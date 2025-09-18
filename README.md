# Ursine Explorer

A Python application that monitors ADS-B signals via RTL-SDR and sends Discord notifications when specific aircraft (by ICAO code) are detected.

## Features

- 🛩️ Real-time ADS-B monitoring using dump1090
- 🎯 Filter by specific ICAO codes
- 📱 Discord webhook notifications
- 🔄 Automatic service management
- 📊 Detailed aircraft information (callsign, altitude, speed, track)
- ⏰ Notification cooldown to prevent spam

## Hardware Requirements

- Raspberry Pi (3B+ or newer recommended)
- RTL-SDR USB dongle
- ADS-B antenna (1090 MHz)

## Quick Setup

1. **Clone and install:**
   ```bash
   git clone https://github.com/AugustWasilowski/ursine-explorer.git
   cd ursine-explorer
   chmod +x install.sh
   sudo ./install.sh
   ```

2. **Configure Discord webhook:**
   - Go to your Discord server settings
   - Create a webhook in the desired channel
   - Copy the webhook URL

3. **Edit configuration:**
   ```bash
   sudo nano /opt/ursine-explorer/config.json
   ```
   
   Update:
   - `discord_webhook`: Your Discord webhook URL
   - `target_icao_codes`: Array of ICAO codes to monitor (e.g., ["A12345", "B67890"])

4. **Start the service:**
   ```bash
   sudo systemctl enable ursine-explorer
   sudo systemctl start ursine-explorer
   ```

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `target_icao_codes` | Array of ICAO codes to monitor | `["A12345", "B67890"]` |
| `discord_webhook` | Discord webhook URL | Required |
| `dump1090_host` | dump1090 server host | `"localhost"` |
| `dump1090_port` | dump1090 server port | `8080` |
| `poll_interval_seconds` | How often to check for aircraft | `5` |
| `notification_cooldown_minutes` | Cooldown between notifications for same aircraft | `30` |
| `log_level` | Logging level (DEBUG, INFO, WARNING, ERROR) | `"INFO"` |

## Finding ICAO Codes

You can find aircraft ICAO codes using:
- **FlightRadar24**: Look up the aircraft registration
- **FlightAware**: Search by tail number or flight
- **Online databases**: Like airframes.org
- **Live monitoring**: Watch your local dump1090 web interface at `http://your-pi-ip:8080`

## Monitoring and Troubleshooting

**Check service status:**
```bash
sudo systemctl status ursine-explorer
```

**View logs:**
```bash
sudo journalctl -u ursine-explorer -f
```

**Test manually:**
```bash
sudo -u ursine python3 /opt/ursine-explorer/monitor.py
```

**Check dump1090:**
```bash
sudo systemctl status dump1090-mutability
curl http://localhost:8080/data/aircraft.json
```

## Discord Notification Format

When a target aircraft is detected, you'll receive a Discord message with:
- ICAO code
- Callsign (if available)
- Altitude
- Ground speed
- Track/heading
- Detection timestamp

## Security Notes

- The service runs as a dedicated `ursine` user with minimal privileges
- Only necessary directories are writable
- Network access is limited to dump1090 and Discord webhook

## Customization

You can modify `monitor.py` to:
- Add more notification channels (email, SMS, etc.)
- Include additional aircraft data
- Implement geofencing
- Add flight path tracking
- Create a web dashboard

## Troubleshooting

**No aircraft detected:**
- Check RTL-SDR connection: `rtl_test`
- Verify antenna connection and positioning
- Check dump1090 is receiving data: visit `http://localhost:8080`

**Discord notifications not working:**
- Verify webhook URL is correct
- Check network connectivity
- Review logs for error messages

**Service won't start:**
- Check configuration file syntax: `python3 -m json.tool config.json`
- Verify file permissions
- Check system logs: `sudo journalctl -u ursine-explorer`