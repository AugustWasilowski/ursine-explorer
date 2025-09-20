# Meshtastic Configuration Examples

This document provides practical configuration examples for different use cases of the enhanced Meshtastic integration in UrsineExplorer.

## Basic Configurations

### 1. Simple Serial Connection (Legacy Compatible)

For users upgrading from the basic Meshtastic integration:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      }
    ],
    "default_channel": "LongFast",
    "connection_mode": "serial",
    "enable_encryption": false,
    "message_format": "standard"
  }
}
```

### 2. MQTT Only Configuration

For network-only deployments without USB serial connection:

```json
{
  "meshtastic": {
    "connection_mode": "mqtt",
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      }
    ],
    "default_channel": "LongFast",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_mqtt_001"
    },
    "enable_encryption": false,
    "message_format": "standard"
  }
}
```

### 3. Dual Mode with Failover

Recommended configuration for maximum reliability:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "failover_enabled": true,
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      }
    ],
    "default_channel": "LongFast",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_dual_001"
    },
    "enable_encryption": false,
    "message_format": "standard",
    "connection_timeout": 10,
    "retry_interval": 30
  }
}
```

## Encrypted Channel Configurations

### 4. Single Encrypted Channel

Basic encrypted setup with one secure channel:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      },
      {
        "name": "SecureAlerts",
        "psk": "AQ==",
        "channel_number": 1
      }
    ],
    "default_channel": "SecureAlerts",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US"
    },
    "enable_encryption": true,
    "message_format": "standard"
  }
}
```

### 5. Multiple Encrypted Channels by Alert Type

Different channels for different types of alerts:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "channels": [
      {
        "name": "PublicAlerts",
        "psk": null,
        "channel_number": 0,
        "uplink_enabled": true,
        "downlink_enabled": true
      },
      {
        "name": "WatchlistAlerts",
        "psk": "d2F0Y2hsaXN0X3BzazEyMzQ1Njc4OTA=",
        "channel_number": 1,
        "uplink_enabled": true,
        "downlink_enabled": false
      },
      {
        "name": "EmergencyAlerts",
        "psk": "ZW1lcmdlbmN5X3BzazEyMzQ1Njc4OTA=",
        "channel_number": 2,
        "uplink_enabled": true,
        "downlink_enabled": false
      },
      {
        "name": "ProximityAlerts",
        "psk": "cHJveGltaXR5X3BzazEyMzQ1Njc4OTA=",
        "channel_number": 3,
        "uplink_enabled": true,
        "downlink_enabled": true
      }
    ],
    "default_channel": "WatchlistAlerts",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US"
    },
    "enable_encryption": true,
    "message_format": "standard"
  }
}
```

### 6. Regional Channels

Different encrypted channels for different geographic regions:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "channels": [
      {
        "name": "PublicGeneral",
        "psk": null,
        "channel_number": 0
      },
      {
        "name": "RegionNorth",
        "psk": "bm9ydGhfcmVnaW9uX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 1
      },
      {
        "name": "RegionSouth",
        "psk": "c291dGhfcmVnaW9uX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 2
      },
      {
        "name": "RegionEast",
        "psk": "ZWFzdF9yZWdpb25fcHNrMTIzNDU2Nzg5MA==",
        "channel_number": 3
      },
      {
        "name": "RegionWest",
        "psk": "d2VzdF9yZWdpb25fcHNrMTIzNDU2Nzg5MA==",
        "channel_number": 4
      }
    ],
    "default_channel": "RegionNorth",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US"
    },
    "enable_encryption": true,
    "message_format": "compact"
  }
}
```

## MQTT Broker Configurations

### 7. Public MQTT Broker (Meshtastic Official)

Using the official Meshtastic MQTT broker:

```json
{
  "meshtastic": {
    "connection_mode": "mqtt",
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      }
    ],
    "default_channel": "LongFast",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "username": null,
      "password": null,
      "use_tls": false,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_public",
      "qos": 0,
      "keepalive": 60
    }
  }
}
```

### 8. Private MQTT Broker with Authentication

Using a private MQTT broker with TLS and authentication:

```json
{
  "meshtastic": {
    "connection_mode": "dual",
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "channels": [
      {
        "name": "PrivateNetwork",
        "psk": "cHJpdmF0ZV9uZXR3b3JrX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 1
      }
    ],
    "default_channel": "PrivateNetwork",
    "mqtt": {
      "broker_url": "secure-mqtt.example.com",
      "port": 8883,
      "username": "adsb_user",
      "password": "secure_password_123",
      "use_tls": true,
      "topic_prefix": "private/mesh",
      "client_id": "ursine_explorer_private_001",
      "qos": 1,
      "keepalive": 120
    },
    "enable_encryption": true
  }
}
```

### 9. Local MQTT Broker (Mosquitto)

Using a local Mosquitto broker:

```json
{
  "meshtastic": {
    "connection_mode": "mqtt",
    "channels": [
      {
        "name": "LocalMesh",
        "psk": "bG9jYWxfbWVzaF9wc2sxMjM0NTY3ODkw",
        "channel_number": 1
      }
    ],
    "default_channel": "LocalMesh",
    "mqtt": {
      "broker_url": "192.168.1.100",
      "port": 1883,
      "username": "meshtastic",
      "password": "local_mesh_password",
      "use_tls": false,
      "topic_prefix": "local/mesh",
      "client_id": "ursine_explorer_local",
      "qos": 1,
      "keepalive": 60
    },
    "enable_encryption": true
  }
}
```

## Message Format Configurations

### 10. Standard Format (Detailed)

Full detail messages for comprehensive information:

```json
{
  "meshtastic": {
    "message_format": "standard",
    "include_position": true,
    "include_timestamp": true,
    "max_message_length": 200,
    "channels": [
      {
        "name": "DetailedAlerts",
        "psk": "ZGV0YWlsZWRfYWxlcnRzX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 1
      }
    ],
    "default_channel": "DetailedAlerts"
  }
}
```

### 11. Compact Format (Bandwidth Optimized)

Minimal messages for bandwidth-constrained environments:

```json
{
  "meshtastic": {
    "message_format": "compact",
    "include_position": true,
    "include_timestamp": false,
    "max_message_length": 100,
    "channels": [
      {
        "name": "CompactAlerts",
        "psk": "Y29tcGFjdF9hbGVydHNfcHNrMTIzNDU2Nzg5MA==",
        "channel_number": 1
      }
    ],
    "default_channel": "CompactAlerts"
  }
}
```

### 12. JSON Format (Machine Readable)

JSON format for automated processing:

```json
{
  "meshtastic": {
    "message_format": "json",
    "include_position": true,
    "include_timestamp": true,
    "max_message_length": 300,
    "channels": [
      {
        "name": "JsonAlerts",
        "psk": "anNvbl9hbGVydHNfcHNrMTIzNDU2Nzg5MA==",
        "channel_number": 1
      }
    ],
    "default_channel": "JsonAlerts"
  }
}
```

## Performance Optimized Configurations

### 13. High Throughput Configuration

Optimized for high message volume:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "failover_enabled": true,
    "channels": [
      {
        "name": "HighThroughput",
        "psk": "aGlnaF90aHJvdWdocHV0X3BzazEyMzQ1Njc4OTA=",
        "channel_number": 1
      }
    ],
    "default_channel": "HighThroughput",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "qos": 0,
      "keepalive": 300
    },
    "message_format": "compact",
    "max_message_length": 80,
    "include_position": false,
    "include_timestamp": false,
    "connection_timeout": 5,
    "retry_interval": 10,
    "health_check_interval": 120,
    "log_all_messages": false
  }
}
```

### 14. High Reliability Configuration

Optimized for maximum message delivery reliability:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "failover_enabled": true,
    "channels": [
      {
        "name": "ReliableAlerts",
        "psk": "cmVsaWFibGVfYWxlcnRzX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 1
      }
    ],
    "default_channel": "ReliableAlerts",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "qos": 1,
      "keepalive": 60
    },
    "message_format": "standard",
    "max_message_length": 200,
    "include_position": true,
    "include_timestamp": true,
    "connection_timeout": 15,
    "retry_interval": 30,
    "health_check_interval": 30,
    "log_all_messages": true,
    "auto_detect_device": true,
    "enable_encryption": true
  }
}
```

### 15. Low Power Configuration

Optimized for battery-powered deployments:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "serial",
    "channels": [
      {
        "name": "LowPowerAlerts",
        "psk": "bG93X3Bvd2VyX2FsZXJ0c19wc2sxMjM0NTY3ODkw",
        "channel_number": 1
      }
    ],
    "default_channel": "LowPowerAlerts",
    "message_format": "compact",
    "max_message_length": 60,
    "include_position": false,
    "include_timestamp": false,
    "connection_timeout": 30,
    "retry_interval": 60,
    "health_check_interval": 300,
    "log_all_messages": false,
    "auto_detect_device": false
  }
}
```

## Specialized Use Cases

### 16. Emergency Services Configuration

Configuration for emergency services with priority channels:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "failover_enabled": true,
    "channels": [
      {
        "name": "PublicSafety",
        "psk": "cHVibGljX3NhZmV0eV9wc2sxMjM0NTY3ODkw",
        "channel_number": 1,
        "uplink_enabled": true,
        "downlink_enabled": true
      },
      {
        "name": "EmergencyDispatch",
        "psk": "ZW1lcmdlbmN5X2Rpc3BhdGNoX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 2,
        "uplink_enabled": true,
        "downlink_enabled": false
      },
      {
        "name": "SearchRescue",
        "psk": "c2VhcmNoX3Jlc2N1ZV9wc2sxMjM0NTY3ODkw",
        "channel_number": 3,
        "uplink_enabled": true,
        "downlink_enabled": true
      }
    ],
    "default_channel": "PublicSafety",
    "mqtt": {
      "broker_url": "emergency-mqtt.example.com",
      "port": 8883,
      "username": "emergency_user",
      "password": "emergency_secure_password",
      "use_tls": true,
      "topic_prefix": "emergency/mesh",
      "qos": 1
    },
    "message_format": "standard",
    "include_position": true,
    "include_timestamp": true,
    "enable_encryption": true,
    "log_all_messages": true
  }
}
```

### 17. Aviation Enthusiast Network

Configuration for aviation enthusiast groups:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "channels": [
      {
        "name": "AvGeeks",
        "psk": "YXZnZWVrc19wc2sxMjM0NTY3ODkw",
        "channel_number": 1
      },
      {
        "name": "SpotterNetwork",
        "psk": "c3BvdHRlcl9uZXR3b3JrX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 2
      },
      {
        "name": "RareAircraft",
        "psk": "cmFyZV9haXJjcmFmdF9wc2sxMjM0NTY3ODkw",
        "channel_number": 3
      }
    ],
    "default_channel": "SpotterNetwork",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US"
    },
    "message_format": "standard",
    "include_position": true,
    "include_timestamp": true,
    "enable_encryption": true
  }
}
```

### 18. Research and Development

Configuration for research institutions:

```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "channels": [
      {
        "name": "ResearchData",
        "psk": "cmVzZWFyY2hfZGF0YV9wc2sxMjM0NTY3ODkw",
        "channel_number": 1
      },
      {
        "name": "TestChannel",
        "psk": "dGVzdF9jaGFubmVsX3BzazEyMzQ1Njc4OTA=",
        "channel_number": 2
      }
    ],
    "default_channel": "ResearchData",
    "mqtt": {
      "broker_url": "research-mqtt.university.edu",
      "port": 8883,
      "username": "research_user",
      "password": "research_password",
      "use_tls": true,
      "topic_prefix": "research/adsb"
    },
    "message_format": "json",
    "include_position": true,
    "include_timestamp": true,
    "max_message_length": 500,
    "enable_encryption": true,
    "log_all_messages": true,
    "health_check_interval": 30
  }
}
```

## Migration Examples

### 19. Migrating from Legacy Configuration

**Before (Legacy):**
```json
{
  "meshtastic_enabled": true,
  "meshtastic_port": "/dev/ttyUSB0",
  "meshtastic_baud": 115200
}
```

**After (Enhanced):**
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      }
    ],
    "default_channel": "LongFast",
    "connection_mode": "serial",
    "enable_encryption": false,
    "message_format": "standard",
    "auto_detect_device": true,
    "failover_enabled": false
  }
}
```

### 20. Gradual Enhancement Migration

**Step 1 - Basic Migration:**
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "serial"
  }
}
```

**Step 2 - Add Channels:**
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "serial",
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      }
    ],
    "default_channel": "LongFast"
  }
}
```

**Step 3 - Add Encryption:**
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "serial",
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      },
      {
        "name": "SecureAlerts",
        "psk": "your_generated_psk_here",
        "channel_number": 1
      }
    ],
    "default_channel": "SecureAlerts",
    "enable_encryption": true
  }
}
```

**Step 4 - Add MQTT (Final):**
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "connection_mode": "dual",
    "failover_enabled": true,
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0
      },
      {
        "name": "SecureAlerts",
        "psk": "your_generated_psk_here",
        "channel_number": 1
      }
    ],
    "default_channel": "SecureAlerts",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US"
    },
    "enable_encryption": true,
    "message_format": "standard"
  }
}
```

## Configuration Validation

Each configuration example can be validated using the built-in validator:

```bash
# Validate configuration
python3 -c "
from pymodes_integration.meshtastic_enhanced import MeshtasticConfig
import json

with open('config.json') as f:
    config = json.load(f)

meshtastic_config = MeshtasticConfig(**config['meshtastic'])
print('Configuration is valid!')
"
```

## Security Notes

- **PSK Generation**: Always generate PSKs using cryptographically secure methods
- **PSK Storage**: Never commit PSKs to version control
- **Channel Isolation**: Use different PSKs for different purposes/groups
- **Regular Rotation**: Rotate PSKs periodically for security
- **TLS Usage**: Always use TLS for MQTT in production environments
- **Authentication**: Use strong passwords for MQTT broker authentication

These examples provide a comprehensive starting point for various deployment scenarios and can be customized further based on specific requirements.