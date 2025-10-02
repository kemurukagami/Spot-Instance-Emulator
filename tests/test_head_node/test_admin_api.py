import unittest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from sie.head_node.api.admin import router, managers, InterruptRequest
from sie.head_node.core import PoolManager
from sie.head_node.api.websocket import ConnectionManager
from sie.head_node.core.instance import Instance
from sie.common.constants import InstanceState
from datetime import datetime


class TestAdminAPI(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        # Create FastAPI test app
        from fastapi import FastAPI
        self.app = FastAPI()
        self.app.include_router(router)
        self.client = TestClient(self.app)
        
        # Set up managers
        managers.pool_manager = PoolManager()
        managers.connection_manager = Mock(spec=ConnectionManager)
        managers.connection_manager.trigger_interruption = AsyncMock()
        
        # Add test instances
        self.test_instances = [
            Instance(
                instance_id="i-test1",
                instance_type="t2.micro",
                hardware={"cpu": {"cores": 2}, "memory_mb": 4096},
                state=InstanceState.RUNNING
            ),
            Instance(
                instance_id="i-test2",
                instance_type="m5.large",
                hardware={"cpu": {"cores": 4}, "memory_mb": 8192},
                state=InstanceState.RUNNING
            )
        ]
        
        for instance in self.test_instances:
            managers.pool_manager.register_instance(instance, f"ws-{instance.instance_id}")
    
    def test_get_instances(self):
        """Test GET /admin/instances endpoint"""
        response = self.client.get("/admin/instances")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        
        # Check instance details
        instance_ids = [inst["instance_id"] for inst in data]
        self.assertIn("i-test1", instance_ids)
        self.assertIn("i-test2", instance_ids)
        
        # Check required fields are present
        for instance in data:
            self.assertIn("instance_id", instance)
            self.assertIn("instance_type", instance)
            self.assertIn("state", instance)
            self.assertIn("hardware", instance)
            self.assertIn("registered_at", instance)
            self.assertIn("last_heartbeat", instance)
    
    def test_get_instances_empty(self):
        """Test GET /admin/instances with no instances"""
        # Clear all instances
        managers.pool_manager.instances.clear()
        managers.pool_manager.instance_to_ws.clear()
        
        response = self.client.get("/admin/instances")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 0)
    
    def test_get_instance_by_id(self):
        """Test GET /admin/instances/{instance_id} endpoint"""
        response = self.client.get("/admin/instances/i-test1")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["instance_id"], "i-test1")
        self.assertEqual(data["instance_type"], "t2.micro")
        self.assertEqual(data["state"], InstanceState.RUNNING)
        self.assertIsNotNone(data["hardware"])
        self.assertIsNone(data["interruption_time"])
    
    def test_get_instance_nonexistent(self):
        """Test GET /admin/instances/{instance_id} for nonexistent instance"""
        response = self.client.get("/admin/instances/i-nonexistent")
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["detail"], "Instance not found")
    
    def test_get_instance_with_interruption_time(self):
        """Test GET /admin/instances/{instance_id} with interruption scheduled"""
        # Mark instance for interruption
        managers.pool_manager.mark_for_interruption("i-test1", 120)
        
        response = self.client.get("/admin/instances/i-test1")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data["interruption_time"])
    
    def test_trigger_interruption(self):
        """Test POST /admin/interrupt endpoint"""
        managers.connection_manager.trigger_interruption.return_value = True
        
        request_data = {
            "instance_id": "i-test1",
            "warning_time": 60
        }
        
        response = self.client.post("/admin/interrupt", json=request_data)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertIn("i-test1", data["message"])
        
        # Verify trigger_interruption was called
        managers.connection_manager.trigger_interruption.assert_called_once_with(
            "i-test1", 60
        )
    
    def test_trigger_interruption_default_warning_time(self):
        """Test POST /admin/interrupt with default warning time"""
        managers.connection_manager.trigger_interruption.return_value = True
        
        request_data = {
            "instance_id": "i-test1"
        }
        
        response = self.client.post("/admin/interrupt", json=request_data)
        
        self.assertEqual(response.status_code, 200)
        
        # Verify default warning time of 120 was used
        managers.connection_manager.trigger_interruption.assert_called_once_with(
            "i-test1", 120
        )
    
    def test_trigger_interruption_nonexistent(self):
        """Test POST /admin/interrupt for nonexistent instance"""
        managers.connection_manager.trigger_interruption.return_value = False
        
        request_data = {
            "instance_id": "i-nonexistent",
            "warning_time": 120
        }
        
        response = self.client.post("/admin/interrupt", json=request_data)
        
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertEqual(data["detail"], "Instance not found")
    
    def test_trigger_interruption_invalid_data(self):
        """Test POST /admin/interrupt with invalid data"""
        request_data = {
            # Missing instance_id
            "warning_time": 120
        }
        
        response = self.client.post("/admin/interrupt", json=request_data)
        
        self.assertEqual(response.status_code, 422)  # Validation error
    
    def test_health_check_all_healthy(self):
        """Test GET /admin/health endpoint with healthy instances"""
        response = self.client.get("/admin/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["total_instances"], 2)
        self.assertEqual(data["healthy_instances"], 2)
        self.assertEqual(len(data["unhealthy_instances"]), 0)
    
    def test_health_check_with_unhealthy(self):
        """Test GET /admin/health endpoint with unhealthy instances"""
        # Mock check_health to return unhealthy instances
        with patch.object(managers.pool_manager, 'check_health', return_value=["i-test1"]):
            response = self.client.get("/admin/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["total_instances"], 2)
        self.assertEqual(data["healthy_instances"], 1)
        self.assertEqual(len(data["unhealthy_instances"]), 1)
        self.assertIn("i-test1", data["unhealthy_instances"])
    
    def test_health_check_no_instances(self):
        """Test GET /admin/health with no instances"""
        managers.pool_manager.instances.clear()
        
        response = self.client.get("/admin/health")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["total_instances"], 0)
        self.assertEqual(data["healthy_instances"], 0)
        self.assertEqual(len(data["unhealthy_instances"]), 0)


if __name__ == "__main__":
    unittest.main()