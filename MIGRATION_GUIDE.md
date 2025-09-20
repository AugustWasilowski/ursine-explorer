# Migration Guide: Upgrading to pyModeS Integration

This guide helps existing UrsineExplorer users upgrade to the new pyModeS-powered version with enhanced ADS-B decoding capabilities.

## Overview

The new version integrates the proven pyModeS library to provide:
- **Improved reliability** with robust message decoding and validation
- **Enhanced position accuracy** using advanced CPR algorithms
- **Better error handling** and automatic recovery
- **Additional aircraft data** including velocity, heading, and navigation accuracy
- **Multi-source support** for various ADS-B data inputs
- **Comprehensive logging** and performance monitoring

## Pre-Migration Checklist

Before upgrading, ensure you have:

1. **Backup your current installation:**
   ```bash
   cp -r /path/to/ursine-explorer /path/to/ursine-explorer-backup
   cp config.json config.json.backup
   cp *.log logs-backup/
   ```

2. **Note your current configuration:**
   - ICAO codes in your watchlist
   - Meshtastic port and settings
   - HackRF gain settings
   - Any custom modifications

3. **Check system requirements:**
   - Python 3.8+ (check with `python3 --version`)
   - Sufficient disk space (additional ~50MB for pyModeS)
   - Network connectivity for package installation

## Migration Steps

### Step 1: Update the Code

```bash
cd ursine-explorer
git pull origin main
# Or download the latest release if not using git
```

### Step 2: Install New Dependencies

**Option A: Using virtual environment (recommended):**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**Option B: System-wide installation:**
```bash
pip3 install -r requirements.txt
# On newer systems: pip install --break-system-packages -r requirements.txt
```

**Verify pyModeS installation:**
```bash
python3 -c "import pyModeS; print('pyModeS version:', pyModeS.__version__)"
```

### Step 3: Configuration Migration

The system will automatically migrate your existing `config.json` to the new format. However, you may want to review and customize the new options.

**Automatic Migration:**
- Your existing settings will be preserved
- New pyModeS settings will be added with defaults
- A backup of your original config will be created as `config.json.pre-pymodes`

**Manual Configuration Review:**

1. **Set reference position for better local CPR decoding:**
   ```json
   "pymodes": {
       "reference_position": {
           "latitude": 40.7128,    // Your approximate latitude
           "longitude": -74.0060   // Your approximate longitude
       }
   }
   ```

2. **Configure message sources (if using non-standard setup):**
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

3. **Adjust aircraft tracking settings if needed:**
   ```json
   "aircraft_tracking": {
       "aircraft_timeout_sec": 300,
       "max_aircraft_count": 10000,
       "enable_data_validation": true
   }
   ```

### Step 4: Test the Migration

1. **Start the system:**
   ```bash
   # If using virtual environment
   source venv/bin/activate
   
   python3 adsb_receiver.py
   ```

2. **Check for migration messages in logs:**
   ```bash
   tail -f adsb_receiver.log | grep -i migration
   ```

3. **Verify pyModeS is working:**
   ```bash
   tail -f adsb_receiver.log | grep -i pymodes
   ```

4. **Test the dashboard:**
   ```bash
   # In another terminal
   python3 adsb_dashboard.py
   ```

## New Features Available After Migration

### Enhanced Aircraft Data

The dashboard and API now provide additional information:
- **True/Indicated Airspeed**: More accurate speed measurements
- **Mach Number**: For high-altitude aircraft
- **Magnetic Heading**: Aircraft heading relative to magnetic north
- **Roll Angle**: Aircraft bank angle
- **Navigation Accuracy**: Position uncertainty metrics
- **Data Quality Indicators**: Message reliability information

### Improved Position Accuracy

- **Global CPR**: Better position calculation using even/odd message pairs
- **Local CPR**: Position updates using reference position for faster updates
- **Surface Position**: Enhanced ground vehicle tracking

### Better Error Handling

- **CRC Validation**: Automatic rejection of corrupted messages
- **Format Validation**: Proper message format checking
- **Range Validation**: Sanity checking of decoded values
- **Automatic Recovery**: System continues operating despite individual message errors

### Enhanced Logging

New log categories provide better troubleshooting:
- Message processing statistics
- Decode success rates
- Position calculation performance
- Connection status for all sources
- Memory usage monitoring

## Configuration Changes

### New Configuration Sections

The following sections have been added to `config.json`:

```json
{
    "pymodes": {
        "enabled": true,
        "reference_position": {
            "latitude": null,
            "longitude": null
        },
        "cpr_settings": {
            "global_position_timeout": 10,
            "local_position_range_nm": 180,
            "surface_position_timeout": 25
        },
        "message_validation": {
            "enable_crc_check": true,
            "enable_format_validation": true,
            "enable_range_validation": true,
            "max_message_age_sec": 60
        },
        "decoder_settings": {
            "supported_message_types": ["DF4", "DF5", "DF17", "DF18", "DF20", "DF21"],
            "enable_enhanced_decoding": true,
            "decode_comm_b": true,
            "decode_bds": true
        }
    },
    
    "message_sources": [
        {
            "name": "dump1090_primary",
            "type": "dump1090",
            "enabled": true,
            "host": "localhost",
            "port": 30005,
            "format": "beast",
            "reconnect_interval_sec": 5,
            "max_reconnect_attempts": 10,
            "buffer_size": 8192
        }
    ],
    
    "aircraft_tracking": {
        "aircraft_timeout_sec": 300,
        "position_timeout_sec": 60,
        "cleanup_interval_sec": 30,
        "max_aircraft_count": 10000,
        "enable_data_validation": true,
        "conflict_resolution": "newest_wins",
        "track_surface_vehicles": true,
        "minimum_message_count": 2
    },
    
    "watchlist": {
        "enabled": true,
        "sources": ["target_icao_codes"],
        "check_icao": true,
        "check_callsign": true,
        "case_sensitive": false,
        "pattern_matching": false,
        "alert_throttling": {
            "enabled": true,
            "min_interval_sec": 300,
            "max_alerts_per_hour": 10,
            "escalation_enabled": false
        }
    },
    
    "logging": {
        "level": "INFO",
        "enable_message_stats": true,
        "enable_aircraft_events": true,
        "enable_connection_events": true,
        "enable_decode_errors": true,
        "stats_interval_sec": 60,
        "log_file": "adsb_receiver.log",
        "max_log_size_mb": 100,
        "backup_count": 5
    },
    
    "performance": {
        "message_batch_size": 100,
        "processing_interval_ms": 100,
        "memory_limit_mb": 512,
        "enable_profiling": false,
        "gc_interval_sec": 300
    }
}
```

### Deprecated Settings

The following settings are deprecated but still supported for backward compatibility:
- `dump1090_port`: Use `message_sources[].port` instead
- `dump1090_host`: Use `message_sources[].host` instead

## Troubleshooting Migration Issues

### Common Issues and Solutions

**1. pyModeS installation fails:**
```bash
# Update pip first
pip3 install --upgrade pip

# Try specific version
pip3 install pyModeS==2.13.0

# On newer systems
pip3 install --break-system-packages pyModeS>=2.13.0
```

**2. Configuration validation errors:**
```bash
# Check config syntax
python3 -c "import json; json.load(open('config.json'))"

# Use config validator
python3 config_validator.py
```

**3. No aircraft detected after migration:**
- Check that `pymodes.enabled` is `true`
- Verify message source configuration
- Check logs for pyModeS initialization messages
- Ensure dump1090 is still running and accessible

**4. Performance issues:**
- Reduce `performance.message_batch_size` if CPU usage is high
- Increase `aircraft_tracking.aircraft_timeout_sec` to reduce memory usage
- Disable profiling: set `performance.enable_profiling` to `false`

**5. Alert system not working:**
- Verify watchlist configuration migrated correctly
- Check `watchlist.enabled` is `true`
- Review alert throttling settings
- Test Meshtastic connection independently

### Diagnostic Commands

**Check migration status:**
```bash
grep -i "migration\|config" adsb_receiver.log
```

**Verify pyModeS integration:**
```bash
python3 -c "
from pymodes_integration import decoder
d = decoder.PyModeSDecode()
print('pyModeS integration working')
"
```

**Test message processing:**
```bash
# Look for decode statistics in logs
grep "decode_rate\|messages/sec" adsb_receiver.log | tail -10
```

## Rollback Instructions

If you encounter issues and need to rollback to the previous version:

### Step 1: Stop the New System
```bash
# Stop all processes
pkill -f adsb_receiver
pkill -f adsb_dashboard
```

### Step 2: Restore Backup
```bash
# Restore code
rm -rf ursine-explorer
mv ursine-explorer-backup ursine-explorer
cd ursine-explorer

# Restore configuration
cp config.json.backup config.json
```

### Step 3: Reinstall Old Dependencies
```bash
# If you used virtual environment, remove it
rm -rf venv

# Reinstall old requirements (if you have them)
pip3 install -r requirements-old.txt
```

### Step 4: Restart Old System
```bash
python3 adsb_receiver.py
```

## Performance Improvements

After migration, you should see:

### Message Processing
- **Higher decode success rates** (typically 95%+ vs 80-90% previously)
- **Better CRC validation** reducing false positives
- **Improved error recovery** with fewer system crashes

### Position Accuracy
- **More accurate positions** using advanced CPR algorithms
- **Faster position updates** with local CPR when reference position is set
- **Better handling** of surface vehicles and ground traffic

### System Reliability
- **Automatic reconnection** to data sources
- **Graceful error handling** for individual message failures
- **Memory management** with configurable limits and cleanup
- **Comprehensive logging** for better troubleshooting

## Getting Help

If you encounter issues during migration:

1. **Check the logs:** Review `adsb_receiver.log` for detailed error messages
2. **Enable debug logging:** Set `logging.level` to `"DEBUG"` temporarily
3. **Compare configurations:** Use `diff config.json.backup config.json`
4. **Test components individually:** Run each component separately
5. **Consult troubleshooting guide:** See README.md troubleshooting section
6. **Report issues:** Include migration steps taken and complete error messages

## Post-Migration Optimization

### Recommended Settings for Better Performance

1. **Set reference position** for your location to improve local CPR:
   ```json
   "pymodes": {
       "reference_position": {
           "latitude": YOUR_LATITUDE,
           "longitude": YOUR_LONGITUDE
       }
   }
   ```

2. **Adjust timeouts** based on your environment:
   ```json
   "aircraft_tracking": {
       "aircraft_timeout_sec": 600,  // Increase for busy airspace
       "position_timeout_sec": 120   // Increase for sparse coverage
   }
   ```

3. **Optimize logging** for your needs:
   ```json
   "logging": {
       "level": "INFO",              // Use "DEBUG" only for troubleshooting
       "stats_interval_sec": 300,    // Reduce frequency for less log volume
       "max_log_size_mb": 50         // Adjust based on disk space
   }
   ```

4. **Configure alert throttling** to prevent spam:
   ```json
   "watchlist": {
       "alert_throttling": {
           "min_interval_sec": 600,   // 10 minutes between alerts
           "max_alerts_per_hour": 6   // Maximum 6 alerts per hour per aircraft
       }
   }
   ```

The migration to pyModeS integration provides significant improvements in reliability, accuracy, and functionality while maintaining full backward compatibility with your existing setup.