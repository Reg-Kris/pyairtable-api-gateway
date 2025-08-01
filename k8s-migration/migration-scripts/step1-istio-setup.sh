#!/bin/bash

# Step 1: Istio Setup for PyAirtable Migration
# This script sets up Istio service mesh for your PyAirtable deployment

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
    print_info "Checking prerequisites for Istio setup..."
    
    if ! command -v istioctl &> /dev/null; then
        print_warning "istioctl not found. Installing Istio..."
        install_istio
    else
        print_success "istioctl found"
    fi
    
    if ! kubectl get namespace pyairtable &> /dev/null; then
        print_error "PyAirtable namespace not found. Deploy PyAirtable services first."
        exit 1
    fi
    
    print_success "Prerequisites check completed"
}

# Install Istio
install_istio() {
    print_info "Installing Istio..."
    
    # Download and install Istio
    curl -L https://istio.io/downloadIstio | sh -
    
    # Find the latest istio directory
    ISTIO_DIR=$(find . -name "istio-*" -type d | sort -V | tail -n 1)
    
    if [ -z "$ISTIO_DIR" ]; then
        print_error "Failed to find Istio installation directory"
        exit 1
    fi
    
    # Add to PATH
    export PATH="$PWD/$ISTIO_DIR/bin:$PATH"
    
    # Make permanent by adding to shell profile
    echo "export PATH=\"$PWD/$ISTIO_DIR/bin:\$PATH\"" >> ~/.bashrc
    echo "export PATH=\"$PWD/$ISTIO_DIR/bin:\$PATH\"" >> ~/.zshrc 2>/dev/null || true
    
    print_success "Istio downloaded and PATH updated"
}

# Install Istio in cluster
install_istio_cluster() {
    print_info "Installing Istio in cluster..."
    
    # Install Istio with demo profile for development
    istioctl install --set values.defaultRevision=default -y
    
    # Enable sidecar injection for pyairtable namespace
    kubectl label namespace pyairtable istio-injection=enabled --overwrite
    
    print_success "Istio installed in cluster"
}

# Install Istio addons
install_istio_addons() {
    print_info "Installing Istio observability addons..."
    
    # Wait for Istio to be ready
    kubectl wait --for=condition=available deployment/istiod -n istio-system --timeout=300s
    
    # Install addons
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/prometheus.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/grafana.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/jaeger.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/kiali.yaml
    
    # Wait for addons to be ready
    print_info "Waiting for addons to be ready..."
    kubectl wait --for=condition=available deployment/prometheus -n istio-system --timeout=180s
    kubectl wait --for=condition=available deployment/grafana -n istio-system --timeout=180s
    kubectl wait --for=condition=available deployment/jaeger -n istio-system --timeout=180s
    kubectl wait --for=condition=available deployment/kiali -n istio-system --timeout=180s
    
    print_success "Istio addons installed and ready"
}

# Create development certificates
create_dev_certificates() {
    print_info "Creating development TLS certificates..."
    
    # Create certificates directory
    mkdir -p ../certs
    
    # Generate root CA
    openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 \
        -subj '/O=PyAirtable Dev/CN=pyairtable.local' \
        -keyout ../certs/root-ca.key \
        -out ../certs/root-ca.crt
    
    # Generate certificate for pyairtable.local
    openssl req -out ../certs/pyairtable.local.csr -newkey rsa:2048 -nodes \
        -keyout ../certs/pyairtable.local.key \
        -subj "/CN=*.pyairtable.local/O=PyAirtable Dev"
    
    openssl x509 -req -days 365 -CA ../certs/root-ca.crt -CAkey ../certs/root-ca.key \
        -set_serial 0 -in ../certs/pyairtable.local.csr -out ../certs/pyairtable.local.crt \
        -extensions v3_req -extfile <(echo -e "subjectAltName=DNS:*.pyairtable.local,DNS:pyairtable.local")
    
    # Create Kubernetes secret
    kubectl create secret tls pyairtable-local-tls \
        --key=../certs/pyairtable.local.key \
        --cert=../certs/pyairtable.local.crt \
        -n istio-system --dry-run=client -o yaml | kubectl apply -f -
    
    print_success "Development certificates created"
}

# Restart PyAirtable pods to inject sidecars
restart_pyairtable_pods() {
    print_info "Restarting PyAirtable pods to inject Istio sidecars..."
    
    # Get all deployments in pyairtable namespace
    deployments=$(kubectl get deployments -n pyairtable -o jsonpath='{.items[*].metadata.name}')
    
    for deployment in $deployments; do
        print_info "Restarting deployment: $deployment"
        kubectl rollout restart deployment/$deployment -n pyairtable
    done
    
    # Wait for rollouts to complete
    for deployment in $deployments; do
        print_info "Waiting for $deployment to be ready..."
        kubectl rollout status deployment/$deployment -n pyairtable --timeout=300s
    done
    
    print_success "All PyAirtable pods restarted with Istio sidecars"
}

# Verify Istio installation
verify_installation() {
    print_info "Verifying Istio installation..."
    
    # Check Istio status
    istioctl verify-install
    
    # Check proxy status
    istioctl proxy-status
    
    # List pods with sidecars
    print_info "PyAirtable pods with Istio sidecars:"
    kubectl get pods -n pyairtable -o wide
    
    print_success "Istio installation verified"
}

# Create helper scripts
create_helper_scripts() {
    print_info "Creating helper scripts..."
    
    # Create observability port-forward script
    cat > ../scripts/start-observability.sh << 'EOF'
#!/bin/bash
echo "Starting Istio observability tools..."
echo "Grafana: http://localhost:3000"
echo "Kiali: http://localhost:20001"
echo "Jaeger: http://localhost:16686"
echo "Prometheus: http://localhost:9090"

kubectl port-forward -n istio-system svc/grafana 3000:3000 &
kubectl port-forward -n istio-system svc/kiali 20001:20001 &
kubectl port-forward -n istio-system svc/jaeger-query 16686:16686 &
kubectl port-forward -n istio-system svc/prometheus 9090:9090 &

echo "Port forwards started. Press Ctrl+C to stop all."
wait
EOF
    
    chmod +x ../scripts/start-observability.sh
    
    # Create Istio status check script
    cat > ../scripts/check-istio-status.sh << 'EOF'
#!/bin/bash
echo "Istio Installation Status:"
echo "=========================="
istioctl verify-install

echo ""
echo "Proxy Status:"
echo "============="
istioctl proxy-status

echo ""
echo "PyAirtable Pods with Sidecars:"
echo "=============================="
kubectl get pods -n pyairtable -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[*].ready,STATUS:.status.phase

echo ""
echo "Istio Configuration Analysis:"
echo "============================="
istioctl analyze -n pyairtable
EOF
    
    chmod +x ../scripts/check-istio-status.sh
    
    print_success "Helper scripts created"
}

# Main execution
main() {
    print_info "Starting Istio setup for PyAirtable..."
    echo ""
    
    check_prerequisites
    install_istio_cluster
    install_istio_addons
    create_dev_certificates
    restart_pyairtable_pods
    verify_installation
    create_helper_scripts
    
    echo ""
    print_success "Istio setup completed successfully!"
    echo ""
    print_info "Next steps:"
    echo "1. Run step2-deploy-istio-config.sh to apply PyAirtable-specific Istio configuration"
    echo "2. Use ../scripts/start-observability.sh to access monitoring tools"
    echo "3. Use ../scripts/check-istio-status.sh to verify installation"
    echo ""
    print_info "Observability tools will be available at:"
    echo "- Grafana: http://localhost:3000"
    echo "- Kiali: http://localhost:20001"
    echo "- Jaeger: http://localhost:16686"
    echo "- Prometheus: http://localhost:9090"
}

# Run main function
main "$@"