# Meshtastic Migration Guide

This guide helps users migrate from the legacy Meshtastic integration to the enhanced version with encrypted channels, MQTT connectivity, and dual-mode operation.

## Overview

The enhanced Meshtastic integration maintains full backward compatibility while adding powerful new features:

- **Encrypted channels** with PSK-based security
- **MQTT connectivity** for network-based mesh access
- **Dual-mode operation** with automatic failover
- **Enhanced message formatting** with multiple output formats
- **Improved diagnostics** and monitoring
- **Better error handling** and recovery

## Migration Process

### Step 1: Backup Current Configuration

Before starting the migration, backup your existing configuration:

```bash
# Backup your current config
cp config.json config.json.backup

# Backup any custom settings
cp -r .kiro .kiro.backup 2>/dev/null || true
```

### Step 2: Understand Configuration Changes

#### Legacy Configuration Format

```json
{
  "meshtastic_enabled": true,
  "meshtastic_port": "/dev/ttyUSB0",
  "meshtastic_baud": 115200,
  "target_icao_codes": ["A12345", "B67890"],
  "alert_interval_sec": 300
}
```

#### Enhanced Configuration Format

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
  },
  "target_icao_codes": ["A12345", "B67890"],
  "alert_interval_sec": 300
}
```

### Step 3: Automatic Migration

The system automatically detects and migrates legacy configurations. When you start the system with a legacy configuration, it will:

1. **Detect legacy format** and create a backup
2. **Migrate settings** to the new structure
3. **Preserve all existing functionality**
4. **Log the migration process**

#### Migration Log Example

```
[INFO] Legacy Meshtastic configuration detected
[INFO] Creating backup: config.json.pre-migration
[INFO] Migrating configuration to enhanced format
[INFO] Migration completed successfully
[INFO] Enhanced Meshtastic features now available
```

### Step 4: Manual Migration (Optional)

If you prefer to migrate manually or want to customize the process:

#### 4.1 Basic Manual Migration

```bash
# Create a new configuration section
python3 -c "
import json

# Load existing config
with open('config.json', 'r') as f:
    config = json.load(f)

# Extract legacy settings
legacy_port = config.get('meshtastic_port', '/dev/ttyUSB0')
legacy_baud = config.get('meshtastic_baud', 115200)
legacy_enabled = config.get('meshtastic_enabled', True)

# Create enhanced configuration
if legacy_enabled:
    config['meshtastic'] = {
        'meshtastic_port': legacy_port,
        'meshtastic_baud': legacy_baud,
        'channels': [
            {
                'name': 'LongFast',
                'psk': None,
                'channel_number': 0
            }
        ],
        'default_channel': 'LongFast',
        'connection_mode': 'serial',
        'enable_encryption': False,
        'message_format': 'standard',
        'auto_detect_device': True,
        'failover_enabled': False
    }

# Remove legacy settings
for key in ['meshtastic_enabled', 'meshtastic_port', 'meshtastic_baud']:
    config.pop(key, None)

# Save updated configuration
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)

print('Manual migration completed')
"
```

#### 4.2 Enhanced Manual Migration with New Features

```bash
# Create enhanced configuration with new features
python3 -c "
import json
import secrets
import base64

# Load existing config
with open('config.json', 'r') as f:
    config = json.load(f)

# Generate a secure PSK for encrypted channel
psk = base64.b64encode(secrets.token_bytes(32)).decode()

# Create enhanced configuration with encryption and MQTT
config['meshtastic'] = {
    'meshtastic_port': config.get('meshtastic_port', '/dev/ttyUSB0'),
    'meshtastic_baud': config.get('meshtastic_baud', 115200),
    'channels': [
        {
            'name': 'LongFast',
            'psk': None,
            'channel_number': 0
        },
        {
            'name': 'SecureAlerts',
            'psk': psk,
            'channel_number': 1
        }
    ],
    'default_channel': 'SecureAlerts',
    'connection_mode': 'dual',
    'mqtt': {
        'broker_url': 'mqtt.meshtastic.org',
        'port': 1883,
        'topic_prefix': 'msh/US',
        'client_id': 'ursine_explorer_enhanced'
    },
    'enable_encryption': True,
    'message_format': 'standard',
    'auto_detect_device': True,
    'failover_enabled': True,
    'include_position': True,
    'include_timestamp': True
}

# Remove legacy settings
for key in ['meshtastic_enabled', 'meshtastic_port', 'meshtastic_baud']:
    config.pop(key, None)

# Save configuration
with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)

print('Enhanced migration completed')
print(f'Generated PSK: {psk}')
print('IMPORTANT: Save this PSK securely and configure your Meshtastic devices with it')
"
```

## Migration Scenarios

### Scenario 1: Simple Upgrade (No Changes)

**Goal**: Upgrade to enhanced system without changing functionality

**Before**:
```json
{
  "meshtastic_enabled": true,
  "meshtastic_port": "/dev/ttyUSB0",
  "meshtastic_baud": 115200
}
```

**After** (Automatic Migration):
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

**Result**: System works exactly as before with enhanced reliability and diagnostics.

### Scenario 2: Add Encryption

**Goal**: Add encrypted communication while maintaining serial connection

**Steps**:
1. Let automatic migration complete
2. Generate PSK: `python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"`
3. Add encrypted channel to configuration
4. Configure Meshtastic device with same PSK

**Enhanced Configuration**:
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
        "psk": "your_generated_psk_here",
        "channel_number": 1
      }
    ],
    "default_channel": "SecureAlerts",
    "connection_mode": "serial",
    "enable_encryption": true
  }
}
```

### Scenario 3: Add MQTT Connectivity

**Goal**: Add MQTT connectivity for network-based mesh access

**Steps**:
1. Complete basic migration
2. Add MQTT configuration
3. Set connection mode to "dual"
4. Enable failover

**Enhanced Configuration**:
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
    "connection_mode": "dual",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_mqtt"
    },
    "failover_enabled": true
  }
}
```

### Scenario 4: Full Enhancement

**Goal**: Utilize all new features (encryption, MQTT, multiple channels)

**Enhanced Configuration**:
```json
{
  "meshtastic": {
    "meshtastic_port": "/dev/ttyUSB0",
    "meshtastic_baud": 115200,
    "channels": [
      {
        "name": "PublicAlerts",
        "psk": null,
        "channel_number": 0
      },
      {
        "name": "WatchlistAlerts",
        "psk": "watchlist_psk_here",
        "channel_number": 1
      },
      {
        "name": "EmergencyAlerts",
        "psk": "emergency_psk_here",
        "channel_number": 2
      }
    ],
    "default_channel": "WatchlistAlerts",
    "connection_mode": "dual",
    "mqtt": {
      "broker_url": "mqtt.meshtastic.org",
      "port": 1883,
      "topic_prefix": "msh/US",
      "client_id": "ursine_explorer_full"
    },
    "enable_encryption": true,
    "message_format": "standard",
    "failover_enabled": true,
    "include_position": true,
    "include_timestamp": true,
    "auto_detect_device": true,
    "health_check_interval": 60
  }
}
```

## Post-Migration Steps

### Step 1: Verify Configuration

```bash
# Test configuration validity
python3 -c "
import json
from pymodes_integration.meshtastic_enhanced import MeshtasticConfig

with open('config.json') as f:
    config = json.load(f)

try:
    meshtastic_config = MeshtasticConfig(**config['meshtastic'])
    print('✓ Configuration is valid')
except Exception as e:
    print(f'✗ Configuration error: {e}')
"
```

### Step 2: Test Basic Functionality

```bash
# Start the system and check logs
python3 adsb_receiver.py &
RECEIVER_PID=$!

# Wait a few seconds and check logs
sleep 5
tail -20 adsb_receiver.log

# Look for successful initialization messages
grep -i "meshtastic.*initialized" adsb_receiver.log

# Stop the test
kill $RECEIVER_PID
```

### Step 3: Configure Meshtastic Devices

If you added encrypted channels, configure your Meshtastic devices:

#### Using Meshtastic CLI
```bash
# Install Meshtastic CLI
pip install meshtastic

# Configure encrypted channel
meshtastic --port /dev/ttyUSB0 --ch-set name "SecureAlerts" --ch-index 1
meshtastic --port /dev/ttyUSB0 --ch-set psk "your_base64_psk_here" --ch-index 1
```

#### Using Meshtastic App
1. Connect to your device via Bluetooth or USB
2. Go to Channel settings
3. Add new channel with same name and PSK
4. Set channel number to match configuration

### Step 4: Test Enhanced Features

#### Test Encrypted Messaging
```bash
# Send test alert to verify encryption works
python3 -c "
from pymodes_integration.meshtastic_enhanced import MeshtasticManager
import json

with open('config.json') as f:
    config = json.load(f)

manager = MeshtasticManager(config['meshtastic'])
if manager.initialize():
    print('✓ Enhanced Meshtastic initialized successfully')
    
    # Test connectivity
    status = manager.test_connectivity()
    for interface, result in status.items():
        print(f'  {interface}: {\"✓\" if result else \"✗\"}')
else:
    print('✗ Initialization failed')
"
```

#### Test MQTT Connectivity (if configured)
```bash
# Test MQTT broker connection
mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/+/+/+/+" -v &
MQTT_PID=$!

# Send test message
python3 -c "
import json
from pymodes_integration.meshtastic_enhanced import MeshtasticMQTTInterface, MQTTConfig, ChannelManager, ChannelConfig

with open('config.json') as f:
    config = json.load(f)

if 'mqtt' in config['meshtastic']:
    mqtt_config = MQTTConfig(**config['meshtastic']['mqtt'])
    channels = [ChannelConfig(**ch) for ch in config['meshtastic']['channels']]
    channel_manager = ChannelManager(channels)
    
    mqtt_interface = MeshtasticMQTTInterface(mqtt_config, channel_manager)
    if mqtt_interface.connect():
        mqtt_interface.send_message('Test message from UrsineExplorer migration', 'LongFast')
        print('✓ MQTT test message sent')
    else:
        print('✗ MQTT connection failed')
"

# Stop MQTT monitoring
kill $MQTT_PID
```

## Troubleshooting Migration Issues

### Issue 1: Configuration Validation Errors

**Error**: `Invalid channel configuration`

**Solution**:
```bash
# Check channel configuration
python3 -c "
import json
from pymodes_integration.meshtastic_enhanced import ChannelConfig

with open('config.json') as f:
    config = json.load(f)

for ch_config in config['meshtastic']['channels']:
    try:
        channel = ChannelConfig(**ch_config)
        print(f'✓ Channel {channel.name} is valid')
    except Exception as e:
        print(f'✗ Channel {ch_config.get(\"name\", \"unknown\")} error: {e}')
"
```

### Issue 2: PSK Format Errors

**Error**: `Invalid PSK format`

**Solution**:
```bash
# Validate and regenerate PSK
python3 -c "
import base64
import secrets

# Generate new PSK
psk = base64.b64encode(secrets.token_bytes(32)).decode()
print(f'New PSK: {psk}')

# Validate existing PSK
existing_psk = 'your_existing_psk_here'
try:
    decoded = base64.b64decode(existing_psk)
    if len(decoded) == 32:
        print('✓ Existing PSK is valid')
    else:
        print(f'✗ PSK length is {len(decoded)}, should be 32 bytes')
except Exception as e:
    print(f'✗ PSK decode error: {e}')
"
```

### Issue 3: MQTT Connection Problems

**Error**: `MQTT broker connection failed`

**Solution**:
```bash
# Test MQTT broker connectivity
mosquitto_pub -h mqtt.meshtastic.org -t "test/topic" -m "test message"

# If that fails, check network connectivity
ping mqtt.meshtastic.org

# Test with different broker
mosquitto_pub -h test.mosquitto.org -t "test/topic" -m "test message"
```

### Issue 4: Serial Device Not Found

**Error**: `Serial device not found at /dev/ttyUSB0`

**Solution**:
```bash
# List available serial devices
ls /dev/ttyUSB* /dev/ttyACM*

# Check device permissions
ls -la /dev/ttyUSB0

# Add user to dialout group
sudo usermod -a -G dialout $USER

# Enable auto-detection in config
python3 -c "
import json

with open('config.json') as f:
    config = json.load(f)

config['meshtastic']['auto_detect_device'] = True

with open('config.json', 'w') as f:
    json.dump(config, f, indent=2)

print('Auto-detection enabled')
"
```

## Rollback Procedure

If you need to rollback to the legacy configuration:

### Step 1: Restore Backup

```bash
# Restore original configuration
cp config.json.backup config.json

# Restore any other backups
cp -r .kiro.backup .kiro 2>/dev/null || true
```

### Step 2: Restart System

```bash
# Restart with legacy configuration
python3 adsb_receiver.py
```

### Step 3: Verify Legacy Operation

```bash
# Check that legacy Meshtastic is working
tail -f adsb_receiver.log | grep -i meshtastic
```

## Migration Checklist

- [ ] **Backup created**: `config.json.backup` exists
- [ ] **Configuration migrated**: New `meshtastic` section present
- [ ] **Legacy settings removed**: Old `meshtastic_*` keys removed
- [ ] **Configuration validated**: No validation errors
- [ ] **Basic functionality tested**: System starts and connects
- [ ] **Meshtastic devices configured**: PSKs and channels match
- [ ] **MQTT tested** (if configured): Broker connection works
- [ ] **Alerts tested**: Watchlist alerts are delivered
- [ ] **Logs reviewed**: No error messages in logs
- [ ] **Documentation updated**: Team informed of new features

## Getting Help

If you encounter issues during migration:

1. **Check logs**: Review `adsb_receiver.log` for detailed error messages
2. **Validate configuration**: Use the built-in configuration validator
3. **Test components individually**: Test serial and MQTT separately
4. **Review examples**: Check `MESHTASTIC_CONFIG_EXAMPLES.md` for reference
5. **Consult troubleshooting**: See `ENHANCED_MESHTASTIC_CONFIG_GUIDE.md`
6. **Seek support**: Open an issue in the GitHub repository

## Benefits After Migration

After successful migration, you'll have access to:

- **Enhanced reliability** with automatic failover
- **Encrypted communication** for secure alerts
- **MQTT connectivity** for network-based mesh access
- **Better diagnostics** and monitoring
- **Flexible message formatting** options
- **Improved error handling** and recovery
- **Future-proof architecture** for new features

The migration process is designed to be safe and reversible, ensuring your existing functionality continues to work while providing access to powerful new capabilities.