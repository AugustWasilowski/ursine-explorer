#!/usr/bin/env python3
"""
Performance and Stress Tests for ADS-B Improvement System

This module implements comprehensive performance and stress testing for the enhanced
ADS-B receiver system with pyModeS integration. Tests cover high message rates,
memory usage under sustained load, and error recovery scenarios.

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
from unittest.mock import Mock, MagicMock, patch
import json
import random
import string

# Simple memory monitoring without psutil
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
    
    return 0.0

# Add pymodes_integration to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pymodes_integration'))

try:
    from pymodes_integration.message_source import MessageSourceManager, MessageSource
    from pymodes_integration.decoder import PyModeSDecode
    from pymodes_integration.config import PyModeSConfig
    from pymodes_integration.aircraft import EnhancedAircraft
    from pymodes_integration.aircraft_tracker import AircraftTracker
    from pymodes_integration.watchlist_monitor import WatchlistMonitor
    from pymodes_integration.alert_throttler import AlertThrottler
    PYMODES_INTEGRATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: pyModeS integration not available: {e}")
    PYMODES_INTEGRATION_AVAILABLE = False

# Simple performance monitor for testing (without psutil dependency)
class SimplePerformanceMonitor:
    """Simplified performance monitor for testing without external dependencies"""
    
    def __init__(self, update_interval_sec: float = 1.0):
        self.update_interval_sec = update_interval_sec
        self.running = False
        self.metrics = {
            'messages_processed': 0,
            'messages_per_second': 0.0,
            'aircraft_count': 0,
            'memory_usage_mb': 0.0,
            'start_time': None
        }
        self.aircraft_count_callback = None
        self.message_queue_callback = None
    
    def start_monitoring(self):
        self.running = True
        self.metrics['start_time'] = time.time()
    
    def stop_monitoring(self):
        self.running = False
    
    def set_aircraft_count_callback(self, callback):
        self.aircraft_count_callback = callback
    
    def set_message_queue_callback(self, callback):
        self.message_queue_callback = callback
    
    def record_message_batch(self, batch_size: int, valid_count: int, processing_time_ms: float):
        self.metrics['messages_processed'] += batch_size
        if self.metrics['start_time']:
            elapsed = time.time() - self.metrics['start_time']
            if elapsed > 0:
                self.metrics['messages_per_second'] = self.metrics['messages_processed'] / elapsed
    
    def get_current_metrics(self):
        if self.aircraft_count_callback:
            self.metrics['aircraft_count'] = self.aircraft_count_callback()
        self.metrics['memory_usage_mb'] = get_memory_usage_mb()
        
        return {
            'processing': {
                'messages_processed': self.metrics['messages_processed'],
                'messages_per_second': self.metrics['messages_per_second']
            },
            'memory': {
                'current_usage_mb': self.metrics['memory_usage_mb'],
                'aircraft_database_size': self.metrics['aircraft_count']
            }
        }

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockHighVolumeMessageSource(MessageSource):
    """Mock message source that generates high volume of messages for stress testing"""
    
    def __init__(self, name: str, messages_per_second: int = 100, duration_seconds: int = 60):
        super().__init__(name)
        self.messages_per_second = messages_per_second
        self.duration_seconds = duration_seconds
        self.start_time = None
        self.message_templates = [
            "8D{icao}202CC371C32CE0576098",  # Identification
            "8D{icao}58C382D690C8AC2863A7",  # Velocity
            "8D{icao}20323DD8F82C4E0576098", # Position
            "8D{icao}99C382D690C8AC2863A7",  # Position with different format
        ]
        self.aircraft_pool = self._generate_aircraft_pool(50)  # 50 different aircraft
        
    def _generate_aircraft_pool(self, count: int) -> List[str]:
        """Generate pool of ICAO codes for testing"""
        aircraft = []
        for i in range(count):
            icao = f"{i:06X}"  # Generate hex ICAO codes
            aircraft.append(icao)
        return aircraft
    
    def connect(self) -> bool:
        self.connected = True
        self.start_time = time.time()
        logger.info(f"Connected to high volume source: {self.name} ({self.messages_per_second} msg/s)")
        return True
    
    def disconnect(self) -> None:
        self.connected = False
        logger.info(f"Disconnected from high volume source: {self.name}")
    
    def get_messages(self) -> List[Tuple[str, float]]:
        if not self.connected or not self.start_time:
            return []
        
        current_time = time.time()
        elapsed = current_time - self.start_time
        
        # Stop generating after duration
        if elapsed > self.duration_seconds:
            return []
        
        # Calculate how many messages to generate this cycle
        # Aim for consistent rate over time
        expected_total = int(elapsed * self.messages_per_second)
        actual_total = self.message_count
        messages_to_generate = max(0, expected_total - actual_total)
        
        # Limit burst size to prevent overwhelming
        messages_to_generate = min(messages_to_generate, self.messages_per_second // 10)
        
        messages = []
        for _ in range(messages_to_generate):
            # Select random aircraft and message template
            icao = random.choice(self.aircraft_pool)
            template = random.choice(self.message_templates)
            message = template.format(icao=icao)
            messages.append((message, current_time))
        
        self._update_message_stats(len(messages))
        return messages


class MockErrorProneMessageSource(MessageSource):
    """Mock message source that generates various error conditions"""
    
    def __init__(self, name: str, error_rate: float = 0.1, connection_failures: int = 3):
        super().__init__(name)
        self.error_rate = error_rate  # Fraction of messages that are invalid
        self.connection_failures = connection_failures
        self.connection_attempts = 0
        self.valid_messages = [
            "8DABC123202CC371C32CE0576098",
            "8DDEF456202CC371C32CE0576098",
            "8D123456202CC371C32CE0576098",
        ]
        self.invalid_messages = [
            "INVALID_HEX_MESSAGE",
            "8DABC12",  # Too short
            "8DDEF456202CC371C32CE0576098EXTRA",  # Too long
            "8DGHIJKL202CC371C32CE0576098",  # Invalid hex characters
            "",  # Empty message
        ]
    
    def connect(self) -> bool:
        self.connection_attempts += 1
        
        # Simulate connection failures
        if self.connection_attempts <= self.connection_failures:
            logger.info(f"Simulating connection failure #{self.connection_attempts} for {self.name}")
            return False
        
        self.connected = True
        logger.info(f"Connected to error-prone source: {self.name}")
        return True
    
    def disconnect(self) -> None:
        self.connected = False
        logger.info(f"Disconnected from error-prone source: {self.name}")
    
    def get_messages(self) -> List[Tuple[str, float]]:
        if not self.connected:
            return []
        
        messages = []
        current_time = time.time()
        
        # Generate 1-5 messages per call
        for _ in range(random.randint(1, 5)):
            if random.random() < self.error_rate:
                # Generate invalid message
                message = random.choice(self.invalid_messages)
            else:
                # Generate valid message
                message = random.choice(self.valid_messages)
            
            messages.append((message, current_time))
        
        self._update_message_stats(len(messages))
        return messages


@unittest.skipUnless(PYMODES_INTEGRATION_AVAILABLE, "pyModeS integration not available")
class TestSystemPerformance(unittest.TestCase):
    """Test system performance with high message rates"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = PyModeSConfig()
        self.config.batch_size = 100
        self.config.log_decode_errors = False  # Reduce logging overhead
        self.config.log_aircraft_updates = False
        self.config.log_message_stats = False
        
        # Track initial system state
        self.initial_memory = get_memory_usage_mb()
        self.initial_time = time.time()
        
        logger.info(f"Test setup - Initial memory: {self.initial_memory:.2f} MB")
    
    def tearDown(self):
        """Clean up after test"""
        # Force garbage collection
        gc.collect()
        
        # Log final memory usage
        final_memory = get_memory_usage_mb()
        memory_growth = final_memory - self.initial_memory
        test_duration = time.time() - self.initial_time
        
        logger.info(f"Test cleanup - Final memory: {final_memory:.2f} MB, "
                   f"Growth: {memory_growth:.2f} MB, Duration: {test_duration:.1f}s")
    
    def test_high_message_rate_processing(self):
        """Test system performance with high message rates"""
        logger.info("Testing high message rate processing")
        
        # Create high-volume message sources
        source_manager = MessageSourceManager()
        
        # Multiple sources generating different rates
        sources = [
            MockHighVolumeMessageSource("high_volume_1", messages_per_second=200, duration_seconds=30),
            MockHighVolumeMessageSource("high_volume_2", messages_per_second=150, duration_seconds=30),
            MockHighVolumeMessageSource("high_volume_3", messages_per_second=100, duration_seconds=30),
        ]
        
        for source in sources:
            source_manager.add_source(source)
        
        # Set up decoder with performance monitoring
        decoder = PyModeSDecode(self.config)
        performance_monitor = SimplePerformanceMonitor(update_interval_sec=1.0)
        
        # Set up callbacks for monitoring
        performance_monitor.set_aircraft_count_callback(lambda: len(decoder.get_aircraft_data()))
        performance_monitor.set_message_queue_callback(lambda: len(source_manager.message_queue))
        
        # Start monitoring and collection
        performance_monitor.start_monitoring()
        source_manager.start_collection()
        
        # Performance tracking
        start_time = time.time()
        total_processed = 0
        processing_times = []
        memory_samples = []
        
        try:
            # Process messages for test duration
            test_duration = 35  # seconds
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
                    
                    # Record performance metrics
                    valid_count = len(decoded_aircraft)
                    performance_monitor.record_message_batch(len(messages), valid_count, decode_time)
                    
                    # Sample memory usage periodically
                    if len(memory_samples) < 100 and total_processed % 100 == 0:
                        memory_usage = get_memory_usage_mb()
                        memory_samples.append(memory_usage)
                
                # Brief pause to prevent CPU saturation
                time.sleep(0.01)
            
            # Stop collection
            source_manager.stop_collection()
            performance_monitor.stop_monitoring()
            
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
            performance_metrics = performance_monitor.get_current_metrics()
            
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
            self.assertGreater(total_processed, 5000, "Should process significant number of messages")
            self.assertGreater(messages_per_second, 100, "Should maintain reasonable processing rate")
            self.assertLess(avg_processing_time, 50, "Average processing time should be reasonable")
            self.assertLess(memory_growth, 200, "Memory growth should be controlled")
            self.assertGreater(decoder_stats['decode_rate'], 0.8, "Should maintain good decode rate")
            
            # Performance monitoring assertions
            self.assertGreater(performance_metrics['processing']['messages_per_second'], 50)
            self.assertLess(performance_metrics['memory']['usage_percent'], 90)
            
        finally:
            # Ensure cleanup
            source_manager.stop_collection()
            performance_monitor.stop_monitoring()
    
    def test_sustained_load_memory_usage(self):
        """Test memory usage under sustained load"""
        logger.info("Testing sustained load memory usage")
        
        # Create sustained load source
        source_manager = MessageSourceManager()
        sustained_source = MockHighVolumeMessageSource(
            "sustained_load", 
            messages_per_second=50, 
            duration_seconds=120  # 2 minutes
        )
        source_manager.add_source(sustained_source)
        
        # Set up decoder and monitoring
        decoder = PyModeSDecode(self.config)
        performance_monitor = SimplePerformanceMonitor(update_interval_sec=5.0)
        
        # Memory tracking
        memory_samples = []
        aircraft_count_samples = []
        gc_count_initial = sum(gc.get_stats()[i]['collections'] for i in range(len(gc.get_stats())))
        
        # Start processing
        performance_monitor.start_monitoring()
        source_manager.start_collection()
        
        start_time = time.time()
        sample_interval = 10  # seconds
        last_sample_time = start_time
        
        try:
            # Run sustained load test
            while time.time() - start_time < 125:  # Run slightly longer than source duration
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
                if len(decoder.get_aircraft_data()) > 100:
                    removed = decoder.clear_old_aircraft(300)  # 5 minute timeout
                    if removed > 0:
                        logger.info(f"Cleaned up {removed} old aircraft")
                
                time.sleep(0.1)
            
            # Final memory sample
            final_memory = get_memory_usage_mb()
            memory_samples.append((time.time() - start_time, final_memory))
            
            # Stop processing
            source_manager.stop_collection()
            performance_monitor.stop_monitoring()
            
            # Analyze memory usage
            if len(memory_samples) >= 2:
                initial_sample_memory = memory_samples[0][1]
                final_sample_memory = memory_samples[-1][1]
                peak_memory = max(sample[1] for sample in memory_samples)
                
                # Calculate memory growth rate
                total_time_hours = (memory_samples[-1][0] - memory_samples[0][0]) / 3600
                memory_growth_rate = (final_sample_memory - initial_sample_memory) / total_time_hours if total_time_hours > 0 else 0
                
                # Garbage collection analysis
                gc_count_final = sum(gc.get_stats()[i]['collections'] for i in range(len(gc.get_stats())))
                gc_collections = gc_count_final - gc_count_initial
                
                # Get final statistics
                decoder_stats = decoder.get_statistics()
                performance_metrics = performance_monitor.get_current_metrics()
                
                # Log memory analysis
                logger.info(f"Memory Usage Analysis:")
                logger.info(f"  Initial memory: {initial_sample_memory:.2f} MB")
                logger.info(f"  Final memory: {final_sample_memory:.2f} MB")
                logger.info(f"  Peak memory: {peak_memory:.2f} MB")
                logger.info(f"  Memory growth rate: {memory_growth_rate:.2f} MB/hour")
                logger.info(f"  GC collections: {gc_collections}")
                logger.info(f"  Final aircraft count: {len(decoder.get_aircraft_data())}")
                logger.info(f"  Total messages processed: {decoder_stats['messages_processed']}")
                
                # Memory usage assertions
                memory_growth = final_sample_memory - initial_sample_memory
                self.assertLess(memory_growth, 100, "Memory growth should be controlled under sustained load")
                self.assertLess(memory_growth_rate, 50, "Memory growth rate should be reasonable")
                self.assertLess(peak_memory, self.initial_memory + 150, "Peak memory should be controlled")
                
                # Performance assertions
                self.assertGreater(decoder_stats['messages_processed'], 3000, "Should process many messages")
                self.assertLess(len(decoder.get_aircraft_data()), 200, "Aircraft count should be managed")
                
        finally:
            source_manager.stop_collection()
            performance_monitor.stop_monitoring()
    
    def test_concurrent_source_performance(self):
        """Test performance with multiple concurrent message sources"""
        logger.info("Testing concurrent source performance")
        
        # Create multiple concurrent sources
        source_manager = MessageSourceManager(max_sources=10)
        
        sources = []
        for i in range(5):
            source = MockHighVolumeMessageSource(
                f"concurrent_source_{i+1}",
                messages_per_second=30,
                duration_seconds=45
            )
            sources.append(source)
            source_manager.add_source(source)
        
        # Set up processing
        decoder = PyModeSDecode(self.config)
        performance_monitor = SimplePerformanceMonitor()
        
        # Performance tracking
        start_time = time.time()
        processing_times = []
        source_stats = []
        
        # Start processing
        performance_monitor.start_monitoring()
        source_manager.start_collection()
        
        try:
            # Process for test duration
            while time.time() - start_time < 50:
                batch_start = time.time()
                
                messages = source_manager.get_message_batch()
                if messages:
                    decode_start = time.time()
                    decoder.process_messages(messages)
                    decode_time = (time.time() - decode_start) * 1000
                    
                    processing_times.append(decode_time)
                
                # Sample source statistics
                if len(source_stats) < 20 and len(processing_times) % 50 == 0:
                    stats = source_manager.get_statistics()
                    source_stats.append(stats)
                
                time.sleep(0.05)
            
            # Stop processing
            source_manager.stop_collection()
            performance_monitor.stop_monitoring()
            
            # Analyze results
            total_duration = time.time() - start_time
            avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
            
            final_stats = source_manager.get_statistics()
            decoder_stats = decoder.get_statistics()
            
            logger.info(f"Concurrent Source Performance:")
            logger.info(f"  Sources: {len(sources)}")
            logger.info(f"  Total messages: {final_stats['total_messages']}")
            logger.info(f"  Duplicate messages: {final_stats['duplicate_messages']}")
            logger.info(f"  Processing rate: {final_stats['messages_per_second']:.1f} msg/s")
            logger.info(f"  Average decode time: {avg_processing_time:.2f} ms")
            logger.info(f"  Aircraft tracked: {len(decoder.get_aircraft_data())}")
            
            # Performance assertions
            self.assertGreater(final_stats['total_messages'], 3000, "Should process many messages from all sources")
            self.assertLess(avg_processing_time, 30, "Should maintain good processing speed")
            self.assertGreater(final_stats['messages_per_second'], 50, "Should maintain good throughput")
            self.assertLess(final_stats['duplicate_messages'] / max(final_stats['total_messages'], 1), 0.1, 
                           "Duplicate rate should be low")
            
        finally:
            source_manager.stop_collection()
            performance_monitor.stop_monitoring()


@unittest.skipUnless(PYMODES_INTEGRATION_AVAILABLE, "pyModeS integration not available")
class TestErrorRecoveryAndResilience(unittest.TestCase):
    """Test error recovery and reconnection scenarios"""
    
    def setUp(self):
        """Set up test environment"""
        self.config = PyModeSConfig()
        self.config.log_decode_errors = True  # Enable error logging for these tests
        
    def test_connection_failure_recovery(self):
        """Test recovery from connection failures"""
        logger.info("Testing connection failure recovery")
        
        source_manager = MessageSourceManager()
        
        # Create error-prone sources that fail initially
        error_sources = [
            MockErrorProneMessageSource("error_source_1", error_rate=0.0, connection_failures=2),
            MockErrorProneMessageSource("error_source_2", error_rate=0.0, connection_failures=3),
            MockErrorProneMessageSource("error_source_3", error_rate=0.0, connection_failures=1),
        ]
        
        for source in error_sources:
            source_manager.add_source(source)
        
        # Track connection attempts and successes
        connection_attempts = 0
        successful_connections = 0
        
        # Start collection (will trigger initial connection attempts)
        source_manager.start_collection()
        
        # Monitor connection recovery over time
        start_time = time.time()
        recovery_time = 30  # seconds
        
        try:
            while time.time() - start_time < recovery_time:
                # Check source status
                sources_status = source_manager.get_sources_status()
                connected_count = sum(1 for status in sources_status if status['connected'])
                
                if connected_count == len(error_sources):
                    successful_connections = connected_count
                    break
                
                # Process any available messages
                messages = source_manager.get_message_batch()
                if messages:
                    logger.info(f"Received {len(messages)} messages during recovery")
                
                time.sleep(1)
            
            # Final status check
            final_sources_status = source_manager.get_sources_status()
            final_connected = sum(1 for status in final_sources_status if status['connected'])
            
            logger.info(f"Connection Recovery Results:")
            logger.info(f"  Sources: {len(error_sources)}")
            logger.info(f"  Final connected: {final_connected}")
            logger.info(f"  Recovery time: {time.time() - start_time:.1f}s")
            
            for status in final_sources_status:
                logger.info(f"  {status['name']}: {'Connected' if status['connected'] else 'Disconnected'}")
            
            # Recovery assertions
            self.assertGreater(final_connected, 0, "At least some sources should recover")
            self.assertEqual(final_connected, len(error_sources), "All sources should eventually connect")
            
        finally:
            source_manager.stop_collection()
    
    def test_invalid_message_handling(self):
        """Test handling of invalid and corrupted messages"""
        logger.info("Testing invalid message handling")
        
        source_manager = MessageSourceManager()
        
        # Create source with high error rate
        error_source = MockErrorProneMessageSource(
            "high_error_source", 
            error_rate=0.3,  # 30% invalid messages
            connection_failures=0
        )
        source_manager.add_source(error_source)
        
        # Set up decoder
        decoder = PyModeSDecode(self.config)
        
        # Error tracking
        total_messages = 0
        valid_messages = 0
        invalid_messages = 0
        decode_errors = 0
        
        # Start processing
        source_manager.start_collection()
        
        start_time = time.time()
        test_duration = 20  # seconds
        
        try:
            while time.time() - start_time < test_duration:
                messages = source_manager.get_message_batch()
                
                for message, timestamp in messages:
                    total_messages += 1
                    
                    # Try to decode each message individually to track errors
                    try:
                        decoded = decoder.decode_message(message, timestamp)
                        if decoded:
                            valid_messages += 1
                        else:
                            invalid_messages += 1
                    except Exception as e:
                        decode_errors += 1
                        logger.debug(f"Decode error for message '{message}': {e}")
                
                time.sleep(0.1)
            
            # Stop processing
            source_manager.stop_collection()
            
            # Calculate error rates
            invalid_rate = invalid_messages / total_messages if total_messages > 0 else 0
            error_rate = decode_errors / total_messages if total_messages > 0 else 0
            
            # Get decoder statistics
            decoder_stats = decoder.get_statistics()
            
            logger.info(f"Invalid Message Handling Results:")
            logger.info(f"  Total messages: {total_messages}")
            logger.info(f"  Valid messages: {valid_messages}")
            logger.info(f"  Invalid messages: {invalid_messages}")
            logger.info(f"  Decode errors: {decode_errors}")
            logger.info(f"  Invalid rate: {invalid_rate:.1%}")
            logger.info(f"  Error rate: {error_rate:.1%}")
            logger.info(f"  Decoder stats: {decoder_stats}")
            
            # Error handling assertions
            self.assertGreater(total_messages, 100, "Should process significant number of messages")
            self.assertGreater(valid_messages, 0, "Should successfully decode some messages")
            self.assertGreater(invalid_messages, 0, "Should encounter invalid messages")
            self.assertLess(error_rate, 0.1, "Decode error rate should be low (graceful handling)")
            self.assertGreater(invalid_rate, 0.2, "Should detect expected invalid message rate")
            
            # System should remain stable despite errors
            self.assertGreater(decoder_stats['messages_processed'], 0, "Decoder should continue processing")
            
        finally:
            source_manager.stop_collection()
    
    def test_memory_pressure_recovery(self):
        """Test system behavior under memory pressure"""
        logger.info("Testing memory pressure recovery")
        
        # Create high-volume source to generate memory pressure
        source_manager = MessageSourceManager()
        memory_pressure_source = MockHighVolumeMessageSource(
            "memory_pressure",
            messages_per_second=300,  # High rate
            duration_seconds=60
        )
        source_manager.add_source(memory_pressure_source)
        
        # Set up decoder with aggressive cleanup
        config = PyModeSConfig()
        config.aircraft_timeout_sec = 30  # Shorter timeout for cleanup
        decoder = PyModeSDecode(config)
        
        # Memory monitoring
        initial_memory = get_memory_usage_mb()
        peak_memory = initial_memory
        memory_samples = []
        cleanup_events = []
        
        # Start processing
        source_manager.start_collection()
        
        start_time = time.time()
        last_cleanup = start_time
        
        try:
            while time.time() - start_time < 65:
                # Process messages
                messages = source_manager.get_message_batch()
                if messages:
                    decoder.process_messages(messages)
                
                # Monitor memory
                current_memory = get_memory_usage_mb()
                peak_memory = max(peak_memory, current_memory)
                
                # Sample memory periodically
                if len(memory_samples) < 50 and len(memory_samples) % 5 == 0:
                    memory_samples.append((time.time() - start_time, current_memory))
                
                # Aggressive cleanup when memory grows too much
                memory_growth = current_memory - initial_memory
                aircraft_count = len(decoder.get_aircraft_data())
                
                if (memory_growth > 50 or aircraft_count > 150) and time.time() - last_cleanup > 10:
                    removed = decoder.clear_old_aircraft(15)  # Very aggressive cleanup
                    cleanup_events.append({
                        'time': time.time() - start_time,
                        'memory_before': current_memory,
                        'aircraft_removed': removed,
                        'aircraft_remaining': len(decoder.get_aircraft_data())
                    })
                    
                    # Force garbage collection
                    gc.collect()
                    
                    last_cleanup = time.time()
                    logger.info(f"Memory cleanup: removed {removed} aircraft, "
                               f"memory: {current_memory:.1f} MB")
                
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
            self.assertLess(total_memory_growth, 100, "Total memory growth should be controlled")
            self.assertLess(peak_memory - initial_memory, 150, "Peak memory should be controlled")
            self.assertGreater(len(cleanup_events), 0, "Should perform cleanup under pressure")
            self.assertLess(len(decoder.get_aircraft_data()), 200, "Aircraft count should be managed")
            
            # System should continue functioning
            self.assertGreater(decoder_stats['messages_processed'], 5000, "Should continue processing messages")
            self.assertGreater(decoder_stats['decode_rate'], 0.5, "Should maintain reasonable decode rate")
            
        finally:
            source_manager.stop_collection()
    
    def test_watchlist_performance_under_load(self):
        """Test watchlist monitoring performance under high load"""
        logger.info("Testing watchlist performance under load")
        
        # Create high-volume source
        source_manager = MessageSourceManager()
        load_source = MockHighVolumeMessageSource(
            "watchlist_load_test",
            messages_per_second=100,
            duration_seconds=30
        )
        source_manager.add_source(load_source)
        
        # Set up decoder and watchlist
        decoder = PyModeSDecode(self.config)
        
        # Create large watchlist
        watchlist_icaos = set()
        for i in range(20):  # 20 aircraft in watchlist
            watchlist_icaos.add(f"{i:06X}")
        
        # Mock alert interface
        alert_interface = Mock()
        alert_interface.send_alert.return_value = True
        alert_interface.is_throttled.return_value = False
        
        watchlist_monitor = WatchlistMonitor(watchlist_icaos, alert_interface)
        alert_throttler = AlertThrottler()
        
        # Performance tracking
        watchlist_checks = 0
        watchlist_hits = 0
        alert_times = []
        
        # Start processing
        source_manager.start_collection()
        
        start_time = time.time()
        
        try:
            while time.time() - start_time < 35:
                messages = source_manager.get_message_batch()
                
                if messages:
                    # Process messages
                    updated_aircraft = decoder.process_messages(messages)
                    
                    # Check watchlist for each updated aircraft
                    for icao, aircraft in updated_aircraft.items():
                        watchlist_checks += 1
                        
                        check_start = time.time()
                        is_watchlist = watchlist_monitor.check_aircraft(aircraft)
                        check_time = (time.time() - check_start) * 1000  # ms
                        
                        alert_times.append(check_time)
                        
                        if is_watchlist:
                            watchlist_hits += 1
                            
                            # Test alert throttling
                            if not alert_throttler.is_throttled(icao):
                                alert_throttler.record_alert(icao)
                
                time.sleep(0.01)
            
            # Stop processing
            source_manager.stop_collection()
            
            # Calculate performance metrics
            total_duration = time.time() - start_time
            checks_per_second = watchlist_checks / total_duration
            avg_check_time = sum(alert_times) / len(alert_times) if alert_times else 0
            max_check_time = max(alert_times) if alert_times else 0
            hit_rate = watchlist_hits / watchlist_checks if watchlist_checks > 0 else 0
            
            logger.info(f"Watchlist Performance Results:")
            logger.info(f"  Watchlist size: {len(watchlist_icaos)}")
            logger.info(f"  Total checks: {watchlist_checks}")
            logger.info(f"  Watchlist hits: {watchlist_hits}")
            logger.info(f"  Hit rate: {hit_rate:.1%}")
            logger.info(f"  Checks per second: {checks_per_second:.1f}")
            logger.info(f"  Average check time: {avg_check_time:.3f} ms")
            logger.info(f"  Max check time: {max_check_time:.3f} ms")
            
            # Watchlist performance assertions
            self.assertGreater(watchlist_checks, 100, "Should perform many watchlist checks")
            self.assertGreater(checks_per_second, 50, "Should maintain good check rate")
            self.assertLess(avg_check_time, 1.0, "Average check time should be fast")
            self.assertLess(max_check_time, 10.0, "Max check time should be reasonable")
            
            # Should find some watchlist matches (based on our test data)
            self.assertGreater(watchlist_hits, 0, "Should detect some watchlist aircraft")
            
        finally:
            source_manager.stop_collection()


def run_performance_tests():
    """Run all performance and stress tests"""
    if not PYMODES_INTEGRATION_AVAILABLE:
        print("ERROR: pyModeS integration not available. Cannot run performance tests.")
        print("Please ensure the pymodes_integration module is properly installed.")
        return False
    
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