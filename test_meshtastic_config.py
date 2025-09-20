#!/usr/bin/env python3
"""
Unit tests for enhanced Meshtastic configuration system.

This test suite validates the Meshtastic configuration classes, validation logic,
and migration utilities to ensure robust configuration handling.
"""

import unittest
import base64
import tempfile
import json
from pathlib import Path
from typing import Dict, Any

from pymodes_integration.meshtastic_config import (
    ChannelConfig,
    MQTTConfig,
    MeshtasticConfig,
    MeshtasticConfigValidator,
    MeshtasticConfigMigrator,
    create_meshtastic_config_from_dict,
    validate_meshtastic_config
)


class TestChannelConfig(unittest.TestCase):
    """Test ChannelConfig class and validation."""
    
    def test_valid_channel_creation(self):
        """Test creating valid channel configurations."""
        # Basic channel without encryption
        channel = ChannelConfig(name="LongFast", channel_number=0)
        self.assertEqual(channel.name, "LongFast")
        self.assertEqual(channel.channel_number, 0)
        self.assertIsNone(channel.psk)
        self.assertFalse(channel.is_encrypted())
        
        # Channel with encryption
        psk = base64.b64encode(b'0123456789abcdef').decode('ascii')  # 16 bytes
        encrypted_channel = ChannelConfig(name="Secure", psk=psk, channel_number=1)
        self.assertTrue(encrypted_channel.is_encrypted())
        self.assertEqual(len(encrypted_channel.get_psk_bytes()), 16)
    
    def test_invalid_channel_name(self):
        """Test validation of channel names."""
        with self.assertRaises(ValueError):
            ChannelConfig(name="", channel_number=0)
        
        with self.assertRaises(ValueError):
            ChannelConfig(name="   ", channel_number=0)
    
    def test_invalid_channel_number(self):
        """Test validation of channel numbers."""
        with self.assertRaises(ValueError):
            ChannelConfig(name="Test", channel_number=-1)
        
        with self.assertRaises(ValueError):
            ChannelConfig(name="Test", channel_number=8)
    
    def test_invalid_psk(self):
        """Test validation of PSK values."""
        # Invalid Base64
        with self.assertRaises(ValueError):
            ChannelConfig(name="Test", psk="invalid_base64!", channel_number=0)
        
        # Wrong length (8 bytes)
        short_psk = base64.b64encode(b'12345678').decode('ascii')
        with self.assertRaises(ValueError):
            ChannelConfig(name="Test", psk=short_psk, channel_number=0)
        
        # Wrong length (64 bytes)
        long_psk = base64.b64encode(b'0' * 64).decode('ascii')
        with self.assertRaises(ValueError):
            ChannelConfig(name="Test", psk=long_psk, channel_number=0)
    
    def test_valid_psk_lengths(self):
        """Test valid PSK lengths (16 and 32 bytes)."""
        # 16 bytes (AES-128)
        psk_16 = base64.b64encode(b'0123456789abcdef').decode('ascii')
        channel_16 = ChannelConfig(name="AES128", psk=psk_16, channel_number=0)
        self.assertEqual(len(channel_16.get_psk_bytes()), 16)
        
        # 32 bytes (AES-256)
        psk_32 = base64.b64encode(b'0123456789abcdef' * 2).decode('ascii')
        channel_32 = ChannelConfig(name="AES256", psk=psk_32, channel_number=1)
        self.assertEqual(len(channel_32.get_psk_bytes()), 32)


class TestMQTTConfig(unittest.TestCase):
    """Test MQTTConfig class and validation."""
    
    def test_valid_mqtt_config(self):
        """Test creating valid MQTT configurations."""
        mqtt = MQTTConfig(broker_url="mqtt.meshtastic.org")
        self.assertEqual(mqtt.broker_url, "mqtt.meshtastic.org")
        self.assertEqual(mqtt.port, 1883)
        self.assertFalse(mqtt.has_authentication())
        
        # With authentication
        mqtt_auth = MQTTConfig(
            broker_url="private.broker.com",
            username="user",
            password="pass"
        )
        self.assertTrue(mqtt_auth.has_authentication())
    
    def test_invalid_broker_url(self):
        """Test validation of broker URLs."""
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="")
        
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="   ")
    
    def test_invalid_port(self):
        """Test validation of MQTT ports."""
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", port=0)
        
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", port=65536)
    
    def test_invalid_qos(self):
        """Test validation of QoS levels."""
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", qos=3)
        
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", qos=-1)
    
    def test_connection_url(self):
        """Test connection URL generation."""
        mqtt = MQTTConfig(broker_url="test.com", port=1883)
        self.assertEqual(mqtt.get_connection_url(), "mqtt://test.com:1883")
        
        mqtt_tls = MQTTConfig(broker_url="secure.com", port=8883, use_tls=True)
        self.assertEqual(mqtt_tls.get_connection_url(), "mqtts://secure.com:8883")


class TestMeshtasticConfig(unittest.TestCase):
    """Test MeshtasticConfig class and validation."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.basic_channels = [
            ChannelConfig(name="LongFast", channel_number=0),
            ChannelConfig(name="Secure", psk=base64.b64encode(b'0123456789abcdef').decode(), channel_number=1)
        ]
    
    def test_valid_config_creation(self):
        """Test creating valid Meshtastic configurations."""
        config = MeshtasticConfig(
            channels=self.basic_channels,
            default_channel="LongFast",
            connection_mode="serial"  # Use serial mode to avoid MQTT requirement
        )
        self.assertEqual(len(config.channels), 2)
        self.assertEqual(config.default_channel, "LongFast")
        self.assertTrue(config.has_serial_connection())
        self.assertFalse(config.has_mqtt_connection())
    
    def test_dual_mode_config(self):
        """Test dual mode configuration."""
        mqtt = MQTTConfig(broker_url="mqtt.test.com")
        config = MeshtasticConfig(
            channels=self.basic_channels,
            default_channel="LongFast",
            mqtt=mqtt,
            connection_mode="dual"
        )
        self.assertTrue(config.has_serial_connection())
        self.assertTrue(config.has_mqtt_connection())
        self.assertTrue(config.is_dual_mode())
    
    def test_no_channels_error(self):
        """Test error when no channels are configured."""
        with self.assertRaises(ValueError):
            MeshtasticConfig(channels=[])
    
    def test_duplicate_channel_names(self):
        """Test error on duplicate channel names."""
        duplicate_channels = [
            ChannelConfig(name="Test", channel_number=0),
            ChannelConfig(name="Test", channel_number=1)
        ]
        with self.assertRaises(ValueError):
            MeshtasticConfig(channels=duplicate_channels)
    
    def test_duplicate_channel_numbers(self):
        """Test error on duplicate channel numbers."""
        duplicate_numbers = [
            ChannelConfig(name="Channel1", channel_number=0),
            ChannelConfig(name="Channel2", channel_number=0)
        ]
        with self.assertRaises(ValueError):
            MeshtasticConfig(channels=duplicate_numbers)
    
    def test_invalid_default_channel(self):
        """Test error when default channel doesn't exist."""
        with self.assertRaises(ValueError):
            MeshtasticConfig(
                channels=self.basic_channels,
                default_channel="NonExistent"
            )
    
    def test_mqtt_required_for_mqtt_mode(self):
        """Test error when MQTT mode requires MQTT config."""
        with self.assertRaises(ValueError):
            MeshtasticConfig(
                channels=self.basic_channels,
                connection_mode="mqtt"
            )
    
    def test_channel_lookup_methods(self):
        """Test channel lookup methods."""
        config = MeshtasticConfig(
            channels=self.basic_channels,
            default_channel="LongFast",
            connection_mode="serial"
        )
        
        # Test get_channel_by_name
        channel = config.get_channel_by_name("Secure")
        self.assertIsNotNone(channel)
        self.assertEqual(channel.name, "Secure")
        
        # Test non-existent channel
        self.assertIsNone(config.get_channel_by_name("NonExistent"))
        
        # Test get_default_channel_config
        default = config.get_default_channel_config()
        self.assertEqual(default.name, "LongFast")
        
        # Test get_encrypted_channels
        encrypted = config.get_encrypted_channels()
        self.assertEqual(len(encrypted), 1)
        self.assertEqual(encrypted[0].name, "Secure")


class TestMeshtasticConfigValidator(unittest.TestCase):
    """Test MeshtasticConfigValidator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.validator = MeshtasticConfigValidator()
        self.valid_config = MeshtasticConfig(
            channels=[ChannelConfig(name="Test", channel_number=0)],
            default_channel="Test",
            connection_mode="serial"
        )
    
    def test_valid_config_validation(self):
        """Test validation of valid configuration."""
        is_valid, errors = self.validator.validate_config(self.valid_config)
        if not is_valid:
            print(f"Validation errors: {errors}")
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
    
    def test_invalid_serial_port_validation(self):
        """Test validation of invalid serial ports."""
        config = MeshtasticConfig(
            channels=[ChannelConfig(name="Test", channel_number=0)],
            default_channel="Test",
            meshtastic_port="invalid_port",
            connection_mode="serial"
        )
        is_valid, errors = self.validator.validate_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("invalid" in error.lower() for error in errors))
    
    def test_mqtt_validation(self):
        """Test MQTT configuration validation."""
        invalid_mqtt = MQTTConfig(broker_url="invalid..hostname")
        config = MeshtasticConfig(
            channels=[ChannelConfig(name="Test", channel_number=0)],
            default_channel="Test",
            mqtt=invalid_mqtt,
            connection_mode="dual"
        )
        is_valid, errors = self.validator.validate_config(config)
        self.assertFalse(is_valid)
    
    def test_message_length_validation(self):
        """Test message length validation."""
        config = MeshtasticConfig(
            channels=[ChannelConfig(name="Test", channel_number=0)],
            default_channel="Test",
            max_message_length=300,  # Exceeds Meshtastic limit
            connection_mode="serial"
        )
        is_valid, errors = self.validator.validate_config(config)
        self.assertFalse(is_valid)
        self.assertTrue(any("237" in error for error in errors))
    
    def test_suggestion_generation(self):
        """Test error suggestion generation."""
        errors = ["Channel name cannot be empty", "Invalid PSK format"]
        suggestions = self.validator.suggest_fixes(self.valid_config, errors)
        self.assertTrue(len(suggestions) > 0)
        self.assertTrue(any("channel" in suggestion.lower() for suggestion in suggestions))


class TestMeshtasticConfigMigrator(unittest.TestCase):
    """Test MeshtasticConfigMigrator class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.migrator = MeshtasticConfigMigrator()
    
    def test_legacy_config_migration(self):
        """Test migration of legacy configuration."""
        legacy_config = {
            "meshtastic_port": "/dev/ttyUSB1",
            "meshtastic_baud": 9600
        }
        
        migrated = self.migrator.migrate_legacy_config(legacy_config)
        
        self.assertEqual(migrated["meshtastic_port"], "/dev/ttyUSB1")
        self.assertEqual(migrated["meshtastic_baud"], 9600)
        self.assertIn("channels", migrated)
        self.assertEqual(len(migrated["channels"]), 1)
        self.assertEqual(migrated["connection_mode"], "serial")
    
    def test_example_config_creation(self):
        """Test example configuration creation."""
        example = self.migrator.create_example_config()
        
        self.assertIn("channels", example)
        self.assertIn("mqtt", example)
        self.assertEqual(len(example["channels"]), 2)
        self.assertIsNotNone(example["mqtt"])


class TestConfigUtilityFunctions(unittest.TestCase):
    """Test utility functions for configuration handling."""
    
    def test_create_config_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "channels": [
                {"name": "Test", "channel_number": 0}
            ],
            "default_channel": "Test",
            "connection_mode": "serial"
        }
        
        config = create_meshtastic_config_from_dict(config_dict)
        self.assertEqual(len(config.channels), 1)
        self.assertEqual(config.default_channel, "Test")
        self.assertEqual(config.connection_mode, "serial")
    
    def test_validate_config_function(self):
        """Test standalone validation function."""
        config = MeshtasticConfig(
            channels=[ChannelConfig(name="Test", channel_number=0)],
            default_channel="Test",
            connection_mode="serial"
        )
        
        is_valid, errors, suggestions = validate_meshtastic_config(config)
        if not is_valid:
            print(f"Validation errors: {errors}")
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(suggestions), 0)


class TestConfigIntegration(unittest.TestCase):
    """Integration tests for configuration system."""
    
    def test_full_config_lifecycle(self):
        """Test complete configuration lifecycle."""
        # Create configuration
        mqtt = MQTTConfig(broker_url="mqtt.test.com")
        channels = [
            ChannelConfig(name="LongFast", channel_number=0),
            ChannelConfig(
                name="Secure", 
                psk=base64.b64encode(b'0123456789abcdef').decode(),
                channel_number=1
            )
        ]
        
        config = MeshtasticConfig(
            channels=channels,
            default_channel="Secure",
            mqtt=mqtt,
            connection_mode="dual"
        )
        
        # Validate configuration
        is_valid, errors, suggestions = validate_meshtastic_config(config)
        self.assertTrue(is_valid, f"Config validation failed: {errors}")
        
        # Test configuration methods
        self.assertTrue(config.is_dual_mode())
        self.assertEqual(len(config.get_encrypted_channels()), 1)
        
        default_channel = config.get_default_channel_config()
        self.assertEqual(default_channel.name, "Secure")
        self.assertTrue(default_channel.is_encrypted())
    
    def test_config_serialization_roundtrip(self):
        """Test configuration serialization and deserialization."""
        # Create original config
        original_config = MeshtasticConfig(
            channels=[
                ChannelConfig(name="Test1", channel_number=0),
                ChannelConfig(name="Test2", channel_number=1)
            ],
            default_channel="Test1",
            connection_mode="serial",
            max_message_length=150
        )
        
        # Convert to dict (simulate JSON serialization)
        config_dict = {
            "channels": [
                {
                    "name": ch.name,
                    "psk": ch.psk,
                    "channel_number": ch.channel_number,
                    "uplink_enabled": ch.uplink_enabled,
                    "downlink_enabled": ch.downlink_enabled
                }
                for ch in original_config.channels
            ],
            "default_channel": original_config.default_channel,
            "connection_mode": original_config.connection_mode,
            "max_message_length": original_config.max_message_length
        }
        
        # Recreate config from dict
        recreated_config = create_meshtastic_config_from_dict(config_dict)
        
        # Verify equivalence
        self.assertEqual(len(recreated_config.channels), len(original_config.channels))
        self.assertEqual(recreated_config.default_channel, original_config.default_channel)
        self.assertEqual(recreated_config.connection_mode, original_config.connection_mode)
        self.assertEqual(recreated_config.max_message_length, original_config.max_message_length)


if __name__ == '__main__':
    # Set up logging for tests
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # Run tests
    unittest.main(verbosity=2)