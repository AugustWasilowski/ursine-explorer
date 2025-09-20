"""
Enhanced Meshtastic configuration management and validation.

This module provides specialized configuration handling for the enhanced
Meshtastic integration, including validation, migration, and helper utilities.
"""

import base64
import logging
import re
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ChannelConfig:
    """Meshtastic channel configuration with validation."""
    name: str
    psk: Optional[str] = None  # Base64 encoded PSK
    channel_number: int = 0
    uplink_enabled: bool = True
    downlink_enabled: bool = True
    
    def __post_init__(self):
        """Validate channel configuration after initialization."""
        if not self.name or not self.name.strip():
            raise ValueError("Channel name cannot be empty")
        
        if self.channel_number < 0 or self.channel_number > 7:
            raise ValueError(f"Channel number must be between 0-7, got {self.channel_number}")
        
        if self.psk is not None:
            self._validate_psk()
    
    def _validate_psk(self) -> None:
        """Validate PSK format and length."""
        if not isinstance(self.psk, str):
            raise ValueError("PSK must be a string")
        
        try:
            decoded = base64.b64decode(self.psk)
            if len(decoded) not in [16, 32]:  # AES-128 or AES-256
                raise ValueError(f"PSK must be 16 or 32 bytes when decoded, got {len(decoded)} bytes")
        except Exception as e:
            raise ValueError(f"Invalid Base64 PSK format: {e}")
    
    def is_encrypted(self) -> bool:
        """Check if channel uses encryption."""
        return self.psk is not None
    
    def get_psk_bytes(self) -> Optional[bytes]:
        """Get PSK as bytes, or None if not encrypted."""
        if self.psk is None:
            return None
        return base64.b64decode(self.psk)


@dataclass
class MQTTConfig:
    """MQTT broker configuration with validation."""
    broker_url: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    use_tls: bool = False
    client_id: Optional[str] = None
    topic_prefix: str = "msh/US"
    qos: int = 0
    keepalive: int = 60
    
    def __post_init__(self):
        """Validate MQTT configuration after initialization."""
        if not self.broker_url or not self.broker_url.strip():
            raise ValueError("MQTT broker URL cannot be empty")
        
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Invalid MQTT port: {self.port}")
        
        if self.qos not in [0, 1, 2]:
            raise ValueError(f"Invalid MQTT QoS level: {self.qos}")
        
        if self.keepalive <= 0:
            raise ValueError("MQTT keepalive must be positive")
        
        if self.client_id is not None and not self.client_id.strip():
            raise ValueError("MQTT client ID cannot be empty string")
    
    def get_connection_url(self) -> str:
        """Get full MQTT connection URL."""
        protocol = "mqtts" if self.use_tls else "mqtt"
        return f"{protocol}://{self.broker_url}:{self.port}"
    
    def has_authentication(self) -> bool:
        """Check if MQTT uses authentication."""
        return self.username is not None and self.password is not None


@dataclass
class MeshtasticConfig:
    """Enhanced Meshtastic configuration with comprehensive validation."""
    # Legacy compatibility
    meshtastic_port: str = "/dev/ttyUSB0"
    meshtastic_baud: int = 115200
    
    # Enhanced channel configuration
    channels: List[ChannelConfig] = field(default_factory=list)
    default_channel: str = "LongFast"
    
    # MQTT configuration
    mqtt: Optional[MQTTConfig] = None
    
    # Connection settings
    connection_mode: str = "serial"  # "serial", "mqtt", "dual"
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
        """Validate configuration after initialization."""
        self._validate_basic_settings()
        self._validate_channels()
        self._validate_connection_mode()
    
    def _validate_basic_settings(self) -> None:
        """Validate basic configuration settings."""
        if self.connection_timeout <= 0:
            raise ValueError("Connection timeout must be positive")
        
        if self.retry_interval <= 0:
            raise ValueError("Retry interval must be positive")
        
        if self.message_format not in ['standard', 'compact', 'json']:
            raise ValueError(f"Invalid message format: {self.message_format}")
        
        if self.max_message_length <= 0:
            raise ValueError("Maximum message length must be positive")
        
        if self.health_check_interval <= 0:
            raise ValueError("Health check interval must be positive")
        
        if self.meshtastic_baud <= 0:
            raise ValueError("Meshtastic baud rate must be positive")
    
    def _validate_channels(self) -> None:
        """Validate channel configuration."""
        if not self.channels:
            raise ValueError("At least one Meshtastic channel must be configured")
        
        channel_names = set()
        channel_numbers = set()
        
        for channel in self.channels:
            # Check for duplicate names
            if channel.name in channel_names:
                raise ValueError(f"Duplicate channel name: {channel.name}")
            channel_names.add(channel.name)
            
            # Check for duplicate channel numbers
            if channel.channel_number in channel_numbers:
                raise ValueError(f"Duplicate channel number {channel.channel_number}")
            channel_numbers.add(channel.channel_number)
        
        # Validate default channel exists
        if self.default_channel not in channel_names:
            raise ValueError(f"Default channel '{self.default_channel}' not found in configured channels")
    
    def _validate_connection_mode(self) -> None:
        """Validate connection mode and related settings."""
        if self.connection_mode not in ['serial', 'mqtt', 'dual']:
            raise ValueError(f"Invalid connection mode: {self.connection_mode}")
        
        # Validate MQTT configuration if needed
        if self.connection_mode in ['mqtt', 'dual']:
            if self.mqtt is None:
                raise ValueError(f"MQTT configuration required for connection mode '{self.connection_mode}'")
    
    def get_channel_by_name(self, name: str) -> Optional[ChannelConfig]:
        """Get channel configuration by name."""
        for channel in self.channels:
            if channel.name == name:
                return channel
        return None
    
    def get_default_channel_config(self) -> ChannelConfig:
        """Get the default channel configuration."""
        channel = self.get_channel_by_name(self.default_channel)
        if channel is None:
            raise ValueError(f"Default channel '{self.default_channel}' not found")
        return channel
    
    def get_encrypted_channels(self) -> List[ChannelConfig]:
        """Get list of encrypted channels."""
        return [channel for channel in self.channels if channel.is_encrypted()]
    
    def has_serial_connection(self) -> bool:
        """Check if serial connection is enabled."""
        return self.connection_mode in ['serial', 'dual']
    
    def has_mqtt_connection(self) -> bool:
        """Check if MQTT connection is enabled."""
        return self.connection_mode in ['mqtt', 'dual']
    
    def is_dual_mode(self) -> bool:
        """Check if dual mode (serial + MQTT) is enabled."""
        return self.connection_mode == 'dual'


class MeshtasticConfigValidator:
    """Comprehensive validator for Meshtastic configuration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def validate_config(self, config: MeshtasticConfig) -> Tuple[bool, List[str]]:
        """
        Validate Meshtastic configuration.
        
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        try:
            # Basic validation is done in __post_init__
            # Additional validation can be added here
            
            # Validate serial port if using serial connection
            if config.has_serial_connection():
                port_errors = self._validate_serial_port(config.meshtastic_port)
                errors.extend(port_errors)
            
            # Validate MQTT configuration if present
            if config.mqtt is not None:
                mqtt_errors = self._validate_mqtt_config(config.mqtt)
                errors.extend(mqtt_errors)
            
            # Validate channel security settings
            security_errors = self._validate_security_settings(config)
            errors.extend(security_errors)
            
            # Validate message settings
            message_errors = self._validate_message_settings(config)
            errors.extend(message_errors)
            
        except Exception as e:
            errors.append(f"Configuration validation error: {e}")
        
        return len(errors) == 0, errors
    
    def _validate_serial_port(self, port: str) -> List[str]:
        """Validate serial port configuration."""
        errors = []
        
        if not port or not port.strip():
            errors.append("Serial port cannot be empty")
            return errors
        
        # Check if port path looks valid
        if not (port.startswith('/dev/') or port.startswith('COM') or port.startswith('/dev/cu.')):
            errors.append(f"Serial port path looks invalid: {port}")
        
        # Check if port exists (warning, not error)
        port_path = Path(port)
        if not port_path.exists():
            self.logger.warning(f"Serial port does not exist: {port}")
        
        return errors
    
    def _validate_mqtt_config(self, mqtt: MQTTConfig) -> List[str]:
        """Validate MQTT configuration."""
        errors = []
        
        # URL validation
        if not self._is_valid_hostname(mqtt.broker_url):
            errors.append(f"Invalid MQTT broker hostname: {mqtt.broker_url}")
        
        # Topic prefix validation
        if mqtt.topic_prefix and not self._is_valid_mqtt_topic(mqtt.topic_prefix):
            errors.append(f"Invalid MQTT topic prefix: {mqtt.topic_prefix}")
        
        # Authentication validation
        if (mqtt.username is None) != (mqtt.password is None):
            errors.append("MQTT username and password must both be provided or both be None")
        
        return errors
    
    def _validate_security_settings(self, config: MeshtasticConfig) -> List[str]:
        """Validate security-related settings."""
        errors = []
        
        # Only warn about encryption settings, don't make it an error
        # This allows for gradual adoption of encryption
        unencrypted_channels = [ch.name for ch in config.channels if not ch.is_encrypted()]
        if config.enable_encryption and unencrypted_channels:
            self.logger.warning(f"Unencrypted channels found: {', '.join(unencrypted_channels)}")
        
        return errors
    
    def _validate_message_settings(self, config: MeshtasticConfig) -> List[str]:
        """Validate message-related settings."""
        errors = []
        
        # Check message length limits
        if config.max_message_length > 237:  # Meshtastic limit
            errors.append(f"Maximum message length exceeds Meshtastic limit (237): {config.max_message_length}")
        
        if config.max_message_length < 50:
            errors.append(f"Maximum message length too small for useful alerts: {config.max_message_length}")
        
        return errors
    
    def _is_valid_hostname(self, hostname: str) -> bool:
        """Check if hostname is valid."""
        if not hostname:
            return False
        
        # Simple hostname validation
        hostname_pattern = re.compile(
            r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$'
        )
        return bool(hostname_pattern.match(hostname))
    
    def _is_valid_mqtt_topic(self, topic: str) -> bool:
        """Check if MQTT topic is valid."""
        if not topic:
            return False
        
        # MQTT topic validation (simplified)
        invalid_chars = ['+', '#', '\0']
        return not any(char in topic for char in invalid_chars)
    
    def suggest_fixes(self, config: MeshtasticConfig, errors: List[str]) -> List[str]:
        """Suggest fixes for configuration errors."""
        suggestions = []
        
        for error in errors:
            if "channel name" in error.lower() and "empty" in error.lower():
                suggestions.append("Ensure all channels have non-empty names")
            
            elif "duplicate channel" in error.lower():
                suggestions.append("Use unique names and numbers for all channels")
            
            elif "mqtt configuration required" in error.lower():
                suggestions.append("Add MQTT configuration or change connection_mode to 'serial'")
            
            elif "psk" in error.lower():
                suggestions.append("Ensure PSKs are valid Base64 encoded 16 or 32 byte keys")
            
            elif "serial port" in error.lower():
                suggestions.append("Check serial port path and ensure device is connected")
            
            elif "message length" in error.lower():
                suggestions.append("Adjust max_message_length to be between 50-237 characters")
        
        return suggestions


class MeshtasticConfigMigrator:
    """Handles migration of legacy Meshtastic configuration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def migrate_legacy_config(self, legacy_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate legacy Meshtastic configuration to enhanced format.
        
        Args:
            legacy_config: Dictionary containing legacy configuration
            
        Returns:
            Dictionary with enhanced Meshtastic configuration
        """
        enhanced_config = {
            # Preserve legacy settings
            "meshtastic_port": legacy_config.get("meshtastic_port", "/dev/ttyUSB0"),
            "meshtastic_baud": legacy_config.get("meshtastic_baud", 115200),
            
            # Default enhanced settings
            "channels": [
                {
                    "name": "LongFast",
                    "psk": None,
                    "channel_number": 0,
                    "uplink_enabled": True,
                    "downlink_enabled": True
                }
            ],
            "default_channel": "LongFast",
            "mqtt": None,
            "connection_mode": "serial",  # Start with serial only for safety
            "failover_enabled": True,
            "connection_timeout": 10,
            "retry_interval": 30,
            "message_format": "standard",
            "include_position": True,
            "include_timestamp": True,
            "max_message_length": 200,
            "auto_detect_device": True,
            "enable_encryption": True,
            "log_all_messages": False,
            "health_check_interval": 60
        }
        
        self.logger.info("Migrated legacy Meshtastic configuration to enhanced format")
        return enhanced_config
    
    def create_example_config(self) -> Dict[str, Any]:
        """Create an example enhanced Meshtastic configuration."""
        return {
            "meshtastic_port": "/dev/ttyUSB0",
            "meshtastic_baud": 115200,
            "channels": [
                {
                    "name": "LongFast",
                    "psk": None,
                    "channel_number": 0,
                    "uplink_enabled": True,
                    "downlink_enabled": True
                },
                {
                    "name": "SecureAlerts",
                    "psk": "AQ==",  # Example Base64 encoded PSK
                    "channel_number": 1,
                    "uplink_enabled": True,
                    "downlink_enabled": True
                }
            ],
            "default_channel": "SecureAlerts",
            "mqtt": {
                "broker_url": "mqtt.meshtastic.org",
                "port": 1883,
                "username": None,
                "password": None,
                "use_tls": False,
                "client_id": "ursine_explorer_adsb",
                "topic_prefix": "msh/US",
                "qos": 0,
                "keepalive": 60
            },
            "connection_mode": "dual",
            "failover_enabled": True,
            "connection_timeout": 10,
            "retry_interval": 30,
            "message_format": "standard",
            "include_position": True,
            "include_timestamp": True,
            "max_message_length": 200,
            "auto_detect_device": True,
            "enable_encryption": True,
            "log_all_messages": False,
            "health_check_interval": 60
        }


def create_meshtastic_config_from_dict(config_dict: Dict[str, Any]) -> MeshtasticConfig:
    """
    Create MeshtasticConfig from dictionary with proper validation.
    
    Args:
        config_dict: Dictionary containing Meshtastic configuration
        
    Returns:
        Validated MeshtasticConfig instance
        
    Raises:
        ValueError: If configuration is invalid
    """
    # Parse channels
    channels = []
    for channel_dict in config_dict.get('channels', []):
        channels.append(ChannelConfig(**channel_dict))
    
    # Parse MQTT config if present
    mqtt_config = None
    if 'mqtt' in config_dict and config_dict['mqtt'] is not None:
        mqtt_config = MQTTConfig(**config_dict['mqtt'])
    
    # Create MeshtasticConfig
    return MeshtasticConfig(
        meshtastic_port=config_dict.get('meshtastic_port', '/dev/ttyUSB0'),
        meshtastic_baud=config_dict.get('meshtastic_baud', 115200),
        channels=channels,
        default_channel=config_dict.get('default_channel', 'LongFast'),
        mqtt=mqtt_config,
        connection_mode=config_dict.get('connection_mode', 'dual'),
        failover_enabled=config_dict.get('failover_enabled', True),
        connection_timeout=config_dict.get('connection_timeout', 10),
        retry_interval=config_dict.get('retry_interval', 30),
        message_format=config_dict.get('message_format', 'standard'),
        include_position=config_dict.get('include_position', True),
        include_timestamp=config_dict.get('include_timestamp', True),
        max_message_length=config_dict.get('max_message_length', 200),
        auto_detect_device=config_dict.get('auto_detect_device', True),
        enable_encryption=config_dict.get('enable_encryption', True),
        log_all_messages=config_dict.get('log_all_messages', False),
        health_check_interval=config_dict.get('health_check_interval', 60)
    )


def validate_meshtastic_config(config: MeshtasticConfig) -> Tuple[bool, List[str], List[str]]:
    """
    Validate Meshtastic configuration and provide suggestions.
    
    Args:
        config: MeshtasticConfig to validate
        
    Returns:
        Tuple of (is_valid, errors, suggestions)
    """
    validator = MeshtasticConfigValidator()
    is_valid, errors = validator.validate_config(config)
    suggestions = validator.suggest_fixes(config, errors) if errors else []
    
    return is_valid, errors, suggestions