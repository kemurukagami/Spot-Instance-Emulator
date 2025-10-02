import asyncio
import websockets
import json
import logging
from typing import Optional, Callable
from datetime import datetime
from sie.common.messages import (
    RegisterMessage, HeartbeatMessage, InterruptMessage,
    AcknowledgeMessage, StatusMessage, AssignInstanceMessage, UnassignInstanceMessage
)
from sie.common.constants import MessageType, InstanceState, ConnectionState, HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)

class WebSocketClient:
    def __init__(self, worker_id: str, hardware_profile: dict, 
                 head_node_url: str, interrupt_callback: Optional[Callable] = None,
                 termination_callback: Optional[Callable] = None,
                 shutdown_callback: Optional[Callable] = None):
        self.worker_id = worker_id
        self.hardware_profile = hardware_profile
        self.head_node_url = head_node_url
        self.interrupt_callback = interrupt_callback
        self.termination_callback = termination_callback  # For instance unassignment
        self.shutdown_callback = shutdown_callback  # For full process shutdown
        self.websocket = None
        self.connection_state = ConnectionState.UNASSIGNED
        self.instance_id: Optional[str] = None  # Will be assigned by head node
        self.instance_type: Optional[str] = None
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
        """Register worker with head node"""
        msg = RegisterMessage(
            worker_id=self.worker_id,
            hardware=self.hardware_profile,
            instance_id=self.instance_id  # Will be None initially
        )
        await self.websocket.send(json.dumps(msg.dict(), default=str))
        logger.info(f"Registered worker: {self.worker_id} in {self.connection_state.value} state")
        
    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self.running:
            try:
                msg = HeartbeatMessage(
                    worker_id=self.worker_id,
                    connection_state=self.connection_state,
                    instance_id=self.instance_id  # May be None if unassigned
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
                logger.warning("Connection closed by head node - shutting down gracefully")
                self.running = False
                # Trigger full process shutdown when connection is lost
                if self.shutdown_callback:
                    await self.shutdown_callback()
                break
            except Exception as e:
                logger.error(f"Receive error: {e}")
                self.running = False
                # If there's a persistent error, shutdown gracefully
                if self.shutdown_callback:
                    await self.shutdown_callback()
                break
                
    async def _handle_message(self, data: dict):
        """Process message from head node"""
        msg_type = data.get("type")
        
        if msg_type == MessageType.ASSIGN_INSTANCE:
            msg = AssignInstanceMessage(**data)
            if msg.worker_id == self.worker_id:
                self.instance_id = msg.instance_id
                self.instance_type = msg.instance_type
                self.connection_state = ConnectionState.ASSIGNED
                logger.info(f" Worker {self.worker_id} assigned to instance {msg.instance_id} (type: {msg.instance_type})")
        
        elif msg_type == MessageType.INTERRUPT:
            msg = InterruptMessage(**data)
            if msg.instance_id == self.instance_id:
                # Calculate real-time warning based on simulation speed
                real_warning_time = msg.warning_time / msg.simulation_speed

                if msg.simulation_speed > 1.0:
                    logger.warning(f" Spot interruption: instance {msg.instance_id} terminating in {real_warning_time:.1f}s real-time ({msg.warning_time}s sim-time at {msg.simulation_speed}x speed)")
                else:
                    logger.warning(f" Spot interruption: instance {msg.instance_id} terminating in {msg.warning_time}s")

                self.connection_state = ConnectionState.INTERRUPTED

                # Call interrupt callback if provided (pass real warning time)
                if self.interrupt_callback:
                    await self.interrupt_callback(real_warning_time, msg.reason)

                # Note: Actual unassignment will come via UnassignInstanceMessage from head node
                # This is just a warning to allow the worker to clean up gracefully
        
        elif msg_type == MessageType.UNASSIGN_INSTANCE:
            msg = UnassignInstanceMessage(**data)
            if msg.instance_id == self.instance_id and msg.worker_id == self.worker_id:
                logger.info(f" Instance {self.instance_id} unassigned from worker {self.worker_id}")
                old_instance_id = self.instance_id
                self.instance_id = None
                self.instance_type = None
                self.connection_state = ConnectionState.UNASSIGNED

                # Notify application that instance is terminated (but worker continues)
                if self.termination_callback:
                    await self.termination_callback()
            
        elif msg_type == MessageType.ACKNOWLEDGE:
            msg = AcknowledgeMessage(**data)
            logger.debug(f"Received acknowledgment for {msg.original_message_type}")
            
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
            logger.info(f"Disconnected worker: {self.worker_id}")