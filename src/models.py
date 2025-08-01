"""
WebSocket models for PyAirtable API Gateway
"""

from typing import Dict, Any, Optional, Union, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class WebSocketMessage(BaseModel):
    """Base WebSocket message model"""
    type: str = Field(..., description="Message type")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Message timestamp")
    session_id: str = Field(..., description="Session identifier")
    data: Dict[str, Any] = Field(default_factory=dict, description="Message payload")


class ChatStreamMessage(WebSocketMessage):
    """Chat streaming message from LLM Orchestrator"""
    type: Literal["chat_stream"] = "chat_stream"
    data: Dict[str, Any] = Field(..., description="Chat stream data containing delta, token_count, etc.")


class ToolProgressMessage(WebSocketMessage):
    """Tool execution progress update from MCP Server"""
    type: Literal["tool_progress"] = "tool_progress"
    data: Dict[str, Any] = Field(..., description="Tool progress data containing tool_name, status, progress, result")


class CostUpdateMessage(WebSocketMessage):
    """Cost tracking update message"""
    type: Literal["cost_update"] = "cost_update"
    data: Dict[str, Any] = Field(..., description="Cost update data containing current_cost, budget_remaining, cost_breakdown")


class SystemStatusMessage(WebSocketMessage):
    """System health and status notification"""
    type: Literal["system_status"] = "system_status"
    data: Dict[str, Any] = Field(..., description="System status data containing service_health, alerts, performance_metrics")


class WebSocketConnectionRequest(BaseModel):
    """WebSocket connection authentication request"""
    api_key: str = Field(..., description="API key for authentication")
    session_id: str = Field(..., description="Session identifier")
    client_info: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Client information")


class WebSocketErrorMessage(WebSocketMessage):
    """WebSocket error message"""
    type: Literal["error"] = "error"
    data: Dict[str, Any] = Field(..., description="Error data containing error_code, message, details")


class WebSocketAuthMessage(BaseModel):
    """WebSocket authentication message"""
    type: Literal["auth"] = "auth"
    api_key: str = Field(..., description="API key for authentication")
    session_id: str = Field(..., description="Session identifier")


class WebSocketPingMessage(BaseModel):
    """WebSocket ping message for connection health"""
    type: Literal["ping"] = "ping"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WebSocketPongMessage(BaseModel):
    """WebSocket pong response message"""
    type: Literal["pong"] = "pong"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# Union type for all WebSocket messages
WebSocketMessageTypes = Union[
    ChatStreamMessage,
    ToolProgressMessage,
    CostUpdateMessage,
    SystemStatusMessage,
    WebSocketErrorMessage,
    WebSocketPingMessage,
    WebSocketPongMessage
]


class ConnectionInfo(BaseModel):
    """Information about a WebSocket connection"""
    session_id: str
    client_info: Dict[str, Any]
    connected_at: datetime
    last_activity: datetime
    message_count: int = 0
    authenticated: bool = False