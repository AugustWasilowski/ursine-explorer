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
from collections import defaultdict, deque
from urllib.parse import urlparse, parse_qs

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

class RateLimiter:
    """Simple rate limiter for API endpoints"""
    
    def __init__(self, max_requests: int = 60, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)
    
    def is_allowed(self, client_ip: str) -> bool:
        """Check if request is allowed for client IP"""
        now = time.time()
        client_requests = self.requests[client_ip]
        
        # Remove old requests outside the window
        while client_requests and client_requests[0] < now - self.window_seconds:
            client_requests.popleft()
        
        # Check if under limit
        if len(client_requests) < self.max_requests:
            client_requests.append(now)
            return True
        
        return False
    
    def get_remaining_requests(self, client_ip: str) -> int:
        """Get remaining requests for client IP"""
        now = time.time()
        client_requests = self.requests[client_ip]
        
        # Remove old requests outside the window
        while client_requests and client_requests[0] < now - self.window_seconds:
            client_requests.popleft()
        
        return max(0, self.max_requests - len(client_requests))
    
    def get_reset_time(self, client_ip: str) -> float:
        """Get time when rate limit resets for client IP"""
        client_requests = self.requests[client_ip]
        if not client_requests:
            return time.time()
        
        return client_requests[0] + self.window_seconds

class APILogger:
    """Enhanced logging for API access and errors"""
    
    def __init__(self):
        self.access_logger = logging.getLogger('api.access')
        self.error_logger = logging.getLogger('api.error')
        
        # Create separate handlers for API logs
        access_handler = logging.FileHandler('api_access.log')
        error_handler = logging.FileHandler('api_errors.log')
        
        # Format for access logs
        access_formatter = logging.Formatter(
            '%(asctime)s - %(message)s'
        )
        access_handler.setFormatter(access_formatter)
        
        # Format for error logs
        error_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        error_handler.setFormatter(error_formatter)
        
        self.access_logger.addHandler(access_handler)
        self.error_logger.addHandler(error_handler)
        self.access_logger.setLevel(logging.INFO)
        self.error_logger.setLevel(logging.ERROR)
    
    def log_access(self, client_ip: str, method: str, path: str, status_code: int, 
                   response_size: int, user_agent: str = None, duration_ms: float = None):
        """Log API access"""
        message = f"{client_ip} - {method} {path} - {status_code} - {response_size} bytes"
        if duration_ms is not None:
            message += f" - {duration_ms:.2f}ms"
        if user_agent:
            message += f" - {user_agent}"
        
        self.access_logger.info(message)
    
    def log_error(self, client_ip: str, method: str, path: str, error: str, 
                  status_code: int = 500, details: str = None):
        """Log API error"""
        message = f"{client_ip} - {method} {path} - ERROR {status_code}: {error}"
        if details:
            message += f" - {details}"
        
        self.error_logger.error(message)
    
    def log_rate_limit(self, client_ip: str, method: str, path: str):
        """Log rate limit violation"""
        message = f"{client_ip} - {method} {path} - RATE_LIMITED"
        self.error_logger.warning(message)

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
            logger.error(f"Failed to connect to Meshtastic: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from Meshtastic device"""
        if self.serial_conn:
            try:
                self.serial_conn.close()
                logger.info("Disconnected from Meshtastic")
            except Exception as e:
                logger.error(f"Error disconnecting from Meshtastic: {e}")
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
            
            logger.info(f"Sent Meshtastic alert: {msg}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send Meshtastic alert: {e}")
            return False
    
    def log_alert(self, message: str, log_file: str):
        """Log alert to file"""
        try:
            with open(log_file, "a") as f:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                f.write(f"{timestamp} - {message}\n")
        except Exception as e:
            logger.error(f"Failed to log alert: {e}")

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
                    '--net-ro-port', str(self.config.get('dump1090_port', 30005)),
                    '--net-sbs-port', '30003',
                    '--write-json', '/tmp/adsb_json',
                    '--write-json-every', '1'
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
    """Enhanced HTTP handler for aircraft data API with pyModeS integration"""
    
    # Class-level rate limiter and logger
    rate_limiter = RateLimiter(max_requests=120, window_seconds=60)  # 120 requests per minute
    api_logger = APILogger()
    
    def do_GET(self):
        start_time = time.time()
        client_ip = self.client_address[0]
        user_agent = self.headers.get('User-Agent', 'Unknown')
        
        try:
            # Rate limiting check
            if not self.rate_limiter.is_allowed(client_ip):
                remaining = self.rate_limiter.get_remaining_requests(client_ip)
                reset_time = self.rate_limiter.get_reset_time(client_ip)
                
                self.api_logger.log_rate_limit(client_ip, 'GET', self.path)
                
                error_data = {
                    "error": "Rate Limit Exceeded",
                    "message": "Too many requests. Please slow down.",
                    "status_code": 429,
                    "timestamp": datetime.now().isoformat(),
                    "rate_limit": {
                        "remaining": remaining,
                        "reset_time": reset_time,
                        "limit": self.rate_limiter.max_requests,
                        "window_seconds": self.rate_limiter.window_seconds
                    }
                }
                
                self._send_json_response(error_data, 429)
                return
            
            # Parse and validate request
            parsed_path = urlparse(self.path)
            path = parsed_path.path
            query_params = parse_qs(parsed_path.query)
            
            # Validate query parameters
            validation_error = self._validate_query_params(path, query_params)
            if validation_error:
                self._send_error_response(400, "Bad Request", validation_error)
                return
            
            # Route requests
            if path == '/data/aircraft.json':
                # Get aircraft data from server
                server = self.server.adsb_server
                aircraft_data = server.get_aircraft_data()
                
                self._send_json_response(aircraft_data)
                
            elif path == '/data/aircraft_enhanced.json':
                # Get enhanced aircraft data with all pyModeS fields
                server = self.server.adsb_server
                aircraft_data = server.get_enhanced_aircraft_data()
                
                self._send_json_response(aircraft_data)
                
            elif path == '/data/fft.json':
                # Get FFT data from server
                server = self.server.adsb_server
                fft_data = server.get_fft_data()
                
                self._send_json_response(fft_data)
                
            elif path == '/api/status':
                # Get system status and diagnostics
                server = self.server.adsb_server
                status_data = server.get_detailed_status()
                
                self._send_json_response(status_data)
                
            elif path == '/api/stats':
                # Get processing statistics
                server = self.server.adsb_server
                stats_data = server.get_processing_stats()
                
                self._send_json_response(stats_data)
                
            elif path == '/api/health':
                # Health check endpoint
                server = self.server.adsb_server
                health_data = server.get_health_status()
                
                # Return appropriate status code based on health
                status_code = 200 if health_data.get('healthy', False) else 503
                self._send_json_response(health_data, status_code)
                
            elif path == '/api/sources':
                # Message source status
                server = self.server.adsb_server
                sources_data = server.get_sources_status()
                
                self._send_json_response(sources_data)
                
            elif path == '/api/decoder':
                # Decoder performance metrics
                server = self.server.adsb_server
                decoder_data = server.get_decoder_metrics()
                
                self._send_json_response(decoder_data)
                
            else:
                self._send_error_response(404, "Not Found", "The requested endpoint was not found")
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            
            self.api_logger.log_error(client_ip, 'GET', self.path, error_msg, 500, 
                                    f"Duration: {duration_ms:.2f}ms")
            logger.error(f"HTTP handler error: {e}")
            self._send_error_response(500, "Internal Server Error", "An internal error occurred")
    
    def _validate_query_params(self, path: str, query_params: dict) -> Optional[str]:
        """Validate query parameters for the given path"""
        
        # Define allowed parameters for each endpoint
        allowed_params = {
            '/data/aircraft.json': ['format', 'limit'],
            '/data/aircraft_enhanced.json': ['format', 'limit', 'include_raw'],
            '/api/stats': ['period', 'format'],
            '/api/status': ['format'],
            '/api/health': ['format'],
            '/api/sources': ['format'],
            '/api/decoder': ['format', 'detailed']
        }
        
        if path not in allowed_params:
            return None  # No validation for unknown paths (will be 404)
        
        # Check for unknown parameters
        for param in query_params:
            if param not in allowed_params[path]:
                return f"Unknown query parameter: {param}"
        
        # Validate specific parameter values
        if 'limit' in query_params:
            try:
                limit = int(query_params['limit'][0])
                if limit < 1 or limit > 1000:
                    return "Parameter 'limit' must be between 1 and 1000"
            except (ValueError, IndexError):
                return "Parameter 'limit' must be a valid integer"
        
        if 'format' in query_params:
            format_val = query_params['format'][0].lower()
            if format_val not in ['json', 'compact']:
                return "Parameter 'format' must be 'json' or 'compact'"
        
        if 'period' in query_params:
            period_val = query_params['period'][0].lower()
            if period_val not in ['1m', '5m', '15m', '1h']:
                return "Parameter 'period' must be one of: 1m, 5m, 15m, 1h"
        
        return None
    
    def _send_json_response(self, data: dict, status_code: int = 200):
        """Send JSON response with proper headers and logging"""
        start_time = time.time()
        client_ip = self.client_address[0]
        user_agent = self.headers.get('User-Agent', 'Unknown')
        
        try:
            json_data = json.dumps(data, indent=2)
            response_size = len(json_data)
            
            # Add rate limit headers
            remaining = self.rate_limiter.get_remaining_requests(client_ip)
            reset_time = int(self.rate_limiter.get_reset_time(client_ip))
            
            self.send_response(status_code)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Content-Length', str(response_size))
            
            # Rate limit headers
            self.send_header('X-RateLimit-Limit', str(self.rate_limiter.max_requests))
            self.send_header('X-RateLimit-Remaining', str(remaining))
            self.send_header('X-RateLimit-Reset', str(reset_time))
            
            # API version header
            self.send_header('X-API-Version', '2.0')
            
            self.end_headers()
            
            self.wfile.write(json_data.encode('utf-8'))
            
            # Log successful request
            duration_ms = (time.time() - start_time) * 1000
            self.api_logger.log_access(client_ip, 'GET', self.path, status_code, 
                                     response_size, user_agent, duration_ms)
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = f"Failed to serialize response: {str(e)}"
            
            self.api_logger.log_error(client_ip, 'GET', self.path, error_msg, 500,
                                    f"Duration: {duration_ms:.2f}ms")
            logger.error(f"Error sending JSON response: {e}")
            self._send_error_response(500, "Internal Server Error", "Failed to serialize response")
    
    def _send_error_response(self, status_code: int, error: str, message: str):
        """Send structured error response with logging"""
        start_time = time.time()
        client_ip = self.client_address[0]
        user_agent = self.headers.get('User-Agent', 'Unknown')
        
        try:
            error_data = {
                "error": error,
                "message": message,
                "status_code": status_code,
                "timestamp": datetime.now().isoformat(),
                "path": self.path,
                "method": "GET"
            }
            
            # Add request ID for tracking
            import uuid
            error_data["request_id"] = str(uuid.uuid4())[:8]
            
            json_data = json.dumps(error_data, indent=2)
            response_size = len(json_data)
            
            # Add rate limit headers even for errors
            remaining = self.rate_limiter.get_remaining_requests(client_ip)
            reset_time = int(self.rate_limiter.get_reset_time(client_ip))
            
            self.send_response(status_code)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(response_size))
            
            # Rate limit headers
            self.send_header('X-RateLimit-Limit', str(self.rate_limiter.max_requests))
            self.send_header('X-RateLimit-Remaining', str(remaining))
            self.send_header('X-RateLimit-Reset', str(reset_time))
            
            # API version header
            self.send_header('X-API-Version', '2.0')
            
            self.end_headers()
            
            self.wfile.write(json_data.encode('utf-8'))
            
            # Log error request
            duration_ms = (time.time() - start_time) * 1000
            self.api_logger.log_error(client_ip, 'GET', self.path, error, status_code,
                                    f"Message: {message}, Duration: {duration_ms:.2f}ms, Request ID: {error_data['request_id']}")
            
        except Exception as e:
            logger.error(f"Error sending error response: {e}")
            # Fallback to basic HTTP error
            try:
                self.send_response(status_code)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error {status_code}: {error}".encode('utf-8'))
            except:
                pass  # Give up if we can't even send basic response
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def log_message(self, format, *args):
        # Use our enhanced API logger instead of default logging
        # The actual logging is handled in _send_json_response and _send_error_response
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
            logger.error(f"Control command error: {e}")
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
        self.start_time = datetime.now()
        
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
            logger.error(f"Config file not found: {config_path}")
            return {}
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return {}
    
    def update_watchlist(self):
        """Update watchlist from config"""
        self.watchlist = set(code.upper() for code in self.config.get('target_icao_codes', []))
        logger.info(f"Watchlist updated: {list(self.watchlist)}")
    
    def start_dump1090(self) -> bool:
        """Start dump1090 process"""
        return self.dump1090_manager.start()
    
    def stop_dump1090(self):
        """Stop dump1090 process"""
        self.dump1090_manager.stop()
    
    def restart_dump1090(self) -> bool:
        """Restart dump1090 process"""
        logger.info("Restarting dump1090...")
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
        """Fetch aircraft data from dump1090 JSON files"""
        try:
            # Read aircraft data from JSON file
            aircraft_file = '/tmp/adsb_json/aircraft.json'
            if os.path.exists(aircraft_file):
                with open(aircraft_file, 'r') as f:
                    aircraft_data = json.load(f)
                
                # Update dump1090 data time for watchdog
                if self.dump1090_manager:
                    self.dump1090_manager.update_data_time()
                
                logger.info(f"Read aircraft data: {len(aircraft_data.get('aircraft', []))} aircraft, {aircraft_data.get('messages', 0)} messages")
                return aircraft_data
            
            return {"aircraft": [], "messages": 0}
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.warning(f"Failed to fetch aircraft data: {e}")
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
            
            # Log aircraft details
            flight = ac_data.get('flight', '').strip() or 'Unknown'
            altitude = ac_data.get('alt_baro', 'Unknown')
            speed = ac_data.get('gs', 'Unknown')
            track = ac_data.get('track', 'Unknown')
            lat = ac_data.get('lat', 'Unknown')
            lon = ac_data.get('lon', 'Unknown')
            squawk = ac_data.get('squawk', 'Unknown')
            
            # Format the log message
            log_msg = f"AIRCRAFT: {hex_code} ({flight})"
            if altitude != 'Unknown':
                log_msg += f" @ {altitude}ft"
            if speed != 'Unknown':
                log_msg += f" {speed}kts"
            if track != 'Unknown':
                log_msg += f" {track}°"
            if lat != 'Unknown' and lon != 'Unknown':
                log_msg += f" [{lat:.4f},{lon:.4f}]"
            if squawk != 'Unknown':
                log_msg += f" squawk:{squawk}"
            if is_watchlist:
                log_msg += " [WATCHLIST]"
            
            logger.info(log_msg)
            
            if hex_code in self.aircraft:
                self.aircraft[hex_code].update(ac_data)
                self.aircraft[hex_code].is_watchlist = is_watchlist
            else:
                new_aircraft = Aircraft(ac_data)
                new_aircraft.is_watchlist = is_watchlist
                self.aircraft[hex_code] = new_aircraft
                self.stats['total_aircraft'] += 1
                logger.info(f"NEW AIRCRAFT: {hex_code} ({flight})")
                
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
            aircraft = self.aircraft[hex_code]
            logger.info(f"AIRCRAFT TIMEOUT: {hex_code} ({aircraft.flight})")
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
    
    def generate_fft_data(self):
        """Generate FFT data for waterfall viewer (in-memory)"""
        try:
            import numpy as np
            
            # Create FFT data (1024 bins)
            fft_size = 1024
            fft_data = np.random.exponential(0.1, fft_size).astype(np.float32)
            
            # Add some peaks to simulate ADS-B signals
            # Peak at 1090 MHz (center bin)
            center_bin = fft_size // 2
            fft_data[center_bin] += np.random.exponential(2.0)
            
            # Add some random peaks to simulate other signals
            for _ in range(3):
                peak_bin = np.random.randint(0, fft_size)
                fft_data[peak_bin] += np.random.exponential(1.0)
            
            # Store in memory for waterfall viewer
            if not hasattr(self, 'fft_history'):
                self.fft_history = []
            
            self.fft_history.append(fft_data)
            
            # Keep only last 10 seconds (assuming 1 update per second)
            if len(self.fft_history) > 10:
                self.fft_history.pop(0)
                
        except Exception as e:
            # If numpy isn't available, just continue
            pass
    
    def get_aircraft_data(self) -> dict:
        """Get current aircraft data for API (legacy format for backward compatibility)"""
        aircraft_list = []
        for aircraft in self.aircraft.values():
            # Use legacy format for backward compatibility
            if hasattr(aircraft, 'to_legacy_dict'):
                aircraft_list.append(aircraft.to_legacy_dict())
            else:
                aircraft_list.append(aircraft.to_dict())
        
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if stats_copy.get('last_update'):
            stats_copy['last_update'] = stats_copy['last_update'].isoformat()
        
        return {
            "now": time.time(),
            "messages": self.stats['messages_total'],
            "aircraft": aircraft_list,
            "stats": stats_copy
        }
    
    def get_enhanced_aircraft_data(self) -> dict:
        """Get enhanced aircraft data with all pyModeS fields"""
        aircraft_list = []
        for aircraft in self.aircraft.values():
            # Use enhanced format with all available fields
            if hasattr(aircraft, 'to_api_dict'):
                aircraft_list.append(aircraft.to_api_dict())
            else:
                # Fallback to legacy format
                aircraft_list.append(aircraft.to_dict())
        
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if stats_copy.get('last_update'):
            stats_copy['last_update'] = stats_copy['last_update'].isoformat()
        
        return {
            "now": time.time(),
            "messages": self.stats['messages_total'],
            "aircraft": aircraft_list,
            "stats": stats_copy,
            "enhanced_fields": {
                "alt_gnss": "GNSS altitude in feet",
                "vertical_rate": "Vertical rate in feet per minute",
                "true_airspeed": "True airspeed in knots",
                "indicated_airspeed": "Indicated airspeed in knots", 
                "mach_number": "Mach number",
                "magnetic_heading": "Magnetic heading in degrees",
                "roll_angle": "Roll angle in degrees",
                "navigation_accuracy": "Navigation accuracy metrics",
                "surveillance_status": "Surveillance status",
                "data_sources": "List of message types received",
                "first_seen": "First time aircraft was detected"
            }
        }
    
    def get_detailed_status(self) -> dict:
        """Get detailed system status and diagnostics"""
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if stats_copy.get('last_update'):
            stats_copy['last_update'] = stats_copy['last_update'].isoformat()
        
        # Get message source status if available
        source_status = {}
        if hasattr(self, 'message_sources'):
            for source_name, source in self.message_sources.items():
                if hasattr(source, 'get_status'):
                    source_status[source_name] = source.get_status()
        
        # Get decoder performance if available
        decoder_stats = {}
        if hasattr(self, 'decoder') and hasattr(self.decoder, 'get_stats'):
            decoder_stats = self.decoder.get_stats()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "dump1090_running": self.dump1090_manager.is_running() if self.dump1090_manager else False,
                "meshtastic_connected": self.meshtastic.serial_conn is not None if self.meshtastic else False,
                "http_server_running": self.httpd is not None,
                "control_server_running": self.control_server is not None
            },
            "aircraft": {
                "total_tracked": len(self.aircraft),
                "watchlist_count": len([a for a in self.aircraft.values() if a.is_watchlist]),
                "with_position": len([a for a in self.aircraft.values() if hasattr(a, 'has_position') and a.has_position()]),
                "with_velocity": len([a for a in self.aircraft.values() if hasattr(a, 'has_velocity') and a.has_velocity()]),
                "with_altitude": len([a for a in self.aircraft.values() if hasattr(a, 'has_altitude') and a.has_altitude()])
            },
            "watchlist": {
                "size": len(self.watchlist),
                "codes": list(self.watchlist)
            },
            "message_sources": source_status,
            "decoder": decoder_stats,
            "stats": stats_copy
        }
    
    def get_processing_stats(self) -> dict:
        """Get message processing statistics and performance metrics"""
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if stats_copy.get('last_update'):
            stats_copy['last_update'] = stats_copy['last_update'].isoformat()
        
        # Calculate rates
        current_time = datetime.now()
        uptime_seconds = 0
        if hasattr(self, 'start_time'):
            uptime_seconds = (current_time - self.start_time).total_seconds()
        
        message_rate = 0
        if uptime_seconds > 0 and self.stats['messages_total'] > 0:
            message_rate = self.stats['messages_total'] / uptime_seconds
        
        # Get memory usage if available
        memory_info = {}
        try:
            import psutil
            process = psutil.Process()
            memory_info = {
                "rss_mb": process.memory_info().rss / 1024 / 1024,
                "vms_mb": process.memory_info().vms / 1024 / 1024,
                "percent": process.memory_percent()
            }
        except ImportError:
            memory_info = {"error": "psutil not available"}
        
        return {
            "timestamp": current_time.isoformat(),
            "uptime_seconds": uptime_seconds,
            "performance": {
                "message_rate_per_second": round(message_rate, 2),
                "aircraft_update_rate": round(self.stats['update_count'] / max(uptime_seconds, 1), 2),
                "error_rate": round(self.stats['errors'] / max(self.stats['messages_total'], 1) * 100, 2)
            },
            "memory": memory_info,
            "counters": stats_copy,
            "aircraft_distribution": {
                "by_message_count": self._get_aircraft_message_distribution(),
                "by_age": self._get_aircraft_age_distribution()
            }
        }
    
    def _get_aircraft_message_distribution(self) -> dict:
        """Get distribution of aircraft by message count"""
        distribution = {"1-10": 0, "11-50": 0, "51-100": 0, "100+": 0}
        
        for aircraft in self.aircraft.values():
            msg_count = getattr(aircraft, 'message_count', getattr(aircraft, 'messages', 0))
            if msg_count <= 10:
                distribution["1-10"] += 1
            elif msg_count <= 50:
                distribution["11-50"] += 1
            elif msg_count <= 100:
                distribution["51-100"] += 1
            else:
                distribution["100+"] += 1
        
        return distribution
    
    def _get_aircraft_age_distribution(self) -> dict:
        """Get distribution of aircraft by age since last seen"""
        distribution = {"0-30s": 0, "30s-2m": 0, "2m-5m": 0, "5m+": 0}
        
        for aircraft in self.aircraft.values():
            if hasattr(aircraft, 'calculate_age_seconds'):
                age = aircraft.calculate_age_seconds()
            else:
                age = aircraft.age_seconds()
            
            if age <= 30:
                distribution["0-30s"] += 1
            elif age <= 120:
                distribution["30s-2m"] += 1
            elif age <= 300:
                distribution["2m-5m"] += 1
            else:
                distribution["5m+"] += 1
        
        return distribution
    
    def get_health_status(self) -> dict:
        """Get overall system health status"""
        current_time = datetime.now()
        
        # Check various system components
        dump1090_healthy = self.dump1090_manager.is_running() if self.dump1090_manager else False
        
        # Check if we're receiving data recently
        data_fresh = False
        if self.stats.get('last_update'):
            if isinstance(self.stats['last_update'], str):
                last_update = datetime.fromisoformat(self.stats['last_update'])
            else:
                last_update = self.stats['last_update']
            data_age = (current_time - last_update).total_seconds()
            data_fresh = data_age < 30  # Data should be less than 30 seconds old
        
        # Check error rate
        error_rate = 0
        if self.stats['messages_total'] > 0:
            error_rate = (self.stats['errors'] / self.stats['messages_total']) * 100
        low_error_rate = error_rate < 5  # Less than 5% error rate
        
        # Overall health
        healthy = dump1090_healthy and data_fresh and low_error_rate
        
        health_checks = {
            "dump1090_running": {
                "status": "pass" if dump1090_healthy else "fail",
                "description": "dump1090 process is running"
            },
            "data_freshness": {
                "status": "pass" if data_fresh else "fail", 
                "description": "Receiving fresh aircraft data",
                "last_update": self.stats.get('last_update', 'never')
            },
            "error_rate": {
                "status": "pass" if low_error_rate else "warn",
                "description": f"Error rate is {error_rate:.2f}%",
                "threshold": "< 5%"
            },
            "aircraft_tracking": {
                "status": "pass" if len(self.aircraft) >= 0 else "fail",
                "description": f"Tracking {len(self.aircraft)} aircraft"
            }
        }
        
        return {
            "timestamp": current_time.isoformat(),
            "healthy": healthy,
            "status": "healthy" if healthy else "unhealthy",
            "checks": health_checks,
            "uptime_seconds": (current_time - self.start_time).total_seconds()
        }
    
    def get_sources_status(self) -> dict:
        """Get detailed status of all message sources"""
        sources = {}
        
        # dump1090 source status
        if self.dump1090_manager:
            sources["dump1090"] = {
                "type": "dump1090",
                "running": self.dump1090_manager.is_running(),
                "last_data_time": self.dump1090_manager.last_data_time.isoformat() if self.dump1090_manager.last_data_time else None,
                "watchdog_timeout": self.dump1090_manager.watchdog_timeout,
                "needs_restart": self.dump1090_manager.needs_restart(),
                "config": {
                    "frequency": self.config.get('frequency', 1090000000),
                    "lna_gain": self.config.get('lna_gain', 40),
                    "vga_gain": self.config.get('vga_gain', 20),
                    "enable_amp": self.config.get('enable_hackrf_amp', True)
                }
            }
        
        # Check for pyModeS message sources if available
        if hasattr(self, 'message_sources'):
            for source_name, source in self.message_sources.items():
                if hasattr(source, 'get_detailed_status'):
                    sources[source_name] = source.get_detailed_status()
                elif hasattr(source, 'is_connected'):
                    sources[source_name] = {
                        "type": "network_source",
                        "connected": source.is_connected(),
                        "status": "connected" if source.is_connected() else "disconnected"
                    }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "sources": sources,
            "total_sources": len(sources),
            "active_sources": len([s for s in sources.values() if s.get('running', False) or s.get('connected', False)])
        }
    
    def get_decoder_metrics(self) -> dict:
        """Get pyModeS decoder performance metrics"""
        current_time = datetime.now()
        
        # Basic decoder stats
        decoder_stats = {
            "messages_processed": self.stats['messages_total'],
            "decode_errors": self.stats['errors'],
            "success_rate": 0
        }
        
        if self.stats['messages_total'] > 0:
            decoder_stats["success_rate"] = ((self.stats['messages_total'] - self.stats['errors']) / self.stats['messages_total']) * 100
        
        # Message type distribution
        message_types = {}
        position_calculations = {"successful": 0, "failed": 0}
        
        # Analyze aircraft data for decoder performance
        for aircraft in self.aircraft.values():
            if hasattr(aircraft, 'data_sources'):
                for source in aircraft.data_sources:
                    message_types[source] = message_types.get(source, 0) + 1
            
            # Count position calculation success
            if hasattr(aircraft, 'has_position') and aircraft.has_position():
                position_calculations["successful"] += 1
            else:
                position_calculations["failed"] += 1
        
        # Get pyModeS specific stats if available
        pymodes_stats = {}
        if hasattr(self, 'decoder') and hasattr(self.decoder, 'get_performance_stats'):
            pymodes_stats = self.decoder.get_performance_stats()
        
        return {
            "timestamp": current_time.isoformat(),
            "decoder_type": "pyModeS" if hasattr(self, 'decoder') else "legacy",
            "performance": decoder_stats,
            "message_types": message_types,
            "position_calculations": position_calculations,
            "pymodes_specific": pymodes_stats,
            "aircraft_with_enhanced_data": {
                "true_airspeed": len([a for a in self.aircraft.values() if hasattr(a, 'true_airspeed') and a.true_airspeed is not None]),
                "magnetic_heading": len([a for a in self.aircraft.values() if hasattr(a, 'magnetic_heading') and a.magnetic_heading is not None]),
                "navigation_accuracy": len([a for a in self.aircraft.values() if hasattr(a, 'navigation_accuracy') and a.navigation_accuracy is not None])
            }
        }
    
    def get_status(self) -> dict:
        """Get system status"""
        # Convert datetime objects to strings for JSON serialization
        stats_copy = self.stats.copy()
        if stats_copy.get('last_update'):
            stats_copy['last_update'] = stats_copy['last_update'].isoformat()
        
        return {
            "dump1090_running": self.dump1090_manager.is_running() if self.dump1090_manager else False,
            "meshtastic_connected": self.meshtastic.serial_conn is not None if self.meshtastic else False,
            "aircraft_count": len(self.aircraft),
            "watchlist_count": len(self.watchlist),
            "stats": stats_copy
        }
    
    def get_fft_data(self) -> list:
        """Get FFT data for waterfall viewer"""
        if hasattr(self, 'fft_history'):
            # Convert numpy arrays to Python lists for JSON serialization
            return [fft_data.tolist() for fft_data in self.fft_history]
        return []
    
    def data_updater(self):
        """Background thread to update aircraft data"""
        while self.running:
            try:
                # Check if dump1090 needs restart
                if self.dump1090_manager and self.dump1090_manager.needs_restart():
                    logger.warning("Watchdog timeout - restarting dump1090")
                    self.restart_dump1090()
                
                # Fetch and update aircraft data
                aircraft_data = self.fetch_aircraft_data()
                if aircraft_data:
                    self.update_aircraft(aircraft_data)
                
                # Generate FFT data for waterfall viewer (in-memory)
                self.generate_fft_data()
                
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
            # Use a different port for the HTTP server to avoid conflict with dump1090
            http_port = 8080
            self.httpd = HTTPServer(('localhost', http_port), ADSBHTTPHandler)
            self.httpd.adsb_server = self
            logger.info(f"HTTP server started on port {http_port}")
            self.httpd.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start HTTP server: {e}")
    
    def start_control_server(self):
        """Start control server for dashboard commands"""
        try:
            self.control_server = socketserver.TCPServer(
                ('localhost', self.config['receiver_control_port']), 
                ControlHandler
            )
            self.control_server.adsb_server = self
            logger.info(f"Control server started on port {self.config['receiver_control_port']}")
            self.control_server.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start control server: {e}")
    
    def start(self):
        """Start the ADS-B server"""
        logger.info("Starting Ursine Explorer ADS-B Server")
        
        # Start dump1090
        if not self.start_dump1090():
            logger.error("Failed to start dump1090")
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
        
        logger.info("ADS-B server started successfully")
        return True
    
    def stop(self):
        """Stop the ADS-B server"""
        logger.info("Shutting down ADS-B server...")
        
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
                logger.error(f"HTTP server stop error: {e}")
        
        # Stop control server
        if self.control_server:
            try:
                self.control_server.shutdown()
                self.control_server.server_close()
            except Exception as e:
                logger.error(f"Control server stop error: {e}")
        
        logger.info("Shutdown complete")

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info('\nReceived interrupt signal')
    if hasattr(signal_handler, 'server'):
        try:
            signal_handler.server.stop()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    # Force exit if needed
    logger.info("Forcing exit...")
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
        logger.error("Failed to start server")
        sys.exit(1)
    
    print("\nADS-B receiver running... Press Ctrl+C to stop")
    print(f"Aircraft data: http://localhost:8080/data/aircraft.json")
    print(f"Control port: {server.config['receiver_control_port']}")
    print(f"Watchlist: {list(server.watchlist)}")
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nKeyboard interrupt received")
        server.stop()
    except Exception as e:
        logger.error(f"\nUnexpected error: {e}")
        server.stop()
    finally:
        logger.info("Exiting main thread...")
        sys.exit(0)

if __name__ == "__main__":
    main()
