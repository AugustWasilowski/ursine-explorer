"""
Enhanced Aircraft Data Structure

Provides an enhanced aircraft class that integrates pyModeS decoded data
while maintaining compatibility with the existing UrsineExplorer system.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EnhancedAircraft:
    """
    Enhanced aircraft data structure with pyModeS integration
    
    This class extends the basic aircraft data with additional fields
    provided by pyModeS decoding while maintaining backward compatibility.
    """
    
    # Required fields
    icao: str
    first_seen: datetime
    last_seen: datetime
    
    # Optional identification
    callsign: Optional[str] = None
    
    # Position (using pyModeS CPR decoding)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude_baro: Optional[int] = None
    altitude_gnss: Optional[int] = None
    
    # Velocity (enhanced with pyModeS)
    ground_speed: Optional[float] = None
    track_angle: Optional[float] = None
    vertical_rate: Optional[float] = None
    
    # Enhanced flight data from pyModeS
    true_airspeed: Optional[float] = None
    indicated_airspeed: Optional[float] = None
    mach_number: Optional[float] = None
    magnetic_heading: Optional[float] = None
    roll_angle: Optional[float] = None
    track_rate: Optional[float] = None
    
    # Navigation accuracy (from pyModeS)
    navigation_accuracy: Optional[Dict[str, float]] = None
    surveillance_status: Optional[str] = None
    
    # Legacy compatibility fields
    squawk: Optional[str] = None
    category: Optional[str] = None
    
    # System metadata
    message_count: int = 0
    is_watchlist: bool = False
    data_sources: Set[str] = field(default_factory=set)
    
    # Raw pyModeS data for debugging
    raw_pymodes_data: Optional[Dict] = None
    
    @classmethod
    def from_pymodes_data(cls, decoded_data: Dict[str, Any]) -> 'EnhancedAircraft':
        """
        Create EnhancedAircraft from pyModeS decoded data
        
        Args:
            decoded_data: Decoded message data from pyModeS
            
        Returns:
            New EnhancedAircraft instance
        """
        now = datetime.now()
        
        aircraft = cls(
            icao=decoded_data['icao'],
            first_seen=now,
            last_seen=now,
            message_count=1,
            raw_pymodes_data=decoded_data.copy()
        )
        
        # Update with decoded data
        aircraft.update_from_pymodes(decoded_data)
        
        return aircraft
    
    def update_from_pymodes(self, decoded_data: Dict[str, Any]) -> None:
        """
        Update aircraft data from pyModeS decoded message
        
        Args:
            decoded_data: Decoded message data from pyModeS
        """
        self.last_seen = datetime.now()
        self.message_count += 1
        
        # Update identification
        if 'callsign' in decoded_data:
            self.callsign = decoded_data['callsign']
        
        # Update position
        if 'latitude' in decoded_data:
            self.latitude = decoded_data['latitude']
        if 'longitude' in decoded_data:
            self.longitude = decoded_data['longitude']
        if 'altitude' in decoded_data:
            self.altitude_baro = decoded_data['altitude']
        
        # Update velocity
        if 'ground_speed' in decoded_data:
            self.ground_speed = decoded_data['ground_speed']
        if 'track' in decoded_data:
            self.track_angle = decoded_data['track']
        if 'vertical_rate' in decoded_data:
            self.vertical_rate = decoded_data['vertical_rate']
        
        # Update enhanced flight data
        if 'true_airspeed' in decoded_data:
            self.true_airspeed = decoded_data['true_airspeed']
        if 'indicated_airspeed' in decoded_data:
            self.indicated_airspeed = decoded_data['indicated_airspeed']
        if 'mach_number' in decoded_data:
            self.mach_number = decoded_data['mach_number']
        
        # Track data source
        message_type = decoded_data.get('message_type', 'unknown')
        self.data_sources.add(message_type)
        
        # Store raw data for debugging
        if self.raw_pymodes_data is None:
            self.raw_pymodes_data = {}
        self.raw_pymodes_data.update(decoded_data)
    
    def update_from_legacy(self, legacy_data: Dict[str, Any]) -> None:
        """
        Update aircraft data from legacy UrsineExplorer format
        
        Args:
            legacy_data: Aircraft data in legacy format
        """
        self.last_seen = datetime.now()
        self.message_count += 1
        
        # Map legacy fields
        if 'flight' in legacy_data and legacy_data['flight'] != 'Unknown':
            self.callsign = legacy_data['flight'].strip()
        
        if 'lat' in legacy_data and legacy_data['lat'] != 'Unknown':
            self.latitude = float(legacy_data['lat'])
        
        if 'lon' in legacy_data and legacy_data['lon'] != 'Unknown':
            self.longitude = float(legacy_data['lon'])
        
        if 'alt_baro' in legacy_data and legacy_data['alt_baro'] != 'Unknown':
            self.altitude_baro = int(legacy_data['alt_baro'])
        
        if 'gs' in legacy_data and legacy_data['gs'] != 'Unknown':
            self.ground_speed = float(legacy_data['gs'])
        
        if 'track' in legacy_data and legacy_data['track'] != 'Unknown':
            self.track_angle = float(legacy_data['track'])
        
        if 'squawk' in legacy_data and legacy_data['squawk'] != 'Unknown':
            self.squawk = str(legacy_data['squawk'])
        
        if 'category' in legacy_data and legacy_data['category'] != 'Unknown':
            self.category = str(legacy_data['category'])
        
        # Track legacy source
        self.data_sources.add('legacy')
    
    def to_api_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for API compatibility
        
        Returns:
            Dictionary compatible with existing API format
        """
        # Legacy compatibility format
        api_dict = {
            'hex': self.icao,
            'flight': self.callsign or 'Unknown',
            'alt_baro': self.altitude_baro if self.altitude_baro is not None else 'Unknown',
            'gs': self.ground_speed if self.ground_speed is not None else 'Unknown',
            'track': self.track_angle if self.track_angle is not None else 'Unknown',
            'lat': self.latitude if self.latitude is not None else 'Unknown',
            'lon': self.longitude if self.longitude is not None else 'Unknown',
            'squawk': self.squawk or 'Unknown',
            'category': self.category or 'Unknown',
            'messages': self.message_count,
            'last_seen': self.last_seen.isoformat(),
            'is_watchlist': self.is_watchlist
        }
        
        # Add enhanced fields if available
        enhanced_fields = {}
        
        if self.altitude_gnss is not None:
            enhanced_fields['alt_gnss'] = self.altitude_gnss
        
        if self.vertical_rate is not None:
            enhanced_fields['vertical_rate'] = self.vertical_rate
        
        if self.true_airspeed is not None:
            enhanced_fields['true_airspeed'] = self.true_airspeed
        
        if self.indicated_airspeed is not None:
            enhanced_fields['indicated_airspeed'] = self.indicated_airspeed
        
        if self.mach_number is not None:
            enhanced_fields['mach_number'] = self.mach_number
        
        if self.magnetic_heading is not None:
            enhanced_fields['magnetic_heading'] = self.magnetic_heading
        
        if self.roll_angle is not None:
            enhanced_fields['roll_angle'] = self.roll_angle
        
        if self.navigation_accuracy is not None:
            enhanced_fields['navigation_accuracy'] = self.navigation_accuracy
        
        if self.surveillance_status is not None:
            enhanced_fields['surveillance_status'] = self.surveillance_status
        
        # Add enhanced fields to API dict
        if enhanced_fields:
            api_dict['enhanced'] = enhanced_fields
        
        # Add metadata
        api_dict['data_sources'] = list(self.data_sources)
        api_dict['first_seen'] = self.first_seen.isoformat()
        
        return api_dict
    
    def to_legacy_dict(self) -> Dict[str, Any]:
        """
        Convert to legacy Aircraft format for backward compatibility
        
        Returns:
            Dictionary in legacy Aircraft format
        """
        return {
            'hex': self.icao,
            'flight': self.callsign or 'Unknown',
            'alt_baro': self.altitude_baro if self.altitude_baro is not None else 'Unknown',
            'gs': self.ground_speed if self.ground_speed is not None else 'Unknown',
            'track': self.track_angle if self.track_angle is not None else 'Unknown',
            'lat': self.latitude if self.latitude is not None else 'Unknown',
            'lon': self.longitude if self.longitude is not None else 'Unknown',
            'squawk': self.squawk or 'Unknown',
            'category': self.category or 'Unknown',
            'messages': self.message_count,
            'last_seen': self.last_seen.isoformat(),
            'is_watchlist': self.is_watchlist
        }
    
    def calculate_age_seconds(self) -> int:
        """Get age in seconds since last seen"""
        return int((datetime.now() - self.last_seen).total_seconds())
    
    def calculate_duration_seconds(self) -> int:
        """Get total tracking duration in seconds"""
        return int((self.last_seen - self.first_seen).total_seconds())
    
    def has_position(self) -> bool:
        """Check if aircraft has valid position data"""
        return self.latitude is not None and self.longitude is not None
    
    def has_velocity(self) -> bool:
        """Check if aircraft has velocity data"""
        return self.ground_speed is not None or self.track_angle is not None
    
    def has_altitude(self) -> bool:
        """Check if aircraft has altitude data"""
        return self.altitude_baro is not None or self.altitude_gnss is not None
    
    def get_display_name(self) -> str:
        """Get display name for aircraft"""
        if self.callsign and self.callsign != 'Unknown':
            return f"{self.icao} ({self.callsign})"
        return self.icao
    
    def __str__(self) -> str:
        """String representation of aircraft"""
        return f"Aircraft({self.get_display_name()})"
    
    def __repr__(self) -> str:
        """Detailed string representation"""
        return (f"EnhancedAircraft(icao='{self.icao}', callsign='{self.callsign}', "
                f"position=({self.latitude}, {self.longitude}), "
                f"altitude={self.altitude_baro}, messages={self.message_count})")