"""
Message delivery tracking and queue management for enhanced Meshtastic integration

This module implements the DeliveryTracker and MessageQueue classes that handle
message delivery status monitoring, retry logic, and priority-based queuing.
"""

import logging
import threading
import time
import uuid
from typing import Dict, List, Any, Optional, Callable, Set
from datetime import datetime, timedelta
from collections import deque, defaultdict
from queue import PriorityQueue, Empty
from dataclasses import dataclass, field

from .data_classes import AlertMessage, MessagePriority
from .exceptions import MeshtasticError, MessageError


logger = logging.getLogger(__name__)


@dataclass
class DeliveryStatus:
    """Tracks delivery status for a message across interfaces"""
    message_id: str
    message: AlertMessage
    target_interfaces: Set[str]
    successful_interfaces: Set[str] = field(default_factory=set)
    failed_interfaces: Set[str] = field(default_factory=set)
    pending_interfaces: Set[str] = field(default_factory=set)
    created_time: datetime = field(default_factory=datetime.now)
    last_attempt_time: Optional[datetime] = None
    next_retry_time: Optional[datetime] = None
    retry_count: int = 0
    error_messages: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize pending interfaces"""
        if not self.pending_interfaces:
            self.pending_interfaces = self.target_interfaces.copy()
    
    @property
    def is_complete(self) -> bool:
        """Check if delivery is complete (all interfaces attempted)"""
        return len(self.pending_interfaces) == 0
    
    @property
    def is_successful(self) -> bool:
        """Check if at least one interface delivered successfully"""
        return len(self.successful_interfaces) > 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total_attempted = len(self.successful_interfaces) + len(self.failed_interfaces)
        if total_attempted == 0:
            return 0.0
        return (len(self.successful_interfaces) / total_attempted) * 100.0
    
    @property
    def can_retry(self) -> bool:
        """Check if message can be retried"""
        return (
            self.message.can_retry and 
            (len(self.failed_interfaces) > 0 or not self.is_complete) and
            not self.is_successful  # Don't retry if at least one succeeded
        )
    
    def record_success(self, interface_type: str) -> None:
        """Record successful delivery for an interface"""
        self.successful_interfaces.add(interface_type)
        self.pending_interfaces.discard(interface_type)
        self.failed_interfaces.discard(interface_type)
        self.last_attempt_time = datetime.now()
        
        if interface_type in self.error_messages:
            del self.error_messages[interface_type]
    
    def record_failure(self, interface_type: str, error_message: str = "") -> None:
        """Record failed delivery for an interface"""
        self.failed_interfaces.add(interface_type)
        self.pending_interfaces.discard(interface_type)
        self.last_attempt_time = datetime.now()
        
        if error_message:
            self.error_messages[interface_type] = error_message
    
    def prepare_retry(self, retry_delay_seconds: int = 30) -> None:
        """Prepare message for retry"""
        if self.can_retry:
            self.retry_count += 1
            self.message.increment_retry()
            
            # Move failed interfaces back to pending for retry
            self.pending_interfaces.update(self.failed_interfaces)
            self.failed_interfaces.clear()
            
            # Set next retry time
            self.next_retry_time = datetime.now() + timedelta(seconds=retry_delay_seconds)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'message_id': self.message_id,
            'message': self.message.to_dict(),
            'target_interfaces': list(self.target_interfaces),
            'successful_interfaces': list(self.successful_interfaces),
            'failed_interfaces': list(self.failed_interfaces),
            'pending_interfaces': list(self.pending_interfaces),
            'created_time': self.created_time.isoformat(),
            'last_attempt_time': self.last_attempt_time.isoformat() if self.last_attempt_time else None,
            'next_retry_time': self.next_retry_time.isoformat() if self.next_retry_time else None,
            'retry_count': self.retry_count,
            'error_messages': self.error_messages,
            'is_complete': self.is_complete,
            'is_successful': self.is_successful,
            'success_rate': self.success_rate,
            'can_retry': self.can_retry
        }


@dataclass
class QueuedMessage:
    """Represents a message in the delivery queue"""
    message: AlertMessage
    priority: int
    queue_time: datetime = field(default_factory=datetime.now)
    attempts: int = 0
    
    def __lt__(self, other):
        """Compare for priority queue ordering (higher priority first)"""
        if self.priority != other.priority:
            return self.priority > other.priority  # Higher priority first
        return self.queue_time < other.queue_time  # Earlier messages first for same priority


class MessageQueue:
    """
    Priority-based message queue with retry logic and delivery tracking
    """
    
    def __init__(self, max_queue_size: int = 1000, max_retry_attempts: int = 3):
        """
        Initialize the message queue
        
        Args:
            max_queue_size: Maximum number of messages to queue
            max_retry_attempts: Maximum retry attempts for failed messages
        """
        self.max_queue_size = max_queue_size
        self.max_retry_attempts = max_retry_attempts
        self.queue = PriorityQueue(maxsize=max_queue_size)
        self.retry_queue = PriorityQueue()
        self.statistics = {
            'total_queued': 0,
            'total_processed': 0,
            'total_dropped': 0,
            'current_queue_size': 0,
            'retry_queue_size': 0,
            'priority_stats': defaultdict(int)
        }
        self._lock = threading.RLock()
        
        logger.info(f"MessageQueue initialized with max_size={max_queue_size}, max_retries={max_retry_attempts}")
    
    def enqueue(self, message: AlertMessage, drop_on_full: bool = True) -> bool:
        """
        Add a message to the queue
        
        Args:
            message: AlertMessage to queue
            drop_on_full: Whether to drop message if queue is full
            
        Returns:
            True if message was queued, False if dropped
        """
        with self._lock:
            try:
                queued_message = QueuedMessage(
                    message=message,
                    priority=message.priority.value
                )
                
                # Try to add to queue
                self.queue.put(queued_message, block=False)
                
                # Update statistics
                self.statistics['total_queued'] += 1
                self.statistics['current_queue_size'] = self.queue.qsize()
                self.statistics['priority_stats'][message.priority.value] += 1
                
                logger.debug(f"Message queued with priority {message.priority.value}")
                return True
                
            except Exception as e:
                if drop_on_full:
                    self.statistics['total_dropped'] += 1
                    logger.warning(f"Message dropped - queue full: {e}")
                    return False
                else:
                    # Try to drop lowest priority message to make room
                    if self._drop_lowest_priority_message():
                        return self.enqueue(message, drop_on_full=False)  # Retry once
                    else:
                        self.statistics['total_dropped'] += 1
                        logger.error(f"Failed to queue message - queue full and couldn't drop: {e}")
                        return False
    
    def dequeue(self, timeout: Optional[float] = None) -> Optional[AlertMessage]:
        """
        Get the next message from the queue
        
        Args:
            timeout: Maximum time to wait for a message
            
        Returns:
            Next AlertMessage or None if timeout/empty
        """
        try:
            # First check retry queue
            try:
                queued_message = self.retry_queue.get(block=False)
                with self._lock:
                    self.statistics['retry_queue_size'] = self.retry_queue.qsize()
                    self.statistics['total_processed'] += 1
                
                queued_message.attempts += 1
                logger.debug(f"Dequeued retry message (attempt {queued_message.attempts})")
                return queued_message.message
                
            except Empty:
                pass
            
            # Then check main queue
            queued_message = self.queue.get(timeout=timeout)
            
            with self._lock:
                self.statistics['current_queue_size'] = self.queue.qsize()
                self.statistics['total_processed'] += 1
            
            queued_message.attempts += 1
            logger.debug(f"Dequeued message with priority {queued_message.priority}")
            return queued_message.message
            
        except Empty:
            return None
        except Exception as e:
            logger.error(f"Error dequeuing message: {e}")
            return None
    
    def enqueue_retry(self, message: AlertMessage, delay_seconds: int = 30) -> bool:
        """
        Add a message to the retry queue
        
        Args:
            message: AlertMessage to retry
            delay_seconds: Delay before retry (not implemented in this simple version)
            
        Returns:
            True if message was queued for retry, False otherwise
        """
        if message.retry_count >= self.max_retry_attempts:
            logger.warning(f"Message exceeded max retry attempts ({self.max_retry_attempts})")
            return False
        
        try:
            queued_message = QueuedMessage(
                message=message,
                priority=message.priority.value + 1  # Slightly higher priority for retries
            )
            
            self.retry_queue.put(queued_message, block=False)
            
            with self._lock:
                self.statistics['retry_queue_size'] = self.retry_queue.qsize()
            
            logger.debug(f"Message queued for retry (attempt {message.retry_count + 1})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to queue message for retry: {e}")
            return False
    
    def _drop_lowest_priority_message(self) -> bool:
        """
        Drop the lowest priority message to make room
        
        Returns:
            True if a message was dropped, False otherwise
        """
        # This is a simplified implementation
        # In a real implementation, you'd need to peek at queue contents
        # For now, we'll just indicate we couldn't drop
        return False
    
    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics
        
        Returns:
            Dictionary with queue statistics
        """
        with self._lock:
            return {
                'max_queue_size': self.max_queue_size,
                'current_queue_size': self.queue.qsize(),
                'retry_queue_size': self.retry_queue.qsize(),
                'total_queued': self.statistics['total_queued'],
                'total_processed': self.statistics['total_processed'],
                'total_dropped': self.statistics['total_dropped'],
                'priority_stats': dict(self.statistics['priority_stats']),
                'queue_utilization': (self.queue.qsize() / self.max_queue_size) * 100
            }
    
    def clear(self) -> int:
        """
        Clear all messages from queues
        
        Returns:
            Number of messages cleared
        """
        cleared_count = 0
        
        # Clear main queue
        while not self.queue.empty():
            try:
                self.queue.get(block=False)
                cleared_count += 1
            except Empty:
                break
        
        # Clear retry queue
        while not self.retry_queue.empty():
            try:
                self.retry_queue.get(block=False)
                cleared_count += 1
            except Empty:
                break
        
        with self._lock:
            self.statistics['current_queue_size'] = 0
            self.statistics['retry_queue_size'] = 0
        
        logger.info(f"Cleared {cleared_count} messages from queues")
        return cleared_count
    
    def is_empty(self) -> bool:
        """Check if both queues are empty"""
        return self.queue.empty() and self.retry_queue.empty()
    
    def is_full(self) -> bool:
        """Check if main queue is full"""
        return self.queue.full()


class DeliveryTracker:
    """
    Tracks message delivery status across multiple interfaces with retry logic
    """
    
    def __init__(self, max_tracked_messages: int = 10000, cleanup_interval: int = 3600):
        """
        Initialize the delivery tracker
        
        Args:
            max_tracked_messages: Maximum number of messages to track
            cleanup_interval: Interval in seconds between cleanup operations
        """
        self.max_tracked_messages = max_tracked_messages
        self.cleanup_interval = cleanup_interval
        self.tracked_messages: Dict[str, DeliveryStatus] = {}
        self.completed_messages: deque = deque(maxlen=1000)  # Keep last 1000 completed
        self.statistics = {
            'total_tracked': 0,
            'completed_successful': 0,
            'completed_failed': 0,
            'pending_delivery': 0,
            'pending_retry': 0,
            'total_retries': 0
        }
        
        # Threading for cleanup
        self._cleanup_thread: Optional[threading.Thread] = None
        self._cleanup_stop_event = threading.Event()
        self._lock = threading.RLock()
        
        # Callbacks
        self.on_delivery_complete: Optional[Callable[[DeliveryStatus], None]] = None
        self.on_delivery_failed: Optional[Callable[[DeliveryStatus], None]] = None
        
        logger.info(f"DeliveryTracker initialized with max_tracked={max_tracked_messages}")
        self._start_cleanup_thread()
    
    def track_message(self, message: AlertMessage, target_interfaces: Set[str]) -> str:
        """
        Start tracking a message delivery
        
        Args:
            message: AlertMessage being tracked
            target_interfaces: Set of interface types to deliver to
            
        Returns:
            Unique message ID for tracking
        """
        message_id = str(uuid.uuid4())
        
        with self._lock:
            delivery_status = DeliveryStatus(
                message_id=message_id,
                message=message,
                target_interfaces=target_interfaces.copy()
            )
            
            self.tracked_messages[message_id] = delivery_status
            self.statistics['total_tracked'] += 1
            self.statistics['pending_delivery'] += 1
            
            # Cleanup old messages if we exceed limit
            if len(self.tracked_messages) > self.max_tracked_messages:
                self._cleanup_old_messages()
        
        logger.debug(f"Started tracking message {message_id} for interfaces: {target_interfaces}")
        return message_id
    
    def confirm_delivery(self, message_id: str, interface_type: str, success: bool = True, error_message: str = "") -> None:
        """
        Confirm delivery status for a specific interface
        
        Args:
            message_id: ID of the message
            interface_type: Interface that attempted delivery
            success: Whether delivery was successful
            error_message: Error message if delivery failed
        """
        with self._lock:
            if message_id not in self.tracked_messages:
                logger.warning(f"Attempted to confirm delivery for unknown message {message_id}")
                return
            
            delivery_status = self.tracked_messages[message_id]
            
            if success:
                delivery_status.record_success(interface_type)
                logger.debug(f"Confirmed successful delivery of {message_id} via {interface_type}")
            else:
                delivery_status.record_failure(interface_type, error_message)
                logger.debug(f"Confirmed failed delivery of {message_id} via {interface_type}: {error_message}")
            
            # Check if delivery is complete
            if delivery_status.is_complete:
                self._handle_delivery_complete(delivery_status)
    
    def get_failed_messages(self, include_retryable_only: bool = True) -> List[DeliveryStatus]:
        """
        Get messages that failed delivery
        
        Args:
            include_retryable_only: Whether to include only retryable messages
            
        Returns:
            List of failed DeliveryStatus objects
        """
        with self._lock:
            failed_messages = []
            
            for delivery_status in self.tracked_messages.values():
                if delivery_status.is_complete and not delivery_status.is_successful:
                    if not include_retryable_only or delivery_status.can_retry:
                        failed_messages.append(delivery_status)
            
            return failed_messages
    
    def retry_failed_messages(self, max_retries: int = None) -> int:
        """
        Retry failed messages that are eligible for retry
        
        Args:
            max_retries: Maximum number of messages to retry (None for all)
            
        Returns:
            Number of messages queued for retry
        """
        failed_messages = self.get_failed_messages(include_retryable_only=True)
        
        if max_retries:
            failed_messages = failed_messages[:max_retries]
        
        retry_count = 0
        
        for delivery_status in failed_messages:
            # Calculate retry delay based on attempt count (exponential backoff)
            retry_delay = min(30 * (2 ** delivery_status.retry_count), 300)  # Max 5 minutes
            
            delivery_status.prepare_retry(retry_delay)
            
            with self._lock:
                self.statistics['total_retries'] += 1
                self.statistics['pending_retry'] += 1
            
            retry_count += 1
            logger.info(f"Queued message {delivery_status.message_id} for retry (attempt {delivery_status.retry_count})")
        
        return retry_count
    
    def get_delivery_status(self, message_id: str) -> Optional[DeliveryStatus]:
        """
        Get delivery status for a specific message
        
        Args:
            message_id: ID of the message
            
        Returns:
            DeliveryStatus object or None if not found
        """
        with self._lock:
            return self.tracked_messages.get(message_id)
    
    def get_pending_messages(self) -> List[DeliveryStatus]:
        """
        Get messages that are still pending delivery
        
        Returns:
            List of pending DeliveryStatus objects
        """
        with self._lock:
            return [
                delivery_status for delivery_status in self.tracked_messages.values()
                if not delivery_status.is_complete
            ]
    
    def get_retry_ready_messages(self) -> List[DeliveryStatus]:
        """
        Get messages that are ready for retry
        
        Returns:
            List of DeliveryStatus objects ready for retry
        """
        now = datetime.now()
        
        with self._lock:
            retry_ready = []
            
            for delivery_status in self.tracked_messages.values():
                if (delivery_status.can_retry and 
                    delivery_status.next_retry_time and 
                    delivery_status.next_retry_time <= now):
                    retry_ready.append(delivery_status)
            
            return retry_ready
    
    def _handle_delivery_complete(self, delivery_status: DeliveryStatus) -> None:
        """
        Handle completion of message delivery
        
        Args:
            delivery_status: Completed DeliveryStatus
        """
        # Update statistics
        self.statistics['pending_delivery'] -= 1
        
        if delivery_status.is_successful:
            self.statistics['completed_successful'] += 1
            logger.info(f"Message {delivery_status.message_id} delivered successfully to {len(delivery_status.successful_interfaces)} interfaces")
            
            # Call success callback
            if self.on_delivery_complete:
                try:
                    self.on_delivery_complete(delivery_status)
                except Exception as e:
                    logger.error(f"Error in delivery complete callback: {e}")
        else:
            self.statistics['completed_failed'] += 1
            logger.warning(f"Message {delivery_status.message_id} failed delivery to all interfaces")
            
            # Call failure callback
            if self.on_delivery_failed:
                try:
                    self.on_delivery_failed(delivery_status)
                except Exception as e:
                    logger.error(f"Error in delivery failed callback: {e}")
        
        # Move to completed messages
        self.completed_messages.append(delivery_status.to_dict())
        
        # Remove from active tracking
        del self.tracked_messages[delivery_status.message_id]
    
    def _start_cleanup_thread(self) -> None:
        """Start the cleanup thread"""
        self._cleanup_stop_event.clear()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            name="DeliveryTrackerCleanup",
            daemon=True
        )
        self._cleanup_thread.start()
        logger.info("Delivery tracker cleanup thread started")
    
    def _cleanup_loop(self) -> None:
        """Main cleanup loop"""
        while not self._cleanup_stop_event.is_set():
            try:
                self._cleanup_old_messages()
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
            
            # Wait for next cleanup or stop event
            self._cleanup_stop_event.wait(self.cleanup_interval)
    
    def _cleanup_old_messages(self) -> None:
        """Clean up old completed messages"""
        cutoff_time = datetime.now() - timedelta(hours=24)  # Remove messages older than 24 hours
        
        with self._lock:
            messages_to_remove = []
            
            for message_id, delivery_status in self.tracked_messages.items():
                # Remove completed messages older than cutoff
                if (delivery_status.is_complete and 
                    delivery_status.created_time < cutoff_time):
                    messages_to_remove.append(message_id)
                
                # Remove very old pending messages (likely stale)
                elif delivery_status.created_time < cutoff_time - timedelta(hours=48):
                    messages_to_remove.append(message_id)
                    logger.warning(f"Removing stale message {message_id}")
            
            for message_id in messages_to_remove:
                del self.tracked_messages[message_id]
            
            if messages_to_remove:
                logger.info(f"Cleaned up {len(messages_to_remove)} old messages")
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get delivery tracking statistics
        
        Returns:
            Dictionary with tracking statistics
        """
        with self._lock:
            return {
                'total_tracked': self.statistics['total_tracked'],
                'completed_successful': self.statistics['completed_successful'],
                'completed_failed': self.statistics['completed_failed'],
                'pending_delivery': self.statistics['pending_delivery'],
                'pending_retry': self.statistics['pending_retry'],
                'total_retries': self.statistics['total_retries'],
                'active_tracked': len(self.tracked_messages),
                'completed_history': len(self.completed_messages),
                'success_rate': (
                    self.statistics['completed_successful'] / 
                    max(1, self.statistics['completed_successful'] + self.statistics['completed_failed'])
                ) * 100
            }
    
    def shutdown(self) -> None:
        """Shutdown the delivery tracker and cleanup resources"""
        logger.info("Shutting down delivery tracker")
        
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_stop_event.set()
            self._cleanup_thread.join(timeout=5)
        
        with self._lock:
            self.tracked_messages.clear()
            self.completed_messages.clear()
        
        logger.info("Delivery tracker shutdown complete")