"""
Enhanced Meshtastic Interface Module

Provides improved Meshtastic communication with better error handling,
connection monitoring, automatic reconnection, and alert queuing for offline periods.
"""

import logging
import serial
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Deque
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import json
import os

from .alert_throttler import PendingAlert, AlertLevel

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Meshtastic connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class MeshtasticConfig:
    """Configuration for Meshtastic interface"""
    port: str = "/dev/ttyUSB0"
    baud_rate: int = 115200
    timeout: float = 2.0
    write_timeout: float = 2.0
    
    # Connection monitoring
    enable_monitoring: bool = True
    heartbeat_interval: int = 30  # seconds
    connection_timeout: int = 10  # seconds
    
    # Reconnection settings
    enable_auto_reconnect: bool = True
    reconnect_delay: int = 5  # seconds
    max_reconnect_attempts: int = 10
    reconnect_backoff_multiplier: float = 1.5
    max_reconnect_delay: int = 300  # 5 minutes
    
    # Queue settings
    enable_offline_queue: bool = True
    max_queue_size: int = 1000
    queue_persistence_file: Optional[str] = "meshtastic_queue.json"
    
    # Message formatting
    message_prefix: str = "ADSB"
    include_timestamp: bool = True
    max_message_length: int = 200


@dataclass
class QueuedMessage:
    """Message queued for sending when connection is restored"""
    message: str
    timestamp: datetime
    priority: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueuedMessage':
        """Create from dictionary"""
        return cls(
            message=data['message'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            priority=data.get('priority', 1),
            retry_count=data.get('retry_count', 0),
            max_retries=data.get('max_retries', 3)
        )


class MeshtasticInterface:
    """
    Enhanced Meshtastic interface with improved error handling and reliability
    """
    
    def __init__(self, config: Optional[MeshtasticConfig] = None):
        """
        Initialize Meshtastic interface
        
        Args:
            config: MeshtasticConfig object, uses defaults if None
        """
        self.config = config or MeshtasticConfig()
        
        # Connection management
        self.serial_conn: Optional[serial.Serial] = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.last_successful_send = datetime.now()
        self.connection_attempts = 0
        self.last_connection_attempt = datetime.now()
        
        # Threading
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._queue_thread: Optional[threading.Thread] = None
        
        # Message queue
        self.message_queue: Deque[QueuedMessage] = deque()
        self.failed_messages: List[QueuedMessage] = []
        
        # Statistics
        self.stats = {
            'total_messages_sent': 0,
            'total_messages_queued': 0,
            'total_messages_failed': 0,
            'connection_attempts': 0,
            'successful_connections': 0,
            'connection_failures': 0,
            'reconnections': 0,
            'queue_overflows': 0,
            'last_send_time': None,
            'last_connection_time': None,
            'uptime_seconds': 0,
            'downtime_seconds': 0
        }
        
        # Callbacks
        self.connection_callbacks: List[Callable[[ConnectionState], None]] = []
        self.message_callbacks: List[Callable[[str, bool], None]] = []  # (message, success)
        
        # Load persisted queue
        if self.config.enable_offline_queue and self.config.queue_persistence_file:
            self._load_queue_from_file()
        
        logger.info(f"MeshtasticInterface initialized for {self.config.port}")
    
    def start(self) -> bool:
        """
        Start the Meshtastic interface
        
        Returns:
            True if started successfully, False otherwise
        """
        with self._lock:
            if self._monitor_thread and self._monitor_thread.is_alive():
                logger.warning("MeshtasticInterface already started")
                return True
            
            self._stop_event.clear()
            
            # Start connection monitoring thread
            if self.config.enable_monitoring:
                self._monitor_thread = threading.Thread(
                    target=self._connection_monitor_loop,
                    name="MeshtasticMonitor",
                    daemon=True
                )
                self._monitor_thread.start()
            
            # Start queue processing thread
            if self.config.enable_offline_queue:
                self._queue_thread = threading.Thread(
                    target=self._queue_processor_loop,
                    name="MeshtasticQueue",
                    daemon=True
                )
                self._queue_thread.start()
            
            # Initial connection attempt
            success = self.connect()
            
            logger.info(f"MeshtasticInterface started (connected: {success})")
            return True
    
    def stop(self) -> None:
        """Stop the Meshtastic interface"""
        with self._lock:
            logger.info("Stopping MeshtasticInterface...")
            
            # Signal threads to stop
            self._stop_event.set()
            
            # Disconnect
            self.disconnect()
            
            # Wait for threads to finish
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=5)
            
            if self._queue_thread and self._queue_thread.is_alive():
                self._queue_thread.join(timeout=5)
            
            # Save queue to file
            if self.config.enable_offline_queue and self.config.queue_persistence_file:
                self._save_queue_to_file()
            
            logger.info("MeshtasticInterface stopped")
    
    def connect(self) -> bool:
        """
        Connect to Meshtastic device
        
        Returns:
            True if connected successfully, False otherwise
        """
        with self._lock:
            if self.connection_state == ConnectionState.CONNECTED:
                return True
            
            self.connection_state = ConnectionState.CONNECTING
            self.stats['connection_attempts'] += 1
            self.connection_attempts += 1
            self.last_connection_attempt = datetime.now()
            
            try:
                # Close existing connection if any
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except:
                        pass
                    self.serial_conn = None
                
                # Create new connection
                self.serial_conn = serial.Serial(
                    port=self.config.port,
                    baudrate=self.config.baud_rate,
                    timeout=self.config.timeout,
                    write_timeout=self.config.write_timeout,
                    exclusive=True  # Prevent other processes from using the port
                )
                
                # Test connection with a simple write
                test_msg = f"{self.config.message_prefix}: Connection test\\n"
                self.serial_conn.write(test_msg.encode('utf-8'))
                self.serial_conn.flush()
                
                # Connection successful
                self.connection_state = ConnectionState.CONNECTED
                self.stats['successful_connections'] += 1
                self.stats['last_connection_time'] = datetime.now().isoformat()
                self.connection_attempts = 0  # Reset counter on success
                
                # Notify callbacks
                self._notify_connection_callbacks(ConnectionState.CONNECTED)
                
                logger.info(f"Connected to Meshtastic on {self.config.port}")
                return True
                
            except Exception as e:
                self.connection_state = ConnectionState.ERROR
                self.stats['connection_failures'] += 1
                
                # Notify callbacks
                self._notify_connection_callbacks(ConnectionState.ERROR)
                
                logger.error(f"Failed to connect to Meshtastic on {self.config.port}: {e}")
                return False
    
    def disconnect(self) -> None:
        """Disconnect from Meshtastic device"""
        with self._lock:
            if self.serial_conn:
                try:
                    self.serial_conn.close()
                    logger.info("Disconnected from Meshtastic")
                except Exception as e:
                    logger.error(f"Error disconnecting from Meshtastic: {e}")
                finally:
                    self.serial_conn = None
            
            if self.connection_state != ConnectionState.DISCONNECTED:
                self.connection_state = ConnectionState.DISCONNECTED
                self._notify_connection_callbacks(ConnectionState.DISCONNECTED)
    
    def send_message(self, message: str, priority: int = 1) -> bool:
        """
        Send a message via Meshtastic
        
        Args:
            message: Message to send
            priority: Message priority (1=low, 4=critical)
            
        Returns:
            True if sent successfully, False if queued or failed
        """
        # Format message
        formatted_msg = self._format_message(message)
        
        with self._lock:
            # If connected, try to send immediately
            if self.connection_state == ConnectionState.CONNECTED and self.serial_conn:
                try:
                    self.serial_conn.write(formatted_msg.encode('utf-8'))
                    self.serial_conn.flush()
                    
                    self.stats['total_messages_sent'] += 1
                    self.stats['last_send_time'] = datetime.now().isoformat()
                    self.last_successful_send = datetime.now()
                    
                    # Notify callbacks
                    self._notify_message_callbacks(message, True)
                    
                    logger.debug(f"Sent Meshtastic message: {message}")
                    return True
                    
                except Exception as e:
                    logger.error(f"Failed to send Meshtastic message: {e}")
                    self.connection_state = ConnectionState.ERROR
                    self._notify_connection_callbacks(ConnectionState.ERROR)
                    
                    # Fall through to queuing logic
            
            # Queue message if not connected or send failed
            if self.config.enable_offline_queue:
                return self._queue_message(message, priority)
            else:
                self.stats['total_messages_failed'] += 1
                self._notify_message_callbacks(message, False)
                return False
    
    def send_alert(self, alert: PendingAlert) -> bool:
        """
        Send an alert via Meshtastic
        
        Args:
            alert: PendingAlert object to send
            
        Returns:
            True if sent successfully, False if queued or failed
        """
        # Convert alert level to priority
        priority_map = {
            AlertLevel.LOW: 1,
            AlertLevel.MEDIUM: 2,
            AlertLevel.HIGH: 3,
            AlertLevel.CRITICAL: 4
        }
        
        priority = priority_map.get(alert.alert_level, 2)
        
        return self.send_message(alert.message, priority)
    
    def send_batch_alerts(self, alerts: List[PendingAlert]) -> int:
        """
        Send a batch of alerts
        
        Args:
            alerts: List of PendingAlert objects
            
        Returns:
            Number of alerts sent successfully
        """
        sent_count = 0
        
        # Sort by priority (highest first)
        sorted_alerts = sorted(alerts, key=lambda a: a.alert_level.value, reverse=True)
        
        for alert in sorted_alerts:
            if self.send_alert(alert):
                sent_count += 1
            
            # Small delay between messages to avoid overwhelming the device
            time.sleep(0.1)
        
        return sent_count
    
    def _queue_message(self, message: str, priority: int) -> bool:
        """Queue a message for later sending"""
        # Check queue size limit
        if len(self.message_queue) >= self.config.max_queue_size:
            # Remove oldest low-priority message to make room
            removed = False
            for i, queued_msg in enumerate(self.message_queue):
                if queued_msg.priority <= 2:  # Remove low/medium priority
                    del self.message_queue[i]
                    self.stats['queue_overflows'] += 1
                    removed = True
                    break
            
            if not removed:
                # Queue is full of high-priority messages, drop this one
                self.stats['total_messages_failed'] += 1
                logger.warning(f"Message queue full, dropping message: {message[:50]}...")
                return False
        
        # Add to queue
        queued_msg = QueuedMessage(
            message=message,
            timestamp=datetime.now(),
            priority=priority
        )
        
        # Insert based on priority (higher priority first)
        inserted = False
        for i, existing_msg in enumerate(self.message_queue):
            if priority > existing_msg.priority:
                self.message_queue.insert(i, queued_msg)
                inserted = True
                break
        
        if not inserted:
            self.message_queue.append(queued_msg)
        
        self.stats['total_messages_queued'] += 1
        logger.debug(f"Queued message (priority {priority}): {message[:50]}...")
        
        return True
    
    def _format_message(self, message: str) -> str:
        """Format message for Meshtastic transmission"""
        # Add prefix if configured
        if self.config.message_prefix:
            formatted = f"{self.config.message_prefix}: {message}"
        else:
            formatted = message
        
        # Add timestamp if configured
        if self.config.include_timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] {formatted}"
        
        # Truncate if too long
        if len(formatted) > self.config.max_message_length:
            formatted = formatted[:self.config.max_message_length - 3] + "..."
        
        # Ensure newline termination
        if not formatted.endswith('\\n'):
            formatted += '\\n'
        
        return formatted
    
    def _connection_monitor_loop(self) -> None:
        """Background thread for connection monitoring"""
        logger.debug("Connection monitor thread started")
        
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    # Check connection health
                    if self.connection_state == ConnectionState.CONNECTED:
                        # Test connection with heartbeat
                        if self._should_send_heartbeat():
                            if not self._send_heartbeat():
                                logger.warning("Heartbeat failed, connection may be lost")
                                self.connection_state = ConnectionState.ERROR
                    
                    # Handle reconnection if needed
                    if (self.connection_state in [ConnectionState.ERROR, ConnectionState.DISCONNECTED] and
                        self.config.enable_auto_reconnect):
                        
                        if self._should_attempt_reconnect():
                            logger.info("Attempting to reconnect to Meshtastic...")
                            self.connection_state = ConnectionState.RECONNECTING
                            self._notify_connection_callbacks(ConnectionState.RECONNECTING)
                            
                            if self.connect():
                                self.stats['reconnections'] += 1
                                logger.info("Reconnection successful")
                            else:
                                # Calculate next reconnect delay with backoff
                                delay = min(
                                    self.config.reconnect_delay * (self.config.reconnect_backoff_multiplier ** (self.connection_attempts - 1)),
                                    self.config.max_reconnect_delay
                                )
                                logger.debug(f"Reconnection failed, next attempt in {delay}s")
                
                # Sleep for heartbeat interval
                self._stop_event.wait(self.config.heartbeat_interval)
                
            except Exception as e:
                logger.error(f"Error in connection monitor: {e}")
                self._stop_event.wait(5)  # Wait before retrying
        
        logger.debug("Connection monitor thread stopped")
    
    def _queue_processor_loop(self) -> None:
        """Background thread for processing queued messages"""
        logger.debug("Queue processor thread started")
        
        while not self._stop_event.is_set():
            try:
                # Process queue if connected
                if (self.connection_state == ConnectionState.CONNECTED and 
                    self.message_queue and self.serial_conn):
                    
                    with self._lock:
                        # Get next message
                        queued_msg = self.message_queue.popleft()
                    
                    try:
                        # Format and send message
                        formatted_msg = self._format_message(queued_msg.message)
                        self.serial_conn.write(formatted_msg.encode('utf-8'))
                        self.serial_conn.flush()
                        
                        self.stats['total_messages_sent'] += 1
                        self.stats['last_send_time'] = datetime.now().isoformat()
                        self.last_successful_send = datetime.now()
                        
                        # Notify callbacks
                        self._notify_message_callbacks(queued_msg.message, True)
                        
                        logger.debug(f"Sent queued message: {queued_msg.message[:50]}...")
                        
                        # Small delay between messages
                        time.sleep(0.5)
                        
                    except Exception as e:
                        logger.error(f"Failed to send queued message: {e}")
                        
                        # Retry logic
                        queued_msg.retry_count += 1
                        if queued_msg.retry_count < queued_msg.max_retries:
                            # Put back in queue for retry
                            with self._lock:
                                self.message_queue.appendleft(queued_msg)
                        else:
                            # Max retries reached, move to failed messages
                            self.failed_messages.append(queued_msg)
                            self.stats['total_messages_failed'] += 1
                            self._notify_message_callbacks(queued_msg.message, False)
                        
                        # Connection might be lost
                        self.connection_state = ConnectionState.ERROR
                        self._notify_connection_callbacks(ConnectionState.ERROR)
                
                else:
                    # Not connected or no messages, wait a bit
                    self._stop_event.wait(1)
                
            except Exception as e:
                logger.error(f"Error in queue processor: {e}")
                self._stop_event.wait(5)
        
        logger.debug("Queue processor thread stopped")
    
    def _should_send_heartbeat(self) -> bool:
        """Check if it's time to send a heartbeat"""
        time_since_last_send = (datetime.now() - self.last_successful_send).total_seconds()
        return time_since_last_send >= self.config.heartbeat_interval
    
    def _send_heartbeat(self) -> bool:
        """Send a heartbeat message to test connection"""
        try:
            if self.serial_conn:
                heartbeat_msg = f"{self.config.message_prefix}: heartbeat\\n"
                self.serial_conn.write(heartbeat_msg.encode('utf-8'))
                self.serial_conn.flush()
                self.last_successful_send = datetime.now()
                return True
        except Exception as e:
            logger.debug(f"Heartbeat failed: {e}")
            return False
        
        return False
    
    def _should_attempt_reconnect(self) -> bool:
        """Check if we should attempt reconnection"""
        if self.connection_attempts >= self.config.max_reconnect_attempts:
            return False
        
        time_since_last_attempt = (datetime.now() - self.last_connection_attempt).total_seconds()
        required_delay = self.config.reconnect_delay * (self.config.reconnect_backoff_multiplier ** (self.connection_attempts - 1))
        
        return time_since_last_attempt >= required_delay
    
    def _notify_connection_callbacks(self, state: ConnectionState) -> None:
        """Notify connection state change callbacks"""
        for callback in self.connection_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"Error in connection callback: {e}")
    
    def _notify_message_callbacks(self, message: str, success: bool) -> None:
        """Notify message send callbacks"""
        for callback in self.message_callbacks:
            try:
                callback(message, success)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")
    
    def _save_queue_to_file(self) -> None:
        """Save message queue to file for persistence"""
        if not self.config.queue_persistence_file:
            return
        
        try:
            queue_data = {
                'messages': [msg.to_dict() for msg in self.message_queue],
                'failed_messages': [msg.to_dict() for msg in self.failed_messages],
                'saved_at': datetime.now().isoformat()
            }
            
            with open(self.config.queue_persistence_file, 'w') as f:
                json.dump(queue_data, f, indent=2)
            
            logger.debug(f"Saved {len(self.message_queue)} queued messages to file")
            
        except Exception as e:
            logger.error(f"Failed to save queue to file: {e}")
    
    def _load_queue_from_file(self) -> None:
        """Load message queue from file"""
        if not self.config.queue_persistence_file or not os.path.exists(self.config.queue_persistence_file):
            return
        
        try:
            with open(self.config.queue_persistence_file, 'r') as f:
                queue_data = json.load(f)
            
            # Load queued messages
            for msg_data in queue_data.get('messages', []):
                try:
                    queued_msg = QueuedMessage.from_dict(msg_data)
                    self.message_queue.append(queued_msg)
                except Exception as e:
                    logger.warning(f"Failed to load queued message: {e}")
            
            # Load failed messages
            for msg_data in queue_data.get('failed_messages', []):
                try:
                    failed_msg = QueuedMessage.from_dict(msg_data)
                    self.failed_messages.append(failed_msg)
                except Exception as e:
                    logger.warning(f"Failed to load failed message: {e}")
            
            logger.info(f"Loaded {len(self.message_queue)} queued messages from file")
            
            # Clean up old file
            os.remove(self.config.queue_persistence_file)
            
        except Exception as e:
            logger.error(f"Failed to load queue from file: {e}")
    
    def add_connection_callback(self, callback: Callable[[ConnectionState], None]) -> None:
        """Add a connection state change callback"""
        self.connection_callbacks.append(callback)
        logger.debug(f"Added connection callback: {callback.__name__}")
    
    def add_message_callback(self, callback: Callable[[str, bool], None]) -> None:
        """Add a message send callback"""
        self.message_callbacks.append(callback)
        logger.debug(f"Added message callback: {callback.__name__}")
    
    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.connection_state == ConnectionState.CONNECTED
    
    def get_connection_state(self) -> ConnectionState:
        """Get current connection state"""
        return self.connection_state
    
    def get_queue_size(self) -> int:
        """Get current queue size"""
        return len(self.message_queue)
    
    def clear_queue(self) -> int:
        """Clear message queue and return number of messages cleared"""
        with self._lock:
            count = len(self.message_queue)
            self.message_queue.clear()
            return count
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get interface statistics"""
        with self._lock:
            stats = self.stats.copy()
            stats.update({
                'connection_state': self.connection_state.value,
                'queue_size': len(self.message_queue),
                'failed_messages_count': len(self.failed_messages),
                'connection_attempts_current': self.connection_attempts,
                'config': {
                    'port': self.config.port,
                    'baud_rate': self.config.baud_rate,
                    'auto_reconnect': self.config.enable_auto_reconnect,
                    'offline_queue': self.config.enable_offline_queue,
                    'max_queue_size': self.config.max_queue_size
                }
            })
            return stats
    
    def reset_statistics(self) -> None:
        """Reset all statistics counters"""
        with self._lock:
            self.stats = {
                'total_messages_sent': 0,
                'total_messages_queued': 0,
                'total_messages_failed': 0,
                'connection_attempts': 0,
                'successful_connections': 0,
                'connection_failures': 0,
                'reconnections': 0,
                'queue_overflows': 0,
                'last_send_time': None,
                'last_connection_time': None,
                'uptime_seconds': 0,
                'downtime_seconds': 0
            }
            logger.info("MeshtasticInterface statistics reset")