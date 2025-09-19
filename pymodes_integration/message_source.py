"""
Message Source Management

Provides base classes and interfaces for managing different ADS-B message sources
including dump1090, network streams, and other data sources.
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Iterator, Dict, Any
from datetime import datetime
import threading
import time

logger = logging.getLogger(__name__)


class MessageSource(ABC):
    """
    Abstract base class for ADS-B message sources
    
    Defines the interface that all message sources must implement
    to provide consistent message handling across different input types.
    """
    
    def __init__(self, name: str):
        """
        Initialize message source
        
        Args:
            name: Human-readable name for this source
        """
        self.name = name
        self.connected = False
        self.last_message_time: Optional[datetime] = None
        self.message_count = 0
        self.error_count = 0
        
    @abstractmethod
    def connect(self) -> bool:
        """
        Connect to the message source
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the message source"""
        pass
    
    @abstractmethod
    def get_messages(self) -> List[Tuple[str, float]]:
        """
        Get available messages from the source
        
        Returns:
            List of (message, timestamp) tuples
        """
        pass
    
    def is_connected(self) -> bool:
        """Check if source is connected"""
        return self.connected
    
    def get_status(self) -> Dict[str, Any]:
        """Get source status information"""
        return {
            'name': self.name,
            'connected': self.connected,
            'message_count': self.message_count,
            'error_count': self.error_count,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None
        }
    
    def _update_message_stats(self, message_count: int = 1):
        """Update message statistics"""
        self.message_count += message_count
        self.last_message_time = datetime.now()


class MessageSourceManager:
    """
    Manages multiple message sources and provides unified message stream
    
    Coordinates multiple message sources, handles connection management,
    and provides a unified interface for message consumption.
    """
    
    def __init__(self, max_sources: int = 5):
        """
        Initialize message source manager
        
        Args:
            max_sources: Maximum number of sources to manage
        """
        self.max_sources = max_sources
        self.sources: List[MessageSource] = []
        self.running = False
        self.message_queue: List[Tuple[str, float]] = []
        self.queue_lock = threading.Lock()
        
        # Statistics
        self.stats = {
            'total_messages': 0,
            'sources_connected': 0,
            'last_update': None
        }
    
    def add_source(self, source: MessageSource) -> bool:
        """
        Add a message source to the manager
        
        Args:
            source: MessageSource instance to add
            
        Returns:
            True if source added successfully, False if at capacity
        """
        if len(self.sources) >= self.max_sources:
            logger.warning(f"Cannot add source {source.name}: at capacity ({self.max_sources})")
            return False
        
        self.sources.append(source)
        logger.info(f"Added message source: {source.name}")
        return True
    
    def remove_source(self, source: MessageSource) -> bool:
        """
        Remove a message source from the manager
        
        Args:
            source: MessageSource instance to remove
            
        Returns:
            True if source removed successfully
        """
        if source in self.sources:
            source.disconnect()
            self.sources.remove(source)
            logger.info(f"Removed message source: {source.name}")
            return True
        return False
    
    def start_collection(self) -> None:
        """Start message collection from all sources"""
        logger.info("Starting message collection")
        self.running = True
        
        # Connect all sources
        for source in self.sources:
            try:
                if source.connect():
                    logger.info(f"Connected to source: {source.name}")
                else:
                    logger.warning(f"Failed to connect to source: {source.name}")
            except Exception as e:
                logger.error(f"Error connecting to source {source.name}: {e}")
        
        # Start collection thread
        collection_thread = threading.Thread(target=self._collection_worker, daemon=True)
        collection_thread.start()
    
    def stop_collection(self) -> None:
        """Stop message collection and disconnect all sources"""
        logger.info("Stopping message collection")
        self.running = False
        
        # Disconnect all sources
        for source in self.sources:
            try:
                source.disconnect()
                logger.info(f"Disconnected from source: {source.name}")
            except Exception as e:
                logger.error(f"Error disconnecting from source {source.name}: {e}")
    
    def get_message_stream(self) -> Iterator[Tuple[str, float]]:
        """
        Get iterator for message stream
        
        Yields:
            (message, timestamp) tuples
        """
        while self.running:
            messages = self.get_message_batch()
            for message in messages:
                yield message
            
            if not messages:
                time.sleep(0.1)  # Brief pause if no messages
    
    def get_message_batch(self) -> List[Tuple[str, float]]:
        """
        Get batch of messages from queue
        
        Returns:
            List of (message, timestamp) tuples
        """
        with self.queue_lock:
            messages = self.message_queue.copy()
            self.message_queue.clear()
            return messages
    
    def get_sources_status(self) -> List[Dict[str, Any]]:
        """Get status of all sources"""
        return [source.get_status() for source in self.sources]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get manager statistics"""
        connected_count = sum(1 for source in self.sources if source.is_connected())
        
        return {
            **self.stats,
            'sources_total': len(self.sources),
            'sources_connected': connected_count,
            'queue_size': len(self.message_queue)
        }
    
    def _collection_worker(self):
        """Background worker to collect messages from all sources"""
        logger.info("Message collection worker started")
        
        while self.running:
            try:
                batch_messages = []
                
                # Collect from all sources
                for source in self.sources:
                    if not source.is_connected():
                        continue
                    
                    try:
                        messages = source.get_messages()
                        if messages:
                            batch_messages.extend(messages)
                            source._update_message_stats(len(messages))
                    except Exception as e:
                        source.error_count += 1
                        logger.debug(f"Error collecting from source {source.name}: {e}")
                
                # Add to queue
                if batch_messages:
                    with self.queue_lock:
                        self.message_queue.extend(batch_messages)
                        self.stats['total_messages'] += len(batch_messages)
                        self.stats['last_update'] = datetime.now()
                
                time.sleep(0.1)  # Brief pause between collections
                
            except Exception as e:
                logger.error(f"Collection worker error: {e}")
                time.sleep(1)
        
        logger.info("Message collection worker stopped")


class DummyMessageSource(MessageSource):
    """
    Dummy message source for testing and development
    
    Generates synthetic ADS-B messages for testing the integration
    without requiring actual hardware or data sources.
    """
    
    def __init__(self, name: str = "dummy"):
        """Initialize dummy source"""
        super().__init__(name)
        self.message_interval = 1.0  # seconds between messages
        self.last_message_time_internal = 0
        
        # Sample ADS-B messages for testing
        self.sample_messages = [
            "8D4840D6202CC371C32CE0576098",  # Position message
            "8D4840D658C382D690C8AC2863A7",  # Velocity message
            "8D4840D620323DD8F82C4E0576098", # Another position
        ]
        self.message_index = 0
    
    def connect(self) -> bool:
        """Connect to dummy source"""
        logger.info(f"Connecting to dummy source: {self.name}")
        self.connected = True
        return True
    
    def disconnect(self) -> None:
        """Disconnect from dummy source"""
        logger.info(f"Disconnecting from dummy source: {self.name}")
        self.connected = False
    
    def get_messages(self) -> List[Tuple[str, float]]:
        """Get dummy messages"""
        if not self.connected:
            return []
        
        current_time = time.time()
        
        # Generate message at specified interval
        if current_time - self.last_message_time_internal >= self.message_interval:
            message = self.sample_messages[self.message_index]
            self.message_index = (self.message_index + 1) % len(self.sample_messages)
            self.last_message_time_internal = current_time
            
            return [(message, current_time)]
        
        return []