"""
Configuration management for pyModeS integration.

This module handles loading, validation, and migration of configuration files
for the enhanced ADS-B receiver system with pyModeS integration.
"""

import json
import logging
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field
from pathlib import Path
import copy

from .meshtastic_config import (
    MeshtasticConfig,
    ChannelConfig,
    MQTTConfig,
    create_meshtastic_config_from_dict
)


@dataclass
class ReferencePosition:
    """Reference position for CPR decoding."""
    latitude: Optional[float] = None
    longitude: Optional[float] = None


@dataclass
class CPRSettings:
    """CPR (Compact Position Reporting) decoder settings."""
    global_position_timeout: int = 10
    local_position_range_nm: int = 180
    surface_position_timeout: int = 25


@dataclass
class MessageValidation:
    """Message validation settings."""
    enable_crc_check: bool = True
    enable_format_validation: bool = True
    enable_range_validation: bool = True
    max_message_age_sec: int = 60


@dataclass
class DecoderSettings:
    """pyModeS decoder configuration."""
    supported_message_types: List[str] = field(default_factory=lambda: ["DF4", "DF5", "DF17", "DF18", "DF20", "DF21"])
    enable_enhanced_decoding: bool = True
    decode_comm_b: bool = True
    decode_bds: bool = True


@dataclass
class PyModeSConfig:
    """pyModeS integration configuration."""
    enabled: bool = True
    reference_position: ReferencePosition = field(default_factory=ReferencePosition)
    cpr_settings: CPRSettings = field(default_factory=CPRSettings)
    message_validation: MessageValidation = field(default_factory=MessageValidation)
    decoder_settings: DecoderSettings = field(default_factory=DecoderSettings)


@dataclass
class MessageSource:
    """Configuration for a message source."""
    name: str
    type: str  # dump1090, network, rtlsdr
    enabled: bool = True
    host: str = "localhost"
    port: int = 30005
    format: str = "beast"  # beast, raw, json, skysense
    reconnect_interval_sec: int = 5
    max_reconnect_attempts: int = 10
    buffer_size: int = 8192
    # Additional source-specific settings
    extra_settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertThrottling:
    """Alert throttling configuration."""
    enabled: bool = True
    min_interval_sec: int = 300
    max_alerts_per_hour: int = 10
    escalation_enabled: bool = False


@dataclass
class WatchlistConfig:
    """Watchlist monitoring configuration."""
    enabled: bool = True
    sources: List[str] = field(default_factory=lambda: ["target_icao_codes"])
    check_icao: bool = True
    check_callsign: bool = True
    case_sensitive: bool = False
    pattern_matching: bool = False
    alert_throttling: AlertThrottling = field(default_factory=AlertThrottling)


@dataclass
class AircraftTracking:
    """Aircraft tracking configuration."""
    aircraft_timeout_sec: int = 300
    position_timeout_sec: int = 60
    cleanup_interval_sec: int = 30
    max_aircraft_count: int = 10000
    enable_data_validation: bool = True
    conflict_resolution: str = "newest_wins"  # newest_wins, oldest_wins, merge
    track_surface_vehicles: bool = True
    minimum_message_count: int = 2


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    enable_message_stats: bool = True
    enable_aircraft_events: bool = True
    enable_connection_events: bool = True
    enable_decode_errors: bool = True
    stats_interval_sec: int = 60
    log_file: str = "adsb_receiver.log"
    max_log_size_mb: int = 100
    backup_count: int = 5


@dataclass
class PerformanceConfig:
    """Performance tuning configuration."""
    message_batch_size: int = 100
    processing_interval_ms: int = 100
    memory_limit_mb: int = 512
    enable_profiling: bool = False
    gc_interval_sec: int = 300





@dataclass
class ADSBConfig:
    """Complete ADS-B receiver configuration."""
    # Legacy settings (maintained for backward compatibility)
    dump1090_host: str = "localhost"
    dump1090_port: int = 30005
    receiver_control_port: int = 8081
    frequency: int = 1090100000
    lna_gain: int = 40
    vga_gain: int = 20
    enable_hackrf_amp: bool = True
    target_icao_codes: List[str] = field(default_factory=list)
    meshtastic_port: str = "/dev/ttyUSB0"
    meshtastic_baud: int = 115200
    log_alerts: bool = True
    alert_log_file: str = "alerts.log"
    alert_interval_sec: int = 300
    dump1090_path: str = "/usr/local/bin/dump1090"
    start_dump1090: bool = True
    watchdog_timeout_sec: int = 60
    poll_interval_sec: int = 1
    
    # Enhanced pyModeS settings
    pymodes: PyModeSConfig = field(default_factory=PyModeSConfig)
    message_sources: List[MessageSource] = field(default_factory=list)
    aircraft_tracking: AircraftTracking = field(default_factory=AircraftTracking)
    watchlist: WatchlistConfig = field(default_factory=WatchlistConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    
    # Enhanced Meshtastic settings
    meshtastic: Optional[MeshtasticConfig] = None


class ConfigurationError(Exception):
    """Configuration-related error."""
    pass


class ConfigManager:
    """Manages configuration loading, validation, and migration."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path) if isinstance(config_path, str) else config_path
        self.logger = logging.getLogger(__name__)
        self._config: Optional[ADSBConfig] = None
    
    def load_config(self) -> ADSBConfig:
        """Load configuration from file with validation and migration."""
        try:
            if not self.config_path.exists():
                self.logger.warning(f"Config file {self.config_path} not found, creating default")
                self._config = self._create_default_config()
                self.save_config()
                return self._config
            
            with open(self.config_path, 'r') as f:
                raw_config = json.load(f)
            
            # Check if migration is needed
            if self._needs_migration(raw_config):
                self.logger.info("Migrating configuration to new format")
                raw_config = self._migrate_config(raw_config)
                # Save migrated config
                with open(self.config_path, 'w') as f:
                    json.dump(raw_config, f, indent=4)
            
            # Validate and create config object
            self._config = self._parse_config(raw_config)
            self._validate_config(self._config)
            
            return self._config
            
        except Exception as e:
            raise ConfigurationError(f"Failed to load configuration: {e}")
    
    def save_config(self) -> None:
        """Save current configuration to file."""
        if self._config is None:
            raise ConfigurationError("No configuration loaded")
        
        try:
            config_dict = self._config_to_dict(self._config)
            with open(self.config_path, 'w') as f:
                json.dump(config_dict, f, indent=4)
        except Exception as e:
            raise ConfigurationError(f"Failed to save configuration: {e}")
    
    def get_config(self) -> ADSBConfig:
        """Get current configuration, loading if necessary."""
        if self._config is None:
            return self.load_config()
        return self._config
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """Update configuration with new values."""
        if self._config is None:
            self.load_config()
        
        # Apply updates (simplified - would need more sophisticated merging)
        config_dict = self._config_to_dict(self._config)
        self._deep_update(config_dict, updates)
        
        # Reload from updated dict
        self._config = self._parse_config(config_dict)
        self._validate_config(self._config)
    
    def _needs_migration(self, config: Dict[str, Any]) -> bool:
        """Check if configuration needs migration to new format."""
        # Check for presence of new sections
        return ("pymodes" not in config or 
                "message_sources" not in config or 
                "meshtastic" not in config)
    
    def _migrate_config(self, old_config: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate old configuration format to new format."""
        # Start with old config
        new_config = copy.deepcopy(old_config)
        
        # Add pyModeS section if missing
        if "pymodes" not in new_config:
            new_config["pymodes"] = {
                "enabled": True,
                "reference_position": {
                    "latitude": None,
                    "longitude": None
                },
                "cpr_settings": {
                    "global_position_timeout": 10,
                    "local_position_range_nm": 180,
                    "surface_position_timeout": 25
                },
                "message_validation": {
                    "enable_crc_check": True,
                    "enable_format_validation": True,
                    "enable_range_validation": True,
                    "max_message_age_sec": 60
                },
                "decoder_settings": {
                    "supported_message_types": ["DF4", "DF5", "DF17", "DF18", "DF20", "DF21"],
                    "enable_enhanced_decoding": True,
                    "decode_comm_b": True,
                    "decode_bds": True
                }
            }
        
        # Migrate dump1090 settings to message sources
        if "message_sources" not in new_config:
            new_config["message_sources"] = [
                {
                    "name": "dump1090_primary",
                    "type": "dump1090",
                    "enabled": True,
                    "host": old_config.get("dump1090_host", "localhost"),
                    "port": old_config.get("dump1090_port", 30005),
                    "format": "beast",
                    "reconnect_interval_sec": 5,
                    "max_reconnect_attempts": 10,
                    "buffer_size": 8192
                }
            ]
        
        # Add other new sections with defaults
        if "aircraft_tracking" not in new_config:
            new_config["aircraft_tracking"] = {
                "aircraft_timeout_sec": 300,
                "position_timeout_sec": 60,
                "cleanup_interval_sec": 30,
                "max_aircraft_count": 10000,
                "enable_data_validation": True,
                "conflict_resolution": "newest_wins",
                "track_surface_vehicles": True,
                "minimum_message_count": 2
            }
        
        if "watchlist" not in new_config:
            new_config["watchlist"] = {
                "enabled": True,
                "sources": ["target_icao_codes"],
                "check_icao": True,
                "check_callsign": True,
                "case_sensitive": False,
                "pattern_matching": False,
                "alert_throttling": {
                    "enabled": True,
                    "min_interval_sec": old_config.get("alert_interval_sec", 300),
                    "max_alerts_per_hour": 10,
                    "escalation_enabled": False
                }
            }
        
        if "logging" not in new_config:
            new_config["logging"] = {
                "level": "INFO",
                "enable_message_stats": True,
                "enable_aircraft_events": True,
                "enable_connection_events": True,
                "enable_decode_errors": True,
                "stats_interval_sec": 60,
                "log_file": "adsb_receiver.log",
                "max_log_size_mb": 100,
                "backup_count": 5
            }
        
        if "performance" not in new_config:
            new_config["performance"] = {
                "message_batch_size": 100,
                "processing_interval_ms": old_config.get("poll_interval_sec", 1) * 1000,
                "memory_limit_mb": 512,
                "enable_profiling": False,
                "gc_interval_sec": 300
            }
        
        # Migrate Meshtastic settings to enhanced format
        if "meshtastic" not in new_config:
            new_config["meshtastic"] = {
                # Preserve legacy settings for backward compatibility
                "meshtastic_port": old_config.get("meshtastic_port", "/dev/ttyUSB0"),
                "meshtastic_baud": old_config.get("meshtastic_baud", 115200),
                
                # Default enhanced settings
                "channels": [
                    {
                        "name": "LongFast",
                        "psk": None,
                        "channel_number": 0,
                        "uplink_enabled": True,
                        "downlink_enabled": True
                    }
                ],
                "default_channel": "LongFast",
                "mqtt": None,
                "connection_mode": "serial",  # Start with serial only for backward compatibility
                "failover_enabled": True,
                "connection_timeout": 10,
                "retry_interval": 30,
                "message_format": "standard",
                "include_position": True,
                "include_timestamp": True,
                "max_message_length": 200,
                "auto_detect_device": True,
                "enable_encryption": True,
                "log_all_messages": False,
                "health_check_interval": 60
            }
        
        return new_config
    
    def _parse_config(self, config_dict: Dict[str, Any]) -> ADSBConfig:
        """Parse configuration dictionary into ADSBConfig object."""
        # This is a simplified version - in practice, you'd want more robust parsing
        config = ADSBConfig()
        
        # Legacy fields
        for field_name in ['dump1090_host', 'dump1090_port', 'receiver_control_port', 
                          'frequency', 'lna_gain', 'vga_gain', 'enable_hackrf_amp',
                          'target_icao_codes', 'meshtastic_port', 'meshtastic_baud',
                          'log_alerts', 'alert_log_file', 'alert_interval_sec',
                          'dump1090_path', 'start_dump1090', 'watchdog_timeout_sec', 'poll_interval_sec']:
            if field_name in config_dict:
                setattr(config, field_name, config_dict[field_name])
        
        # Parse pyModeS config
        if 'pymodes' in config_dict:
            pymodes_dict = config_dict['pymodes']
            config.pymodes = PyModeSConfig(
                enabled=pymodes_dict.get('enabled', True),
                reference_position=ReferencePosition(**pymodes_dict.get('reference_position', {})),
                cpr_settings=CPRSettings(**pymodes_dict.get('cpr_settings', {})),
                message_validation=MessageValidation(**pymodes_dict.get('message_validation', {})),
                decoder_settings=DecoderSettings(**pymodes_dict.get('decoder_settings', {}))
            )
        
        # Parse message sources
        if 'message_sources' in config_dict:
            config.message_sources = [
                MessageSource(**source_dict) for source_dict in config_dict['message_sources']
            ]
        
        # Parse other sections
        if 'aircraft_tracking' in config_dict:
            config.aircraft_tracking = AircraftTracking(**config_dict['aircraft_tracking'])
        
        if 'watchlist' in config_dict:
            watchlist_dict = config_dict['watchlist']
            config.watchlist = WatchlistConfig(
                **{k: v for k, v in watchlist_dict.items() if k != 'alert_throttling'},
                alert_throttling=AlertThrottling(**watchlist_dict.get('alert_throttling', {}))
            )
        
        if 'logging' in config_dict:
            config.logging = LoggingConfig(**config_dict['logging'])
        
        if 'performance' in config_dict:
            config.performance = PerformanceConfig(**config_dict['performance'])
        
        # Parse enhanced Meshtastic config
        if 'meshtastic' in config_dict:
            config.meshtastic = create_meshtastic_config_from_dict(config_dict['meshtastic'])
        else:
            # Create default Meshtastic config if not present
            config.meshtastic = create_meshtastic_config_from_dict({
                "channels": [
                    {
                        "name": "LongFast",
                        "psk": None,
                        "channel_number": 0,
                        "uplink_enabled": True,
                        "downlink_enabled": True
                    }
                ],
                "default_channel": "LongFast",
                "connection_mode": "serial"
            })
        
        return config
    
    def _validate_config(self, config: ADSBConfig) -> None:
        """Validate configuration for consistency and correctness."""
        errors = []
        
        # Validate pyModeS settings
        if config.pymodes.enabled:
            if config.pymodes.cpr_settings.global_position_timeout <= 0:
                errors.append("CPR global position timeout must be positive")
            
            if config.pymodes.cpr_settings.local_position_range_nm <= 0:
                errors.append("CPR local position range must be positive")
        
        # Validate message sources
        if not config.message_sources:
            errors.append("At least one message source must be configured")
        
        for source in config.message_sources:
            if source.enabled:
                if source.port <= 0 or source.port > 65535:
                    errors.append(f"Invalid port {source.port} for source {source.name}")
                
                if source.type not in ['dump1090', 'network', 'rtlsdr']:
                    errors.append(f"Unknown source type {source.type} for source {source.name}")
        
        # Validate aircraft tracking
        if config.aircraft_tracking.aircraft_timeout_sec <= 0:
            errors.append("Aircraft timeout must be positive")
        
        if config.aircraft_tracking.max_aircraft_count <= 0:
            errors.append("Maximum aircraft count must be positive")
        
        # Validate performance settings
        if config.performance.message_batch_size <= 0:
            errors.append("Message batch size must be positive")
        
        if config.performance.memory_limit_mb <= 0:
            errors.append("Memory limit must be positive")
        
        # Meshtastic validation is handled by the MeshtasticConfig class itself
        
        if errors:
            raise ConfigurationError("Configuration validation failed: " + "; ".join(errors))
    
    def _create_default_config(self) -> ADSBConfig:
        """Create default configuration."""
        config = ADSBConfig()
        
        # Add default message source
        config.message_sources = [
            MessageSource(
                name="dump1090_primary",
                type="dump1090",
                enabled=True,
                host="localhost",
                port=30005,
                format="beast"
            )
        ]
        
        # Add default Meshtastic configuration
        config.meshtastic = create_meshtastic_config_from_dict({
            "channels": [
                {
                    "name": "LongFast",
                    "psk": None,
                    "channel_number": 0,
                    "uplink_enabled": True,
                    "downlink_enabled": True
                }
            ],
            "default_channel": "LongFast",
            "connection_mode": "serial"  # Start with serial only for safety
        })
        
        return config
    
    def _config_to_dict(self, config: ADSBConfig) -> Dict[str, Any]:
        """Convert ADSBConfig object to dictionary for JSON serialization."""
        # This is a simplified version - would need proper dataclass serialization
        result = {}
        
        # Legacy fields
        for field_name in ['dump1090_host', 'dump1090_port', 'receiver_control_port', 
                          'frequency', 'lna_gain', 'vga_gain', 'enable_hackrf_amp',
                          'target_icao_codes', 'meshtastic_port', 'meshtastic_baud',
                          'log_alerts', 'alert_log_file', 'alert_interval_sec',
                          'dump1090_path', 'start_dump1090', 'watchdog_timeout_sec', 'poll_interval_sec']:
            result[field_name] = getattr(config, field_name)
        
        # Convert complex objects to dicts (simplified)
        result['pymodes'] = {
            'enabled': config.pymodes.enabled,
            'reference_position': {
                'latitude': config.pymodes.reference_position.latitude,
                'longitude': config.pymodes.reference_position.longitude
            },
            'cpr_settings': {
                'global_position_timeout': config.pymodes.cpr_settings.global_position_timeout,
                'local_position_range_nm': config.pymodes.cpr_settings.local_position_range_nm,
                'surface_position_timeout': config.pymodes.cpr_settings.surface_position_timeout
            },
            'message_validation': {
                'enable_crc_check': config.pymodes.message_validation.enable_crc_check,
                'enable_format_validation': config.pymodes.message_validation.enable_format_validation,
                'enable_range_validation': config.pymodes.message_validation.enable_range_validation,
                'max_message_age_sec': config.pymodes.message_validation.max_message_age_sec
            },
            'decoder_settings': {
                'supported_message_types': config.pymodes.decoder_settings.supported_message_types,
                'enable_enhanced_decoding': config.pymodes.decoder_settings.enable_enhanced_decoding,
                'decode_comm_b': config.pymodes.decoder_settings.decode_comm_b,
                'decode_bds': config.pymodes.decoder_settings.decode_bds
            }
        }
        
        # Message sources
        result['message_sources'] = []
        for source in config.message_sources:
            source_dict = {
                'name': source.name,
                'type': source.type,
                'enabled': source.enabled,
                'host': source.host,
                'port': source.port,
                'format': source.format,
                'reconnect_interval_sec': source.reconnect_interval_sec,
                'max_reconnect_attempts': source.max_reconnect_attempts,
                'buffer_size': source.buffer_size
            }
            source_dict.update(source.extra_settings)
            result['message_sources'].append(source_dict)
        
        # Other sections (simplified)
        result['aircraft_tracking'] = {
            'aircraft_timeout_sec': config.aircraft_tracking.aircraft_timeout_sec,
            'position_timeout_sec': config.aircraft_tracking.position_timeout_sec,
            'cleanup_interval_sec': config.aircraft_tracking.cleanup_interval_sec,
            'max_aircraft_count': config.aircraft_tracking.max_aircraft_count,
            'enable_data_validation': config.aircraft_tracking.enable_data_validation,
            'conflict_resolution': config.aircraft_tracking.conflict_resolution,
            'track_surface_vehicles': config.aircraft_tracking.track_surface_vehicles,
            'minimum_message_count': config.aircraft_tracking.minimum_message_count
        }
        
        result['watchlist'] = {
            'enabled': config.watchlist.enabled,
            'sources': config.watchlist.sources,
            'check_icao': config.watchlist.check_icao,
            'check_callsign': config.watchlist.check_callsign,
            'case_sensitive': config.watchlist.case_sensitive,
            'pattern_matching': config.watchlist.pattern_matching,
            'alert_throttling': {
                'enabled': config.watchlist.alert_throttling.enabled,
                'min_interval_sec': config.watchlist.alert_throttling.min_interval_sec,
                'max_alerts_per_hour': config.watchlist.alert_throttling.max_alerts_per_hour,
                'escalation_enabled': config.watchlist.alert_throttling.escalation_enabled
            }
        }
        
        result['logging'] = {
            'level': config.logging.level,
            'enable_message_stats': config.logging.enable_message_stats,
            'enable_aircraft_events': config.logging.enable_aircraft_events,
            'enable_connection_events': config.logging.enable_connection_events,
            'enable_decode_errors': config.logging.enable_decode_errors,
            'stats_interval_sec': config.logging.stats_interval_sec,
            'log_file': config.logging.log_file,
            'max_log_size_mb': config.logging.max_log_size_mb,
            'backup_count': config.logging.backup_count
        }
        
        result['performance'] = {
            'message_batch_size': config.performance.message_batch_size,
            'processing_interval_ms': config.performance.processing_interval_ms,
            'memory_limit_mb': config.performance.memory_limit_mb,
            'enable_profiling': config.performance.enable_profiling,
            'gc_interval_sec': config.performance.gc_interval_sec
        }
        
        # Enhanced Meshtastic configuration
        result['meshtastic'] = {
            'meshtastic_port': config.meshtastic.meshtastic_port,
            'meshtastic_baud': config.meshtastic.meshtastic_baud,
            'channels': [
                {
                    'name': channel.name,
                    'psk': channel.psk,
                    'channel_number': channel.channel_number,
                    'uplink_enabled': channel.uplink_enabled,
                    'downlink_enabled': channel.downlink_enabled
                }
                for channel in config.meshtastic.channels
            ],
            'default_channel': config.meshtastic.default_channel,
            'mqtt': {
                'broker_url': config.meshtastic.mqtt.broker_url,
                'port': config.meshtastic.mqtt.port,
                'username': config.meshtastic.mqtt.username,
                'password': config.meshtastic.mqtt.password,
                'use_tls': config.meshtastic.mqtt.use_tls,
                'client_id': config.meshtastic.mqtt.client_id,
                'topic_prefix': config.meshtastic.mqtt.topic_prefix,
                'qos': config.meshtastic.mqtt.qos,
                'keepalive': config.meshtastic.mqtt.keepalive
            } if config.meshtastic.mqtt is not None else None,
            'connection_mode': config.meshtastic.connection_mode,
            'failover_enabled': config.meshtastic.failover_enabled,
            'connection_timeout': config.meshtastic.connection_timeout,
            'retry_interval': config.meshtastic.retry_interval,
            'message_format': config.meshtastic.message_format,
            'include_position': config.meshtastic.include_position,
            'include_timestamp': config.meshtastic.include_timestamp,
            'max_message_length': config.meshtastic.max_message_length,
            'auto_detect_device': config.meshtastic.auto_detect_device,
            'enable_encryption': config.meshtastic.enable_encryption,
            'log_all_messages': config.meshtastic.log_all_messages,
            'health_check_interval': config.meshtastic.health_check_interval
        }
        
        return result
    
    def _deep_update(self, base_dict: Dict[str, Any], update_dict: Dict[str, Any]) -> None:
        """Deep update dictionary with another dictionary."""
        for key, value in update_dict.items():
            if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                self._deep_update(base_dict[key], value)
            else:
                base_dict[key] = value


# Global config manager instance
config_manager = ConfigManager()


def get_config() -> ADSBConfig:
    """Get the current configuration."""
    return config_manager.get_config()


def reload_config() -> ADSBConfig:
    """Reload configuration from file."""
    return config_manager.load_config()


def save_config() -> None:
    """Save current configuration to file."""
    config_manager.save_config()


def update_config(updates: Dict[str, Any]) -> None:
    """Update configuration with new values."""
    config_manager.update_config(updates)