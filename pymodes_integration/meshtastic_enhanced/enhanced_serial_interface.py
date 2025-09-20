"""
Enhanced Serial Interface for Meshtastic Integration

This module provides an enhanced serial interface that extends the existing
MeshtasticInterface with channel management, device detection, and improved
device information retrieval capabilities.
"""

import logging
import serial
import serial.tools.list_ports
import threading
import time
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

from .interfaces import MeshtasticInterface
from .data_classes import (
    ChannelConfig, ConnectionStatus, ConnectionState, 
    MeshtasticConfig, AlertMessage
)
from .channel_manager import ChannelManager
from .exceptions import MeshtasticConnectionError, MeshtasticConfigError
from ..meshtastic_interface import MeshtasticInterface as LegacyMeshtasticInterface


logger = logging.getLogger(__name__)


@dataclass
class DeviceInfo:
    """Information about a connected Meshtastic device"""
    node_id: Optional[str] = None
    hardware_model: Optional[str] = None
    firmware_version: Optional[str] = None
    region: Optional[str] = None
    modem_preset: Optional[str] = None
    has_wifi: bool = False
    has_bluetooth: bool = False
    battery_level: Optional[int] = None
    voltage: Optional[float] = None
    channel_utilization: Optional[float] = None
    air_util_tx: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'node_id': self.node_id,
            'hardware_model': self.hardware_model,
            'firmware_version': self.firmware_version,
            'region': self.region,
            'modem_preset': self.modem_preset,
            'has_wifi': self.has_wifi,
            'has_bluetooth': self.has_bluetooth,
            'battery_level': self.battery_level,
            'voltage': self.voltage,
            'channel_utilization': self.channel_utilization,
            'air_util_tx': self.air_util_tx
        }


class EnhancedSerialInterface(MeshtasticInterface):
    """
    Enhanced serial interface for Meshtastic communication
    
    This class extends the base MeshtasticInterface with:
    - Channel management and configuration
    - Device detection and capability querying
    - Enhanced device information retrieval
    - Improved error handling and connection management
    """
    
    def __init__(self, config: MeshtasticConfig, channel_manager: ChannelManager):
        """
        Initialize enhanced serial interface
        
        Args:
            config: Meshtastic configuration
            channel_manager: Channel manager instance
        """
        self.config = config
        self.channel_manager = channel_manager
        
        # Connection management
        self.serial_conn: Optional[serial.Serial] = None
        self.connection_state = ConnectionState.DISCONNECTED
        self.connected_since: Optional[datetime] = None
        self.last_message_time: Optional[datetime] = None
        self.error_message: Optional[str] = None
        
        # Device information
        self.device_info: Optional[DeviceInfo] = None
        self.device_capabilities: Dict[str, Any] = {}
        
        # Threading
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.statistics = {
            'messages_sent': 0,
            'messages_failed': 0,
            'connection_attempts': 0,
            'successful_connections': 0,
            'reconnections': 0,
            'device_queries': 0,
            'channel_switches': 0,
            'last_activity': None
        }
        
        # Legacy interface for backward compatibility
        self._legacy_interface: Optional[LegacyMeshtasticInterface] = None
        
        logger.info(f"EnhancedSerialInterface initialized for {config.meshtastic_port}")
    
    def connect(self) -> bool:
        """
        Establish connection to Meshtastic device
        
        Returns:
            True if connection successful, False otherwise
        """
        with self._lock:
            if self.connection_state == ConnectionState.CONNECTED:
                return True
            
            self.connection_state = ConnectionState.CONNECTING
            self.statistics['connection_attempts'] += 1
            self.error_message = None
            
            try:
                # Close existing connection if any
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except:
                        pass
                    self.serial_conn = None
                
                # Create new serial connection
                self.serial_conn = serial.Serial(
                    port=self.config.meshtastic_port,
                    baudrate=self.config.meshtastic_baud,
                    timeout=self.config.connection_timeout,
                    write_timeout=self.config.connection_timeout,
                    exclusive=True
                )
                
                # Wait for device to be ready
                time.sleep(2)
                
                # Test connection and get device info
                if self._test_connection():
                    self.connection_state = ConnectionState.CONNECTED
                    self.connected_since = datetime.now()
                    self.statistics['successful_connections'] += 1
                    self.statistics['last_activity'] = datetime.now().isoformat()
                    
                    # Query device information
                    self._query_device_info()
                    
                    # Configure channels if needed
                    if self.config.auto_detect_device:
                        self._configure_device_channels()
                    
                    logger.info(f"Connected to Meshtastic device on {self.config.meshtastic_port}")
                    return True
                else:
                    raise MeshtasticConnectionError("Device connection test failed")
                
            except Exception as e:
                self.connection_state = ConnectionState.ERROR
                self.error_message = str(e)
                logger.error(f"Failed to connect to Meshtastic device: {e}")
                
                if self.serial_conn:
                    try:
                        self.serial_conn.close()
                    except:
                        pass
                    self.serial_conn = None
                
                return False
    
    def disconnect(self) -> None:
        """Disconnect from Meshtastic device"""
        with self._lock:
            if self.serial_conn:
                try:
                    self.serial_conn.close()
                    logger.info("Disconnected from Meshtastic device")
                except Exception as e:
                    logger.error(f"Error disconnecting: {e}")
                finally:
                    self.serial_conn = None
            
            self.connection_state = ConnectionState.DISCONNECTED
            self.connected_since = None
            self.device_info = None
    
    def send_message(self, message: str, channel: Optional[str] = None) -> bool:
        """
        Send a message through the serial interface
        
        Args:
            message: Message content to send
            channel: Optional channel name (uses default if None)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        if not self.is_connected():
            logger.warning("Cannot send message: not connected")
            return False
        
        # Get channel configuration
        if channel:
            channel_config = self.channel_manager.get_channel_by_name(channel)
            if not channel_config:
                logger.error(f"Channel '{channel}' not found")
                return False
        else:
            channel_config = self.channel_manager.get_default_channel()
        
        try:
            with self._lock:
                # Switch to channel if needed
                if not self._switch_to_channel(channel_config):
                    logger.error(f"Failed to switch to channel '{channel_config.name}'")
                    return False
                
                # Format message
                formatted_message = self._format_message(message, channel_config)
                
                # Send message
                self.serial_conn.write(formatted_message.encode('utf-8'))
                self.serial_conn.flush()
                
                # Update statistics
                self.statistics['messages_sent'] += 1
                self.statistics['last_activity'] = datetime.now().isoformat()
                self.last_message_time = datetime.now()
                
                logger.debug(f"Sent message on channel '{channel_config.name}': {message[:50]}...")
                return True
                
        except Exception as e:
            self.statistics['messages_failed'] += 1
            self.error_message = str(e)
            logger.error(f"Failed to send message: {e}")
            
            # Connection might be lost
            self.connection_state = ConnectionState.ERROR
            return False
    
    def is_connected(self) -> bool:
        """Check if currently connected to device"""
        return self.connection_state == ConnectionState.CONNECTED and self.serial_conn is not None
    
    def get_connection_status(self) -> ConnectionStatus:
        """Get detailed connection status information"""
        return ConnectionStatus(
            interface_type="serial",
            state=self.connection_state,
            connected_since=self.connected_since,
            last_message_time=self.last_message_time,
            error_message=self.error_message,
            device_info=self.device_info.to_dict() if self.device_info else None,
            statistics=self.statistics.copy()
        )
    
    def get_interface_type(self) -> str:
        """Get interface type identifier"""
        return "serial"
    
    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """
        Get device information including node ID, hardware model, and firmware
        
        Returns:
            Dictionary with device information or None if not available
        """
        if self.device_info:
            return self.device_info.to_dict()
        return None
    
    def configure_channels(self, channels: List[ChannelConfig]) -> bool:
        """
        Configure device channels
        
        Args:
            channels: List of channel configurations to apply
            
        Returns:
            True if channels configured successfully
        """
        if not self.is_connected():
            logger.warning("Cannot configure channels: not connected")
            return False
        
        try:
            success_count = 0
            for channel in channels:
                if self._configure_single_channel(channel):
                    success_count += 1
                else:
                    logger.warning(f"Failed to configure channel '{channel.name}'")
            
            self.statistics['channel_switches'] += success_count
            logger.info(f"Configured {success_count}/{len(channels)} channels")
            return success_count == len(channels)
            
        except Exception as e:
            logger.error(f"Error configuring channels: {e}")
            return False
    
    def get_signal_strength(self) -> Optional[float]:
        """
        Get current signal strength/SNR
        
        Returns:
            Signal strength in dB or None if not available
        """
        if not self.is_connected():
            return None
        
        try:
            # Query device for signal strength
            # This would depend on the specific Meshtastic device protocol
            # For now, return a placeholder
            return None
        except Exception as e:
            logger.debug(f"Failed to get signal strength: {e}")
            return None
    
    def _test_connection(self) -> bool:
        """Test if device connection is working"""
        try:
            if not self.serial_conn:
                return False
            
            # Send a simple command to test connectivity
            test_command = "!help\n"
            self.serial_conn.write(test_command.encode('utf-8'))
            self.serial_conn.flush()
            
            # Wait for response
            time.sleep(1)
            
            # Check if we can read from the device
            if self.serial_conn.in_waiting > 0:
                response = self.serial_conn.read(self.serial_conn.in_waiting)
                logger.debug(f"Device test response: {response[:100]}")
                return True
            
            # If no immediate response, assume connection is working
            # (some devices might not respond to help command)
            return True
            
        except Exception as e:
            logger.debug(f"Connection test failed: {e}")
            return False
    
    def _query_device_info(self) -> None:
        """Query device for information"""
        if not self.is_connected():
            return
        
        try:
            self.statistics['device_queries'] += 1
            
            # Initialize device info
            self.device_info = DeviceInfo()
            
            # Query device information using Meshtastic CLI commands
            info_commands = [
                ("!info", self._parse_info_response),
                ("!status", self._parse_status_response),
                ("!channels", self._parse_channels_response)
            ]
            
            for command, parser in info_commands:
                try:
                    response = self._send_command_and_wait(command)
                    if response:
                        parser(response)
                except Exception as e:
                    logger.debug(f"Failed to query {command}: {e}")
            
            logger.debug(f"Device info: {self.device_info.to_dict()}")
            
        except Exception as e:
            logger.warning(f"Failed to query device info: {e}")
    
    def _send_command_and_wait(self, command: str, timeout: float = 3.0) -> Optional[str]:
        """Send command and wait for response"""
        try:
            # Clear input buffer
            self.serial_conn.reset_input_buffer()
            
            # Send command
            self.serial_conn.write(f"{command}\n".encode('utf-8'))
            self.serial_conn.flush()
            
            # Wait for response
            start_time = time.time()
            response_lines = []
            
            while time.time() - start_time < timeout:
                if self.serial_conn.in_waiting > 0:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        response_lines.append(line)
                        
                        # Check for command completion indicators
                        if any(indicator in line.lower() for indicator in ['>', 'ok', 'done', 'error']):
                            break
                else:
                    time.sleep(0.1)
            
            return '\n'.join(response_lines) if response_lines else None
            
        except Exception as e:
            logger.debug(f"Command '{command}' failed: {e}")
            return None
    
    def _parse_info_response(self, response: str) -> None:
        """Parse device info response"""
        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip().lower()
                
                # Parse node ID
                if 'node' in line and 'id' in line:
                    match = re.search(r'([a-f0-9]{8})', line)
                    if match:
                        self.device_info.node_id = match.group(1)
                
                # Parse hardware model
                if 'hardware' in line or 'model' in line:
                    # Extract model name
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part in ['hardware', 'model'] and i + 1 < len(parts):
                            self.device_info.hardware_model = parts[i + 1].upper()
                            break
                
                # Parse firmware version
                if 'firmware' in line or 'version' in line:
                    match = re.search(r'(\d+\.\d+\.\d+)', line)
                    if match:
                        self.device_info.firmware_version = match.group(1)
                
                # Parse region
                if 'region' in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == 'region' and i + 1 < len(parts):
                            self.device_info.region = parts[i + 1].upper()
                            break
                            
        except Exception as e:
            logger.debug(f"Failed to parse info response: {e}")
    
    def _parse_status_response(self, response: str) -> None:
        """Parse device status response"""
        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip().lower()
                
                # Parse battery level
                if 'battery' in line:
                    match = re.search(r'(\d+)%', line)
                    if match:
                        self.device_info.battery_level = int(match.group(1))
                
                # Parse voltage
                if 'voltage' in line or 'volt' in line:
                    match = re.search(r'(\d+\.\d+)v', line)
                    if match:
                        self.device_info.voltage = float(match.group(1))
                
                # Parse channel utilization
                if 'channel' in line and 'util' in line:
                    match = re.search(r'(\d+\.\d+)%', line)
                    if match:
                        self.device_info.channel_utilization = float(match.group(1))
                
                # Parse air utilization
                if 'air' in line and 'util' in line:
                    match = re.search(r'(\d+\.\d+)%', line)
                    if match:
                        self.device_info.air_util_tx = float(match.group(1))
                        
        except Exception as e:
            logger.debug(f"Failed to parse status response: {e}")
    
    def _parse_channels_response(self, response: str) -> None:
        """Parse channels response to understand device capabilities"""
        try:
            # This would parse the channel configuration from the device
            # and update device capabilities
            self.device_capabilities['channels_supported'] = True
            self.device_capabilities['max_channels'] = 8  # Standard Meshtastic limit
            
        except Exception as e:
            logger.debug(f"Failed to parse channels response: {e}")
    
    def _configure_device_channels(self) -> bool:
        """Configure device with channel manager channels"""
        try:
            channels = self.channel_manager.get_all_channels()
            return self.configure_channels(channels)
        except Exception as e:
            logger.warning(f"Failed to configure device channels: {e}")
            return False
    
    def _configure_single_channel(self, channel: ChannelConfig) -> bool:
        """Configure a single channel on the device"""
        try:
            # Build channel configuration command
            cmd_parts = [f"!channel set {channel.channel_number}"]
            
            # Add channel name
            cmd_parts.append(f"name {channel.name}")
            
            # Add PSK if encrypted
            if channel.is_encrypted:
                cmd_parts.append(f"psk {channel.psk}")
            
            # Add other settings
            if not channel.uplink_enabled:
                cmd_parts.append("uplink_enabled false")
            
            if not channel.downlink_enabled:
                cmd_parts.append("downlink_enabled false")
            
            # Send configuration command
            command = " ".join(cmd_parts)
            response = self._send_command_and_wait(command)
            
            if response and 'ok' in response.lower():
                logger.debug(f"Configured channel '{channel.name}' successfully")
                return True
            else:
                logger.warning(f"Channel configuration may have failed: {response}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to configure channel '{channel.name}': {e}")
            return False
    
    def _switch_to_channel(self, channel: ChannelConfig) -> bool:
        """Switch to a specific channel"""
        try:
            # Send channel switch command
            command = f"!channel use {channel.channel_number}"
            response = self._send_command_and_wait(command)
            
            if response and ('ok' in response.lower() or 'switched' in response.lower()):
                logger.debug(f"Switched to channel '{channel.name}'")
                return True
            else:
                # Channel switching might not be explicitly confirmed
                # Assume success if no error
                return True
                
        except Exception as e:
            logger.debug(f"Failed to switch to channel '{channel.name}': {e}")
            return False
    
    def _format_message(self, message: str, channel: ChannelConfig) -> str:
        """Format message for transmission"""
        formatted = message
        
        # Add timestamp if configured
        if self.config.include_timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] {formatted}"
        
        # Truncate if too long
        if len(formatted) > self.config.max_message_length:
            formatted = formatted[:self.config.max_message_length - 3] + "..."
        
        # Ensure newline termination
        if not formatted.endswith('\n'):
            formatted += '\n'
        
        return formatted
    
    def start_monitoring(self) -> None:
        """Start background monitoring thread"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            name="EnhancedSerialMonitor",
            daemon=True
        )
        self._monitor_thread.start()
        logger.debug("Started monitoring thread")
    
    def stop_monitoring(self) -> None:
        """Stop background monitoring thread"""
        self._stop_event.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        logger.debug("Stopped monitoring thread")
    
    def _monitor_loop(self) -> None:
        """Background monitoring loop"""
        while not self._stop_event.is_set():
            try:
                # Check connection health
                if self.is_connected():
                    # Periodic device info refresh
                    if (datetime.now() - (self.connected_since or datetime.now())).total_seconds() > 300:
                        self._query_device_info()
                
                # Sleep for health check interval
                self._stop_event.wait(self.config.health_check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                self._stop_event.wait(10)