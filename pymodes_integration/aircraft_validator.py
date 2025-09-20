"""
Aircraft Data Validation and Cleanup Module

Implements age-based aircraft removal, data consistency checking, outlier detection,
and memory management for large aircraft datasets.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import statistics

from .aircraft import EnhancedAircraft

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for validation issues"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """Represents a data validation issue"""
    severity: ValidationSeverity
    field: str
    message: str
    current_value: Any
    expected_range: Optional[Tuple[Any, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class CleanupConfig:
    """Configuration for aircraft cleanup operations"""
    # Age-based cleanup
    default_timeout_seconds: int = 300  # 5 minutes
    surface_timeout_seconds: int = 180  # 3 minutes for surface aircraft
    airborne_timeout_seconds: int = 600  # 10 minutes for airborne aircraft
    
    # Memory management
    max_aircraft_count: int = 10000
    cleanup_batch_size: int = 100
    memory_pressure_threshold: float = 0.8  # 80% of max
    
    # Data consistency
    enable_outlier_detection: bool = True
    position_jump_threshold_km: float = 50.0  # Suspicious if >50km in short time
    altitude_jump_threshold_ft: int = 5000    # Suspicious if >5000ft in short time
    speed_jump_threshold_kts: float = 200.0   # Suspicious if >200kts change
    
    # Validation thresholds
    min_message_count_for_validation: int = 3
    max_validation_issues_per_aircraft: int = 10


class AircraftValidator:
    """
    Handles aircraft data validation, outlier detection, and cleanup operations
    
    Provides comprehensive validation for aircraft data consistency,
    age-based cleanup, and memory management for large datasets.
    """
    
    def __init__(self, config: Optional[CleanupConfig] = None):
        """
        Initialize aircraft validator
        
        Args:
            config: Cleanup and validation configuration
        """
        self.config = config or CleanupConfig()
        
        # Validation issue tracking
        self.validation_issues: Dict[str, List[ValidationIssue]] = {}
        
        # Statistics
        self.stats = {
            'aircraft_validated': 0,
            'validation_issues_found': 0,
            'outliers_detected': 0,
            'aircraft_cleaned_up': 0,
            'memory_cleanups_performed': 0,
            'consistency_checks_performed': 0
        }
        
        logger.info("AircraftValidator initialized")
        logger.info(f"Default timeout: {self.config.default_timeout_seconds}s")
        logger.info(f"Max aircraft: {self.config.max_aircraft_count}")
    
    def validate_aircraft_data(self, aircraft: EnhancedAircraft) -> List[ValidationIssue]:
        """
        Validate aircraft data for consistency and reasonableness
        
        Args:
            aircraft: Aircraft to validate
            
        Returns:
            List of validation issues found
        """
        self.stats['aircraft_validated'] += 1
        issues = []
        
        # Skip validation for aircraft with too few messages
        if aircraft.message_count < self.config.min_message_count_for_validation:
            return issues
        
        # Validate position data
        issues.extend(self._validate_position_data(aircraft))
        
        # Validate altitude data
        issues.extend(self._validate_altitude_data(aircraft))
        
        # Validate velocity data
        issues.extend(self._validate_velocity_data(aircraft))
        
        # Validate temporal consistency
        issues.extend(self._validate_temporal_consistency(aircraft))
        
        # Store issues for tracking
        if issues:
            self.validation_issues[aircraft.icao] = issues
            self.stats['validation_issues_found'] += len(issues)
        
        self.stats['consistency_checks_performed'] += 1
        
        return issues
    
    def detect_outliers(self, aircraft: EnhancedAircraft, 
                       previous_aircraft_state: Optional[EnhancedAircraft] = None) -> List[ValidationIssue]:
        """
        Detect outliers in aircraft data updates
        
        Args:
            aircraft: Current aircraft state
            previous_aircraft_state: Previous state for comparison
            
        Returns:
            List of outlier issues detected
        """
        if not self.config.enable_outlier_detection or not previous_aircraft_state:
            return []
        
        issues = []
        time_diff = (aircraft.last_seen - previous_aircraft_state.last_seen).total_seconds()
        
        # Skip if time difference is too large (normal for outlier detection)
        if time_diff > 60:  # More than 1 minute
            return issues
        
        # Check position jumps
        if (aircraft.latitude is not None and aircraft.longitude is not None and
            previous_aircraft_state.latitude is not None and previous_aircraft_state.longitude is not None):
            
            distance_km = self._calculate_distance_km(
                aircraft.latitude, aircraft.longitude,
                previous_aircraft_state.latitude, previous_aircraft_state.longitude
            )
            
            # Calculate expected maximum distance based on time and reasonable speed
            max_reasonable_speed_kts = 600  # Mach 0.9 at altitude
            max_distance_km = (max_reasonable_speed_kts * 1.852 * time_diff) / 3600
            
            if distance_km > max_distance_km and distance_km > self.config.position_jump_threshold_km:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="position",
                    message=f"Suspicious position jump: {distance_km:.1f}km in {time_diff:.1f}s",
                    current_value=(aircraft.latitude, aircraft.longitude),
                    expected_range=(0, max_distance_km)
                ))
        
        # Check altitude jumps
        if (aircraft.altitude_baro is not None and 
            previous_aircraft_state.altitude_baro is not None):
            
            altitude_diff = abs(aircraft.altitude_baro - previous_aircraft_state.altitude_baro)
            max_climb_rate = 6000  # ft/min for military aircraft
            max_altitude_change = (max_climb_rate * time_diff) / 60
            
            if altitude_diff > max_altitude_change and altitude_diff > self.config.altitude_jump_threshold_ft:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="altitude",
                    message=f"Suspicious altitude jump: {altitude_diff}ft in {time_diff:.1f}s",
                    current_value=aircraft.altitude_baro,
                    expected_range=(-max_altitude_change, max_altitude_change)
                ))
        
        # Check speed jumps
        if (aircraft.ground_speed is not None and 
            previous_aircraft_state.ground_speed is not None):
            
            speed_diff = abs(aircraft.ground_speed - previous_aircraft_state.ground_speed)
            
            if speed_diff > self.config.speed_jump_threshold_kts:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="ground_speed",
                    message=f"Suspicious speed jump: {speed_diff:.1f}kts in {time_diff:.1f}s",
                    current_value=aircraft.ground_speed,
                    expected_range=None
                ))
        
        if issues:
            self.stats['outliers_detected'] += len(issues)
        
        return issues
    
    def cleanup_old_aircraft(self, aircraft_dict: Dict[str, EnhancedAircraft], 
                           force_timeout: Optional[int] = None) -> int:
        """
        Remove aircraft that haven't been seen recently
        
        Args:
            aircraft_dict: Dictionary of aircraft to clean up
            force_timeout: Override default timeout
            
        Returns:
            Number of aircraft removed
        """
        current_time = datetime.now()
        removed_count = 0
        
        aircraft_to_remove = []
        
        for icao, aircraft in aircraft_dict.items():
            # Determine appropriate timeout based on aircraft type
            if force_timeout is not None:
                timeout = force_timeout
            elif aircraft.altitude_baro is not None and aircraft.altitude_baro > 1000:
                # Airborne aircraft - longer timeout
                timeout = self.config.airborne_timeout_seconds
            elif aircraft.has_position() and aircraft.altitude_baro is not None and aircraft.altitude_baro <= 1000:
                # Surface aircraft - shorter timeout
                timeout = self.config.surface_timeout_seconds
            else:
                # Unknown state - default timeout
                timeout = self.config.default_timeout_seconds
            
            # Check if aircraft should be removed
            age_seconds = (current_time - aircraft.last_seen).total_seconds()
            if age_seconds > timeout:
                aircraft_to_remove.append(icao)
        
        # Remove old aircraft
        for icao in aircraft_to_remove:
            del aircraft_dict[icao]
            # Also remove validation issues
            if icao in self.validation_issues:
                del self.validation_issues[icao]
            removed_count += 1
        
        self.stats['aircraft_cleaned_up'] += removed_count
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} old aircraft")
        
        return removed_count
    
    def manage_memory_pressure(self, aircraft_dict: Dict[str, EnhancedAircraft]) -> int:
        """
        Manage memory pressure by removing oldest aircraft when approaching limits
        
        Args:
            aircraft_dict: Dictionary of aircraft to manage
            
        Returns:
            Number of aircraft removed
        """
        current_count = len(aircraft_dict)
        
        # Check if we're approaching memory pressure
        pressure_threshold = int(self.config.max_aircraft_count * self.config.memory_pressure_threshold)
        
        if current_count < pressure_threshold:
            return 0
        
        # Calculate how many to remove
        target_count = int(self.config.max_aircraft_count * 0.7)  # Remove to 70% capacity
        remove_count = min(current_count - target_count, self.config.cleanup_batch_size)
        
        if remove_count <= 0:
            return 0
        
        # Sort aircraft by last_seen time and remove oldest
        sorted_aircraft = sorted(
            aircraft_dict.items(),
            key=lambda x: x[1].last_seen
        )
        
        removed_count = 0
        for i in range(min(remove_count, len(sorted_aircraft))):
            icao = sorted_aircraft[i][0]
            del aircraft_dict[icao]
            if icao in self.validation_issues:
                del self.validation_issues[icao]
            removed_count += 1
        
        self.stats['memory_cleanups_performed'] += 1
        logger.warning(f"Memory pressure cleanup: removed {removed_count} oldest aircraft")
        
        return removed_count
    
    def get_validation_summary(self, icao: str = None) -> Dict[str, Any]:
        """
        Get validation summary for specific aircraft or all aircraft
        
        Args:
            icao: Specific aircraft ICAO (optional)
            
        Returns:
            Validation summary dictionary
        """
        if icao:
            issues = self.validation_issues.get(icao, [])
            return {
                'icao': icao,
                'total_issues': len(issues),
                'issues_by_severity': {
                    severity.value: len([i for i in issues if i.severity == severity])
                    for severity in ValidationSeverity
                },
                'issues': [
                    {
                        'severity': issue.severity.value,
                        'field': issue.field,
                        'message': issue.message,
                        'timestamp': issue.timestamp.isoformat()
                    }
                    for issue in issues
                ]
            }
        else:
            # Summary for all aircraft
            all_issues = []
            for aircraft_issues in self.validation_issues.values():
                all_issues.extend(aircraft_issues)
            
            return {
                'total_aircraft_with_issues': len(self.validation_issues),
                'total_issues': len(all_issues),
                'issues_by_severity': {
                    severity.value: len([i for i in all_issues if i.severity == severity])
                    for severity in ValidationSeverity
                },
                'issues_by_field': self._group_issues_by_field(all_issues)
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get validator statistics"""
        return {
            **self.stats,
            'aircraft_with_issues': len(self.validation_issues),
            'total_validation_issues': sum(len(issues) for issues in self.validation_issues.values()),
            'config': {
                'default_timeout': self.config.default_timeout_seconds,
                'max_aircraft': self.config.max_aircraft_count,
                'outlier_detection_enabled': self.config.enable_outlier_detection
            }
        }
    
    def reset_statistics(self) -> None:
        """Reset all statistics"""
        self.stats = {key: 0 for key in self.stats}
        self.validation_issues.clear()
        logger.info("Aircraft validator statistics reset")
    
    def _validate_position_data(self, aircraft: EnhancedAircraft) -> List[ValidationIssue]:
        """Validate position-related data"""
        issues = []
        
        # Check if position coordinates are reasonable
        if aircraft.latitude is not None:
            if not (-90 <= aircraft.latitude <= 90):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="latitude",
                    message=f"Latitude out of valid range: {aircraft.latitude}",
                    current_value=aircraft.latitude,
                    expected_range=(-90, 90)
                ))
        
        if aircraft.longitude is not None:
            if not (-180 <= aircraft.longitude <= 180):
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="longitude",
                    message=f"Longitude out of valid range: {aircraft.longitude}",
                    current_value=aircraft.longitude,
                    expected_range=(-180, 180)
                ))
        
        # Check for incomplete position data
        if (aircraft.latitude is None) != (aircraft.longitude is None):
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="position",
                message="Incomplete position data (only lat or lon available)",
                current_value=(aircraft.latitude, aircraft.longitude)
            ))
        
        return issues
    
    def _validate_altitude_data(self, aircraft: EnhancedAircraft) -> List[ValidationIssue]:
        """Validate altitude-related data"""
        issues = []
        
        # Check barometric altitude
        if aircraft.altitude_baro is not None:
            if aircraft.altitude_baro < -2000 or aircraft.altitude_baro > 60000:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="altitude_baro",
                    message=f"Altitude outside typical range: {aircraft.altitude_baro}ft",
                    current_value=aircraft.altitude_baro,
                    expected_range=(-2000, 60000)
                ))
        
        # Check GNSS altitude
        if aircraft.altitude_gnss is not None:
            if aircraft.altitude_gnss < -2000 or aircraft.altitude_gnss > 60000:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="altitude_gnss",
                    message=f"GNSS altitude outside typical range: {aircraft.altitude_gnss}ft",
                    current_value=aircraft.altitude_gnss,
                    expected_range=(-2000, 60000)
                ))
        
        # Check altitude consistency
        if (aircraft.altitude_baro is not None and aircraft.altitude_gnss is not None):
            diff = abs(aircraft.altitude_baro - aircraft.altitude_gnss)
            if diff > 1000:  # More than 1000ft difference
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    field="altitude_consistency",
                    message=f"Large difference between baro and GNSS altitude: {diff}ft",
                    current_value=diff,
                    expected_range=(0, 1000)
                ))
        
        return issues
    
    def _validate_velocity_data(self, aircraft: EnhancedAircraft) -> List[ValidationIssue]:
        """Validate velocity-related data"""
        issues = []
        
        # Check ground speed
        if aircraft.ground_speed is not None:
            if aircraft.ground_speed < 0 or aircraft.ground_speed > 1000:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="ground_speed",
                    message=f"Ground speed outside reasonable range: {aircraft.ground_speed}kts",
                    current_value=aircraft.ground_speed,
                    expected_range=(0, 1000)
                ))
        
        # Check track angle
        if aircraft.track_angle is not None:
            if aircraft.track_angle < 0 or aircraft.track_angle >= 360:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    field="track_angle",
                    message=f"Track angle out of valid range: {aircraft.track_angle}°",
                    current_value=aircraft.track_angle,
                    expected_range=(0, 360)
                ))
        
        # Check vertical rate
        if aircraft.vertical_rate is not None:
            if abs(aircraft.vertical_rate) > 10000:  # More than 10,000 ft/min
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    field="vertical_rate",
                    message=f"Extreme vertical rate: {aircraft.vertical_rate}ft/min",
                    current_value=aircraft.vertical_rate,
                    expected_range=(-10000, 10000)
                ))
        
        return issues
    
    def _validate_temporal_consistency(self, aircraft: EnhancedAircraft) -> List[ValidationIssue]:
        """Validate temporal consistency of aircraft data"""
        issues = []
        
        # Check if first_seen is after last_seen
        if aircraft.first_seen > aircraft.last_seen:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                field="temporal_consistency",
                message="First seen time is after last seen time",
                current_value=(aircraft.first_seen, aircraft.last_seen)
            ))
        
        # Check if last_seen is in the future
        now = datetime.now()
        if aircraft.last_seen > now + timedelta(seconds=60):  # Allow 1 minute clock skew
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                field="last_seen",
                message="Last seen time is in the future",
                current_value=aircraft.last_seen
            ))
        
        return issues
    
    def _calculate_distance_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points using haversine formula"""
        import math
        
        # Convert to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Haversine formula
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        a = (math.sin(dlat/2)**2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2)
        c = 2 * math.asin(math.sqrt(a))
        
        # Earth radius in kilometers
        r = 6371
        
        return c * r
    
    def _group_issues_by_field(self, issues: List[ValidationIssue]) -> Dict[str, int]:
        """Group validation issues by field name"""
        field_counts = {}
        for issue in issues:
            field_counts[issue.field] = field_counts.get(issue.field, 0) + 1
        return field_counts