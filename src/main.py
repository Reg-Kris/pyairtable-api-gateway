"""
PyAirtable API Gateway
Simple routing service for PyAirtable microservices
"""

import os
import sys
import asyncio
import json
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, Request, Header, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import logging
from pydantic import ValidationError

# Import WebSocket components
from .websocket_manager import WebSocketConnectionManager
from .service_integrations import ServiceIntegrationManager
from .models import (
    WebSocketAuthMessage,
    WebSocketPingMessage,
    WebSocketPongMessage,
    ChatStreamMessage,
    ToolProgressMessage,
    CostUpdateMessage,
    SystemStatusMessage
)

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")))
logger = logging.getLogger(__name__)

# Secure configuration and middleware imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../pyairtable-common'))

try:
    from pyairtable_common.config import initialize_secrets, get_secret, close_secrets, ConfigurationError
    from pyairtable_common.middleware import setup_security_middleware, verify_api_key_secure
    SECURE_CONFIG_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ Secure configuration not available: {e}")
    SECURE_CONFIG_AVAILABLE = False
    # Fallback security functions
    def verify_api_key_secure(provided, expected):
        return provided == expected

# Configuration
AIRTABLE_GATEWAY_URL = os.getenv("AIRTABLE_GATEWAY_URL", "http://localhost:8002")
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")
LLM_ORCHESTRATOR_URL = os.getenv("LLM_ORCHESTRATOR_URL", "http://localhost:8003")

# Initialize secure configuration
config_manager = None
if SECURE_CONFIG_AVAILABLE:
    try:
        config_manager = initialize_secrets()
        logger.info("✅ Secure configuration manager initialized")
    except Exception as e:
        logger.error(f"💥 Failed to initialize secure configuration: {e}")
        raise

# Get API key from secure manager or fallback to environment
API_KEY = None
if config_manager:
    try:
        API_KEY = get_secret("API_KEY")
    except Exception as e:
        logger.error(f"💥 Failed to get API_KEY from secure config: {e}")
        raise ValueError("API_KEY could not be retrieved from secure configuration")
else:
    API_KEY = os.getenv("API_KEY")
    if not API_KEY:
        logger.error("💥 CRITICAL: API_KEY environment variable is required")
        raise ValueError("API_KEY environment variable is required")
# SECURITY: Replace wildcard with specific origins
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
HEALTH_CHECK_TIMEOUT = int(os.getenv("HEALTH_CHECK_TIMEOUT", "5"))

# HTTP client for service communication
http_client = httpx.AsyncClient(timeout=30.0)

# WebSocket connection manager
websocket_manager = WebSocketConnectionManager(
    max_connections_per_session=5,
    message_rate_limit=100,  # messages per minute
    rate_limit_window=60,
    max_queued_messages=1000,
    message_queue_ttl=3600,
    ping_interval=30,
    connection_timeout=300
)

# Service integration manager
service_integrations = ServiceIntegrationManager(
    llm_orchestrator_url=LLM_ORCHESTRATOR_URL,
    mcp_server_url=MCP_SERVER_URL,
    cost_tracking_url=os.getenv("COST_TRACKING_URL"),  # Optional cost tracking service
    websocket_broadcaster=None  # Will be set after initialization
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting PyAirtable API Gateway...")
    logger.info(f"Routing to services:")
    logger.info(f"  - Airtable Gateway: {AIRTABLE_GATEWAY_URL}")
    logger.info(f"  - MCP Server: {MCP_SERVER_URL}")
    logger.info(f"  - LLM Orchestrator: {LLM_ORCHESTRATOR_URL}")
    
    # Start WebSocket background tasks
    await websocket_manager.start_background_tasks()
    logger.info("WebSocket manager started")
    
    # Configure service integrations with WebSocket broadcasting
    service_integrations.websocket_broadcaster = create_websocket_broadcaster()
    await service_integrations.start_integrations()
    logger.info("Service integrations started")
    
    yield
    
    # Shutdown
    await service_integrations.stop_integrations()
    logger.info("Service integrations stopped")
    
    await websocket_manager.stop_background_tasks()
    logger.info("WebSocket manager stopped")
    
    await http_client.aclose()
    if config_manager:
        await close_secrets()
        logger.info("Closed secure configuration manager")
    logger.info("Shutting down PyAirtable API Gateway...")


# Initialize FastAPI app
app = FastAPI(
    title="PyAirtable API Gateway",
    description="Central entry point for PyAirtable microservices",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware with security hardening
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key"],
)

# Add security middleware
if SECURE_CONFIG_AVAILABLE:
    setup_security_middleware(app, rate_limit_calls=1000, rate_limit_period=60)


def verify_api_key(x_api_key: Optional[str] = Header(None)) -> bool:
    """Secure API key verification with constant-time comparison"""
    if not verify_api_key_secure(x_api_key or "", API_KEY or ""):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return True


def verify_api_key_websocket(api_key: str) -> bool:
    """WebSocket API key verification"""
    return verify_api_key_secure(api_key or "", API_KEY or "")


def create_websocket_broadcaster():
    """Create WebSocket broadcaster function for service integrations"""
    async def broadcast(message_type: str, session_id: str, data: Dict[str, Any]):
        """Broadcast message to WebSocket clients"""
        try:
            if message_type == "chat_stream":
                message = ChatStreamMessage(session_id=session_id, data=data)
            elif message_type == "tool_progress":
                message = ToolProgressMessage(session_id=session_id, data=data)
            elif message_type == "cost_update":
                message = CostUpdateMessage(session_id=session_id, data=data)
            elif message_type == "system_status":
                message = SystemStatusMessage(session_id=session_id, data=data)
            else:
                logger.warning(f"Unknown message type for broadcasting: {message_type}")
                return
            
            if session_id == "*":
                # Broadcast to all sessions
                for active_session_id in websocket_manager.session_connections.keys():
                    message.session_id = active_session_id
                    await websocket_manager.broadcast_to_session(active_session_id, message)
            else:
                # Broadcast to specific session
                await websocket_manager.broadcast_to_session(session_id, message)
                
        except Exception as e:
            logger.error(f"WebSocket broadcast error: {e}")
    
    return broadcast


async def check_service_health(service_url: str, service_name: str) -> Dict[str, Any]:
    """Check health of a specific service"""
    try:
        response = await http_client.get(
            f"{service_url}/health",
            timeout=HEALTH_CHECK_TIMEOUT
        )
        if response.status_code == 200:
            return {
                "name": service_name,
                "status": "healthy",
                "url": service_url,
                "response_time": response.elapsed.total_seconds()
            }
        else:
            return {
                "name": service_name,
                "status": "unhealthy",
                "url": service_url,
                "error": f"HTTP {response.status_code}"
            }
    except Exception as e:
        return {
            "name": service_name,
            "status": "unreachable",
            "url": service_url,
            "error": str(e)
        }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "PyAirtable API Gateway",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/health",
            "chat": "/api/chat",
            "tools": "/api/tools",
            "airtable": "/api/airtable/*",
            "websocket": "/ws"
        }
    }


@app.get("/api/health")
async def health_check():
    """Aggregate health check for all services"""
    services = [
        (AIRTABLE_GATEWAY_URL, "airtable-gateway"),
        (MCP_SERVER_URL, "mcp-server"),
        (LLM_ORCHESTRATOR_URL, "llm-orchestrator")
    ]
    
    # Check all services concurrently
    health_checks = [
        check_service_health(url, name) for url, name in services
    ]
    results = await asyncio.gather(*health_checks, return_exceptions=True)
    
    # Process results
    service_status = []
    overall_healthy = True
    
    for result in results:
        if isinstance(result, Exception):
            service_status.append({
                "name": "unknown",
                "status": "error", 
                "error": str(result)
            })
            overall_healthy = False
        else:
            service_status.append(result)
            if result["status"] != "healthy":
                overall_healthy = False
    
    return {
        "status": "healthy" if overall_healthy else "degraded",
        "gateway": "healthy",
        "services": service_status,
        "websocket_stats": websocket_manager.get_stats(),
        "timestamp": "2025-07-31T19:30:00Z"
    }


@app.post("/api/chat")
async def chat_proxy(request: Request, x_api_key: Optional[str] = Header(None)):
    """Proxy chat requests to LLM Orchestrator with optional streaming"""
    verify_api_key(x_api_key)
    
    try:
        # Get request body
        body = await request.json()
        session_id = body.get("session_id")
        enable_streaming = body.get("stream", False)
        
        # Use streaming if requested and session_id is provided
        if enable_streaming and session_id:
            return await service_integrations.handle_chat_stream(session_id, body)
        else:
            # Standard non-streaming request
            response = await http_client.post(
                f"{LLM_ORCHESTRATOR_URL}/chat",
                json=body,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        
    except httpx.HTTPStatusError as e:
        logger.error(f"LLM Orchestrator error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Chat proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/tools")
async def tools_proxy(x_api_key: Optional[str] = Header(None)):
    """Proxy tools requests to LLM Orchestrator"""
    verify_api_key(x_api_key)
    
    try:
        response = await http_client.get(f"{LLM_ORCHESTRATOR_URL}/tools")
        response.raise_for_status()
        return response.json()
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Tools proxy error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Tools proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.api_route("/api/airtable/{path:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"])
async def airtable_proxy(
    path: str,
    request: Request,
    x_api_key: Optional[str] = Header(None)
):
    """Proxy Airtable requests to Airtable Gateway"""
    verify_api_key(x_api_key)
    
    try:
        # Build target URL
        target_url = f"{AIRTABLE_GATEWAY_URL}/{path}"
        
        # Get request body if present
        body = None
        if request.method in ["POST", "PATCH", "PUT"]:
            body = await request.json()
        
        # Forward request
        response = await http_client.request(
            method=request.method,
            url=target_url,
            json=body,
            params=dict(request.query_params),
            headers={"X-API-Key": API_KEY}  # Use gateway's API key
        )
        response.raise_for_status()
        
        return response.json()
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Airtable Gateway error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Airtable proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/execute-tool")
async def execute_tool_proxy(request: Request, x_api_key: Optional[str] = Header(None)):
    """Proxy tool execution with progress updates"""
    verify_api_key(x_api_key)
    
    try:
        body = await request.json()
        session_id = body.get("session_id")
        enable_progress = body.get("stream_progress", False)
        
        # Use progress streaming if requested and session_id is provided
        if enable_progress and session_id:
            return await service_integrations.handle_tool_execution(session_id, body)
        else:
            # Standard non-streaming request
            response = await http_client.post(
                f"{LLM_ORCHESTRATOR_URL}/execute-tool",
                json=body,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Tool execution proxy error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Tool execution proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{session_id}/history")
async def session_history_proxy(session_id: str, x_api_key: Optional[str] = Header(None)):
    """Proxy session history requests"""
    verify_api_key(x_api_key)
    
    try:
        response = await http_client.get(f"{LLM_ORCHESTRATOR_URL}/sessions/{session_id}/history")
        response.raise_for_status()
        return response.json()
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Session history proxy error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Session history proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/sessions/{session_id}")
async def clear_session_proxy(session_id: str, x_api_key: Optional[str] = Header(None)):
    """Proxy clear session requests"""
    verify_api_key(x_api_key)
    
    try:
        response = await http_client.delete(f"{LLM_ORCHESTRATOR_URL}/sessions/{session_id}")
        response.raise_for_status()
        return response.json()
        
    except httpx.HTTPStatusError as e:
        logger.error(f"Clear session proxy error: {e}")
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except Exception as e:
        logger.error(f"Clear session proxy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    session_id = None
    
    try:
        # Extract session_id from query parameters
        session_id = websocket.query_params.get("session_id")
        if not session_id:
            await websocket.close(code=1008, reason="session_id parameter required")
            return
        
        client_info = {
            "user_agent": websocket.headers.get("user-agent", ""),
            "origin": websocket.headers.get("origin", ""),
            "ip": websocket.client.host if websocket.client else "unknown"
        }
        
        # Connect to WebSocket manager
        connected = await websocket_manager.connect(websocket, session_id, client_info)
        if not connected:
            return
        
        logger.info(f"WebSocket connection established: session={session_id}")
        
        # Wait for authentication message
        auth_timeout = 10  # seconds
        try:
            auth_data = await asyncio.wait_for(websocket.receive_text(), timeout=auth_timeout)
            auth_message = json.loads(auth_data)
            
            if auth_message.get("type") != "auth":
                await websocket.close(code=1008, reason="Authentication required")
                return
            
            api_key = auth_message.get("api_key")
            if not api_key:
                await websocket.close(code=1008, reason="API key required")
                return
            
            # Authenticate
            authenticated = await websocket_manager.authenticate(
                websocket, api_key, verify_api_key_websocket
            )
            
            if not authenticated:
                await websocket.close(code=1008, reason="Authentication failed")
                return
            
            logger.info(f"WebSocket authenticated: session={session_id}")
            
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="Authentication timeout")
            return
        except json.JSONDecodeError:
            await websocket.close(code=1008, reason="Invalid JSON")
            return
        
        # Handle messages
        while True:
            try:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                message_type = message_data.get("type")
                
                # Handle ping/pong
                if message_type == "ping":
                    pong_message = WebSocketPongMessage()
                    await websocket_manager.send_message(websocket, pong_message)
                    continue
                
                # Handle other message types
                await handle_websocket_message(websocket, session_id, message_data)
                
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                await websocket_manager.send_error(websocket, "invalid_json", "Invalid JSON format")
            except Exception as e:
                logger.error(f"WebSocket message handling error: {e}")
                await websocket_manager.send_error(websocket, "message_error", str(e))
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await websocket_manager.disconnect(websocket)


async def handle_websocket_message(websocket: WebSocket, session_id: str, message_data: Dict[str, Any]):
    """Handle incoming WebSocket messages"""
    message_type = message_data.get("type")
    
    try:
        if message_type == "subscribe":
            # Handle subscription to specific message types
            subscription_types = message_data.get("types", [])
            logger.info(f"WebSocket subscription: session={session_id}, types={subscription_types}")
            # Store subscription preferences (could be added to ConnectionInfo)
            
        elif message_type == "unsubscribe":
            # Handle unsubscription
            unsubscribe_types = message_data.get("types", [])
            logger.info(f"WebSocket unsubscription: session={session_id}, types={unsubscribe_types}")
            
        else:
            await websocket_manager.send_error(websocket, "unknown_message_type", f"Unknown message type: {message_type}")
            
    except Exception as e:
        logger.error(f"Error handling WebSocket message: {e}")
        await websocket_manager.send_error(websocket, "message_handling_error", str(e))


# Integration functions for service updates
async def broadcast_chat_stream(session_id: str, chat_data: Dict[str, Any]):
    """Broadcast chat streaming updates to WebSocket clients"""
    message = ChatStreamMessage(session_id=session_id, data=chat_data)
    await websocket_manager.broadcast_to_session(session_id, message)


async def broadcast_tool_progress(session_id: str, tool_data: Dict[str, Any]):
    """Broadcast tool execution progress to WebSocket clients"""
    message = ToolProgressMessage(session_id=session_id, data=tool_data)
    await websocket_manager.broadcast_to_session(session_id, message)


async def broadcast_cost_update(session_id: str, cost_data: Dict[str, Any]):
    """Broadcast cost tracking updates to WebSocket clients"""
    message = CostUpdateMessage(session_id=session_id, data=cost_data)
    await websocket_manager.broadcast_to_session(session_id, message)


async def broadcast_system_status(session_id: str, status_data: Dict[str, Any]):
    """Broadcast system status updates to WebSocket clients"""
    message = SystemStatusMessage(session_id=session_id, data=status_data)
    await websocket_manager.broadcast_to_session(session_id, message)


@app.get("/api/websocket/stats")
async def websocket_stats(x_api_key: Optional[str] = Header(None)):
    """Get WebSocket connection statistics"""
    verify_api_key(x_api_key)
    return websocket_manager.get_stats()


# Error handlers
@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Endpoint not found",
            "path": str(request.url.path),
            "available_endpoints": [
                "/api/health",
                "/api/chat", 
                "/api/tools",
                "/api/airtable/*",
                "/api/execute-tool",
                "/api/sessions/{session_id}/history",
                "/ws",
                "/api/websocket/stats"
            ]
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))