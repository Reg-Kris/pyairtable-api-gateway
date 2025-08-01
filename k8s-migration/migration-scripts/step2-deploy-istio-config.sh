#!/bin/bash

# Step 2: Deploy PyAirtable Istio Configuration
# This script applies the PyAirtable-specific Istio gateway and security configuration

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
    print_info "Checking prerequisites..."
    
    # Check if Istio is installed
    if ! kubectl get namespace istio-system &> /dev/null; then
        print_error "Istio is not installed. Run step1-istio-setup.sh first."
        exit 1
    fi
    
    # Check if istiod is running
    if ! kubectl get deployment istiod -n istio-system &> /dev/null; then
        print_error "Istio control plane is not running. Run step1-istio-setup.sh first."
        exit 1
    fi
    
    # Check if PyAirtable namespace has Istio injection enabled
    if ! kubectl get namespace pyairtable -o jsonpath='{.metadata.labels.istio-injection}' | grep -q "enabled"; then
        print_warning "PyAirtable namespace doesn't have Istio injection enabled. Enabling now..."
        kubectl label namespace pyairtable istio-injection=enabled --overwrite
    fi
    
    print_success "Prerequisites check completed"
}

# Remove existing ingress to avoid conflicts
cleanup_existing_ingress() {
    print_info "Cleaning up existing ingress configurations..."
    
    # Remove nginx ingress if it exists
    kubectl delete ingress --all -n pyairtable --ignore-not-found=true
    
    # Remove any existing Istio configurations
    kubectl delete gateway --all -n pyairtable --ignore-not-found=true
    kubectl delete virtualservice --all -n pyairtable --ignore-not-found=true
    kubectl delete destinationrule --all -n pyairtable --ignore-not-found=true
    kubectl delete authorizationpolicy --all -n pyairtable --ignore-not-found=true
    kubectl delete peerauthentication --all -n pyairtable --ignore-not-found=true
    
    print_success "Existing configurations cleaned up"
}

# Deploy Istio gateway configuration
deploy_istio_gateway() {
    print_info "Deploying PyAirtable Istio gateway configuration..."
    
    # Apply the gateway configuration
    kubectl apply -f ../istio-integration/pyairtable-istio-gateway.yaml
    
    # Wait for gateway to be ready
    print_info "Waiting for gateway configuration to be applied..."
    sleep 10
    
    print_success "Istio gateway configuration deployed"
}

# Deploy security configuration (optional, with user confirmation)
deploy_security_config() {
    print_info "Security configuration is available but optional for development."
    print_warning "Security policies will enable strict mTLS and authorization."
    
    read -p "Do you want to apply security policies? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        print_info "Deploying security configuration..."
        kubectl apply -f ../istio-integration/pyairtable-security.yaml
        print_success "Security configuration deployed"
        
        print_warning "Note: Strict mTLS is now enabled. All services must communicate through Istio."
    else
        print_info "Skipping security configuration. You can apply it later if needed."
    fi
}

# Setup local DNS for Istio
setup_local_dns() {
    print_info "Setting up local DNS for Istio gateway..."
    
    # Get ingress gateway external IP/port
    INGRESS_HOST=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}')
    
    # For minikube, we need to use the minikube IP
    if [ -z "$INGRESS_HOST" ]; then
        INGRESS_HOST=$(minikube ip)
        print_info "Using minikube IP: $INGRESS_HOST"
    fi
    
    INGRESS_PORT=$(kubectl -n istio-system get service istio-ingressgateway -o jsonpath='{.spec.ports[?(@.name=="http2")].nodePort}')
    
    print_warning "This will modify your /etc/hosts file and requires sudo access."
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Backup existing hosts file
        sudo cp /etc/hosts /etc/hosts.backup.istio.$(date +%Y%m%d_%H%M%S)
        
        # Remove existing pyairtable.local entries
        sudo sed -i '' '/pyairtable\.local/d' /etc/hosts
        
        # Add new entries
        echo "# PyAirtable Istio Gateway - Migration Step 2" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST pyairtable.local" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST api.pyairtable.local" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST mcp.pyairtable.local" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST airtable.pyairtable.local" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST llm.pyairtable.local" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST platform.pyairtable.local" | sudo tee -a /etc/hosts
        echo "$INGRESS_HOST automation.pyairtable.local" | sudo tee -a /etc/hosts
        
        print_success "Local DNS configured for Istio gateway"
    else
        print_warning "Skipping DNS setup. You'll need to add entries to /etc/hosts manually:"
        echo "$INGRESS_HOST pyairtable.local"
        echo "$INGRESS_HOST api.pyairtable.local"
        echo "$INGRESS_HOST mcp.pyairtable.local"
        echo "$INGRESS_HOST airtable.pyairtable.local"
        echo "$INGRESS_HOST llm.pyairtable.local"
        echo "$INGRESS_HOST platform.pyairtable.local"
        echo "$INGRESS_HOST automation.pyairtable.local"
    fi
    
    # Store connection info for later use
    echo "export INGRESS_HOST=$INGRESS_HOST" > ../config/istio-connection.env
    echo "export INGRESS_PORT=$INGRESS_PORT" >> ../config/istio-connection.env
}

# Test the configuration
test_configuration() {
    print_info "Testing Istio configuration..."
    
    # Wait a bit for configuration to propagate
    print_info "Waiting for configuration to propagate..."
    sleep 30
    
    # Test gateway status
    print_info "Checking gateway status..."
    kubectl get gateway -n istio-system
    kubectl get virtualservice -n pyairtable
    kubectl get destinationrule -n pyairtable
    
    # Test connectivity
    print_info "Testing service connectivity through Istio gateway..."
    
    # Get ingress info
    source ../config/istio-connection.env 2>/dev/null || true
    
    if [ -n "$INGRESS_HOST" ]; then
        # Test API gateway
        if curl -s -o /dev/null -w "%{http_code}" -H "Host: api.pyairtable.local" "http://$INGRESS_HOST" | grep -q "200\|404"; then
            print_success "API Gateway accessible through Istio"
        else
            print_warning "API Gateway might not be ready yet"
        fi
        
        # Test other services
        services=("mcp.pyairtable.local" "airtable.pyairtable.local" "llm.pyairtable.local")
        
        for service in "${services[@]}"; do
            if curl -s -o /dev/null -w "%{http_code}" -H "Host: $service" "http://$INGRESS_HOST" | grep -q "200\|404\|502"; then
                print_success "$service accessible through Istio"
            else
                print_warning "$service might not be ready yet"
            fi
        done
    else
        print_warning "Could not determine ingress host. Manual testing required."
    fi
}

# Create helper scripts
create_helper_scripts() {
    print_info "Creating helper scripts for Istio management..."
    
    # Create gateway status script
    cat > ../scripts/check-gateway-status.sh << 'EOF'
#!/bin/bash
echo "Istio Gateway Status:"
echo "===================="
kubectl get gateway -n istio-system
echo ""
echo "Virtual Services:"
echo "================"
kubectl get virtualservice -n pyairtable
echo ""
echo "Destination Rules:"
echo "=================="
kubectl get destinationrule -n pyairtable
echo ""
echo "Ingress Gateway Info:"
echo "===================="
kubectl get svc istio-ingressgateway -n istio-system
echo ""
echo "Available URLs:"
echo "==============="
echo "- Main App: http://pyairtable.local"
echo "- API Gateway: http://api.pyairtable.local"
echo "- MCP Server: http://mcp.pyairtable.local"
echo "- Airtable Gateway: http://airtable.pyairtable.local"
echo "- LLM Orchestrator: http://llm.pyairtable.local"
echo "- Platform Services: http://platform.pyairtable.local"
echo "- Automation Services: http://automation.pyairtable.local"
EOF
    
    chmod +x ../scripts/check-gateway-status.sh
    
    # Create traffic analysis script
    cat > ../scripts/analyze-traffic.sh << 'EOF'
#!/bin/bash
echo "Analyzing Istio traffic for PyAirtable..."
echo "========================================"
istioctl analyze -n pyairtable

echo ""
echo "Proxy Configuration:"
echo "==================="
istioctl proxy-config cluster -n pyairtable

echo ""
echo "Traffic Distribution:"
echo "===================="
kubectl top pods -n pyairtable
EOF
    
    chmod +x ../scripts/analyze-traffic.sh
    
    print_success "Helper scripts created"
}

# Main execution
main() {
    print_info "Starting PyAirtable Istio configuration deployment..."
    echo ""
    
    check_prerequisites
    cleanup_existing_ingress
    deploy_istio_gateway
    deploy_security_config
    setup_local_dns
    test_configuration
    create_helper_scripts
    
    echo ""
    print_success "PyAirtable Istio configuration deployed successfully!"
    echo ""
    print_info "Your services are now accessible through Istio gateway:"
    echo "- Main App: http://pyairtable.local"
    echo "- API Gateway: http://api.pyairtable.local"
    echo "- Individual services: http://[service].pyairtable.local"
    echo ""
    print_info "Helper scripts available:"
    echo "- ../scripts/check-gateway-status.sh - Check gateway and routing status"
    echo "- ../scripts/analyze-traffic.sh - Analyze traffic and configuration"
    echo "- ../scripts/start-observability.sh - Start monitoring tools"
    echo ""
    print_info "Next steps:"
    echo "1. Test your services through the new Istio gateway"
    echo "2. Run step3-enable-advanced-features.sh for SPIRE integration (optional)"
    echo "3. Monitor traffic using Kiali and other observability tools"
}

# Run main function
main "$@"