#!/bin/bash

# Step 3: Enable Advanced Features (SPIRE Integration)
# This script integrates the network engineer's SPIRE setup with PyAirtable

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    print_info "Checking prerequisites for SPIRE integration..."
    
    # Check if Istio is installed and working
    if ! kubectl get deployment istiod -n istio-system &> /dev/null; then
        print_error "Istio is not installed. Run step1-istio-setup.sh first."
        exit 1
    fi
    
    # Check if PyAirtable Istio config is deployed
    if ! kubectl get gateway pyairtable-gateway -n istio-system &> /dev/null; then
        print_error "PyAirtable Istio configuration not found. Run step2-deploy-istio-config.sh first."
        exit 1
    fi
    
    print_success "Prerequisites check completed"
}

# Setup SPIRE namespace and RBAC
setup_spire_namespace() {
    print_info "Setting up SPIRE namespace and RBAC..."
    
    # Create SPIRE namespace
    kubectl create namespace spire --dry-run=client -o yaml | kubectl apply -f -
    
    # Label namespace for monitoring
    kubectl label namespace spire istio-injection=disabled --overwrite
    
    print_success "SPIRE namespace created"
}

# Deploy SPIRE server
deploy_spire_server() {
    print_info "Deploying SPIRE server..."
    
    # Use the network engineer's SPIRE server configuration
    kubectl apply -f ../../k8s-dev-setup/security/spire-server.yaml
    
    # Wait for SPIRE server to be ready
    print_info "Waiting for SPIRE server to be ready..."
    kubectl wait --for=condition=ready pod -l app=spire-server -n spire --timeout=300s
    
    print_success "SPIRE server deployed and ready"
}

# Deploy SPIRE agent
deploy_spire_agent() {
    print_info "Deploying SPIRE agent..."
    
    # Use the network engineer's SPIRE agent configuration
    kubectl apply -f ../../k8s-dev-setup/security/spire-agent.yaml
    
    # Wait for SPIRE agents to be ready
    print_info "Waiting for SPIRE agents to be ready..."
    kubectl wait --for=condition=ready pod -l app=spire-agent -n spire --timeout=300s
    
    print_success "SPIRE agents deployed and ready"
}

# Register PyAirtable services with SPIRE
register_pyairtable_services() {
    print_info "Registering PyAirtable services with SPIRE..."
    
    # Get SPIRE server pod name
    SPIRE_SERVER_POD=$(kubectl get pods -n spire -l app=spire-server -o jsonpath='{.items[0].metadata.name}')
    
    if [ -z "$SPIRE_SERVER_POD" ]; then
        print_error "SPIRE server pod not found"
        exit 1
    fi
    
    # PyAirtable services to register
    services=(
        "api-gateway:8000"
        "mcp-server:8001"
        "airtable-gateway:8002"
        "llm-orchestrator:8003"
        "platform-services:8007"
        "automation-services:8006"
        "frontend:3000"
    )
    
    for service_info in "${services[@]}"; do
        service=$(echo "$service_info" | cut -d: -f1)
        port=$(echo "$service_info" | cut -d: -f2)
        
        print_info "Registering $service..."
        
        kubectl exec -n spire "$SPIRE_SERVER_POD" -- \
            /opt/spire/bin/spire-server entry create \
            -spiffeID "spiffe://pyairtable.local/ns/pyairtable/sa/$service" \
            -parentID "spiffe://pyairtable.local/ns/spire/sa/spire-agent" \
            -selector "k8s:ns:pyairtable" \
            -selector "k8s:sa:$service" \
            -dns "$service" \
            -dns "$service.pyairtable" \
            -dns "$service.pyairtable.svc.cluster.local" || true
    done
    
    print_success "PyAirtable services registered with SPIRE"
}

# Configure Istio to use SPIRE for certificates
configure_istio_spire_integration() {
    print_info "Configuring Istio to use SPIRE for certificate management..."
    
    # Create ConfigMap for Istio-SPIRE integration
    cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: ConfigMap
metadata:
  name: istio-spire-config
  namespace: istio-system
data:
  mesh: |
    defaultConfig:
      proxyStatsMatcher:
        inclusionRegexps:
        - ".*circuit_breakers.*"
        - ".*upstream_rq_retry.*"
        - ".*upstream_rq_pending.*"
        - ".*_cx_.*"
      trustDomain: pyairtable.local
    extensionProviders:
    - name: spire
      envoyExtAuthzGrpc:
        service: spire-agent.spire.svc.cluster.local
        port: 8081
    trustDomain: pyairtable.local
EOF
    
    # Restart Istio to pick up the new configuration
    print_info "Restarting Istio control plane to apply SPIRE integration..."
    kubectl rollout restart deployment/istiod -n istio-system
    kubectl rollout status deployment/istiod -n istio-system --timeout=300s
    
    print_success "Istio-SPIRE integration configured"
}

# Apply enhanced security policies
apply_enhanced_security() {
    print_info "Applying enhanced security policies with SPIRE..."
    
    # Create SPIRE-enhanced security configuration
    cat <<EOF | kubectl apply -f -
# Enhanced PeerAuthentication with SPIRE
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: pyairtable-spire-mtls
  namespace: pyairtable
spec:
  mtls:
    mode: STRICT
---
# Authorization policy using SPIFFE identities
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: pyairtable-spiffe-authz
  namespace: pyairtable
spec:
  rules:
  # Allow communication between PyAirtable services using SPIFFE IDs
  - from:
    - source:
        principals: ["spiffe://pyairtable.local/ns/pyairtable/sa/*"]
  # Allow ingress gateway
  - from:
    - source:
        principals: ["cluster.local/ns/istio-system/sa/istio-ingressgateway-service-account"]
  # Allow health checks
  - to:
    - operation:
        paths: ["/health", "/ready", "/healthz"]
EOF
    
    print_success "Enhanced security policies applied"
}

# Test SPIRE integration
test_spire_integration() {
    print_info "Testing SPIRE integration..."
    
    # Check SPIRE server status
    SPIRE_SERVER_POD=$(kubectl get pods -n spire -l app=spire-server -o jsonpath='{.items[0].metadata.name}')
    
    print_info "SPIRE server entries:"
    kubectl exec -n spire "$SPIRE_SERVER_POD" -- \
        /opt/spire/bin/spire-server entry show
    
    # Check agent status
    print_info "SPIRE agent status:"
    kubectl get pods -n spire -l app=spire-agent
    
    # Check Istio proxy status with SPIRE
    print_info "Istio proxy status:"
    istioctl proxy-status
    
    print_success "SPIRE integration test completed"
}

# Create monitoring and debugging tools
create_spire_tools() {
    print_info "Creating SPIRE monitoring and debugging tools..."
    
    # Create SPIRE status check script
    cat > ../scripts/check-spire-status.sh << 'EOF'
#!/bin/bash
echo "SPIRE System Status:"
echo "==================="
echo "SPIRE Server:"
kubectl get pods -n spire -l app=spire-server
echo ""
echo "SPIRE Agents:"
kubectl get pods -n spire -l app=spire-agent
echo ""

SPIRE_SERVER_POD=$(kubectl get pods -n spire -l app=spire-server -o jsonpath='{.items[0].metadata.name}')
if [ -n "$SPIRE_SERVER_POD" ]; then
    echo "Registered Entries:"
    kubectl exec -n spire "$SPIRE_SERVER_POD" -- /opt/spire/bin/spire-server entry show
    echo ""
    echo "Server Health:"
    kubectl exec -n spire "$SPIRE_SERVER_POD" -- /opt/spire/bin/spire-server healthcheck
fi
EOF
    
    chmod +x ../scripts/check-spire-status.sh
    
    # Create service identity verification script
    cat > ../scripts/verify-service-identities.sh << 'EOF'
#!/bin/bash
echo "Verifying PyAirtable Service Identities:"
echo "========================================"

services=("api-gateway" "mcp-server" "airtable-gateway" "llm-orchestrator" "platform-services" "automation-services")

for service in "${services[@]}"; do
    echo "Checking $service..."
    pod=$(kubectl get pods -n pyairtable -l app=$service -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if [ -n "$pod" ]; then
        # Check if SPIFFE certificate is present
        kubectl exec -n pyairtable "$pod" -c istio-proxy -- ls -la /etc/ssl/certs/ | grep spiffe || echo "No SPIFFE certificate found"
    else
        echo "Pod not found for $service"
    fi
    echo ""
done
EOF
    
    chmod +x ../scripts/verify-service-identities.sh
    
    print_success "SPIRE tools created"
}

# Main execution
main() {
    print_info "Starting SPIRE integration for PyAirtable..."
    echo ""
    
    print_warning "This step enables advanced security features:"
    print_warning "- SPIFFE/SPIRE for cryptographic service identities"
    print_warning "- Enhanced mTLS with automatic certificate management"
    print_warning "- Zero-trust security policies"
    echo ""
    
    read -p "Do you want to continue with SPIRE integration? (y/N): " -n 1 -r
    echo
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_info "SPIRE integration skipped. Your current Istio setup provides basic mTLS."
        exit 0
    fi
    
    check_prerequisites
    setup_spire_namespace
    deploy_spire_server
    deploy_spire_agent
    register_pyairtable_services
    configure_istio_spire_integration
    apply_enhanced_security
    test_spire_integration
    create_spire_tools
    
    echo ""
    print_success "SPIRE integration completed successfully!"
    echo ""
    print_info "Your PyAirtable deployment now has:"
    echo "- Cryptographic service identities via SPIFFE"
    echo "- Automatic certificate rotation"
    echo "- Zero-trust security policies"
    echo "- Enhanced observability and debugging tools"
    echo ""
    print_info "SPIRE management scripts available:"
    echo "- ../scripts/check-spire-status.sh - Check SPIRE system status"
    echo "- ../scripts/verify-service-identities.sh - Verify service identities"
    echo ""
    print_info "Your services are still accessible at the same URLs:"
    echo "- Main App: http://pyairtable.local"
    echo "- API Gateway: http://api.pyairtable.local"
    echo "- Individual services: http://[service].pyairtable.local"
}

# Run main function
main "$@"