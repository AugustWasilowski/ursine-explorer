"""
Message Validation and Filtering Module

This module provides comprehensive validation and filtering capabilities for ADS-B messages
using pyModeS CRC functions and format validation.
"""

import logging
from typing import Optional, Dict, Any, Set
from dataclasses import dataclass
from enum import Enum

try:
    import pyModeS as pms
    PYMODES_AVAILABLE = True
except ImportError:
    PYMODES_AVAILABLE = False
    pms = None

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """ADS-B message types"""
    UNKNOWN = "unknown"
    IDENTIFICATION = "identification"
    SURFACE_POSITION = "surface_position"
    AIRBORNE_POSITION = "airborne_position"
    VELOCITY = "velocity"
    SURVEILLANCE = "surveillance"


@dataclass
class ValidationConfig:
    """Configuration for message validation"""
    # CRC validation
    enable_crc_validation: bool = True
    
    # Message format validation
    validate_message_length: bool = True
    validate_hex_format: bool = True
    
    # DF type filtering
    allowed_df_types: Set[int] = None
    
    # Data range validation
    validate_altitude_range: bool = True
    min_altitude: int = -2000  # feet
    max_altitude: int = 60000  # feet
    
    validate_speed_range: bool = True
    max_ground_speed: float = 1000.0  # knots
    
    validate_position_range: bool = True
    min_latitude: float = -90.0
    max_latitude: float = 90.0
    min_longitude: float = -180.0
    max_longitude: float = 180.0
    
    # Logging
    log_validation_errors: bool = False
    log_validation_stats: bool = True
    
    def __post_init__(self):
        if self.allowed_df_types is None:
            # Default allowed DF types: 4, 5, 17, 18, 20, 21
            self.allowed_df_types = {4, 5, 17, 18, 20, 21}


class MessageValidator:
    """
    Comprehensive message validation and filtering using pyModeS functions
    
    This class provides multiple layers of validation:
    1. Format validation (length, hex format)
    2. CRC validation using pyModeS
    3. DF type filtering
    4. Data range validation for decoded values
    """
    
    def __init__(self, config: Optional[ValidationConfig] = None):
        """Initialize message validator"""
        if not PYMODES_AVAILABLE:
            raise ImportError("pyModeS library is not available. Install with: pip install pyModeS")
        
        self.config = config or ValidationConfig()
        
        # Statistics tracking
        self.stats = {
            'total_messages': 0,
            'valid_messages': 0,
            'invalid_format': 0,
            'invalid_crc': 0,
            'invalid_df_type': 0,
            'invalid_data_range': 0,
            'validation_errors': 0
        }
        
        logger.info("MessageValidator initialized")
        logger.info(f"CRC validation: {self.config.enable_crc_validation}")
        logger.info(f"Allowed DF types: {sorted(self.config.allowed_df_types)}")
    
    def validate_message_format(self, message: str) -> bool:
        """
        Validate basic message format
        
        Args:
            message: Raw ADS-B message in hex format
            
        Returns:
            True if format is valid, False otherwise
        """
        try:
            if not message:
                return False
            
            # Check message length (7 or 14 bytes = 14 or 28 hex characters)
            if self.config.validate_message_length:
                if len(message) not in [14, 28]:
                    if self.config.log_validation_errors:
                        logger.debug(f"Invalid message length: {len(message)} (expected 14 or 28)")
                    return False
            
            # Check if it's valid hexadecimal
            if self.config.validate_hex_format:
                try:
                    int(message, 16)
                except ValueError:
                    if self.config.log_validation_errors:
                        logger.debug(f"Invalid hex format: {message}")
                    return False
            
            return True
            
        except Exception as e:
            if self.config.log_validation_errors:
                logger.debug(f"Format validation error: {e}")
            return False
    
    def validate_crc(self, message: str) -> bool:
        """
        Validate message CRC using pyModeS
        
        Args:
            message: Raw ADS-B message in hex format
            
        Returns:
            True if CRC is valid, False otherwise
        """
        try:
            if not self.config.enable_crc_validation:
                return True
            
            # Use pyModeS CRC validation
            return pms.crc(message) == 0
            
        except Exception as e:
            if self.config.log_validation_errors:
                logger.debug(f"CRC validation error for {message}: {e}")
            return False
    
    def validate_df_type(self, message: str) -> bool:
        """
        Validate DF (Downlink Format) type
        
        Args:
            message: Raw ADS-B message in hex format
            
        Returns:
            True if DF type is allowed, False otherwise
        """
        try:
            df = pms.df(message)
            if df not in self.config.allowed_df_types:
                if self.config.log_validation_errors:
                    logger.debug(f"Disallowed DF type: {df}")
                return False
            
            return True
            
        except Exception as e:
            if self.config.log_validation_errors:
                logger.debug(f"DF type validation error: {e}")
            return False
    
    def validate_decoded_data(self, decoded_data: Dict[str, Any]) -> bool:
        """
        Validate ranges of decoded data values
        
        Args:
            decoded_data: Dictionary containing decoded message data
            
        Returns:
            True if all data is within valid ranges, False otherwise
        """
        try:
            # Validate altitude
            if self.config.validate_altitude_range and 'altitude' in decoded_data:
                altitude = decoded_data['altitude']
                if altitude is not None:
                    if not (self.config.min_altitude <= altitude <= self.config.max_altitude):
                        if self.config.log_validation_errors:
                            logger.debug(f"Altitude out of range: {altitude}")
                        return False
            
            # Validate ground speed
            if self.config.validate_speed_range and 'ground_speed' in decoded_data:
                speed = decoded_data['ground_speed']
                if speed is not None:
                    if speed < 0 or speed > self.config.max_ground_speed:
                        if self.config.log_validation_errors:
                            logger.debug(f"Ground speed out of range: {speed}")
                        return False
            
            # Validate position
            if self.config.validate_position_range:
                lat = decoded_data.get('latitude')
                lon = decoded_data.get('longitude')
                
                if lat is not None:
                    if not (self.config.min_latitude <= lat <= self.config.max_latitude):
                        if self.config.log_validation_errors:
                            logger.debug(f"Latitude out of range: {lat}")
                        return False
                
                if lon is not None:
                    if not (self.config.min_longitude <= lon <= self.config.max_longitude):
                        if self.config.log_validation_errors:
                            logger.debug(f"Longitude out of range: {lon}")
                        return False
            
            return True
            
        except Exception as e:
            if self.config.log_validation_errors:
                logger.debug(f"Data range validation error: {e}")
            return False
    
    def validate_message(self, message: str, decoded_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Perform complete message validation
        
        Args:
            message: Raw ADS-B message in hex format
            decoded_data: Optional decoded data for range validation
            
        Returns:
            True if message passes all validation checks, False otherwise
        """
        self.stats['total_messages'] += 1
        
        try:
            # Format validation
            if not self.validate_message_format(message):
                self.stats['invalid_format'] += 1
                return False
            
            # CRC validation
            if not self.validate_crc(message):
                self.stats['invalid_crc'] += 1
                return False
            
            # DF type validation
            if not self.validate_df_type(message):
                self.stats['invalid_df_type'] += 1
                return False
            
            # Data range validation (if decoded data provided)
            if decoded_data and not self.validate_decoded_data(decoded_data):
                self.stats['invalid_data_range'] += 1
                return False
            
            self.stats['valid_messages'] += 1
            return True
            
        except Exception as e:
            self.stats['validation_errors'] += 1
            if self.config.log_validation_errors:
                logger.error(f"Validation error for message {message}: {e}")
            return False
    
    def get_message_type(self, message: str) -> MessageType:
        """
        Determine the type of ADS-B message
        
        Args:
            message: Raw ADS-B message in hex format
            
        Returns:
            MessageType enum value
        """
        try:
            df = pms.df(message)
            
            # Handle ADS-B messages (DF17, DF18)
            if df in [17, 18]:
                tc = pms.adsb.typecode(message)
                
                if 1 <= tc <= 4:
                    return MessageType.IDENTIFICATION
                elif 5 <= tc <= 8:
                    return MessageType.SURFACE_POSITION
                elif 9 <= tc <= 18:
                    return MessageType.AIRBORNE_POSITION
                elif tc == 19:
                    return MessageType.VELOCITY
            
            # Handle surveillance messages (DF4, DF5, DF20, DF21)
            elif df in [4, 5, 20, 21]:
                return MessageType.SURVEILLANCE
            
            return MessageType.UNKNOWN
            
        except Exception as e:
            if self.config.log_validation_errors:
                logger.debug(f"Message type detection error: {e}")
            return MessageType.UNKNOWN
    
    def filter_messages(self, messages: list) -> list:
        """
        Filter a list of messages, keeping only valid ones
        
        Args:
            messages: List of (message, timestamp) tuples or message strings
            
        Returns:
            List of valid messages in the same format
        """
        valid_messages = []
        
        for item in messages:
            # Handle both (message, timestamp) tuples and plain message strings
            if isinstance(item, tuple):
                message, timestamp = item
                if self.validate_message(message):
                    valid_messages.append(item)
            else:
                message = item
                if self.validate_message(message):
                    valid_messages.append(item)
        
        return valid_messages
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get validation statistics"""
        total = self.stats['total_messages']
        if total > 0:
            return {
                **self.stats,
                'validation_rate': self.stats['valid_messages'] / total,
                'error_rate': (total - self.stats['valid_messages']) / total
            }
        else:
            return {**self.stats, 'validation_rate': 0.0, 'error_rate': 0.0}
    
    def reset_statistics(self):
        """Reset validation statistics"""
        for key in self.stats:
            self.stats[key] = 0
        
        if self.config.log_validation_stats:
            logger.info("Validation statistics reset")
    
    def log_statistics(self):
        """Log current validation statistics"""
        if not self.config.log_validation_stats:
            return
        
        stats = self.get_statistics()
        logger.info(
            f"Validation Stats: {stats['total_messages']} total, "
            f"{stats['valid_messages']} valid ({stats['validation_rate']:.1%}), "
            f"Errors: format={stats['invalid_format']}, "
            f"crc={stats['invalid_crc']}, "
            f"df_type={stats['invalid_df_type']}, "
            f"data_range={stats['invalid_data_range']}"
        )