"""
pyModeS Decoder Integration

This module provides a wrapper around pyModeS decoding functionality,
integrating it with the UrsineExplorer system while maintaining compatibility.
"""

import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime, timedelta
import time

try:
    import pyModeS as pms
    PYMODES_AVAILABLE = True
except ImportError:
    PYMODES_AVAILABLE = False
    pms = None

from .config import PyModeSConfig
from .aircraft import EnhancedAircraft

logger = logging.getLogger(__name__)


class PyModeSDecode:
    """
    Wrapper around pyModeS decode functionality for UrsineExplorer integration
    
    This class provides a bridge between pyModeS library and the existing
    UrsineExplorer architecture, handling message decoding, aircraft tracking,
    and data validation.
    """
    
    def __init__(self, config: Optional[PyModeSConfig] = None):
        """Initialize pyModeS decoder"""
        if not PYMODES_AVAILABLE:
            raise ImportError("pyModeS library is not available. Install with: pip install pyModeS")
        
        self.config = config or PyModeSConfig()
        self.aircraft: Dict[str, EnhancedAircraft] = {}
        
        # Statistics tracking
        self.stats = {
            'messages_processed': 0,
            'messages_decoded': 0,
            'messages_failed': 0,
            'aircraft_created': 0,
            'aircraft_updated': 0,
            'last_stats_time': datetime.now(),
            'decode_rate': 0.0,
            'error_rate': 0.0
        }
        
        # CPR position tracking for global decoding
        self.cpr_cache: Dict[str, Dict] = {}
        
        logger.info("pyModeS decoder initialized")
        if self.config.reference_latitude and self.config.reference_longitude:
            logger.info(f"Reference position: {self.config.reference_latitude:.4f}, {self.config.reference_longitude:.4f}")
    
    def is_valid_message(self, message: str) -> bool:
        """
        Validate ADS-B message format and CRC
        
        Args:
            message: Raw ADS-B message in hex format
            
        Returns:
            True if message is valid, False otherwise
        """
        try:
            # Basic format validation
            if not message or len(message) not in [14, 28]:  # 7 or 14 bytes
                return False
            
            # Check if it's valid hex
            try:
                int(message, 16)
            except ValueError:
                return False
            
            # CRC validation if enabled
            if self.config.crc_validation:
                try:
                    # Use pyModeS CRC check
                    return pms.crc(message) == 0
                except Exception:
                    return False
            
            return True
            
        except Exception as e:
            if self.config.log_decode_errors:
                logger.debug(f"Message validation error: {e}")
            return False
    
    def decode_message(self, message: str, timestamp: float) -> Optional[Dict[str, Any]]:
        """
        Decode a single ADS-B message using pyModeS
        
        Args:
            message: Raw ADS-B message in hex format
            timestamp: Message timestamp
            
        Returns:
            Decoded message data or None if decoding fails
        """
        try:
            if not self.is_valid_message(message):
                return None
            
            # Extract ICAO address
            icao = pms.icao(message)
            if not icao:
                return None
            
            # Get message type
            df = pms.df(message)
            tc = None
            
            # Decode based on message type
            decoded_data = {
                'icao': icao.upper(),
                'timestamp': timestamp,
                'raw_message': message,
                'df': df,
                'message_type': 'unknown'
            }
            
            # Handle ADS-B messages (DF17, DF18)
            if df in [17, 18]:
                tc = pms.adsb.typecode(message)
                decoded_data['tc'] = tc
                
                # Aircraft identification (TC 1-4)
                if 1 <= tc <= 4:
                    decoded_data['message_type'] = 'identification'
                    try:
                        callsign = pms.adsb.callsign(message)
                        if callsign:
                            decoded_data['callsign'] = callsign.strip()
                    except Exception:
                        pass
                
                # Surface position (TC 5-8)
                elif 5 <= tc <= 8:
                    decoded_data['message_type'] = 'surface_position'
                    self._decode_position_message(message, decoded_data)
                
                # Airborne position (TC 9-18)
                elif 9 <= tc <= 18:
                    decoded_data['message_type'] = 'airborne_position'
                    self._decode_position_message(message, decoded_data)
                    
                    # Decode altitude
                    try:
                        altitude = pms.adsb.altitude(message)
                        if altitude is not None:
                            decoded_data['altitude'] = altitude
                    except Exception:
                        pass
                
                # Airborne velocity (TC 19)
                elif tc == 19:
                    decoded_data['message_type'] = 'velocity'
                    self._decode_velocity_message(message, decoded_data)
            
            # Handle other message types (DF4, DF5, DF20, DF21)
            elif df in [4, 5, 20, 21]:
                decoded_data['message_type'] = 'surveillance'
                try:
                    altitude = pms.common.altcode(message)
                    if altitude is not None:
                        decoded_data['altitude'] = altitude
                except Exception:
                    pass
            
            return decoded_data
            
        except Exception as e:
            if self.config.log_decode_errors:
                logger.debug(f"Message decode error for {message}: {e}")
            return None
    
    def _decode_position_message(self, message: str, decoded_data: Dict[str, Any]):
        """Decode position information from ADS-B message"""
        try:
            icao = decoded_data['icao']
            
            # Get CPR format and encoded position
            oe = pms.adsb.oe_flag(message)
            decoded_data['cpr_format'] = 'odd' if oe else 'even'
            
            # Store CPR data for global decoding
            if icao not in self.cpr_cache:
                self.cpr_cache[icao] = {}
            
            cpr_data = {
                'message': message,
                'timestamp': decoded_data['timestamp'],
                'lat_cpr': pms.adsb.cprlat(message),
                'lon_cpr': pms.adsb.cprlon(message)
            }
            
            self.cpr_cache[icao][oe] = cpr_data
            
            # Try to decode position
            position = self._calculate_position(icao, decoded_data['timestamp'])
            if position:
                decoded_data.update(position)
            
        except Exception as e:
            if self.config.log_decode_errors:
                logger.debug(f"Position decode error: {e}")
    
    def _decode_velocity_message(self, message: str, decoded_data: Dict[str, Any]):
        """Decode velocity information from ADS-B message"""
        try:
            # Ground speed and track
            velocity_data = pms.adsb.velocity(message)
            if velocity_data:
                speed, track, vr, tag = velocity_data
                if speed is not None:
                    decoded_data['ground_speed'] = speed
                if track is not None:
                    decoded_data['track'] = track
                if vr is not None:
                    decoded_data['vertical_rate'] = vr
            
            # True airspeed if available
            try:
                tas = pms.adsb.tas(message)
                if tas is not None:
                    decoded_data['true_airspeed'] = tas
            except Exception:
                pass
            
            # Indicated airspeed if available
            try:
                ias = pms.adsb.ias(message)
                if ias is not None:
                    decoded_data['indicated_airspeed'] = ias
            except Exception:
                pass
            
            # Mach number if available
            try:
                mach = pms.adsb.mach(message)
                if mach is not None:
                    decoded_data['mach_number'] = mach
            except Exception:
                pass
            
        except Exception as e:
            if self.config.log_decode_errors:
                logger.debug(f"Velocity decode error: {e}")
    
    def _calculate_position(self, icao: str, timestamp: float) -> Optional[Dict[str, float]]:
        """Calculate aircraft position using CPR decoding"""
        try:
            if icao not in self.cpr_cache:
                return None
            
            cpr_data = self.cpr_cache[icao]
            
            # Check if we have both even and odd messages for global decoding
            if self.config.use_global_cpr and 0 in cpr_data and 1 in cpr_data:
                even_msg = cpr_data[0]['message']
                odd_msg = cpr_data[1]['message']
                
                # Check message age
                even_age = timestamp - cpr_data[0]['timestamp']
                odd_age = timestamp - cpr_data[1]['timestamp']
                
                if even_age <= self.config.position_timeout_sec and odd_age <= self.config.position_timeout_sec:
                    try:
                        lat, lon = pms.adsb.position(even_msg, odd_msg, 0, 1)
                        if lat is not None and lon is not None:
                            return {'latitude': lat, 'longitude': lon}
                    except Exception:
                        pass
            
            # Try local decoding if reference position is available
            if (self.config.use_local_cpr and 
                self.config.reference_latitude is not None and 
                self.config.reference_longitude is not None):
                
                # Use the most recent message
                recent_format = None
                recent_msg = None
                recent_time = 0
                
                for fmt, data in cpr_data.items():
                    if data['timestamp'] > recent_time:
                        recent_time = data['timestamp']
                        recent_format = fmt
                        recent_msg = data['message']
                
                if recent_msg and (timestamp - recent_time) <= self.config.position_timeout_sec:
                    try:
                        lat, lon = pms.adsb.position_with_ref(
                            recent_msg,
                            self.config.reference_latitude,
                            self.config.reference_longitude
                        )
                        if lat is not None and lon is not None:
                            return {'latitude': lat, 'longitude': lon}
                    except Exception:
                        pass
            
            return None
            
        except Exception as e:
            if self.config.log_decode_errors:
                logger.debug(f"Position calculation error for {icao}: {e}")
            return None
    
    def process_messages(self, messages: List[Tuple[str, float]]) -> Dict[str, EnhancedAircraft]:
        """
        Process a batch of ADS-B messages
        
        Args:
            messages: List of (message, timestamp) tuples
            
        Returns:
            Dictionary of updated aircraft data keyed by ICAO
        """
        updated_aircraft = {}
        
        for message, timestamp in messages:
            self.stats['messages_processed'] += 1
            
            # Decode message
            decoded = self.decode_message(message, timestamp)
            if decoded:
                self.stats['messages_decoded'] += 1
                icao = decoded['icao']
                
                # Update or create aircraft
                if icao in self.aircraft:
                    self.aircraft[icao].update_from_pymodes(decoded)
                    self.stats['aircraft_updated'] += 1
                else:
                    self.aircraft[icao] = EnhancedAircraft.from_pymodes_data(decoded)
                    self.stats['aircraft_created'] += 1
                
                updated_aircraft[icao] = self.aircraft[icao]
                
                if self.config.log_aircraft_updates:
                    logger.debug(f"Updated aircraft {icao}: {decoded.get('message_type', 'unknown')}")
            else:
                self.stats['messages_failed'] += 1
        
        # Update statistics
        self._update_statistics()
        
        return updated_aircraft
    
    def get_aircraft_data(self) -> Dict[str, EnhancedAircraft]:
        """Get current aircraft data"""
        return self.aircraft.copy()
    
    def clear_old_aircraft(self, timeout_seconds: Optional[int] = None) -> int:
        """
        Remove aircraft that haven't been seen recently
        
        Args:
            timeout_seconds: Override default timeout
            
        Returns:
            Number of aircraft removed
        """
        timeout = timeout_seconds or self.config.aircraft_timeout_sec
        cutoff_time = datetime.now() - timedelta(seconds=timeout)
        
        to_remove = [
            icao for icao, aircraft in self.aircraft.items()
            if aircraft.last_seen < cutoff_time
        ]
        
        for icao in to_remove:
            del self.aircraft[icao]
            # Also clean up CPR cache
            if icao in self.cpr_cache:
                del self.cpr_cache[icao]
        
        if to_remove and self.config.log_aircraft_updates:
            logger.info(f"Removed {len(to_remove)} old aircraft")
        
        return len(to_remove)
    
    def _update_statistics(self):
        """Update processing statistics"""
        now = datetime.now()
        time_diff = (now - self.stats['last_stats_time']).total_seconds()
        
        if time_diff >= self.config.stats_interval_sec:
            # Calculate rates
            total_messages = self.stats['messages_processed']
            if total_messages > 0:
                self.stats['decode_rate'] = self.stats['messages_decoded'] / total_messages
                self.stats['error_rate'] = self.stats['messages_failed'] / total_messages
            
            if self.config.log_message_stats:
                logger.info(
                    f"pyModeS Stats: {total_messages} processed, "
                    f"{self.stats['messages_decoded']} decoded "
                    f"({self.stats['decode_rate']:.1%}), "
                    f"{len(self.aircraft)} aircraft tracked"
                )
            
            self.stats['last_stats_time'] = now
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get current processing statistics"""
        return {
            **self.stats,
            'aircraft_count': len(self.aircraft),
            'cpr_cache_size': len(self.cpr_cache)
        }