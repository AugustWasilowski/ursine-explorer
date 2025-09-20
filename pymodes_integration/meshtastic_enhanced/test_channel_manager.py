"""
Unit tests for ChannelManager

This module contains tests for the channel configuration and management
functionality of the enhanced Meshtastic integration.
"""

import unittest
from .channel_manager import ChannelManager
from .data_classes import ChannelConfig
from .exceptions import MeshtasticConfigError, MeshtasticValidationError


class TestChannelManager(unittest.TestCase):
    """Test cases for ChannelManager class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.test_channels = [
            ChannelConfig(name="LongFast", channel_number=0),
            ChannelConfig(name="SecureChannel", psk="AQ==", channel_number=1),
            ChannelConfig(name="EmergencyChannel", psk="AQIDBA==", channel_number=2)
        ]
        self.manager = ChannelManager(self.test_channels)
    
    def test_initialization(self):
        """Test ChannelManager initialization"""
        # Test with valid channels
        manager = ChannelManager(self.test_channels)
        self.assertEqual(len(manager.get_all_channels()), 3)
        
        # Test with empty channels
        empty_manager = ChannelManager([])
        self.assertEqual(len(empty_manager.get_all_channels()), 0)
    
    def test_add_channel(self):
        """Test adding channels"""
        new_channel = ChannelConfig(name="NewChannel", channel_number=3)
        self.manager.add_channel(new_channel)
        
        self.assertEqual(len(self.manager.get_all_channels()), 4)
        self.assertIsNotNone(self.manager.get_channel_by_name("NewChannel"))
        
        # Test adding duplicate channel name
        with self.assertRaises(MeshtasticValidationError):
            self.manager.add_channel(new_channel)
    
    def test_remove_channel(self):
        """Test removing channels"""
        # Remove existing channel
        result = self.manager.remove_channel("SecureChannel")
        self.assertTrue(result)
        self.assertIsNone(self.manager.get_channel_by_name("SecureChannel"))
        
        # Remove non-existent channel
        result = self.manager.remove_channel("NonExistent")
        self.assertFalse(result)
    
    def test_get_channel_by_name(self):
        """Test getting channels by name"""
        # Existing channel
        channel = self.manager.get_channel_by_name("LongFast")
        self.assertIsNotNone(channel)
        self.assertEqual(channel.name, "LongFast")
        
        # Non-existent channel
        channel = self.manager.get_channel_by_name("NonExistent")
        self.assertIsNone(channel)
    
    def test_get_all_channels(self):
        """Test getting all channels"""
        channels = self.manager.get_all_channels()
        self.assertEqual(len(channels), 3)
        
        channel_names = [ch.name for ch in channels]
        self.assertIn("LongFast", channel_names)
        self.assertIn("SecureChannel", channel_names)
        self.assertIn("EmergencyChannel", channel_names)
    
    def test_get_channel_names(self):
        """Test getting channel names"""
        names = self.manager.get_channel_names()
        self.assertEqual(len(names), 3)
        self.assertIn("LongFast", names)
        self.assertIn("SecureChannel", names)
        self.assertIn("EmergencyChannel", names)
    
    def test_default_channel(self):
        """Test default channel functionality"""
        # Get default channel (should be first one)
        default = self.manager.get_default_channel()
        self.assertIsNotNone(default)
        
        # Set specific default channel
        self.manager.set_default_channel("SecureChannel")
        default = self.manager.get_default_channel()
        self.assertEqual(default.name, "SecureChannel")
        
        # Try to set non-existent channel as default
        with self.assertRaises(MeshtasticValidationError):
            self.manager.set_default_channel("NonExistent")
    
    def test_encrypted_channels(self):
        """Test getting encrypted/unencrypted channels"""
        encrypted = self.manager.get_encrypted_channels()
        unencrypted = self.manager.get_unencrypted_channels()
        
        self.assertEqual(len(encrypted), 2)  # SecureChannel and EmergencyChannel
        self.assertEqual(len(unencrypted), 1)  # LongFast
        
        encrypted_names = [ch.name for ch in encrypted]
        self.assertIn("SecureChannel", encrypted_names)
        self.assertIn("EmergencyChannel", encrypted_names)
        
        unencrypted_names = [ch.name for ch in unencrypted]
        self.assertIn("LongFast", unencrypted_names)
    
    def test_validate_channel_config(self):
        """Test channel configuration validation"""
        # Valid channel
        valid_channel = ChannelConfig(name="ValidChannel", channel_number=4)
        is_valid, error = self.manager.validate_channel_config(valid_channel)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
        
        # Test that invalid channels raise exceptions during creation
        # Empty name
        with self.assertRaises(ValueError):
            ChannelConfig(name="", channel_number=0)
        
        # Bad channel number
        with self.assertRaises(ValueError):
            ChannelConfig(name="BadChannel", channel_number=10)
    
    def test_psk_validation(self):
        """Test PSK validation methods"""
        # Valid PSKs
        valid_psks = ["AQ==", "AQID", "AQIDBA=="]
        for psk in valid_psks:
            self.assertTrue(ChannelManager.validate_psk(psk))
        
        # Invalid PSKs
        invalid_psks = ["", "invalid", None]
        for psk in invalid_psks:
            self.assertFalse(ChannelManager.validate_psk(psk))
    
    def test_psk_encoding_decoding(self):
        """Test PSK encoding and decoding"""
        test_bytes = b"test_key_123"
        
        # Encode to PSK
        psk = ChannelManager.encode_psk(test_bytes)
        self.assertTrue(ChannelManager.validate_psk(psk))
        
        # Decode back to bytes
        decoded = ChannelManager.decode_psk(psk)
        self.assertEqual(decoded, test_bytes)
        
        # Test invalid inputs
        with self.assertRaises(MeshtasticValidationError):
            ChannelManager.encode_psk(b"")  # Empty bytes
        
        with self.assertRaises(MeshtasticValidationError):
            ChannelManager.decode_psk("invalid")  # Invalid PSK
    
    def test_generate_psk(self):
        """Test PSK generation"""
        # Default length
        psk = ChannelManager.generate_psk()
        self.assertTrue(ChannelManager.validate_psk(psk))
        
        # Custom lengths
        for length in [1, 16, 32]:
            psk = ChannelManager.generate_psk(length)
            self.assertTrue(ChannelManager.validate_psk(psk))
        
        # Invalid length
        with self.assertRaises(MeshtasticValidationError):
            ChannelManager.generate_psk(0)
    
    def test_statistics(self):
        """Test getting statistics"""
        stats = self.manager.get_statistics()
        
        self.assertEqual(stats['total_channels'], 3)
        self.assertEqual(stats['encrypted_channels'], 2)
        self.assertEqual(stats['unencrypted_channels'], 1)
        self.assertIn('channel_names', stats)
        self.assertEqual(len(stats['channel_names']), 3)
    
    def test_serialization(self):
        """Test to_dict and from_dict methods"""
        # Convert to dict
        data = self.manager.to_dict()
        self.assertIn('channels', data)
        self.assertIn('statistics', data)
        
        # Create new manager from dict
        new_manager = ChannelManager.from_dict(data)
        self.assertEqual(len(new_manager.get_all_channels()), 3)
        
        # Check that channels are preserved
        original_names = set(self.manager.get_channel_names())
        new_names = set(new_manager.get_channel_names())
        self.assertEqual(original_names, new_names)
    
    def test_empty_manager_default_channel(self):
        """Test default channel behavior with empty manager"""
        empty_manager = ChannelManager([])
        
        with self.assertRaises(MeshtasticConfigError):
            empty_manager.get_default_channel()


if __name__ == '__main__':
    unittest.main()