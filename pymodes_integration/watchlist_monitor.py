"""
Enhanced Watchlist Monitor Module

Provides improved watchlist monitoring with better pattern matching,
multiple watchlist types, and real-time updates without restart.
Enhanced with support for the new MeshtasticManager integration.
"""

import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, Set, List, Optional, Union, Callable
from enum import Enum
from dataclasses import dataclass, field
import threading
import json
import os

from .aircraft import EnhancedAircraft

logger = logging.getLogger(__name__)


class WatchlistType(Enum):
    """Types of watchlist entries"""
    ICAO = "icao"
    CALLSIGN = "callsign"
    REGISTRATION = "registration"
    PATTERN = "pattern"
    RANGE = "range"


@dataclass
class WatchlistEntry:
    """Individual watchlist entry with metadata"""
    value: str
    entry_type: WatchlistType
    description: Optional[str] = None
    priority: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    enabled: bool = True
    created: datetime = field(default_factory=datetime.now)
    last_matched: Optional[datetime] = None
    match_count: int = 0
    
    def matches(self, aircraft: EnhancedAircraft) -> bool:
        """
        Check if this watchlist entry matches the given aircraft
        
        Args:
            aircraft: Aircraft to check against
            
        Returns:
            True if aircraft matches this entry
        """
        if not self.enabled:
            return False
        
        value_upper = self.value.upper()
        
        if self.entry_type == WatchlistType.ICAO:
            return aircraft.icao.upper() == value_upper
        
        elif self.entry_type == WatchlistType.CALLSIGN:
            if not aircraft.callsign:
                return False
            callsign_clean = aircraft.callsign.strip().upper()
            return callsign_clean == value_upper
        
        elif self.entry_type == WatchlistType.REGISTRATION:
            # Registration matching would need additional aircraft data
            # For now, check if it matches callsign as fallback
            if aircraft.callsign:
                callsign_clean = aircraft.callsign.strip().upper()
                return callsign_clean == value_upper
            return False
        
        elif self.entry_type == WatchlistType.PATTERN:
            # Pattern matching for callsigns and ICAO codes
            try:
                pattern = re.compile(self.value, re.IGNORECASE)
                
                # Check ICAO
                if pattern.search(aircraft.icao):
                    return True
                
                # Check callsign
                if aircraft.callsign and pattern.search(aircraft.callsign.strip()):
                    return True
                
            except re.error as e:
                logger.warning(f"Invalid regex pattern '{self.value}': {e}")
                return False
        
        elif self.entry_type == WatchlistType.RANGE:
            # Range matching for ICAO codes (e.g., "A00000-A0FFFF")
            if "-" in self.value:
                try:
                    start_hex, end_hex = self.value.split("-", 1)
                    start_int = int(start_hex.strip(), 16)
                    end_int = int(end_hex.strip(), 16)
                    aircraft_int = int(aircraft.icao, 16)
                    
                    return start_int <= aircraft_int <= end_int
                    
                except ValueError as e:
                    logger.warning(f"Invalid range format '{self.value}': {e}")
                    return False
        
        return False
    
    def record_match(self) -> None:
        """Record that this entry matched an aircraft"""
        self.last_matched = datetime.now()
        self.match_count += 1


class WatchlistMonitor:
    """
    Enhanced watchlist monitoring with improved pattern matching
    and support for multiple watchlist types.
    
    Now supports integration with enhanced MeshtasticManager for
    channel-based alert routing and delivery confirmation.
    """
    
    def __init__(self, config_path: Optional[str] = None, meshtastic_manager=None):
        """
        Initialize watchlist monitor
        
        Args:
            config_path: Path to watchlist configuration file
            meshtastic_manager: Optional MeshtasticManager instance for alerts
        """
        self.entries: Dict[str, WatchlistEntry] = {}
        self.config_path = config_path
        self.last_config_check = datetime.now()
        self.config_check_interval = 30  # Check for config changes every 30 seconds
        
        # Enhanced Meshtastic integration
        self.meshtastic_manager = meshtastic_manager
        self._channel_mapping: Dict[int, str] = {}  # Priority to channel mapping
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Statistics
        self.stats = {
            'total_checks': 0,
            'total_matches': 0,
            'matches_by_type': {wt.value: 0 for wt in WatchlistType},
            'matches_by_priority': {1: 0, 2: 0, 3: 0, 4: 0},
            'last_match_time': None,
            'config_reloads': 0,
            'meshtastic_alerts_sent': 0,
            'meshtastic_alerts_failed': 0,
            'alerts_by_channel': {}
        }
        
        # Callbacks for match events
        self.match_callbacks: List[Callable[[EnhancedAircraft, WatchlistEntry], None]] = []
        
        # Load initial configuration
        if config_path and os.path.exists(config_path):
            self.load_watchlist_config(config_path)
        
        # Set up default channel mapping
        self._setup_default_channel_mapping()
        
        logger.info(f"WatchlistMonitor initialized with {len(self.entries)} entries")
    
    def set_meshtastic_manager(self, meshtastic_manager) -> None:
        """
        Set or update the MeshtasticManager instance
        
        Args:
            meshtastic_manager: MeshtasticManager instance for sending alerts
        """
        self.meshtastic_manager = meshtastic_manager
        logger.info("MeshtasticManager updated for watchlist monitor")
    
    def _setup_default_channel_mapping(self) -> None:
        """Set up default priority to channel mapping"""
        self._channel_mapping = {
            1: "LongFast",      # Low priority -> default channel
            2: "LongFast",      # Medium priority -> default channel  
            3: "SecureAlerts",  # High priority -> secure channel if available
            4: "SecureAlerts"   # Critical priority -> secure channel if available
        }
    
    def configure_channel_mapping(self, priority_to_channel: Dict[int, str]) -> None:
        """
        Configure mapping from watchlist entry priority to Meshtastic channel
        
        Args:
            priority_to_channel: Dictionary mapping priority levels (1-4) to channel names
        """
        with self._lock:
            self._channel_mapping.update(priority_to_channel)
            logger.info(f"Updated channel mapping: {self._channel_mapping}")
    
    def get_channel_for_priority(self, priority: int) -> str:
        """
        Get the appropriate channel for a given priority level
        
        Args:
            priority: Priority level (1-4)
            
        Returns:
            Channel name to use for this priority
        """
        return self._channel_mapping.get(priority, "LongFast")
    
    def add_entry(self, entry_id: str, entry: WatchlistEntry) -> None:
        """
        Add a watchlist entry
        
        Args:
            entry_id: Unique identifier for the entry
            entry: WatchlistEntry object
        """
        with self._lock:
            self.entries[entry_id] = entry
            logger.info(f"Added watchlist entry: {entry_id} ({entry.entry_type.value}: {entry.value})")
    
    def remove_entry(self, entry_id: str) -> bool:
        """
        Remove a watchlist entry
        
        Args:
            entry_id: Identifier of entry to remove
            
        Returns:
            True if entry was removed, False if not found
        """
        with self._lock:
            if entry_id in self.entries:
                del self.entries[entry_id]
                logger.info(f"Removed watchlist entry: {entry_id}")
                return True
            return False
    
    def update_entry(self, entry_id: str, **kwargs) -> bool:
        """
        Update an existing watchlist entry
        
        Args:
            entry_id: Identifier of entry to update
            **kwargs: Fields to update
            
        Returns:
            True if entry was updated, False if not found
        """
        with self._lock:
            if entry_id not in self.entries:
                return False
            
            entry = self.entries[entry_id]
            
            # Update allowed fields
            for field_name, value in kwargs.items():
                if hasattr(entry, field_name):
                    setattr(entry, field_name, value)
                    logger.debug(f"Updated {entry_id}.{field_name} = {value}")
            
            return True
    
    def enable_entry(self, entry_id: str) -> bool:
        """Enable a watchlist entry"""
        return self.update_entry(entry_id, enabled=True)
    
    def disable_entry(self, entry_id: str) -> bool:
        """Disable a watchlist entry"""
        return self.update_entry(entry_id, enabled=False)
    
    def check_aircraft(self, aircraft: EnhancedAircraft) -> List[WatchlistEntry]:
        """
        Check if aircraft matches any watchlist entries
        
        Args:
            aircraft: Aircraft to check
            
        Returns:
            List of matching watchlist entries
        """
        matches = []
        
        with self._lock:
            self.stats['total_checks'] += 1
            
            for entry_id, entry in self.entries.items():
                if entry.matches(aircraft):
                    matches.append(entry)
                    entry.record_match()
                    
                    # Update statistics
                    self.stats['total_matches'] += 1
                    self.stats['matches_by_type'][entry.entry_type.value] += 1
                    self.stats['matches_by_priority'][entry.priority] += 1
                    self.stats['last_match_time'] = datetime.now().isoformat()
                    
                    # Mark aircraft as watchlist
                    aircraft.is_watchlist = True
                    
                    # Send enhanced Meshtastic alert if manager is available
                    if self.meshtastic_manager:
                        try:
                            alert_type = self._determine_alert_type(entry, aircraft)
                            success = self._send_enhanced_meshtastic_alert(aircraft, entry, alert_type)
                            
                            if success:
                                self.stats['meshtastic_alerts_sent'] += 1
                                channel = self.get_channel_for_priority(entry.priority)
                                self.stats['alerts_by_channel'][channel] = self.stats['alerts_by_channel'].get(channel, 0) + 1
                            else:
                                self.stats['meshtastic_alerts_failed'] += 1
                                
                        except Exception as e:
                            logger.error(f"Error sending enhanced Meshtastic alert: {e}")
                            self.stats['meshtastic_alerts_failed'] += 1
                    
                    # Call registered callbacks
                    for callback in self.match_callbacks:
                        try:
                            callback(aircraft, entry)
                        except Exception as e:
                            logger.error(f"Error in watchlist callback: {e}")
                    
                    logger.info(f"Watchlist match: {aircraft.icao} matched {entry_id} "
                              f"({entry.entry_type.value}: {entry.value}, priority: {entry.priority})")
        
        return matches
    
    def _determine_alert_type(self, entry: WatchlistEntry, aircraft: EnhancedAircraft) -> str:
        """
        Determine the alert type based on watchlist entry and aircraft data
        
        Args:
            entry: Matched watchlist entry
            aircraft: Aircraft that matched
            
        Returns:
            Alert type string
        """
        # Determine alert type based on priority and entry type
        if entry.priority >= 4:
            return "critical_watchlist"
        elif entry.priority >= 3:
            return "high_priority_watchlist"
        elif entry.entry_type == WatchlistType.PATTERN:
            return "pattern_watchlist"
        elif entry.entry_type == WatchlistType.RANGE:
            return "range_watchlist"
        else:
            return "watchlist"
    
    def _send_enhanced_meshtastic_alert(self, aircraft: EnhancedAircraft, entry: WatchlistEntry, alert_type: str) -> bool:
        """
        Send alert using enhanced MeshtasticManager
        
        Args:
            aircraft: Aircraft triggering the alert
            entry: Matched watchlist entry
            alert_type: Type of alert to send
            
        Returns:
            True if alert sent successfully, False otherwise
        """
        if not self.meshtastic_manager:
            logger.warning("No MeshtasticManager available for sending alerts")
            return False
        
        try:
            # Create enhanced aircraft object with additional metadata
            enhanced_aircraft = self._prepare_aircraft_for_alert(aircraft, entry)
            
            # Send alert through MeshtasticManager
            success = self.meshtastic_manager.send_alert(enhanced_aircraft, alert_type)
            
            if success:
                logger.info(f"Enhanced Meshtastic alert sent for {aircraft.icao} "
                          f"(type: {alert_type}, priority: {entry.priority})")
            else:
                logger.warning(f"Failed to send enhanced Meshtastic alert for {aircraft.icao}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error in enhanced Meshtastic alert sending: {e}")
            return False
    
    def _prepare_aircraft_for_alert(self, aircraft: EnhancedAircraft, entry: WatchlistEntry) -> EnhancedAircraft:
        """
        Prepare aircraft object with additional metadata for alert
        
        Args:
            aircraft: Original aircraft object
            entry: Matched watchlist entry
            
        Returns:
            Aircraft object with enhanced metadata
        """
        # Create a copy to avoid modifying the original
        alert_aircraft = aircraft
        
        # Add watchlist-specific metadata
        if not hasattr(alert_aircraft, 'watchlist_metadata'):
            alert_aircraft.watchlist_metadata = {}
        
        alert_aircraft.watchlist_metadata.update({
            'matched_entry_id': entry.value,
            'matched_entry_type': entry.entry_type.value,
            'matched_entry_description': entry.description,
            'priority': entry.priority,
            'match_timestamp': datetime.now().isoformat(),
            'match_count': entry.match_count
        })
        
        return alert_aircraft
    
    def send_test_alert(self, test_message: str = "Watchlist test alert") -> bool:
        """
        Send a test alert through the enhanced Meshtastic system
        
        Args:
            test_message: Message to send for testing
            
        Returns:
            True if test alert sent successfully
        """
        if not self.meshtastic_manager:
            logger.error("No MeshtasticManager available for test alert")
            return False
        
        try:
            # Create a dummy aircraft for testing
            from .aircraft import EnhancedAircraft
            now = datetime.now()
            test_aircraft = EnhancedAircraft(
                icao="TEST01",
                first_seen=now,
                last_seen=now,
                callsign="TEST",
                latitude=0.0,
                longitude=0.0,
                altitude_baro=10000,
                ground_speed=250,
                track_angle=90
            )
            
            # Add test metadata
            test_aircraft.watchlist_metadata = {
                'test_alert': True,
                'message': test_message,
                'timestamp': datetime.now().isoformat()
            }
            
            success = self.meshtastic_manager.send_alert(test_aircraft, "test")
            
            if success:
                logger.info("Test alert sent successfully")
                self.stats['meshtastic_alerts_sent'] += 1
            else:
                logger.warning("Test alert failed")
                self.stats['meshtastic_alerts_failed'] += 1
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending test alert: {e}")
            self.stats['meshtastic_alerts_failed'] += 1
            return False
    
    def add_match_callback(self, callback: Callable[[EnhancedAircraft, WatchlistEntry], None]) -> None:
        """
        Add a callback function to be called when aircraft match watchlist entries
        
        Args:
            callback: Function that takes (aircraft, entry) parameters
        """
        self.match_callbacks.append(callback)
        logger.debug(f"Added watchlist match callback: {callback.__name__}")
    
    def remove_match_callback(self, callback: Callable[[EnhancedAircraft, WatchlistEntry], None]) -> bool:
        """
        Remove a match callback
        
        Args:
            callback: Callback function to remove
            
        Returns:
            True if callback was removed, False if not found
        """
        try:
            self.match_callbacks.remove(callback)
            logger.debug(f"Removed watchlist match callback: {callback.__name__}")
            return True
        except ValueError:
            return False
    
    def load_watchlist_config(self, config_path: str) -> bool:
        """
        Load watchlist configuration from file
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            with self._lock:
                # Clear existing entries
                self.entries.clear()
                
                # Load entries from config
                entries_data = config_data.get('watchlist_entries', [])
                
                for entry_data in entries_data:
                    entry_id = entry_data.get('id')
                    if not entry_id:
                        continue
                    
                    try:
                        entry_type = WatchlistType(entry_data.get('type', 'icao'))
                        
                        entry = WatchlistEntry(
                            value=entry_data['value'],
                            entry_type=entry_type,
                            description=entry_data.get('description'),
                            priority=entry_data.get('priority', 1),
                            enabled=entry_data.get('enabled', True)
                        )
                        
                        self.entries[entry_id] = entry
                        
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Invalid watchlist entry {entry_id}: {e}")
                        continue
                
                # Load legacy ICAO codes for backward compatibility
                legacy_icao_codes = config_data.get('target_icao_codes', [])
                for i, icao_code in enumerate(legacy_icao_codes):
                    entry_id = f"legacy_icao_{i}"
                    if entry_id not in self.entries:
                        entry = WatchlistEntry(
                            value=icao_code,
                            entry_type=WatchlistType.ICAO,
                            description="Legacy ICAO code",
                            priority=2
                        )
                        self.entries[entry_id] = entry
                
                self.config_path = config_path
                self.last_config_check = datetime.now()
                self.stats['config_reloads'] += 1
                
                logger.info(f"Loaded {len(self.entries)} watchlist entries from {config_path}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to load watchlist config from {config_path}: {e}")
            return False
    
    def save_watchlist_config(self, config_path: Optional[str] = None) -> bool:
        """
        Save current watchlist configuration to file
        
        Args:
            config_path: Path to save configuration (uses self.config_path if None)
            
        Returns:
            True if saved successfully, False otherwise
        """
        save_path = config_path or self.config_path
        if not save_path:
            logger.error("No config path specified for saving")
            return False
        
        try:
            with self._lock:
                # Convert entries to serializable format
                entries_data = []
                
                for entry_id, entry in self.entries.items():
                    # Skip legacy entries when saving
                    if entry_id.startswith('legacy_'):
                        continue
                    
                    entry_data = {
                        'id': entry_id,
                        'value': entry.value,
                        'type': entry.entry_type.value,
                        'description': entry.description,
                        'priority': entry.priority,
                        'enabled': entry.enabled,
                        'created': entry.created.isoformat(),
                        'match_count': entry.match_count
                    }
                    
                    if entry.last_matched:
                        entry_data['last_matched'] = entry.last_matched.isoformat()
                    
                    entries_data.append(entry_data)
                
                config_data = {
                    'watchlist_entries': entries_data,
                    'last_updated': datetime.now().isoformat(),
                    'version': '1.0'
                }
            
            # Write to file
            with open(save_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            logger.info(f"Saved {len(entries_data)} watchlist entries to {save_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save watchlist config to {save_path}: {e}")
            return False
    
    def check_config_updates(self) -> bool:
        """
        Check if configuration file has been updated and reload if necessary
        
        Returns:
            True if config was reloaded, False otherwise
        """
        if not self.config_path or not os.path.exists(self.config_path):
            return False
        
        # Check if enough time has passed since last check
        if (datetime.now() - self.last_config_check).total_seconds() < self.config_check_interval:
            return False
        
        try:
            # Check file modification time
            file_mtime = datetime.fromtimestamp(os.path.getmtime(self.config_path))
            
            if file_mtime > self.last_config_check:
                logger.info("Watchlist config file updated, reloading...")
                return self.load_watchlist_config(self.config_path)
            
            self.last_config_check = datetime.now()
            return False
            
        except Exception as e:
            logger.error(f"Error checking config file updates: {e}")
            return False
    
    def get_entries(self, enabled_only: bool = True) -> Dict[str, WatchlistEntry]:
        """
        Get all watchlist entries
        
        Args:
            enabled_only: If True, return only enabled entries
            
        Returns:
            Dictionary of watchlist entries
        """
        with self._lock:
            if enabled_only:
                return {
                    entry_id: entry 
                    for entry_id, entry in self.entries.items() 
                    if entry.enabled
                }
            else:
                return self.entries.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get watchlist monitoring statistics"""
        with self._lock:
            stats = self.stats.copy()
            stats.update({
                'total_entries': len(self.entries),
                'enabled_entries': len([e for e in self.entries.values() if e.enabled]),
                'entries_by_type': {
                    wt.value: len([e for e in self.entries.values() if e.entry_type == wt])
                    for wt in WatchlistType
                },
                'entries_by_priority': {
                    priority: len([e for e in self.entries.values() if e.priority == priority])
                    for priority in [1, 2, 3, 4]
                },
                'meshtastic_manager_available': self.meshtastic_manager is not None,
                'channel_mapping': self._channel_mapping.copy(),
                'meshtastic_connection_status': self._get_meshtastic_status()
            })
            return stats
    
    def _get_meshtastic_status(self) -> Dict[str, Any]:
        """Get current Meshtastic connection status"""
        if not self.meshtastic_manager:
            return {'available': False, 'error': 'No MeshtasticManager configured'}
        
        try:
            return self.meshtastic_manager.get_connection_status()
        except Exception as e:
            return {'available': False, 'error': str(e)}
    
    def reset_statistics(self) -> None:
        """Reset all statistics counters"""
        with self._lock:
            self.stats = {
                'total_checks': 0,
                'total_matches': 0,
                'matches_by_type': {wt.value: 0 for wt in WatchlistType},
                'matches_by_priority': {1: 0, 2: 0, 3: 0, 4: 0},
                'last_match_time': None,
                'config_reloads': 0,
                'meshtastic_alerts_sent': 0,
                'meshtastic_alerts_failed': 0,
                'alerts_by_channel': {}
            }
            logger.info("Watchlist monitor statistics reset")
    
    def create_legacy_compatible_watchlist(self) -> Set[str]:
        """
        Create a legacy-compatible watchlist set for backward compatibility
        
        Returns:
            Set of ICAO codes and callsigns for legacy systems
        """
        legacy_set = set()
        
        with self._lock:
            for entry in self.entries.values():
                if not entry.enabled:
                    continue
                
                if entry.entry_type in [WatchlistType.ICAO, WatchlistType.CALLSIGN]:
                    legacy_set.add(entry.value.upper())
        
        return legacy_set