"""
Unit tests for DeviceDetector

Tests device detection functionality with mock serial devices
and various device identification scenarios.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import serial
from typing import List, Dict, Any

from .device_detector import DeviceDetector, DetectedDevice, DeviceType
from .exceptions import MeshtasticDetectionError


class MockPortInfo:
    """Mock serial port info for testing"""
    def __init__(self, device: str, vid: int = None, pid: int = None, 
                 product: str = None, manufacturer: str = None, 
                 description: str = None, serial_number: str = None):
        self.device = device
        self.vid = vid
        self.pid = pid
        self.product = product
        self.manufacturer = manufacturer
        self.description = description
        self.serial_number = serial_number


class MockSerial:
    """Mock serial connection for testing"""
    def __init__(self, port: str, baudrate: int, timeout: float = None, write_timeout: float = None, exclusive: bool = False):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.exclusive = exclusive
        self.in_waiting = 0
        self._input_buffer = b""
        self._output_buffer = b""
        self.is_open = True
    
    def write(self, data: bytes) -> int:
        self._output_buffer += data
        return len(data)
    
    def flush(self):
        pass
    
    def read(self, size: int = 1) -> bytes:
        data = self._input_buffer[:size]
        self._input_buffer = self._input_buffer[size:]
        self.in_waiting = len(self._input_buffer)
        return data
    
    def readline(self) -> bytes:
        if b'\n' in self._input_buffer:
            line_end = self._input_buffer.index(b'\n') + 1
            line = self._input_buffer[:line_end]
            self._input_buffer = self._input_buffer[line_end:]
            self.in_waiting = len(self._input_buffer)
            return line
        else:
            data = self._input_buffer
            self._input_buffer = b""
            self.in_waiting = 0
            return data
    
    def reset_input_buffer(self):
        self._input_buffer = b""
        self.in_waiting = 0
    
    def reset_output_buffer(self):
        self._output_buffer = b""
    
    def close(self):
        self.is_open = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
    
    def set_response(self, response: str):
        """Set response data for testing"""
        self._input_buffer = response.encode('utf-8')
        self.in_waiting = len(self._input_buffer)


class TestDeviceDetector(unittest.TestCase):
    """Test cases for DeviceDetector"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.detector = DeviceDetector(timeout=1.0)
    
    def test_init(self):
        """Test DeviceDetector initialization"""
        detector = DeviceDetector(timeout=2.0, baud_rates=[9600, 115200])
        
        self.assertEqual(detector.timeout, 2.0)
        self.assertEqual(detector.baud_rates, [9600, 115200])
        self.assertIsInstance(detector.stats, dict)
    
    def test_init_defaults(self):
        """Test DeviceDetector initialization with defaults"""
        detector = DeviceDetector()
        
        self.assertEqual(detector.timeout, 5.0)
        self.assertIn(115200, detector.baud_rates)
        self.assertIn(9600, detector.baud_rates)
    
    @patch('serial.tools.list_ports.comports')
    def test_detect_no_devices(self, mock_comports):
        """Test detection when no devices are present"""
        mock_comports.return_value = []
        
        devices = self.detector.detect_meshtastic_devices()
        
        self.assertEqual(len(devices), 0)
        self.assertEqual(self.detector.stats['total_ports_scanned'], 0)
        self.assertEqual(self.detector.stats['devices_detected'], 0)
    
    @patch('serial.tools.list_ports.comports')
    def test_detect_heltec_device_by_vid_pid(self, mock_comports):
        """Test detection of Heltec device by VID/PID"""
        mock_port = MockPortInfo(
            device="/dev/ttyUSB0",
            vid=0x10C4,
            pid=0xEA60,
            product="CP2102 USB to UART Bridge Controller",
            manufacturer="Silicon Labs"
        )
        mock_comports.return_value = [mock_port]
        
        with patch('serial.Serial', MockSerial):
            with patch.object(self.detector, '_populate_device_info'):
                with patch.object(self.detector, 'validate_device_compatibility', return_value=(True, "")):
                    devices = self.detector.detect_meshtastic_devices()
        
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.port, "/dev/ttyUSB0")
        self.assertEqual(device.device_type, DeviceType.HELTEC_V3)
        self.assertTrue(device.is_compatible)
    
    @patch('serial.tools.list_ports.comports')
    def test_detect_device_by_product_string(self, mock_comports):
        """Test detection of device by product string"""
        mock_port = MockPortInfo(
            device="/dev/ttyUSB1",
            product="TTGO T-Beam",
            manufacturer="TTGO"
        )
        mock_comports.return_value = [mock_port]
        
        with patch('serial.Serial', MockSerial):
            with patch.object(self.detector, '_populate_device_info'):
                with patch.object(self.detector, 'validate_device_compatibility', return_value=(True, "")):
                    devices = self.detector.detect_meshtastic_devices()
        
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.device_type, DeviceType.TBEAM)
    
    @patch('serial.tools.list_ports.comports')
    @patch('serial.Serial')
    def test_detect_device_by_communication(self, mock_serial_class, mock_comports):
        """Test detection of device by communication"""
        mock_port = MockPortInfo(device="/dev/ttyUSB2")
        mock_comports.return_value = [mock_port]
        
        # Mock serial connection
        mock_serial = MockSerial("/dev/ttyUSB2", 115200)
        mock_serial.set_response("Meshtastic device info: HELTEC_V3\nNode ID: 12345678\n")
        mock_serial_class.return_value = mock_serial
        
        with patch.object(self.detector, '_populate_device_info'):
            with patch.object(self.detector, 'validate_device_compatibility', return_value=(True, "")):
                devices = self.detector.detect_meshtastic_devices()
        
        self.assertEqual(len(devices), 1)
        device = devices[0]
        self.assertEqual(device.device_type, DeviceType.HELTEC_V3)
    
    def test_identify_by_usb_info_known_device(self):
        """Test identification by USB VID/PID for known device"""
        port_info = MockPortInfo(
            device="/dev/ttyUSB0",
            vid=0x10C4,
            pid=0xEA60
        )
        
        device_type = self.detector._identify_by_usb_info(port_info)
        self.assertEqual(device_type, DeviceType.HELTEC_V3)
    
    def test_identify_by_usb_info_product_string(self):
        """Test identification by product string"""
        port_info = MockPortInfo(
            device="/dev/ttyUSB0",
            product="WiFi LoRa 32 V3"
        )
        
        device_type = self.detector._identify_by_usb_info(port_info)
        self.assertEqual(device_type, DeviceType.HELTEC_V3)
    
    def test_identify_by_usb_info_unknown(self):
        """Test identification returns unknown for unrecognized device"""
        port_info = MockPortInfo(
            device="/dev/ttyUSB0",
            vid=0x1234,
            pid=0x5678,
            product="Unknown Device"
        )
        
        device_type = self.detector._identify_by_usb_info(port_info)
        self.assertEqual(device_type, DeviceType.UNKNOWN)
    
    @patch('serial.Serial')
    def test_identify_by_communication_success(self, mock_serial_class):
        """Test successful identification by communication"""
        mock_serial = MockSerial("/dev/ttyUSB0", 115200)
        mock_serial.set_response("Device info: HELTEC_V3 firmware 2.1.0\n")
        mock_serial_class.return_value = mock_serial
        
        device_type = self.detector._identify_by_communication("/dev/ttyUSB0")
        self.assertEqual(device_type, DeviceType.HELTEC_V3)
    
    @patch('serial.Serial')
    def test_identify_by_communication_failure(self, mock_serial_class):
        """Test identification failure by communication"""
        mock_serial_class.side_effect = serial.SerialException("Port not found")
        
        device_type = self.detector._identify_by_communication("/dev/ttyUSB0")
        self.assertEqual(device_type, DeviceType.UNKNOWN)
    
    def test_has_meshtastic_indicators_positive(self):
        """Test positive identification of Meshtastic indicators"""
        port_info = MockPortInfo(
            device="/dev/ttyUSB0",
            product="ESP32 LoRa Module",
            manufacturer="Heltec"
        )
        
        result = self.detector._has_meshtastic_indicators(port_info)
        self.assertTrue(result)
    
    def test_has_meshtastic_indicators_negative(self):
        """Test negative identification of Meshtastic indicators"""
        port_info = MockPortInfo(
            device="/dev/ttyUSB0",
            product="Generic USB Serial",
            manufacturer="FTDI"
        )
        
        result = self.detector._has_meshtastic_indicators(port_info)
        self.assertFalse(result)
    
    @patch('serial.Serial')
    def test_get_device_capabilities_success(self, mock_serial_class):
        """Test successful device capabilities query"""
        mock_serial = MockSerial("/dev/ttyUSB0", 115200)
        mock_serial.set_response("Help: channel, psk, encrypt commands available\n")
        mock_serial_class.return_value = mock_serial
        
        capabilities = self.detector.get_device_capabilities("/dev/ttyUSB0")
        
        self.assertTrue(capabilities['communication'])
        self.assertTrue(capabilities['channels_supported'])
        self.assertTrue(capabilities['encryption_supported'])
        self.assertEqual(capabilities['baud_rate'], 115200)
    
    @patch('serial.Serial')
    def test_get_device_capabilities_fallback(self, mock_serial_class):
        """Test device capabilities fallback when query fails"""
        mock_serial_class.side_effect = serial.SerialException("Connection failed")
        
        capabilities = self.detector.get_device_capabilities("/dev/ttyUSB0")
        
        # Should return basic fallback capabilities
        self.assertTrue(capabilities['communication'])
        self.assertTrue(capabilities['channels_supported'])
        self.assertTrue(capabilities['encryption_supported'])
        self.assertEqual(capabilities['query_method'], 'fallback')
    
    def test_validate_device_compatibility_success(self):
        """Test successful device compatibility validation"""
        with patch.object(self.detector, 'get_device_capabilities') as mock_get_caps:
            mock_get_caps.return_value = {
                'communication': True,
                'channels_supported': True,
                'encryption_supported': True,
                'firmware_version': '2.1.0'
            }
            
            is_compatible, error_msg = self.detector.validate_device_compatibility("/dev/ttyUSB0")
            
            self.assertTrue(is_compatible)
            self.assertEqual(error_msg, "")
    
    def test_validate_device_compatibility_failure(self):
        """Test device compatibility validation failure"""
        with patch.object(self.detector, 'get_device_capabilities') as mock_get_caps:
            mock_get_caps.return_value = {
                'communication': False,
                'channels_supported': False,
                'encryption_supported': False
            }
            
            is_compatible, error_msg = self.detector.validate_device_compatibility("/dev/ttyUSB0")
            
            self.assertFalse(is_compatible)
            self.assertIn("Cannot establish communication", error_msg)
            self.assertIn("does not support channel configuration", error_msg)
            self.assertIn("does not support encryption", error_msg)
    
    def test_get_best_device_with_compatible_devices(self):
        """Test getting best device when compatible devices exist"""
        devices = [
            DetectedDevice(
                port="/dev/ttyUSB0",
                device_type=DeviceType.UNKNOWN,
                is_compatible=True,
                capabilities={'test': True}
            ),
            DetectedDevice(
                port="/dev/ttyUSB1",
                device_type=DeviceType.HELTEC_V3,
                is_compatible=True,
                firmware_version="2.1.0",
                node_id="12345678",
                capabilities={'test': True, 'advanced': True}
            )
        ]
        
        with patch.object(self.detector, 'detect_meshtastic_devices', return_value=devices):
            best_device = self.detector.get_best_device()
        
        self.assertIsNotNone(best_device)
        self.assertEqual(best_device.port, "/dev/ttyUSB1")
        self.assertEqual(best_device.device_type, DeviceType.HELTEC_V3)
    
    def test_get_best_device_no_devices(self):
        """Test getting best device when no devices exist"""
        with patch.object(self.detector, 'detect_meshtastic_devices', return_value=[]):
            best_device = self.detector.get_best_device()
        
        self.assertIsNone(best_device)
    
    def test_get_best_device_no_compatible_devices(self):
        """Test getting best device when no compatible devices exist"""
        devices = [
            DetectedDevice(
                port="/dev/ttyUSB0",
                device_type=DeviceType.UNKNOWN,
                is_compatible=False,
                compatibility_issues=["Communication failed"]
            )
        ]
        
        with patch.object(self.detector, 'detect_meshtastic_devices', return_value=devices):
            best_device = self.detector.get_best_device()
        
        # Should return best available even if not compatible
        self.assertIsNotNone(best_device)
        self.assertEqual(best_device.port, "/dev/ttyUSB0")
        self.assertFalse(best_device.is_compatible)
    
    def test_parse_device_info(self):
        """Test parsing device info response"""
        capabilities = {}
        response = """
        Device info:
        Hardware: HELTEC_V3
        Firmware version: 2.1.0
        Node ID: 12345678
        Region: US
        """
        
        self.detector._parse_device_info(response, capabilities)
        
        self.assertEqual(capabilities['hardware_model'], 'HELTEC_V3')
        self.assertEqual(capabilities['firmware_version'], '2.1.0')
        self.assertEqual(capabilities['node_id'], '12345678')
        self.assertEqual(capabilities['region'], 'US')
    
    def test_parse_device_status(self):
        """Test parsing device status response"""
        capabilities = {}
        response = """
        Device status:
        Battery: 85%
        Voltage: 4.1V
        """
        
        self.detector._parse_device_status(response, capabilities)
        
        self.assertEqual(capabilities['battery_level'], 85)
        self.assertEqual(capabilities['voltage'], 4.1)
    
    def test_is_firmware_compatible_new_version(self):
        """Test firmware compatibility check for new version"""
        self.assertTrue(self.detector._is_firmware_compatible("2.1.0"))
        self.assertTrue(self.detector._is_firmware_compatible("2.0.0"))
        self.assertTrue(self.detector._is_firmware_compatible("3.0.0"))
    
    def test_is_firmware_compatible_old_version(self):
        """Test firmware compatibility check for old version"""
        self.assertFalse(self.detector._is_firmware_compatible("1.2.0"))
        self.assertTrue(self.detector._is_firmware_compatible("1.3.0"))
        self.assertTrue(self.detector._is_firmware_compatible("1.3.5"))
    
    def test_is_firmware_compatible_invalid_version(self):
        """Test firmware compatibility check for invalid version"""
        # Should assume compatible if can't parse
        self.assertTrue(self.detector._is_firmware_compatible("invalid"))
        self.assertTrue(self.detector._is_firmware_compatible(""))
    
    def test_get_statistics(self):
        """Test getting detection statistics"""
        # Set some test statistics
        self.detector.stats['total_ports_scanned'] = 5
        self.detector.stats['devices_detected'] = 2
        self.detector.stats['compatible_devices'] = 1
        
        stats = self.detector.get_statistics()
        
        self.assertEqual(stats['total_ports_scanned'], 5)
        self.assertEqual(stats['devices_detected'], 2)
        self.assertEqual(stats['compatible_devices'], 1)
        
        # Ensure it's a copy, not the original
        stats['total_ports_scanned'] = 10
        self.assertEqual(self.detector.stats['total_ports_scanned'], 5)


class TestDetectedDevice(unittest.TestCase):
    """Test cases for DetectedDevice data class"""
    
    def test_detected_device_creation(self):
        """Test DetectedDevice creation"""
        device = DetectedDevice(
            port="/dev/ttyUSB0",
            device_type=DeviceType.HELTEC_V3,
            hardware_model="HELTEC_V3",
            firmware_version="2.1.0",
            node_id="12345678"
        )
        
        self.assertEqual(device.port, "/dev/ttyUSB0")
        self.assertEqual(device.device_type, DeviceType.HELTEC_V3)
        self.assertEqual(device.hardware_model, "HELTEC_V3")
        self.assertEqual(device.firmware_version, "2.1.0")
        self.assertEqual(device.node_id, "12345678")
        self.assertTrue(device.is_compatible)
        self.assertIsInstance(device.capabilities, dict)
        self.assertIsInstance(device.compatibility_issues, list)
        self.assertIsInstance(device.usb_info, dict)
    
    def test_detected_device_to_dict(self):
        """Test DetectedDevice serialization to dictionary"""
        device = DetectedDevice(
            port="/dev/ttyUSB0",
            device_type=DeviceType.HELTEC_V3,
            hardware_model="HELTEC_V3",
            capabilities={'test': True},
            is_compatible=False,
            compatibility_issues=["Test issue"]
        )
        
        device_dict = device.to_dict()
        
        self.assertEqual(device_dict['port'], "/dev/ttyUSB0")
        self.assertEqual(device_dict['device_type'], "HELTEC_V3")
        self.assertEqual(device_dict['hardware_model'], "HELTEC_V3")
        self.assertEqual(device_dict['capabilities'], {'test': True})
        self.assertFalse(device_dict['is_compatible'])
        self.assertEqual(device_dict['compatibility_issues'], ["Test issue"])


if __name__ == '__main__':
    unittest.main()