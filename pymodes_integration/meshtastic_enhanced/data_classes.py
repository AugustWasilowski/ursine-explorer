"""
Data classes for enhanced Meshtastic integration

This module contains all the data structures used throughout
the enhanced Meshtastic system.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ConnectionState(Enum):
    """Enumeration of possible connection states"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"
    UNKNOWN = "unknown"


class MessagePriority(Enum):
    """Message priority levels"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class RoutingPolicy(Enum):
    """Message routing policies"""
    ALL = "all"          # Send to all available interfaces
    PRIMARY = "primary"  # Send to primary interface only
    FALLBACK = "fallback"  # Send to fallback if primary fails
    LOAD_BALANCE = "load_balance"  # Distribute across interfaces


@dataclass
class ChannelConfig:
    """
    Configuration for a Meshtastic channel
    
    Attributes:
        name: Human-readable channel name
        psk: Base64 encoded pre-shared key (None for unencrypted)
        channel_number: Channel number (0-7)
        uplink_enabled: Whether uplink is enabled
        downlink_enabled: Whether downlink is enabled
        max_hops: Maximum number of hops for messages
        tx_power: Transmission power level
    """
    name: str
    psk: Optional[str] = None
    channel_number: int = 0
    uplink_enabled: bool = True
    downlink_enabled: bool = True
    max_hops: int = 3
    tx_power: int = 0  # 0 = default power
    
    def __post_init__(self):
        """Validate channel configuration after initialization"""
        if not self.name:
            raise ValueError("Channel name cannot be empty")
        
        if not (0 <= self.channel_number <= 7):
            raise ValueError("Channel number must be between 0 and 7")
        
        if self.psk is not None and not self.psk:
            raise ValueError("PSK cannot be empty string (use None for unencrypted)")
    
    @property
    def is_encrypted(self) -> bool:
        """Check if this channel uses encryption"""
        return self.psk is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'name': self.name,
            'psk': self.psk,
            'channel_number': self.channel_number,
            'uplink_enabled': self.uplink_enabled,
            'downlink_enabled': self.downlink_enabled,
            'max_hops': self.max_hops,
            'tx_power': self.tx_power
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChannelConfig':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class MQTTConfig:
    """
    Configuration for MQTT broker connection
    
    Attributes:
        broker_url: MQTT broker hostname or IP
        port: MQTT broker port
        username: Optional username for authentication
        password: Optional password for authentication
        use_tls: Whether to use TLS encryption
        client_id: Optional client ID (auto-generated if None)
        topic_prefix: Prefix for MQTT topics
        qos: Quality of Service level (0, 1, or 2)
        keepalive: Keepalive interval in seconds
        clean_session: Whether to use clean session
        will_topic: Optional last will topic
        will_message: Optional last will message
    """
    broker_url: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = False
    client_id: Optional[str] = None
    topic_prefix: str = "msh/US"
    qos: int = 0
    keepalive: int = 60
    clean_session: bool = True
    will_topic: Optional[str] = None
    will_message: Optional[str] = None
    
    def __post_init__(self):
        """Validate MQTT configuration after initialization"""
        if not self.broker_url:
            raise ValueError("Broker URL cannot be empty")
        
        if not (1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        
        if self.qos not in [0, 1, 2]:
            raise ValueError("QoS must be 0, 1, or 2")
        
        if self.keepalive < 1:
            raise ValueError("Keepalive must be positive")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'broker_url': self.broker_url,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'use_tls': self.use_tls,
            'client_id': self.client_id,
            'topic_prefix': self.topic_prefix,
            'qos': self.qos,
            'keepalive': self.keepalive,
            'clean_session': self.clean_session,
            'will_topic': self.will_topic,
            'will_message': self.will_message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MQTTConfig':
        """Create from dictionary"""
        return cls(**data)


@dataclass
class MeshtasticConfig:
    """
    Main configuration for enhanced Meshtastic integration
    
    Attributes:
        # Legacy compatibility
        meshtastic_port: Serial port for USB connection
        meshtastic_baud: Baud rate for serial connection
        
        # Enhanced configuration
        channels: List of channel configurations
        default_channel: Name of default channel to use
        mqtt: Optional MQTT configuration
        connection_mode: Connection mode ("serial", "mqtt", "dual")
        failover_enabled: Whether to enable automatic failover
        connection_timeout: Connection timeout in seconds
        retry_interval: Retry interval for failed connections
        
        # Message settings
        message_format: Message format ("standard", "compact", "json")
        include_position: Whether to include position in messages
        include_timestamp: Whether to include timestamp in messages
        max_message_length: Maximum message length in characters
        
        # Advanced settings
        auto_detect_device: Whether to auto-detect serial devices
        enable_encryption: Whether encryption is enabled
        log_all_messages: Whether to log all messages
        health_check_interval: Health check interval in seconds
    """
    # Legacy compatibility
    meshtastic_port: str = "/dev/ttyUSB0"
    meshtastic_baud: int = 115200
    
    # Enhanced channel configuration
    channels: List[ChannelConfig] = field(default_factory=list)
    default_channel: str = "LongFast"
    
    # MQTT configuration
    mqtt: Optional[MQTTConfig] = None
    
    # Connection settings
    connection_mode: str = "dual"  # "serial", "mqtt", "dual"
    failover_enabled: bool = True
    connection_timeout: int = 10
    retry_interval: int = 30
    
    # Message settings
    message_format: str = "standard"  # "standard", "compact", "json"
    include_position: bool = True
    include_timestamp: bool = True
    max_message_length: int = 200
    
    # Advanced settings
    auto_detect_device: bool = True
    enable_encryption: bool = True
    log_all_messages: bool = False
    health_check_interval: int = 60
    
    def __post_init__(self):
        """Validate configuration after initialization"""
        if self.connection_mode not in ["serial", "mqtt", "dual"]:
            raise ValueError("Connection mode must be 'serial', 'mqtt', or 'dual'")
        
        if self.message_format not in ["standard", "compact", "json"]:
            raise ValueError("Message format must be 'standard', 'compact', or 'json'")
        
        if self.connection_timeout < 1:
            raise ValueError("Connection timeout must be positive")
        
        if self.retry_interval < 1:
            raise ValueError("Retry interval must be positive")
        
        if self.max_message_length < 10:
            raise ValueError("Max message length must be at least 10 characters")
        
        if self.health_check_interval < 1:
            raise ValueError("Health check interval must be positive")
        
        # Ensure we have a default channel if channels are configured
        if self.channels and not any(ch.name == self.default_channel for ch in self.channels):
            # Add default LongFast channel if not present
            self.channels.insert(0, ChannelConfig(name=self.default_channel))
    
    def get_default_channel_config(self) -> ChannelConfig:
        """Get the default channel configuration"""
        for channel in self.channels:
            if channel.name == self.default_channel:
                return channel
        
        # Return basic default if not found
        return ChannelConfig(name=self.default_channel)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'meshtastic_port': self.meshtastic_port,
            'meshtastic_baud': self.meshtastic_baud,
            'channels': [ch.to_dict() for ch in self.channels],
            'default_channel': self.default_channel,
            'mqtt': self.mqtt.to_dict() if self.mqtt else None,
            'connection_mode': self.connection_mode,
            'failover_enabled': self.failover_enabled,
            'connection_timeout': self.connection_timeout,
            'retry_interval': self.retry_interval,
            'message_format': self.message_format,
            'include_position': self.include_position,
            'include_timestamp': self.include_timestamp,
            'max_message_length': self.max_message_length,
            'auto_detect_device': self.auto_detect_device,
            'enable_encryption': self.enable_encryption,
            'log_all_messages': self.log_all_messages,
            'health_check_interval': self.health_check_interval
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MeshtasticConfig':
        """Create from dictionary"""
        # Handle channels
        channels = []
        if 'channels' in data:
            channels = [ChannelConfig.from_dict(ch) for ch in data['channels']]
        
        # Handle MQTT config
        mqtt_config = None
        if data.get('mqtt'):
            mqtt_config = MQTTConfig.from_dict(data['mqtt'])
        
        # Create config with processed data
        config_data = data.copy()
        config_data['channels'] = channels
        config_data['mqtt'] = mqtt_config
        
        return cls(**config_data)


@dataclass
class AlertMessage:
    """
    Represents an alert message to be sent via Meshtastic
    
    Attributes:
        content: The message content
        channel: Channel name to send on
        priority: Message priority level
        retry_count: Number of retry attempts made
        max_retries: Maximum number of retries allowed
        timestamp: When the message was created
        aircraft_icao: Optional ICAO code of related aircraft
        alert_type: Type of alert (watchlist, emergency, etc.)
        position: Optional position tuple (lat, lon)
        metadata: Additional metadata dictionary
    """
    content: str
    channel: str
    priority: MessagePriority = MessagePriority.MEDIUM
    retry_count: int = 0
    max_retries: int = 3
    timestamp: datetime = field(default_factory=datetime.now)
    aircraft_icao: Optional[str] = None
    alert_type: Optional[str] = None
    position: Optional[tuple[float, float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate message after initialization"""
        if not self.content:
            raise ValueError("Message content cannot be empty")
        
        if not self.channel:
            raise ValueError("Channel cannot be empty")
        
        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")
    
    @property
    def can_retry(self) -> bool:
        """Check if message can be retried"""
        return self.retry_count < self.max_retries
    
    def increment_retry(self) -> None:
        """Increment retry count"""
        self.retry_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'content': self.content,
            'channel': self.channel,
            'priority': self.priority.value,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'timestamp': self.timestamp.isoformat(),
            'aircraft_icao': self.aircraft_icao,
            'alert_type': self.alert_type,
            'position': self.position,
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertMessage':
        """Create from dictionary"""
        # Convert priority back to enum
        priority = MessagePriority(data.get('priority', MessagePriority.MEDIUM.value))
        
        # Convert timestamp back to datetime
        timestamp = datetime.fromisoformat(data['timestamp']) if 'timestamp' in data else datetime.now()
        
        return cls(
            content=data['content'],
            channel=data['channel'],
            priority=priority,
            retry_count=data.get('retry_count', 0),
            max_retries=data.get('max_retries', 3),
            timestamp=timestamp,
            aircraft_icao=data.get('aircraft_icao'),
            alert_type=data.get('alert_type'),
            position=data.get('position'),
            metadata=data.get('metadata', {})
        )


@dataclass
class ConnectionStatus:
    """
    Represents the status of a Meshtastic interface connection
    
    Attributes:
        interface_type: Type of interface ("serial", "mqtt")
        state: Current connection state
        connected_since: When connection was established (None if not connected)
        last_message_time: When last message was sent/received
        error_message: Last error message (None if no error)
        device_info: Optional device information dictionary
        statistics: Connection statistics dictionary
    """
    interface_type: str
    state: ConnectionState
    connected_since: Optional[datetime] = None
    last_message_time: Optional[datetime] = None
    error_message: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None
    statistics: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_connected(self) -> bool:
        """Check if connection is active"""
        return self.state == ConnectionState.CONNECTED
    
    @property
    def uptime_seconds(self) -> Optional[float]:
        """Get connection uptime in seconds"""
        if self.connected_since and self.is_connected:
            return (datetime.now() - self.connected_since).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'interface_type': self.interface_type,
            'state': self.state.value,
            'connected_since': self.connected_since.isoformat() if self.connected_since else None,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None,
            'error_message': self.error_message,
            'device_info': self.device_info,
            'statistics': self.statistics,
            'uptime_seconds': self.uptime_seconds
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConnectionStatus':
        """Create from dictionary"""
        # Convert state back to enum
        state = ConnectionState(data['state'])
        
        # Convert timestamps back to datetime
        connected_since = None
        if data.get('connected_since'):
            connected_since = datetime.fromisoformat(data['connected_since'])
        
        last_message_time = None
        if data.get('last_message_time'):
            last_message_time = datetime.fromisoformat(data['last_message_time'])
        
        return cls(
            interface_type=data['interface_type'],
            state=state,
            connected_since=connected_since,
            last_message_time=last_message_time,
            error_message=data.get('error_message'),
            device_info=data.get('device_info'),
            statistics=data.get('statistics', {})
        )