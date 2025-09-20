"""
Exception classes for enhanced Meshtastic integration

This module defines custom exceptions used throughout the
enhanced Meshtastic system for better error handling and debugging.
"""


class MeshtasticError(Exception):
    """Base exception for all Meshtastic-related errors"""
    pass


class ConnectionError(MeshtasticError):
    """Raised when connection to Meshtastic device/network fails"""
    pass


class ConfigurationError(MeshtasticError):
    """Raised when there are configuration validation errors"""
    pass


class ChannelError(MeshtasticError):
    """Raised when there are channel-related errors"""
    pass


class EncryptionError(MeshtasticError):
    """Raised when encryption/decryption operations fail"""
    pass


class MessageError(MeshtasticError):
    """Raised when message processing fails"""
    pass


class DeviceError(MeshtasticError):
    """Raised when device detection or communication fails"""
    pass


class MQTTError(MeshtasticError):
    """Raised when MQTT operations fail"""
    pass


class RoutingError(MeshtasticError):
    """Raised when message routing fails"""
    pass


class ValidationError(MeshtasticError):
    """Raised when data validation fails"""
    pass


class MeshtasticConfigError(ConfigurationError):
    """Raised when there are Meshtastic configuration errors"""
    pass


class MeshtasticValidationError(ValidationError):
    """Raised when Meshtastic data validation fails"""
    pass


class MeshtasticConnectionError(ConnectionError):
    """Raised when Meshtastic device connection fails"""
    pass


class MeshtasticDetectionError(DeviceError):
    """Raised when device detection fails"""
    pass