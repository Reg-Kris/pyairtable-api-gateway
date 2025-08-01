"""
WebSocket Connection Manager for PyAirtable API Gateway
"""

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from .models import (
    WebSocketMessage,
    WebSocketErrorMessage,
    WebSocketAuthMessage,
    WebSocketPingMessage,
    WebSocketPongMessage,
    ConnectionInfo,
    ChatStreamMessage,
    ToolProgressMessage,
    CostUpdateMessage,
    SystemStatusMessage
)

logger = logging.getLogger(__name__)


@dataclass
class QueuedMessage:
    """Represents a queued message for offline clients"""
    message: WebSocketMessage
    queued_at: datetime
    priority: int = 0  # Higher number = higher priority


@dataclass
class RateLimitInfo:
    """Rate limiting information for a connection"""
    message_count: int = 0
    window_start: datetime = field(default_factory=datetime.utcnow)
    blocked_until: Optional[datetime] = None


class WebSocketConnectionManager:
    """Manages WebSocket connections with authentication, rate limiting, and message queuing"""
    
    def __init__(
        self,
        max_connections_per_session: int = 5,
        message_rate_limit: int = 100,  # messages per minute
        rate_limit_window: int = 60,  # seconds
        max_queued_messages: int = 1000,
        message_queue_ttl: int = 3600,  # seconds
        ping_interval: int = 30,  # seconds
        connection_timeout: int = 300  # seconds
    ):
        self.max_connections_per_session = max_connections_per_session
        self.message_rate_limit = message_rate_limit
        self.rate_limit_window = rate_limit_window
        self.max_queued_messages = max_queued_messages
        self.message_queue_ttl = message_queue_ttl
        self.ping_interval = ping_interval
        self.connection_timeout = connection_timeout
        
        # Connection tracking
        self.active_connections: Dict[str, List[WebSocket]] = defaultdict(list)
        self.connection_info: Dict[WebSocket, ConnectionInfo] = {}
        self.session_connections: Dict[str, Set[WebSocket]] = defaultdict(set)
        
        # Rate limiting
        self.rate_limits: Dict[WebSocket, RateLimitInfo] = {}
        
        # Message queuing for offline clients
        self.message_queues: Dict[str, deque] = defaultdict(lambda: deque(maxlen=self.max_queued_messages))
        
        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.stats = {
            "total_connections": 0,
            "active_connections": 0,
            "messages_sent": 0,
            "messages_queued": 0,
            "rate_limit_violations": 0,
            "authentication_failures": 0
        }
    
    async def start_background_tasks(self):
        """Start background maintenance tasks"""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        if not self._ping_task:
            self._ping_task = asyncio.create_task(self._ping_loop())
    
    async def stop_background_tasks(self):
        """Stop background maintenance tasks"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            
        if self._ping_task:
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass
            self._ping_task = None
    
    async def connect(self, websocket: WebSocket, session_id: str, client_info: Dict = None) -> bool:
        """
        Accept a new WebSocket connection
        Returns True if connection was accepted, False otherwise
        """
        # Check connection limits
        if len(self.session_connections[session_id]) >= self.max_connections_per_session:
            logger.warning(f"Connection limit exceeded for session {session_id}")
            await websocket.close(code=1008, reason="Connection limit exceeded")
            return False
        
        await websocket.accept()
        
        # Initialize connection info
        connection_info = ConnectionInfo(
            session_id=session_id,
            client_info=client_info or {},
            connected_at=datetime.utcnow(),
            last_activity=datetime.utcnow(),
            authenticated=False
        )
        
        self.connection_info[websocket] = connection_info
        self.session_connections[session_id].add(websocket)
        self.rate_limits[websocket] = RateLimitInfo()
        
        # Update statistics
        self.stats["total_connections"] += 1
        self.stats["active_connections"] = len(self.connection_info)
        
        logger.info(f"WebSocket connected: session={session_id}, total_active={self.stats['active_connections']}")
        return True
    
    async def disconnect(self, websocket: WebSocket):
        """Handle WebSocket disconnection"""
        if websocket not in self.connection_info:
            return
        
        connection_info = self.connection_info[websocket]
        session_id = connection_info.session_id
        
        # Remove from tracking
        self.session_connections[session_id].discard(websocket)
        if not self.session_connections[session_id]:
            del self.session_connections[session_id]
        
        del self.connection_info[websocket]
        self.rate_limits.pop(websocket, None)
        
        # Update statistics
        self.stats["active_connections"] = len(self.connection_info)
        
        logger.info(f"WebSocket disconnected: session={session_id}, total_active={self.stats['active_connections']}")
    
    async def authenticate(self, websocket: WebSocket, api_key: str, verify_api_key_func) -> bool:
        """Authenticate a WebSocket connection"""
        if websocket not in self.connection_info:
            return False
        
        try:
            # Use the provided API key verification function
            if not verify_api_key_func(api_key):
                self.stats["authentication_failures"] += 1
                await self.send_error(websocket, "authentication_failed", "Invalid API key")
                return False
            
            # Mark as authenticated
            self.connection_info[websocket].authenticated = True
            
            # Send queued messages if any
            session_id = self.connection_info[websocket].session_id
            await self._send_queued_messages(websocket, session_id)
            
            logger.info(f"WebSocket authenticated: session={session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            self.stats["authentication_failures"] += 1
            await self.send_error(websocket, "authentication_error", str(e))
            return False
    
    async def is_rate_limited(self, websocket: WebSocket) -> bool:
        """Check if connection is rate limited"""
        if websocket not in self.rate_limits:
            return False
        
        rate_info = self.rate_limits[websocket]
        now = datetime.utcnow()
        
        # Check if still blocked
        if rate_info.blocked_until and now < rate_info.blocked_until:
            return True
        
        # Reset window if needed
        if now - rate_info.window_start > timedelta(seconds=self.rate_limit_window):
            rate_info.message_count = 0
            rate_info.window_start = now
            rate_info.blocked_until = None
        
        # Check rate limit
        if rate_info.message_count >= self.message_rate_limit:
            rate_info.blocked_until = now + timedelta(seconds=self.rate_limit_window)
            self.stats["rate_limit_violations"] += 1
            return True
        
        return False
    
    async def send_message(self, websocket: WebSocket, message: WebSocketMessage) -> bool:
        """Send a message to a specific WebSocket connection"""
        if websocket not in self.connection_info:
            return False
        
        connection_info = self.connection_info[websocket]
        
        # Check authentication
        if not connection_info.authenticated:
            logger.warning(f"Attempted to send message to unauthenticated connection: {connection_info.session_id}")
            return False
        
        # Check rate limiting
        if await self.is_rate_limited(websocket):
            logger.warning(f"Rate limited connection: {connection_info.session_id}")
            await self.send_error(websocket, "rate_limited", "Message rate limit exceeded")
            return False
        
        try:
            # Send message
            message_json = message.model_dump_json()
            await websocket.send_text(message_json)
            
            # Update statistics and rate limiting
            self.rate_limits[websocket].message_count += 1
            connection_info.message_count += 1
            connection_info.last_activity = datetime.utcnow()
            self.stats["messages_sent"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to {connection_info.session_id}: {e}")
            return False
    
    async def broadcast_to_session(self, session_id: str, message: WebSocketMessage) -> int:
        """Broadcast a message to all connections in a session"""
        sent_count = 0
        
        if session_id not in self.session_connections:
            # Queue message for offline session
            await self._queue_message(session_id, message)
            return 0
        
        connections = list(self.session_connections[session_id])
        for websocket in connections:
            if await self.send_message(websocket, message):
                sent_count += 1
        
        # If no messages were sent, queue the message
        if sent_count == 0:
            await self._queue_message(session_id, message)
        
        return sent_count
    
    async def send_error(self, websocket: WebSocket, error_code: str, message: str):
        """Send an error message to a WebSocket connection"""
        if websocket not in self.connection_info:
            return
        
        connection_info = self.connection_info[websocket]
        error_message = WebSocketErrorMessage(
            session_id=connection_info.session_id,
            data={
                "error_code": error_code,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        try:
            await websocket.send_text(error_message.model_dump_json())
        except Exception as e:
            logger.error(f"Error sending error message: {e}")
    
    async def _queue_message(self, session_id: str, message: WebSocketMessage):
        """Queue a message for offline delivery"""
        queued_message = QueuedMessage(
            message=message,
            queued_at=datetime.utcnow(),
            priority=self._get_message_priority(message)
        )
        
        self.message_queues[session_id].append(queued_message)
        self.stats["messages_queued"] += 1
        
        logger.debug(f"Queued message for session {session_id}: {message.type}")
    
    async def _send_queued_messages(self, websocket: WebSocket, session_id: str):
        """Send queued messages to a newly connected client"""
        if session_id not in self.message_queues:
            return
        
        queue = self.message_queues[session_id]
        now = datetime.utcnow()
        sent_count = 0
        
        # Sort by priority and age (higher priority and newer messages first)
        messages = sorted(queue, key=lambda x: (-x.priority, -x.queued_at.timestamp()))
        
        for queued_message in messages:
            # Skip expired messages
            if now - queued_message.queued_at > timedelta(seconds=self.message_queue_ttl):
                continue
            
            if await self.send_message(websocket, queued_message.message):
                sent_count += 1
        
        # Clear the queue after sending
        queue.clear()
        
        if sent_count > 0:
            logger.info(f"Sent {sent_count} queued messages to session {session_id}")
    
    def _get_message_priority(self, message: WebSocketMessage) -> int:
        """Get priority for message queuing (higher = more important)"""
        if isinstance(message, SystemStatusMessage):
            return 10
        elif isinstance(message, WebSocketErrorMessage):
            return 9
        elif isinstance(message, CostUpdateMessage):
            return 8
        elif isinstance(message, ToolProgressMessage):
            return 7
        elif isinstance(message, ChatStreamMessage):
            return 5
        else:
            return 1
    
    async def _cleanup_loop(self):
        """Periodic cleanup of stale connections and expired messages"""
        while True:
            try:
                await asyncio.sleep(60)  # Run cleanup every minute
                await self._cleanup_stale_connections()
                await self._cleanup_expired_messages()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
    
    async def _ping_loop(self):
        """Periodic ping to maintain connection health"""
        while True:
            try:
                await asyncio.sleep(self.ping_interval)
                await self._send_ping_to_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Ping loop error: {e}")
    
    async def _cleanup_stale_connections(self):
        """Remove stale connections that haven't responded to pings"""
        now = datetime.utcnow()
        stale_connections = []
        
        for websocket, connection_info in self.connection_info.items():
            if now - connection_info.last_activity > timedelta(seconds=self.connection_timeout):
                stale_connections.append(websocket)
        
        for websocket in stale_connections:
            logger.info(f"Closing stale connection: {self.connection_info[websocket].session_id}")
            try:
                await websocket.close(code=1000, reason="Connection timeout")
            except Exception:
                pass
            await self.disconnect(websocket)
    
    async def _cleanup_expired_messages(self):
        """Remove expired messages from queues"""
        now = datetime.utcnow()
        ttl_delta = timedelta(seconds=self.message_queue_ttl)
        
        for session_id, queue in self.message_queues.items():
            # Remove expired messages
            while queue and now - queue[0].queued_at > ttl_delta:
                queue.popleft()
            
            # Remove empty queues
            if not queue and session_id in self.message_queues:
                del self.message_queues[session_id]
    
    async def _send_ping_to_all(self):
        """Send ping messages to all authenticated connections"""
        ping_message = WebSocketPingMessage()
        
        for websocket, connection_info in list(self.connection_info.items()):
            if connection_info.authenticated:
                try:
                    await websocket.send_text(ping_message.model_dump_json())
                except Exception as e:
                    logger.warning(f"Failed to ping {connection_info.session_id}: {e}")
                    await self.disconnect(websocket)
    
    def get_stats(self) -> Dict:
        """Get connection manager statistics"""
        return {
            **self.stats,
            "active_sessions": len(self.session_connections),
            "queued_messages_total": sum(len(queue) for queue in self.message_queues.values()),
            "average_messages_per_connection": (
                self.stats["messages_sent"] / max(1, self.stats["total_connections"])
            )
        }