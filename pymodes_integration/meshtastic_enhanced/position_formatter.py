"""
Position formatting and coordinate conversion utilities

This module provides utilities for formatting position data in various formats
and converting between different coordinate systems for Meshtastic messages.
"""

import math
import logging
from typing import Tuple, Optional, Dict, Any, Union
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class CoordinateFormat(Enum):
    """Supported coordinate formats"""
    DECIMAL_DEGREES = "decimal_degrees"      # 40.7128, -74.0060
    DEGREES_MINUTES = "degrees_minutes"      # 40°42.768'N, 74°00.360'W
    DEGREES_MINUTES_SECONDS = "degrees_minutes_seconds"  # 40°42'46.08"N, 74°00'21.60"W
    MAIDENHEAD = "maidenhead"               # FN30as
    MGRS = "mgrs"                          # 18TWL8745110705
    UTM = "utm"                            # 18T 587451 4507071
    COMPACT = "compact"                     # 40.713,-74.006 (3 decimal places)
    ULTRA_COMPACT = "ultra_compact"         # 4071,-7401 (no decimal point)


class DistanceUnit(Enum):
    """Distance units"""
    METERS = "m"
    KILOMETERS = "km"
    FEET = "ft"
    NAUTICAL_MILES = "nm"
    STATUTE_MILES = "mi"


@dataclass
class Position:
    """
    Position data with formatting capabilities
    
    Attributes:
        latitude: Latitude in decimal degrees
        longitude: Longitude in decimal degrees
        altitude: Optional altitude in feet
        accuracy: Optional accuracy in meters
        timestamp: Optional timestamp
    """
    latitude: float
    longitude: float
    altitude: Optional[float] = None
    accuracy: Optional[float] = None
    timestamp: Optional[str] = None
    
    def __post_init__(self):
        """Validate position data"""
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"Latitude must be between -90 and 90, got {self.latitude}")
        
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"Longitude must be between -180 and 180, got {self.longitude}")
    
    def format(self, format_type: CoordinateFormat) -> str:
        """
        Format position in specified coordinate format
        
        Args:
            format_type: Coordinate format to use
            
        Returns:
            Formatted position string
        """
        if format_type == CoordinateFormat.DECIMAL_DEGREES:
            return f"{self.latitude:.6f},{self.longitude:.6f}"
        
        elif format_type == CoordinateFormat.COMPACT:
            return f"{self.latitude:.3f},{self.longitude:.3f}"
        
        elif format_type == CoordinateFormat.ULTRA_COMPACT:
            # Convert to integer representation (multiply by 1000, remove decimal)
            lat_int = int(self.latitude * 1000)
            lon_int = int(self.longitude * 1000)
            return f"{lat_int},{lon_int}"
        
        elif format_type == CoordinateFormat.DEGREES_MINUTES:
            return self._format_degrees_minutes()
        
        elif format_type == CoordinateFormat.DEGREES_MINUTES_SECONDS:
            return self._format_degrees_minutes_seconds()
        
        elif format_type == CoordinateFormat.MAIDENHEAD:
            return self._format_maidenhead()
        
        elif format_type == CoordinateFormat.MGRS:
            return self._format_mgrs()
        
        elif format_type == CoordinateFormat.UTM:
            return self._format_utm()
        
        else:
            # Default to decimal degrees
            return self.format(CoordinateFormat.DECIMAL_DEGREES)
    
    def _format_degrees_minutes(self) -> str:
        """Format as degrees and decimal minutes"""
        lat_deg = int(abs(self.latitude))
        lat_min = (abs(self.latitude) - lat_deg) * 60
        lat_dir = 'N' if self.latitude >= 0 else 'S'
        
        lon_deg = int(abs(self.longitude))
        lon_min = (abs(self.longitude) - lon_deg) * 60
        lon_dir = 'E' if self.longitude >= 0 else 'W'
        
        return f"{lat_deg}°{lat_min:.3f}'{lat_dir}, {lon_deg}°{lon_min:.3f}'{lon_dir}"
    
    def _format_degrees_minutes_seconds(self) -> str:
        """Format as degrees, minutes, and seconds"""
        lat_deg = int(abs(self.latitude))
        lat_min_float = (abs(self.latitude) - lat_deg) * 60
        lat_min = int(lat_min_float)
        lat_sec = (lat_min_float - lat_min) * 60
        lat_dir = 'N' if self.latitude >= 0 else 'S'
        
        lon_deg = int(abs(self.longitude))
        lon_min_float = (abs(self.longitude) - lon_deg) * 60
        lon_min = int(lon_min_float)
        lon_sec = (lon_min_float - lon_min) * 60
        lon_dir = 'E' if self.longitude >= 0 else 'W'
        
        return f"{lat_deg}°{lat_min}'{lat_sec:.1f}\"{lat_dir}, {lon_deg}°{lon_min}'{lon_sec:.1f}\"{lon_dir}"
    
    def _format_maidenhead(self) -> str:
        """Format as Maidenhead locator (6-character)"""
        # Adjust longitude and latitude to positive values
        adj_lon = self.longitude + 180
        adj_lat = self.latitude + 90
        
        # First pair (field)
        field_lon = chr(ord('A') + int(adj_lon / 20))
        field_lat = chr(ord('A') + int(adj_lat / 10))
        
        # Second pair (square)
        square_lon = str(int((adj_lon % 20) / 2))
        square_lat = str(int((adj_lat % 10) / 1))
        
        # Third pair (subsquare)
        subsq_lon = chr(ord('a') + int(((adj_lon % 20) % 2) * 12))
        subsq_lat = chr(ord('a') + int(((adj_lat % 10) % 1) * 24))
        
        return f"{field_lon}{field_lat}{square_lon}{square_lat}{subsq_lon}{subsq_lat}"
    
    def _format_mgrs(self) -> str:
        """Format as Military Grid Reference System (simplified)"""
        # This is a simplified MGRS implementation
        # For production use, consider using a proper MGRS library
        utm_zone, utm_letter, easting, northing = self._to_utm()
        
        # Simplified grid square calculation
        grid_square = "WL"  # Placeholder - proper MGRS would calculate this
        
        # Format easting and northing to 5 digits each
        easting_str = f"{int(easting):05d}"
        northing_str = f"{int(northing):05d}"
        
        return f"{utm_zone}{utm_letter}{grid_square}{easting_str}{northing_str}"
    
    def _format_utm(self) -> str:
        """Format as UTM coordinates"""
        utm_zone, utm_letter, easting, northing = self._to_utm()
        return f"{utm_zone}{utm_letter} {easting:.0f} {northing:.0f}"
    
    def _to_utm(self) -> Tuple[int, str, float, float]:
        """
        Convert to UTM coordinates (simplified implementation)
        
        Returns:
            Tuple of (zone_number, zone_letter, easting, northing)
        """
        # Simplified UTM conversion - for production use, consider using pyproj
        zone_number = int((self.longitude + 180) / 6) + 1
        
        # Zone letter calculation
        if self.latitude >= 0:
            zone_letter = chr(ord('N') + min(int(self.latitude / 8), 11))
        else:
            zone_letter = chr(ord('M') - min(int(abs(self.latitude) / 8), 12))
        
        # Simplified easting/northing calculation
        # This is a very rough approximation - use proper UTM library for accuracy
        central_meridian = (zone_number - 1) * 6 - 180 + 3
        easting = 500000 + (self.longitude - central_meridian) * 111320 * math.cos(math.radians(self.latitude))
        northing = self.latitude * 110540
        
        if northing < 0:
            northing += 10000000  # False northing for southern hemisphere
        
        return zone_number, zone_letter, easting, northing
    
    def distance_to(self, other: 'Position', unit: DistanceUnit = DistanceUnit.NAUTICAL_MILES) -> float:
        """
        Calculate distance to another position using Haversine formula
        
        Args:
            other: Other position
            unit: Distance unit to return
            
        Returns:
            Distance in specified unit
        """
        # Haversine formula
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Distance in kilometers
        distance_km = 6371 * c
        
        # Convert to requested unit
        if unit == DistanceUnit.KILOMETERS:
            return distance_km
        elif unit == DistanceUnit.METERS:
            return distance_km * 1000
        elif unit == DistanceUnit.NAUTICAL_MILES:
            return distance_km * 0.539957
        elif unit == DistanceUnit.STATUTE_MILES:
            return distance_km * 0.621371
        elif unit == DistanceUnit.FEET:
            return distance_km * 3280.84
        else:
            return distance_km
    
    def bearing_to(self, other: 'Position') -> float:
        """
        Calculate bearing to another position
        
        Args:
            other: Other position
            
        Returns:
            Bearing in degrees (0-360)
        """
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        
        dlon = lon2 - lon1
        
        y = math.sin(dlon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
        
        bearing = math.atan2(y, x)
        bearing = math.degrees(bearing)
        bearing = (bearing + 360) % 360
        
        return bearing


class PositionFormatter:
    """
    Utility class for formatting positions in various ways
    """
    
    @staticmethod
    def format_position(latitude: float, longitude: float, 
                       format_type: CoordinateFormat = CoordinateFormat.DECIMAL_DEGREES,
                       precision: Optional[int] = None) -> str:
        """
        Format position coordinates
        
        Args:
            latitude: Latitude in decimal degrees
            longitude: Longitude in decimal degrees
            format_type: Coordinate format to use
            precision: Optional precision override
            
        Returns:
            Formatted position string
        """
        position = Position(latitude, longitude)
        formatted = position.format(format_type)
        
        # Apply precision override if specified
        if precision is not None and format_type == CoordinateFormat.DECIMAL_DEGREES:
            formatted = f"{latitude:.{precision}f},{longitude:.{precision}f}"
        
        return formatted
    
    @staticmethod
    def format_distance(distance: float, unit: DistanceUnit = DistanceUnit.NAUTICAL_MILES,
                       precision: int = 1) -> str:
        """
        Format distance with unit
        
        Args:
            distance: Distance value
            unit: Distance unit
            precision: Decimal places
            
        Returns:
            Formatted distance string
        """
        return f"{distance:.{precision}f}{unit.value}"
    
    @staticmethod
    def format_bearing(bearing: float, precision: int = 0) -> str:
        """
        Format bearing in degrees
        
        Args:
            bearing: Bearing in degrees
            precision: Decimal places
            
        Returns:
            Formatted bearing string
        """
        return f"{bearing:.{precision}f}°"
    
    @staticmethod
    def format_altitude(altitude: float, unit: str = "ft", precision: int = 0) -> str:
        """
        Format altitude with unit
        
        Args:
            altitude: Altitude value
            unit: Altitude unit
            precision: Decimal places
            
        Returns:
            Formatted altitude string
        """
        if altitude >= 10000 and unit == "ft":
            # Use flight level notation for high altitudes
            flight_level = int(altitude / 100)
            return f"FL{flight_level:03d}"
        else:
            return f"{altitude:.{precision}f}{unit}"
    
    @staticmethod
    def calculate_distance_and_bearing(lat1: float, lon1: float, 
                                     lat2: float, lon2: float) -> Tuple[float, float]:
        """
        Calculate distance and bearing between two positions
        
        Args:
            lat1, lon1: First position
            lat2, lon2: Second position
            
        Returns:
            Tuple of (distance_nm, bearing_degrees)
        """
        pos1 = Position(lat1, lon1)
        pos2 = Position(lat2, lon2)
        
        distance = pos1.distance_to(pos2, DistanceUnit.NAUTICAL_MILES)
        bearing = pos1.bearing_to(pos2)
        
        return distance, bearing
    
    @staticmethod
    def parse_position_string(position_str: str) -> Optional[Tuple[float, float]]:
        """
        Parse position string in various formats
        
        Args:
            position_str: Position string to parse
            
        Returns:
            Tuple of (latitude, longitude) or None if parsing fails
        """
        try:
            # Try decimal degrees format first
            if ',' in position_str:
                parts = position_str.split(',')
                if len(parts) == 2:
                    lat = float(parts[0].strip())
                    lon = float(parts[1].strip())
                    return lat, lon
            
            # Try space-separated format
            if ' ' in position_str:
                parts = position_str.split()
                if len(parts) == 2:
                    lat = float(parts[0])
                    lon = float(parts[1])
                    return lat, lon
            
            # Could add more parsing formats here (DMS, etc.)
            
        except (ValueError, IndexError):
            logger.warning(f"Failed to parse position string: {position_str}")
        
        return None
    
    @staticmethod
    def get_position_summary(latitude: float, longitude: float, 
                           observer_lat: Optional[float] = None,
                           observer_lon: Optional[float] = None) -> Dict[str, Any]:
        """
        Get comprehensive position summary
        
        Args:
            latitude: Target latitude
            longitude: Target longitude
            observer_lat: Optional observer latitude for distance/bearing
            observer_lon: Optional observer longitude for distance/bearing
            
        Returns:
            Dictionary with position information in various formats
        """
        position = Position(latitude, longitude)
        
        summary = {
            'decimal_degrees': position.format(CoordinateFormat.DECIMAL_DEGREES),
            'compact': position.format(CoordinateFormat.COMPACT),
            'degrees_minutes': position.format(CoordinateFormat.DEGREES_MINUTES),
            'maidenhead': position.format(CoordinateFormat.MAIDENHEAD),
            'utm': position.format(CoordinateFormat.UTM)
        }
        
        # Add distance and bearing if observer position provided
        if observer_lat is not None and observer_lon is not None:
            observer = Position(observer_lat, observer_lon)
            distance = position.distance_to(observer, DistanceUnit.NAUTICAL_MILES)
            bearing = observer.bearing_to(position)
            
            summary['distance_nm'] = distance
            summary['bearing_deg'] = bearing
            summary['distance_formatted'] = PositionFormatter.format_distance(distance)
            summary['bearing_formatted'] = PositionFormatter.format_bearing(bearing)
        
        return summary


# Convenience functions for common operations
def format_lat_lon(lat: float, lon: float, format_type: str = "decimal", precision: int = 4) -> str:
    """
    Convenience function to format latitude/longitude
    
    Args:
        lat: Latitude
        lon: Longitude
        format_type: Format type ("decimal", "compact", "dms", "maidenhead")
        precision: Decimal precision for decimal formats
        
    Returns:
        Formatted position string
    """
    format_map = {
        "decimal": CoordinateFormat.DECIMAL_DEGREES,
        "compact": CoordinateFormat.COMPACT,
        "dms": CoordinateFormat.DEGREES_MINUTES_SECONDS,
        "maidenhead": CoordinateFormat.MAIDENHEAD,
        "utm": CoordinateFormat.UTM
    }
    
    coord_format = format_map.get(format_type, CoordinateFormat.DECIMAL_DEGREES)
    return PositionFormatter.format_position(lat, lon, coord_format, precision)


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float, 
                      unit: str = "nm") -> float:
    """
    Convenience function to calculate distance between two points
    
    Args:
        lat1, lon1: First position
        lat2, lon2: Second position
        unit: Distance unit ("nm", "km", "mi", "m", "ft")
        
    Returns:
        Distance in specified unit
    """
    unit_map = {
        "nm": DistanceUnit.NAUTICAL_MILES,
        "km": DistanceUnit.KILOMETERS,
        "mi": DistanceUnit.STATUTE_MILES,
        "m": DistanceUnit.METERS,
        "ft": DistanceUnit.FEET
    }
    
    distance_unit = unit_map.get(unit, DistanceUnit.NAUTICAL_MILES)
    pos1 = Position(lat1, lon1)
    pos2 = Position(lat2, lon2)
    
    return pos1.distance_to(pos2, distance_unit)


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Convenience function to calculate bearing between two points
    
    Args:
        lat1, lon1: From position
        lat2, lon2: To position
        
    Returns:
        Bearing in degrees (0-360)
    """
    pos1 = Position(lat1, lon1)
    pos2 = Position(lat2, lon2)
    
    return pos1.bearing_to(pos2)