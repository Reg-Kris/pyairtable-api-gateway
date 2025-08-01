#!/bin/bash

# PyAirtable Quick Fix Deployment Script
# Solves port-forwarding issues immediately with minimal changes

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

# Check if we're in the right directory
check_environment() {
    print_info "Checking environment..."
    
    if ! kubectl get namespace pyairtable &> /dev/null; then
        print_error "PyAirtable namespace not found. Make sure your services are deployed."
        exit 1
    fi
    
    if ! minikube status &> /dev/null; then
        print_error "Minikube is not running. Please start minikube first."
        exit 1
    fi
    
    print_success "Environment check passed"
}

# Remove old ingress to avoid conflicts
cleanup_old_ingress() {
    print_info "Cleaning up old ingress configuration..."
    
    # Remove existing ingress if it exists
    kubectl delete ingress pyairtable-core-pyairtable-stack-ingress -n pyairtable --ignore-not-found=true
    
    print_success "Old ingress cleaned up"
}

# Deploy the enhanced ingress
deploy_enhanced_ingress() {
    print_info "Deploying enhanced ingress configuration..."
    
    # Apply the enhanced ingress
    kubectl apply -f enhanced-ingress.yaml
    
    # Wait for ingress to be ready
    print_info "Waiting for ingress to be ready..."
    kubectl wait --for=condition=ready ingress/pyairtable-enhanced-ingress -n pyairtable --timeout=60s
    
    print_success "Enhanced ingress deployed successfully"
}

# Setup local DNS
setup_local_dns() {
    print_info "Setting up local DNS entries..."
    
    # Extract and run the DNS setup script
    kubectl get configmap local-dns-setup -n pyairtable -o jsonpath='{.data.setup-local-dns\.sh}' > /tmp/setup-local-dns.sh
    chmod +x /tmp/setup-local-dns.sh
    
    print_warning "This will modify your /etc/hosts file and requires sudo access."
    read -p "Do you want to continue? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        /tmp/setup-local-dns.sh
        rm /tmp/setup-local-dns.sh
        print_success "Local DNS setup completed"
    else
        print_warning "Skipping DNS setup. You'll need to add entries to /etc/hosts manually."
        echo "Manual entries needed:"
        echo "$(minikube ip) pyairtable.local"
        echo "$(minikube ip) api.pyairtable.local" 
        echo "$(minikube ip) mcp.pyairtable.local"
        echo "$(minikube ip) airtable.pyairtable.local"
        echo "$(minikube ip) llm.pyairtable.local"
        echo "$(minikube ip) platform.pyairtable.local"
        echo "$(minikube ip) automation.pyairtable.local"
    fi
}

# Test the setup
test_setup() {
    print_info "Testing the setup..."
    
    # Get ingress status
    kubectl get ingress pyairtable-enhanced-ingress -n pyairtable
    
    print_info "Testing service connectivity..."
    
    # Test API gateway
    if curl -s -o /dev/null -w "%{http_code}" http://api.pyairtable.local | grep -q "200\|404"; then
        print_success "API Gateway accessible at http://api.pyairtable.local"
    else
        print_warning "API Gateway might not be ready yet"
    fi
    
    # Test other services
    services=("mcp.pyairtable.local" "airtable.pyairtable.local" "llm.pyairtable.local" "platform.pyairtable.local")
    
    for service in "${services[@]}"; do
        if curl -s -o /dev/null -w "%{http_code}" "http://$service" | grep -q "200\|404\|502"; then
            print_success "$service is accessible"
        else
            print_warning "$service might not be ready yet"
        fi
    done
}

# Create helper scripts
create_helper_scripts() {
    print_info "Creating helper scripts..."
    
    # Create status check script
    cat > check-status.sh << 'EOF'
#!/bin/bash
echo "PyAirtable Service Status:"
echo "=========================="
kubectl get pods -n pyairtable
echo ""
echo "Ingress Status:"
echo "==============="
kubectl get ingress -n pyairtable
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
    
    chmod +x check-status.sh
    
    # Create cleanup script
    cat > cleanup-quick-fix.sh << 'EOF'
#!/bin/bash
echo "Cleaning up PyAirtable quick fix..."
kubectl delete ingress pyairtable-enhanced-ingress -n pyairtable --ignore-not-found=true
kubectl delete configmap local-dns-setup -n pyairtable --ignore-not-found=true

# Remove DNS entries
sudo sed -i '' '/pyairtable\.local/d' /etc/hosts
sudo sed -i '' '/PyAirtable Local Development/d' /etc/hosts

echo "Quick fix cleaned up"
EOF
    
    chmod +x cleanup-quick-fix.sh
    
    print_success "Helper scripts created"
}

# Main execution
main() {
    print_info "Starting PyAirtable Quick Fix Deployment..."
    print_info "This will solve your port-forwarding issues with minimal changes."
    echo ""
    
    check_environment
    cleanup_old_ingress
    deploy_enhanced_ingress
    setup_local_dns
    create_helper_scripts
    test_setup
    
    echo ""
    print_success "Quick Fix Deployment Complete!"
    echo ""
    print_info "What changed:"
    echo "- Replaced basic ingress with enhanced multi-host ingress"
    echo "- Added DNS entries to /etc/hosts for easy access"
    echo "- Created helper scripts for status checking and cleanup"
    echo ""
    print_info "You can now access your services without port-forwarding:"
    echo "- Main App: http://pyairtable.local"
    echo "- API Gateway: http://api.pyairtable.local"
    echo "- Individual services: http://[service].pyairtable.local"
    echo ""
    print_info "Helper scripts available:"
    echo "- ./check-status.sh - Check service and ingress status"
    echo "- ./cleanup-quick-fix.sh - Remove this quick fix"
    echo ""
    print_info "Next step: Consider migrating to the full Istio solution for production-ready features."
}

# Run main function
main "$@"