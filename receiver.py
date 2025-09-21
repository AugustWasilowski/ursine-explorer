#!/usr/bin/env python3
"""
Core ADS-B reception, decoding, and Meshtastic integration for Ursine Capture.
"""

import json
import logging
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from threading import Thread, Event
from typing import Dict, Any, Optional

from utils import (setup_logging, check_process_running, kill_process, run_command,
                  error_handler, ErrorSeverity, ComponentType, handle_exception, safe_execute)
from config import Config, RadioConfig, ReceiverConfig
from aircraft import AircraftTracker


logger = logging.getLogger(__name__)


class Dump1090Manager:
    """Manages dump1090 process and HackRF configuration."""
    
    def __init__(self, config: Config):
        self.config = config
        self.receiver_config = config.get_receiver_config()
        self.radio_config = config.get_radio_config()
        self.dump1090_process = None
        self.hackrf_connected = False
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        
        # Register for configuration updates
        self.config.register_reload_callback(self._on_config_reload)
        
    def start_dump1090(self) -> bool:
        """Start dump1090 process if not already running."""
        try:
            if self.is_running():
                logger.info("dump1090 is already running")
                return True
                
            logger.info("Starting dump1090...")
            
            # Configure HackRF first
            if not self.configure_hackrf():
                error_handler.handle_error(
                    ComponentType.HACKRF,
                    ErrorSeverity.HIGH,
                    "HackRF configuration failed, cannot start dump1090",
                    error_code="HACKRF_CONFIG_FAILED"
                )
                return False
            
            # Validate radio settings before starting
            if not self._validate_radio_settings():
                error_handler.handle_error(
                    ComponentType.DUMP1090,
                    ErrorSeverity.HIGH,
                    "Invalid radio settings, cannot start dump1090",
                    error_code="INVALID_RADIO_SETTINGS"
                )
                return False
            
            # Build dump1090 command with current settings
            cmd = self._build_dump1090_command()
            
            # Start dump1090 as a subprocess for better control
            try:
                import subprocess
                self.dump1090_process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                
                # Give it time to start and check if it's running
                time.sleep(3)
                
                if self.dump1090_process.poll() is None:
                    logger.info("dump1090 started successfully")
                    return True
                else:
                    # Process exited, get error output
                    _, stderr = self.dump1090_process.communicate()
                    error_handler.handle_error(
                        ComponentType.DUMP1090,
                        ErrorSeverity.CRITICAL,
                        f"dump1090 failed to start: {stderr}",
                        error_code="DUMP1090_START_FAILED",
                        details=f"Command: {' '.join(cmd)}"
                    )
                    self.dump1090_process = None
                    return False
                    
            except Exception as e:
                error_handler.handle_error(
                    ComponentType.DUMP1090,
                    ErrorSeverity.CRITICAL,
                    f"Failed to start dump1090 subprocess: {str(e)}",
                    error_code="SUBPROCESS_ERROR",
                    details=f"Command: {' '.join(cmd)}"
                )
                return False
                
        except Exception as e:
            error_handler.handle_error(
                ComponentType.DUMP1090,
                ErrorSeverity.CRITICAL,
                f"Unexpected error starting dump1090: {str(e)}",
                error_code="UNEXPECTED_ERROR"
            )
            return False
    
    def stop_dump1090(self) -> None:
        """Stop dump1090 process."""
        try:
            # Stop our managed process first
            if self.dump1090_process:
                try:
                    self.dump1090_process.terminate()
                    self.dump1090_process.wait(timeout=5)
                    logger.info("dump1090 process terminated")
                except subprocess.TimeoutExpired:
                    self.dump1090_process.kill()
                    logger.info("dump1090 process killed")
                except Exception as e:
                    logger.error(f"Error stopping dump1090 process: {e}")
                finally:
                    self.dump1090_process = None
            
            # Also kill any other dump1090 processes
            if kill_process("dump1090"):
                logger.info("Additional dump1090 processes stopped")
                
        except Exception as e:
            logger.error(f"Error stopping dump1090: {e}")
    
    def is_running(self) -> bool:
        """Check if dump1090 is currently running."""
        try:
            # Check our managed process first
            if self.dump1090_process and self.dump1090_process.poll() is None:
                return True
            
            # Check for any dump1090 processes
            return check_process_running("dump1090")
            
        except Exception as e:
            logger.error(f"Error checking dump1090 status: {e}")
            return False
    
    def configure_hackrf(self) -> bool:
        """Configure HackRF settings with current radio configuration."""
        try:
            logger.info("Configuring HackRF...")
            
            # Get current radio settings
            radio_config = self.config.get_radio_config()
            
            # Check if HackRF is connected
            success, stdout, stderr = run_command(["hackrf_info"], timeout=10)
            if not success:
                error_handler.handle_error(
                    ComponentType.HACKRF,
                    ErrorSeverity.HIGH,
                    f"HackRF not detected: {stderr}",
                    error_code="HACKRF_NOT_DETECTED",
                    details=f"Command output: {stderr}"
                )
                self.hackrf_connected = False
                return False
            
            logger.info("HackRF detected")
            logger.debug(f"HackRF info: {stdout}")
            
            # Apply radio settings using hackrf_transfer (if available)
            # Note: dump1090 will handle most settings, but we can validate them here
            if not self._validate_hackrf_settings(radio_config):
                error_handler.handle_error(
                    ComponentType.HACKRF,
                    ErrorSeverity.HIGH,
                    "Invalid HackRF settings",
                    error_code="INVALID_HACKRF_SETTINGS",
                    details=f"Freq: {radio_config.frequency}, LNA: {radio_config.lna_gain}, VGA: {radio_config.vga_gain}"
                )
                self.hackrf_connected = False
                return False
            
            self.hackrf_connected = True
            logger.info(f"HackRF configured - Freq: {radio_config.frequency}Hz, "
                       f"LNA: {radio_config.lna_gain}dB, VGA: {radio_config.vga_gain}dB")
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.HACKRF,
                ErrorSeverity.HIGH,
                f"Error configuring HackRF: {str(e)}",
                error_code="HACKRF_CONFIG_ERROR"
            )
            self.hackrf_connected = False
            return False
    
    def apply_radio_settings(self, radio_config: RadioConfig) -> bool:
        """Apply new radio settings, restarting dump1090 if necessary."""
        try:
            logger.info("Applying new radio settings...")
            
            # Validate new settings
            if not self._validate_hackrf_settings(radio_config):
                logger.error("Invalid radio settings, cannot apply")
                return False
            
            # Update configuration
            config_data = self.config.load()
            config_data['radio'] = {
                'frequency': radio_config.frequency,
                'lna_gain': radio_config.lna_gain,
                'vga_gain': radio_config.vga_gain,
                'enable_amp': radio_config.enable_amp
            }
            
            if not self.config.validate(config_data):
                logger.error("Configuration validation failed")
                return False
            
            self.config.save(config_data)
            
            # Restart dump1090 with new settings
            was_running = self.is_running()
            if was_running:
                logger.info("Restarting dump1090 with new settings...")
                self.stop_dump1090()
                time.sleep(2)
            
            # Update our cached config
            self.radio_config = radio_config
            
            # Start with new settings if it was running before
            if was_running:
                return self.start_dump1090()
            else:
                # Just configure HackRF if dump1090 wasn't running
                return self.configure_hackrf()
                
        except Exception as e:
            logger.error(f"Error applying radio settings: {e}")
            return False
    
    def get_health_status(self) -> dict:
        """Get comprehensive health status of dump1090 and HackRF."""
        try:
            current_time = time.time()
            
            # Only do expensive checks periodically
            if current_time - self.last_health_check > self.health_check_interval:
                self._perform_health_check()
                self.last_health_check = current_time
            
            return {
                'dump1090_running': self.is_running(),
                'hackrf_connected': self.hackrf_connected,
                'radio_frequency': self.radio_config.frequency,
                'lna_gain': self.radio_config.lna_gain,
                'vga_gain': self.radio_config.vga_gain,
                'amp_enabled': self.radio_config.enable_amp,
                'last_health_check': self.last_health_check
            }
            
        except Exception as e:
            logger.error(f"Error getting health status: {e}")
            return {
                'dump1090_running': False,
                'hackrf_connected': False,
                'error': str(e)
            }
    
    def restart_if_needed(self) -> bool:
        """Check health and restart dump1090 if needed with comprehensive error handling."""
        try:
            if not self.is_running():
                error_handler.handle_error(
                    ComponentType.DUMP1090,
                    ErrorSeverity.HIGH,
                    "dump1090 not running, attempting restart",
                    error_code="DUMP1090_NOT_RUNNING"
                )
                return self.start_dump1090()
            
            # Check if HackRF is still connected
            if not self.hackrf_connected:
                error_handler.handle_error(
                    ComponentType.HACKRF,
                    ErrorSeverity.HIGH,
                    "HackRF disconnected, attempting reconfiguration",
                    error_code="HACKRF_DISCONNECTED"
                )
                
                if self.configure_hackrf():
                    logger.info("HackRF reconfiguration successful")
                    return True
                else:
                    # Try restarting dump1090
                    error_handler.handle_error(
                        ComponentType.HACKRF,
                        ErrorSeverity.CRITICAL,
                        "HackRF reconfiguration failed, restarting dump1090",
                        error_code="HACKRF_RECONFIG_FAILED"
                    )
                    self.stop_dump1090()
                    time.sleep(2)
                    return self.start_dump1090()
            
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.DUMP1090,
                ErrorSeverity.HIGH,
                f"Error in restart_if_needed: {str(e)}",
                error_code="RESTART_ERROR"
            )
            return False
    
    def _build_dump1090_command(self) -> list:
        """Build dump1090 command line with current settings."""
        cmd = [
            self.receiver_config.dump1090_path,
            "--device-type", "hackrf",
            "--gain", str(self.radio_config.lna_gain),
            "--freq", str(self.radio_config.frequency),
            "--net",
            "--net-sbs-port", "30003",
            "--net-bi-port", "30005",
            "--quiet"
        ]
        
        # Add VGA gain if supported
        if hasattr(self.radio_config, 'vga_gain'):
            cmd.extend(["--vga-gain", str(self.radio_config.vga_gain)])
        
        # Add amp enable if supported and enabled
        if self.radio_config.enable_amp:
            cmd.append("--enable-amp")
        
        return cmd
    
    def _validate_radio_settings(self) -> bool:
        """Validate current radio settings."""
        try:
            from utils import validate_frequency, validate_gain
            
            if not validate_frequency(self.radio_config.frequency):
                logger.error(f"Invalid frequency: {self.radio_config.frequency}")
                return False
            
            if not validate_gain(self.radio_config.lna_gain):
                logger.error(f"Invalid LNA gain: {self.radio_config.lna_gain}")
                return False
            
            if not validate_gain(self.radio_config.vga_gain):
                logger.error(f"Invalid VGA gain: {self.radio_config.vga_gain}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating radio settings: {e}")
            return False
    
    def _validate_hackrf_settings(self, radio_config: RadioConfig) -> bool:
        """Validate HackRF-specific settings."""
        try:
            from utils import validate_frequency, validate_gain
            
            # Validate frequency range for HackRF
            if not (1000000 <= radio_config.frequency <= 6000000000):
                logger.error(f"Frequency {radio_config.frequency} outside HackRF range")
                return False
            
            # Validate gain ranges for HackRF
            if not (0 <= radio_config.lna_gain <= 40):
                logger.error(f"LNA gain {radio_config.lna_gain} outside HackRF range (0-40)")
                return False
            
            if not (0 <= radio_config.vga_gain <= 62):
                logger.error(f"VGA gain {radio_config.vga_gain} outside HackRF range (0-62)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating HackRF settings: {e}")
            return False
    
    def _perform_health_check(self) -> None:
        """Perform periodic health check of HackRF."""
        try:
            # Check HackRF connection
            success, stdout, stderr = run_command(["hackrf_info"], timeout=5)
            if success:
                self.hackrf_connected = True
            else:
                logger.warning(f"HackRF health check failed: {stderr}")
                self.hackrf_connected = False
                
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            self.hackrf_connected = False
    
    def _on_config_reload(self, new_config: dict) -> None:
        """Handle configuration reload events."""
        try:
            # Update radio config if it changed
            new_radio_config = RadioConfig(**new_config.get('radio', {}))
            
            if (new_radio_config.frequency != self.radio_config.frequency or
                new_radio_config.lna_gain != self.radio_config.lna_gain or
                new_radio_config.vga_gain != self.radio_config.vga_gain or
                new_radio_config.enable_amp != self.radio_config.enable_amp):
                
                logger.info("Radio configuration changed, applying new settings...")
                self.apply_radio_settings(new_radio_config)
            
            # Update receiver config
            self.receiver_config = ReceiverConfig(**new_config.get('receiver', {}))
            
        except Exception as e:
            logger.error(f"Error handling config reload: {e}")
    
    def __del__(self):
        """Cleanup when manager is destroyed."""
        try:
            self.config.unregister_reload_callback(self._on_config_reload)
            if self.dump1090_process:
                self.dump1090_process.terminate()
        except:
            pass


class MeshtasticManager:
    """Manages Meshtastic device communication."""
    
    def __init__(self, config: Config):
        self.config = config
        self.meshtastic_config = config.get_meshtastic_config()
        self.serial_connection = None
        self.connected = False
        self.last_connection_attempt = 0
        self.connection_retry_delay = 5  # seconds
        self.max_retry_delay = 60  # seconds
        self.retry_count = 0
        self.max_retries = 10
        
        # Message queue for offline periods
        self.message_queue = []
        self.max_queue_size = 100
        
        # Health monitoring
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        self.last_successful_send = 0
        
        # Alert throttling
        self.last_alert_times = {}  # icao -> timestamp
        self.alert_cooldown = 300  # 5 minutes between alerts for same aircraft
        
    def connect(self, port: str = None) -> bool:
        """Connect to Meshtastic device with comprehensive error handling."""
        try:
            port = port or self.meshtastic_config.port
            current_time = time.time()
            
            # Check if we should retry connection
            if (current_time - self.last_connection_attempt < self.connection_retry_delay and 
                self.retry_count > 0):
                return False
                
            self.last_connection_attempt = current_time
            logger.info(f"Connecting to Meshtastic device on {port}...")
            
            # Close existing connection if any
            self.disconnect()
            
            # Import serial library
            try:
                import serial
            except ImportError:
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.CRITICAL,
                    "pyserial not installed. Run: pip install pyserial",
                    error_code="MISSING_DEPENDENCY"
                )
                return False
            
            # Attempt serial connection
            try:
                self.serial_connection = serial.Serial(
                    port=port,
                    baudrate=self.meshtastic_config.baud,
                    timeout=2.0,
                    write_timeout=2.0
                )
                
                # Test connection with a simple command
                if self._test_connection():
                    self.connected = True
                    self.retry_count = 0
                    self.connection_retry_delay = 5  # Reset delay
                    logger.info(f"Meshtastic connected on {port}")
                    
                    # Send boot message
                    self.send_boot_message()
                    
                    # Process any queued messages
                    self._process_message_queue()
                    
                    return True
                else:
                    error_handler.handle_error(
                        ComponentType.MESHTASTIC,
                        ErrorSeverity.HIGH,
                        "Meshtastic device not responding",
                        error_code="DEVICE_NOT_RESPONDING",
                        details=f"Port: {port}, Baud: {self.meshtastic_config.baud}"
                    )
                    self.disconnect()
                    
            except serial.SerialException as e:
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.HIGH,
                    f"Serial connection failed: {str(e)}",
                    error_code="SERIAL_CONNECTION_FAILED",
                    details=f"Port: {port}, Baud: {self.meshtastic_config.baud}"
                )
            except Exception as e:
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.HIGH,
                    f"Unexpected error connecting to Meshtastic: {str(e)}",
                    error_code="UNEXPECTED_CONNECTION_ERROR"
                )
                
            # Connection failed, update retry logic
            self.retry_count += 1
            if self.retry_count < self.max_retries:
                # Exponential backoff
                self.connection_retry_delay = min(
                    self.connection_retry_delay * 1.5,
                    self.max_retry_delay
                )
                logger.info(f"Will retry Meshtastic connection in {self.connection_retry_delay:.1f} seconds "
                           f"(attempt {self.retry_count}/{self.max_retries})")
            else:
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.CRITICAL,
                    f"Max Meshtastic connection retries ({self.max_retries}) exceeded",
                    error_code="MAX_RETRIES_EXCEEDED",
                    details=f"Port: {port}, Attempts: {self.retry_count}"
                )
                
            return False
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.MESHTASTIC,
                ErrorSeverity.HIGH,
                f"Error connecting to Meshtastic: {str(e)}",
                error_code="CONNECTION_ERROR"
            )
            self.connected = False
            return False
    
    def disconnect(self) -> None:
        """Disconnect from Meshtastic device."""
        try:
            if self.serial_connection:
                self.serial_connection.close()
                self.serial_connection = None
            self.connected = False
            logger.info("Meshtastic disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting Meshtastic: {e}")
    
    def send_message(self, message: str, channel: int = None) -> bool:
        """Send message to Meshtastic network."""
        try:
            if not self.connected or not self.serial_connection:
                # Queue message for later if offline
                self._queue_message(message)
                logger.warning("Meshtastic not connected, message queued")
                return False
                
            channel = channel or self.meshtastic_config.channel
            
            # Format message for Meshtastic
            formatted_message = self._format_message(message)
            
            # Send via serial connection
            if self._send_serial_message(formatted_message, channel):
                self.last_successful_send = time.time()
                logger.info(f"Meshtastic message sent to channel {channel}: {message}")
                return True
            else:
                # Send failed, queue message and try to reconnect
                self._queue_message(message)
                self.connected = False
                logger.warning("Meshtastic send failed, message queued")
                return False
                
        except Exception as e:
            logger.error(f"Error sending Meshtastic message: {e}")
            self._queue_message(message)
            return False
    
    def send_alert(self, aircraft_data: dict) -> bool:
        """Send watchlist aircraft alert with throttling."""
        try:
            icao = aircraft_data.get('icao', 'UNKNOWN')
            current_time = time.time()
            
            # Check alert throttling
            if icao in self.last_alert_times:
                time_since_last = current_time - self.last_alert_times[icao]
                if time_since_last < self.alert_cooldown:
                    logger.debug(f"Alert for {icao} throttled (last sent {time_since_last:.0f}s ago)")
                    return False
            
            # Format alert message
            alert_message = self._format_alert_message(aircraft_data)
            
            # Send alert
            if self.send_message(alert_message):
                self.last_alert_times[icao] = current_time
                logger.info(f"Watchlist alert sent for {icao}")
                return True
            else:
                logger.warning(f"Failed to send watchlist alert for {icao}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending alert: {e}")
            return False
    
    def send_boot_message(self) -> bool:
        """Send boot notification message."""
        try:
            boot_msg = f"Ursine Capture started at {datetime.now().strftime('%H:%M:%S')}"
            return self.send_message(boot_msg)
        except Exception as e:
            logger.error(f"Error sending boot message: {e}")
            return False
    
    def is_connected(self) -> bool:
        """Check if Meshtastic device is connected."""
        return self.connected and self.serial_connection is not None
    
    def get_health_status(self) -> dict:
        """Get Meshtastic connection health status."""
        try:
            current_time = time.time()
            
            # Perform periodic health check
            if current_time - self.last_health_check > self.health_check_interval:
                self._perform_health_check()
                self.last_health_check = current_time
            
            return {
                'connected': self.connected,
                'port': self.meshtastic_config.port,
                'baud': self.meshtastic_config.baud,
                'channel': self.meshtastic_config.channel,
                'queued_messages': len(self.message_queue),
                'retry_count': self.retry_count,
                'last_successful_send': self.last_successful_send,
                'connection_attempts': self.retry_count
            }
            
        except Exception as e:
            logger.error(f"Error getting Meshtastic health status: {e}")
            return {'connected': False, 'error': str(e)}
    
    def reconnect_if_needed(self) -> bool:
        """Check connection and reconnect if needed with error handling."""
        try:
            if not self.is_connected():
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.MEDIUM,
                    "Meshtastic disconnected, attempting reconnection",
                    error_code="DISCONNECTED"
                )
                return self.connect()
            
            # Test connection health
            if not self._test_connection():
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.MEDIUM,
                    "Meshtastic connection unhealthy, reconnecting",
                    error_code="CONNECTION_UNHEALTHY"
                )
                return self.connect()
                
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.MESHTASTIC,
                ErrorSeverity.HIGH,
                f"Error in Meshtastic reconnect: {str(e)}",
                error_code="RECONNECT_ERROR"
            )
            return False
    
    def _test_connection(self) -> bool:
        """Test if Meshtastic connection is working."""
        try:
            if not self.serial_connection:
                return False
                
            # Simple test - check if port is open and responsive
            if not self.serial_connection.is_open:
                return False
                
            # Try to write a simple command (this is device-specific)
            # For now, just check if we can write to the port
            try:
                self.serial_connection.write(b'\n')
                self.serial_connection.flush()
                return True
            except:
                return False
                
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False
    
    def _send_serial_message(self, message: str, channel: int) -> bool:
        """Send message via serial connection."""
        try:
            if not self.serial_connection or not self.serial_connection.is_open:
                return False
            
            # Format command for Meshtastic device
            # This is a simplified implementation - actual Meshtastic protocol may differ
            command = f"--ch {channel} --sendtext \"{message}\"\n"
            
            self.serial_connection.write(command.encode('utf-8'))
            self.serial_connection.flush()
            
            # Wait for acknowledgment (simplified)
            time.sleep(0.1)
            
            return True
            
        except Exception as e:
            logger.error(f"Serial send error: {e}")
            return False
    
    def _format_message(self, message: str) -> str:
        """Format message for Meshtastic transmission."""
        try:
            # Add timestamp if configured
            if hasattr(self.meshtastic_config, 'include_timestamp'):
                timestamp = datetime.now().strftime('%H:%M')
                formatted = f"[{timestamp}] {message}"
            else:
                formatted = message
            
            # Truncate if too long
            max_length = getattr(self.meshtastic_config, 'max_message_length', 200)
            if len(formatted) > max_length:
                formatted = formatted[:max_length-3] + "..."
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error formatting message: {e}")
            return message
    
    def _format_alert_message(self, aircraft_data: dict) -> str:
        """Format enhanced watchlist alert message."""
        try:
            icao = aircraft_data.get('icao', 'UNKNOWN')
            callsign = aircraft_data.get('callsign', 'N/A')
            altitude = aircraft_data.get('altitude')
            watchlist_name = aircraft_data.get('watchlist_name', '')
            alert_type = aircraft_data.get('alert_type', 'ALERT')
            distance_info = aircraft_data.get('distance_info', '')
            bearing_info = aircraft_data.get('bearing_info', '')
            alert_count = aircraft_data.get('alert_count', 1)
            
            # Build enhanced alert message
            parts = [f"{alert_type}: {icao}"]
            
            # Add callsign or watchlist name
            if callsign and callsign != 'N/A':
                parts.append(f"({callsign})")
            elif watchlist_name:
                parts.append(f"({watchlist_name})")
            
            # Add altitude
            if altitude:
                parts.append(f"Alt:{altitude}ft")
            
            # Add distance and bearing if available
            if distance_info and bearing_info:
                parts.append(f"{distance_info}{bearing_info}")
            elif distance_info:
                parts.append(distance_info)
            
            # Add alert count for repeat alerts
            if alert_count > 1:
                parts.append(f"#{alert_count}")
            
            return " ".join(parts)
            
        except Exception as e:
            logger.error(f"Error formatting alert message: {e}")
            return f"ALERT: {aircraft_data.get('icao', 'UNKNOWN')}"
    
    def _queue_message(self, message: str) -> None:
        """Queue message for sending when connection is restored."""
        try:
            if len(self.message_queue) >= self.max_queue_size:
                # Remove oldest message
                self.message_queue.pop(0)
                logger.warning("Message queue full, removed oldest message")
            
            self.message_queue.append({
                'message': message,
                'timestamp': datetime.now(),
                'attempts': 0
            })
            
        except Exception as e:
            logger.error(f"Error queuing message: {e}")
    
    def _process_message_queue(self) -> None:
        """Process queued messages when connection is restored."""
        try:
            if not self.message_queue:
                return
                
            logger.info(f"Processing {len(self.message_queue)} queued messages...")
            
            processed = 0
            failed = []
            
            for queued_msg in self.message_queue[:]:  # Copy list to avoid modification during iteration
                try:
                    if self._send_serial_message(queued_msg['message'], self.meshtastic_config.channel):
                        processed += 1
                        self.message_queue.remove(queued_msg)
                        time.sleep(0.1)  # Small delay between messages
                    else:
                        queued_msg['attempts'] += 1
                        if queued_msg['attempts'] >= 3:
                            failed.append(queued_msg)
                            self.message_queue.remove(queued_msg)
                        
                except Exception as e:
                    logger.error(f"Error processing queued message: {e}")
                    failed.append(queued_msg)
                    self.message_queue.remove(queued_msg)
            
            if processed > 0:
                logger.info(f"Processed {processed} queued messages")
            
            if failed:
                logger.warning(f"Failed to send {len(failed)} queued messages")
                
        except Exception as e:
            logger.error(f"Error processing message queue: {e}")
    
    def _perform_health_check(self) -> None:
        """Perform periodic health check."""
        try:
            if self.connected and self.serial_connection:
                # Test connection
                if not self._test_connection():
                    logger.warning("Meshtastic health check failed")
                    self.connected = False
                    
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            self.connected = False
    
    def __del__(self):
        """Cleanup when manager is destroyed."""
        try:
            self.disconnect()
        except:
            pass


class ADSBReceiver:
    """Main ADS-B receiver class integrating all components."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.aircraft_tracker = AircraftTracker()
        self.dump1090_manager = Dump1090Manager(self.config)
        self.meshtastic_manager = MeshtasticManager(self.config)
        
        self.running = False
        self.stop_event = Event()
        
        # Statistics
        self.message_count = 0
        self.valid_message_count = 0
        self.error_count = 0
        self.start_time = datetime.now()
        self.last_message_time = datetime.now()
        
        # Message rate tracking
        self.message_rate_window = []
        self.rate_window_size = 60  # Track rate over 60 seconds
        
        # Position message cache for CPR decoding
        self.position_cache = {}  # icao -> [even_msg, odd_msg]
        self.position_cache_timeout = 10  # seconds
        
    def start(self) -> None:
        """Start the receiver system."""
        try:
            logger.info("Starting Ursine Capture receiver...")
            
            # Load configuration
            config_data = self.config.load()
            if not self.config.validate(config_data):
                logger.error("Invalid configuration, cannot start")
                return
                
            # Start configuration file watching for hot-reload
            self.config.start_watching()
            
            # Register callback for configuration changes
            self.config.register_reload_callback(self._on_config_reload)
                
            # Update watchlist
            watchlist = self.config.get_watchlist()
            self.aircraft_tracker.update_watchlist(watchlist)
            
            # Start dump1090 with enhanced management
            if not self.dump1090_manager.start_dump1090():
                logger.error("Failed to start dump1090")
                return
                
            # Connect to Meshtastic
            if not self.meshtastic_manager.connect():
                logger.warning("Meshtastic connection failed, continuing without alerts")
            
            # Start processing
            self.running = True
            
            # Start background threads
            processing_thread = Thread(target=self.process_messages, daemon=True)
            status_thread = Thread(target=self.update_status, daemon=True)
            cleanup_thread = Thread(target=self.cleanup_loop, daemon=True)
            health_thread = Thread(target=self.health_monitor_loop, daemon=True)
            
            processing_thread.start()
            status_thread.start()
            cleanup_thread.start()
            health_thread.start()
            
            logger.info("Receiver started successfully")
            
            # Main loop
            while self.running and not self.stop_event.is_set():
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        except Exception as e:
            logger.error(f"Error in receiver: {e}")
        finally:
            self.stop()
    
    def stop(self) -> None:
        """Stop the receiver system."""
        logger.info("Stopping receiver...")
        self.running = False
        self.stop_event.set()
        
        # Stop configuration watching and unregister callback
        self.config.unregister_reload_callback(self._on_config_reload)
        self.config.stop_watching()
        
        # Stop dump1090
        self.dump1090_manager.stop_dump1090()
        
        # Disconnect Meshtastic
        self.meshtastic_manager.disconnect()
        
        logger.info("Receiver stopped")
    
    def process_messages(self) -> None:
        """Process ADS-B messages from dump1090."""
        logger.info("Starting message processing...")
        
        connection_attempts = 0
        max_connection_attempts = 10
        
        while self.running and not self.stop_event.is_set():
            try:
                connection_attempts += 1
                
                # Check if dump1090 is running before attempting connection
                if not self.dump1090_manager.is_running():
                    logger.warning("dump1090 not running, attempting restart...")
                    if not self.dump1090_manager.start_dump1090():
                        logger.error("Failed to start dump1090, retrying in 10 seconds...")
                        time.sleep(10)
                        continue
                
                # Connect to dump1090 TCP stream
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(10.0)  # Longer timeout for connection
                    sock.connect(('localhost', 30005))
                    
                    logger.info(f"Connected to dump1090 data stream (attempt {connection_attempts})")
                    connection_attempts = 0  # Reset on successful connection
                    
                    # Set socket to non-blocking for better control
                    sock.settimeout(1.0)
                    
                    buffer = ""
                    last_data_time = datetime.now()
                    
                    while self.running and not self.stop_event.is_set():
                        try:
                            data = sock.recv(4096).decode('utf-8', errors='ignore')
                            if not data:
                                logger.warning("No data received from dump1090, connection closed")
                                break
                                
                            last_data_time = datetime.now()
                            buffer += data
                            lines = buffer.split('\n')
                            buffer = lines[-1]  # Keep incomplete line
                            
                            for line in lines[:-1]:
                                if line.strip():
                                    self.process_message_line(line.strip())
                                    
                        except socket.timeout:
                            # Check if we haven't received data for too long
                            if (datetime.now() - last_data_time).total_seconds() > 30:
                                logger.warning("No data received for 30 seconds, reconnecting...")
                                break
                            continue
                        except ConnectionResetError:
                            logger.warning("Connection reset by dump1090")
                            break
                        except Exception as e:
                            logger.error(f"Error processing data from dump1090: {e}")
                            break
                            
            except ConnectionRefusedError:
                logger.error("Connection refused by dump1090 (port 30005)")
                if connection_attempts >= max_connection_attempts:
                    logger.error(f"Failed to connect after {max_connection_attempts} attempts")
                    break
            except Exception as e:
                logger.error(f"Error connecting to dump1090: {e}")
                
            if self.running:
                # Exponential backoff for reconnection
                wait_time = min(30, 2 ** min(connection_attempts, 5))
                logger.info(f"Retrying connection in {wait_time} seconds...")
                time.sleep(wait_time)
        
        logger.info("Message processing stopped")
    
    def _decode_position(self, raw_message: str, icao: str, ref_lat: float, ref_lon: float) -> Optional[tuple]:
        """Decode position using multiple methods for better accuracy."""
        try:
            import pyModeS as pms
            
            # Method 1: Use reference position (local decoding)
            try:
                position = pms.adsb.position_with_ref(raw_message, ref_lat, ref_lon)
                if position and len(position) >= 2:
                    lat, lon = position[0], position[1]
                    # Validate coordinates
                    if -90 <= lat <= 90 and -180 <= lon <= 180:
                        return (lat, lon)
            except Exception as e:
                logger.debug(f"Reference position decoding failed: {e}")
            
            # Method 2: Try CPR decoding with cached messages
            try:
                # Get CPR format (even/odd)
                cpr_format = pms.adsb.oe_flag(raw_message)
                current_time = datetime.now()
                
                # Initialize cache for this aircraft if needed
                if icao not in self.position_cache:
                    self.position_cache[icao] = {'even': None, 'odd': None, 'time': current_time}
                
                # Store message in appropriate slot
                if cpr_format == 0:  # Even
                    self.position_cache[icao]['even'] = raw_message
                else:  # Odd
                    self.position_cache[icao]['odd'] = raw_message
                
                self.position_cache[icao]['time'] = current_time
                
                # Try to decode if we have both even and odd messages
                cache_entry = self.position_cache[icao]
                if (cache_entry['even'] and cache_entry['odd'] and
                    (current_time - cache_entry['time']).total_seconds() < self.position_cache_timeout):
                    
                    position = pms.adsb.position(cache_entry['even'], cache_entry['odd'], 0, 1)
                    if position and len(position) >= 2:
                        lat, lon = position[0], position[1]
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            return (lat, lon)
                            
            except Exception as e:
                logger.debug(f"CPR position decoding failed: {e}")
            
            return None
            
        except Exception as e:
            logger.debug(f"Position decoding error: {e}")
            return None
    
    def _cleanup_position_cache(self) -> None:
        """Clean up old entries from position cache."""
        try:
            current_time = datetime.now()
            expired_icaos = []
            
            for icao, cache_entry in self.position_cache.items():
                if (current_time - cache_entry['time']).total_seconds() > self.position_cache_timeout:
                    expired_icaos.append(icao)
            
            for icao in expired_icaos:
                del self.position_cache[icao]
                
        except Exception as e:
            logger.error(f"Error cleaning position cache: {e}")

    def _validate_raw_message(self, raw_message: str) -> bool:
        """Validate raw ADS-B message format and content."""
        try:
            # Check minimum length (14 hex chars = 7 bytes minimum)
            if len(raw_message) < 14:
                return False
                
            # Check maximum length (28 hex chars = 14 bytes maximum for ADS-B)
            if len(raw_message) > 28:
                return False
                
            # Validate hex format
            try:
                int(raw_message, 16)
            except ValueError:
                return False
                
            # Check if length is even (hex pairs)
            if len(raw_message) % 2 != 0:
                return False
                
            return True
            
        except Exception as e:
            logger.debug(f"Error validating message: {e}")
            return False

    def decode_adsb_message(self, raw_message: str) -> Optional[Dict[str, Any]]:
        """Decode ADS-B message using pyModeS and extract aircraft data."""
        try:
            # Import pyModeS for message decoding
            try:
                import pyModeS as pms
            except ImportError:
                logger.error("pyModeS not installed. Run: pip install pyModeS")
                return None
            
            # Validate message format
            if not pms.adsb.icao(raw_message):
                return None
                
            # Extract ICAO address
            icao = pms.adsb.icao(raw_message)
            if not icao:
                return None
                
            # Initialize decoded data
            decoded_data = {
                'icao': icao,
                'raw_message': raw_message,
                'message_type': None
            }
            
            # Determine message type
            typecode = pms.adsb.typecode(raw_message)
            decoded_data['message_type'] = typecode
            
            # Decode based on message type
            if 1 <= typecode <= 4:
                # Aircraft identification
                callsign = pms.adsb.callsign(raw_message)
                if callsign:
                    decoded_data['callsign'] = callsign.strip()
                    
            elif 5 <= typecode <= 8:
                # Surface position
                try:
                    # Need reference position for surface decoding
                    receiver_config = self.config.get_receiver_config()
                    ref_lat = receiver_config.reference_lat
                    ref_lon = receiver_config.reference_lon
                    
                    position = pms.adsb.position_with_ref(raw_message, ref_lat, ref_lon)
                    if position and len(position) >= 2:
                        lat, lon = position[0], position[1]
                        # Validate coordinates
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            decoded_data['latitude'] = lat
                            decoded_data['longitude'] = lon
                            # Surface aircraft have altitude 0
                            decoded_data['altitude'] = 0
                        else:
                            logger.debug(f"Invalid surface coordinates: {lat}, {lon}")
                        
                except Exception as e:
                    logger.debug(f"Error decoding surface position: {e}")
                    
            elif 9 <= typecode <= 18:
                # Airborne position
                try:
                    # Decode altitude first (always available)
                    altitude = pms.adsb.altitude(raw_message)
                    if altitude is not None:
                        decoded_data['altitude'] = altitude
                    
                    # Try to decode position with reference
                    receiver_config = self.config.get_receiver_config()
                    ref_lat = receiver_config.reference_lat
                    ref_lon = receiver_config.reference_lon
                    
                    # Try multiple position decoding methods
                    position = self._decode_position(raw_message, icao, ref_lat, ref_lon)
                    if position:
                        decoded_data['latitude'] = position[0]
                        decoded_data['longitude'] = position[1]
                            
                except Exception as e:
                    logger.debug(f"Error decoding airborne position: {e}")
                    
            elif typecode == 19:
                # Airborne velocity
                try:
                    velocity = pms.adsb.velocity(raw_message)
                    if velocity:
                        speed, track, vertical_rate, _ = velocity
                        if speed is not None:
                            decoded_data['speed'] = int(speed)
                        if track is not None:
                            decoded_data['track'] = int(track)
                        if vertical_rate is not None:
                            decoded_data['vertical_rate'] = int(vertical_rate)
                            
                except Exception as e:
                    logger.debug(f"Error decoding velocity: {e}")
                    
            # Try to decode squawk code if available
            try:
                # Note: Squawk is typically in Mode A/C messages, not ADS-B
                # But we'll check if pyModeS can extract it
                if hasattr(pms, 'commb') and hasattr(pms.commb, 'selalt40mcp'):
                    # This is a placeholder - actual squawk decoding depends on message type
                    pass
            except Exception:
                pass
                
            return decoded_data
            
        except Exception as e:
            logger.debug(f"Error decoding message {raw_message[:20]}...: {e}")
            return None

    def process_message_line(self, line: str) -> None:
        """Process a single message line from dump1090."""
        try:
            # Skip empty lines
            if not line.strip():
                return
                
            self.message_count += 1
            self.last_message_time = datetime.now()
            
            # Update message rate tracking
            self._update_message_rate()
            
            # Parse the raw message from dump1090
            # Format: *8D<ICAO><DATA>;<timestamp>
            if not line.startswith('*') or ';' not in line:
                return
                
            # Extract message and timestamp
            parts = line.split(';')
            raw_message = parts[0]
            
            # Remove the '*' prefix
            if raw_message.startswith('*'):
                raw_message = raw_message[1:]
            
            # Validate message format and length
            if not self._validate_raw_message(raw_message):
                self.error_count += 1
                return
                
            # Decode the message using pyModeS
            decoded_data = self.decode_adsb_message(raw_message)
            if decoded_data:
                self.valid_message_count += 1
                
                # Update aircraft tracking
                aircraft = self.aircraft_tracker.update_aircraft(decoded_data['icao'], decoded_data)
                if aircraft:
                    # Check watchlist and send alerts if needed
                    self.check_watchlist(aircraft)
            else:
                self.error_count += 1
            
            # Log message rate periodically
            if self.message_count % 1000 == 0:
                rate = self.get_message_rate()
                valid_rate = self.get_valid_message_rate()
                aircraft_count = self.aircraft_tracker.get_aircraft_count()
                logger.info(f"Processed {self.message_count} messages "
                           f"(rate: {rate}/sec, valid: {valid_rate}/sec, "
                           f"errors: {self.error_count}, aircraft: {aircraft_count})")
                
        except Exception as e:
            self.error_count += 1
            logger.error(f"Error processing message line '{line[:50]}...': {e}")
    
    def check_watchlist(self, aircraft) -> None:
        """Check aircraft against watchlist and send alerts with smart throttling."""
        try:
            if not aircraft.on_watchlist:
                return
                
            # Check if this is a new detection
            if aircraft.is_new_watchlist_detection():
                logger.info(f"NEW watchlist aircraft detected: {aircraft.get_display_name()} ({aircraft.icao})")
                self.send_meshtastic_alert(aircraft)
                return
            
            # Check if we should send a periodic alert
            receiver_config = self.config.get_receiver_config()
            alert_interval = receiver_config.alert_interval
            
            if aircraft.should_send_watchlist_alert(alert_interval):
                logger.info(f"Periodic watchlist alert for: {aircraft.get_display_name()} ({aircraft.icao})")
                self.send_meshtastic_alert(aircraft)
                
        except Exception as e:
            logger.error(f"Error checking watchlist: {e}")
    
    def send_meshtastic_alert(self, aircraft) -> None:
        """Send enhanced Meshtastic alert for watchlist aircraft."""
        try:
            # Calculate distance and bearing if position is available
            distance_info = ""
            bearing_info = ""
            
            if aircraft.has_position():
                receiver_config = self.config.get_receiver_config()
                ref_lat = receiver_config.reference_lat
                ref_lon = receiver_config.reference_lon
                
                try:
                    from utils import calculate_distance, calculate_bearing
                    distance = calculate_distance(ref_lat, ref_lon, aircraft.latitude, aircraft.longitude)
                    bearing = calculate_bearing(ref_lat, ref_lon, aircraft.latitude, aircraft.longitude)
                    distance_info = f" {distance:.1f}km"
                    bearing_info = f" {bearing:.0f}°"
                except:
                    pass  # Fall back to basic alert if distance calculation fails
            
            # Determine alert type
            alert_type = "NEW" if aircraft.is_new_watchlist_detection() else "UPDATE"
            
            # Build enhanced aircraft data for alert
            aircraft_data = {
                'icao': aircraft.icao,
                'callsign': aircraft.callsign,
                'altitude': aircraft.altitude,
                'latitude': aircraft.latitude,
                'longitude': aircraft.longitude,
                'speed': aircraft.speed,
                'track': aircraft.track,
                'watchlist_name': aircraft.watchlist_name,
                'alert_type': alert_type,
                'distance_info': distance_info,
                'bearing_info': bearing_info,
                'first_detected': aircraft.watchlist_first_detected,
                'alert_count': aircraft.watchlist_alert_count + 1
            }
            
            # Send alert and mark as alerted if successful
            if self.meshtastic_manager.send_alert(aircraft_data):
                aircraft.mark_watchlist_alerted()
                logger.info(f"Watchlist alert sent for {aircraft.icao} (alert #{aircraft.watchlist_alert_count})")
            else:
                logger.warning(f"Failed to send watchlist alert for {aircraft.icao}")
            
        except Exception as e:
            logger.error(f"Error sending Meshtastic alert: {e}")
    
    def update_status(self) -> None:
        """Update status JSON file periodically."""
        while self.running and not self.stop_event.is_set():
            try:
                # Save aircraft data
                self.aircraft_tracker.save_to_json("aircraft.json")
                
                # Get comprehensive health status
                health_status = self.dump1090_manager.get_health_status()
                meshtastic_status = self.meshtastic_manager.get_health_status()
                
                # Get message statistics
                message_stats = self.get_message_statistics()
                
                # Save status data
                status = {
                    "timestamp": datetime.now().isoformat(),
                    "receiver_running": self.running,
                    "dump1090_running": health_status.get('dump1090_running', False),
                    "hackrf_connected": health_status.get('hackrf_connected', False),
                    "meshtastic_connected": meshtastic_status.get('connected', False),
                    "message_rate": message_stats["overall_rate"],
                    "current_message_rate": message_stats["current_rate"],
                    "valid_message_rate": message_stats["valid_rate"],
                    "aircraft_count": self.aircraft_tracker.get_aircraft_count(),
                    "watchlist_count": len(self.config.get_watchlist()),
                    "uptime": str(datetime.now() - self.start_time),
                    "message_statistics": message_stats,
                    "aircraft_statistics": self.aircraft_tracker.get_statistics(),
                    "watchlist_statistics": self.aircraft_tracker.get_watchlist_statistics(),
                    "radio_settings": {
                        "frequency": health_status.get('radio_frequency', 0),
                        "lna_gain": health_status.get('lna_gain', 0),
                        "vga_gain": health_status.get('vga_gain', 0),
                        "amp_enabled": health_status.get('amp_enabled', False)
                    },
                    "meshtastic_status": meshtastic_status,
                    "last_health_check": health_status.get('last_health_check', 0)
                }
                
                with open("status.json", 'w') as f:
                    json.dump(status, f, indent=2)
                    
            except Exception as e:
                logger.error(f"Error updating status: {e}")
                
            # Wait 5 seconds before next update
            self.stop_event.wait(5)
    
    def _on_config_reload(self, new_config: dict) -> None:
        """Handle configuration reload events, particularly watchlist updates."""
        try:
            logger.info("Configuration reloaded, updating watchlist...")
            
            # Update watchlist from new configuration
            watchlist_data = new_config.get('watchlist', [])
            
            # Convert to watchlist entries format
            from config import WatchlistEntry
            watchlist_entries = []
            for entry in watchlist_data:
                if isinstance(entry, dict):
                    watchlist_entries.append(WatchlistEntry(
                        icao=entry.get('icao', ''),
                        name=entry.get('name', '')
                    ))
            
            # Update aircraft tracker with new watchlist
            self.aircraft_tracker.update_watchlist(watchlist_entries)
            
            logger.info(f"Watchlist updated with {len(watchlist_entries)} entries")
            
        except Exception as e:
            logger.error(f"Error handling config reload: {e}")
    
    def cleanup_loop(self) -> None:
        """Periodic cleanup of stale aircraft and position cache."""
        while self.running and not self.stop_event.is_set():
            try:
                # Clean up stale aircraft
                self.aircraft_tracker.cleanup_stale(300)  # 5 minute timeout
                
                # Clean up position cache
                self._cleanup_position_cache()
                
            except Exception as e:
                logger.error(f"Error during cleanup: {e}")
                
            # Wait 60 seconds before next cleanup
            self.stop_event.wait(60)
    
    def health_monitor_loop(self) -> None:
        """Monitor system health and restart components if needed."""
        while self.running and not self.stop_event.is_set():
            try:
                # Check and restart dump1090/HackRF if needed
                if not self.dump1090_manager.restart_if_needed():
                    logger.warning("Failed to restart dump1090/HackRF")
                
                # Check and reconnect Meshtastic if needed
                if not self.meshtastic_manager.reconnect_if_needed():
                    logger.debug("Meshtastic reconnection not needed or failed")
                    
            except Exception as e:
                logger.error(f"Error in health monitor: {e}")
                
            # Wait 30 seconds before next health check
            self.stop_event.wait(30)
    
    def _update_message_rate(self) -> None:
        """Update message rate tracking window."""
        try:
            current_time = datetime.now()
            
            # Add current message to rate window
            self.message_rate_window.append(current_time)
            
            # Remove messages older than window size
            cutoff_time = current_time - timedelta(seconds=self.rate_window_size)
            self.message_rate_window = [
                msg_time for msg_time in self.message_rate_window 
                if msg_time > cutoff_time
            ]
            
        except Exception as e:
            logger.error(f"Error updating message rate: {e}")
    
    def get_message_rate(self) -> float:
        """Calculate current message rate per second (overall average)."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        if uptime > 0:
            return round(self.message_count / uptime, 1)
        return 0.0
    
    def get_current_message_rate(self) -> float:
        """Calculate current message rate per second (recent window)."""
        try:
            if len(self.message_rate_window) < 2:
                return 0.0
                
            # Calculate rate based on messages in the current window
            return round(len(self.message_rate_window) / self.rate_window_size, 1)
            
        except Exception as e:
            logger.error(f"Error calculating current message rate: {e}")
            return 0.0
    
    def get_valid_message_rate(self) -> float:
        """Calculate valid message rate per second."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        if uptime > 0:
            return round(self.valid_message_count / uptime, 1)
        return 0.0
    
    def get_message_statistics(self) -> Dict[str, Any]:
        """Get comprehensive message processing statistics."""
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "total_messages": self.message_count,
            "valid_messages": self.valid_message_count,
            "error_count": self.error_count,
            "overall_rate": self.get_message_rate(),
            "current_rate": self.get_current_message_rate(),
            "valid_rate": self.get_valid_message_rate(),
            "error_rate": round(self.error_count / max(uptime, 1), 1),
            "success_percentage": round((self.valid_message_count / max(self.message_count, 1)) * 100, 1),
            "uptime_seconds": round(uptime, 1),
            "last_message_age": round((datetime.now() - self.last_message_time).total_seconds(), 1),
            "position_cache_size": len(self.position_cache)
        }
    
    def update_radio_settings(self, frequency: int = None, lna_gain: int = None, 
                            vga_gain: int = None, enable_amp: bool = None) -> bool:
        """Update radio settings and apply them immediately."""
        try:
            # Get current radio config
            current_config = self.config.get_radio_config()
            
            # Update only provided values
            new_config = RadioConfig(
                frequency=frequency if frequency is not None else current_config.frequency,
                lna_gain=lna_gain if lna_gain is not None else current_config.lna_gain,
                vga_gain=vga_gain if vga_gain is not None else current_config.vga_gain,
                enable_amp=enable_amp if enable_amp is not None else current_config.enable_amp
            )
            
            # Apply the new settings
            if self.dump1090_manager.apply_radio_settings(new_config):
                logger.info("Radio settings updated successfully")
                return True
            else:
                logger.error("Failed to apply radio settings")
                return False
                
        except Exception as e:
            logger.error(f"Error updating radio settings: {e}")
            return False
    
    def get_radio_settings(self) -> dict:
        """Get current radio settings."""
        try:
            health_status = self.dump1090_manager.get_health_status()
            return {
                'frequency': health_status.get('radio_frequency', 0),
                'lna_gain': health_status.get('lna_gain', 0),
                'vga_gain': health_status.get('vga_gain', 0),
                'amp_enabled': health_status.get('amp_enabled', False)
            }
        except Exception as e:
            logger.error(f"Error getting radio settings: {e}")
            return {}


class ADSBReceiver:
    """Main ADS-B receiver application with comprehensive error handling and recovery."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.aircraft_tracker = AircraftTracker()
        self.dump1090_manager = Dump1090Manager(self.config)
        self.meshtastic_manager = MeshtasticManager(self.config)
        
        # Status tracking
        self.running = False
        self.start_time = datetime.now()
        self.last_health_check = 0
        self.health_check_interval = 30  # seconds
        
        # Message processing
        self.message_processor = None
        self.tcp_socket = None
        self.processing_thread = None
        self.stop_event = Event()
        
        # Error tracking
        self.consecutive_errors = 0
        self.max_consecutive_errors = 10
        self.last_successful_message = datetime.now()
        
        # Recovery tracking
        self.recovery_attempts = 0
        self.max_recovery_attempts = 5
        self.last_recovery_attempt = 0
        self.recovery_cooldown = 60  # seconds
        
        # Register error recovery strategies
        self._register_recovery_strategies()
        
        logger.info("ADSBReceiver initialized")
    
    def _register_recovery_strategies(self) -> None:
        """Register automatic recovery strategies for different error types."""
        error_handler.register_recovery_strategy("TCP_CONNECTION_FAILED", self._recover_tcp_connection)
        error_handler.register_recovery_strategy("DUMP1090_NOT_RUNNING", self._recover_dump1090)
        error_handler.register_recovery_strategy("HACKRF_DISCONNECTED", self._recover_hackrf)
        error_handler.register_recovery_strategy("MESHTASTIC_DISCONNECTED", self._recover_meshtastic)
    
    def start(self) -> bool:
        """Start the receiver with comprehensive error handling."""
        try:
            if self.running:
                logger.warning("Receiver is already running")
                return True
            
            logger.info("Starting ADS-B receiver...")
            
            # Load and validate configuration
            if not self._initialize_configuration():
                return False
            
            # Start dump1090 and configure HackRF
            if not self._initialize_hardware():
                return False
            
            # Connect to Meshtastic
            self._initialize_meshtastic()
            
            # Start message processing
            if not self._start_message_processing():
                return False
            
            # Start configuration watching
            self.config.start_watching()
            
            self.running = True
            self.start_time = datetime.now()
            logger.info("ADS-B receiver started successfully")
            
            # Main processing loop
            self._main_loop()
            
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                f"Failed to start receiver: {str(e)}",
                error_code="RECEIVER_START_FAILED"
            )
            self.stop()
            return False
    
    def stop(self) -> None:
        """Stop the receiver gracefully."""
        try:
            if not self.running:
                return
            
            logger.info("Stopping ADS-B receiver...")
            self.running = False
            self.stop_event.set()
            
            # Stop message processing
            if self.processing_thread and self.processing_thread.is_alive():
                self.processing_thread.join(timeout=5)
            
            # Close TCP connection
            if self.tcp_socket:
                self.tcp_socket.close()
            
            # Stop managers
            self.dump1090_manager.stop_dump1090()
            self.meshtastic_manager.disconnect()
            
            # Stop configuration watching
            self.config.stop_watching()
            
            logger.info("ADS-B receiver stopped")
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.HIGH,
                f"Error stopping receiver: {str(e)}",
                error_code="RECEIVER_STOP_ERROR"
            )
    
    def _initialize_configuration(self) -> bool:
        """Initialize and validate configuration."""
        try:
            config_data = self.config.load()
            if not self.config.validate(config_data):
                error_handler.handle_error(
                    ComponentType.CONFIG,
                    ErrorSeverity.CRITICAL,
                    "Invalid configuration detected",
                    error_code="INVALID_CONFIG"
                )
                return False
            
            # Update aircraft tracker with watchlist
            watchlist = self.config.get_watchlist()
            self.aircraft_tracker.update_watchlist(watchlist)
            
            logger.info("Configuration initialized successfully")
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.CONFIG,
                ErrorSeverity.CRITICAL,
                f"Configuration initialization failed: {str(e)}",
                error_code="CONFIG_INIT_FAILED"
            )
            return False
    
    def _initialize_hardware(self) -> bool:
        """Initialize dump1090 and HackRF with error handling."""
        try:
            # Start dump1090
            if not self.dump1090_manager.start_dump1090():
                error_handler.handle_error(
                    ComponentType.DUMP1090,
                    ErrorSeverity.CRITICAL,
                    "Failed to start dump1090",
                    error_code="DUMP1090_START_FAILED"
                )
                return False
            
            # Wait for dump1090 to be ready
            time.sleep(3)
            
            # Verify dump1090 is running
            if not self.dump1090_manager.is_running():
                error_handler.handle_error(
                    ComponentType.DUMP1090,
                    ErrorSeverity.CRITICAL,
                    "dump1090 not running after start attempt",
                    error_code="DUMP1090_NOT_RUNNING"
                )
                return False
            
            logger.info("Hardware initialized successfully")
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                f"Hardware initialization failed: {str(e)}",
                error_code="HARDWARE_INIT_FAILED"
            )
            return False
    
    def _initialize_meshtastic(self) -> None:
        """Initialize Meshtastic connection (non-blocking)."""
        try:
            # Attempt connection but don't fail if it doesn't work
            if self.meshtastic_manager.connect():
                logger.info("Meshtastic initialized successfully")
            else:
                error_handler.handle_error(
                    ComponentType.MESHTASTIC,
                    ErrorSeverity.MEDIUM,
                    "Meshtastic initialization failed, will retry later",
                    error_code="MESHTASTIC_INIT_FAILED"
                )
        except Exception as e:
            error_handler.handle_error(
                ComponentType.MESHTASTIC,
                ErrorSeverity.MEDIUM,
                f"Meshtastic initialization error: {str(e)}",
                error_code="MESHTASTIC_INIT_ERROR"
            )
    
    def _start_message_processing(self) -> bool:
        """Start TCP connection and message processing thread."""
        try:
            # Connect to dump1090 TCP stream
            if not self._connect_to_dump1090():
                return False
            
            # Start processing thread
            self.processing_thread = Thread(target=self._message_processing_loop, daemon=True)
            self.processing_thread.start()
            
            logger.info("Message processing started")
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                f"Failed to start message processing: {str(e)}",
                error_code="MESSAGE_PROCESSING_START_FAILED"
            )
            return False
    
    def _connect_to_dump1090(self) -> bool:
        """Connect to dump1090 TCP stream with error handling."""
        try:
            if self.tcp_socket:
                self.tcp_socket.close()
            
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(5.0)
            self.tcp_socket.connect(("localhost", 30005))
            self.tcp_socket.settimeout(1.0)  # Shorter timeout for reads
            
            logger.info("Connected to dump1090 TCP stream")
            return True
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.HIGH,
                f"Failed to connect to dump1090 TCP stream: {str(e)}",
                error_code="TCP_CONNECTION_FAILED"
            )
            return False
    
    def _main_loop(self) -> None:
        """Main processing loop with health monitoring."""
        try:
            while self.running:
                current_time = time.time()
                
                # Periodic health checks
                if current_time - self.last_health_check > self.health_check_interval:
                    self._perform_health_checks()
                    self.last_health_check = current_time
                
                # Update status files
                self._update_status_files()
                
                # Sleep briefly
                time.sleep(1)
                
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                f"Error in main loop: {str(e)}",
                error_code="MAIN_LOOP_ERROR"
            )
            self.stop()
    
    def _perform_health_checks(self) -> None:
        """Perform comprehensive health checks and recovery."""
        try:
            # Check dump1090 health
            if not self.dump1090_manager.restart_if_needed():
                self.consecutive_errors += 1
            else:
                self.consecutive_errors = 0
            
            # Check Meshtastic health
            self.meshtastic_manager.reconnect_if_needed()
            
            # Check message processing health
            message_age = (datetime.now() - self.last_successful_message).total_seconds()
            if message_age > 60:  # No messages for 1 minute
                error_handler.handle_error(
                    ComponentType.RECEIVER,
                    ErrorSeverity.HIGH,
                    f"No messages received for {message_age:.0f} seconds",
                    error_code="NO_MESSAGES"
                )
                self._attempt_recovery()
            
            # Check for too many consecutive errors
            if self.consecutive_errors >= self.max_consecutive_errors:
                error_handler.handle_error(
                    ComponentType.RECEIVER,
                    ErrorSeverity.CRITICAL,
                    f"Too many consecutive errors ({self.consecutive_errors})",
                    error_code="TOO_MANY_ERRORS"
                )
                self._attempt_full_recovery()
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.HIGH,
                f"Error during health checks: {str(e)}",
                error_code="HEALTH_CHECK_ERROR"
            )
    
    def _attempt_recovery(self) -> bool:
        """Attempt to recover from errors."""
        try:
            current_time = time.time()
            
            # Check recovery cooldown
            if current_time - self.last_recovery_attempt < self.recovery_cooldown:
                return False
            
            # Check max recovery attempts
            if self.recovery_attempts >= self.max_recovery_attempts:
                error_handler.handle_error(
                    ComponentType.RECEIVER,
                    ErrorSeverity.CRITICAL,
                    f"Max recovery attempts ({self.max_recovery_attempts}) exceeded",
                    error_code="MAX_RECOVERY_ATTEMPTS"
                )
                return False
            
            self.last_recovery_attempt = current_time
            self.recovery_attempts += 1
            
            logger.info(f"Attempting recovery (attempt {self.recovery_attempts}/{self.max_recovery_attempts})")
            
            # Try to reconnect TCP
            if self._connect_to_dump1090():
                logger.info("Recovery successful")
                self.recovery_attempts = 0
                return True
            
            return False
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.HIGH,
                f"Error during recovery attempt: {str(e)}",
                error_code="RECOVERY_ERROR"
            )
            return False
    
    def _attempt_full_recovery(self) -> None:
        """Attempt full system recovery by restarting all components."""
        try:
            logger.warning("Attempting full system recovery...")
            
            # Stop everything
            self.stop_event.set()
            if self.tcp_socket:
                self.tcp_socket.close()
            
            # Restart dump1090
            self.dump1090_manager.stop_dump1090()
            time.sleep(5)
            
            if self.dump1090_manager.start_dump1090():
                # Reconnect TCP
                time.sleep(3)
                if self._connect_to_dump1090():
                    # Restart processing thread
                    self.stop_event.clear()
                    self.processing_thread = Thread(target=self._message_processing_loop, daemon=True)
                    self.processing_thread.start()
                    
                    self.consecutive_errors = 0
                    self.recovery_attempts = 0
                    logger.info("Full recovery successful")
                    return
            
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                "Full recovery failed",
                error_code="FULL_RECOVERY_FAILED"
            )
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                f"Error during full recovery: {str(e)}",
                error_code="FULL_RECOVERY_ERROR"
            )
    
    def _message_processing_loop(self) -> None:
        """Message processing loop with error handling."""
        try:
            buffer = ""
            
            while not self.stop_event.is_set():
                try:
                    # Read data from TCP socket
                    data = self.tcp_socket.recv(1024).decode('utf-8', errors='ignore')
                    if not data:
                        error_handler.handle_error(
                            ComponentType.RECEIVER,
                            ErrorSeverity.HIGH,
                            "TCP connection closed by dump1090",
                            error_code="TCP_CONNECTION_CLOSED"
                        )
                        break
                    
                    buffer += data
                    
                    # Process complete messages
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        if line.strip():
                            self._process_message(line.strip())
                            self.last_successful_message = datetime.now()
                    
                except socket.timeout:
                    # Timeout is normal, continue
                    continue
                except Exception as e:
                    error_handler.handle_error(
                        ComponentType.RECEIVER,
                        ErrorSeverity.HIGH,
                        f"Error in message processing loop: {str(e)}",
                        error_code="MESSAGE_PROCESSING_ERROR"
                    )
                    time.sleep(1)
                    
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.CRITICAL,
                f"Fatal error in message processing loop: {str(e)}",
                error_code="MESSAGE_PROCESSING_FATAL"
            )
    
    def _process_message(self, message: str) -> None:
        """Process individual ADS-B message with error handling."""
        try:
            # This would integrate with pyModeS for actual message decoding
            # For now, implement basic message parsing
            
            # Simple message format parsing (placeholder)
            if message.startswith('MSG'):
                parts = message.split(',')
                if len(parts) >= 11:
                    icao = parts[4].strip()
                    if icao:
                        # Create basic aircraft data
                        aircraft_data = {
                            'icao': icao,
                            'callsign': parts[10].strip() if len(parts) > 10 else None,
                            'altitude': safe_int(parts[11]) if len(parts) > 11 else None,
                            'speed': safe_int(parts[12]) if len(parts) > 12 else None,
                            'track': safe_int(parts[13]) if len(parts) > 13 else None,
                            'latitude': safe_float(parts[14]) if len(parts) > 14 else None,
                            'longitude': safe_float(parts[15]) if len(parts) > 15 else None
                        }
                        
                        # Update aircraft tracker
                        aircraft = self.aircraft_tracker.update_aircraft(icao, aircraft_data)
                        
                        # Check for watchlist alerts
                        if aircraft and aircraft.should_send_watchlist_alert():
                            self._send_watchlist_alert(aircraft)
                            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.LOW,
                f"Error processing message: {str(e)}",
                error_code="MESSAGE_PARSE_ERROR",
                details=f"Message: {message[:100]}"
            )
    
    def _send_watchlist_alert(self, aircraft) -> None:
        """Send watchlist alert via Meshtastic."""
        try:
            alert_data = {
                'icao': aircraft.icao,
                'callsign': aircraft.callsign,
                'altitude': aircraft.altitude,
                'watchlist_name': aircraft.watchlist_name,
                'alert_type': 'WATCHLIST',
                'alert_count': aircraft.watchlist_alert_count + 1
            }
            
            if self.meshtastic_manager.send_alert(alert_data):
                aircraft.mark_watchlist_alerted()
                logger.info(f"Watchlist alert sent for {aircraft.icao}")
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.MESHTASTIC,
                ErrorSeverity.MEDIUM,
                f"Error sending watchlist alert: {str(e)}",
                error_code="ALERT_SEND_ERROR"
            )
    
    def _update_status_files(self) -> None:
        """Update status.json and aircraft.json files with comprehensive error information."""
        try:
            # Update aircraft.json
            self.aircraft_tracker.save_to_json("aircraft.json")
            
            # Get comprehensive system status
            dump1090_health = self.dump1090_manager.get_health_status()
            meshtastic_health = self.meshtastic_manager.get_health_status()
            error_summary = error_handler.get_error_summary()
            
            # Update status.json with comprehensive information
            status_data = {
                "receiver_running": self.running,
                "dump1090_running": self.dump1090_manager.is_running(),
                "hackrf_connected": self.dump1090_manager.hackrf_connected,
                "meshtastic_connected": self.meshtastic_manager.is_connected(),
                "aircraft_count": self.aircraft_tracker.get_aircraft_count(),
                "watchlist_count": len(self.config.get_watchlist()),
                "uptime": str(datetime.now() - self.start_time),
                "message_rate": 0.0,  # Would be calculated from message processor
                "total_messages": 0,  # Would be from message processor
                "consecutive_errors": self.consecutive_errors,
                "recovery_attempts": self.recovery_attempts,
                "last_successful_message": self.last_successful_message.isoformat(),
                "dump1090_health": dump1090_health,
                "meshtastic_health": meshtastic_health,
                "error_summary": error_summary,
                "recent_errors": [error.to_dict() for error in error_handler.get_recent_errors(1)],
                "critical_errors": [error.to_dict() for error in error_handler.get_critical_errors()],
                "system_health": self._calculate_system_health(),
                "last_update": datetime.now().isoformat()
            }
            
            with open("status.json", 'w') as f:
                json.dump(status_data, f, indent=2)
                
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.LOW,
                f"Error updating status files: {str(e)}",
                error_code="STATUS_UPDATE_ERROR"
            )
    
    def _calculate_system_health(self) -> str:
        """Calculate overall system health status."""
        try:
            critical_errors = len(error_handler.get_critical_errors())
            recent_errors = len(error_handler.get_recent_errors(1))
            
            # Check critical components
            dump1090_ok = self.dump1090_manager.is_running()
            hackrf_ok = self.dump1090_manager.hackrf_connected
            
            # Calculate health score
            if critical_errors > 0:
                return "CRITICAL"
            elif not dump1090_ok or not hackrf_ok:
                return "DEGRADED"
            elif recent_errors > 10:
                return "WARNING"
            elif self.consecutive_errors > 3:
                return "WARNING"
            else:
                return "HEALTHY"
                
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.LOW,
                f"Error calculating system health: {str(e)}",
                error_code="HEALTH_CALC_ERROR"
            )
            return "UNKNOWN"
    
    # Recovery strategy implementations
    def _recover_tcp_connection(self, error: 'SystemError') -> bool:
        """Recover TCP connection to dump1090."""
        return self._connect_to_dump1090()
    
    def _recover_dump1090(self, error: 'SystemError') -> bool:
        """Recover dump1090 process."""
        return self.dump1090_manager.start_dump1090()
    
    def _recover_hackrf(self, error: 'SystemError') -> bool:
        """Recover HackRF connection."""
        return self.dump1090_manager.configure_hackrf()
    
    def _recover_meshtastic(self, error: 'SystemError') -> bool:
        """Recover Meshtastic connection."""
        return self.meshtastic_manager.connect()


# Global receiver instance for signal handling
_receiver_instance = None


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global _receiver_instance
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    
    if _receiver_instance:
        _receiver_instance.stop()
    
    logger.info("Graceful shutdown complete")
    sys.exit(0)


def main():
    """Main receiver entry point with comprehensive error handling and recovery."""
    global _receiver_instance
    
    try:
        # Set up logging
        setup_logging("ursine-receiver.log")
        logger.info("Starting Ursine Capture Receiver")
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Parse command line arguments
        config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
        
        # Initialize error handler with recovery strategies
        error_handler.register_recovery_strategy("RECEIVER_FATAL", _emergency_recovery)
        error_handler.register_recovery_strategy("MAX_RECOVERY_ATTEMPTS", _emergency_shutdown)
        
        # Create and start receiver with retry logic
        max_start_attempts = 3
        start_attempt = 0
        
        while start_attempt < max_start_attempts:
            try:
                start_attempt += 1
                logger.info(f"Starting receiver (attempt {start_attempt}/{max_start_attempts})")
                
                _receiver_instance = ADSBReceiver(config_path)
                
                if _receiver_instance.start():
                    logger.info("Receiver started successfully")
                    break
                else:
                    error_handler.handle_error(
                        ComponentType.RECEIVER,
                        ErrorSeverity.HIGH,
                        f"Receiver start failed (attempt {start_attempt})",
                        error_code="RECEIVER_START_FAILED"
                    )
                    
                    if start_attempt < max_start_attempts:
                        logger.info(f"Retrying in 5 seconds...")
                        time.sleep(5)
                    else:
                        error_handler.handle_error(
                            ComponentType.RECEIVER,
                            ErrorSeverity.CRITICAL,
                            "All receiver start attempts failed",
                            error_code="RECEIVER_START_EXHAUSTED"
                        )
                        sys.exit(1)
                        
            except Exception as e:
                error_handler.handle_error(
                    ComponentType.RECEIVER,
                    ErrorSeverity.CRITICAL,
                    f"Exception during receiver start attempt {start_attempt}: {str(e)}",
                    error_code="RECEIVER_START_EXCEPTION"
                )
                
                if start_attempt >= max_start_attempts:
                    logger.error("Max start attempts reached, exiting")
                    sys.exit(1)
                    
                time.sleep(5)
        
        # Main receiver should now be running
        logger.info("Receiver initialization complete")
        
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
        error_handler.handle_error(
            ComponentType.RECEIVER,
            ErrorSeverity.LOW,
            "Receiver interrupted by user",
            error_code="USER_INTERRUPT"
        )
        if _receiver_instance:
            _receiver_instance.stop()
    except Exception as e:
        error_handler.handle_error(
            ComponentType.RECEIVER,
            ErrorSeverity.CRITICAL,
            f"Fatal error in main: {str(e)}",
            error_code="RECEIVER_FATAL_ERROR"
        )
        if _receiver_instance:
            _receiver_instance.stop()
        sys.exit(1)
    finally:
        # Clean up error handler
        error_handler.clear_old_errors(days=1)
        logger.info("Receiver main process exiting")
        sys.exit(0)


def _emergency_recovery(error: 'SystemError') -> bool:
    """Emergency recovery function for critical receiver errors."""
    try:
        logger.warning("Attempting emergency recovery...")
        
        # Kill all related processes
        kill_process("dump1090")
        time.sleep(2)
        
        # Try to restart the receiver
        global _receiver_instance
        if _receiver_instance:
            _receiver_instance.stop()
            time.sleep(3)
            
            # Create new instance
            _receiver_instance = ADSBReceiver("config.json")
            return _receiver_instance.start()
        
        return False
        
    except Exception as e:
        logger.error(f"Emergency recovery failed: {e}")
        return False


def _emergency_shutdown(error: 'SystemError') -> bool:
    """Emergency shutdown when recovery is not possible."""
    try:
        logger.critical("Emergency shutdown initiated - too many recovery failures")
        
        # Save error state
        error_summary = error_handler.get_error_summary()
        with open("emergency_shutdown.json", 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "trigger_error": error.to_dict(),
                "error_summary": error_summary,
                "reason": "Max recovery attempts exceeded"
            }, f, indent=2)
        
        # Graceful shutdown
        global _receiver_instance
        if _receiver_instance:
            _receiver_instance.stop()
        
        logger.critical("Emergency shutdown complete")
        sys.exit(1)
        
    except Exception as e:
        logger.error(f"Emergency shutdown failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()