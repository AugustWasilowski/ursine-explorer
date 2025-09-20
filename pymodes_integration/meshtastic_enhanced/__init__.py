"""
Enhanced Meshtastic Integration Module

This module provides enhanced Meshtastic functionality including:
- Encrypted channel communication
- MQTT integration
- Multi-interface support
- Advanced message routing
- Comprehensive monitoring and diagnostics

Main Components:
- MeshtasticManager: Central coordinator for all Meshtastic operations
- ChannelManager: Handles channel configuration and encryption
- EnhancedSerialInterface: Improved USB serial communication
- MQTTInterface: Network-based MQTT communication
- MessageRouter: Routes messages between interfaces
"""

from .interfaces import (
    MeshtasticInterface,
    ChannelManagerInterface,
    EncryptionHandlerInterface,
    MessageRouterInterface,
    DiagnosticsInterface
)
from .data_classes import (
    ChannelConfig,
    MQTTConfig,
    MeshtasticConfig,
    AlertMessage,
    ConnectionStatus,
    ConnectionState,
    MessagePriority,
    RoutingPolicy
)
from .exceptions import (
    MeshtasticError,
    ConnectionError,
    ConfigurationError,
    ChannelError,
    EncryptionError,
    MessageError,
    DeviceError,
    MQTTError,
    RoutingError,
    ValidationError,
    MeshtasticConfigError,
    MeshtasticValidationError
)
from .channel_manager import ChannelManager
from .encryption_handler import EncryptionHandler
from .mqtt_interface import MeshtasticMQTTInterface, MQTTMessageHandler
from .meshtastic_manager import MeshtasticManager
from .connection_manager import ConnectionManager, InterfacePriority
from . import utils

__version__ = "1.0.0"
__all__ = [
    # Interfaces
    "MeshtasticInterface",
    "ChannelManagerInterface",
    "EncryptionHandlerInterface", 
    "MessageRouterInterface",
    "DiagnosticsInterface",
    
    # Managers
    "ChannelManager",
    "EncryptionHandler",
    "MeshtasticMQTTInterface",
    "MQTTMessageHandler",
    "MeshtasticManager",
    "ConnectionManager",
    "InterfacePriority",
    
    # Data Classes
    "ChannelConfig", 
    "MQTTConfig",
    "MeshtasticConfig",
    "AlertMessage",
    "ConnectionStatus",
    "ConnectionState",
    "MessagePriority",
    "RoutingPolicy",
    
    # Exceptions
    "MeshtasticError",
    "ConnectionError",
    "ConfigurationError",
    "ChannelError",
    "EncryptionError",
    "MessageError",
    "DeviceError",
    "MQTTError",
    "RoutingError",
    "ValidationError",
    "MeshtasticConfigError",
    "MeshtasticValidationError",
    
    # Utils module
    "utils"
]