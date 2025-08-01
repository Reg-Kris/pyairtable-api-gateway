# PyAirtable API Gateway WebSocket Implementation

This document describes the comprehensive WebSocket implementation for real-time communication between the PyAirtable API Gateway and Next.js frontend.

## Overview

The WebSocket implementation provides real-time communication capabilities for:
- **Chat message streaming** from LLM Orchestrator
- **Tool execution progress updates** from MCP Server  
- **Cost tracking updates** in real-time
- **System health and status notifications**

## Architecture

### Components

1. **WebSocket Connection Manager** (`websocket_manager.py`)
   - Manages client connections with session tracking
   - Handles authentication and authorization
   - Implements rate limiting and message queuing
   - Provides connection cleanup and health monitoring

2. **Message Models** (`models.py`)
   - Defines typed message structures for all WebSocket communications
   - Ensures data validation and consistency

3. **Service Integration Manager** (`service_integrations.py`)
   - Handles real-time integrations with backend services
   - Manages streaming connections to LLM Orchestrator and MCP Server
   - Polls for cost and system status updates

4. **WebSocket Endpoint** (`main.py`)
   - Provides `/ws` endpoint for client connections
   - Handles message routing and broadcasting

## WebSocket Endpoint

### Connection URL
```
ws://localhost:8000/ws?session_id={session_id}
```

### Authentication Flow

1. Client connects to WebSocket endpoint with `session_id` parameter
2. Client sends authentication message:
   ```json
   {
     "type": "auth",
     "api_key": "your-api-key",
     "session_id": "your-session-id"
   }
   ```
3. Server validates API key using existing security infrastructure
4. Upon successful authentication, queued messages are delivered

## Message Types

### 1. Chat Stream Messages
Real-time chat responses from LLM Orchestrator.

```json
{
  "type": "chat_stream",
  "timestamp": "2025-07-31T19:30:00Z",
  "session_id": "session-123",
  "data": {
    "delta": "text chunk",
    "token_count": 150,
    "is_complete": false
  }
}
```

### 2. Tool Progress Messages
Progress updates during MCP tool execution.

```json
{
  "type": "tool_progress", 
  "timestamp": "2025-07-31T19:30:00Z",
  "session_id": "session-123",
  "data": {
    "tool_name": "airtable_query",
    "status": "running",
    "progress": 50,
    "message": "Fetching records...",
    "result": null
  }
}
```

### 3. Cost Update Messages
Real-time budget and cost tracking updates.

```json
{
  "type": "cost_update",
  "timestamp": "2025-07-31T19:30:00Z", 
  "session_id": "session-123",
  "data": {
    "current_cost": 12.45,
    "budget_remaining": 87.55,
    "cost_breakdown": {
      "llm_calls": 10.20,
      "tool_executions": 2.25
    },
    "period": "monthly"
  }
}
```

### 4. System Status Messages
Health and service status notifications.

```json
{
  "type": "system_status",
  "timestamp": "2025-07-31T19:30:00Z",
  "session_id": "session-123", 
  "data": {
    "overall_status": "healthy",
    "services": {
      "llm_orchestrator": {"status": "healthy", "response_time": 0.150},
      "mcp_server": {"status": "healthy", "response_time": 0.080}
    },
    "alerts": []
  }
}
```

### 5. Control Messages

**Ping/Pong for connection health:**
```json
// Client sends
{"type": "ping"}

// Server responds  
{"type": "pong", "timestamp": "2025-07-31T19:30:00Z"}
```

**Subscription management:**
```json
// Subscribe to message types
{
  "type": "subscribe",
  "types": ["chat_stream", "tool_progress", "cost_update"]
}

// Unsubscribe from message types
{
  "type": "unsubscribe", 
  "types": ["system_status"]
}
```

**Error messages:**
```json
{
  "type": "error",
  "timestamp": "2025-07-31T19:30:00Z",
  "session_id": "session-123",
  "data": {
    "error_code": "rate_limited",
    "message": "Message rate limit exceeded",
    "details": {}
  }
}
```

## Security Features

### Authentication
- Uses existing API key system from pyairtable-common
- Constant-time comparison for API key validation
- 10-second authentication timeout

### Rate Limiting  
- 100 messages per minute per connection
- Configurable rate limit windows
- Automatic blocking of rate-limited connections

### Connection Limits
- Maximum 5 connections per session
- Automatic cleanup of stale connections
- Connection timeout after 5 minutes of inactivity

### Input Validation
- JSON message validation
- Pydantic models for type safety
- Sanitized error messages

## Configuration

### Environment Variables

```bash
# Optional cost tracking service
COST_TRACKING_URL=http://localhost:8004

# WebSocket-specific settings (optional)
WS_MAX_CONNECTIONS_PER_SESSION=5
WS_MESSAGE_RATE_LIMIT=100
WS_RATE_LIMIT_WINDOW=60
WS_MAX_QUEUED_MESSAGES=1000
WS_MESSAGE_QUEUE_TTL=3600
WS_PING_INTERVAL=30
WS_CONNECTION_TIMEOUT=300
```

### Connection Manager Settings

```python
websocket_manager = WebSocketConnectionManager(
    max_connections_per_session=5,
    message_rate_limit=100,        # messages per minute
    rate_limit_window=60,          # seconds
    max_queued_messages=1000,      # per session
    message_queue_ttl=3600,        # seconds
    ping_interval=30,              # seconds  
    connection_timeout=300         # seconds
)
```

## Integration Points

### Chat Streaming
Enable streaming in chat requests:
```json
{
  "message": "Hello",
  "session_id": "session-123",
  "stream": true
}
```

### Tool Progress Streaming
Enable progress updates in tool execution:
```json
{
  "tool_name": "airtable_query",
  "arguments": {"table": "Contacts"},
  "session_id": "session-123", 
  "stream_progress": true
}
```

### Cost Tracking Integration
- Automatic polling of cost tracking service (if configured)
- Broadcasts updates when costs change by >$0.01
- Supports monthly/weekly/daily budget periods

### System Monitoring
- Health checks for all backend services every 30 seconds
- Performance monitoring with response time tracking
- Alert generation for unhealthy services

## Client Implementation

### JavaScript/TypeScript Example

```javascript
class PyAirtableWebSocket {
  constructor(apiKey, sessionId) {
    this.apiKey = apiKey;
    this.sessionId = sessionId;
    this.ws = null;
    this.authenticated = false;
  }

  async connect() {
    const url = `ws://localhost:8000/ws?session_id=${this.sessionId}`;
    this.ws = new WebSocket(url);
    
    this.ws.onopen = () => {
      // Send authentication
      this.ws.send(JSON.stringify({
        type: 'auth',
        api_key: this.apiKey,
        session_id: this.sessionId
      }));
    };
    
    this.ws.onmessage = (event) => {
      const message = JSON.parse(event.data);
      this.handleMessage(message);
    };
  }

  handleMessage(message) {
    switch (message.type) {
      case 'chat_stream':
        this.onChatStream(message.data);
        break;
      case 'tool_progress':
        this.onToolProgress(message.data);
        break;
      case 'cost_update':
        this.onCostUpdate(message.data);
        break;
      case 'system_status':
        this.onSystemStatus(message.data);
        break;
    }
  }

  subscribe(messageTypes) {
    this.ws.send(JSON.stringify({
      type: 'subscribe',
      types: messageTypes
    }));
  }
}
```

### Python Client Example
See `websocket_client_example.py` for a complete Python client implementation.

## Monitoring and Stats

### WebSocket Statistics Endpoint
```
GET /api/websocket/stats
X-API-Key: your-api-key
```

Response:
```json
{
  "total_connections": 150,
  "active_connections": 25,
  "active_sessions": 20,
  "messages_sent": 5000,
  "messages_queued": 10,
  "rate_limit_violations": 2,
  "authentication_failures": 1,
  "average_messages_per_connection": 33.33
}
```

### Health Check Integration
WebSocket stats are included in the main health check:
```
GET /api/health
```

### Logging
Comprehensive logging for:
- Connection establishment/termination
- Authentication attempts  
- Message broadcasting
- Rate limiting violations
- Error conditions

## Deployment Considerations

### Production Settings
- Use WSS (WebSocket Secure) in production
- Configure appropriate CORS origins
- Set up monitoring for WebSocket metrics
- Consider connection limits based on server capacity

### Scaling
- WebSocket connections are server-local (not shared across instances)
- Consider using Redis for cross-server message broadcasting
- Load balancer should support WebSocket connections
- Monitor memory usage for connection/message queues

### Performance
- Message queuing prevents loss during brief disconnections
- Rate limiting protects against client abuse
- Efficient JSON serialization with Pydantic
- Background tasks for cleanup and health monitoring

## Troubleshooting

### Common Issues

1. **Authentication failures**
   - Verify API key is correct
   - Check API key header format
   - Ensure session_id is provided

2. **Connection drops**
   - Check network connectivity
   - Verify WebSocket proxy configuration
   - Review server logs for rate limiting

3. **Missing messages**
   - Check subscription settings
   - Verify message queuing is working
   - Review client-side message handling

### Debug Logging
Enable debug logging:
```python
logging.getLogger('pyairtable-api-gateway.websocket_manager').setLevel(logging.DEBUG)
```

## Future Enhancements

- **Message persistence**: Store messages in database for offline clients
- **Cross-server broadcasting**: Redis pub/sub for multi-instance deployments  
- **Message filtering**: Client-side filtering based on content
- **Compression**: WebSocket message compression for large payloads
- **Metrics**: Prometheus metrics for monitoring
- **Admin interface**: Web interface for connection management