#!/usr/bin/env python3
"""
Example Python service client with SPIFFE/mTLS integration
This shows how services can authenticate to each other using SPIFFE identities
"""

import os
import json
import requests
import jwt
from datetime import datetime, timedelta
from pyspiffe import WorkloadApiClient, X509Source
from pyspiffe.spiffe_id import SpiffeId
import ssl
import urllib3
from urllib3.util import ssl_
from requests.adapters import HTTPAdapter

class SPIFFEHTTPAdapter(HTTPAdapter):
    """Custom HTTP adapter that uses SPIFFE X.509 certificates for mTLS"""
    
    def __init__(self, x509_source: X509Source):
        self.x509_source = x509_source
        super().__init__()
    
    def init_poolmanager(self, *args, **kwargs):
        # Get current SPIFFE certificate and private key
        x509_svid = self.x509_source.get_x509_svid()
        
        # Create SSL context with SPIFFE certificates
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        
        # Load the trust bundle (root CAs)
        for cert in self.x509_source.get_x509_bundle_for_trust_domain(
            SpiffeId.parse("spiffe://dev.local").trust_domain
        ).x509_authorities:
            ssl_context.load_verify_locations(cadata=cert.public_bytes(
                encoding=serialization.Encoding.PEM
            ).decode())
        
        # Load client certificate for mutual TLS
        ssl_context.load_cert_chain(
            certfile=x509_svid.cert_chain_pem(),
            keyfile=x509_svid.private_key_pem()
        )
        
        kwargs['ssl_context'] = ssl_context
        return super().init_poolmanager(*args, **kwargs)

class ServiceClient:
    """Service client with SPIFFE-based mTLS and JWT authentication"""
    
    def __init__(self, service_name: str, spiffe_socket_path: str = None):
        self.service_name = service_name
        self.spiffe_socket_path = spiffe_socket_path or os.getenv(
            'SPIFFE_ENDPOINT_SOCKET', 
            'unix:///run/spire/sockets/agent.sock'
        )
        self.trust_domain = os.getenv('TRUST_DOMAIN', 'dev.local')
        
        # Initialize SPIFFE X.509 source
        self.x509_source = None
        self._setup_spiffe_client()
        
        # Create HTTP session with SPIFFE adapter
        self.session = requests.Session()
        if self.x509_source:
            self.session.mount('https://', SPIFFEHTTPAdapter(self.x509_source))
        
        # JWT token for external authentication
        self.jwt_token = None
        self.jwt_expiry = None
        
    def _setup_spiffe_client(self):
        """Initialize SPIFFE workload API client"""
        try:
            # Create X.509 source from SPIFFE workload API
            self.x509_source = X509Source.from_workload_api(
                workload_api_client=WorkloadApiClient(self.spiffe_socket_path)
            )
            print(f"SPIFFE identity initialized for {self.service_name}")
        except Exception as e:
            print(f"Warning: Could not initialize SPIFFE client: {e}")
            print("Falling back to standard HTTPS without mTLS")
    
    def get_service_identity(self) -> str:
        """Get the current service's SPIFFE identity"""
        if self.x509_source:
            svid = self.x509_source.get_x509_svid()
            return str(svid.spiffe_id)
        return f"spiffe://{self.trust_domain}/ns/default/sa/{self.service_name}"
    
    def authenticate_with_auth_service(self, username: str, password: str) -> str:
        """Authenticate with the auth service and get JWT token"""
        auth_url = os.getenv('AUTH_SERVICE_URL', 'https://auth-service:8080')
        
        response = self.session.post(f"{auth_url}/auth/login", json={
            'username': username,
            'password': password,
            'service_identity': self.get_service_identity()
        })
        
        if response.status_code == 200:
            token_data = response.json()
            self.jwt_token = token_data['access_token']
            
            # Parse token to get expiry
            decoded = jwt.decode(
                self.jwt_token, 
                options={"verify_signature": False}
            )
            self.jwt_expiry = datetime.fromtimestamp(decoded['exp'])
            
            return self.jwt_token
        else:
            raise Exception(f"Authentication failed: {response.text}")
    
    def is_token_valid(self) -> bool:
        """Check if current JWT token is valid"""
        if not self.jwt_token or not self.jwt_expiry:
            return False
        return datetime.now() < self.jwt_expiry - timedelta(minutes=5)
    
    def get_auth_headers(self) -> dict:
        """Get authentication headers for requests"""
        headers = {
            'X-Service-Identity': self.get_service_identity(),
            'Content-Type': 'application/json'
        }
        
        if self.jwt_token and self.is_token_valid():
            headers['Authorization'] = f'Bearer {self.jwt_token}'
        
        return headers
    
    def call_service(self, service_name: str, endpoint: str, method: str = 'GET', data: dict = None) -> dict:
        """Make authenticated call to another service"""
        # Determine service URL based on service discovery
        if '.' in service_name:
            # Fully qualified domain name
            service_url = f"https://{service_name}"
        else:
            # Service name only - use cluster DNS
            service_url = f"https://{service_name}:8080"
        
        url = f"{service_url}{endpoint}"
        headers = self.get_auth_headers()
        
        # Make the request with mTLS if available
        response = self.session.request(
            method=method,
            url=url,
            headers=headers,
            json=data if method in ['POST', 'PUT', 'PATCH'] else None,
            timeout=30
        )
        
        if response.status_code >= 400:
            raise Exception(f"Service call failed: {response.status_code} - {response.text}")
        
        return response.json() if response.text else {}
    
    def health_check(self) -> dict:
        """Perform health check on this service"""
        return {
            'service': self.service_name,
            'spiffe_identity': self.get_service_identity(),
            'jwt_valid': self.is_token_valid(),
            'timestamp': datetime.now().isoformat()
        }

# Example usage
if __name__ == "__main__":
    # Initialize service client
    client = ServiceClient("user-service")
    
    # Authenticate if needed (for testing)
    try:
        # This would typically be done with service account credentials
        token = client.authenticate_with_auth_service("service-user", "service-password")
        print(f"Authenticated successfully")
    except Exception as e:
        print(f"Authentication not needed or failed: {e}")
    
    # Example service-to-service calls
    try:
        # Call auth service to validate a token
        auth_result = client.call_service(
            "auth-service", 
            "/auth/validate", 
            "POST", 
            {"token": "user-jwt-token"}
        )
        print(f"Auth validation result: {auth_result}")
        
        # Call order service
        orders = client.call_service("order-service", "/orders/user/123")
        print(f"User orders: {orders}")
        
        # Call inventory service
        inventory = client.call_service("inventory-service", "/inventory/product/456")
        print(f"Product inventory: {inventory}")
        
    except Exception as e:
        print(f"Service call failed: {e}")
    
    # Health check
    health = client.health_check()
    print(f"Health check: {json.dumps(health, indent=2)}")