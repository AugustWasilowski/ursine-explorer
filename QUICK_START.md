# Ursine Explorer - Quick Start Guide

## Installation

### Automated Installation (Raspberry Pi)
```bash
sudo ./install.sh
```

### Manual Installation
```bash
# Install dependencies
pip3 install pyModeS numpy requests pyserial

# Run the system
python3 start_integrated_system.py
```

## Running the System

### Option 1: Simple Startup Script (Recommended)
```bash
./start_ursine_integrated.sh
```

### Option 2: With Dashboard
```bash
./start_ursine_integrated.sh --dashboard
```

### Option 3: Direct Python
```bash
python3 start_integrated_system.py
```

### Option 4: System Service (After Installation)
```bash
sudo systemctl start ursine-explorer
sudo systemctl status ursine-explorer
```

## First Time Setup

1. **Edit Configuration** (optional):
   ```bash
   nano config.json
   ```
   
   Add your watchlist ICAO codes:
   ```json
   {
     "target_icao_codes": ["A12345", "B67890"],
     "meshtastic_port": "/dev/ttyUSB0"
   }
   ```

2. **Test the System**:
   ```bash
   ./start_ursine_integrated.sh --validate
   ```

## Accessing the System

### Web Interface
- **Aircraft Data**: http://localhost:8080/data/aircraft.json
- **Enhanced Data**: http://localhost:8080/data/aircraft_enhanced.json
- **System Status**: http://localhost:8080/api/status
- **Health Check**: http://localhost:8080/api/health

### Dashboard
```bash
python3 adsb_dashboard.py
```

### Control Interface
```bash
telnet localhost 8081
```

## Common Commands

### Check System Status
```bash
curl http://localhost:8080/api/health
```

### View Live Aircraft Data
```bash
curl http://localhost:8080/data/aircraft.json | python3 -m json.tool
```

### Run Tests
```bash
./start_ursine_integrated.sh --test
```

### Validate System
```bash
./start_ursine_integrated.sh --validate
```

## Troubleshooting

### Check Dependencies
```bash
python3 -c "import pyModeS, numpy, requests, serial; print('All dependencies OK')"
```

### Check Ports
```bash
netstat -tulpn | grep -E ':(8080|8081|30005)'
```

### View Logs (if using systemd service)
```bash
sudo journalctl -u ursine-explorer -f
```

### Kill Conflicting Processes
```bash
sudo lsof -ti:8080 | xargs sudo kill -9  # Kill process on port 8080
sudo lsof -ti:30005 | xargs sudo kill -9  # Kill process on port 30005
```

## Migration from Legacy System

If you have an existing Ursine Explorer installation:

```bash
python3 migrate_to_integrated.py
```

This will:
- Backup your existing files
- Convert your configuration
- Test the new system
- Provide rollback instructions if needed

## Configuration Examples

### Basic Configuration
```json
{
  "dump1090_host": "localhost",
  "dump1090_port": 30005,
  "target_icao_codes": [],
  "meshtastic_port": null
}
```

### With Watchlist and Meshtastic
```json
{
  "dump1090_host": "localhost",
  "dump1090_port": 30005,
  "target_icao_codes": ["A12345", "B67890", "C11111"],
  "meshtastic_port": "/dev/ttyUSB0",
  "meshtastic_baud": 115200,
  "alert_interval_sec": 300
}
```

### With Reference Position (for better accuracy)
```json
{
  "dump1090_host": "localhost",
  "dump1090_port": 30005,
  "pymodes": {
    "enabled": true,
    "reference_position": {
      "latitude": 40.7128,
      "longitude": -74.0060
    }
  }
}
```

## System Requirements

- **Python 3.7+**
- **pyModeS** (automatically installed)
- **numpy, requests, pyserial** (automatically installed)
- **dump1090** (for SDR integration)
- **HackRF or RTL-SDR** (for radio reception)

## Getting Help

1. **Check the logs**: Look for error messages in the console output
2. **Run validation**: `./start_ursine_integrated.sh --validate`
3. **Run tests**: `./start_ursine_integrated.sh --test`
4. **Check system status**: `curl http://localhost:8080/api/health`
5. **Read the full documentation**: `INTEGRATION_COMPLETE.md`

## Quick Commands Reference

| Command | Description |
|---------|-------------|
| `./start_ursine_integrated.sh` | Start the system |
| `./start_ursine_integrated.sh --dashboard` | Start with dashboard |
| `./start_ursine_integrated.sh --test` | Run tests |
| `./start_ursine_integrated.sh --validate` | Validate system |
| `python3 adsb_dashboard.py` | Start dashboard only |
| `curl http://localhost:8080/api/health` | Check system health |
| `sudo systemctl status ursine-explorer` | Check service status |
| `sudo journalctl -u ursine-explorer -f` | View service logs |

---

**Need more help?** Check the complete documentation in `INTEGRATION_COMPLETE.md`