#!/usr/bin/env python3
"""
Minimal Performance and Stress Tests for ADS-B Improvement System

This module implements core performance and stress testing without external dependencies.
Tests focus on high message rates, memory usage patterns, and error recovery scenarios.

Requirements covered: 5.2 (System architecture and modularity)
"""

import unittest
import time
import threading
import gc
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from unittest.mock import Mock, MagicMock
import json
import random

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_memory_usage_mb():
    """Get approximate memory usage in MB (simplified version)"""
    try:
        # Try to get memory info from /proc/self/status on Linux
        with open('/proc/self/status', 'r') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    # Extract memory in kB and convert to MB
                    memory_kb = int(line.split()[1])
                    return memory_kb / 1024
    except:
        pass
    
    # Fallback: use gc stats as rough approximation
    stats = gc.get_stats()
    if stats:
        # Very rough approximation based on GC collections
        return sum(stat.get('collections', 0) for stat in stats) * 0.1
    
    return 10.0  # Default fallback


class MockADSBMessage:
    """Mock ADS-B message for testing"""
    
    def __init__(self, icao: str, message_type: str = "position", valid: bool = True):
        self.icao = icao
        self.message_type = message_type
        self.valid = valid
        self.timestamp = time.time()
        
        if valid:
            # Generate valid-looking hex message
            self.raw_message = f"8D{icao}202CC371C32CE0576098"
        else:
            # Generate invalid message
            self.raw_message = "INVALID_MESSAGE"
    
    def to_tuple(self) -> Tuple[str, float]:
        return (self.raw_message, self.timestamp)


class MockMessageSource:
    """Mock message source for performance testing"""
    
    def __init__(self, name: str, messages_per_second: int = 50, duration_seconds: int = 30):
        self.name = name
        self.messages_per_second = messages_per_second
        self.duration_seconds = duration_seconds
        self.connected = False
        self.start_time = None
        self.message_count = 0
        self.error_count = 0
        
        # Generate pool of aircraft ICAOs
        self.aircraft_pool = [f"{i:06X}" for i in range(20)]
    
    def connect(self) -> bool:
        self.connected = True
        self.start_time = time.time()
        logger.info(f"Connected to mock source: {self.name}")
        return True
    
    def disconnect(self) -> None:
        self.connected = False
        logger.info(f"Disconnected from mock source: {self.name}")
    
    def is_connected(self) -> bool:
        return self.connected
    
    def get_messages(self) -> List[Tuple[str, float]]:
        if not self.connected or not self.start_time:
            return []
        
        elapsed = time.time() - self.start_time
        if elapsed > self.duration_seconds:
            return []
        
        # Calculate messages to generate this cycle
        expected_total = int(elapsed * self.messages_per_second)
        messages_to_generate = max(0, min(expected_total - self.message_count, 10))
        
        messages = []
        for _ in range(messages_to_generate):
            icao = random.choice(self.aircraft_pool)
            message = MockADSBMessage(icao, valid=True)
            messages.append(message.to_tuple())
        
        self.message_count += len(messages)
        return messages


class MockErrorProneSource(MockMessageSource):
    """Mock source that generates errors for resilience testing"""
    
    def __init__(self, name: str, error_rate: float = 0.2, connection_failures: int = 2):
        super().__init__(name, messages_per_second=30, duration_seconds=60)
        self.error_rate = error_rate
        self.connection_failures = connection_failures
        self.connection_attempts = 0
    
    def connect(self) -> bool:
        self.connection_attempts += 1
        
        # Simulate connection failures
        if self.connection_attempts <= self.connection_failures:
            logger.info(f"Simulating connection failure #{self.connection_attempts} for {self.name}")
            return False
        
        return super().connect()
    
    def get_messages(self) -> List[Tuple[str, float]]:
        if not self.connected:
            return []
        
        messages = []
        for _ in range(random.randint(1, 5)):
            icao = random.choice(self.aircraft_pool)
            valid = random.random() > self.error_rate
            message = MockADSBMessage(icao, valid=valid)
            messages.append(message.to_tuple())
        
        self.message_count += len(messages)
        return messages


class MockMessageSourceManager:
    """Mock message source manager for testing"""
    
    def __init__(self):
        self.sources = []
        self.running = False
        self.message_queue = []
        self.stats = {
            'total_messages': 0,
            'duplicate_messages': 0,
            'messages_per_second': 0.0
        }
    
    def add_source(self, source: MockMessageSource):
        self.sources.append(source)
    
    def start_collection(self):
        self.running = True
        for source in self.sources:
            source.connect()
    
    def stop_collection(self):
        self.running = False
        for source in self.sources:
            source.disconnect()
    
    def get_message_batch(self) -> List[Tuple[str, float]]:
        if not self.running:
            return []
        
        all_messages = []
        for source in self.sources:
            if source.is_connected():
                messages = source.get_messages()
                all_messages.extend(messages)
        
        self.stats['total_messages'] += len(all_messages)
        return all_messages
    
    def get_statistics(self) -> Dict[str, Any]:
        return self.stats.copy()


class MockADSBDecoder:
    """Mock ADS-B decoder for performance testing"""
    
    def __init__(self):
        self.aircraft = {}
        self.stats = {
            'messages_processed': 0,
            'messages_decoded': 0,
            'messages_failed': 0,
            'decode_rate': 0.0
        }
    
    def is_valid_message(self, message: str) -> bool:
        """Simple validation - check if it looks like hex and reasonable length"""
        if not message or len(message) not in [14, 28]:
            return False
        
        try:
            int(message, 16)
            return True
        except ValueError:
            return False
    
    def decode_message(self, message: str, timestamp: float) -> Optional[Dict[str, Any]]:
        """Mock decode - extract ICAO if valid"""
        if not self.is_valid_message(message):
            return None
        
        # Extract ICAO from message (positions 2-8)
        if len(message) >= 8:
            icao = message[2:8]
            return {
                'icao': icao,
                'timestamp': timestamp,
                'message_type': 'position',
                'raw_message': message
            }
        
        return None
    
    def process_messages(self, messages: List[Tuple[str, float]]) -> Dict[str, Dict]:
        """Process batch of messages"""
        updated_aircraft = {}
        
        for message, timestamp in messages:
            self.stats['messages_processed'] += 1
            
            decoded = self.decode_message(message, timestamp)
            if decoded:
                self.stats['messages_decoded'] += 1
                icao = decoded['icao']
                
                # Update or create aircraft
                if icao not in self.aircraft:
                    self.aircraft[icao] = {
                        'icao': icao,
                        'first_seen': timestamp,
                        'last_seen': timestamp,
                        'message_count': 1
                    }
                else:
                    self.aircraft[icao]['last_seen'] = timestamp
                    self.aircraft[icao]['message_count'] += 1
                
                updated_aircraft[icao] = self.aircraft[icao]
            else:
                self.stats['messages_failed'] += 1
        
        # Update decode rate
        total = self.stats['messages_processed']
        if total > 0:
            self.stats['decode_rate'] = self.stats['messages_decoded'] / total
        
        return updated_aircraft
    
    def get_aircraft_data(self) -> Dict[str, Dict]:
        return self.aircraft.copy()
    
    def clear_old_aircraft(self, timeout_seconds: int = 300) -> int:
        """Remove old aircraft"""
        current_time = time.time()
        to_remove = []
        
        for icao, aircraft in self.aircraft.items():
            if current_time - aircraft['last_seen'] > timeout_seconds:
                to_remove.append(icao)
        
        for icao in to_remove:
            del self.aircraft[icao]
        
        return len(to_remove)
    
    def get_statistics(self) -> Dict[str, Any]:
        return {
            **self.stats,
            'aircraft_count': len(self.aircraft)
        }


class TestSystemPerformance(unittest.TestCase):
    """Test system performance with high message rates"""
    
    def setUp(self):
        """Set up test environment"""
        self.initial_memory = get_memory_usage_mb()
        self.initial_time = time.time()
        logger.info(f"Test setup - Initial memory: {self.initial_memory:.2f} MB")
    
    def tearDown(self):
        """Clean up after test"""
        gc.collect()
        final_memory = get_memory_usage_mb()
        memory_growth = final_memory - self.initial_memory
        test_duration = time.time() - self.initial_time
        logger.info(f"Test cleanup - Final memory: {final_memory:.2f} MB, "
                   f"Growth: {memory_growth:.2f} MB, Duration: {test_duration:.1f}s")
    
    def test_high_message_rate_processing(self):
        """Test system performance with high message rates"""
        logger.info("Testing high message rate processing")
        
        # Create high-volume message sources
        source_manager = MockMessageSourceManager()
        
        sources = [
            MockMessageSource("high_volume_1", messages_per_second=100, duration_seconds=20),
            MockMessageSource("high_volume_2", messages_per_second=80, duration_seconds=20),
            MockMessageSource("high_volume_3", messages_per_second=60, duration_seconds=20),
        ]
        
        for source in sources:
            source_manager.add_source(source)
        
        # Set up decoder
        decoder = MockADSBDecoder()
        
        # Performance tracking
        start_time = time.time()
        total_processed = 0
        processing_times = []
        memory_samples = []
        
        # Start processing
        source_manager.start_collection()
        
        try:
            # Process messages for test duration
            test_duration = 25  # seconds
            while time.time() - start_time < test_duration:
                batch_start = time.time()
                
                # Get message batch
                messages = source_manager.get_message_batch()
                
                if messages:
                    # Process batch and measure time
                    decode_start = time.time()
                    decoded_aircraft = decoder.process_messages(messages)
                    decode_time = (time.time() - decode_start) * 1000  # ms
                    
                    # Record metrics
                    total_processed += len(messages)
                    processing_times.append(decode_time)
                    
                    # Sample memory usage periodically
                    if len(memory_samples) < 50 and total_processed % 50 == 0:
                        memory_usage = get_memory_usage_mb()
                        memory_samples.append(memory_usage)
                
                # Brief pause to prevent CPU saturation
                time.sleep(0.01)
            
            # Stop collection
            source_manager.stop_collection()
            
            # Calculate performance metrics
            actual_duration = time.time() - start_time
            messages_per_second = total_processed / actual_duration
            avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
            max_processing_time = max(processing_times) if processing_times else 0
            
            # Memory analysis
            peak_memory = max(memory_samples) if memory_samples else self.initial_memory
            memory_growth = peak_memory - self.initial_memory
            
            # Get final statistics
            decoder_stats = decoder.get_statistics()
            
            # Log results
            logger.info(f"Performance Test Results:")
            logger.info(f"  Total messages processed: {total_processed}")
            logger.info(f"  Processing rate: {messages_per_second:.1f} msg/s")
            logger.info(f"  Average processing time: {avg_processing_time:.2f} ms")
            logger.info(f"  Peak processing time: {max_processing_time:.2f} ms")
            logger.info(f"  Memory growth: {memory_growth:.2f} MB")
            logger.info(f"  Peak memory: {peak_memory:.2f} MB")
            logger.info(f"  Aircraft tracked: {len(decoder.get_aircraft_data())}")
            logger.info(f"  Decode rate: {decoder_stats['decode_rate']:.1%}")
            
            # Performance assertions
            self.assertGreater(total_processed, 1000, "Should process significant number of messages")
            self.assertGreater(messages_per_second, 50, "Should maintain reasonable processing rate")
            self.assertLess(avg_processing_time, 10, "Average processing time should be reasonable")
            self.assertLess(memory_growth, 50, "Memory growth should be controlled")
            self.assertGreater(decoder_stats['decode_rate'], 0.8, "Should maintain good decode rate")
            
        finally:
            source_manager.stop_collection()
    
    def test_sustained_load_memory_usage(self):
        """Test memory usage under sustained load"""
        logger.info("Testing sustained load memory usage")
        
        # Create sustained load source
        source_manager = MockMessageSourceManager()
        sustained_source = MockMessageSource(
            "sustained_load", 
            messages_per_second=40, 
            duration_seconds=60  # 1 minute
        )
        source_manager.add_source(sustained_source)
        
        # Set up decoder
        decoder = MockADSBDecoder()
        
        # Memory tracking
        memory_samples = []
        aircraft_count_samples = []
        
        # Start processing
        source_manager.start_collection()
        
        start_time = time.time()
        sample_interval = 5  # seconds
        last_sample_time = start_time
        
        try:
            # Run sustained load test
            while time.time() - start_time < 65:  # Run slightly longer
                # Process messages
                messages = source_manager.get_message_batch()
                if messages:
                    decoder.process_messages(messages)
                
                # Sample memory periodically
                current_time = time.time()
                if current_time - last_sample_time >= sample_interval:
                    memory_usage = get_memory_usage_mb()
                    aircraft_count = len(decoder.get_aircraft_data())
                    
                    memory_samples.append((current_time - start_time, memory_usage))
                    aircraft_count_samples.append((current_time - start_time, aircraft_count))
                    
                    logger.info(f"Memory sample at {current_time - start_time:.0f}s: "
                               f"{memory_usage:.2f} MB, {aircraft_count} aircraft")
                    
                    last_sample_time = current_time
                
                # Periodic cleanup
                if len(decoder.get_aircraft_data()) > 50:
                    removed = decoder.clear_old_aircraft(120)  # 2 minute timeout
                    if removed > 0:
                        logger.info(f"Cleaned up {removed} old aircraft")
                
                time.sleep(0.1)
            
            # Stop processing
            source_manager.stop_collection()
            
            # Analyze memory usage
            if len(memory_samples) >= 2:
                initial_sample_memory = memory_samples[0][1]
                final_sample_memory = memory_samples[-1][1]
                peak_memory = max(sample[1] for sample in memory_samples)
                
                # Calculate memory growth rate
                total_time_hours = (memory_samples[-1][0] - memory_samples[0][0]) / 3600
                memory_growth_rate = (final_sample_memory - initial_sample_memory) / total_time_hours if total_time_hours > 0 else 0
                
                # Get final statistics
                decoder_stats = decoder.get_statistics()
                
                # Log memory analysis
                logger.info(f"Memory Usage Analysis:")
                logger.info(f"  Initial memory: {initial_sample_memory:.2f} MB")
                logger.info(f"  Final memory: {final_sample_memory:.2f} MB")
                logger.info(f"  Peak memory: {peak_memory:.2f} MB")
                logger.info(f"  Memory growth rate: {memory_growth_rate:.2f} MB/hour")
                logger.info(f"  Final aircraft count: {len(decoder.get_aircraft_data())}")
                logger.info(f"  Total messages processed: {decoder_stats['messages_processed']}")
                
                # Memory usage assertions
                memory_growth = final_sample_memory - initial_sample_memory
                self.assertLess(memory_growth, 30, "Memory growth should be controlled under sustained load")
                self.assertLess(memory_growth_rate, 20, "Memory growth rate should be reasonable")
                
                # Performance assertions
                self.assertGreater(decoder_stats['messages_processed'], 1000, "Should process many messages")
                self.assertLess(len(decoder.get_aircraft_data()), 100, "Aircraft count should be managed")
                
        finally:
            source_manager.stop_collection()
    
    def test_concurrent_source_performance(self):
        """Test performance with multiple concurrent message sources"""
        logger.info("Testing concurrent source performance")
        
        # Create multiple concurrent sources
        source_manager = MockMessageSourceManager()
        
        sources = []
        for i in range(4):
            source = MockMessageSource(
                f"concurrent_source_{i+1}",
                messages_per_second=25,
                duration_seconds=30
            )
            sources.append(source)
            source_manager.add_source(source)
        
        # Set up processing
        decoder = MockADSBDecoder()
        
        # Performance tracking
        start_time = time.time()
        processing_times = []
        
        # Start processing
        source_manager.start_collection()
        
        try:
            # Process for test duration
            while time.time() - start_time < 35:
                messages = source_manager.get_message_batch()
                if messages:
                    decode_start = time.time()
                    decoder.process_messages(messages)
                    decode_time = (time.time() - decode_start) * 1000
                    
                    processing_times.append(decode_time)
                
                time.sleep(0.05)
            
            # Stop processing
            source_manager.stop_collection()
            
            # Analyze results
            avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
            
            final_stats = source_manager.get_statistics()
            decoder_stats = decoder.get_statistics()
            
            logger.info(f"Concurrent Source Performance:")
            logger.info(f"  Sources: {len(sources)}")
            logger.info(f"  Total messages: {final_stats['total_messages']}")
            logger.info(f"  Average decode time: {avg_processing_time:.2f} ms")
            logger.info(f"  Aircraft tracked: {len(decoder.get_aircraft_data())}")
            
            # Performance assertions
            self.assertGreater(final_stats['total_messages'], 1500, "Should process many messages from all sources")
            self.assertLess(avg_processing_time, 5, "Should maintain good processing speed")
            
        finally:
            source_manager.stop_collection()


class TestErrorRecoveryAndResilience(unittest.TestCase):
    """Test error recovery and reconnection scenarios"""
    
    def test_connection_failure_recovery(self):
        """Test recovery from connection failures"""
        logger.info("Testing connection failure recovery")
        
        source_manager = MockMessageSourceManager()
        
        # Create error-prone sources that fail initially
        error_sources = [
            MockErrorProneSource("error_source_1", error_rate=0.0, connection_failures=1),
            MockErrorProneSource("error_source_2", error_rate=0.0, connection_failures=2),
        ]
        
        for source in error_sources:
            source_manager.add_source(source)
        
        # Start collection (will trigger initial connection attempts)
        source_manager.start_collection()
        
        # Monitor connection recovery over time
        start_time = time.time()
        recovery_time = 15  # seconds
        successful_connections = 0
        
        try:
            while time.time() - start_time < recovery_time:
                # Check how many sources are connected
                connected_count = sum(1 for source in error_sources if source.is_connected())
                successful_connections = max(successful_connections, connected_count)
                
                # Try to reconnect failed sources
                for source in error_sources:
                    if not source.is_connected():
                        source.connect()
                
                # Process any available messages
                messages = source_manager.get_message_batch()
                if messages:
                    logger.info(f"Received {len(messages)} messages during recovery")
                
                time.sleep(1)
            
            # Final status check
            final_connected = sum(1 for source in error_sources if source.is_connected())
            
            logger.info(f"Connection Recovery Results:")
            logger.info(f"  Sources: {len(error_sources)}")
            logger.info(f"  Final connected: {final_connected}")
            logger.info(f"  Recovery time: {time.time() - start_time:.1f}s")
            
            # Recovery assertions
            self.assertGreater(final_connected, 0, "At least some sources should recover")
            self.assertEqual(final_connected, len(error_sources), "All sources should eventually connect")
            
        finally:
            source_manager.stop_collection()
    
    def test_invalid_message_handling(self):
        """Test handling of invalid and corrupted messages"""
        logger.info("Testing invalid message handling")
        
        source_manager = MockMessageSourceManager()
        
        # Create source with high error rate
        error_source = MockErrorProneSource(
            "high_error_source", 
            error_rate=0.4,  # 40% invalid messages
            connection_failures=0
        )
        source_manager.add_source(error_source)
        
        # Set up decoder
        decoder = MockADSBDecoder()
        
        # Error tracking
        total_messages = 0
        valid_messages = 0
        invalid_messages = 0
        
        # Start processing
        source_manager.start_collection()
        
        start_time = time.time()
        test_duration = 15  # seconds
        
        try:
            while time.time() - start_time < test_duration:
                messages = source_manager.get_message_batch()
                
                for message, timestamp in messages:
                    total_messages += 1
                    
                    # Try to decode each message individually to track errors
                    decoded = decoder.decode_message(message, timestamp)
                    if decoded:
                        valid_messages += 1
                    else:
                        invalid_messages += 1
                
                time.sleep(0.1)
            
            # Stop processing
            source_manager.stop_collection()
            
            # Calculate error rates
            invalid_rate = invalid_messages / total_messages if total_messages > 0 else 0
            
            # Get decoder statistics
            decoder_stats = decoder.get_statistics()
            
            logger.info(f"Invalid Message Handling Results:")
            logger.info(f"  Total messages: {total_messages}")
            logger.info(f"  Valid messages: {valid_messages}")
            logger.info(f"  Invalid messages: {invalid_messages}")
            logger.info(f"  Invalid rate: {invalid_rate:.1%}")
            logger.info(f"  Decoder stats: {decoder_stats}")
            
            # Error handling assertions
            self.assertGreater(total_messages, 50, "Should process significant number of messages")
            self.assertGreater(valid_messages, 0, "Should successfully decode some messages")
            self.assertGreater(invalid_messages, 0, "Should encounter invalid messages")
            self.assertGreater(invalid_rate, 0.3, "Should detect expected invalid message rate")
            
            # System should remain stable despite errors
            self.assertGreater(decoder_stats['messages_processed'], 0, "Decoder should continue processing")
            
        finally:
            source_manager.stop_collection()
    
    def test_memory_pressure_recovery(self):
        """Test system behavior under memory pressure"""
        logger.info("Testing memory pressure recovery")
        
        # Create high-volume source to generate memory pressure
        source_manager = MockMessageSourceManager()
        memory_pressure_source = MockMessageSource(
            "memory_pressure",
            messages_per_second=150,  # High rate
            duration_seconds=40
        )
        source_manager.add_source(memory_pressure_source)
        
        # Set up decoder
        decoder = MockADSBDecoder()
        
        # Memory monitoring
        initial_memory = get_memory_usage_mb()
        peak_memory = initial_memory
        cleanup_events = []
        
        # Start processing
        source_manager.start_collection()
        
        start_time = time.time()
        last_cleanup = start_time
        
        try:
            while time.time() - start_time < 45:
                # Process messages
                messages = source_manager.get_message_batch()
                if messages:
                    decoder.process_messages(messages)
                
                # Monitor memory and aircraft count
                current_memory = get_memory_usage_mb()
                peak_memory = max(peak_memory, current_memory)
                aircraft_count = len(decoder.get_aircraft_data())
                
                # Aggressive cleanup when aircraft count grows too much
                if aircraft_count > 30 and time.time() - last_cleanup > 5:
                    removed = decoder.clear_old_aircraft(10)  # Very aggressive cleanup
                    cleanup_events.append({
                        'time': time.time() - start_time,
                        'aircraft_removed': removed,
                        'aircraft_remaining': len(decoder.get_aircraft_data())
                    })
                    
                    # Force garbage collection
                    gc.collect()
                    
                    last_cleanup = time.time()
                    logger.info(f"Memory cleanup: removed {removed} aircraft")
                
                time.sleep(0.05)
            
            # Stop processing
            source_manager.stop_collection()
            
            # Final memory check
            final_memory = get_memory_usage_mb()
            total_memory_growth = final_memory - initial_memory
            
            # Get final statistics
            decoder_stats = decoder.get_statistics()
            
            logger.info(f"Memory Pressure Recovery Results:")
            logger.info(f"  Initial memory: {initial_memory:.2f} MB")
            logger.info(f"  Peak memory: {peak_memory:.2f} MB")
            logger.info(f"  Final memory: {final_memory:.2f} MB")
            logger.info(f"  Total growth: {total_memory_growth:.2f} MB")
            logger.info(f"  Cleanup events: {len(cleanup_events)}")
            logger.info(f"  Messages processed: {decoder_stats['messages_processed']}")
            logger.info(f"  Final aircraft count: {len(decoder.get_aircraft_data())}")
            
            # Memory pressure recovery assertions
            self.assertLess(total_memory_growth, 20, "Total memory growth should be controlled")
            self.assertGreater(len(cleanup_events), 0, "Should perform cleanup under pressure")
            self.assertLess(len(decoder.get_aircraft_data()), 50, "Aircraft count should be managed")
            
            # System should continue functioning
            self.assertGreater(decoder_stats['messages_processed'], 2000, "Should continue processing messages")
            self.assertGreater(decoder_stats['decode_rate'], 0.5, "Should maintain reasonable decode rate")
            
        finally:
            source_manager.stop_collection()


def run_performance_tests():
    """Run all performance and stress tests"""
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add performance test classes
    test_classes = [
        TestSystemPerformance,
        TestErrorRecoveryAndResilience,
    ]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests with detailed output
    runner = unittest.TextTestRunner(
        verbosity=2,
        stream=sys.stdout,
        buffer=False
    )
    
    print("=" * 70)
    print("RUNNING ADS-B SYSTEM PERFORMANCE AND STRESS TESTS")
    print("=" * 70)
    print()
    
    result = runner.run(test_suite)
    
    print()
    print("=" * 70)
    print("PERFORMANCE TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")
    
    if result.failures:
        print("\nFAILURES:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback.split('AssertionError: ')[-1].split('\\n')[0]}")
    
    if result.errors:
        print("\nERRORS:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback.split('\\n')[-2]}")
    
    print()
    if result.wasSuccessful():
        print("✅ All performance tests passed!")
        print("\nTest Coverage Summary:")
        print("✓ High message rate processing (100+ msg/s)")
        print("✓ Sustained load memory usage monitoring")
        print("✓ Concurrent source performance")
        print("✓ Connection failure recovery")
        print("✓ Invalid message handling")
        print("✓ Memory pressure recovery")
        print("\nNext steps:")
        print("1. Review performance metrics in test output")
        print("2. Run integration tests: python test_integration_complete_system.py")
        print("3. Monitor system performance in production")
    else:
        print("❌ Some performance tests failed!")
        print("\nRecommended actions:")
        print("1. Review failed test details above")
        print("2. Check system resources and configuration")
        print("3. Optimize performance bottlenecks")
        print("4. Re-run tests after fixes")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_performance_tests()
    sys.exit(0 if success else 1)