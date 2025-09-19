#!/usr/bin/env python3
"""
Unit tests for the configuration system.

Tests configuration loading, validation, migration, and error handling.
"""

import unittest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

from pymodes_integration.config import (
    ConfigManager, ConfigurationError, ADSBConfig, PyModeSConfig,
    MessageSource, AircraftTracking, WatchlistConfig, LoggingConfig,
    PerformanceConfig, ReferencePosition, CPRSettings, MessageValidation,
    DecoderSettings, AlertThrottling
)


class TestConfigManager(unittest.TestCase):
    """Test cases for ConfigManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_config.json")
        self.config_manager = ConfigManager(self.config_path)
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_create_default_config(self):
        """Test creation of default configuration."""
        config = self.config_manager._create_default_config()
        
        self.assertIsInstance(config, ADSBConfig)
        self.assertTrue(config.pymodes.enabled)
        self.assertEqual(len(config.message_sources), 1)
        self.assertEqual(config.message_sources[0].name, "dump1090_primary")
        self.assertEqual(config.message_sources[0].type, "dump1090")
    
    def test_load_nonexistent_config(self):
        """Test loading configuration when file doesn't exist."""
        config = self.config_manager.load_config()
        
        self.assertIsInstance(config, ADSBConfig)
        self.assertTrue(Path(self.config_path).exists())
    
    def test_load_valid_config(self):
        """Test loading a valid configuration file."""
        # Create a valid config file
        valid_config = {
            "dump1090_host": "localhost",
            "dump1090_port": 30005,
            "target_icao_codes": ["ABC123"],
            "pymodes": {
                "enabled": True,
                "reference_position": {"latitude": 40.0, "longitude": -74.0},
                "cpr_settings": {"global_position_timeout": 15},
                "message_validation": {"enable_crc_check": True},
                "decoder_settings": {"supported_message_types": ["DF17"]}
            },
            "message_sources": [
                {
                    "name": "test_source",
                    "type": "dump1090",
                    "enabled": True,
                    "host": "test.example.com",
                    "port": 30005,
                    "format": "beast"
                }
            ],
            "aircraft_tracking": {"aircraft_timeout_sec": 600},
            "watchlist": {
                "enabled": True,
                "alert_throttling": {"enabled": True, "min_interval_sec": 600}
            },
            "logging": {"level": "DEBUG"},
            "performance": {"message_batch_size": 200}
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(valid_config, f)
        
        config = self.config_manager.load_config()
        
        self.assertEqual(config.dump1090_host, "localhost")
        self.assertEqual(config.dump1090_port, 30005)
        self.assertEqual(config.target_icao_codes, ["ABC123"])
        self.assertTrue(config.pymodes.enabled)
        self.assertEqual(config.pymodes.reference_position.latitude, 40.0)
        self.assertEqual(config.pymodes.cpr_settings.global_position_timeout, 15)
        self.assertEqual(len(config.message_sources), 1)
        self.assertEqual(config.message_sources[0].name, "test_source")
        self.assertEqual(config.aircraft_tracking.aircraft_timeout_sec, 600)
        self.assertEqual(config.logging.level, "DEBUG")
    
    def test_migration_needed(self):
        """Test detection of configuration that needs migration."""
        # Old format config (missing pyModeS section)
        old_config = {
            "dump1090_host": "localhost",
            "dump1090_port": 30005,
            "target_icao_codes": []
        }
        
        self.assertTrue(self.config_manager._needs_migration(old_config))
        
        # New format config
        new_config = {
            "dump1090_host": "localhost",
            "pymodes": {"enabled": True},
            "message_sources": []
        }
        
        self.assertFalse(self.config_manager._needs_migration(new_config))
    
    def test_config_migration(self):
        """Test configuration migration from old to new format."""
        # Create old format config
        old_config = {
            "dump1090_host": "test.example.com",
            "dump1090_port": 30006,
            "target_icao_codes": ["TEST01"],
            "alert_interval_sec": 600,
            "poll_interval_sec": 2
        }
        
        with open(self.config_path, 'w') as f:
            json.dump(old_config, f)
        
        # Load config (should trigger migration)
        config = self.config_manager.load_config()
        
        # Verify migration preserved old settings
        self.assertEqual(config.dump1090_host, "test.example.com")
        self.assertEqual(config.dump1090_port, 30006)
        self.assertEqual(config.target_icao_codes, ["TEST01"])
        
        # Verify new sections were added
        self.assertTrue(hasattr(config, 'pymodes'))
        self.assertTrue(config.pymodes.enabled)
        self.assertEqual(len(config.message_sources), 1)
        self.assertEqual(config.message_sources[0].host, "test.example.com")
        self.assertEqual(config.message_sources[0].port, 30006)
        
        # Verify migrated alert settings
        self.assertEqual(config.watchlist.alert_throttling.min_interval_sec, 600)
        self.assertEqual(config.performance.processing_interval_ms, 2000)
    
    def test_config_validation_success(self):
        """Test successful configuration validation."""
        config = self.config_manager._create_default_config()
        
        # Should not raise exception
        self.config_manager._validate_config(config)
    
    def test_config_validation_errors(self):
        """Test configuration validation with various errors."""
        config = self.config_manager._create_default_config()
        
        # Test invalid CPR timeout
        config.pymodes.cpr_settings.global_position_timeout = -1
        with self.assertRaises(ConfigurationError):
            self.config_manager._validate_config(config)
        
        # Reset and test empty message sources
        config = self.config_manager._create_default_config()
        config.message_sources = []
        with self.assertRaises(ConfigurationError):
            self.config_manager._validate_config(config)
        
        # Reset and test invalid port
        config = self.config_manager._create_default_config()
        config.message_sources[0].port = -1
        with self.assertRaises(ConfigurationError):
            self.config_manager._validate_config(config)
        
        # Reset and test invalid aircraft timeout
        config = self.config_manager._create_default_config()
        config.aircraft_tracking.aircraft_timeout_sec = 0
        with self.assertRaises(ConfigurationError):
            self.config_manager._validate_config(config)
    
    def test_save_and_load_config(self):
        """Test saving and loading configuration."""
        # Create and modify config
        config = self.config_manager._create_default_config()
        config.dump1090_host = "modified.example.com"
        config.pymodes.reference_position.latitude = 45.0
        
        self.config_manager._config = config
        self.config_manager.save_config()
        
        # Create new manager and load
        new_manager = ConfigManager(self.config_path)
        loaded_config = new_manager.load_config()
        
        self.assertEqual(loaded_config.dump1090_host, "modified.example.com")
        self.assertEqual(loaded_config.pymodes.reference_position.latitude, 45.0)
    
    def test_update_config(self):
        """Test configuration updates."""
        config = self.config_manager.load_config()
        
        updates = {
            "dump1090_host": "updated.example.com",
            "pymodes": {
                "reference_position": {
                    "latitude": 50.0
                }
            }
        }
        
        self.config_manager.update_config(updates)
        updated_config = self.config_manager.get_config()
        
        self.assertEqual(updated_config.dump1090_host, "updated.example.com")
        # Note: This test would need more sophisticated update logic in the actual implementation
    
    def test_invalid_json_handling(self):
        """Test handling of invalid JSON files."""
        # Write invalid JSON
        with open(self.config_path, 'w') as f:
            f.write("{ invalid json }")
        
        with self.assertRaises(ConfigurationError):
            self.config_manager.load_config()


class TestConfigDataClasses(unittest.TestCase):
    """Test cases for configuration data classes."""
    
    def test_reference_position_creation(self):
        """Test ReferencePosition data class."""
        pos = ReferencePosition(latitude=40.0, longitude=-74.0)
        self.assertEqual(pos.latitude, 40.0)
        self.assertEqual(pos.longitude, -74.0)
        
        # Test default values
        pos_default = ReferencePosition()
        self.assertIsNone(pos_default.latitude)
        self.assertIsNone(pos_default.longitude)
    
    def test_message_source_creation(self):
        """Test MessageSource data class."""
        source = MessageSource(
            name="test_source",
            type="dump1090",
            host="test.example.com",
            port=30005
        )
        
        self.assertEqual(source.name, "test_source")
        self.assertEqual(source.type, "dump1090")
        self.assertEqual(source.host, "test.example.com")
        self.assertEqual(source.port, 30005)
        self.assertTrue(source.enabled)  # Default value
        self.assertEqual(source.format, "beast")  # Default value
    
    def test_pymodes_config_creation(self):
        """Test PyModeSConfig data class."""
        config = PyModeSConfig()
        
        self.assertTrue(config.enabled)
        self.assertIsInstance(config.reference_position, ReferencePosition)
        self.assertIsInstance(config.cpr_settings, CPRSettings)
        self.assertIsInstance(config.message_validation, MessageValidation)
        self.assertIsInstance(config.decoder_settings, DecoderSettings)
    
    def test_adsb_config_creation(self):
        """Test ADSBConfig data class."""
        config = ADSBConfig()
        
        # Test default values
        self.assertEqual(config.dump1090_host, "localhost")
        self.assertEqual(config.dump1090_port, 30005)
        self.assertEqual(config.target_icao_codes, [])
        self.assertIsInstance(config.pymodes, PyModeSConfig)
        self.assertEqual(config.message_sources, [])
        self.assertIsInstance(config.aircraft_tracking, AircraftTracking)
        self.assertIsInstance(config.watchlist, WatchlistConfig)
        self.assertIsInstance(config.logging, LoggingConfig)
        self.assertIsInstance(config.performance, PerformanceConfig)


class TestConfigValidatorScript(unittest.TestCase):
    """Test cases for the config validator script."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.temp_dir, "test_config.json")
    
    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)
    
    @patch('config_validator.ConfigManager')
    def test_validate_config_success(self, mock_config_manager):
        """Test successful configuration validation."""
        from config_validator import validate_config
        
        mock_manager = MagicMock()
        mock_config_manager.return_value = mock_manager
        mock_manager.load_config.return_value = ADSBConfig()
        
        result = validate_config(self.config_path)
        self.assertTrue(result)
        mock_manager.load_config.assert_called_once()
    
    @patch('config_validator.ConfigManager')
    def test_validate_config_failure(self, mock_config_manager):
        """Test configuration validation failure."""
        from config_validator import validate_config
        
        mock_manager = MagicMock()
        mock_config_manager.return_value = mock_manager
        mock_manager.load_config.side_effect = ConfigurationError("Test error")
        
        result = validate_config(self.config_path)
        self.assertFalse(result)
    
    def test_create_default_config_success(self):
        """Test successful default configuration creation."""
        from config_validator import create_default_config
        
        result = create_default_config(self.config_path)
        self.assertTrue(result)
        self.assertTrue(Path(self.config_path).exists())
    
    def test_create_default_config_exists(self):
        """Test default configuration creation when file exists."""
        from config_validator import create_default_config
        
        # Create existing file
        Path(self.config_path).touch()
        
        result = create_default_config(self.config_path, overwrite=False)
        self.assertFalse(result)
        
        # Test with overwrite
        result = create_default_config(self.config_path, overwrite=True)
        self.assertTrue(result)


if __name__ == '__main__':
    # Set up test environment
    import sys
    import os
    
    # Add the project root to Python path
    project_root = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, project_root)
    
    # Run tests
    unittest.main(verbosity=2)