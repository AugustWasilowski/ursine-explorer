#!/usr/bin/env python3
"""
Configuration validation and migration utility for ADS-B receiver.

This script provides command-line tools for validating, migrating, and 
managing configuration files for the enhanced ADS-B receiver system.
"""

import argparse
import json
import sys
import logging
from pathlib import Path
from typing import Dict, Any, List

from pymodes_integration.config import ConfigManager, ConfigurationError, ADSBConfig


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def validate_config(config_path: str, verbose: bool = False) -> bool:
    """
    Validate configuration file.
    
    Args:
        config_path: Path to configuration file
        verbose: Enable verbose output
        
    Returns:
        True if configuration is valid, False otherwise
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Validating configuration file: {config_path}")
        
        config_manager = ConfigManager(config_path)
        config = config_manager.load_config()
        
        logger.info("Configuration validation successful")
        
        if verbose:
            logger.info("Configuration summary:")
            logger.info(f"  pyModeS enabled: {config.pymodes.enabled}")
            logger.info(f"  Message sources: {len(config.message_sources)}")
            logger.info(f"  Aircraft timeout: {config.aircraft_tracking.aircraft_timeout_sec}s")
            logger.info(f"  Watchlist enabled: {config.watchlist.enabled}")
            
        return True
        
    except ConfigurationError as e:
        logger.error(f"Configuration validation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during validation: {e}")
        return False


def migrate_config(config_path: str, backup: bool = True, verbose: bool = False) -> bool:
    """
    Migrate configuration file to new format.
    
    Args:
        config_path: Path to configuration file
        backup: Create backup of original file
        verbose: Enable verbose output
        
    Returns:
        True if migration was successful, False otherwise
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.error(f"Configuration file not found: {config_path}")
            return False
        
        # Create backup if requested
        if backup:
            backup_path = config_file.with_suffix('.json.backup')
            logger.info(f"Creating backup: {backup_path}")
            backup_path.write_text(config_file.read_text())
        
        logger.info(f"Migrating configuration file: {config_path}")
        
        # Load and check if migration is needed
        with open(config_file, 'r') as f:
            raw_config = json.load(f)
        
        config_manager = ConfigManager(config_path)
        
        if not config_manager._needs_migration(raw_config):
            logger.info("Configuration is already in the latest format")
            return True
        
        # Perform migration by loading (which triggers migration)
        config = config_manager.load_config()
        
        logger.info("Configuration migration completed successfully")
        
        if verbose:
            logger.info("Migration changes:")
            logger.info("  + Added pyModeS configuration section")
            logger.info("  + Added message sources configuration")
            logger.info("  + Added enhanced aircraft tracking settings")
            logger.info("  + Added watchlist configuration")
            logger.info("  + Added logging configuration")
            logger.info("  + Added performance tuning settings")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False


def create_default_config(config_path: str, overwrite: bool = False, verbose: bool = False) -> bool:
    """
    Create a default configuration file.
    
    Args:
        config_path: Path where to create configuration file
        overwrite: Overwrite existing file
        verbose: Enable verbose output
        
    Returns:
        True if creation was successful, False otherwise
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        config_file = Path(config_path)
        
        if config_file.exists() and not overwrite:
            logger.error(f"Configuration file already exists: {config_path}")
            logger.error("Use --overwrite to replace existing file")
            return False
        
        logger.info(f"Creating default configuration: {config_path}")
        
        config_manager = ConfigManager(config_path)
        config = config_manager._create_default_config()
        config_manager._config = config
        config_manager.save_config()
        
        logger.info("Default configuration created successfully")
        
        if verbose:
            logger.info("Default configuration includes:")
            logger.info("  - pyModeS integration enabled")
            logger.info("  - Single dump1090 message source")
            logger.info("  - Standard aircraft tracking settings")
            logger.info("  - Watchlist monitoring enabled")
            logger.info("  - Comprehensive logging configuration")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to create default configuration: {e}")
        return False


def check_config_compatibility(config_path: str, verbose: bool = False) -> bool:
    """
    Check configuration compatibility with current system.
    
    Args:
        config_path: Path to configuration file
        verbose: Enable verbose output
        
    Returns:
        True if configuration is compatible, False otherwise
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Checking configuration compatibility: {config_path}")
        
        config_manager = ConfigManager(config_path)
        config = config_manager.load_config()
        
        warnings = []
        errors = []
        
        # Check pyModeS availability
        try:
            import pyModeS
            logger.info("pyModeS library is available")
        except ImportError:
            errors.append("pyModeS library is not installed")
        
        # Check message source connectivity
        for source in config.message_sources:
            if source.enabled:
                if source.type == "dump1090":
                    # Could add actual connectivity check here
                    logger.info(f"Message source '{source.name}' configured for {source.host}:{source.port}")
                elif source.type == "rtlsdr":
                    try:
                        import rtlsdr
                        logger.info("RTL-SDR support available")
                    except ImportError:
                        warnings.append("RTL-SDR library not available for source: " + source.name)
        
        # Check Meshtastic configuration
        if config.meshtastic_port:
            meshtastic_path = Path(config.meshtastic_port)
            if not meshtastic_path.exists():
                warnings.append(f"Meshtastic device not found: {config.meshtastic_port}")
        
        # Check file paths
        dump1090_path = Path(config.dump1090_path)
        if not dump1090_path.exists():
            warnings.append(f"dump1090 binary not found: {config.dump1090_path}")
        
        # Report results
        if errors:
            logger.error("Configuration compatibility errors:")
            for error in errors:
                logger.error(f"  - {error}")
            return False
        
        if warnings:
            logger.warning("Configuration compatibility warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        
        logger.info("Configuration compatibility check completed")
        return True
        
    except Exception as e:
        logger.error(f"Compatibility check failed: {e}")
        return False


def show_config_info(config_path: str, verbose: bool = False) -> bool:
    """
    Display configuration information.
    
    Args:
        config_path: Path to configuration file
        verbose: Enable verbose output
        
    Returns:
        True if successful, False otherwise
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    try:
        logger.info(f"Configuration information for: {config_path}")
        
        config_manager = ConfigManager(config_path)
        config = config_manager.load_config()
        
        print("\n=== ADS-B Receiver Configuration ===")
        print(f"Configuration file: {config_path}")
        print(f"pyModeS integration: {'Enabled' if config.pymodes.enabled else 'Disabled'}")
        
        print(f"\nMessage Sources ({len(config.message_sources)}):")
        for i, source in enumerate(config.message_sources, 1):
            status = "Enabled" if source.enabled else "Disabled"
            print(f"  {i}. {source.name} ({source.type}) - {status}")
            print(f"     Host: {source.host}:{source.port}, Format: {source.format}")
        
        print(f"\nAircraft Tracking:")
        print(f"  Timeout: {config.aircraft_tracking.aircraft_timeout_sec}s")
        print(f"  Max aircraft: {config.aircraft_tracking.max_aircraft_count}")
        print(f"  Data validation: {'Enabled' if config.aircraft_tracking.enable_data_validation else 'Disabled'}")
        
        print(f"\nWatchlist:")
        print(f"  Enabled: {'Yes' if config.watchlist.enabled else 'No'}")
        print(f"  Target ICAO codes: {len(config.target_icao_codes)}")
        print(f"  Alert throttling: {'Enabled' if config.watchlist.alert_throttling.enabled else 'Disabled'}")
        
        print(f"\nLogging:")
        print(f"  Level: {config.logging.level}")
        print(f"  Log file: {config.logging.log_file}")
        print(f"  Message stats: {'Enabled' if config.logging.enable_message_stats else 'Disabled'}")
        
        print(f"\nPerformance:")
        print(f"  Batch size: {config.performance.message_batch_size}")
        print(f"  Processing interval: {config.performance.processing_interval_ms}ms")
        print(f"  Memory limit: {config.performance.memory_limit_mb}MB")
        
        if verbose:
            print(f"\n=== Detailed Configuration ===")
            
            print(f"\npyModeS Settings:")
            print(f"  Reference position: {config.pymodes.reference_position.latitude}, {config.pymodes.reference_position.longitude}")
            print(f"  CPR timeout: {config.pymodes.cpr_settings.global_position_timeout}s")
            print(f"  CRC validation: {'Enabled' if config.pymodes.message_validation.enable_crc_check else 'Disabled'}")
            print(f"  Supported message types: {', '.join(config.pymodes.decoder_settings.supported_message_types)}")
            
            print(f"\nLegacy Settings:")
            print(f"  Frequency: {config.frequency} Hz")
            print(f"  LNA Gain: {config.lna_gain}")
            print(f"  VGA Gain: {config.vga_gain}")
            print(f"  HackRF Amp: {'Enabled' if config.enable_hackrf_amp else 'Disabled'}")
            print(f"  Meshtastic: {config.meshtastic_port} @ {config.meshtastic_baud} baud")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to show configuration info: {e}")
        return False


def main():
    """Main entry point for configuration utility."""
    parser = argparse.ArgumentParser(
        description="ADS-B Receiver Configuration Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s validate config.json
  %(prog)s migrate config.json --backup
  %(prog)s create-default new_config.json
  %(prog)s check-compatibility config.json
  %(prog)s info config.json --verbose
        """
    )
    
    parser.add_argument(
        'command',
        choices=['validate', 'migrate', 'create-default', 'check-compatibility', 'info'],
        help='Command to execute'
    )
    
    parser.add_argument(
        'config_path',
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Create backup before migration (migrate command only)'
    )
    
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite existing file (create-default command only)'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    args = parser.parse_args()
    
    success = False
    
    if args.command == 'validate':
        success = validate_config(args.config_path, args.verbose)
    elif args.command == 'migrate':
        success = migrate_config(args.config_path, args.backup, args.verbose)
    elif args.command == 'create-default':
        success = create_default_config(args.config_path, args.overwrite, args.verbose)
    elif args.command == 'check-compatibility':
        success = check_config_compatibility(args.config_path, args.verbose)
    elif args.command == 'info':
        success = show_config_info(args.config_path, args.verbose)
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()