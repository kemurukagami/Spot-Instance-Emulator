import unittest
from datetime import datetime
from pydantic import ValidationError
from sie.common.messages import (
    BaseMessage, RegisterMessage, HeartbeatMessage,
    InterruptMessage, AcknowledgeMessage, StatusMessage
)
from sie.common.constants import MessageType, InstanceState


class TestBaseMessage(unittest.TestCase):
    
    def test_base_message_timestamp_auto_generated(self):
        """Test that timestamp is automatically generated"""
        msg = BaseMessage(type=MessageType.HEARTBEAT)
        self.assertIsInstance(msg.timestamp, datetime)
        self.assertIsNotNone(msg.timestamp)
    
    def test_base_message_custom_timestamp(self):
        """Test that custom timestamp can be provided"""
        custom_time = datetime(2024, 1, 1, 10, 0, 0)
        msg = BaseMessage(type=MessageType.HEARTBEAT, timestamp=custom_time)
        self.assertEqual(msg.timestamp, custom_time)


class TestRegisterMessage(unittest.TestCase):
    
    def setUp(self):
        self.valid_hardware = {
            "cpu": {"cores": 4, "threads": 8},
            "memory_mb": 8192
        }
    
    def test_register_message_creation(self):
        """Test creating a valid register message"""
        msg = RegisterMessage(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware=self.valid_hardware
        )
        self.assertEqual(msg.type, MessageType.REGISTER)
        self.assertEqual(msg.instance_id, "i-test123")
        self.assertEqual(msg.instance_type, "t2.micro")
        self.assertEqual(msg.hardware, self.valid_hardware)
    
    def test_register_message_missing_fields(self):
        """Test that missing required fields raise ValidationError"""
        with self.assertRaises(ValidationError):
            RegisterMessage(instance_id="i-test123")
    
    def test_register_message_to_dict(self):
        """Test converting register message to dictionary"""
        msg = RegisterMessage(
            instance_id="i-test123",
            instance_type="t2.micro",
            hardware=self.valid_hardware
        )
        data = msg.dict()
        self.assertEqual(data["type"], "register")
        self.assertEqual(data["instance_id"], "i-test123")
        self.assertIn("timestamp", data)


class TestHeartbeatMessage(unittest.TestCase):
    
    def test_heartbeat_message_creation(self):
        """Test creating a valid heartbeat message"""
        msg = HeartbeatMessage(
            instance_id="i-test123",
            state=InstanceState.RUNNING
        )
        self.assertEqual(msg.type, MessageType.HEARTBEAT)
        self.assertEqual(msg.instance_id, "i-test123")
        self.assertEqual(msg.state, InstanceState.RUNNING)
    
    def test_heartbeat_message_invalid_state(self):
        """Test that invalid state raises ValidationError"""
        with self.assertRaises(ValidationError):
            HeartbeatMessage(
                instance_id="i-test123",
                state="invalid_state"
            )
    
    def test_heartbeat_message_from_dict(self):
        """Test creating heartbeat message from dictionary"""
        data = {
            "type": "heartbeat",
            "instance_id": "i-test123",
            "state": "running"
        }
        msg = HeartbeatMessage(**data)
        self.assertEqual(msg.instance_id, "i-test123")
        self.assertEqual(msg.state, InstanceState.RUNNING)


class TestInterruptMessage(unittest.TestCase):
    
    def test_interrupt_message_creation(self):
        """Test creating a valid interrupt message"""
        msg = InterruptMessage(
            instance_id="i-test123",
            warning_time=120,
            reason="spot-interruption"
        )
        self.assertEqual(msg.type, MessageType.INTERRUPT)
        self.assertEqual(msg.instance_id, "i-test123")
        self.assertEqual(msg.warning_time, 120)
        self.assertEqual(msg.reason, "spot-interruption")
    
    def test_interrupt_message_default_values(self):
        """Test interrupt message with default values"""
        msg = InterruptMessage(instance_id="i-test123")
        self.assertEqual(msg.warning_time, 120)
        self.assertEqual(msg.reason, "spot-interruption")
    
    def test_interrupt_message_custom_warning_time(self):
        """Test interrupt message with custom warning time"""
        msg = InterruptMessage(
            instance_id="i-test123",
            warning_time=60
        )
        self.assertEqual(msg.warning_time, 60)


class TestAcknowledgeMessage(unittest.TestCase):
    
    def test_acknowledge_message_creation(self):
        """Test creating a valid acknowledge message"""
        msg = AcknowledgeMessage(
            instance_id="i-test123",
            original_message_type=MessageType.REGISTER
        )
        self.assertEqual(msg.type, MessageType.ACKNOWLEDGE)
        self.assertEqual(msg.instance_id, "i-test123")
        self.assertEqual(msg.original_message_type, MessageType.REGISTER)
    
    def test_acknowledge_message_different_types(self):
        """Test acknowledge message for different message types"""
        for msg_type in [MessageType.REGISTER, MessageType.HEARTBEAT, MessageType.STATUS]:
            msg = AcknowledgeMessage(
                instance_id="i-test123",
                original_message_type=msg_type
            )
            self.assertEqual(msg.original_message_type, msg_type)


class TestStatusMessage(unittest.TestCase):
    
    def test_status_message_creation(self):
        """Test creating a valid status message"""
        msg = StatusMessage(
            instance_id="i-test123",
            state=InstanceState.INTERRUPTED,
            details={"interruption_time": "2024-01-01T10:00:00"}
        )
        self.assertEqual(msg.type, MessageType.STATUS)
        self.assertEqual(msg.instance_id, "i-test123")
        self.assertEqual(msg.state, InstanceState.INTERRUPTED)
        self.assertIsNotNone(msg.details)
    
    def test_status_message_no_details(self):
        """Test status message without details"""
        msg = StatusMessage(
            instance_id="i-test123",
            state=InstanceState.RUNNING
        )
        self.assertIsNone(msg.details)
    
    def test_status_message_state_transitions(self):
        """Test status message with different states"""
        for state in [InstanceState.PENDING, InstanceState.RUNNING, 
                      InstanceState.INTERRUPTED, InstanceState.TERMINATED]:
            msg = StatusMessage(
                instance_id="i-test123",
                state=state
            )
            self.assertEqual(msg.state, state)


if __name__ == "__main__":
    unittest.main()