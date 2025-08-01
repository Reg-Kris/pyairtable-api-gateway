"""
PyAirtable API Gateway - Refactored with PyAirtableService Base Class
Simple routing service for PyAirtable microservices
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional

import httpx
from fastapi import HTTPException, Request, Depends
from fastapi.responses import JSONResponse

# Add pyairtable-common to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pyairtable-common'))

from pyairtable_common.service import PyAirtableService, ServiceConfig

# Secure configuration and middleware imports
try:
    from pyairtable_common.config import initialize_secrets, get_secret, close_secrets, ConfigurationError
    SECURE_CONFIG_AVAILABLE = True
except ImportError:
    SECURE_CONFIG_AVAILABLE = False


class PyAirtableAPIGatewayService(PyAirtableService):
    """
    PyAirtable API Gateway service extending PyAirtableService base class.
    Routes requests to appropriate microservices.
    """
    
    def __init__(self):
        # Configuration
        self.airtable_gateway_url = os.getenv("AIRTABLE_GATEWAY_URL", "http://localhost:8002")
        self.mcp_server_url = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
        self.llm_orchestrator_url = os.getenv("LLM_ORCHESTRATOR_URL", "http://localhost:8003")
        
        # Initialize secure configuration
        self.config_manager = None
        if SECURE_CONFIG_AVAILABLE:
            try:
                self.config_manager = initialize_secrets()
                api_key = get_secret("API_KEY")
                self.logger.info("✅ Secure configuration manager initialized")
            except Exception as e:
                self.logger.error(f"💥 Failed to initialize secure configuration: {e}")
                raise
        else:
            api_key = os.getenv("API_KEY")
            if not api_key:
                self.logger.error("💥 CRITICAL: API_KEY environment variable is required")
                raise ValueError("API_KEY environment variable is required")
        
        # Initialize service configuration
        config = ServiceConfig(
            title="PyAirtable API Gateway",
            description="Central entry point for PyAirtable microservices",
            version="1.0.0",
            service_name="api-gateway",
            port=int(os.getenv("PORT", 8000)),
            api_key=api_key,
            rate_limit_calls=1000,  # Higher rate limit for gateway
            rate_limit_period=60,
            startup_tasks=[self._initialize_http_client, self._log_service_urls],
            shutdown_tasks=[self._close_http_client, self._close_secrets],
            health_check_dependencies=[self._check_services_health]
        )
        
        super().__init__(config)
        
        # HTTP client for service communication
        self.http_client: Optional[httpx.AsyncClient] = None
        self.health_check_timeout = int(os.getenv("HEALTH_CHECK_TIMEOUT", "5"))
        
        # Setup routes
        self._setup_gateway_routes()
    
    async def _initialize_http_client(self) -> None:
        """Initialize HTTP client for service communication."""
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.logger.info("✅ HTTP client initialized")
    
    async def _log_service_urls(self) -> None:
        """Log service URLs for debugging."""
        self.logger.info(f"Routing to services:")
        self.logger.info(f"  - Airtable Gateway: {self.airtable_gateway_url}")
        self.logger.info(f"  - MCP Server: {self.mcp_server_url}")
        self.logger.info(f"  - LLM Orchestrator: {self.llm_orchestrator_url}")
    
    async def _close_http_client(self) -> None:
        """Close HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
            self.logger.info("✅ HTTP client closed")
    
    async def _close_secrets(self) -> None:
        """Close secure configuration manager."""
        if self.config_manager:
            await close_secrets()
            self.logger.info("✅ Closed secure configuration manager")
    
    async def _check_service_health(self, service_url: str, service_name: str) -> Dict[str, Any]:
        """Check health of a specific service"""
        try:
            if not self.http_client:
                return {
                    "name": service_name,
                    "status": "error",
                    "error": "HTTP client not initialized"
                }
            
            response = await self.http_client.get(
                f"{service_url}/health",
                timeout=self.health_check_timeout
            )
            if response.status_code == 200:
                return {
                    "name": service_name,
                    "status": "healthy",
                    "url": service_url,
                    "response_time": response.elapsed.total_seconds()
                }
            else:
                return {
                    "name": service_name,
                    "status": "unhealthy",
                    "url": service_url,
                    "error": f"HTTP {response.status_code}"
                }
        except Exception as e:
            return {
                "name": service_name,
                "status": "unreachable",
                "url": service_url,
                "error": str(e)
            }
    
    async def _check_services_health(self) -> Dict[str, Any]:
        """Check health of all dependent services."""
        services = [
            (self.airtable_gateway_url, "airtable-gateway"),
            (self.mcp_server_url, "mcp-server"),
            (self.llm_orchestrator_url, "llm-orchestrator")
        ]
        
        # Check all services concurrently
        health_checks = [
            self._check_service_health(url, name) for url, name in services
        ]
        results = await asyncio.gather(*health_checks, return_exceptions=True)
        
        # Process results
        service_status = []
        overall_healthy = True
        
        for result in results:
            if isinstance(result, Exception):
                service_status.append({
                    "name": "unknown",
                    "status": "error", 
                    "error": str(result)
                })
                overall_healthy = False
            else:
                service_status.append(result)
                if result["status"] != "healthy":
                    overall_healthy = False
        
        return {
            "name": "dependent_services",
            "status": "healthy" if overall_healthy else "degraded",
            "services": service_status
        }
    
    def _setup_gateway_routes(self) -> None:
        """Setup API Gateway specific routes."""
        
        @self.app.get("/")
        async def root():
            """Root endpoint"""
            return {
                "service": "PyAirtable API Gateway",
                "version": "1.0.0",
                "endpoints": {
                    "health": "/api/health",
                    "chat": "/api/chat",
                    "tools": "/api/tools",
                    "airtable": "/api/airtable/*"
                }
            }

        @self.app.post("/api/chat")
        async def chat_proxy(request: Request, authenticated: bool = Depends(self.verify_api_key)):
            """Proxy chat requests to LLM Orchestrator"""
            try:
                # Get request body
                body = await request.json()
                
                # Forward to LLM Orchestrator
                response = await self.http_client.post(
                    f"{self.llm_orchestrator_url}/chat",
                    json=body,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                self.logger.error(f"LLM Orchestrator error: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except Exception as e:
                self.logger.error(f"Chat proxy error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/tools")
        async def tools_proxy(authenticated: bool = Depends(self.verify_api_key)):
            """Proxy tools requests to LLM Orchestrator"""
            try:
                response = await self.http_client.get(f"{self.llm_orchestrator_url}/tools")
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                self.logger.error(f"Tools proxy error: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except Exception as e:
                self.logger.error(f"Tools proxy error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.api_route("/api/airtable/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"])
        async def airtable_proxy(
            path: str,
            request: Request,
            authenticated: bool = Depends(self.verify_api_key)
        ):
            """Proxy Airtable requests to Airtable Gateway"""
            try:
                # Build target URL
                target_url = f"{self.airtable_gateway_url}/{path}"
                
                # Get request body if present
                body = None
                if request.method in ["POST", "PATCH", "PUT"]:
                    body = await request.json()
                
                # Forward request
                response = await self.http_client.request(
                    method=request.method,
                    url=target_url,
                    json=body,
                    params=dict(request.query_params),
                    headers={"X-API-Key": self.config.api_key}  # Use gateway's API key
                )
                response.raise_for_status()
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                self.logger.error(f"Airtable Gateway error: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except Exception as e:
                self.logger.error(f"Airtable proxy error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/execute-tool")
        async def execute_tool_proxy(request: Request, authenticated: bool = Depends(self.verify_api_key)):
            """Proxy tool execution to LLM Orchestrator"""
            try:
                body = await request.json()
                
                response = await self.http_client.post(
                    f"{self.llm_orchestrator_url}/execute-tool",
                    json=body,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                
                return response.json()
                
            except httpx.HTTPStatusError as e:
                self.logger.error(f"Tool execution proxy error: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except Exception as e:
                self.logger.error(f"Tool execution proxy error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/sessions/{session_id}/history")
        async def session_history_proxy(session_id: str, authenticated: bool = Depends(self.verify_api_key)):
            """Proxy session history requests"""
            try:
                response = await self.http_client.get(f"{self.llm_orchestrator_url}/sessions/{session_id}/history")
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                self.logger.error(f"Session history proxy error: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except Exception as e:
                self.logger.error(f"Session history proxy error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/api/sessions/{session_id}")
        async def clear_session_proxy(session_id: str, authenticated: bool = Depends(self.verify_api_key)):
            """Proxy clear session requests"""
            try:
                response = await self.http_client.delete(f"{self.llm_orchestrator_url}/sessions/{session_id}")
                response.raise_for_status()
                return response.json()
                
            except httpx.HTTPStatusError as e:
                self.logger.error(f"Clear session proxy error: {e}")
                raise HTTPException(status_code=e.response.status_code, detail=str(e))
            except Exception as e:
                self.logger.error(f"Clear session proxy error: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # Error handlers
        @self.app.exception_handler(404)
        async def not_found_handler(request: Request, exc: HTTPException):
            return JSONResponse(
                status_code=404,
                content={
                    "error": "Endpoint not found",
                    "path": str(request.url.path),
                    "available_endpoints": [
                        "/api/health",
                        "/api/chat", 
                        "/api/tools",
                        "/api/airtable/*",
                        "/api/execute-tool",
                        "/api/sessions/{session_id}/history"
                    ]
                }
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Custom health check for API Gateway."""
        return {
            "http_client": "ready" if self.http_client else "not_initialized",
            "service_urls": {
                "airtable_gateway": self.airtable_gateway_url,
                "mcp_server": self.mcp_server_url,
                "llm_orchestrator": self.llm_orchestrator_url
            }
        }


def create_api_gateway_service() -> PyAirtableAPIGatewayService:
    """Factory function to create API Gateway service."""
    return PyAirtableAPIGatewayService()


if __name__ == "__main__":
    service = create_api_gateway_service()
    service.run()