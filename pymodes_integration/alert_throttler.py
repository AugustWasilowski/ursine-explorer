"""
Alert Throttler Module

Provides intelligent alert frequency control, deduplication, and batching
capabilities for the enhanced ADS-B watchlist monitoring system.

Enhanced with support for per-channel throttling, delivery tracking,
and integration with the new MeshtasticManager system.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import threading
import json
from collections import defaultdict, deque

from .aircraft import EnhancedAircraft
from .watchlist_monitor import WatchlistEntry

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class AlertType(Enum):
    """Types of alerts"""
    FIRST_DETECTION = "first_detection"
    POSITION_UPDATE = "position_update"
    ALTITUDE_CHANGE = "altitude_change"
    CALLSIGN_CHANGE = "callsign_change"
    PERIODIC_UPDATE = "periodic_update"
    LOST_CONTACT = "lost_contact"


@dataclass
class AlertConfig:
    """Configuration for alert throttling"""
    # Basic throttling intervals (seconds)
    min_interval: int = 300  # Minimum time between alerts for same aircraft
    max_interval: int = 3600  # Maximum time before forcing an update
    
    # Alert type specific intervals
    type_intervals: Dict[AlertType, int] = field(default_factory=lambda: {
        AlertType.FIRST_DETECTION: 0,      # Always send immediately
        AlertType.POSITION_UPDATE: 600,    # Every 10 minutes
        AlertType.ALTITUDE_CHANGE: 300,    # Every 5 minutes
        AlertType.CALLSIGN_CHANGE: 60,     # Every minute
        AlertType.PERIODIC_UPDATE: 1800,   # Every 30 minutes
        AlertType.LOST_CONTACT: 0          # Always send immediately
    })
    
    # Priority-based multipliers
    priority_multipliers: Dict[int, float] = field(default_factory=lambda: {
        1: 2.0,    # Low priority: double intervals
        2: 1.0,    # Medium priority: normal intervals
        3: 0.5,    # High priority: half intervals
        4: 0.1     # Critical priority: very short intervals
    })
    
    # Per-channel throttling configuration
    channel_throttling: Dict[str, Dict[str, int]] = field(default_factory=dict)
    enable_per_channel_throttling: bool = True
    
    # Batching configuration
    enable_batching: bool = True
    batch_size: int = 5
    batch_timeout: int = 60  # Send batch after this many seconds
    per_channel_batching: bool = True  # Separate batches per channel
    
    # Escalation rules
    enable_escalation: bool = True
    escalation_threshold: int = 3  # Number of alerts before escalating
    escalation_multiplier: float = 0.5  # Reduce interval by this factor
    
    # Delivery tracking
    enable_delivery_tracking: bool = True
    delivery_timeout: int = 300  # Consider delivery failed after this many seconds
    max_delivery_retries: int = 3  # Maximum retry attempts for failed deliveries


@dataclass
class PendingAlert:
    """Alert waiting to be sent"""
    aircraft_icao: str
    alert_type: AlertType
    alert_level: AlertLevel
    message: str
    timestamp: datetime
    watchlist_entry: Optional[WatchlistEntry] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Enhanced delivery tracking fields
    alert_id: Optional[str] = None
    channel: Optional[str] = None
    delivery_attempts: int = 0
    max_delivery_attempts: int = 3
    last_delivery_attempt: Optional[datetime] = None
    delivery_status: str = "pending"  # pending, sent, delivered, failed
    delivery_error: Optional[str] = None
    
    def __post_init__(self):
        """Generate alert ID if not provided"""
        if not self.alert_id:
            import uuid
            self.alert_id = str(uuid.uuid4())[:8]
    
    @property
    def can_retry_delivery(self) -> bool:
        """Check if delivery can be retried"""
        return (self.delivery_attempts < self.max_delivery_attempts and 
                self.delivery_status in ["pending", "failed"])
    
    def record_delivery_attempt(self, success: bool, error: Optional[str] = None) -> None:
        """Record a delivery attempt"""
        self.delivery_attempts += 1
        self.last_delivery_attempt = datetime.now()
        
        if success:
            self.delivery_status = "sent"
            self.delivery_error = None
        else:
            self.delivery_status = "failed" if self.delivery_attempts >= self.max_delivery_attempts else "pending"
            self.delivery_error = error
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary format"""
        return {
            'alert_id': self.alert_id,
            'aircraft_icao': self.aircraft_icao,
            'alert_type': self.alert_type.value,
            'alert_level': self.alert_level.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'watchlist_entry_id': getattr(self.watchlist_entry, 'value', None),
            'metadata': self.metadata,
            'channel': self.channel,
            'delivery_attempts': self.delivery_attempts,
            'delivery_status': self.delivery_status,
            'delivery_error': self.delivery_error,
            'last_delivery_attempt': self.last_delivery_attempt.isoformat() if self.last_delivery_attempt else None
        }


@dataclass
class AlertHistory:
    """History of alerts for an aircraft"""
    aircraft_icao: str
    first_alert: datetime
    last_alert: datetime
    alert_count: int = 0
    alert_types: Dict[AlertType, int] = field(default_factory=lambda: defaultdict(int))
    escalation_level: int = 0
    is_throttled: bool = False
    next_allowed_time: Optional[datetime] = None
    
    # Per-channel tracking
    channel_history: Dict[str, Dict[str, Any]] = field(default_factory=lambda: defaultdict(dict))
    delivery_stats: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    
    def record_alert(self, alert_type: AlertType, channel: Optional[str] = None) -> None:
        """Record that an alert was sent"""
        self.last_alert = datetime.now()
        self.alert_count += 1
        self.alert_types[alert_type] += 1
        
        # Track per-channel statistics
        if channel:
            if channel not in self.channel_history:
                self.channel_history[channel] = {
                    'first_alert': datetime.now(),
                    'last_alert': datetime.now(),
                    'alert_count': 0,
                    'next_allowed_time': None
                }
            
            self.channel_history[channel]['last_alert'] = datetime.now()
            self.channel_history[channel]['alert_count'] += 1
    
    def record_delivery_result(self, channel: str, success: bool) -> None:
        """Record delivery result for statistics"""
        if success:
            self.delivery_stats[f"{channel}_delivered"] += 1
        else:
            self.delivery_stats[f"{channel}_failed"] += 1
    
    def is_channel_throttled(self, channel: str) -> bool:
        """Check if alerts are throttled for a specific channel"""
        if channel not in self.channel_history:
            return False
        
        next_allowed = self.channel_history[channel].get('next_allowed_time')
        if next_allowed and datetime.now() < next_allowed:
            return True
        
        return False
    
    def set_channel_throttle(self, channel: str, next_allowed_time: datetime) -> None:
        """Set throttle time for a specific channel"""
        if channel not in self.channel_history:
            self.channel_history[channel] = {
                'first_alert': datetime.now(),
                'last_alert': datetime.now(),
                'alert_count': 0,
                'next_allowed_time': next_allowed_time
            }
        else:
            self.channel_history[channel]['next_allowed_time'] = next_allowed_time


class AlertThrottler:
    """
    Intelligent alert frequency control with deduplication and batching.
    
    Enhanced with per-channel throttling, delivery tracking, and
    integration with MeshtasticManager for improved reliability.
    """
    
    def __init__(self, config: Optional[AlertConfig] = None, meshtastic_manager=None):
        """
        Initialize alert throttler
        
        Args:
            config: AlertConfig object, uses defaults if None
            meshtastic_manager: Optional MeshtasticManager for delivery tracking
        """
        self.config = config or AlertConfig()
        self.meshtastic_manager = meshtastic_manager
        
        # Alert tracking
        self.alert_history: Dict[str, AlertHistory] = {}
        self.pending_alerts: deque[PendingAlert] = deque()
        self.alert_queue: List[PendingAlert] = []
        
        # Per-channel queues for enhanced batching
        self.channel_queues: Dict[str, List[PendingAlert]] = defaultdict(list)
        self.channel_batch_times: Dict[str, datetime] = {}
        
        # Delivery tracking
        self.pending_deliveries: Dict[str, PendingAlert] = {}  # alert_id -> alert
        self.failed_deliveries: List[PendingAlert] = []
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Statistics
        self.stats = {
            'total_alerts_received': 0,
            'total_alerts_sent': 0,
            'total_alerts_throttled': 0,
            'total_alerts_batched': 0,
            'alerts_by_type': {at.value: 0 for at in AlertType},
            'alerts_by_level': {al.value: 0 for al in AlertLevel},
            'alerts_by_channel': defaultdict(int),
            'delivery_success_rate': 0.0,
            'escalations_triggered': 0,
            'batch_sends': 0,
            'channel_batch_sends': defaultdict(int),
            'delivery_retries': 0,
            'last_alert_time': None,
            'last_batch_time': None
        }
        
        # Callbacks for sending alerts
        self.alert_callbacks: List[callable] = []
        
        # Last batch send time
        self.last_batch_send = datetime.now()
        
        logger.info("AlertThrottler initialized with enhanced per-channel throttling and delivery tracking")
    
    def set_meshtastic_manager(self, meshtastic_manager) -> None:
        """
        Set or update the MeshtasticManager instance
        
        Args:
            meshtastic_manager: MeshtasticManager instance for delivery tracking
        """
        self.meshtastic_manager = meshtastic_manager
        logger.info("MeshtasticManager updated for alert throttler")
    
    def configure_channel_throttling(self, channel_config: Dict[str, Dict[str, int]]) -> None:
        """
        Configure per-channel throttling settings
        
        Args:
            channel_config: Dictionary mapping channel names to throttling settings
                          e.g., {"SecureAlerts": {"min_interval": 60, "max_interval": 1800}}
        """
        with self._lock:
            self.config.channel_throttling.update(channel_config)
            logger.info(f"Updated channel throttling configuration: {channel_config}")
    
    def get_channel_for_alert(self, aircraft: EnhancedAircraft, watchlist_entry: Optional[WatchlistEntry] = None) -> str:
        """
        Determine the appropriate channel for an alert
        
        Args:
            aircraft: Aircraft triggering the alert
            watchlist_entry: Associated watchlist entry
            
        Returns:
            Channel name to use for this alert
        """
        if watchlist_entry:
            # Use priority-based channel selection
            if watchlist_entry.priority >= 4:
                return "SecureAlerts"  # Critical alerts go to secure channel
            elif watchlist_entry.priority >= 3:
                return "SecureAlerts"  # High priority alerts go to secure channel
            else:
                return "LongFast"  # Normal alerts go to default channel
        
        return "LongFast"  # Default channel
    
    def should_send_alert(self, aircraft: EnhancedAircraft, alert_type: AlertType, 
                         watchlist_entry: Optional[WatchlistEntry] = None, 
                         channel: Optional[str] = None) -> bool:
        """
        Determine if an alert should be sent based on throttling rules
        
        Args:
            aircraft: Aircraft triggering the alert
            alert_type: Type of alert
            watchlist_entry: Associated watchlist entry
            channel: Optional specific channel to check throttling for
            
        Returns:
            True if alert should be sent, False if throttled
        """
        with self._lock:
            icao = aircraft.icao
            now = datetime.now()
            
            # Determine channel if not provided
            if not channel:
                channel = self.get_channel_for_alert(aircraft, watchlist_entry)
            
            # Get or create alert history
            if icao not in self.alert_history:
                self.alert_history[icao] = AlertHistory(
                    aircraft_icao=icao,
                    first_alert=now,
                    last_alert=now
                )
            
            history = self.alert_history[icao]
            
            # Always allow first detection and lost contact alerts
            if alert_type in [AlertType.FIRST_DETECTION, AlertType.LOST_CONTACT]:
                return True
            
            # Check per-channel throttling if enabled
            if self.config.enable_per_channel_throttling and history.is_channel_throttled(channel):
                return False
            
            # Check global throttling
            if history.next_allowed_time and now < history.next_allowed_time:
                return False
            
            # Get base interval for this alert type
            base_interval = self.config.type_intervals.get(alert_type, self.config.min_interval)
            
            # Apply channel-specific throttling if configured
            if channel in self.config.channel_throttling:
                channel_config = self.config.channel_throttling[channel]
                channel_min_interval = channel_config.get('min_interval', base_interval)
                base_interval = max(base_interval, channel_min_interval)
            
            # Apply priority multiplier if watchlist entry available
            if watchlist_entry:
                priority_multiplier = self.config.priority_multipliers.get(
                    watchlist_entry.priority, 1.0
                )
                base_interval = int(base_interval * priority_multiplier)
            
            # Apply escalation if enabled
            if self.config.enable_escalation and history.alert_count >= self.config.escalation_threshold:
                escalation_factor = self.config.escalation_multiplier ** history.escalation_level
                base_interval = int(base_interval * escalation_factor)
                
                if history.escalation_level == 0:  # First escalation
                    self.stats['escalations_triggered'] += 1
                    logger.info(f"Alert escalation triggered for {icao} (count: {history.alert_count})")
                
                history.escalation_level += 1
            
            # Check minimum interval (global)
            if history.last_alert:
                time_since_last = (now - history.last_alert).total_seconds()
                if time_since_last < base_interval:
                    # Set next allowed time
                    history.next_allowed_time = history.last_alert + timedelta(seconds=base_interval)
                    return False
            
            # Check per-channel minimum interval
            if channel in history.channel_history:
                channel_history = history.channel_history[channel]
                if channel_history.get('last_alert'):
                    time_since_channel_alert = (now - channel_history['last_alert']).total_seconds()
                    if time_since_channel_alert < base_interval:
                        # Set channel-specific throttle
                        next_allowed = channel_history['last_alert'] + timedelta(seconds=base_interval)
                        history.set_channel_throttle(channel, next_allowed)
                        return False
            
            # Check maximum interval (force update)
            if history.last_alert:
                time_since_last = (now - history.last_alert).total_seconds()
                max_interval = self.config.channel_throttling.get(channel, {}).get('max_interval', self.config.max_interval)
                if time_since_last >= max_interval:
                    logger.debug(f"Forcing alert for {icao} on {channel} due to max interval ({time_since_last}s)")
                    return True
            
            return True
    
    def queue_alert(self, aircraft: EnhancedAircraft, alert_type: AlertType, 
                   message: str, watchlist_entry: Optional[WatchlistEntry] = None,
                   metadata: Optional[Dict[str, Any]] = None, 
                   channel: Optional[str] = None) -> bool:
        """
        Queue an alert for processing
        
        Args:
            aircraft: Aircraft triggering the alert
            alert_type: Type of alert
            message: Alert message
            watchlist_entry: Associated watchlist entry
            metadata: Additional alert metadata
            channel: Optional specific channel to use
            
        Returns:
            True if alert was queued, False if throttled
        """
        with self._lock:
            self.stats['total_alerts_received'] += 1
            self.stats['alerts_by_type'][alert_type.value] += 1
            
            # Determine channel if not provided
            if not channel:
                channel = self.get_channel_for_alert(aircraft, watchlist_entry)
            
            # Check if alert should be sent
            if not self.should_send_alert(aircraft, alert_type, watchlist_entry, channel):
                self.stats['total_alerts_throttled'] += 1
                logger.debug(f"Alert throttled for {aircraft.icao} on {channel}: {alert_type.value}")
                return False
            
            # Determine alert level based on priority
            alert_level = AlertLevel.MEDIUM  # Default
            if watchlist_entry:
                if watchlist_entry.priority == 4:
                    alert_level = AlertLevel.CRITICAL
                elif watchlist_entry.priority == 3:
                    alert_level = AlertLevel.HIGH
                elif watchlist_entry.priority == 1:
                    alert_level = AlertLevel.LOW
            
            self.stats['alerts_by_level'][alert_level.value] += 1
            self.stats['alerts_by_channel'][channel] += 1
            
            # Create pending alert with enhanced fields
            alert = PendingAlert(
                aircraft_icao=aircraft.icao,
                alert_type=alert_type,
                alert_level=alert_level,
                message=message,
                timestamp=datetime.now(),
                watchlist_entry=watchlist_entry,
                metadata=metadata or {},
                channel=channel,
                max_delivery_attempts=self.config.max_delivery_retries
            )
            
            # Update alert history
            history = self.alert_history[aircraft.icao]
            history.record_alert(alert_type, channel)
            
            # Handle immediate vs batched sending
            if (alert_type in [AlertType.FIRST_DETECTION, AlertType.LOST_CONTACT] or
                alert_level == AlertLevel.CRITICAL or
                not self.config.enable_batching):
                
                # Send immediately
                self._send_alert_immediately(alert)
                
            else:
                # Add to appropriate queue
                if self.config.per_channel_batching:
                    # Add to channel-specific queue
                    self.channel_queues[channel].append(alert)
                    if channel not in self.channel_batch_times:
                        self.channel_batch_times[channel] = datetime.now()
                else:
                    # Add to global queue
                    self.alert_queue.append(alert)
                
                self.stats['total_alerts_batched'] += 1
                
                # Check if batch should be sent
                self._check_batch_send()
            
            return True
    
    def _send_alert_immediately(self, alert: PendingAlert) -> None:
        """
        Send an alert immediately with delivery tracking
        
        Args:
            alert: Alert to send
        """
        self.stats['total_alerts_sent'] += 1
        self.stats['last_alert_time'] = datetime.now().isoformat()
        
        # Track pending delivery if enabled
        if self.config.enable_delivery_tracking and alert.alert_id:
            self.pending_deliveries[alert.alert_id] = alert
        
        # Send through MeshtasticManager if available
        success = False
        error_message = None
        
        if self.meshtastic_manager:
            try:
                # Create aircraft object for MeshtasticManager
                from .aircraft import EnhancedAircraft
                now = datetime.now()
                
                alert_aircraft = EnhancedAircraft(
                    icao=alert.aircraft_icao,
                    first_seen=now,
                    last_seen=now,
                    callsign=alert.metadata.get('callsign'),
                    latitude=alert.metadata.get('lat'),
                    longitude=alert.metadata.get('lon'),
                    altitude_baro=alert.metadata.get('altitude'),
                    ground_speed=alert.metadata.get('speed'),
                    track_angle=alert.metadata.get('heading')
                )
                
                # Add alert metadata
                alert_aircraft.alert_metadata = {
                    'alert_id': alert.alert_id,
                    'alert_type': alert.alert_type.value,
                    'alert_level': alert.alert_level.value,
                    'channel': alert.channel,
                    'message': alert.message
                }
                
                success = self.meshtastic_manager.send_alert(alert_aircraft, alert.alert_type.value)
                
            except Exception as e:
                error_message = str(e)
                logger.error(f"Error sending alert through MeshtasticManager: {e}")
        
        # Record delivery attempt
        alert.record_delivery_attempt(success, error_message)
        
        # Update statistics
        if success:
            if alert.aircraft_icao in self.alert_history:
                self.alert_history[alert.aircraft_icao].record_delivery_result(alert.channel, True)
        else:
            if alert.aircraft_icao in self.alert_history:
                self.alert_history[alert.aircraft_icao].record_delivery_result(alert.channel, False)
            
            # Add to failed deliveries for retry
            if alert.can_retry_delivery:
                self.failed_deliveries.append(alert)
        
        # Call registered callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        logger.info(f"Sent immediate alert: {alert.aircraft_icao} on {alert.channel} - {alert.message} (success: {success})")
    
    def _check_batch_send(self) -> None:
        """Check if batched alerts should be sent"""
        now = datetime.now()
        
        if self.config.per_channel_batching:
            # Check each channel queue
            for channel, queue in self.channel_queues.items():
                if not queue:
                    continue
                
                batch_start_time = self.channel_batch_times.get(channel, now)
                should_send = (
                    len(queue) >= self.config.batch_size or
                    (now - batch_start_time).total_seconds() >= self.config.batch_timeout
                )
                
                if should_send:
                    self._send_channel_batch(channel)
        else:
            # Check global queue
            if not self.alert_queue:
                return
            
            should_send = (
                len(self.alert_queue) >= self.config.batch_size or
                (now - self.last_batch_send).total_seconds() >= self.config.batch_timeout
            )
            
            if should_send:
                self._send_batch()
    
    def _send_batch(self) -> None:
        """Send all queued alerts as a batch"""
        if not self.alert_queue:
            return
        
        batch = self.alert_queue.copy()
        self.alert_queue.clear()
        self.last_batch_send = datetime.now()
        
        self.stats['batch_sends'] += 1
        self.stats['total_alerts_sent'] += len(batch)
        self.stats['last_batch_time'] = self.last_batch_send.isoformat()
        
        # Group alerts by priority for better organization
        batch_by_priority = defaultdict(list)
        for alert in batch:
            batch_by_priority[alert.alert_level].append(alert)
        
        # Send batch through callbacks
        for callback in self.alert_callbacks:
            try:
                callback(batch)
            except Exception as e:
                logger.error(f"Error in batch alert callback: {e}")
        
        logger.info(f"Sent batch of {len(batch)} alerts")
    
    def _send_channel_batch(self, channel: str) -> None:
        """Send all queued alerts for a specific channel as a batch"""
        if channel not in self.channel_queues or not self.channel_queues[channel]:
            return
        
        batch = self.channel_queues[channel].copy()
        self.channel_queues[channel].clear()
        
        if channel in self.channel_batch_times:
            del self.channel_batch_times[channel]
        
        self.stats['channel_batch_sends'][channel] += 1
        self.stats['total_alerts_sent'] += len(batch)
        self.stats['last_batch_time'] = datetime.now().isoformat()
        
        # Track pending deliveries if enabled
        if self.config.enable_delivery_tracking:
            for alert in batch:
                if alert.alert_id:
                    self.pending_deliveries[alert.alert_id] = alert
        
        # Send batch through callbacks
        for callback in self.alert_callbacks:
            try:
                callback(batch)
            except Exception as e:
                logger.error(f"Error in channel batch alert callback: {e}")
        
        logger.info(f"Sent channel batch of {len(batch)} alerts on {channel}")
    
    def force_batch_send(self) -> int:
        """
        Force sending of all queued alerts
        
        Returns:
            Number of alerts sent
        """
        with self._lock:
            total_sent = 0
            
            if self.config.per_channel_batching:
                # Send all channel batches
                for channel in list(self.channel_queues.keys()):
                    if self.channel_queues[channel]:
                        count = len(self.channel_queues[channel])
                        self._send_channel_batch(channel)
                        total_sent += count
            else:
                # Send global batch
                count = len(self.alert_queue)
                if count > 0:
                    self._send_batch()
                    total_sent = count
            
            return total_sent
    
    def retry_failed_deliveries(self) -> int:
        """
        Retry failed alert deliveries
        
        Returns:
            Number of alerts retried
        """
        with self._lock:
            if not self.failed_deliveries:
                return 0
            
            retry_count = 0
            remaining_failures = []
            
            for alert in self.failed_deliveries:
                if alert.can_retry_delivery:
                    logger.info(f"Retrying failed alert delivery: {alert.alert_id}")
                    self._send_alert_immediately(alert)
                    retry_count += 1
                    self.stats['delivery_retries'] += 1
                else:
                    # Max retries reached, keep in failed list
                    remaining_failures.append(alert)
            
            self.failed_deliveries = remaining_failures
            
            if retry_count > 0:
                logger.info(f"Retried {retry_count} failed alert deliveries")
            
            return retry_count
    
    def confirm_delivery(self, alert_id: str, success: bool) -> bool:
        """
        Confirm delivery status for an alert
        
        Args:
            alert_id: ID of the alert to confirm
            success: Whether delivery was successful
            
        Returns:
            True if alert was found and updated
        """
        with self._lock:
            if alert_id not in self.pending_deliveries:
                return False
            
            alert = self.pending_deliveries[alert_id]
            
            if success:
                alert.delivery_status = "delivered"
                # Update statistics
                if alert.aircraft_icao in self.alert_history:
                    self.alert_history[alert.aircraft_icao].record_delivery_result(alert.channel, True)
            else:
                alert.delivery_status = "failed"
                # Add to retry queue if possible
                if alert.can_retry_delivery:
                    self.failed_deliveries.append(alert)
                
                # Update statistics
                if alert.aircraft_icao in self.alert_history:
                    self.alert_history[alert.aircraft_icao].record_delivery_result(alert.channel, False)
            
            # Remove from pending
            del self.pending_deliveries[alert_id]
            
            return True
    
    def add_alert_callback(self, callback: callable) -> None:
        """
        Add a callback function for alert sending
        
        Args:
            callback: Function that takes either PendingAlert or List[PendingAlert]
        """
        self.alert_callbacks.append(callback)
        logger.debug(f"Added alert callback: {callback.__name__}")
    
    def remove_alert_callback(self, callback: callable) -> bool:
        """
        Remove an alert callback
        
        Args:
            callback: Callback function to remove
            
        Returns:
            True if callback was removed, False if not found
        """
        try:
            self.alert_callbacks.remove(callback)
            logger.debug(f"Removed alert callback: {callback.__name__}")
            return True
        except ValueError:
            return False
    
    def is_throttled(self, aircraft_icao: str) -> bool:
        """
        Check if alerts for an aircraft are currently throttled
        
        Args:
            aircraft_icao: ICAO code of aircraft
            
        Returns:
            True if throttled, False otherwise
        """
        with self._lock:
            if aircraft_icao not in self.alert_history:
                return False
            
            history = self.alert_history[aircraft_icao]
            
            if history.next_allowed_time:
                return datetime.now() < history.next_allowed_time
            
            return False
    
    def get_throttle_status(self, aircraft_icao: str) -> Dict[str, Any]:
        """
        Get detailed throttle status for an aircraft
        
        Args:
            aircraft_icao: ICAO code of aircraft
            
        Returns:
            Dictionary with throttle status information
        """
        with self._lock:
            if aircraft_icao not in self.alert_history:
                return {
                    'is_throttled': False,
                    'alert_count': 0,
                    'escalation_level': 0
                }
            
            history = self.alert_history[aircraft_icao]
            now = datetime.now()
            
            return {
                'is_throttled': history.next_allowed_time and now < history.next_allowed_time,
                'next_allowed_time': history.next_allowed_time.isoformat() if history.next_allowed_time else None,
                'alert_count': history.alert_count,
                'escalation_level': history.escalation_level,
                'first_alert': history.first_alert.isoformat(),
                'last_alert': history.last_alert.isoformat(),
                'alert_types': dict(history.alert_types),
                'time_since_last_alert': (now - history.last_alert).total_seconds() if history.last_alert else None
            }
    
    def cleanup_old_history(self, max_age_hours: int = 24) -> int:
        """
        Clean up old alert history entries
        
        Args:
            max_age_hours: Maximum age of history entries to keep
            
        Returns:
            Number of entries removed
        """
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            
            old_entries = [
                icao for icao, history in self.alert_history.items()
                if history.last_alert < cutoff_time
            ]
            
            for icao in old_entries:
                del self.alert_history[icao]
            
            if old_entries:
                logger.info(f"Cleaned up {len(old_entries)} old alert history entries")
            
            return len(old_entries)
    
    def update_config(self, new_config: AlertConfig) -> None:
        """
        Update throttler configuration
        
        Args:
            new_config: New AlertConfig object
        """
        with self._lock:
            self.config = new_config
            logger.info("Alert throttler configuration updated")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get alert throttler statistics"""
        with self._lock:
            # Calculate delivery success rate
            total_delivered = sum(
                h.delivery_stats.get(f"{ch}_delivered", 0) 
                for h in self.alert_history.values() 
                for ch in h.channel_history.keys()
            )
            total_failed = sum(
                h.delivery_stats.get(f"{ch}_failed", 0) 
                for h in self.alert_history.values() 
                for ch in h.channel_history.keys()
            )
            total_attempts = total_delivered + total_failed
            success_rate = (total_delivered / total_attempts * 100) if total_attempts > 0 else 0.0
            
            stats = self.stats.copy()
            stats['delivery_success_rate'] = round(success_rate, 2)
            
            stats.update({
                'active_aircraft_count': len(self.alert_history),
                'queued_alerts_count': len(self.alert_queue),
                'channel_queue_counts': {ch: len(q) for ch, q in self.channel_queues.items()},
                'pending_deliveries_count': len(self.pending_deliveries),
                'failed_deliveries_count': len(self.failed_deliveries),
                'throttled_aircraft_count': len([
                    h for h in self.alert_history.values() 
                    if h.next_allowed_time and datetime.now() < h.next_allowed_time
                ]),
                'channel_throttled_aircraft': {
                    channel: len([
                        h for h in self.alert_history.values()
                        if h.is_channel_throttled(channel)
                    ])
                    for channel in set().union(*[h.channel_history.keys() for h in self.alert_history.values()])
                },
                'escalated_aircraft_count': len([
                    h for h in self.alert_history.values() 
                    if h.escalation_level > 0
                ]),
                'meshtastic_manager_available': self.meshtastic_manager is not None,
                'config': {
                    'min_interval': self.config.min_interval,
                    'max_interval': self.config.max_interval,
                    'enable_batching': self.config.enable_batching,
                    'per_channel_batching': self.config.per_channel_batching,
                    'batch_size': self.config.batch_size,
                    'batch_timeout': self.config.batch_timeout,
                    'enable_escalation': self.config.enable_escalation,
                    'enable_per_channel_throttling': self.config.enable_per_channel_throttling,
                    'enable_delivery_tracking': self.config.enable_delivery_tracking,
                    'channel_throttling': dict(self.config.channel_throttling)
                }
            })
            return stats
    
    def reset_statistics(self) -> None:
        """Reset all statistics counters"""
        with self._lock:
            self.stats = {
                'total_alerts_received': 0,
                'total_alerts_sent': 0,
                'total_alerts_throttled': 0,
                'total_alerts_batched': 0,
                'alerts_by_type': {at.value: 0 for at in AlertType},
                'alerts_by_level': {al.value: 0 for al in AlertLevel},
                'alerts_by_channel': defaultdict(int),
                'delivery_success_rate': 0.0,
                'escalations_triggered': 0,
                'batch_sends': 0,
                'channel_batch_sends': defaultdict(int),
                'delivery_retries': 0,
                'last_alert_time': None,
                'last_batch_time': None
            }
            
            # Reset delivery statistics in alert history
            for history in self.alert_history.values():
                history.delivery_stats.clear()
            
            logger.info("Alert throttler statistics reset")
    
    def reset_aircraft_history(self, aircraft_icao: str) -> bool:
        """
        Reset alert history for a specific aircraft
        
        Args:
            aircraft_icao: ICAO code of aircraft
            
        Returns:
            True if history was reset, False if aircraft not found
        """
        with self._lock:
            if aircraft_icao in self.alert_history:
                del self.alert_history[aircraft_icao]
                logger.info(f"Reset alert history for aircraft {aircraft_icao}")
                return True
            return False