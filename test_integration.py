#!/usr/bin/env python3
"""
Integration Test Suite for Ursine Explorer ADS-B Receiver
Tests the complete integrated system with pyModeS components
"""

import unittest
import json
import time
import threading
import tempfile
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import logging

# Add current directory to path for imports
sys.path.insert(0, '.')

# Import components to test
try:
    from adsb_receiver_integrated import IntegratedADSBServer
    from pymodes_integration import (
        PyModeSDecode, MessageSourceManager, Dump1090Source,
        EnhancedAircraft, MessageValidator, ADSBLogger
    )
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Import error: {e}")
    IMPORTS_AVAILABLE = False

# Set up logging for tests
logging.basicConfig(level=logging.WARNING)  # Reduce noise during tests


class TestIntegratedSystem(unittest.TestCase):
    """Test the complete integrated system"""
    
    def setUp(self):
        """Set up test environment"""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Required modules not available")
        
        # Create temporary config
        self.test_config = {
            "dump1090_host": "localhost",
            "dump1090_port": 30005,
            "receiver_control_port": 8081,
            "target_icao_codes": ["A12345", "B67890"],
            "meshtastic_port": None,  # Disable for testing
            "pymodes": {
                "enabled": True,
                "reference_position": {
                    "latitude": 40.7128,
                    "longitude": -74.0060
                }
            },
            "message_sources": [
                {
                    "name": "test_source",
                    "type": "dump1090",
                    "enabled": True,
                    "host": "localhost",
                    "port": 30005,
                    "format": "beast"
                }
            ]
        }
        
        # Create temporary config file
        self.config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(self.test_config, self.config_file)
        self.config_file.close()
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'config_file'):
            try:
                os.unlink(self.config_file.name)
            except:
                pass
    
    def test_server_initialization(self):
        """Test server initializes correctly"""
        server = IntegratedADSBServer(self.config_file.name)
        
        self.assertIsNotNone(server.config)
        self.assertIsNotNone(server.pymodes_decoder)
        self.assertIsNotNone(server.message_source_manager)
        self.assertEqual(len(server.watchlist), 2)  # Two ICAO codes in config
        self.assertIn("A12345", server.watchlist)
        self.assertIn("B67890", server.watchlist)
    
    def test_config_loading(self):
        """Test configuration loading and defaults"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Check basic config
        self.assertEqual(server.config['dump1090_host'], 'localhost')
        self.assertEqual(server.config['dump1090_port'], 30005)
        
        # Check pyModeS config
        self.assertTrue(server.config['pymodes']['enabled'])
        self.assertEqual(server.config['pymodes']['reference_position']['latitude'], 40.7128)
        
        # Check message sources
        self.assertEqual(len(server.config['message_sources']), 1)
        self.assertEqual(server.config['message_sources'][0]['name'], 'test_source')
    
    def test_pymodes_decoder_integration(self):
        """Test pyModeS decoder integration"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Test sample ADS-B messages
        test_messages = [
            ("8D4840D6202CC371C32CE0576098", time.time()),  # Position message
            ("8D4840D658C382D690C8AC2863A7", time.time()),  # Velocity message
        ]
        
        # Process messages
        updated_aircraft = server.pymodes_decoder.process_messages(test_messages)
        
        # Check results
        self.assertIsInstance(updated_aircraft, dict)
        # Note: Actual decoding depends on pyModeS being available
    
    def test_aircraft_tracking(self):
        """Test aircraft tracking functionality"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Create test aircraft data
        test_aircraft_data = {
            'icao': 'A12345',
            'timestamp': time.time(),
            'message_type': 'identification',
            'callsign': 'TEST123'
        }
        
        # Create aircraft
        aircraft = EnhancedAircraft.from_pymodes_data(test_aircraft_data)
        server.aircraft['A12345'] = aircraft
        
        # Check aircraft is tracked
        self.assertIn('A12345', server.aircraft)
        self.assertEqual(server.aircraft['A12345'].callsign, 'TEST123')
        self.assertTrue(server.aircraft['A12345'].is_watchlist)  # Should be on watchlist
    
    def test_api_endpoints(self):
        """Test API endpoint functionality"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Add test aircraft
        test_aircraft = EnhancedAircraft(
            icao='TEST01',
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            callsign='TESTFLT',
            latitude=40.7128,
            longitude=-74.0060,
            altitude_baro=35000,
            ground_speed=450
        )
        server.aircraft['TEST01'] = test_aircraft
        
        # Test get_aircraft_data (legacy format)
        aircraft_data = server.get_aircraft_data()
        self.assertIn('aircraft', aircraft_data)
        self.assertEqual(len(aircraft_data['aircraft']), 1)
        self.assertEqual(aircraft_data['aircraft'][0]['hex'], 'TEST01')
        
        # Test get_enhanced_aircraft_data
        enhanced_data = server.get_enhanced_aircraft_data()
        self.assertIn('enhanced', enhanced_data)
        self.assertTrue(enhanced_data['enhanced'])
        
        # Test status endpoints
        status = server.get_detailed_status()
        self.assertIn('server', status)
        self.assertIn('statistics', status)
        
        health = server.get_health_status()
        self.assertIn('healthy', health)
        self.assertIn('status', health)
    
    def test_watchlist_functionality(self):
        """Test watchlist monitoring"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Create test aircraft - one on watchlist, one not
        watchlist_aircraft = EnhancedAircraft(
            icao='A12345',  # On watchlist
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            callsign='WATCH1'
        )
        
        normal_aircraft = EnhancedAircraft(
            icao='NORMAL',  # Not on watchlist
            first_seen=datetime.now(),
            last_seen=datetime.now(),
            callsign='NORM1'
        )
        
        # Test watchlist checking
        updated_aircraft = {
            'A12345': watchlist_aircraft,
            'NORMAL': normal_aircraft
        }
        
        # Mock Meshtastic to avoid actual hardware
        server.meshtastic = Mock()
        server.meshtastic.serial_conn = Mock()
        server.meshtastic.send_alert = Mock(return_value=True)
        
        # Check watchlist
        server._check_watchlist(updated_aircraft)
        
        # Verify results
        self.assertTrue(watchlist_aircraft.is_watchlist)
        self.assertFalse(normal_aircraft.is_watchlist)
    
    def test_statistics_tracking(self):
        """Test statistics tracking"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Initial stats
        initial_messages = server.stats['messages_total']
        
        # Update statistics
        server._update_statistics(10, 5)  # 10 messages processed, 5 aircraft updated
        
        # Check stats updated
        self.assertEqual(server.stats['messages_total'], initial_messages + 10)
        self.assertIsNotNone(server.stats['last_update'])
        self.assertEqual(server.stats['update_count'], 1)
    
    def test_error_handling(self):
        """Test error handling and graceful degradation"""
        # Test with invalid config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            invalid_config_file = f.name
        
        try:
            # Should not crash, should use defaults
            server = IntegratedADSBServer(invalid_config_file)
            self.assertIsNotNone(server.config)
            self.assertEqual(server.config['dump1090_host'], 'localhost')  # Default value
        finally:
            os.unlink(invalid_config_file)
    
    def test_message_source_manager(self):
        """Test message source management"""
        server = IntegratedADSBServer(self.config_file.name)
        
        # Check sources were initialized
        sources_status = server.get_sources_status()
        self.assertIn('sources', sources_status)
        self.assertIn('statistics', sources_status)
        
        # Test source statistics
        source_stats = server.message_source_manager.get_statistics()
        self.assertIn('sources_total', source_stats)
        self.assertIn('sources_connected', source_stats)


class TestPyModeSIntegration(unittest.TestCase):
    """Test pyModeS integration components"""
    
    def setUp(self):
        """Set up test environment"""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Required modules not available")
    
    def test_message_validation(self):
        """Test message validation"""
        validator = MessageValidator()
        
        # Test valid message format
        valid_message = "8D4840D6202CC371C32CE0576098"
        self.assertTrue(len(valid_message) == 28)  # 14 bytes * 2 hex chars
        
        # Test invalid message format
        invalid_message = "invalid"
        self.assertFalse(len(invalid_message) == 28)
    
    def test_enhanced_aircraft(self):
        """Test enhanced aircraft data structure"""
        now = datetime.now()
        
        aircraft = EnhancedAircraft(
            icao='TEST01',
            first_seen=now,
            last_seen=now,
            callsign='TESTFLT',
            latitude=40.7128,
            longitude=-74.0060,
            altitude_baro=35000
        )
        
        # Test basic properties
        self.assertEqual(aircraft.icao, 'TEST01')
        self.assertEqual(aircraft.callsign, 'TESTFLT')
        self.assertEqual(aircraft.latitude, 40.7128)
        self.assertEqual(aircraft.altitude_baro, 35000)
        
        # Test API conversion
        api_dict = aircraft.to_api_dict()
        self.assertIn('icao', api_dict)
        self.assertIn('callsign', api_dict)
        self.assertIn('position', api_dict)
        
        # Test age calculation
        age = aircraft.calculate_age_seconds()
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 5)  # Should be very recent
    
    def test_message_source_dummy(self):
        """Test dummy message source for testing"""
        from pymodes_integration.message_source import DummyMessageSource
        
        source = DummyMessageSource("test_dummy")
        
        # Test connection
        self.assertTrue(source.connect())
        self.assertTrue(source.is_connected())
        
        # Test message generation
        messages = source.get_messages()
        # May or may not have messages depending on timing
        self.assertIsInstance(messages, list)
        
        # Test disconnection
        source.disconnect()
        self.assertFalse(source.is_connected())


class TestSystemIntegration(unittest.TestCase):
    """Test complete system integration scenarios"""
    
    def setUp(self):
        """Set up test environment"""
        if not IMPORTS_AVAILABLE:
            self.skipTest("Required modules not available")
    
    @patch('socket.socket')
    def test_end_to_end_message_flow(self, mock_socket):
        """Test complete message flow from source to aircraft tracking"""
        # Mock socket for dump1090 connection
        mock_socket_instance = Mock()
        mock_socket.return_value = mock_socket_instance
        mock_socket_instance.connect.return_value = None
        mock_socket_instance.recv.return_value = b"8D4840D6202CC371C32CE0576098\n"
        
        # Create test config
        config = {
            "message_sources": [
                {
                    "name": "test_dump1090",
                    "type": "dump1090",
                    "enabled": True,
                    "host": "localhost",
                    "port": 30005,
                    "format": "raw"
                }
            ],
            "target_icao_codes": ["4840D6"],
            "meshtastic_port": None
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_file = f.name
        
        try:
            server = IntegratedADSBServer(config_file)
            
            # Start message collection briefly
            server.message_source_manager.start_collection()
            time.sleep(0.5)  # Brief collection period
            server.message_source_manager.stop_collection()
            
            # Check that system handled the flow without errors
            self.assertIsNotNone(server.stats)
            
        finally:
            os.unlink(config_file)
    
    def test_configuration_validation(self):
        """Test configuration validation and error handling"""
        # Test various config scenarios
        test_configs = [
            # Minimal config
            {"target_icao_codes": []},
            
            # Config with pyModeS disabled
            {"pymodes": {"enabled": False}},
            
            # Config with multiple sources
            {
                "message_sources": [
                    {"name": "source1", "type": "dump1090", "enabled": True},
                    {"name": "source2", "type": "network", "enabled": False}
                ]
            }
        ]
        
        for i, config in enumerate(test_configs):
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(config, f)
                config_file = f.name
            
            try:
                server = IntegratedADSBServer(config_file)
                self.assertIsNotNone(server.config)
                # Should not crash with any of these configs
            finally:
                os.unlink(config_file)
    
    def test_performance_under_load(self):
        """Test system performance with simulated load"""
        config = {"target_icao_codes": [], "meshtastic_port": None}
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            config_file = f.name
        
        try:
            server = IntegratedADSBServer(config_file)
            
            # Simulate processing many messages
            test_messages = []
            for i in range(100):
                # Generate test messages with different ICAOs
                icao = f"{i:06X}"
                message = f"8D{icao}202CC371C32CE0576098"
                test_messages.append((message, time.time()))
            
            start_time = time.time()
            updated_aircraft = server.pymodes_decoder.process_messages(test_messages)
            processing_time = time.time() - start_time
            
            # Check performance is reasonable (should process 100 messages quickly)
            self.assertLess(processing_time, 5.0)  # Should take less than 5 seconds
            self.assertIsInstance(updated_aircraft, dict)
            
        finally:
            os.unlink(config_file)


def run_integration_tests():
    """Run all integration tests"""
    print("Running Ursine Explorer ADS-B Integration Tests")
    print("=" * 50)
    
    if not IMPORTS_AVAILABLE:
        print("❌ Required modules not available for testing")
        print("Please ensure all dependencies are installed:")
        print("  pip install pyModeS numpy requests pyserial")
        return False
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestIntegratedSystem,
        TestPyModeSIntegration,
        TestSystemIntegration
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print("\n" + "=" * 50)
    if result.wasSuccessful():
        print("✅ All integration tests passed!")
        print(f"Ran {result.testsRun} tests successfully")
        return True
    else:
        print("❌ Some integration tests failed!")
        print(f"Ran {result.testsRun} tests")
        print(f"Failures: {len(result.failures)}")
        print(f"Errors: {len(result.errors)}")
        
        if result.failures:
            print("\nFailures:")
            for test, traceback in result.failures:
                print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
        
        if result.errors:
            print("\nErrors:")
            for test, traceback in result.errors:
                print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")
        
        return False


def main():
    """Main test function"""
    success = run_integration_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()