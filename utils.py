"""
Shared utilities and helper functions for Ursine Capture system.
"""

import logging
import math
import re
import subprocess
import psutil
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Optional, Callable, Dict, List
from enum import Enum
from dataclasses import dataclass, field


class ErrorSeverity(Enum):
    """Error severity levels for system monitoring."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ComponentType(Enum):
    """System component types for error tracking."""
    RECEIVER = "RECEIVER"
    DUMP1090 = "DUMP1090"
    HACKRF = "HACKRF"
    MESHTASTIC = "MESHTASTIC"
    DASHBOARD = "DASHBOARD"
    CONFIG = "CONFIG"
    AIRCRAFT_TRACKER = "AIRCRAFT_TRACKER"


@dataclass
class SystemError:
    """Structured error information for system monitoring."""
    component: ComponentType
    severity: ErrorSeverity
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    error_code: Optional[str] = None
    details: Optional[str] = None
    recovery_attempted: bool = False
    recovery_successful: bool = False
    occurrence_count: int = 1
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for JSON serialization."""
        return {
            "component": self.component.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "error_code": self.error_code,
            "details": self.details,
            "recovery_attempted": self.recovery_attempted,
            "recovery_successful": self.recovery_successful,
            "occurrence_count": self.occurrence_count
        }


class ErrorHandler:
    """Centralized error handling and recovery system."""
    
    def __init__(self, max_errors: int = 100):
        self.errors: List[SystemError] = []
        self.max_errors = max_errors
        self.recovery_strategies: Dict[str, Callable] = {}
        self.error_counts: Dict[str, int] = {}
        self.last_error_times: Dict[str, datetime] = {}
        self.logger = logging.getLogger(__name__)
        
    def register_recovery_strategy(self, error_pattern: str, recovery_func: Callable) -> None:
        """Register a recovery strategy for specific error patterns."""
        self.recovery_strategies[error_pattern] = recovery_func
        
    def handle_error(self, component: ComponentType, severity: ErrorSeverity, 
                    message: str, error_code: str = None, details: str = None,
                    attempt_recovery: bool = True) -> SystemError:
        """Handle an error with optional automatic recovery."""
        try:
            # Create error object
            error = SystemError(
                component=component,
                severity=severity,
                message=message,
                error_code=error_code,
                details=details
            )
            
            # Check for duplicate errors and update count
            error_key = f"{component.value}:{error_code or message}"
            if error_key in self.error_counts:
                self.error_counts[error_key] += 1
                error.occurrence_count = self.error_counts[error_key]
                
                # Update existing error instead of creating new one
                for existing_error in self.errors:
                    if (existing_error.component == component and 
                        existing_error.error_code == error_code and
                        existing_error.message == message):
                        existing_error.occurrence_count = error.occurrence_count
                        existing_error.timestamp = datetime.now()
                        break
                else:
                    self.errors.append(error)
            else:
                self.error_counts[error_key] = 1
                self.errors.append(error)
            
            # Limit error history
            if len(self.errors) > self.max_errors:
                self.errors = self.errors[-self.max_errors:]
            
            # Log the error
            log_level = self._get_log_level(severity)
            self.logger.log(log_level, f"[{component.value}] {message}")
            if details:
                self.logger.log(log_level, f"Details: {details}")
            
            # Attempt recovery if enabled and appropriate
            if attempt_recovery and severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
                recovery_success = self._attempt_recovery(error)
                error.recovery_attempted = True
                error.recovery_successful = recovery_success
                
                if recovery_success:
                    self.logger.info(f"Recovery successful for {component.value} error: {message}")
                else:
                    self.logger.warning(f"Recovery failed for {component.value} error: {message}")
            
            self.last_error_times[error_key] = datetime.now()
            return error
            
        except Exception as e:
            # Fallback logging if error handling itself fails
            self.logger.error(f"Error in error handler: {e}")
            return SystemError(component, severity, message)
    
    def _get_log_level(self, severity: ErrorSeverity) -> int:
        """Get appropriate logging level for error severity."""
        severity_map = {
            ErrorSeverity.LOW: logging.INFO,
            ErrorSeverity.MEDIUM: logging.WARNING,
            ErrorSeverity.HIGH: logging.ERROR,
            ErrorSeverity.CRITICAL: logging.CRITICAL
        }
        return severity_map.get(severity, logging.ERROR)
    
    def _attempt_recovery(self, error: SystemError) -> bool:
        """Attempt to recover from an error using registered strategies."""
        try:
            # Try specific recovery strategies
            for pattern, recovery_func in self.recovery_strategies.items():
                if pattern in error.message or pattern in (error.error_code or ""):
                    try:
                        return recovery_func(error)
                    except Exception as e:
                        self.logger.error(f"Recovery strategy failed: {e}")
                        return False
            
            # Default recovery strategies by component
            return self._default_recovery(error)
            
        except Exception as e:
            self.logger.error(f"Error during recovery attempt: {e}")
            return False
    
    def _default_recovery(self, error: SystemError) -> bool:
        """Default recovery strategies for different components."""
        try:
            if error.component == ComponentType.DUMP1090:
                return self._recover_dump1090()
            elif error.component == ComponentType.HACKRF:
                return self._recover_hackrf()
            elif error.component == ComponentType.MESHTASTIC:
                return self._recover_meshtastic()
            elif error.component == ComponentType.CONFIG:
                return self._recover_config()
            else:
                return False
                
        except Exception as e:
            self.logger.error(f"Default recovery failed: {e}")
            return False
    
    def _recover_dump1090(self) -> bool:
        """Attempt to recover dump1090 process."""
        try:
            # Kill existing processes
            kill_process("dump1090")
            time.sleep(2)
            
            # Try to restart (this would need access to dump1090 manager)
            # For now, just return True if we successfully killed the process
            return True
            
        except Exception as e:
            self.logger.error(f"dump1090 recovery failed: {e}")
            return False
    
    def _recover_hackrf(self) -> bool:
        """Attempt to recover HackRF connection."""
        try:
            # Reset HackRF device
            success, stdout, stderr = run_command(["hackrf_info"], timeout=5)
            return success
            
        except Exception as e:
            self.logger.error(f"HackRF recovery failed: {e}")
            return False
    
    def _recover_meshtastic(self) -> bool:
        """Attempt to recover Meshtastic connection."""
        try:
            # This would need access to Meshtastic manager
            # For now, just return False to indicate manual intervention needed
            return False
            
        except Exception as e:
            self.logger.error(f"Meshtastic recovery failed: {e}")
            return False
    
    def _recover_config(self) -> bool:
        """Attempt to recover from configuration errors."""
        try:
            # This would involve reloading configuration or using defaults
            return True
            
        except Exception as e:
            self.logger.error(f"Config recovery failed: {e}")
            return False
    
    def get_recent_errors(self, hours: int = 24) -> List[SystemError]:
        """Get errors from the last N hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [error for error in self.errors if error.timestamp >= cutoff_time]
    
    def get_critical_errors(self) -> List[SystemError]:
        """Get all critical errors."""
        return [error for error in self.errors if error.severity == ErrorSeverity.CRITICAL]
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of system errors."""
        recent_errors = self.get_recent_errors(24)
        critical_errors = self.get_critical_errors()
        
        component_counts = {}
        severity_counts = {}
        
        for error in recent_errors:
            component_counts[error.component.value] = component_counts.get(error.component.value, 0) + 1
            severity_counts[error.severity.value] = severity_counts.get(error.severity.value, 0) + 1
        
        return {
            "total_errors": len(self.errors),
            "recent_errors_24h": len(recent_errors),
            "critical_errors": len(critical_errors),
            "component_breakdown": component_counts,
            "severity_breakdown": severity_counts,
            "recovery_success_rate": self._calculate_recovery_success_rate()
        }
    
    def _calculate_recovery_success_rate(self) -> float:
        """Calculate the success rate of recovery attempts."""
        recovery_attempts = [error for error in self.errors if error.recovery_attempted]
        if not recovery_attempts:
            return 0.0
        
        successful_recoveries = [error for error in recovery_attempts if error.recovery_successful]
        return len(successful_recoveries) / len(recovery_attempts) * 100
    
    def clear_old_errors(self, days: int = 7) -> int:
        """Clear errors older than specified days."""
        cutoff_time = datetime.now() - timedelta(days=days)
        old_errors = [error for error in self.errors if error.timestamp < cutoff_time]
        self.errors = [error for error in self.errors if error.timestamp >= cutoff_time]
        
        # Clean up error counts for old errors
        for error in old_errors:
            error_key = f"{error.component.value}:{error.error_code or error.message}"
            if error_key in self.error_counts:
                del self.error_counts[error_key]
            if error_key in self.last_error_times:
                del self.last_error_times[error_key]
        
        return len(old_errors)


# Global error handler instance
error_handler = ErrorHandler()


def setup_logging(log_file: str = "ursine-capture.log", level: int = logging.INFO) -> None:
    """Set up logging configuration for the application."""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )


def handle_exception(component: ComponentType, func_name: str = None):
    """Decorator for automatic exception handling and logging."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_message = f"Exception in {func_name or func.__name__}: {str(e)}"
                error_details = traceback.format_exc()
                
                error_handler.handle_error(
                    component=component,
                    severity=ErrorSeverity.HIGH,
                    message=error_message,
                    details=error_details,
                    attempt_recovery=False
                )
                
                # Re-raise the exception
                raise
        return wrapper
    return decorator


def safe_execute(func: Callable, component: ComponentType, error_message: str = None, 
                default_return: Any = None, attempt_recovery: bool = True) -> Any:
    """Safely execute a function with error handling."""
    try:
        return func()
    except Exception as e:
        message = error_message or f"Error in {func.__name__ if hasattr(func, '__name__') else 'function'}: {str(e)}"
        details = traceback.format_exc()
        
        error_handler.handle_error(
            component=component,
            severity=ErrorSeverity.MEDIUM,
            message=message,
            details=details,
            attempt_recovery=attempt_recovery
        )
        
        return default_return


def format_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Calculate and format distance between two coordinates."""
    if None in (lat1, lon1, lat2, lon2):
        return "N/A"
    
    # Haversine formula
    R = 6371  # Earth's radius in kilometers
    
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    a = (math.sin(delta_lat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    
    if distance < 1:
        return f"{distance * 1000:.0f}m"
    else:
        return f"{distance:.1f}km"


def format_time_ago(timestamp: datetime) -> str:
    """Format time difference as human-readable string."""
    now = datetime.now()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=now.tzinfo)
    
    delta = now - timestamp
    
    if delta.total_seconds() < 60:
        return f"{int(delta.total_seconds())}s ago"
    elif delta.total_seconds() < 3600:
        return f"{int(delta.total_seconds() / 60)}m ago"
    elif delta.total_seconds() < 86400:
        return f"{int(delta.total_seconds() / 3600)}h ago"
    else:
        return f"{delta.days}d ago"


def validate_icao(icao: str) -> bool:
    """Validate ICAO aircraft identifier format."""
    if not icao or not isinstance(icao, str):
        return False
    
    # ICAO should be 6 hexadecimal characters
    pattern = re.compile(r'^[0-9A-Fa-f]{6}$')
    return bool(pattern.match(icao))


def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to integer with default fallback."""
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    """Safely convert value to float with default fallback."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def check_process_running(process_name: str) -> bool:
    """Check if a process with given name is currently running."""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if process_name.lower() in proc.info['name'].lower():
                return True
            if proc.info['cmdline'] and any(process_name.lower() in cmd.lower() 
                                          for cmd in proc.info['cmdline']):
                return True
        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def kill_process(process_name: str) -> bool:
    """Kill process by name. Returns True if successful."""
    try:
        killed = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            if (process_name.lower() in proc.info['name'].lower() or
                (proc.info['cmdline'] and any(process_name.lower() in cmd.lower() 
                                            for cmd in proc.info['cmdline']))):
                proc.terminate()
                killed = True
        return killed
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def run_command(command: list, timeout: int = 30) -> tuple[bool, str, str]:
    """Run shell command and return success status, stdout, stderr."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def validate_frequency(freq: int) -> bool:
    """Validate radio frequency is in valid ADS-B range."""
    # ADS-B frequency should be around 1090 MHz
    return 1080000000 <= freq <= 1100000000


def validate_gain(gain: int, min_val: int = 0, max_val: int = 60) -> bool:
    """Validate gain value is within acceptable range."""
    return min_val <= gain <= max_val


def validate_coordinates(lat: float, lon: float) -> bool:
    """Validate latitude and longitude coordinates."""
    return -90 <= lat <= 90 and -180 <= lon <= 180


def check_hackrf_connected() -> bool:
    """Check if HackRF device is connected and accessible."""
    try:
        success, stdout, stderr = run_command(["hackrf_info"], timeout=5)
        return success and "Found HackRF" in stdout
    except Exception:
        return False


def get_hackrf_info() -> dict:
    """Get detailed HackRF device information."""
    try:
        success, stdout, stderr = run_command(["hackrf_info"], timeout=10)
        if not success:
            return {"connected": False, "error": stderr}
        
        info = {"connected": True}
        
        # Parse hackrf_info output
        for line in stdout.split('\n'):
            line = line.strip()
            if "Serial number:" in line:
                info["serial"] = line.split(":")[-1].strip()
            elif "Board ID Number:" in line:
                info["board_id"] = line.split(":")[-1].strip()
            elif "Firmware Version:" in line:
                info["firmware"] = line.split(":")[-1].strip()
        
        return info
        
    except Exception as e:
        return {"connected": False, "error": str(e)}


def validate_hackrf_frequency(freq: int) -> bool:
    """Validate frequency is within HackRF's supported range."""
    # HackRF One supports 1 MHz to 6 GHz
    return 1000000 <= freq <= 6000000000


def validate_hackrf_gain(gain: int, gain_type: str = "lna") -> bool:
    """Validate gain values for HackRF."""
    if not isinstance(gain, int):
        return False
        
    if gain_type == "lna":
        # LNA gain: 0-40 dB (allow any value in range for flexibility)
        return 0 <= gain <= 40
    elif gain_type == "vga":
        # VGA gain: 0-62 dB (allow any value in range for flexibility)
        return 0 <= gain <= 62
    else:
        return False


def format_frequency(freq: int) -> str:
    """Format frequency for display."""
    if freq >= 1000000000:
        return f"{freq / 1000000000:.3f} GHz"
    elif freq >= 1000000:
        return f"{freq / 1000000:.1f} MHz"
    elif freq >= 1000:
        return f"{freq / 1000:.1f} kHz"
    else:
        return f"{freq} Hz"


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates in kilometers using Haversine formula."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert coordinates to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)
    
    # Haversine formula
    a = (math.sin(delta_lat / 2) ** 2 + 
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c
    
    return distance


def calculate_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate bearing from point 1 to point 2 in degrees."""
    if None in (lat1, lon1, lat2, lon2):
        return 0.0
    
    # Convert coordinates to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    
    # Calculate bearing
    y = math.sin(delta_lon) * math.cos(lat2_rad)
    x = (math.cos(lat1_rad) * math.sin(lat2_rad) - 
         math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(delta_lon))
    
    bearing_rad = math.atan2(y, x)
    bearing_deg = math.degrees(bearing_rad)
    
    # Normalize to 0-360 degrees
    bearing_deg = (bearing_deg + 360) % 360
    
    return bearing_deg