# Ursine Capture - ADS-B Monitoring System

A simplified, reliable ADS-B monitoring system with Meshtastic integration and live terminal dashboard.

## Overview

Ursine Capture is a complete rewrite of the Ursine Explorer system, designed for simplicity and reliability. It consists of just 6 core Python files that provide:

- **ADS-B Reception**: Automatic dump1090 management and HackRF control
- **Aircraft Tracking**: Real-time aircraft monitoring with watchlist support
- **Meshtastic Integration**: Automatic alerts for watchlist aircraft
- **Live Dashboard**: Terminal-based UI with aircraft list, waterfall display, and controls

## Quick Start

### 1. Installation

#### One-Command Installation

```bash
./install.sh
```

The installer will:
- Install all Python dependencies (pyModeS, psutil, meshtastic, etc.)
- Set up dump1090-fa for ADS-B decoding
- Configure HackRF drivers and permissions
- Create initial configuration file with hardware detection
- Verify all components work

#### Installation Options

```bash
./install.sh --test-mode        # Run without making system changes
./install.sh --verify-only      # Only verify existing installation
./install.sh --detect-hardware  # Only detect and report hardware
```

#### Manual Installation (if needed)

```bash
# Install system packages (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install python3 python3-pip dump1090-fa hackrf libhackrf-dev

# Install Python dependencies
pip install -r requirements.txt

# Add user to plugdev group for USB access
sudo usermod -a -G plugdev $USER
```

### 2. Basic Usage

Start the complete system:
```bash
./start-ursine-capture.sh
```

Or start components individually:
```bash
# Start receiver only (background process)
python3 start-receiver.py

# Start dashboard only (requires receiver to be running)
python3 start-dashboard.py
```

### 3. Dashboard Controls

Once the dashboard is running:
- **Arrow Keys**: Navigate aircraft list
- **M**: Open main menu
- **W**: Manage watchlist
- **R**: Radio settings
- **Enter**: Add selected aircraft to watchlist
- **Q**: Quit

## System Requirements

### Hardware
- **Computer**: Raspberry Pi 4 or similar Linux system
- **SDR**: HackRF One (other SDRs may work with configuration changes)
- **Antenna**: ADS-B antenna (1090 MHz)
- **Meshtastic Device**: Any compatible Meshtastic radio (optional)

### Software
- **OS**: Linux (tested on Raspberry Pi OS)
- **Python**: 3.7 or newer
- **Dependencies**: Installed automatically by installer.py

## Configuration

The system uses a single `config.json` file for all settings:

```json
{
  "radio": {
    "frequency": 1090100000,
    "lna_gain": 40,
    "vga_gain": 20,
    "enable_amp": true
  },
  "meshtastic": {
    "port": "/dev/ttyUSB0",
    "baud": 115200,
    "channel": 2
  },
  "receiver": {
    "dump1090_path": "/usr/bin/dump1090-fa",
    "reference_lat": 41.9481,
    "reference_lon": -87.6555,
    "alert_interval": 300
  },
  "watchlist": [
    {"icao": "4B1234", "name": "Test Aircraft"}
  ]
}
```

### Key Settings

- **radio.frequency**: ADS-B frequency (1090.1 MHz default)
- **radio.lna_gain**: LNA gain setting (0-40)
- **radio.vga_gain**: VGA gain setting (0-62)
- **meshtastic.port**: USB port for Meshtastic device
- **meshtastic.channel**: Meshtastic channel for alerts
- **receiver.reference_lat/lon**: Your location for distance calculations
- **watchlist**: Aircraft to monitor (ICAO codes)

## File Structure

```
ursine-capture/
├── installer.py              # One-command installation
├── receiver.py               # ADS-B reception and Meshtastic
├── dashboard.py              # Terminal UI and controls
├── config.py                 # Configuration management
├── aircraft.py               # Aircraft data structures
├── utils.py                  # Shared utilities
├── start-receiver.py         # Receiver startup script
├── start-dashboard.py        # Dashboard startup script
├── start-ursine-capture.sh   # Complete system startup
├── config.json               # Configuration file
├── aircraft.json             # Current aircraft data (generated)
├── status.json               # System status (generated)
├── performance_profiler.py   # Performance profiling and optimization
├── memory_optimizer.py       # Memory usage analysis and optimization
├── stability_tester.py       # Long-term stability testing
├── system_monitor.py         # System health monitoring
├── final_optimization.py     # Comprehensive optimization and validation
├── create_deployment_package.py # Deployment package creation
└── README.md                 # This file
```

## Features

### ADS-B Reception
- Automatic dump1090 process management
- HackRF configuration and control
- Real-time message decoding with pyModeS
- Aircraft position and velocity tracking
- Message rate monitoring

### Watchlist Monitoring
- Add/remove aircraft by ICAO code
- Automatic Meshtastic alerts for watchlist matches
- Visual highlighting in dashboard
- Persistent watchlist storage

### Terminal Dashboard
- Real-time aircraft list with sorting
- Color-coded waterfall spectrum display
- System status monitoring
- Interactive menus for configuration
- Keyboard navigation and controls

### Meshtastic Integration
- Automatic device connection
- Boot notification messages
- Watchlist alert transmission
- Connection status monitoring
- Automatic reconnection

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for detailed troubleshooting information.

### Common Issues

**No aircraft appearing:**
- Check antenna connection
- Verify HackRF is connected and recognized
- Ensure you're in an area with ADS-B traffic
- Check dump1090 is running: `ps aux | grep dump1090`

**Meshtastic not connecting:**
- Check USB cable and port
- Verify device permissions: `ls -l /dev/ttyUSB*`
- Try different USB port
- Check Meshtastic device is in correct mode

**Dashboard display issues:**
- Ensure terminal is at least 80x24 characters
- Try different terminal emulator
- Check terminal supports color

**Permission errors:**
- Run installer as root if needed: `sudo python3 installer.py`
- Add user to dialout group: `sudo usermod -a -G dialout $USER`
- Reboot after permission changes

## Performance Monitoring & Optimization

The system includes comprehensive performance monitoring and optimization tools:

### Performance Profiling
Profile system performance and identify bottlenecks:
```bash
# Run 5-minute performance profile
python3 performance_profiler.py profile 300

# Continuous monitoring
python3 performance_profiler.py monitor

# Generate performance report
python3 performance_profiler.py report performance_report.txt
```

### Memory Optimization
Analyze and optimize memory usage:
```bash
# Analyze memory usage patterns
python3 memory_optimizer.py analyze 300

# Apply memory optimizations
python3 memory_optimizer.py optimize

# Continuous memory monitoring
python3 memory_optimizer.py monitor
```

### Stability Testing
Test long-term system stability:
```bash
# Run 24-hour stability test
python3 stability_tester.py test 24

# Quick stability check
python3 stability_tester.py quick

# Generate stability report
python3 stability_tester.py report stability_report.txt
```

### System Health Monitoring
Monitor system health and perform recovery:
```bash
# Check system health
python3 system_monitor.py health

# Perform basic recovery
python3 system_monitor.py recover

# Continuous monitoring
python3 system_monitor.py monitor
```

### Final Optimization
Run comprehensive optimization and validation:
```bash
# Full optimization and validation
python3 final_optimization.py optimize

# Validation only
python3 final_optimization.py validate

# Generate optimization report
python3 final_optimization.py report optimization_report.txt
```

### Performance Targets
The system is designed to meet these performance targets:
- **Message Rate**: 100+ messages/second
- **Latency**: <100ms from reception to display
- **Memory Usage**: <50MB total system usage
- **CPU Usage**: <25% on Raspberry Pi 4
- **Uptime**: 24+ hours continuous operation
- **Error Rate**: <5 errors per hour

## Deployment

### Creating Deployment Packages
Create distribution packages for different use cases:
```bash
# Create minimal package (core files only)
python3 create_deployment_package.py create minimal

# Create standard package (includes docs and tools)
python3 create_deployment_package.py create standard

# Create full package (everything)
python3 create_deployment_package.py create full

# Validate a package
python3 create_deployment_package.py validate package.tar.gz
```

## Development

### Running Tests
```bash
# Test installation
python3 installer.py --test-mode

# Test receiver (60 second test)
python3 receiver.py --test --duration 60

# Test dashboard (demo mode)
python3 dashboard.py --demo

# Run integration tests
python3 integration_test.py
```

### Log Files
- **ursine-capture.log**: Main system log
- **dump1090.log**: dump1090 process log
- **meshtastic.log**: Meshtastic communication log
- **performance-profiler.log**: Performance profiling logs
- **memory-optimizer.log**: Memory optimization logs
- **stability-tester.log**: Stability testing logs

### Data Files
- **aircraft.json**: Current aircraft data (updated every second)
- **status.json**: System status (updated every 5 seconds)
- **config.json**: Configuration (user editable)

## Support

For issues, questions, or contributions:
1. Check the troubleshooting guide
2. Review log files for error messages
3. Verify hardware connections
4. Test with minimal configuration

## License

This project is open source. See individual file headers for specific license information.

## Changelog

### Version 2.0 (Current)
- Complete system rewrite
- Simplified 6-file architecture
- Improved reliability and error handling
- Better Meshtastic integration
- Enhanced terminal dashboard

### Version 1.x (Legacy)
- Original Ursine Explorer system
- Multiple configuration files
- Complex multi-file architecture
- Deprecated - use version 2.0