#!/usr/bin/env python3
"""
Example of how to integrate the configuration system into the main ADS-B application.

This demonstrates how the enhanced configuration system would be used
in the actual ADS-B receiver application.
"""

import logging
import sys
from typing import Optional

from pymodes_integration.config import get_config, reload_config, ConfigurationError


class ADSBApplication:
    """Example ADS-B application using the enhanced configuration system."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize the application with configuration."""
        self.logger = logging.getLogger(__name__)
        self.config = None
        self.running = False
        
        # Load configuration
        try:
            if config_path:
                # Use custom config path
                from pymodes_integration.config import ConfigManager
                global_config_manager = ConfigManager(config_path)
                self.config = global_config_manager.load_config()
            else:
                self.config = get_config()
            self._setup_logging()
            self.logger.info("ADS-B application initialized successfully")
            
        except ConfigurationError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            sys.exit(1)
    
    def _setup_logging(self):
        """Set up logging based on configuration."""
        log_config = self.config.logging
        
        # Configure logging level
        level = getattr(logging, log_config.level.upper(), logging.INFO)
        
        # Set up file handler
        file_handler = logging.FileHandler(log_config.log_file)
        file_handler.setLevel(level)
        
        # Set up console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
    
    def start(self):
        """Start the ADS-B receiver application."""
        self.logger.info("Starting ADS-B receiver application")
        
        # Initialize components based on configuration
        self._initialize_pymodes()
        self._initialize_message_sources()
        self._initialize_aircraft_tracking()
        self._initialize_watchlist()
        self._initialize_api_server()
        
        self.running = True
        self.logger.info("ADS-B receiver application started successfully")
    
    def stop(self):
        """Stop the ADS-B receiver application."""
        self.logger.info("Stopping ADS-B receiver application")
        self.running = False
        
        # Cleanup components
        self._cleanup_components()
        
        self.logger.info("ADS-B receiver application stopped")
    
    def reload_configuration(self):
        """Reload configuration and update components."""
        self.logger.info("Reloading configuration")
        
        try:
            old_config = self.config
            self.config = reload_config()
            
            # Update components that support runtime configuration changes
            self._update_logging_config(old_config.logging, self.config.logging)
            self._update_watchlist_config(old_config.watchlist, self.config.watchlist)
            
            self.logger.info("Configuration reloaded successfully")
            
        except ConfigurationError as e:
            self.logger.error(f"Failed to reload configuration: {e}")
            # Keep using old configuration
    
    def _initialize_pymodes(self):
        """Initialize pyModeS decoder based on configuration."""
        if not self.config.pymodes.enabled:
            self.logger.info("pyModeS integration is disabled")
            return
        
        self.logger.info("Initializing pyModeS decoder")
        
        # Configure reference position for CPR decoding
        ref_pos = self.config.pymodes.reference_position
        if ref_pos.latitude is not None and ref_pos.longitude is not None:
            self.logger.info(f"Using reference position: {ref_pos.latitude}, {ref_pos.longitude}")
        else:
            self.logger.info("No reference position configured, using global CPR decoding only")
        
        # Configure message validation
        validation = self.config.pymodes.message_validation
        self.logger.info(f"Message validation - CRC: {validation.enable_crc_check}, "
                        f"Format: {validation.enable_format_validation}, "
                        f"Range: {validation.enable_range_validation}")
        
        # Configure decoder settings
        decoder = self.config.pymodes.decoder_settings
        self.logger.info(f"Supported message types: {', '.join(decoder.supported_message_types)}")
        self.logger.info(f"Enhanced decoding: {decoder.enable_enhanced_decoding}")
    
    def _initialize_message_sources(self):
        """Initialize message sources based on configuration."""
        self.logger.info(f"Initializing {len(self.config.message_sources)} message sources")
        
        for source in self.config.message_sources:
            if not source.enabled:
                self.logger.info(f"Message source '{source.name}' is disabled, skipping")
                continue
            
            self.logger.info(f"Initializing message source '{source.name}' "
                           f"({source.type}) at {source.host}:{source.port}")
            
            # Here you would create the actual message source objects
            # For example:
            # if source.type == "dump1090":
            #     self.sources[source.name] = Dump1090Source(source)
            # elif source.type == "network":
            #     self.sources[source.name] = NetworkSource(source)
    
    def _initialize_aircraft_tracking(self):
        """Initialize aircraft tracking based on configuration."""
        tracking = self.config.aircraft_tracking
        
        self.logger.info(f"Initializing aircraft tracking - "
                        f"timeout: {tracking.aircraft_timeout_sec}s, "
                        f"max aircraft: {tracking.max_aircraft_count}, "
                        f"validation: {tracking.enable_data_validation}")
        
        # Configure cleanup intervals
        self.logger.info(f"Aircraft cleanup interval: {tracking.cleanup_interval_sec}s")
        self.logger.info(f"Position timeout: {tracking.position_timeout_sec}s")
        self.logger.info(f"Conflict resolution: {tracking.conflict_resolution}")
    
    def _initialize_watchlist(self):
        """Initialize watchlist monitoring based on configuration."""
        if not self.config.watchlist.enabled:
            self.logger.info("Watchlist monitoring is disabled")
            return
        
        watchlist = self.config.watchlist
        self.logger.info(f"Initializing watchlist monitoring - "
                        f"ICAO: {watchlist.check_icao}, "
                        f"Callsign: {watchlist.check_callsign}")
        
        # Configure alert throttling
        throttling = watchlist.alert_throttling
        if throttling.enabled:
            self.logger.info(f"Alert throttling enabled - "
                           f"min interval: {throttling.min_interval_sec}s, "
                           f"max per hour: {throttling.max_alerts_per_hour}")
        
        # Load target ICAO codes
        if self.config.target_icao_codes:
            self.logger.info(f"Loaded {len(self.config.target_icao_codes)} target ICAO codes")
    
    def _initialize_api_server(self):
        """Initialize HTTP API server based on configuration."""
        self.logger.info(f"Initializing API server on port {self.config.receiver_control_port}")
        
        # Here you would initialize the actual HTTP server
        # server = HTTPServer(port=self.config.receiver_control_port)
    
    def _cleanup_components(self):
        """Clean up application components."""
        # Here you would clean up message sources, close connections, etc.
        pass
    
    def _update_logging_config(self, old_config, new_config):
        """Update logging configuration at runtime."""
        if old_config.level != new_config.level:
            self.logger.info(f"Updating log level from {old_config.level} to {new_config.level}")
            # Update logging level
    
    def _update_watchlist_config(self, old_config, new_config):
        """Update watchlist configuration at runtime."""
        if old_config.enabled != new_config.enabled:
            self.logger.info(f"Watchlist monitoring {'enabled' if new_config.enabled else 'disabled'}")
    
    def get_status(self) -> dict:
        """Get application status information."""
        return {
            "running": self.running,
            "pymodes_enabled": self.config.pymodes.enabled,
            "message_sources": len([s for s in self.config.message_sources if s.enabled]),
            "watchlist_enabled": self.config.watchlist.enabled,
            "target_icao_count": len(self.config.target_icao_codes),
            "aircraft_timeout": self.config.aircraft_tracking.aircraft_timeout_sec,
            "log_level": self.config.logging.level
        }


def main():
    """Example main function showing how to use the configuration system."""
    import argparse
    
    parser = argparse.ArgumentParser(description="ADS-B Receiver Application")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--validate-config", action="store_true", 
                       help="Validate configuration and exit")
    
    args = parser.parse_args()
    
    if args.validate_config:
        # Just validate configuration
        try:
            if args.config:
                from pymodes_integration.config import ConfigManager
                manager = ConfigManager(args.config)
                manager.load_config()
            else:
                get_config()
            print("Configuration is valid")
            return 0
        except ConfigurationError as e:
            print(f"Configuration error: {e}", file=sys.stderr)
            return 1
    
    # Run the application
    try:
        app = ADSBApplication(args.config)
        app.start()
        
        # Print status
        status = app.get_status()
        print("\nApplication Status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
        
        # In a real application, you would run the main loop here
        print("\nApplication would run main processing loop here...")
        
        app.stop()
        return 0
        
    except KeyboardInterrupt:
        print("\nShutting down...")
        return 0
    except Exception as e:
        print(f"Application error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())