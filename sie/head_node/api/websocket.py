from fastapi import WebSocket, WebSocketDisconnect
import json
import uuid
import asyncio
from typing import Dict
from datetime import datetime
import logging
from sie.common.messages import (
    RegisterMessage, HeartbeatMessage, InterruptMessage, 
    AcknowledgeMessage, StatusMessage, AssignInstanceMessage, UnassignInstanceMessage,
    CreateUserMessage, DeleteUserMessage
)
from sie.common.constants import MessageType, InstanceState, ConnectionState
from sie.head_node.models.instance import WorkerConnection, Instance
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
        
        # Try to get client IP address
        client_ip = self._get_client_ip(websocket)
        self.pool_manager.websocket_connections[connection_id] = {
            'websocket': websocket,
            'client_ip': client_ip
        }
        
        logger.info(f"WebSocket connected: {connection_id} from IP: {client_ip}")
        return connection_id
    
    def _get_client_ip(self, websocket: WebSocket) -> str:
        """Extract client IP address from WebSocket connection"""
        try:
            # Try to get the real client IP
            if hasattr(websocket, 'client') and websocket.client:
                return websocket.client.host
            
            # Fallback to headers if behind proxy
            headers = getattr(websocket, 'headers', {})
            if 'x-forwarded-for' in headers:
                return headers['x-forwarded-for'].split(',')[0].strip()
            if 'x-real-ip' in headers:
                return headers['x-real-ip']
                
        except Exception as e:
            logger.warning(f"Could not extract client IP: {e}")
        
        return "unknown"
        
    def disconnect(self, connection_id: str):
        """Handle WebSocket disconnection"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            # Find and unregister associated worker
            for worker_id, ws_id in list(self.pool_manager.worker_to_ws.items()):
                if ws_id == connection_id:
                    self.pool_manager.unregister_worker(worker_id)
            logger.info(f"WebSocket disconnected: {connection_id}")
            
    async def send_message(self, connection_id: str, message: dict):
        """Send message to specific connection"""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            # Convert datetime objects to strings for JSON serialization
            import json
            json_str = json.dumps(message, default=str)
            await websocket.send_text(json_str)
            
    async def send_to_worker(self, worker_id: str, message: dict):
        """Send message to specific worker"""
        ws_id = self.pool_manager.get_websocket_id(worker_id)
        if ws_id:
            await self.send_message(ws_id, message)
            
    async def send_to_instance(self, instance_id: str, message: dict):
        """Send message to instance (find worker first)"""
        instance = self.pool_manager.get_instance(instance_id)
        if instance:
            await self.send_to_worker(instance.worker_id, message)
            
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
                worker = WorkerConnection(
                    worker_id=msg.worker_id,
                    hardware=msg.hardware,
                    connection_state=ConnectionState.UNASSIGNED
                )
                self.pool_manager.register_worker(worker, connection_id)
                
                # Send acknowledgment
                ack = AcknowledgeMessage(
                    instance_id="N/A",  # No instance assigned yet
                    original_message_type=MessageType.REGISTER
                )
                await self.send_message(connection_id, ack.dict())
                logger.info(f"Registered worker: {msg.worker_id}")
                
            elif msg_type == MessageType.HEARTBEAT:
                msg = HeartbeatMessage(**data)
                success = self.pool_manager.update_worker_heartbeat(
                    msg.worker_id, 
                    msg.connection_state,
                    msg.instance_id
                )
                if success:
                    # Send acknowledgment
                    ack = AcknowledgeMessage(
                        instance_id=msg.instance_id or "N/A",
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
            
    async def assign_instance(self, worker_id: str, instance_type: str) -> str:
        """Assign an instance ID to a worker"""
        instance_id = self.pool_manager.assign_instance(worker_id, instance_type)
        if instance_id:
            # Send assignment message to worker
            msg = AssignInstanceMessage(
                worker_id=worker_id,
                instance_id=instance_id,
                instance_type=instance_type
            )
            await self.send_to_worker(worker_id, msg.dict())
            logger.info(f"Assigned instance {instance_id} to worker {worker_id}")
            return instance_id
        return None
        
    async def unassign_instance(self, instance_id: str) -> bool:
        """Unassign an instance and return worker to unassigned state"""
        instance = self.pool_manager.get_instance(instance_id)
        if not instance:
            return False
            
        worker_id = instance.worker_id
        success = self.pool_manager.unassign_instance(instance_id)
        if success:
            # Send unassignment message to worker
            msg = UnassignInstanceMessage(
                instance_id=instance_id,
                worker_id=worker_id
            )
            await self.send_to_worker(worker_id, msg.dict())
            logger.info(f"Unassigned instance {instance_id} from worker {worker_id}")
            return True
        return False
        
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
            
            # Schedule automatic unassignment after warning time
            asyncio.create_task(self._schedule_unassignment(instance_id, warning_time))
            return True
        return False
        
    async def _schedule_unassignment(self, instance_id: str, warning_time: int):
        """Schedule automatic unassignment after warning time"""
        await asyncio.sleep(warning_time)
        await self.unassign_instance(instance_id)
        logger.info(f"Automatically unassigned instance {instance_id} after {warning_time}s")
    
    async def create_user_on_worker(self, worker_id: str, username: str, ssh_public_key: str, assignment_id: str) -> bool:
        """Send message to worker to create a system user"""
        msg = CreateUserMessage(
            username=username,
            ssh_public_key=ssh_public_key,
            assignment_id=assignment_id
        )
        await self.send_to_worker(worker_id, msg.dict())
        logger.info(f"Sent user creation request for {username} to worker {worker_id}")
        return True
    
    async def delete_user_on_worker(self, worker_id: str, username: str, assignment_id: str) -> bool:
        """Send message to worker to delete a system user"""
        msg = DeleteUserMessage(
            username=username,
            assignment_id=assignment_id
        )
        await self.send_to_worker(worker_id, msg.dict())
        logger.info(f"Sent user deletion request for {username} to worker {worker_id}")
        return True