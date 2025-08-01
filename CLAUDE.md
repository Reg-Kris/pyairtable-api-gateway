# API Gateway - Claude Context

## 🎯 Service Purpose
This is the **front door** to the PyAirtable ecosystem - a simple, lightweight routing service that provides a unified API interface. It handles authentication, request routing, health aggregation, and acts as the single entry point for all client applications.

## 🏗️ Current State

### Deployment Status
- **Environment**: ✅ Local Kubernetes (Minikube)
- **Services Running**: ✅ 7 out of 9 services operational
- **Database Analysis**: ✅ Airtable test database analyzed (34 tables, 539 fields)
- **Metadata Tool**: ✅ Table analysis tool executed successfully

### Service Status
- **Routing**: ✅ Working for all services
- **Authentication**: ⚠️ Simple API key only
- **Health Checks**: ✅ Aggregates from all services
- **Load Balancing**: ❌ Not implemented
- **Rate Limiting**: ❌ Not implemented
- **Monitoring**: ❌ Basic logging only

### Recent Fixes Applied
- ✅ Pydantic v2 compatibility issues resolved
- ✅ Gemini ThinkingConfig configuration fixed
- ✅ SQLAlchemy metadata handling updated
- ✅ Service deployment to Kubernetes completed

## 🚦 Routing Rules

### Current Routes
```python
# Main chat endpoint
POST /api/chat → LLM Orchestrator (8003)

# Tool operations
GET  /api/tools → LLM Orchestrator (8003)
POST /api/execute-tool → LLM Orchestrator (8003)

# Airtable operations (proxy all)
*    /api/airtable/* → Airtable Gateway (8002)

# Session management
GET    /api/sessions/{id}/history → LLM Orchestrator (8003)
DELETE /api/sessions/{id} → LLM Orchestrator (8003)

# System
GET  /api/health → Aggregated health check
GET  / → Service info
```

### Service URLs
```python
AIRTABLE_GATEWAY_URL = "http://airtable-gateway:8002"
MCP_SERVER_URL = "http://mcp-server:8001"  # Not directly routed
LLM_ORCHESTRATOR_URL = "http://llm-orchestrator:8003"
```

## 🚀 Immediate Priorities

1. **Add Rate Limiting** (HIGH)
   ```python
   from slowapi import Limiter
   
   limiter = Limiter(key_func=get_remote_address)
   
   @app.post("/api/chat")
   @limiter.limit("10/minute")
   async def chat_proxy(...):
   ```

2. **Implement Request ID Tracking** (HIGH)
   ```python
   # Add middleware for correlation IDs
   request_id = request.headers.get('X-Request-ID', str(uuid.uuid4()))
   # Forward to all services
   ```

3. **Add Circuit Breakers** (MEDIUM)
   ```python
   # Prevent cascading failures
   from pybreaker import CircuitBreaker
   
   airtable_breaker = CircuitBreaker(fail_max=5, reset_timeout=60)
   ```

## 🔮 Future Enhancements

### Phase 1 (Next Sprint)
- [ ] JWT authentication instead of API key
- [ ] Request/response logging middleware
- [ ] API versioning support (/v1/, /v2/)
- [ ] Request transformation middleware

### Phase 2 (Next Month)
- [ ] Load balancing for service instances
- [ ] API documentation aggregation
- [ ] WebSocket support for streaming
- [ ] Request caching layer

### Phase 3 (Future)
- [ ] GraphQL gateway option
- [ ] API analytics dashboard
- [ ] Dynamic routing rules
- [ ] Service mesh integration

## ⚠️ Known Issues
1. **No request validation** - Forwards everything
2. **Simple API key** - Not secure for production
3. **No retry logic** - Fails immediately
4. **Missing CORS config** - Currently allows all

## 🧪 Testing Strategy
```python
# Priority test coverage:
- Route testing for all endpoints
- Health check aggregation logic
- Authentication middleware
- Error handling for service failures
- Load testing for concurrent requests
```

## 🔧 Technical Details
- **Framework**: FastAPI with async
- **HTTP Client**: httpx with connection pooling
- **Python**: 3.12
- **No database**: Stateless service

## 📊 Performance Targets
- **Latency Overhead**: < 10ms added
- **Throughput**: 1000+ requests/second
- **Memory Usage**: < 100MB
- **CPU Usage**: < 10% under normal load

## 🤝 Service Communication
```
Client → API Gateway → [Service Routes] → Backend Services
            ↓
      Health Checks → All Services
```

## 💡 Development Tips
1. Keep it simple - this is just a router
2. Don't add business logic here
3. Log all routing decisions for debugging
4. Monitor service health actively

## 🚨 Critical Configuration
```python
# Required environment variables:
AIRTABLE_GATEWAY_URL=http://airtable-gateway:8002
MCP_SERVER_URL=http://mcp-server:8001
LLM_ORCHESTRATOR_URL=http://llm-orchestrator:8003
API_KEY=simple-api-key  # Replace with JWT
```

## 🔒 Security Responsibilities
- **Authentication**: Verify API keys/JWT tokens
- **Authorization**: Route based on permissions (future)
- **Rate Limiting**: Prevent abuse
- **Input Sanitization**: Basic validation

## 📈 Monitoring Metrics
```python
# Key metrics to track:
gateway_requests_total{method,endpoint,status}  # Request counts
gateway_request_duration_seconds{endpoint}      # Latency
gateway_active_connections                      # Current load
gateway_health_check_status{service}           # Service health
```

## 🎯 Gateway Patterns

### Health Check Aggregation
```python
# Current implementation is good:
services = [
    (AIRTABLE_GATEWAY_URL, "airtable-gateway"),
    (MCP_SERVER_URL, "mcp-server"),
    (LLM_ORCHESTRATOR_URL, "llm-orchestrator")
]
results = await asyncio.gather(*health_checks)
```

### Future: Smart Routing
```python
# Route based on load/health
if airtable_gateway_healthy and load < threshold:
    route_to_primary()
else:
    route_to_backup()
```

### Future: Request Transformation
```python
# Transform requests between API versions
if request.headers.get("API-Version") == "v1":
    body = transform_v1_to_v2(body)
```

## ⚡ Performance Optimization
1. **Connection Pooling**: Already implemented ✅
2. **Async Everything**: Using async/await ✅
3. **Minimal Processing**: Just routing ✅
4. **Add Caching**: For repeated requests 🔄

Remember: This service is the **gatekeeper** - it should be fast, secure, and reliable. Every millisecond counts!