"""
Channel management for enhanced Meshtastic integration

This module provides channel configuration management, validation,
and PSK handling utilities for the enhanced Meshtastic system.
"""

import base64
import secrets
import logging
from typing import List, Optional, Tuple, Dict, Any
from .data_classes import ChannelConfig
from .exceptions import MeshtasticConfigError, MeshtasticValidationError


logger = logging.getLogger(__name__)


class ChannelManager:
    """
    Manages Meshtastic channel configuration and selection
    
    This class handles channel configuration, validation, PSK management,
    and provides utilities for channel selection and encryption key handling.
    """
    
    def __init__(self, channels: List[ChannelConfig]):
        """
        Initialize channel manager with channel configurations
        
        Args:
            channels: List of channel configurations
            
        Raises:
            MeshtasticConfigError: If channel configuration is invalid
        """
        self._channels = {}
        self._default_channel = None
        
        # Validate and store channels
        for channel in channels:
            self._validate_channel_config(channel)
            self._channels[channel.name] = channel
        
        logger.info(f"Initialized ChannelManager with {len(self._channels)} channels")
    
    def add_channel(self, channel: ChannelConfig) -> None:
        """
        Add a new channel configuration
        
        Args:
            channel: Channel configuration to add
            
        Raises:
            MeshtasticConfigError: If channel configuration is invalid
            MeshtasticValidationError: If channel name already exists
        """
        self._validate_channel_config(channel)
        
        if channel.name in self._channels:
            raise MeshtasticValidationError(f"Channel '{channel.name}' already exists")
        
        self._channels[channel.name] = channel
        logger.info(f"Added channel '{channel.name}'")
    
    def remove_channel(self, channel_name: str) -> bool:
        """
        Remove a channel configuration
        
        Args:
            channel_name: Name of channel to remove
            
        Returns:
            True if channel was removed, False if not found
        """
        if channel_name in self._channels:
            del self._channels[channel_name]
            logger.info(f"Removed channel '{channel_name}'")
            return True
        return False
    
    def get_channel_by_name(self, name: str) -> Optional[ChannelConfig]:
        """
        Get channel configuration by name
        
        Args:
            name: Channel name to look up
            
        Returns:
            Channel configuration if found, None otherwise
        """
        return self._channels.get(name)
    
    def get_all_channels(self) -> List[ChannelConfig]:
        """
        Get all configured channels
        
        Returns:
            List of all channel configurations
        """
        return list(self._channels.values())
    
    def get_channel_names(self) -> List[str]:
        """
        Get list of all channel names
        
        Returns:
            List of channel names
        """
        return list(self._channels.keys())
    
    def get_default_channel(self) -> ChannelConfig:
        """
        Get the default channel configuration
        
        Returns:
            Default channel configuration
            
        Raises:
            MeshtasticConfigError: If no channels are configured
        """
        if not self._channels:
            raise MeshtasticConfigError("No channels configured")
        
        # Return first channel if no specific default set
        if self._default_channel and self._default_channel in self._channels:
            return self._channels[self._default_channel]
        
        # Return first available channel
        return next(iter(self._channels.values()))
    
    def set_default_channel(self, channel_name: str) -> None:
        """
        Set the default channel
        
        Args:
            channel_name: Name of channel to set as default
            
        Raises:
            MeshtasticValidationError: If channel doesn't exist
        """
        if channel_name not in self._channels:
            raise MeshtasticValidationError(f"Channel '{channel_name}' not found")
        
        self._default_channel = channel_name
        logger.info(f"Set default channel to '{channel_name}'")
    
    def get_encrypted_channels(self) -> List[ChannelConfig]:
        """
        Get all channels that use encryption
        
        Returns:
            List of encrypted channel configurations
        """
        return [ch for ch in self._channels.values() if ch.is_encrypted]
    
    def get_unencrypted_channels(self) -> List[ChannelConfig]:
        """
        Get all channels that don't use encryption
        
        Returns:
            List of unencrypted channel configurations
        """
        return [ch for ch in self._channels.values() if not ch.is_encrypted]
    
    def validate_channel_config(self, config: ChannelConfig) -> Tuple[bool, str]:
        """
        Validate a channel configuration
        
        Args:
            config: Channel configuration to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            self._validate_channel_config(config)
            return True, ""
        except (MeshtasticConfigError, MeshtasticValidationError) as e:
            return False, str(e)
    
    def _validate_channel_config(self, config: ChannelConfig) -> None:
        """
        Internal validation of channel configuration
        
        Args:
            config: Channel configuration to validate
            
        Raises:
            MeshtasticConfigError: If configuration is invalid
            MeshtasticValidationError: If validation fails
        """
        if not isinstance(config, ChannelConfig):
            raise MeshtasticConfigError("Invalid channel configuration type")
        
        # Validate channel name
        if not config.name or not config.name.strip():
            raise MeshtasticValidationError("Channel name cannot be empty")
        
        if len(config.name) > 32:
            raise MeshtasticValidationError("Channel name cannot exceed 32 characters")
        
        # Validate channel number
        if not (0 <= config.channel_number <= 7):
            raise MeshtasticValidationError("Channel number must be between 0 and 7")
        
        # Validate PSK if provided
        if config.psk is not None:
            if not self.validate_psk(config.psk):
                raise MeshtasticValidationError("Invalid PSK format")
        
        # Validate power settings
        if not (0 <= config.tx_power <= 30):
            raise MeshtasticValidationError("TX power must be between 0 and 30")
        
        # Validate hop count
        if not (1 <= config.max_hops <= 7):
            raise MeshtasticValidationError("Max hops must be between 1 and 7")
    
    def apply_channel_settings(self, device_interface) -> bool:
        """
        Apply channel settings to a device interface
        
        Args:
            device_interface: Device interface to configure
            
        Returns:
            True if settings were applied successfully
            
        Note:
            This is a placeholder for actual device configuration.
            Implementation depends on the specific device interface.
        """
        try:
            # This would be implemented based on the actual device interface
            # For now, just log the operation
            logger.info(f"Applying channel settings to device interface")
            
            for channel in self._channels.values():
                logger.debug(f"Would configure channel '{channel.name}' "
                           f"(number: {channel.channel_number}, "
                           f"encrypted: {channel.is_encrypted})")
            
            return True
        except Exception as e:
            logger.error(f"Failed to apply channel settings: {e}")
            return False
    
    @staticmethod
    def validate_psk(psk: str) -> bool:
        """
        Validate a PSK (Pre-Shared Key)
        
        Args:
            psk: Base64 encoded PSK to validate
            
        Returns:
            True if PSK is valid, False otherwise
        """
        if not psk:
            return False
        
        try:
            # Decode base64 to validate format
            decoded = base64.b64decode(psk, validate=True)
            
            # PSK should be between 1 and 32 bytes
            if not (1 <= len(decoded) <= 32):
                return False
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def encode_psk(key_bytes: bytes) -> str:
        """
        Encode raw key bytes to Base64 PSK format
        
        Args:
            key_bytes: Raw key bytes to encode
            
        Returns:
            Base64 encoded PSK string
            
        Raises:
            MeshtasticValidationError: If key bytes are invalid
        """
        if not key_bytes:
            raise MeshtasticValidationError("Key bytes cannot be empty")
        
        if len(key_bytes) > 32:
            raise MeshtasticValidationError("Key cannot exceed 32 bytes")
        
        return base64.b64encode(key_bytes).decode('ascii')
    
    @staticmethod
    def decode_psk(psk: str) -> bytes:
        """
        Decode Base64 PSK to raw key bytes
        
        Args:
            psk: Base64 encoded PSK string
            
        Returns:
            Raw key bytes
            
        Raises:
            MeshtasticValidationError: If PSK is invalid
        """
        if not ChannelManager.validate_psk(psk):
            raise MeshtasticValidationError("Invalid PSK format")
        
        try:
            return base64.b64decode(psk, validate=True)
        except Exception as e:
            raise MeshtasticValidationError(f"Failed to decode PSK: {e}")
    
    @staticmethod
    def generate_psk(length: int = 32) -> str:
        """
        Generate a new random PSK
        
        Args:
            length: Length of key in bytes (1-32)
            
        Returns:
            Base64 encoded PSK string
            
        Raises:
            MeshtasticValidationError: If length is invalid
        """
        if not (1 <= length <= 32):
            raise MeshtasticValidationError("PSK length must be between 1 and 32 bytes")
        
        # Generate random key bytes
        key_bytes = secrets.token_bytes(length)
        
        # Encode to base64
        return ChannelManager.encode_psk(key_bytes)
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get channel manager statistics
        
        Returns:
            Dictionary containing statistics
        """
        encrypted_count = len(self.get_encrypted_channels())
        unencrypted_count = len(self.get_unencrypted_channels())
        
        return {
            'total_channels': len(self._channels),
            'encrypted_channels': encrypted_count,
            'unencrypted_channels': unencrypted_count,
            'default_channel': self._default_channel,
            'channel_names': self.get_channel_names()
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert channel manager to dictionary for serialization
        
        Returns:
            Dictionary representation
        """
        return {
            'channels': [ch.to_dict() for ch in self._channels.values()],
            'default_channel': self._default_channel,
            'statistics': self.get_statistics()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChannelManager':
        """
        Create channel manager from dictionary
        
        Args:
            data: Dictionary containing channel manager data
            
        Returns:
            New ChannelManager instance
        """
        channels = [ChannelConfig.from_dict(ch) for ch in data.get('channels', [])]
        manager = cls(channels)
        
        if data.get('default_channel'):
            try:
                manager.set_default_channel(data['default_channel'])
            except MeshtasticValidationError:
                # Ignore if default channel doesn't exist
                pass
        
        return manager