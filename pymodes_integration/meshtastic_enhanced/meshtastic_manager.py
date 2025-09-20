"""
Enhanced MeshtasticManager coordinator

This module implements the central coordinator for all Meshtastic operations,
integrating ChannelManager, SerialInterface, and MQTTInterface with dual-mode
operation and automatic failover capabilities.
"""

import logging
import threading
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta

from .interfaces import MeshtasticInterface
from .data_classes import (
    MeshtasticConfig, ChannelConfig, MQTTConfig, AlertMessage, 
    ConnectionStatus, ConnectionState, MessagePriority, RoutingPolicy
)
from .channel_manager import ChannelManager
from .enhanced_serial_interface import EnhancedSerialInterface
from .mqtt_interface import MeshtasticMQTTInterface
from .message_router import MessageRouter
from .connection_manager import ConnectionManager, InterfacePriority
from .exceptions import (
    MeshtasticError, MeshtasticConfigError, MeshtasticConnectionError,
    ConfigurationError, ConnectionError
)


logger = logging.getLogger(__name__)


class MeshtasticManager:
    """
    Central coordinator for all Meshtastic operations
    
    This class integrates all Meshtastic components and provides a unified
    interface for sending alerts, managing connections, and monitoring health.
    Supports dual-mode operation with automatic failover between serial and MQTT.
    """
    
    def __init__(self, config: MeshtasticConfig):
        """
        Initialize MeshtasticManager with configuration
        
        Args:
            config: MeshtasticConfig object with all settings
            
        Raises:
            MeshtasticConfigError: If configuration is invalid
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Core components
        self.channel_manager: Optional[ChannelManager] = None
        self.serial_interface: Optional[EnhancedSerialInterface] = None
        self.mqtt_interface: Optional[MeshtasticMQTTInterface] = None
        self.message_router: Optional[MessageRouter] = None
        self.connection_manager: Optional[ConnectionManager] = None
        
        # State management
        self._initialized = False
        self._shutdown_requested = False
        self._health_check_thread: Optional[threading.Thread] = None
        self._health_check_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            'messages_sent': 0,
            'messages_failed': 0,
            'serial_messages': 0,
            'mqtt_messages': 0,
            'failovers': 0,
            'start_time': datetime.now()
        }
        
        # Validate configuration
        self._validate_configuration()
        
        self.logger.info(f"MeshtasticManager initialized with mode: {config.connection_mode}")
    
    def _validate_configuration(self) -> None:
        """
        Validate the Meshtastic configuration
        
        Raises:
            MeshtasticConfigError: If configuration is invalid
        """
        try:
            # Validate connection mode
            if self.config.connection_mode not in ["serial", "mqtt", "dual"]:
                raise MeshtasticConfigError(
                    f"Invalid connection mode: {self.config.connection_mode}. "
                    "Must be 'serial', 'mqtt', or 'dual'"
                )
            
            # Validate serial configuration if needed
            if self.config.connection_mode in ["serial", "dual"]:
                if not self.config.meshtastic_port:
                    raise MeshtasticConfigError("Serial port must be specified for serial mode")
                
                if not (1200 <= self.config.meshtastic_baud <= 115200):
                    raise MeshtasticConfigError(
                        f"Invalid baud rate: {self.config.meshtastic_baud}. "
                        "Must be between 1200 and 115200"
                    )
            
            # Validate MQTT configuration if needed
            if self.config.connection_mode in ["mqtt", "dual"]:
                if not self.config.mqtt:
                    raise MeshtasticConfigError("MQTT configuration required for MQTT mode")
                
                # MQTT config validation is handled by MQTTConfig.__post_init__
            
            # Validate channels
            if not self.config.channels:
                self.logger.warning("No channels configured, using default LongFast channel")
                self.config.channels = [ChannelConfig(name="LongFast")]
            
            # Validate default channel exists
            channel_names = [ch.name for ch in self.config.channels]
            if self.config.default_channel not in channel_names:
                self.logger.warning(
                    f"Default channel '{self.config.default_channel}' not found in channels. "
                    f"Using first channel: {channel_names[0]}"
                )
                self.config.default_channel = channel_names[0]
            
            self.logger.info("Configuration validation passed")
            
        except Exception as e:
            raise MeshtasticConfigError(f"Configuration validation failed: {str(e)}")
    
    def initialize(self) -> bool:
        """
        Initialize all Meshtastic components and establish connections
        
        Returns:
            True if initialization successful, False otherwise
        """
        if self._initialized:
            self.logger.warning("MeshtasticManager already initialized")
            return True
        
        try:
            self.logger.info("Initializing MeshtasticManager...")
            
            # Initialize channel manager
            self.channel_manager = ChannelManager(self.config.channels)
            self.logger.info("Channel manager initialized")
            
            # Initialize connection manager
            self.connection_manager = ConnectionManager(
                failover_enabled=self.config.failover_enabled,
                health_check_interval=self.config.health_check_interval
            )
            self.logger.info("Connection manager initialized")
            
            # Initialize interfaces based on connection mode
            interfaces = []
            
            # Initialize serial interface if needed
            if self.config.connection_mode in ["serial", "dual"]:
                try:
                    self.serial_interface = EnhancedSerialInterface(
                        config=self.config,
                        channel_manager=self.channel_manager
                    )
                    
                    if self.serial_interface.connect():
                        interfaces.append(self.serial_interface)
                        # Add to connection manager with high priority (primary interface)
                        self.connection_manager.add_interface(
                            self.serial_interface, 
                            priority=InterfacePriority.HIGH,
                            is_primary=True
                        )
                        self.logger.info("Serial interface initialized and connected")
                    else:
                        self.logger.warning("Serial interface failed to connect")
                        if self.config.connection_mode == "serial":
                            raise MeshtasticConnectionError("Serial connection required but failed")
                
                except Exception as e:
                    self.logger.error(f"Serial interface initialization failed: {e}")
                    if self.config.connection_mode == "serial":
                        raise MeshtasticConnectionError(f"Serial interface required but failed: {e}")
            
            # Initialize MQTT interface if needed
            if self.config.connection_mode in ["mqtt", "dual"] and self.config.mqtt:
                try:
                    self.mqtt_interface = MeshtasticMQTTInterface(
                        config=self.config.mqtt,
                        channel_manager=self.channel_manager
                    )
                    
                    if self.mqtt_interface.connect():
                        interfaces.append(self.mqtt_interface)
                        # Add to connection manager with medium priority (backup interface)
                        priority = InterfacePriority.HIGH if self.config.connection_mode == "mqtt" else InterfacePriority.MEDIUM
                        is_primary = self.config.connection_mode == "mqtt" and not self.serial_interface
                        self.connection_manager.add_interface(
                            self.mqtt_interface,
                            priority=priority,
                            is_primary=is_primary
                        )
                        self.logger.info("MQTT interface initialized and connected")
                    else:
                        self.logger.warning("MQTT interface failed to connect")
                        if self.config.connection_mode == "mqtt":
                            raise MeshtasticConnectionError("MQTT connection required but failed")
                
                except Exception as e:
                    self.logger.error(f"MQTT interface initialization failed: {e}")
                    if self.config.connection_mode == "mqtt":
                        raise MeshtasticConnectionError(f"MQTT interface required but failed: {e}")
            
            # Ensure we have at least one working interface
            if not interfaces:
                raise MeshtasticConnectionError("No working interfaces available")
            
            # Initialize message router
            self.message_router = MessageRouter(
                health_check_interval=self.config.health_check_interval
            )
            
            # Add interfaces to message router
            for interface in interfaces:
                self.message_router.add_interface(interface)
            
            # Set routing policy
            if len(interfaces) > 1:
                self.message_router.set_routing_policy(RoutingPolicy.ALL)
            else:
                self.message_router.set_routing_policy(RoutingPolicy.PRIMARY)
            self.logger.info("Message router initialized")
            
            # Start health monitoring if enabled
            if self.config.health_check_interval > 0:
                self._start_health_monitoring()
                # Also start connection manager health monitoring
                self.connection_manager.start_health_monitoring()
            
            self._initialized = True
            self.logger.info("MeshtasticManager initialization completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"MeshtasticManager initialization failed: {e}")
            self._cleanup_partial_initialization()
            return False
    
    def _cleanup_partial_initialization(self) -> None:
        """Clean up partially initialized components"""
        try:
            if self.serial_interface:
                self.serial_interface.disconnect()
                self.serial_interface = None
            
            if self.mqtt_interface:
                self.mqtt_interface.disconnect()
                self.mqtt_interface = None
            
            if self.message_router:
                self.message_router = None
            
            if self.connection_manager:
                self.connection_manager = None
            
            if self.channel_manager:
                self.channel_manager = None
                
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def send_alert(self, aircraft: Any, alert_type: str) -> bool:
        """
        Send an aircraft alert through available Meshtastic interfaces
        
        Args:
            aircraft: Aircraft object with alert information
            alert_type: Type of alert (watchlist, emergency, etc.)
            
        Returns:
            True if message sent successfully through at least one interface
        """
        if not self._initialized:
            self.logger.error("MeshtasticManager not initialized")
            return False
        
        try:
            # Create alert message
            alert_message = self._create_alert_message(aircraft, alert_type)
            
            # Route message through available interfaces
            results = self.message_router.route_message(alert_message)
            
            # Record results in connection manager
            active_interfaces = self.connection_manager.get_active_interfaces()
            for i, result in enumerate(results):
                if i < len(active_interfaces):
                    interface = active_interfaces[i]
                    self.connection_manager.record_message_result(
                        interface, result, error=None if result else "Message delivery failed"
                    )
            
            # Update statistics
            if any(results):
                self._stats['messages_sent'] += 1
                if self.serial_interface and self.serial_interface in active_interfaces:
                    self._stats['serial_messages'] += 1
                if self.mqtt_interface and self.mqtt_interface in active_interfaces:
                    self._stats['mqtt_messages'] += 1
            else:
                self._stats['messages_failed'] += 1
            
            success = any(results)
            if success:
                self.logger.info(f"Alert sent successfully: {alert_type} for {getattr(aircraft, 'icao', 'unknown')}")
            else:
                self.logger.error(f"Failed to send alert: {alert_type} for {getattr(aircraft, 'icao', 'unknown')}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error sending alert: {e}")
            self._stats['messages_failed'] += 1
            return False
    
    def _create_alert_message(self, aircraft: Any, alert_type: str) -> AlertMessage:
        """
        Create an AlertMessage from aircraft data and alert type
        
        Args:
            aircraft: Aircraft object with alert information
            alert_type: Type of alert
            
        Returns:
            AlertMessage object ready for transmission
        """
        # Format message content based on configuration
        if self.config.message_format == "json":
            content = self._format_json_message(aircraft, alert_type)
        elif self.config.message_format == "compact":
            content = self._format_compact_message(aircraft, alert_type)
        else:  # standard
            content = self._format_standard_message(aircraft, alert_type)
        
        # Truncate if too long
        if len(content) > self.config.max_message_length:
            content = content[:self.config.max_message_length - 3] + "..."
        
        # Determine priority based on alert type
        priority = MessagePriority.HIGH if alert_type == "emergency" else MessagePriority.MEDIUM
        
        # Get position if available and enabled
        position = None
        if self.config.include_position and hasattr(aircraft, 'lat') and hasattr(aircraft, 'lon'):
            if aircraft.lat is not None and aircraft.lon is not None:
                position = (aircraft.lat, aircraft.lon)
        
        return AlertMessage(
            content=content,
            channel=self.config.default_channel,
            priority=priority,
            aircraft_icao=getattr(aircraft, 'icao', None),
            alert_type=alert_type,
            position=position,
            metadata={
                'callsign': getattr(aircraft, 'callsign', None),
                'altitude': getattr(aircraft, 'altitude', None),
                'speed': getattr(aircraft, 'speed', None),
                'heading': getattr(aircraft, 'heading', None)
            }
        )
    
    def _format_standard_message(self, aircraft: Any, alert_type: str) -> str:
        """Format message in standard human-readable format"""
        parts = []
        
        # Alert type and ICAO
        icao = getattr(aircraft, 'icao', 'UNKNOWN')
        parts.append(f"{alert_type.upper()}: {icao}")
        
        # Callsign if available
        callsign = getattr(aircraft, 'callsign', None)
        if callsign:
            parts.append(f"({callsign})")
        
        # Position if enabled and available
        if self.config.include_position:
            lat = getattr(aircraft, 'lat', None)
            lon = getattr(aircraft, 'lon', None)
            if lat is not None and lon is not None:
                parts.append(f"@{lat:.4f},{lon:.4f}")
        
        # Altitude if available
        altitude = getattr(aircraft, 'altitude', None)
        if altitude is not None:
            parts.append(f"FL{int(altitude/100):03d}")
        
        # Timestamp if enabled
        if self.config.include_timestamp:
            parts.append(f"[{datetime.now().strftime('%H:%M:%S')}]")
        
        return " ".join(parts)
    
    def _format_compact_message(self, aircraft: Any, alert_type: str) -> str:
        """Format message in compact format for bandwidth-limited scenarios"""
        icao = getattr(aircraft, 'icao', 'UNK')
        alert_code = alert_type[0].upper()  # First letter of alert type
        
        parts = [f"{alert_code}:{icao}"]
        
        # Position in compact format
        if self.config.include_position:
            lat = getattr(aircraft, 'lat', None)
            lon = getattr(aircraft, 'lon', None)
            if lat is not None and lon is not None:
                parts.append(f"{lat:.3f},{lon:.3f}")
        
        # Altitude in compact format
        altitude = getattr(aircraft, 'altitude', None)
        if altitude is not None:
            parts.append(f"A{int(altitude/100):03d}")
        
        return "|".join(parts)
    
    def _format_json_message(self, aircraft: Any, alert_type: str) -> str:
        """Format message as JSON for structured data transmission"""
        import json
        
        data = {
            'alert_type': alert_type,
            'icao': getattr(aircraft, 'icao', None),
            'callsign': getattr(aircraft, 'callsign', None),
            'timestamp': datetime.now().isoformat() if self.config.include_timestamp else None
        }
        
        if self.config.include_position:
            lat = getattr(aircraft, 'lat', None)
            lon = getattr(aircraft, 'lon', None)
            if lat is not None and lon is not None:
                data['position'] = {'lat': lat, 'lon': lon}
        
        # Add other aircraft data
        for attr in ['altitude', 'speed', 'heading']:
            value = getattr(aircraft, attr, None)
            if value is not None:
                data[attr] = value
        
        return json.dumps(data, separators=(',', ':'))  # Compact JSON
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get comprehensive connection status for all interfaces
        
        Returns:
            Dictionary with connection status information
        """
        if not self._initialized:
            return {
                'initialized': False,
                'error': 'MeshtasticManager not initialized'
            }
        
        status = {
            'initialized': True,
            'connection_mode': self.config.connection_mode,
            'interfaces': {},
            'statistics': self._stats.copy(),
            'health_monitoring': self._health_check_thread is not None and self._health_check_thread.is_alive()
        }
        
        # Get serial interface status
        if self.serial_interface:
            status['interfaces']['serial'] = self.serial_interface.get_connection_status().to_dict()
        
        # Get MQTT interface status
        if self.mqtt_interface:
            status['interfaces']['mqtt'] = self.mqtt_interface.get_connection_status().to_dict()
        
        # Get message router status
        if self.message_router:
            status['message_router'] = self.message_router.get_delivery_stats()
        
        # Get connection manager status
        if self.connection_manager:
            status['connection_manager'] = self.connection_manager.get_health_status()
        
        return status
    
    def configure_channels(self, channels: List[ChannelConfig]) -> bool:
        """
        Configure channels for all interfaces
        
        Args:
            channels: List of channel configurations
            
        Returns:
            True if configuration successful
        """
        if not self._initialized:
            self.logger.error("MeshtasticManager not initialized")
            return False
        
        try:
            # Update channel manager
            self.channel_manager = ChannelManager(channels)
            
            # Configure serial interface channels
            if self.serial_interface:
                if not self.serial_interface.configure_channels(channels):
                    self.logger.warning("Failed to configure serial interface channels")
            
            # MQTT interface channels are handled through channel manager
            
            self.logger.info(f"Configured {len(channels)} channels")
            return True
            
        except Exception as e:
            self.logger.error(f"Channel configuration failed: {e}")
            return False
    
    def get_device_info(self) -> Optional[Dict[str, Any]]:
        """
        Get device information from connected interfaces
        
        Returns:
            Dictionary with device information or None if not available
        """
        if not self._initialized:
            return None
        
        device_info = {}
        
        # Get serial device info
        if self.serial_interface:
            serial_info = self.serial_interface.get_device_info()
            if serial_info:
                device_info['serial'] = serial_info
        
        # Get MQTT connection info
        if self.mqtt_interface:
            mqtt_status = self.mqtt_interface.get_connection_status()
            if mqtt_status.is_connected:
                device_info['mqtt'] = {
                    'broker': self.config.mqtt.broker_url,
                    'connected_since': mqtt_status.connected_since.isoformat() if mqtt_status.connected_since else None,
                    'client_id': self.config.mqtt.client_id
                }
        
        return device_info if device_info else None
    
    def test_connectivity(self) -> Dict[str, bool]:
        """
        Test connectivity of all configured interfaces
        
        Returns:
            Dictionary mapping interface names to test results
        """
        if not self._initialized:
            return {'error': 'Not initialized'}
        
        results = {}
        
        # Test serial interface
        if self.serial_interface:
            results['serial'] = self.serial_interface.is_connected()
        
        # Test MQTT interface
        if self.mqtt_interface:
            results['mqtt'] = self.mqtt_interface.is_connected()
        
        return results
    
    def _start_health_monitoring(self) -> None:
        """Start background health monitoring thread"""
        if self._health_check_thread and self._health_check_thread.is_alive():
            return
        
        self._health_check_thread = threading.Thread(
            target=self._health_monitor_loop,
            name="MeshtasticHealthMonitor",
            daemon=True
        )
        self._health_check_thread.start()
        self.logger.info("Health monitoring started")
    
    def _health_monitor_loop(self) -> None:
        """Background health monitoring loop"""
        while not self._shutdown_requested:
            try:
                with self._health_check_lock:
                    self._perform_health_check()
                
                time.sleep(self.config.health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Health check error: {e}")
                time.sleep(min(self.config.health_check_interval, 30))
    
    def _perform_health_check(self) -> None:
        """Perform health check on all interfaces"""
        if not self._initialized:
            return
        
        # Check serial interface health
        if self.serial_interface:
            if not self.serial_interface.is_connected():
                self.logger.warning("Serial interface disconnected, attempting reconnection")
                if self.serial_interface.connect():
                    self.logger.info("Serial interface reconnected successfully")
                else:
                    self.logger.error("Serial interface reconnection failed")
        
        # Check MQTT interface health
        if self.mqtt_interface:
            if not self.mqtt_interface.is_connected():
                self.logger.warning("MQTT interface disconnected, attempting reconnection")
                if self.mqtt_interface.connect():
                    self.logger.info("MQTT interface reconnected successfully")
                else:
                    self.logger.error("MQTT interface reconnection failed")
        
        # Update message router with current interface states
        if self.message_router:
            self.message_router.update_interface_health()
        
        # Connection manager handles its own health monitoring
        # but we can trigger failover if needed
        if self.connection_manager and self.config.failover_enabled:
            if self.connection_manager.handle_failover():
                self._stats['failovers'] += 1
    
    def shutdown(self) -> None:
        """
        Gracefully shutdown all Meshtastic components
        """
        self.logger.info("Shutting down MeshtasticManager...")
        
        self._shutdown_requested = True
        
        # Stop health monitoring
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_thread.join(timeout=5)
        
        # Shutdown connection manager
        if self.connection_manager:
            self.connection_manager.shutdown()
        
        # Shutdown interfaces
        if self.serial_interface:
            self.serial_interface.disconnect()
        
        if self.mqtt_interface:
            self.mqtt_interface.disconnect()
        
        # Clear components
        self.message_router = None
        self.connection_manager = None
        self.channel_manager = None
        self.serial_interface = None
        self.mqtt_interface = None
        
        self._initialized = False
        self.logger.info("MeshtasticManager shutdown completed")