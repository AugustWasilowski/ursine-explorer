"""
Example usage of the enhanced MeshtasticManager

This example demonstrates how to use the MeshtasticManager with
ConnectionManager for coordinated Meshtastic operations.
"""

import logging
import time
from typing import Any

from .meshtastic_manager import MeshtasticManager
from .data_classes import MeshtasticConfig, ChannelConfig, MQTTConfig


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MockAircraft:
    """Mock aircraft for demonstration"""
    
    def __init__(self, icao: str, callsign: str = None, lat: float = None, 
                 lon: float = None, altitude: int = None):
        self.icao = icao
        self.callsign = callsign
        self.lat = lat
        self.lon = lon
        self.altitude = altitude
        self.speed = 250
        self.heading = 90


def create_example_config() -> MeshtasticConfig:
    """Create an example configuration for testing"""
    
    # Define channels with encryption
    channels = [
        ChannelConfig(
            name="LongFast",
            psk=None,  # Unencrypted default channel
            channel_number=0
        ),
        ChannelConfig(
            name="SecureAlerts",
            psk="AQ==",  # Base64 encoded PSK (example)
            channel_number=1
        )
    ]
    
    # MQTT configuration (optional)
    mqtt_config = MQTTConfig(
        broker_url="mqtt.meshtastic.org",
        port=1883,
        topic_prefix="msh/US",
        client_id="ursine_explorer_demo"
    )
    
    # Main configuration
    config = MeshtasticConfig(
        # Legacy serial settings
        meshtastic_port="/dev/ttyUSB0",
        meshtastic_baud=115200,
        
        # Enhanced settings
        channels=channels,
        default_channel="SecureAlerts",
        mqtt=mqtt_config,
        connection_mode="dual",  # Use both serial and MQTT
        failover_enabled=True,
        
        # Message formatting
        message_format="standard",
        include_position=True,
        include_timestamp=True,
        max_message_length=200,
        
        # Health monitoring
        health_check_interval=30
    )
    
    return config


def demonstrate_manager_usage():
    """Demonstrate MeshtasticManager usage"""
    
    logger.info("=== MeshtasticManager Demo ===")
    
    # Create configuration
    config = create_example_config()
    logger.info(f"Created configuration with {len(config.channels)} channels")
    
    # Initialize manager
    manager = MeshtasticManager(config)
    
    try:
        # Initialize all components
        logger.info("Initializing MeshtasticManager...")
        if not manager.initialize():
            logger.error("Failed to initialize MeshtasticManager")
            return
        
        logger.info("MeshtasticManager initialized successfully!")
        
        # Get connection status
        status = manager.get_connection_status()
        logger.info(f"Connection status: {status['connection_mode']}")
        logger.info(f"Active interfaces: {len(status.get('interfaces', {}))}")
        
        # Get device information
        device_info = manager.get_device_info()
        if device_info:
            logger.info(f"Device info: {device_info}")
        
        # Test connectivity
        connectivity = manager.test_connectivity()
        logger.info(f"Connectivity test: {connectivity}")
        
        # Create mock aircraft for alert testing
        aircraft = MockAircraft(
            icao="ABC123",
            callsign="TEST123",
            lat=40.7128,
            lon=-74.0060,
            altitude=35000
        )
        
        # Send test alerts
        logger.info("Sending test alerts...")
        
        # Watchlist alert
        if manager.send_alert(aircraft, "watchlist"):
            logger.info("Watchlist alert sent successfully")
        else:
            logger.warning("Watchlist alert failed")
        
        # Emergency alert
        if manager.send_alert(aircraft, "emergency"):
            logger.info("Emergency alert sent successfully")
        else:
            logger.warning("Emergency alert failed")
        
        # Wait a bit for health monitoring
        logger.info("Waiting for health monitoring...")
        time.sleep(5)
        
        # Get updated status
        final_status = manager.get_connection_status()
        logger.info(f"Final statistics: {final_status.get('statistics', {})}")
        
        # Show connection manager health
        if 'connection_manager' in final_status:
            cm_status = final_status['connection_manager']
            logger.info(f"Connection Manager - Active: {cm_status.get('active_interfaces', 0)}, "
                       f"Failed: {cm_status.get('failed_interfaces', 0)}")
        
    except Exception as e:
        logger.error(f"Demo error: {e}")
    
    finally:
        # Shutdown gracefully
        logger.info("Shutting down MeshtasticManager...")
        manager.shutdown()
        logger.info("Demo completed")


def demonstrate_configuration_options():
    """Demonstrate different configuration options"""
    
    logger.info("=== Configuration Options Demo ===")
    
    # Serial-only configuration
    serial_config = MeshtasticConfig(
        connection_mode="serial",
        meshtastic_port="/dev/ttyUSB0",
        channels=[ChannelConfig(name="LongFast")],
        message_format="compact"
    )
    logger.info("Serial-only config created")
    
    # MQTT-only configuration
    mqtt_config = MeshtasticConfig(
        connection_mode="mqtt",
        mqtt=MQTTConfig(broker_url="test.broker.com"),
        channels=[ChannelConfig(name="LongFast")],
        message_format="json"
    )
    logger.info("MQTT-only config created")
    
    # Dual-mode with encryption
    dual_config = MeshtasticConfig(
        connection_mode="dual",
        meshtastic_port="/dev/ttyUSB0",
        mqtt=MQTTConfig(broker_url="mqtt.meshtastic.org"),
        channels=[
            ChannelConfig(name="Public", psk=None),
            ChannelConfig(name="Private", psk="your_psk_here")
        ],
        default_channel="Private",
        failover_enabled=True,
        enable_encryption=True
    )
    logger.info("Dual-mode encrypted config created")
    
    logger.info("Configuration options demo completed")


if __name__ == "__main__":
    # Run demonstrations
    demonstrate_configuration_options()
    print()
    demonstrate_manager_usage()