"""
Position Calculator Module

Implements CPR (Compact Position Reporting) position decoding using pyModeS algorithms
for accurate aircraft position calculation from ADS-B messages.
"""

import logging
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

try:
    import pyModeS as pms
except ImportError:
    pms = None
    logging.warning("pyModeS not available - position calculation will be limited")

logger = logging.getLogger(__name__)


class PositionCalculator:
    """
    Handles CPR position decoding using pyModeS algorithms
    
    Supports both global and local position calculation methods,
    handles even/odd message pairing and reference position logic.
    """
    
    def __init__(self, reference_lat: Optional[float] = None, reference_lon: Optional[float] = None):
        """
        Initialize position calculator
        
        Args:
            reference_lat: Reference latitude for local position calculation
            reference_lon: Reference longitude for local position calculation
        """
        self.reference_lat = reference_lat
        self.reference_lon = reference_lon
        
        # Store recent position messages for global decoding
        self.position_cache: Dict[str, Dict[str, Any]] = defaultdict(dict)
        
        # Statistics
        self.stats = {
            'global_positions_calculated': 0,
            'local_positions_calculated': 0,
            'surface_positions_calculated': 0,
            'position_errors': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        
        # Cache cleanup interval
        self.cache_cleanup_interval = timedelta(minutes=5)
        self.last_cleanup = datetime.now()
        
        logger.info(f"PositionCalculator initialized with reference: ({reference_lat}, {reference_lon})")
    
    def calculate_position(self, icao: str, message: str, timestamp: float = None) -> Optional[Tuple[float, float]]:
        """
        Calculate aircraft position from ADS-B message
        
        Args:
            icao: Aircraft ICAO identifier
            message: Raw ADS-B message (hex string)
            timestamp: Message timestamp (optional)
            
        Returns:
            Tuple of (latitude, longitude) or None if calculation fails
        """
        if not pms:
            logger.error("pyModeS not available for position calculation")
            return None
        
        if timestamp is None:
            timestamp = datetime.now().timestamp()
        
        try:
            # Check if this is a position message
            if not self._is_position_message(message):
                return None
            
            # Get message type and format
            df = pms.df(message)
            tc = pms.adsb.typecode(message) if df == 17 else None
            
            if df == 17 and tc in [9, 10, 11, 12, 13, 14, 15, 16, 17, 18]:
                # Airborne position message
                return self._calculate_airborne_position(icao, message, timestamp)
            elif df == 17 and tc in [5, 6, 7, 8]:
                # Surface position message
                return self._calculate_surface_position(icao, message, timestamp)
            else:
                logger.debug(f"Unsupported position message type: DF={df}, TC={tc}")
                return None
                
        except Exception as e:
            self.stats['position_errors'] += 1
            logger.error(f"Error calculating position for {icao}: {e}")
            return None
    
    def calculate_position_from_cpr(self, icao: str, lat_cpr: int, lon_cpr: int, 
                                  cpr_format: int, timestamp: float = None) -> Optional[Tuple[float, float]]:
        """
        Calculate position directly from CPR coordinates
        
        Args:
            icao: Aircraft ICAO identifier
            lat_cpr: CPR latitude coordinate
            lon_cpr: CPR longitude coordinate
            cpr_format: CPR format (0 for even, 1 for odd)
            timestamp: Message timestamp
            
        Returns:
            Tuple of (latitude, longitude) or None if calculation fails
        """
        if not pms:
            return None
        
        if timestamp is None:
            timestamp = datetime.now().timestamp()
        
        try:
            # Store CPR data for global calculation
            self._store_cpr_data(icao, lat_cpr, lon_cpr, cpr_format, timestamp)
            
            # Try global position calculation first
            position = self._try_global_position(icao)
            if position:
                self.stats['global_positions_calculated'] += 1
                return position
            
            # Fall back to local position if reference available
            if self.reference_lat is not None and self.reference_lon is not None:
                position = self._try_local_position(lat_cpr, lon_cpr, cpr_format)
                if position:
                    self.stats['local_positions_calculated'] += 1
                    return position
            
            return None
            
        except Exception as e:
            self.stats['position_errors'] += 1
            logger.error(f"Error calculating CPR position for {icao}: {e}")
            return None
    
    def set_reference_position(self, lat: float, lon: float) -> None:
        """
        Set reference position for local CPR calculation
        
        Args:
            lat: Reference latitude
            lon: Reference longitude
        """
        self.reference_lat = lat
        self.reference_lon = lon
        logger.info(f"Reference position updated to ({lat}, {lon})")
    
    def cleanup_cache(self, max_age_seconds: int = 300) -> int:
        """
        Clean up old position cache entries
        
        Args:
            max_age_seconds: Maximum age for cache entries
            
        Returns:
            Number of entries removed
        """
        current_time = datetime.now().timestamp()
        cutoff_time = current_time - max_age_seconds
        
        removed_count = 0
        
        for icao in list(self.position_cache.keys()):
            aircraft_cache = self.position_cache[icao]
            
            # Remove old entries
            for format_key in list(aircraft_cache.keys()):
                if aircraft_cache[format_key]['timestamp'] < cutoff_time:
                    del aircraft_cache[format_key]
                    removed_count += 1
            
            # Remove empty aircraft entries
            if not aircraft_cache:
                del self.position_cache[icao]
        
        self.last_cleanup = datetime.now()
        
        if removed_count > 0:
            logger.debug(f"Cleaned up {removed_count} old position cache entries")
        
        return removed_count
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get position calculator statistics"""
        stats = self.stats.copy()
        stats.update({
            'cache_size': sum(len(cache) for cache in self.position_cache.values()),
            'aircraft_in_cache': len(self.position_cache),
            'reference_position': (self.reference_lat, self.reference_lon),
            'pymodes_available': pms is not None
        })
        return stats
    
    def reset_statistics(self) -> None:
        """Reset all statistics counters"""
        self.stats = {key: 0 for key in self.stats}
        logger.info("Position calculator statistics reset")
    
    def _is_position_message(self, message: str) -> bool:
        """Check if message contains position information"""
        if not pms:
            return False
        
        try:
            df = pms.df(message)
            if df != 17:  # Only ADS-B messages
                return False
            
            tc = pms.adsb.typecode(message)
            # Position message type codes: 5-8 (surface), 9-18 (airborne)
            return tc in [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18]
            
        except Exception:
            return False
    
    def _calculate_airborne_position(self, icao: str, message: str, timestamp: float) -> Optional[Tuple[float, float]]:
        """Calculate airborne position from ADS-B message"""
        try:
            # Extract CPR coordinates
            lat_cpr = pms.adsb.cprlat(message)
            lon_cpr = pms.adsb.cprlon(message)
            cpr_format = pms.adsb.oe_flag(message)
            
            return self.calculate_position_from_cpr(icao, lat_cpr, lon_cpr, cpr_format, timestamp)
            
        except Exception as e:
            logger.error(f"Error calculating airborne position: {e}")
            return None
    
    def _calculate_surface_position(self, icao: str, message: str, timestamp: float) -> Optional[Tuple[float, float]]:
        """Calculate surface position from ADS-B message"""
        try:
            # Extract CPR coordinates for surface position
            lat_cpr = pms.adsb.cprlat(message)
            lon_cpr = pms.adsb.cprlon(message)
            cpr_format = pms.adsb.oe_flag(message)
            
            # Surface positions require reference position
            if self.reference_lat is None or self.reference_lon is None:
                logger.debug(f"No reference position for surface calculation: {icao}")
                return None
            
            # Try local position calculation for surface
            position = self._try_local_position(lat_cpr, lon_cpr, cpr_format)
            if position:
                self.stats['surface_positions_calculated'] += 1
                return position
            
            return None
            
        except Exception as e:
            logger.error(f"Error calculating surface position: {e}")
            return None
    
    def _store_cpr_data(self, icao: str, lat_cpr: int, lon_cpr: int, cpr_format: int, timestamp: float) -> None:
        """Store CPR data for global position calculation"""
        format_key = f"format_{cpr_format}"
        
        self.position_cache[icao][format_key] = {
            'lat_cpr': lat_cpr,
            'lon_cpr': lon_cpr,
            'timestamp': timestamp
        }
        
        # Periodic cache cleanup
        if datetime.now() - self.last_cleanup > self.cache_cleanup_interval:
            self.cleanup_cache()
    
    def _try_global_position(self, icao: str) -> Optional[Tuple[float, float]]:
        """Try to calculate global position using even/odd message pair"""
        if icao not in self.position_cache:
            self.stats['cache_misses'] += 1
            return None
        
        cache = self.position_cache[icao]
        
        # Need both even and odd messages
        if 'format_0' not in cache or 'format_1' not in cache:
            self.stats['cache_misses'] += 1
            return None
        
        self.stats['cache_hits'] += 1
        
        try:
            even_data = cache['format_0']
            odd_data = cache['format_1']
            
            # Check if messages are recent enough (within 10 seconds)
            time_diff = abs(even_data['timestamp'] - odd_data['timestamp'])
            if time_diff > 10:
                logger.debug(f"CPR messages too far apart for {icao}: {time_diff}s")
                return None
            
            # Use pyModeS global position calculation
            lat, lon = pms.adsb.cpr2position(
                even_data['lat_cpr'], even_data['lon_cpr'],
                odd_data['lat_cpr'], odd_data['lon_cpr'],
                even_data['timestamp'], odd_data['timestamp']
            )
            
            # Validate calculated position
            if lat is None or lon is None:
                return None
            
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                logger.warning(f"Invalid global position calculated for {icao}: ({lat}, {lon})")
                return None
            
            return (lat, lon)
            
        except Exception as e:
            logger.error(f"Error in global position calculation for {icao}: {e}")
            return None
    
    def _try_local_position(self, lat_cpr: int, lon_cpr: int, cpr_format: int) -> Optional[Tuple[float, float]]:
        """Try to calculate local position using reference position"""
        if self.reference_lat is None or self.reference_lon is None:
            return None
        
        try:
            # Use pyModeS local position calculation
            lat, lon = pms.adsb.cpr2position(
                lat_cpr, lon_cpr, cpr_format,
                self.reference_lat, self.reference_lon
            )
            
            # Validate calculated position
            if lat is None or lon is None:
                return None
            
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                logger.warning(f"Invalid local position calculated: ({lat}, {lon})")
                return None
            
            # Check if position is within reasonable range of reference (180 NM ~ 3 degrees)
            lat_diff = abs(lat - self.reference_lat)
            lon_diff = abs(lon - self.reference_lon)
            
            if lat_diff > 3 or lon_diff > 3:
                logger.debug(f"Local position too far from reference: ({lat}, {lon})")
                return None
            
            return (lat, lon)
            
        except Exception as e:
            logger.error(f"Error in local position calculation: {e}")
            return None