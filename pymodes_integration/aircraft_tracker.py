"""
Aircraft Tracker Module

Manages aircraft lifecycle, data updates, and temporal validation
for the enhanced ADS-B system with pyModeS integration.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Set
from collections import defaultdict

from .aircraft import EnhancedAircraft

logger = logging.getLogger(__name__)


class AircraftTracker:
    """
    Manages aircraft lifecycle and data updates
    
    Handles creation, updates, and cleanup of aircraft objects with
    proper data merging and temporal validation.
    """
    
    def __init__(self, cleanup_timeout: int = 300, max_aircraft: int = 10000):
        """
        Initialize aircraft tracker
        
        Args:
            cleanup_timeout: Seconds after which aircraft are removed if no updates
            max_aircraft: Maximum number of aircraft to track simultaneously
        """
        self.aircraft: Dict[str, EnhancedAircraft] = {}
        self.cleanup_timeout = cleanup_timeout
        self.max_aircraft = max_aircraft
        
        # Statistics tracking
        self.stats = {
            'total_aircraft_seen': 0,
            'aircraft_created': 0,
            'aircraft_updated': 0,
            'aircraft_cleaned_up': 0,
            'messages_processed': 0,
            'validation_errors': 0,
            'conflicts_resolved': 0
        }
        
        # Conflict resolution tracking
        self.conflict_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        
        logger.info(f"AircraftTracker initialized with {cleanup_timeout}s timeout, max {max_aircraft} aircraft")
    
    def update_aircraft(self, icao: str, decoded_data: Dict[str, Any]) -> EnhancedAircraft:
        """
        Update or create aircraft with new data
        
        Args:
            icao: Aircraft ICAO identifier
            decoded_data: Decoded message data from pyModeS or legacy source
            
        Returns:
            Updated or created EnhancedAircraft instance
        """
        self.stats['messages_processed'] += 1
        
        # Validate input data
        if not self._validate_decoded_data(icao, decoded_data):
            self.stats['validation_errors'] += 1
            logger.warning(f"Invalid data for aircraft {icao}: {decoded_data}")
            # Return existing aircraft or create minimal one
            if icao in self.aircraft:
                return self.aircraft[icao]
            else:
                return self._create_minimal_aircraft(icao)
        
        # Check if aircraft exists
        if icao in self.aircraft:
            aircraft = self.aircraft[icao]
            
            # Perform conflict resolution if needed
            if self._has_data_conflict(aircraft, decoded_data):
                self._resolve_data_conflict(aircraft, decoded_data)
                self.stats['conflicts_resolved'] += 1
            
            # Update existing aircraft
            if 'message_type' in decoded_data and decoded_data['message_type'] == 'legacy':
                aircraft.update_from_legacy(decoded_data)
            else:
                aircraft.update_from_pymodes(decoded_data)
            
            self.stats['aircraft_updated'] += 1
            
        else:
            # Create new aircraft
            if 'message_type' in decoded_data and decoded_data['message_type'] == 'legacy':
                aircraft = self._create_aircraft_from_legacy(icao, decoded_data)
            else:
                aircraft = EnhancedAircraft.from_pymodes_data({**decoded_data, 'icao': icao})
            
            self.aircraft[icao] = aircraft
            self.stats['aircraft_created'] += 1
            self.stats['total_aircraft_seen'] += 1
            
            logger.debug(f"Created new aircraft: {icao}")
        
        # Check if we need to cleanup old aircraft
        if len(self.aircraft) > self.max_aircraft:
            self._cleanup_oldest_aircraft()
        
        return aircraft
    
    def get_aircraft(self, icao: str) -> Optional[EnhancedAircraft]:
        """Get aircraft by ICAO identifier"""
        return self.aircraft.get(icao)
    
    def get_all_aircraft(self) -> Dict[str, EnhancedAircraft]:
        """Get all tracked aircraft"""
        return self.aircraft.copy()
    
    def get_active_aircraft(self, max_age_seconds: int = None) -> Dict[str, EnhancedAircraft]:
        """
        Get aircraft that have been seen recently
        
        Args:
            max_age_seconds: Maximum age in seconds (default: cleanup_timeout)
            
        Returns:
            Dictionary of active aircraft
        """
        if max_age_seconds is None:
            max_age_seconds = self.cleanup_timeout
        
        cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
        
        return {
            icao: aircraft 
            for icao, aircraft in self.aircraft.items()
            if aircraft.last_seen >= cutoff_time
        }
    
    def cleanup_old_aircraft(self, force_timeout: int = None) -> int:
        """
        Remove aircraft that haven't been seen recently
        
        Args:
            force_timeout: Override default cleanup timeout
            
        Returns:
            Number of aircraft removed
        """
        timeout = force_timeout if force_timeout is not None else self.cleanup_timeout
        cutoff_time = datetime.now() - timedelta(seconds=timeout)
        
        old_aircraft = [
            icao for icao, aircraft in self.aircraft.items()
            if aircraft.last_seen < cutoff_time
        ]
        
        for icao in old_aircraft:
            del self.aircraft[icao]
            logger.debug(f"Cleaned up old aircraft: {icao}")
        
        removed_count = len(old_aircraft)
        self.stats['aircraft_cleaned_up'] += removed_count
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old aircraft")
        
        return removed_count
    
    def get_watchlist_aircraft(self, watchlist: Set[str]) -> List[EnhancedAircraft]:
        """
        Get aircraft that match watchlist criteria
        
        Args:
            watchlist: Set of ICAO codes or callsigns to watch
            
        Returns:
            List of matching aircraft
        """
        matching_aircraft = []
        
        for aircraft in self.aircraft.values():
            # Check ICAO match
            if aircraft.icao.upper() in {w.upper() for w in watchlist}:
                aircraft.is_watchlist = True
                matching_aircraft.append(aircraft)
                continue
            
            # Check callsign match
            if aircraft.callsign:
                callsign_clean = aircraft.callsign.strip().upper()
                if callsign_clean in {w.upper() for w in watchlist}:
                    aircraft.is_watchlist = True
                    matching_aircraft.append(aircraft)
        
        return matching_aircraft
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracker statistics"""
        current_stats = self.stats.copy()
        current_stats.update({
            'current_aircraft_count': len(self.aircraft),
            'active_aircraft_count': len(self.get_active_aircraft()),
            'memory_usage_estimate': len(self.aircraft) * 1024,  # Rough estimate
            'conflict_history_size': sum(len(conflicts) for conflicts in self.conflict_history.values())
        })
        return current_stats
    
    def reset_statistics(self) -> None:
        """Reset all statistics counters"""
        self.stats = {key: 0 for key in self.stats}
        self.conflict_history.clear()
        logger.info("Aircraft tracker statistics reset")
    
    def _validate_decoded_data(self, icao: str, data: Dict[str, Any]) -> bool:
        """
        Validate decoded data for consistency and reasonableness
        
        Args:
            icao: Aircraft ICAO identifier
            data: Decoded message data
            
        Returns:
            True if data is valid, False otherwise
        """
        # Basic ICAO validation
        if not icao or len(icao) != 6:
            return False
        
        # Validate position data if present
        if 'latitude' in data:
            lat = data['latitude']
            if not isinstance(lat, (int, float)) or not (-90 <= lat <= 90):
                logger.warning(f"Invalid latitude for {icao}: {lat}")
                return False
        
        if 'longitude' in data:
            lon = data['longitude']
            if not isinstance(lon, (int, float)) or not (-180 <= lon <= 180):
                logger.warning(f"Invalid longitude for {icao}: {lon}")
                return False
        
        # Validate altitude data
        if 'altitude' in data:
            alt = data['altitude']
            if isinstance(alt, (int, float)) and not (-1000 <= alt <= 60000):
                logger.warning(f"Suspicious altitude for {icao}: {alt}")
                # Don't reject, just warn
        
        # Validate speed data
        if 'ground_speed' in data:
            gs = data['ground_speed']
            if isinstance(gs, (int, float)) and not (0 <= gs <= 1000):
                logger.warning(f"Suspicious ground speed for {icao}: {gs}")
        
        # Validate track angle
        if 'track' in data:
            track = data['track']
            if isinstance(track, (int, float)) and not (0 <= track <= 360):
                logger.warning(f"Invalid track angle for {icao}: {track}")
                return False
        
        return True
    
    def _has_data_conflict(self, aircraft: EnhancedAircraft, new_data: Dict[str, Any]) -> bool:
        """
        Check if new data conflicts with existing aircraft data
        
        Args:
            aircraft: Existing aircraft object
            new_data: New decoded data
            
        Returns:
            True if there's a significant conflict
        """
        # Check position conflicts (significant movement in short time)
        if ('latitude' in new_data and 'longitude' in new_data and 
            aircraft.latitude is not None and aircraft.longitude is not None):
            
            time_diff = (datetime.now() - aircraft.last_seen).total_seconds()
            if time_diff < 10:  # Less than 10 seconds
                # Calculate rough distance (simplified)
                lat_diff = abs(new_data['latitude'] - aircraft.latitude)
                lon_diff = abs(new_data['longitude'] - aircraft.longitude)
                
                # If movement is more than ~0.1 degrees in <10 seconds, it's suspicious
                if lat_diff > 0.1 or lon_diff > 0.1:
                    return True
        
        # Check altitude conflicts (rapid altitude changes)
        if ('altitude' in new_data and aircraft.altitude_baro is not None):
            time_diff = (datetime.now() - aircraft.last_seen).total_seconds()
            if time_diff < 5:  # Less than 5 seconds
                alt_diff = abs(new_data['altitude'] - aircraft.altitude_baro)
                # More than 5000 ft change in 5 seconds is suspicious
                if alt_diff > 5000:
                    return True
        
        # Check callsign conflicts
        if ('callsign' in new_data and aircraft.callsign is not None and 
            new_data['callsign'] != aircraft.callsign and 
            new_data['callsign'] != 'Unknown' and aircraft.callsign != 'Unknown'):
            return True
        
        return False
    
    def _resolve_data_conflict(self, aircraft: EnhancedAircraft, new_data: Dict[str, Any]) -> None:
        """
        Resolve conflicts between existing and new data
        
        Args:
            aircraft: Existing aircraft object
            new_data: New conflicting data
        """
        conflict_info = {
            'timestamp': datetime.now().isoformat(),
            'icao': aircraft.icao,
            'existing_data': {
                'latitude': aircraft.latitude,
                'longitude': aircraft.longitude,
                'altitude': aircraft.altitude_baro,
                'callsign': aircraft.callsign,
                'last_seen': aircraft.last_seen.isoformat()
            },
            'new_data': new_data.copy(),
            'resolution': 'prefer_newer'
        }
        
        # Store conflict for analysis
        self.conflict_history[aircraft.icao].append(conflict_info)
        
        # Keep only recent conflicts (last 100)
        if len(self.conflict_history[aircraft.icao]) > 100:
            self.conflict_history[aircraft.icao] = self.conflict_history[aircraft.icao][-100:]
        
        logger.warning(f"Data conflict resolved for {aircraft.icao}: preferring newer data")
    
    def _create_aircraft_from_legacy(self, icao: str, legacy_data: Dict[str, Any]) -> EnhancedAircraft:
        """
        Create aircraft from legacy data format
        
        Args:
            icao: Aircraft ICAO identifier
            legacy_data: Legacy format data
            
        Returns:
            New EnhancedAircraft instance
        """
        now = datetime.now()
        aircraft = EnhancedAircraft(
            icao=icao,
            first_seen=now,
            last_seen=now,
            message_count=1
        )
        
        aircraft.update_from_legacy(legacy_data)
        return aircraft
    
    def _create_minimal_aircraft(self, icao: str) -> EnhancedAircraft:
        """
        Create minimal aircraft object for invalid data cases
        
        Args:
            icao: Aircraft ICAO identifier
            
        Returns:
            Minimal EnhancedAircraft instance
        """
        now = datetime.now()
        return EnhancedAircraft(
            icao=icao,
            first_seen=now,
            last_seen=now,
            message_count=1
        )
    
    def _cleanup_oldest_aircraft(self) -> None:
        """Remove oldest aircraft to stay under max_aircraft limit"""
        if len(self.aircraft) <= self.max_aircraft:
            return
        
        # Sort by last_seen time and remove oldest
        sorted_aircraft = sorted(
            self.aircraft.items(),
            key=lambda x: x[1].last_seen
        )
        
        # Remove oldest 10% or at least 1
        remove_count = max(1, len(self.aircraft) // 10)
        
        for i in range(remove_count):
            if i < len(sorted_aircraft):
                icao = sorted_aircraft[i][0]
                del self.aircraft[icao]
                logger.debug(f"Removed oldest aircraft: {icao}")
        
        self.stats['aircraft_cleaned_up'] += remove_count
        logger.info(f"Cleaned up {remove_count} oldest aircraft to stay under limit")