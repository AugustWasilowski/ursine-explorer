# pyModeS Integration Module

This module provides integration between the UrsineExplorer ADS-B receiver system and the pyModeS library for robust ADS-B message decoding and processing.

## Overview

The pyModeS integration enhances the UrsineExplorer system with:

- **Robust Message Decoding**: Uses pyModeS's proven algorithms for ADS-B message processing
- **Enhanced Aircraft Tracking**: Improved position calculation using CPR decoding
- **Flexible Message Sources**: Support for multiple simultaneous data sources
- **Backward Compatibility**: Maintains compatibility with existing UrsineExplorer APIs

## Installation

### Prerequisites

1. Python 3.7 or higher
2. pyModeS library and dependencies

### Install Dependencies

```bash
# Option 1: Using virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
pip install -r requirements.txt

# Option 2: System-wide installation (if allowed)
pip install --break-system-packages -r requirements.txt

# Option 3: Manual installation
pip install pyModeS>=2.13.0 numpy>=1.21.0 requests>=2.25.0 pyserial>=3.5
```

## Quick Start

### Basic Usage

```python
from pymodes_integration import PyModeSConfig, PyModeSDecode, MessageSourceManager

# 1. Create configuration
config = PyModeSConfig()
config.reference_latitude = 40.7128   # Your location
config.reference_longitude = -74.0060

# 2. Initialize decoder
decoder = PyModeSDecode(config)

# 3. Process messages
messages = [("8D4840D6202CC371C32CE0576098", time.time())]
aircraft_data = decoder.process_messages(messages)

# 4. Access aircraft information
for icao, aircraft in aircraft_data.items():
    print(f"Aircraft {aircraft.get_display_name()}")
    print(f"Position: {aircraft.latitude}, {aircraft.longitude}")
```

### Configuration

```python
from pymodes_integration.config import PyModeSConfig

# Load from existing config.json
config = PyModeSConfig.from_file("config.json")

# Or create from dictionary
config_dict = {
    'pymodes': {
        'crc_validation': True,
        'reference_latitude': 40.7128,
        'reference_longitude': -74.0060,
        'use_global_cpr': True,
        'aircraft_timeout_sec': 300
    }
}
config = PyModeSConfig.from_dict(config_dict)
```

## Module Structure

### Core Components

- **`config.py`**: Configuration management and validation
- **`decoder.py`**: pyModeS integration and message decoding
- **`aircraft.py`**: Enhanced aircraft data structure
- **`message_source.py`**: Message source management and interfaces

### Key Classes

#### `PyModeSConfig`
Configuration class for pyModeS integration settings.

```python
config = PyModeSConfig()
config.crc_validation = True
config.reference_latitude = 40.7128
config.reference_longitude = -74.0060
```

#### `PyModeSDecode`
Main decoder class that wraps pyModeS functionality.

```python
decoder = PyModeSDecode(config)
aircraft_data = decoder.process_messages(messages)
stats = decoder.get_statistics()
```

#### `EnhancedAircraft`
Enhanced aircraft data structure with pyModeS integration.

```python
aircraft = EnhancedAircraft.from_pymodes_data(decoded_data)
api_dict = aircraft.to_api_dict()
legacy_dict = aircraft.to_legacy_dict()
```

#### `MessageSourceManager`
Manages multiple message sources for unified data collection.

```python
manager = MessageSourceManager()
manager.add_source(source)
manager.start_collection()
messages = manager.get_message_batch()
```

## Configuration Options

### pyModeS Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `crc_validation` | `True` | Enable CRC validation for messages |
| `reference_latitude` | `None` | Reference latitude for local CPR decoding |
| `reference_longitude` | `None` | Reference longitude for local CPR decoding |
| `use_global_cpr` | `True` | Enable global CPR position decoding |
| `use_local_cpr` | `True` | Enable local CPR position decoding |
| `aircraft_timeout_sec` | `300` | Aircraft timeout in seconds |
| `message_timeout_sec` | `300` | Message timeout in seconds |
| `position_timeout_sec` | `60` | Position message timeout in seconds |

### Performance Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `batch_size` | `100` | Message batch processing size |
| `processing_threads` | `1` | Number of processing threads |
| `max_aircraft` | `10000` | Maximum aircraft to track |
| `cleanup_interval_sec` | `60` | Aircraft cleanup interval |

## Integration with UrsineExplorer

### Backward Compatibility

The integration maintains full backward compatibility with existing UrsineExplorer APIs:

```python
# Enhanced aircraft provides legacy format
aircraft = EnhancedAircraft.from_pymodes_data(data)
legacy_data = aircraft.to_legacy_dict()

# API format includes enhanced fields
api_data = aircraft.to_api_dict()
```

### Configuration Integration

Add pyModeS settings to your existing `config.json`:

```json
{
  "dump1090_host": "localhost",
  "dump1090_port": 30005,
  "pymodes": {
    "crc_validation": true,
    "reference_latitude": 40.7128,
    "reference_longitude": -74.0060,
    "use_global_cpr": true,
    "aircraft_timeout_sec": 300
  }
}
```

## Testing

Run the integration tests:

```bash
python3 test_pymodes_integration.py
```

Run the example:

```bash
python3 -m pymodes_integration.example
```

## Error Handling

The integration includes comprehensive error handling:

- **Import Errors**: Graceful handling when pyModeS is not available
- **Decode Errors**: Invalid messages are logged and skipped
- **Connection Errors**: Automatic reconnection for message sources
- **Configuration Errors**: Validation with helpful error messages

## Logging

Configure logging levels for different components:

```python
import logging

# Enable debug logging for pyModeS integration
logging.getLogger('pymodes_integration').setLevel(logging.DEBUG)

# Enable info logging for decoder statistics
logging.getLogger('pymodes_integration.decoder').setLevel(logging.INFO)
```

## Performance Considerations

- **Message Batching**: Process messages in batches for better performance
- **CPR Caching**: Position messages are cached for global decoding
- **Memory Management**: Old aircraft are automatically cleaned up
- **Threading**: Message collection runs in background threads

## Troubleshooting

### Common Issues

1. **pyModeS Import Error**
   ```
   ModuleNotFoundError: No module named 'pyModeS'
   ```
   Solution: Install pyModeS with `pip install pyModeS`

2. **CRC Validation Failures**
   ```
   Many messages failing CRC validation
   ```
   Solution: Check message source quality or disable CRC validation

3. **Position Decoding Issues**
   ```
   Aircraft positions not calculated
   ```
   Solution: Set reference position or ensure even/odd message pairs

### Debug Mode

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

config = PyModeSConfig()
config.log_decode_errors = True
config.log_aircraft_updates = True
```

## Contributing

When contributing to the pyModeS integration:

1. Follow the existing code style and patterns
2. Add comprehensive error handling
3. Include unit tests for new functionality
4. Update documentation for new features
5. Maintain backward compatibility

## License

This integration module follows the same license as the main UrsineExplorer project.