# Enhanced Meshtastic Configuration Guide

## Overview

This guide covers the enhanced Meshtastic integration features in UrsineExplorer, including encrypted channel configuration, MQTT connectivity, and dual-mode operation. The enhanced system supports both USB serial and MQTT connections with automatic failover and encrypted communication.

## Quick Start

### Basic Configuration

Add the following to your `config.json` file:

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
    "enable_encryption": false
  }
}
```

### Enhanced Configuration with Encryption

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
      },
      {
        "name": "SecureAlerts",
        "psk": "AQ==",
        "channel_number": 1
      }
    ],
    "default_channel": "SecureAlerts",
    "connection_mode": "dual",
    "enable_encryption": true,
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_adsb"
    }
  }
}
```

## Channel Configuration

### Understanding Channels

Meshtastic devices support multiple communication channels, each with different settings:

- **Channel 0 (LongFast)**: Default public channel, no encryption
- **Channel 1-7**: Custom channels that can be encrypted with PSK
- **Channel Number**: Must match across all devices in your network

### Setting Up Encrypted Channels

1. **Generate a PSK (Pre-Shared Key)**:
   ```bash
   # Generate a random 32-byte key and encode as Base64
   python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
   ```

2. **Configure the channel in config.json**:
   ```json
   {
     "name": "MySecureChannel",
     "psk": "your_generated_base64_psk_here",
     "channel_number": 1
   }
   ```

3. **Configure your Meshtastic devices** with the same PSK using the Meshtastic app or CLI

### Channel Configuration Examples

#### Multiple Channels for Different Alert Types
```json
"channels": [
  {
    "name": "PublicAlerts",
    "psk": null,
    "channel_number": 0
  },
  {
    "name": "EmergencyAlerts", 
    "psk": "emergency_psk_base64_here",
    "channel_number": 1
  },
  {
    "name": "WatchlistAlerts",
    "psk": "watchlist_psk_base64_here", 
    "channel_number": 2
  }
]
```

#### Regional Channels
```json
"channels": [
  {
    "name": "RegionNorth",
    "psk": "north_region_psk_here",
    "channel_number": 1
  },
  {
    "name": "RegionSouth", 
    "psk": "south_region_psk_here",
    "channel_number": 2
  }
]
```

## MQTT Broker Setup

### Using Public MQTT Brokers

#### Meshtastic Official Broker
```json
"mqtt": {
  "broker_url": "mqtt.meshtastic.org",
  "port": 1883,
  "topic_prefix": "msh/US",
  "client_id": "ursine_explorer_adsb"
}
```

#### Custom MQTT Broker
```json
"mqtt": {
  "broker_url": "your-broker.example.com",
  "port": 1883,
  "username": "your_username",
  "password": "your_password",
  "use_tls": true,
  "topic_prefix": "msh/US",
  "client_id": "ursine_explorer_adsb",
  "qos": 1,
  "keepalive": 60
}
```

### Setting Up Your Own MQTT Broker

#### Using Mosquitto (Recommended)

1. **Install Mosquitto**:
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install mosquitto mosquitto-clients
   
   # Start the service
   sudo systemctl start mosquitto
   sudo systemctl enable mosquitto
   ```

2. **Configure authentication** (optional but recommended):
   ```bash
   # Create password file
   sudo mosquitto_passwd -c /etc/mosquitto/passwd your_username
   
   # Edit /etc/mosquitto/mosquitto.conf
   echo "password_file /etc/mosquitto/passwd" | sudo tee -a /etc/mosquitto/mosquitto.conf
   echo "allow_anonymous false" | sudo tee -a /etc/mosquitto/mosquitto.conf
   
   # Restart mosquitto
   sudo systemctl restart mosquitto
   ```

3. **Test the broker**:
   ```bash
   # Subscribe to test topic
   mosquitto_sub -h localhost -t test/topic -u your_username -P your_password
   
   # Publish test message (in another terminal)
   mosquitto_pub -h localhost -t test/topic -m "Hello World" -u your_username -P your_password
   ```

#### Using Docker

```bash
# Run Mosquitto in Docker
docker run -it -p 1883:1883 -p 9001:9001 eclipse-mosquitto

# Or with persistent configuration
docker run -it -p 1883:1883 -p 9001:9001 \
  -v /path/to/mosquitto.conf:/mosquitto/config/mosquitto.conf \
  eclipse-mosquitto
```

## Connection Modes

### Serial Only Mode
```json
"connection_mode": "serial",
"meshtastic_port": "/dev/ttyUSB0",
"meshtastic_baud": 115200
```

### MQTT Only Mode  
```json
"connection_mode": "mqtt",
"mqtt": {
  "broker_url": "mqtt.meshtastic.org",
  "port": 1883
}
```

### Dual Mode (Recommended)
```json
"connection_mode": "dual",
"failover_enabled": true,
"meshtastic_port": "/dev/ttyUSB0", 
"mqtt": {
  "broker_url": "mqtt.meshtastic.org",
  "port": 1883
}
```

## Message Formatting Options

### Standard Format (Default)
```json
"message_format": "standard",
"include_position": true,
"include_timestamp": true,
"max_message_length": 200
```

Example output:
```
ALERT: N12345 (UAL123) WATCHLIST 
Pos: 40.7128,-74.0060 Alt: 35000ft
Speed: 450kts Hdg: 090° 
Time: 2024-01-15 14:30:25Z
```

### Compact Format
```json
"message_format": "compact",
"max_message_length": 100
```

Example output:
```
ALERT: N12345 WATCHLIST 40.71,-74.01 35k 450kt 090°
```

### JSON Format
```json
"message_format": "json"
```

Example output:
```json
{"icao":"N12345","callsign":"UAL123","alert":"WATCHLIST","lat":40.7128,"lon":-74.0060,"alt":35000,"speed":450,"heading":90,"time":"2024-01-15T14:30:25Z"}
```

## Advanced Configuration Options

### Complete Configuration Example
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "channels": [
      {
        "name": "LongFast",
        "psk": null,
        "channel_number": 0,
        "uplink_enabled": true,
        "downlink_enabled": true
      },
      {
        "name": "SecureAlerts",
        "psk": "your_base64_psk_here",
        "channel_number": 1,
        "uplink_enabled": true,
        "downlink_enabled": false
      }
    ],
    "default_channel": "SecureAlerts",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "username": null,
      "password": null,
      "use_tls": false,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_adsb",
      "qos": 0,
      "keepalive": 60
    },
    "connection_mode": "dual",
    "failover_enabled": true,
    "connection_timeout": 10,
    "retry_interval": 30,
    "message_format": "standard",
    "include_position": true,
    "include_timestamp": true,
    "max_message_length": 200,
    "auto_detect_device": true,
    "enable_encryption": true,
    "log_all_messages": false,
    "health_check_interval": 60
  }
}
```

### Configuration Parameters Reference

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `meshtastic_port` | string | "/dev/ttyUSB0" | Serial port for USB connection |
| `meshtastic_baud` | integer | 115200 | Serial baud rate |
| `channels` | array | [] | List of channel configurations |
| `default_channel` | string | "LongFast" | Default channel for alerts |
| `connection_mode` | string | "dual" | "serial", "mqtt", or "dual" |
| `failover_enabled` | boolean | true | Enable automatic failover |
| `connection_timeout` | integer | 10 | Connection timeout in seconds |
| `retry_interval` | integer | 30 | Retry interval in seconds |
| `message_format` | string | "standard" | "standard", "compact", or "json" |
| `include_position` | boolean | true | Include GPS coordinates |
| `include_timestamp` | boolean | true | Include timestamp |
| `max_message_length` | integer | 200 | Maximum message length |
| `auto_detect_device` | boolean | true | Auto-detect Meshtastic devices |
| `enable_encryption` | boolean | true | Enable PSK encryption |
| `log_all_messages` | boolean | false | Log all sent/received messages |
| `health_check_interval` | integer | 60 | Health check interval in seconds |
## Troubleshooting Guide

### Common Connection Issues

#### Serial Connection Problems

**Problem**: Device not found at `/dev/ttyUSB0`
```
Solution:
1. Check if device is connected: ls /dev/ttyUSB*
2. Check permissions: sudo chmod 666 /dev/ttyUSB0
3. Add user to dialout group: sudo usermod -a -G dialout $USER
4. Enable auto-detection: "auto_detect_device": true
```

**Problem**: Permission denied accessing serial port
```
Solution:
1. Add user to dialout group: sudo usermod -a -G dialout $USER
2. Log out and log back in
3. Or run with sudo (not recommended for production)
```

**Problem**: Device detected but communication fails
```
Solution:
1. Check baud rate matches device: usually 115200
2. Verify device firmware is compatible
3. Try different USB cable/port
4. Check device logs for errors
```

#### MQTT Connection Problems

**Problem**: Cannot connect to MQTT broker
```
Solution:
1. Verify broker URL and port
2. Check network connectivity: ping mqtt.meshtastic.org
3. Verify credentials if using authentication
4. Check firewall settings
5. Try different broker (mqtt.meshtastic.org vs custom)
```

**Problem**: MQTT connection drops frequently
```
Solution:
1. Increase keepalive interval: "keepalive": 120
2. Check network stability
3. Verify broker capacity and limits
4. Enable TLS if supported: "use_tls": true
```

**Problem**: Messages not appearing on MQTT
```
Solution:
1. Verify topic prefix matches your region: "msh/US"
2. Check QoS settings: try "qos": 1
3. Verify channel configuration matches devices
4. Check broker logs for errors
```

#### Channel Configuration Issues

**Problem**: Encrypted messages not working
```
Solution:
1. Verify PSK is Base64 encoded correctly
2. Ensure all devices use same PSK
3. Check channel numbers match across devices
4. Verify "enable_encryption": true
```

**Problem**: Messages sent to wrong channel
```
Solution:
1. Check "default_channel" setting
2. Verify channel names match exactly
3. Check channel_number configuration
4. Review alert routing logic
```

#### Device Detection Issues

**Problem**: Auto-detection not finding device
```
Solution:
1. Disable auto-detection: "auto_detect_device": false
2. Manually specify port: "meshtastic_port": "/dev/ttyUSB0"
3. Check USB device enumeration: lsusb
4. Verify device is in correct mode (not bootloader)
```

### Diagnostic Commands

#### Check Serial Devices
```bash
# List all USB serial devices
ls /dev/ttyUSB* /dev/ttyACM*

# Check device permissions
ls -la /dev/ttyUSB0

# Monitor serial communication
sudo screen /dev/ttyUSB0 115200
```

#### Test MQTT Connection
```bash
# Install MQTT clients
sudo apt install mosquitto-clients

# Test connection
mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/2/c/LongFast/+/+" -v

# Test publishing
mosquitto_pub -h mqtt.meshtastic.org -t "msh/US/2/c/LongFast/test" -m "Hello World"
```

#### Check System Logs
```bash
# Check system logs for USB events
dmesg | grep -i usb

# Check application logs
tail -f adsb_receiver.log

# Check MQTT broker logs (if running locally)
sudo journalctl -u mosquitto -f
```

### Performance Optimization

#### Message Throughput
```json
{
  "message_format": "compact",
  "max_message_length": 100,
  "include_position": false,
  "include_timestamp": false
}
```

#### Reliability Settings
```json
{
  "connection_mode": "dual",
  "failover_enabled": true,
  "retry_interval": 15,
  "health_check_interval": 30
}
```

#### Low Bandwidth Settings
```json
{
  "message_format": "compact",
  "max_message_length": 80,
  "log_all_messages": false,
  "mqtt": {
    "qos": 0,
    "keepalive": 300
  }
}
```

## Security Best Practices

### PSK Management

#### Generating Secure PSKs
```bash
# Generate cryptographically secure PSK
python3 -c "
import secrets
import base64
psk = secrets.token_bytes(32)
print('PSK (Base64):', base64.b64encode(psk).decode())
print('PSK (Hex):', psk.hex())
"
```

#### PSK Storage and Distribution
1. **Never store PSKs in plain text** in version control
2. **Use environment variables** for sensitive PSKs:
   ```bash
   export MESHTASTIC_PSK="your_base64_psk_here"
   ```
3. **Rotate PSKs regularly** (monthly/quarterly)
4. **Use different PSKs** for different purposes/groups
5. **Document PSK distribution** securely

#### Channel Security Recommendations
```json
{
  "channels": [
    {
      "name": "PublicInfo",
      "psk": null,
      "channel_number": 0
    },
    {
      "name": "PrivateAlerts",
      "psk": "secure_psk_here",
      "channel_number": 1,
      "uplink_enabled": true,
      "downlink_enabled": false
    }
  ]
}
```

### MQTT Security

#### Authentication
```json
{
  "mqtt": {
    "broker_url": "secure-broker.example.com",
    "port": 8883,
    "username": "adsb_user",
    "password": "secure_password",
    "use_tls": true,
    "client_id": "ursine_explorer_unique_id"
  }
}
```

#### TLS Configuration
1. **Always use TLS** for production: `"use_tls": true`
2. **Use port 8883** for TLS connections
3. **Verify certificates** when possible
4. **Use strong passwords** for MQTT authentication

### Network Security

#### Firewall Configuration
```bash
# Allow MQTT traffic (if running local broker)
sudo ufw allow 1883/tcp
sudo ufw allow 8883/tcp

# Restrict to specific IPs if possible
sudo ufw allow from 192.168.1.0/24 to any port 1883
```

#### VPN Recommendations
- Use VPN for remote MQTT broker connections
- Consider mesh VPN solutions for distributed deployments
- Isolate Meshtastic traffic on separate network segments

### Monitoring and Alerting

#### Security Monitoring
```json
{
  "log_all_messages": true,
  "health_check_interval": 30,
  "enable_security_logging": true
}
```

#### Alert on Security Events
- Failed authentication attempts
- Unexpected channel changes
- Encryption failures
- Unusual message patterns

## Migration from Legacy Configuration

### Automatic Migration

The system automatically detects and migrates legacy configurations:

**Legacy format**:
```json
{
  "meshtastic_enabled": true,
  "meshtastic_port": "/dev/ttyUSB0",
  "meshtastic_baud": 115200
}
```

**Migrated to**:
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
    "enable_encryption": false
  }
}
```

### Manual Migration Steps

1. **Backup existing configuration**:
   ```bash
   cp config.json config.json.backup
   ```

2. **Update configuration structure**:
   - Move `meshtastic_*` settings under `"meshtastic"` object
   - Add `"channels"` array with default channel
   - Set `"connection_mode"` to `"serial"`

3. **Test basic functionality** before adding advanced features

4. **Gradually add enhanced features**:
   - Add encrypted channels
   - Configure MQTT if needed
   - Enable dual-mode operation

### Validation

The system validates configuration on startup and provides helpful error messages:

```
[ERROR] Invalid Meshtastic configuration:
- PSK for channel 'SecureAlerts' is not valid Base64
- MQTT broker URL is required when connection_mode is 'mqtt'
- Channel number 1 is used by multiple channels

Suggestions:
- Generate PSK with: python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
- Set mqtt.broker_url to a valid MQTT broker
- Ensure each channel has a unique channel_number
```

## Support and Resources

### Documentation
- [Meshtastic Official Documentation](https://meshtastic.org/docs/)
- [MQTT Protocol Specification](https://mqtt.org/)
- [UrsineExplorer GitHub Repository](https://github.com/your-repo/ursine-explorer)

### Community
- [Meshtastic Discord](https://discord.gg/meshtastic)
- [Meshtastic Forum](https://meshtastic.discourse.group/)
- [Reddit r/meshtastic](https://reddit.com/r/meshtastic)

### Hardware Compatibility
- **Tested Devices**: HELTEC_V3, TBEAM, TLORA_V2
- **Firmware Requirements**: 2.0+ recommended
- **USB Requirements**: USB-C or Micro-USB cable

### Getting Help

1. **Check logs** first: `tail -f adsb_receiver.log`
2. **Verify configuration** with built-in validator
3. **Test with minimal configuration** first
4. **Check hardware connections** and permissions
5. **Search existing issues** in GitHub repository
6. **Create detailed bug report** with logs and configuration

For additional support, please open an issue in the GitHub repository with:
- Configuration file (with PSKs redacted)
- Log files showing the issue
- Hardware information
- Steps to reproduce the problem