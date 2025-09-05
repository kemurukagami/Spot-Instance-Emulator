import unittest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from sie.head_node.api.websocket import ConnectionManager
from sie.head_node.core import PoolManager
from sie.common.constants import MessageType, InstanceState


class TestConnectionManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.pool_manager = PoolManager()
        self.connection_manager = ConnectionManager(self.pool_manager)
        self.mock_websocket = AsyncMock()
    
    def test_init(self):
        """Test ConnectionManager initialization"""
        self.assertIsInstance(self.connection_manager.active_connections, dict)
        self.assertEqual(len(self.connection_manager.active_connections), 0)
        self.assertIs(self.connection_manager.pool_manager, self.pool_manager)
    
    async def async_test_connect(self):
        """Test WebSocket connection"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        self.assertIsNotNone(connection_id)
        self.assertIn(connection_id, self.connection_manager.active_connections)
        self.assertEqual(self.connection_manager.active_connections[connection_id], self.mock_websocket)
        self.mock_websocket.accept.assert_called_once()
    
    def test_connect(self):
        """Wrapper for async connect test"""
        asyncio.run(self.async_test_connect())
    
    async def async_test_disconnect(self):
        """Test WebSocket disconnection"""
        # First connect
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        # Register an instance with this connection
        from sie.head_node.models import Instance
        instance = Instance(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware={}
        )
        self.pool_manager.register_instance(instance, connection_id)
        
        # Now disconnect
        self.connection_manager.disconnect(connection_id)
        
        self.assertNotIn(connection_id, self.connection_manager.active_connections)
        self.assertNotIn("i-test123", self.pool_manager.instances)
    
    def test_disconnect(self):
        """Wrapper for async disconnect test"""
        asyncio.run(self.async_test_disconnect())
    
    def test_disconnect_nonexistent(self):
        """Test disconnecting non-existent connection"""
        # Should not raise an exception
        self.connection_manager.disconnect("nonexistent-id")
    
    async def async_test_send_message(self):
        """Test sending message to specific connection"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        message = {"type": "test", "data": "hello"}
        await self.connection_manager.send_message(connection_id, message)
        
        self.mock_websocket.send_json.assert_called_once_with(message)
    
    def test_send_message(self):
        """Wrapper for async send_message test"""
        asyncio.run(self.async_test_send_message())
    
    async def async_test_send_to_instance(self):
        """Test sending message to specific instance"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        # Register an instance
        from sie.head_node.models import Instance
        instance = Instance(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware={}
        )
        self.pool_manager.register_instance(instance, connection_id)
        
        message = {"type": "interrupt", "instance_id": "i-test123"}
        await self.connection_manager.send_to_instance("i-test123", message)
        
        self.mock_websocket.send_json.assert_called_once_with(message)
    
    def test_send_to_instance(self):
        """Wrapper for async send_to_instance test"""
        asyncio.run(self.async_test_send_to_instance())
    
    async def async_test_broadcast(self):
        """Test broadcasting message to all connections"""
        # Create multiple connections
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws3 = AsyncMock()
        
        conn1 = await self.connection_manager.connect(ws1)
        conn2 = await self.connection_manager.connect(ws2)
        conn3 = await self.connection_manager.connect(ws3)
        
        message = {"type": "broadcast", "data": "hello all"}
        await self.connection_manager.broadcast(message)
        
        ws1.send_json.assert_called_once_with(message)
        ws2.send_json.assert_called_once_with(message)
        ws3.send_json.assert_called_once_with(message)
    
    def test_broadcast(self):
        """Wrapper for async broadcast test"""
        asyncio.run(self.async_test_broadcast())
    
    async def async_test_handle_register_message(self):
        """Test handling REGISTER message"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        register_data = {
            "type": MessageType.REGISTER,
            "instance_id": "i-test123",
            "instance_type": "t2.micro",
            "hardware": {"cpu": {"cores": 2}}
        }
        
        await self.connection_manager.handle_message(connection_id, register_data)
        
        # Check instance was registered
        self.assertIn("i-test123", self.pool_manager.instances)
        instance = self.pool_manager.instances["i-test123"]
        self.assertEqual(instance.instance_type, "t2.micro")
        self.assertEqual(instance.state, InstanceState.RUNNING)
        
        # Check acknowledgment was sent
        self.mock_websocket.send_json.assert_called()
        sent_data = self.mock_websocket.send_json.call_args[0][0]
        self.assertEqual(sent_data["type"], MessageType.ACKNOWLEDGE)
        self.assertEqual(sent_data["instance_id"], "i-test123")
    
    def test_handle_register_message(self):
        """Wrapper for async handle_register_message test"""
        asyncio.run(self.async_test_handle_register_message())
    
    async def async_test_handle_heartbeat_message(self):
        """Test handling HEARTBEAT message"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        # First register an instance
        from sie.head_node.models import Instance
        instance = Instance(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware={}
        )
        self.pool_manager.register_instance(instance, connection_id)
        
        # Send heartbeat
        heartbeat_data = {
            "type": MessageType.HEARTBEAT,
            "instance_id": "i-test123",
            "state": InstanceState.RUNNING
        }
        
        await self.connection_manager.handle_message(connection_id, heartbeat_data)
        
        # Check acknowledgment was sent
        self.mock_websocket.send_json.assert_called()
        sent_data = self.mock_websocket.send_json.call_args[0][0]
        self.assertEqual(sent_data["type"], MessageType.ACKNOWLEDGE)
        self.assertEqual(sent_data["original_message_type"], MessageType.HEARTBEAT)
    
    def test_handle_heartbeat_message(self):
        """Wrapper for async handle_heartbeat_message test"""
        asyncio.run(self.async_test_handle_heartbeat_message())
    
    async def async_test_handle_status_message(self):
        """Test handling STATUS message"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        # First register an instance
        from sie.head_node.models import Instance
        instance = Instance(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware={}
        )
        self.pool_manager.register_instance(instance, connection_id)
        
        # Send status update
        status_data = {
            "type": MessageType.STATUS,
            "instance_id": "i-test123",
            "state": InstanceState.INTERRUPTED
        }
        
        await self.connection_manager.handle_message(connection_id, status_data)
        
        # Check instance state was updated
        updated_instance = self.pool_manager.get_instance("i-test123")
        self.assertEqual(updated_instance.state, InstanceState.INTERRUPTED)
    
    def test_handle_status_message(self):
        """Wrapper for async handle_status_message test"""
        asyncio.run(self.async_test_handle_status_message())
    
    async def async_test_trigger_interruption(self):
        """Test triggering interruption"""
        connection_id = await self.connection_manager.connect(self.mock_websocket)
        
        # Register an instance
        from sie.head_node.models import Instance
        instance = Instance(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware={}
        )
        self.pool_manager.register_instance(instance, connection_id)
        
        # Trigger interruption
        result = await self.connection_manager.trigger_interruption("i-test123", 60)
        
        self.assertTrue(result)
        
        # Check instance was marked for interruption
        instance = self.pool_manager.get_instance("i-test123")
        self.assertEqual(instance.state, InstanceState.INTERRUPTED)
        
        # Check interruption message was sent
        self.mock_websocket.send_json.assert_called()
        sent_data = self.mock_websocket.send_json.call_args[0][0]
        self.assertEqual(sent_data["type"], MessageType.INTERRUPT)
        self.assertEqual(sent_data["instance_id"], "i-test123")
        self.assertEqual(sent_data["warning_time"], 60)
    
    def test_trigger_interruption(self):
        """Wrapper for async trigger_interruption test"""
        asyncio.run(self.async_test_trigger_interruption())
    
    async def async_test_trigger_interruption_nonexistent(self):
        """Test triggering interruption for nonexistent instance"""
        result = await self.connection_manager.trigger_interruption("i-nonexistent", 120)
        self.assertFalse(result)
    
    def test_trigger_interruption_nonexistent(self):
        """Wrapper for async trigger_interruption_nonexistent test"""
        asyncio.run(self.async_test_trigger_interruption_nonexistent())


if __name__ == "__main__":
    unittest.main()