#!/usr/bin/env python3
"""
Ursine Explorer ADS-B Receiver - Integrated pyModeS Version
Main application integrating all pyModeS components with existing functionality
"""

import json
import time
import threading
import signal
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Any
import logging
from http.server import HTTPServer

# Import existing components
from adsb_receiver import (
    MeshtasticAlert, Dump1090Manager, ADSBHTTPHandler, ControlHandler,
    RateLimiter, APILogger, Aircraft as LegacyAircraft
)

# Import pyModeS integration components
from pymodes_integration import (
    PyModeSConfig, PyModeSDecode, MessageSourceManager, 
    Dump1090Source, NetworkSource, EnhancedAircraft,
    MessageValidator, ValidationConfig, ADSBLogger,
    PerformanceMonitor, initialize_logger, initialize_performance_monitor,
    get_logger, get_performance_monitor
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('adsb_receiver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class IntegratedADSBServer:
    """
    Integrated ADS-B server combining pyModeS capabilities with existing features
    
    This class serves as the main coordinator, integrating:
    - pyModeS message decoding and aircraft tracking
    - Existing Meshtastic alerts and watchlist monitoring
    - HTTP API server with enhanced endpoints
    - Dashboard compatibility
    - Configuration management
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize integrated ADS-B server"""
        logger.info("Initializing Integrated ADS-B Server with pyModeS")
        
        # Load configuration
        self.config = self.load_config(config_path)
        self.config_path = config_path
        
        # Initialize logging and monitoring
        self._initialize_logging()
        self._initialize_monitoring()
        
        # Core components
        self.running = False
        self.start_time = datetime.now()
        
        # pyModeS components
        self.pymodes_config = self._create_pymodes_config()
        self.pymodes_decoder = PyModeSDecode(self.pymodes_config)
        self.message_source_manager = MessageSourceManager()
        self.message_validator = MessageValidator(ValidationConfig())
        
        # Legacy components for backward compatibility
        self.meshtastic = None
        self.dump1090_manager = None
        
        # Aircraft tracking (unified)
        self.aircraft: Dict[str, EnhancedAircraft] = {}
        self.watchlist: Set[str] = set()
        
        # HTTP server components
        self.httpd = None
        self.control_server = None
        
        # Statistics and monitoring
        self.stats = {
            'total_aircraft': 0,
            'active_aircraft': 0,
            'messages_total': 0,
            'messages_decoded': 0,
            'messages_failed': 0,
            'last_update': None,
            'update_count': 0,
            'errors': 0,
            'watchlist_alerts': 0,
            'dump1090_restarts': 0,
            'pymodes_decode_rate': 0.0,
            'sources_connected': 0,
            'cpr_success_rate': 0.0
        }
        
        # Threading
        self.processing_thread = None
        self.cleanup_thread = None
        
        # Initialize components
        self._initialize_components()
        
        logger.info("Integrated ADS-B Server initialized successfully")
    
    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file with defaults"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {config_path} not found, using defaults")
            config = {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            config = {}
        
        # Set defaults for backward compatibility
        defaults = {
            'dump1090_host': 'localhost',
            'dump1090_port': 30005,
            'receiver_control_port': 8081,
            'frequency': 1090000000,
            'lna_gain': 40,
            'vga_gain': 20,
            'enable_hackrf_amp': True,
            'target_icao_codes': [],
            'meshtastic_port': None,
            'meshtastic_baud': 115200,
            'log_alerts': True,
            'alert_log_file': 'alerts.log',
            'alert_interval_sec': 300,
            'dump1090_path': '/usr/bin/dump1090-fa',
            'watchdog_timeout_sec': 60,
            'poll_interval_sec': 1,
            
            # pyModeS specific defaults
            'pymodes': {
                'enabled': True,
                'reference_position': {
                    'latitude': None,
                    'longitude': None
                },
                'cpr_settings': {
                    'global_position_timeout': 10,
                    'local_position_range_nm': 180,
                    'surface_position_timeout': 25
                },
                'message_validation': {
                    'enable_crc_check': True,
                    'enable_format_validation': True,
                    'enable_range_validation': True,
                    'max_message_age_sec': 60
                },
                'decoder_settings': {
                    'supported_message_types': ['DF4', 'DF5', 'DF17', 'DF18', 'DF20', 'DF21'],
                    'enable_enhanced_decoding': True,
                    'decode_comm_b': True,
                    'decode_bds': True
                }
            },
            
            'message_sources': [
                {
                    'name': 'dump1090_primary',
                    'type': 'dump1090',
                    'enabled': True,
                    'host': 'localhost',
                    'port': 30005,
                    'format': 'beast',
                    'reconnect_interval_sec': 5,
                    'max_reconnect_attempts': 10,
                    'buffer_size': 8192
                }
            ],
            
            'aircraft_tracking': {
                'aircraft_timeout_sec': 300,
                'position_timeout_sec': 60,
                'cleanup_interval_sec': 30,
                'max_aircraft_count': 10000,
                'enable_data_validation': True,
                'conflict_resolution': 'newest_wins',
                'track_surface_vehicles': True,
                'minimum_message_count': 2
            },
            
            'watchlist': {
                'enabled': True,
                'sources': ['target_icao_codes'],
                'check_icao': True,
                'check_callsign': True,
                'case_sensitive': False,
                'pattern_matching': False,
                'alert_throttling': {
                    'enabled': True,
                    'min_interval_sec': 300,
                    'max_alerts_per_hour': 10,
                    'escalation_enabled': False
                }
            },
            
            'logging': {
                'level': 'INFO',
                'enable_message_stats': True,
                'enable_aircraft_events': True,
                'enable_connection_events': True,
                'enable_decode_errors': True,
                'stats_interval_sec': 60,
                'log_file': 'adsb_receiver.log',
                'max_log_size_mb': 100,
                'backup_count': 5
            },
            
            'performance': {
                'message_batch_size': 100,
                'processing_interval_ms': 100,
                'memory_limit_mb': 512,
                'enable_profiling': False,
                'gc_interval_sec': 300
            }
        }
        
        # Merge defaults with loaded config
        def merge_dicts(default, config):
            result = default.copy()
            for key, value in config.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = merge_dicts(result[key], value)
                else:
                    result[key] = value
            return result
        
        return merge_dicts(defaults, config)
    
    def _initialize_logging(self):
        """Initialize enhanced logging system"""
        try:
            log_config = self.config.get('logging', {})
            initialize_logger(self.config)
            self.adsb_logger = get_logger()
            logger.info("Enhanced logging system initialized")
        except Exception as e:
            logger.error(f"Failed to initialize enhanced logging: {e}")
            self.adsb_logger = None
    
    def _initialize_monitoring(self):
        """Initialize performance monitoring"""
        try:
            perf_config = self.config.get('performance', {})
            initialize_performance_monitor(
                memory_limit_mb=perf_config.get('memory_limit_mb', 512),
                enable_profiling=perf_config.get('enable_profiling', False)
            )
            self.performance_monitor = get_performance_monitor()
            logger.info("Performance monitoring initialized")
        except Exception as e:
            logger.error(f"Failed to initialize performance monitoring: {e}")
            self.performance_monitor = None
    
    def _create_pymodes_config(self) -> PyModeSConfig:
        """Create pyModeS configuration from main config"""
        pymodes_settings = self.config.get('pymodes', {})
        
        config = PyModeSConfig()
        
        # Reference position
        ref_pos = pymodes_settings.get('reference_position', {})
        config.reference_latitude = ref_pos.get('latitude')
        config.reference_longitude = ref_pos.get('longitude')
        
        # CPR settings
        cpr_settings = pymodes_settings.get('cpr_settings', {})
        config.position_timeout_sec = cpr_settings.get('global_position_timeout', 10)
        config.local_position_range_nm = cpr_settings.get('local_position_range_nm', 180)
        
        # Message validation
        validation = pymodes_settings.get('message_validation', {})
        config.crc_validation = validation.get('enable_crc_check', True)
        config.format_validation = validation.get('enable_format_validation', True)
        config.range_validation = validation.get('enable_range_validation', True)
        
        # Decoder settings
        decoder = pymodes_settings.get('decoder_settings', {})
        config.supported_message_types = decoder.get('supported_message_types', ['DF17', 'DF18'])
        config.enhanced_decoding = decoder.get('enable_enhanced_decoding', True)
        
        # Logging settings
        logging_config = self.config.get('logging', {})
        config.log_message_stats = logging_config.get('enable_message_stats', True)
        config.log_aircraft_updates = logging_config.get('enable_aircraft_events', True)
        config.log_decode_errors = logging_config.get('enable_decode_errors', True)
        config.stats_interval_sec = logging_config.get('stats_interval_sec', 60)
        
        # Aircraft tracking
        tracking = self.config.get('aircraft_tracking', {})
        config.aircraft_timeout_sec = tracking.get('aircraft_timeout_sec', 300)
        
        return config
    
    def _initialize_components(self):
        """Initialize all server components"""
        # Initialize watchlist
        self.update_watchlist()
        
        # Initialize Meshtastic if configured
        if self.config.get('meshtastic_port'):
            try:
                self.meshtastic = MeshtasticAlert(
                    self.config['meshtastic_port'],
                    self.config.get('meshtastic_baud', 115200)
                )
                logger.info("Meshtastic alert system initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Meshtastic: {e}")
                self.meshtastic = None
        
        # Initialize dump1090 manager for backward compatibility
        try:
            self.dump1090_manager = Dump1090Manager(self.config)
            logger.info("dump1090 manager initialized")
        except Exception as e:
            logger.error(f"Failed to initialize dump1090 manager: {e}")
            self.dump1090_manager = None
        
        # Initialize message sources
        self._initialize_message_sources()
        
        logger.info("All components initialized")
    
    def _initialize_message_sources(self):
        """Initialize message sources from configuration"""
        sources_config = self.config.get('message_sources', [])
        
        for source_config in sources_config:
            if not source_config.get('enabled', True):
                continue
            
            try:
                source_type = source_config.get('type', 'dump1090')
                name = source_config.get('name', f"{source_type}_source")
                
                if source_type == 'dump1090':
                    source = Dump1090Source(
                        name=name,
                        host=source_config.get('host', 'localhost'),
                        port=source_config.get('port', 30005),
                        format_type=source_config.get('format', 'beast'),
                        reconnect_interval=source_config.get('reconnect_interval_sec', 5)
                    )
                elif source_type == 'network':
                    source = NetworkSource(
                        name=name,
                        host=source_config.get('host', 'localhost'),
                        port=source_config.get('port', 30005),
                        format_type=source_config.get('format', 'raw'),
                        reconnect_interval=source_config.get('reconnect_interval_sec', 5),
                        buffer_size=source_config.get('buffer_size', 8192)
                    )
                else:
                    logger.warning(f"Unknown source type: {source_type}")
                    continue
                
                if self.message_source_manager.add_source(source):
                    logger.info(f"Added message source: {name} ({source_type})")
                else:
                    logger.warning(f"Failed to add message source: {name}")
                    
            except Exception as e:
                logger.error(f"Error initializing message source {source_config}: {e}")
    
    def update_watchlist(self):
        """Update watchlist from configuration"""
        watchlist_config = self.config.get('watchlist', {})
        if not watchlist_config.get('enabled', True):
            self.watchlist.clear()
            return
        
        # Get watchlist from various sources
        new_watchlist = set()
        
        # From target_icao_codes
        if 'target_icao_codes' in watchlist_config.get('sources', ['target_icao_codes']):
            icao_codes = self.config.get('target_icao_codes', [])
            new_watchlist.update(code.upper() for code in icao_codes)
        
        # Update watchlist
        if new_watchlist != self.watchlist:
            self.watchlist = new_watchlist
            logger.info(f"Watchlist updated: {len(self.watchlist)} entries")
            if self.watchlist:
                logger.debug(f"Watchlist entries: {', '.join(sorted(self.watchlist))}")
    
    def start(self):
        """Start the integrated ADS-B server"""
        logger.info("Starting Integrated ADS-B Server")
        
        try:
            self.running = True
            
            # Start message collection
            self.message_source_manager.start_collection()
            
            # Connect Meshtastic if available
            if self.meshtastic:
                if self.meshtastic.connect():
                    logger.info("Meshtastic connected successfully")
                else:
                    logger.warning("Failed to connect to Meshtastic")
            
            # Start dump1090 if configured
            if self.dump1090_manager and self.config.get('start_dump1090', False):
                if self.dump1090_manager.start():
                    logger.info("dump1090 started successfully")
                else:
                    logger.warning("Failed to start dump1090")
            
            # Start processing threads
            self._start_processing_threads()
            
            # Start HTTP server
            self._start_http_server()
            
            # Start control server
            self._start_control_server()
            
            logger.info("Integrated ADS-B Server started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop the integrated ADS-B server"""
        logger.info("Stopping Integrated ADS-B Server")
        
        self.running = False
        
        # Stop HTTP servers
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
                logger.info("HTTP server stopped")
            except Exception as e:
                logger.error(f"Error stopping HTTP server: {e}")
        
        if self.control_server:
            try:
                self.control_server.shutdown()
                self.control_server.server_close()
                logger.info("Control server stopped")
            except Exception as e:
                logger.error(f"Error stopping control server: {e}")
        
        # Stop message collection
        try:
            self.message_source_manager.stop_collection()
            logger.info("Message collection stopped")
        except Exception as e:
            logger.error(f"Error stopping message collection: {e}")
        
        # Stop dump1090
        if self.dump1090_manager:
            try:
                self.dump1090_manager.stop()
                logger.info("dump1090 stopped")
            except Exception as e:
                logger.error(f"Error stopping dump1090: {e}")
        
        # Disconnect Meshtastic
        if self.meshtastic:
            try:
                self.meshtastic.disconnect()
                logger.info("Meshtastic disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting Meshtastic: {e}")
        
        # Wait for threads to finish
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=5)
        
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=5)
        
        logger.info("Integrated ADS-B Server stopped")
    
    def _start_processing_threads(self):
        """Start background processing threads"""
        # Main message processing thread
        self.processing_thread = threading.Thread(
            target=self._message_processing_worker,
            name="MessageProcessor",
            daemon=True
        )
        self.processing_thread.start()
        
        # Cleanup thread
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_worker,
            name="CleanupWorker", 
            daemon=True
        )
        self.cleanup_thread.start()
        
        logger.info("Processing threads started")
    
    def _start_http_server(self):
        """Start HTTP API server"""
        try:
            # Create custom handler class with server reference
            class CustomHTTPHandler(ADSBHTTPHandler):
                def __init__(self, *args, **kwargs):
                    super().__init__(*args, **kwargs)
            
            # Set up HTTP server
            server_address = ('', 8080)
            self.httpd = HTTPServer(server_address, CustomHTTPHandler)
            self.httpd.adsb_server = self  # Attach server reference
            
            # Start server in background thread
            server_thread = threading.Thread(
                target=self.httpd.serve_forever,
                name="HTTPServer",
                daemon=True
            )
            server_thread.start()
            
            logger.info("HTTP server started on port 8080")
            
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {e}")
            raise
    
    def _start_control_server(self):
        """Start control command server"""
        try:
            import socketserver
            
            # Create custom handler class with server reference
            class CustomControlHandler(ControlHandler):
                pass
            
            # Set up control server
            server_address = ('localhost', self.config.get('receiver_control_port', 8081))
            self.control_server = socketserver.ThreadingTCPServer(server_address, CustomControlHandler)
            self.control_server.adsb_server = self  # Attach server reference
            
            # Start server in background thread
            control_thread = threading.Thread(
                target=self.control_server.serve_forever,
                name="ControlServer",
                daemon=True
            )
            control_thread.start()
            
            logger.info(f"Control server started on port {self.config.get('receiver_control_port', 8081)}")
            
        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
            # Control server is not critical, continue without it
    
    def _message_processing_worker(self):
        """Main message processing worker thread"""
        logger.info("Message processing worker started")
        
        processing_interval = self.config.get('performance', {}).get('processing_interval_ms', 100) / 1000.0
        batch_size = self.config.get('performance', {}).get('message_batch_size', 100)
        
        while self.running:
            try:
                start_time = time.time()
                
                # Get message batch
                messages = self.message_source_manager.get_message_batch()
                
                if messages:
                    # Limit batch size for performance
                    if len(messages) > batch_size:
                        messages = messages[:batch_size]
                    
                    # Process messages through pyModeS
                    updated_aircraft = self.pymodes_decoder.process_messages(messages)
                    
                    # Update main aircraft dictionary
                    for icao, aircraft in updated_aircraft.items():
                        self.aircraft[icao] = aircraft
                    
                    # Check watchlist
                    self._check_watchlist(updated_aircraft)
                    
                    # Update statistics
                    self._update_statistics(len(messages), len(updated_aircraft))
                    
                    # Log processing stats periodically
                    if self.adsb_logger:
                        self.adsb_logger.log_message_processing(
                            len(messages), len(updated_aircraft), 
                            time.time() - start_time
                        )
                
                # Sleep for processing interval
                elapsed = time.time() - start_time
                sleep_time = max(0, processing_interval - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Message processing error: {e}")
                self.stats['errors'] += 1
                time.sleep(1)  # Brief pause on error
        
        logger.info("Message processing worker stopped")
    
    def _cleanup_worker(self):
        """Background cleanup worker thread"""
        logger.info("Cleanup worker started")
        
        cleanup_interval = self.config.get('aircraft_tracking', {}).get('cleanup_interval_sec', 30)
        
        while self.running:
            try:
                time.sleep(cleanup_interval)
                
                if not self.running:
                    break
                
                # Clean up old aircraft
                removed_count = self.pymodes_decoder.clear_old_aircraft()
                if removed_count > 0:
                    logger.info(f"Cleaned up {removed_count} old aircraft")
                
                # Update aircraft dictionary
                self.aircraft = self.pymodes_decoder.get_aircraft_data()
                
                # Perform garbage collection if enabled
                if self.config.get('performance', {}).get('gc_interval_sec'):
                    import gc
                    gc.collect()
                
                # Update performance metrics
                if self.performance_monitor:
                    self.performance_monitor.update_metrics()
                
            except Exception as e:
                logger.error(f"Cleanup worker error: {e}")
        
        logger.info("Cleanup worker stopped")
    
    def _check_watchlist(self, updated_aircraft: Dict[str, EnhancedAircraft]):
        """Check updated aircraft against watchlist"""
        if not self.watchlist or not self.meshtastic:
            return
        
        watchlist_config = self.config.get('watchlist', {})
        if not watchlist_config.get('enabled', True):
            return
        
        for icao, aircraft in updated_aircraft.items():
            # Check ICAO match
            if icao.upper() in self.watchlist:
                aircraft.is_watchlist = True
                self._send_watchlist_alert(aircraft, 'icao_match')
                continue
            
            # Check callsign match if enabled
            if (watchlist_config.get('check_callsign', True) and 
                aircraft.callsign and aircraft.callsign != 'Unknown'):
                
                callsign_clean = aircraft.callsign.strip().upper()
                if callsign_clean in self.watchlist:
                    aircraft.is_watchlist = True
                    self._send_watchlist_alert(aircraft, 'callsign_match')
    
    def _send_watchlist_alert(self, aircraft: EnhancedAircraft, match_type: str):
        """Send watchlist alert via Meshtastic"""
        if not self.meshtastic or not self.meshtastic.serial_conn:
            return
        
        try:
            # Create legacy aircraft object for compatibility
            legacy_aircraft = LegacyAircraft({
                'hex': aircraft.icao,
                'flight': aircraft.callsign or 'Unknown',
                'alt_baro': aircraft.altitude_baro,
                'gs': aircraft.ground_speed,
                'lat': aircraft.latitude,
                'lon': aircraft.longitude
            })
            
            # Send alert
            if self.meshtastic.send_alert(legacy_aircraft):
                self.stats['watchlist_alerts'] += 1
                logger.info(f"Sent watchlist alert for {aircraft.icao} ({match_type})")
                
                # Log alert event
                if self.adsb_logger:
                    self.adsb_logger.log_watchlist_alert(aircraft.icao, match_type)
            
        except Exception as e:
            logger.error(f"Error sending watchlist alert: {e}")
    
    def _update_statistics(self, messages_processed: int, aircraft_updated: int):
        """Update server statistics"""
        self.stats['messages_total'] += messages_processed
        self.stats['last_update'] = datetime.now()
        self.stats['update_count'] += 1
        self.stats['active_aircraft'] = len(self.aircraft)
        
        # Get pyModeS statistics
        pymodes_stats = self.pymodes_decoder.get_statistics()
        self.stats['messages_decoded'] = pymodes_stats.get('messages_decoded', 0)
        self.stats['messages_failed'] = pymodes_stats.get('messages_failed', 0)
        self.stats['pymodes_decode_rate'] = pymodes_stats.get('decode_rate', 0.0)
        
        # Get source statistics
        source_stats = self.message_source_manager.get_statistics()
        self.stats['sources_connected'] = source_stats.get('sources_connected', 0)
    
    # API methods for HTTP server compatibility
    def get_aircraft_data(self) -> dict:
        """Get aircraft data in legacy format for API compatibility"""
        aircraft_list = []
        
        for aircraft in self.aircraft.values():
            # Convert to legacy format
            aircraft_dict = {
                'hex': aircraft.icao,
                'flight': aircraft.callsign or 'Unknown',
                'alt_baro': aircraft.altitude_baro,
                'gs': aircraft.ground_speed,
                'track': aircraft.track_angle,
                'lat': aircraft.latitude,
                'lon': aircraft.longitude,
                'messages': aircraft.message_count,
                'last_seen': aircraft.last_seen.isoformat(),
                'is_watchlist': aircraft.is_watchlist
            }
            aircraft_list.append(aircraft_dict)
        
        return {
            'now': datetime.now().timestamp(),
            'messages': self.stats['messages_total'],
            'aircraft': aircraft_list
        }
    
    def get_enhanced_aircraft_data(self) -> dict:
        """Get enhanced aircraft data with pyModeS fields"""
        aircraft_list = []
        
        for aircraft in self.aircraft.values():
            aircraft_dict = aircraft.to_api_dict()
            aircraft_list.append(aircraft_dict)
        
        return {
            'now': datetime.now().timestamp(),
            'messages': self.stats['messages_total'],
            'aircraft': aircraft_list,
            'enhanced': True,
            'pymodes_version': '1.0.0'
        }
    
    def get_detailed_status(self) -> dict:
        """Get detailed system status"""
        return {
            'server': {
                'running': self.running,
                'start_time': self.start_time.isoformat(),
                'uptime_seconds': (datetime.now() - self.start_time).total_seconds()
            },
            'statistics': self.stats,
            'pymodes': self.pymodes_decoder.get_statistics(),
            'sources': self.message_source_manager.get_statistics(),
            'aircraft_count': len(self.aircraft),
            'watchlist_size': len(self.watchlist),
            'meshtastic_connected': self.meshtastic.serial_conn is not None if self.meshtastic else False
        }
    
    def get_processing_stats(self) -> dict:
        """Get processing statistics"""
        pymodes_stats = self.pymodes_decoder.get_statistics()
        source_stats = self.message_source_manager.get_statistics()
        
        return {
            'messages': {
                'total_processed': self.stats['messages_total'],
                'decoded': self.stats['messages_decoded'],
                'failed': self.stats['messages_failed'],
                'decode_rate': self.stats['pymodes_decode_rate'],
                'messages_per_second': source_stats.get('messages_per_second', 0.0)
            },
            'aircraft': {
                'total_seen': pymodes_stats.get('aircraft_created', 0),
                'currently_tracked': len(self.aircraft),
                'with_positions': sum(1 for a in self.aircraft.values() if a.latitude is not None),
                'watchlist_matches': sum(1 for a in self.aircraft.values() if a.is_watchlist)
            },
            'sources': {
                'total': source_stats.get('sources_total', 0),
                'connected': source_stats.get('sources_connected', 0),
                'health_status': source_stats.get('health_status', 'unknown')
            }
        }
    
    def get_health_status(self) -> dict:
        """Get system health status"""
        healthy = (
            self.running and
            self.stats['sources_connected'] > 0 and
            self.stats['errors'] < 100  # Arbitrary threshold
        )
        
        return {
            'healthy': healthy,
            'status': 'healthy' if healthy else 'degraded',
            'checks': {
                'server_running': self.running,
                'sources_connected': self.stats['sources_connected'] > 0,
                'error_rate_acceptable': self.stats['errors'] < 100,
                'pymodes_functioning': self.stats['pymodes_decode_rate'] > 0.1
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def get_sources_status(self) -> dict:
        """Get message sources status"""
        return {
            'sources': self.message_source_manager.get_sources_status(),
            'statistics': self.message_source_manager.get_statistics()
        }
    
    def get_decoder_metrics(self) -> dict:
        """Get decoder performance metrics"""
        return self.pymodes_decoder.get_statistics()
    
    def get_fft_data(self) -> dict:
        """Get FFT data (placeholder for compatibility)"""
        return {
            'fft_data': [],
            'center_freq': self.config.get('frequency', 1090000000),
            'sample_rate': 2000000,
            'timestamp': datetime.now().isoformat()
        }
    
    def get_status(self) -> dict:
        """Get basic status (for control server compatibility)"""
        return {
            'running': self.running,
            'aircraft_count': len(self.aircraft),
            'messages_total': self.stats['messages_total'],
            'sources_connected': self.stats['sources_connected'],
            'watchlist_alerts': self.stats['watchlist_alerts']
        }
    
    def restart_dump1090(self) -> bool:
        """Restart dump1090 (for control server compatibility)"""
        if self.dump1090_manager:
            try:
                self.dump1090_manager.stop()
                time.sleep(2)
                success = self.dump1090_manager.start()
                if success:
                    self.stats['dump1090_restarts'] += 1
                return success
            except Exception as e:
                logger.error(f"Error restarting dump1090: {e}")
                return False
        return False


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down...")
    if hasattr(signal_handler, 'server'):
        signal_handler.server.stop()
    sys.exit(0)


def main():
    """Main entry point"""
    logger.info("Starting Ursine Explorer ADS-B Receiver (Integrated)")
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Create and start server
        server = IntegratedADSBServer()
        signal_handler.server = server  # Store reference for signal handler
        
        server.start()
        
        # Keep main thread alive
        while server.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise
    finally:
        if 'server' in locals():
            server.stop()


if __name__ == "__main__":
    main()