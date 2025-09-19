"""
Alert Throttler Module

Provides intelligent alert frequency control, deduplication, and batching
capabilities for the enhanced ADS-B watchlist monitoring system.
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
    
    # Batching configuration
    enable_batching: bool = True
    batch_size: int = 5
    batch_timeout: int = 60  # Send batch after this many seconds
    
    # Escalation rules
    enable_escalation: bool = True
    escalation_threshold: int = 3  # Number of alerts before escalating
    escalation_multiplier: float = 0.5  # Reduce interval by this factor


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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary format"""
        return {
            'aircraft_icao': self.aircraft_icao,
            'alert_type': self.alert_type.value,
            'alert_level': self.alert_level.value,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'watchlist_entry_id': getattr(self.watchlist_entry, 'value', None),
            'metadata': self.metadata
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
    
    def record_alert(self, alert_type: AlertType) -> None:
        """Record that an alert was sent"""
        self.last_alert = datetime.now()
        self.alert_count += 1
        self.alert_types[alert_type] += 1


class AlertThrottler:
    """
    Intelligent alert frequency control with deduplication and batching
    """
    
    def __init__(self, config: Optional[AlertConfig] = None):
        """
        Initialize alert throttler
        
        Args:
            config: AlertConfig object, uses defaults if None
        """
        self.config = config or AlertConfig()
        
        # Alert tracking
        self.alert_history: Dict[str, AlertHistory] = {}
        self.pending_alerts: deque[PendingAlert] = deque()
        self.alert_queue: List[PendingAlert] = []
        
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
            'escalations_triggered': 0,
            'batch_sends': 0,
            'last_alert_time': None,
            'last_batch_time': None
        }
        
        # Callbacks for sending alerts
        self.alert_callbacks: List[callable] = []
        
        # Last batch send time
        self.last_batch_send = datetime.now()
        
        logger.info("AlertThrottler initialized with intelligent frequency control")
    
    def should_send_alert(self, aircraft: EnhancedAircraft, alert_type: AlertType, 
                         watchlist_entry: Optional[WatchlistEntry] = None) -> bool:
        """
        Determine if an alert should be sent based on throttling rules
        
        Args:
            aircraft: Aircraft triggering the alert
            alert_type: Type of alert
            watchlist_entry: Associated watchlist entry
            
        Returns:
            True if alert should be sent, False if throttled
        """
        with self._lock:
            icao = aircraft.icao
            now = datetime.now()
            
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
            
            # Check if we're in a throttled state
            if history.next_allowed_time and now < history.next_allowed_time:
                return False
            
            # Get base interval for this alert type
            base_interval = self.config.type_intervals.get(alert_type, self.config.min_interval)
            
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
            
            # Check minimum interval
            if history.last_alert:
                time_since_last = (now - history.last_alert).total_seconds()
                if time_since_last < base_interval:
                    # Set next allowed time
                    history.next_allowed_time = history.last_alert + timedelta(seconds=base_interval)
                    return False
            
            # Check maximum interval (force update)
            if history.last_alert:
                time_since_last = (now - history.last_alert).total_seconds()
                if time_since_last >= self.config.max_interval:
                    logger.debug(f"Forcing alert for {icao} due to max interval ({time_since_last}s)")
                    return True
            
            return True
    
    def queue_alert(self, aircraft: EnhancedAircraft, alert_type: AlertType, 
                   message: str, watchlist_entry: Optional[WatchlistEntry] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Queue an alert for processing
        
        Args:
            aircraft: Aircraft triggering the alert
            alert_type: Type of alert
            message: Alert message
            watchlist_entry: Associated watchlist entry
            metadata: Additional alert metadata
            
        Returns:
            True if alert was queued, False if throttled
        """
        with self._lock:
            self.stats['total_alerts_received'] += 1
            self.stats['alerts_by_type'][alert_type.value] += 1
            
            # Check if alert should be sent
            if not self.should_send_alert(aircraft, alert_type, watchlist_entry):
                self.stats['total_alerts_throttled'] += 1
                logger.debug(f"Alert throttled for {aircraft.icao}: {alert_type.value}")
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
            
            # Create pending alert
            alert = PendingAlert(
                aircraft_icao=aircraft.icao,
                alert_type=alert_type,
                alert_level=alert_level,
                message=message,
                timestamp=datetime.now(),
                watchlist_entry=watchlist_entry,
                metadata=metadata or {}
            )
            
            # Update alert history
            history = self.alert_history[aircraft.icao]
            history.record_alert(alert_type)
            
            # Handle immediate vs batched sending
            if (alert_type in [AlertType.FIRST_DETECTION, AlertType.LOST_CONTACT] or
                alert_level == AlertLevel.CRITICAL or
                not self.config.enable_batching):
                
                # Send immediately
                self._send_alert_immediately(alert)
                
            else:
                # Add to batch queue
                self.alert_queue.append(alert)
                self.stats['total_alerts_batched'] += 1
                
                # Check if batch should be sent
                self._check_batch_send()
            
            return True
    
    def _send_alert_immediately(self, alert: PendingAlert) -> None:
        """
        Send an alert immediately
        
        Args:
            alert: Alert to send
        """
        self.stats['total_alerts_sent'] += 1
        self.stats['last_alert_time'] = datetime.now().isoformat()
        
        # Call all registered callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        logger.info(f"Sent immediate alert: {alert.aircraft_icao} - {alert.message}")
    
    def _check_batch_send(self) -> None:
        """Check if batched alerts should be sent"""
        if not self.alert_queue:
            return
        
        now = datetime.now()
        
        # Send if batch is full or timeout reached
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
    
    def force_batch_send(self) -> int:
        """
        Force sending of all queued alerts
        
        Returns:
            Number of alerts sent
        """
        with self._lock:
            count = len(self.alert_queue)
            if count > 0:
                self._send_batch()
            return count
    
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
            stats = self.stats.copy()
            stats.update({
                'active_aircraft_count': len(self.alert_history),
                'queued_alerts_count': len(self.alert_queue),
                'throttled_aircraft_count': len([
                    h for h in self.alert_history.values() 
                    if h.next_allowed_time and datetime.now() < h.next_allowed_time
                ]),
                'escalated_aircraft_count': len([
                    h for h in self.alert_history.values() 
                    if h.escalation_level > 0
                ]),
                'config': {
                    'min_interval': self.config.min_interval,
                    'max_interval': self.config.max_interval,
                    'enable_batching': self.config.enable_batching,
                    'batch_size': self.config.batch_size,
                    'batch_timeout': self.config.batch_timeout,
                    'enable_escalation': self.config.enable_escalation
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
                'escalations_triggered': 0,
                'batch_sends': 0,
                'last_alert_time': None,
                'last_batch_time': None
            }
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