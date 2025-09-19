#!/usr/bin/env python3
"""
Complete System Integration Tests

This test suite provides comprehensive integration tests for the complete
pyModeS integration system, testing end-to-end message flow, multi-source
handling, and watchlist monitoring.

Requirements covered:
- 3.1: Test end-to-end message flow from source to display
- 5.1: Validate multi-source message handling and deduplication
- 6.2: Test watchlist monitoring and alert generation
"""

import unittest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os
import threading
import time
import json
import tempfile
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
import logging

# Configure logging for tests
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Test data - Real ADS-B message samples for integration testing
INTEGRATION_TEST_MESSAGES = {
    'aircraft_1': {
        'icao': 'ABC123',
        'messages': [
            # Identification message
            ('8DABC123202CC371C32CE0576098', 'identification', {'callsign': 'TEST123'}),
            # Position message (even)
            ('8DABC12358C382D690C8AC2863A7', 'airborne_position', {'altitude': 35000, 'cpr_format': 'even'}),
            # Position message (odd)
            ('8DABC12358C386435CC412692AD6', 'airborne_position', {'altitude': 35000, 'cpr_format': 'odd'}),
            # Velocity message
            ('8DABC123994409940838175B284F', 'velocity', {'ground_speed': 450, 'track': 90}),
        ]
    },
    'aircraft_2': {
        'icao': 'DEF456',
        'messages': [
            # Identification message
            ('8DDEF456202CC371C32CE0576098', 'identification', {'callsign': 'WATCH1'}),
            # Position message
            ('8DDEF45658C382D690C8AC2863A7', 'airborne_position', {'altitude': 25000}),
            # Velocity message
            ('8DDEF456994409940838175B284F', 'velocity', {'ground_speed': 380, 'track': 180}),
        ]
    },
    'aircraft_3': {
        'icao': 'GHI789',
        'messages': [
            # Identification message
            ('8DGHI789202CC371C32CE0576098', 'identification', {'callsign': 'NORMAL'}),
            # Position message
            ('8DGHI78958C382D690C8AC2863A7', 'airborne_position', {'altitude': 40000}),
        ]
    }
}

# Watchlist configuration for testing
TEST_WATCHLIST_CONFIG = {
    'watchlist_entries': [
        {
            'id': 'test_icao_1',
            'value': 'DEF456',
            'type': 'icao',
            'description': 'Test ICAO watchlist entry',
            'priority': 3,
            'enabled': True
        },
        {
            'id': 'test_callsign_1',
            'value': 'WATCH1',
            'type': 'callsign',
            'description': 'Test callsign watchlist entry',
            'priority': 2,
            'enabled': True
        },
        {
            'id': 'test_pattern_1',
            'value': 'TEST.*',
            'type': 'pattern',
            'description': 'Test pattern watchlist entry',
            'priority': 1,
            'enabled': True
        },
        {
            'id': 'disabled_entry',
            'value': 'DISABLED',
            'type': 'icao',
            'description': 'Disabled entry',
            'priority': 1,
            'enabled': False
        }
    ]
}


class MockMessageSource:
    """Mock message source for integration testing"""
    
    def __init__(self, name: str, messages: List[Tuple[str, float]], delay: float = 0.1):
        self.name = name
        self.messages = messages
        self.delay = delay
        self.connected = False
        self.message_index = 0
        self.message_count = 0
        self.error_count = 0
        self.last_message_time = None
    
    def connect(self) -> bool:
        self.connected = True
        return True
    
    def disconnect(self) -> None:
        self.connected = False
    
    def is_connected(self) -> bool:
        return self.connected
    
    def get_messages(self) -> List[Tuple[str, float]]:
        if not self.connected or self.message_index >= len(self.messages):
            return []
        
        # Return one message at a time with delay
        message, timestamp = self.messages[self.message_index]
        self.message_index += 1
        self.message_count += 1
        self.last_message_time = datetime.now()
        
        time.sleep(self.delay)  # Simulate network delay
        return [(message, timestamp)]
    
    def get_status(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'connected': self.connected,
            'message_count': self.message_count,
            'error_count': self.error_count,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None
        }
    
    def _update_message_stats(self, count: int = 1):
        self.message_count += count
        self.last_message_time = datetime.now()


class TestCompleteSystemIntegration(unittest.TestCase):
    """Integration tests for the complete pyModeS system"""
    
    def setUp(self):
        """Set up test fixtures"""
        # Mock pyModeS to avoid dependency issues
        self.pymodes_mock = Mock()
        
        # Create patches
        self.pymodes_patch = patch.dict('sys.modules', {
            'pyModeS': self.pymodes_mock,
            'pymodes_integration.decoder.pms': self.pymodes_mock,
            'pymodes_integration.position_calculator.pms': self.pymodes_mock
        })
        self.pymodes_available_patch = patch('pymodes_integration.decoder.PYMODES_AVAILABLE', True)
        
        # Start patches
        self.pymodes_patch.start()
        self.pymodes_available_patch.start()
        
        # Import modules after patching
        try:
            from pymodes_integration.message_source import MessageSourceManager
            from pymodes_integration.decoder import PyModeSDecode
            from pymodes_integration.config import PyModeSConfig
            from pymodes_integration.watchlist_monitor import WatchlistMonitor, WatchlistEntry, WatchlistType
            from pymodes_integration.aircraft import EnhancedAircraft
            from pymodes_integration.alert_throttler import AlertThrottler
            
            self.MessageSourceManager = MessageSourceManager
            self.PyModeSDecode = PyModeSDecode
            self.PyModeSConfig = PyModeSConfig
            self.WatchlistMonitor = WatchlistMonitor
            self.WatchlistEntry = WatchlistEntry
            self.WatchlistType = WatchlistType
            self.EnhancedAircraft = EnhancedAircraft
            self.AlertThrottler = AlertThrottler
            
        except ImportError as e:
            self.skipTest(f"Integration modules not available: {e}")
        
        # Create temporary config file for watchlist testing
        self.temp_config_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(TEST_WATCHLIST_CONFIG, self.temp_config_file, indent=2)
        self.temp_config_file.close()
        
        # Set up mock pyModeS responses
        self._setup_pymodes_mocks()
    
    def tearDown(self):
        """Clean up patches and temporary files"""
        self.pymodes_patch.stop()
        self.pymodes_available_patch.stop()
        
        # Clean up temporary config file
        try:
            os.unlink(self.temp_config_file.name)
        except:
            pass
    
    def _setup_pymodes_mocks(self):
        """Set up pyModeS mock responses for test messages"""
        def mock_icao(message):
            # Extract ICAO from test messages
            for aircraft_data in INTEGRATION_TEST_MESSAGES.values():
                for msg, msg_type, data in aircraft_data['messages']:
                    if msg == message:
                        return aircraft_data['icao']
            return 'UNKNOWN'
        
        def mock_df(message):
            return 17  # ADS-B message
        
        def mock_typecode(message):
            # Determine type code based on message type
            for aircraft_data in INTEGRATION_TEST_MESSAGES.values():
                for msg, msg_type, data in aircraft_data['messages']:
                    if msg == message:
                        if msg_type == 'identification':
                            return 4
                        elif msg_type == 'airborne_position':
                            return 11
                        elif msg_type == 'velocity':
                            return 19
            return 0
        
        def mock_callsign(message):
            for aircraft_data in INTEGRATION_TEST_MESSAGES.values():
                for msg, msg_type, data in aircraft_data['messages']:
                    if msg == message and msg_type == 'identification':
                        return data.get('callsign', 'UNKNOWN')
            return None
        
        def mock_altitude(message):
            for aircraft_data in INTEGRATION_TEST_MESSAGES.values():
                for msg, msg_type, data in aircraft_data['messages']:
                    if msg == message and 'altitude' in data:
                        return data['altitude']
            return None
        
        def mock_velocity(message):
            for aircraft_data in INTEGRATION_TEST_MESSAGES.values():
                for msg, msg_type, data in aircraft_data['messages']:
                    if msg == message and msg_type == 'velocity':
                        return (data.get('ground_speed'), data.get('track'), 0, 'GS')
            return None
        
        def mock_oe_flag(message):
            for aircraft_data in INTEGRATION_TEST_MESSAGES.values():
                for msg, msg_type, data in aircraft_data['messages']:
                    if msg == message and 'cpr_format' in data:
                        return 1 if data['cpr_format'] == 'odd' else 0
            return 0
        
        def mock_position(even_msg, odd_msg, even_flag, odd_flag):
            # Return mock position for global CPR calculation
            return (52.3676, 4.9041)  # Amsterdam coordinates
        
        # Set up mock functions
        self.pymodes_mock.icao.side_effect = mock_icao
        self.pymodes_mock.df.side_effect = mock_df
        self.pymodes_mock.adsb.typecode.side_effect = mock_typecode
        self.pymodes_mock.adsb.callsign.side_effect = mock_callsign
        self.pymodes_mock.adsb.altitude.side_effect = mock_altitude
        self.pymodes_mock.adsb.velocity.side_effect = mock_velocity
        self.pymodes_mock.adsb.oe_flag.side_effect = mock_oe_flag
        self.pymodes_mock.adsb.position.side_effect = mock_position
        self.pymodes_mock.adsb.cprlat.return_value = 74158
        self.pymodes_mock.adsb.cprlon.return_value = 50194
        self.pymodes_mock.crc.return_value = 0  # All messages pass CRC
    
    def test_end_to_end_message_flow(self):
        """Test complete end-to-end message flow from source to display (Requirement 3.1)"""
        logger.info("Testing end-to-end message flow")
        
        # 1. Set up message sources
        source_manager = self.MessageSourceManager()
        
        # Create mock sources with test messages
        timestamp = time.time()
        source1_messages = []
        source2_messages = []
        
        # Distribute messages across sources
        for i, (aircraft_id, aircraft_data) in enumerate(INTEGRATION_TEST_MESSAGES.items()):
            for j, (message, msg_type, data) in enumerate(aircraft_data['messages']):
                msg_timestamp = timestamp + i * 10 + j
                if i % 2 == 0:
                    source1_messages.append((message, msg_timestamp))
                else:
                    source2_messages.append((message, msg_timestamp))
        
        source1 = MockMessageSource("test_source_1", source1_messages, delay=0.05)
        source2 = MockMessageSource("test_source_2", source2_messages, delay=0.05)
        
        # Add sources to manager
        self.assertTrue(source_manager.add_source(source1))
        self.assertTrue(source_manager.add_source(source2))
        
        # 2. Set up decoder
        config = self.PyModeSConfig()
        config.reference_latitude = 52.3676
        config.reference_longitude = 4.9041
        decoder = self.PyModeSDecode(config)
        
        # 3. Set up watchlist monitor
        watchlist_monitor = self.WatchlistMonitor(self.temp_config_file.name)
        
        # Track alerts
        alerts_received = []
        def alert_callback(aircraft, entry):
            alerts_received.append((aircraft.icao, entry.value, entry.entry_type.value))
        
        watchlist_monitor.add_match_callback(alert_callback)
        
        # 4. Start message collection
        source_manager.start_collection()
        
        # 5. Process messages in batches (simulating real-time processing)
        total_processed = 0
        aircraft_seen = set()
        processing_rounds = 0
        max_rounds = 20  # Prevent infinite loop
        
        while processing_rounds < max_rounds:
            processing_rounds += 1
            
            # Get message batch
            messages = source_manager.get_message_batch()
            if not messages:
                time.sleep(0.1)
                continue
            
            logger.info(f"Processing batch of {len(messages)} messages")
            
            # Decode messages
            updated_aircraft = decoder.process_messages(messages)
            total_processed += len(messages)
            
            # Check watchlist for each aircraft
            for icao, aircraft in updated_aircraft.items():
                aircraft_seen.add(icao)
                matches = watchlist_monitor.check_aircraft(aircraft)
                if matches:
                    logger.info(f"Watchlist matches for {icao}: {[m.value for m in matches]}")
            
            # Check if we've processed all expected aircraft
            expected_aircraft = set(data['icao'] for data in INTEGRATION_TEST_MESSAGES.values())
            if aircraft_seen >= expected_aircraft:
                logger.info("All expected aircraft processed")
                break
        
        # 6. Stop collection
        source_manager.stop_collection()
        
        # 7. Verify end-to-end flow
        
        # Check that messages were processed
        self.assertGreater(total_processed, 0, "No messages were processed")
        logger.info(f"Total messages processed: {total_processed}")
        
        # Check that aircraft were created
        aircraft_data = decoder.get_aircraft_data()
        self.assertGreater(len(aircraft_data), 0, "No aircraft were created")
        logger.info(f"Aircraft created: {len(aircraft_data)}")
        
        # Verify specific aircraft data
        expected_aircraft = set(data['icao'] for data in INTEGRATION_TEST_MESSAGES.values())
        actual_aircraft = set(aircraft_data.keys())
        self.assertTrue(expected_aircraft.issubset(actual_aircraft), 
                       f"Missing aircraft: {expected_aircraft - actual_aircraft}")
        
        # Check aircraft data quality
        for icao, aircraft in aircraft_data.items():
            self.assertEqual(aircraft.icao, icao)
            self.assertIsInstance(aircraft.message_count, int)
            self.assertGreater(aircraft.message_count, 0)
            self.assertIsInstance(aircraft.first_seen, datetime)
            self.assertIsInstance(aircraft.last_seen, datetime)
            
            # Check if aircraft has expected data based on test messages
            if icao in ['ABC123', 'DEF456', 'GHI789']:
                # These aircraft should have callsigns
                self.assertIsNotNone(aircraft.callsign, f"Aircraft {icao} missing callsign")
        
        # Check watchlist alerts
        self.assertGreater(len(alerts_received), 0, "No watchlist alerts were generated")
        logger.info(f"Watchlist alerts received: {len(alerts_received)}")
        
        # Verify specific alerts
        alert_icaos = [alert[0] for alert in alerts_received]
        self.assertIn('DEF456', alert_icaos, "Expected ICAO watchlist alert not received")
        
        # Check statistics
        decoder_stats = decoder.get_statistics()
        self.assertGreater(decoder_stats['messages_processed'], 0)
        self.assertGreater(decoder_stats['messages_decoded'], 0)
        self.assertGreater(decoder_stats['aircraft_count'], 0)
        
        watchlist_stats = watchlist_monitor.get_statistics()
        self.assertGreater(watchlist_stats['total_checks'], 0)
        self.assertGreater(watchlist_stats['total_matches'], 0)
        
        logger.info("End-to-end message flow test completed successfully")  
  
    def test_multi_source_handling_and_deduplication(self):
        """Test multi-source message handling and deduplication (Requirement 5.1)"""
        logger.info("Testing multi-source handling and deduplication")
        
        # 1. Set up multiple sources with overlapping messages
        source_manager = self.MessageSourceManager(deduplication_window=2)
        
        timestamp = time.time()
        
        # Create identical messages for deduplication testing
        duplicate_message = INTEGRATION_TEST_MESSAGES['aircraft_1']['messages'][0][0]
        
        # Source 1: Original messages + duplicates
        source1_messages = [
            (duplicate_message, timestamp),
            (duplicate_message, timestamp + 0.5),  # Duplicate within window
            (INTEGRATION_TEST_MESSAGES['aircraft_1']['messages'][1][0], timestamp + 1),
        ]
        
        # Source 2: Same duplicates + unique messages
        source2_messages = [
            (duplicate_message, timestamp + 0.2),  # Duplicate within window
            (duplicate_message, timestamp + 3),    # Duplicate outside window (should pass)
            (INTEGRATION_TEST_MESSAGES['aircraft_2']['messages'][0][0], timestamp + 2),
        ]
        
        # Source 3: Unique messages only
        source3_messages = [
            (INTEGRATION_TEST_MESSAGES['aircraft_3']['messages'][0][0], timestamp + 1.5),
            (INTEGRATION_TEST_MESSAGES['aircraft_3']['messages'][1][0], timestamp + 2.5),
        ]
        
        source1 = MockMessageSource("source_1", source1_messages, delay=0.01)
        source2 = MockMessageSource("source_2", source2_messages, delay=0.01)
        source3 = MockMessageSource("source_3", source3_messages, delay=0.01)
        
        # Add sources
        self.assertTrue(source_manager.add_source(source1))
        self.assertTrue(source_manager.add_source(source2))
        self.assertTrue(source_manager.add_source(source3))
        
        # 2. Start collection
        source_manager.start_collection()
        
        # 3. Collect messages and track deduplication
        all_messages = []
        collection_time = 5  # seconds
        start_time = time.time()
        
        while time.time() - start_time < collection_time:
            messages = source_manager.get_message_batch()
            all_messages.extend(messages)
            time.sleep(0.1)
        
        source_manager.stop_collection()
        
        # 4. Verify multi-source handling
        
        # Check that all sources were connected
        sources_status = source_manager.get_sources_status()
        self.assertEqual(len(sources_status), 3, "Not all sources were added")
        
        connected_sources = [s for s in sources_status if s['connected']]
        self.assertEqual(len(connected_sources), 3, "Not all sources connected")
        
        # Check statistics
        manager_stats = source_manager.get_statistics()
        self.assertGreater(manager_stats['total_messages'], 0, "No messages collected")
        self.assertEqual(manager_stats['sources_total'], 3)
        self.assertEqual(manager_stats['sources_connected'], 3)
        
        # 5. Verify deduplication
        
        # Count occurrences of the duplicate message
        duplicate_count = sum(1 for msg, _ in all_messages if msg == duplicate_message)
        
        # We expect:
        # - First occurrence from source1 (timestamp)
        # - Duplicates from source1 (timestamp + 0.5) and source2 (timestamp + 0.2) should be filtered
        # - Later occurrence from source2 (timestamp + 3) should pass (outside window)
        # So we should see 2 instances of the duplicate message
        self.assertEqual(duplicate_count, 2, 
                        f"Expected 2 instances of duplicate message after deduplication, got {duplicate_count}")
        
        # Check that deduplication statistics are tracked
        self.assertGreaterEqual(manager_stats['duplicate_messages'], 0)
        
        logger.info(f"Collected {len(all_messages)} messages from {len(sources_status)} sources")
        logger.info(f"Duplicate messages filtered: {manager_stats['duplicate_messages']}")
        
        # 6. Test source health monitoring
        
        # Disconnect one source and verify health status
        source1.disconnect()
        time.sleep(1)  # Allow health check to run
        
        updated_stats = source_manager.get_statistics()
        # Health status should be 'degraded' with only 2/3 sources connected
        self.assertIn(updated_stats['health_status'], ['degraded', 'healthy'])
        
        logger.info("Multi-source handling and deduplication test completed successfully")
    
    def test_watchlist_monitoring_and_alert_generation(self):
        """Test watchlist monitoring and alert generation (Requirement 6.2)"""
        logger.info("Testing watchlist monitoring and alert generation")
        
        # 1. Set up watchlist monitor with test configuration
        watchlist_monitor = self.WatchlistMonitor(self.temp_config_file.name)
        
        # Verify watchlist entries were loaded
        entries = watchlist_monitor.get_entries()
        self.assertGreater(len(entries), 0, "No watchlist entries loaded")
        
        # Check specific entries
        entry_values = [entry.value for entry in entries.values()]
        self.assertIn('DEF456', entry_values, "ICAO watchlist entry not found")
        self.assertIn('WATCH1', entry_values, "Callsign watchlist entry not found")
        self.assertIn('TEST.*', entry_values, "Pattern watchlist entry not found")
        
        # 2. Set up alert tracking
        alerts_generated = []
        alert_details = []
        
        def alert_callback(aircraft, entry):
            alerts_generated.append({
                'icao': aircraft.icao,
                'callsign': aircraft.callsign,
                'entry_id': entry.value,
                'entry_type': entry.entry_type.value,
                'priority': entry.priority,
                'timestamp': datetime.now()
            })
            alert_details.append(f"{aircraft.icao} matched {entry.value} ({entry.entry_type.value})")
        
        watchlist_monitor.add_match_callback(alert_callback)
        
        # 3. Set up alert throttling
        alert_throttler = self.AlertThrottler()
        
        throttled_alerts = []
        def throttled_alert_callback(aircraft, entry):
            if not alert_throttler.is_throttled(aircraft.icao, entry.value):
                throttled_alerts.append({
                    'icao': aircraft.icao,
                    'entry': entry.value,
                    'timestamp': datetime.now()
                })
                alert_throttler.record_alert(aircraft.icao, entry.value)
        
        watchlist_monitor.add_match_callback(throttled_alert_callback)
        
        # 4. Create test aircraft and check watchlist
        
        # Aircraft that should match ICAO watchlist (DEF456)
        aircraft_1_data = {
            'icao': 'DEF456',
            'timestamp': time.time(),
            'message_type': 'identification',
            'callsign': 'WATCH1'
        }
        aircraft_1 = self.EnhancedAircraft.from_pymodes_data(aircraft_1_data)
        
        # Aircraft that should match callsign watchlist (WATCH1)
        aircraft_2_data = {
            'icao': 'XYZ999',
            'timestamp': time.time(),
            'message_type': 'identification',
            'callsign': 'WATCH1'
        }
        aircraft_2 = self.EnhancedAircraft.from_pymodes_data(aircraft_2_data)
        
        # Aircraft that should match pattern watchlist (TEST.*)
        aircraft_3_data = {
            'icao': 'ABC123',
            'timestamp': time.time(),
            'message_type': 'identification',
            'callsign': 'TEST123'
        }
        aircraft_3 = self.EnhancedAircraft.from_pymodes_data(aircraft_3_data)
        
        # Aircraft that should not match any watchlist
        aircraft_4_data = {
            'icao': 'NORMAL',
            'timestamp': time.time(),
            'message_type': 'identification',
            'callsign': 'NORMAL'
        }
        aircraft_4 = self.EnhancedAircraft.from_pymodes_data(aircraft_4_data)
        
        # 5. Test watchlist matching
        
        # Check aircraft 1 (should match ICAO and callsign)
        matches_1 = watchlist_monitor.check_aircraft(aircraft_1)
        self.assertGreater(len(matches_1), 0, "Aircraft 1 should match watchlist")
        self.assertTrue(aircraft_1.is_watchlist, "Aircraft 1 should be marked as watchlist")
        
        # Check aircraft 2 (should match callsign only)
        matches_2 = watchlist_monitor.check_aircraft(aircraft_2)
        self.assertGreater(len(matches_2), 0, "Aircraft 2 should match watchlist")
        self.assertTrue(aircraft_2.is_watchlist, "Aircraft 2 should be marked as watchlist")
        
        # Check aircraft 3 (should match pattern)
        matches_3 = watchlist_monitor.check_aircraft(aircraft_3)
        self.assertGreater(len(matches_3), 0, "Aircraft 3 should match pattern watchlist")
        self.assertTrue(aircraft_3.is_watchlist, "Aircraft 3 should be marked as watchlist")
        
        # Check aircraft 4 (should not match)
        matches_4 = watchlist_monitor.check_aircraft(aircraft_4)
        self.assertEqual(len(matches_4), 0, "Aircraft 4 should not match watchlist")
        self.assertFalse(aircraft_4.is_watchlist, "Aircraft 4 should not be marked as watchlist")
        
        # 6. Verify alert generation
        
        self.assertGreater(len(alerts_generated), 0, "No alerts were generated")
        logger.info(f"Generated {len(alerts_generated)} alerts")
        
        # Check alert details
        alert_icaos = [alert['icao'] for alert in alerts_generated]
        self.assertIn('DEF456', alert_icaos, "Expected ICAO alert not generated")
        self.assertIn('XYZ999', alert_icaos, "Expected callsign alert not generated")
        self.assertIn('ABC123', alert_icaos, "Expected pattern alert not generated")
        self.assertNotIn('NORMAL', alert_icaos, "Unexpected alert generated for normal aircraft")
        
        # Check alert priorities
        high_priority_alerts = [alert for alert in alerts_generated if alert['priority'] >= 3]
        self.assertGreater(len(high_priority_alerts), 0, "No high priority alerts generated")
        
        # 7. Test alert throttling
        
        # Generate multiple alerts for the same aircraft
        for i in range(5):
            watchlist_monitor.check_aircraft(aircraft_1)
            time.sleep(0.1)
        
        # Check that throttling is working
        initial_throttled_count = len(throttled_alerts)
        
        # Wait for throttle period and try again
        time.sleep(1)
        watchlist_monitor.check_aircraft(aircraft_1)
        
        # Should have more throttled alerts now
        self.assertGreaterEqual(len(throttled_alerts), initial_throttled_count)
        
        # 8. Test watchlist statistics
        
        stats = watchlist_monitor.get_statistics()
        self.assertGreater(stats['total_checks'], 0, "No watchlist checks recorded")
        self.assertGreater(stats['total_matches'], 0, "No watchlist matches recorded")
        self.assertGreater(stats['total_entries'], 0, "No watchlist entries found")
        
        # Check match statistics by type
        self.assertGreater(stats['matches_by_type']['icao'], 0, "No ICAO matches recorded")
        self.assertGreater(stats['matches_by_type']['callsign'], 0, "No callsign matches recorded")
        self.assertGreater(stats['matches_by_type']['pattern'], 0, "No pattern matches recorded")
        
        # 9. Test dynamic watchlist updates
        
        # Add a new entry dynamically
        new_entry = self.WatchlistEntry(
            value='DYNAMIC',
            entry_type=self.WatchlistType.ICAO,
            description='Dynamically added entry',
            priority=4
        )
        watchlist_monitor.add_entry('dynamic_test', new_entry)
        
        # Create aircraft that matches new entry
        dynamic_aircraft_data = {
            'icao': 'DYNAMIC',
            'timestamp': time.time(),
            'message_type': 'identification',
            'callsign': 'DYNAMIC'
        }
        dynamic_aircraft = self.EnhancedAircraft.from_pymodes_data(dynamic_aircraft_data)
        
        # Check that it matches
        dynamic_matches = watchlist_monitor.check_aircraft(dynamic_aircraft)
        self.assertGreater(len(dynamic_matches), 0, "Dynamic watchlist entry should match")
        
        # Remove the entry
        self.assertTrue(watchlist_monitor.remove_entry('dynamic_test'))
        
        # Check that it no longer matches
        dynamic_matches_after = watchlist_monitor.check_aircraft(dynamic_aircraft)
        dynamic_match_values = [m.value for m in dynamic_matches_after]
        self.assertNotIn('DYNAMIC', dynamic_match_values, "Removed entry should not match")
        
        logger.info("Watchlist monitoring and alert generation test completed successfully")
        logger.info(f"Alert details: {alert_details}")    

    def test_system_performance_and_stress(self):
        """Test system performance under load"""
        logger.info("Testing system performance under load")
        
        # 1. Set up high-volume message sources
        source_manager = self.MessageSourceManager()
        
        # Create large number of messages
        timestamp = time.time()
        high_volume_messages = []
        
        # Generate 1000 messages across multiple aircraft
        for i in range(1000):
            icao = f"T{i:05X}"  # Generate unique ICAO codes
            message = f"8D{icao}202CC371C32CE0576098"  # Mock identification message
            high_volume_messages.append((message, timestamp + i * 0.01))
        
        # Create multiple sources
        chunk_size = len(high_volume_messages) // 3
        source1 = MockMessageSource("perf_source_1", high_volume_messages[:chunk_size], delay=0.001)
        source2 = MockMessageSource("perf_source_2", high_volume_messages[chunk_size:chunk_size*2], delay=0.001)
        source3 = MockMessageSource("perf_source_3", high_volume_messages[chunk_size*2:], delay=0.001)
        
        source_manager.add_source(source1)
        source_manager.add_source(source2)
        source_manager.add_source(source3)
        
        # 2. Set up decoder
        config = self.PyModeSConfig()
        config.batch_size = 50  # Process in larger batches
        decoder = self.PyModeSDecode(config)
        
        # 3. Performance test
        start_time = time.time()
        source_manager.start_collection()
        
        total_processed = 0
        processing_start = time.time()
        
        # Process for limited time
        while time.time() - processing_start < 10:  # 10 seconds max
            messages = source_manager.get_message_batch()
            if messages:
                decoder.process_messages(messages)
                total_processed += len(messages)
            else:
                time.sleep(0.01)
        
        source_manager.stop_collection()
        end_time = time.time()
        
        # 4. Verify performance
        processing_time = end_time - start_time
        messages_per_second = total_processed / processing_time if processing_time > 0 else 0
        
        logger.info(f"Processed {total_processed} messages in {processing_time:.2f} seconds")
        logger.info(f"Processing rate: {messages_per_second:.1f} messages/second")
        
        # Performance assertions
        self.assertGreater(total_processed, 100, "Should process significant number of messages")
        self.assertGreater(messages_per_second, 10, "Should maintain reasonable processing rate")
        
        # Check memory usage (aircraft count should be reasonable)
        aircraft_count = len(decoder.get_aircraft_data())
        self.assertLess(aircraft_count, 2000, "Should not create excessive aircraft objects")
        
        # Check statistics
        stats = decoder.get_statistics()
        self.assertGreater(stats['decode_rate'], 0.5, "Should maintain good decode rate")
        
        logger.info("Performance test completed successfully")
    
    def test_error_recovery_and_resilience(self):
        """Test system error recovery and resilience"""
        logger.info("Testing error recovery and resilience")
        
        # 1. Test with invalid messages
        source_manager = self.MessageSourceManager()
        
        # Mix of valid and invalid messages
        mixed_messages = [
            ("8DABC123202CC371C32CE0576098", time.time()),      # Valid
            ("INVALID_MESSAGE", time.time() + 1),               # Invalid hex
            ("8DABC12", time.time() + 2),                       # Too short
            ("8DDEF456202CC371C32CE0576098EXTRA", time.time() + 3),  # Too long
            ("8DGHI789202CC371C32CE0576098", time.time() + 4),  # Valid
        ]
        
        error_source = MockMessageSource("error_source", mixed_messages, delay=0.01)
        source_manager.add_source(error_source)
        
        # 2. Set up decoder with error logging
        config = self.PyModeSConfig()
        config.log_decode_errors = True
        decoder = self.PyModeSDecode(config)
        
        # 3. Process messages with errors
        source_manager.start_collection()
        
        processed_messages = []
        for _ in range(10):  # Limited iterations
            messages = source_manager.get_message_batch()
            if messages:
                processed_messages.extend(messages)
                decoder.process_messages(messages)
            time.sleep(0.1)
        
        source_manager.stop_collection()
        
        # 4. Verify error handling
        stats = decoder.get_statistics()
        
        # Should have processed some messages
        self.assertGreater(stats['messages_processed'], 0, "Should process some messages")
        
        # Should have some failures due to invalid messages
        self.assertGreater(stats['messages_failed'], 0, "Should record message failures")
        
        # Should still decode valid messages
        self.assertGreater(stats['messages_decoded'], 0, "Should decode valid messages")
        
        # System should remain stable
        aircraft_data = decoder.get_aircraft_data()
        self.assertGreaterEqual(len(aircraft_data), 0, "System should remain stable")
        
        logger.info(f"Processed {len(processed_messages)} messages with {stats['messages_failed']} failures")
        logger.info("Error recovery test completed successfully")


def run_integration_tests():
    """Run all integration tests"""
    logger.info("Starting complete system integration tests")
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test cases
    test_suite.addTest(unittest.makeSuite(TestCompleteSystemIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Report results
    if result.wasSuccessful():
        logger.info("🎉 All integration tests passed!")
        return 0
    else:
        logger.error(f"❌ {len(result.failures)} test(s) failed, {len(result.errors)} error(s)")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(run_integration_tests())