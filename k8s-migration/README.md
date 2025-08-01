# PyAirtable Kubernetes Migration

> **Practical migration from port-forwarding chaos to modern service mesh architecture**

## Quick Start (5 minutes)

**Problem**: Constantly need port-forwarding, conflicts between developers, manual service access.

**Solution**: Enhanced ingress with immediate benefits.

```bash
cd quick-wins
chmod +x deploy-quick-fix.sh
./deploy-quick-fix.sh
```

**Result**: Access all services without port-forwarding:
- Main App: `http://pyairtable.local`
- API Gateway: `http://api.pyairtable.local`
- All services: `http://[service].pyairtable.local`

## Migration Paths

### 🚀 Path 1: Quick Fix (Recommended Start)
- **Time**: 15 minutes
- **Complexity**: Low
- **Benefits**: Immediate port-forwarding relief
- **Rollback**: Easy
- **Production Ready**: Development only

### 🏗️ Path 2: Full Istio Migration
- **Time**: 45-60 minutes
- **Complexity**: Medium
- **Benefits**: Service mesh, observability, security
- **Rollback**: Moderate
- **Production Ready**: Yes

### 🔒 Path 3: SPIRE Integration (Advanced)
- **Time**: +15 minutes after Istio
- **Complexity**: High
- **Benefits**: Zero-trust security, cryptographic identities
- **Rollback**: Complex
- **Production Ready**: Enterprise-grade

## Directory Structure

```
k8s-migration/
├── README.md                           # This file
├── IMPLEMENTATION_GUIDE.md             # Detailed implementation guide
├── quick-wins/                         # Immediate solutions
│   ├── enhanced-ingress.yaml           # Multi-host ingress configuration
│   └── deploy-quick-fix.sh             # One-click deployment
├── istio-integration/                  # Service mesh configuration
│   ├── pyairtable-istio-gateway.yaml   # Istio gateway for PyAirtable
│   └── pyairtable-security.yaml        # Security policies
├── migration-scripts/                  # Step-by-step migration
│   ├── step1-istio-setup.sh            # Istio installation
│   ├── step2-deploy-istio-config.sh    # PyAirtable Istio config
│   └── step3-enable-advanced-features.sh # SPIRE integration
├── scripts/                            # Helper utilities
│   ├── start-observability.sh          # Start monitoring tools
│   ├── check-istio-status.sh           # Istio health checks
│   ├── check-gateway-status.sh         # Gateway status
│   ├── analyze-traffic.sh              # Traffic analysis
│   ├── check-spire-status.sh           # SPIRE monitoring
│   └── verify-service-identities.sh    # Identity verification
├── config/                             # Configuration storage
│   └── istio-connection.env            # Connection parameters
└── certs/                              # TLS certificates
    ├── root-ca.crt                     # Root CA certificate
    ├── root-ca.key                     # Root CA private key
    ├── pyairtable.local.crt            # Service certificate
    └── pyairtable.local.key            # Service private key
```

## Your Current Services

| Service | Current Port | New URL | Status |
|---------|-------------|---------|--------|
| API Gateway | 8000 | api.pyairtable.local | ✅ Running |
| MCP Server | 8001 | mcp.pyairtable.local | ✅ Running |
| Airtable Gateway | 8002 | airtable.pyairtable.local | ✅ Running |
| LLM Orchestrator | 8003 | llm.pyairtable.local | ✅ Running |
| Platform Services | 8007 | platform.pyairtable.local | ✅ Running |
| Automation Services | 8006 | automation.pyairtable.local | ⚠️ Issues |
| Frontend | 3000 | pyairtable.local | ⚠️ Issues |
| PostgreSQL | 5432 | db.pyairtable.local | ✅ Running |
| Redis | 6379 | redis.pyairtable.local | ✅ Running |

## Decision Matrix

| Need | Quick Fix | Istio | SPIRE |
|------|-----------|-------|-------|
| Stop port-forwarding | ✅ | ✅ | ✅ |
| Multi-developer support | ✅ | ✅ | ✅ |
| Service observability | ❌ | ✅ | ✅ |
| Traffic management | ❌ | ✅ | ✅ |
| Automatic mTLS | ❌ | ✅ | ✅ |
| Zero-trust security | ❌ | ⚠️ | ✅ |
| Production readiness | ❌ | ✅ | ✅ |
| Certificate management | ❌ | Manual | Automatic |

## Implementation Approach

### Recommended Sequence

1. **Week 1**: Deploy Quick Fix
   - Immediate relief from port-forwarding
   - Test all services work with new URLs
   - Get team comfortable with new workflow

2. **Week 2**: Plan Istio Migration
   - Review implementation guide
   - Schedule migration during low-traffic period
   - Prepare rollback plan

3. **Week 3**: Execute Istio Migration
   - Run step-by-step migration scripts
   - Validate all services work correctly
   - Set up monitoring dashboards

4. **Week 4**: Consider SPIRE (Optional)
   - Evaluate security requirements
   - Test SPIRE integration in development
   - Plan production security policies

### Alternative: Direct to Istio

If you prefer to skip the quick fix and go directly to Istio:

```bash
cd migration-scripts
./step1-istio-setup.sh
./step2-deploy-istio-config.sh
# Optional: ./step3-enable-advanced-features.sh
```

## Validation Commands

### Quick Fix Validation
```bash
# Test service access
curl -I http://api.pyairtable.local
curl -I http://mcp.pyairtable.local

# Check ingress status
kubectl get ingress -n pyairtable
```

### Istio Validation
```bash
# Check mesh status
istioctl proxy-status

# Verify configuration
istioctl analyze -n pyairtable

# Test mTLS
istioctl authn tls-check [pod-name].pyairtable
```

### SPIRE Validation
```bash
# Check SPIFFE identities
./scripts/check-spire-status.sh

# Verify service identities
./scripts/verify-service-identities.sh
```

## Troubleshooting

### Common Issues

1. **DNS Resolution Fails**
   ```bash
   # Check hosts file
   grep pyairtable /etc/hosts
   
   # Update if needed
   echo "$(minikube ip) pyairtable.local" | sudo tee -a /etc/hosts
   ```

2. **Service Not Accessible**
   ```bash
   # Check pod status
   kubectl get pods -n pyairtable
   
   # Check ingress
   kubectl describe ingress -n pyairtable
   ```

3. **Istio Issues**
   ```bash
   # Check sidecar injection
   kubectl get pods -n pyairtable -o wide
   
   # Analyze configuration
   istioctl analyze -n pyairtable
   ```

### Getting Help

1. **Check logs**: `kubectl logs -f [pod-name] -n pyairtable`
2. **Run diagnostics**: Use scripts in `/scripts/` directory
3. **Rollback**: Each path has rollback instructions in implementation guide

## Benefits

### Immediate (Quick Fix)
- ✅ No more `kubectl port-forward` commands
- ✅ Multiple developers can work simultaneously
- ✅ Easy service discovery and testing
- ✅ Simplified development workflow

### Medium-term (Istio)
- ✅ Service mesh visibility and control
- ✅ Automatic load balancing and retries
- ✅ Traffic splitting for canary deployments
- ✅ Built-in observability (metrics, traces, logs)
- ✅ Automatic mTLS between services

### Long-term (SPIRE)
- ✅ Cryptographic service identities
- ✅ Zero-trust security architecture
- ✅ Automatic certificate rotation
- ✅ Fine-grained authorization policies
- ✅ Compliance and audit capabilities

## Next Steps

1. **Start Here**: `cd quick-wins && ./deploy-quick-fix.sh`
2. **Read**: [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) for detailed instructions
3. **Plan**: Choose your migration path based on your needs
4. **Execute**: Follow step-by-step scripts for chosen path
5. **Monitor**: Use provided scripts to validate and monitor

---

**Need immediate help?** Start with the Quick Fix - it's safe, reversible, and gives you immediate benefits while you plan the full migration.