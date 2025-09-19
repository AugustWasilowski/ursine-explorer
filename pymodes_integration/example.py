#!/usr/bin/env python3
"""
Example usage of pyModeS integration

This example demonstrates how to use the pyModeS integration
with the UrsineExplorer system.
"""

import logging
import time
from typing import Dict

from .config import PyModeSConfig
from .decoder import PyModeSDecode
from .message_source import MessageSourceManager, DummyMessageSource
from .aircraft import EnhancedAircraft

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def example_basic_usage():
    """Basic usage example"""
    logger.info("=== Basic pyModeS Integration Example ===")
    
    # 1. Create configuration
    config = PyModeSConfig()
    config.reference_latitude = 40.7128  # New York City
    config.reference_longitude = -74.0060
    logger.info("Configuration created with NYC reference position")
    
    # 2. Create decoder (requires pyModeS to be installed)
    try:
        decoder = PyModeSDecode(config)
        logger.info("pyModeS decoder initialized")
    except ImportError:
        logger.error("pyModeS not available - install with: pip install pyModeS")
        return
    
    # 3. Create message source manager
    source_manager = MessageSourceManager()
    
    # 4. Add a dummy source for testing
    dummy_source = DummyMessageSource("example-dummy")
    source_manager.add_source(dummy_source)
    
    # 5. Start message collection
    source_manager.start_collection()
    logger.info("Message collection started")
    
    # 6. Process messages for a short time
    start_time = time.time()
    processed_aircraft: Dict[str, EnhancedAircraft] = {}
    
    while time.time() - start_time < 10:  # Run for 10 seconds
        # Get message batch
        messages = source_manager.get_message_batch()
        
        if messages:
            # Process with pyModeS decoder
            updated_aircraft = decoder.process_messages(messages)
            processed_aircraft.update(updated_aircraft)
            
            logger.info(f"Processed {len(messages)} messages, tracking {len(processed_aircraft)} aircraft")
        
        time.sleep(1)
    
    # 7. Stop collection
    source_manager.stop_collection()
    logger.info("Message collection stopped")
    
    # 8. Display results
    logger.info(f"\n=== Results ===")
    logger.info(f"Total aircraft tracked: {len(processed_aircraft)}")
    
    for icao, aircraft in processed_aircraft.items():
        logger.info(f"Aircraft {aircraft.get_display_name()}:")
        logger.info(f"  Messages: {aircraft.message_count}")
        logger.info(f"  Data sources: {list(aircraft.data_sources)}")
        logger.info(f"  Position: {aircraft.has_position()}")
        logger.info(f"  Velocity: {aircraft.has_velocity()}")
    
    # 9. Show statistics
    stats = decoder.get_statistics()
    logger.info(f"\nDecoder Statistics:")
    logger.info(f"  Messages processed: {stats['messages_processed']}")
    logger.info(f"  Messages decoded: {stats['messages_decoded']}")
    logger.info(f"  Decode rate: {stats['decode_rate']:.1%}")


def example_config_from_file():
    """Example of loading configuration from file"""
    logger.info("=== Configuration from File Example ===")
    
    # Load from existing config.json
    try:
        config = PyModeSConfig.from_file("config.json")
        logger.info("Configuration loaded from config.json")
        
        # Show some settings
        logger.info(f"CRC validation: {config.crc_validation}")
        logger.info(f"Aircraft timeout: {config.aircraft_timeout_sec}s")
        logger.info(f"Reference position: {config.reference_latitude}, {config.reference_longitude}")
        
    except Exception as e:
        logger.error(f"Failed to load config: {e}")


def example_aircraft_conversion():
    """Example of aircraft data conversion"""
    logger.info("=== Aircraft Data Conversion Example ===")
    
    # Create sample aircraft
    pymodes_data = {
        'icao': 'A12345',
        'timestamp': time.time(),
        'message_type': 'identification',
        'callsign': 'UAL123',
        'latitude': 40.7128,
        'longitude': -74.0060,
        'altitude': 35000,
        'ground_speed': 450.0,
        'track': 90.0
    }
    
    aircraft = EnhancedAircraft.from_pymodes_data(pymodes_data)
    logger.info(f"Created aircraft: {aircraft}")
    
    # Convert to API format
    api_data = aircraft.to_api_dict()
    logger.info("API format:")
    for key, value in api_data.items():
        logger.info(f"  {key}: {value}")
    
    # Convert to legacy format
    legacy_data = aircraft.to_legacy_dict()
    logger.info("Legacy format:")
    for key, value in legacy_data.items():
        logger.info(f"  {key}: {value}")


if __name__ == "__main__":
    # Run examples
    example_config_from_file()
    print()
    example_aircraft_conversion()
    print()
    example_basic_usage()