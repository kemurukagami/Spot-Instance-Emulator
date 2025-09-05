from fastapi import WebSocket, WebSocketDisconnect
import json
import uuid
from typing import Dict
from datetime import datetime
import logging
from sie.common.messages import (
    RegisterMessage, HeartbeatMessage, InterruptMessage, 
    AcknowledgeMessage, StatusMessage
)
from sie.common.constants import MessageType, InstanceState
from sie.head_node.models import Instance
from sie.head_node.core import PoolManager

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self, pool_manager: PoolManager):
        self.active_connections: Dict[str, WebSocket] = {}
        self.pool_manager = pool_manager
        
    async def connect(self, websocket: WebSocket) -> str:
        """Accept new WebSocket connection"""
        await websocket.accept()
        connection_id = str(uuid.uuid4())
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket connected: {connection_id}")
        return connection_id
        
    def disconnect(self, connection_id: str):
        """Handle WebSocket disconnection"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            # Find and unregister associated instance
            for instance_id, ws_id in list(self.pool_manager.instance_to_ws.items()):
                if ws_id == connection_id:
                    self.pool_manager.unregister_instance(instance_id)
            logger.info(f"WebSocket disconnected: {connection_id}")
            
    async def send_message(self, connection_id: str, message: dict):
        """Send message to specific connection"""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            # Convert datetime objects to strings for JSON serialization
            import json
            json_str = json.dumps(message, default=str)
            await websocket.send_text(json_str)
            
    async def send_to_instance(self, instance_id: str, message: dict):
        """Send message to specific instance"""
        ws_id = self.pool_manager.get_websocket_id(instance_id)
        if ws_id:
            await self.send_message(ws_id, message)
            
    async def broadcast(self, message: dict):
        """Broadcast message to all connections"""
        for connection_id in list(self.active_connections.keys()):
            await self.send_message(connection_id, message)
            
    async def handle_message(self, connection_id: str, data: dict):
        """Process incoming WebSocket message"""
        try:
            msg_type = data.get("type")
            
            if msg_type == MessageType.REGISTER:
                msg = RegisterMessage(**data)
                instance = Instance(
                    instance_id=msg.instance_id,
                    instance_type=msg.instance_type,
                    hardware=msg.hardware
                )
                self.pool_manager.register_instance(instance, connection_id)
                
                # Send acknowledgment
                ack = AcknowledgeMessage(
                    instance_id=msg.instance_id,
                    original_message_type=MessageType.REGISTER
                )
                await self.send_message(connection_id, ack.dict())
                logger.info(f"Registered instance: {msg.instance_id}")
                
            elif msg_type == MessageType.HEARTBEAT:
                msg = HeartbeatMessage(**data)
                success = self.pool_manager.update_heartbeat(msg.instance_id)
                if success:
                    # Send acknowledgment
                    ack = AcknowledgeMessage(
                        instance_id=msg.instance_id,
                        original_message_type=MessageType.HEARTBEAT
                    )
                    await self.send_message(connection_id, ack.dict())
                    
            elif msg_type == MessageType.STATUS:
                msg = StatusMessage(**data)
                instance = self.pool_manager.get_instance(msg.instance_id)
                if instance:
                    instance.state = msg.state
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            
    async def trigger_interruption(self, instance_id: str, warning_time: int = 120):
        """Send interruption message to instance"""
        success = self.pool_manager.mark_for_interruption(instance_id, warning_time)
        if success:
            msg = InterruptMessage(
                instance_id=instance_id,
                warning_time=warning_time
            )
            await self.send_to_instance(instance_id, msg.dict())
            logger.info(f"Sent interruption to instance: {instance_id}")
            return True
        return False