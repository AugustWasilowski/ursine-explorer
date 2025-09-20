"""
Example usage of enhanced Meshtastic integration foundation

This module demonstrates how to use the basic components
of the enhanced Meshtastic system.
"""

from datetime import datetime
from .data_classes import (
    ChannelConfig, MQTTConfig, MeshtasticConfig,
    AlertMessage, MessagePriority
)
from .utils import generate_psk, format_message_content


def create_example_configuration():
    """Create an example Meshtastic configuration"""
    print("Creating example Meshtastic configuration...")
    
    # Create some channels
    channels = [
        # Default unencrypted channel
        ChannelConfig(name="LongFast", channel_number=0),
        
        # Encrypted channel for sensitive alerts
        ChannelConfig(
            name="SecureAlerts",
            psk=generate_psk(32),  # Generate 256-bit key
            channel_number=1
        ),
        
        # Another encrypted channel for emergency use
        ChannelConfig(
            name="Emergency",
            psk=generate_psk(32),
            channel_number=2
        )
    ]
    
    # Create MQTT configuration
    mqtt_config = MQTTConfig(
        broker_url="mqtt.meshtastic.org",
        port=1883,
        topic_prefix="msh/US",
        client_id="ursine_adsb_demo"
    )
    
    # Create main configuration
    config = MeshtasticConfig(
        meshtastic_port="/dev/ttyUSB0",
        meshtastic_baud=115200,
        channels=channels,
        default_channel="SecureAlerts",
        mqtt=mqtt_config,
        connection_mode="dual",
        failover_enabled=True,
        message_format="standard",
        include_position=True,
        include_timestamp=True,
        enable_encryption=True
    )
    
    print(f"Created configuration with {len(config.channels)} channels")
    print(f"Default channel: {config.default_channel}")
    print(f"Connection mode: {config.connection_mode}")
    
    return config


def create_example_alert_messages():
    """Create example alert messages"""
    print("\nCreating example alert messages...")
    
    messages = [
        # High priority watchlist alert
        AlertMessage(
            content="WATCHLIST: Aircraft ABC123 detected at 35000ft",
            channel="SecureAlerts",
            priority=MessagePriority.HIGH,
            aircraft_icao="ABC123",
            alert_type="watchlist",
            position=(40.7128, -74.0060)  # NYC coordinates
        ),
        
        # Critical emergency alert
        AlertMessage(
            content="EMERGENCY: Squawk 7700 detected - Aircraft XYZ789",
            channel="Emergency", 
            priority=MessagePriority.CRITICAL,
            aircraft_icao="XYZ789",
            alert_type="emergency"
        ),
        
        # Medium priority proximity alert
        AlertMessage(
            content="PROXIMITY: Multiple aircraft in close formation",
            channel="LongFast",
            priority=MessagePriority.MEDIUM,
            alert_type="proximity"
        )
    ]
    
    for i, msg in enumerate(messages, 1):
        print(f"Message {i}: {msg.content[:50]}... (Priority: {msg.priority.name})")
    
    return messages


def demonstrate_message_formatting():
    """Demonstrate message formatting capabilities"""
    print("\nDemonstrating message formatting...")
    
    raw_message = "Aircraft ABC123 detected at coordinates 40.7128, -74.0060"
    
    # Standard formatting with timestamp and prefix
    formatted_standard = format_message_content(
        raw_message,
        include_timestamp=True,
        prefix="ADSB"
    )
    print(f"Standard format: {formatted_standard}")
    
    # Compact formatting without timestamp
    formatted_compact = format_message_content(
        raw_message,
        max_length=80,
        include_timestamp=False,
        prefix="A"
    )
    print(f"Compact format: {formatted_compact}")
    
    # Truncated long message
    long_message = "This is a very long message that exceeds the maximum length limit and should be truncated"
    formatted_truncated = format_message_content(
        long_message,
        max_length=50
    )
    print(f"Truncated format: {formatted_truncated}")


def demonstrate_serialization():
    """Demonstrate configuration serialization"""
    print("\nDemonstrating configuration serialization...")
    
    # Create a configuration
    config = create_example_configuration()
    
    # Serialize to dictionary
    config_dict = config.to_dict()
    print(f"Serialized config keys: {list(config_dict.keys())}")
    
    # Deserialize back
    restored_config = MeshtasticConfig.from_dict(config_dict)
    print(f"Restored config has {len(restored_config.channels)} channels")
    print(f"MQTT broker: {restored_config.mqtt.broker_url if restored_config.mqtt else 'None'}")
    
    # Verify they match
    assert config.default_channel == restored_config.default_channel
    assert len(config.channels) == len(restored_config.channels)
    print("✓ Serialization/deserialization successful")


def main():
    """Main demonstration function"""
    print("Enhanced Meshtastic Integration Foundation Demo")
    print("=" * 50)
    
    try:
        # Create example configuration
        config = create_example_configuration()
        
        # Create example messages
        messages = create_example_alert_messages()
        
        # Demonstrate formatting
        demonstrate_message_formatting()
        
        # Demonstrate serialization
        demonstrate_serialization()
        
        print("\n" + "=" * 50)
        print("Demo completed successfully!")
        print("\nNext steps:")
        print("- Implement ChannelManager and EncryptionHandler")
        print("- Create EnhancedSerialInterface")
        print("- Add MQTTInterface")
        print("- Build MessageRouter")
        print("- Create MeshtasticManager coordinator")
        
    except Exception as e:
        print(f"Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    main()