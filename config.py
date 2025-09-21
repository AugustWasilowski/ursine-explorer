"""
Configuration management and validation for Ursine Capture system.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Any, Optional, Callable
from utils import (validate_frequency, validate_gain, validate_coordinates, validate_icao,
                  error_handler, ErrorSeverity, ComponentType, handle_exception, safe_execute)


logger = logging.getLogger(__name__)


@dataclass
class RadioConfig:
    """Radio configuration settings."""
    frequency: int = 1090100000
    lna_gain: int = 40
    vga_gain: int = 20
    enable_amp: bool = True


@dataclass
class MeshtasticConfig:
    """Meshtastic device configuration."""
    port: str = "/dev/ttyUSB0"
    baud: int = 115200
    channel: int = 2


@dataclass
class ReceiverConfig:
    """ADS-B receiver configuration."""
    dump1090_path: str = "/usr/bin/dump1090-fa"
    reference_lat: float = 41.9481
    reference_lon: float = -87.6555
    alert_interval: int = 300


@dataclass
class WatchlistEntry:
    """Single watchlist entry."""
    icao: str
    name: str = ""


class ConfigValidator:
    """Configuration validation utilities."""
    
    @staticmethod
    def validate_radio_settings(settings: Dict[str, Any]) -> bool:
        """Validate radio configuration settings."""
        try:
            freq = settings.get('frequency', 1090100000)
            lna_gain = settings.get('lna_gain', 40)
            vga_gain = settings.get('vga_gain', 20)
            
            if not validate_frequency(freq):
                logger.error(f"Invalid frequency: {freq}")
                return False
                
            if not validate_gain(lna_gain):
                logger.error(f"Invalid LNA gain: {lna_gain}")
                return False
                
            if not validate_gain(vga_gain):
                logger.error(f"Invalid VGA gain: {vga_gain}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Radio settings validation error: {e}")
            return False
    
    @staticmethod
    def validate_meshtastic_settings(settings: Dict[str, Any]) -> bool:
        """Validate Meshtastic configuration settings."""
        try:
            port = settings.get('port', '/dev/ttyUSB0')
            baud = settings.get('baud', 115200)
            channel = settings.get('channel', 2)
            
            if not isinstance(port, str) or not port:
                logger.error(f"Invalid Meshtastic port: {port}")
                return False
                
            if not isinstance(baud, int) or baud <= 0:
                logger.error(f"Invalid Meshtastic baud rate: {baud}")
                return False
                
            if not isinstance(channel, int) or channel < 0 or channel > 7:
                logger.error(f"Invalid Meshtastic channel: {channel}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Meshtastic settings validation error: {e}")
            return False
    
    @staticmethod
    def validate_receiver_settings(settings: Dict[str, Any]) -> bool:
        """Validate receiver configuration settings."""
        try:
            dump1090_path = settings.get('dump1090_path', '/usr/bin/dump1090-fa')
            ref_lat = settings.get('reference_lat', 41.9481)
            ref_lon = settings.get('reference_lon', -87.6555)
            alert_interval = settings.get('alert_interval', 300)
            
            if not isinstance(dump1090_path, str) or not dump1090_path:
                logger.error(f"Invalid dump1090 path: {dump1090_path}")
                return False
                
            if not validate_coordinates(ref_lat, ref_lon):
                logger.error(f"Invalid reference coordinates: {ref_lat}, {ref_lon}")
                return False
                
            if not isinstance(alert_interval, int) or alert_interval < 0:
                logger.error(f"Invalid alert interval: {alert_interval}")
                return False
                
            return True
        except Exception as e:
            logger.error(f"Receiver settings validation error: {e}")
            return False
    
    @staticmethod
    def validate_watchlist(watchlist: List[Dict[str, Any]]) -> bool:
        """Validate watchlist entries."""
        try:
            for entry in watchlist:
                icao = entry.get('icao', '')
                name = entry.get('name', '')
                
                if not validate_icao(icao):
                    logger.error(f"Invalid ICAO in watchlist: {icao}")
                    return False
                    
                if not isinstance(name, str):
                    logger.error(f"Invalid name in watchlist entry: {name}")
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Watchlist validation error: {e}")
            return False


class Config:
    """Main configuration management class with hot-reload capability."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self.validator = ConfigValidator()
        self._config_data = {}
        self._last_modified = 0
        self._reload_callbacks = []
        self._watch_thread = None
        self._stop_watching = False
        self._lock = threading.Lock()
        
    def get_defaults(self) -> Dict[str, Any]:
        """Get default configuration values."""
        return {
            "radio": asdict(RadioConfig()),
            "meshtastic": asdict(MeshtasticConfig()),
            "receiver": asdict(ReceiverConfig()),
            "watchlist": []
        }
    
    def load(self) -> Dict[str, Any]:
        """Load configuration from file, creating defaults if needed."""
        try:
            if not self.config_path.exists():
                error_handler.handle_error(
                    ComponentType.CONFIG,
                    ErrorSeverity.LOW,
                    f"Config file {self.config_path} not found, creating defaults",
                    error_code="CONFIG_FILE_MISSING"
                )
                defaults = self.get_defaults()
                self.save(defaults)
                return defaults
            
            # Update last modified time
            self._last_modified = os.path.getmtime(self.config_path)
                
            with open(self.config_path, 'r') as f:
                config_data = json.load(f)
                
            # Merge with defaults to ensure all keys exist
            defaults = self.get_defaults()
            for section in defaults:
                if section not in config_data:
                    config_data[section] = defaults[section]
                elif isinstance(defaults[section], dict):
                    for key in defaults[section]:
                        if key not in config_data[section]:
                            config_data[section][key] = defaults[section][key]
            
            self._config_data = config_data
            return config_data
            
        except json.JSONDecodeError as e:
            error_handler.handle_error(
                ComponentType.CONFIG,
                ErrorSeverity.HIGH,
                f"Invalid JSON in config file: {str(e)}",
                error_code="CONFIG_INVALID_JSON",
                details=f"File: {self.config_path}"
            )
            logger.info("Using default configuration")
            return self.get_defaults()
        except Exception as e:
            error_handler.handle_error(
                ComponentType.CONFIG,
                ErrorSeverity.HIGH,
                f"Error loading config: {str(e)}",
                error_code="CONFIG_LOAD_ERROR",
                details=f"File: {self.config_path}"
            )
            logger.info("Using default configuration")
            return self.get_defaults()
    
    def save(self, config: Dict[str, Any]) -> None:
        """Save configuration to file with error handling."""
        try:
            # Validate before saving
            if not self.validate(config):
                error_handler.handle_error(
                    ComponentType.CONFIG,
                    ErrorSeverity.HIGH,
                    "Cannot save invalid configuration",
                    error_code="CONFIG_VALIDATION_FAILED"
                )
                raise ValueError("Configuration validation failed")
            
            with open(self.config_path, 'w') as f:
                json.dump(config, f, indent=2)
            self._config_data = config
            logger.info(f"Configuration saved to {self.config_path}")
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.CONFIG,
                ErrorSeverity.HIGH,
                f"Error saving config: {str(e)}",
                error_code="CONFIG_SAVE_ERROR",
                details=f"File: {self.config_path}"
            )
            raise
    
    def validate(self, config: Dict[str, Any]) -> bool:
        """Validate entire configuration."""
        try:
            # Validate each section
            if 'radio' in config:
                if not self.validator.validate_radio_settings(config['radio']):
                    return False
                    
            if 'meshtastic' in config:
                if not self.validator.validate_meshtastic_settings(config['meshtastic']):
                    return False
                    
            if 'receiver' in config:
                if not self.validator.validate_receiver_settings(config['receiver']):
                    return False
                    
            if 'watchlist' in config:
                if not self.validator.validate_watchlist(config['watchlist']):
                    return False
                    
            return True
        except Exception as e:
            logger.error(f"Configuration validation error: {e}")
            return False
    
    def get_radio_config(self) -> RadioConfig:
        """Get radio configuration as dataclass."""
        config = self.load()
        radio_data = config.get('radio', {})
        return RadioConfig(**radio_data)
    
    def get_meshtastic_config(self) -> MeshtasticConfig:
        """Get Meshtastic configuration as dataclass."""
        config = self.load()
        meshtastic_data = config.get('meshtastic', {})
        return MeshtasticConfig(**meshtastic_data)
    
    def get_receiver_config(self) -> ReceiverConfig:
        """Get receiver configuration as dataclass."""
        config = self.load()
        receiver_data = config.get('receiver', {})
        return ReceiverConfig(**receiver_data)
    
    def get_watchlist(self) -> List[WatchlistEntry]:
        """Get watchlist as list of dataclasses."""
        config = self.load()
        watchlist_data = config.get('watchlist', [])
        return [WatchlistEntry(**entry) for entry in watchlist_data]
    
    def add_to_watchlist(self, icao: str, name: str = "") -> bool:
        """Add aircraft to watchlist."""
        try:
            if not validate_icao(icao):
                logger.error(f"Invalid ICAO for watchlist: {icao}")
                return False
                
            config = self.load()
            watchlist = config.get('watchlist', [])
            
            # Check if already exists
            for entry in watchlist:
                if entry.get('icao', '').upper() == icao.upper():
                    logger.info(f"Aircraft {icao} already in watchlist")
                    return True
                    
            # Add new entry
            watchlist.append({"icao": icao.upper(), "name": name})
            config['watchlist'] = watchlist
            
            if self.validate(config):
                self.save(config)
                logger.info(f"Added {icao} to watchlist")
                return True
            else:
                logger.error("Failed to validate config after adding to watchlist")
                return False
                
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            return False
    
    def remove_from_watchlist(self, icao: str) -> bool:
        """Remove aircraft from watchlist."""
        try:
            config = self.load()
            watchlist = config.get('watchlist', [])
            
            original_length = len(watchlist)
            watchlist = [entry for entry in watchlist 
                        if entry.get('icao', '').upper() != icao.upper()]
            
            if len(watchlist) < original_length:
                config['watchlist'] = watchlist
                self.save(config)
                logger.info(f"Removed {icao} from watchlist")
                return True
            else:
                logger.info(f"Aircraft {icao} not found in watchlist")
                return False
                
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            return False
    
    def register_reload_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback to be called when configuration is reloaded."""
        with self._lock:
            self._reload_callbacks.append(callback)
    
    def unregister_reload_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Unregister a reload callback."""
        with self._lock:
            if callback in self._reload_callbacks:
                self._reload_callbacks.remove(callback)
    
    def start_watching(self) -> None:
        """Start watching the configuration file for changes."""
        if self._watch_thread is not None and self._watch_thread.is_alive():
            logger.warning("Configuration file watching is already active")
            return
            
        self._stop_watching = False
        self._watch_thread = threading.Thread(target=self._watch_config_file, daemon=True)
        self._watch_thread.start()
        logger.info(f"Started watching configuration file: {self.config_path}")
    
    def stop_watching(self) -> None:
        """Stop watching the configuration file for changes."""
        self._stop_watching = True
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=1.0)
            self._watch_thread = None
        logger.info("Stopped watching configuration file")
    
    def _watch_config_file(self) -> None:
        """Internal method to watch configuration file for changes."""
        while not self._stop_watching:
            try:
                if self.config_path.exists():
                    current_modified = os.path.getmtime(self.config_path)
                    
                    if current_modified > self._last_modified:
                        logger.info("Configuration file changed, reloading...")
                        self._last_modified = current_modified
                        
                        # Reload configuration
                        new_config = self.load()
                        
                        # Validate new configuration
                        if self.validate(new_config):
                            logger.info("Configuration reloaded successfully")
                            
                            # Call registered callbacks
                            with self._lock:
                                for callback in self._reload_callbacks:
                                    try:
                                        callback(new_config)
                                    except Exception as e:
                                        logger.error(f"Error in reload callback: {e}")
                        else:
                            logger.error("Invalid configuration detected, keeping previous config")
                            
                time.sleep(1.0)  # Check every second
                
            except Exception as e:
                logger.error(f"Error watching config file: {e}")
                time.sleep(5.0)  # Wait longer on error
    
    def reload(self) -> bool:
        """Manually reload configuration from file."""
        try:
            if not self.config_path.exists():
                logger.warning(f"Config file {self.config_path} does not exist")
                return False
                
            new_config = self.load()
            
            if self.validate(new_config):
                logger.info("Configuration reloaded manually")
                
                # Call registered callbacks
                with self._lock:
                    for callback in self._reload_callbacks:
                        try:
                            callback(new_config)
                        except Exception as e:
                            logger.error(f"Error in reload callback: {e}")
                return True
            else:
                logger.error("Invalid configuration, reload failed")
                return False
                
        except Exception as e:
            logger.error(f"Error reloading configuration: {e}")
            return False
    
    def update_section(self, section: str, updates: Dict[str, Any]) -> bool:
        """Update a specific section of the configuration."""
        try:
            config = self.load()
            
            if section not in config:
                logger.error(f"Configuration section '{section}' does not exist")
                return False
            
            # Update the section
            config[section].update(updates)
            
            # Validate the updated configuration
            if not self.validate(config):
                logger.error(f"Invalid configuration after updating section '{section}'")
                return False
            
            # Save the updated configuration
            self.save(config)
            logger.info(f"Updated configuration section '{section}'")
            return True
            
        except Exception as e:
            logger.error(f"Error updating configuration section '{section}': {e}")
            return False
    
    def get_section(self, section: str) -> Optional[Dict[str, Any]]:
        """Get a specific section of the configuration."""
        try:
            config = self.load()
            return config.get(section)
        except Exception as e:
            logger.error(f"Error getting configuration section '{section}': {e}")
            return None
    
    def __del__(self):
        """Cleanup when Config object is destroyed."""
        self.stop_watching()