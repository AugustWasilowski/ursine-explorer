"""
Basic tests for enhanced Meshtastic integration foundation

This module contains basic tests to verify that the foundation
components are working correctly.
"""

import unittest
from datetime import datetime
from typing import Dict, Any

from .data_classes import (
    ChannelConfig, MQTTConfig, MeshtasticConfig, 
    AlertMessage, ConnectionStatus, ConnectionState, MessagePriority
)
from .exceptions import ValidationError, ConfigurationError
from .utils import (
    validate_psk, generate_psk, validate_channel_name,
    format_message_content, calculate_message_hash
)


class TestDataClasses(unittest.TestCase):
    """Test data class functionality"""
    
    def test_channel_config_creation(self):
        """Test ChannelConfig creation and validation"""
        # Valid channel
        channel = ChannelConfig(name="TestChannel", psk="AQ==", channel_number=1)
        self.assertEqual(channel.name, "TestChannel")
        self.assertEqual(channel.psk, "AQ==")
        self.assertEqual(channel.channel_number, 1)
        self.assertTrue(channel.is_encrypted)
        
        # Unencrypted channel
        unencrypted = ChannelConfig(name="Public")
        self.assertFalse(unencrypted.is_encrypted)
        
        # Invalid channel number
        with self.assertRaises(ValueError):
            ChannelConfig(name="Invalid", channel_number=10)
        
        # Empty name
        with self.assertRaises(ValueError):
            ChannelConfig(name="")
    
    def test_mqtt_config_creation(self):
        """Test MQTTConfig creation and validation"""
        # Valid MQTT config
        mqtt = MQTTConfig(broker_url="mqtt.example.com", port=1883)
        self.assertEqual(mqtt.broker_url, "mqtt.example.com")
        self.assertEqual(mqtt.port, 1883)
        
        # Invalid port
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", port=70000)
        
        # Empty broker URL
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="")
    
    def test_meshtastic_config_creation(self):
        """Test MeshtasticConfig creation and validation"""
        # Basic config
        config = MeshtasticConfig()
        self.assertEqual(config.connection_mode, "dual")
        self.assertTrue(config.failover_enabled)
        
        # With channels
        channels = [
            ChannelConfig(name="LongFast"),
            ChannelConfig(name="Secure", psk="AQ==")
        ]
        config_with_channels = MeshtasticConfig(channels=channels)
        self.assertEqual(len(config_with_channels.channels), 2)
        
        # Invalid connection mode
        with self.assertRaises(ValueError):
            MeshtasticConfig(connection_mode="invalid")
    
    def test_alert_message_creation(self):
        """Test AlertMessage creation and validation"""
        # Valid message
        message = AlertMessage(
            content="Test alert",
            channel="TestChannel",
            priority=MessagePriority.HIGH
        )
        self.assertEqual(message.content, "Test alert")
        self.assertEqual(message.priority, MessagePriority.HIGH)
        self.assertTrue(message.can_retry)
        
        # Empty content
        with self.assertRaises(ValueError):
            AlertMessage(content="", channel="test")
        
        # Empty channel
        with self.assertRaises(ValueError):
            AlertMessage(content="test", channel="")
    
    def test_connection_status_creation(self):
        """Test ConnectionStatus creation"""
        status = ConnectionStatus(
            interface_type="serial",
            state=ConnectionState.CONNECTED,
            connected_since=datetime.now()
        )
        self.assertEqual(status.interface_type, "serial")
        self.assertTrue(status.is_connected)
        self.assertIsNotNone(status.uptime_seconds)


class TestUtils(unittest.TestCase):
    """Test utility functions"""
    
    def test_psk_validation(self):
        """Test PSK validation"""
        # Valid PSKs (16 and 32 bytes)
        self.assertTrue(validate_psk("AAAAAAAAAAAAAAAAAAAAAA=="))  # 16 bytes
        self.assertTrue(validate_psk("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="))  # 32 bytes
        
        # Invalid PSKs
        self.assertFalse(validate_psk(""))
        self.assertFalse(validate_psk("invalid"))
        self.assertFalse(validate_psk("AQ=="))  # Only 1 byte, too short
    
    def test_psk_generation(self):
        """Test PSK generation"""
        # Generate 16-byte key
        psk16 = generate_psk(16)
        self.assertTrue(validate_psk(psk16))
        
        # Generate 32-byte key
        psk32 = generate_psk(32)
        self.assertTrue(validate_psk(psk32))
        
        # Invalid key size
        with self.assertRaises(ValidationError):
            generate_psk(8)
    
    def test_channel_name_validation(self):
        """Test channel name validation"""
        # Valid names
        self.assertTrue(validate_channel_name("LongFast"))
        self.assertTrue(validate_channel_name("test_123"))
        self.assertTrue(validate_channel_name("ch-1"))
        
        # Invalid names
        self.assertFalse(validate_channel_name(""))
        self.assertFalse(validate_channel_name("invalid channel"))  # Space
        self.assertFalse(validate_channel_name("a" * 25))  # Too long
    
    def test_message_formatting(self):
        """Test message content formatting"""
        # Basic formatting
        formatted = format_message_content("Test message")
        self.assertIn("Test message", formatted)
        self.assertIn("[", formatted)  # Timestamp
        
        # With prefix
        formatted_with_prefix = format_message_content(
            "Test message", 
            prefix="ADSB"
        )
        self.assertIn("ADSB:", formatted_with_prefix)
        
        # Truncation
        long_message = "A" * 300
        truncated = format_message_content(long_message, max_length=50)
        self.assertEqual(len(truncated), 50)
        self.assertTrue(truncated.endswith("..."))
    
    def test_message_hash(self):
        """Test message hash calculation"""
        hash1 = calculate_message_hash("Test message")
        hash2 = calculate_message_hash("Test message")
        hash3 = calculate_message_hash("Different message")
        
        # Same content should produce same hash
        self.assertEqual(hash1, hash2)
        
        # Different content should produce different hash
        self.assertNotEqual(hash1, hash3)
        
        # Hash should be 8 characters
        self.assertEqual(len(hash1), 8)


class TestSerialization(unittest.TestCase):
    """Test serialization/deserialization"""
    
    def test_channel_config_serialization(self):
        """Test ChannelConfig to/from dict"""
        original = ChannelConfig(name="Test", psk="AQ==", channel_number=1)
        
        # Serialize
        data = original.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data['name'], "Test")
        
        # Deserialize
        restored = ChannelConfig.from_dict(data)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.psk, original.psk)
        self.assertEqual(restored.channel_number, original.channel_number)
    
    def test_alert_message_serialization(self):
        """Test AlertMessage to/from dict"""
        original = AlertMessage(
            content="Test alert",
            channel="TestChannel",
            priority=MessagePriority.HIGH,
            aircraft_icao="ABC123"
        )
        
        # Serialize
        data = original.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data['content'], "Test alert")
        
        # Deserialize
        restored = AlertMessage.from_dict(data)
        self.assertEqual(restored.content, original.content)
        self.assertEqual(restored.priority, original.priority)
        self.assertEqual(restored.aircraft_icao, original.aircraft_icao)
    
    def test_meshtastic_config_serialization(self):
        """Test MeshtasticConfig to/from dict"""
        channels = [ChannelConfig(name="Test", psk="AQ==")]
        mqtt = MQTTConfig(broker_url="test.com")
        
        original = MeshtasticConfig(
            channels=channels,
            mqtt=mqtt,
            connection_mode="dual"
        )
        
        # Serialize
        data = original.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data['connection_mode'], "dual")
        
        # Deserialize
        restored = MeshtasticConfig.from_dict(data)
        self.assertEqual(restored.connection_mode, original.connection_mode)
        self.assertEqual(len(restored.channels), len(original.channels))
        self.assertIsNotNone(restored.mqtt)


def run_foundation_tests():
    """Run all foundation tests"""
    print("Running enhanced Meshtastic foundation tests...")
    
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestDataClasses))
    suite.addTests(loader.loadTestsFromTestCase(TestUtils))
    suite.addTests(loader.loadTestsFromTestCase(TestSerialization))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Return success status
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_foundation_tests()
    exit(0 if success else 1)