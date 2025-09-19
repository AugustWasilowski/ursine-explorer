# Ursine Explorer ADS-B System - Enhanced Edition

This enhanced version of the Ursine Explorer ADS-B system implements the plan from [GitHub Issue #1](https://github.com/AugustWasilowski/ursine-explorer/issues/1), featuring dump1090 integration, watchlist alerts via Meshtastic, and improved terminal UI.

## 🆕 New Features

### 1. dump1090 Integration
- **Replaced GNU Radio** with optimized dump1090-fa for better performance
- **Direct HackRF support** with proper gain control
- **Automatic process management** with watchdog and auto-restart
- **Real-time aircraft data** via HTTP JSON API

### 2. Watchlist Alert System
- **Target aircraft tracking** with configurable ICAO codes
- **Meshtastic LoRa mesh integration** for remote alerts
- **Periodic alert timing** (5-minute intervals to prevent spam)
- **Alert logging** to file for record keeping

### 3. Enhanced Terminal UI
- **Green highlighting** for watchlist aircraft
- **Real-time status indicators** for dump1090 and Meshtastic
- **Improved statistics** and performance monitoring
- **Watchlist indicators** (🎯) in aircraft list

### 4. Robust System Management
- **Watchdog mechanism** for automatic dump1090 restart
- **Comprehensive logging** with configurable levels
- **Graceful shutdown** handling
- **Resource monitoring** and performance optimization

## 📋 Requirements

### Hardware
- **Raspberry Pi** (3B+ or newer recommended)
- **HackRF One** SDR device
- **Meshtastic device** (optional, for alerts)
- **1090 MHz antenna** optimized for ADS-B

### Software Dependencies
- **dump1090-fa** (FlightAware version with HackRF support)
- **Python 3.7+** with required packages
- **pyserial** for Meshtastic communication
- **requests** for HTTP API communication

## 🚀 Installation

1. **Run the installation script:**
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

2. **Configure the system:**
   Edit `config.json` with your settings:
   ```json
   {
       "dump1090_host": "localhost",
       "dump1090_port": 8080,
       "receiver_control_port": 8081,
       "frequency": 1090000000,
       "lna_gain": 40,
       "vga_gain": 20,
       "enable_hackrf_amp": true,
       "target_icao_codes": ["ABC123", "DEF456"],
       "meshtastic_port": "/dev/ttyUSB0",
       "meshtastic_baud": 115200,
       "log_alerts": true,
       "alert_log_file": "alerts.log",
       "alert_interval_sec": 300,
       "dump1090_path": "/usr/bin/dump1090-fa",
       "watchdog_timeout_sec": 60,
       "poll_interval_sec": 1
   }
   ```

3. **Test the installation:**
   ```bash
   python3 test_integration.py
   ```

## 🎯 Configuration Guide

### Watchlist Setup
Add ICAO codes of aircraft you want to track:
```json
"target_icao_codes": ["ABC123", "DEF456", "789XYZ"]
```

### Meshtastic Configuration
1. **Connect your Meshtastic device** via USB
2. **Set device to TEXTMSG mode** in Meshtastic config
3. **Configure serial port** in config.json:
   ```json
   "meshtastic_port": "/dev/ttyUSB0",
   "meshtastic_baud": 115200
   ```

### HackRF Settings
Optimize reception with proper gain settings:
```json
"lna_gain": 40,        // RF gain (0-47 dB)
"vga_gain": 20,        // VGA gain (0-62 dB)
"enable_hackrf_amp": true  // Enable internal amplifier
```

## 🖥️ Usage

### Start the System
1. **Start the ADS-B receiver:**
   ```bash
   python3 adsb_receiver.py
   ```

2. **Launch the dashboard:**
   ```bash
   python3 adsb_dashboard.py
   ```

### Dashboard Controls
- **q** - Quit dashboard
- **m** - Open configuration menu
- **w** - Toggle waterfall display
- **s** - Cycle sort options
- **r** - Reverse sort order
- **Space** - Force refresh

### Configuration Menu
- **RF Gain** - Adjust RF gain (0-47 dB)
- **IF Gain** - Adjust IF gain (0-47 dB)
- **BB Gain** - Adjust BB gain (0-62 dB)
- **Sample Rate** - Set sample rate (1-20 MHz)
- **Center Freq** - Set center frequency (1000-1200 MHz)
- **Test Connection** - Test receiver connectivity

## 📊 Monitoring and Alerts

### Aircraft Tracking
- **Real-time updates** every second
- **Watchlist highlighting** in green with 🎯 indicator
- **Automatic cleanup** of stale aircraft (5+ minutes)
- **Comprehensive statistics** and performance metrics

### Alert System
- **Automatic detection** of watchlist aircraft
- **Meshtastic mesh broadcasting** for remote notifications
- **5-minute intervals** to prevent alert spam
- **File logging** of all alerts with timestamps

### System Health
- **Watchdog monitoring** for dump1090 process
- **Automatic restart** on timeout or crash
- **Connection status** indicators in dashboard
- **Performance metrics** and error tracking

## 🔧 Troubleshooting

### Common Issues

1. **dump1090 won't start:**
   - Check HackRF connection: `hackrf_info`
   - Verify permissions: `sudo usermod -a -G plugdev $USER`
   - Test manually: `dump1090-fa --device-type hackrf --freq 1090e6 --net`

2. **No aircraft detected:**
   - Check antenna connection
   - Verify frequency settings (1090 MHz)
   - Adjust gain settings for your location
   - Check for interference sources

3. **Meshtastic not working:**
   - Verify device is in TEXTMSG mode
   - Check serial port permissions
   - Test connection: `python3 -c "import serial; print(serial.Serial('/dev/ttyUSB0', 115200))"`

4. **Dashboard connection issues:**
   - Ensure receiver is running first
   - Check firewall settings
   - Verify port availability

### Performance Optimization

1. **CPU Usage:**
   - Use latest dump1090-fa version
   - Optimize gain settings for your environment
   - Consider using a Pi 4 for better performance

2. **Memory Usage:**
   - Monitor aircraft count (auto-cleanup after 5 minutes)
   - Adjust polling intervals if needed
   - Check for memory leaks in logs

3. **Network Performance:**
   - Use localhost for receiver communication
   - Monitor HTTP API response times
   - Check for network bottlenecks

## 📈 Performance Expectations

### Typical Performance (Raspberry Pi 4)
- **CPU Usage:** 15-25% with active aircraft
- **Memory Usage:** <200MB
- **Aircraft Range:** 200-400 km (depending on antenna)
- **Update Rate:** 1 second intervals
- **Alert Latency:** <2 seconds for new watchlist aircraft

### Scaling Considerations
- **High aircraft density:** May need to reduce update frequency
- **Multiple receivers:** Consider load balancing
- **Remote monitoring:** Use VPN or secure tunnels

## 🔒 Security Considerations

1. **Network Security:**
   - Run on localhost only (default)
   - Use firewall rules for external access
   - Consider VPN for remote monitoring

2. **Device Security:**
   - Run as non-root user (ursine)
   - Limit file permissions
   - Regular security updates

3. **Data Privacy:**
   - Aircraft data is public information
   - Alert logs may contain sensitive location data
   - Consider data retention policies

## 📚 API Reference

### HTTP Endpoints
- `GET /data/aircraft.json` - Current aircraft data
- `GET /status` - System status information

### Control Commands
- `PING` - Test connectivity
- `RESTART_DUMP1090` - Restart dump1090 process
- `GET_STATUS` - Get detailed system status

### Data Format
```json
{
  "now": 1640995200.0,
  "messages": 12345,
  "aircraft": [
    {
      "hex": "ABC123",
      "flight": "UAL123",
      "alt_baro": 35000,
      "gs": 450,
      "track": 180,
      "lat": 40.7128,
      "lon": -74.0060,
      "squawk": "1234",
      "category": "A3",
      "messages": 15,
      "last_seen": "2023-01-01T12:00:00",
      "is_watchlist": true
    }
  ],
  "stats": {
    "total_aircraft": 50,
    "active_aircraft": 12,
    "watchlist_alerts": 5,
    "dump1090_restarts": 0
  }
}
```

## 🤝 Contributing

This implementation follows the plan from [GitHub Issue #1](https://github.com/AugustWasilowski/ursine-explorer/issues/1). For contributions:

1. **Follow the existing code style**
2. **Add comprehensive logging**
3. **Include error handling**
4. **Update documentation**
5. **Test on Raspberry Pi hardware**

## 📄 License

This project maintains the same license as the original Ursine Explorer system.

## 🙏 Acknowledgments

- **FlightAware** for dump1090-fa
- **Meshtastic community** for LoRa mesh networking
- **HackRF community** for SDR support
- **Original Ursine Explorer** developers

---

**Note:** This enhanced system is designed for educational and monitoring purposes. Always comply with local regulations regarding radio frequency monitoring and data collection.
