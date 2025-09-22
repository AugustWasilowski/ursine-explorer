#!/usr/bin/env python3
"""
Terminal-based UI for monitoring and control of Ursine Capture system.
"""

import curses
import json
import logging
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils import (setup_logging, format_time_ago, error_handler, ErrorSeverity, 
                  ComponentType, handle_exception, safe_execute)
from config import Config, RadioConfig


logger = logging.getLogger(__name__)


class WaterfallDisplay:
    """Enhanced waterfall spectrum display with FFT data processing and real-time scrolling."""
    
    def __init__(self, width: int, height: int):
        self.width = max(1, width)
        self.height = max(1, height)
        self.data = []
        self.update_counter = 0
        self.fft_history = []
        self.max_history = 100  # Keep more history for smoother scrolling
        
        # FFT processing parameters
        self.center_freq = 1090000000  # 1090 MHz
        self.sample_rate = 2000000     # 2 MHz sample rate
        self.fft_size = 1024
        
        # Display parameters
        self.min_db = -80  # Minimum dB level for display
        self.max_db = -20  # Maximum dB level for display
        
        # Scrolling parameters
        self.scroll_speed = 1  # Lines to scroll per update
        self.last_update_time = time.time()
        self.update_interval = 0.1  # Update every 100ms
        
    def update(self, fft_data: List[float] = None) -> None:
        """Update waterfall with new FFT data or fetch from available sources."""
        try:
            current_time = time.time()
            
            # Only update at specified interval for smooth scrolling
            if current_time - self.last_update_time < self.update_interval:
                return
                
            self.last_update_time = current_time
            
            # Try to get real FFT data from multiple sources
            processed_data = self._get_fft_data(fft_data)
            
            if processed_data is not None:
                # Add to history
                self.fft_history.append(processed_data)
                
                # Keep history within limits
                if len(self.fft_history) > self.max_history:
                    self.fft_history = self.fft_history[-self.max_history:]
                
                # Update display data with scrolling effect
                self._update_display_data()
            # If no real data, don't add anything - waterfall will show empty
            
            self.update_counter += 1
                
        except Exception as e:
            logger.error(f"Error updating waterfall: {e}")
    
    def _get_fft_data(self, provided_data: List[float] = None) -> Optional[List[int]]:
        """Get FFT data from various sources and process it for display."""
        try:
            # If data was provided directly, use it
            if provided_data and len(provided_data) > 0:
                return self._process_fft_data(provided_data)
            
            # Try to get data from dump1090 HTTP API
            fft_data = self._fetch_from_dump1090_api()
            if fft_data is not None:
                return self._process_fft_data(fft_data)
            
            # Try to get data from file
            fft_data = self._fetch_from_file()
            if fft_data is not None:
                return self._process_fft_data(fft_data)
            
            # No real data available - return None to show empty waterfall
            return None
            
        except Exception as e:
            logger.error(f"Error getting FFT data: {e}")
            return None
    
    def _fetch_from_dump1090_api(self) -> Optional[List[float]]:
        """Fetch FFT data from dump1090 HTTP API."""
        try:
            import requests
            url = "http://localhost:8080/data/fft.json"
            response = requests.get(url, timeout=0.5)
            
            if response.status_code == 200:
                data = response.json()
                if 'fft_data' in data and data['fft_data']:
                    return data['fft_data']
                    
        except Exception:
            pass  # Silently fail and try next source
        
        return None
    
    def _fetch_from_file(self) -> Optional[List[float]]:
        """Fetch FFT data from file (dump1090 --write-json output)."""
        try:
            import os
            import numpy as np
            
            fft_file = "/tmp/adsb_fft.dat"
            
            if not os.path.exists(fft_file):
                return None
            
            file_size = os.path.getsize(fft_file)
            if file_size < self.fft_size * 4:
                return None
            
            with open(fft_file, 'rb') as f:
                f.seek(-self.fft_size * 4, 2)  # Seek to last FFT frame
                data = np.frombuffer(f.read(self.fft_size * 4), dtype=np.float32)
                
                if len(data) == self.fft_size:
                    # Convert to dB and shift
                    data = np.maximum(data, 1e-12)  # Avoid log(0)
                    db_data = 10 * np.log10(data)
                    return np.fft.fftshift(db_data).tolist()
                    
        except Exception:
            pass  # Silently fail and try next source
        
        return None
    
    def _process_fft_data(self, fft_data: List[float]) -> List[int]:
        """Process raw FFT data into display values."""
        try:
            import numpy as np
            
            # Convert to numpy array if needed
            if not isinstance(fft_data, np.ndarray):
                fft_data = np.array(fft_data)
            
            # Resample to display width if needed
            if len(fft_data) != self.width:
                # Simple linear interpolation to match display width
                indices = np.linspace(0, len(fft_data) - 1, self.width)
                fft_data = np.interp(indices, np.arange(len(fft_data)), fft_data)
            
            # Normalize to display range (0-100)
            normalized = np.clip((fft_data - self.min_db) / (self.max_db - self.min_db) * 100, 0, 100)
            
            return normalized.astype(int).tolist()
            
        except Exception as e:
            logger.error(f"Error processing FFT data: {e}")
            return None
    
    def _generate_simulated_data(self) -> List[int]:
        """Generate realistic simulated ADS-B spectrum data."""
        try:
            import random
            import math
            
            line = []
            center_freq = self.width // 2  # 1090 MHz center
            
            for i in range(self.width):
                # Base noise floor
                base_noise = random.randint(8, 18)
                
                # Add ADS-B signal characteristics
                distance_from_center = abs(i - center_freq)
                
                # Strong signal at center frequency (1090 MHz)
                if distance_from_center < 3:
                    if self.update_counter % 15 == 0:  # Periodic ADS-B bursts
                        signal_strength = random.randint(70, 95)
                    else:
                        signal_strength = base_noise + random.randint(10, 25)
                
                # Weaker signals at adjacent frequencies
                elif distance_from_center < 8:
                    if random.random() < 0.1:  # 10% chance of adjacent channel activity
                        signal_strength = base_noise + random.randint(15, 35)
                    else:
                        signal_strength = base_noise
                
                # Occasional interference spikes
                elif random.random() < 0.02:  # 2% chance of interference
                    signal_strength = random.randint(40, 70)
                
                else:
                    # Normal noise floor with slight variations
                    signal_strength = base_noise + random.randint(-3, 3)
                
                # Add some frequency-dependent characteristics
                freq_factor = math.sin((i / self.width) * math.pi * 4) * 2
                signal_strength += int(freq_factor)
                
                line.append(max(0, min(100, signal_strength)))
            
            return line
            
        except Exception as e:
            logger.error(f"Error generating simulated data: {e}")
            return [10] * self.width  # Fallback to flat noise floor
    
    def _update_display_data(self) -> None:
        """Update display data with scrolling effect."""
        try:
            if not self.fft_history:
                return
            
            # Get the latest FFT data
            latest_data = self.fft_history[-1]
            
            # Add new line to display data
            self.data.append(latest_data)
            
            # Implement scrolling by removing old lines
            while len(self.data) > self.height:
                self.data.pop(0)  # Remove oldest line
                
        except Exception as e:
            logger.error(f"Error updating display data: {e}")
    
    def draw(self, screen, start_y: int, start_x: int) -> None:
        """Draw waterfall display with enhanced color coding and scrolling."""
        try:
            max_y, max_x = screen.getmaxyx()
            
            # Draw each line of the waterfall
            for y, line in enumerate(self.data):
                screen_y = start_y + y
                if screen_y >= max_y - 1:
                    break
                    
                # Draw frequency scale on first line
                if y == 0 and len(line) > 20:
                    self._draw_frequency_scale(screen, screen_y - 1, start_x, max_x)
                
                # Draw the spectrum line
                for x, value in enumerate(line):
                    screen_x = start_x + x
                    if screen_x >= max_x - 1:
                        break
                    
                    char, color = self._get_char_and_color(value)
                        
                    try:
                        screen.addch(screen_y, screen_x, char, color)
                    except curses.error:
                        pass  # Ignore drawing errors at screen edges
            
            # Draw center frequency marker if there's space
            if self.width > 10:
                center_x = start_x + self.width // 2
                if center_x < max_x - 1:
                    try:
                        # Draw vertical line to mark 1090 MHz
                        for y in range(len(self.data)):
                            screen_y = start_y + y
                            if screen_y < max_y - 1:
                                screen.addch(screen_y, center_x, '│', curses.color_pair(6) | curses.A_BOLD)
                    except curses.error:
                        pass
                        
        except Exception as e:
            logger.error(f"Error drawing waterfall: {e}")
    
    def _draw_frequency_scale(self, screen, y: int, start_x: int, max_x: int) -> None:
        """Draw frequency scale above the waterfall."""
        try:
            if y < 0:
                return
                
            # Calculate frequency range
            freq_start = self.center_freq - (self.sample_rate // 2)
            freq_end = self.center_freq + (self.sample_rate // 2)
            
            # Draw scale markers
            scale_positions = [0, self.width // 4, self.width // 2, 3 * self.width // 4, self.width - 1]
            
            for pos in scale_positions:
                if pos < self.width and start_x + pos < max_x - 8:
                    freq = freq_start + (pos / self.width) * self.sample_rate
                    freq_mhz = freq / 1000000
                    
                    # Format frequency label
                    if pos == self.width // 2:  # Center frequency
                        label = f"{freq_mhz:.1f}"
                        color = curses.color_pair(6) | curses.A_BOLD
                    else:
                        label = f"{freq_mhz:.0f}"
                        color = curses.color_pair(4)
                    
                    try:
                        screen.addstr(y, start_x + pos, label, color)
                    except curses.error:
                        pass
                        
        except Exception as e:
            logger.error(f"Error drawing frequency scale: {e}")
    
    def _get_char_and_color(self, value: int) -> tuple:
        """Get character and color for signal intensity with enhanced color coding."""
        try:
            # Enhanced color mapping with more granular levels
            if value > 90:
                return '█', curses.color_pair(1) | curses.A_BOLD  # Bright red - very strong
            elif value > 80:
                return '█', curses.color_pair(1)  # Red - strong signal
            elif value > 70:
                return '▓', curses.color_pair(5) | curses.A_BOLD  # Bright magenta - strong
            elif value > 60:
                return '▓', curses.color_pair(5)  # Magenta - medium-strong
            elif value > 50:
                return '▓', curses.color_pair(2) | curses.A_BOLD  # Bright yellow - medium
            elif value > 40:
                return '▒', curses.color_pair(2)  # Yellow - medium-weak
            elif value > 30:
                return '▒', curses.color_pair(3)  # Green - weak signal
            elif value > 20:
                return '░', curses.color_pair(6)  # Cyan - very weak
            elif value > 10:
                return '░', curses.color_pair(4)  # Blue - noise floor
            elif value > 5:
                return '·', curses.color_pair(4)  # Dim blue - low noise
            else:
                return ' ', 0  # Background - no signal
                
        except Exception:
            return ' ', 0
    
    def get_status_info(self) -> dict:
        """Get waterfall status information for display."""
        try:
            return {
                'fft_history_length': len(self.fft_history),
                'display_lines': len(self.data),
                'update_counter': self.update_counter,
                'center_freq_mhz': self.center_freq / 1000000,
                'sample_rate_mhz': self.sample_rate / 1000000,
                'width': self.width,
                'height': self.height
            }
        except Exception:
            return {}


class SystemStatusMonitor:
    """System status monitoring and display for receiver, dump1090, HackRF, and Meshtastic."""
    
    def __init__(self, status_file: str = "status.json"):
        self.status_file = Path(status_file)
        self.last_status = {}
        self.last_update = datetime.now()
        self.update_interval = 1.0  # Update every second
        
    def load_status(self) -> dict:
        """Load system status from status.json file with error handling."""
        try:
            if self.status_file.exists():
                with open(self.status_file, 'r') as f:
                    status = json.load(f)
                    self.last_status = status
                    self.last_update = datetime.now()
                    return status
            else:
                # Return default status if file doesn't exist
                error_handler.handle_error(
                    ComponentType.DASHBOARD,
                    ErrorSeverity.LOW,
                    f"Status file {self.status_file} does not exist",
                    error_code="STATUS_FILE_MISSING"
                )
                return self._get_default_status()
        except json.JSONDecodeError as e:
            error_handler.handle_error(
                ComponentType.DASHBOARD,
                ErrorSeverity.MEDIUM,
                f"Invalid JSON in status file: {str(e)}",
                error_code="STATUS_FILE_INVALID_JSON"
            )
            return self._get_default_status()
        except Exception as e:
            error_handler.handle_error(
                ComponentType.DASHBOARD,
                ErrorSeverity.MEDIUM,
                f"Error loading status file: {str(e)}",
                error_code="STATUS_FILE_LOAD_ERROR"
            )
            return self._get_default_status()
    
    def _get_default_status(self) -> dict:
        """Get default status when status file is unavailable."""
        return {
            "receiver_running": False,
            "dump1090_running": False,
            "hackrf_connected": False,
            "meshtastic_connected": False,
            "message_rate": 0.0,
            "aircraft_count": 0,
            "watchlist_count": 0,
            "total_messages": 0,
            "uptime": "0s",
            "errors": [],
            "last_update": datetime.now().isoformat()
        }
    
    def get_status_display_data(self) -> dict:
        """Get formatted status data for display."""
        status = self.load_status()
        
        # Calculate status indicators
        overall_health = self._calculate_overall_health(status)
        
        return {
            "overall_health": overall_health,
            "receiver_status": self._format_component_status("Receiver", status.get("receiver_running", False)),
            "dump1090_status": self._format_component_status("dump1090", status.get("dump1090_running", False)),
            "hackrf_status": self._format_component_status("HackRF", status.get("hackrf_connected", False)),
            "meshtastic_status": self._format_component_status("Meshtastic", status.get("meshtastic_connected", False)),
            "message_rate": status.get("message_rate", 0.0),
            "aircraft_count": status.get("aircraft_count", 0),
            "watchlist_count": status.get("watchlist_count", 0),
            "total_messages": status.get("total_messages", 0),
            "uptime": status.get("uptime", "0s"),
            "errors": status.get("errors", []),
            "last_update": status.get("last_update", "Never")
        }
    
    def _calculate_overall_health(self, status: dict) -> str:
        """Calculate overall system health status."""
        critical_components = [
            status.get("receiver_running", False),
            status.get("dump1090_running", False),
            status.get("hackrf_connected", False)
        ]
        
        errors = status.get("errors", [])
        
        if all(critical_components) and len(errors) == 0:
            return "HEALTHY"
        elif any(critical_components) and len(errors) < 3:
            return "DEGRADED"
        else:
            return "ERROR"
    
    def _format_component_status(self, component: str, is_running: bool) -> dict:
        """Format individual component status for display."""
        return {
            "name": component,
            "status": "RUNNING" if is_running else "STOPPED",
            "color": "green" if is_running else "red",
            "symbol": "●" if is_running else "○"
        }
    
    def draw_status_section(self, screen, start_y: int, start_x: int, width: int, height: int) -> None:
        """Draw comprehensive system status section."""
        try:
            status_data = self.get_status_display_data()
            
            # Draw status section border and title
            self._draw_status_border(screen, start_y, start_x, width, height)
            
            # Draw overall health indicator
            self._draw_overall_health(screen, start_y + 1, start_x + 2, status_data["overall_health"])
            
            # Draw component status
            self._draw_component_status(screen, start_y + 3, start_x + 2, width - 4, status_data)
            
            # Draw performance metrics
            self._draw_performance_metrics(screen, start_y + 8, start_x + 2, width - 4, status_data)
            
            # Draw error conditions if any
            if status_data["errors"]:
                self._draw_error_conditions(screen, start_y + 12, start_x + 2, width - 4, status_data["errors"])
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.DASHBOARD,
                ErrorSeverity.MEDIUM,
                f"Error drawing status section: {str(e)}",
                error_code="STATUS_DRAW_ERROR"
            )
            # Draw error message with graceful degradation
            try:
                error_msg = f"Status Error: {str(e)[:width-6]}"
                screen.addstr(start_y + 2, start_x + 2, error_msg, curses.color_pair(1))
                
                # Show basic fallback status
                fallback_status = "System status unavailable - check logs"
                screen.addstr(start_y + 4, start_x + 2, fallback_status[:width-4], curses.color_pair(4))
                
            except curses.error:
                pass
    
    def _draw_status_border(self, screen, start_y: int, start_x: int, width: int, height: int) -> None:
        """Draw border and title for status section."""
        try:
            # Draw horizontal borders
            for x in range(width):
                screen.addch(start_y, start_x + x, '─', curses.color_pair(4))
                if start_y + height - 1 < curses.LINES:
                    screen.addch(start_y + height - 1, start_x + x, '─', curses.color_pair(4))
            
            # Draw vertical borders
            for y in range(height):
                if start_y + y < curses.LINES:
                    screen.addch(start_y + y, start_x, '│', curses.color_pair(4))
                    if start_x + width - 1 < curses.COLS:
                        screen.addch(start_y + y, start_x + width - 1, '│', curses.color_pair(4))
            
            # Draw corners
            screen.addch(start_y, start_x, '┌', curses.color_pair(4))
            screen.addch(start_y, start_x + width - 1, '┐', curses.color_pair(4))
            if start_y + height - 1 < curses.LINES:
                screen.addch(start_y + height - 1, start_x, '└', curses.color_pair(4))
                screen.addch(start_y + height - 1, start_x + width - 1, '┘', curses.color_pair(4))
            
            # Draw title
            title = " SYSTEM STATUS "
            title_x = start_x + (width - len(title)) // 2
            screen.addstr(start_y, title_x, title, curses.color_pair(4) | curses.A_BOLD)
            
        except curses.error:
            pass
    
    def _draw_overall_health(self, screen, y: int, x: int, health: str) -> None:
        """Draw overall system health indicator."""
        try:
            health_colors = {
                "HEALTHY": curses.color_pair(2) | curses.A_BOLD,  # Green
                "DEGRADED": curses.color_pair(3) | curses.A_BOLD,  # Yellow
                "ERROR": curses.color_pair(1) | curses.A_BOLD     # Red
            }
            
            health_symbols = {
                "HEALTHY": "✓",
                "DEGRADED": "⚠",
                "ERROR": "✗"
            }
            
            color = health_colors.get(health, curses.color_pair(4))
            symbol = health_symbols.get(health, "?")
            
            status_line = f"Overall: {symbol} {health}"
            screen.addstr(y, x, status_line, color)
            
        except curses.error:
            pass
    
    def _draw_component_status(self, screen, start_y: int, start_x: int, width: int, status_data: dict) -> None:
        """Draw individual component status indicators."""
        try:
            components = [
                status_data["receiver_status"],
                status_data["dump1090_status"],
                status_data["hackrf_status"],
                status_data["meshtastic_status"]
            ]
            
            for i, component in enumerate(components):
                y = start_y + i
                if y >= curses.LINES - 1:
                    break
                
                # Choose color based on status
                if component["color"] == "green":
                    color = curses.color_pair(2)  # Green
                elif component["color"] == "red":
                    color = curses.color_pair(1)  # Red
                else:
                    color = curses.color_pair(4)  # Blue
                
                status_line = f"{component['symbol']} {component['name']:<12} {component['status']}"
                screen.addstr(y, start_x, status_line[:width], color)
                
        except curses.error:
            pass
    
    def _draw_performance_metrics(self, screen, start_y: int, start_x: int, width: int, status_data: dict) -> None:
        """Draw performance metrics and statistics."""
        try:
            metrics = [
                f"Messages/sec: {status_data['message_rate']:.1f}",
                f"Aircraft: {status_data['aircraft_count']}",
                f"Watchlist: {status_data['watchlist_count']}",
                f"Total Messages: {status_data['total_messages']:,}",
                f"Uptime: {status_data['uptime']}"
            ]
            
            for i, metric in enumerate(metrics):
                y = start_y + i
                if y >= curses.LINES - 1:
                    break
                
                # Color code based on values
                color = curses.color_pair(4)  # Default blue
                
                if "Messages/sec" in metric:
                    rate = status_data['message_rate']
                    if rate > 30:
                        color = curses.color_pair(2)  # Green - good rate
                    elif rate > 10:
                        color = curses.color_pair(3)  # Yellow - moderate rate
                    elif rate > 0:
                        color = curses.color_pair(1)  # Red - low rate
                
                screen.addstr(y, start_x, metric[:width], color)
                
        except curses.error:
            pass
    
    def _draw_error_conditions(self, screen, start_y: int, start_x: int, width: int, errors: list) -> None:
        """Draw error conditions and alerts."""
        try:
            if not errors:
                return
            
            # Draw error header
            screen.addstr(start_y, start_x, "ERRORS:", curses.color_pair(1) | curses.A_BOLD)
            
            # Draw up to 3 most recent errors
            for i, error in enumerate(errors[-3:]):
                y = start_y + 1 + i
                if y >= curses.LINES - 1:
                    break
                
                error_text = f"• {error}"
                screen.addstr(y, start_x, error_text[:width], curses.color_pair(1))
                
        except curses.error:
            pass
    
    def get_status_summary(self) -> str:
        """Get brief status summary for main display."""
        try:
            status_data = self.get_status_display_data()
            health = status_data["overall_health"]
            rate = status_data["message_rate"]
            aircraft = status_data["aircraft_count"]
            
            return f"Status: {health} | {rate:.0f} msg/s | {aircraft} aircraft"
            
        except Exception as e:
            logger.error(f"Error getting status summary: {e}")
            return "Status: ERROR"


class ErrorNotificationSystem:
    """Error notification and alert system for dashboard."""
    
    def __init__(self):
        self.active_notifications = []
        self.max_notifications = 5
        self.notification_timeout = 30  # seconds
        
    def add_notification(self, severity: ErrorSeverity, message: str, component: str = None) -> None:
        """Add a new error notification."""
        try:
            notification = {
                'severity': severity,
                'message': message,
                'component': component,
                'timestamp': datetime.now(),
                'acknowledged': False
            }
            
            self.active_notifications.append(notification)
            
            # Limit number of notifications
            if len(self.active_notifications) > self.max_notifications:
                self.active_notifications = self.active_notifications[-self.max_notifications:]
                
        except Exception as e:
            logger.error(f"Error adding notification: {e}")
    
    def update_from_error_handler(self) -> None:
        """Update notifications from global error handler."""
        try:
            # Get recent critical and high severity errors
            recent_errors = error_handler.get_recent_errors(hours=1)
            critical_errors = [e for e in recent_errors if e.severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]]
            
            # Add new notifications for errors not already shown
            for error in critical_errors[-3:]:  # Show last 3 critical errors
                # Check if we already have this error
                existing = any(n['message'] == error.message and 
                             n['component'] == error.component.value 
                             for n in self.active_notifications)
                
                if not existing:
                    self.add_notification(
                        error.severity,
                        error.message,
                        error.component.value
                    )
                    
        except Exception as e:
            logger.error(f"Error updating notifications from error handler: {e}")
    
    def draw_notifications(self, screen, start_y: int, start_x: int, width: int) -> int:
        """Draw error notifications and return height used."""
        try:
            if not self.active_notifications:
                return 0
            
            # Clean up old notifications
            current_time = datetime.now()
            self.active_notifications = [
                n for n in self.active_notifications 
                if (current_time - n['timestamp']).total_seconds() < self.notification_timeout
            ]
            
            if not self.active_notifications:
                return 0
            
            height_used = 0
            
            # Draw notification header
            header = " ERROR NOTIFICATIONS "
            screen.addstr(start_y, start_x + (width - len(header)) // 2, 
                         header, curses.color_pair(1) | curses.A_BOLD)
            height_used += 1
            
            # Draw notifications
            for i, notification in enumerate(self.active_notifications[-3:]):  # Show last 3
                y = start_y + height_used + 1
                if y >= curses.LINES - 1:
                    break
                
                # Choose color based on severity
                if notification['severity'] == ErrorSeverity.CRITICAL:
                    color = curses.color_pair(1) | curses.A_BOLD  # Bright red
                elif notification['severity'] == ErrorSeverity.HIGH:
                    color = curses.color_pair(1)  # Red
                else:
                    color = curses.color_pair(3)  # Yellow
                
                # Format notification
                component = notification['component'] or 'SYSTEM'
                age = (current_time - notification['timestamp']).total_seconds()
                age_str = f"{int(age)}s" if age < 60 else f"{int(age/60)}m"
                
                notification_text = f"[{component}] {notification['message'][:width-20]} ({age_str})"
                
                try:
                    screen.addstr(y, start_x, notification_text[:width], color)
                except curses.error:
                    pass
                
                height_used += 1
            
            return height_used + 1
            
        except Exception as e:
            logger.error(f"Error drawing notifications: {e}")
            return 0
    
    def acknowledge_all(self) -> None:
        """Acknowledge all notifications."""
        for notification in self.active_notifications:
            notification['acknowledged'] = True
    
    def clear_old_notifications(self) -> None:
        """Clear old notifications."""
        current_time = datetime.now()
        self.active_notifications = [
            n for n in self.active_notifications 
            if (current_time - n['timestamp']).total_seconds() < self.notification_timeout
        ]


class MenuSystem:
    """Interactive menu system for settings and controls."""
    
    def __init__(self, config: Config):
        self.config = config
        self.active = False
        self.current_menu = None
        
    def show_main_menu(self, screen) -> Optional[str]:
        """Show main menu and return selected action."""
        try:
            menu_items = [
                "R - Radio Settings",
                "W - Watchlist Management", 
                "S - System Status",
                "Q - Quit",
                "ESC - Cancel"
            ]
            
            # Clear area for menu
            menu_height = len(menu_items) + 4
            menu_width = 30
            start_y = curses.LINES // 2 - menu_height // 2
            start_x = curses.COLS // 2 - menu_width // 2
            
            # Draw menu box
            for y in range(menu_height):
                for x in range(menu_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw menu title
            title = "MAIN MENU"
            screen.addstr(start_y + 1, start_x + (menu_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            # Draw menu items
            for i, item in enumerate(menu_items):
                screen.addstr(start_y + 3 + i, start_x + 2, item, curses.A_REVERSE)
            
            screen.refresh()
            
            # Get user input
            key = screen.getch()
            
            if key == ord('r') or key == ord('R'):
                return "radio"
            elif key == ord('w') or key == ord('W'):
                return "watchlist"
            elif key == ord('s') or key == ord('S'):
                return "status"
            elif key == ord('q') or key == ord('Q'):
                return "quit"
            elif key == 27:  # ESC
                return "cancel"
                
            return None
            
        except Exception as e:
            logger.error(f"Error showing main menu: {e}")
            return None
    
    def show_radio_menu(self, screen) -> None:
        """Show radio settings menu with gain and frequency controls."""
        try:
            # Get current radio configuration
            radio_config = self.config.get_radio_config()
            
            while True:
                # Clear screen area for menu
                menu_height = 12
                menu_width = 50
                start_y = curses.LINES // 2 - menu_height // 2
                start_x = curses.COLS // 2 - menu_width // 2
                
                # Draw menu box
                for y in range(menu_height):
                    for x in range(menu_width):
                        try:
                            screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                        except curses.error:
                            pass
                
                # Draw menu title
                title = "RADIO SETTINGS"
                screen.addstr(start_y + 1, start_x + (menu_width - len(title)) // 2, 
                             title, curses.A_REVERSE | curses.A_BOLD)
                
                # Draw current settings
                freq_mhz = radio_config.frequency / 1000000
                settings_lines = [
                    f"1. Frequency: {freq_mhz:.1f} MHz",
                    f"2. LNA Gain: {radio_config.lna_gain} dB",
                    f"3. VGA Gain: {radio_config.vga_gain} dB",
                    f"4. Amp Enable: {'ON' if radio_config.enable_amp else 'OFF'}",
                    "",
                    "5. Reset to Defaults",
                    "",
                    "ESC - Back to Main Menu"
                ]
                
                for i, line in enumerate(settings_lines):
                    screen.addstr(start_y + 3 + i, start_x + 2, line, curses.A_REVERSE)
                
                screen.refresh()
                
                # Get user input
                key = screen.getch()
                
                if key == 27:  # ESC
                    break
                elif key == ord('1'):
                    new_freq = self._edit_frequency(screen, radio_config.frequency)
                    if new_freq is not None:
                        radio_config.frequency = new_freq
                        self._save_radio_config(radio_config)
                elif key == ord('2'):
                    new_gain = self._edit_gain(screen, "LNA Gain", radio_config.lna_gain, 0, 40)
                    if new_gain is not None:
                        radio_config.lna_gain = new_gain
                        self._save_radio_config(radio_config)
                elif key == ord('3'):
                    new_gain = self._edit_gain(screen, "VGA Gain", radio_config.vga_gain, 0, 62)
                    if new_gain is not None:
                        radio_config.vga_gain = new_gain
                        self._save_radio_config(radio_config)
                elif key == ord('4'):
                    radio_config.enable_amp = not radio_config.enable_amp
                    self._save_radio_config(radio_config)
                elif key == ord('5'):
                    # Reset to defaults
                    radio_config = RadioConfig()
                    self._save_radio_config(radio_config)
                    
        except Exception as e:
            logger.error(f"Error showing radio menu: {e}")
    
    def show_watchlist_menu(self, screen) -> None:
        """Enhanced watchlist management menu with comprehensive editing capabilities."""
        try:
            selected_row = 0
            scroll_offset = 0
            
            while True:
                # Get current watchlist
                watchlist = self.config.get_watchlist()
                
                # Clear screen area for menu
                menu_height = min(22, curses.LINES - 4)
                menu_width = min(70, curses.COLS - 4)
                start_y = curses.LINES // 2 - menu_height // 2
                start_x = curses.COLS // 2 - menu_width // 2
                
                # Draw menu box
                for y in range(menu_height):
                    for x in range(menu_width):
                        try:
                            screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                        except curses.error:
                            pass
                
                # Draw menu title with enhanced info
                title = f"WATCHLIST MANAGEMENT ({len(watchlist)} aircraft)"
                screen.addstr(start_y + 1, start_x + (menu_width - len(title)) // 2, 
                             title, curses.A_REVERSE | curses.A_BOLD)
                
                # Draw enhanced instructions
                instructions = [
                    "A - Add Aircraft    D - Delete    E - Edit Name    C - Clear All",
                    "I - Import from Current    ↑↓ - Navigate    ESC - Back"
                ]
                for i, instruction in enumerate(instructions):
                    screen.addstr(start_y + 2 + i, start_x + 2, instruction[:menu_width-4], curses.A_REVERSE)
                
                # Calculate display area
                list_start_y = start_y + 5
                max_entries = menu_height - 8
                
                if not watchlist:
                    screen.addstr(list_start_y, start_x + 2, "No aircraft in watchlist", 
                                curses.A_REVERSE | curses.color_pair(4))
                    screen.addstr(list_start_y + 2, start_x + 2, "Press 'A' to add aircraft manually", 
                                curses.A_REVERSE | curses.color_pair(4))
                    screen.addstr(list_start_y + 3, start_x + 2, "Press 'I' to import from currently tracked aircraft", 
                                curses.A_REVERSE | curses.color_pair(4))
                else:
                    # Adjust scroll and selection
                    if selected_row >= len(watchlist):
                        selected_row = max(0, len(watchlist) - 1)
                    
                    if selected_row < scroll_offset:
                        scroll_offset = selected_row
                    elif selected_row >= scroll_offset + max_entries:
                        scroll_offset = selected_row - max_entries + 1
                    
                    # Draw enhanced header
                    header = "ICAO     Name                           Status"
                    screen.addstr(list_start_y, start_x + 2, header[:menu_width-4], 
                                curses.A_REVERSE | curses.A_BOLD | curses.A_UNDERLINE)
                    
                    # Draw entries with enhanced information
                    for i in range(max_entries):
                        entry_index = scroll_offset + i
                        if entry_index >= len(watchlist):
                            break
                            
                        entry = watchlist[entry_index]
                        y = list_start_y + 1 + i
                        
                        icao = entry.icao[:8].ljust(8)
                        name = (entry.name[:25] if entry.name else "(No name)").ljust(25)
                        
                        # Check if aircraft is currently being tracked
                        status = "Not seen"
                        try:
                            # This would need to be connected to live aircraft data
                            # For now, show placeholder status
                            status = "Unknown"
                        except:
                            status = "Unknown"
                        
                        line = f"{icao} {name} {status}"
                        
                        # Highlight selected row
                        color = curses.A_REVERSE
                        if entry_index == selected_row:
                            color |= curses.color_pair(7)  # Selection highlight
                        
                        screen.addstr(y, start_x + 2, line[:menu_width-4], color)
                    
                    # Draw scroll indicator if needed
                    if len(watchlist) > max_entries:
                        scroll_info = f"[{scroll_offset + 1}-{min(scroll_offset + max_entries, len(watchlist))}/{len(watchlist)}]"
                        screen.addstr(start_y + menu_height - 2, start_x + menu_width - len(scroll_info) - 2, 
                                    scroll_info, curses.A_REVERSE | curses.color_pair(4))
                
                screen.refresh()
                
                # Get user input
                key = screen.getch()
                
                if key == 27:  # ESC
                    break
                elif key == ord('a') or key == ord('A'):
                    # Add aircraft manually
                    icao = self._input_icao(screen)
                    if icao:
                        name = self._input_name(screen, icao)
                        if self.config.add_to_watchlist(icao, name):
                            self._show_message(screen, f"Added {icao} to watchlist")
                        else:
                            self._show_message(screen, f"Aircraft {icao} already in watchlist")
                elif key == ord('d') or key == ord('D'):
                    # Delete selected aircraft
                    if watchlist and 0 <= selected_row < len(watchlist):
                        entry = watchlist[selected_row]
                        if self._confirm_delete(screen, entry.icao):
                            if self.config.remove_from_watchlist(entry.icao):
                                self._show_message(screen, f"Removed {entry.icao} from watchlist")
                                if selected_row >= len(watchlist) - 1:
                                    selected_row = max(0, len(watchlist) - 2)
                            else:
                                self._show_message(screen, f"Failed to remove {entry.icao}")
                elif key == ord('e') or key == ord('E'):
                    # Edit name of selected aircraft
                    if watchlist and 0 <= selected_row < len(watchlist):
                        entry = watchlist[selected_row]
                        new_name = self._edit_aircraft_name(screen, entry.icao, entry.name)
                        if new_name is not None:
                            # Remove and re-add with new name
                            if self.config.remove_from_watchlist(entry.icao):
                                if self.config.add_to_watchlist(entry.icao, new_name):
                                    self._show_message(screen, f"Updated name for {entry.icao}")
                                else:
                                    # Re-add with old name if new add failed
                                    self.config.add_to_watchlist(entry.icao, entry.name)
                                    self._show_message(screen, f"Failed to update name for {entry.icao}")
                elif key == ord('c') or key == ord('C'):
                    # Clear all watchlist entries
                    if watchlist and self._confirm_clear_all(screen):
                        cleared_count = 0
                        for entry in watchlist[:]:  # Copy list to avoid modification during iteration
                            if self.config.remove_from_watchlist(entry.icao):
                                cleared_count += 1
                        self._show_message(screen, f"Cleared {cleared_count} aircraft from watchlist")
                        selected_row = 0
                        scroll_offset = 0
                elif key == ord('i') or key == ord('I'):
                    # Import from currently tracked aircraft
                    self._import_from_tracked_aircraft(screen)
                elif key == curses.KEY_UP or key == ord('k'):
                    if watchlist:
                        selected_row = max(0, selected_row - 1)
                elif key == curses.KEY_DOWN or key == ord('j'):
                    if watchlist:
                        selected_row = min(len(watchlist) - 1, selected_row + 1)
                elif key == curses.KEY_HOME:
                    selected_row = 0
                    scroll_offset = 0
                elif key == curses.KEY_END:
                    if watchlist:
                        selected_row = len(watchlist) - 1
                elif key == curses.KEY_PPAGE:  # Page Up
                    selected_row = max(0, selected_row - max_entries)
                elif key == curses.KEY_NPAGE:  # Page Down
                    if watchlist:
                        selected_row = min(len(watchlist) - 1, selected_row + max_entries)
                        
        except Exception as e:
            logger.error(f"Error showing watchlist menu: {e}")
    
    def _edit_frequency(self, screen, current_freq: int) -> Optional[int]:
        """Edit frequency setting with input validation."""
        try:
            # Show input dialog
            dialog_height = 8
            dialog_width = 40
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = "EDIT FREQUENCY"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            current_mhz = current_freq / 1000000
            screen.addstr(start_y + 3, start_x + 2, f"Current: {current_mhz:.1f} MHz", curses.A_REVERSE)
            screen.addstr(start_y + 4, start_x + 2, "New (MHz):", curses.A_REVERSE)
            screen.addstr(start_y + 6, start_x + 2, "Enter - Save  ESC - Cancel", curses.A_REVERSE)
            
            # Input field
            input_x = start_x + 12
            input_y = start_y + 4
            input_str = f"{current_mhz:.1f}"
            
            # Enable cursor and echo
            curses.curs_set(1)
            curses.echo()
            
            try:
                screen.addstr(input_y, input_x, input_str, curses.A_REVERSE)
                screen.move(input_y, input_x + len(input_str))
                screen.refresh()
                
                # Get input
                new_input = screen.getstr(input_y, input_x, 10).decode('utf-8')
                
                if new_input.strip():
                    new_freq_mhz = float(new_input.strip())
                    new_freq_hz = int(new_freq_mhz * 1000000)
                    
                    # Validate frequency range (HackRF supports 1 MHz to 6 GHz, but practical range is 24 MHz to 1750 MHz)
                    if 24 <= new_freq_mhz <= 1750:
                        return new_freq_hz
                    else:
                        self._show_message(screen, "Frequency must be between 24-1750 MHz")
                        
            except ValueError:
                self._show_message(screen, "Invalid frequency format")
            except Exception as e:
                logger.error(f"Error in frequency input: {e}")
            finally:
                curses.noecho()
                curses.curs_set(0)
                
            return None
            
        except Exception as e:
            logger.error(f"Error editing frequency: {e}")
            return None
    
    def _edit_gain(self, screen, gain_type: str, current_gain: int, min_gain: int, max_gain: int) -> Optional[int]:
        """Edit gain setting with input validation."""
        try:
            # Show input dialog
            dialog_height = 8
            dialog_width = 40
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = f"EDIT {gain_type.upper()}"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            screen.addstr(start_y + 3, start_x + 2, f"Current: {current_gain} dB", curses.A_REVERSE)
            screen.addstr(start_y + 4, start_x + 2, f"New ({min_gain}-{max_gain}):", curses.A_REVERSE)
            screen.addstr(start_y + 6, start_x + 2, "Enter - Save  ESC - Cancel", curses.A_REVERSE)
            
            # Input field
            input_x = start_x + 15
            input_y = start_y + 4
            input_str = str(current_gain)
            
            # Enable cursor and echo
            curses.curs_set(1)
            curses.echo()
            
            try:
                screen.addstr(input_y, input_x, input_str, curses.A_REVERSE)
                screen.move(input_y, input_x + len(input_str))
                screen.refresh()
                
                # Get input
                new_input = screen.getstr(input_y, input_x, 5).decode('utf-8')
                
                if new_input.strip():
                    new_gain = int(new_input.strip())
                    
                    # Validate gain range
                    if min_gain <= new_gain <= max_gain:
                        return new_gain
                    else:
                        self._show_message(screen, f"Gain must be between {min_gain}-{max_gain} dB")
                        
            except ValueError:
                self._show_message(screen, "Invalid gain format")
            except Exception as e:
                logger.error(f"Error in gain input: {e}")
            finally:
                curses.noecho()
                curses.curs_set(0)
                
            return None
            
        except Exception as e:
            logger.error(f"Error editing gain: {e}")
            return None
    
    def _save_radio_config(self, radio_config: RadioConfig) -> None:
        """Save radio configuration to file."""
        try:
            from dataclasses import asdict
            radio_dict = asdict(radio_config)
            if self.config.update_section('radio', radio_dict):
                logger.info("Radio configuration saved")
            else:
                logger.error("Failed to save radio configuration")
        except Exception as e:
            logger.error(f"Error saving radio config: {e}")
    
    def _input_icao(self, screen) -> Optional[str]:
        """Input ICAO code with validation."""
        try:
            # Show input dialog
            dialog_height = 8
            dialog_width = 30
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = "ADD AIRCRAFT"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            screen.addstr(start_y + 3, start_x + 2, "ICAO Code:", curses.A_REVERSE)
            screen.addstr(start_y + 5, start_x + 2, "Enter - OK  ESC - Cancel", curses.A_REVERSE)
            
            # Input field
            input_x = start_x + 2
            input_y = start_y + 4
            
            # Enable cursor and echo
            curses.curs_set(1)
            curses.echo()
            
            try:
                screen.refresh()
                
                # Get input
                icao_input = screen.getstr(input_y, input_x, 8).decode('utf-8').strip().upper()
                
                if icao_input and len(icao_input) >= 4:
                    from utils import validate_icao
                    if validate_icao(icao_input):
                        return icao_input
                    else:
                        self._show_message(screen, "Invalid ICAO format")
                        
            except Exception as e:
                logger.error(f"Error in ICAO input: {e}")
            finally:
                curses.noecho()
                curses.curs_set(0)
                
            return None
            
        except Exception as e:
            logger.error(f"Error inputting ICAO: {e}")
            return None
    
    def _input_name(self, screen, icao: str) -> str:
        """Input aircraft name (optional)."""
        try:
            # Show input dialog
            dialog_height = 8
            dialog_width = 40
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = f"NAME FOR {icao}"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            screen.addstr(start_y + 3, start_x + 2, "Name (optional):", curses.A_REVERSE)
            screen.addstr(start_y + 5, start_x + 2, "Enter - OK  ESC - Skip", curses.A_REVERSE)
            
            # Input field
            input_x = start_x + 2
            input_y = start_y + 4
            
            # Enable cursor and echo
            curses.curs_set(1)
            curses.echo()
            
            try:
                screen.refresh()
                
                # Get input
                name_input = screen.getstr(input_y, input_x, 30).decode('utf-8').strip()
                return name_input
                
            except Exception as e:
                logger.error(f"Error in name input: {e}")
                return ""
            finally:
                curses.noecho()
                curses.curs_set(0)
                
        except Exception as e:
            logger.error(f"Error inputting name: {e}")
            return ""
    
    def _confirm_delete(self, screen, icao: str) -> bool:
        """Confirm deletion of watchlist entry."""
        try:
            # Show confirmation dialog
            dialog_height = 6
            dialog_width = 40
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = "CONFIRM DELETE"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            message = f"Delete {icao}?"
            screen.addstr(start_y + 3, start_x + (dialog_width - len(message)) // 2, 
                         message, curses.A_REVERSE)
            
            options = "Y - Yes  N - No"
            screen.addstr(start_y + 4, start_x + (dialog_width - len(options)) // 2, 
                         options, curses.A_REVERSE)
            
            screen.refresh()
            
            # Get confirmation
            while True:
                key = screen.getch()
                if key == ord('y') or key == ord('Y'):
                    return True
                elif key == ord('n') or key == ord('N') or key == 27:  # ESC
                    return False
                    
        except Exception as e:
            logger.error(f"Error confirming delete: {e}")
            return False
    
    def _show_message(self, screen, message: str) -> None:
        """Show a temporary message dialog."""
        try:
            # Show message dialog
            dialog_height = 5
            dialog_width = min(len(message) + 6, curses.COLS - 4)
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw message
            screen.addstr(start_y + 2, start_x + (dialog_width - len(message)) // 2, 
                         message, curses.A_REVERSE | curses.A_BOLD)
            
            screen.addstr(start_y + 3, start_x + (dialog_width - 16) // 2, 
                         "Press any key...", curses.A_REVERSE)
            
            screen.refresh()
            screen.getch()  # Wait for key press
            
        except Exception as e:
            logger.error(f"Error showing message: {e}")
    
    def _edit_aircraft_name(self, screen, icao: str, current_name: str) -> Optional[str]:
        """Edit aircraft name with current value pre-filled."""
        try:
            # Show input dialog
            dialog_height = 8
            dialog_width = 50
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = f"EDIT NAME FOR {icao}"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            screen.addstr(start_y + 3, start_x + 2, f"Current: {current_name}", curses.A_REVERSE)
            screen.addstr(start_y + 4, start_x + 2, "New name:", curses.A_REVERSE)
            screen.addstr(start_y + 6, start_x + 2, "Enter - Save  ESC - Cancel", curses.A_REVERSE)
            
            # Input field
            input_x = start_x + 12
            input_y = start_y + 4
            
            # Enable cursor and echo
            curses.curs_set(1)
            curses.echo()
            
            try:
                # Pre-fill with current name
                screen.addstr(input_y, input_x, current_name[:30], curses.A_REVERSE)
                screen.move(input_y, input_x + len(current_name[:30]))
                screen.refresh()
                
                # Get input
                new_name = screen.getstr(input_y, input_x, 30).decode('utf-8').strip()
                return new_name if new_name else current_name
                
            except Exception as e:
                logger.error(f"Error in name edit input: {e}")
                return None
            finally:
                curses.noecho()
                curses.curs_set(0)
                
        except Exception as e:
            logger.error(f"Error editing aircraft name: {e}")
            return None
    
    def _confirm_clear_all(self, screen) -> bool:
        """Confirm clearing all watchlist entries."""
        try:
            # Show confirmation dialog
            dialog_height = 7
            dialog_width = 50
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = "CONFIRM CLEAR ALL"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            message1 = "This will remove ALL aircraft"
            message2 = "from the watchlist!"
            screen.addstr(start_y + 3, start_x + (dialog_width - len(message1)) // 2, 
                         message1, curses.A_REVERSE | curses.color_pair(1))
            screen.addstr(start_y + 4, start_x + (dialog_width - len(message2)) // 2, 
                         message2, curses.A_REVERSE | curses.color_pair(1))
            
            options = "Y - Yes, clear all    N - Cancel"
            screen.addstr(start_y + 5, start_x + (dialog_width - len(options)) // 2, 
                         options, curses.A_REVERSE)
            
            screen.refresh()
            
            # Get confirmation
            while True:
                key = screen.getch()
                if key == ord('y') or key == ord('Y'):
                    return True
                elif key == ord('n') or key == ord('N') or key == 27:  # ESC
                    return False
                    
        except Exception as e:
            logger.error(f"Error confirming clear all: {e}")
            return False
    
    def _import_from_tracked_aircraft(self, screen) -> None:
        """Import aircraft from currently tracked aircraft list."""
        try:
            # This would need access to current aircraft data
            # For now, show a placeholder dialog
            dialog_height = 10
            dialog_width = 60
            start_y = curses.LINES // 2 - dialog_height // 2
            start_x = curses.COLS // 2 - dialog_width // 2
            
            # Draw dialog box
            for y in range(dialog_height):
                for x in range(dialog_width):
                    try:
                        screen.addch(start_y + y, start_x + x, ' ', curses.A_REVERSE)
                    except curses.error:
                        pass
            
            # Draw dialog content
            title = "IMPORT FROM TRACKED AIRCRAFT"
            screen.addstr(start_y + 1, start_x + (dialog_width - len(title)) // 2, 
                         title, curses.A_REVERSE | curses.A_BOLD)
            
            # This is a placeholder - in a full implementation, this would:
            # 1. Load current aircraft.json
            # 2. Show list of currently tracked aircraft
            # 3. Allow selection of multiple aircraft to add to watchlist
            # 4. Add selected aircraft with their callsigns as names
            
            message_lines = [
                "This feature would show currently tracked",
                "aircraft and allow you to select which",
                "ones to add to the watchlist.",
                "",
                "Implementation requires connection to",
                "live aircraft data from receiver process.",
                "",
                "Press any key to continue..."
            ]
            
            for i, line in enumerate(message_lines):
                y = start_y + 2 + i
                if y < start_y + dialog_height - 1:
                    screen.addstr(y, start_x + 2, line, curses.A_REVERSE)
            
            screen.refresh()
            screen.getch()  # Wait for key press
            
        except Exception as e:
            logger.error(f"Error importing from tracked aircraft: {e}")


class Dashboard:
    """Main dashboard class integrating all UI components."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.waterfall = None
        self.menu_system = MenuSystem(self.config)
        self.status_monitor = SystemStatusMonitor()
        self.running = False
        self.selected_row = 0
        
        # Screen management
        self.screen_height = 0
        self.screen_width = 0
        self.aircraft_list_height = 0
        self.waterfall_height = 0
        self.status_height = 3
        self.header_height = 2
        self.footer_height = 1
        
        # Data
        self.aircraft_data = {}
        self.status_data = {}
        self.last_update = datetime.now()
        self.update_interval = 0.1  # 100ms refresh rate
        
        # Aircraft display settings
        self.sort_column = 'icao'  # Default sort column
        self.sort_reverse = False  # Sort direction
        self.show_only_watchlist = False  # Filter for watchlist only
        self.scroll_offset = 0  # For scrolling through long lists
        
        # Status message system
        self._status_message = ""
        self._status_message_time = 0
        
    def run(self) -> None:
        """Run the dashboard application."""
        try:
            curses.wrapper(self._main_loop)
        except KeyboardInterrupt:
            logger.info("Dashboard interrupted by user")
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
    
    def _main_loop(self, screen) -> None:
        """Main dashboard loop with curses."""
        try:
            # Initialize curses
            self._initialize_curses(screen)
            
            # Initialize screen management
            self._update_screen_dimensions(screen)
            
            # Initialize waterfall
            self.waterfall = WaterfallDisplay(self.screen_width - 4, self.waterfall_height)
            
            self.running = True
            last_refresh = time.time()
            
            while self.running:
                try:
                    current_time = time.time()
                    
                    # Check if screen was resized
                    if self._check_screen_resize(screen):
                        self._update_screen_dimensions(screen)
                        self.waterfall = WaterfallDisplay(self.screen_width - 4, self.waterfall_height)
                    
                    # Only refresh screen at specified interval
                    if current_time - last_refresh >= self.update_interval:
                        # Clear screen
                        screen.clear()
                        
                        # Load latest data
                        self.load_data()
                        
                        # Draw UI components in order
                        self.draw_header(screen)
                        self.draw_aircraft_list(screen)
                        self.draw_waterfall(screen)
                        self.draw_status(screen)
                        self.draw_footer(screen)
                        
                        # Update waterfall with real-time data
                        self.waterfall.update()
                        
                        screen.refresh()
                        last_refresh = current_time
                    
                    # Handle input (non-blocking)
                    key = screen.getch()
                    if key != -1:  # Key was pressed
                        if not self.handle_input(screen, key):
                            break
                    
                    # Small sleep to prevent excessive CPU usage
                    time.sleep(0.01)
                    
                except curses.error:
                    # Ignore curses drawing errors (usually screen size issues)
                    pass
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    
        except Exception as e:
            logger.error(f"Error in dashboard main loop: {e}")
    
    def _initialize_curses(self, screen) -> None:
        """Initialize curses settings and colors."""
        try:
            curses.curs_set(0)  # Hide cursor
            screen.nodelay(1)   # Non-blocking input
            screen.timeout(10)  # 10ms timeout for getch()
            
            # Initialize colors if supported
            if curses.has_colors():
                curses.start_color()
                curses.use_default_colors()
                
                # Define color pairs
                curses.init_pair(1, curses.COLOR_RED, -1)      # Red text
                curses.init_pair(2, curses.COLOR_YELLOW, -1)   # Yellow text (watchlist)
                curses.init_pair(3, curses.COLOR_GREEN, -1)    # Green text (good status)
                curses.init_pair(4, curses.COLOR_BLUE, -1)     # Blue text
                curses.init_pair(5, curses.COLOR_MAGENTA, -1)  # Magenta text
                curses.init_pair(6, curses.COLOR_CYAN, -1)     # Cyan text
                curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Selection highlight
                
        except Exception as e:
            logger.error(f"Error initializing curses: {e}")
    
    def _update_screen_dimensions(self, screen) -> None:
        """Update screen dimensions and calculate layout."""
        try:
            self.screen_height, self.screen_width = screen.getmaxyx()
            
            # Calculate component heights
            available_height = self.screen_height - self.header_height - self.footer_height - self.status_height
            
            # Allocate space: 60% for aircraft list, 40% for waterfall
            self.aircraft_list_height = max(5, int(available_height * 0.6))
            self.waterfall_height = max(4, available_height - self.aircraft_list_height)
            
            logger.debug(f"Screen dimensions: {self.screen_width}x{self.screen_height}")
            logger.debug(f"Aircraft list height: {self.aircraft_list_height}")
            logger.debug(f"Waterfall height: {self.waterfall_height}")
            
        except Exception as e:
            logger.error(f"Error updating screen dimensions: {e}")
            # Set safe defaults
            self.screen_height = 24
            self.screen_width = 80
            self.aircraft_list_height = 10
            self.waterfall_height = 6
    
    def _check_screen_resize(self, screen) -> bool:
        """Check if screen has been resized."""
        try:
            height, width = screen.getmaxyx()
            if height != self.screen_height or width != self.screen_width:
                return True
            return False
        except:
            return False
    
    def load_data(self) -> None:
        """Load aircraft and status data from JSON files with error handling."""
        try:
            # Load aircraft data
            aircraft_file = Path("aircraft.json")
            if aircraft_file.exists():
                try:
                    with open(aircraft_file, 'r') as f:
                        new_aircraft_data = json.load(f)
                    
                    # Validate data structure
                    if isinstance(new_aircraft_data, dict):
                        self.aircraft_data = new_aircraft_data
                    else:
                        logger.warning("Invalid aircraft data format, keeping previous data")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in aircraft.json: {e}")
                except Exception as e:
                    logger.error(f"Error reading aircraft.json: {e}")
            else:
                # Initialize with empty data if file doesn't exist
                if not self.aircraft_data:
                    self.aircraft_data = {"aircraft": []}
            
            # Load status data
            status_file = Path("status.json")
            if status_file.exists():
                try:
                    with open(status_file, 'r') as f:
                        new_status_data = json.load(f)
                    
                    # Validate data structure
                    if isinstance(new_status_data, dict):
                        self.status_data = new_status_data
                    else:
                        logger.warning("Invalid status data format, keeping previous data")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in status.json: {e}")
                except Exception as e:
                    logger.error(f"Error reading status.json: {e}")
            else:
                # Initialize with default status if file doesn't exist
                if not self.status_data:
                    self.status_data = {
                        "receiver_running": False,
                        "hackrf_connected": False,
                        "meshtastic_connected": False,
                        "total_messages": 0,
                        "message_rate": 0.0,
                        "aircraft_count": 0,
                        "uptime": "N/A"
                    }
                    
            self.last_update = datetime.now()
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
    
    def draw_header(self, screen) -> None:
        """Draw dashboard header with enhanced status information."""
        try:
            title = "Ursine Capture - ADS-B Monitor"
            
            # Get status summary from monitor
            status_summary = self.status_monitor.get_status_summary()
            
            # Title
            screen.addstr(0, 2, title, curses.A_BOLD)
            
            # Enhanced status summary on the right
            if len(status_summary) < self.screen_width - len(title) - 6:
                status_x = self.screen_width - len(status_summary) - 2
                screen.addstr(0, status_x, status_summary, curses.color_pair(4))
            else:
                # Fallback to simple status if summary is too long
                status = self.status_data.get('receiver_running', False)
                status_text = "[RUNNING]" if status else "[STOPPED]"
                color = curses.color_pair(3) if status else curses.color_pair(1)
                screen.addstr(0, self.screen_width - len(status_text) - 2, status_text, color)
            
            # Separator line
            screen.addstr(1, 0, "─" * self.screen_width, curses.color_pair(4))
            
        except curses.error:
            pass
    
    def _sort_aircraft_list(self, aircraft_list: List[Dict]) -> List[Dict]:
        """Sort aircraft list by current sort column and direction."""
        try:
            if not aircraft_list:
                return aircraft_list
            
            # Define sort key functions
            def get_sort_key(aircraft):
                if self.sort_column == 'icao':
                    return aircraft.get('icao', '')
                elif self.sort_column == 'callsign':
                    return aircraft.get('callsign', aircraft.get('icao', ''))
                elif self.sort_column == 'altitude':
                    return aircraft.get('altitude') or 0
                elif self.sort_column == 'speed':
                    return aircraft.get('speed') or 0
                elif self.sort_column == 'track':
                    return aircraft.get('track') or 0
                elif self.sort_column == 'distance':
                    # Calculate distance from reference point if position available
                    lat = aircraft.get('latitude')
                    lon = aircraft.get('longitude')
                    if lat is not None and lon is not None:
                        try:
                            receiver_config = self.config.get_receiver_config()
                            from utils import calculate_distance
                            return calculate_distance(receiver_config.reference_lat, receiver_config.reference_lon, lat, lon)
                        except:
                            return 999999  # Put aircraft without distance at end
                    return 999999
                elif self.sort_column == 'age':
                    last_seen = aircraft.get('last_seen', '')
                    if last_seen:
                        try:
                            if last_seen.endswith('Z'):
                                last_time = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                            else:
                                last_time = datetime.fromisoformat(last_seen)
                            return (datetime.now() - last_time).total_seconds()
                        except:
                            return 999999
                    return 999999
                elif self.sort_column == 'watchlist':
                    return not aircraft.get('on_watchlist', False)  # Watchlist first when reverse=False
                else:
                    return aircraft.get('icao', '')
            
            return sorted(aircraft_list, key=get_sort_key, reverse=self.sort_reverse)
            
        except Exception as e:
            logger.error(f"Error sorting aircraft list: {e}")
            return aircraft_list
    
    def _filter_aircraft_list(self, aircraft_list: List[Dict]) -> List[Dict]:
        """Filter aircraft list based on current filter settings."""
        try:
            if not self.show_only_watchlist:
                return aircraft_list
            
            return [aircraft for aircraft in aircraft_list if aircraft.get('on_watchlist', False)]
            
        except Exception as e:
            logger.error(f"Error filtering aircraft list: {e}")
            return aircraft_list
    
    def draw_aircraft_list(self, screen) -> None:
        """Draw aircraft list display with sorting, filtering, and enhanced formatting."""
        try:
            start_y = self.header_height
            max_display_rows = self.aircraft_list_height - 2  # Reserve lines for header and info
            
            # Draw section border
            try:
                screen.addstr(start_y - 1, 0, "─" * self.screen_width)
            except curses.error:
                pass
            
            # Get and process aircraft data
            raw_aircraft_list = self.aircraft_data.get('aircraft', [])
            filtered_list = self._filter_aircraft_list(raw_aircraft_list)
            sorted_list = self._sort_aircraft_list(filtered_list)
            
            # Calculate display info
            total_aircraft = len(raw_aircraft_list)
            displayed_aircraft = len(sorted_list)
            watchlist_count = len([a for a in raw_aircraft_list if a.get('on_watchlist', False)])
            
            # Draw header with sort indicator
            sort_indicators = {
                'icao': '▲' if not self.sort_reverse else '▼',
                'callsign': '▲' if not self.sort_reverse else '▼',
                'altitude': '▲' if not self.sort_reverse else '▼',
                'speed': '▲' if not self.sort_reverse else '▼',
                'track': '▲' if not self.sort_reverse else '▼',
                'age': '▲' if not self.sort_reverse else '▼'
            }
            
            sort_indicator = sort_indicators.get(self.sort_column, '')
            
            # Enhanced header with sort indicator
            header_parts = [
                f"ICAO{sort_indicator if self.sort_column == 'icao' else ''}".ljust(9),
                f"Flight{sort_indicator if self.sort_column == 'callsign' else ''}".ljust(9),
                f"Alt{sort_indicator if self.sort_column == 'altitude' else ''}".ljust(7),
                f"Spd{sort_indicator if self.sort_column == 'speed' else ''}".ljust(7),
                f"Trk{sort_indicator if self.sort_column == 'track' else ''}".ljust(7),
                "Lat".ljust(9),
                "Lon".ljust(10),
                f"Age{sort_indicator if self.sort_column == 'age' else ''}".ljust(7)
            ]
            
            header = "".join(header_parts)
            if len(header) > self.screen_width - 4:
                header = header[:self.screen_width - 4]
            
            try:
                screen.addstr(start_y, 2, header, curses.A_BOLD | curses.A_UNDERLINE)
            except curses.error:
                pass
            
            # Draw info line
            filter_text = " [WATCHLIST ONLY]" if self.show_only_watchlist else ""
            info_line = f"Showing {displayed_aircraft}/{total_aircraft} aircraft, {watchlist_count} on watchlist{filter_text}"
            if len(info_line) > self.screen_width - 4:
                info_line = info_line[:self.screen_width - 4]
            
            try:
                screen.addstr(start_y + 1, 2, info_line, curses.color_pair(4))
            except curses.error:
                pass
            
            # Adjust scroll offset and selected row for current list
            if sorted_list:
                # Ensure selected row is within bounds
                if self.selected_row >= len(sorted_list):
                    self.selected_row = max(0, len(sorted_list) - 1)
                
                # Adjust scroll offset to keep selected row visible
                if self.selected_row < self.scroll_offset:
                    self.scroll_offset = self.selected_row
                elif self.selected_row >= self.scroll_offset + max_display_rows:
                    self.scroll_offset = self.selected_row - max_display_rows + 1
                
                # Ensure scroll offset is valid
                max_scroll = max(0, len(sorted_list) - max_display_rows)
                self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))
            else:
                self.selected_row = 0
                self.scroll_offset = 0
            
            # Draw aircraft rows
            for i in range(max_display_rows):
                aircraft_index = self.scroll_offset + i
                y = start_y + 2 + i
                
                if aircraft_index >= len(sorted_list) or y >= start_y + self.aircraft_list_height:
                    break
                
                aircraft = sorted_list[aircraft_index]
                
                # Format aircraft data with enhanced formatting
                icao = str(aircraft.get('icao', 'N/A'))[:8]
                callsign = str(aircraft.get('callsign', ''))[:8] or icao
                
                # Format altitude with thousands separator
                altitude = aircraft.get('altitude')
                alt_str = f"{altitude:,}" if altitude else "N/A"
                alt_str = alt_str[:6]
                
                # Format speed and track
                speed = aircraft.get('speed') or 0
                track = aircraft.get('track') or 0
                
                # Format coordinates with better precision
                lat = aircraft.get('latitude')
                lon = aircraft.get('longitude')
                lat_str = f"{lat:.3f}" if lat is not None else "N/A"
                lon_str = f"{lon:.3f}" if lon is not None else "N/A"
                
                # Calculate and format age
                last_seen = aircraft.get('last_seen', '')
                age = "N/A"
                if last_seen:
                    try:
                        if last_seen.endswith('Z'):
                            last_time = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                        else:
                            last_time = datetime.fromisoformat(last_seen)
                        age = format_time_ago(last_time)
                    except Exception:
                        age = "N/A"
                
                # Format line with consistent spacing
                line_parts = [
                    icao.ljust(9),
                    callsign.ljust(9),
                    alt_str.ljust(7),
                    str(speed).ljust(7),
                    f"{track:03d}°".ljust(7),
                    lat_str.ljust(9),
                    lon_str.ljust(10),
                    age.ljust(7)
                ]
                
                line = "".join(line_parts)
                
                # Truncate line to fit screen
                if len(line) > self.screen_width - 4:
                    line = line[:self.screen_width - 4]
                
                # Determine colors and attributes
                color = 0
                
                # Highlight watchlist aircraft in yellow/bold
                if aircraft.get('on_watchlist', False):
                    color = curses.color_pair(2) | curses.A_BOLD
                    # Add watchlist indicator
                    if len(line) < self.screen_width - 6:
                        line += " ★"
                
                # Highlight selected row
                if aircraft_index == self.selected_row:
                    if curses.has_colors():
                        color = curses.color_pair(7)  # White on blue
                    else:
                        color = curses.A_REVERSE
                
                try:
                    screen.addstr(y, 2, line, color)
                except curses.error:
                    pass
            
            # Draw scroll indicator if needed
            if len(sorted_list) > max_display_rows:
                try:
                    scroll_info = f"[{self.scroll_offset + 1}-{min(self.scroll_offset + max_display_rows, len(sorted_list))}/{len(sorted_list)}]"
                    screen.addstr(start_y + self.aircraft_list_height - 1, self.screen_width - len(scroll_info) - 2, 
                                scroll_info, curses.color_pair(4))
                except curses.error:
                    pass
            
            # Draw bottom border
            try:
                border_y = start_y + self.aircraft_list_height
                if border_y < self.screen_height - self.status_height - self.footer_height:
                    screen.addstr(border_y, 0, "─" * self.screen_width)
            except curses.error:
                pass
                
        except Exception as e:
            logger.error(f"Error drawing aircraft list: {e}")
    
    def draw_waterfall(self, screen) -> None:
        """Draw enhanced waterfall spectrum display with status information."""
        try:
            start_y = self.header_height + self.aircraft_list_height + 1
            
            # Ensure we don't draw outside screen bounds
            if start_y >= self.screen_height - self.status_height - self.footer_height:
                return
            
            # Enhanced title with status information
            if self.waterfall:
                status_info = self.waterfall.get_status_info()
                center_freq = status_info.get('center_freq_mhz', 1090)
                sample_rate = status_info.get('sample_rate_mhz', 2)
                update_count = status_info.get('update_counter', 0)
                
                title = f"Waterfall Display ({center_freq:.1f} MHz ±{sample_rate/2:.1f} MHz) - Updates: {update_count}"
            else:
                title = "Waterfall Display (1090 MHz)"
            
            # Truncate title if too long
            if len(title) > self.screen_width - 4:
                title = title[:self.screen_width - 7] + "..."
            
            try:
                screen.addstr(start_y, 2, title, curses.A_BOLD)
            except curses.error:
                pass
            
            # Draw waterfall if there's space
            if self.waterfall and start_y + 1 < self.screen_height - self.status_height - self.footer_height:
                available_height = min(self.waterfall_height - 1, 
                                     self.screen_height - start_y - self.status_height - self.footer_height - 2)
                if available_height > 0:
                    # Check if waterfall has real data
                    if len(self.waterfall.data) > 0:
                        self.waterfall.draw(screen, start_y + 1, 2)
                    else:
                        # Show message when no FFT data is available
                        try:
                            screen.addstr(start_y + 1, 2, "No FFT data available - waterfall requires dump1090 with --write-json or HTTP API", curses.color_pair(4))
                        except curses.error:
                            pass
                else:
                    # Show message if no space for waterfall
                    try:
                        screen.addstr(start_y + 1, 2, "Insufficient space for waterfall display", curses.color_pair(1))
                    except curses.error:
                        pass
            else:
                # Show message if waterfall not initialized
                try:
                    screen.addstr(start_y + 1, 2, "Waterfall display initializing...", curses.color_pair(4))
                except curses.error:
                    pass
            
            # Draw color legend if there's space
            legend_y = start_y + self.waterfall_height - 1
            if legend_y > start_y + 2 and legend_y < self.screen_height - self.status_height - self.footer_height:
                self._draw_waterfall_legend(screen, legend_y)
            
            # Draw bottom border
            try:
                border_y = start_y + self.waterfall_height
                if border_y < self.screen_height - self.status_height - self.footer_height:
                    screen.addstr(border_y, 0, "─" * self.screen_width)
            except curses.error:
                pass
                
        except Exception as e:
            logger.error(f"Error drawing waterfall: {e}")
    
    def _draw_waterfall_legend(self, screen, y: int) -> None:
        """Draw color legend for waterfall display."""
        try:
            legend_items = [
                ("█", curses.color_pair(1) | curses.A_BOLD, "Strong"),
                ("▓", curses.color_pair(5), "Medium"),
                ("▒", curses.color_pair(2), "Weak"),
                ("░", curses.color_pair(4), "Noise"),
                ("│", curses.color_pair(6) | curses.A_BOLD, "1090MHz")
            ]
            
            legend_text = "Legend: "
            x_pos = 2
            
            try:
                screen.addstr(y, x_pos, legend_text, curses.color_pair(4))
                x_pos += len(legend_text)
                
                for char, color, label in legend_items:
                    if x_pos + len(char) + len(label) + 3 < self.screen_width - 2:
                        screen.addch(y, x_pos, char, color)
                        x_pos += 1
                        screen.addstr(y, x_pos, f"{label} ", curses.color_pair(4))
                        x_pos += len(label) + 1
                    else:
                        break
                        
            except curses.error:
                pass
                
        except Exception as e:
            logger.error(f"Error drawing waterfall legend: {e}")
    
    def draw_status(self, screen) -> None:
        """Draw enhanced system status information with comprehensive monitoring."""
        try:
            start_y = self.screen_height - self.status_height - self.footer_height
            status_width = self.screen_width - 4
            
            # Use the SystemStatusMonitor for enhanced status display
            status_data = self.status_monitor.get_status_display_data()
            
            # Get configuration for display
            try:
                radio_config = self.config.get_radio_config()
                gain_info = f"Gain: {radio_config.lna_gain}/{radio_config.vga_gain}"
            except:
                gain_info = "Gain: N/A"
            
            # Status line 1 - Component status with health indicators
            components = [
                f"{status_data['receiver_status']['symbol']} Receiver",
                f"{status_data['dump1090_status']['symbol']} dump1090", 
                f"{status_data['hackrf_status']['symbol']} HackRF",
                f"{status_data['meshtastic_status']['symbol']} Meshtastic"
            ]
            
            # Add overall health indicator
            health_colors = {
                "HEALTHY": curses.color_pair(2),   # Green
                "DEGRADED": curses.color_pair(3), # Yellow  
                "ERROR": curses.color_pair(1)     # Red
            }
            
            health_color = health_colors.get(status_data["overall_health"], curses.color_pair(4))
            health_text = f"[{status_data['overall_health']}]"
            
            line1 = f"{health_text} {' '.join(components[:2])} {gain_info}"
            
            # Truncate to fit screen
            if len(line1) > status_width:
                line1 = line1[:status_width]
            
            try:
                # Draw health indicator with appropriate color
                screen.addstr(start_y, 2, health_text, health_color | curses.A_BOLD)
                # Draw rest of line in normal color
                remaining_text = line1[len(health_text):]
                screen.addstr(start_y, 2 + len(health_text), remaining_text, 0)
            except curses.error:
                pass
            
            # Status line 2 - More components and performance metrics
            line2_parts = [
                ' '.join(components[2:]),  # HackRF and Meshtastic
                f"Rate: {status_data['message_rate']:.1f}/s",
                f"Aircraft: {status_data['aircraft_count']}"
            ]
            
            line2 = '  '.join(line2_parts)
            
            # Truncate to fit screen
            if len(line2) > status_width:
                line2 = line2[:status_width]
            
            # Color code message rate
            rate = status_data['message_rate']
            if rate > 30:
                rate_color = curses.color_pair(2)  # Green - good rate
            elif rate > 10:
                rate_color = curses.color_pair(3)  # Yellow - moderate rate
            elif rate > 0:
                rate_color = curses.color_pair(1)  # Red - low rate
            else:
                rate_color = curses.color_pair(4)  # Blue - no data
            
            try:
                screen.addstr(start_y + 1, 2, line2, rate_color)
            except curses.error:
                pass
            
            # Status line 3 - Extended metrics and error conditions
            current_time = time.time()
            if (hasattr(self, '_status_message') and self._status_message and 
                hasattr(self, '_status_message_time') and 
                current_time - self._status_message_time < 3.0):  # Show for 3 seconds
                # Show status message instead of normal info
                line3 = f"Status: {self._status_message}"
                color = curses.color_pair(2) | curses.A_BOLD  # Green and bold
            elif status_data["errors"]:
                # Show most recent error
                error_text = status_data["errors"][-1]
                line3 = f"ERROR: {error_text}"
                color = curses.color_pair(1) | curses.A_BOLD  # Red and bold
            else:
                # Show extended metrics
                line3_parts = [
                    f"Watchlist: {status_data['watchlist_count']}",
                    f"Total: {status_data['total_messages']:,}",
                    f"Up: {status_data['uptime']}"
                ]
                line3 = '  '.join(line3_parts)
                color = curses.color_pair(4)  # Blue
            
            # Truncate to fit screen
            if len(line3) > status_width:
                line3 = line3[:status_width]
            
            try:
                screen.addstr(start_y + 2, 2, line3, color)
            except curses.error:
                pass
            
        except Exception as e:
            logger.error(f"Error drawing enhanced status: {e}")
            # Fallback to simple status display
            try:
                screen.addstr(start_y, 2, f"Status Error: {str(e)[:status_width-15]}", 
                            curses.color_pair(1))
            except curses.error:
                pass
    
    def show_detailed_status(self, screen) -> None:
        """Show detailed system status in a full-screen overlay."""
        try:
            # Get comprehensive status data
            status_data = self.status_monitor.get_status_display_data()
            
            # Clear screen for status display
            screen.clear()
            
            # Draw title
            title = "DETAILED SYSTEM STATUS"
            title_y = 2
            title_x = (self.screen_width - len(title)) // 2
            screen.addstr(title_y, title_x, title, curses.A_BOLD | curses.A_UNDERLINE)
            
            # Draw overall health
            health_y = 4
            health_colors = {
                "HEALTHY": curses.color_pair(2) | curses.A_BOLD,   # Green
                "DEGRADED": curses.color_pair(3) | curses.A_BOLD, # Yellow  
                "ERROR": curses.color_pair(1) | curses.A_BOLD     # Red
            }
            health_color = health_colors.get(status_data["overall_health"], curses.color_pair(4))
            health_text = f"Overall System Health: {status_data['overall_health']}"
            screen.addstr(health_y, 4, health_text, health_color)
            
            # Draw component status section
            comp_y = 6
            screen.addstr(comp_y, 4, "COMPONENT STATUS:", curses.A_BOLD)
            
            components = [
                status_data["receiver_status"],
                status_data["dump1090_status"], 
                status_data["hackrf_status"],
                status_data["meshtastic_status"]
            ]
            
            for i, component in enumerate(components):
                y = comp_y + 2 + i
                color = curses.color_pair(2) if component["color"] == "green" else curses.color_pair(1)
                status_line = f"  {component['symbol']} {component['name']:<15} {component['status']}"
                screen.addstr(y, 4, status_line, color)
            
            # Draw performance metrics section
            perf_y = comp_y + 7
            screen.addstr(perf_y, 4, "PERFORMANCE METRICS:", curses.A_BOLD)
            
            metrics = [
                f"Message Rate: {status_data['message_rate']:.1f} messages/second",
                f"Aircraft Count: {status_data['aircraft_count']} currently tracked",
                f"Watchlist Count: {status_data['watchlist_count']} aircraft monitored",
                f"Total Messages: {status_data['total_messages']:,} received",
                f"System Uptime: {status_data['uptime']}"
            ]
            
            for i, metric in enumerate(metrics):
                y = perf_y + 2 + i
                # Color code message rate
                if "Message Rate" in metric:
                    rate = status_data['message_rate']
                    if rate > 30:
                        color = curses.color_pair(2)  # Green
                    elif rate > 10:
                        color = curses.color_pair(3)  # Yellow
                    elif rate > 0:
                        color = curses.color_pair(1)  # Red
                    else:
                        color = curses.color_pair(4)  # Blue
                else:
                    color = 0
                
                screen.addstr(y, 6, metric, color)
            
            # Draw error conditions if any
            if status_data["errors"]:
                error_y = perf_y + 8
                screen.addstr(error_y, 4, "ERROR CONDITIONS:", curses.color_pair(1) | curses.A_BOLD)
                
                for i, error in enumerate(status_data["errors"][-5:]):  # Show last 5 errors
                    y = error_y + 2 + i
                    if y < self.screen_height - 3:
                        error_text = f"  • {error}"
                        screen.addstr(y, 4, error_text[:self.screen_width-8], curses.color_pair(1))
            
            # Draw configuration info
            config_y = self.screen_height - 8
            try:
                radio_config = self.config.get_radio_config()
                screen.addstr(config_y, 4, "RADIO CONFIGURATION:", curses.A_BOLD)
                screen.addstr(config_y + 1, 6, f"Frequency: {radio_config.frequency / 1000000:.1f} MHz")
                screen.addstr(config_y + 2, 6, f"LNA Gain: {radio_config.lna_gain} dB")
                screen.addstr(config_y + 3, 6, f"VGA Gain: {radio_config.vga_gain} dB")
                screen.addstr(config_y + 4, 6, f"Amp Enable: {'ON' if radio_config.enable_amp else 'OFF'}")
            except Exception as e:
                screen.addstr(config_y, 4, f"Configuration Error: {e}", curses.color_pair(1))
            
            # Draw instructions
            instructions = "Press any key to return to main dashboard"
            instr_y = self.screen_height - 2
            instr_x = (self.screen_width - len(instructions)) // 2
            screen.addstr(instr_y, instr_x, instructions, curses.A_BOLD)
            
            screen.refresh()
            
            # Wait for user input
            screen.getch()
            
        except Exception as e:
            logger.error(f"Error showing detailed status: {e}")
            # Show error message and wait
            try:
                screen.clear()
                error_msg = f"Error displaying status: {e}"
                screen.addstr(self.screen_height // 2, 4, error_msg, curses.color_pair(1))
                screen.addstr(self.screen_height // 2 + 2, 4, "Press any key to continue", curses.A_BOLD)
                screen.refresh()
                screen.getch()
            except curses.error:
                pass
    
    def draw_footer(self, screen) -> None:
        """Draw footer with key commands."""
        try:
            footer_y = self.screen_height - 1
            
            # Create dynamic footer based on current state and selected aircraft
            aircraft_list = self._get_current_aircraft_list()
            selected_aircraft = None
            if 0 <= self.selected_row < len(aircraft_list):
                selected_aircraft = aircraft_list[self.selected_row]
            
            # Base commands change based on selected aircraft watchlist status
            if selected_aircraft and selected_aircraft.get('on_watchlist', False):
                base_commands = "[M]enu [↑↓]Select [X]Remove"
            else:
                base_commands = "[M]enu [↑↓]Select [Enter]Add"
            
            watchlist_commands = "[W]atchlist"
            status_commands = "[S]tatus"
            sort_commands = "[1-8]Sort"
            filter_commands = "[T]oggle Filter"
            help_commands = "[?]Help [Q]uit"
            
            # Combine commands based on available space
            if self.screen_width > 140:
                footer = f"{base_commands} {watchlist_commands} {status_commands} {sort_commands} {filter_commands} {help_commands}"
            elif self.screen_width > 120:
                footer = f"{base_commands} {watchlist_commands} {status_commands} {sort_commands} {help_commands}"
            elif self.screen_width > 100:
                footer = f"{base_commands} {watchlist_commands} {status_commands} {help_commands}"
            elif self.screen_width > 80:
                footer = f"{base_commands} {watchlist_commands} {help_commands}"
            elif self.screen_width > 60:
                footer = f"{base_commands} {help_commands}"
            else:
                footer = "[M]enu [Enter]Add [Q]uit"
            
            # Add filter indicator if active
            if self.show_only_watchlist and len(footer) < self.screen_width - 20:
                footer += " [FILTERED]"
            
            # Truncate footer to fit screen
            if len(footer) > self.screen_width - 4:
                footer = footer[:self.screen_width - 4]
            
            # Draw footer background
            try:
                # Fill entire footer line with reverse video
                footer_line = footer.ljust(self.screen_width - 4)
                screen.addstr(footer_y, 2, footer_line, curses.A_REVERSE)
            except curses.error:
                # Fallback: just draw the text
                screen.addstr(footer_y, 2, footer, curses.A_REVERSE)
            
        except curses.error:
            pass
    
    def handle_input(self, screen, key: int) -> bool:
        """Handle keyboard input with comprehensive navigation and sorting. Returns False to quit."""
        try:
            # Handle special keys first
            if key == ord('q') or key == ord('Q'):
                return False
            elif key == 27:  # ESC key
                return True  # Just refresh screen
            elif key == ord('m') or key == ord('M'):
                action = self.menu_system.show_main_menu(screen)
                if action == "quit":
                    return False
                elif action == "radio":
                    self.menu_system.show_radio_menu(screen)
                elif action == "watchlist":
                    self.menu_system.show_watchlist_menu(screen)
                elif action == "status":
                    self.show_detailed_status(screen)
                # Redraw screen after menu
                screen.clear()
            
            # Navigation keys
            elif key == curses.KEY_UP or key == ord('k'):
                # Move selection up
                self.selected_row = max(0, self.selected_row - 1)
            elif key == curses.KEY_DOWN or key == ord('j'):
                # Move selection down
                aircraft_list = self._get_current_aircraft_list()
                max_rows = max(0, len(aircraft_list) - 1)
                self.selected_row = min(max_rows, self.selected_row + 1)
            elif key == curses.KEY_HOME or key == ord('g'):
                # Go to first aircraft
                self.selected_row = 0
                self.scroll_offset = 0
            elif key == curses.KEY_END or key == ord('G'):
                # Go to last aircraft
                aircraft_list = self._get_current_aircraft_list()
                self.selected_row = max(0, len(aircraft_list) - 1)
            elif key == curses.KEY_PPAGE:  # Page Up
                # Move up by 10 rows
                self.selected_row = max(0, self.selected_row - 10)
            elif key == curses.KEY_NPAGE:  # Page Down
                # Move down by 10 rows
                aircraft_list = self._get_current_aircraft_list()
                max_rows = max(0, len(aircraft_list) - 1)
                self.selected_row = min(max_rows, self.selected_row + 10)
            
            # Action keys
            elif key == ord('\n') or key == ord('\r') or key == 10:  # Enter key
                self.add_selected_to_watchlist()
            elif key == ord(' '):  # Space bar - also add to watchlist
                self.add_selected_to_watchlist()
            elif key == ord('x') or key == ord('X'):
                # Remove selected aircraft from watchlist
                self.remove_selected_from_watchlist()
            
            # Sorting keys
            elif key == ord('1'):
                self._toggle_sort('icao')
            elif key == ord('2'):
                self._toggle_sort('callsign')
            elif key == ord('3'):
                self._toggle_sort('altitude')
            elif key == ord('4'):
                self._toggle_sort('speed')
            elif key == ord('5'):
                self._toggle_sort('track')
            elif key == ord('6'):
                self._toggle_sort('distance')
            elif key == ord('7'):
                self._toggle_sort('age')
            elif key == ord('8'):
                self._toggle_sort('watchlist')
            
            # Filter keys
            elif key == ord('t') or key == ord('T'):
                # Toggle watchlist filter
                self.show_only_watchlist = not self.show_only_watchlist
                self.selected_row = 0
                self.scroll_offset = 0
            
            # Menu shortcuts
            elif key == ord('w') or key == ord('W'):
                # Quick watchlist menu
                self.menu_system.show_watchlist_menu(screen)
                screen.clear()
            elif key == ord('r') or key == ord('R'):
                # Quick radio menu
                self.menu_system.show_radio_menu(screen)
                screen.clear()
            elif key == ord('s') or key == ord('S'):
                # Quick status display
                self.show_detailed_status(screen)
                screen.clear()
            elif key == ord('?') or key == ord('h'):
                # Show help
                self._show_help(screen)
                screen.clear()
            elif key == ord('f') or key == ord('F'):
                # Force refresh
                self.load_data()
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling input: {e}")
            return True
    
    def _get_current_aircraft_list(self) -> List[Dict]:
        """Get the current filtered and sorted aircraft list."""
        try:
            raw_aircraft_list = self.aircraft_data.get('aircraft', [])
            filtered_list = self._filter_aircraft_list(raw_aircraft_list)
            sorted_list = self._sort_aircraft_list(filtered_list)
            return sorted_list
        except Exception as e:
            logger.error(f"Error getting current aircraft list: {e}")
            return []
    
    def _toggle_sort(self, column: str) -> None:
        """Toggle sort column and direction."""
        try:
            if self.sort_column == column:
                # Same column, toggle direction
                self.sort_reverse = not self.sort_reverse
            else:
                # New column, default to ascending
                self.sort_column = column
                self.sort_reverse = False
            
            # Reset selection to top when sorting changes
            self.selected_row = 0
            self.scroll_offset = 0
            
            logger.debug(f"Sort changed to {column} {'desc' if self.sort_reverse else 'asc'}")
            
        except Exception as e:
            logger.error(f"Error toggling sort: {e}")
    
    def remove_selected_from_watchlist(self) -> None:
        """Remove currently selected aircraft from watchlist with enhanced feedback."""
        try:
            aircraft_list = self._get_current_aircraft_list()
            if 0 <= self.selected_row < len(aircraft_list):
                aircraft = aircraft_list[self.selected_row]
                icao = aircraft.get('icao', '')
                
                if icao and aircraft.get('on_watchlist', False):
                    if self.config.remove_from_watchlist(icao):
                        logger.info(f"Removed {icao} from watchlist")
                        # Update the aircraft data to reflect watchlist status
                        aircraft['on_watchlist'] = False
                        # Find and update in original data too
                        for orig_aircraft in self.aircraft_data.get('aircraft', []):
                            if orig_aircraft.get('icao') == icao:
                                orig_aircraft['on_watchlist'] = False
                                break
                        self._show_brief_message(f"Removed {icao} from watchlist")
                    else:
                        logger.error(f"Failed to remove {icao} from watchlist")
                        self._show_brief_message(f"Failed to remove {icao}")
                else:
                    logger.info(f"Aircraft {icao} is not on watchlist")
                    self._show_brief_message(f"{icao} not on watchlist")
                        
        except Exception as e:
            logger.error(f"Error removing from watchlist: {e}")
            self._show_brief_message("Error removing from watchlist")
    
    def _show_brief_message(self, message: str, duration: float = 1.0) -> None:
        """Show a brief status message that doesn't block the interface."""
        try:
            # Store message for display in status area
            self._status_message = message
            self._status_message_time = time.time()
            logger.info(f"Status: {message}")
        except Exception as e:
            logger.error(f"Error showing brief message: {e}")
    
    def _show_help(self, screen) -> None:
        """Show help screen with key bindings."""
        try:
            help_text = [
                "URSINE CAPTURE - KEYBOARD SHORTCUTS",
                "",
                "Navigation:",
                "  ↑/k        - Move selection up",
                "  ↓/j        - Move selection down", 
                "  Home/g     - Go to first aircraft",
                "  End/G      - Go to last aircraft",
                "  Page Up    - Move up 10 rows",
                "  Page Down  - Move down 10 rows",
                "",
                "Actions:",
                "  Enter/Space - Add selected aircraft to watchlist",
                "  x          - Remove selected aircraft from watchlist",
                "  m          - Show main menu",
                "  w          - Show watchlist menu",
                "  r          - Show radio menu",
                "  f          - Force data refresh",
                "  ?/h        - Show this help",
                "  q          - Quit application",
                "  ESC        - Cancel/refresh",
                "",
                "Sorting (1-8):",
                "  1          - Sort by ICAO",
                "  2          - Sort by Flight/Callsign",
                "  3          - Sort by Altitude",
                "  4          - Sort by Speed",
                "  5          - Sort by Track",
                "  6          - Sort by Distance",
                "  7          - Sort by Age",
                "  8          - Sort by Watchlist status",
                "",
                "Filtering:",
                "  t          - Toggle watchlist-only filter",
                "",
                "Watchlist Management:",
                "  w          - Open watchlist management menu",
                "  A/E/D/C    - Add/Edit/Delete/Clear in watchlist menu",
                "  I          - Import from tracked aircraft",
                "",
                "Press any key to continue..."
            ]
            
            # Clear screen and show help
            screen.clear()
            
            start_y = max(0, (self.screen_height - len(help_text)) // 2)
            
            for i, line in enumerate(help_text):
                y = start_y + i
                if y < self.screen_height - 1:
                    x = max(0, (self.screen_width - len(line)) // 2)
                    try:
                        if line.startswith("URSINE CAPTURE"):
                            screen.addstr(y, x, line, curses.A_BOLD | curses.A_UNDERLINE)
                        elif line.endswith(":"):
                            screen.addstr(y, x, line, curses.A_BOLD)
                        else:
                            screen.addstr(y, x, line)
                    except curses.error:
                        pass
            
            screen.refresh()
            screen.getch()  # Wait for key press
            
        except Exception as e:
            logger.error(f"Error showing help: {e}")
    
    def add_selected_to_watchlist(self) -> None:
        """Add currently selected aircraft to watchlist with enhanced feedback."""
        try:
            aircraft_list = self._get_current_aircraft_list()
            if 0 <= self.selected_row < len(aircraft_list):
                aircraft = aircraft_list[self.selected_row]
                icao = aircraft.get('icao', '')
                callsign = aircraft.get('callsign', '')
                
                if icao:
                    if aircraft.get('on_watchlist', False):
                        logger.info(f"Aircraft {icao} is already on watchlist")
                        # Show brief status message
                        self._show_brief_message(f"{icao} already on watchlist")
                        return
                    
                    name = callsign if callsign else f"Aircraft {icao}"
                    if self.config.add_to_watchlist(icao, name):
                        logger.info(f"Added {icao} ({name}) to watchlist")
                        # Update the aircraft data to reflect watchlist status
                        # Find the aircraft in the original data and update it
                        for orig_aircraft in self.aircraft_data.get('aircraft', []):
                            if orig_aircraft.get('icao') == icao:
                                orig_aircraft['on_watchlist'] = True
                                break
                        # Show success message
                        self._show_brief_message(f"Added {icao} to watchlist")
                    else:
                        logger.error(f"Failed to add {icao} to watchlist")
                        self._show_brief_message(f"Failed to add {icao}")
                        
        except Exception as e:
            logger.error(f"Error adding to watchlist: {e}")
            self._show_brief_message("Error adding to watchlist")
    
    def shutdown(self) -> None:
        """Gracefully shutdown the dashboard."""
        try:
            self.running = False
            logger.info("Dashboard shutting down")
        except Exception as e:
            logger.error(f"Error during dashboard shutdown: {e}")


dashboard_instance = None

def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Dashboard received signal {signum}")
    if dashboard_instance:
        dashboard_instance.shutdown()
    sys.exit(0)


def main():
    """Main dashboard entry point with comprehensive error handling."""
    global dashboard_instance
    
    try:
        setup_logging("ursine-dashboard.log")
        logger.info("Starting Ursine Capture Dashboard")
        
        # Set up signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
        
        dashboard_instance = Dashboard(config_path)
        
        # Initialize error notification system
        dashboard_instance.error_notifications = ErrorNotificationSystem()
        
        # Run dashboard with error handling
        dashboard_instance.run()
        
    except KeyboardInterrupt:
        logger.info("Dashboard interrupted by user")
        if dashboard_instance:
            dashboard_instance.shutdown()
    except Exception as e:
        error_handler.handle_error(
            ComponentType.DASHBOARD,
            ErrorSeverity.CRITICAL,
            f"Fatal error in dashboard main: {str(e)}",
            error_code="DASHBOARD_FATAL_ERROR"
        )
        logger.error(f"Fatal dashboard error: {e}")
        if dashboard_instance:
            dashboard_instance.shutdown()
        sys.exit(1)
    finally:
        logger.info("Dashboard main process exiting")
        sys.exit(0)


if __name__ == "__main__":
    main()