"""
Service integrations for WebSocket real-time updates
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
import httpx
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class ServiceIntegrationManager:
    """Manages real-time integrations with backend services"""
    
    def __init__(
        self,
        llm_orchestrator_url: str,
        mcp_server_url: str,
        cost_tracking_url: Optional[str] = None,
        websocket_broadcaster: Optional[Callable] = None
    ):
        self.llm_orchestrator_url = llm_orchestrator_url
        self.mcp_server_url = mcp_server_url
        self.cost_tracking_url = cost_tracking_url
        self.websocket_broadcaster = websocket_broadcaster
        
        # HTTP clients for service communication
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # Polling intervals (in seconds)
        self.cost_polling_interval = 60  # Poll cost updates every minute
        self.status_polling_interval = 30  # Poll service status every 30 seconds
        
        # Background tasks
        self._cost_polling_task: Optional[asyncio.Task] = None
        self._status_polling_task: Optional[asyncio.Task] = None
        
        # State tracking
        self.last_cost_data: Dict[str, Any] = {}
        self.last_status_data: Dict[str, Any] = {}
        
    async def start_integrations(self):
        """Start background integration tasks"""
        logger.info("Starting service integrations...")
        
        # Start cost tracking polling if URL is provided
        if self.cost_tracking_url and not self._cost_polling_task:
            self._cost_polling_task = asyncio.create_task(self._cost_polling_loop())
            logger.info("Started cost tracking integration")
        
        # Start status monitoring
        if not self._status_polling_task:
            self._status_polling_task = asyncio.create_task(self._status_polling_loop())
            logger.info("Started system status monitoring")
    
    async def stop_integrations(self):
        """Stop background integration tasks"""
        logger.info("Stopping service integrations...")
        
        # Stop cost polling
        if self._cost_polling_task:
            self._cost_polling_task.cancel()
            try:
                await self._cost_polling_task
            except asyncio.CancelledError:
                pass
            self._cost_polling_task = None
        
        # Stop status polling
        if self._status_polling_task:
            self._status_polling_task.cancel()
            try:
                await self._status_polling_task
            except asyncio.CancelledError:
                pass
            self._status_polling_task = None
        
        # Close HTTP client
        await self.http_client.aclose()
        
        logger.info("Service integrations stopped")
    
    async def handle_chat_stream(self, session_id: str, chat_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle chat streaming with real-time WebSocket updates
        This would be called from the chat endpoint to enable streaming
        """
        try:
            # Start streaming request to LLM Orchestrator
            async with self.http_client.stream(
                "POST",
                f"{self.llm_orchestrator_url}/chat/stream",
                json={
                    **chat_request,
                    "stream": True,
                    "session_id": session_id
                },
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status_code != 200:
                    logger.error(f"Chat stream error: {response.status_code}")
                    return {"error": f"Stream error: {response.status_code}"}
                
                full_response = ""
                
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        try:
                            # Parse streaming chunk
                            chunk_data = json.loads(chunk)
                            
                            # Broadcast to WebSocket clients
                            if self.websocket_broadcaster:
                                await self.websocket_broadcaster(
                                    "chat_stream",
                                    session_id,
                                    {
                                        "delta": chunk_data.get("delta", ""),
                                        "token_count": chunk_data.get("token_count", 0),
                                        "is_complete": chunk_data.get("is_complete", False),
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                                )
                            
                            # Accumulate response
                            if "delta" in chunk_data:
                                full_response += chunk_data["delta"]
                            
                            # Check if streaming is complete
                            if chunk_data.get("is_complete", False):
                                break
                                
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON chunk: {chunk}")
                            continue
                
                return {
                    "response": full_response,
                    "session_id": session_id,
                    "streaming": True
                }
                
        except Exception as e:
            logger.error(f"Chat streaming error: {e}")
            return {"error": str(e)}
    
    async def handle_tool_execution(self, session_id: str, tool_request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tool execution with progress updates
        This would be called from the execute-tool endpoint
        """
        try:
            # Start tool execution request to MCP Server
            async with self.http_client.stream(
                "POST",
                f"{self.mcp_server_url}/tools/execute",
                json={
                    **tool_request,
                    "session_id": session_id,
                    "stream_progress": True
                },
                headers={"Content-Type": "application/json"}
            ) as response:
                
                if response.status_code != 200:
                    logger.error(f"Tool execution error: {response.status_code}")
                    return {"error": f"Tool execution error: {response.status_code}"}
                
                final_result = None
                
                async for chunk in response.aiter_text():
                    if chunk.strip():
                        try:
                            progress_data = json.loads(chunk)
                            
                            # Broadcast progress to WebSocket clients
                            if self.websocket_broadcaster:
                                await self.websocket_broadcaster(
                                    "tool_progress",
                                    session_id,
                                    {
                                        "tool_name": tool_request.get("tool_name", "unknown"),
                                        "status": progress_data.get("status", "running"),
                                        "progress": progress_data.get("progress", 0),
                                        "message": progress_data.get("message", ""),
                                        "result": progress_data.get("result"),
                                        "timestamp": datetime.utcnow().isoformat()
                                    }
                                )
                            
                            # Store final result
                            if progress_data.get("status") == "completed":
                                final_result = progress_data.get("result")
                                break
                            elif progress_data.get("status") == "failed":
                                return {"error": progress_data.get("message", "Tool execution failed")}
                                
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON progress chunk: {chunk}")
                            continue
                
                return {
                    "result": final_result,
                    "session_id": session_id,
                    "tool_name": tool_request.get("tool_name", "unknown")
                }
                
        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return {"error": str(e)}
    
    async def _cost_polling_loop(self):
        """Periodically poll for cost updates"""
        while True:
            try:
                await asyncio.sleep(self.cost_polling_interval)
                
                # Fetch current cost data
                response = await self.http_client.get(f"{self.cost_tracking_url}/api/costs/current")
                
                if response.status_code == 200:
                    cost_data = response.json()
                    
                    # Check if cost data has changed significantly
                    if self._cost_data_changed(cost_data):
                        self.last_cost_data = cost_data
                        
                        # Broadcast to all active sessions
                        if self.websocket_broadcaster:
                            await self.websocket_broadcaster(
                                "cost_update",
                                "*",  # Broadcast to all sessions
                                {
                                    "current_cost": cost_data.get("current_cost", 0),
                                    "budget_remaining": cost_data.get("budget_remaining", 0),
                                    "cost_breakdown": cost_data.get("breakdown", {}),
                                    "timestamp": datetime.utcnow().isoformat(),
                                    "period": cost_data.get("period", "monthly")
                                }
                            )
                        
                        logger.debug(f"Cost update broadcast: {cost_data.get('current_cost', 0)}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cost polling error: {e}")
    
    async def _status_polling_loop(self):
        """Periodically poll for system status updates"""
        while True:
            try:
                await asyncio.sleep(self.status_polling_interval)
                
                # Check health of all services
                services_health = await self._check_all_services_health()
                
                # Check if status has changed
                if self._status_data_changed(services_health):
                    self.last_status_data = services_health
                    
                    # Broadcast status updates
                    if self.websocket_broadcaster:
                        await self.websocket_broadcaster(
                            "system_status",
                            "*",  # Broadcast to all sessions
                            {
                                "services": services_health,
                                "overall_status": "healthy" if all(
                                    s.get("status") == "healthy" for s in services_health.values()
                                ) else "degraded",
                                "timestamp": datetime.utcnow().isoformat(),
                                "alerts": self._generate_alerts(services_health)
                            }
                        )
                    
                    logger.debug("System status update broadcast")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Status polling error: {e}")
    
    async def _check_all_services_health(self) -> Dict[str, Any]:
        """Check health of all backend services"""
        services = {
            "llm_orchestrator": self.llm_orchestrator_url,
            "mcp_server": self.mcp_server_url
        }
        
        if self.cost_tracking_url:
            services["cost_tracking"] = self.cost_tracking_url
        
        health_results = {}
        
        for service_name, service_url in services.items():
            try:
                start_time = datetime.utcnow()
                response = await self.http_client.get(
                    f"{service_url}/health",
                    timeout=5.0
                )
                response_time = (datetime.utcnow() - start_time).total_seconds()
                
                health_results[service_name] = {
                    "status": "healthy" if response.status_code == 200 else "unhealthy",
                    "response_time": response_time,
                    "last_check": datetime.utcnow().isoformat()
                }
                
            except Exception as e:
                health_results[service_name] = {
                    "status": "unreachable",
                    "error": str(e),
                    "last_check": datetime.utcnow().isoformat()
                }
        
        return health_results
    
    def _cost_data_changed(self, new_data: Dict[str, Any]) -> bool:
        """Check if cost data has changed significantly"""
        if not self.last_cost_data:
            return True
        
        # Check if current cost changed by more than $0.01
        old_cost = self.last_cost_data.get("current_cost", 0)
        new_cost = new_data.get("current_cost", 0)
        
        return abs(new_cost - old_cost) > 0.01
    
    def _status_data_changed(self, new_data: Dict[str, Any]) -> bool:
        """Check if system status has changed"""
        if not self.last_status_data:
            return True
        
        # Check if any service status changed
        for service_name, service_data in new_data.items():
            old_status = self.last_status_data.get(service_name, {}).get("status")
            new_status = service_data.get("status")
            
            if old_status != new_status:
                return True
        
        return False
    
    def _generate_alerts(self, services_health: Dict[str, Any]) -> list:
        """Generate alerts based on service health"""
        alerts = []
        
        for service_name, health_data in services_health.items():
            status = health_data.get("status")
            
            if status == "unhealthy":
                alerts.append({
                    "level": "warning",
                    "service": service_name,
                    "message": f"Service {service_name} is unhealthy",
                    "timestamp": datetime.utcnow().isoformat()
                })
            elif status == "unreachable":
                alerts.append({
                    "level": "error",
                    "service": service_name,
                    "message": f"Service {service_name} is unreachable",
                    "timestamp": datetime.utcnow().isoformat()
                })
            elif health_data.get("response_time", 0) > 5.0:
                alerts.append({
                    "level": "warning",
                    "service": service_name,
                    "message": f"Service {service_name} response time is high ({health_data['response_time']:.2f}s)",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        return alerts