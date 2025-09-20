# Ursine Explorer

A comprehensive ADS-B monitoring system powered by pyModeS that integrates dump1090 with HackRF One for real-time aircraft tracking, watchlist alerts via Meshtastic LoRa mesh, and a live terminal dashboard. Now featuring enhanced message decoding, improved position accuracy, and robust error handling.

## Features

- **Enhanced ADS-B decoding** powered by pyModeS library for improved reliability
- **Advanced position calculation** using CPR (Compact Position Reporting) algorithms
- **Multi-source data input** supporting dump1090, network streams, and various formats
- **Robust message validation** with CRC checking and error recovery
- **Enhanced aircraft tracking** with velocity, heading, and navigation accuracy data
- **Enhanced Meshtastic integration** with encrypted channels, MQTT connectivity, and dual-mode operation
- **Watchlist alerts** via Meshtastic LoRa mesh networking with intelligent throttling
- **Live terminal dashboard** with aircraft tracking and system status
- **Waterfall spectrum viewer** for frequency analysis
- **Comprehensive logging** and performance monitoring
- **Backward compatibility** with existing configurations and features
- **JSON API** for integration with other tools

## Hardware Requirements

- **Raspberry Pi** (3B+ or newer recommended) or compatible Linux system
- **HackRF One** SDR device or other dump1090-compatible receiver
- **ADS-B antenna** (1090 MHz)
- **Meshtastic device** (optional, for LoRa alerts)
- **Python 3.8+** with pip package manager

## Installation

### Prerequisites

Ensure you have Python 3.8+ installed:
```bash
python3 --version
pip3 --version
```

### Method 1: Automated Installation (Recommended)

1. **Clone and install:**
   ```bash
   git clone https://github.com/AugustWasilowski/ursine-explorer.git
   cd ursine-explorer
   chmod +x install.sh
   sudo ./install.sh
   ```

### Method 2: Manual Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AugustWasilowski/ursine-explorer.git
   cd ursine-explorer
   ```

2. **Install Python dependencies:**
   ```bash
   # Option A: Using virtual environment (recommended)
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   
   # Option B: System-wide installation
   pip3 install -r requirements.txt
   # Or on newer systems: pip install --break-system-packages -r requirements.txt
   ```

3. **Install system dependencies:**
   ```bash
   # Ubuntu/Debian
   sudo apt update
   sudo apt install hackrf libhackrf-dev dump1090-mutability
   
   # Fedora/RHEL
   sudo dnf install hackrf dump1090
   ```

### pyModeS Integration

The system now uses pyModeS (>=2.13.0) for enhanced ADS-B message decoding. This provides:
- Improved message validation with CRC checking
- Advanced CPR position decoding algorithms
- Enhanced aircraft data extraction (velocity, heading, navigation accuracy)
- Better error handling and recovery

## Configuration

1. **Basic configuration:**
   ```bash
   nano config.json
   ```
   
   Essential settings:
   - `target_icao_codes`: Array of ICAO codes to monitor (e.g., `["A12345", "B67890"]`)
   - `meshtastic_port`: Serial port for Meshtastic device (e.g., `"/dev/ttyUSB0"`)
   - `frequency`: ADS-B frequency (default: `1090100000` Hz)
   - `lna_gain`/`vga_gain`: HackRF gain settings

2. **Enhanced Meshtastic configuration:**
   ```json
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
               "psk": "your_base64_psk_here",
               "channel_number": 1
           }
       ],
       "default_channel": "SecureAlerts",
       "connection_mode": "dual",
       "mqtt": {
           "broker_url": "mqtt.meshtastic.org",
           "port": 1883,
           "topic_prefix": "msh/US"
       },
       "enable_encryption": true,
       "message_format": "standard"
   }
   ```

2. **pyModeS-specific settings:**
   ```json
   "pymodes": {
       "enabled": true,
       "reference_position": {
           "latitude": 40.7128,
           "longitude": -74.0060
       },
       "cpr_settings": {
           "global_position_timeout": 10,
           "local_position_range_nm": 180
       }
   }
   ```

3. **Message source configuration:**
   ```json
   "message_sources": [
       {
           "name": "dump1090_primary",
           "type": "dump1090",
           "enabled": true,
           "host": "localhost",
           "port": 30005,
           "format": "beast"
       }
   ]
   ```

## Quick Start

1. **Start the system:**
   ```bash
   # If using virtual environment
   source venv/bin/activate
   
   # Start the ADS-B receiver
   python3 adsb_receiver.py
   
   # In another terminal, start the dashboard
   python3 adsb_dashboard.py
   
   # Optional: Start the waterfall viewer
   python3 waterfall_viewer.py
   ```

## Configuration Options

### Core Settings

| Option | Description | Default |
|--------|-------------|---------|
| `target_icao_codes` | Array of ICAO codes to monitor | `[]` |
| `meshtastic_port` | Serial port for Meshtastic device | `"/dev/ttyUSB0"` |
| `meshtastic_baud` | Meshtastic baud rate | `115200` |
| `dump1090_host` | dump1090 server host | `"localhost"` |
| `dump1090_port` | dump1090 Beast TCP port | `30005` |
| `frequency` | ADS-B frequency in Hz | `1090100000` |
| `lna_gain` | HackRF LNA gain (0-40 dB) | `40` |
| `vga_gain` | HackRF VGA gain (0-62 dB) | `20` |
| `enable_hackrf_amp` | Enable HackRF amplifier | `true` |
| `alert_interval_sec` | Cooldown between alerts (seconds) | `300` |
| `log_alerts` | Log alerts to file | `true` |
| `alert_log_file` | Alert log filename | `"alerts.log"` |
| `watchdog_timeout_sec` | Auto-restart timeout | `60` |
| `poll_interval_sec` | Data update interval | `1` |

### pyModeS Integration Settings

| Option | Description | Default |
|--------|-------------|---------|
| `pymodes.enabled` | Enable pyModeS integration | `true` |
| `pymodes.reference_position.latitude` | Reference latitude for local CPR | `null` |
| `pymodes.reference_position.longitude` | Reference longitude for local CPR | `null` |
| `pymodes.cpr_settings.global_position_timeout` | Timeout for global CPR (seconds) | `10` |
| `pymodes.cpr_settings.local_position_range_nm` | Local CPR range (nautical miles) | `180` |
| `pymodes.message_validation.enable_crc_check` | Enable CRC validation | `true` |
| `pymodes.message_validation.enable_format_validation` | Enable format validation | `true` |
| `pymodes.decoder_settings.supported_message_types` | Supported DF types | `["DF4", "DF5", "DF17", "DF18", "DF20", "DF21"]` |

### Message Sources

| Option | Description | Default |
|--------|-------------|---------|
| `message_sources[].name` | Source identifier | `"dump1090_primary"` |
| `message_sources[].type` | Source type (dump1090, network) | `"dump1090"` |
| `message_sources[].enabled` | Enable this source | `true` |
| `message_sources[].host` | Source hostname | `"localhost"` |
| `message_sources[].port` | Source port | `30005` |
| `message_sources[].format` | Data format (beast, raw, json) | `"beast"` |

### Aircraft Tracking

| Option | Description | Default |
|--------|-------------|---------|
| `aircraft_tracking.aircraft_timeout_sec` | Aircraft removal timeout | `300` |
| `aircraft_tracking.position_timeout_sec` | Position data timeout | `60` |
| `aircraft_tracking.max_aircraft_count` | Maximum tracked aircraft | `10000` |
| `aircraft_tracking.enable_data_validation` | Enable data validation | `true` |
| `aircraft_tracking.conflict_resolution` | Conflict resolution strategy | `"newest_wins"` |

### Enhanced Meshtastic Settings

| Option | Description | Default |
|--------|-------------|---------|
| `meshtastic.channels` | Array of channel configurations | `[]` |
| `meshtastic.default_channel` | Default channel for alerts | `"LongFast"` |
| `meshtastic.connection_mode` | Connection mode: "serial", "mqtt", "dual" | `"dual"` |
| `meshtastic.failover_enabled` | Enable automatic failover | `true` |
| `meshtastic.enable_encryption` | Enable PSK encryption | `true` |
| `meshtastic.message_format` | Message format: "standard", "compact", "json" | `"standard"` |
| `meshtastic.mqtt.broker_url` | MQTT broker URL | `"mqtt.meshtastic.org"` |
| `meshtastic.mqtt.port` | MQTT broker port | `1883` |
| `meshtastic.mqtt.use_tls` | Enable TLS for MQTT | `false` |
| `meshtastic.mqtt.topic_prefix` | MQTT topic prefix | `"msh/US"` |
| `meshtastic.auto_detect_device` | Auto-detect Meshtastic devices | `true` |
| `meshtastic.health_check_interval` | Health check interval (seconds) | `60` |

## System Components

### Enhanced ADS-B Receiver (`adsb_receiver.py`)
- **pyModeS-powered decoding** for improved message processing reliability
- **Multi-source support** for dump1090, network streams, and various data formats
- **Advanced position calculation** using CPR algorithms with global/local positioning
- **Comprehensive message validation** with CRC checking and format verification
- **Enhanced aircraft tracking** with velocity, heading, and navigation accuracy
- **Intelligent alert system** with throttling and deduplication
- **Robust error handling** and automatic recovery
- **Performance monitoring** and detailed logging
- **HTTP API** with enhanced aircraft data and system status

### Live Dashboard (`adsb_dashboard.py`)
- Real-time terminal interface using curses
- **Enhanced aircraft display** with additional pyModeS data fields:
  - True/Indicated airspeed, Mach number
  - Magnetic heading and roll angle
  - Navigation accuracy indicators
  - Data quality metrics
- Shows system status (dump1090, Meshtastic, pyModeS decoder)
- Highlights watchlist aircraft in green
- Interactive menu for HackRF configuration
- **Performance metrics** display (decode rates, message statistics)
- Waterfall display option

### Waterfall Viewer (`waterfall_viewer.py`)
- Spectrum analysis display
- Shows frequency content over time
- Focuses on ADS-B frequency range (1090 MHz)
- Real-time updates via HTTP API

### pyModeS Integration Layer
- **Message Source Manager**: Handles multiple simultaneous data sources
- **Enhanced Decoder**: Wraps pyModeS with UrsineExplorer-specific logic
- **Aircraft Tracker**: Advanced aircraft lifecycle and data management
- **Position Calculator**: CPR-based position decoding with reference positioning
- **Watchlist Monitor**: Improved pattern matching and alert management

## Finding ICAO Codes

You can find aircraft ICAO codes using:
- **FlightRadar24**: Look up the aircraft registration
- **FlightAware**: Search by tail number or flight
- **Online databases**: Like airframes.org
- **Live monitoring**: Watch your dashboard for detected aircraft

## API Endpoints

The system provides HTTP APIs on port 8080:

### Data Endpoints
- `GET /data/aircraft.json` - Enhanced aircraft data with pyModeS fields
- `GET /data/fft.json` - FFT data for waterfall viewer
- `GET /data/status.json` - System status and performance metrics
- `GET /data/stats.json` - Message processing statistics

### Enhanced Aircraft Data Format
The `/data/aircraft.json` endpoint now includes additional fields from pyModeS:

```json
{
  "aircraft": [
    {
      "icao": "A12345",
      "callsign": "UAL123",
      "latitude": 40.7128,
      "longitude": -74.0060,
      "altitude_baro": 35000,
      "altitude_gnss": 35100,
      "ground_speed": 450.5,
      "track_angle": 270.0,
      "vertical_rate": 0,
      "true_airspeed": 465.2,
      "indicated_airspeed": 280.0,
      "mach_number": 0.78,
      "magnetic_heading": 268.5,
      "roll_angle": -2.1,
      "navigation_accuracy": {
        "horizontal": 10.0,
        "vertical": 15.0
      },
      "surveillance_status": "ADS-B",
      "message_count": 156,
      "first_seen": "2024-01-15T10:30:00Z",
      "last_seen": "2024-01-15T10:35:00Z",
      "is_watchlist": false,
      "data_sources": ["dump1090_primary"]
    }
  ],
  "stats": {
    "total_aircraft": 25,
    "messages_per_second": 120.5,
    "decode_success_rate": 98.2,
    "position_success_rate": 85.7
  }
}
```

### Control Commands
Control commands via TCP on port 8081:
- `PING` - Test connection
- `GET_STATUS` - Get detailed system status
- `GET_STATS` - Get performance statistics
- `RESTART_DUMP1090` - Restart dump1090 process
- `RELOAD_CONFIG` - Reload configuration without restart
- `CLEAR_AIRCRAFT` - Clear aircraft database

## Monitoring and Troubleshooting

**Check system status:**
```bash
# View receiver logs
tail -f adsb_receiver.log

# Check if dump1090 is running
ps aux | grep dump1090

# Test Meshtastic connection
python3 -c "import serial; print('Meshtastic port available')"
```

**Test components:**
```bash
# Test receiver
python3 adsb_receiver.py

# Test dashboard
python3 adsb_dashboard.py

# Test waterfall viewer
python3 waterfall_viewer.py
```

**Check JSON data:**
```bash
# View aircraft data
curl http://localhost:8080/data/aircraft.json

# View FFT data
curl http://localhost:8080/data/fft.json
```

## Enhanced Alert System

When a watchlist aircraft is detected:
1. **Enhanced Meshtastic alerts** sent via encrypted channels and/or MQTT
2. **Multi-interface delivery** with automatic failover between serial and MQTT
3. **Delivery confirmation** and retry logic for reliable message transmission
4. **Log entry** written to `alerts.log` with delivery status
5. **Dashboard highlight** shows aircraft in green
6. **Intelligent throttling** prevents spam (default: 5 minutes per aircraft)

### Alert Formats

**Standard format:**
```
ALERT: N12345 (UAL123) WATCHLIST 
Pos: 40.7128,-74.0060 Alt: 35000ft
Speed: 450kts Hdg: 090° 
Time: 2024-01-15 14:30:25Z
```

**Compact format:**
```
ALERT: N12345 WATCHLIST 40.71,-74.01 35k 450kt 090°
```

**JSON format:**
```json
{"icao":"N12345","callsign":"UAL123","alert":"WATCHLIST","lat":40.7128,"lon":-74.0060,"alt":35000,"speed":450,"heading":90,"time":"2024-01-15T14:30:25Z"}
```

### Connection Modes

- **Serial Mode**: Direct USB connection to Meshtastic device
- **MQTT Mode**: Network connection via MQTT broker
- **Dual Mode**: Both serial and MQTT with automatic failover
- **Encrypted Channels**: PSK-based encryption for secure communication

## Dashboard Controls

- `q` - Quit dashboard
- `m` - Open configuration menu
- `w` - Toggle waterfall display
- `s` - Cycle sort options (last_seen, altitude, speed, flight, hex)
- `r` - Reverse sort order
- `Space` - Force refresh

## Waterfall Controls

- `q` - Quit waterfall viewer
- `r` - Reset display
- `+/-` - Adjust scale
- `Space` - Pause/resume

## Hardware Setup

1. **Connect HackRF One** to Raspberry Pi via USB
2. **Install ADS-B antenna** (1090 MHz, vertical polarization)
3. **Connect Meshtastic device** (optional) to USB serial port
4. **Position antenna** outdoors, elevated, clear line of sight

## Performance Tuning

- **Gain settings**: Adjust `lna_gain` and `vga_gain` for optimal signal
- **Frequency correction**: Use `ppm` setting if needed
- **Update intervals**: Adjust `poll_interval_sec` for performance
- **Watchdog timeout**: Increase `watchdog_timeout_sec` if needed

## Security Notes

- The system runs with standard user privileges
- Network access limited to localhost and Meshtastic
- No external network dependencies (except Meshtastic mesh)
- Alert logs contain only aircraft information

## Customization

You can extend the system by:
- Adding new alert channels (email, SMS, webhooks)
- Implementing geofencing based on aircraft position
- Creating custom dashboard layouts
- Adding flight path tracking
- Integrating with other ADS-B databases

## Troubleshooting

### Installation Issues

**pyModeS installation fails:**
```bash
# Try upgrading pip first
pip3 install --upgrade pip

# Install with specific version
pip3 install pyModeS==2.13.0

# On newer systems, use break-system-packages
pip3 install --break-system-packages pyModeS>=2.13.0

# Check installation
python3 -c "import pyModeS; print(pyModeS.__version__)"
```

**Missing system dependencies:**
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install python3-dev python3-pip libhackrf-dev

# Fedora/RHEL
sudo dnf install python3-devel python3-pip hackrf-devel

# Check HackRF installation
hackrf_info
```

### Runtime Issues

**No aircraft detected:**
- Check HackRF connection: `hackrf_info`
- Verify antenna connection and positioning
- Check dump1090 logs for errors: `tail -f adsb_receiver.log`
- Ensure proper gain settings in config.json
- Verify pyModeS is processing messages: look for "pyModeS decoder" in logs

**pyModeS decoding errors:**
```bash
# Check for CRC validation errors in logs
grep "CRC" adsb_receiver.log

# Verify message format validation
grep "format_validation" adsb_receiver.log

# Test pyModeS directly
python3 -c "
import pyModeS as pms
msg = '8D40621D58C382D690C8AC2863A7'  # Example message
print('ICAO:', pms.icao(msg))
print('Valid CRC:', pms.crc(msg, encode=False) == 0)
"
```

**Position calculation issues:**
- Check reference position in config.json (set your approximate location)
- Verify CPR timeout settings aren't too restrictive
- Look for "CPR" errors in logs
- Ensure both even/odd position messages are being received

**Message source connection problems:**
```bash
# Test dump1090 connection
telnet localhost 30005

# Check message source status in logs
grep "MessageSource" adsb_receiver.log

# Verify network connectivity
netstat -an | grep 30005
```

**High memory usage:**
- Reduce `aircraft_tracking.max_aircraft_count`
- Increase `aircraft_tracking.aircraft_timeout_sec` for faster cleanup
- Enable garbage collection: set `performance.gc_interval_sec` to lower value
- Monitor with: `grep "memory" adsb_receiver.log`

### Performance Issues

**Slow message processing:**
- Increase `performance.message_batch_size` (default: 100)
- Reduce `performance.processing_interval_ms` (default: 100)
- Check CPU usage: `top -p $(pgrep -f adsb_receiver)`
- Enable profiling: set `performance.enable_profiling` to `true`

**Dashboard lag:**
- Increase `poll_interval_sec` to reduce update frequency
- Check for network connectivity issues to API
- Verify sufficient system resources

### Alert System Issues

**Enhanced Meshtastic alerts not working:**
- Verify serial port: `ls /dev/ttyUSB*`
- Check baud rate settings match device
- Test Meshtastic device independently
- Review alert logs: `tail -f alerts.log`
- Check alert throttling settings
- **For encrypted channels**: Verify PSK configuration matches devices
- **For MQTT mode**: Test broker connectivity: `mosquitto_sub -h mqtt.meshtastic.org -t "msh/US/+/+/+/+"`
- **For dual mode**: Check failover logs for interface switching
- **Channel configuration**: Verify channel numbers and names match device settings

**Watchlist not triggering:**
- Verify ICAO codes are correct (uppercase, no spaces)
- Check `watchlist.enabled` is `true`
- Review watchlist configuration in logs
- Test with known aircraft: add currently visible aircraft to watchlist

### Configuration Issues

**Config validation errors:**
```bash
# Validate config file
python3 -c "
import json
with open('config.json') as f:
    config = json.load(f)
print('Config loaded successfully')
"

# Check for required fields
python3 config_validator.py
```

**Migration from old config:**
- Backup your current config: `cp config.json config.json.backup`
- The system will automatically migrate old format configs
- Check logs for migration messages
- Compare with example config for new options

### Diagnostic Commands

**System health check:**
```bash
# Check all processes
ps aux | grep -E "(adsb_receiver|dump1090|hackrf)"

# Check log files
ls -la *.log

# Test API endpoints
curl -s http://localhost:8080/data/aircraft.json | jq length
curl -s http://localhost:8080/data/status.json

# Check pyModeS integration
python3 -c "
from pymodes_integration import decoder
d = decoder.PyModeSDecode()
print('pyModeS decoder initialized successfully')
"
```

**Performance monitoring:**
```bash
# Monitor message rates
grep "messages/sec" adsb_receiver.log | tail -10

# Check decode success rates
grep "decode_rate" adsb_receiver.log | tail -10

# Monitor memory usage
grep "memory_usage" adsb_receiver.log | tail -10
```

### Getting Help

If you encounter issues not covered here:

1. **Check logs:** Always review `adsb_receiver.log` for detailed error messages
2. **Enable debug logging:** Set `logging.level` to `"DEBUG"` in config.json
3. **Test components individually:** Run each component separately to isolate issues
4. **Check GitHub issues:** Search for similar problems in the project repository
5. **Provide details:** When reporting issues, include:
   - System information (OS, Python version)
   - Complete error messages from logs
   - Configuration file (remove sensitive data)
   - Steps to reproduce the problem

## Enhanced Meshtastic Documentation

For detailed information about the enhanced Meshtastic features:

- **[Enhanced Meshtastic Configuration Guide](ENHANCED_MESHTASTIC_CONFIG_GUIDE.md)** - Complete setup and configuration guide
- **[Meshtastic Configuration Examples](MESHTASTIC_CONFIG_EXAMPLES.md)** - Ready-to-use configuration examples for different scenarios
- **[Meshtastic Migration Guide](MESHTASTIC_MIGRATION_GUIDE.md)** - Step-by-step migration from legacy configurations
- **[Enhanced Meshtastic API Documentation](ENHANCED_MESHTASTIC_API.md)** - Complete API reference for developers

### Quick Links

- **Encrypted Channels**: See [Configuration Guide](ENHANCED_MESHTASTIC_CONFIG_GUIDE.md#channel-configuration) for PSK setup
- **MQTT Integration**: See [MQTT Setup](ENHANCED_MESHTASTIC_CONFIG_GUIDE.md#mqtt-broker-setup) for broker configuration
- **Dual-Mode Operation**: See [Connection Modes](ENHANCED_MESHTASTIC_CONFIG_GUIDE.md#connection-modes) for serial + MQTT
- **Troubleshooting**: See [Troubleshooting Guide](ENHANCED_MESHTASTIC_CONFIG_GUIDE.md#troubleshooting-guide) for common issues
- **Migration**: See [Migration Guide](MESHTASTIC_MIGRATION_GUIDE.md) for upgrading existing setups

## License

This project is open source. See LICENSE file for details.

## Contributing

Contributions welcome! Please submit issues and pull requests on GitHub.