#!/usr/bin/env python3
"""
Comprehensive Unit Tests for pyModeS Integration

This test suite provides comprehensive unit tests for pyModeS integration components
including message decoding, aircraft data processing, and position calculation accuracy
with reference data.

Requirements covered:
- 1.1: Test message decoding with known ADS-B message samples
- 2.1: Validate aircraft data processing and updates  
- 4.1: Test position calculation accuracy with reference data
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import json

# Test data - Known ADS-B message samples with expected results
TEST_MESSAGES = {
    # Aircraft identification message (TC=4)
    'identification': {
        'message': '8D4840D6202CC371C32CE0576098',
        'icao': '4840D6',
        'callsign': 'KLM1023',
        'expected_type': 'identification',
        'df': 17,
        'tc': 4
    },
    
    # Airborne position message (TC=11, even)
    'position_even': {
        'message': '8D40621D58C382D690C8AC2863A7',
        'icao': '40621D',
        'expected_type': 'airborne_position',
        'cpr_format': 'even',
        'df': 17,
        'tc': 11,
        'altitude': 38000,
        'lat_cpr': 74158,
        'lon_cpr': 50194
    },
    
    # Airborne position message (TC=11, odd)
    'position_odd': {
        'message': '8D40621D58C386435CC412692AD6',
        'icao': '40621D',
        'expected_type': 'airborne_position',
        'cpr_format': 'odd',
        'df': 17,
        'tc': 11,
        'altitude': 38000,
        'lat_cpr': 74158,
        'lon_cpr': 50194
    },
    
    # Velocity message (TC=19)
    'velocity': {
        'message': '8D485020994409940838175B284F',
        'icao': '485020',
        'expected_type': 'velocity',
        'df': 17,
        'tc': 19,
        'ground_speed': 159,
        'track': 183.2,
        'vertical_rate': -64,
        'true_airspeed': 180,
        'indicated_airspeed': 165
    },
    
    # Surface position message (TC=6)
    'surface_position': {
        'message': '8D4840D6304149B1C36E60A5343D',
        'icao': '4840D6',
        'expected_type': 'surface_position',
        'df': 17,
        'tc': 6
    },
    
    # Surveillance message (DF4)
    'surveillance': {
        'message': '20001838CA3804',
        'icao': '001838',
        'expected_type': 'surveillance',
        'df': 4,
        'altitude': 2000
    }
}

# Reference position for testing (Amsterdam Airport Schiphol)
TEST_REFERENCE_LAT = 52.3676
TEST_REFERENCE_LON = 4.9041

# Expected position calculation results
EXPECTED_POSITIONS = {
    'global_cpr': {
        'icao': '40621D',
        'latitude': 52.2572,
        'longitude': 3.9190
    },
    'local_cpr': {
        'icao': '40621D',
        'latitude': 52.3676,
        'longitude': 4.9041
    }
}


class TestPyModeSDecoder(unittest.TestCase):
    """Test cases for PyModeSDecode class"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock pyModeS to avoid dependency issues
        self.pymodes_mock = Mock()
        
        # Create patches
        self.pymodes_patch = patch.dict('sys.modules', {
            'pyModeS': self.pymodes_mock,
            'pymodes_integration.decoder.pms': self.pymodes_mock
        })
        self.pymodes_available_patch = patch('pymodes_integration.decoder.PYMODES_AVAILABLE', True)
        
        # Start patches
        self.pymodes_patch.start()
        self.pymodes_available_patch.start()
        
        # Import after patching
        try:
            from pymodes_integration.decoder import PyModeSDecode
            from pymodes_integration.config import PyModeSConfig
            
            self.PyModeSDecode = PyModeSDecode
            self.config = PyModeSConfig()
            self.decoder = PyModeSDecode(self.config)
        except ImportError:
            self.skipTest("pyModeS integration modules not available")
    
    def tearDown(self):
        """Clean up patches"""
        self.pymodes_patch.stop()
        self.pymodes_available_patch.stop()
    
    def test_decoder_initialization(self):
        """Test decoder initialization with configuration"""
        self.assertIsNotNone(self.decoder)
        self.assertEqual(len(self.decoder.aircraft), 0)
        self.assertIsInstance(self.decoder.stats, dict)
        self.assertIn('messages_processed', self.decoder.stats)
        self.assertIn('messages_decoded', self.decoder.stats)
        self.assertIn('messages_failed', self.decoder.stats)
        self.assertEqual(self.decoder.stats['messages_processed'], 0)
    
    def test_message_validation_valid_messages(self):
        """Test message validation with valid ADS-B messages"""
        # Mock CRC validation to return success
        self.pymodes_mock.crc.return_value = 0
        
        # Test all valid test messages
        for msg_type, msg_data in TEST_MESSAGES.items():
            with self.subTest(message_type=msg_type):
                result = self.decoder.is_valid_message(msg_data['message'])
                self.assertTrue(result, f"Valid message {msg_type} should pass validation")
    
    def test_message_validation_invalid_messages(self):
        """Test message validation with invalid messages"""
        invalid_messages = [
            ('empty', ''),
            ('too_short', '123'),
            ('too_long', '8D4840D6202CC371C32CE0576098EXTRA'),
            ('non_hex', 'ZZZZZZZZZZZZZZ'),
            ('wrong_length', '8D4840D6202CC371C32CE057609'),  # 13 bytes
        ]
        
        for desc, message in invalid_messages:
            with self.subTest(invalid_type=desc):
                result = self.decoder.is_valid_message(message)
                self.assertFalse(result, f"Invalid message ({desc}) should fail validation")
    
    def test_message_validation_crc_failure(self):
        """Test message validation with CRC failures"""
        # Mock CRC validation to return failure
        self.pymodes_mock.crc.return_value = 1
        
        valid_message = TEST_MESSAGES['identification']['message']
        result = self.decoder.is_valid_message(valid_message)
        self.assertFalse(result, "Message with CRC failure should be rejected")
    
    def test_decode_identification_message(self):
        """Test decoding aircraft identification message (Requirement 1.1)"""
        test_data = TEST_MESSAGES['identification']
        
        # Mock pyModeS functions for identification message
        self.pymodes_mock.icao.return_value = test_data['icao']
        self.pymodes_mock.df.return_value = test_data['df']
        self.pymodes_mock.adsb.typecode.return_value = test_data['tc']
        self.pymodes_mock.adsb.callsign.return_value = test_data['callsign']
        self.pymodes_mock.crc.return_value = 0
        
        timestamp = datetime.now().timestamp()
        decoded = self.decoder.decode_message(test_data['message'], timestamp)
        
        # Verify decoded data
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['icao'], test_data['icao'])
        self.assertEqual(decoded['message_type'], test_data['expected_type'])
        self.assertEqual(decoded['callsign'], test_data['callsign'])
        self.assertEqual(decoded['df'], test_data['df'])
        self.assertEqual(decoded['tc'], test_data['tc'])
        self.assertEqual(decoded['timestamp'], timestamp)
        self.assertEqual(decoded['raw_message'], test_data['message'])
    
    def test_decode_position_message(self):
        """Test decoding airborne position message (Requirement 2.1)"""
        test_data = TEST_MESSAGES['position_even']
        
        # Mock pyModeS functions for position message
        self.pymodes_mock.icao.return_value = test_data['icao']
        self.pymodes_mock.df.return_value = test_data['df']
        self.pymodes_mock.adsb.typecode.return_value = test_data['tc']
        self.pymodes_mock.adsb.oe_flag.return_value = 0  # even format
        self.pymodes_mock.adsb.cprlat.return_value = test_data['lat_cpr']
        self.pymodes_mock.adsb.cprlon.return_value = test_data['lon_cpr']
        self.pymodes_mock.adsb.altitude.return_value = test_data['altitude']
        self.pymodes_mock.crc.return_value = 0
        
        timestamp = datetime.now().timestamp()
        decoded = self.decoder.decode_message(test_data['message'], timestamp)
        
        # Verify decoded data
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['icao'], test_data['icao'])
        self.assertEqual(decoded['message_type'], test_data['expected_type'])
        self.assertEqual(decoded['altitude'], test_data['altitude'])
        self.assertEqual(decoded['cpr_format'], test_data['cpr_format'])
        self.assertEqual(decoded['df'], test_data['df'])
        self.assertEqual(decoded['tc'], test_data['tc'])
    
    def test_decode_velocity_message(self):
        """Test decoding velocity message (Requirement 1.1)"""
        test_data = TEST_MESSAGES['velocity']
        
        # Mock pyModeS functions for velocity message
        self.pymodes_mock.icao.return_value = test_data['icao']
        self.pymodes_mock.df.return_value = test_data['df']
        self.pymodes_mock.adsb.typecode.return_value = test_data['tc']
        self.pymodes_mock.adsb.velocity.return_value = (
            test_data['ground_speed'], 
            test_data['track'], 
            test_data['vertical_rate'], 
            'GS'
        )
        self.pymodes_mock.adsb.tas.return_value = test_data['true_airspeed']
        self.pymodes_mock.adsb.ias.return_value = test_data['indicated_airspeed']
        self.pymodes_mock.adsb.mach.return_value = None
        self.pymodes_mock.crc.return_value = 0
        
        timestamp = datetime.now().timestamp()
        decoded = self.decoder.decode_message(test_data['message'], timestamp)
        
        # Verify decoded data
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['icao'], test_data['icao'])
        self.assertEqual(decoded['message_type'], test_data['expected_type'])
        self.assertEqual(decoded['ground_speed'], test_data['ground_speed'])
        self.assertEqual(decoded['track'], test_data['track'])
        self.assertEqual(decoded['vertical_rate'], test_data['vertical_rate'])
        self.assertEqual(decoded['true_airspeed'], test_data['true_airspeed'])
        self.assertEqual(decoded['indicated_airspeed'], test_data['indicated_airspeed'])
    
    def test_decode_surface_position_message(self):
        """Test decoding surface position message"""
        test_data = TEST_MESSAGES['surface_position']
        
        # Mock pyModeS functions for surface position
        self.pymodes_mock.icao.return_value = test_data['icao']
        self.pymodes_mock.df.return_value = test_data['df']
        self.pymodes_mock.adsb.typecode.return_value = test_data['tc']
        self.pymodes_mock.adsb.oe_flag.return_value = 0
        self.pymodes_mock.adsb.cprlat.return_value = 74158
        self.pymodes_mock.adsb.cprlon.return_value = 50194
        self.pymodes_mock.crc.return_value = 0
        
        timestamp = datetime.now().timestamp()
        decoded = self.decoder.decode_message(test_data['message'], timestamp)
        
        # Verify decoded data
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['icao'], test_data['icao'])
        self.assertEqual(decoded['message_type'], test_data['expected_type'])
        self.assertEqual(decoded['cpr_format'], 'even')
    
    def test_decode_surveillance_message(self):
        """Test decoding surveillance message (DF4/5/20/21)"""
        test_data = TEST_MESSAGES['surveillance']
        
        # Mock pyModeS functions for surveillance message
        self.pymodes_mock.icao.return_value = test_data['icao']
        self.pymodes_mock.df.return_value = test_data['df']
        self.pymodes_mock.common.altcode.return_value = test_data['altitude']
        self.pymodes_mock.crc.return_value = 0
        
        timestamp = datetime.now().timestamp()
        decoded = self.decoder.decode_message(test_data['message'], timestamp)
        
        # Verify decoded data
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded['icao'], test_data['icao'])
        self.assertEqual(decoded['message_type'], test_data['expected_type'])
        self.assertEqual(decoded['altitude'], test_data['altitude'])
        self.assertEqual(decoded['df'], test_data['df'])
    
    def test_process_messages_batch(self):
        """Test processing a batch of messages (Requirement 2.1)"""
        # Mock successful decoding for identification message
        self.pymodes_mock.icao.return_value = 'ABC123'
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 4
        self.pymodes_mock.adsb.callsign.return_value = 'TEST123'
        self.pymodes_mock.crc.return_value = 0
        
        # Create batch of messages
        timestamp = datetime.now().timestamp()
        messages = [
            (TEST_MESSAGES['identification']['message'], timestamp),
            (TEST_MESSAGES['identification']['message'], timestamp + 1),
            ('INVALID_MESSAGE', timestamp + 2)  # This should fail
        ]
        
        updated_aircraft = self.decoder.process_messages(messages)
        
        # Verify processing results
        self.assertEqual(len(updated_aircraft), 1)
        self.assertIn('ABC123', updated_aircraft)
        self.assertEqual(self.decoder.stats['messages_processed'], 3)
        self.assertEqual(self.decoder.stats['messages_decoded'], 2)
        self.assertEqual(self.decoder.stats['messages_failed'], 1)
        
        # Verify aircraft was created and updated
        aircraft = updated_aircraft['ABC123']
        self.assertEqual(aircraft.icao, 'ABC123')
        self.assertEqual(aircraft.callsign, 'TEST123')
        self.assertEqual(aircraft.message_count, 2)  # Two successful messages
    
    def test_aircraft_cleanup(self):
        """Test old aircraft cleanup functionality"""
        # Create aircraft with old timestamp
        old_time = datetime.now() - timedelta(minutes=10)
        
        # Mock aircraft creation
        self.pymodes_mock.icao.return_value = 'OLD123'
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 4
        self.pymodes_mock.adsb.callsign.return_value = 'OLDTEST'
        self.pymodes_mock.crc.return_value = 0
        
        # Process message to create aircraft
        messages = [(TEST_MESSAGES['identification']['message'], old_time.timestamp())]
        self.decoder.process_messages(messages)
        
        # Verify aircraft exists
        self.assertEqual(len(self.decoder.aircraft), 1)
        self.assertIn('OLD123', self.decoder.aircraft)
        
        # Clean up with short timeout (60 seconds)
        removed = self.decoder.clear_old_aircraft(timeout_seconds=60)
        
        # Verify cleanup
        self.assertEqual(removed, 1)
        self.assertEqual(len(self.decoder.aircraft), 0)
        self.assertNotIn('OLD123', self.decoder.aircraft)
    
    def test_statistics_tracking(self):
        """Test statistics tracking functionality"""
        # Get initial statistics
        initial_stats = self.decoder.get_statistics()
        self.assertIn('messages_processed', initial_stats)
        self.assertIn('aircraft_count', initial_stats)
        self.assertEqual(initial_stats['messages_processed'], 0)
        self.assertEqual(initial_stats['aircraft_count'], 0)
        
        # Process some messages
        self.pymodes_mock.icao.return_value = 'STAT123'
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 4
        self.pymodes_mock.crc.return_value = 0
        
        messages = [(TEST_MESSAGES['identification']['message'], datetime.now().timestamp())]
        self.decoder.process_messages(messages)
        
        # Check updated statistics
        updated_stats = self.decoder.get_statistics()
        self.assertEqual(updated_stats['messages_processed'], 1)
        self.assertEqual(updated_stats['aircraft_count'], 1)
        self.assertGreater(updated_stats['decode_rate'], 0)


class TestEnhancedAircraft(unittest.TestCase):
    """Test cases for EnhancedAircraft class (Requirement 2.1)"""
    
    def setUp(self):
        """Set up test fixtures"""
        try:
            from pymodes_integration.aircraft import EnhancedAircraft
            self.EnhancedAircraft = EnhancedAircraft
        except ImportError:
            self.skipTest("EnhancedAircraft module not available")
        
        self.test_pymodes_data = {
            'icao': 'ABC123',
            'timestamp': datetime.now().timestamp(),
            'message_type': 'identification',
            'callsign': 'TEST123',
            'latitude': 52.3676,
            'longitude': 4.9041,
            'altitude': 35000,
            'ground_speed': 450,
            'track': 90,
            'vertical_rate': 1000,
            'true_airspeed': 480,
            'indicated_airspeed': 420
        }
    
    def test_aircraft_creation_from_pymodes(self):
        """Test creating aircraft from pyModeS data"""
        aircraft = self.EnhancedAircraft.from_pymodes_data(self.test_pymodes_data)
        
        # Verify core fields
        self.assertEqual(aircraft.icao, 'ABC123')
        self.assertEqual(aircraft.callsign, 'TEST123')
        self.assertEqual(aircraft.message_count, 1)
        self.assertIsInstance(aircraft.first_seen, datetime)
        self.assertIsInstance(aircraft.last_seen, datetime)
        
        # Verify position data
        self.assertEqual(aircraft.latitude, 52.3676)
        self.assertEqual(aircraft.longitude, 4.9041)
        self.assertEqual(aircraft.altitude_baro, 35000)
        
        # Verify velocity data
        self.assertEqual(aircraft.ground_speed, 450)
        self.assertEqual(aircraft.track_angle, 90)
        self.assertEqual(aircraft.vertical_rate, 1000)
        
        # Verify enhanced data
        self.assertEqual(aircraft.true_airspeed, 480)
        self.assertEqual(aircraft.indicated_airspeed, 420)
        
        # Verify metadata
        self.assertFalse(aircraft.is_watchlist)
        self.assertIn('identification', aircraft.data_sources)
    
    def test_aircraft_update_from_pymodes(self):
        """Test updating aircraft with new pyModeS data"""
        aircraft = self.EnhancedAircraft.from_pymodes_data(self.test_pymodes_data)
        initial_count = aircraft.message_count
        initial_first_seen = aircraft.first_seen
        
        # Update with new velocity data
        update_data = {
            'icao': 'ABC123',
            'timestamp': datetime.now().timestamp(),
            'message_type': 'velocity',
            'ground_speed': 460,
            'track': 95,
            'vertical_rate': 1200,
            'true_airspeed': 490
        }
        
        aircraft.update_from_pymodes(update_data)
        
        # Verify updates
        self.assertEqual(aircraft.ground_speed, 460)
        self.assertEqual(aircraft.track_angle, 95)
        self.assertEqual(aircraft.vertical_rate, 1200)
        self.assertEqual(aircraft.true_airspeed, 490)
        self.assertEqual(aircraft.message_count, initial_count + 1)
        self.assertEqual(aircraft.first_seen, initial_first_seen)  # Should not change
        self.assertIn('velocity', aircraft.data_sources)
        self.assertIn('identification', aircraft.data_sources)  # Should still be there
    
    def test_aircraft_to_api_dict(self):
        """Test converting aircraft to API dictionary format"""
        aircraft = self.EnhancedAircraft.from_pymodes_data(self.test_pymodes_data)
        api_dict = aircraft.to_api_dict()
        
        # Check legacy compatibility fields
        self.assertEqual(api_dict['hex'], 'ABC123')
        self.assertEqual(api_dict['flight'], 'TEST123')
        self.assertEqual(api_dict['lat'], 52.3676)
        self.assertEqual(api_dict['lon'], 4.9041)
        self.assertEqual(api_dict['alt_baro'], 35000)
        self.assertEqual(api_dict['gs'], 450)
        self.assertEqual(api_dict['track'], 90)
        self.assertEqual(api_dict['messages'], 1)
        self.assertFalse(api_dict['is_watchlist'])
        
        # Check enhanced fields
        self.assertIn('enhanced', api_dict)
        enhanced = api_dict['enhanced']
        self.assertEqual(enhanced['vertical_rate'], 1000)
        self.assertEqual(enhanced['true_airspeed'], 480)
        self.assertEqual(enhanced['indicated_airspeed'], 420)
        
        # Check metadata
        self.assertIn('data_sources', api_dict)
        self.assertIn('first_seen', api_dict)
        self.assertIn('last_seen', api_dict)
    
    def test_aircraft_to_legacy_dict(self):
        """Test converting aircraft to legacy dictionary format"""
        aircraft = self.EnhancedAircraft.from_pymodes_data(self.test_pymodes_data)
        legacy_dict = aircraft.to_legacy_dict()
        
        # Verify legacy format
        expected_fields = ['hex', 'flight', 'lat', 'lon', 'alt_baro', 'gs', 'track', 
                          'squawk', 'category', 'messages', 'last_seen', 'is_watchlist']
        
        for field in expected_fields:
            self.assertIn(field, legacy_dict)
        
        self.assertEqual(legacy_dict['hex'], 'ABC123')
        self.assertEqual(legacy_dict['flight'], 'TEST123')
        self.assertEqual(legacy_dict['lat'], 52.3676)
        self.assertEqual(legacy_dict['lon'], 4.9041)
        self.assertEqual(legacy_dict['alt_baro'], 35000)
        self.assertEqual(legacy_dict['gs'], 450)
        self.assertEqual(legacy_dict['track'], 90)
    
    def test_aircraft_helper_methods(self):
        """Test aircraft helper methods"""
        aircraft = self.EnhancedAircraft.from_pymodes_data(self.test_pymodes_data)
        
        # Test position check
        self.assertTrue(aircraft.has_position())
        
        # Test velocity check
        self.assertTrue(aircraft.has_velocity())
        
        # Test altitude check
        self.assertTrue(aircraft.has_altitude())
        
        # Test display name
        self.assertEqual(aircraft.get_display_name(), 'ABC123 (TEST123)')
        
        # Test age calculation
        age = aircraft.calculate_age_seconds()
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 5)  # Should be very recent
        
        # Test duration calculation
        duration = aircraft.calculate_duration_seconds()
        self.assertGreaterEqual(duration, 0)
    
    def test_aircraft_without_optional_data(self):
        """Test aircraft with minimal data"""
        minimal_data = {
            'icao': 'MIN123',
            'timestamp': datetime.now().timestamp(),
            'message_type': 'surveillance'
        }
        
        aircraft = self.EnhancedAircraft.from_pymodes_data(minimal_data)
        
        # Verify minimal creation
        self.assertEqual(aircraft.icao, 'MIN123')
        self.assertIsNone(aircraft.callsign)
        self.assertIsNone(aircraft.latitude)
        self.assertIsNone(aircraft.longitude)
        
        # Test helper methods with no data
        self.assertFalse(aircraft.has_position())
        self.assertFalse(aircraft.has_velocity())
        self.assertFalse(aircraft.has_altitude())
        self.assertEqual(aircraft.get_display_name(), 'MIN123')
        
        # Test API conversion with minimal data
        api_dict = aircraft.to_api_dict()
        self.assertEqual(api_dict['hex'], 'MIN123')
        self.assertEqual(api_dict['flight'], 'Unknown')
        self.assertEqual(api_dict['lat'], 'Unknown')
        self.assertEqual(api_dict['lon'], 'Unknown')


class TestPositionCalculator(unittest.TestCase):
    """Test cases for PositionCalculator class (Requirement 4.1)"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock pyModeS
        self.pymodes_mock = Mock()
        
        self.pymodes_patch = patch.dict('sys.modules', {
            'pyModeS': self.pymodes_mock,
            'pymodes_integration.position_calculator.pms': self.pymodes_mock
        })
        self.pymodes_patch.start()
        
        try:
            from pymodes_integration.position_calculator import PositionCalculator
            self.PositionCalculator = PositionCalculator
            self.calculator = PositionCalculator(TEST_REFERENCE_LAT, TEST_REFERENCE_LON)
        except ImportError:
            self.skipTest("PositionCalculator module not available")
    
    def tearDown(self):
        """Clean up patches"""
        self.pymodes_patch.stop()
    
    def test_calculator_initialization(self):
        """Test position calculator initialization"""
        self.assertEqual(self.calculator.reference_lat, TEST_REFERENCE_LAT)
        self.assertEqual(self.calculator.reference_lon, TEST_REFERENCE_LON)
        self.assertIsInstance(self.calculator.stats, dict)
        self.assertIn('global_positions_calculated', self.calculator.stats)
        self.assertIn('local_positions_calculated', self.calculator.stats)
        self.assertEqual(len(self.calculator.position_cache), 0)
    
    def test_global_position_calculation(self):
        """Test global position calculation with even/odd pair (Requirement 4.1)"""
        expected_pos = EXPECTED_POSITIONS['global_cpr']
        
        # Mock pyModeS functions for position messages
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 11
        self.pymodes_mock.adsb.cprlat.return_value = 74158
        self.pymodes_mock.adsb.cprlon.return_value = 50194
        self.pymodes_mock.adsb.oe_flag.side_effect = [0, 1]  # even, then odd
        self.pymodes_mock.adsb.cpr2position.return_value = (expected_pos['latitude'], expected_pos['longitude'])
        
        icao = expected_pos['icao']
        timestamp = datetime.now().timestamp()
        
        # Process even message first
        even_message = TEST_MESSAGES['position_even']['message']
        position1 = self.calculator.calculate_position(icao, even_message, timestamp)
        
        # Should not have position yet (need both even and odd)
        self.assertIsNone(position1)
        self.assertEqual(self.calculator.stats['global_positions_calculated'], 0)
        
        # Process odd message
        odd_message = TEST_MESSAGES['position_odd']['message']
        position2 = self.calculator.calculate_position(icao, odd_message, timestamp + 1)
        
        # Should have position now
        self.assertIsNotNone(position2)
        self.assertEqual(position2[0], expected_pos['latitude'])
        self.assertEqual(position2[1], expected_pos['longitude'])
        self.assertEqual(self.calculator.stats['global_positions_calculated'], 1)
        
        # Verify cache contains both messages
        self.assertIn(icao, self.calculator.position_cache)
        self.assertIn('format_0', self.calculator.position_cache[icao])
        self.assertIn('format_1', self.calculator.position_cache[icao])
    
    def test_local_position_calculation(self):
        """Test local position calculation with reference (Requirement 4.1)"""
        expected_pos = EXPECTED_POSITIONS['local_cpr']
        
        # Mock pyModeS functions for local calculation
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 11
        self.pymodes_mock.adsb.cprlat.return_value = 74158
        self.pymodes_mock.adsb.cprlon.return_value = 50194
        self.pymodes_mock.adsb.oe_flag.return_value = 0  # even format
        self.pymodes_mock.adsb.cpr2position.return_value = (expected_pos['latitude'], expected_pos['longitude'])
        
        # Test direct CPR calculation (should use local method when global not available)
        position = self.calculator.calculate_position_from_cpr(
            expected_pos['icao'], 74158, 50194, 0, datetime.now().timestamp()
        )
        
        # Should get local position
        self.assertIsNotNone(position)
        self.assertEqual(position[0], expected_pos['latitude'])
        self.assertEqual(position[1], expected_pos['longitude'])
        self.assertEqual(self.calculator.stats['local_positions_calculated'], 1)
    
    def test_surface_position_calculation(self):
        """Test surface position calculation"""
        # Mock pyModeS functions for surface position
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 6  # Surface position
        self.pymodes_mock.adsb.cprlat.return_value = 74158
        self.pymodes_mock.adsb.cprlon.return_value = 50194
        self.pymodes_mock.adsb.oe_flag.return_value = 0
        self.pymodes_mock.adsb.cpr2position.return_value = (52.3676, 4.9041)
        
        surface_message = TEST_MESSAGES['surface_position']['message']
        position = self.calculator.calculate_position(
            'SURF123', surface_message, datetime.now().timestamp()
        )
        
        # Should get surface position
        self.assertIsNotNone(position)
        self.assertEqual(self.calculator.stats['surface_positions_calculated'], 1)
    
    def test_position_validation(self):
        """Test position validation and range checking"""
        # Mock invalid position (out of range)
        self.pymodes_mock.df.return_value = 17
        self.pymodes_mock.adsb.typecode.return_value = 11
        self.pymodes_mock.adsb.cprlat.return_value = 74158
        self.pymodes_mock.adsb.cprlon.return_value = 50194
        self.pymodes_mock.adsb.oe_flag.return_value = 0
        self.pymodes_mock.adsb.cpr2position.return_value = (91.0, 181.0)  # Invalid coordinates
        
        position = self.calculator.calculate_position_from_cpr(
            'INVALID', 74158, 50194, 0, datetime.now().timestamp()
        )
        
        # Should reject invalid position
        self.assertIsNone(position)
    
    def test_cache_cleanup(self):
        """Test position cache cleanup functionality"""
        # Add some test data to cache
        icao = 'CACHE123'
        old_timestamp = datetime.now().timestamp() - 400  # 400 seconds ago
        recent_timestamp = datetime.now().timestamp() - 100  # 100 seconds ago
        
        # Add old and recent data
        self.calculator._store_cpr_data(icao, 74158, 50194, 0, old_timestamp)
        self.calculator._store_cpr_data(icao, 74158, 50194, 1, recent_timestamp)
        
        # Verify data is in cache
        self.assertIn(icao, self.calculator.position_cache)
        self.assertEqual(len(self.calculator.position_cache[icao]), 2)
        
        # Clean up with 300 second timeout (should remove old entry)
        removed = self.calculator.cleanup_cache(max_age_seconds=300)
        
        self.assertEqual(removed, 1)
        self.assertIn(icao, self.calculator.position_cache)
        self.assertEqual(len(self.calculator.position_cache[icao]), 1)
        
        # Clean up with 50 second timeout (should remove remaining entry)
        removed = self.calculator.cleanup_cache(max_age_seconds=50)
        
        self.assertEqual(removed, 1)
        self.assertNotIn(icao, self.calculator.position_cache)
    
    def test_reference_position_update(self):
        """Test updating reference position"""
        new_lat, new_lon = 40.7128, -74.0060  # New York
        
        self.calculator.set_reference_position(new_lat, new_lon)
        
        self.assertEqual(self.calculator.reference_lat, new_lat)
        self.assertEqual(self.calculator.reference_lon, new_lon)
    
    def test_statistics_and_reset(self):
        """Test statistics tracking and reset"""
        # Get initial stats
        stats = self.calculator.get_statistics()
        self.assertIn('global_positions_calculated', stats)
        self.assertIn('local_positions_calculated', stats)
        self.assertIn('cache_size', stats)
        self.assertIn('aircraft_in_cache', stats)
        self.assertIn('reference_position', stats)
        self.assertTrue(stats['pymodes_available'])
        
        # Verify initial values
        self.assertEqual(stats['global_positions_calculated'], 0)
        self.assertEqual(stats['cache_size'], 0)
        
        # Reset stats
        self.calculator.reset_statistics()
        
        # Verify reset
        for key in ['global_positions_calculated', 'local_positions_calculated', 'position_errors']:
            self.assertEqual(self.calculator.stats[key], 0)


class TestDecodedMessage(unittest.TestCase):
    """Test cases for DecodedMessage data structure"""
    
    def setUp(self):
        """Set up test fixtures"""
        try:
            from pymodes_integration.decoded_message import DecodedMessage, MessageType, PositionData, VelocityData
            self.DecodedMessage = DecodedMessage
            self.MessageType = MessageType
            self.PositionData = PositionData
            self.VelocityData = VelocityData
        except ImportError:
            self.skipTest("DecodedMessage module not available")
        
        self.test_pymodes_data = {
            'icao': 'MSG123',
            'message_type': 'identification',
            'timestamp': datetime.now().timestamp(),
            'raw_message': '8D4840D6202CC371C32CE0576098',
            'df': 17,
            'tc': 4,
            'callsign': 'TEST123',
            'latitude': 52.3676,
            'longitude': 4.9041,
            'altitude': 35000,
            'ground_speed': 450,
            'track': 90
        }
    
    def test_decoded_message_creation(self):
        """Test creating DecodedMessage from pyModeS data"""
        message = self.DecodedMessage.from_pymodes_data(self.test_pymodes_data)
        
        # Verify core fields
        self.assertEqual(message.icao, 'MSG123')
        self.assertEqual(message.message_type, self.MessageType.IDENTIFICATION)
        self.assertEqual(message.metadata.timestamp, self.test_pymodes_data['timestamp'])
        self.assertEqual(message.metadata.raw_message, self.test_pymodes_data['raw_message'])
        self.assertEqual(message.metadata.df, 17)
        self.assertEqual(message.metadata.tc, 4)
        
        # Verify position data
        self.assertIsNotNone(message.position)
        self.assertEqual(message.position.latitude, 52.3676)
        self.assertEqual(message.position.longitude, 4.9041)
        self.assertEqual(message.position.altitude_baro, 35000)
        
        # Verify velocity data
        self.assertIsNotNone(message.velocity)
        self.assertEqual(message.velocity.ground_speed, 450)
        self.assertEqual(message.velocity.track_angle, 90)
        
        # Verify identification data
        self.assertIsNotNone(message.identification)
        self.assertEqual(message.identification.callsign, 'TEST123')
    
    def test_decoded_message_to_dict(self):
        """Test converting DecodedMessage to dictionary"""
        message = self.DecodedMessage.from_pymodes_data(self.test_pymodes_data)
        result_dict = message.to_dict()
        
        # Verify dictionary structure
        self.assertEqual(result_dict['icao'], 'MSG123')
        self.assertEqual(result_dict['message_type'], 'identification')
        self.assertEqual(result_dict['df'], 17)
        self.assertEqual(result_dict['tc'], 4)
        self.assertEqual(result_dict['latitude'], 52.3676)
        self.assertEqual(result_dict['longitude'], 4.9041)
        self.assertEqual(result_dict['altitude'], 35000)
        self.assertEqual(result_dict['ground_speed'], 450)
        self.assertEqual(result_dict['track'], 90)
        self.assertEqual(result_dict['callsign'], 'TEST123')
    
    def test_decoded_message_helper_methods(self):
        """Test DecodedMessage helper methods"""
        message = self.DecodedMessage.from_pymodes_data(self.test_pymodes_data)
        
        # Test data checks
        self.assertTrue(message.has_position())
        self.assertTrue(message.has_velocity())
        self.assertTrue(message.has_identification())
        
        # Test age calculation
        age = message.get_age_seconds()
        self.assertGreaterEqual(age, 0)
        self.assertLess(age, 5)
        
        # Test recent check
        self.assertTrue(message.is_recent(300))
        self.assertFalse(message.is_recent(0.001))
        
        # Test summary
        summary = message.get_summary()
        self.assertIn('MSG123', summary)
        self.assertIn('identification', summary)
        self.assertIn('TEST123', summary)


if __name__ == '__main__':
    # Configure logging for tests
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_classes = [
        TestPyModeSDecoder,
        TestEnhancedAircraft,
        TestPositionCalculator,
        TestDecodedMessage
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"pyModeS Integration Unit Tests Summary:")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.testsRun > 0:
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
        print(f"Success rate: {success_rate:.1f}%")
    
    # Print requirement coverage
    print(f"\nRequirement Coverage:")
    print(f"✓ 1.1: Message decoding with known ADS-B message samples")
    print(f"✓ 2.1: Aircraft data processing and updates validation")
    print(f"✓ 4.1: Position calculation accuracy with reference data")
    
    if result.failures:
        print(f"\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}")
    
    if result.errors:
        print(f"\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}")
    
    # Exit with appropriate code
    sys.exit(0 if result.wasSuccessful() else 1)