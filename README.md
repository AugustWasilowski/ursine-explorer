# Ursine Explorer

A comprehensive ADS-B monitoring system that integrates dump1090 with HackRF One for real-time aircraft tracking, watchlist alerts via Meshtastic LoRa mesh, and a live terminal dashboard.

## Features

- **Real-time ADS-B monitoring** using dump1090 with HackRF One support
- **Watchlist alerts** via Meshtastic LoRa mesh networking
- **Live terminal dashboard** with aircraft tracking and system status
- **Waterfall spectrum viewer** for frequency analysis
- **Automatic service management** with watchdog monitoring
- **Detailed aircraft information** (callsign, altitude, speed, track, position)
- **Configurable alert intervals** to prevent spam
- **JSON API** for integration with other tools

## Hardware Requirements

- **Raspberry Pi** (3B+ or newer recommended)
- **HackRF One** SDR device
- **ADS-B antenna** (1090 MHz)
- **Meshtastic device** (optional, for LoRa alerts)

## Quick Setup

1. **Clone and install:**
   ```bash
   git clone https://github.com/AugustWasilowski/ursine-explorer.git
   cd ursine-explorer
   chmod +x install.sh
   sudo ./install.sh
   ```

2. **Configure the system:**
   ```bash
   sudo nano config.json
   ```
   
   Update key settings:
   - `target_icao_codes`: Array of ICAO codes to monitor (e.g., `["A12345", "B67890"]`)
   - `meshtastic_port`: Serial port for Meshtastic device (e.g., `"/dev/ttyUSB0"`)
   - `frequency`: ADS-B frequency (default: `1090000000` Hz)
   - `lna_gain`/`vga_gain`: HackRF gain settings

3. **Start the system:**
   ```bash
   # Start the ADS-B receiver
   python3 adsb_receiver.py
   
   # In another terminal, start the dashboard
   python3 adsb_dashboard.py
   
   # Optional: Start the waterfall viewer
   python3 waterfall_viewer.py
   ```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `target_icao_codes` | Array of ICAO codes to monitor | `[]` |
| `meshtastic_port` | Serial port for Meshtastic device | `"/dev/ttyUSB0"` |
| `meshtastic_baud` | Meshtastic baud rate | `115200` |
| `dump1090_host` | dump1090 server host | `"localhost"` |
| `dump1090_port` | dump1090 Beast TCP port | `40005` |
| `frequency` | ADS-B frequency in Hz | `1090000000` |
| `lna_gain` | HackRF LNA gain (0-40 dB) | `40` |
| `vga_gain` | HackRF VGA gain (0-62 dB) | `20` |
| `enable_hackrf_amp` | Enable HackRF amplifier | `true` |
| `alert_interval_sec` | Cooldown between alerts (seconds) | `300` |
| `log_alerts` | Log alerts to file | `true` |
| `alert_log_file` | Alert log filename | `"alerts.log"` |
| `watchdog_timeout_sec` | Auto-restart timeout | `60` |
| `poll_interval_sec` | Data update interval | `1` |

## System Components

### ADS-B Receiver (`adsb_receiver.py`)
- Manages dump1090 process with HackRF One
- Reads aircraft data from JSON files
- Sends watchlist alerts via Meshtastic
- Provides HTTP API for dashboard integration
- Implements watchdog monitoring for reliability

### Live Dashboard (`adsb_dashboard.py`)
- Real-time terminal interface using curses
- Displays aircraft list with detailed information
- Shows system status (dump1090, Meshtastic)
- Highlights watchlist aircraft in green
- Interactive menu for HackRF configuration
- Waterfall display option

### Waterfall Viewer (`waterfall_viewer.py`)
- Spectrum analysis display
- Shows frequency content over time
- Focuses on ADS-B frequency range (1090 MHz)
- Real-time updates via HTTP API

## Finding ICAO Codes

You can find aircraft ICAO codes using:
- **FlightRadar24**: Look up the aircraft registration
- **FlightAware**: Search by tail number or flight
- **Online databases**: Like airframes.org
- **Live monitoring**: Watch your dashboard for detected aircraft

## API Endpoints

The system provides HTTP APIs on port 8080:

- `GET /data/aircraft.json` - Current aircraft data
- `GET /data/fft.json` - FFT data for waterfall viewer

Control commands via TCP on port 8081:
- `PING` - Test connection
- `GET_STATUS` - Get system status
- `RESTART_DUMP1090` - Restart dump1090 process

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

## Alert System

When a watchlist aircraft is detected:
1. **Meshtastic alert** sent via LoRa mesh
2. **Log entry** written to `alerts.log`
3. **Dashboard highlight** shows aircraft in green
4. **Cooldown period** prevents spam (default: 5 minutes)

Alert format:
```
ALERT: Watchlist aircraft A12345 (UAL123) overhead at 35000 ft
```

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

**No aircraft detected:**
- Check HackRF connection: `hackrf_info`
- Verify antenna connection and positioning
- Check dump1090 logs for errors
- Ensure proper gain settings

**Meshtastic alerts not working:**
- Verify serial port: `ls /dev/ttyUSB*`
- Check baud rate settings
- Test Meshtastic device independently
- Review alert logs

**Dashboard not updating:**
- Check receiver is running
- Verify HTTP API connectivity
- Check for JSON parsing errors
- Review system logs

**Waterfall not displaying:**
- Ensure receiver is generating FFT data
- Check HTTP API for FFT endpoint
- Verify numpy is installed
- Check for display errors

## License

This project is open source. See LICENSE file for details.

## Contributing

Contributions welcome! Please submit issues and pull requests on GitHub.