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
        self.message_history = []  # Track message rates
        self.signal_strengths = []  # Track signal strengths
        self.sort_by = 'last_seen'  # Options: last_seen, altitude, speed, flight, hex
        self.sort_reverse = True
        
    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Set defaults if not present
                config.setdefault('dump1090_host', 'localhost')
                config.setdefault('dump1090_port', 8080)
                config.setdefault('receiver_control_port', 8081)
                config.setdefault('target_icao_codes', [])
                return config
        except FileNotFoundError:
            # Return default config if file not found
            return {
                'dump1090_host': 'localhost',
                'dump1090_port': 8080,
                'receiver_control_port': 8081,
                'target_icao_codes': []
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
            return False, "Connection refused - is receiver running?"
        except socket.timeout:
            return False, "Connection timeout"
        except Exception as e:
            return False, f"Connection error: {str(e)}"
    
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
        """Apply a setting to the HackRF"""
        command_map = {
            'rf_gain': 'SET_RF_GAIN',
            'if_gain': 'SET_IF_GAIN', 
            'bb_gain': 'SET_BB_GAIN',
            'sample_rate': 'SET_SAMPLE_RATE',
            'center_freq': 'SET_CENTER_FREQ'
        }
        
        command = command_map.get(setting_name)
        if not command:
            return False, "Unknown command"
        
        success, message = self.send_receiver_command(command, value)
        if success:
            self.hackrf_settings[setting_name]['value'] = value
            return True, "Applied successfully"
        return False, message
    
    def fetch_aircraft_data(self) -> Optional[dict]:
        """Fetch aircraft data from ADS-B receiver"""
        try:
            url = f"http://{self.config['dump1090_host']}:{self.config['dump1090_port']}/data/aircraft.json"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            self.stats['errors'] += 1
            return None
    
    def update_aircraft(self, aircraft_data: dict):
        """Update aircraft tracking data"""
        if not aircraft_data or 'aircraft' not in aircraft_data:
            return
        
        current_time = datetime.now()
        current_aircraft = set()
        
        # Update basic stats
        prev_messages = self.stats['messages_total']
        self.stats['messages_total'] = aircraft_data.get('messages', 0)
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
    
    def get_sorted_aircraft(self) -> List[Aircraft]:
        """Get aircraft list sorted by current criteria"""
        aircraft_list = list(self.aircraft.values())
        
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
        
        # Aircraft stats line
        stats_line = f"Active: {self.stats['active_aircraft']} | Total Seen: {self.stats['total_aircraft']} | With Position: {self.stats['aircraft_with_positions']} | Max Range: {self.stats['max_range_km']:.1f}km"
        stdscr.addstr(2, 0, stats_line[:width-1])
        
        # Radio performance line
        perf_line = f"Messages: {self.stats['messages_total']} | Rate: {self.stats['messages_per_second']:.1f}/sec | Avg Signal: {self.stats['avg_signal_strength']:.1f}dBm | Strong: {self.stats['strong_signals']} | Weak: {self.stats['weak_signals']}"
        stdscr.addstr(3, 0, perf_line[:width-1], curses.color_pair(4))
        
        # System status line
        status_line = f"Updates: {self.stats['update_count']} | Errors: {self.stats['errors']}"
        if self.stats['last_update']:
            age = int((datetime.now() - self.stats['last_update']).total_seconds())
            status_line += f" | Last Update: {age}s ago"
            if age > 5:
                status_line += " ⚠️"
        else:
            status_line += " | Waiting for data... 🔄"
        
        stdscr.addstr(4, 0, status_line[:width-1])
        
        # Target aircraft line (optional - only show if targets are configured)
        header_y = 6
        if self.config['target_icao_codes']:
            target_line = f"🎯 Targets: {', '.join(self.config['target_icao_codes'])} (highlighted in green)"
            stdscr.addstr(5, 0, target_line[:width-1], curses.color_pair(2))
            header_y = 7
        
        # Column headers
        header = f"{'ICAO':<8} {'CALLSIGN':<10} {'ALT':<8} {'SPD':<6} {'TRK':<4} {'AGE':<5} {'DUR':<5} {'MSGS':<6}"
        stdscr.addstr(header_y, 0, header[:width-1], curses.A_BOLD)
        
        return header_y + 1
    
    def draw_aircraft_list(self, stdscr, start_y: int, height: int, width: int):
        """Draw the aircraft list"""
        aircraft_list = self.get_sorted_aircraft()
        max_rows = height - start_y - 2
        
        target_icaos = set(code.upper() for code in self.config['target_icao_codes'])
        
        for i, aircraft in enumerate(aircraft_list[:max_rows]):
            y = start_y + i
            if y >= height - 1:
                break
            
            # Format aircraft data
            alt_str = f"{aircraft.altitude}" if isinstance(aircraft.altitude, (int, float)) else "---"
            spd_str = f"{aircraft.speed}" if isinstance(aircraft.speed, (int, float)) else "---"
            trk_str = f"{aircraft.track}" if isinstance(aircraft.track, (int, float)) else "---"
            age_str = f"{aircraft.age_seconds()}s"
            dur_str = f"{aircraft.duration_seconds()}s"
            msg_str = f"{aircraft.messages}" if isinstance(aircraft.messages, int) else "---"
            
            line = f"{aircraft.hex:<8} {aircraft.flight:<10} {alt_str:<8} {spd_str:<6} {trk_str:<4} {age_str:<5} {dur_str:<5} {msg_str:<6}"
            
            # Highlight target aircraft
            if aircraft.hex in target_icaos:
                stdscr.addstr(y, 0, line[:width-1], curses.A_BOLD | curses.color_pair(3))
            else:
                stdscr.addstr(y, 0, line[:width-1])
    
    def draw_footer(self, stdscr, height: int, width: int):
        """Draw dashboard footer with controls"""
        footer_y = height - 1
        if self.menu_active:
            controls = "Menu Mode: ↑↓=navigate | ENTER=select | ESC=exit | Type values and press ENTER"
        else:
            controls = f"Controls: q=quit | m=menu | s=sort({self.sort_by}) | r=reverse | Space=refresh"
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
                        sort_options = ['last_seen', 'altitude', 'speed', 'flight', 'hex']
                        current_idx = sort_options.index(self.sort_by)
                        self.sort_by = sort_options[(current_idx + 1) % len(sort_options)]
                    elif key == ord('r') or key == ord('R'):
                        self.sort_reverse = not self.sort_reverse
                    elif key == ord(' '):
                        # Force refresh
                        pass
                    
            except curses.error:
                pass
            
            time.sleep(0.1)
    
    def data_updater(self):
        """Background thread to update aircraft data"""
        while self.running:
            aircraft_data = self.fetch_aircraft_data()
            if aircraft_data:
                self.update_aircraft(aircraft_data)
            time.sleep(1)  # Update every second
    
    def run_dashboard(self, stdscr):
        """Main dashboard loop"""
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)    # Title
        curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Target line
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)   # Target aircraft / Input
        curses.init_pair(4, curses.COLOR_MAGENTA, curses.COLOR_BLACK) # Performance stats
        curses.init_pair(5, curses.COLOR_WHITE, curses.COLOR_BLACK)   # HackRF settings
        
        # Start background data updater
        data_thread = threading.Thread(target=self.data_updater, daemon=True)
        data_thread.start()
        
        # Start input handler
        input_thread = threading.Thread(target=self.handle_input, args=(stdscr,), daemon=True)
        input_thread.start()
        
        while self.running:
            try:
                stdscr.clear()
                height, width = stdscr.getmaxyx()
                
                # Draw dashboard components
                data_start_y = self.draw_header(stdscr, height, width)
                if not self.menu_active:
                    self.draw_aircraft_list(stdscr, data_start_y, height, width)
                self.draw_footer(stdscr, height, width)
                
                stdscr.refresh()
                time.sleep(0.5)  # Refresh display twice per second
                
            except curses.error:
                pass
            except KeyboardInterrupt:
                self.running = False
    
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