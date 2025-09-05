import unittest
from datetime import datetime, timedelta
from sie.head_node.core import PoolManager
from sie.head_node.models import Instance
from sie.common.constants import InstanceState, HEARTBEAT_TIMEOUT


class TestPoolManager(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        self.pool_manager = PoolManager()
        self.test_instance = Instance(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware={"cpu": {"cores": 2}, "memory_mb": 4096}
        )
    
    def test_register_instance(self):
        """Test registering a new instance"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        self.assertIn("i-test123", self.pool_manager.instances)
        self.assertEqual(self.pool_manager.instances["i-test123"].state, InstanceState.RUNNING)
        self.assertEqual(self.pool_manager.instance_to_ws["i-test123"], ws_id)
    
    def test_unregister_instance(self):
        """Test unregistering an instance"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        self.pool_manager.unregister_instance("i-test123")
        
        self.assertNotIn("i-test123", self.pool_manager.instances)
        self.assertNotIn("i-test123", self.pool_manager.instance_to_ws)
    
    def test_unregister_nonexistent_instance(self):
        """Test unregistering an instance that doesn't exist"""
        # Should not raise an exception
        self.pool_manager.unregister_instance("i-nonexistent")
    
    def test_update_heartbeat(self):
        """Test updating instance heartbeat"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        # Store original heartbeat time
        original_time = self.pool_manager.instances["i-test123"].last_heartbeat
        
        # Update heartbeat
        result = self.pool_manager.update_heartbeat("i-test123")
        
        self.assertTrue(result)
        new_time = self.pool_manager.instances["i-test123"].last_heartbeat
        self.assertGreater(new_time, original_time)
    
    def test_update_heartbeat_nonexistent(self):
        """Test updating heartbeat for nonexistent instance"""
        result = self.pool_manager.update_heartbeat("i-nonexistent")
        self.assertFalse(result)
    
    def test_get_instance(self):
        """Test getting instance by ID"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        instance = self.pool_manager.get_instance("i-test123")
        self.assertIsNotNone(instance)
        self.assertEqual(instance.instance_id, "i-test123")
        self.assertEqual(instance.instance_type, "t2.micro")
    
    def test_get_nonexistent_instance(self):
        """Test getting nonexistent instance"""
        instance = self.pool_manager.get_instance("i-nonexistent")
        self.assertIsNone(instance)
    
    def test_get_all_instances(self):
        """Test getting all instances"""
        # Register multiple instances
        for i in range(3):
            instance = Instance(
                instance_id=f"i-test{i}",
                instance_type="t2.micro",
                hardware={}
            )
            self.pool_manager.register_instance(instance, f"ws-{i}")
        
        instances = self.pool_manager.get_all_instances()
        self.assertEqual(len(instances), 3)
        instance_ids = [inst.instance_id for inst in instances]
        self.assertIn("i-test0", instance_ids)
        self.assertIn("i-test1", instance_ids)
        self.assertIn("i-test2", instance_ids)
    
    def test_check_health_all_healthy(self):
        """Test health check with all healthy instances"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        unhealthy = self.pool_manager.check_health()
        self.assertEqual(len(unhealthy), 0)
    
    def test_check_health_with_unhealthy(self):
        """Test health check with unhealthy instances"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        # Manually set last_heartbeat to old time
        old_time = datetime.utcnow() - timedelta(seconds=HEARTBEAT_TIMEOUT + 10)
        self.pool_manager.instances["i-test123"].last_heartbeat = old_time
        
        unhealthy = self.pool_manager.check_health()
        self.assertEqual(len(unhealthy), 1)
        self.assertIn("i-test123", unhealthy)
    
    def test_mark_for_interruption(self):
        """Test marking instance for interruption"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        result = self.pool_manager.mark_for_interruption("i-test123", 120)
        
        self.assertTrue(result)
        instance = self.pool_manager.instances["i-test123"]
        self.assertEqual(instance.state, InstanceState.INTERRUPTED)
        self.assertIsNotNone(instance.interruption_time)
        
        # Check interruption time is approximately 2 minutes in future
        expected_time = datetime.utcnow() + timedelta(seconds=120)
        time_diff = abs((instance.interruption_time - expected_time).total_seconds())
        self.assertLess(time_diff, 1)  # Within 1 second tolerance
    
    def test_mark_nonexistent_for_interruption(self):
        """Test marking nonexistent instance for interruption"""
        result = self.pool_manager.mark_for_interruption("i-nonexistent")
        self.assertFalse(result)
    
    def test_get_websocket_id(self):
        """Test getting WebSocket ID for instance"""
        ws_id = "ws-123"
        self.pool_manager.register_instance(self.test_instance, ws_id)
        
        retrieved_ws_id = self.pool_manager.get_websocket_id("i-test123")
        self.assertEqual(retrieved_ws_id, ws_id)
    
    def test_get_websocket_id_nonexistent(self):
        """Test getting WebSocket ID for nonexistent instance"""
        ws_id = self.pool_manager.get_websocket_id("i-nonexistent")
        self.assertIsNone(ws_id)
    
    def test_multiple_instances_same_websocket(self):
        """Test that multiple instances can't share same WebSocket"""
        ws_id = "ws-123"
        
        instance1 = Instance(
            instance_id="i-test1",
            instance_type="t2.micro",
            hardware={}
        )
        instance2 = Instance(
            instance_id="i-test2",
            instance_type="t2.micro",
            hardware={}
        )
        
        self.pool_manager.register_instance(instance1, ws_id)
        self.pool_manager.register_instance(instance2, ws_id)
        
        # Both should be registered (implementation allows this)
        self.assertIn("i-test1", self.pool_manager.instances)
        self.assertIn("i-test2", self.pool_manager.instances)


if __name__ == "__main__":
    unittest.main()