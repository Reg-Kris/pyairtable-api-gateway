#!/usr/bin/env python3
"""
Example WebSocket client for PyAirtable API Gateway
This demonstrates how to connect and interact with the WebSocket endpoint
"""

import asyncio
import json
import logging
from typing import Dict, Any
import websockets
from websockets.exceptions import ConnectionClosed

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PyAirtableWebSocketClient:
    """Example WebSocket client for PyAirtable API Gateway"""
    
    def __init__(self, gateway_url: str, api_key: str, session_id: str):
        self.gateway_url = gateway_url
        self.api_key = api_key
        self.session_id = session_id
        self.websocket = None
        self.connected = False
        self.authenticated = False
        
    async def connect(self):
        """Connect to the WebSocket endpoint"""
        try:
            # Connect to WebSocket with session_id parameter
            uri = f"{self.gateway_url}/ws?session_id={self.session_id}"
            logger.info(f"Connecting to {uri}")
            
            self.websocket = await websockets.connect(uri)
            self.connected = True
            logger.info("WebSocket connected")
            
            # Send authentication message
            auth_message = {
                "type": "auth",
                "api_key": self.api_key,
                "session_id": self.session_id
            }
            
            await self.websocket.send(json.dumps(auth_message))
            logger.info("Authentication message sent")
            
            # Start message handling
            await self.handle_messages()
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            self.connected = False
    
    async def handle_messages(self):
        """Handle incoming WebSocket messages"""
        try:
            async for message in self.websocket:
                await self.process_message(json.loads(message))
                
        except ConnectionClosed:
            logger.info("WebSocket connection closed")
            self.connected = False
            self.authenticated = False
        except Exception as e:
            logger.error(f"Message handling error: {e}")
    
    async def process_message(self, message: Dict[str, Any]):
        """Process incoming message"""
        message_type = message.get("type")
        
        if message_type == "error":
            logger.error(f"Server error: {message.get('data', {})}")
            
        elif message_type == "chat_stream":
            # Handle real-time chat streaming
            data = message.get("data", {})
            delta = data.get("delta", "")
            is_complete = data.get("is_complete", False)
            
            if delta:
                print(f"Chat delta: {delta}", end="", flush=True)
            
            if is_complete:
                print("\n[Chat stream complete]")
                
        elif message_type == "tool_progress":
            # Handle tool execution progress
            data = message.get("data", {})
            tool_name = data.get("tool_name", "unknown")
            status = data.get("status", "unknown")
            progress = data.get("progress", 0)
            message_text = data.get("message", "")
            
            logger.info(f"Tool {tool_name}: {status} ({progress}%) - {message_text}")
            
        elif message_type == "cost_update":
            # Handle cost tracking updates
            data = message.get("data", {})
            current_cost = data.get("current_cost", 0)
            budget_remaining = data.get("budget_remaining", 0)
            
            logger.info(f"Cost update: ${current_cost:.2f} spent, ${budget_remaining:.2f} remaining")
            
        elif message_type == "system_status":
            # Handle system status updates
            data = message.get("data", {})
            overall_status = data.get("overall_status", "unknown")
            alerts = data.get("alerts", [])
            
            logger.info(f"System status: {overall_status}")
            for alert in alerts:
                logger.warning(f"Alert ({alert.get('level')}): {alert.get('message')}")
                
        elif message_type == "pong":
            # Handle pong responses
            logger.debug("Received pong")
            
        else:
            logger.info(f"Received {message_type}: {message}")
    
    async def send_ping(self):
        """Send ping message"""
        if self.connected and self.websocket:
            ping_message = {"type": "ping"}
            await self.websocket.send(json.dumps(ping_message))
            logger.debug("Sent ping")
    
    async def subscribe(self, message_types: list):
        """Subscribe to specific message types"""
        if self.connected and self.websocket:
            subscribe_message = {
                "type": "subscribe",
                "types": message_types
            }
            await self.websocket.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to: {message_types}")
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        if self.websocket:
            await self.websocket.close()
            logger.info("WebSocket disconnected")
        
        self.connected = False
        self.authenticated = False


async def main():
    """Example usage"""
    # Configuration
    GATEWAY_URL = "ws://localhost:8000"
    API_KEY = "your-api-key-here"  # Replace with your actual API key
    SESSION_ID = "example-session-123"
    
    # Create client
    client = PyAirtableWebSocketClient(GATEWAY_URL, API_KEY, SESSION_ID)
    
    try:
        # Connect and start message handling
        connection_task = asyncio.create_task(client.connect())
        
        # Wait a bit for connection to establish
        await asyncio.sleep(2)
        
        if client.connected:
            # Subscribe to all message types
            await client.subscribe([
                "chat_stream",
                "tool_progress", 
                "cost_update",
                "system_status"
            ])
            
            # Send periodic pings
            while client.connected:
                await client.send_ping()
                await asyncio.sleep(30)  # Ping every 30 seconds
        
        await connection_task
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await client.disconnect()
    except Exception as e:
        logger.error(f"Client error: {e}")
        await client.disconnect()


if __name__ == "__main__":
    print("PyAirtable WebSocket Client Example")
    print("==================================")
    print("This example demonstrates connecting to the PyAirtable API Gateway WebSocket.")
    print("Make sure to:")
    print("1. Update the API_KEY variable with your actual API key")
    print("2. Start the PyAirtable API Gateway server")
    print("3. Install websockets: pip install websockets")
    print()
    
    # Run the client
    asyncio.run(main())