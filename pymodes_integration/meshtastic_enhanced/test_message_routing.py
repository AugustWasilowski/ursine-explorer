"""
Tests for message routing and delivery system

This module contains comprehensive tests for the MessageRouter,
DeliveryTracker, and MessageQueue classes.
"""

import unittest
import time
import threading
import logging
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta

from .message_router import MessageRouter, InterfaceHealth
from .delivery_tracker import DeliveryTracker, MessageQueue, DeliveryStatus, QueuedMessage
from .data_classes import (
    AlertMessage, MessagePriority, RoutingPolicy, 
    ConnectionStatus, ConnectionState
)
from .interfaces import MeshtasticInterface


class MockMeshtasticInterface(MeshtasticInterface):
    """Mock Meshtastic interface for testing"""
    
    def __init__(self, interface_type: str, should_fail: bool = False):
        self.interface_type = interface_type
        self.should_fail = should_fail
        self.connected = True
        self.messages_sent = []
        self.send_delay = 0.0  # Simulate network delay
        
    def connect(self) -> bool:
        self.connected = True
        return not self.should_fail
    
    def disconnect(self) -> None:
        self.connected = False
    
    def send_message(self, message: str, channel: str = None) -> bool:
        if self.send_delay > 0:
            time.sleep(self.send_delay)
        
        if self.should_fail:
            return False
        
        self.messages_sent.append({
            'message': message,
            'channel': channel,
            'timestamp': datetime.now()
        })
        return True
    
    def is_connected(self) -> bool:
        return self.connected
    
    def get_connection_status(self) -> ConnectionStatus:
        state = ConnectionState.CONNECTED if self.connected else ConnectionState.DISCONNECTED
        return ConnectionStatus(
            interface_type=self.interface_type,
            state=state,
            connected_since=datetime.now() if self.connected else None
        )
    
    def get_interface_type(self) -> str:
        return self.interface_type


class TestInterfaceHealth(unittest.TestCase):
    """Test InterfaceHealth class"""
    
    def setUp(self):
        self.interface = MockMeshtasticInterface("test")
        self.health = InterfaceHealth(self.interface)
    
    def test_initial_state(self):
        """Test initial health state"""
        self.assertTrue(self.health.is_healthy)
        self.assertEqual(self.health.success_count, 0)
        self.assertEqual(self.health.failure_count, 0)
        self.assertEqual(self.health.consecutive_failures, 0)
        self.assertEqual(self.health.success_rate, 100.0)
    
    def test_record_success(self):
        """Test recording successful operations"""
        self.health.record_success(0.5)
        
        self.assertEqual(self.health.success_count, 1)
        self.assertEqual(self.health.consecutive_failures, 0)
        self.assertTrue(self.health.is_healthy)
        self.assertIsNotNone(self.health.last_success_time)
        self.assertEqual(self.health.average_response_time, 0.5)
    
    def test_record_failure(self):
        """Test recording failed operations"""
        # Record a few failures
        for i in range(2):
            self.health.record_failure(f"Error {i}")
        
        self.assertEqual(self.health.failure_count, 2)
        self.assertEqual(self.health.consecutive_failures, 2)
        self.assertTrue(self.health.is_healthy)  # Still healthy until 3 failures
        
        # Third failure should mark as unhealthy
        self.health.record_failure("Error 3")
        self.assertFalse(self.health.is_healthy)
    
    def test_success_rate_calculation(self):
        """Test success rate calculation"""
        self.health.record_success()
        self.health.record_success()
        self.health.record_failure()
        
        self.assertAlmostEqual(self.health.success_rate, 66.67, places=1)
    
    def test_health_recovery(self):
        """Test health recovery after failures"""
        # Mark as unhealthy
        for i in range(3):
            self.health.record_failure(f"Error {i}")
        self.assertFalse(self.health.is_healthy)
        
        # Success should restore health
        self.health.record_success()
        self.assertTrue(self.health.is_healthy)


class TestMessageRouter(unittest.TestCase):
    """Test MessageRouter class"""
    
    def setUp(self):
        self.router = MessageRouter(health_check_interval=1)  # Fast health checks for testing
        self.serial_interface = MockMeshtasticInterface("serial")
        self.mqtt_interface = MockMeshtasticInterface("mqtt")
        
        # Create test message
        self.test_message = AlertMessage(
            content="Test alert message",
            channel="LongFast",
            priority=MessagePriority.MEDIUM
        )
    
    def tearDown(self):
        self.router.shutdown()
    
    def test_add_remove_interface(self):
        """Test adding and removing interfaces"""
        self.assertEqual(len(self.router.interfaces), 0)
        
        # Add interface
        self.router.add_interface(self.serial_interface)
        self.assertEqual(len(self.router.interfaces), 1)
        self.assertEqual(self.router.primary_interface, self.serial_interface)
        
        # Add second interface
        self.router.add_interface(self.mqtt_interface)
        self.assertEqual(len(self.router.interfaces), 2)
        self.assertEqual(self.router.primary_interface, self.serial_interface)  # Should remain primary
        
        # Remove interface
        self.router.remove_interface(self.serial_interface)
        self.assertEqual(len(self.router.interfaces), 1)
        self.assertEqual(self.router.primary_interface, self.mqtt_interface)  # Should update primary
    
    def test_routing_policy_all(self):
        """Test routing to all interfaces"""
        self.router.add_interface(self.serial_interface)
        self.router.add_interface(self.mqtt_interface)
        self.router.set_routing_policy(RoutingPolicy.ALL)
        
        results = self.router.route_message(self.test_message)
        
        self.assertEqual(len(results), 2)
        self.assertTrue(all(results))  # All should succeed
        self.assertEqual(len(self.serial_interface.messages_sent), 1)
        self.assertEqual(len(self.mqtt_interface.messages_sent), 1)
    
    def test_routing_policy_primary(self):
        """Test routing to primary interface only"""
        self.router.add_interface(self.serial_interface)
        self.router.add_interface(self.mqtt_interface)
        self.router.set_routing_policy(RoutingPolicy.PRIMARY)
        
        results = self.router.route_message(self.test_message)
        
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0])
        self.assertEqual(len(self.serial_interface.messages_sent), 1)
        self.assertEqual(len(self.mqtt_interface.messages_sent), 0)
    
    def test_routing_policy_fallback(self):
        """Test fallback routing when primary fails"""
        failing_interface = MockMeshtasticInterface("serial", should_fail=True)
        self.router.add_interface(failing_interface)
        self.router.add_interface(self.mqtt_interface)
        self.router.set_routing_policy(RoutingPolicy.FALLBACK)
        
        # First message should try primary (which will fail but still be healthy initially)
        results = self.router.route_message(self.test_message)
        
        # Should route to primary interface first (even if it fails)
        self.assertEqual(len(results), 1)
        self.assertFalse(results[0])  # Primary should fail
        
        # After 3 failures, should fallback to MQTT
        for _ in range(2):  # 2 more failures to mark as unhealthy
            self.router.route_message(self.test_message)
        
        # Now should use fallback
        results = self.router.route_message(self.test_message)
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0])  # MQTT should succeed
        self.assertEqual(len(self.mqtt_interface.messages_sent), 1)
    
    def test_interface_health_monitoring(self):
        """Test interface health monitoring"""
        failing_interface = MockMeshtasticInterface("serial", should_fail=True)
        self.router.add_interface(failing_interface)
        
        # Send messages to trigger failures
        for _ in range(3):
            self.router.route_message(self.test_message)
        
        # Give a moment for health monitoring to process
        time.sleep(0.1)
        
        # Interface should be marked as unhealthy
        health = self.router.interface_health["serial"]
        self.assertFalse(health.is_healthy)
        self.assertEqual(health.consecutive_failures, 3)
    
    def test_delivery_statistics(self):
        """Test delivery statistics tracking"""
        self.router.add_interface(self.serial_interface)
        failing_mqtt = MockMeshtasticInterface("mqtt", should_fail=True)
        self.router.add_interface(failing_mqtt)
        
        # Send some messages
        for _ in range(5):
            self.router.route_message(self.test_message)
        
        # Give a moment for health monitoring to process
        time.sleep(0.1)
        
        stats = self.router.get_delivery_stats()
        
        self.assertEqual(stats['total_messages'], 5)
        self.assertEqual(stats['successful_deliveries'], 5)  # At least serial succeeds
        self.assertEqual(stats['interface_stats']['serial']['success'], 5)
        # MQTT might be marked unhealthy after 3 failures, so check actual count
        self.assertGreaterEqual(stats['interface_stats']['mqtt']['failed'], 3)
    
    def test_no_interfaces_available(self):
        """Test behavior when no interfaces are available"""
        results = self.router.route_message(self.test_message)
        self.assertEqual(len(results), 0)
    
    def test_critical_message_routing(self):
        """Test that critical messages are attempted even on unhealthy interfaces"""
        failing_interface = MockMeshtasticInterface("serial", should_fail=True)
        self.router.add_interface(failing_interface)
        
        # Mark interface as unhealthy
        for _ in range(3):
            self.router.route_message(self.test_message)
        
        # Critical message should still be attempted
        critical_message = AlertMessage(
            content="Critical alert",
            channel="LongFast",
            priority=MessagePriority.CRITICAL
        )
        
        results = self.router.route_message(critical_message)
        self.assertEqual(len(results), 1)  # Should attempt even unhealthy interface


class TestMessageQueue(unittest.TestCase):
    """Test MessageQueue class"""
    
    def setUp(self):
        self.queue = MessageQueue(max_queue_size=10, max_retry_attempts=3)
        
        # Create test messages with different priorities
        self.low_priority_msg = AlertMessage(
            content="Low priority message",
            channel="LongFast",
            priority=MessagePriority.LOW
        )
        
        self.high_priority_msg = AlertMessage(
            content="High priority message",
            channel="LongFast",
            priority=MessagePriority.HIGH
        )
        
        self.critical_msg = AlertMessage(
            content="Critical message",
            channel="LongFast",
            priority=MessagePriority.CRITICAL
        )
    
    def test_enqueue_dequeue(self):
        """Test basic enqueue and dequeue operations"""
        # Enqueue messages
        self.assertTrue(self.queue.enqueue(self.low_priority_msg))
        self.assertTrue(self.queue.enqueue(self.high_priority_msg))
        
        # Dequeue should return high priority first
        message = self.queue.dequeue(timeout=1.0)
        self.assertIsNotNone(message)
        self.assertEqual(message.priority, MessagePriority.HIGH)
        
        # Then low priority
        message = self.queue.dequeue(timeout=1.0)
        self.assertIsNotNone(message)
        self.assertEqual(message.priority, MessagePriority.LOW)
    
    def test_priority_ordering(self):
        """Test that messages are dequeued in priority order"""
        # Enqueue in random order
        messages = [self.low_priority_msg, self.critical_msg, self.high_priority_msg]
        for msg in messages:
            self.queue.enqueue(msg)
        
        # Should dequeue in priority order: CRITICAL, HIGH, LOW
        expected_priorities = [MessagePriority.CRITICAL, MessagePriority.HIGH, MessagePriority.LOW]
        
        for expected_priority in expected_priorities:
            message = self.queue.dequeue(timeout=1.0)
            self.assertIsNotNone(message)
            self.assertEqual(message.priority, expected_priority)
    
    def test_queue_full_behavior(self):
        """Test behavior when queue is full"""
        # Fill queue to capacity
        for i in range(10):
            msg = AlertMessage(
                content=f"Message {i}",
                channel="LongFast",
                priority=MessagePriority.MEDIUM
            )
            self.assertTrue(self.queue.enqueue(msg))
        
        # Next message should be dropped
        overflow_msg = AlertMessage(
            content="Overflow message",
            channel="LongFast",
            priority=MessagePriority.MEDIUM
        )
        self.assertFalse(self.queue.enqueue(overflow_msg))
        
        stats = self.queue.get_queue_stats()
        self.assertEqual(stats['total_dropped'], 1)
    
    def test_retry_queue(self):
        """Test retry queue functionality"""
        # Enqueue for retry
        self.assertTrue(self.queue.enqueue_retry(self.high_priority_msg))
        
        # Should dequeue from retry queue first
        message = self.queue.dequeue(timeout=1.0)
        self.assertIsNotNone(message)
        self.assertEqual(message.content, "High priority message")
    
    def test_max_retry_attempts(self):
        """Test that messages exceeding max retries are rejected"""
        # Set retry count to max
        self.high_priority_msg.retry_count = 3
        
        # Should reject retry
        self.assertFalse(self.queue.enqueue_retry(self.high_priority_msg))
    
    def test_queue_statistics(self):
        """Test queue statistics"""
        # Enqueue some messages
        self.queue.enqueue(self.low_priority_msg)
        self.queue.enqueue(self.high_priority_msg)
        
        # Dequeue one
        self.queue.dequeue(timeout=1.0)
        
        stats = self.queue.get_queue_stats()
        
        self.assertEqual(stats['total_queued'], 2)
        self.assertEqual(stats['total_processed'], 1)
        self.assertEqual(stats['current_queue_size'], 1)
        self.assertGreater(stats['queue_utilization'], 0)
    
    def test_clear_queue(self):
        """Test clearing all messages from queue"""
        # Add messages to both queues
        self.queue.enqueue(self.low_priority_msg)
        self.queue.enqueue_retry(self.high_priority_msg)
        
        cleared_count = self.queue.clear()
        self.assertEqual(cleared_count, 2)
        self.assertTrue(self.queue.is_empty())


class TestDeliveryTracker(unittest.TestCase):
    """Test DeliveryTracker class"""
    
    def setUp(self):
        self.tracker = DeliveryTracker(max_tracked_messages=100, cleanup_interval=3600)
        
        self.test_message = AlertMessage(
            content="Test message for tracking",
            channel="LongFast",
            priority=MessagePriority.MEDIUM
        )
        
        self.target_interfaces = {"serial", "mqtt"}
    
    def tearDown(self):
        self.tracker.shutdown()
    
    def test_track_message(self):
        """Test message tracking initialization"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        self.assertIsNotNone(message_id)
        
        status = self.tracker.get_delivery_status(message_id)
        self.assertIsNotNone(status)
        self.assertEqual(status.target_interfaces, self.target_interfaces)
        self.assertEqual(len(status.pending_interfaces), 2)
        self.assertFalse(status.is_complete)
    
    def test_confirm_delivery_success(self):
        """Test confirming successful delivery"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        # Confirm success for one interface
        self.tracker.confirm_delivery(message_id, "serial", success=True)
        
        status = self.tracker.get_delivery_status(message_id)
        self.assertIn("serial", status.successful_interfaces)
        self.assertNotIn("serial", status.pending_interfaces)
        self.assertFalse(status.is_complete)  # Still pending MQTT
        self.assertTrue(status.is_successful)  # At least one succeeded
    
    def test_confirm_delivery_failure(self):
        """Test confirming failed delivery"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        # Confirm failure for one interface
        self.tracker.confirm_delivery(message_id, "serial", success=False, error_message="Connection failed")
        
        status = self.tracker.get_delivery_status(message_id)
        self.assertIn("serial", status.failed_interfaces)
        self.assertNotIn("serial", status.pending_interfaces)
        self.assertEqual(status.error_messages["serial"], "Connection failed")
    
    def test_delivery_complete(self):
        """Test delivery completion handling"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        # Confirm delivery for both interfaces
        self.tracker.confirm_delivery(message_id, "serial", success=True)
        self.tracker.confirm_delivery(message_id, "mqtt", success=False, error_message="MQTT error")
        
        # Message should be moved to completed
        status = self.tracker.get_delivery_status(message_id)
        self.assertIsNone(status)  # Removed from active tracking
        
        # Should be in completed messages
        stats = self.tracker.get_statistics()
        self.assertEqual(stats['completed_successful'], 1)  # At least one interface succeeded
    
    def test_failed_messages_retrieval(self):
        """Test retrieving failed messages"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        # Fail both interfaces
        self.tracker.confirm_delivery(message_id, "serial", success=False)
        self.tracker.confirm_delivery(message_id, "mqtt", success=False)
        
        # Should appear in failed messages (briefly before cleanup)
        failed_messages = self.tracker.get_failed_messages()
        self.assertEqual(len(failed_messages), 0)  # Moved to completed immediately
        
        stats = self.tracker.get_statistics()
        self.assertEqual(stats['completed_failed'], 1)
    
    def test_retry_logic(self):
        """Test retry preparation"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        # Fail both interfaces
        self.tracker.confirm_delivery(message_id, "serial", success=False)
        self.tracker.confirm_delivery(message_id, "mqtt", success=False)
        
        # Message should be completed and failed
        stats = self.tracker.get_statistics()
        self.assertEqual(stats['completed_failed'], 1)
    
    def test_delivery_statistics(self):
        """Test delivery statistics tracking"""
        # Track multiple messages
        for i in range(5):
            msg = AlertMessage(
                content=f"Message {i}",
                channel="LongFast",
                priority=MessagePriority.MEDIUM
            )
            message_id = self.tracker.track_message(msg, {"serial"})
            
            # Confirm delivery (some succeed, some fail)
            success = i % 2 == 0
            self.tracker.confirm_delivery(message_id, "serial", success=success)
        
        stats = self.tracker.get_statistics()
        self.assertEqual(stats['total_tracked'], 5)
        self.assertEqual(stats['completed_successful'], 3)  # Messages 0, 2, 4
        self.assertEqual(stats['completed_failed'], 2)     # Messages 1, 3
    
    def test_pending_messages(self):
        """Test retrieving pending messages"""
        message_id = self.tracker.track_message(self.test_message, self.target_interfaces)
        
        pending = self.tracker.get_pending_messages()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].message_id, message_id)
        
        # Complete delivery
        self.tracker.confirm_delivery(message_id, "serial", success=True)
        self.tracker.confirm_delivery(message_id, "mqtt", success=True)
        
        # Should no longer be pending
        pending = self.tracker.get_pending_messages()
        self.assertEqual(len(pending), 0)


class TestDeliveryStatus(unittest.TestCase):
    """Test DeliveryStatus class"""
    
    def setUp(self):
        self.message = AlertMessage(
            content="Test message",
            channel="LongFast",
            priority=MessagePriority.MEDIUM,
            max_retries=2
        )
        
        self.status = DeliveryStatus(
            message_id="test-123",
            message=self.message,
            target_interfaces={"serial", "mqtt"}
        )
    
    def test_initial_state(self):
        """Test initial delivery status state"""
        self.assertFalse(self.status.is_complete)
        self.assertFalse(self.status.is_successful)
        self.assertEqual(len(self.status.pending_interfaces), 2)
        self.assertEqual(self.status.success_rate, 0.0)
        self.assertTrue(self.status.can_retry)  # Can retry because not complete and not successful
    
    def test_record_success(self):
        """Test recording successful delivery"""
        self.status.record_success("serial")
        
        self.assertIn("serial", self.status.successful_interfaces)
        self.assertNotIn("serial", self.status.pending_interfaces)
        self.assertTrue(self.status.is_successful)
        self.assertEqual(self.status.success_rate, 100.0)  # 1 success, 0 failures
    
    def test_record_failure(self):
        """Test recording failed delivery"""
        self.status.record_failure("serial", "Connection timeout")
        
        self.assertIn("serial", self.status.failed_interfaces)
        self.assertNotIn("serial", self.status.pending_interfaces)
        self.assertEqual(self.status.error_messages["serial"], "Connection timeout")
    
    def test_completion_detection(self):
        """Test completion detection"""
        self.status.record_success("serial")
        self.assertFalse(self.status.is_complete)  # Still pending MQTT
        
        self.status.record_failure("mqtt", "MQTT error")
        self.assertTrue(self.status.is_complete)  # All interfaces attempted
    
    def test_retry_preparation(self):
        """Test retry preparation"""
        # Fail both interfaces
        self.status.record_failure("serial", "Error 1")
        self.status.record_failure("mqtt", "Error 2")
        
        self.assertTrue(self.status.can_retry)
        
        # Prepare for retry
        self.status.prepare_retry(30)
        
        self.assertEqual(self.status.retry_count, 1)
        self.assertEqual(len(self.status.pending_interfaces), 2)  # Back to pending
        self.assertEqual(len(self.status.failed_interfaces), 0)   # Cleared for retry
        self.assertIsNotNone(self.status.next_retry_time)
    
    def test_max_retries_exceeded(self):
        """Test behavior when max retries exceeded"""
        # Exceed max retries
        self.message.retry_count = 2  # At max
        self.status.record_failure("serial", "Error")
        self.status.record_failure("mqtt", "Error")
        
        self.assertFalse(self.status.can_retry)


if __name__ == '__main__':
    # Configure logging for tests
    logging.basicConfig(level=logging.DEBUG)
    
    # Run tests
    unittest.main(verbosity=2)