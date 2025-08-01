# Local Kubernetes Development Environment

This directory contains a comprehensive solution for local Kubernetes development that eliminates port forwarding conflicts and provides proper service discovery, authentication, and security.

## Architecture Overview

The solution provides:

1. **Service Discovery**: DNS-based service discovery using CoreDNS and External DNS
2. **Single Entry Point**: Istio ingress gateway for all external access
3. **Zero Trust Security**: mTLS between all services using SPIFFE/SPIRE
4. **Authentication**: JWT-based external auth + service-to-service mTLS
5. **Developer Experience**: Easy testing without port conflicts

## Directory Structure

```
k8s-dev-setup/
├── README.md                          # This file
├── service-discovery/                 # DNS and service discovery configs
│   ├── coredns-config.yaml           # CoreDNS configuration
│   └── external-dns-config.yaml      # External DNS for local domains
├── ingress/                          # Ingress gateway configuration
│   └── istio-gateway.yaml            # Istio gateway and virtual services
├── security/                         # Security and authentication
│   ├── spire-server.yaml             # SPIRE server for SPIFFE identities
│   ├── spire-agent.yaml              # SPIRE agent DaemonSet
│   └── istio-mtls-policy.yaml        # mTLS and authorization policies
├── scripts/                          # Setup and utility scripts
│   └── setup-dev-environment.sh      # Main setup script
├── examples/                         # Templates and examples
│   ├── service-template.yaml         # Service deployment template
│   └── python-service-client.py      # Python client with SPIFFE support
└── testing/                          # Testing utilities
    └── test-connectivity.sh          # Comprehensive connectivity tests
```

## Quick Start

### Prerequisites

- Docker
- minikube
- kubectl
- curl

### Setup

1. **Run the setup script**:
   ```bash
   cd scripts
   chmod +x setup-dev-environment.sh
   ./setup-dev-environment.sh
   ```

2. **Register your services with SPIRE**:
   ```bash
   ./register-services.sh
   ```

3. **Start observability tools**:
   ```bash
   ./port-forward-tools.sh
   ```

### Testing

Run comprehensive connectivity tests:
```bash
cd testing
chmod +x test-connectivity.sh
./test-connectivity.sh
```

## Service Access

After setup, your services are accessible via:

- **API Gateway**: https://api.dev.local
- **Individual Services**: https://[service-name].dev.local
- **Internal Communication**: Automatic via service names (e.g., `https://auth-service:8080`)

## Observability Tools

Access these via port forwards (run `./port-forward-tools.sh`):

- **Grafana**: http://localhost:3000
- **Kiali**: http://localhost:20001  
- **Jaeger**: http://localhost:16686
- **Prometheus**: http://localhost:9090

## Service Deployment

Use the service template in `examples/service-template.yaml`:

1. Copy the template:
   ```bash
   cp examples/service-template.yaml my-service.yaml
   ```

2. Replace placeholders:
   - `REPLACE_SERVICE_NAME`: Your service name
   - `REPLACE_IMAGE_NAME`: Your container image

3. Deploy:
   ```bash
   kubectl apply -f my-service.yaml
   ```

## Authentication Flows

### External Client Authentication
1. Client authenticates with auth service
2. Receives JWT token
3. Includes JWT in requests to API gateway
4. Gateway validates JWT and forwards to services

### Service-to-Service Authentication
1. Services get SPIFFE identities from SPIRE
2. Istio enforces mTLS using SPIFFE certificates
3. Authorization policies control access between services
4. No manual certificate management required

## Security Features

### Network Security
- **mTLS Everywhere**: Automatic mTLS between all services
- **Network Policies**: Restrict traffic to necessary communications
- **Zero Trust**: No implicit trust between services

### Identity and Access
- **SPIFFE Identities**: Cryptographic service identities
- **JWT Authentication**: For external client access
- **Authorization Policies**: Fine-grained access control

### Certificate Management
- **Automatic Rotation**: SPIFFE certificates auto-rotate
- **No Manual Management**: SPIRE handles all certificate lifecycle
- **Trust Bundle Distribution**: Automatic CA distribution

## Development Workflow

### Adding a New Service

1. **Create service using template**:
   ```bash
   sed 's/REPLACE_SERVICE_NAME/my-new-service/g' examples/service-template.yaml > my-new-service.yaml
   sed -i 's/REPLACE_IMAGE_NAME/my-registry\/my-new-service:latest/g' my-new-service.yaml
   ```

2. **Deploy service**:
   ```bash
   kubectl apply -f my-new-service.yaml
   ```

3. **Register with SPIRE**:
   ```bash
   kubectl exec -n spire $(kubectl get pods -n spire -l app=spire-server -o jsonpath='{.items[0].metadata.name}') -- \
     /opt/spire/bin/spire-server entry create \
     -spiffeID spiffe://dev.local/ns/default/sa/my-new-service \
     -parentID spiffe://dev.local/ns/spire/sa/spire-agent \
     -selector k8s:ns:default \
     -selector k8s:sa:my-new-service
   ```

4. **Update ingress if needed**:
   - Add routes to `ingress/istio-gateway.yaml`
   - Add DNS entry to `/etc/hosts`

### Testing Service Communication

Use the Python client example:

```python
from examples.python_service_client import ServiceClient

# Initialize client
client = ServiceClient("my-service")

# Call another service
result = client.call_service("auth-service", "/auth/validate", "POST", {"token": "jwt-token"})
print(result)
```

### Debugging

1. **Check service status**:
   ```bash
   kubectl get pods
   kubectl logs -f deployment/my-service
   ```

2. **Check mTLS status**:
   ```bash
   istioctl proxy-status
   istioctl proxy-config cluster my-service-pod
   ```

3. **Check SPIFFE identities**:
   ```bash
   kubectl exec -n spire spire-server-pod -- /opt/spire/bin/spire-server entry show
   ```

4. **Test connectivity**:
   ```bash
   cd testing
   ./test-connectivity.sh
   ```

## Cleanup

To remove the development environment:

```bash
cd scripts
./cleanup-dev-environment.sh
```

This will:
- Remove DNS entries from `/etc/hosts`
- Delete the minikube cluster
- Clean up all resources

## Troubleshooting

### Common Issues

1. **DNS Resolution Fails**
   - Check `/etc/hosts` has correct entries
   - Verify minikube IP with `minikube ip`
   - Restart CoreDNS: `kubectl rollout restart deployment/coredns -n kube-system`

2. **mTLS Connection Fails**
   - Check SPIRE server/agent status: `kubectl get pods -n spire`
   - Verify service registration: `kubectl exec -n spire spire-server-pod -- /opt/spire/bin/spire-server entry show`
   - Check Istio proxy status: `istioctl proxy-status`

3. **Service Can't Connect to Others**
   - Verify network policies allow traffic
   - Check authorization policies in Istio
   - Ensure service has proper SPIFFE identity

4. **JWT Authentication Fails**
   - Check token expiry and format
   - Verify issuer and audience claims
   - Check authorization policies

### Useful Commands

```bash
# Check all service mesh status
istioctl analyze

# View service mesh configuration
istioctl proxy-config all pod-name

# Check mTLS status
istioctl authn tls-check pod-name.namespace

# View SPIFFE identities
kubectl exec -n spire spire-server-pod -- /opt/spire/bin/spire-server entry show

# Test internal connectivity
kubectl run test-pod --image=curlimages/curl:latest --rm -it -- sh
```

## Best Practices

1. **Service Design**
   - Always include health check endpoints (`/health`, `/ready`)
   - Use structured logging with correlation IDs
   - Implement graceful shutdown

2. **Security**
   - Never disable mTLS in production
   - Use least-privilege authorization policies
   - Rotate service account keys regularly

3. **Development**
   - Use meaningful SPIFFE IDs that reflect service purpose
   - Test both authenticated and unauthenticated endpoints
   - Monitor service mesh metrics in Grafana

4. **Debugging**
   - Use distributed tracing (Jaeger) for request flow
   - Check service mesh configuration before code issues
   - Use Kiali for visual service mesh debugging

## Further Reading

- [SPIFFE/SPIRE Documentation](https://spiffe.io/docs/)
- [Istio Security](https://istio.io/latest/docs/concepts/security/)
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [JWT Authentication](https://jwt.io/introduction/)