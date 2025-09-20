#!/usr/bin/env python3
"""
Ursine Explorer - Live ADS-B Dashboard
Real-time terminal dashboard showing aircraft activity
"""

import json
import time
import requests
import curses
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import signal
import sys
import socket
import struct
import os
import numpy as np

class Aircraft:
    def __init__(self, data: dict):
        self.hex = data.get('hex', 'Unknown').upper()
        self.flight = data.get('flight', '').strip() or 'Unknown'
        self.altitude = data.get('alt_baro', 'Unknown')
        self.speed = data.get('gs', 'Unknown')
        self.track = data.get('track', 'Unknown')
        self.lat = data.get('lat', 'Unknown')
        self.lon = data.get('lon', 'Unknown')
        self.squawk = data.get('squawk', 'Unknown')
        self.category = data.get('category', 'Unknown')
        self.last_seen = datetime.now()
        self.first_seen = datetime.now()
        self.messages = data.get('messages', 0)
        
        # Enhanced pyModeS fields
        self.enhanced = data.get('enhanced', {})
        self.true_airspeed = self.enhanced.get('true_airspeed', 'Unknown')
        self.indicated_airspeed = self.enhanced.get('indicated_airspeed', 'Unknown')
        self.magnetic_heading = self.enhanced.get('magnetic_heading', 'Unknown')
        self.vertical_rate = self.enhanced.get('vertical_rate', 'Unknown')
        self.navigation_accuracy = self.enhanced.get('navigation_accuracy', {})
        self.surveillance_status = self.enhanced.get('surveillance_status', 'Unknown')
        self.data_sources = data.get('data_sources', [])
        
        # Data quality indicators
        self.has_position = self.lat != 'Unknown' and self.lon != 'Unknown'
        self.has_velocity = self.speed != 'Unknown' or self.track != 'Unknown'
        self.has_altitude = self.altitude != 'Unknown'
        self.enhanced_data_available = bool(self.enhanced)
        
    def update(self, data: dict):
        """Update aircraft data"""
        self.flight = data.get('flight', '').strip() or self.flight
        self.altitude = data.get('alt_baro', self.altitude)
        self.speed = data.get('gs', self.speed)
        self.track = data.get('track', self.track)
        self.lat = data.get('lat', self.lat)
        self.lon = data.get('lon', self.lon)
        self.squawk = data.get('squawk', self.squawk)
        self.category = data.get('category', self.category)
        self.messages = data.get('messages', self.messages)
        self.last_seen = datetime.now()
        
        # Update enhanced fields
        if 'enhanced' in data:
            self.enhanced.update(data['enhanced'])
            self.true_airspeed = self.enhanced.get('true_airspeed', self.true_airspeed)
            self.indicated_airspeed = self.enhanced.get('indicated_airspeed', self.indicated_airspeed)
            self.magnetic_heading = self.enhanced.get('magnetic_heading', self.magnetic_heading)
            self.vertical_rate = self.enhanced.get('vertical_rate', self.vertical_rate)
            self.navigation_accuracy = self.enhanced.get('navigation_accuracy', self.navigation_accuracy)
            self.surveillance_status = self.enhanced.get('surveillance_status', self.surveillance_status)
        
        if 'data_sources' in data:
            self.data_sources = data['data_sources']
        
        # Update data quality indicators
        self.has_position = self.lat != 'Unknown' and self.lon != 'Unknown'
        self.has_velocity = self.speed != 'Unknown' or self.track != 'Unknown'
        self.has_altitude = self.altitude != 'Unknown'
        self.enhanced_data_available = bool(self.enhanced)
    
    def age_seconds(self) -> int:
        """Get age in seconds since last seen"""
        return int((datetime.now() - self.last_seen).total_seconds())
    
    def duration_seconds(self) -> int:
        """Get total tracking duration in seconds"""
        return int((self.last_seen - self.first_seen).total_seconds())

class ADSBDashboard:
    def __init__(self, config_path: str = "config.json"):
        self.config = self.load_config(config_path)
        self.aircraft: Dict[str, Aircraft] = {}
        self.running = True
        
        # Menu system
        self.menu_active = False
        self.menu_items = ['RF Gain', 'IF Gain', 'BB Gain', 'Sample Rate', 'Center Freq', 'Test Connection', 'Exit Menu']
        self.menu_selected = 0
        self.input_mode = False
        self.input_buffer = ""
        self.input_prompt = ""
        self.connection_status = "Unknown"
        
        # Waterfall display
        self.show_waterfall = False
        self.waterfall_data = []
        self.fft_file = "/tmp/adsb_fft.dat"
        self.fft_size = 1024
        
        # HackRF settings with safe ranges
        self.hackrf_settings = {
            'rf_gain': {'value': 40, 'min': 0, 'max': 47, 'unit': 'dB'},
            'if_gain': {'value': 32, 'min': 0, 'max': 47, 'unit': 'dB'},
            'bb_gain': {'value': 32, 'min': 0, 'max': 62, 'unit': 'dB'},
            'sample_rate': {'value': 2000000, 'min': 1000000, 'max': 20000000, 'unit': 'Hz'},
            'center_freq': {'value': 1090000000, 'min': 1000000000, 'max': 1200000000, 'unit': 'Hz'}
        }
        
        self.stats = {
            'total_aircraft': 0,
            'active_aircraft': 0,
            'messages_total': 0,
            'last_update': None,
            'update_count': 0,
            'errors': 0,
            'messages_per_second': 0,
            'aircraft_with_positions': 0,
            'max_range_km': 0,
            'avg_signal_strength': 0,
            'strong_signals': 0,
            'weak_signals': 0
        }
        
        # pyModeS-specific statistics
        self.pymodes_stats = {
            'messages_processed': 0,
            'messages_decoded': 0,
            'messages_failed': 0,
            'decode_rate': 0.0,
            'error_rate': 0.0,
            'aircraft_count': 0,
            'cpr_success_rate': 0.0,
            'position_calculations': 0,
            'position_successes': 0,
            'last_stats_update': None
        }
        
        # Message source statistics
        self.source_stats = {
            'sources_total': 0,
            'sources_connected': 0,
            'health_status': 'unknown',
            'total_messages': 0,
            'duplicate_messages': 0,
            'messages_per_second': 0.0,
            'sources': []
        }
        
        # Error tracking and diagnostics
        self.error_log = []  # Recent errors with timestamps
        self.max_error_log_size = 50
        self.connection_history = []  # Connection status changes
        self.max_connection_history = 20
        self.alert_status = {
            'watchlist_alerts_sent': 0,
            'last_alert_time': None,
            'alert_errors': 0,
            'meshtastic_status': 'unknown'
        }
        
        # Enhanced Meshtastic status tracking
        self.meshtastic_status = {
            'initialized': False,
            'connection_mode': 'unknown',
            'interfaces': {},
            'active_channels': [],
            'message_stats': {
                'messages_sent': 0,
                'messages_failed': 0,
                'success_rate': 0.0
            },
            'device_info': {},
            'mqtt_broker': 'unknown',
            'last_update': None,
            'health_score': 0,
            'diagnostics': {}
        }
        self.message_history = []  # Track message rates
        self.signal_strengths = []  # Track signal strengths
        self.sort_by = 'last_seen'  # Options: last_seen, altitude, speed, flight, hex, true_airspeed, heading, quality
        self.sort_reverse = True
        self.display_mode = 'standard'  # Options: standard, enhanced, compact
        self.show_data_quality = True
        self.filter_enhanced_only = False
        self.show_detailed_stats = False
        self.show_meshtastic_status = False
        
    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Set defaults if not present
                config.setdefault('dump1090_host', 'localhost')
                config.setdefault('dump1090_port', 40005)
                config.setdefault('receiver_control_port', 8081)
                config.setdefault('target_icao_codes', [])
                config.setdefault('frequency', 1090000000)
                config.setdefault('lna_gain', 40)
                config.setdefault('vga_gain', 20)
                config.setdefault('enable_hackrf_amp', True)
                config.setdefault('log_alerts', True)
                config.setdefault('alert_log_file', 'alerts.log')
                config.setdefault('alert_interval_sec', 300)
                config.setdefault('dump1090_path', '/usr/bin/dump1090-fa')
                config.setdefault('watchdog_timeout_sec', 60)
                config.setdefault('poll_interval_sec', 1)
                return config
        except FileNotFoundError:
            # Return default config if file not found
            return {
                'dump1090_host': 'localhost',
                'dump1090_port': 40005,
                'receiver_control_port': 8081,
                'target_icao_codes': [],
                'frequency': 1090000000,
                'lna_gain': 40,
                'vga_gain': 20,
                'enable_hackrf_amp': True,
                'log_alerts': True,
                'alert_log_file': 'alerts.log',
                'alert_interval_sec': 300,
                'dump1090_path': '/usr/bin/dump1090-fa',
                'watchdog_timeout_sec': 60,
                'poll_interval_sec': 1
            }
    
    def send_receiver_command(self, command: str, value: float = None) -> tuple[bool, str]:
        """Send command to ADS-B receiver for gain adjustment"""
        try:
            # Create a simple TCP connection to send commands
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((self.config['dump1090_host'], self.config['receiver_control_port']))
            
            if value is not None:
                message = f"{command}:{value}\n"
            else:
                message = f"{command}\n"
            
            sock.send(message.encode())
            response = sock.recv(1024).decode().strip()
            sock.close()
            
            return response == "OK", response
        except ConnectionRefusedError:
            self.log_error("connection_error", "Connection refused - is receiver running?", "receiver_control")
            return False, "Connection refused - is receiver running?"
        except socket.timeout:
            self.log_error("connection_error", "Connection timeout", "receiver_control")
            return False, "Connection timeout"
        except Exception as e:
            self.log_error("connection_error", f"Connection error: {str(e)}", "receiver_control")
            return False, f"Connection error: {str(e)}"
    
    def get_receiver_status(self) -> dict:
        """Get receiver status information"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            sock.connect((self.config['dump1090_host'], self.config['receiver_control_port']))
            
            sock.send(b"GET_STATUS\n")
            response = sock.recv(4096).decode().strip()
            sock.close()
            
            return json.loads(response)
        except Exception as e:
            return {"error": str(e)}
    
    def validate_setting(self, setting_name: str, value: str) -> tuple[bool, float, str]:
        """Validate a setting value and return (valid, parsed_value, error_message)"""
        try:
            parsed_value = float(value)
            setting = self.hackrf_settings.get(setting_name)
            
            if not setting:
                return False, 0, "Unknown setting"
            
            if parsed_value < setting['min'] or parsed_value > setting['max']:
                return False, 0, f"Value must be between {setting['min']} and {setting['max']} {setting['unit']}"
            
            # Additional validation for specific settings
            if setting_name == 'sample_rate' and parsed_value % 1000000 != 0:
                return False, 0, "Sample rate must be a multiple of 1MHz"
            
            return True, parsed_value, ""
        except ValueError:
            return False, 0, "Invalid number format"
    
    def test_connection(self) -> tuple[bool, str]:
        """Test connection to receiver"""
        success, message = self.send_receiver_command("PING")
        self.connection_status = "Connected" if success else f"Disconnected ({message})"
        return success, message
    
    def apply_setting(self, setting_name: str, value: float) -> tuple[bool, str]:
        """Apply a setting to the HackRF via dump1090 restart"""
        # For the new system, we need to restart dump1090 with new settings
        # This is a simplified approach - in practice, you might want to
        # implement dynamic parameter changes
        
        # Update local settings
        if setting_name in self.hackrf_settings:
            self.hackrf_settings[setting_name]['value'] = value
            
        # Send restart command to receiver
        success, message = self.send_receiver_command('RESTART_DUMP1090')
        if success:
            return True, "Settings updated - dump1090 restarted"
        return False, message
    
    def fetch_aircraft_data(self) -> Optional[dict]:
        """Fetch aircraft data from ADS-B receiver"""
        try:
            # The HTTP server is on port 8080, not the dump1090 port
            url = f"http://{self.config['dump1090_host']}:8080/data/aircraft.json"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            
            # Validate that we got actual aircraft data
            if data and 'aircraft' in data and isinstance(data['aircraft'], list):
                return data
            else:
                # Invalid data structure, don't update
                return None
                
        except requests.RequestException as e:
            self.stats['errors'] += 1
            self.log_error("api_error", f"Failed to fetch aircraft data: {str(e)}", "aircraft_api")
            return None
    
    def fetch_pymodes_stats(self) -> Optional[dict]:
        """Fetch pyModeS decoder statistics"""
        try:
            url = f"http://{self.config['dump1090_host']}:8080/api/stats"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            
            # Extract pyModeS-related stats from the general stats endpoint
            if data and isinstance(data, dict):
                return data
            return None
        except requests.RequestException as e:
            self.log_error("api_error", f"Failed to fetch pyModeS stats: {str(e)}", "pymodes_api")
            return None
    
    def fetch_source_stats(self) -> Optional[dict]:
        """Fetch message source statistics"""
        try:
            url = f"http://{self.config['dump1090_host']}:8080/api/sources"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, dict):
                return data
            return None
        except requests.RequestException as e:
            self.log_error("api_error", f"Failed to fetch source stats: {str(e)}", "source_api")
            return None
    
    def fetch_alert_status(self) -> Optional[dict]:
        """Fetch alert system status"""
        try:
            url = f"http://{self.config['dump1090_host']}:8080/api/status"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, dict):
                # Extract alert-related information from status
                return {
                    'watchlist_alerts_sent': data.get('statistics', {}).get('watchlist_alerts', 0),
                    'meshtastic_status': 'connected' if data.get('meshtastic_connected', False) else 'disconnected',
                    'alert_errors': 0  # Default value
                }
            return None
        except requests.RequestException as e:
            self.log_error("api_error", f"Failed to fetch alert status: {str(e)}", "alert_api")
            return None
    
    def fetch_meshtastic_status(self) -> Optional[dict]:
        """Fetch enhanced Meshtastic status and diagnostics"""
        try:
            url = f"http://{self.config['dump1090_host']}:8080/api/meshtastic/status"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            
            if data and isinstance(data, dict):
                return data
            return None
        except requests.RequestException as e:
            self.log_error("api_error", f"Failed to fetch Meshtastic status: {str(e)}", "meshtastic_api")
            return None
    
    def update_aircraft(self, aircraft_data: dict):
        """Update aircraft tracking data"""
        if not aircraft_data or 'aircraft' not in aircraft_data or not isinstance(aircraft_data['aircraft'], list):
            # Don't clear existing data if update fails - preserve what we have
            return
        
        current_time = datetime.now()
        current_aircraft = set()
        
        # Update basic stats safely
        prev_messages = self.stats.get('messages_total', 0)
        new_messages = aircraft_data.get('messages', 0)
        
        # Only update if we got valid data
        if isinstance(new_messages, (int, float)) and new_messages >= 0:
            self.stats['messages_total'] = int(new_messages)
        
        self.stats['last_update'] = current_time
        self.stats['update_count'] += 1
        
        # Calculate messages per second
        if prev_messages > 0:
            new_messages = self.stats['messages_total'] - prev_messages
            self.message_history.append((current_time, new_messages))
            # Keep only last 10 seconds of data
            cutoff = current_time - timedelta(seconds=10)
            self.message_history = [(t, m) for t, m in self.message_history if t > cutoff]
            
            if self.message_history:
                total_messages = sum(m for _, m in self.message_history)
                time_span = (self.message_history[-1][0] - self.message_history[0][0]).total_seconds()
                self.stats['messages_per_second'] = total_messages / max(time_span, 1)
        
        # Reset performance counters
        self.stats['aircraft_with_positions'] = 0
        self.stats['max_range_km'] = 0
        signal_strengths = []
        self.stats['strong_signals'] = 0
        self.stats['weak_signals'] = 0
        
        # Process each aircraft
        for ac_data in aircraft_data['aircraft']:
            hex_code = ac_data.get('hex', '').upper()
            if not hex_code:
                continue
                
            current_aircraft.add(hex_code)
            
            # Track aircraft with position data
            if ac_data.get('lat') is not None and ac_data.get('lon') is not None:
                self.stats['aircraft_with_positions'] += 1
                
                # Calculate approximate range (assuming receiver at 0,0 for demo)
                lat, lon = ac_data.get('lat', 0), ac_data.get('lon', 0)
                if lat != 0 and lon != 0:
                    # Simple distance calculation (not accurate but gives an idea)
                    range_km = ((lat**2 + lon**2) ** 0.5) * 111  # Rough km conversion
                    self.stats['max_range_km'] = max(self.stats['max_range_km'], range_km)
            
            # Track signal strength (RSSI if available)
            rssi = ac_data.get('rssi', ac_data.get('signal', None))
            if rssi is not None:
                signal_strengths.append(rssi)
                if rssi > -40:  # Strong signal
                    self.stats['strong_signals'] += 1
                elif rssi < -70:  # Weak signal
                    self.stats['weak_signals'] += 1
            
            if hex_code in self.aircraft:
                self.aircraft[hex_code].update(ac_data)
            else:
                self.aircraft[hex_code] = Aircraft(ac_data)
                self.stats['total_aircraft'] += 1
            
            # Set watchlist flag from receiver data
            if 'is_watchlist' in ac_data:
                self.aircraft[hex_code].is_watchlist = ac_data['is_watchlist']
        
        # Update average signal strength
        if signal_strengths:
            self.stats['avg_signal_strength'] = sum(signal_strengths) / len(signal_strengths)
        
        # Remove aircraft not seen for more than 5 minutes
        cutoff_time = current_time - timedelta(minutes=5)
        to_remove = [
            hex_code for hex_code, aircraft in self.aircraft.items()
            if aircraft.last_seen < cutoff_time
        ]
        
        for hex_code in to_remove:
            del self.aircraft[hex_code]
        
        # Update active count
        self.stats['active_aircraft'] = len(self.aircraft)
    
    def update_pymodes_stats(self, pymodes_data: dict):
        """Update pyModeS decoder statistics"""
        if not pymodes_data or not isinstance(pymodes_data, dict):
            return  # Don't update with invalid data
        
        # Only update fields that exist and are valid
        for key, value in pymodes_data.items():
            if key in self.pymodes_stats and value is not None:
                self.pymodes_stats[key] = value
        
        self.pymodes_stats['last_stats_update'] = datetime.now()
        
        # Calculate CPR success rate
        if self.pymodes_stats.get('position_calculations', 0) > 0:
            self.pymodes_stats['cpr_success_rate'] = (
                self.pymodes_stats.get('position_successes', 0) / 
                self.pymodes_stats['position_calculations']
            )
    
    def update_source_stats(self, source_data: dict):
        """Update message source statistics"""
        if not source_data or not isinstance(source_data, dict):
            return  # Don't update with invalid data
        
        # Track connection status changes
        old_connected = self.source_stats.get('sources_connected', 0)
        
        # Only update fields that exist and are valid
        for key, value in source_data.items():
            if key in self.source_stats and value is not None:
                self.source_stats[key] = value
        
        new_connected = self.source_stats.get('sources_connected', 0)
        
        if old_connected != new_connected:
            self.log_connection_change(old_connected, new_connected)
    
    def update_meshtastic_status(self, meshtastic_data: dict):
        """Update enhanced Meshtastic status"""
        if not meshtastic_data or not isinstance(meshtastic_data, dict):
            return  # Don't update with invalid data
        
        # Update all available fields
        for key, value in meshtastic_data.items():
            if key in self.meshtastic_status and value is not None:
                self.meshtastic_status[key] = value
        
        self.meshtastic_status['last_update'] = datetime.now()
        
        # Log significant status changes
        if 'initialized' in meshtastic_data:
            if meshtastic_data['initialized'] != self.meshtastic_status.get('initialized', False):
                status = "initialized" if meshtastic_data['initialized'] else "shutdown"
                self.log_error("meshtastic_status", f"Meshtastic {status}", "meshtastic")
        
        # Update interface connection counts
        if 'interfaces' in meshtastic_data:
            connected_interfaces = sum(1 for iface in meshtastic_data['interfaces'].values() 
                                     if iface.get('connection_status', {}).get('state') == 'connected')
            total_interfaces = len(meshtastic_data['interfaces'])
            
            # Log interface changes
            old_connected = len([iface for iface in self.meshtastic_status.get('interfaces', {}).values() 
                               if iface.get('connection_status', {}).get('state') == 'connected'])
            
            if connected_interfaces != old_connected:
                self.log_error("meshtastic_interfaces", 
                             f"Meshtastic interfaces: {connected_interfaces}/{total_interfaces} connected", 
                             "meshtastic")
    
    def log_error(self, error_type: str, message: str, source: str = "system"):
        """Log an error with timestamp"""
        error_entry = {
            'timestamp': datetime.now(),
            'type': error_type,
            'message': message,
            'source': source
        }
        
        self.error_log.append(error_entry)
        
        # Keep only recent errors
        if len(self.error_log) > self.max_error_log_size:
            self.error_log.pop(0)
    
    def log_connection_change(self, old_count: int, new_count: int):
        """Log connection status changes"""
        change_entry = {
            'timestamp': datetime.now(),
            'old_connected': old_count,
            'new_connected': new_count,
            'change_type': 'connected' if new_count > old_count else 'disconnected'
        }
        
        self.connection_history.append(change_entry)
        
        # Keep only recent changes
        if len(self.connection_history) > self.max_connection_history:
            self.connection_history.pop(0)
    
    def get_system_health_status(self) -> dict:
        """Get comprehensive system health status"""
        now = datetime.now()
        
        # Check for recent errors
        recent_errors = [e for e in self.error_log if (now - e['timestamp']).total_seconds() < 300]  # Last 5 minutes
        
        # Check connection stability
        recent_disconnections = [c for c in self.connection_history 
                               if c['change_type'] == 'disconnected' and 
                               (now - c['timestamp']).total_seconds() < 600]  # Last 10 minutes
        
        # Determine overall health
        health_score = 100
        health_issues = []
        
        if len(recent_errors) > 10:
            health_score -= 30
            health_issues.append(f"High error rate: {len(recent_errors)} errors in 5 min")
        
        if len(recent_disconnections) > 3:
            health_score -= 25
            health_issues.append(f"Connection instability: {len(recent_disconnections)} disconnections")
        
        if self.source_stats['sources_connected'] == 0:
            health_score -= 50
            health_issues.append("No message sources connected")
        
        if self.stats['errors'] > 0 and self.stats['update_count'] > 0:
            error_rate = self.stats['errors'] / self.stats['update_count']
            if error_rate > 0.1:  # More than 10% error rate
                health_score -= 20
                health_issues.append(f"High system error rate: {error_rate:.1%}")
        
        # Determine status
        if health_score >= 90:
            status = "excellent"
        elif health_score >= 70:
            status = "good"
        elif health_score >= 50:
            status = "fair"
        elif health_score >= 30:
            status = "poor"
        else:
            status = "critical"
        
        return {
            'health_score': health_score,
            'status': status,
            'issues': health_issues,
            'recent_errors': len(recent_errors),
            'recent_disconnections': len(recent_disconnections)
        }
    
    def get_sorted_aircraft(self) -> List[Aircraft]:
        """Get aircraft list sorted by current criteria"""
        aircraft_list = list(self.aircraft.values())
        
        # Apply enhanced data filter if enabled
        if self.filter_enhanced_only:
            aircraft_list = [a for a in aircraft_list if a.enhanced_data_available]
        
        if self.sort_by == 'last_seen':
            aircraft_list.sort(key=lambda a: a.last_seen, reverse=self.sort_reverse)
        elif self.sort_by == 'altitude':
            aircraft_list.sort(key=lambda a: a.altitude if isinstance(a.altitude, (int, float)) else -1, reverse=self.sort_reverse)
        elif self.sort_by == 'speed':
            aircraft_list.sort(key=lambda a: a.speed if isinstance(a.speed, (int, float)) else -1, reverse=self.sort_reverse)
        elif self.sort_by == 'flight':
            aircraft_list.sort(key=lambda a: a.flight, reverse=self.sort_reverse)
        elif self.sort_by == 'hex':
            aircraft_list.sort(key=lambda a: a.hex, reverse=self.sort_reverse)
        elif self.sort_by == 'true_airspeed':
            aircraft_list.sort(key=lambda a: a.true_airspeed if isinstance(a.true_airspeed, (int, float)) else -1, reverse=self.sort_reverse)
        elif self.sort_by == 'heading':
            aircraft_list.sort(key=lambda a: a.magnetic_heading if isinstance(a.magnetic_heading, (int, float)) else -1, reverse=self.sort_reverse)
        elif self.sort_by == 'quality':
            # Sort by data quality score (position + velocity + altitude + enhanced data)
            def quality_score(aircraft):
                score = 0
                if aircraft.has_position: score += 3
                if aircraft.has_velocity: score += 2
                if aircraft.has_altitude: score += 1
                if aircraft.enhanced_data_available: score += 2
                return score
            aircraft_list.sort(key=quality_score, reverse=self.sort_reverse)
        
        return aircraft_list
    
    def draw_menu(self, stdscr, width: int):
        """Draw the configuration menu"""
        menu_y = 1
        
        # Menu title
        menu_title = "⚙️  HACKRF CONFIGURATION MENU  ⚙️"
        stdscr.addstr(menu_y, max(0, (width - len(menu_title)) // 2), menu_title, curses.A_BOLD | curses.color_pair(1))
        menu_y += 2
        
        # Current settings display
        settings_line = f"RF: {self.hackrf_settings['rf_gain']['value']}dB | IF: {self.hackrf_settings['if_gain']['value']}dB | BB: {self.hackrf_settings['bb_gain']['value']}dB | Rate: {self.hackrf_settings['sample_rate']['value']/1e6:.1f}MHz | Freq: {self.hackrf_settings['center_freq']['value']/1e6:.1f}MHz"
        stdscr.addstr(menu_y, 0, settings_line[:width-1], curses.color_pair(4))
        menu_y += 1
        
        # Connection status
        status_color = curses.color_pair(3) if "Connected" in self.connection_status else curses.color_pair(2)
        status_line = f"Receiver Status: {self.connection_status}"
        stdscr.addstr(menu_y, 0, status_line[:width-1], status_color)
        menu_y += 2
        
        # Menu items
        for i, item in enumerate(self.menu_items):
            if i == self.menu_selected:
                attr = curses.A_REVERSE | curses.A_BOLD
            else:
                attr = curses.A_NORMAL
            
            # Add current value for settings
            if item == 'RF Gain':
                display_text = f"RF Gain: {self.hackrf_settings['rf_gain']['value']}dB (0-47dB)"
            elif item == 'IF Gain':
                display_text = f"IF Gain: {self.hackrf_settings['if_gain']['value']}dB (0-47dB)"
            elif item == 'BB Gain':
                display_text = f"BB Gain: {self.hackrf_settings['bb_gain']['value']}dB (0-62dB)"
            elif item == 'Sample Rate':
                display_text = f"Sample Rate: {self.hackrf_settings['sample_rate']['value']/1e6:.1f}MHz (1-20MHz)"
            elif item == 'Center Freq':
                display_text = f"Center Freq: {self.hackrf_settings['center_freq']['value']/1e6:.1f}MHz (1000-1200MHz)"
            elif item == 'Test Connection':
                display_text = f"Test Connection (Status: {self.connection_status})"
            else:
                display_text = item
            
            stdscr.addstr(menu_y + i, 2, f"[{chr(65+i)}] {display_text}", attr)
        
        menu_y += len(self.menu_items) + 1
        
        # Instructions
        if self.input_mode:
            stdscr.addstr(menu_y, 0, f"{self.input_prompt}: {self.input_buffer}_", curses.color_pair(3))
            stdscr.addstr(menu_y + 1, 0, "Enter new value (ESC to cancel, ENTER to apply)", curses.A_DIM)
        else:
            stdscr.addstr(menu_y, 0, "Use ↑↓ arrows to navigate, ENTER to select, ESC to exit menu", curses.A_DIM)
        
        return menu_y + 3
    
    def draw_header(self, stdscr, height: int, width: int):
        """Draw dashboard header"""
        if self.menu_active:
            return self.draw_menu(stdscr, width)
        
        title = "🛩️  URSINE EXPLORER - ADS-B LIVE DASHBOARD  🛩️"
        stdscr.addstr(0, max(0, (width - len(title)) // 2), title, curses.A_BOLD | curses.color_pair(1))
        
        # HackRF settings line
        hackrf_line = f"HackRF: RF={self.hackrf_settings['rf_gain']['value']}dB IF={self.hackrf_settings['if_gain']['value']}dB BB={self.hackrf_settings['bb_gain']['value']}dB | {self.hackrf_settings['sample_rate']['value']/1e6:.1f}MHz @ {self.hackrf_settings['center_freq']['value']/1e6:.1f}MHz"
        stdscr.addstr(1, 0, hackrf_line[:width-1], curses.color_pair(5))
        
        # Aircraft stats line with enhanced data metrics
        enhanced_count = sum(1 for a in self.aircraft.values() if a.enhanced_data_available)
        high_quality_count = sum(1 for a in self.aircraft.values() if self._calculate_quality_score(a) >= 3)
        
        stats_line = f"Active: {self.stats['active_aircraft']} | Enhanced: {enhanced_count} | High Quality: {high_quality_count} | With Position: {self.stats['aircraft_with_positions']} | Max Range: {self.stats['max_range_km']:.1f}km"
        stdscr.addstr(2, 0, stats_line[:width-1])
        
        # Radio performance line
        perf_line = f"Messages: {self.stats['messages_total']} | Rate: {self.stats['messages_per_second']:.1f}/sec | Avg Signal: {self.stats['avg_signal_strength']:.1f}dBm | Strong: {self.stats['strong_signals']} | Weak: {self.stats['weak_signals']}"
        stdscr.addstr(3, 0, perf_line[:width-1], curses.color_pair(4))
        
        # pyModeS decoder performance line
        pymodes_line = f"pyModeS: Processed: {self.pymodes_stats['messages_processed']} | Decoded: {self.pymodes_stats['messages_decoded']} | Success: {self.pymodes_stats['decode_rate']:.1%} | CPR Success: {self.pymodes_stats['cpr_success_rate']:.1%}"
        stdscr.addstr(4, 0, pymodes_line[:width-1], curses.color_pair(1))
        
        # Message sources status line
        sources_line = f"Sources: {self.source_stats['sources_connected']}/{self.source_stats['sources_total']} | Health: {self.source_stats['health_status']} | Duplicates: {self.source_stats['duplicate_messages']} | Source Rate: {self.source_stats['messages_per_second']:.1f}/sec"
        stdscr.addstr(5, 0, sources_line[:width-1], curses.color_pair(5))
        
        # System status line with health indicator
        try:
            health_status = self.get_system_health_status()
            health_icons = {
                'excellent': '💚', 'good': '💛', 'fair': '🟠', 'poor': '🔴', 'critical': '💀'
            }
            health_icon = health_icons.get(health_status.get('status', 'unknown'), '❓')
            
            status_line = f"Updates: {self.stats.get('update_count', 0)} | Errors: {self.stats.get('errors', 0)} | Health: {health_icon}"
            
            if self.stats.get('last_update'):
                try:
                    age = int((datetime.now() - self.stats['last_update']).total_seconds())
                    status_line += f" | Last Update: {age}s ago"
                    if age > 5:
                        status_line += " ⚠️"
                except:
                    status_line += " | Last Update: Unknown"
            else:
                status_line += " | Waiting for data... 🔄"
            
            # Add receiver status if available (but don't let it block the display)
            try:
                receiver_status = self.get_receiver_status()
                if isinstance(receiver_status, dict):
                    if 'dump1090_running' in receiver_status:
                        status_line += f" | dump1090: {'✅' if receiver_status['dump1090_running'] else '❌'}"
                    if 'meshtastic_connected' in receiver_status:
                        status_line += f" | Meshtastic: {'✅' if receiver_status['meshtastic_connected'] else '❌'}"
            except:
                # Don't add receiver status if there's an error
                pass
        except Exception:
            # Fallback status line if health calculation fails
            status_line = f"Updates: {self.stats.get('update_count', 0)} | Errors: {self.stats.get('errors', 0)} | Status: Unknown"
        
        # Color code the status line based on health
        status_color = curses.A_NORMAL
        if health_status['status'] in ['poor', 'critical']:
            status_color = curses.color_pair(2)  # Red
        elif health_status['status'] == 'fair':
            status_color = curses.color_pair(4)  # Yellow
        
        stdscr.addstr(6, 0, status_line[:width-1], status_color)
        
        # Target aircraft line (optional - only show if targets are configured)
        header_y = 8
        if self.config['target_icao_codes']:
            target_line = f"🎯 Targets: {', '.join(self.config['target_icao_codes'])} (highlighted in green)"
            stdscr.addstr(7, 0, target_line[:width-1], curses.color_pair(2))
            header_y = 9
        
        # Column headers based on display mode
        if self.display_mode == 'enhanced':
            header = f"{'🎯':<2} {'ICAO':<8} {'CALLSIGN':<10} {'ALT':<8} {'TAS':<6} {'IAS':<6} {'HDG':<4} {'V/R':<5} {'Q':<2} {'AGE':<4}"
        elif self.display_mode == 'compact':
            header = f"{'🎯':<2} {'ICAO':<8} {'CALL':<8} {'ALT':<6} {'SPD':<5} {'TRK':<4} {'Q':<2} {'AGE':<4}"
        else:  # standard
            header = f"{'🎯':<2} {'ICAO':<8} {'CALLSIGN':<10} {'ALT':<8} {'SPD':<6} {'TRK':<4} {'AGE':<5} {'DUR':<5} {'MSGS':<6}"
        
        # Add sort indicator
        sort_indicators = {
            'last_seen': '⏰', 'altitude': '📏', 'speed': '💨', 'flight': '✈️', 
            'hex': '🔢', 'true_airspeed': '🚀', 'heading': '🧭', 'quality': '⭐'
        }
        sort_indicator = sort_indicators.get(self.sort_by, '📊')
        direction = '↓' if self.sort_reverse else '↑'
        
        header_with_sort = f"{header} | Sort: {sort_indicator}{direction}"
        if self.filter_enhanced_only:
            header_with_sort += " | Enhanced Only"
        
        stdscr.addstr(header_y, 0, header_with_sort[:width-1], curses.A_BOLD)
        
        return header_y + 1
    
    def draw_aircraft_list(self, stdscr, start_y: int, height: int, width: int):
        """Draw the aircraft list"""
        try:
            aircraft_list = self.get_sorted_aircraft()
            max_rows = height - start_y - 2
            
            # Ensure we don't try to draw beyond screen bounds
            if start_y >= height - 1 or max_rows <= 0:
                return
            
            for i, aircraft in enumerate(aircraft_list[:max_rows]):
                y = start_y + i
                if y >= height - 1:
                    break
                
                try:
                    # Add watchlist indicator
                    watchlist_indicator = "🎯" if getattr(aircraft, 'is_watchlist', False) else "  "
                    
                    # Format line based on display mode
                    if self.display_mode == 'enhanced':
                        line = self._format_enhanced_line(aircraft, watchlist_indicator)
                    elif self.display_mode == 'compact':
                        line = self._format_compact_line(aircraft, watchlist_indicator)
                    else:  # standard
                        line = self._format_standard_line(aircraft, watchlist_indicator)
                    
                    # Choose color based on aircraft properties
                    color_attr = self._get_aircraft_color(aircraft)
                    
                    # Ensure line fits within screen width
                    safe_line = line[:width-1] if len(line) >= width else line
                    stdscr.addstr(y, 0, safe_line, color_attr)
                    
                except (curses.error, ValueError):
                    # Skip this line if there's a drawing error
                    continue
                    
        except Exception:
            # If aircraft list drawing fails completely, just skip it
            pass
    
    def _format_standard_line(self, aircraft, watchlist_indicator):
        """Format aircraft line in standard mode"""
        alt_str = f"{int(aircraft.altitude)}" if isinstance(aircraft.altitude, (int, float)) else "---"
        spd_str = f"{int(aircraft.speed)}" if isinstance(aircraft.speed, (int, float)) else "---"
        trk_str = f"{int(aircraft.track)}" if isinstance(aircraft.track, (int, float)) else "---"
        age_str = f"{aircraft.age_seconds()}s"
        dur_str = f"{aircraft.duration_seconds()}s"
        msg_str = f"{aircraft.messages}" if isinstance(aircraft.messages, int) else "---"
        
        return f"{watchlist_indicator} {aircraft.hex:<8} {aircraft.flight:<10} {alt_str:<8} {spd_str:<6} {trk_str:<4} {age_str:<5} {dur_str:<5} {msg_str:<6}"
    
    def _format_enhanced_line(self, aircraft, watchlist_indicator):
        """Format aircraft line in enhanced mode showing pyModeS data"""
        alt_str = f"{int(aircraft.altitude)}" if isinstance(aircraft.altitude, (int, float)) else "---"
        tas_str = f"{int(aircraft.true_airspeed)}" if isinstance(aircraft.true_airspeed, (int, float)) else "---"
        ias_str = f"{int(aircraft.indicated_airspeed)}" if isinstance(aircraft.indicated_airspeed, (int, float)) else "---"
        hdg_str = f"{int(aircraft.magnetic_heading)}" if isinstance(aircraft.magnetic_heading, (int, float)) else "---"
        vr_str = f"{int(aircraft.vertical_rate)}" if isinstance(aircraft.vertical_rate, (int, float)) else "---"
        age_str = f"{aircraft.age_seconds()}s"
        
        # Data quality indicator
        quality_score = self._calculate_quality_score(aircraft)
        quality_str = "⭐" * quality_score if quality_score > 0 else "❌"
        
        return f"{watchlist_indicator} {aircraft.hex:<8} {aircraft.flight:<10} {alt_str:<8} {tas_str:<6} {ias_str:<6} {hdg_str:<4} {vr_str:<5} {quality_str:<2} {age_str:<4}"
    
    def _format_compact_line(self, aircraft, watchlist_indicator):
        """Format aircraft line in compact mode"""
        alt_str = f"{int(aircraft.altitude)}" if isinstance(aircraft.altitude, (int, float)) else "---"
        spd_str = f"{int(aircraft.speed)}" if isinstance(aircraft.speed, (int, float)) else "---"
        trk_str = f"{int(aircraft.track)}" if isinstance(aircraft.track, (int, float)) else "---"
        age_str = f"{aircraft.age_seconds()}s"
        
        # Shortened callsign
        call_str = aircraft.flight[:8] if aircraft.flight != 'Unknown' else aircraft.flight
        
        # Data quality indicator
        quality_score = self._calculate_quality_score(aircraft)
        quality_str = "⭐" * min(quality_score, 3) if quality_score > 0 else "❌"
        
        return f"{watchlist_indicator} {aircraft.hex:<8} {call_str:<8} {alt_str:<6} {spd_str:<5} {trk_str:<4} {quality_str:<2} {age_str:<4}"
    
    def _calculate_quality_score(self, aircraft):
        """Calculate data quality score for aircraft"""
        score = 0
        if aircraft.has_position: score += 1
        if aircraft.has_velocity: score += 1
        if aircraft.has_altitude: score += 1
        if aircraft.enhanced_data_available: score += 2
        return min(score, 5)
    
    def _get_aircraft_color(self, aircraft):
        """Get color attributes for aircraft display"""
        # Watchlist aircraft in green
        if getattr(aircraft, 'is_watchlist', False):
            return curses.A_BOLD | curses.color_pair(3)
        
        # Enhanced data aircraft in cyan
        elif aircraft.enhanced_data_available:
            return curses.color_pair(1)
        
        # High quality data in white/bold
        elif self._calculate_quality_score(aircraft) >= 3:
            return curses.A_BOLD
        
        # Low quality data dimmed
        elif self._calculate_quality_score(aircraft) <= 1:
            return curses.A_DIM
        
        # Default
        else:
            return curses.A_NORMAL
    
    def read_fft_data(self):
        """Read FFT data for waterfall display"""
        try:
            # First try to get FFT data from the API
            url = f"http://{self.config['dump1090_host']}:8080/data/fft.json"
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                fft_data = response.json()
                if 'fft_data' in fft_data and fft_data['fft_data']:
                    return np.array(fft_data['fft_data'])
        except:
            pass
        
        # Fallback to file-based FFT data
        try:
            if not os.path.exists(self.fft_file):
                return None
            
            file_size = os.path.getsize(self.fft_file)
            if file_size < self.fft_size * 4:
                return None
            
            with open(self.fft_file, 'rb') as f:
                f.seek(-self.fft_size * 4, 2)
                data = np.frombuffer(f.read(self.fft_size * 4), dtype=np.float32)
                
                if len(data) == self.fft_size:
                    # Convert to dB and shift
                    data = np.maximum(data, 1e-12)
                    db_data = 10 * np.log10(data)
                    return np.fft.fftshift(db_data)
        except:
            pass
        return None
    
    def draw_mini_waterfall(self, stdscr, start_y: int, height: int, width: int):
        """Draw a mini waterfall display"""
        if not self.show_waterfall:
            return start_y
        
        # Read latest FFT data
        fft_data = self.read_fft_data()
        if fft_data is not None:
            self.waterfall_data.append(fft_data)
            # Keep only last 10 lines
            if len(self.waterfall_data) > 10:
                self.waterfall_data.pop(0)
        
        # Draw waterfall title
        stdscr.addstr(start_y, 0, "Mini Waterfall (1090 MHz ±1 MHz):", curses.A_BOLD)
        start_y += 1
        
        if not self.waterfall_data:
            stdscr.addstr(start_y, 0, "FFT data not available - waterfall requires dump1090 with --write-json option", curses.A_DIM)
            stdscr.addstr(start_y + 1, 0, "Start dump1090 with: --write-json /tmp/adsb_json --write-json-every 1", curses.A_DIM)
            stdscr.addstr(start_y + 2, 0, "Press 'w' to disable waterfall display.", curses.A_DIM)
            return start_y + 4
        
        # Focus on ADS-B frequency range
        center_bin = len(self.waterfall_data[0]) // 2
        bins_around_center = min(width - 5, 100)  # Show ~100 bins around center
        start_bin = center_bin - bins_around_center // 2
        end_bin = center_bin + bins_around_center // 2
        
        intensity_chars = " .:-=+*#%@"
        
        # Draw recent waterfall lines
        for i, line_data in enumerate(self.waterfall_data[-8:]):  # Last 8 lines
            if start_y + i >= height - 2:
                break
            
            line_chars = ""
            for bin_idx in range(start_bin, min(end_bin, len(line_data))):
                # Normalize to character range
                db_val = line_data[bin_idx]
                normalized = (db_val + 80) / 60  # Assume -80 to -20 dB range
                normalized = max(0, min(1, normalized))
                char_idx = int(normalized * (len(intensity_chars) - 1))
                line_chars += intensity_chars[char_idx]
            
            stdscr.addstr(start_y + i, 0, line_chars[:width-1])
        
        return start_y + min(8, len(self.waterfall_data)) + 1
    
    def draw_detailed_stats(self, stdscr, start_y: int, height: int, width: int):
        """Draw detailed pyModeS and source statistics"""
        if not self.show_detailed_stats:
            return start_y
        
        # pyModeS detailed statistics
        stdscr.addstr(start_y, 0, "📊 pyModeS Decoder Statistics:", curses.A_BOLD | curses.color_pair(1))
        start_y += 1
        
        pymodes_details = [
            f"  Messages Processed: {self.pymodes_stats['messages_processed']}",
            f"  Successfully Decoded: {self.pymodes_stats['messages_decoded']} ({self.pymodes_stats['decode_rate']:.1%})",
            f"  Failed Decodes: {self.pymodes_stats['messages_failed']} ({self.pymodes_stats['error_rate']:.1%})",
            f"  Aircraft Tracked: {self.pymodes_stats['aircraft_count']}",
            f"  Position Calculations: {self.pymodes_stats['position_calculations']}",
            f"  CPR Success Rate: {self.pymodes_stats['cpr_success_rate']:.1%}"
        ]
        
        for i, line in enumerate(pymodes_details):
            if start_y + i >= height - 3:
                break
            stdscr.addstr(start_y + i, 0, line[:width-1])
        
        start_y += len(pymodes_details) + 1
        
        # Message sources detailed statistics
        if start_y < height - 5:
            stdscr.addstr(start_y, 0, "📡 Message Sources:", curses.A_BOLD | curses.color_pair(5))
            start_y += 1
            
            for i, source in enumerate(self.source_stats.get('sources', [])):
                if start_y >= height - 3:
                    break
                
                status_icon = "✅" if source.get('connected', False) else "❌"
                source_line = f"  {status_icon} {source.get('name', 'Unknown')}: {source.get('message_count', 0)} msgs, {source.get('error_count', 0)} errors"
                stdscr.addstr(start_y, 0, source_line[:width-1])
                start_y += 1
        
        return start_y
    
    def draw_error_diagnostics(self, stdscr, start_y: int, height: int, width: int):
        """Draw error and diagnostic information"""
        if not self.show_detailed_stats:
            return start_y
        
        # System health overview
        health_status = self.get_system_health_status()
        
        # Health status header with color coding
        health_color = curses.color_pair(3)  # Green for good
        if health_status['status'] in ['poor', 'critical']:
            health_color = curses.color_pair(2)  # Red for bad
        elif health_status['status'] == 'fair':
            health_color = curses.color_pair(4)  # Yellow for fair
        
        health_line = f"🏥 System Health: {health_status['status'].upper()} ({health_status['health_score']}/100)"
        stdscr.addstr(start_y, 0, health_line[:width-1], curses.A_BOLD | health_color)
        start_y += 1
        
        # Health issues
        if health_status['issues']:
            for issue in health_status['issues'][:3]:  # Show max 3 issues
                if start_y >= height - 3:
                    break
                stdscr.addstr(start_y, 0, f"  ⚠️ {issue}"[:width-1], curses.color_pair(2))
                start_y += 1
        
        start_y += 1
        
        # Recent errors
        if self.error_log and start_y < height - 5:
            stdscr.addstr(start_y, 0, "🚨 Recent Errors:", curses.A_BOLD | curses.color_pair(2))
            start_y += 1
            
            recent_errors = self.error_log[-5:]  # Show last 5 errors
            for error in recent_errors:
                if start_y >= height - 3:
                    break
                
                time_str = error['timestamp'].strftime("%H:%M:%S")
                error_line = f"  {time_str} [{error['source']}] {error['type']}: {error['message']}"
                stdscr.addstr(start_y, 0, error_line[:width-1], curses.A_DIM)
                start_y += 1
        
        start_y += 1
        
        # Alert system status
        if start_y < height - 4:
            stdscr.addstr(start_y, 0, "📢 Alert System:", curses.A_BOLD | curses.color_pair(4))
            start_y += 1
            
            alert_lines = [
                f"  Alerts Sent: {self.alert_status['watchlist_alerts_sent']}",
                f"  Alert Errors: {self.alert_status['alert_errors']}",
                f"  Meshtastic: {self.alert_status['meshtastic_status']}"
            ]
            
            if self.alert_status['last_alert_time']:
                last_alert = datetime.fromisoformat(self.alert_status['last_alert_time']) if isinstance(self.alert_status['last_alert_time'], str) else self.alert_status['last_alert_time']
                time_since = (datetime.now() - last_alert).total_seconds()
                alert_lines.append(f"  Last Alert: {int(time_since)}s ago")
            
            for line in alert_lines:
                if start_y >= height - 3:
                    break
                stdscr.addstr(start_y, 0, line[:width-1])
                start_y += 1
        
        return start_y
    
    def draw_meshtastic_status(self, stdscr, start_y: int, height: int, width: int):
        """Draw enhanced Meshtastic status display"""
        if start_y >= height - 3:
            return start_y
        
        # Meshtastic status header
        meshtastic_title = "📡 Enhanced Meshtastic Status:"
        status_color = curses.A_BOLD | curses.color_pair(1)
        
        # Color code based on initialization status
        if self.meshtastic_status.get('initialized', False):
            health_score = self.meshtastic_status.get('health_score', 0)
            if health_score >= 80:
                status_color = curses.A_BOLD | curses.color_pair(3)  # Green for healthy
            elif health_score >= 50:
                status_color = curses.A_BOLD | curses.color_pair(4)  # Yellow for fair
            else:
                status_color = curses.A_BOLD | curses.color_pair(2)  # Red for poor
        else:
            status_color = curses.A_BOLD | curses.A_DIM  # Dimmed for not initialized
        
        stdscr.addstr(start_y, 0, meshtastic_title, status_color)
        start_y += 1
        
        # Connection mode and initialization status
        init_status = "✅ Initialized" if self.meshtastic_status.get('initialized', False) else "❌ Not Initialized"
        connection_mode = self.meshtastic_status.get('connection_mode', 'unknown').title()
        health_score = self.meshtastic_status.get('health_score', 0)
        
        status_line = f"  Status: {init_status} | Mode: {connection_mode} | Health: {health_score}%"
        stdscr.addstr(start_y, 0, status_line[:width-1])
        start_y += 1
        
        # Interface status
        interfaces = self.meshtastic_status.get('interfaces', {})
        if interfaces:
            connected_count = sum(1 for iface in interfaces.values() 
                                if iface.get('connection_status', {}).get('state') == 'connected')
            total_count = len(interfaces)
            
            interface_line = f"  Interfaces: {connected_count}/{total_count} connected"
            
            # Add interface details
            interface_details = []
            for iface_name, iface_data in interfaces.items():
                conn_status = iface_data.get('connection_status', {})
                state = conn_status.get('state', 'unknown')
                
                if state == 'connected':
                    icon = "✅"
                elif state == 'connecting':
                    icon = "🔄"
                else:
                    icon = "❌"
                
                interface_details.append(f"{icon}{iface_name}")
            
            if interface_details:
                interface_line += f" ({', '.join(interface_details)})"
            
            stdscr.addstr(start_y, 0, interface_line[:width-1])
            start_y += 1
        
        # Active channels
        channels = self.meshtastic_status.get('active_channels', [])
        if channels:
            channel_names = [ch.get('name', 'Unknown') for ch in channels if isinstance(ch, dict)]
            encrypted_count = sum(1 for ch in channels if isinstance(ch, dict) and ch.get('is_encrypted', False))
            
            channel_line = f"  Channels: {len(channels)} active"
            if encrypted_count > 0:
                channel_line += f" ({encrypted_count} encrypted)"
            
            if channel_names:
                channel_line += f" - {', '.join(channel_names[:3])}"  # Show first 3 channels
                if len(channel_names) > 3:
                    channel_line += f" +{len(channel_names) - 3} more"
            
            stdscr.addstr(start_y, 0, channel_line[:width-1])
            start_y += 1
        
        # Message statistics
        msg_stats = self.meshtastic_status.get('message_stats', {})
        if msg_stats:
            messages_sent = msg_stats.get('messages_sent', 0)
            messages_failed = msg_stats.get('messages_failed', 0)
            success_rate = msg_stats.get('success_rate', 0.0)
            
            msg_line = f"  Messages: {messages_sent} sent, {messages_failed} failed"
            if messages_sent > 0:
                msg_line += f" (Success: {success_rate:.1%})"
            
            stdscr.addstr(start_y, 0, msg_line[:width-1])
            start_y += 1
        
        # Device information
        device_info = self.meshtastic_status.get('device_info', {})
        if device_info:
            device_details = []
            
            # Serial device info
            if 'serial' in device_info:
                serial_info = device_info['serial']
                node_id = serial_info.get('node_id', 'Unknown')
                firmware = serial_info.get('firmware_version', 'Unknown')
                device_details.append(f"Serial: {node_id} (FW: {firmware})")
            
            # MQTT broker info
            if 'mqtt' in device_info:
                mqtt_info = device_info['mqtt']
                broker = mqtt_info.get('broker', 'Unknown')
                device_details.append(f"MQTT: {broker}")
            
            if device_details:
                device_line = f"  Devices: {' | '.join(device_details)}"
                stdscr.addstr(start_y, 0, device_line[:width-1])
                start_y += 1
        
        # MQTT broker status
        mqtt_broker = self.meshtastic_status.get('mqtt_broker', 'unknown')
        if mqtt_broker != 'unknown':
            mqtt_line = f"  MQTT Broker: {mqtt_broker}"
            stdscr.addstr(start_y, 0, mqtt_line[:width-1])
            start_y += 1
        
        # Last update time
        last_update = self.meshtastic_status.get('last_update')
        if last_update:
            age = int((datetime.now() - last_update).total_seconds())
            update_line = f"  Last Update: {age}s ago"
            if age > 30:
                update_line += " ⚠️"
            stdscr.addstr(start_y, 0, update_line[:width-1])
            start_y += 1
        
        # Diagnostics summary
        diagnostics = self.meshtastic_status.get('diagnostics', {})
        if diagnostics:
            config_issues = diagnostics.get('configuration_issues', 0)
            interface_tests = diagnostics.get('interface_tests_passed', 0)
            total_tests = diagnostics.get('total_interface_tests', 0)
            
            diag_line = f"  Diagnostics: {config_issues} config issues"
            if total_tests > 0:
                diag_line += f", {interface_tests}/{total_tests} tests passed"
            
            stdscr.addstr(start_y, 0, diag_line[:width-1])
            start_y += 1
        
        return start_y + 1
    
    def draw_footer(self, stdscr, height: int, width: int):
        """Draw dashboard footer with controls"""
        footer_y = height - 1
        if self.menu_active:
            controls = "Menu Mode: ↑↓=navigate | ENTER=select | ESC=exit | Type values and press ENTER"
        else:
            waterfall_status = "ON" if self.show_waterfall else "OFF"
            enhanced_filter = "ON" if self.filter_enhanced_only else "OFF"
            stats_status = "ON" if self.show_detailed_stats else "OFF"
            meshtastic_status = "ON" if self.show_meshtastic_status else "OFF"
            controls = f"Controls: q=quit | m=menu | w=waterfall({waterfall_status}) | t=stats({stats_status}) | n=meshtastic({meshtastic_status}) | s=sort({self.sort_by}) | r=reverse | d=display({self.display_mode}) | e=enhanced({enhanced_filter}) | c=clear_errors | Space=refresh"
        stdscr.addstr(footer_y, 0, controls[:width-1], curses.A_DIM)
    
    def handle_menu_input(self, key):
        """Handle menu-specific input"""
        if self.input_mode:
            # Handle input mode
            if key == 27:  # ESC
                self.input_mode = False
                self.input_buffer = ""
                self.input_prompt = ""
            elif key == 10 or key == 13:  # ENTER
                # Apply the setting
                setting_map = {
                    0: 'rf_gain',
                    1: 'if_gain', 
                    2: 'bb_gain',
                    3: 'sample_rate',
                    4: 'center_freq'
                }
                
                setting_name = setting_map.get(self.menu_selected)
                if setting_name:
                    valid, value, error = self.validate_setting(setting_name, self.input_buffer)
                    if valid:
                        success, message = self.apply_setting(setting_name, value)
                        if success:
                            # Success - exit input mode
                            self.input_mode = False
                            self.input_buffer = ""
                            self.input_prompt = ""
                        else:
                            # Failed to apply - show detailed error
                            self.input_prompt = f"Failed: {message}"
                    else:
                        # Validation error
                        self.input_prompt = f"Error: {error}"
                
            elif key == 127 or key == 8:  # BACKSPACE
                if self.input_buffer:
                    self.input_buffer = self.input_buffer[:-1]
            elif 32 <= key <= 126:  # Printable characters
                self.input_buffer += chr(key)
        else:
            # Handle menu navigation
            if key == curses.KEY_UP:
                self.menu_selected = (self.menu_selected - 1) % len(self.menu_items)
            elif key == curses.KEY_DOWN:
                self.menu_selected = (self.menu_selected + 1) % len(self.menu_items)
            elif key == 10 or key == 13:  # ENTER
                if self.menu_selected == len(self.menu_items) - 1:  # Exit Menu
                    self.menu_active = False
                elif self.menu_selected == len(self.menu_items) - 2:  # Test Connection
                    success, message = self.test_connection()
                    self.input_prompt = f"Connection test: {message}"
                elif self.menu_selected < len(self.menu_items) - 2:
                    # Start input for selected setting
                    setting_names = ['RF Gain', 'IF Gain', 'BB Gain', 'Sample Rate', 'Center Freq']
                    self.input_mode = True
                    self.input_buffer = ""
                    self.input_prompt = f"Enter new {setting_names[self.menu_selected]}"
            elif key == 27:  # ESC
                self.menu_active = False
    
    def handle_input(self, stdscr):
        """Handle keyboard input"""
        stdscr.nodelay(True)  # Non-blocking input
        
        while self.running:
            try:
                key = stdscr.getch()
                
                if self.menu_active:
                    self.handle_menu_input(key)
                else:
                    # Normal dashboard controls
                    if key == ord('q') or key == ord('Q'):
                        self.running = False
                    elif key == ord('m') or key == ord('M'):
                        self.menu_active = True
                        self.menu_selected = 0
                    elif key == ord('s') or key == ord('S'):
                        # Cycle through sort options
                        sort_options = ['last_seen', 'altitude', 'speed', 'flight', 'hex', 'true_airspeed', 'heading', 'quality']
                        current_idx = sort_options.index(self.sort_by)
                        self.sort_by = sort_options[(current_idx + 1) % len(sort_options)]
                    elif key == ord('r') or key == ord('R'):
                        self.sort_reverse = not self.sort_reverse
                    elif key == ord('w') or key == ord('W'):
                        self.show_waterfall = not self.show_waterfall
                    elif key == ord('d') or key == ord('D'):
                        # Cycle through display modes
                        display_modes = ['standard', 'enhanced', 'compact']
                        current_idx = display_modes.index(self.display_mode)
                        self.display_mode = display_modes[(current_idx + 1) % len(display_modes)]
                    elif key == ord('e') or key == ord('E'):
                        # Toggle enhanced data filter
                        self.filter_enhanced_only = not self.filter_enhanced_only
                    elif key == ord('t') or key == ord('T'):
                        # Toggle detailed statistics display
                        self.show_detailed_stats = not self.show_detailed_stats
                    elif key == ord('n') or key == ord('N'):
                        # Toggle Meshtastic status display
                        self.show_meshtastic_status = not self.show_meshtastic_status
                    elif key == ord('c') or key == ord('C'):
                        # Clear error log
                        self.error_log.clear()
                        self.connection_history.clear()
                    elif key == ord(' '):
                        # Force refresh
                        pass
                    
            except curses.error:
                pass
            
            time.sleep(0.1)
    
    def data_updater(self):
        """Background thread to update aircraft data"""
        stats_update_counter = 0
        last_successful_update = datetime.now()
        
        while self.running:
            try:
                # Fetch aircraft data with timeout protection
                aircraft_data = self.fetch_aircraft_data()
                if aircraft_data and isinstance(aircraft_data, dict) and 'aircraft' in aircraft_data:
                    self.update_aircraft(aircraft_data)
                    last_successful_update = datetime.now()
                else:
                    # If we haven't had a successful update in a while, log it (but not too frequently)
                    time_since_update = (datetime.now() - last_successful_update).total_seconds()
                    if time_since_update > 60 and time_since_update % 30 < 1:  # Log every 30s after 60s timeout
                        self.log_error("data_timeout", f"No aircraft data for {int(time_since_update)} seconds", "data_updater")
                
                # Update additional stats every 5 seconds to reduce API load
                stats_update_counter += 1
                if stats_update_counter >= 5:
                    self._update_additional_stats()
                    stats_update_counter = 0
                
            except Exception as e:
                # Log errors but don't let them crash the updater
                self.log_error("data_updater_error", f"Data updater error: {str(e)}", "data_updater")
            
            # Sleep for 1 second between updates
            time.sleep(1)
    
    def _update_additional_stats(self):
        """Update additional statistics in a separate method for better error handling"""
        # Update each stat source independently so one failure doesn't affect others
        
        # pyModeS stats
        try:
            pymodes_data = self.fetch_pymodes_stats()
            if pymodes_data and isinstance(pymodes_data, dict):
                self.update_pymodes_stats(pymodes_data)
        except Exception:
            pass  # Silently handle to prevent display disruption
        
        # Source stats
        try:
            source_data = self.fetch_source_stats()
            if source_data and isinstance(source_data, dict):
                self.update_source_stats(source_data)
        except Exception:
            pass  # Silently handle to prevent display disruption
        
        # Alert status
        try:
            alert_data = self.fetch_alert_status()
            if alert_data and isinstance(alert_data, dict):
                # Only update specific fields to prevent overwriting
                for key, value in alert_data.items():
                    if key in self.alert_status and value is not None:
                        self.alert_status[key] = value
        except Exception:
            pass  # Silently handle to prevent display disruption
        
        # Meshtastic status
        try:
            meshtastic_data = self.fetch_meshtastic_status()
            if meshtastic_data and isinstance(meshtastic_data, dict):
                self.update_meshtastic_status(meshtastic_data)
        except Exception:
            pass  # Silently handle to prevent display disruption
    
    def run_dashboard(self, stdscr):
        """Main dashboard loop"""
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Title
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Target line
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Target aircraft / Input
        curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Performance stats
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)   # HackRF settings
        
        # Configure curses for better performance
        curses.curs_set(0)  # Hide cursor
        stdscr.timeout(100)  # Set timeout for getch
        
        # Start background data updater
        data_thread = threading.Thread(target=self.data_updater, daemon=True)
        data_thread.start()
        
        # Start input handler
        input_thread = threading.Thread(target=self.handle_input, args=(stdscr,), daemon=True)
        input_thread.start()
        
        # Track drawing state
        last_height, last_width = 0, 0
        force_redraw = True
        consecutive_errors = 0
        
        while self.running:
            try:
                height, width = stdscr.getmaxyx()
                
                # Only clear screen when necessary (size change or force redraw)
                if height != last_height or width != last_width or force_redraw:
                    stdscr.clear()
                    last_height, last_width = height, width
                    force_redraw = False
                
                # Draw dashboard components with comprehensive error handling
                try:
                    # Draw all components in order
                    data_start_y = self.draw_header(stdscr, height, width)
                    
                    if not self.menu_active:
                        current_y = data_start_y
                        
                        if self.show_detailed_stats:
                            current_y = self.draw_detailed_stats(stdscr, current_y, height, width)
                        
                        if self.show_meshtastic_status:
                            current_y = self.draw_meshtastic_status(stdscr, current_y, height, width)
                        
                        if self.show_waterfall:
                            current_y = self.draw_mini_waterfall(stdscr, current_y, height, width)
                        
                        # Only draw aircraft list if we have space
                        if current_y < height - 2:
                            self.draw_aircraft_list(stdscr, current_y, height, width)
                    
                    self.draw_footer(stdscr, height, width)
                    
                    # Refresh screen only after all drawing is complete
                    stdscr.refresh()
                    consecutive_errors = 0
                    
                except Exception as e:
                    consecutive_errors += 1
                    
                    # If we have too many consecutive errors, force a redraw
                    if consecutive_errors >= 3:
                        force_redraw = True
                        consecutive_errors = 0
                    
                    # Try to show error message without disrupting display too much
                    try:
                        error_msg = f"Draw error: {str(e)[:width-20]}"
                        stdscr.addstr(height-2, 0, error_msg, curses.A_BOLD | curses.color_pair(2))
                        stdscr.refresh()
                    except:
                        # If we can't even draw the error, force a complete redraw next time
                        force_redraw = True
                
                # Slower refresh rate to reduce flickering
                time.sleep(1.0)
                
            except curses.error:
                # Terminal size changed or other curses error
                force_redraw = True
                time.sleep(0.5)
            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                # Unexpected error - log it and continue
                self.log_error("dashboard_error", f"Dashboard loop error: {str(e)}", "dashboard")
                force_redraw = True
                time.sleep(1.0)
    
    def run(self):
        """Start the dashboard"""
        try:
            curses.wrapper(self.run_dashboard)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False

def signal_handler(sig, frame):
    print('\n🛑 Dashboard stopped')
    sys.exit(0)

def main():
    print("🛩️ Starting Ursine Explorer ADS-B Dashboard...")
    print("Press Ctrl+C to stop")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    dashboard = ADSBDashboard()
    dashboard.run()

if __name__ == "__main__":
    main()