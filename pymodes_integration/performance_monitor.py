"""
Performance monitoring and metrics collection for ADS-B receiver system.

This module provides comprehensive performance monitoring including message processing
rates, decode success rates, memory usage tracking, and watchlist alert statistics
as specified in requirement 5.3.
"""

import time
import threading
import gc
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    psutil = None
import os
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from statistics import mean, median
import json


@dataclass
class ProcessingMetrics:
    """Metrics for message processing performance."""
    messages_processed: int = 0
    messages_per_second: float = 0.0
    decode_success_rate: float = 0.0
    avg_processing_time_ms: float = 0.0
    peak_processing_time_ms: float = 0.0
    batch_processing_times: deque = field(default_factory=lambda: deque(maxlen=100))
    last_update: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryMetrics:
    """Memory usage metrics."""
    current_usage_mb: float = 0.0
    peak_usage_mb: float = 0.0
    usage_percent: float = 0.0
    aircraft_database_size: int = 0
    aircraft_memory_mb: float = 0.0
    message_queue_size: int = 0
    gc_collections: int = 0
    memory_growth_rate_mb_per_hour: float = 0.0
    last_gc_time: datetime = field(default_factory=datetime.now)


@dataclass
class NetworkMetrics:
    """Network and connection metrics."""
    bytes_received_per_second: float = 0.0
    total_bytes_received: int = 0
    connection_uptime_seconds: int = 0
    reconnection_count: int = 0
    connection_success_rate: float = 100.0
    avg_message_size_bytes: float = 0.0
    network_latency_ms: float = 0.0


@dataclass
class AlertMetrics:
    """Watchlist alert metrics and timing."""
    total_alerts_sent: int = 0
    alerts_per_hour: float = 0.0
    alert_success_rate: float = 100.0
    avg_alert_processing_time_ms: float = 0.0
    throttled_alerts: int = 0
    failed_alerts: int = 0
    alert_response_times: deque = field(default_factory=lambda: deque(maxlen=50))
    watchlist_check_time_ms: float = 0.0


@dataclass
class SystemMetrics:
    """Overall system performance metrics."""
    cpu_usage_percent: float = 0.0
    system_load_average: float = 0.0
    disk_usage_percent: float = 0.0
    uptime_seconds: int = 0
    thread_count: int = 0
    file_descriptor_count: int = 0
    system_temperature_celsius: Optional[float] = None


class PerformanceMonitor:
    """
    Comprehensive performance monitoring system for ADS-B receiver.
    
    Tracks message processing rates, decode success rates, memory usage,
    aircraft database size, and watchlist alert statistics as required
    by specification 5.3.
    """
    
    def __init__(self, 
                 update_interval_sec: float = 1.0,
                 history_retention_hours: int = 24,
                 enable_detailed_metrics: bool = True):
        """
        Initialize the performance monitor.
        
        Args:
            update_interval_sec: How often to update metrics
            history_retention_hours: How long to keep historical data
            enable_detailed_metrics: Whether to collect detailed performance data
        """
        self.update_interval_sec = update_interval_sec
        self.history_retention_hours = history_retention_hours
        self.enable_detailed_metrics = enable_detailed_metrics
        
        # Metrics storage
        self.processing_metrics = ProcessingMetrics()
        self.memory_metrics = MemoryMetrics()
        self.network_metrics = NetworkMetrics()
        self.alert_metrics = AlertMetrics()
        self.system_metrics = SystemMetrics()
        
        # Historical data storage
        max_history_points = int(history_retention_hours * 3600 / update_interval_sec)
        self.processing_history: deque = deque(maxlen=max_history_points)
        self.memory_history: deque = deque(maxlen=max_history_points)
        self.network_history: deque = deque(maxlen=max_history_points)
        self.alert_history: deque = deque(maxlen=max_history_points)
        self.system_history: deque = deque(maxlen=max_history_points)
        
        # Tracking variables
        self._start_time = datetime.now()
        self._last_update = datetime.now()
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None
        
        # Counters for rate calculations
        self._message_count_tracker = deque(maxlen=60)  # Last 60 seconds
        self._bytes_received_tracker = deque(maxlen=60)
        self._alert_count_tracker = deque(maxlen=3600)  # Last hour
        
        # Thread safety
        self._metrics_lock = threading.Lock()
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Callbacks for external data
        self._aircraft_count_callback: Optional[Callable[[], int]] = None
        self._message_queue_callback: Optional[Callable[[], int]] = None
        
        # Performance thresholds for alerting
        self.thresholds = {
            'cpu_usage_percent': 80.0,
            'memory_usage_percent': 85.0,
            'decode_success_rate': 95.0,
            'messages_per_second_min': 10.0,
            'alert_success_rate': 98.0
        }
        
        # Performance alert callbacks
        self._alert_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
    
    def start_monitoring(self) -> None:
        """Start the performance monitoring thread."""
        if self._running:
            return
        
        self._running = True
        self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitor_thread.start()
    
    def stop_monitoring(self) -> None:
        """Stop the performance monitoring thread."""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop that updates metrics periodically."""
        while self._running:
            try:
                self._update_all_metrics()
                self._check_performance_thresholds()
                time.sleep(self.update_interval_sec)
            except Exception as e:
                # Log error but continue monitoring
                print(f"Performance monitoring error: {e}")
                time.sleep(self.update_interval_sec)
    
    def _update_all_metrics(self) -> None:
        """Update all performance metrics."""
        current_time = datetime.now()
        
        with self._metrics_lock:
            # Update system metrics
            self._update_system_metrics()
            
            # Update memory metrics
            self._update_memory_metrics()
            
            # Update processing metrics
            self._update_processing_metrics()
            
            # Update network metrics
            self._update_network_metrics()
            
            # Update alert metrics
            self._update_alert_metrics()
            
            # Store historical data
            self._store_historical_data(current_time)
            
            self._last_update = current_time
    
    def _update_system_metrics(self) -> None:
        """Update system-level performance metrics."""
        try:
            # CPU usage
            self.system_metrics.cpu_usage_percent = self._process.cpu_percent()
            
            # System load (Unix-like systems only)
            try:
                load_avg = os.getloadavg()[0]  # 1-minute load average
                self.system_metrics.system_load_average = load_avg
            except (OSError, AttributeError):
                # Windows doesn't have getloadavg
                pass
            
            # Disk usage
            if PSUTIL_AVAILABLE:
                disk_usage = psutil.disk_usage('/')
                self.system_metrics.disk_usage_percent = (disk_usage.used / disk_usage.total) * 100
            else:
                self.system_metrics.disk_usage_percent = 0.0
            
            # Uptime
            self.system_metrics.uptime_seconds = int((datetime.now() - self._start_time).total_seconds())
            
            # Thread count
            if PSUTIL_AVAILABLE and self._process:
                self.system_metrics.thread_count = self._process.num_threads()
                
                # File descriptors (Unix-like systems only)
                try:
                    self.system_metrics.file_descriptor_count = self._process.num_fds()
                except (AttributeError, psutil.AccessDenied):
                    # Windows doesn't have num_fds or access denied
                    pass
            else:
                self.system_metrics.thread_count = 0
                self.system_metrics.file_descriptor_count = 0
            
            # System temperature (if available)
            if PSUTIL_AVAILABLE:
                try:
                    temps = psutil.sensors_temperatures()
                    if temps:
                        # Get CPU temperature if available
                        for name, entries in temps.items():
                            if 'cpu' in name.lower() or 'core' in name.lower():
                                if entries:
                                    self.system_metrics.system_temperature_celsius = entries[0].current
                                    break
                except (AttributeError, OSError):
                    # Temperature sensors not available
                    pass
                
        except Exception as e:
            print(f"Error updating system metrics: {e}")
    
    def _update_memory_metrics(self) -> None:
        """Update memory usage metrics."""
        try:
            # Process memory info
            memory_info = self._process.memory_info()
            self.memory_metrics.current_usage_mb = memory_info.rss / 1024 / 1024
            self.memory_metrics.usage_percent = self._process.memory_percent()
            
            # Track peak usage
            if self.memory_metrics.current_usage_mb > self.memory_metrics.peak_usage_mb:
                self.memory_metrics.peak_usage_mb = self.memory_metrics.current_usage_mb
            
            # Aircraft database size (if callback provided)
            if self._aircraft_count_callback:
                self.memory_metrics.aircraft_database_size = self._aircraft_count_callback()
                # Estimate memory per aircraft (rough calculation)
                if self.memory_metrics.aircraft_database_size > 0:
                    self.memory_metrics.aircraft_memory_mb = (
                        self.memory_metrics.current_usage_mb * 0.6  # Assume 60% for aircraft data
                    )
            
            # Message queue size (if callback provided)
            if self._message_queue_callback:
                self.memory_metrics.message_queue_size = self._message_queue_callback()
            
            # Garbage collection info
            gc_stats = gc.get_stats()
            if gc_stats:
                self.memory_metrics.gc_collections = sum(stat['collections'] for stat in gc_stats)
            
            # Calculate memory growth rate
            if len(self.memory_history) > 10:
                # Use last 10 data points to calculate growth rate
                recent_history = list(self.memory_history)[-10:]
                if len(recent_history) >= 2:
                    time_diff_hours = (
                        datetime.fromisoformat(recent_history[-1]['timestamp']) - 
                        datetime.fromisoformat(recent_history[0]['timestamp'])
                    ).total_seconds() / 3600
                    
                    if time_diff_hours > 0:
                        memory_diff = recent_history[-1]['current_usage_mb'] - recent_history[0]['current_usage_mb']
                        self.memory_metrics.memory_growth_rate_mb_per_hour = memory_diff / time_diff_hours
                        
        except Exception as e:
            print(f"Error updating memory metrics: {e}")
    
    def _update_processing_metrics(self) -> None:
        """Update message processing metrics."""
        try:
            # Calculate messages per second from recent history
            current_time = time.time()
            
            # Remove old entries (older than 60 seconds)
            while (self._message_count_tracker and 
                   current_time - self._message_count_tracker[0][0] > 60):
                self._message_count_tracker.popleft()
            
            # Calculate rate
            if len(self._message_count_tracker) >= 2:
                total_messages = sum(count for _, count in self._message_count_tracker)
                time_span = current_time - self._message_count_tracker[0][0]
                if time_span > 0:
                    self.processing_metrics.messages_per_second = total_messages / time_span
            
            # Calculate average processing time from recent batches
            if self.processing_metrics.batch_processing_times:
                self.processing_metrics.avg_processing_time_ms = mean(
                    self.processing_metrics.batch_processing_times
                )
                self.processing_metrics.peak_processing_time_ms = max(
                    self.processing_metrics.batch_processing_times
                )
                
        except Exception as e:
            print(f"Error updating processing metrics: {e}")
    
    def _update_network_metrics(self) -> None:
        """Update network and connection metrics."""
        try:
            # Calculate bytes per second from recent history
            current_time = time.time()
            
            # Remove old entries (older than 60 seconds)
            while (self._bytes_received_tracker and 
                   current_time - self._bytes_received_tracker[0][0] > 60):
                self._bytes_received_tracker.popleft()
            
            # Calculate rate
            if len(self._bytes_received_tracker) >= 2:
                total_bytes = sum(bytes_count for _, bytes_count in self._bytes_received_tracker)
                time_span = current_time - self._bytes_received_tracker[0][0]
                if time_span > 0:
                    self.network_metrics.bytes_received_per_second = total_bytes / time_span
            
            # Calculate average message size
            if (self.processing_metrics.messages_processed > 0 and 
                self.network_metrics.total_bytes_received > 0):
                self.network_metrics.avg_message_size_bytes = (
                    self.network_metrics.total_bytes_received / 
                    self.processing_metrics.messages_processed
                )
                
        except Exception as e:
            print(f"Error updating network metrics: {e}")
    
    def _update_alert_metrics(self) -> None:
        """Update watchlist alert metrics."""
        try:
            # Calculate alerts per hour from recent history
            current_time = time.time()
            
            # Remove old entries (older than 1 hour)
            while (self._alert_count_tracker and 
                   current_time - self._alert_count_tracker[0] > 3600):
                self._alert_count_tracker.popleft()
            
            # Calculate hourly rate
            self.alert_metrics.alerts_per_hour = len(self._alert_count_tracker)
            
            # Calculate average alert processing time
            if self.alert_metrics.alert_response_times:
                self.alert_metrics.avg_alert_processing_time_ms = mean(
                    self.alert_metrics.alert_response_times
                )
            
            # Calculate alert success rate
            total_alert_attempts = (self.alert_metrics.total_alerts_sent + 
                                  self.alert_metrics.failed_alerts)
            if total_alert_attempts > 0:
                self.alert_metrics.alert_success_rate = (
                    self.alert_metrics.total_alerts_sent / total_alert_attempts * 100
                )
                
        except Exception as e:
            print(f"Error updating alert metrics: {e}")
    
    def _store_historical_data(self, timestamp: datetime) -> None:
        """Store current metrics in historical data."""
        timestamp_str = timestamp.isoformat()
        
        # Store processing history
        self.processing_history.append({
            'timestamp': timestamp_str,
            'messages_per_second': self.processing_metrics.messages_per_second,
            'decode_success_rate': self.processing_metrics.decode_success_rate,
            'avg_processing_time_ms': self.processing_metrics.avg_processing_time_ms,
            'messages_processed': self.processing_metrics.messages_processed
        })
        
        # Store memory history
        self.memory_history.append({
            'timestamp': timestamp_str,
            'current_usage_mb': self.memory_metrics.current_usage_mb,
            'usage_percent': self.memory_metrics.usage_percent,
            'aircraft_database_size': self.memory_metrics.aircraft_database_size,
            'message_queue_size': self.memory_metrics.message_queue_size,
            'gc_collections': self.memory_metrics.gc_collections
        })
        
        # Store network history
        self.network_history.append({
            'timestamp': timestamp_str,
            'bytes_per_second': self.network_metrics.bytes_received_per_second,
            'total_bytes': self.network_metrics.total_bytes_received,
            'connection_uptime': self.network_metrics.connection_uptime_seconds,
            'avg_message_size': self.network_metrics.avg_message_size_bytes
        })
        
        # Store alert history
        self.alert_history.append({
            'timestamp': timestamp_str,
            'alerts_per_hour': self.alert_metrics.alerts_per_hour,
            'alert_success_rate': self.alert_metrics.alert_success_rate,
            'avg_processing_time_ms': self.alert_metrics.avg_alert_processing_time_ms,
            'throttled_alerts': self.alert_metrics.throttled_alerts
        })
        
        # Store system history
        self.system_history.append({
            'timestamp': timestamp_str,
            'cpu_usage_percent': self.system_metrics.cpu_usage_percent,
            'disk_usage_percent': self.system_metrics.disk_usage_percent,
            'thread_count': self.system_metrics.thread_count,
            'uptime_seconds': self.system_metrics.uptime_seconds
        })
    
    def _check_performance_thresholds(self) -> None:
        """Check if any performance metrics exceed thresholds and trigger alerts."""
        alerts = []
        
        # Check CPU usage
        if self.system_metrics.cpu_usage_percent > self.thresholds['cpu_usage_percent']:
            alerts.append({
                'type': 'high_cpu_usage',
                'value': self.system_metrics.cpu_usage_percent,
                'threshold': self.thresholds['cpu_usage_percent'],
                'message': f"High CPU usage: {self.system_metrics.cpu_usage_percent:.1f}%"
            })
        
        # Check memory usage
        if self.memory_metrics.usage_percent > self.thresholds['memory_usage_percent']:
            alerts.append({
                'type': 'high_memory_usage',
                'value': self.memory_metrics.usage_percent,
                'threshold': self.thresholds['memory_usage_percent'],
                'message': f"High memory usage: {self.memory_metrics.usage_percent:.1f}%"
            })
        
        # Check decode success rate
        if self.processing_metrics.decode_success_rate < self.thresholds['decode_success_rate']:
            alerts.append({
                'type': 'low_decode_success_rate',
                'value': self.processing_metrics.decode_success_rate,
                'threshold': self.thresholds['decode_success_rate'],
                'message': f"Low decode success rate: {self.processing_metrics.decode_success_rate:.1f}%"
            })
        
        # Check message processing rate
        if self.processing_metrics.messages_per_second < self.thresholds['messages_per_second_min']:
            alerts.append({
                'type': 'low_message_rate',
                'value': self.processing_metrics.messages_per_second,
                'threshold': self.thresholds['messages_per_second_min'],
                'message': f"Low message rate: {self.processing_metrics.messages_per_second:.1f} msg/s"
            })
        
        # Check alert success rate
        if self.alert_metrics.alert_success_rate < self.thresholds['alert_success_rate']:
            alerts.append({
                'type': 'low_alert_success_rate',
                'value': self.alert_metrics.alert_success_rate,
                'threshold': self.thresholds['alert_success_rate'],
                'message': f"Low alert success rate: {self.alert_metrics.alert_success_rate:.1f}%"
            })
        
        # Trigger alert callbacks
        for alert in alerts:
            for callback in self._alert_callbacks:
                try:
                    callback(alert['type'], alert)
                except Exception as e:
                    print(f"Error in performance alert callback: {e}")
    
    # Public methods for recording metrics
    
    def record_message_batch(self, 
                           batch_size: int, 
                           valid_count: int, 
                           processing_time_ms: float) -> None:
        """Record message batch processing metrics."""
        with self._metrics_lock:
            self.processing_metrics.messages_processed += batch_size
            
            # Update decode success rate
            if batch_size > 0:
                success_rate = (valid_count / batch_size) * 100
                # Use exponential moving average for smoothing
                alpha = 0.1
                self.processing_metrics.decode_success_rate = (
                    alpha * success_rate + 
                    (1 - alpha) * self.processing_metrics.decode_success_rate
                )
            
            # Record processing time
            self.processing_metrics.batch_processing_times.append(processing_time_ms)
            
            # Add to message count tracker for rate calculation
            current_time = time.time()
            self._message_count_tracker.append((current_time, batch_size))
    
    def record_bytes_received(self, bytes_count: int) -> None:
        """Record bytes received from network sources."""
        with self._metrics_lock:
            self.network_metrics.total_bytes_received += bytes_count
            
            # Add to bytes tracker for rate calculation
            current_time = time.time()
            self._bytes_received_tracker.append((current_time, bytes_count))
    
    def record_connection_event(self, event_type: str, source_name: str) -> None:
        """Record connection events (connect, disconnect, reconnect)."""
        with self._metrics_lock:
            if event_type == 'connect':
                self.network_metrics.connection_uptime_seconds = 0
            elif event_type == 'reconnect':
                self.network_metrics.reconnection_count += 1
            elif event_type == 'disconnect':
                # Connection success rate calculation could be added here
                pass
    
    def record_alert_sent(self, processing_time_ms: float, success: bool) -> None:
        """Record watchlist alert metrics."""
        with self._metrics_lock:
            if success:
                self.alert_metrics.total_alerts_sent += 1
                self.alert_metrics.alert_response_times.append(processing_time_ms)
                
                # Add to alert count tracker
                current_time = time.time()
                self._alert_count_tracker.append(current_time)
            else:
                self.alert_metrics.failed_alerts += 1
    
    def record_alert_throttled(self) -> None:
        """Record throttled alert."""
        with self._metrics_lock:
            self.alert_metrics.throttled_alerts += 1
    
    def record_watchlist_check_time(self, time_ms: float) -> None:
        """Record time taken for watchlist checking."""
        with self._metrics_lock:
            # Use exponential moving average
            alpha = 0.1
            self.alert_metrics.watchlist_check_time_ms = (
                alpha * time_ms + 
                (1 - alpha) * self.alert_metrics.watchlist_check_time_ms
            )
    
    # Callback registration methods
    
    def set_aircraft_count_callback(self, callback: Callable[[], int]) -> None:
        """Set callback to get current aircraft count."""
        self._aircraft_count_callback = callback
    
    def set_message_queue_callback(self, callback: Callable[[], int]) -> None:
        """Set callback to get current message queue size."""
        self._message_queue_callback = callback
    
    def add_alert_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Add callback for performance alerts."""
        self._alert_callbacks.append(callback)
    
    def set_performance_thresholds(self, thresholds: Dict[str, float]) -> None:
        """Update performance alert thresholds."""
        self.thresholds.update(thresholds)
    
    # Data access methods
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics snapshot."""
        with self._metrics_lock:
            return {
                'processing': {
                    'messages_processed': self.processing_metrics.messages_processed,
                    'messages_per_second': round(self.processing_metrics.messages_per_second, 2),
                    'decode_success_rate': round(self.processing_metrics.decode_success_rate, 2),
                    'avg_processing_time_ms': round(self.processing_metrics.avg_processing_time_ms, 3),
                    'peak_processing_time_ms': round(self.processing_metrics.peak_processing_time_ms, 3)
                },
                'memory': {
                    'current_usage_mb': round(self.memory_metrics.current_usage_mb, 2),
                    'peak_usage_mb': round(self.memory_metrics.peak_usage_mb, 2),
                    'usage_percent': round(self.memory_metrics.usage_percent, 2),
                    'aircraft_database_size': self.memory_metrics.aircraft_database_size,
                    'aircraft_memory_mb': round(self.memory_metrics.aircraft_memory_mb, 2),
                    'message_queue_size': self.memory_metrics.message_queue_size,
                    'gc_collections': self.memory_metrics.gc_collections,
                    'memory_growth_rate_mb_per_hour': round(self.memory_metrics.memory_growth_rate_mb_per_hour, 3)
                },
                'network': {
                    'bytes_per_second': round(self.network_metrics.bytes_received_per_second, 2),
                    'total_bytes_received': self.network_metrics.total_bytes_received,
                    'connection_uptime_seconds': self.network_metrics.connection_uptime_seconds,
                    'reconnection_count': self.network_metrics.reconnection_count,
                    'connection_success_rate': round(self.network_metrics.connection_success_rate, 2),
                    'avg_message_size_bytes': round(self.network_metrics.avg_message_size_bytes, 2),
                    'network_latency_ms': round(self.network_metrics.network_latency_ms, 3)
                },
                'alerts': {
                    'total_alerts_sent': self.alert_metrics.total_alerts_sent,
                    'alerts_per_hour': round(self.alert_metrics.alerts_per_hour, 2),
                    'alert_success_rate': round(self.alert_metrics.alert_success_rate, 2),
                    'avg_alert_processing_time_ms': round(self.alert_metrics.avg_alert_processing_time_ms, 3),
                    'throttled_alerts': self.alert_metrics.throttled_alerts,
                    'failed_alerts': self.alert_metrics.failed_alerts,
                    'watchlist_check_time_ms': round(self.alert_metrics.watchlist_check_time_ms, 3)
                },
                'system': {
                    'cpu_usage_percent': round(self.system_metrics.cpu_usage_percent, 2),
                    'system_load_average': round(self.system_metrics.system_load_average, 2),
                    'disk_usage_percent': round(self.system_metrics.disk_usage_percent, 2),
                    'uptime_seconds': self.system_metrics.uptime_seconds,
                    'thread_count': self.system_metrics.thread_count,
                    'file_descriptor_count': self.system_metrics.file_descriptor_count,
                    'system_temperature_celsius': self.system_metrics.system_temperature_celsius
                },
                'timestamp': self._last_update.isoformat()
            }
    
    def get_historical_data(self, 
                          metric_type: str, 
                          hours: int = 1) -> List[Dict[str, Any]]:
        """Get historical data for specified metric type and time range."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        history_map = {
            'processing': self.processing_history,
            'memory': self.memory_history,
            'network': self.network_history,
            'alerts': self.alert_history,
            'system': self.system_history
        }
        
        if metric_type not in history_map:
            return []
        
        history = history_map[metric_type]
        
        return [
            entry for entry in history
            if datetime.fromisoformat(entry['timestamp']) >= cutoff_time
        ]
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get a summary of key performance indicators."""
        with self._metrics_lock:
            return {
                'overall_health': self._calculate_overall_health(),
                'key_metrics': {
                    'messages_per_second': round(self.processing_metrics.messages_per_second, 2),
                    'decode_success_rate': round(self.processing_metrics.decode_success_rate, 2),
                    'memory_usage_percent': round(self.memory_metrics.usage_percent, 2),
                    'cpu_usage_percent': round(self.system_metrics.cpu_usage_percent, 2),
                    'active_aircraft': self.memory_metrics.aircraft_database_size,
                    'alerts_per_hour': round(self.alert_metrics.alerts_per_hour, 2),
                    'uptime_hours': round(self.system_metrics.uptime_seconds / 3600, 2)
                },
                'performance_trends': self._calculate_performance_trends(),
                'last_updated': self._last_update.isoformat()
            }
    
    def _calculate_overall_health(self) -> str:
        """Calculate overall system health score."""
        score = 100
        
        # Deduct points for threshold violations
        if self.system_metrics.cpu_usage_percent > self.thresholds['cpu_usage_percent']:
            score -= 20
        
        if self.memory_metrics.usage_percent > self.thresholds['memory_usage_percent']:
            score -= 20
        
        if self.processing_metrics.decode_success_rate < self.thresholds['decode_success_rate']:
            score -= 25
        
        if self.processing_metrics.messages_per_second < self.thresholds['messages_per_second_min']:
            score -= 15
        
        if self.alert_metrics.alert_success_rate < self.thresholds['alert_success_rate']:
            score -= 10
        
        # Additional deductions for severe issues
        if self.memory_metrics.memory_growth_rate_mb_per_hour > 50:  # Memory leak indication
            score -= 15
        
        if self.network_metrics.reconnection_count > 10:  # Connection instability
            score -= 10
        
        # Return health status
        if score >= 90:
            return "excellent"
        elif score >= 75:
            return "good"
        elif score >= 60:
            return "fair"
        elif score >= 40:
            return "poor"
        else:
            return "critical"
    
    def _calculate_performance_trends(self) -> Dict[str, str]:
        """Calculate performance trends from historical data."""
        trends = {}
        
        # Analyze message processing trend
        if len(self.processing_history) >= 10:
            recent_rates = [entry['messages_per_second'] for entry in list(self.processing_history)[-10:]]
            older_rates = [entry['messages_per_second'] for entry in list(self.processing_history)[-20:-10]]
            
            if older_rates and recent_rates:
                recent_avg = mean(recent_rates)
                older_avg = mean(older_rates)
                
                if recent_avg > older_avg * 1.1:
                    trends['message_processing'] = 'improving'
                elif recent_avg < older_avg * 0.9:
                    trends['message_processing'] = 'declining'
                else:
                    trends['message_processing'] = 'stable'
        
        # Analyze memory usage trend
        if len(self.memory_history) >= 10:
            recent_usage = [entry['current_usage_mb'] for entry in list(self.memory_history)[-10:]]
            older_usage = [entry['current_usage_mb'] for entry in list(self.memory_history)[-20:-10]]
            
            if older_usage and recent_usage:
                recent_avg = mean(recent_usage)
                older_avg = mean(older_usage)
                
                if recent_avg > older_avg * 1.1:
                    trends['memory_usage'] = 'increasing'
                elif recent_avg < older_avg * 0.9:
                    trends['memory_usage'] = 'decreasing'
                else:
                    trends['memory_usage'] = 'stable'
        
        return trends
    
    def export_metrics(self, format_type: str = 'json') -> str:
        """Export current metrics in specified format."""
        metrics = self.get_current_metrics()
        
        if format_type.lower() == 'json':
            return json.dumps(metrics, indent=2)
        elif format_type.lower() == 'csv':
            # Simple CSV export for key metrics
            lines = ['metric,value,unit,timestamp']
            timestamp = metrics['timestamp']
            
            # Add key metrics
            lines.append(f"messages_per_second,{metrics['processing']['messages_per_second']},msg/s,{timestamp}")
            lines.append(f"decode_success_rate,{metrics['processing']['decode_success_rate']},%,{timestamp}")
            lines.append(f"memory_usage_mb,{metrics['memory']['current_usage_mb']},MB,{timestamp}")
            lines.append(f"cpu_usage_percent,{metrics['system']['cpu_usage_percent']},%,{timestamp}")
            lines.append(f"aircraft_count,{metrics['memory']['aircraft_database_size']},count,{timestamp}")
            
            return '\n'.join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    def __del__(self) -> None:
        """Cleanup when monitor is destroyed."""
        self.stop_monitoring()


# Global performance monitor instance
_global_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor


def initialize_performance_monitor(config: Dict[str, Any]) -> PerformanceMonitor:
    """Initialize the global performance monitor with configuration."""
    global _global_monitor
    
    performance_config = config.get('performance', {})
    
    _global_monitor = PerformanceMonitor(
        update_interval_sec=performance_config.get('monitoring_interval_sec', 1.0),
        history_retention_hours=performance_config.get('history_retention_hours', 24),
        enable_detailed_metrics=performance_config.get('enable_detailed_metrics', True)
    )
    
    # Set performance thresholds from config
    thresholds = performance_config.get('thresholds', {})
    if thresholds:
        _global_monitor.set_performance_thresholds(thresholds)
    
    return _global_monitor


def shutdown_performance_monitor() -> None:
    """Shutdown the global performance monitor."""
    global _global_monitor
    if _global_monitor:
        _global_monitor.stop_monitoring()
        _global_monitor = None