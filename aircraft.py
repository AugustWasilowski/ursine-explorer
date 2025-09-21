"""
Aircraft data structures and tracking logic for Ursine Capture system.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
from utils import (validate_icao, safe_int, safe_float, error_handler, 
                  ErrorSeverity, ComponentType, handle_exception, safe_execute)


logger = logging.getLogger(__name__)


@dataclass
class Aircraft:
    """Aircraft data structure with all tracking information."""
    icao: str
    callsign: Optional[str] = None
    altitude: Optional[int] = None
    speed: Optional[int] = None
    track: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    squawk: Optional[str] = None
    vertical_rate: Optional[int] = None
    last_seen: datetime = field(default_factory=datetime.now)
    first_seen: datetime = field(default_factory=datetime.now)
    message_count: int = 0
    on_watchlist: bool = False
    # Watchlist-specific tracking
    watchlist_first_detected: Optional[datetime] = None
    watchlist_last_alerted: Optional[datetime] = None
    watchlist_alert_count: int = 0
    watchlist_name: str = ""
    
    def __post_init__(self):
        """Validate ICAO after initialization."""
        if not validate_icao(self.icao):
            raise ValueError(f"Invalid ICAO: {self.icao}")
    
    def update_from_message(self, message: Dict[str, Any]) -> None:
        """Update aircraft data from decoded ADS-B message with error handling."""
        try:
            self.last_seen = datetime.now()
            self.message_count += 1
            
            # Update fields if present in message
            if 'callsign' in message and message['callsign']:
                self.callsign = str(message['callsign']).strip()
                
            if 'altitude' in message:
                self.altitude = safe_int(message['altitude'])
                
            if 'speed' in message:
                self.speed = safe_int(message['speed'])
                
            if 'track' in message:
                self.track = safe_int(message['track'])
                
            if 'latitude' in message:
                self.latitude = safe_float(message['latitude'])
                
            if 'longitude' in message:
                self.longitude = safe_float(message['longitude'])
                
            if 'squawk' in message and message['squawk']:
                self.squawk = str(message['squawk'])
                
            if 'vertical_rate' in message:
                self.vertical_rate = safe_int(message['vertical_rate'])
                
        except Exception as e:
            error_handler.handle_error(
                ComponentType.AIRCRAFT_TRACKER,
                ErrorSeverity.LOW,
                f"Error updating aircraft {self.icao} from message: {str(e)}",
                error_code="AIRCRAFT_UPDATE_ERROR",
                details=f"Message: {str(message)[:200]}"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert aircraft to dictionary for JSON serialization."""
        data = asdict(self)
        # Convert datetime objects to ISO strings
        data['last_seen'] = self.last_seen.isoformat()
        data['first_seen'] = self.first_seen.isoformat()
        return data
    
    def is_stale(self, timeout: int = 300) -> bool:
        """Check if aircraft data is stale (not seen recently)."""
        return (datetime.now() - self.last_seen).total_seconds() > timeout
    
    def get_display_name(self) -> str:
        """Get display name for aircraft (callsign or ICAO)."""
        if self.callsign and self.callsign.strip():
            return self.callsign.strip()
        return self.icao
    
    def has_position(self) -> bool:
        """Check if aircraft has valid position data."""
        return (self.latitude is not None and 
                self.longitude is not None and
                -90 <= self.latitude <= 90 and
                -180 <= self.longitude <= 180)
    
    def get_age_seconds(self) -> int:
        """Get age of aircraft data in seconds."""
        return int((datetime.now() - self.last_seen).total_seconds())
    
    def is_new_watchlist_detection(self) -> bool:
        """Check if this is a new watchlist aircraft detection."""
        return (self.on_watchlist and 
                self.watchlist_first_detected is not None and
                self.watchlist_last_alerted is None)
    
    def should_send_watchlist_alert(self, alert_interval: int = 300) -> bool:
        """Check if we should send a watchlist alert for this aircraft."""
        if not self.on_watchlist:
            return False
            
        # Always alert on first detection (when first_detected is set but never alerted)
        if self.watchlist_first_detected is not None and self.watchlist_last_alerted is None:
            return True
            
        # Alert if enough time has passed since last alert
        if self.watchlist_last_alerted is not None:
            time_since_last_alert = (datetime.now() - self.watchlist_last_alerted).total_seconds()
            return time_since_last_alert >= alert_interval
            
        return False
    
    def mark_watchlist_detected(self, watchlist_name: str = "") -> None:
        """Mark aircraft as detected on watchlist."""
        if self.watchlist_first_detected is None:
            self.watchlist_first_detected = datetime.now()
        self.watchlist_name = watchlist_name
    
    def mark_watchlist_alerted(self) -> None:
        """Mark that an alert was sent for this watchlist aircraft."""
        self.watchlist_last_alerted = datetime.now()
        self.watchlist_alert_count += 1
    
    def clear_watchlist_status(self) -> None:
        """Clear watchlist status when aircraft is removed from watchlist."""
        self.on_watchlist = False
        self.watchlist_first_detected = None
        self.watchlist_last_alerted = None
        self.watchlist_alert_count = 0
        self.watchlist_name = ""


class AircraftTracker:
    """Manages collection of tracked aircraft."""
    
    def __init__(self):
        self.aircraft: Dict[str, Aircraft] = {}
        self.watchlist_icaos: set = set()
        self.watchlist_entries: Dict[str, str] = {}  # icao -> name mapping
        
    def update_aircraft(self, icao: str, data: Dict[str, Any]) -> Aircraft:
        """Update or create aircraft from message data."""
        try:
            icao = icao.upper()
            
            if not validate_icao(icao):
                logger.warning(f"Invalid ICAO received: {icao}")
                return None
                
            # Create new aircraft if not exists
            if icao not in self.aircraft:
                aircraft = Aircraft(icao=icao)
                if icao in self.watchlist_icaos:
                    aircraft.on_watchlist = True
                    aircraft.mark_watchlist_detected(self.watchlist_entries.get(icao, ''))
                self.aircraft[icao] = aircraft
                logger.debug(f"New aircraft tracked: {icao}")
            else:
                aircraft = self.aircraft[icao]
            
            # Update with new data
            aircraft.update_from_message(data)
            
            return aircraft
            
        except Exception as e:
            logger.error(f"Error updating aircraft {icao}: {e}")
            return None
    
    def get_aircraft(self, icao: str) -> Optional[Aircraft]:
        """Get specific aircraft by ICAO."""
        return self.aircraft.get(icao.upper())
    
    def get_all_aircraft(self) -> Dict[str, Aircraft]:
        """Get all tracked aircraft."""
        return self.aircraft.copy()
    
    def get_aircraft_list(self) -> list:
        """Get list of aircraft dictionaries for JSON output."""
        return [aircraft.to_dict() for aircraft in self.aircraft.values()]
    
    def cleanup_stale(self, timeout: int = 300) -> int:
        """Remove stale aircraft and return count removed."""
        try:
            stale_icaos = []
            for icao, aircraft in self.aircraft.items():
                if aircraft.is_stale(timeout):
                    stale_icaos.append(icao)
            
            for icao in stale_icaos:
                del self.aircraft[icao]
                logger.debug(f"Removed stale aircraft: {icao}")
            
            if stale_icaos:
                logger.info(f"Cleaned up {len(stale_icaos)} stale aircraft")
                
            return len(stale_icaos)
            
        except Exception as e:
            logger.error(f"Error during aircraft cleanup: {e}")
            return 0
    
    def update_watchlist(self, watchlist_entries: list) -> None:
        """Update watchlist and mark aircraft accordingly."""
        try:
            # Build ICAO set and name mapping from watchlist entries
            self.watchlist_icaos = set()
            self.watchlist_entries = {}
            
            for entry in watchlist_entries:
                if hasattr(entry, 'icao'):
                    icao = entry.icao.upper()
                    name = getattr(entry, 'name', '')
                elif isinstance(entry, dict):
                    icao = entry.get('icao', '').upper()
                    name = entry.get('name', '')
                else:
                    continue
                    
                self.watchlist_icaos.add(icao)
                self.watchlist_entries[icao] = name
            
            # Update existing aircraft watchlist status
            for aircraft in self.aircraft.values():
                was_on_watchlist = aircraft.on_watchlist
                is_on_watchlist = aircraft.icao in self.watchlist_icaos
                
                if is_on_watchlist and not was_on_watchlist:
                    # Aircraft added to watchlist
                    aircraft.on_watchlist = True
                    aircraft.mark_watchlist_detected(self.watchlist_entries.get(aircraft.icao, ''))
                    logger.info(f"Aircraft {aircraft.icao} added to watchlist")
                elif not is_on_watchlist and was_on_watchlist:
                    # Aircraft removed from watchlist
                    aircraft.clear_watchlist_status()
                    logger.info(f"Aircraft {aircraft.icao} removed from watchlist")
                elif is_on_watchlist:
                    # Update name if changed
                    aircraft.watchlist_name = self.watchlist_entries.get(aircraft.icao, '')
                
            logger.info(f"Updated watchlist with {len(self.watchlist_icaos)} aircraft")
            
        except Exception as e:
            logger.error(f"Error updating watchlist: {e}")
    
    def is_watchlist_aircraft(self, icao: str) -> bool:
        """Check if aircraft is on watchlist."""
        return icao.upper() in self.watchlist_icaos
    
    def get_watchlist_aircraft(self) -> Dict[str, Aircraft]:
        """Get only aircraft that are on watchlist."""
        return {icao: aircraft for icao, aircraft in self.aircraft.items() 
                if aircraft.on_watchlist}
    
    def get_aircraft_count(self) -> int:
        """Get total number of tracked aircraft."""
        return len(self.aircraft)
    
    def get_aircraft_with_position(self) -> Dict[str, Aircraft]:
        """Get aircraft that have valid position data."""
        return {icao: aircraft for icao, aircraft in self.aircraft.items() 
                if aircraft.has_position()}
    
    def get_watchlist_aircraft_needing_alerts(self, alert_interval: int = 300) -> Dict[str, Aircraft]:
        """Get watchlist aircraft that need alerts sent."""
        return {icao: aircraft for icao, aircraft in self.aircraft.items() 
                if aircraft.should_send_watchlist_alert(alert_interval)}
    
    def get_new_watchlist_detections(self) -> Dict[str, Aircraft]:
        """Get aircraft that are newly detected on watchlist."""
        return {icao: aircraft for icao, aircraft in self.aircraft.items() 
                if aircraft.is_new_watchlist_detection()}
    
    def get_watchlist_statistics(self) -> Dict[str, Any]:
        """Get watchlist-specific statistics."""
        watchlist_aircraft = self.get_watchlist_aircraft()
        total_alerts_sent = sum(aircraft.watchlist_alert_count for aircraft in watchlist_aircraft.values())
        
        new_detections = len(self.get_new_watchlist_detections())
        need_alerts = len(self.get_watchlist_aircraft_needing_alerts())
        
        return {
            "watchlist_size": len(self.watchlist_icaos),
            "active_watchlist_aircraft": len(watchlist_aircraft),
            "new_detections": new_detections,
            "pending_alerts": need_alerts,
            "total_alerts_sent": total_alerts_sent
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get tracking statistics."""
        total_aircraft = len(self.aircraft)
        with_position = len(self.get_aircraft_with_position())
        on_watchlist = len(self.get_watchlist_aircraft())
        
        total_messages = sum(aircraft.message_count for aircraft in self.aircraft.values())
        
        return {
            "total_aircraft": total_aircraft,
            "aircraft_with_position": with_position,
            "watchlist_aircraft": on_watchlist,
            "total_messages": total_messages,
            "watchlist_size": len(self.watchlist_icaos)
        }
    
    def save_to_json(self, filename: str = "aircraft.json") -> bool:
        """Save aircraft data to JSON file with error handling."""
        try:
            data = {
                "timestamp": datetime.now().isoformat(),
                "aircraft": self.get_aircraft_list(),
                "statistics": self.get_statistics()
            }
            
            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)
                
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.AIRCRAFT_TRACKER,
                ErrorSeverity.MEDIUM,
                f"Error saving aircraft data to {filename}: {str(e)}",
                error_code="AIRCRAFT_SAVE_ERROR",
                details=f"Aircraft count: {len(self.aircraft)}"
            )
            return False