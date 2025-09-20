# Enhanced Message Formatting Guide

This guide demonstrates the customizable message formatting capabilities implemented for task 8.2 of the Meshtastic Enhanced Integration feature.

## Overview

The enhanced message formatting system provides:

- **Configurable message templates** with custom field selection
- **Multiple position formats** (decimal degrees, compact, DMS, Maidenhead, UTM)
- **Multiple unit formats** for altitude, speed, and distance
- **Customizable field formatters** for specialized formatting needs
- **Template validation** and error handling
- **Message length control** with intelligent truncation
- **Priority mapping** customization per template

## Available Template Fields

### Basic Aircraft Fields
- `{icao}` - Aircraft ICAO hex code
- `{callsign}` - Aircraft callsign
- `{alert_type}` - Alert type (lowercase)
- `{alert_type_upper}` - Alert type (uppercase)
- `{message}` - Custom alert message

### Position Fields
- `{lat}` - Latitude (decimal degrees)
- `{lon}` - Longitude (decimal degrees)
- `{position}` - Position (lat,lon)
- `{position_decimal}` - Position in decimal degrees format (40.712800,-74.006000)
- `{position_compact}` - Position in compact format (40.713,-74.006)
- `{position_dms}` - Position in degrees/minutes/seconds (40°42'46.08"N, 74°00'21.60"W)
- `{position_maidenhead}` - Position in Maidenhead locator (FN30as)
- `{position_utm}` - Position in UTM coordinates

### Flight Data Fields
- `{altitude}` - Altitude with unit
- `{altitude_ft}` - Altitude in feet (35000ft or FL350)
- `{altitude_m}` - Altitude in meters
- `{altitude_fl}` - Altitude as flight level (FL350)
- `{speed}` - Ground speed with unit
- `{speed_kt}` - Speed in knots
- `{speed_mph}` - Speed in miles per hour
- `{speed_kmh}` - Speed in kilometers per hour
- `{heading}` - Track angle with unit
- `{heading_deg}` - Heading in degrees
- `{heading_cardinal}` - Heading as cardinal direction (N, NE, E, etc.)
- `{squawk}` - Transponder squawk code

### Distance/Bearing Fields (if calculated)
- `{distance}` - Distance from observer
- `{distance_nm}` - Distance in nautical miles
- `{distance_km}` - Distance in kilometers
- `{distance_mi}` - Distance in statute miles
- `{bearing}` - Bearing from observer
- `{bearing_deg}` - Bearing in degrees

### Time Fields
- `{timestamp}` - Timestamp (HH:MM:SS)
- `{time_hms}` - Time in HH:MM:SS format
- `{time_hm}` - Time in HH:MM format
- `{date}` - Date (YYYY-MM-DD)
- `{date_ymd}` - Date in YYYY-MM-DD format
- `{date_dmy}` - Date in DD/MM/YYYY format

### Formatted Variants
- `{icao_upper}` - ICAO in uppercase
- `{icao_lower}` - ICAO in lowercase
- `{callsign_clean}` - Cleaned callsign
- `{callsign_short}` - Callsign truncated to 8 characters

## Template Examples

### 1. Standard Template
```python
template = MessageTemplate(
    name='standard',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao} ({callsign}) | Pos: {position} | Alt: {altitude} | Spd: {speed} | @{timestamp}",
    max_length=200,
    include_position=True,
    include_timestamp=True,
    include_altitude=True,
    include_speed=True
)
```
**Output:** `WATCHLIST: ABC123 (TEST123) | Pos: 40.7128,-74.0060 | Alt: 35000ft | Spd: 450kt | @14:30:25`

### 2. Compact Template
```python
template = MessageTemplate(
    name='compact',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type[0]}{icao}|{position_compact}|{altitude_fl}|{speed_kt}",
    max_length=80,
    include_position=True,
    include_timestamp=False
)
```
**Output:** `WABC123|40.713,-74.006|FL350|450kt`

### 3. Position-Focused Template
```python
template = MessageTemplate(
    name='position_detailed',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao} | Grid: {position_maidenhead} | UTM: {position_utm} | {distance_nm} @ {bearing_deg}",
    max_length=250,
    include_position=True
)
```
**Output:** `WATCHLIST: ABC123 | Grid: FN30as | UTM: 18T 587451 4507071 | 65.2nm @ 045°`

### 4. Emergency Template
```python
template = MessageTemplate(
    name='emergency',
    format_type=MessageFormat.CUSTOM,
    template_string="🚨 EMERGENCY: {icao} ({callsign}) at {position_dms} - {altitude_fl} - {message}",
    max_length=180,
    priority_mapping={
        AlertType.EMERGENCY.value: MessagePriority.CRITICAL
    }
)
```
**Output:** `🚨 EMERGENCY: ABC123 (TEST123) at 40°42'46.08"N, 74°00'21.60"W - FL350 - Squawk 7700`

### 5. Speed and Heading Focused Template
```python
template = MessageTemplate(
    name='flight_data',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao} | {altitude_fl} | {speed_kmh} | {heading_cardinal} ({heading_deg})",
    max_length=120,
    include_position=False,
    include_altitude=True,
    include_speed=True
)
```
**Output:** `WATCHLIST: ABC123 | FL350 | 833km/h | E (90°)`

### 6. Time-Focused Template
```python
template = MessageTemplate(
    name='timestamped',
    format_type=MessageFormat.CUSTOM,
    template_string="[{date_dmy} {time_hms}] {alert_type_upper}: {icao} | {position_compact} | {altitude_ft}",
    max_length=150,
    include_timestamp=True
)
```
**Output:** `[20/12/2024 14:30:25] WATCHLIST: ABC123 | 40.713,-74.006 | 35000ft`

### 7. Ultra-Compact Template
```python
template = MessageTemplate(
    name='ultra_compact',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type[0]}{icao}{position_compact}{altitude_fl}",
    max_length=40,
    include_position=True,
    include_timestamp=False
)
```
**Output:** `WABC12340.713,-74.006FL350`

### 8. Distance-Focused Template (for proximity alerts)
```python
template = MessageTemplate(
    name='proximity',
    format_type=MessageFormat.CUSTOM,
    template_string="📍 PROXIMITY: {icao} | {distance_nm} away at {bearing_deg} | {altitude_ft} | {speed_kt}",
    max_length=150,
    priority_mapping={
        AlertType.PROXIMITY.value: MessagePriority.HIGH
    }
)
```
**Output:** `📍 PROXIMITY: ABC123 | 65.2nm away at 045° | 35000ft | 450kt`

## Template Configuration Options

### MessageTemplate Parameters

- **name**: Unique template identifier
- **format_type**: MessageFormat enum (STANDARD, COMPACT, JSON, CUSTOM)
- **template_string**: Format string with field placeholders
- **max_length**: Maximum message length (0 = no limit)
- **include_position**: Whether to include position data
- **include_timestamp**: Whether to include timestamp
- **include_altitude**: Whether to include altitude
- **include_speed**: Whether to include speed/track
- **priority_mapping**: Custom priority mapping for alert types

### Field Selection Control

Templates can control which fields are included:

```python
# Minimal template - only basic info
minimal_template = MessageTemplate(
    name='minimal',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao}",
    max_length=50,
    include_position=False,
    include_timestamp=False,
    include_altitude=False,
    include_speed=False
)

# Full template - all available info
full_template = MessageTemplate(
    name='full',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao} ({callsign}) | {position_dms} | {altitude_fl} | {speed_kmh} | {heading_cardinal} | {distance_nm} @ {bearing_deg} | [{time_hms}]",
    max_length=300,
    include_position=True,
    include_timestamp=True,
    include_altitude=True,
    include_speed=True
)
```

## Position Formatting Options

The system supports multiple coordinate formats:

### Decimal Degrees
- **Format**: `40.712800,-74.006000`
- **Use case**: Standard GPS coordinates
- **Field**: `{position_decimal}`

### Compact
- **Format**: `40.713,-74.006`
- **Use case**: Bandwidth-limited scenarios
- **Field**: `{position_compact}`

### Degrees/Minutes/Seconds
- **Format**: `40°42'46.08"N, 74°00'21.60"W`
- **Use case**: Navigation and aviation
- **Field**: `{position_dms}`

### Maidenhead Locator
- **Format**: `FN30as`
- **Use case**: Ham radio and compact grid reference
- **Field**: `{position_maidenhead}`

### UTM Coordinates
- **Format**: `18T 587451 4507071`
- **Use case**: Military and surveying applications
- **Field**: `{position_utm}`

## Unit Conversion Support

### Altitude Formats
- `{altitude_ft}`: 35000ft or FL350 (automatic flight level for >10000ft)
- `{altitude_m}`: 10668m (converted from feet)
- `{altitude_fl}`: FL350 (flight level format)

### Speed Formats
- `{speed_kt}`: 450kt (knots)
- `{speed_mph}`: 518mph (statute miles per hour)
- `{speed_kmh}`: 833km/h (kilometers per hour)

### Distance Formats
- `{distance_nm}`: 65.2nm (nautical miles)
- `{distance_km}`: 120.8km (kilometers)
- `{distance_mi}`: 75.1mi (statute miles)

### Heading Formats
- `{heading_deg}`: 90° (degrees)
- `{heading_cardinal}`: E (cardinal direction)

## Priority Mapping

Templates can override default priority mappings:

```python
custom_priority_template = MessageTemplate(
    name='custom_priority',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao}",
    priority_mapping={
        AlertType.INTERESTING.value: MessagePriority.CRITICAL,  # Override default LOW
        AlertType.WATCHLIST.value: MessagePriority.LOW,         # Override default HIGH
        AlertType.EMERGENCY.value: MessagePriority.CRITICAL     # Keep default
    }
)
```

## Message Length Control

Templates automatically handle message length limits:

```python
# Short message template with truncation
short_template = MessageTemplate(
    name='short',
    format_type=MessageFormat.CUSTOM,
    template_string="{alert_type_upper}: {icao} ({callsign}) at {position_decimal} with altitude {altitude_ft} and speed {speed_kt}",
    max_length=60  # Will be truncated with "..."
)
```

**Output**: `WATCHLIST: ABC123 (TEST123) at 40.712800,-74.006000...`

## Error Handling

The system gracefully handles template errors:

1. **Invalid field names**: Falls back to standard format
2. **Missing data**: Shows "Unknown" for unavailable fields
3. **Template syntax errors**: Uses fallback formatting
4. **Length violations**: Automatic truncation with ellipsis

## Integration with Position Formatter

The message formatting system is fully integrated with the position formatter:

```python
# Calculate distance and bearing
distance, bearing = PositionFormatter.calculate_distance_and_bearing(
    observer_lat, observer_lon, aircraft_lat, aircraft_lon
)

# Create alert with calculated values
alert = StandardAlertMessage.from_aircraft(
    aircraft, 
    AlertType.PROXIMITY,
    distance=distance,
    bearing=bearing
)

# Format with distance-aware template
formatted_message = alert.to_meshtastic_text(proximity_template)
```

## Usage Examples

### Creating and Using Custom Templates

```python
from pymodes_integration.meshtastic_enhanced.message_formatter import (
    MessageFormatter, MessageTemplate, MessageFormat, AlertType
)

# Initialize formatter
formatter = MessageFormatter()

# Create custom template
custom_template = MessageTemplate(
    name='my_custom',
    format_type=MessageFormat.CUSTOM,
    template_string="🛩️ {alert_type_upper}: {icao_upper} | {position_maidenhead} | {altitude_fl} | {speed_kmh}",
    max_length=120,
    include_position=True,
    include_altitude=True,
    include_speed=True
)

# Add to formatter
formatter.add_template(custom_template)

# Format aircraft alert
alert_message = formatter.format_aircraft_alert(
    aircraft=my_aircraft,
    alert_type=AlertType.WATCHLIST,
    template_name='my_custom',
    channel='LongFast'
)

print(alert_message.content)
# Output: 🛩️ WATCHLIST: ABC123 | FN30AS | FL350 | 833km/h
```

### Loading Templates from Configuration

```python
# Template configuration
templates_config = [
    {
        'name': 'emergency_alert',
        'format_type': 'custom',
        'template_string': '🚨 {alert_type_upper}: {icao} at {position_compact} - {message}',
        'max_length': 100,
        'include_position': True,
        'include_timestamp': False,
        'priority_mapping': {
            'emergency': 4  # CRITICAL priority
        }
    },
    {
        'name': 'minimal_alert',
        'format_type': 'custom',
        'template_string': '{alert_type[0]}{icao}',
        'max_length': 20,
        'include_position': False,
        'include_timestamp': False,
        'include_altitude': False,
        'include_speed': False
    }
]

# Load templates
formatter.load_templates_from_config(templates_config)
```

## Best Practices

1. **Keep templates focused**: Design templates for specific use cases
2. **Consider bandwidth**: Use compact formats for bandwidth-limited scenarios
3. **Test length limits**: Ensure important information fits within limits
4. **Use appropriate precision**: Match coordinate precision to use case
5. **Handle missing data**: Templates should work even with incomplete aircraft data
6. **Validate templates**: Use the validation methods to check template syntax
7. **Document custom fields**: Maintain documentation for custom field formatters

## Performance Considerations

- Position format calculations are cached where possible
- Template formatting is optimized for common use cases
- Message length validation is performed efficiently
- Field formatters are loaded once and reused

This enhanced message formatting system provides the flexibility needed for various Meshtastic communication scenarios while maintaining reliability and performance.