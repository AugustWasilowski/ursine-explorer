# Enhanced Meshtastic API Documentation

## Overview

This document provides comprehensive API documentation for the enhanced Meshtastic integration classes and methods in UrsineExplorer. The enhanced system supports encrypted channels, MQTT connectivity, and dual-mode operation.

## Core Classes

### MeshtasticManager

Central coordinator for all Meshtastic operations.

```python
class MeshtasticManager:
    """
    Main coordinator class for enhanced Meshtastic functionality.
    Manages both serial and MQTT connections with automatic failover.
    """
    
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the Meshtastic manager.
        
        Args:
            config: Configuration dictionary containing Meshtastic settings
        """
    
    def initialize(self) -> bool:
        """
        Initialize all configured interfaces and connections.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
    
    def send_alert(self, aircraft: Aircraft, alert_type: str) -> bool:
        """
        Send an alert message for the specified aircraft.
        
        Args:
            aircraft: Aircraft object containing flight data
            alert_type: Type of alert ("watchlist", "emergency", "proximity")
            
        Returns:
            bool: True if message sent successfully via at least one interface
        """
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get detailed connection status for all interfaces.
        
        Returns:
            Dict containing connection status, health metrics, and statistics
        """
    
    def configure_channels(self, channels: List[ChannelConfig]) -> bool:
        """
        Configure Meshtastic channels with encryption settings.
        
        Args:
            channels: List of ChannelConfig objects
            
        Returns:
            bool: True if configuration successful
        """
    
    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about connected Meshtastic device.
        
        Returns:
            Dict containing device info (node ID, hardware, firmware) or None
        """
    
    def test_connectivity(self) -> Dict[str, bool]:
        """
        Test connectivity of all configured interfaces.
        
        Returns:
            Dict mapping interface names to connectivity status
        """
    
    def shutdown(self) -> None:
        """
        Gracefully shutdown all interfaces and connections.
        """
```

### ChannelManager

Manages Meshtastic channel configuration and selection.

```python
class ChannelManager:
    """
    Handles Meshtastic channel configuration, encryption, and selection.
    """
    
    def __init__(self, channels: List[ChannelConfig]) -> None:
        """
        Initialize channel manager with channel configurations.
        
        Args:
            channels: List of ChannelConfig objects
        """
    
    def get_channel_by_name(self, name: str) -> Optional[ChannelConfig]:
        """
        Get channel configuration by name.
        
        Args:
            name: Channel name
            
        Returns:
            ChannelConfig object or None if not found
        """
    
    def get_default_channel(self) -> ChannelConfig:
        """
        Get the default channel configuration.
        
        Returns:
            Default ChannelConfig object
        """
    
    def validate_channel_config(self, config: ChannelConfig) -> Tuple[bool, str]:
        """
        Validate a channel configuration.
        
        Args:
            config: ChannelConfig to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
    
    def apply_channel_settings(self, device_interface) -> bool:
        """
        Apply channel settings to a device interface.
        
        Args:
            device_interface: Device interface to configure
            
        Returns:
            bool: True if settings applied successfully
        """
```

### ChannelConfig

Data class for channel configuration.

```python
@dataclass
class ChannelConfig:
    """
    Configuration for a Meshtastic channel.
    """
    name: str                    # Channel name (e.g., "LongFast", "SecureAlerts")
    psk: Optional[str] = None    # Base64 encoded PSK for encryption
    channel_number: int = 0      # Channel number (0-7)
    uplink_enabled: bool = True  # Enable uplink transmission
    downlink_enabled: bool = True # Enable downlink reception
    
    def is_encrypted(self) -> bool:
        """Check if channel uses encryption."""
        return self.psk is not None
    
    def validate_psk(self) -> bool:
        """Validate PSK format (Base64)."""
        # Implementation validates Base64 encoding
```

### EncryptionHandler

Handles PSK encryption and decryption.

```python
class EncryptionHandler:
    """
    Handles PSK-based message encryption for Meshtastic channels.
    """
    
    def encrypt_message(self, message: str, psk: str) -> bytes:
        """
        Encrypt a message using PSK.
        
        Args:
            message: Plain text message to encrypt
            psk: Base64 encoded PSK
            
        Returns:
            Encrypted message bytes
        """
    
    def decrypt_message(self, encrypted_data: bytes, psk: str) -> str:
        """
        Decrypt a message using PSK.
        
        Args:
            encrypted_data: Encrypted message bytes
            psk: Base64 encoded PSK
            
        Returns:
            Decrypted plain text message
        """
    
    def generate_psk(self) -> str:
        """
        Generate a cryptographically secure PSK.
        
        Returns:
            Base64 encoded PSK
        """
    
    def validate_psk(self, psk: str) -> bool:
        """
        Validate PSK format and strength.
        
        Args:
            psk: Base64 encoded PSK to validate
            
        Returns:
            bool: True if PSK is valid
        """
```

### EnhancedSerialInterface

Enhanced USB serial communication interface.

```python
class EnhancedSerialInterface(MeshtasticInterface):
    """
    Enhanced serial interface for USB Meshtastic device communication.
    """
    
    def __init__(self, port: str, baud: int, channel_manager: ChannelManager) -> None:
        """
        Initialize enhanced serial interface.
        
        Args:
            port: Serial port path (e.g., "/dev/ttyUSB0")
            baud: Baud rate (typically 115200)
            channel_manager: ChannelManager instance
        """
    
    def connect(self) -> bool:
        """
        Connect to the Meshtastic device.
        
        Returns:
            bool: True if connection successful
        """
    
    def disconnect(self) -> None:
        """
        Disconnect from the device.
        """
    
    def send_message(self, message: str, channel: str = None) -> bool:
        """
        Send a message via the serial interface.
        
        Args:
            message: Message text to send
            channel: Channel name (uses default if None)
            
        Returns:
            bool: True if message sent successfully
        """
    
    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """
        Get device information.
        
        Returns:
            Dict containing device info or None if unavailable
        """
    
    def configure_channels(self, channels: List[ChannelConfig]) -> bool:
        """
        Configure device channels.
        
        Args:
            channels: List of channel configurations
            
        Returns:
            bool: True if configuration successful
        """
    
    def is_connected(self) -> bool:
        """
        Check if device is connected.
        
        Returns:
            bool: True if connected
        """
    
    def get_signal_strength(self) -> Optional[float]:
        """
        Get current signal strength.
        
        Returns:
            Signal strength in dBm or None if unavailable
        """
```

### MeshtasticMQTTInterface

MQTT-based network interface.

```python
class MeshtasticMQTTInterface(MeshtasticInterface):
    """
    MQTT interface for network-based Meshtastic communication.
    """
    
    def __init__(self, broker_config: MQTTConfig, channel_manager: ChannelManager) -> None:
        """
        Initialize MQTT interface.
        
        Args:
            broker_config: MQTT broker configuration
            channel_manager: ChannelManager instance
        """
    
    def connect(self) -> bool:
        """
        Connect to MQTT broker.
        
        Returns:
            bool: True if connection successful
        """
    
    def disconnect(self) -> None:
        """
        Disconnect from MQTT broker.
        """
    
    def send_message(self, message: str, channel: str = None) -> bool:
        """
        Send message via MQTT.
        
        Args:
            message: Message text to send
            channel: Channel name (uses default if None)
            
        Returns:
            bool: True if message published successfully
        """
    
    def subscribe_to_channels(self, channels: List[str]) -> bool:
        """
        Subscribe to MQTT topics for specified channels.
        
        Args:
            channels: List of channel names to subscribe to
            
        Returns:
            bool: True if subscriptions successful
        """
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get MQTT connection status and statistics.
        
        Returns:
            Dict containing connection status and metrics
        """
```

### MQTTConfig

Configuration for MQTT broker connection.

```python
@dataclass
class MQTTConfig:
    """
    Configuration for MQTT broker connection.
    """
    broker_url: str                    # MQTT broker hostname/IP
    port: int = 1883                   # MQTT broker port
    username: Optional[str] = None     # Authentication username
    password: Optional[str] = None     # Authentication password
    use_tls: bool = False             # Enable TLS encryption
    client_id: Optional[str] = None    # MQTT client ID
    topic_prefix: str = "msh/US"      # Topic prefix for region
    qos: int = 0                      # Quality of Service level
    keepalive: int = 60               # Keepalive interval in seconds
    
    def get_topic_for_channel(self, channel: str) -> str:
        """
        Generate MQTT topic for a channel.
        
        Args:
            channel: Channel name
            
        Returns:
            Full MQTT topic string
        """
```

### MessageRouter

Routes messages between multiple interfaces.

```python
class MessageRouter:
    """
    Routes messages between serial and MQTT interfaces with failover.
    """
    
    def __init__(self, interfaces: List[MeshtasticInterface]) -> None:
        """
        Initialize message router.
        
        Args:
            interfaces: List of available interfaces
        """
    
    def route_message(self, message: AlertMessage, routing_policy: str = "all") -> List[bool]:
        """
        Route message according to policy.
        
        Args:
            message: AlertMessage to route
            routing_policy: "all", "primary", or "fallback"
            
        Returns:
            List of delivery results for each interface
        """
    
    def set_routing_policy(self, policy: str) -> None:
        """
        Set message routing policy.
        
        Args:
            policy: "all", "primary", or "fallback"
        """
    
    def get_delivery_stats(self) -> Dict[str, Any]:
        """
        Get message delivery statistics.
        
        Returns:
            Dict containing delivery metrics and success rates
        """
```

### AlertMessage

Data class for alert messages.

```python
@dataclass
class AlertMessage:
    """
    Represents an alert message with metadata.
    """
    content: str                                    # Message content
    channel: str                                   # Target channel
    priority: int = 1                              # Message priority (1-5)
    retry_count: int = 0                           # Current retry count
    max_retries: int = 3                           # Maximum retry attempts
    timestamp: datetime = field(default_factory=datetime.now)  # Creation time
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
    
    def is_expired(self, timeout_seconds: int = 300) -> bool:
        """Check if message has expired."""
```

### DeliveryTracker

Tracks message delivery and handles retries.

```python
class DeliveryTracker:
    """
    Tracks message delivery status and handles retry logic.
    """
    
    def track_message(self, message_id: str, interfaces: List[str]) -> None:
        """
        Start tracking a message delivery.
        
        Args:
            message_id: Unique message identifier
            interfaces: List of interface names message was sent to
        """
    
    def confirm_delivery(self, message_id: str, interface: str) -> None:
        """
        Confirm successful delivery via an interface.
        
        Args:
            message_id: Message identifier
            interface: Interface name that confirmed delivery
        """
    
    def get_failed_messages(self) -> List[AlertMessage]:
        """
        Get list of messages that failed delivery.
        
        Returns:
            List of AlertMessage objects that need retry
        """
    
    def retry_failed_messages(self) -> int:
        """
        Retry delivery of failed messages.
        
        Returns:
            Number of messages retried
        """
    
    def get_delivery_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive delivery statistics.
        
        Returns:
            Dict containing success rates, retry counts, etc.
        """
```

### MeshtasticDiagnostics

Comprehensive diagnostics and monitoring.

```python
class MeshtasticDiagnostics:
    """
    Provides comprehensive diagnostics for Meshtastic system.
    """
    
    def get_connection_health(self) -> Dict[str, Any]:
        """
        Get comprehensive connection health information.
        
        Returns:
            Dict containing health status for all interfaces
        """
    
    def get_message_statistics(self) -> Dict[str, Any]:
        """
        Get message delivery and processing statistics.
        
        Returns:
            Dict containing message metrics and performance data
        """
    
    def test_all_interfaces(self) -> Dict[str, bool]:
        """
        Test connectivity of all configured interfaces.
        
        Returns:
            Dict mapping interface names to test results
        """
    
    def validate_configuration(self) -> List[str]:
        """
        Validate current configuration and identify issues.
        
        Returns:
            List of validation error messages (empty if valid)
        """
    
    def generate_health_report(self) -> str:
        """
        Generate comprehensive health report.
        
        Returns:
            Formatted health report string
        """
```

## Usage Examples

### Basic Setup

```python
from pymodes_integration.meshtastic_enhanced import (
    MeshtasticManager, ChannelConfig, MQTTConfig
)

# Configure channels
channels = [
    ChannelConfig(name="LongFast", psk=None, channel_number=0),
    ChannelConfig(name="SecureAlerts", psk="your_base64_psk", channel_number=1)
]

# Configure MQTT
mqtt_config = MQTTConfig(
    broker_url="mqtt.meshtastic.org",
    port=1883,
    topic_prefix="msh/US"
)

# Initialize manager
config = {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "channels": channels,
    "mqtt": mqtt_config,
    "connection_mode": "dual"
}

manager = MeshtasticManager(config)
if manager.initialize():
    print("Meshtastic system initialized successfully")
```

### Sending Alerts

```python
# Send alert for watchlist aircraft
aircraft = Aircraft(icao="A12345", callsign="UAL123", latitude=40.7128, longitude=-74.0060)
success = manager.send_alert(aircraft, "watchlist")

if success:
    print("Alert sent successfully")
else:
    print("Alert delivery failed")
```

### Channel Management

```python
from pymodes_integration.meshtastic_enhanced import ChannelManager, EncryptionHandler

# Generate secure PSK
encryption = EncryptionHandler()
new_psk = encryption.generate_psk()

# Create encrypted channel
secure_channel = ChannelConfig(
    name="EmergencyAlerts",
    psk=new_psk,
    channel_number=2
)

# Validate configuration
channel_manager = ChannelManager([secure_channel])
is_valid, error = channel_manager.validate_channel_config(secure_channel)

if is_valid:
    print("Channel configuration is valid")
else:
    print(f"Configuration error: {error}")
```

### MQTT Integration

```python
from pymodes_integration.meshtastic_enhanced import MeshtasticMQTTInterface

# Configure MQTT with authentication
mqtt_config = MQTTConfig(
    broker_url="your-broker.example.com",
    port=8883,
    username="adsb_user",
    password="secure_password",
    use_tls=True,
    client_id="ursine_explorer_001"
)

# Initialize MQTT interface
mqtt_interface = MeshtasticMQTTInterface(mqtt_config, channel_manager)

if mqtt_interface.connect():
    # Subscribe to channels
    mqtt_interface.subscribe_to_channels(["LongFast", "SecureAlerts"])
    
    # Send test message
    mqtt_interface.send_message("Test message", "LongFast")
```

### Diagnostics and Monitoring

```python
from pymodes_integration.meshtastic_enhanced import MeshtasticDiagnostics

# Initialize diagnostics
diagnostics = MeshtasticDiagnostics(manager)

# Get health status
health = diagnostics.get_connection_health()
print(f"Serial interface: {health['serial']['status']}")
print(f"MQTT interface: {health['mqtt']['status']}")

# Test all interfaces
test_results = diagnostics.test_all_interfaces()
for interface, result in test_results.items():
    print(f"{interface}: {'OK' if result else 'FAILED'}")

# Validate configuration
errors = diagnostics.validate_configuration()
if errors:
    print("Configuration issues found:")
    for error in errors:
        print(f"  - {error}")
```

## Error Handling

### Common Exceptions

```python
class MeshtasticConnectionError(Exception):
    """Raised when connection to Meshtastic device fails."""

class MeshtasticConfigurationError(Exception):
    """Raised when configuration is invalid."""

class MeshtasticEncryptionError(Exception):
    """Raised when encryption/decryption fails."""

class MQTTConnectionError(Exception):
    """Raised when MQTT broker connection fails."""
```

### Error Handling Example

```python
try:
    manager = MeshtasticManager(config)
    manager.initialize()
except MeshtasticConfigurationError as e:
    print(f"Configuration error: {e}")
except MeshtasticConnectionError as e:
    print(f"Connection error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Configuration Migration

### Legacy Configuration Support

The system automatically migrates legacy configurations:

```python
# Legacy format (automatically detected and migrated)
legacy_config = {
    "meshtastic_enabled": True,
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200
}

# Enhanced format (migrated to)
enhanced_config = {
    "meshtastic": {
        "meshtastic_port": "/dev/ttyUSB0",
        "meshtastic_baud": 115200,
        "channels": [
            {"name": "LongFast", "psk": None, "channel_number": 0}
        ],
        "default_channel": "LongFast",
        "connection_mode": "serial",
        "enable_encryption": False
    }
}
```

## Performance Considerations

### Optimization Settings

```python
# High-throughput configuration
config = {
    "message_format": "compact",
    "max_message_length": 100,
    "mqtt": {
        "qos": 0,  # Faster delivery, no confirmation
        "keepalive": 300  # Longer keepalive for stability
    },
    "health_check_interval": 120,  # Less frequent health checks
    "retry_interval": 15  # Faster retry for failed messages
}

# High-reliability configuration
config = {
    "message_format": "standard",
    "failover_enabled": True,
    "connection_mode": "dual",
    "mqtt": {
        "qos": 1,  # Confirmed delivery
        "keepalive": 60
    },
    "health_check_interval": 30,  # Frequent health monitoring
    "retry_interval": 30,
    "max_retries": 5
}
```

This API documentation provides comprehensive coverage of all enhanced Meshtastic classes and methods, with practical examples and best practices for implementation.