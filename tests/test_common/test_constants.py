import unittest
from sie.common.constants import (
    InstanceState, MessageType,
    DEFAULT_WARNING_TIME, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT
)


class TestInstanceState(unittest.TestCase):
    
    def test_instance_states_exist(self):
        """Test that all instance states are defined"""
        states = [
            InstanceState.PENDING,
            InstanceState.RUNNING,
            InstanceState.STOPPING,
            InstanceState.TERMINATED,
            InstanceState.INTERRUPTED
        ]
        for state in states:
            self.assertIsNotNone(state)
    
    def test_instance_state_values(self):
        """Test instance state string values"""
        self.assertEqual(InstanceState.PENDING, "pending")
        self.assertEqual(InstanceState.RUNNING, "running")
        self.assertEqual(InstanceState.STOPPING, "stopping")
        self.assertEqual(InstanceState.TERMINATED, "terminated")
        self.assertEqual(InstanceState.INTERRUPTED, "interrupted")
    
    def test_instance_state_comparison(self):
        """Test that instance states can be compared"""
        state1 = InstanceState.RUNNING
        state2 = InstanceState.RUNNING
        state3 = InstanceState.TERMINATED
        
        self.assertEqual(state1, state2)
        self.assertNotEqual(state1, state3)


class TestMessageType(unittest.TestCase):
    
    def test_message_types_exist(self):
        """Test that all message types are defined"""
        types = [
            MessageType.REGISTER,
            MessageType.HEARTBEAT,
            MessageType.STATUS,
            MessageType.INTERRUPT,
            MessageType.ACKNOWLEDGE,
            MessageType.ERROR
        ]
        for msg_type in types:
            self.assertIsNotNone(msg_type)
    
    def test_message_type_values(self):
        """Test message type string values"""
        self.assertEqual(MessageType.REGISTER, "register")
        self.assertEqual(MessageType.HEARTBEAT, "heartbeat")
        self.assertEqual(MessageType.STATUS, "status")
        self.assertEqual(MessageType.INTERRUPT, "interrupt")
        self.assertEqual(MessageType.ACKNOWLEDGE, "acknowledge")
        self.assertEqual(MessageType.ERROR, "error")
    
    def test_message_type_usage_in_dict(self):
        """Test that message types can be used as dict keys"""
        msg_dict = {
            MessageType.REGISTER: "registration",
            MessageType.HEARTBEAT: "health_check"
        }
        self.assertEqual(msg_dict[MessageType.REGISTER], "registration")
        self.assertEqual(msg_dict[MessageType.HEARTBEAT], "health_check")


class TestTimingConstants(unittest.TestCase):
    
    def test_default_warning_time(self):
        """Test default warning time is 2 minutes"""
        self.assertEqual(DEFAULT_WARNING_TIME, 120)
    
    def test_heartbeat_interval(self):
        """Test heartbeat interval is 30 seconds"""
        self.assertEqual(HEARTBEAT_INTERVAL, 30)
    
    def test_heartbeat_timeout(self):
        """Test heartbeat timeout is 90 seconds"""
        self.assertEqual(HEARTBEAT_TIMEOUT, 90)
    
    def test_timeout_is_multiple_of_interval(self):
        """Test that timeout is a multiple of interval"""
        self.assertEqual(HEARTBEAT_TIMEOUT % HEARTBEAT_INTERVAL, 0)
        self.assertEqual(HEARTBEAT_TIMEOUT // HEARTBEAT_INTERVAL, 3)


if __name__ == "__main__":
    unittest.main()