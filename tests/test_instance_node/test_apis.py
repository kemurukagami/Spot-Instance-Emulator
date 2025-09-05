import unittest
from unittest.mock import Mock, AsyncMock, patch
from fastapi.testclient import TestClient
from datetime import datetime, timedelta
from sie.instance_node.api.status import router as status_router, status
from sie.instance_node.api.webhook import router as webhook_router, webhook_config, send_interruption_notice
from sie.common.constants import InstanceState


class TestStatusAPI(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        from fastapi import FastAPI
        self.app = FastAPI()
        self.app.include_router(status_router)
        self.client = TestClient(self.app)
        
        # Reset status
        status.instance_id = "i-test123"
        status.instance_type = "t2.micro"
        status.state = InstanceState.RUNNING
        status.hardware = {"cpu": {"cores": 2}, "memory_mb": 4096}
        status.interruption_time = None
    
    def test_get_status(self):
        """Test GET /instance/status endpoint"""
        response = self.client.get("/instance/status")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["instance_id"], "i-test123")
        self.assertEqual(data["instance_type"], "t2.micro")
        self.assertEqual(data["state"], InstanceState.RUNNING)
        self.assertIsNotNone(data["hardware"])
    
    def test_get_metadata(self):
        """Test GET /instance/metadata endpoint"""
        response = self.client.get("/instance/metadata")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["instance-id"], "i-test123")
        self.assertEqual(data["instance-type"], "t2.micro")
        self.assertIn("local-hostname", data)
        self.assertIn("local-ipv4", data)
        self.assertIn("public-hostname", data)
        self.assertIn("public-ipv4", data)
    
    def test_get_termination_time_not_scheduled(self):
        """Test GET /instance/termination-time when no termination scheduled"""
        response = self.client.get("/instance/termination-time")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIsNone(data["termination_time"])
        self.assertIsNone(data["time_remaining"])
    
    def test_get_termination_time_scheduled(self):
        """Test GET /instance/termination-time when termination is scheduled"""
        # Set interruption time
        status.interruption_time = datetime.utcnow() + timedelta(seconds=60)
        
        response = self.client.get("/instance/termination-time")
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertIsNotNone(data["termination_time"])
        self.assertIsNotNone(data["time_remaining"])
        # Time remaining should be approximately 60 seconds
        self.assertGreater(data["time_remaining"], 55)
        self.assertLess(data["time_remaining"], 65)


class TestWebhookAPI(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures"""
        from fastapi import FastAPI
        self.app = FastAPI()
        self.app.include_router(webhook_router)
        self.client = TestClient(self.app)
        
        # Reset webhook config
        webhook_config.url = None
        webhook_config.enabled = False
    
    def test_configure_webhook(self):
        """Test POST /webhook/configure endpoint"""
        config_data = {
            "url": "http://example.com/webhook",
            "enabled": True
        }
        
        response = self.client.post("/webhook/configure", json=config_data)
        
        self.assertEqual(response.status_code, 200)
        data = response.json()
        
        self.assertEqual(data["status"], "configured")
        self.assertEqual(data["url"], "http://example.com/webhook")
        
        # Check webhook_config was updated
        self.assertEqual(webhook_config.url, "http://example.com/webhook")
        self.assertTrue(webhook_config.enabled)
    
    def test_configure_webhook_disabled(self):
        """Test configuring webhook as disabled"""
        config_data = {
            "url": "http://example.com/webhook",
            "enabled": False
        }
        
        response = self.client.post("/webhook/configure", json=config_data)
        
        self.assertEqual(response.status_code, 200)
        
        self.assertEqual(webhook_config.url, "http://example.com/webhook")
        self.assertFalse(webhook_config.enabled)
    
    def test_configure_webhook_no_url(self):
        """Test configuring webhook without URL"""
        config_data = {
            "enabled": True
        }
        
        response = self.client.post("/webhook/configure", json=config_data)
        
        self.assertEqual(response.status_code, 200)
        
        self.assertIsNone(webhook_config.url)
        self.assertTrue(webhook_config.enabled)


class TestSendInterruptionNotice(unittest.TestCase):
    
    @patch('sie.instance_node.api.webhook.aiohttp.ClientSession')
    async def async_test_send_interruption_notice_success(self, mock_session_class):
        """Test sending interruption notice successfully"""
        # Configure webhook
        webhook_config.url = "http://example.com/webhook"
        webhook_config.enabled = True
        
        # Mock the HTTP session and response
        mock_response = AsyncMock()
        mock_response.status = 200
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Send interruption notice
        await send_interruption_notice("i-test123", 120, "spot-interruption")
        
        # Verify the request was made
        mock_session.post.assert_called_once()
        call_args = mock_session.post.call_args
        
        self.assertEqual(call_args[0][0], "http://example.com/webhook")
        
        # Check the payload
        json_data = call_args[1]["json"]
        self.assertEqual(json_data["instance_id"], "i-test123")
        self.assertEqual(json_data["reason"], "spot-interruption")
        self.assertEqual(json_data["warning_seconds"], 120)
        self.assertEqual(json_data["action"], "terminate")
        self.assertIn("time", json_data)
    
    def test_send_interruption_notice_success(self):
        """Wrapper for async send_interruption_notice_success test"""
        import asyncio
        asyncio.run(self.async_test_send_interruption_notice_success())
    
    async def async_test_send_interruption_notice_disabled(self):
        """Test sending interruption notice when webhook is disabled"""
        # Disable webhook
        webhook_config.url = "http://example.com/webhook"
        webhook_config.enabled = False
        
        with patch('sie.instance_node.api.webhook.aiohttp.ClientSession') as mock_session_class:
            await send_interruption_notice("i-test123", 120, "spot-interruption")
            
            # Should not make any HTTP request
            mock_session_class.assert_not_called()
    
    def test_send_interruption_notice_disabled(self):
        """Wrapper for async send_interruption_notice_disabled test"""
        import asyncio
        asyncio.run(self.async_test_send_interruption_notice_disabled())
    
    async def async_test_send_interruption_notice_no_url(self):
        """Test sending interruption notice when no URL configured"""
        # Enable webhook but no URL
        webhook_config.url = None
        webhook_config.enabled = True
        
        with patch('sie.instance_node.api.webhook.aiohttp.ClientSession') as mock_session_class:
            await send_interruption_notice("i-test123", 120, "spot-interruption")
            
            # Should not make any HTTP request
            mock_session_class.assert_not_called()
    
    def test_send_interruption_notice_no_url(self):
        """Wrapper for async send_interruption_notice_no_url test"""
        import asyncio
        asyncio.run(self.async_test_send_interruption_notice_no_url())
    
    @patch('sie.instance_node.api.webhook.aiohttp.ClientSession')
    async def async_test_send_interruption_notice_http_error(self, mock_session_class):
        """Test handling HTTP error when sending interruption notice"""
        # Configure webhook
        webhook_config.url = "http://example.com/webhook"
        webhook_config.enabled = True
        
        # Mock the HTTP session with error response
        mock_response = AsyncMock()
        mock_response.status = 500
        
        mock_session = AsyncMock()
        mock_session.post.return_value.__aenter__.return_value = mock_response
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Should not raise exception
        await send_interruption_notice("i-test123", 120, "spot-interruption")
        
        # Request should have been attempted
        mock_session.post.assert_called_once()
    
    def test_send_interruption_notice_http_error(self):
        """Wrapper for async send_interruption_notice_http_error test"""
        import asyncio
        asyncio.run(self.async_test_send_interruption_notice_http_error())
    
    @patch('sie.instance_node.api.webhook.aiohttp.ClientSession')
    async def async_test_send_interruption_notice_timeout(self, mock_session_class):
        """Test handling timeout when sending interruption notice"""
        # Configure webhook
        webhook_config.url = "http://example.com/webhook"
        webhook_config.enabled = True
        
        # Mock the HTTP session with timeout
        import asyncio
        mock_session = AsyncMock()
        mock_session.post.side_effect = asyncio.TimeoutError()
        mock_session_class.return_value.__aenter__.return_value = mock_session
        
        # Should not raise exception
        await send_interruption_notice("i-test123", 120, "spot-interruption")
        
        # Request should have been attempted
        mock_session.post.assert_called_once()
    
    def test_send_interruption_notice_timeout(self):
        """Wrapper for async send_interruption_notice_timeout test"""
        import asyncio
        asyncio.run(self.async_test_send_interruption_notice_timeout())


if __name__ == "__main__":
    unittest.main()