"""
Device Detection for Enhanced Meshtastic Integration

This module provides automatic detection and identification of Meshtastic devices
connected via USB, along with capability detection and compatibility checking.
"""

import logging
import serial
import serial.tools.list_ports
import time
import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from .exceptions import MeshtasticDetectionError, MeshtasticConnectionError


logger = logging.getLogger(__name__)


class DeviceType(Enum):
    """Known Meshtastic device types"""
    HELTEC_V3 = "HELTEC_V3"
    TBEAM = "TBEAM"
    TLORA_V2 = "TLORA_V2"
    TLORA_V1 = "TLORA_V1"
    TECHO = "TECHO"
    STATION_G1 = "STATION_G1"
    RAK4631 = "RAK4631"
    UNKNOWN = "UNKNOWN"


@dataclass
class DetectedDevice:
    """Information about a detected Meshtastic device"""
    port: str
    device_type: DeviceType
    hardware_model: Optional[str] = None
    firmware_version: Optional[str] = None
    node_id: Optional[str] = None
    region: Optional[str] = None
    capabilities: Dict[str, Any] = None
    usb_info: Dict[str, Any] = None
    is_compatible: bool = True
    compatibility_issues: List[str] = None
    
    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = {}
        if self.compatibility_issues is None:
            self.compatibility_issues = []
        if self.usb_info is None:
            self.usb_info = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'port': self.port,
            'device_type': self.device_type.value,
            'hardware_model': self.hardware_model,
            'firmware_version': self.firmware_version,
            'node_id': self.node_id,
            'region': self.region,
            'capabilities': self.capabilities,
            'usb_info': self.usb_info,
            'is_compatible': self.is_compatible,
            'compatibility_issues': self.compatibility_issues
        }


class DeviceDetector:
    """
    Automatic detection and identification of Meshtastic devices
    
    This class provides functionality to:
    - Enumerate USB serial devices
    - Identify Meshtastic devices by VID/PID and communication
    - Query device capabilities and compatibility
    - Validate device compatibility with the enhanced system
    """
    
    # Known USB VID/PID combinations for Meshtastic devices
    KNOWN_DEVICES = {
        # Heltec devices
        (0x10C4, 0xEA60): DeviceType.HELTEC_V3,  # CP2102 USB to UART Bridge
        (0x1A86, 0x7523): DeviceType.HELTEC_V3,  # CH340 serial converter
        
        # TTGO/LilyGO devices
        (0x10C4, 0xEA60): DeviceType.TBEAM,      # CP2102 (also used by T-Beam)
        (0x1A86, 0x55D4): DeviceType.TLORA_V2,   # CH9102 USB serial converter
        
        # RAK devices
        (0x239A, 0x8029): DeviceType.RAK4631,    # RAK4631 nRF52840
        
        # Generic USB-Serial converters (need further identification)
        (0x0403, 0x6001): DeviceType.UNKNOWN,    # FTDI FT232R
        (0x067B, 0x2303): DeviceType.UNKNOWN,    # Prolific PL2303
    }
    
    # Device identification strings
    DEVICE_STRINGS = {
        'heltec': DeviceType.HELTEC_V3,
        'wifi_lora_32': DeviceType.HELTEC_V3,
        'tbeam': DeviceType.TBEAM,
        't-beam': DeviceType.TBEAM,
        'tlora': DeviceType.TLORA_V2,
        't-lora': DeviceType.TLORA_V2,
        'techo': DeviceType.TECHO,
        't-echo': DeviceType.TECHO,
        'station': DeviceType.STATION_G1,
        'rak4631': DeviceType.RAK4631,
        'rak': DeviceType.RAK4631,
    }
    
    def __init__(self, timeout: float = 5.0, baud_rates: List[int] = None):
        """
        Initialize device detector
        
        Args:
            timeout: Timeout for device communication in seconds
            baud_rates: List of baud rates to try (defaults to common rates)
        """
        self.timeout = timeout
        self.baud_rates = baud_rates or [115200, 9600, 57600, 38400, 19200]
        
        # Detection statistics
        self.stats = {
            'total_ports_scanned': 0,
            'devices_detected': 0,
            'compatible_devices': 0,
            'last_scan_time': None,
            'scan_duration': 0
        }
        
        logger.info("DeviceDetector initialized")
    
    def detect_meshtastic_devices(self) -> List[DetectedDevice]:
        """
        Detect all Meshtastic devices connected via USB
        
        Returns:
            List of detected Meshtastic devices
        """
        start_time = time.time()
        detected_devices = []
        
        try:
            # Get all available serial ports
            ports = serial.tools.list_ports.comports()
            self.stats['total_ports_scanned'] = len(ports)
            
            logger.info(f"Scanning {len(ports)} serial ports for Meshtastic devices...")
            
            for port_info in ports:
                try:
                    device = self._identify_device(port_info)
                    if device:
                        detected_devices.append(device)
                        logger.info(f"Detected Meshtastic device: {device.device_type.value} on {device.port}")
                except Exception as e:
                    logger.debug(f"Failed to identify device on {port_info.device}: {e}")
            
            # Update statistics
            self.stats['devices_detected'] = len(detected_devices)
            self.stats['compatible_devices'] = sum(1 for d in detected_devices if d.is_compatible)
            self.stats['last_scan_time'] = time.time()
            self.stats['scan_duration'] = time.time() - start_time
            
            logger.info(f"Device detection completed: found {len(detected_devices)} devices in {self.stats['scan_duration']:.2f}s")
            
            return detected_devices
            
        except Exception as e:
            logger.error(f"Error during device detection: {e}")
            raise MeshtasticDetectionError(f"Device detection failed: {e}")
    
    def get_device_capabilities(self, port: str) -> Dict[str, Any]:
        """
        Get detailed capabilities of a device on the specified port
        
        Args:
            port: Serial port path
            
        Returns:
            Dictionary with device capabilities
        """
        try:
            # Try to connect and query capabilities
            for baud_rate in self.baud_rates:
                try:
                    capabilities = self._query_device_capabilities(port, baud_rate)
                    if capabilities:
                        return capabilities
                except Exception as e:
                    logger.debug(f"Failed to query capabilities at {baud_rate} baud: {e}")
            
            # Return basic capabilities if detailed query fails
            return {
                'communication': True,
                'channels_supported': True,
                'encryption_supported': True,
                'max_channels': 8,
                'query_method': 'fallback'
            }
            
        except Exception as e:
            logger.warning(f"Failed to get device capabilities for {port}: {e}")
            return {}
    
    def validate_device_compatibility(self, port: str) -> Tuple[bool, str]:
        """
        Validate device compatibility with enhanced Meshtastic features
        
        Args:
            port: Serial port path
            
        Returns:
            Tuple of (is_compatible, error_message)
        """
        try:
            # Get device capabilities
            capabilities = self.get_device_capabilities(port)
            
            issues = []
            
            # Check basic communication
            if not capabilities.get('communication', False):
                issues.append("Cannot establish communication with device")
            
            # Check channel support
            if not capabilities.get('channels_supported', True):
                issues.append("Device does not support channel configuration")
            
            # Check encryption support
            if not capabilities.get('encryption_supported', True):
                issues.append("Device does not support encryption")
            
            # Check firmware version if available
            firmware_version = capabilities.get('firmware_version')
            if firmware_version:
                if not self._is_firmware_compatible(firmware_version):
                    issues.append(f"Firmware version {firmware_version} may not be fully compatible")
            
            is_compatible = len(issues) == 0
            error_message = "; ".join(issues) if issues else ""
            
            return is_compatible, error_message
            
        except Exception as e:
            return False, f"Compatibility check failed: {e}"
    
    def get_best_device(self) -> Optional[DetectedDevice]:
        """
        Get the best available Meshtastic device
        
        Returns:
            Best detected device or None if no devices found
        """
        devices = self.detect_meshtastic_devices()
        
        if not devices:
            return None
        
        # Filter compatible devices
        compatible_devices = [d for d in devices if d.is_compatible]
        
        if not compatible_devices:
            logger.warning("No compatible devices found, returning best available")
            compatible_devices = devices
        
        # Sort by preference (known devices first, then by capabilities)
        def device_score(device: DetectedDevice) -> int:
            score = 0
            
            # Prefer known device types
            if device.device_type != DeviceType.UNKNOWN:
                score += 100
            
            # Prefer devices with more capabilities
            score += len(device.capabilities)
            
            # Prefer devices with firmware info
            if device.firmware_version:
                score += 10
            
            # Prefer devices with node ID
            if device.node_id:
                score += 5
            
            return score
        
        best_device = max(compatible_devices, key=device_score)
        logger.info(f"Selected best device: {best_device.device_type.value} on {best_device.port}")
        
        return best_device
    
    def _identify_device(self, port_info) -> Optional[DetectedDevice]:
        """Identify if a port has a Meshtastic device"""
        try:
            # First, check USB VID/PID
            device_type = self._identify_by_usb_info(port_info)
            
            # If not identified by USB info, try communication
            if device_type == DeviceType.UNKNOWN:
                device_type = self._identify_by_communication(port_info.device)
            
            # Skip if still unknown and no Meshtastic indicators
            if device_type == DeviceType.UNKNOWN and not self._has_meshtastic_indicators(port_info):
                return None
            
            # Create detected device
            device = DetectedDevice(
                port=port_info.device,
                device_type=device_type,
                usb_info={
                    'vid': getattr(port_info, 'vid', None),
                    'pid': getattr(port_info, 'pid', None),
                    'serial_number': getattr(port_info, 'serial_number', None),
                    'manufacturer': getattr(port_info, 'manufacturer', None),
                    'product': getattr(port_info, 'product', None),
                    'description': getattr(port_info, 'description', None)
                }
            )
            
            # Get detailed device information
            self._populate_device_info(device)
            
            # Validate compatibility
            is_compatible, issues = self.validate_device_compatibility(device.port)
            device.is_compatible = is_compatible
            if issues:
                device.compatibility_issues = issues.split("; ")
            
            return device
            
        except Exception as e:
            logger.debug(f"Failed to identify device on {port_info.device}: {e}")
            return None
    
    def _identify_by_usb_info(self, port_info) -> DeviceType:
        """Identify device type by USB VID/PID"""
        try:
            vid = getattr(port_info, 'vid', None)
            pid = getattr(port_info, 'pid', None)
            
            if vid and pid:
                device_type = self.KNOWN_DEVICES.get((vid, pid))
                if device_type:
                    logger.debug(f"Identified device by USB VID/PID: {device_type.value}")
                    return device_type
            
            # Check product/manufacturer strings
            product = getattr(port_info, 'product', '') or ''
            manufacturer = getattr(port_info, 'manufacturer', '') or ''
            description = getattr(port_info, 'description', '') or ''
            
            combined_info = f"{product} {manufacturer} {description}".lower()
            
            for keyword, device_type in self.DEVICE_STRINGS.items():
                if keyword in combined_info:
                    logger.debug(f"Identified device by string '{keyword}': {device_type.value}")
                    return device_type
            
            return DeviceType.UNKNOWN
            
        except Exception as e:
            logger.debug(f"Failed to identify by USB info: {e}")
            return DeviceType.UNKNOWN
    
    def _identify_by_communication(self, port: str) -> DeviceType:
        """Identify device type by communication"""
        try:
            for baud_rate in self.baud_rates:
                try:
                    with serial.Serial(port, baud_rate, timeout=2) as ser:
                        # Clear buffers
                        ser.reset_input_buffer()
                        ser.reset_output_buffer()
                        
                        # Send info command
                        ser.write(b"!info\n")
                        ser.flush()
                        
                        # Read response
                        time.sleep(1)
                        if ser.in_waiting > 0:
                            response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore').lower()
                            
                            # Look for device type indicators in response
                            for keyword, device_type in self.DEVICE_STRINGS.items():
                                if keyword in response:
                                    logger.debug(f"Identified device by communication: {device_type.value}")
                                    return device_type
                            
                            # If we got a response but no specific type, it's likely a Meshtastic device
                            if any(indicator in response for indicator in ['meshtastic', 'node', 'channel']):
                                return DeviceType.UNKNOWN  # Meshtastic device but unknown type
                
                except Exception as e:
                    logger.debug(f"Communication test failed at {baud_rate} baud: {e}")
                    continue
            
            return DeviceType.UNKNOWN
            
        except Exception as e:
            logger.debug(f"Failed to identify by communication: {e}")
            return DeviceType.UNKNOWN
    
    def _has_meshtastic_indicators(self, port_info) -> bool:
        """Check if port has indicators suggesting it might be a Meshtastic device"""
        try:
            # Check USB strings for Meshtastic-related keywords
            strings_to_check = [
                getattr(port_info, 'product', '') or '',
                getattr(port_info, 'manufacturer', '') or '',
                getattr(port_info, 'description', '') or ''
            ]
            
            combined = ' '.join(strings_to_check).lower()
            
            # Look for common indicators
            indicators = [
                'esp32', 'lora', 'mesh', 'radio', 'wireless',
                'heltec', 'ttgo', 'lilygo', 'rak', 'station'
            ]
            
            return any(indicator in combined for indicator in indicators)
            
        except Exception:
            return False
    
    def _populate_device_info(self, device: DetectedDevice) -> None:
        """Populate detailed device information"""
        try:
            # Get device capabilities which includes detailed info
            capabilities = self.get_device_capabilities(device.port)
            device.capabilities = capabilities
            
            # Extract specific info from capabilities
            device.hardware_model = capabilities.get('hardware_model')
            device.firmware_version = capabilities.get('firmware_version')
            device.node_id = capabilities.get('node_id')
            device.region = capabilities.get('region')
            
        except Exception as e:
            logger.debug(f"Failed to populate device info: {e}")
    
    def _query_device_capabilities(self, port: str, baud_rate: int) -> Optional[Dict[str, Any]]:
        """Query device for detailed capabilities"""
        try:
            capabilities = {
                'communication': False,
                'channels_supported': False,
                'encryption_supported': False,
                'max_channels': 0,
                'baud_rate': baud_rate
            }
            
            with serial.Serial(port, baud_rate, timeout=self.timeout) as ser:
                # Clear buffers
                ser.reset_input_buffer()
                ser.reset_output_buffer()
                time.sleep(0.5)
                
                # Test basic communication
                ser.write(b"!help\n")
                ser.flush()
                time.sleep(1)
                
                if ser.in_waiting > 0:
                    capabilities['communication'] = True
                    response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                    
                    # Check for channel support
                    if 'channel' in response.lower():
                        capabilities['channels_supported'] = True
                        capabilities['max_channels'] = 8  # Standard Meshtastic limit
                    
                    # Check for encryption support
                    if 'psk' in response.lower() or 'encrypt' in response.lower():
                        capabilities['encryption_supported'] = True
                
                # Query device info
                info_commands = [
                    ("!info", self._parse_device_info),
                    ("!status", self._parse_device_status)
                ]
                
                for command, parser in info_commands:
                    try:
                        ser.reset_input_buffer()
                        ser.write(f"{command}\n".encode('utf-8'))
                        ser.flush()
                        time.sleep(1)
                        
                        if ser.in_waiting > 0:
                            response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                            parser(response, capabilities)
                    except Exception as e:
                        logger.debug(f"Failed to execute {command}: {e}")
                
                return capabilities if capabilities['communication'] else None
                
        except Exception as e:
            logger.debug(f"Failed to query device capabilities: {e}")
            return None
    
    def _parse_device_info(self, response: str, capabilities: Dict[str, Any]) -> None:
        """Parse device info response"""
        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip().lower()
                
                # Parse hardware model
                if 'hardware' in line or 'model' in line:
                    match = re.search(r'([a-zA-Z0-9_]+)', line.split('hardware')[-1] if 'hardware' in line else line.split('model')[-1])
                    if match:
                        capabilities['hardware_model'] = match.group(1).upper()
                
                # Parse firmware version
                if 'firmware' in line or 'version' in line:
                    match = re.search(r'(\d+\.\d+\.\d+)', line)
                    if match:
                        capabilities['firmware_version'] = match.group(1)
                
                # Parse node ID
                if 'node' in line and 'id' in line:
                    match = re.search(r'([a-f0-9]{8})', line)
                    if match:
                        capabilities['node_id'] = match.group(1)
                
                # Parse region
                if 'region' in line:
                    match = re.search(r'([A-Z]{2})', line)
                    if match:
                        capabilities['region'] = match.group(1)
                        
        except Exception as e:
            logger.debug(f"Failed to parse device info: {e}")
    
    def _parse_device_status(self, response: str, capabilities: Dict[str, Any]) -> None:
        """Parse device status response"""
        try:
            lines = response.split('\n')
            for line in lines:
                line = line.strip().lower()
                
                # Parse battery info
                if 'battery' in line:
                    match = re.search(r'(\d+)%', line)
                    if match:
                        capabilities['battery_level'] = int(match.group(1))
                
                # Parse voltage
                if 'voltage' in line:
                    match = re.search(r'(\d+\.\d+)', line)
                    if match:
                        capabilities['voltage'] = float(match.group(1))
                        
        except Exception as e:
            logger.debug(f"Failed to parse device status: {e}")
    
    def _is_firmware_compatible(self, firmware_version: str) -> bool:
        """Check if firmware version is compatible"""
        try:
            # Parse version string
            version_parts = firmware_version.split('.')
            if len(version_parts) >= 2:
                major = int(version_parts[0])
                minor = int(version_parts[1])
                
                # Require minimum version 2.0 for enhanced features
                if major >= 2:
                    return True
                elif major == 1 and minor >= 3:
                    return True  # Some 1.3+ versions support enhanced features
            
            return False
            
        except Exception:
            # If we can't parse version, assume compatible
            return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get detection statistics"""
        return self.stats.copy()