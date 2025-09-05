import asyncio
import websockets
import json
import logging
from typing import Optional, Callable
from datetime import datetime
from sie.common.messages import (
    RegisterMessage, HeartbeatMessage, InterruptMessage,
    AcknowledgeMessage, StatusMessage
)
from sie.common.constants import MessageType, InstanceState, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

class WebSocketClient:
    def __init__(self, instance_id: str, instance_type: str, hardware_profile: dict, 
                 head_node_url: str, interrupt_callback: Optional[Callable] = None,
                 termination_callback: Optional[Callable] = None):
        self.instance_id = instance_id
        self.instance_type = instance_type
        self.hardware_profile = hardware_profile
        self.head_node_url = head_node_url
        self.interrupt_callback = interrupt_callback
        self.termination_callback = termination_callback
        self.websocket = None
        self.state = InstanceState.PENDING
        self.running = False
        
    async def connect(self):
        """Connect to head node"""
        try:
            self.websocket = await websockets.connect(self.head_node_url)
            logger.info(f"Connected to head node: {self.head_node_url}")
            
            # Register instance
            await self._register()
            
            # Start heartbeat and message handler
            self.running = True
            await asyncio.gather(
                self._heartbeat_loop(),
                self._receive_messages()
            )
        except Exception as e:
            logger.error(f"Connection error: {e}")
            await self._reconnect()
            
    async def _register(self):
        """Register instance with head node"""
        msg = RegisterMessage(
            instance_id=self.instance_id,
            instance_type=self.instance_type,
            hardware=self.hardware_profile
        )
        await self.websocket.send(json.dumps(msg.dict(), default=str))
        logger.info(f"Registered instance: {self.instance_id}")
        self.state = InstanceState.RUNNING
        
    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                msg = HeartbeatMessage(
                    instance_id=self.instance_id,
                    state=self.state
                )
                await self.websocket.send(json.dumps(msg.dict(), default=str))
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break
                
    async def _receive_messages(self):
        """Handle incoming messages from head node"""
        while self.running:
            try:
                message = await self.websocket.recv()
                data = json.loads(message)
                await self._handle_message(data)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection closed by head node")
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                break
                
    async def _handle_message(self, data: dict):
        """Process message from head node"""
        msg_type = data.get("type")
        
        if msg_type == MessageType.INTERRUPT:
            msg = InterruptMessage(**data)
            logger.warning(f"Received interruption notice: {msg.warning_time}s warning")
            self.state = InstanceState.INTERRUPTED
            
            # Call interrupt callback if provided
            if self.interrupt_callback:
                await self.interrupt_callback(msg.warning_time, msg.reason)
                
            # Schedule termination
            asyncio.create_task(self._schedule_termination(msg.warning_time))
            
        elif msg_type == MessageType.ACKNOWLEDGE:
            msg = AcknowledgeMessage(**data)
            logger.debug(f"Received acknowledgment for {msg.original_message_type}")
            
    async def _schedule_termination(self, warning_time: int):
        """Schedule instance termination"""
        await asyncio.sleep(warning_time)
        logger.info(f"Terminating instance: {self.instance_id}")
        self.state = InstanceState.TERMINATED
        self.running = False
        if self.websocket:
            await self.websocket.close()
        
        # Notify main process to terminate
        if self.termination_callback:
            await self.termination_callback()
            
    async def _reconnect(self):
        """Reconnect to head node"""
        while not self.websocket or self.websocket.closed:
            logger.info("Attempting to reconnect...")
            await asyncio.sleep(5)
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                
    async def disconnect(self):
        """Disconnect from head node"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            logger.info(f"Disconnected instance: {self.instance_id}")