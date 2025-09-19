#!/usr/bin/env python3
"""
Ursine Explorer ADS-B Receiver with dump1090 Integration
Manages dump1090 process and provides aircraft data via HTTP API
Implements watchlist detection and Meshtastic alert system
"""

import json
import time
import threading
import socket
import socketserver
import subprocess
import signal
import sys
import os
import serial
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('adsb_receiver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Aircraft:
    """Aircraft data structure"""
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
        self.is_watchlist = False
        
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
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'hex': self.hex,
            'flight': self.flight,
            'alt_baro': self.altitude,
            'gs': self.speed,
            'track': self.track,
            'lat': self.lat,
            'lon': self.lon,
            'squawk': self.squawk,
            'category': self.category,
            'messages': self.messages,
            'last_seen': self.last_seen.isoformat(),
            'is_watchlist': self.is_watchlist
        }

class MeshtasticAlert:
    """Handles Meshtastic serial communication for alerts"""
    
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.serial_conn = None
        self.last_alert_times: Dict[str, datetime] = {}
        self.alert_interval = timedelta(seconds=300)  # 5 minutes default
        
    def connect(self) -> bool:
        """Connect to Meshtastic device"""
        try:
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                timeout=1,
                write_timeout=1
            )
            logger.info(f"Connected to Meshtastic on {self.port}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to Meshtastic: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Meshtastic device"""
        if self.serial_conn:
            try:
                self.serial_conn.close()
                logger.info("🔌 Disconnected from Meshtastic")
            except Exception as e:
                logger.error(f"⚠️ Error disconnecting from Meshtastic: {e}")
            finally:
                self.serial_conn = None
    
    def send_alert(self, aircraft: Aircraft, log_alerts: bool = True, log_file: str = "alerts.log") -> bool:
        """Send alert for watchlist aircraft"""
        if not self.serial_conn:
            return False
        
        # Check if enough time has passed since last alert for this aircraft
        now = datetime.now()
        last_alert = self.last_alert_times.get(aircraft.hex)
        
        if last_alert and (now - last_alert) < self.alert_interval:
            return False  # Too soon for another alert
        
        try:
            # Create alert message
            alt_str = f"{aircraft.altitude} ft" if isinstance(aircraft.altitude, (int, float)) else "unknown alt"
            msg = f"ALERT: Watchlist aircraft {aircraft.hex} ({aircraft.flight}) overhead at {alt_str}"
            
            # Send to Meshtastic
            self.serial_conn.write((msg + "\n").encode('utf-8'))
            self.serial_conn.flush()
            
            # Update last alert time
            self.last_alert_times[aircraft.hex] = now
            
            # Log alert if enabled
            if log_alerts:
                self.log_alert(msg, log_file)
            
            logger.info(f"📡 Sent Meshtastic alert: {msg}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to send Meshtastic alert: {e}")
            return False
    
    def log_alert(self, message: str, log_file: str):
        """Log alert to file"""
        try:
            with open(log_file, "a") as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp} - {message}\n")
        except Exception as e:
            logger.error(f"❌ Failed to log alert: {e}")

class Dump1090Manager:
    """Manages dump1090 process lifecycle"""
    
    def __init__(self, config: dict):
        self.config = config
        self.process = None
        self.running = False
        self.last_data_time = None
        self.watchdog_timeout = config.get('watchdog_timeout_sec', 60)
        
    def start(self) -> bool:
        """Start dump1090 process"""
        try:
            dump1090_path = self.config.get('dump1090_path', '/usr/bin/dump1090-fa')
            
            # Check if it's dump1090-mutability (different command line options)
            if 'mutability' in dump1090_path:
                # dump1090-mutability uses basic options - no HackRF support, no HTTP port
                cmd = [
                    dump1090_path,
                    '--freq', str(self.config.get('frequency', 1090000000)),
                    '--net',
                    '--net-ro-port', '30005',
                    '--net-sbs-port', '30003'
                ]
                
                # Add basic gain setting for mutability
                lna_gain = self.config.get('lna_gain', 40)
                cmd.extend(['--gain', str(lna_gain)])
            else:
                # dump1090-fa options
                cmd = [
                    dump1090_path,
                    '--device-type', 'hackrf',
                    '--freq', str(self.config.get('frequency', 1090000000)),
                    '--net',
                    '--net-ro-port', '30005',
                    '--net-sbs-port', '30003',
                    '--net-http-port', str(self.config.get('dump1090_port', 8080))
                ]
                
                # Add gain settings
                if self.config.get('enable_hackrf_amp', True):
                    cmd.append('--enable-amp')
                
                lna_gain = self.config.get('lna_gain', 40)
                vga_gain = self.config.get('vga_gain', 20)
                cmd.extend(['--lna-gain', str(lna_gain)])
                cmd.extend(['--vga-gain', str(vga_gain)])
            
            logger.info(f"Starting dump1090: {' '.join(cmd)}")
            
            # Start process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            self.running = True
            self.last_data_time = datetime.now()
            
            # Give it time to start
            time.sleep(2)
            
            if self.process.poll() is None:
                logger.info("dump1090 started successfully")
                return True
            else:
                stdout, stderr = self.process.communicate()
                logger.error(f"dump1090 failed to start: {stderr.decode()}")
                return False
            
        except Exception as e:
            logger.error(f"Failed to start dump1090: {e}")
            return False
    
    def stop(self):
        """Stop dump1090 process"""
        if self.process and self.running:
            try:
                logger.info("Stopping dump1090...")
                
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                
                # Wait for graceful shutdown
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't stop gracefully
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    self.process.wait()
                
                self.running = False
                logger.info("dump1090 stopped")
                
            except Exception as e:
                logger.error(f"Error stopping dump1090: {e}")
            finally:
                self.process = None
    
    def is_running(self) -> bool:
        """Check if dump1090 is still running"""
        if not self.process:
            return False
        
        return self.process.poll() is None
    
    def needs_restart(self) -> bool:
        """Check if dump1090 needs restart due to watchdog timeout"""
        if not self.running or not self.last_data_time:
            return False
        
        time_since_data = datetime.now() - self.last_data_time
        return time_since_data.total_seconds() > self.watchdog_timeout
    
    def update_data_time(self):
        """Update last data received time"""
        self.last_data_time = datetime.now()

class ADSBHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for aircraft data API"""
    
    def do_GET(self):
        if self.path == '/data/aircraft.json':
            # Get aircraft data from server
            server = self.server.adsb_server
            aircraft_data = server.get_aircraft_data()
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(aircraft_data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass

class ControlHandler(socketserver.BaseRequestHandler):
    """Handle control commands from dashboard"""
    
    def handle(self):
        try:
            data = self.request.recv(1024).decode().strip()
            logger.info(f"🔧 Received command: {data}")
            
            if ':' in data:
                command, value = data.split(':', 1)
                value = float(value)
            else:
                command = data
                value = None
            
            # Get the server instance
            server = self.server.adsb_server
            success = False
            
            if command == 'PING':
                success = True
            elif command == 'RESTART_DUMP1090':
                success = server.restart_dump1090()
            elif command == 'GET_STATUS':
                status = server.get_status()
                self.request.sendall(json.dumps(status).encode())
                return
            
            response = "OK" if success else "ERROR"
            self.request.sendall(response.encode())
            
        except Exception as e:
            logger.error(f"❌ Control command error: {e}")
            self.request.sendall(b"ERROR")

class ADSBServer:
    """Main ADS-B server with dump1090 integration"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = self.load_config(config_path)
        self.aircraft: Dict[str, Aircraft] = {}
        self.watchlist: Set[str] = set()
        self.meshtastic = None
        self.dump1090_manager = None
        self.httpd = None
        self.control_server = None
        self.running = False
        
        # Statistics
        self.stats = {
            'total_aircraft': 0,
            'active_aircraft': 0,
            'messages_total': 0,
            'last_update': None,
            'update_count': 0,
            'errors': 0,
            'watchlist_alerts': 0,
            'dump1090_restarts': 0
        }
        
        # Initialize watchlist
        self.update_watchlist()
        
        # Initialize Meshtastic
        if self.config.get('meshtastic_port'):
            self.meshtastic = MeshtasticAlert(
                self.config['meshtastic_port'],
                self.config.get('meshtastic_baud', 115200)
            )
        
        # Initialize dump1090 manager
        self.dump1090_manager = Dump1090Manager(self.config)
    
    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                # Set defaults
                config.setdefault('dump1090_host', 'localhost')
                config.setdefault('dump1090_port', 8080)
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
            logger.error(f"❌ Config file not found: {config_path}")
            return {}
        except Exception as e:
            logger.error(f"❌ Error loading config: {e}")
            return {}
    
    def update_watchlist(self):
        """Update watchlist from config"""
        self.watchlist = set(code.upper() for code in self.config.get('target_icao_codes', []))
        logger.info(f"🎯 Watchlist updated: {list(self.watchlist)}")
    
    def start_dump1090(self) -> bool:
        """Start dump1090 process"""
        return self.dump1090_manager.start()
    
    def stop_dump1090(self):
        """Stop dump1090 process"""
        self.dump1090_manager.stop()
    
    def restart_dump1090(self) -> bool:
        """Restart dump1090 process"""
        logger.info("🔄 Restarting dump1090...")
        self.stop_dump1090()
        time.sleep(2)
        success = self.start_dump1090()
        if success:
            self.stats['dump1090_restarts'] += 1
        return success
    
    def connect_meshtastic(self) -> bool:
        """Connect to Meshtastic device"""
        if self.meshtastic:
            return self.meshtastic.connect()
        return False
    
    def disconnect_meshtastic(self):
        """Disconnect from Meshtastic device"""
        if self.meshtastic:
            self.meshtastic.disconnect()
    
    def fetch_aircraft_data(self) -> Optional[dict]:
        """Fetch aircraft data from dump1090"""
        try:
            url = f"http://{self.config['dump1090_host']}:{self.config['dump1090_port']}/data/aircraft.json"
            response = requests.get(url, timeout=2)
            response.raise_for_status()
            data = response.json()
            
            # Update dump1090 data time for watchdog
            if self.dump1090_manager:
                self.dump1090_manager.update_data_time()
            
            return data
        except requests.RequestException as e:
            self.stats['errors'] += 1
            logger.warning(f"⚠️ Failed to fetch aircraft data: {e}")
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
        
        # Process each aircraft
        for ac_data in aircraft_data['aircraft']:
            hex_code = ac_data.get('hex', '').upper()
            if not hex_code:
                continue
                
            current_aircraft.add(hex_code)
            
            # Check if aircraft is on watchlist
            is_watchlist = hex_code in self.watchlist
            
            if hex_code in self.aircraft:
                self.aircraft[hex_code].update(ac_data)
                self.aircraft[hex_code].is_watchlist = is_watchlist
            else:
                new_aircraft = Aircraft(ac_data)
                new_aircraft.is_watchlist = is_watchlist
                self.aircraft[hex_code] = new_aircraft
                self.stats['total_aircraft'] += 1
                
                # Send initial alert for new watchlist aircraft
                if is_watchlist and self.meshtastic:
                    self.send_watchlist_alert(new_aircraft)
        
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
    
    def send_watchlist_alert(self, aircraft: Aircraft):
        """Send alert for watchlist aircraft"""
        if not self.meshtastic or not aircraft.is_watchlist:
            return
        
        success = self.meshtastic.send_alert(
            aircraft,
            self.config.get('log_alerts', True),
            self.config.get('alert_log_file', 'alerts.log')
        )
        
        if success:
            self.stats['watchlist_alerts'] += 1
    
    def get_aircraft_data(self) -> dict:
        """Get current aircraft data for API"""
        aircraft_list = []
        for aircraft in self.aircraft.values():
            aircraft_list.append(aircraft.to_dict())
        
        return {
            "now": time.time(),
            "messages": self.stats['messages_total'],
            "aircraft": aircraft_list,
            "stats": self.stats
        }
    
    def get_status(self) -> dict:
        """Get system status"""
        return {
            "dump1090_running": self.dump1090_manager.is_running() if self.dump1090_manager else False,
            "meshtastic_connected": self.meshtastic.serial_conn is not None if self.meshtastic else False,
            "aircraft_count": len(self.aircraft),
            "watchlist_count": len(self.watchlist),
            "stats": self.stats
        }
    
    def data_updater(self):
        """Background thread to update aircraft data"""
        while self.running:
            try:
                # Check if dump1090 needs restart
                if self.dump1090_manager and self.dump1090_manager.needs_restart():
                    logger.warning("⚠️ Watchdog timeout - restarting dump1090")
                    self.restart_dump1090()
                
                # Fetch and update aircraft data
                aircraft_data = self.fetch_aircraft_data()
                if aircraft_data:
                    self.update_aircraft(aircraft_data)
                
                # Check for periodic watchlist alerts
                for aircraft in self.aircraft.values():
                    if aircraft.is_watchlist:
                        self.send_watchlist_alert(aircraft)
                
                time.sleep(self.config.get('poll_interval_sec', 1))
                
            except Exception as e:
                logger.error(f"Data updater error: {e}")
                time.sleep(5)
    
    def start_http_server(self):
        """Start HTTP server for aircraft data"""
        try:
            self.httpd = HTTPServer(('localhost', self.config['dump1090_port']), ADSBHTTPHandler)
            self.httpd.adsb_server = self
            logger.info(f"✅ HTTP server started on port {self.config['dump1090_port']}")
            self.httpd.serve_forever()
        except Exception as e:
            logger.error(f"❌ Failed to start HTTP server: {e}")
    
    def start_control_server(self):
        """Start control server for dashboard commands"""
        try:
            self.control_server = socketserver.TCPServer(
                ('localhost', self.config['receiver_control_port']), 
                ControlHandler
            )
            self.control_server.adsb_server = self
            logger.info(f"✅ Control server started on port {self.config['receiver_control_port']}")
            self.control_server.serve_forever()
        except Exception as e:
            logger.error(f"❌ Failed to start control server: {e}")
    
    def start(self):
        """Start the ADS-B server"""
        logger.info("🛩️ Starting Ursine Explorer ADS-B Server")
        
        # Start dump1090
        if not self.start_dump1090():
            logger.error("❌ Failed to start dump1090")
            return False
        
        # Connect to Meshtastic
        if self.meshtastic:
            self.connect_meshtastic()
        
        # Start HTTP server in background thread
        http_thread = threading.Thread(target=self.start_http_server, daemon=True)
        http_thread.start()
        
        # Start control server in background thread
        control_thread = threading.Thread(target=self.start_control_server, daemon=True)
        control_thread.start()
        
        # Start data updater in background thread
        self.running = True
        data_thread = threading.Thread(target=self.data_updater, daemon=True)
        data_thread.start()
        
        logger.info("✅ ADS-B server started successfully")
        return True
    
    def stop(self):
        """Stop the ADS-B server"""
        logger.info("🛑 Shutting down ADS-B server...")
        
        self.running = False
        
        # Stop dump1090
        self.stop_dump1090()
        
        # Disconnect from Meshtastic
        self.disconnect_meshtastic()
        
        # Stop HTTP server
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception as e:
                logger.error(f"⚠️ HTTP server stop error: {e}")
        
        # Stop control server
        if self.control_server:
            try:
                self.control_server.shutdown()
                self.control_server.server_close()
            except Exception as e:
                logger.error(f"⚠️ Control server stop error: {e}")
        
        logger.info("✅ Shutdown complete")

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info('\n🛑 Received interrupt signal')
    if hasattr(signal_handler, 'server'):
        try:
            signal_handler.server.stop()
        except Exception as e:
            logger.error(f"⚠️ Error during shutdown: {e}")
    
    # Force exit if needed
    logger.info("🔄 Forcing exit...")
    os._exit(0)

def main():
    """Main entry point"""
    print("Ursine Explorer ADS-B Receiver with dump1090 Integration")
    print("=" * 60)
    
    server = ADSBServer()
    signal_handler.server = server
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start server
    if not server.start():
        logger.error("❌ Failed to start server")
        sys.exit(1)
    
    print("\nADS-B receiver running... Press Ctrl+C to stop")
    print(f"Aircraft data: http://localhost:{server.config['dump1090_port']}/data/aircraft.json")
    print(f"Control port: {server.config['receiver_control_port']}")
    print(f"Watchlist: {list(server.watchlist)}")
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n🛑 Keyboard interrupt received")
        server.stop()
    except Exception as e:
        logger.error(f"\n❌ Unexpected error: {e}")
        server.stop()
    finally:
        logger.info("🔄 Exiting main thread...")
        sys.exit(0)

if __name__ == "__main__":
    main()
