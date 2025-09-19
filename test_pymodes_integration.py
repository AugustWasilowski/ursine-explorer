#!/usr/bin/env python3
"""
Test script for pyModeS integration foundation

This script tests the basic integration structure and verifies that
all components can be imported and initialized correctly.
"""

import sys
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_imports():
    """Test that all integration modules can be imported"""
    logger.info("Testing module imports...")
    
    try:
        from pymodes_integration.config import PyModeSConfig
        logger.info("✓ Config module imported successfully")
    except ImportError as e:
        logger.error(f"✗ Failed to import config module: {e}")
        return False
    
    try:
        from pymodes_integration.aircraft import EnhancedAircraft
        logger.info("✓ Aircraft module imported successfully")
    except ImportError as e:
        logger.error(f"✗ Failed to import aircraft module: {e}")
        return False
    
    try:
        from pymodes_integration.message_source import MessageSource, MessageSourceManager, DummyMessageSource
        logger.info("✓ Message source module imported successfully")
    except ImportError as e:
        logger.error(f"✗ Failed to import message source module: {e}")
        return False
    
    try:
        from pymodes_integration.decoder import PyModeSDecode
        logger.info("✓ Decoder module imported successfully")
    except ImportError as e:
        logger.error(f"✗ Failed to import decoder module: {e}")
        return False
    
    try:
        import pymodes_integration
        logger.info("✓ Main integration package imported successfully")
    except ImportError as e:
        logger.error(f"✗ Failed to import main package: {e}")
        return False
    
    return True

def test_config():
    """Test configuration functionality"""
    logger.info("Testing configuration...")
    
    try:
        from pymodes_integration.config import PyModeSConfig
        
        # Test default config
        config = PyModeSConfig()
        logger.info("✓ Default configuration created")
        
        # Test validation
        if config.validate():
            logger.info("✓ Configuration validation passed")
        else:
            logger.error("✗ Configuration validation failed")
            return False
        
        # Test from dict
        config_dict = {
            'pymodes': {
                'crc_validation': True,
                'reference_latitude': 40.7128,
                'reference_longitude': -74.0060
            }
        }
        config_from_dict = PyModeSConfig.from_dict(config_dict)
        logger.info("✓ Configuration created from dictionary")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Configuration test failed: {e}")
        return False

def test_aircraft():
    """Test enhanced aircraft functionality"""
    logger.info("Testing enhanced aircraft...")
    
    try:
        from pymodes_integration.aircraft import EnhancedAircraft
        
        # Test creation from pyModeS data
        pymodes_data = {
            'icao': 'A12345',
            'timestamp': datetime.now().timestamp(),
            'message_type': 'identification',
            'callsign': 'TEST123'
        }
        
        aircraft = EnhancedAircraft.from_pymodes_data(pymodes_data)
        logger.info(f"✓ Aircraft created: {aircraft}")
        
        # Test API conversion
        api_dict = aircraft.to_api_dict()
        logger.info("✓ Aircraft converted to API format")
        
        # Test legacy conversion
        legacy_dict = aircraft.to_legacy_dict()
        logger.info("✓ Aircraft converted to legacy format")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Aircraft test failed: {e}")
        return False

def test_message_source():
    """Test message source functionality"""
    logger.info("Testing message source...")
    
    try:
        from pymodes_integration.message_source import MessageSourceManager, DummyMessageSource
        
        # Test manager
        manager = MessageSourceManager()
        logger.info("✓ Message source manager created")
        
        # Test dummy source
        dummy_source = DummyMessageSource("test-dummy")
        logger.info("✓ Dummy message source created")
        
        # Test adding source
        if manager.add_source(dummy_source):
            logger.info("✓ Source added to manager")
        else:
            logger.error("✗ Failed to add source to manager")
            return False
        
        # Test connection
        if dummy_source.connect():
            logger.info("✓ Dummy source connected")
        else:
            logger.error("✗ Failed to connect dummy source")
            return False
        
        # Test message generation
        messages = dummy_source.get_messages()
        logger.info(f"✓ Generated {len(messages)} messages")
        
        dummy_source.disconnect()
        logger.info("✓ Dummy source disconnected")
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Message source test failed: {e}")
        return False

def test_decoder():
    """Test decoder functionality (without pyModeS)"""
    logger.info("Testing decoder...")
    
    try:
        from pymodes_integration.decoder import PyModeSDecode
        from pymodes_integration.config import PyModeSConfig
        
        # This will fail if pyModeS is not installed, which is expected
        try:
            config = PyModeSConfig()
            decoder = PyModeSDecode(config)
            logger.info("✓ Decoder created (pyModeS available)")
            return True
        except ImportError:
            logger.warning("⚠ pyModeS not available - decoder creation skipped")
            logger.info("✓ Decoder import successful (pyModeS will be required at runtime)")
            return True
        
    except Exception as e:
        logger.error(f"✗ Decoder test failed: {e}")
        return False

def main():
    """Run all tests"""
    logger.info("Starting pyModeS integration foundation tests")
    logger.info("=" * 50)
    
    tests = [
        ("Module Imports", test_imports),
        ("Configuration", test_config),
        ("Enhanced Aircraft", test_aircraft),
        ("Message Source", test_message_source),
        ("Decoder", test_decoder),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\nRunning test: {test_name}")
        logger.info("-" * 30)
        
        if test_func():
            logger.info(f"✓ {test_name} PASSED")
            passed += 1
        else:
            logger.error(f"✗ {test_name} FAILED")
    
    logger.info("\n" + "=" * 50)
    logger.info(f"Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! pyModeS integration foundation is ready.")
        return 0
    else:
        logger.error("❌ Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())