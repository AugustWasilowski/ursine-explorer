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
# Optional MQTT interface (requires paho-mqtt)
try:
    from .mqtt_interface import MeshtasticMQTTInterface, MQTTMessageHandler
    _MQTT_AVAILABLE = True
except ImportError:
    _MQTT_AVAILABLE = False
    MeshtasticMQTTInterface = None
    MQTTMessageHandler = None
from .meshtastic_manager import MeshtasticManager
from .connection_manager import ConnectionManager, InterfacePriority
from .diagnostics import MeshtasticDiagnostics, DiagnosticTest, PerformanceMetrics
from . import utils

__version__ = "1.0.0"
# Build __all__ list dynamically based on available imports
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
    "MeshtasticManager",
    "ConnectionManager",
    "InterfacePriority",
    
    # Diagnostics
    "MeshtasticDiagnostics",
    "DiagnosticTest",
    "PerformanceMetrics",
    
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

# Add MQTT components if available
if _MQTT_AVAILABLE:
    __all__.extend(["MeshtasticMQTTInterface", "MQTTMessageHandler"])