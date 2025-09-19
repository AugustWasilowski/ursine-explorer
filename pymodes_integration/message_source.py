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
import json
import socket
import struct

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
    message deduplication, and provides a unified interface for message consumption.
    """
    
    def __init__(self, max_sources: int = 5, deduplication_window: int = 5):
        """
        Initialize message source manager
        
        Args:
            max_sources: Maximum number of sources to manage
            deduplication_window: Time window in seconds for message deduplication
        """
        self.max_sources = max_sources
        self.deduplication_window = deduplication_window
        self.sources: List[MessageSource] = []
        self.running = False
        self.message_queue: List[Tuple[str, float]] = []
        self.queue_lock = threading.Lock()
        
        # Message deduplication tracking
        self.recent_messages: Dict[str, float] = {}  # message_hash -> timestamp
        self.dedup_lock = threading.Lock()
        
        # Health monitoring
        self.health_check_interval = 30  # seconds
        self.last_health_check = 0
        
        # Statistics
        self.stats = {
            'total_messages': 0,
            'duplicate_messages': 0,
            'sources_connected': 0,
            'last_update': None,
            'messages_per_second': 0.0,
            'health_status': 'unknown'
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
            'queue_size': len(self.message_queue),
            'deduplication_cache_size': len(self.recent_messages)
        }
    
    def _deduplicate_messages(self, messages: List[Tuple[str, float]]) -> List[Tuple[str, float]]:
        """
        Remove duplicate messages based on content and timing
        
        Args:
            messages: List of (message, timestamp) tuples
            
        Returns:
            Deduplicated list of messages
        """
        deduplicated = []
        current_time = time.time()
        
        with self.dedup_lock:
            for message, timestamp in messages:
                # Create hash of message content
                message_hash = hash(message)
                
                # Check if we've seen this message recently
                if message_hash in self.recent_messages:
                    last_seen = self.recent_messages[message_hash]
                    if current_time - last_seen < self.deduplication_window:
                        # Skip duplicate message
                        continue
                
                # Add to deduplicated list and update cache
                deduplicated.append((message, timestamp))
                self.recent_messages[message_hash] = current_time
        
        return deduplicated
    
    def _cleanup_deduplication_cache(self, current_time: float):
        """Clean up old entries from deduplication cache"""
        with self.dedup_lock:
            # Remove entries older than deduplication window
            expired_keys = [
                key for key, timestamp in self.recent_messages.items()
                if current_time - timestamp > self.deduplication_window * 2
            ]
            
            for key in expired_keys:
                del self.recent_messages[key]
    
    def _perform_health_check(self):
        """Perform health check on all sources and update status"""
        try:
            connected_sources = 0
            total_sources = len(self.sources)
            
            for source in self.sources:
                if source.is_connected():
                    connected_sources += 1
                else:
                    # Try to reconnect disconnected sources
                    logger.debug(f"Attempting to reconnect source: {source.name}")
                    try:
                        source.connect()
                    except Exception as e:
                        logger.debug(f"Reconnection failed for {source.name}: {e}")
            
            # Update health status
            if connected_sources == 0:
                self.stats['health_status'] = 'critical'
            elif connected_sources < total_sources:
                self.stats['health_status'] = 'degraded'
            else:
                self.stats['health_status'] = 'healthy'
            
            self.stats['sources_connected'] = connected_sources
            
            logger.debug(f"Health check: {connected_sources}/{total_sources} sources connected")
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            self.stats['health_status'] = 'error'
    
    def get_source_by_name(self, name: str) -> Optional[MessageSource]:
        """Get source by name"""
        for source in self.sources:
            if source.name == name:
                return source
        return None
    
    def restart_source(self, name: str) -> bool:
        """Restart a specific source by name"""
        source = self.get_source_by_name(name)
        if source:
            try:
                source.disconnect()
                time.sleep(1)  # Brief pause
                return source.connect()
            except Exception as e:
                logger.error(f"Error restarting source {name}: {e}")
                return False
        return False
    
    def set_deduplication_window(self, window_seconds: int):
        """Update deduplication window"""
        self.deduplication_window = max(1, window_seconds)
        logger.info(f"Deduplication window set to {self.deduplication_window} seconds")
    
    def _collection_worker(self):
        """Background worker to collect messages from all sources"""
        logger.info("Message collection worker started")
        
        message_count_history = []
        last_stats_update = time.time()
        
        while self.running:
            try:
                batch_messages = []
                current_time = time.time()
                
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
                
                # Deduplicate messages
                if batch_messages:
                    deduplicated_messages = self._deduplicate_messages(batch_messages)
                    duplicate_count = len(batch_messages) - len(deduplicated_messages)
                    
                    # Add to queue
                    with self.queue_lock:
                        self.message_queue.extend(deduplicated_messages)
                        self.stats['total_messages'] += len(deduplicated_messages)
                        self.stats['duplicate_messages'] += duplicate_count
                        self.stats['last_update'] = datetime.now()
                
                # Update message rate statistics
                if current_time - last_stats_update >= 1.0:  # Update every second
                    message_count_history.append(len(batch_messages))
                    if len(message_count_history) > 60:  # Keep last 60 seconds
                        message_count_history.pop(0)
                    
                    # Calculate messages per second
                    if message_count_history:
                        self.stats['messages_per_second'] = sum(message_count_history) / len(message_count_history)
                    
                    last_stats_update = current_time
                
                # Periodic health check
                if current_time - self.last_health_check >= self.health_check_interval:
                    self._perform_health_check()
                    self.last_health_check = current_time
                
                # Clean up old deduplication entries
                self._cleanup_deduplication_cache(current_time)
                
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


class Dump1090Source(MessageSource):
    """
    Message source for dump1090 connections
    
    Supports both JSON output and raw beast format from dump1090.
    Handles connection monitoring and automatic reconnection.
    """
    
    def __init__(self, name: str, host: str = "localhost", port: int = 30003, 
                 format_type: str = "raw", reconnect_interval: int = 5):
        """
        Initialize dump1090 source
        
        Args:
            name: Human-readable name for this source
            host: dump1090 host address
            port: dump1090 port (30003 for raw, 30001 for beast, 8080 for JSON)
            format_type: "raw", "beast", or "json"
            reconnect_interval: Seconds between reconnection attempts
        """
        super().__init__(name)
        self.host = host
        self.port = port
        self.format_type = format_type.lower()
        self.reconnect_interval = reconnect_interval
        
        self.socket: Optional[socket.socket] = None
        self.buffer = b""
        self.last_reconnect_attempt = 0
        
        # Validate format type
        if self.format_type not in ["raw", "beast", "json"]:
            raise ValueError(f"Unsupported format type: {format_type}")
    
    def connect(self) -> bool:
        """Connect to dump1090 source"""
        try:
            logger.info(f"Connecting to dump1090 at {self.host}:{self.port} ({self.format_type})")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)  # 5 second timeout
            self.socket.connect((self.host, self.port))
            
            # Set socket to non-blocking for message reading
            self.socket.setblocking(False)
            
            self.connected = True
            self.buffer = b""
            logger.info(f"Connected to dump1090 source: {self.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to dump1090 {self.name}: {e}")
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False
    
    def disconnect(self) -> None:
        """Disconnect from dump1090 source"""
        logger.info(f"Disconnecting from dump1090 source: {self.name}")
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.buffer = b""
    
    def get_messages(self) -> List[Tuple[str, float]]:
        """Get messages from dump1090 source"""
        if not self.connected or not self.socket:
            # Try to reconnect if enough time has passed
            current_time = time.time()
            if current_time - self.last_reconnect_attempt >= self.reconnect_interval:
                self.last_reconnect_attempt = current_time
                logger.debug(f"Attempting to reconnect to {self.name}")
                self.connect()
            return []
        
        try:
            # Read data from socket
            data = self.socket.recv(4096)
            if not data:
                # Connection closed by remote
                logger.warning(f"Connection closed by dump1090: {self.name}")
                self.disconnect()
                return []
            
            self.buffer += data
            
            # Parse messages based on format type
            if self.format_type == "raw":
                return self._parse_raw_messages()
            elif self.format_type == "beast":
                return self._parse_beast_messages()
            elif self.format_type == "json":
                return self._parse_json_messages()
            
        except socket.error as e:
            if e.errno not in [socket.EAGAIN, socket.EWOULDBLOCK]:
                logger.error(f"Socket error on {self.name}: {e}")
                self.disconnect()
        except Exception as e:
            logger.error(f"Error reading from dump1090 {self.name}: {e}")
            self.error_count += 1
        
        return []
    
    def _parse_raw_messages(self) -> List[Tuple[str, float]]:
        """Parse raw ASCII hex messages"""
        messages = []
        current_time = time.time()
        
        # Split buffer by newlines
        lines = self.buffer.split(b'\n')
        
        # Keep the last incomplete line in buffer
        self.buffer = lines[-1]
        
        # Process complete lines
        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue
            
            try:
                # Raw format is typically just hex strings
                message_hex = line.decode('ascii').strip()
                
                # Validate hex format (should be even length, hex characters only)
                if len(message_hex) % 2 == 0 and all(c in '0123456789ABCDEFabcdef' for c in message_hex):
                    messages.append((message_hex.upper(), current_time))
                
            except Exception as e:
                logger.debug(f"Error parsing raw message: {e}")
                continue
        
        return messages
    
    def _parse_beast_messages(self) -> List[Tuple[str, float]]:
        """Parse beast format binary messages"""
        messages = []
        current_time = time.time()
        
        while len(self.buffer) >= 23:  # Minimum beast message size
            # Look for beast message start (0x1A)
            start_idx = self.buffer.find(b'\x1a')
            if start_idx == -1:
                # No start marker found, clear buffer
                self.buffer = b""
                break
            
            # Remove data before start marker
            if start_idx > 0:
                self.buffer = self.buffer[start_idx:]
            
            # Check if we have enough data for a complete message
            if len(self.buffer) < 23:
                break
            
            try:
                # Beast format: 1A <type> <timestamp> <signal> <message>
                message_type = self.buffer[1]
                
                # Different message types have different lengths
                if message_type == 0x31:  # Mode AC
                    msg_len = 16
                elif message_type == 0x32:  # Mode S short
                    msg_len = 16  
                elif message_type == 0x33:  # Mode S long
                    msg_len = 23
                else:
                    # Unknown type, skip this byte and continue
                    self.buffer = self.buffer[1:]
                    continue
                
                if len(self.buffer) < msg_len:
                    break
                
                # Extract message data (skip header bytes)
                if message_type == 0x33:  # Mode S long (14 bytes of data)
                    message_data = self.buffer[9:23]
                elif message_type == 0x32:  # Mode S short (7 bytes of data)
                    message_data = self.buffer[9:16]
                else:
                    # Skip unsupported message types
                    self.buffer = self.buffer[msg_len:]
                    continue
                
                # Convert to hex string
                message_hex = message_data.hex().upper()
                messages.append((message_hex, current_time))
                
                # Remove processed message from buffer
                self.buffer = self.buffer[msg_len:]
                
            except Exception as e:
                logger.debug(f"Error parsing beast message: {e}")
                # Skip this byte and continue
                self.buffer = self.buffer[1:]
                continue
        
        return messages
    
    def _parse_json_messages(self) -> List[Tuple[str, float]]:
        """Parse JSON format messages from dump1090"""
        messages = []
        current_time = time.time()
        
        # Split buffer by newlines
        lines = self.buffer.split(b'\n')
        
        # Keep the last incomplete line in buffer
        self.buffer = lines[-1]
        
        # Process complete lines
        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue
            
            try:
                # Parse JSON
                data = json.loads(line.decode('utf-8'))
                
                # Extract hex message if present
                if 'hex' in data:
                    message_hex = data['hex'].upper()
                    messages.append((message_hex, current_time))
                
            except Exception as e:
                logger.debug(f"Error parsing JSON message: {e}")
                continue
        
        return messages
    
    def get_status(self) -> Dict[str, Any]:
        """Get extended status information"""
        status = super().get_status()
        status.update({
            'host': self.host,
            'port': self.port,
            'format_type': self.format_type,
            'buffer_size': len(self.buffer) if self.buffer else 0,
            'last_reconnect_attempt': self.last_reconnect_attempt
        })
        return status


class NetworkSource(MessageSource):
    """
    Generic network TCP source for ADS-B messages
    
    Supports raw, beast, and skysense data formats over TCP connections.
    Can be used for various network-based ADS-B sources beyond dump1090.
    """
    
    def __init__(self, name: str, host: str, port: int, 
                 format_type: str = "raw", reconnect_interval: int = 5,
                 buffer_size: int = 8192):
        """
        Initialize network source
        
        Args:
            name: Human-readable name for this source
            host: Remote host address
            port: Remote port number
            format_type: "raw", "beast", or "skysense"
            reconnect_interval: Seconds between reconnection attempts
            buffer_size: Socket receive buffer size
        """
        super().__init__(name)
        self.host = host
        self.port = port
        self.format_type = format_type.lower()
        self.reconnect_interval = reconnect_interval
        self.buffer_size = buffer_size
        
        self.socket: Optional[socket.socket] = None
        self.buffer = b""
        self.last_reconnect_attempt = 0
        
        # Validate format type
        if self.format_type not in ["raw", "beast", "skysense"]:
            raise ValueError(f"Unsupported format type: {format_type}")
    
    def connect(self) -> bool:
        """Connect to network source"""
        try:
            logger.info(f"Connecting to network source at {self.host}:{self.port} ({self.format_type})")
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)  # 10 second timeout for connection
            self.socket.connect((self.host, self.port))
            
            # Set socket to non-blocking for message reading
            self.socket.setblocking(False)
            
            # Set buffer size
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.buffer_size)
            
            self.connected = True
            self.buffer = b""
            logger.info(f"Connected to network source: {self.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to network source {self.name}: {e}")
            self.connected = False
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False
    
    def disconnect(self) -> None:
        """Disconnect from network source"""
        logger.info(f"Disconnecting from network source: {self.name}")
        self.connected = False
        
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        self.buffer = b""
    
    def get_messages(self) -> List[Tuple[str, float]]:
        """Get messages from network source"""
        if not self.connected or not self.socket:
            # Try to reconnect if enough time has passed
            current_time = time.time()
            if current_time - self.last_reconnect_attempt >= self.reconnect_interval:
                self.last_reconnect_attempt = current_time
                logger.debug(f"Attempting to reconnect to {self.name}")
                self.connect()
            return []
        
        try:
            # Read data from socket
            data = self.socket.recv(self.buffer_size)
            if not data:
                # Connection closed by remote
                logger.warning(f"Connection closed by remote: {self.name}")
                self.disconnect()
                return []
            
            self.buffer += data
            
            # Parse messages based on format type
            if self.format_type == "raw":
                return self._parse_raw_messages()
            elif self.format_type == "beast":
                return self._parse_beast_messages()
            elif self.format_type == "skysense":
                return self._parse_skysense_messages()
            
        except socket.error as e:
            if e.errno not in [socket.EAGAIN, socket.EWOULDBLOCK]:
                logger.error(f"Socket error on {self.name}: {e}")
                self.disconnect()
        except Exception as e:
            logger.error(f"Error reading from network source {self.name}: {e}")
            self.error_count += 1
        
        return []
    
    def _parse_raw_messages(self) -> List[Tuple[str, float]]:
        """Parse raw ASCII hex messages"""
        messages = []
        current_time = time.time()
        
        # Split buffer by newlines
        lines = self.buffer.split(b'\n')
        
        # Keep the last incomplete line in buffer
        self.buffer = lines[-1]
        
        # Process complete lines
        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue
            
            try:
                # Raw format is typically just hex strings
                message_hex = line.decode('ascii').strip()
                
                # Remove any prefixes (like asterisks or timestamps)
                if message_hex.startswith('*'):
                    message_hex = message_hex[1:]
                
                # Extract just the hex part (remove any trailing data)
                hex_part = ""
                for char in message_hex:
                    if char in '0123456789ABCDEFabcdef':
                        hex_part += char
                    else:
                        break
                
                # Validate hex format (should be even length, minimum 14 chars for Mode S)
                if len(hex_part) >= 14 and len(hex_part) % 2 == 0:
                    messages.append((hex_part.upper(), current_time))
                
            except Exception as e:
                logger.debug(f"Error parsing raw message: {e}")
                continue
        
        return messages
    
    def _parse_beast_messages(self) -> List[Tuple[str, float]]:
        """Parse beast format binary messages"""
        messages = []
        current_time = time.time()
        
        while len(self.buffer) >= 23:  # Minimum beast message size
            # Look for beast message start (0x1A)
            start_idx = self.buffer.find(b'\x1a')
            if start_idx == -1:
                # No start marker found, clear buffer
                self.buffer = b""
                break
            
            # Remove data before start marker
            if start_idx > 0:
                self.buffer = self.buffer[start_idx:]
            
            # Check if we have enough data for a complete message
            if len(self.buffer) < 23:
                break
            
            try:
                # Beast format: 1A <type> <timestamp> <signal> <message>
                message_type = self.buffer[1]
                
                # Different message types have different lengths
                if message_type == 0x31:  # Mode AC
                    msg_len = 16
                elif message_type == 0x32:  # Mode S short
                    msg_len = 16  
                elif message_type == 0x33:  # Mode S long
                    msg_len = 23
                else:
                    # Unknown type, skip this byte and continue
                    self.buffer = self.buffer[1:]
                    continue
                
                if len(self.buffer) < msg_len:
                    break
                
                # Extract message data (skip header bytes)
                if message_type == 0x33:  # Mode S long (14 bytes of data)
                    message_data = self.buffer[9:23]
                elif message_type == 0x32:  # Mode S short (7 bytes of data)
                    message_data = self.buffer[9:16]
                else:
                    # Skip unsupported message types
                    self.buffer = self.buffer[msg_len:]
                    continue
                
                # Convert to hex string
                message_hex = message_data.hex().upper()
                messages.append((message_hex, current_time))
                
                # Remove processed message from buffer
                self.buffer = self.buffer[msg_len:]
                
            except Exception as e:
                logger.debug(f"Error parsing beast message: {e}")
                # Skip this byte and continue
                self.buffer = self.buffer[1:]
                continue
        
        return messages
    
    def _parse_skysense_messages(self) -> List[Tuple[str, float]]:
        """Parse skysense format messages"""
        messages = []
        current_time = time.time()
        
        # Skysense format is similar to raw but may have different delimiters
        # Split buffer by newlines or semicolons
        lines = self.buffer.replace(b';', b'\n').split(b'\n')
        
        # Keep the last incomplete line in buffer
        self.buffer = lines[-1]
        
        # Process complete lines
        for line in lines[:-1]:
            line = line.strip()
            if not line:
                continue
            
            try:
                # Decode line
                line_str = line.decode('ascii').strip()
                
                # Skysense may have format like: timestamp,hex_message
                if ',' in line_str:
                    parts = line_str.split(',')
                    if len(parts) >= 2:
                        message_hex = parts[-1].strip()  # Take last part as hex
                    else:
                        message_hex = line_str
                else:
                    message_hex = line_str
                
                # Remove any non-hex characters from start
                while message_hex and message_hex[0] not in '0123456789ABCDEFabcdef':
                    message_hex = message_hex[1:]
                
                # Extract hex part
                hex_part = ""
                for char in message_hex:
                    if char in '0123456789ABCDEFabcdef':
                        hex_part += char
                    else:
                        break
                
                # Validate hex format
                if len(hex_part) >= 14 and len(hex_part) % 2 == 0:
                    messages.append((hex_part.upper(), current_time))
                
            except Exception as e:
                logger.debug(f"Error parsing skysense message: {e}")
                continue
        
        return messages
    
    def get_status(self) -> Dict[str, Any]:
        """Get extended status information"""
        status = super().get_status()
        status.update({
            'host': self.host,
            'port': self.port,
            'format_type': self.format_type,
            'buffer_size': self.buffer_size,
            'current_buffer_size': len(self.buffer) if self.buffer else 0,
            'last_reconnect_attempt': self.last_reconnect_attempt
        })
        return status