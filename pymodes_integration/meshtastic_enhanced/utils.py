"""
Utility functions for enhanced Meshtastic integration

This module contains common utility functions used throughout
the enhanced Meshtastic system.
"""

import base64
import hashlib
import logging
import re
import secrets
from typing import Optional, Dict, Any, List
from datetime import datetime

from .exceptions import ValidationError, EncryptionError

logger = logging.getLogger(__name__)


def validate_psk(psk: str) -> bool:
    """
    Validate a Pre-Shared Key format
    
    Args:
        psk: Base64 encoded PSK string
        
    Returns:
        True if valid, False otherwise
    """
    if not psk:
        return False
    
    try:
        # Must be valid base64
        decoded = base64.b64decode(psk)
        
        # Must be 16 or 32 bytes (128 or 256 bit)
        if len(decoded) not in [16, 32]:
            return False
        
        # Re-encode and compare to ensure it's properly formatted
        reencoded = base64.b64encode(decoded).decode('ascii')
        return reencoded == psk
        
    except Exception:
        return False


def generate_psk(key_size: int = 32) -> str:
    """
    Generate a new Pre-Shared Key
    
    Args:
        key_size: Size of key in bytes (16 or 32)
        
    Returns:
        Base64 encoded PSK string
        
    Raises:
        ValidationError: If key_size is invalid
    """
    if key_size not in [16, 32]:
        raise ValidationError("Key size must be 16 or 32 bytes")
    
    # Generate random bytes
    key_bytes = secrets.token_bytes(key_size)
    
    # Encode as base64
    psk = base64.b64encode(key_bytes).decode('ascii')
    
    logger.debug(f"Generated {key_size * 8}-bit PSK")
    return psk


def encode_psk(key_bytes: bytes) -> str:
    """
    Encode raw key bytes as base64 PSK
    
    Args:
        key_bytes: Raw key bytes
        
    Returns:
        Base64 encoded PSK string
        
    Raises:
        ValidationError: If key bytes are invalid length
    """
    if len(key_bytes) not in [16, 32]:
        raise ValidationError("Key must be 16 or 32 bytes")
    
    return base64.b64encode(key_bytes).decode('ascii')


def decode_psk(psk: str) -> bytes:
    """
    Decode base64 PSK to raw bytes
    
    Args:
        psk: Base64 encoded PSK string
        
    Returns:
        Raw key bytes
        
    Raises:
        EncryptionError: If PSK is invalid
    """
    if not validate_psk(psk):
        raise EncryptionError("Invalid PSK format")
    
    try:
        return base64.b64decode(psk)
    except Exception as e:
        raise EncryptionError(f"Failed to decode PSK: {e}")


def validate_channel_name(name: str) -> bool:
    """
    Validate a channel name format
    
    Args:
        name: Channel name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not name:
        return False
    
    # Must be 1-20 characters, alphanumeric plus underscore/dash
    if not re.match(r'^[a-zA-Z0-9_-]{1,20}$', name):
        return False
    
    return True


def validate_mqtt_topic(topic: str) -> bool:
    """
    Validate an MQTT topic format
    
    Args:
        topic: MQTT topic to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not topic:
        return False
    
    # Basic MQTT topic validation
    # No wildcards in publish topics, reasonable length
    if len(topic) > 256:
        return False
    
    # No null bytes or control characters
    if any(ord(c) < 32 for c in topic):
        return False
    
    # No wildcards in publish topics
    if '+' in topic or '#' in topic:
        return False
    
    return True


def format_message_timestamp(dt: Optional[datetime] = None) -> str:
    """
    Format a timestamp for message inclusion
    
    Args:
        dt: Datetime to format (uses current time if None)
        
    Returns:
        Formatted timestamp string
    """
    if dt is None:
        dt = datetime.now()
    
    return dt.strftime("%H:%M:%S")


def format_message_content(
    content: str,
    max_length: int = 200,
    include_timestamp: bool = True,
    prefix: Optional[str] = None
) -> str:
    """
    Format message content for Meshtastic transmission
    
    Args:
        content: Raw message content
        max_length: Maximum message length
        include_timestamp: Whether to include timestamp
        prefix: Optional message prefix
        
    Returns:
        Formatted message string
    """
    formatted = content
    
    # Add prefix if provided
    if prefix:
        formatted = f"{prefix}: {formatted}"
    
    # Add timestamp if requested
    if include_timestamp:
        timestamp = format_message_timestamp()
        formatted = f"[{timestamp}] {formatted}"
    
    # Truncate if too long
    if len(formatted) > max_length:
        # Leave room for ellipsis
        truncate_length = max_length - 3
        formatted = formatted[:truncate_length] + "..."
    
    return formatted


def sanitize_device_info(device_info: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize device information for safe logging/display
    
    Args:
        device_info: Raw device information dictionary
        
    Returns:
        Sanitized device information
    """
    sanitized = {}
    
    # Safe fields to include
    safe_fields = [
        'node_id', 'hardware_model', 'firmware_version',
        'region', 'modem_preset', 'has_bluetooth', 'has_wifi',
        'battery_level', 'voltage', 'channel_utilization',
        'air_util_tx', 'num_online_nodes', 'num_total_nodes'
    ]
    
    for field in safe_fields:
        if field in device_info:
            sanitized[field] = device_info[field]
    
    return sanitized


def calculate_message_hash(content: str) -> str:
    """
    Calculate a hash of message content for deduplication
    
    Args:
        content: Message content
        
    Returns:
        SHA256 hash of content (first 8 characters)
    """
    hash_obj = hashlib.sha256(content.encode('utf-8'))
    return hash_obj.hexdigest()[:8]


def parse_node_id(node_id_str: str) -> Optional[int]:
    """
    Parse a Meshtastic node ID from string format
    
    Args:
        node_id_str: Node ID as string (hex or decimal)
        
    Returns:
        Node ID as integer, or None if invalid
    """
    if not node_id_str:
        return None
    
    try:
        # Try hex format first (with or without 0x prefix)
        if node_id_str.startswith('0x'):
            return int(node_id_str, 16)
        elif node_id_str.startswith('!'):
            # Meshtastic format with ! prefix
            return int(node_id_str[1:], 16)
        else:
            # Try as decimal, then hex
            try:
                return int(node_id_str, 10)
            except ValueError:
                return int(node_id_str, 16)
    except ValueError:
        return None


def format_node_id(node_id: int) -> str:
    """
    Format a node ID for display
    
    Args:
        node_id: Node ID as integer
        
    Returns:
        Formatted node ID string
    """
    return f"!{node_id:08x}"


def validate_coordinates(lat: float, lon: float) -> bool:
    """
    Validate latitude/longitude coordinates
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        
    Returns:
        True if valid, False otherwise
    """
    return (-90 <= lat <= 90) and (-180 <= lon <= 180)


def format_coordinates(lat: float, lon: float, precision: int = 6) -> str:
    """
    Format coordinates for display
    
    Args:
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        precision: Number of decimal places
        
    Returns:
        Formatted coordinate string
    """
    if not validate_coordinates(lat, lon):
        return "Invalid coordinates"
    
    lat_str = f"{lat:.{precision}f}"
    lon_str = f"{lon:.{precision}f}"
    
    return f"{lat_str}, {lon_str}"


def get_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two coordinates using Haversine formula
    
    Args:
        lat1, lon1: First coordinate pair
        lat2, lon2: Second coordinate pair
        
    Returns:
        Distance in kilometers
    """
    import math
    
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = (math.sin(dlat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2)
    
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth radius in kilometers
    earth_radius_km = 6371.0
    
    return earth_radius_km * c


def create_client_id(prefix: str = "ursine_adsb") -> str:
    """
    Create a unique client ID for MQTT connections
    
    Args:
        prefix: Prefix for the client ID
        
    Returns:
        Unique client ID string
    """
    import uuid
    
    # Use first 8 characters of UUID for uniqueness
    unique_suffix = str(uuid.uuid4())[:8]
    
    return f"{prefix}_{unique_suffix}"


def retry_with_backoff(
    func,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_multiplier: float = 2.0,
    max_delay: float = 60.0
):
    """
    Decorator for retrying functions with exponential backoff
    
    Args:
        func: Function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay between retries
        backoff_multiplier: Multiplier for delay on each retry
        max_delay: Maximum delay between retries
        
    Returns:
        Decorated function
    """
    import time
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        delay = initial_delay
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if attempt < max_retries:
                    logger.debug(f"Attempt {attempt + 1} failed, retrying in {delay}s: {e}")
                    time.sleep(delay)
                    delay = min(delay * backoff_multiplier, max_delay)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed")
        
        # Re-raise the last exception
        raise last_exception
    
    return wrapper