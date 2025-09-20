"""
Message formatting and templates for enhanced Meshtastic integration

This module provides message formatting capabilities for different alert types
and scenarios, with support for multiple output formats and customizable templates.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from enum import Enum

from .data_classes import AlertMessage, MessagePriority
from ..aircraft import EnhancedAircraft

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """Types of aircraft alerts"""
    WATCHLIST = "watchlist"
    EMERGENCY = "emergency"
    PROXIMITY = "proximity"
    MILITARY = "military"
    INTERESTING = "interesting"
    CUSTOM = "custom"


class MessageFormat(Enum):
    """Supported message output formats"""
    STANDARD = "standard"
    COMPACT = "compact"
    JSON = "json"
    CUSTOM = "custom"


@dataclass
class MessageTemplate:
    """
    Template for formatting alert messages
    
    Attributes:
        name: Template name
        format_type: Output format type
        template_string: Template string with placeholders
        max_length: Maximum message length (0 = no limit)
        include_position: Whether to include position data
        include_timestamp: Whether to include timestamp
        include_altitude: Whether to include altitude
        include_speed: Whether to include speed/track
        priority_mapping: Mapping of alert types to message priorities
    """
    name: str
    format_type: MessageFormat
    template_string: str
    max_length: int = 200
    include_position: bool = True
    include_timestamp: bool = True
    include_altitude: bool = True
    include_speed: bool = True
    priority_mapping: Dict[str, MessagePriority] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate template after initialization"""
        if not self.name:
            raise ValueError("Template name cannot be empty")
        
        if not self.template_string:
            raise ValueError("Template string cannot be empty")
        
        if self.max_length < 0:
            raise ValueError("Max length cannot be negative")
        
        # Set default priority mapping if empty
        if not self.priority_mapping:
            self.priority_mapping = {
                AlertType.EMERGENCY.value: MessagePriority.CRITICAL,
                AlertType.MILITARY.value: MessagePriority.HIGH,
                AlertType.WATCHLIST.value: MessagePriority.HIGH,
                AlertType.PROXIMITY.value: MessagePriority.MEDIUM,
                AlertType.INTERESTING.value: MessagePriority.LOW,
                AlertType.CUSTOM.value: MessagePriority.MEDIUM
            }


@dataclass
class StandardAlertMessage:
    """
    Enhanced alert message with aircraft and alert information
    
    Attributes:
        aircraft_icao: Aircraft ICAO hex code
        callsign: Aircraft callsign (if available)
        alert_type: Type of alert
        timestamp: Alert timestamp
        position: Aircraft position (lat, lon) if available
        altitude: Aircraft altitude in feet
        speed: Ground speed in knots
        heading: Track angle in degrees
        vertical_rate: Vertical rate in feet/minute
        squawk: Transponder squawk code
        distance: Distance from observer in nautical miles
        bearing: Bearing from observer in degrees
        message: Custom alert message
        metadata: Additional metadata
    """
    aircraft_icao: str
    alert_type: AlertType
    timestamp: datetime = field(default_factory=datetime.now)
    callsign: Optional[str] = None
    position: Optional[tuple[float, float]] = None
    altitude: Optional[int] = None
    speed: Optional[float] = None
    heading: Optional[float] = None
    vertical_rate: Optional[float] = None
    squawk: Optional[str] = None
    distance: Optional[float] = None
    bearing: Optional[float] = None
    message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_aircraft(cls, aircraft: EnhancedAircraft, alert_type: AlertType, 
                     message: Optional[str] = None, **kwargs) -> 'StandardAlertMessage':
        """
        Create StandardAlertMessage from EnhancedAircraft
        
        Args:
            aircraft: Aircraft data
            alert_type: Type of alert
            message: Optional custom message
            **kwargs: Additional fields to set
            
        Returns:
            New StandardAlertMessage instance
        """
        position = None
        if aircraft.has_position():
            position = (aircraft.latitude, aircraft.longitude)
        
        alert_msg = cls(
            aircraft_icao=aircraft.icao,
            alert_type=alert_type,
            callsign=aircraft.callsign,
            position=position,
            altitude=aircraft.altitude_baro,
            speed=aircraft.ground_speed,
            heading=aircraft.track_angle,
            vertical_rate=aircraft.vertical_rate,
            squawk=aircraft.squawk,
            message=message,
            **kwargs
        )
        
        return alert_msg
    
    def to_meshtastic_text(self, template: Optional[MessageTemplate] = None) -> str:
        """
        Convert to human-readable Meshtastic text message
        
        Args:
            template: Optional message template to use
            
        Returns:
            Formatted text message
        """
        if template and template.format_type == MessageFormat.CUSTOM:
            return self._format_with_template(template)
        
        # Standard format
        parts = []
        
        # Alert type and aircraft ID
        alert_prefix = self.alert_type.value.upper()
        aircraft_id = f"{self.aircraft_icao}"
        if self.callsign:
            aircraft_id += f" ({self.callsign})"
        
        parts.append(f"{alert_prefix}: {aircraft_id}")
        
        # Position if available
        if self.position and (not template or template.include_position):
            lat, lon = self.position
            parts.append(f"Pos: {lat:.4f},{lon:.4f}")
        
        # Altitude if available
        if self.altitude is not None and (not template or template.include_altitude):
            parts.append(f"Alt: {self.altitude}ft")
        
        # Speed and heading if available
        if (not template or template.include_speed):
            if self.speed is not None:
                parts.append(f"Spd: {self.speed:.0f}kt")
            if self.heading is not None:
                parts.append(f"Hdg: {self.heading:.0f}°")
        
        # Distance and bearing if available
        if self.distance is not None:
            parts.append(f"Dist: {self.distance:.1f}nm")
        if self.bearing is not None:
            parts.append(f"Brg: {self.bearing:.0f}°")
        
        # Custom message
        if self.message:
            parts.append(self.message)
        
        # Timestamp if requested
        if template and template.include_timestamp:
            time_str = self.timestamp.strftime("%H:%M:%S")
            parts.append(f"@{time_str}")
        
        message = " | ".join(parts)
        
        # Apply length limit if specified
        if template and template.max_length > 0:
            message = self._truncate_message(message, template.max_length)
        
        return message
    
    def to_compact(self, max_length: int = 100) -> str:
        """
        Convert to compact format for bandwidth-limited scenarios
        
        Args:
            max_length: Maximum message length
            
        Returns:
            Compact formatted message
        """
        # Use abbreviated format
        alert_code = self.alert_type.value[0].upper()  # First letter
        aircraft_id = self.aircraft_icao
        
        parts = [f"{alert_code}:{aircraft_id}"]
        
        # Add callsign if available and short
        if self.callsign and len(self.callsign) <= 8:
            parts[0] += f"({self.callsign})"
        
        # Position in compact format
        if self.position:
            lat, lon = self.position
            parts.append(f"{lat:.3f},{lon:.3f}")
        
        # Altitude in compact format
        if self.altitude is not None:
            if self.altitude >= 10000:
                parts.append(f"FL{self.altitude//100:03d}")
            else:
                parts.append(f"{self.altitude}ft")
        
        # Speed if significant
        if self.speed is not None and self.speed > 50:
            parts.append(f"{self.speed:.0f}kt")
        
        # Distance if available
        if self.distance is not None:
            parts.append(f"{self.distance:.1f}nm")
        
        message = "|".join(parts)
        
        return self._truncate_message(message, max_length)
    
    def to_json(self, include_metadata: bool = True) -> str:
        """
        Convert to JSON format for MQTT and structured data
        
        Args:
            include_metadata: Whether to include metadata
            
        Returns:
            JSON formatted message
        """
        data = {
            'aircraft_icao': self.aircraft_icao,
            'alert_type': self.alert_type.value,
            'timestamp': self.timestamp.isoformat(),
        }
        
        # Add optional fields if present
        if self.callsign:
            data['callsign'] = self.callsign
        
        if self.position:
            data['position'] = {
                'latitude': self.position[0],
                'longitude': self.position[1]
            }
        
        if self.altitude is not None:
            data['altitude'] = self.altitude
        
        if self.speed is not None:
            data['speed'] = self.speed
        
        if self.heading is not None:
            data['heading'] = self.heading
        
        if self.vertical_rate is not None:
            data['vertical_rate'] = self.vertical_rate
        
        if self.squawk:
            data['squawk'] = self.squawk
        
        if self.distance is not None:
            data['distance'] = self.distance
        
        if self.bearing is not None:
            data['bearing'] = self.bearing
        
        if self.message:
            data['message'] = self.message
        
        if include_metadata and self.metadata:
            data['metadata'] = self.metadata
        
        return json.dumps(data, separators=(',', ':'))
    
    def _format_with_template(self, template: MessageTemplate) -> str:
        """
        Format message using custom template with enhanced field support
        
        Args:
            template: Message template to use
            
        Returns:
            Formatted message
        """
        from .position_formatter import PositionFormatter, CoordinateFormat, DistanceUnit
        
        # Create basic substitution dictionary
        subs = {
            'icao': self.aircraft_icao,
            'callsign': self.callsign or 'Unknown',
            'alert_type': self.alert_type.value,
            'alert_type_upper': self.alert_type.value.upper(),
            'timestamp': self.timestamp.strftime("%H:%M:%S"),
            'date': self.timestamp.strftime("%Y-%m-%d"),
            'message': self.message or '',
        }
        
        # Position fields with multiple formats
        if self.position:
            lat, lon = self.position
            subs['lat'] = f"{lat:.4f}"
            subs['lon'] = f"{lon:.4f}"
            subs['position'] = f"{lat:.4f},{lon:.4f}"
            
            # Enhanced position formats
            subs['position_decimal'] = PositionFormatter.format_position(lat, lon, CoordinateFormat.DECIMAL_DEGREES)
            subs['position_compact'] = PositionFormatter.format_position(lat, lon, CoordinateFormat.COMPACT)
            subs['position_dms'] = PositionFormatter.format_position(lat, lon, CoordinateFormat.DEGREES_MINUTES_SECONDS)
            subs['position_maidenhead'] = PositionFormatter.format_position(lat, lon, CoordinateFormat.MAIDENHEAD)
            subs['position_utm'] = PositionFormatter.format_position(lat, lon, CoordinateFormat.UTM)
        else:
            subs['lat'] = 'Unknown'
            subs['lon'] = 'Unknown'
            subs['position'] = 'Unknown'
            subs['position_decimal'] = 'Unknown'
            subs['position_compact'] = 'Unknown'
            subs['position_dms'] = 'Unknown'
            subs['position_maidenhead'] = 'Unknown'
            subs['position_utm'] = 'Unknown'
        
        # Flight data fields with multiple formats
        if self.altitude is not None:
            subs['altitude'] = f"{self.altitude}ft"
            subs['altitude_ft'] = PositionFormatter.format_altitude(self.altitude, "ft")
            subs['altitude_m'] = PositionFormatter.format_altitude(self.altitude * 0.3048, "m")
            subs['altitude_fl'] = f"FL{int(self.altitude/100):03d}" if self.altitude >= 1000 else f"{self.altitude}ft"
        else:
            subs['altitude'] = 'Unknown'
            subs['altitude_ft'] = 'Unknown'
            subs['altitude_m'] = 'Unknown'
            subs['altitude_fl'] = 'Unknown'
        
        if self.speed is not None:
            subs['speed'] = f"{self.speed:.0f}kt"
            subs['speed_kt'] = f"{self.speed:.0f}kt"
            subs['speed_mph'] = f"{self.speed * 1.15078:.0f}mph"
            subs['speed_kmh'] = f"{self.speed * 1.852:.0f}km/h"
        else:
            subs['speed'] = 'Unknown'
            subs['speed_kt'] = 'Unknown'
            subs['speed_mph'] = 'Unknown'
            subs['speed_kmh'] = 'Unknown'
        
        if self.heading is not None:
            subs['heading'] = f"{self.heading:.0f}°"
            subs['heading_deg'] = f"{self.heading:.0f}°"
            subs['heading_cardinal'] = self._heading_to_cardinal(self.heading)
        else:
            subs['heading'] = 'Unknown'
            subs['heading_deg'] = 'Unknown'
            subs['heading_cardinal'] = 'Unknown'
        
        subs['squawk'] = self.squawk or 'Unknown'
        
        # Distance/bearing fields with multiple formats
        if self.distance is not None:
            subs['distance'] = f"{self.distance:.1f}nm"
            subs['distance_nm'] = PositionFormatter.format_distance(self.distance, DistanceUnit.NAUTICAL_MILES)
            subs['distance_km'] = PositionFormatter.format_distance(self.distance, DistanceUnit.KILOMETERS)
            subs['distance_mi'] = PositionFormatter.format_distance(self.distance, DistanceUnit.STATUTE_MILES)
        else:
            subs['distance'] = 'Unknown'
            subs['distance_nm'] = 'Unknown'
            subs['distance_km'] = 'Unknown'
            subs['distance_mi'] = 'Unknown'
        
        if self.bearing is not None:
            subs['bearing'] = f"{self.bearing:.0f}°"
            subs['bearing_deg'] = PositionFormatter.format_bearing(self.bearing)
        else:
            subs['bearing'] = 'Unknown'
            subs['bearing_deg'] = 'Unknown'
        
        # Time formatting variants
        subs['time_hms'] = self.timestamp.strftime("%H:%M:%S")
        subs['time_hm'] = self.timestamp.strftime("%H:%M")
        subs['date_ymd'] = self.timestamp.strftime("%Y-%m-%d")
        subs['date_dmy'] = self.timestamp.strftime("%d/%m/%Y")
        
        # ICAO/Callsign variants
        subs['icao_upper'] = self.aircraft_icao.upper() if self.aircraft_icao else "UNKNOWN"
        subs['icao_lower'] = self.aircraft_icao.lower() if self.aircraft_icao else "unknown"
        subs['callsign_clean'] = (self.callsign or "Unknown").strip()
        subs['callsign_short'] = (self.callsign or "Unknown")[:8]
        
        # Format using template
        try:
            formatted = template.template_string.format(**subs)
        except KeyError as e:
            logger.warning(f"Template formatting error: missing key {e}")
            # Fallback to standard format
            return self.to_meshtastic_text()
        
        # Apply length limit
        if template.max_length > 0:
            formatted = self._truncate_message(formatted, template.max_length)
        
        return formatted
    
    def _heading_to_cardinal(self, heading: float) -> str:
        """Convert heading to cardinal direction"""
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = int((heading + 11.25) / 22.5) % 16
        return directions[index]
    
    def _truncate_message(self, message: str, max_length: int) -> str:
        """
        Truncate message to maximum length with ellipsis
        
        Args:
            message: Message to truncate
            max_length: Maximum length
            
        Returns:
            Truncated message
        """
        if len(message) <= max_length:
            return message
        
        if max_length <= 3:
            return message[:max_length]
        
        return message[:max_length-3] + "..."
    
    def get_priority(self, template: Optional[MessageTemplate] = None) -> MessagePriority:
        """
        Get message priority based on alert type
        
        Args:
            template: Optional template with priority mapping
            
        Returns:
            Message priority
        """
        if template and self.alert_type.value in template.priority_mapping:
            return template.priority_mapping[self.alert_type.value]
        
        # Default priority mapping
        priority_map = {
            AlertType.EMERGENCY: MessagePriority.CRITICAL,
            AlertType.MILITARY: MessagePriority.HIGH,
            AlertType.WATCHLIST: MessagePriority.HIGH,
            AlertType.PROXIMITY: MessagePriority.MEDIUM,
            AlertType.INTERESTING: MessagePriority.LOW,
            AlertType.CUSTOM: MessagePriority.MEDIUM
        }
        
        return priority_map.get(self.alert_type, MessagePriority.MEDIUM)
    
    def to_alert_message(self, channel: str, template: Optional[MessageTemplate] = None) -> AlertMessage:
        """
        Convert to AlertMessage for delivery
        
        Args:
            channel: Channel name to send on
            template: Optional message template
            
        Returns:
            AlertMessage ready for delivery
        """
        # Choose format based on template or default to standard
        if template:
            if template.format_type == MessageFormat.JSON:
                content = self.to_json()
            elif template.format_type == MessageFormat.COMPACT:
                content = self.to_compact(template.max_length or 100)
            else:
                content = self.to_meshtastic_text(template)
        else:
            content = self.to_meshtastic_text()
        
        priority = self.get_priority(template)
        
        return AlertMessage(
            content=content,
            channel=channel,
            priority=priority,
            aircraft_icao=self.aircraft_icao,
            alert_type=self.alert_type.value,
            position=self.position,
            metadata={
                'original_alert': self.to_json(include_metadata=False),
                'formatted_with_template': template.name if template else None
            }
        )


class MessageFormatter:
    """
    Main message formatter with template management and customizable field selection
    """
    
    def __init__(self):
        """Initialize formatter with default templates"""
        self.templates: Dict[str, MessageTemplate] = {}
        self.custom_field_formatters: Dict[str, callable] = {}
        self._load_default_templates()
        self._load_default_field_formatters()
    
    def _load_default_templates(self):
        """Load default message templates"""
        # Standard template
        self.templates['standard'] = MessageTemplate(
            name='standard',
            format_type=MessageFormat.STANDARD,
            template_string="{alert_type_upper}: {icao} ({callsign}) | Pos: {position} | Alt: {altitude} | Spd: {speed} | @{timestamp}",
            max_length=200,
            include_position=True,
            include_timestamp=True,
            include_altitude=True,
            include_speed=True
        )
        
        # Compact template
        self.templates['compact'] = MessageTemplate(
            name='compact',
            format_type=MessageFormat.COMPACT,
            template_string="{alert_type_upper[0]}:{icao}|{position}|{altitude}|{speed}",
            max_length=100,
            include_position=True,
            include_timestamp=False,
            include_altitude=True,
            include_speed=True
        )
        
        # JSON template
        self.templates['json'] = MessageTemplate(
            name='json',
            format_type=MessageFormat.JSON,
            template_string="JSON",  # Placeholder for JSON (not used in formatting)
            max_length=0,  # No limit for JSON
            include_position=True,
            include_timestamp=True,
            include_altitude=True,
            include_speed=True
        )
        
        # Emergency template (high priority, minimal info)
        self.templates['emergency'] = MessageTemplate(
            name='emergency',
            format_type=MessageFormat.CUSTOM,
            template_string="🚨 EMERGENCY: {icao} ({callsign}) at {position} - {message}",
            max_length=150,
            include_position=True,
            include_timestamp=False,
            priority_mapping={
                AlertType.EMERGENCY.value: MessagePriority.CRITICAL
            }
        )
        
        # Watchlist template
        self.templates['watchlist'] = MessageTemplate(
            name='watchlist',
            format_type=MessageFormat.CUSTOM,
            template_string="⚠️ WATCHLIST: {icao} ({callsign}) | {position} | {altitude} | {distance}",
            max_length=180,
            include_position=True,
            include_timestamp=False
        )
        
        # Military template
        self.templates['military'] = MessageTemplate(
            name='military',
            format_type=MessageFormat.CUSTOM,
            template_string="🛡️ MILITARY: {icao} | {position} | {altitude} | {speed} | {heading}",
            max_length=160,
            include_position=True,
            include_timestamp=False
        )
        
        # Position-focused template with multiple formats
        self.templates['position_detailed'] = MessageTemplate(
            name='position_detailed',
            format_type=MessageFormat.CUSTOM,
            template_string="{alert_type_upper}: {icao} | Decimal: {position_decimal} | Grid: {position_maidenhead} | {distance_nm} @ {bearing_deg}",
            max_length=200,
            include_position=True,
            include_timestamp=False
        )
        
        # Speed and altitude focused template
        self.templates['flight_data'] = MessageTemplate(
            name='flight_data',
            format_type=MessageFormat.CUSTOM,
            template_string="{alert_type_upper}: {icao} ({callsign_short}) | {altitude_fl} | {speed_kt} | {heading_cardinal}",
            max_length=150,
            include_position=False,
            include_timestamp=False,
            include_altitude=True,
            include_speed=True
        )
        
        # Ultra-compact template for bandwidth-limited scenarios
        self.templates['ultra_compact'] = MessageTemplate(
            name='ultra_compact',
            format_type=MessageFormat.CUSTOM,
            template_string="{alert_type[0]}{icao}{position_compact}{altitude_fl}",
            max_length=50,
            include_position=True,
            include_timestamp=False,
            include_altitude=True,
            include_speed=False
        )
        
        # Time-focused template
        self.templates['timestamped'] = MessageTemplate(
            name='timestamped',
            format_type=MessageFormat.CUSTOM,
            template_string="[{time_hms}] {alert_type_upper}: {icao} | {position_compact} | {altitude_ft}",
            max_length=120,
            include_position=True,
            include_timestamp=True,
            include_altitude=True
        )
        
        # Distance-focused template for proximity alerts
        self.templates['proximity'] = MessageTemplate(
            name='proximity',
            format_type=MessageFormat.CUSTOM,
            template_string="📍 PROXIMITY: {icao} | {distance_nm} away at {bearing_deg} | {altitude_ft} | {speed_kt}",
            max_length=180,
            include_position=False,  # Using distance/bearing instead
            include_timestamp=False,
            priority_mapping={
                AlertType.PROXIMITY.value: MessagePriority.HIGH
            }
        )
    
    def add_template(self, template: MessageTemplate):
        """
        Add or update a message template
        
        Args:
            template: Template to add
        """
        self.templates[template.name] = template
    
    def get_template(self, name: str) -> Optional[MessageTemplate]:
        """
        Get template by name
        
        Args:
            name: Template name
            
        Returns:
            Template if found, None otherwise
        """
        return self.templates.get(name)
    
    def list_templates(self) -> List[str]:
        """
        Get list of available template names
        
        Returns:
            List of template names
        """
        return list(self.templates.keys())
    
    def format_aircraft_alert(self, aircraft: EnhancedAircraft, alert_type: AlertType,
                            template_name: str = 'standard', channel: str = 'LongFast',
                            message: Optional[str] = None, **kwargs) -> AlertMessage:
        """
        Format aircraft alert using specified template
        
        Args:
            aircraft: Aircraft data
            alert_type: Type of alert
            template_name: Name of template to use
            channel: Channel to send on
            message: Optional custom message
            **kwargs: Additional fields for StandardAlertMessage
            
        Returns:
            Formatted AlertMessage ready for delivery
        """
        # Create standard alert message
        standard_alert = StandardAlertMessage.from_aircraft(
            aircraft, alert_type, message, **kwargs
        )
        
        # Get template
        template = self.get_template(template_name)
        if not template:
            logger.warning(f"Template '{template_name}' not found, using standard")
            template = self.get_template('standard')
        
        # Convert to AlertMessage
        return standard_alert.to_alert_message(channel, template)
    
    def _load_default_field_formatters(self):
        """Load default field formatters for custom template processing"""
        from .position_formatter import PositionFormatter, CoordinateFormat, DistanceUnit
        
        self.custom_field_formatters = {
            # Position formatters
            'position_decimal': lambda lat, lon: PositionFormatter.format_position(lat, lon, CoordinateFormat.DECIMAL_DEGREES),
            'position_compact': lambda lat, lon: PositionFormatter.format_position(lat, lon, CoordinateFormat.COMPACT),
            'position_dms': lambda lat, lon: PositionFormatter.format_position(lat, lon, CoordinateFormat.DEGREES_MINUTES_SECONDS),
            'position_maidenhead': lambda lat, lon: PositionFormatter.format_position(lat, lon, CoordinateFormat.MAIDENHEAD),
            'position_utm': lambda lat, lon: PositionFormatter.format_position(lat, lon, CoordinateFormat.UTM),
            
            # Distance formatters
            'distance_nm': lambda dist: PositionFormatter.format_distance(dist, DistanceUnit.NAUTICAL_MILES),
            'distance_km': lambda dist: PositionFormatter.format_distance(dist, DistanceUnit.KILOMETERS),
            'distance_mi': lambda dist: PositionFormatter.format_distance(dist, DistanceUnit.STATUTE_MILES),
            
            # Bearing formatter
            'bearing_deg': lambda brg: PositionFormatter.format_bearing(brg),
            
            # Altitude formatters
            'altitude_ft': lambda alt: PositionFormatter.format_altitude(alt, "ft") if alt is not None else "Unknown",
            'altitude_m': lambda alt: PositionFormatter.format_altitude(alt * 0.3048, "m") if alt is not None else "Unknown",
            'altitude_fl': lambda alt: f"FL{int(alt/100):03d}" if alt is not None and alt >= 1000 else f"{alt}ft" if alt is not None else "Unknown",
            
            # Speed formatters
            'speed_kt': lambda spd: f"{spd:.0f}kt" if spd is not None else "Unknown",
            'speed_mph': lambda spd: f"{spd * 1.15078:.0f}mph" if spd is not None else "Unknown",
            'speed_kmh': lambda spd: f"{spd * 1.852:.0f}km/h" if spd is not None else "Unknown",
            
            # Heading formatters
            'heading_deg': lambda hdg: f"{hdg:.0f}°" if hdg is not None else "Unknown",
            'heading_cardinal': lambda hdg: self._heading_to_cardinal(hdg) if hdg is not None else "Unknown",
            
            # Time formatters
            'time_hms': lambda dt: dt.strftime("%H:%M:%S"),
            'time_hm': lambda dt: dt.strftime("%H:%M"),
            'date_ymd': lambda dt: dt.strftime("%Y-%m-%d"),
            'date_dmy': lambda dt: dt.strftime("%d/%m/%Y"),
            
            # ICAO formatters
            'icao_upper': lambda icao: icao.upper() if icao else "UNKNOWN",
            'icao_lower': lambda icao: icao.lower() if icao else "unknown",
            
            # Callsign formatters
            'callsign_clean': lambda cs: cs.strip() if cs else "Unknown",
            'callsign_short': lambda cs: cs[:8] if cs else "Unknown",
        }
    
    def _heading_to_cardinal(self, heading: float) -> str:
        """Convert heading to cardinal direction"""
        directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                     "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        index = int((heading + 11.25) / 22.5) % 16
        return directions[index]
    
    def add_custom_field_formatter(self, name: str, formatter: callable):
        """
        Add a custom field formatter
        
        Args:
            name: Name of the formatter
            formatter: Callable that formats the field
        """
        self.custom_field_formatters[name] = formatter
    
    def create_template_from_config(self, config: Dict[str, Any]) -> MessageTemplate:
        """
        Create a message template from configuration dictionary
        
        Args:
            config: Template configuration dictionary
            
        Returns:
            MessageTemplate instance
        """
        return MessageTemplate(
            name=config['name'],
            format_type=MessageFormat(config.get('format_type', 'custom')),
            template_string=config['template_string'],
            max_length=config.get('max_length', 200),
            include_position=config.get('include_position', True),
            include_timestamp=config.get('include_timestamp', True),
            include_altitude=config.get('include_altitude', True),
            include_speed=config.get('include_speed', True),
            priority_mapping=config.get('priority_mapping', {})
        )
    
    def load_templates_from_config(self, templates_config: List[Dict[str, Any]]):
        """
        Load multiple templates from configuration
        
        Args:
            templates_config: List of template configuration dictionaries
        """
        for template_config in templates_config:
            try:
                template = self.create_template_from_config(template_config)
                self.add_template(template)
                logger.info(f"Loaded template: {template.name}")
            except Exception as e:
                logger.error(f"Failed to load template {template_config.get('name', 'unknown')}: {e}")
    
    def get_available_template_fields(self) -> Dict[str, str]:
        """
        Get dictionary of available template fields and their descriptions
        
        Returns:
            Dictionary mapping field names to descriptions
        """
        return {
            # Basic aircraft fields
            'icao': 'Aircraft ICAO hex code',
            'callsign': 'Aircraft callsign',
            'alert_type': 'Alert type (lowercase)',
            'alert_type_upper': 'Alert type (uppercase)',
            'message': 'Custom alert message',
            
            # Position fields
            'lat': 'Latitude (decimal degrees)',
            'lon': 'Longitude (decimal degrees)',
            'position': 'Position (lat,lon)',
            'position_decimal': 'Position in decimal degrees format',
            'position_compact': 'Position in compact format',
            'position_dms': 'Position in degrees/minutes/seconds',
            'position_maidenhead': 'Position in Maidenhead locator',
            'position_utm': 'Position in UTM coordinates',
            
            # Flight data fields
            'altitude': 'Altitude with unit',
            'altitude_ft': 'Altitude in feet',
            'altitude_m': 'Altitude in meters',
            'altitude_fl': 'Altitude as flight level',
            'speed': 'Ground speed with unit',
            'speed_kt': 'Speed in knots',
            'speed_mph': 'Speed in miles per hour',
            'speed_kmh': 'Speed in kilometers per hour',
            'heading': 'Track angle with unit',
            'heading_deg': 'Heading in degrees',
            'heading_cardinal': 'Heading as cardinal direction',
            'squawk': 'Transponder squawk code',
            
            # Distance/bearing fields (if calculated)
            'distance': 'Distance from observer',
            'distance_nm': 'Distance in nautical miles',
            'distance_km': 'Distance in kilometers',
            'distance_mi': 'Distance in statute miles',
            'bearing': 'Bearing from observer',
            'bearing_deg': 'Bearing in degrees',
            
            # Time fields
            'timestamp': 'Timestamp (HH:MM:SS)',
            'time_hms': 'Time in HH:MM:SS format',
            'time_hm': 'Time in HH:MM format',
            'date': 'Date (YYYY-MM-DD)',
            'date_ymd': 'Date in YYYY-MM-DD format',
            'date_dmy': 'Date in DD/MM/YYYY format',
            
            # Formatted variants
            'icao_upper': 'ICAO in uppercase',
            'icao_lower': 'ICAO in lowercase',
            'callsign_clean': 'Cleaned callsign',
            'callsign_short': 'Callsign truncated to 8 characters',
        }
    
    def validate_template_string(self, template_string: str) -> tuple[bool, List[str]]:
        """
        Validate a template string and return any issues
        
        Args:
            template_string: Template string to validate
            
        Returns:
            Tuple of (is_valid, list_of_issues)
        """
        issues = []
        available_fields = self.get_available_template_fields()
        
        # Extract field names from template string
        import re
        field_pattern = r'\{([^}]+)\}'
        fields_used = re.findall(field_pattern, template_string)
        
        # Check for unknown fields
        for field in fields_used:
            if field not in available_fields:
                issues.append(f"Unknown field: {field}")
        
        # Check for basic syntax issues
        if template_string.count('{') != template_string.count('}'):
            issues.append("Mismatched braces in template string")
        
        # Check for empty template
        if not template_string.strip():
            issues.append("Template string cannot be empty")
        
        return len(issues) == 0, issues
    
    def format_with_custom_fields(self, template_string: str, aircraft: Any, 
                                 alert_type: AlertType, **kwargs) -> str:
        """
        Format template string with custom field formatters
        
        Args:
            template_string: Template string to format
            aircraft: Aircraft data
            alert_type: Alert type
            **kwargs: Additional fields (distance, bearing, etc.)
            
        Returns:
            Formatted string
        """
        # Create standard substitution dictionary
        subs = self._create_substitution_dict(aircraft, alert_type, **kwargs)
        
        # Add custom formatted fields
        if hasattr(aircraft, 'latitude') and hasattr(aircraft, 'longitude'):
            if aircraft.latitude is not None and aircraft.longitude is not None:
                # Position formatters
                subs['position_decimal'] = self.custom_field_formatters['position_decimal'](aircraft.latitude, aircraft.longitude)
                subs['position_compact'] = self.custom_field_formatters['position_compact'](aircraft.latitude, aircraft.longitude)
                subs['position_dms'] = self.custom_field_formatters['position_dms'](aircraft.latitude, aircraft.longitude)
                subs['position_maidenhead'] = self.custom_field_formatters['position_maidenhead'](aircraft.latitude, aircraft.longitude)
                subs['position_utm'] = self.custom_field_formatters['position_utm'](aircraft.latitude, aircraft.longitude)
        
        # Altitude formatters
        altitude = getattr(aircraft, 'altitude_baro', None)
        if altitude is not None:
            subs['altitude_ft'] = self.custom_field_formatters['altitude_ft'](altitude)
            subs['altitude_m'] = self.custom_field_formatters['altitude_m'](altitude)
            subs['altitude_fl'] = self.custom_field_formatters['altitude_fl'](altitude)
        
        # Speed formatters
        speed = getattr(aircraft, 'ground_speed', None)
        if speed is not None:
            subs['speed_kt'] = self.custom_field_formatters['speed_kt'](speed)
            subs['speed_mph'] = self.custom_field_formatters['speed_mph'](speed)
            subs['speed_kmh'] = self.custom_field_formatters['speed_kmh'](speed)
        
        # Heading formatters
        heading = getattr(aircraft, 'track_angle', None)
        if heading is not None:
            subs['heading_deg'] = self.custom_field_formatters['heading_deg'](heading)
            subs['heading_cardinal'] = self.custom_field_formatters['heading_cardinal'](heading)
        
        # Distance/bearing formatters
        distance = kwargs.get('distance')
        if distance is not None:
            subs['distance_nm'] = self.custom_field_formatters['distance_nm'](distance)
            subs['distance_km'] = self.custom_field_formatters['distance_km'](distance)
            subs['distance_mi'] = self.custom_field_formatters['distance_mi'](distance)
        
        bearing = kwargs.get('bearing')
        if bearing is not None:
            subs['bearing_deg'] = self.custom_field_formatters['bearing_deg'](bearing)
        
        # Time formatters
        timestamp = kwargs.get('timestamp', datetime.now())
        subs['time_hms'] = self.custom_field_formatters['time_hms'](timestamp)
        subs['time_hm'] = self.custom_field_formatters['time_hm'](timestamp)
        subs['date_ymd'] = self.custom_field_formatters['date_ymd'](timestamp)
        subs['date_dmy'] = self.custom_field_formatters['date_dmy'](timestamp)
        
        # ICAO/Callsign formatters
        icao = getattr(aircraft, 'icao', None)
        if icao:
            subs['icao_upper'] = self.custom_field_formatters['icao_upper'](icao)
            subs['icao_lower'] = self.custom_field_formatters['icao_lower'](icao)
        
        callsign = getattr(aircraft, 'callsign', None)
        if callsign:
            subs['callsign_clean'] = self.custom_field_formatters['callsign_clean'](callsign)
            subs['callsign_short'] = self.custom_field_formatters['callsign_short'](callsign)
        
        # Format the template
        try:
            return template_string.format(**subs)
        except KeyError as e:
            logger.warning(f"Template formatting error: missing key {e}")
            # Return basic format as fallback
            return f"{alert_type.value.upper()}: {getattr(aircraft, 'icao', 'UNKNOWN')}"
    
    def _create_substitution_dict(self, aircraft: Any, alert_type: AlertType, **kwargs) -> Dict[str, str]:
        """Create basic substitution dictionary for template formatting"""
        timestamp = kwargs.get('timestamp', datetime.now())
        
        subs = {
            'icao': getattr(aircraft, 'icao', 'UNKNOWN'),
            'callsign': getattr(aircraft, 'callsign', None) or 'Unknown',
            'alert_type': alert_type.value,
            'alert_type_upper': alert_type.value.upper(),
            'timestamp': timestamp.strftime("%H:%M:%S"),
            'date': timestamp.strftime("%Y-%m-%d"),
            'message': kwargs.get('message', ''),
        }
        
        # Position fields
        if hasattr(aircraft, 'latitude') and hasattr(aircraft, 'longitude'):
            if aircraft.latitude is not None and aircraft.longitude is not None:
                subs['lat'] = f"{aircraft.latitude:.4f}"
                subs['lon'] = f"{aircraft.longitude:.4f}"
                subs['position'] = f"{aircraft.latitude:.4f},{aircraft.longitude:.4f}"
            else:
                subs['lat'] = 'Unknown'
                subs['lon'] = 'Unknown'
                subs['position'] = 'Unknown'
        else:
            subs['lat'] = 'Unknown'
            subs['lon'] = 'Unknown'
            subs['position'] = 'Unknown'
        
        # Flight data fields
        altitude = getattr(aircraft, 'altitude_baro', None)
        subs['altitude'] = f"{altitude}ft" if altitude is not None else 'Unknown'
        
        speed = getattr(aircraft, 'ground_speed', None)
        subs['speed'] = f"{speed:.0f}kt" if speed is not None else 'Unknown'
        
        heading = getattr(aircraft, 'track_angle', None)
        subs['heading'] = f"{heading:.0f}°" if heading is not None else 'Unknown'
        
        subs['squawk'] = getattr(aircraft, 'squawk', None) or 'Unknown'
        
        # Distance/bearing fields
        distance = kwargs.get('distance')
        subs['distance'] = f"{distance:.1f}nm" if distance is not None else 'Unknown'
        
        bearing = kwargs.get('bearing')
        subs['bearing'] = f"{bearing:.0f}°" if bearing is not None else 'Unknown'
        
        return subs
    
    def validate_message_length(self, message: str, max_length: int) -> tuple[bool, str]:
        """
        Validate message length and provide truncation if needed
        
        Args:
            message: Message to validate
            max_length: Maximum allowed length
            
        Returns:
            Tuple of (is_valid, processed_message)
        """
        if len(message) <= max_length:
            return True, message
        
        if max_length <= 3:
            return False, message[:max_length]
        
        truncated = message[:max_length-3] + "..."
        return False, truncated