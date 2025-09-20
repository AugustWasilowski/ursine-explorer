"""
Unit tests for MeshtasticManager and ConnectionManager

This module contains tests to verify the enhanced MeshtasticManager
coordinator and ConnectionManager functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import threading
import time
from datetime import datetime

from .meshtastic_manager import MeshtasticManager
from .connection_manager import ConnectionManager, InterfacePriority, InterfaceMetrics
from .data_classes import (
    MeshtasticConfig, ChannelConfig, MQTTConfig, AlertMessage,
    ConnectionStatus, ConnectionState, MessagePriority
)
from .exceptions import MeshtasticConfigError, MeshtasticConnectionError


class MockInterface:
    """Mock Meshtastic interface for testing"""
    
    def __init__(self, interface_type: str, connected: bool = True):
        self.interface_type = interface_type
        self.connected = connected
        self.connection_status = ConnectionStatus(
            interface_type=interface_type,
            state=ConnectionState.CONNECTED if connected else ConnectionState.DISCONNECTED
        )
    
    def get_interface_type(self) -> str:
        return self.interface_type
    
    def is_connected(self) -> bool:
        return self.connected
    
    def connect(self) -> bool:
        self.connected = True
        self.connection_status.state = ConnectionState.CONNECTED
        return True
    
    def disconnect(self) -> None:
        self.connected = False
        self.connection_status.state = ConnectionState.DISCONNECTED
    
    def send_message(self, message: str, channel: str = None) -> bool:
        return self.connected
    
    def get_connection_status(self) -> ConnectionStatus:
        return self.connection_status


class TestConnectionManager(unittest.TestCase):
    """Test cases for ConnectionManager"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.connection_manager = ConnectionManager(
            failover_enabled=True,
            health_check_interval=1
        )
    
    def tearDown(self):
        """Clean up after tests"""
        self.connection_manager.shutdown()
    
    def test_add_interface(self):
        """Test adding interfaces to connection manager"""
        # Create mock interfaces
        serial_interface = MockInterface("serial")
        mqtt_interface = MockInterface("mqtt")
        
        # Add interfaces
        self.connection_manager.add_interface(
            serial_interface, 
            priority=InterfacePriority.HIGH,
            is_primary=True
        )
        self.connection_manager.add_interface(
            mqtt_interface,
            priority=InterfacePriority.MEDIUM
        )
        
        # Verify interfaces were added
        active_interfaces = self.connection_manager.get_active_interfaces()
        self.assertEqual(len(active_interfaces), 2)
        
        # Verify primary interface
        primary = self.connection_manager.get_primary_interface()
        self.assertEqual(primary.get_interface_type(), "serial")
    
    def test_interface_metrics(self):
        """Test interface metrics tracking"""
        interface = MockInterface("test")
        metrics = InterfaceMetrics(interface)
        
        # Test connection metrics
        metrics.record_connection_attempt()
        metrics.record_successful_connection()
        self.assertEqual(metrics.connection_attempts, 1)
        self.assertEqual(metrics.successful_connections, 1)
        self.assertEqual(metrics.availability, 1.0)
        
        # Test message metrics
        metrics.record_message_success(0.5)
        metrics.record_message_failure("Test error")
        self.assertEqual(metrics.messages_sent, 1)
        self.assertEqual(metrics.messages_failed, 1)
        self.assertEqual(metrics.success_rate, 0.5)
        
        # Test health score calculation
        self.assertGreater(metrics.health_score, 0)
        self.assertLessEqual(metrics.health_score, 100)
    
    def test_failover(self):
        """Test automatic failover functionality"""
        # Create interfaces with different health
        healthy_interface = MockInterface("healthy", connected=True)
        failed_interface = MockInterface("failed", connected=False)
        
        # Add interfaces
        self.connection_manager.add_interface(
            failed_interface,
            priority=InterfacePriority.HIGH,
            is_primary=True
        )
        self.connection_manager.add_interface(
            healthy_interface,
            priority=InterfacePriority.MEDIUM
        )
        
        # Trigger failover
        result = self.connection_manager.handle_failover()
        self.assertTrue(result)
        
        # Verify new primary
        primary = self.connection_manager.get_primary_interface()
        self.assertEqual(primary.get_interface_type(), "healthy")
    
    def test_health_status(self):
        """Test health status reporting"""
        interface = MockInterface("test")
        self.connection_manager.add_interface(interface)
        
        status = self.connection_manager.get_health_status()
        
        # Verify status structure
        self.assertIn('timestamp', status)
        self.assertIn('total_interfaces', status)
        self.assertIn('active_interfaces', status)
        self.assertIn('interfaces', status)
        
        self.assertEqual(status['total_interfaces'], 1)
        self.assertEqual(status['active_interfaces'], 1)


class TestMeshtasticManager(unittest.TestCase):
    """Test cases for MeshtasticManager"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = MeshtasticConfig(
            connection_mode="dual",
            channels=[ChannelConfig(name="TestChannel")],
            mqtt=MQTTConfig(broker_url="test.broker.com"),
            health_check_interval=1
        )
    
    def test_configuration_validation(self):
        """Test configuration validation"""
        # Test valid configuration
        manager = MeshtasticManager(self.config)
        self.assertIsNotNone(manager)
        
        # Test invalid connection mode - this should raise ValueError from MeshtasticConfig
        with self.assertRaises(ValueError):
            invalid_config = MeshtasticConfig(connection_mode="invalid")
    
    @patch('pymodes_integration.meshtastic_enhanced.meshtastic_manager.EnhancedSerialInterface')
    @patch('pymodes_integration.meshtastic_enhanced.meshtastic_manager.MeshtasticMQTTInterface')
    def test_initialization(self, mock_mqtt, mock_serial):
        """Test manager initialization"""
        # Mock interfaces
        mock_serial_instance = Mock()
        mock_serial_instance.connect.return_value = True
        mock_serial_instance.get_interface_type.return_value = "serial"
        mock_serial_instance.is_connected.return_value = True
        mock_serial.return_value = mock_serial_instance
        
        mock_mqtt_instance = Mock()
        mock_mqtt_instance.connect.return_value = True
        mock_mqtt_instance.get_interface_type.return_value = "mqtt"
        mock_mqtt_instance.is_connected.return_value = True
        mock_mqtt.return_value = mock_mqtt_instance
        
        # Initialize manager
        manager = MeshtasticManager(self.config)
        result = manager.initialize()
        
        self.assertTrue(result)
        self.assertTrue(manager._initialized)
        self.assertIsNotNone(manager.connection_manager)
        
        # Clean up
        manager.shutdown()
    
    def test_alert_message_formatting(self):
        """Test alert message formatting"""
        manager = MeshtasticManager(self.config)
        
        # Create mock aircraft
        aircraft = Mock()
        aircraft.icao = "ABC123"
        aircraft.callsign = "TEST123"
        aircraft.lat = 40.7128
        aircraft.lon = -74.0060
        aircraft.altitude = 35000
        
        # Test standard format
        manager.config.message_format = "standard"
        message = manager._create_alert_message(aircraft, "watchlist")
        self.assertIn("ABC123", message.content)
        self.assertIn("TEST123", message.content)
        
        # Test compact format
        manager.config.message_format = "compact"
        message = manager._create_alert_message(aircraft, "emergency")
        self.assertIn("E:ABC123", message.content)
        
        # Test JSON format - need to set actual values instead of Mock
        manager.config.message_format = "json"
        aircraft.icao = "ABC123"  # Ensure it's a string, not Mock
        aircraft.callsign = "TEST123"
        aircraft.lat = 40.7128
        aircraft.lon = -74.0060
        aircraft.altitude = 35000
        aircraft.speed = 250
        aircraft.heading = 90
        message = manager._create_alert_message(aircraft, "proximity")
        self.assertIn('"icao":"ABC123"', message.content)
    
    def test_connection_status(self):
        """Test connection status reporting"""
        manager = MeshtasticManager(self.config)
        
        # Test uninitialized status
        status = manager.get_connection_status()
        self.assertFalse(status['initialized'])
        
        # Test device info when not initialized
        device_info = manager.get_device_info()
        self.assertIsNone(device_info)
        
        # Test connectivity test when not initialized
        connectivity = manager.test_connectivity()
        self.assertIn('error', connectivity)


if __name__ == '__main__':
    unittest.main()