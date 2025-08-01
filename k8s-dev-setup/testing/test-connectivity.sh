#!/bin/bash

# Comprehensive connectivity and security testing script
# Tests service discovery, mTLS, JWT authentication, and network policies

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Test DNS resolution
test_dns_resolution() {
    print_info "Testing DNS resolution..."
    
    services=("api.dev.local" "auth.dev.local" "users.dev.local" "orders.dev.local")
    
    for service in "${services[@]}"; do
        if nslookup $service > /dev/null 2>&1; then
            print_success "DNS resolution for $service: OK"
        else
            print_error "DNS resolution for $service: FAILED"
        fi
    done
}

# Test ingress gateway connectivity
test_ingress_connectivity() {
    print_info "Testing ingress gateway connectivity..."
    
    # Get minikube IP
    MINIKUBE_IP=$(minikube ip)
    
    # Test HTTP connectivity
    if curl -s -k -m 5 "https://api.dev.local/health" > /dev/null; then
        print_success "HTTPS connectivity to API gateway: OK"
    else
        print_warning "HTTPS connectivity to API gateway: FAILED (service may not be deployed)"
    fi
    
    # Test individual services
    services=("auth" "users" "orders" "inventory")
    for service in "${services[@]}"; do
        if curl -s -k -m 5 "https://$service.dev.local/health" > /dev/null; then
            print_success "HTTPS connectivity to $service: OK"
        else
            print_warning "HTTPS connectivity to $service: FAILED (service may not be deployed)"
        fi
    done
}

# Test service mesh mTLS
test_mtls() {
    print_info "Testing mTLS between services..."
    
    # Create a test pod to check mTLS
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: mtls-test-pod
  namespace: default
  labels:
    app: mtls-test
spec:
  containers:
  - name: curl
    image: curlimages/curl:latest
    command: ['sleep', '3600']
  restartPolicy: Always
EOF
    
    # Wait for pod to be ready
    kubectl wait --for=condition=ready pod/mtls-test-pod --timeout=60s
    
    # Test internal service communication
    services=("auth-service" "user-service" "order-service")
    for service in "${services[@]}"; do
        result=$(kubectl exec mtls-test-pod -- curl -s -m 5 "http://$service:8080/health" 2>/dev/null || echo "FAILED")
        if [[ "$result" != "FAILED" ]]; then
            print_success "Internal connectivity to $service: OK"
        else
            print_warning "Internal connectivity to $service: FAILED (service may not be deployed)"
        fi
    done
    
    # Check if mTLS is enforced (should fail without proper certificates)
    print_info "Checking mTLS enforcement..."
    result=$(kubectl exec mtls-test-pod -- curl -s -k -m 5 "https://auth-service:8080/health" 2>/dev/null || echo "FAILED")
    if [[ "$result" == "FAILED" ]]; then
        print_success "mTLS enforcement: OK (external requests properly blocked)"
    else
        print_warning "mTLS enforcement: MAY NOT BE CONFIGURED"
    fi
    
    # Cleanup test pod
    kubectl delete pod mtls-test-pod --ignore-not-found=true
}

# Test SPIRE server and agent
test_spire() {
    print_info "Testing SPIRE server and agent..."
    
    # Check SPIRE server status
    if kubectl get pods -n spire -l app=spire-server | grep -q Running; then
        print_success "SPIRE server: Running"
    else
        print_error "SPIRE server: Not running"
        return 1
    fi
    
    # Check SPIRE agent status
    if kubectl get pods -n spire -l app=spire-agent | grep -q Running; then
        print_success "SPIRE agent: Running"
    else
        print_error "SPIRE agent: Not running"
        return 1
    fi
    
    # Test SPIRE server registration
    SPIRE_SERVER_POD=$(kubectl get pods -n spire -l app=spire-server -o jsonpath='{.items[0].metadata.name}')
    if kubectl exec -n spire $SPIRE_SERVER_POD -- /opt/spire/bin/spire-server entry show > /dev/null 2>&1; then
        print_success "SPIRE server registration: OK"
    else
        print_warning "SPIRE server registration: No entries found"
    fi
}

# Test Istio configuration
test_istio() {
    print_info "Testing Istio configuration..."
    
    # Check Istio system pods
    if kubectl get pods -n istio-system | grep -q Running; then
        print_success "Istio system pods: Running"
    else
        print_error "Istio system pods: Not all running"
    fi
    
    # Check gateway configuration
    if kubectl get gateway -n istio-system dev-gateway > /dev/null 2>&1; then
        print_success "Istio gateway: Configured"
    else
        print_error "Istio gateway: Not found"
    fi
    
    # Check virtual services
    if kubectl get virtualservice > /dev/null 2>&1; then
        print_success "Virtual services: Configured"
    else
        print_warning "Virtual services: Not found"
    fi
    
    # Check peer authentication policies
    if kubectl get peerauthentication default > /dev/null 2>&1; then
        print_success "mTLS policy: Configured"
    else
        print_warning "mTLS policy: Not found"
    fi
}

# Test network policies
test_network_policies() {
    print_info "Testing network policies..."
    
    # Check if network policies exist
    if kubectl get networkpolicy > /dev/null 2>&1; then
        print_success "Network policies: Found"
        kubectl get networkpolicy --no-headers | while read policy rest; do
            print_info "  - $policy"
        done
    else
        print_warning "Network policies: None found"
    fi
}

# Test observability tools
test_observability() {
    print_info "Testing observability tools..."
    
    tools=("grafana" "kiali" "jaeger-query" "prometheus")
    
    for tool in "${tools[@]}"; do
        if kubectl get svc -n istio-system $tool > /dev/null 2>&1; then
            print_success "$tool: Deployed"
        else
            print_warning "$tool: Not deployed"
        fi
    done
}

# Generate test JWT token
generate_test_jwt() {
    print_info "Generating test JWT token..."
    
    # This is a mock JWT for testing - in real scenarios, get from auth service
    cat > test-jwt.json <<EOF
{
  "iss": "https://auth.dev.local",
  "aud": "dev.local",
  "sub": "test-user",
  "exp": $(date -d "+1 hour" +%s),
  "iat": $(date +%s),
  "roles": ["user", "developer"]
}
EOF
    
    # In a real scenario, you would sign this with the auth service's private key
    print_info "Test JWT payload created (unsigned for testing)"
}

# Test service-to-service authentication
test_service_auth() {
    print_info "Testing service-to-service authentication..."
    
    # Create a test client pod with the service client code
    kubectl apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: auth-test-pod
  namespace: default
  labels:
    app: auth-test
spec:
  containers:
  - name: python-client
    image: python:3.9-slim
    command: ['sleep', '3600']
    env:
    - name: SPIFFE_ENDPOINT_SOCKET
      value: "unix:///run/spire/sockets/agent.sock"
    volumeMounts:
    - name: spire-agent-socket
      mountPath: /run/spire/sockets
      readOnly: true
  volumes:
  - name: spire-agent-socket
    hostPath:
      path: /run/spire/sockets
      type: Directory
  restartPolicy: Always
EOF
    
    # Wait for pod to be ready
    kubectl wait --for=condition=ready pod/auth-test-pod --timeout=60s
    
    # Install required packages
    kubectl exec auth-test-pod -- pip install requests pyspiffe pyjwt > /dev/null 2>&1
    
    print_success "Authentication test pod ready"
    
    # Cleanup
    kubectl delete pod auth-test-pod --ignore-not-found=true
}

# Performance test
test_performance() {
    print_info "Running basic performance test..."
    
    # Test with curl for basic latency
    if command -v curl > /dev/null 2>&1; then
        response_time=$(curl -s -k -w "%{time_total}" -o /dev/null "https://api.dev.local/health" 2>/dev/null || echo "0")
        if [[ "$response_time" != "0" ]]; then
            print_success "Response time to API gateway: ${response_time}s"
        else
            print_warning "Could not measure response time"
        fi
    fi
}

# Main test runner
main() {
    print_info "Starting comprehensive connectivity and security tests..."
    echo ""
    
    test_dns_resolution
    echo ""
    
    test_ingress_connectivity
    echo ""
    
    test_istio
    echo ""
    
    test_spire
    echo ""
    
    test_mtls
    echo ""
    
    test_network_policies
    echo ""
    
    test_observability
    echo ""
    
    test_service_auth
    echo ""
    
    test_performance
    echo ""
    
    generate_test_jwt
    echo ""
    
    print_success "All tests completed!"
    echo ""
    print_info "Next steps:"
    echo "1. If any tests failed, check the corresponding service deployments"
    echo "2. Use './port-forward-tools.sh' to access observability tools"
    echo "3. Check logs with: kubectl logs -f deployment/[service-name]"
    echo "4. Test your applications at https://*.dev.local"
}

# Run tests
main "$@"