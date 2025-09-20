"""
Decoded Message Data Structure

This module provides structured representation of decoded ADS-B data,
mapping pyModeS output to standardized internal format with message
type classification and metadata.
"""

import logging
from typing import Optional, Dict, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """ADS-B message types"""
    UNKNOWN = "unknown"
    IDENTIFICATION = "identification"
    SURFACE_POSITION = "surface_position"
    AIRBORNE_POSITION = "airborne_position"
    VELOCITY = "velocity"
    SURVEILLANCE = "surveillance"


class DataQuality(Enum):
    """Data quality indicators"""
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class PositionData:
    """Position-related data from ADS-B messages"""
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_baro: Optional[int] = None  # Barometric altitude in feet
    altitude_gnss: Optional[int] = None  # GNSS altitude in feet
    
    # CPR decoding metadata
    cpr_format: Optional[str] = None  # "even" or "odd"
    cpr_lat: Optional[int] = None
    cpr_lon: Optional[int] = None
    position_source: Optional[str] = None  # "global_cpr", "local_cpr", "surveillance"
    
    # Quality indicators
    navigation_accuracy: Optional[float] = None
    position_uncertainty: Optional[Dict[str, float]] = None
    
    def is_valid_position(self) -> bool:
        """Check if position data is valid"""
        return (self.latitude is not None and 
                self.longitude is not None and
                -90 <= self.latitude <= 90 and
                -180 <= self.longitude <= 180)


@dataclass
class VelocityData:
    """Velocity-related data from ADS-B messages"""
    ground_speed: Optional[float] = None  # knots
    track_angle: Optional[float] = None   # degrees
    vertical_rate: Optional[float] = None # feet/minute
    
    # Enhanced velocity data
    true_airspeed: Optional[float] = None      # knots
    indicated_airspeed: Optional[float] = None # knots
    mach_number: Optional[float] = None
    magnetic_heading: Optional[float] = None   # degrees
    
    # Quality indicators
    velocity_uncertainty: Optional[Dict[str, float]] = None
    
    def is_valid_velocity(self) -> bool:
        """Check if velocity data is reasonable"""
        if self.ground_speed is not None:
            return 0 <= self.ground_speed <= 1000  # reasonable speed range
        return True


@dataclass
class IdentificationData:
    """Identification-related data from ADS-B messages"""
    callsign: Optional[str] = None
    aircraft_category: Optional[str] = None
    emitter_category: Optional[str] = None
    
    def get_clean_callsign(self) -> Optional[str]:
        """Get cleaned callsign (trimmed and validated)"""
        if self.callsign:
            cleaned = self.callsign.strip()
            return cleaned if cleaned else None
        return None


@dataclass
class MessageMetadata:
    """Metadata about the message and decoding process"""
    timestamp: float
    raw_message: str
    df: int  # Downlink Format
    tc: Optional[int] = None  # Type Code (for ADS-B messages)
    
    # Message source information
    source_id: Optional[str] = None
    source_type: Optional[str] = None  # "dump1090", "network", "rtlsdr"
    
    # Decoding information
    decode_time: Optional[float] = None
    crc_valid: Optional[bool] = None
    decode_errors: Optional[list] = field(default_factory=list)
    
    # Quality assessment
    signal_strength: Optional[float] = None
    data_quality: DataQuality = DataQuality.UNKNOWN


@dataclass
class DecodedMessage:
    """
    Structured representation of decoded ADS-B data
    
    This class provides a standardized format for decoded ADS-B messages,
    mapping pyModeS output to internal format with proper type classification
    and metadata tracking.
    """
    
    # Core identification
    icao: str
    message_type: MessageType
    metadata: MessageMetadata
    
    # Data components (optional based on message type)
    position: Optional[PositionData] = None
    velocity: Optional[VelocityData] = None
    identification: Optional[IdentificationData] = None
    
    # Additional data fields
    surveillance_status: Optional[str] = None
    emergency_status: Optional[str] = None
    
    # Raw pyModeS data for debugging/analysis
    raw_pymodes_data: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_pymodes_data(cls, pymodes_data: Dict[str, Any], 
                         source_info: Optional[Dict[str, Any]] = None) -> 'DecodedMessage':
        """
        Create DecodedMessage from pyModeS decoder output
        
        Args:
            pymodes_data: Dictionary from pyModeS decoder
            source_info: Optional source information
            
        Returns:
            DecodedMessage instance
        """
        # Extract core fields
        icao = pymodes_data.get('icao', '').upper()
        message_type = MessageType(pymodes_data.get('message_type', 'unknown'))
        
        # Create metadata
        metadata = MessageMetadata(
            timestamp=pymodes_data.get('timestamp', 0.0),
            raw_message=pymodes_data.get('raw_message', ''),
            df=pymodes_data.get('df', 0),
            tc=pymodes_data.get('tc'),
            crc_valid=pymodes_data.get('crc_valid'),
            source_id=source_info.get('source_id') if source_info else None,
            source_type=source_info.get('source_type') if source_info else None
        )
        
        # Create message instance
        message = cls(
            icao=icao,
            message_type=message_type,
            metadata=metadata,
            raw_pymodes_data=pymodes_data.copy()
        )
        
        # Populate data based on message type
        message._populate_position_data(pymodes_data)
        message._populate_velocity_data(pymodes_data)
        message._populate_identification_data(pymodes_data)
        message._populate_surveillance_data(pymodes_data)
        
        return message
    
    def _populate_position_data(self, data: Dict[str, Any]):
        """Populate position data from pyModeS output"""
        if any(key in data for key in ['latitude', 'longitude', 'altitude', 'cpr_format']):
            self.position = PositionData(
                latitude=data.get('latitude'),
                longitude=data.get('longitude'),
                altitude_baro=data.get('altitude'),
                altitude_gnss=data.get('altitude_gnss'),
                cpr_format=data.get('cpr_format'),
                cpr_lat=data.get('cpr_lat'),
                cpr_lon=data.get('cpr_lon'),
                position_source=data.get('position_source'),
                navigation_accuracy=data.get('navigation_accuracy')
            )
    
    def _populate_velocity_data(self, data: Dict[str, Any]):
        """Populate velocity data from pyModeS output"""
        if any(key in data for key in ['ground_speed', 'track', 'vertical_rate', 'true_airspeed']):
            self.velocity = VelocityData(
                ground_speed=data.get('ground_speed'),
                track_angle=data.get('track'),
                vertical_rate=data.get('vertical_rate'),
                true_airspeed=data.get('true_airspeed'),
                indicated_airspeed=data.get('indicated_airspeed'),
                mach_number=data.get('mach_number'),
                magnetic_heading=data.get('magnetic_heading')
            )
    
    def _populate_identification_data(self, data: Dict[str, Any]):
        """Populate identification data from pyModeS output"""
        if any(key in data for key in ['callsign', 'aircraft_category']):
            self.identification = IdentificationData(
                callsign=data.get('callsign'),
                aircraft_category=data.get('aircraft_category'),
                emitter_category=data.get('emitter_category')
            )
    
    def _populate_surveillance_data(self, data: Dict[str, Any]):
        """Populate surveillance-specific data from pyModeS output"""
        self.surveillance_status = data.get('surveillance_status')
        self.emergency_status = data.get('emergency_status')
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format for API/JSON serialization
        
        Returns:
            Dictionary representation suitable for JSON serialization
        """
        result = {
            'icao': self.icao,
            'message_type': self.message_type.value,
            'timestamp': self.metadata.timestamp,
            'df': self.metadata.df,
            'tc': self.metadata.tc
        }
        
        # Add position data
        if self.position:
            if self.position.latitude is not None:
                result['latitude'] = self.position.latitude
            if self.position.longitude is not None:
                result['longitude'] = self.position.longitude
            if self.position.altitude_baro is not None:
                result['altitude'] = self.position.altitude_baro
            if self.position.altitude_gnss is not None:
                result['altitude_gnss'] = self.position.altitude_gnss
            if self.position.cpr_format is not None:
                result['cpr_format'] = self.position.cpr_format
            if self.position.position_source is not None:
                result['position_source'] = self.position.source
        
        # Add velocity data
        if self.velocity:
            if self.velocity.ground_speed is not None:
                result['ground_speed'] = self.velocity.ground_speed
            if self.velocity.track_angle is not None:
                result['track'] = self.velocity.track_angle
            if self.velocity.vertical_rate is not None:
                result['vertical_rate'] = self.velocity.vertical_rate
            if self.velocity.true_airspeed is not None:
                result['true_airspeed'] = self.velocity.true_airspeed
            if self.velocity.indicated_airspeed is not None:
                result['indicated_airspeed'] = self.velocity.indicated_airspeed
            if self.velocity.mach_number is not None:
                result['mach_number'] = self.velocity.mach_number
            if self.velocity.magnetic_heading is not None:
                result['magnetic_heading'] = self.velocity.magnetic_heading
        
        # Add identification data
        if self.identification:
            if self.identification.callsign is not None:
                result['callsign'] = self.identification.get_clean_callsign()
            if self.identification.aircraft_category is not None:
                result['aircraft_category'] = self.identification.aircraft_category
        
        # Add surveillance data
        if self.surveillance_status is not None:
            result['surveillance_status'] = self.surveillance_status
        if self.emergency_status is not None:
            result['emergency_status'] = self.emergency_status
        
        # Add metadata
        if self.metadata.source_id is not None:
            result['source_id'] = self.metadata.source_id
        if self.metadata.source_type is not None:
            result['source_type'] = self.metadata.source_type
        if self.metadata.crc_valid is not None:
            result['crc_valid'] = self.metadata.crc_valid
        
        return result
    
    def to_api_dict(self) -> Dict[str, Any]:
        """
        Convert to API format compatible with existing UrsineExplorer format
        
        Returns:
            Dictionary in format expected by existing API consumers
        """
        api_data = {
            'hex': self.icao,
            'type': self.message_type.value,
            'seen': self.metadata.timestamp,
            'messages': 1  # Single message
        }
        
        # Position data
        if self.position and self.position.is_valid_position():
            api_data['lat'] = self.position.latitude
            api_data['lon'] = self.position.longitude
            
            if self.position.altitude_baro is not None:
                api_data['altitude'] = self.position.altitude_baro
        
        # Velocity data
        if self.velocity:
            if self.velocity.ground_speed is not None:
                api_data['speed'] = self.velocity.ground_speed
            if self.velocity.track_angle is not None:
                api_data['track'] = self.velocity.track_angle
            if self.velocity.vertical_rate is not None:
                api_data['vert_rate'] = self.velocity.vertical_rate
        
        # Identification data
        if self.identification and self.identification.get_clean_callsign():
            api_data['flight'] = self.identification.get_clean_callsign()
        
        return api_data
    
    def get_age_seconds(self, current_time: Optional[float] = None) -> float:
        """
        Get message age in seconds
        
        Args:
            current_time: Current timestamp (defaults to now)
            
        Returns:
            Age in seconds
        """
        if current_time is None:
            current_time = datetime.now().timestamp()
        
        return current_time - self.metadata.timestamp
    
    def is_recent(self, max_age_seconds: float = 300) -> bool:
        """
        Check if message is recent
        
        Args:
            max_age_seconds: Maximum age to consider recent
            
        Returns:
            True if message is recent, False otherwise
        """
        return self.get_age_seconds() <= max_age_seconds
    
    def has_position(self) -> bool:
        """Check if message contains valid position data"""
        return self.position is not None and self.position.is_valid_position()
    
    def has_velocity(self) -> bool:
        """Check if message contains velocity data"""
        return self.velocity is not None and self.velocity.is_valid_velocity()
    
    def has_identification(self) -> bool:
        """Check if message contains identification data"""
        return (self.identification is not None and 
                self.identification.get_clean_callsign() is not None)
    
    def get_summary(self) -> str:
        """
        Get human-readable summary of message
        
        Returns:
            String summary of message content
        """
        parts = [f"ICAO:{self.icao}", f"Type:{self.message_type.value}"]
        
        if self.has_identification():
            parts.append(f"Call:{self.identification.get_clean_callsign()}")
        
        if self.has_position():
            parts.append(f"Pos:{self.position.latitude:.4f},{self.position.longitude:.4f}")
            if self.position.altitude_baro:
                parts.append(f"Alt:{self.position.altitude_baro}ft")
        
        if self.has_velocity():
            if self.velocity.ground_speed:
                parts.append(f"Spd:{self.velocity.ground_speed:.0f}kt")
            if self.velocity.track_angle:
                parts.append(f"Trk:{self.velocity.track_angle:.0f}°")
        
        return " ".join(parts)
    
    def __str__(self) -> str:
        """String representation"""
        return self.get_summary()
    
    def __repr__(self) -> str:
        """Detailed representation"""
        return f"DecodedMessage({self.get_summary()})"


class MessageBatch:
    """
    Container for multiple decoded messages with batch operations
    """
    
    def __init__(self, messages: Optional[list] = None):
        """Initialize message batch"""
        self.messages: list[DecodedMessage] = messages or []
        self.created_at = datetime.now()
    
    def add_message(self, message: DecodedMessage):
        """Add a message to the batch"""
        self.messages.append(message)
    
    def filter_by_type(self, message_type: MessageType) -> 'MessageBatch':
        """Filter messages by type"""
        filtered = [msg for msg in self.messages if msg.message_type == message_type]
        return MessageBatch(filtered)
    
    def filter_by_icao(self, icao: str) -> 'MessageBatch':
        """Filter messages by ICAO address"""
        icao_upper = icao.upper()
        filtered = [msg for msg in self.messages if msg.icao == icao_upper]
        return MessageBatch(filtered)
    
    def filter_recent(self, max_age_seconds: float = 300) -> 'MessageBatch':
        """Filter to recent messages only"""
        filtered = [msg for msg in self.messages if msg.is_recent(max_age_seconds)]
        return MessageBatch(filtered)
    
    def get_unique_aircraft(self) -> set[str]:
        """Get set of unique ICAO addresses"""
        return {msg.icao for msg in self.messages}
    
    def group_by_icao(self) -> Dict[str, list[DecodedMessage]]:
        """Group messages by ICAO address"""
        groups = {}
        for msg in self.messages:
            if msg.icao not in groups:
                groups[msg.icao] = []
            groups[msg.icao].append(msg)
        return groups
    
    def to_api_format(self) -> Dict[str, Any]:
        """Convert batch to API format"""
        aircraft_dict = {}
        
        for msg in self.messages:
            icao = msg.icao
            if icao not in aircraft_dict:
                aircraft_dict[icao] = msg.to_api_dict()
            else:
                # Merge data from multiple messages
                existing = aircraft_dict[icao]
                new_data = msg.to_api_dict()
                
                # Update with newer data
                if new_data.get('seen', 0) > existing.get('seen', 0):
                    existing.update(new_data)
                    existing['messages'] = existing.get('messages', 0) + 1
        
        return {
            'aircraft': list(aircraft_dict.values()),
            'now': datetime.now().timestamp(),
            'messages': len(self.messages)
        }
    
    def __len__(self) -> int:
        """Get number of messages in batch"""
        return len(self.messages)
    
    def __iter__(self):
        """Iterate over messages"""
        return iter(self.messages)
    
    def __getitem__(self, index):
        """Get message by index"""
        return self.messages[index]