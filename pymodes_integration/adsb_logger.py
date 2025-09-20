"""
Structured logging system for ADS-B receiver with pyModeS integration.

This module provides comprehensive logging capabilities including message processing
statistics, aircraft tracking events, and performance metrics as specified in
requirement 5.3.
"""

import logging
import logging.handlers
import time
import threading
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from pathlib import Path
import json
import os

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None


@dataclass
class MessageStats:
    """Statistics for message processing."""
    total_messages: int = 0
    valid_messages: int = 0
    invalid_messages: int = 0
    decode_errors: int = 0
    crc_failures: int = 0
    format_errors: int = 0
    processing_time_ms: float = 0.0
    messages_per_second: float = 0.0
    last_reset: datetime = field(default_factory=datetime.now)


@dataclass
class AircraftStats:
    """Statistics for aircraft tracking."""
    total_aircraft: int = 0
    active_aircraft: int = 0
    new_aircraft: int = 0
    updated_aircraft: int = 0
    expired_aircraft: int = 0
    position_updates: int = 0
    velocity_updates: int = 0
    identification_updates: int = 0
    watchlist_matches: int = 0


@dataclass
class ConnectionStats:
    """Statistics for message source connections."""
    source_name: str
    connection_status: str = "disconnected"
    connect_time: Optional[datetime] = None
    disconnect_time: Optional[datetime] = None
    reconnect_attempts: int = 0
    bytes_received: int = 0
    messages_received: int = 0
    last_message_time: Optional[datetime] = None
    error_count: int = 0


@dataclass
class PerformanceMetrics:
    """System performance metrics."""
    cpu_usage_percent: float = 0.0
    memory_usage_mb: float = 0.0
    memory_usage_percent: float = 0.0
    aircraft_database_size: int = 0
    message_queue_size: int = 0
    processing_latency_ms: float = 0.0
    gc_collections: int = 0
    timestamp: datetime = field(default_factory=datetime.now)


class LogCategory:
    """Log categories for structured logging."""
    MESSAGE_PROCESSING = "message_processing"
    AIRCRAFT_TRACKING = "aircraft_tracking"
    CONNECTION_EVENTS = "connection_events"
    WATCHLIST_ALERTS = "watchlist_alerts"
    PERFORMANCE = "performance"
    DECODE_ERRORS = "decode_errors"
    SYSTEM_EVENTS = "system_events"


class ADSBLogger:
    """
    Structured logging system for ADS-B receiver with categorized log levels
    and performance metrics tracking.
    
    Implements requirement 5.3 for comprehensive logging and monitoring.
    """
    
    def __init__(self, 
                 log_file: str = "adsb_receiver.log",
                 log_level: str = "INFO",
                 max_log_size_mb: int = 100,
                 backup_count: int = 5,
                 stats_interval_sec: int = 60,
                 enable_console: bool = True):
        """
        Initialize the ADS-B logging system.
        
        Args:
            log_file: Path to the main log file
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_log_size_mb: Maximum log file size before rotation
            backup_count: Number of backup log files to keep
            stats_interval_sec: Interval for statistics logging
            enable_console: Whether to enable console logging
        """
        self.log_file = Path(log_file)
        self.log_level = getattr(logging, log_level.upper())
        self.max_log_size_mb = max_log_size_mb
        self.backup_count = backup_count
        self.stats_interval_sec = stats_interval_sec
        self.enable_console = enable_console
        
        # Statistics tracking
        self.message_stats = MessageStats()
        self.aircraft_stats = AircraftStats()
        self.connection_stats: Dict[str, ConnectionStats] = {}
        self.performance_metrics = PerformanceMetrics()
        
        # Performance history for trending
        self.performance_history: deque = deque(maxlen=1440)  # 24 hours at 1-minute intervals
        
        # Thread safety
        self._stats_lock = threading.Lock()
        self._logger_lock = threading.Lock()
        
        # Statistics timer
        self._stats_timer: Optional[threading.Timer] = None
        self._running = False
        
        # Initialize loggers
        self._setup_loggers()
        
        # Start statistics collection
        self.start_stats_collection()
    
    def _setup_loggers(self) -> None:
        """Set up the logging infrastructure with categorized loggers."""
        # Create main logger
        self.logger = logging.getLogger("adsb_receiver")
        self.logger.setLevel(self.log_level)
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - [%(category)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        
        # File handler with rotation
        file_handler = logging.handlers.RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_log_size_mb * 1024 * 1024,
            backupCount=self.backup_count
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(file_handler)
        
        # Console handler
        if self.enable_console:
            console_handler = logging.StreamHandler()
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(simple_formatter)
            self.logger.addHandler(console_handler)
        
        # Category-specific loggers
        self.category_loggers = {}
        for category in [LogCategory.MESSAGE_PROCESSING, LogCategory.AIRCRAFT_TRACKING,
                        LogCategory.CONNECTION_EVENTS, LogCategory.WATCHLIST_ALERTS,
                        LogCategory.PERFORMANCE, LogCategory.DECODE_ERRORS,
                        LogCategory.SYSTEM_EVENTS]:
            
            cat_logger = logging.getLogger(f"adsb_receiver.{category}")
            cat_logger.setLevel(self.log_level)
            
            # Create category-specific file handler
            cat_file = self.log_file.parent / f"{self.log_file.stem}_{category}.log"
            cat_handler = logging.handlers.RotatingFileHandler(
                cat_file,
                maxBytes=self.max_log_size_mb * 1024 * 1024,
                backupCount=self.backup_count
            )
            cat_handler.setLevel(self.log_level)
            cat_handler.setFormatter(detailed_formatter)
            cat_logger.addHandler(cat_handler)
            
            self.category_loggers[category] = cat_logger
    
    def start_stats_collection(self) -> None:
        """Start periodic statistics collection and logging."""
        self._running = True
        self._schedule_stats_logging()
    
    def stop_stats_collection(self) -> None:
        """Stop statistics collection."""
        self._running = False
        if self._stats_timer:
            self._stats_timer.cancel()
    
    def _schedule_stats_logging(self) -> None:
        """Schedule the next statistics logging."""
        if self._running:
            self._stats_timer = threading.Timer(self.stats_interval_sec, self._log_periodic_stats)
            self._stats_timer.start()
    
    def _log_periodic_stats(self) -> None:
        """Log periodic statistics and performance metrics."""
        try:
            # Update performance metrics
            self._update_performance_metrics()
            
            # Log statistics
            self.log_message_statistics()
            self.log_aircraft_statistics()
            self.log_connection_statistics()
            self.log_performance_metrics()
            
            # Reset counters for next period
            self._reset_periodic_counters()
            
            # Schedule next logging
            self._schedule_stats_logging()
            
        except Exception as e:
            self.log_system_error("Failed to log periodic statistics", e)
    
    def _update_performance_metrics(self) -> None:
        """Update system performance metrics."""
        try:
            if PSUTIL_AVAILABLE:
                process = psutil.Process()
                
                with self._stats_lock:
                    self.performance_metrics.cpu_usage_percent = process.cpu_percent()
                    
                    memory_info = process.memory_info()
                    self.performance_metrics.memory_usage_mb = memory_info.rss / 1024 / 1024
                    self.performance_metrics.memory_usage_percent = process.memory_percent()
            else:
                # Fallback when psutil is not available
                with self._stats_lock:
                    self.performance_metrics.cpu_usage_percent = 0.0
                    self.performance_metrics.memory_usage_mb = 0.0
                    self.performance_metrics.memory_usage_percent = 0.0
            
            with self._stats_lock:
                self.performance_metrics.timestamp = datetime.now()
                
                # Add to history
                self.performance_history.append({
                    'timestamp': self.performance_metrics.timestamp.isoformat(),
                    'cpu_percent': self.performance_metrics.cpu_usage_percent,
                    'memory_mb': self.performance_metrics.memory_usage_mb,
                    'memory_percent': self.performance_metrics.memory_usage_percent,
                    'aircraft_count': self.aircraft_stats.active_aircraft,
                    'message_rate': self.message_stats.messages_per_second
                })
                
        except Exception as e:
            self.log_system_error("Failed to update performance metrics", e)
    
    def _reset_periodic_counters(self) -> None:
        """Reset counters that are tracked per period."""
        with self._stats_lock:
            # Reset message stats
            self.message_stats.total_messages = 0
            self.message_stats.valid_messages = 0
            self.message_stats.invalid_messages = 0
            self.message_stats.decode_errors = 0
            self.message_stats.crc_failures = 0
            self.message_stats.format_errors = 0
            self.message_stats.processing_time_ms = 0.0
            self.message_stats.messages_per_second = 0.0
            self.message_stats.last_reset = datetime.now()
            
            # Reset aircraft stats
            self.aircraft_stats.new_aircraft = 0
            self.aircraft_stats.updated_aircraft = 0
            self.aircraft_stats.expired_aircraft = 0
            self.aircraft_stats.position_updates = 0
            self.aircraft_stats.velocity_updates = 0
            self.aircraft_stats.identification_updates = 0
            self.aircraft_stats.watchlist_matches = 0
    
    # Message Processing Logging Methods
    
    def log_message_batch_processed(self, 
                                   batch_size: int, 
                                   valid_count: int, 
                                   processing_time_ms: float) -> None:
        """Log message batch processing statistics."""
        with self._stats_lock:
            self.message_stats.total_messages += batch_size
            self.message_stats.valid_messages += valid_count
            self.message_stats.invalid_messages += (batch_size - valid_count)
            self.message_stats.processing_time_ms += processing_time_ms
            
            # Calculate messages per second
            elapsed = (datetime.now() - self.message_stats.last_reset).total_seconds()
            if elapsed > 0:
                self.message_stats.messages_per_second = self.message_stats.total_messages / elapsed
        
        self._log_categorized(
            LogCategory.MESSAGE_PROCESSING,
            logging.INFO,
            f"Processed batch: {batch_size} messages, {valid_count} valid, "
            f"{processing_time_ms:.2f}ms processing time"
        )
    
    def log_decode_error(self, message: str, error: Exception, message_hex: str = None) -> None:
        """Log message decoding errors."""
        with self._stats_lock:
            self.message_stats.decode_errors += 1
        
        error_details = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'message_hex': message_hex[:50] if message_hex else None  # Truncate for logging
        }
        
        self._log_categorized(
            LogCategory.DECODE_ERRORS,
            logging.WARNING,
            f"Decode error: {message} - {error_details}"
        )
    
    def log_crc_failure(self, message_hex: str) -> None:
        """Log CRC validation failures."""
        with self._stats_lock:
            self.message_stats.crc_failures += 1
        
        self._log_categorized(
            LogCategory.MESSAGE_PROCESSING,
            logging.DEBUG,
            f"CRC validation failed for message: {message_hex[:20]}..."
        )
    
    def log_format_error(self, message_hex: str, expected_length: int, actual_length: int) -> None:
        """Log message format validation errors."""
        with self._stats_lock:
            self.message_stats.format_errors += 1
        
        self._log_categorized(
            LogCategory.MESSAGE_PROCESSING,
            logging.DEBUG,
            f"Format error: expected {expected_length} bytes, got {actual_length} "
            f"for message: {message_hex[:20]}..."
        )
    
    # Aircraft Tracking Logging Methods
    
    def log_aircraft_created(self, icao: str, initial_data: Dict[str, Any]) -> None:
        """Log new aircraft creation."""
        with self._stats_lock:
            self.aircraft_stats.new_aircraft += 1
            self.aircraft_stats.total_aircraft += 1
            self.aircraft_stats.active_aircraft += 1
        
        self._log_categorized(
            LogCategory.AIRCRAFT_TRACKING,
            logging.INFO,
            f"New aircraft created: {icao} with data: {initial_data}"
        )
    
    def log_aircraft_updated(self, icao: str, updates: Dict[str, Any]) -> None:
        """Log aircraft data updates."""
        with self._stats_lock:
            self.aircraft_stats.updated_aircraft += 1
            
            # Track specific update types
            if any(key in updates for key in ['latitude', 'longitude', 'altitude']):
                self.aircraft_stats.position_updates += 1
            
            if any(key in updates for key in ['ground_speed', 'track', 'vertical_rate']):
                self.aircraft_stats.velocity_updates += 1
            
            if 'callsign' in updates:
                self.aircraft_stats.identification_updates += 1
        
        self._log_categorized(
            LogCategory.AIRCRAFT_TRACKING,
            logging.DEBUG,
            f"Aircraft {icao} updated: {updates}"
        )
    
    def log_aircraft_expired(self, icao: str, age_seconds: int) -> None:
        """Log aircraft expiration due to timeout."""
        with self._stats_lock:
            self.aircraft_stats.expired_aircraft += 1
            self.aircraft_stats.active_aircraft -= 1
        
        self._log_categorized(
            LogCategory.AIRCRAFT_TRACKING,
            logging.INFO,
            f"Aircraft {icao} expired after {age_seconds} seconds"
        )
    
    def log_position_calculation(self, icao: str, method: str, success: bool, 
                               lat: float = None, lon: float = None) -> None:
        """Log CPR position calculation results."""
        status = "successful" if success else "failed"
        position_str = f"({lat:.6f}, {lon:.6f})" if success and lat and lon else "unknown"
        
        self._log_categorized(
            LogCategory.AIRCRAFT_TRACKING,
            logging.DEBUG,
            f"Position calculation for {icao}: {method} method {status}, position: {position_str}"
        )
    
    # Connection Event Logging Methods
    
    def log_source_connected(self, source_name: str, host: str, port: int) -> None:
        """Log message source connection."""
        if source_name not in self.connection_stats:
            self.connection_stats[source_name] = ConnectionStats(source_name=source_name)
        
        with self._stats_lock:
            stats = self.connection_stats[source_name]
            stats.connection_status = "connected"
            stats.connect_time = datetime.now()
            stats.disconnect_time = None
        
        self._log_categorized(
            LogCategory.CONNECTION_EVENTS,
            logging.INFO,
            f"Source {source_name} connected to {host}:{port}"
        )
    
    def log_source_disconnected(self, source_name: str, reason: str = None) -> None:
        """Log message source disconnection."""
        if source_name in self.connection_stats:
            with self._stats_lock:
                stats = self.connection_stats[source_name]
                stats.connection_status = "disconnected"
                stats.disconnect_time = datetime.now()
        
        reason_str = f" ({reason})" if reason else ""
        self._log_categorized(
            LogCategory.CONNECTION_EVENTS,
            logging.WARNING,
            f"Source {source_name} disconnected{reason_str}"
        )
    
    def log_reconnection_attempt(self, source_name: str, attempt: int, max_attempts: int) -> None:
        """Log reconnection attempts."""
        if source_name in self.connection_stats:
            with self._stats_lock:
                self.connection_stats[source_name].reconnect_attempts = attempt
        
        self._log_categorized(
            LogCategory.CONNECTION_EVENTS,
            logging.INFO,
            f"Reconnection attempt {attempt}/{max_attempts} for source {source_name}"
        )
    
    def log_connection_error(self, source_name: str, error: Exception) -> None:
        """Log connection errors."""
        if source_name in self.connection_stats:
            with self._stats_lock:
                self.connection_stats[source_name].error_count += 1
        
        self._log_categorized(
            LogCategory.CONNECTION_EVENTS,
            logging.ERROR,
            f"Connection error for source {source_name}: {type(error).__name__}: {error}"
        )
    
    # Watchlist Alert Logging Methods
    
    def log_watchlist_match(self, icao: str, callsign: str = None, 
                           match_type: str = "icao", alert_sent: bool = False) -> None:
        """Log watchlist matches and alerts."""
        with self._stats_lock:
            self.aircraft_stats.watchlist_matches += 1
        
        callsign_str = f" (callsign: {callsign})" if callsign else ""
        alert_str = " - Alert sent" if alert_sent else " - Alert throttled"
        
        self._log_categorized(
            LogCategory.WATCHLIST_ALERTS,
            logging.WARNING,
            f"Watchlist match: {icao}{callsign_str} matched on {match_type}{alert_str}"
        )
    
    def log_alert_throttled(self, icao: str, time_remaining: int) -> None:
        """Log throttled alerts."""
        self._log_categorized(
            LogCategory.WATCHLIST_ALERTS,
            logging.INFO,
            f"Alert throttled for {icao}, {time_remaining} seconds remaining"
        )
    
    def log_alert_sent(self, icao: str, alert_type: str, destination: str) -> None:
        """Log successful alert transmission."""
        self._log_categorized(
            LogCategory.WATCHLIST_ALERTS,
            logging.INFO,
            f"Alert sent for {icao}: {alert_type} to {destination}"
        )
    
    def log_alert_failed(self, icao: str, error: Exception) -> None:
        """Log failed alert transmission."""
        self._log_categorized(
            LogCategory.WATCHLIST_ALERTS,
            logging.ERROR,
            f"Alert failed for {icao}: {type(error).__name__}: {error}"
        )
    
    # Statistics Logging Methods
    
    def log_message_statistics(self) -> None:
        """Log current message processing statistics."""
        with self._stats_lock:
            stats = self.message_stats
            
            success_rate = (stats.valid_messages / stats.total_messages * 100) if stats.total_messages > 0 else 0
            avg_processing_time = (stats.processing_time_ms / stats.total_messages) if stats.total_messages > 0 else 0
            
            stats_dict = {
                'total_messages': stats.total_messages,
                'valid_messages': stats.valid_messages,
                'invalid_messages': stats.invalid_messages,
                'decode_errors': stats.decode_errors,
                'crc_failures': stats.crc_failures,
                'format_errors': stats.format_errors,
                'success_rate_percent': round(success_rate, 2),
                'messages_per_second': round(stats.messages_per_second, 2),
                'avg_processing_time_ms': round(avg_processing_time, 3)
            }
        
        self._log_categorized(
            LogCategory.PERFORMANCE,
            logging.INFO,
            f"Message statistics: {json.dumps(stats_dict)}"
        )
    
    def log_aircraft_statistics(self) -> None:
        """Log current aircraft tracking statistics."""
        with self._stats_lock:
            stats = self.aircraft_stats
            
            stats_dict = {
                'total_aircraft': stats.total_aircraft,
                'active_aircraft': stats.active_aircraft,
                'new_aircraft': stats.new_aircraft,
                'updated_aircraft': stats.updated_aircraft,
                'expired_aircraft': stats.expired_aircraft,
                'position_updates': stats.position_updates,
                'velocity_updates': stats.velocity_updates,
                'identification_updates': stats.identification_updates,
                'watchlist_matches': stats.watchlist_matches
            }
        
        self._log_categorized(
            LogCategory.PERFORMANCE,
            logging.INFO,
            f"Aircraft statistics: {json.dumps(stats_dict)}"
        )
    
    def log_connection_statistics(self) -> None:
        """Log connection statistics for all sources."""
        with self._stats_lock:
            for source_name, stats in self.connection_stats.items():
                uptime_seconds = 0
                if stats.connect_time and stats.connection_status == "connected":
                    uptime_seconds = (datetime.now() - stats.connect_time).total_seconds()
                
                stats_dict = {
                    'source_name': stats.source_name,
                    'status': stats.connection_status,
                    'uptime_seconds': int(uptime_seconds),
                    'reconnect_attempts': stats.reconnect_attempts,
                    'bytes_received': stats.bytes_received,
                    'messages_received': stats.messages_received,
                    'error_count': stats.error_count
                }
                
                self._log_categorized(
                    LogCategory.PERFORMANCE,
                    logging.INFO,
                    f"Connection statistics: {json.dumps(stats_dict)}"
                )
    
    def log_performance_metrics(self) -> None:
        """Log system performance metrics."""
        with self._stats_lock:
            metrics = self.performance_metrics
            
            metrics_dict = {
                'cpu_usage_percent': round(metrics.cpu_usage_percent, 2),
                'memory_usage_mb': round(metrics.memory_usage_mb, 2),
                'memory_usage_percent': round(metrics.memory_usage_percent, 2),
                'aircraft_database_size': metrics.aircraft_database_size,
                'message_queue_size': metrics.message_queue_size,
                'processing_latency_ms': round(metrics.processing_latency_ms, 3),
                'gc_collections': metrics.gc_collections
            }
        
        self._log_categorized(
            LogCategory.PERFORMANCE,
            logging.INFO,
            f"Performance metrics: {json.dumps(metrics_dict)}"
        )
    
    # System Event Logging Methods
    
    def log_system_startup(self, config: Dict[str, Any]) -> None:
        """Log system startup with configuration."""
        self._log_categorized(
            LogCategory.SYSTEM_EVENTS,
            logging.INFO,
            f"ADS-B receiver system starting up with config: {json.dumps(config, default=str)}"
        )
    
    def log_system_shutdown(self, reason: str = None) -> None:
        """Log system shutdown."""
        reason_str = f" ({reason})" if reason else ""
        self._log_categorized(
            LogCategory.SYSTEM_EVENTS,
            logging.INFO,
            f"ADS-B receiver system shutting down{reason_str}"
        )
    
    def log_system_error(self, message: str, error: Exception) -> None:
        """Log system-level errors."""
        self._log_categorized(
            LogCategory.SYSTEM_EVENTS,
            logging.ERROR,
            f"System error: {message} - {type(error).__name__}: {error}"
        )
    
    def log_config_change(self, changes: Dict[str, Any]) -> None:
        """Log configuration changes."""
        self._log_categorized(
            LogCategory.SYSTEM_EVENTS,
            logging.INFO,
            f"Configuration changed: {json.dumps(changes, default=str)}"
        )
    
    # Utility Methods
    
    def _log_categorized(self, category: str, level: int, message: str) -> None:
        """Log a message to both main logger and category-specific logger."""
        # Add category to the log record
        extra = {'category': category}
        
        # Log to main logger
        self.logger.log(level, message, extra=extra)
        
        # Log to category-specific logger if it exists
        if category in self.category_loggers:
            self.category_loggers[category].log(level, message)
    
    def get_statistics_summary(self) -> Dict[str, Any]:
        """Get a summary of all current statistics."""
        with self._stats_lock:
            return {
                'message_stats': {
                    'total_messages': self.message_stats.total_messages,
                    'valid_messages': self.message_stats.valid_messages,
                    'invalid_messages': self.message_stats.invalid_messages,
                    'decode_errors': self.message_stats.decode_errors,
                    'messages_per_second': self.message_stats.messages_per_second
                },
                'aircraft_stats': {
                    'total_aircraft': self.aircraft_stats.total_aircraft,
                    'active_aircraft': self.aircraft_stats.active_aircraft,
                    'new_aircraft': self.aircraft_stats.new_aircraft,
                    'watchlist_matches': self.aircraft_stats.watchlist_matches
                },
                'performance_metrics': {
                    'cpu_usage_percent': self.performance_metrics.cpu_usage_percent,
                    'memory_usage_mb': self.performance_metrics.memory_usage_mb,
                    'aircraft_database_size': self.performance_metrics.aircraft_database_size
                },
                'connection_stats': {
                    name: {
                        'status': stats.connection_status,
                        'messages_received': stats.messages_received,
                        'error_count': stats.error_count
                    }
                    for name, stats in self.connection_stats.items()
                }
            }
    
    def get_performance_history(self, hours: int = 1) -> List[Dict[str, Any]]:
        """Get performance history for the specified number of hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        return [
            entry for entry in self.performance_history
            if datetime.fromisoformat(entry['timestamp']) >= cutoff_time
        ]
    
    def update_aircraft_database_size(self, size: int) -> None:
        """Update the aircraft database size metric."""
        with self._stats_lock:
            self.performance_metrics.aircraft_database_size = size
    
    def update_message_queue_size(self, size: int) -> None:
        """Update the message queue size metric."""
        with self._stats_lock:
            self.performance_metrics.message_queue_size = size
    
    def update_processing_latency(self, latency_ms: float) -> None:
        """Update the processing latency metric."""
        with self._stats_lock:
            self.performance_metrics.processing_latency_ms = latency_ms
    
    def record_source_data(self, source_name: str, bytes_received: int, messages_received: int) -> None:
        """Record data received from a message source."""
        if source_name not in self.connection_stats:
            self.connection_stats[source_name] = ConnectionStats(source_name=source_name)
        
        with self._stats_lock:
            stats = self.connection_stats[source_name]
            stats.bytes_received += bytes_received
            stats.messages_received += messages_received
            stats.last_message_time = datetime.now()
    
    def __del__(self) -> None:
        """Cleanup when logger is destroyed."""
        self.stop_stats_collection()


# Global logger instance
_global_logger: Optional[ADSBLogger] = None


def get_logger() -> ADSBLogger:
    """Get the global ADS-B logger instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = ADSBLogger()
    return _global_logger


def initialize_logger(config: Dict[str, Any]) -> ADSBLogger:
    """Initialize the global logger with configuration."""
    global _global_logger
    
    logging_config = config.get('logging', {})
    
    _global_logger = ADSBLogger(
        log_file=logging_config.get('log_file', 'adsb_receiver.log'),
        log_level=logging_config.get('level', 'INFO'),
        max_log_size_mb=logging_config.get('max_log_size_mb', 100),
        backup_count=logging_config.get('backup_count', 5),
        stats_interval_sec=logging_config.get('stats_interval_sec', 60),
        enable_console=True
    )
    
    return _global_logger


def shutdown_logger() -> None:
    """Shutdown the global logger."""
    global _global_logger
    if _global_logger:
        _global_logger.stop_stats_collection()
        _global_logger = None