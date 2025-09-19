"""
Configuration management for pyModeS integration

Handles configuration loading, validation, and default settings for the
pyModeS integration layer.
"""

import json
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PyModeSConfig:
    """Configuration class for pyModeS integration"""
    
    # Message processing settings
    crc_validation: bool = True
    message_timeout_sec: int = 300
    position_timeout_sec: int = 60
    
    # CPR position calculation settings
    reference_latitude: Optional[float] = None
    reference_longitude: Optional[float] = None
    use_global_cpr: bool = True
    use_local_cpr: bool = True
    
    # Message source settings
    max_sources: int = 5
    reconnect_interval_sec: int = 30
    connection_timeout_sec: int = 10
    
    # Aircraft tracking settings
    aircraft_timeout_sec: int = 300
    max_aircraft: int = 10000
    cleanup_interval_sec: int = 60
    
    # Logging and debugging
    log_decode_errors: bool = True
    log_aircraft_updates: bool = False
    log_message_stats: bool = True
    stats_interval_sec: int = 60
    
    # Performance settings
    batch_size: int = 100
    processing_threads: int = 1
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'PyModeSConfig':
        """Create configuration from dictionary"""
        # Extract pyModeS-specific settings
        pymodes_config = config_dict.get('pymodes', {})
        
        # Map legacy settings to new structure
        config_data = {
            'crc_validation': pymodes_config.get('crc_validation', True),
            'message_timeout_sec': config_dict.get('watchdog_timeout_sec', 300),
            'position_timeout_sec': pymodes_config.get('position_timeout_sec', 60),
            'reference_latitude': pymodes_config.get('reference_latitude'),
            'reference_longitude': pymodes_config.get('reference_longitude'),
            'use_global_cpr': pymodes_config.get('use_global_cpr', True),
            'use_local_cpr': pymodes_config.get('use_local_cpr', True),
            'max_sources': pymodes_config.get('max_sources', 5),
            'reconnect_interval_sec': pymodes_config.get('reconnect_interval_sec', 30),
            'connection_timeout_sec': pymodes_config.get('connection_timeout_sec', 10),
            'aircraft_timeout_sec': config_dict.get('watchdog_timeout_sec', 300),
            'max_aircraft': pymodes_config.get('max_aircraft', 10000),
            'cleanup_interval_sec': pymodes_config.get('cleanup_interval_sec', 60),
            'log_decode_errors': pymodes_config.get('log_decode_errors', True),
            'log_aircraft_updates': pymodes_config.get('log_aircraft_updates', False),
            'log_message_stats': pymodes_config.get('log_message_stats', True),
            'stats_interval_sec': pymodes_config.get('stats_interval_sec', 60),
            'batch_size': pymodes_config.get('batch_size', 100),
            'processing_threads': pymodes_config.get('processing_threads', 1),
        }
        
        return cls(**config_data)
    
    @classmethod
    def from_file(cls, config_path: str) -> 'PyModeSConfig':
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config_dict = json.load(f)
            return cls.from_dict(config_dict)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}, using defaults")
            return cls()
        except Exception as e:
            logger.error(f"Error loading config: {e}, using defaults")
            return cls()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'pymodes': {
                'crc_validation': self.crc_validation,
                'message_timeout_sec': self.message_timeout_sec,
                'position_timeout_sec': self.position_timeout_sec,
                'reference_latitude': self.reference_latitude,
                'reference_longitude': self.reference_longitude,
                'use_global_cpr': self.use_global_cpr,
                'use_local_cpr': self.use_local_cpr,
                'max_sources': self.max_sources,
                'reconnect_interval_sec': self.reconnect_interval_sec,
                'connection_timeout_sec': self.connection_timeout_sec,
                'aircraft_timeout_sec': self.aircraft_timeout_sec,
                'max_aircraft': self.max_aircraft,
                'cleanup_interval_sec': self.cleanup_interval_sec,
                'log_decode_errors': self.log_decode_errors,
                'log_aircraft_updates': self.log_aircraft_updates,
                'log_message_stats': self.log_message_stats,
                'stats_interval_sec': self.stats_interval_sec,
                'batch_size': self.batch_size,
                'processing_threads': self.processing_threads,
            }
        }
    
    def validate(self) -> bool:
        """Validate configuration settings"""
        try:
            # Validate numeric ranges
            if self.message_timeout_sec <= 0:
                raise ValueError("message_timeout_sec must be positive")
            
            if self.position_timeout_sec <= 0:
                raise ValueError("position_timeout_sec must be positive")
            
            if self.max_sources <= 0:
                raise ValueError("max_sources must be positive")
            
            if self.aircraft_timeout_sec <= 0:
                raise ValueError("aircraft_timeout_sec must be positive")
            
            if self.max_aircraft <= 0:
                raise ValueError("max_aircraft must be positive")
            
            if self.batch_size <= 0:
                raise ValueError("batch_size must be positive")
            
            if self.processing_threads <= 0:
                raise ValueError("processing_threads must be positive")
            
            # Validate reference position if provided
            if self.reference_latitude is not None:
                if not (-90 <= self.reference_latitude <= 90):
                    raise ValueError("reference_latitude must be between -90 and 90")
            
            if self.reference_longitude is not None:
                if not (-180 <= self.reference_longitude <= 180):
                    raise ValueError("reference_longitude must be between -180 and 180")
            
            return True
            
        except ValueError as e:
            logger.error(f"Configuration validation error: {e}")
            return False