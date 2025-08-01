#!/bin/bash

# Development Environment Setup Script
# This script sets up the complete local Kubernetes development environment

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
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
    
    # Check if minikube is installed
    if ! command -v minikube &> /dev/null; then
        print_error "minikube is not installed. Please install minikube first."
        exit 1
    fi
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        print_error "kubectl is not installed. Please install kubectl first."
        exit 1
    fi
    
    # Check if istioctl is installed
    if ! command -v istioctl &> /dev/null; then
        print_warning "istioctl is not installed. Installing Istio..."
        install_istio
    fi
    
    print_success "Prerequisites check completed"
}

# Install Istio
install_istio() {
    print_info "Installing Istio..."
    curl -L https://istio.io/downloadIstio | sh -
    export PATH="$PATH:$PWD/istio-*/bin"
    echo 'export PATH="$PATH:'"$PWD"'/istio-*/bin"' >> ~/.bashrc
}

# Start minikube with appropriate resources
start_minikube() {
    print_info "Starting minikube with appropriate resources..."
    
    # Check if minikube is already running
    if minikube status &> /dev/null; then
        print_warning "Minikube is already running"
    else
        minikube start \
            --cpus=4 \
            --memory=8192 \
            --disk-size=20g \
            --driver=docker \
            --kubernetes-version=v1.28.0 \
            --addons=ingress,dns,metrics-server
    fi
    
    print_success "Minikube started successfully"
}

# Setup Istio service mesh
setup_istio() {
    print_info "Setting up Istio service mesh..."
    
    # Install Istio with demo profile for development
    istioctl install --set values.defaultRevision=default -y
    
    # Enable sidecar injection for default namespace
    kubectl label namespace default istio-injection=enabled --overwrite
    
    # Install Istio addons for observability
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/prometheus.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/grafana.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/jaeger.yaml
    kubectl apply -f https://raw.githubusercontent.com/istio/istio/release-1.19/samples/addons/kiali.yaml
    
    print_success "Istio service mesh installed successfully"
}

# Setup SPIRE for SPIFFE identities
setup_spire() {
    print_info "Setting up SPIRE for secure identities..."
    
    kubectl apply -f ../security/spire-server.yaml
    kubectl apply -f ../security/spire-agent.yaml
    
    # Wait for SPIRE server to be ready
    kubectl wait --for=condition=ready pod -l app=spire-server -n spire --timeout=300s
    
    print_success "SPIRE installed successfully"
}

# Setup DNS resolution
setup_dns() {
    print_info "Setting up DNS resolution..."
    
    # Apply CoreDNS configuration
    kubectl apply -f ../service-discovery/coredns-config.yaml
    kubectl apply -f ../service-discovery/external-dns-config.yaml
    
    # Get minikube IP
    MINIKUBE_IP=$(minikube ip)
    
    # Add DNS entries to /etc/hosts
    print_info "Adding DNS entries to /etc/hosts (requires sudo)..."
    
    # Backup existing hosts file
    sudo cp /etc/hosts /etc/hosts.backup.$(date +%Y%m%d_%H%M%S)
    
    # Remove existing dev.local entries
    sudo sed -i '' '/dev\.local/d' /etc/hosts
    
    # Add new entries
    echo "# Local Kubernetes Development - Added by setup script" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP api.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP auth.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP users.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP orders.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP inventory.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP notifications.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP analytics.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP payments.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP catalog.dev.local" | sudo tee -a /etc/hosts
    echo "$MINIKUBE_IP search.dev.local" | sudo tee -a /etc/hosts
    
    print_success "DNS resolution configured"
}

# Setup ingress gateway
setup_ingress() {
    print_info "Setting up Istio ingress gateway..."
    
    kubectl apply -f ../ingress/istio-gateway.yaml
    
    # Create TLS certificate for dev.local
    create_dev_certificates
    
    print_success "Ingress gateway configured"
}

# Create development TLS certificates
create_dev_certificates() {
    print_info "Creating development TLS certificates..."
    
    # Create certificates directory
    mkdir -p ../certs
    
    # Generate root CA
    openssl req -x509 -sha256 -nodes -days 365 -newkey rsa:2048 \
        -subj '/O=Local Dev/CN=dev.local' \
        -keyout ../certs/root-ca.key \
        -out ../certs/root-ca.crt
    
    # Generate certificate for dev.local
    openssl req -out ../certs/dev.local.csr -newkey rsa:2048 -nodes \
        -keyout ../certs/dev.local.key \
        -subj "/CN=*.dev.local/O=Local Dev"
    
    openssl x509 -req -days 365 -CA ../certs/root-ca.crt -CAkey ../certs/root-ca.key \
        -set_serial 0 -in ../certs/dev.local.csr -out ../certs/dev.local.crt \
        -extensions v3_req -extfile <(echo -e "subjectAltName=DNS:*.dev.local,DNS:dev.local")
    
    # Create Kubernetes secret
    kubectl create secret tls dev-local-tls \
        --key=../certs/dev.local.key \
        --cert=../certs/dev.local.crt \
        -n istio-system --dry-run=client -o yaml | kubectl apply -f -
    
    print_success "Development certificates created"
}

# Setup security policies
setup_security() {
    print_info "Setting up security policies..."
    
    kubectl apply -f ../security/istio-mtls-policy.yaml
    
    print_success "Security policies applied"
}

# Create development utilities
create_dev_utilities() {
    print_info "Creating development utilities..."
    
    # Create port-forward script for observability tools
    cat > port-forward-tools.sh << 'EOF'
#!/bin/bash
# Port forward observability tools for easy access

echo "Starting port forwards for observability tools..."
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
    
    chmod +x port-forward-tools.sh
    
    # Create service registration script for SPIRE
    cat > register-services.sh << 'EOF'
#!/bin/bash
# Register services with SPIRE for SPIFFE identities

SPIRE_SERVER_POD=$(kubectl get pods -n spire -l app=spire-server -o jsonpath='{.items[0].metadata.name}')

services=("auth-service" "user-service" "order-service" "inventory-service" 
          "notification-service" "analytics-service" "payment-service" 
          "catalog-service" "search-service" "api-gateway")

for service in "${services[@]}"; do
    echo "Registering $service..."
    kubectl exec -n spire $SPIRE_SERVER_POD -- \
        /opt/spire/bin/spire-server entry create \
        -spiffeID spiffe://dev.local/ns/default/sa/$service \
        -parentID spiffe://dev.local/ns/spire/sa/spire-agent \
        -selector k8s:ns:default \
        -selector k8s:sa:$service \
        -dns $service \
        -dns $service.default \
        -dns $service.default.svc.cluster.local
done

echo "All services registered with SPIRE"
EOF
    
    chmod +x register-services.sh
    
    # Create cleanup script
    cat > cleanup-dev-environment.sh << 'EOF'
#!/bin/bash
# Cleanup development environment

echo "Cleaning up development environment..."

# Remove DNS entries from /etc/hosts
sudo sed -i '' '/dev\.local/d' /etc/hosts
sudo sed -i '' '/Local Kubernetes Development/d' /etc/hosts

# Delete minikube cluster
minikube delete

echo "Development environment cleaned up"
EOF
    
    chmod +x cleanup-dev-environment.sh
    
    print_success "Development utilities created"
}

# Main setup function
main() {
    print_info "Starting development environment setup..."
    
    check_prerequisites
    start_minikube
    setup_istio
    setup_spire
    setup_dns
    setup_ingress
    setup_security
    create_dev_utilities
    
    print_success "Development environment setup completed!"
    
    echo ""
    print_info "Next steps:"
    echo "1. Deploy your microservices with Istio sidecar injection enabled"
    echo "2. Run './register-services.sh' to register services with SPIRE"
    echo "3. Run './port-forward-tools.sh' to access observability tools"
    echo "4. Test your services at https://*.dev.local"
    echo ""
    print_info "URLs available:"
    echo "- API Gateway: https://api.dev.local"
    echo "- Individual services: https://[service-name].dev.local"
    echo "- Grafana: http://localhost:3000"
    echo "- Kiali: http://localhost:20001"
    echo "- Jaeger: http://localhost:16686"
}

# Run main function
main "$@"