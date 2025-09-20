"""
Base interfaces for enhanced Meshtastic integration

This module defines the core interfaces and abstract base classes
that all Meshtastic components must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime

from .data_classes import AlertMessage, ConnectionStatus


class MeshtasticInterface(ABC):
    """
    Abstract base class for all Meshtastic communication interfaces
    
    This interface defines the contract that all Meshtastic communication
    methods (serial, MQTT, etc.) must implement.
    """
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to the Meshtastic network
        
        Returns:
            True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """
        Disconnect from the Meshtastic network
        """
        pass
    
    @abstractmethod
    def send_message(self, message: str, channel: Optional[str] = None) -> bool:
        """
        Send a message through this interface
        
        Args:
            message: The message content to send
            channel: Optional channel name to send on
            
        Returns:
            True if message sent successfully, False otherwise
        """
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """
        Check if the interface is currently connected
        
        Returns:
            True if connected, False otherwise
        """
        pass
    
    @abstractmethod
    def get_connection_status(self) -> ConnectionStatus:
        """
        Get detailed connection status information
        
        Returns:
            ConnectionStatus object with current status details
        """
        pass
    
    @abstractmethod
    def get_interface_type(self) -> str:
        """
        Get the type identifier for this interface
        
        Returns:
            String identifier (e.g., "serial", "mqtt")
        """
        pass


class ChannelManagerInterface(ABC):
    """
    Abstract interface for channel management functionality
    """
    
    @abstractmethod
    def get_channel_by_name(self, name: str) -> Optional['ChannelConfig']:
        """
        Get channel configuration by name
        
        Args:
            name: Channel name to look up
            
        Returns:
            ChannelConfig if found, None otherwise
        """
        pass
    
    @abstractmethod
    def get_default_channel(self) -> 'ChannelConfig':
        """
        Get the default channel configuration
        
        Returns:
            Default ChannelConfig
        """
        pass
    
    @abstractmethod
    def validate_channel_config(self, config: 'ChannelConfig') -> tuple[bool, str]:
        """
        Validate a channel configuration
        
        Args:
            config: ChannelConfig to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        pass


class EncryptionHandlerInterface(ABC):
    """
    Abstract interface for message encryption functionality
    """
    
    @abstractmethod
    def encrypt_message(self, message: str, psk: str) -> bytes:
        """
        Encrypt a message using the provided PSK
        
        Args:
            message: Plain text message to encrypt
            psk: Pre-shared key for encryption
            
        Returns:
            Encrypted message as bytes
        """
        pass
    
    @abstractmethod
    def decrypt_message(self, encrypted_data: bytes, psk: str) -> str:
        """
        Decrypt a message using the provided PSK
        
        Args:
            encrypted_data: Encrypted message bytes
            psk: Pre-shared key for decryption
            
        Returns:
            Decrypted plain text message
        """
        pass
    
    @abstractmethod
    def validate_psk(self, psk: str) -> bool:
        """
        Validate a pre-shared key format
        
        Args:
            psk: PSK to validate
            
        Returns:
            True if valid, False otherwise
        """
        pass


class MessageRouterInterface(ABC):
    """
    Abstract interface for message routing functionality
    """
    
    @abstractmethod
    def route_message(self, message: AlertMessage, routing_policy: str = "all") -> List[bool]:
        """
        Route a message through available interfaces
        
        Args:
            message: AlertMessage to route
            routing_policy: Routing policy ("all", "primary", "fallback")
            
        Returns:
            List of success status for each interface
        """
        pass
    
    @abstractmethod
    def add_interface(self, interface: MeshtasticInterface) -> None:
        """
        Add an interface to the router
        
        Args:
            interface: MeshtasticInterface to add
        """
        pass
    
    @abstractmethod
    def remove_interface(self, interface: MeshtasticInterface) -> None:
        """
        Remove an interface from the router
        
        Args:
            interface: MeshtasticInterface to remove
        """
        pass
    
    @abstractmethod
    def get_delivery_stats(self) -> Dict[str, Any]:
        """
        Get message delivery statistics
        
        Returns:
            Dictionary with delivery statistics
        """
        pass


class DiagnosticsInterface(ABC):
    """
    Abstract interface for diagnostics and monitoring functionality
    """
    
    @abstractmethod
    def get_connection_health(self) -> Dict[str, Any]:
        """
        Get comprehensive connection health information
        
        Returns:
            Dictionary with health status for all components
        """
        pass
    
    @abstractmethod
    def get_message_statistics(self) -> Dict[str, Any]:
        """
        Get message delivery and processing statistics
        
        Returns:
            Dictionary with message statistics
        """
        pass
    
    @abstractmethod
    def test_all_interfaces(self) -> Dict[str, bool]:
        """
        Test connectivity of all configured interfaces
        
        Returns:
            Dictionary mapping interface names to test results
        """
        pass
    
    @abstractmethod
    def validate_configuration(self) -> List[str]:
        """
        Validate current configuration and return any issues
        
        Returns:
            List of configuration issues (empty if valid)
        """
        pass