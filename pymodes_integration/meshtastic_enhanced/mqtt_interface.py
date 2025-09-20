"""
MQTT interface for enhanced Meshtastic integration

This module implements MQTT-based communication with Meshtastic networks
through MQTT brokers, providing network connectivity alongside serial interfaces.
"""

import json
import logging
import threading
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable
from uuid import uuid4

try:
    import paho.mqtt.client as mqtt
except ImportError:
    raise ImportError("paho-mqtt library is required. Install with: pip install paho-mqtt>=1.6.0")

from .interfaces import MeshtasticInterface
from .data_classes import (
    MQTTConfig, ConnectionStatus, ConnectionState, AlertMessage, 
    ChannelConfig, MessagePriority
)
from .exceptions import MeshtasticConnectionError, MeshtasticConfigError


class MQTTMessageHandler:
    """
    Handles MQTT message formatting, parsing, and topic generation
    """
    
    def __init__(self, config: MQTTConfig):
        """
        Initialize MQTT message handler
        
        Args:
            config: MQTT configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
    
    def format_outgoing_message(self, alert_data: Dict[str, Any], channel: str) -> str:
        """
        Format an alert message for MQTT transmission
        
        Args:
            alert_data: Dictionary containing alert information
            channel: Channel name for the message
            
        Returns:
            Formatted message string
        """
        try:
            # Create standardized message format
            message_data = {
                "timestamp": datetime.now().isoformat(),
                "channel": channel,
                "source": "ursine_explorer_adsb",
                "message_type": "aircraft_alert",
                "data": alert_data
            }
            
            # Convert to JSON for MQTT transmission
            return json.dumps(message_data, separators=(',', ':'))
            
        except Exception as e:
            self.logger.error(f"Error formatting outgoing message: {e}")
            # Fallback to simple text format
            return f"ADSB Alert: {alert_data.get('content', 'Unknown alert')}"
    
    def parse_incoming_message(self, topic: str, payload: bytes) -> Optional[Dict[str, Any]]:
        """
        Parse an incoming MQTT message
        
        Args:
            topic: MQTT topic the message was received on
            payload: Message payload bytes
            
        Returns:
            Parsed message dictionary or None if parsing failed
        """
        try:
            # Decode payload
            message_str = payload.decode('utf-8')
            
            # Try to parse as JSON first
            try:
                message_data = json.loads(message_str)
                return {
                    "topic": topic,
                    "parsed_data": message_data,
                    "raw_message": message_str,
                    "timestamp": datetime.now().isoformat()
                }
            except json.JSONDecodeError:
                # Handle as plain text message
                return {
                    "topic": topic,
                    "parsed_data": {"content": message_str},
                    "raw_message": message_str,
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            self.logger.error(f"Error parsing incoming message from topic {topic}: {e}")
            return None
    
    def get_topic_for_channel(self, channel: str, message_type: str = "json") -> str:
        """
        Generate MQTT topic for a specific channel and message type
        
        Args:
            channel: Channel name
            message_type: Type of message ("json", "text", "c", etc.)
            
        Returns:
            Complete MQTT topic string
        """
        # Standard Meshtastic MQTT topic format: msh/US/2/json/LongFast/!4358bcb4
        # For our purposes, we'll use a simplified format
        base_topic = self.config.topic_prefix.rstrip('/')
        
        # Generate a simple node ID for our client
        node_id = f"!{hash(self.config.client_id or 'ursine') & 0xffffffff:08x}"
        
        return f"{base_topic}/2/{message_type}/{channel}/{node_id}"
    
    def get_subscription_topics(self, channels: List[str]) -> List[str]:
        """
        Get list of topics to subscribe to for receiving messages
        
        Args:
            channels: List of channel names to subscribe to
            
        Returns:
            List of MQTT topic patterns for subscription
        """
        base_topic = self.config.topic_prefix.rstrip('/')
        topics = []
        
        for channel in channels:
            # Subscribe to all message types for each channel
            topics.append(f"{base_topic}/2/+/{channel}/+")
        
        return topics


class MeshtasticMQTTInterface(MeshtasticInterface):
    """
    MQTT-based Meshtastic interface for network connectivity
    
    This interface connects to Meshtastic networks through MQTT brokers,
    providing an alternative to direct serial connections.
    """
    
    def __init__(self, mqtt_config: MQTTConfig, channels: List[ChannelConfig]):
        """
        Initialize MQTT interface
        
        Args:
            mqtt_config: MQTT broker configuration
            channels: List of available channels
        """
        self.config = mqtt_config
        self.channels = {ch.name: ch for ch in channels}
        self.logger = logging.getLogger(__name__)
        
        # MQTT client setup
        self.client_id = mqtt_config.client_id or f"ursine_adsb_{uuid4().hex[:8]}"
        self.client = mqtt.Client(client_id=self.client_id, clean_session=mqtt_config.clean_session)
        
        # Message handler
        self.message_handler = MQTTMessageHandler(mqtt_config)
        
        # Connection state
        self._connection_state = ConnectionState.DISCONNECTED
        self._connected_since: Optional[datetime] = None
        self._last_message_time: Optional[datetime] = None
        self._error_message: Optional[str] = None
        self._connection_lock = threading.Lock()
        
        # Statistics
        self._stats = {
            "messages_sent": 0,
            "messages_received": 0,
            "connection_attempts": 0,
            "last_error": None,
            "bytes_sent": 0,
            "bytes_received": 0
        }
        
        # Message callbacks
        self._message_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        # Setup MQTT client callbacks
        self._setup_mqtt_callbacks()
    
    def _setup_mqtt_callbacks(self) -> None:
        """Setup MQTT client event callbacks"""
        
        def on_connect(client, userdata, flags, rc):
            """Handle MQTT connection events"""
            if rc == 0:
                self.logger.info(f"MQTT connected to {self.config.broker_url}:{self.config.port}")
                with self._connection_lock:
                    self._connection_state = ConnectionState.CONNECTED
                    self._connected_since = datetime.now()
                    self._error_message = None
                
                # Subscribe to channels
                self._subscribe_to_channels()
                
            else:
                error_msg = f"MQTT connection failed with code {rc}"
                self.logger.error(error_msg)
                with self._connection_lock:
                    self._connection_state = ConnectionState.ERROR
                    self._error_message = error_msg
        
        def on_disconnect(client, userdata, rc):
            """Handle MQTT disconnection events"""
            if rc != 0:
                self.logger.warning(f"MQTT unexpected disconnection (code {rc})")
                with self._connection_lock:
                    self._connection_state = ConnectionState.RECONNECTING
            else:
                self.logger.info("MQTT disconnected")
                with self._connection_lock:
                    self._connection_state = ConnectionState.DISCONNECTED
                    self._connected_since = None
        
        def on_message(client, userdata, msg):
            """Handle incoming MQTT messages"""
            try:
                self._stats["messages_received"] += 1
                self._stats["bytes_received"] += len(msg.payload)
                self._last_message_time = datetime.now()
                
                # Parse message
                parsed_msg = self.message_handler.parse_incoming_message(msg.topic, msg.payload)
                if parsed_msg:
                    self.logger.debug(f"Received MQTT message on {msg.topic}: {parsed_msg}")
                    
                    # Notify callbacks
                    for callback in self._message_callbacks:
                        try:
                            callback(parsed_msg)
                        except Exception as e:
                            self.logger.error(f"Error in message callback: {e}")
                
            except Exception as e:
                self.logger.error(f"Error processing MQTT message: {e}")
        
        def on_publish(client, userdata, mid):
            """Handle message publish confirmation"""
            self.logger.debug(f"MQTT message published (mid: {mid})")
        
        def on_log(client, userdata, level, buf):
            """Handle MQTT client log messages"""
            if level == mqtt.MQTT_LOG_DEBUG:
                self.logger.debug(f"MQTT: {buf}")
            elif level == mqtt.MQTT_LOG_INFO:
                self.logger.info(f"MQTT: {buf}")
            elif level == mqtt.MQTT_LOG_WARNING:
                self.logger.warning(f"MQTT: {buf}")
            elif level == mqtt.MQTT_LOG_ERR:
                self.logger.error(f"MQTT: {buf}")
        
        # Assign callbacks
        self.client.on_connect = on_connect
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message
        self.client.on_publish = on_publish
        self.client.on_log = on_log
    
    def _subscribe_to_channels(self) -> None:
        """Subscribe to MQTT topics for configured channels"""
        try:
            channel_names = list(self.channels.keys())
            topics = self.message_handler.get_subscription_topics(channel_names)
            
            for topic in topics:
                result = self.client.subscribe(topic, qos=self.config.qos)
                if result[0] == mqtt.MQTT_ERR_SUCCESS:
                    self.logger.debug(f"Subscribed to MQTT topic: {topic}")
                else:
                    self.logger.error(f"Failed to subscribe to MQTT topic {topic}: {result}")
                    
        except Exception as e:
            self.logger.error(f"Error subscribing to MQTT channels: {e}")
    
    def connect(self) -> bool:
        """
        Establish connection to MQTT broker
        
        Returns:
            True if connection successful, False otherwise
        """
        try:
            with self._connection_lock:
                if self._connection_state == ConnectionState.CONNECTED:
                    return True
                
                self._connection_state = ConnectionState.CONNECTING
                self._stats["connection_attempts"] += 1
            
            # Configure authentication if provided
            if self.config.username and self.config.password:
                self.client.username_pw_set(self.config.username, self.config.password)
            
            # Configure TLS if enabled
            if self.config.use_tls:
                self.client.tls_set()
            
            # Configure last will if provided
            if self.config.will_topic and self.config.will_message:
                self.client.will_set(
                    self.config.will_topic,
                    self.config.will_message,
                    qos=self.config.qos,
                    retain=False
                )
            
            # Attempt connection
            self.logger.info(f"Connecting to MQTT broker {self.config.broker_url}:{self.config.port}")
            self.client.connect(
                self.config.broker_url,
                self.config.port,
                self.config.keepalive
            )
            
            # Start network loop
            self.client.loop_start()
            
            # Wait for connection with timeout
            timeout = 10  # seconds
            start_time = time.time()
            while time.time() - start_time < timeout:
                with self._connection_lock:
                    if self._connection_state == ConnectionState.CONNECTED:
                        return True
                    elif self._connection_state == ConnectionState.ERROR:
                        return False
                time.sleep(0.1)
            
            # Timeout reached
            self.logger.error("MQTT connection timeout")
            with self._connection_lock:
                self._connection_state = ConnectionState.ERROR
                self._error_message = "Connection timeout"
            
            return False
            
        except Exception as e:
            error_msg = f"MQTT connection error: {e}"
            self.logger.error(error_msg)
            with self._connection_lock:
                self._connection_state = ConnectionState.ERROR
                self._error_message = error_msg
                self._stats["last_error"] = error_msg
            return False
    
    def disconnect(self) -> None:
        """Disconnect from MQTT broker"""
        try:
            self.logger.info("Disconnecting from MQTT broker")
            self.client.loop_stop()
            self.client.disconnect()
            
            with self._connection_lock:
                self._connection_state = ConnectionState.DISCONNECTED
                self._connected_since = None
                
        except Exception as e:
            self.logger.error(f"Error during MQTT disconnect: {e}")
    
    def send_message(self, message: str, channel: Optional[str] = None) -> bool:
        """
        Send a message through MQTT
        
        Args:
            message: Message content to send
            channel: Optional channel name (uses default if None)
            
        Returns:
            True if message sent successfully, False otherwise
        """
        try:
            if not self.is_connected():
                self.logger.error("Cannot send MQTT message: not connected")
                return False
            
            # Determine channel
            if channel is None:
                channel = next(iter(self.channels.keys())) if self.channels else "LongFast"
            
            if channel not in self.channels:
                self.logger.warning(f"Unknown channel {channel}, using first available")
                channel = next(iter(self.channels.keys())) if self.channels else "LongFast"
            
            # Format message for MQTT
            alert_data = {
                "content": message,
                "channel": channel,
                "timestamp": datetime.now().isoformat()
            }
            
            formatted_message = self.message_handler.format_outgoing_message(alert_data, channel)
            
            # Get topic for channel
            topic = self.message_handler.get_topic_for_channel(channel, "json")
            
            # Publish message
            result = self.client.publish(
                topic,
                formatted_message,
                qos=self.config.qos,
                retain=False
            )
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self._stats["messages_sent"] += 1
                self._stats["bytes_sent"] += len(formatted_message.encode('utf-8'))
                self._last_message_time = datetime.now()
                
                self.logger.debug(f"MQTT message sent to {topic}: {message}")
                return True
            else:
                self.logger.error(f"MQTT publish failed with code {result.rc}")
                return False
                
        except Exception as e:
            error_msg = f"Error sending MQTT message: {e}"
            self.logger.error(error_msg)
            self._stats["last_error"] = error_msg
            return False
    
    def is_connected(self) -> bool:
        """
        Check if MQTT interface is connected
        
        Returns:
            True if connected, False otherwise
        """
        with self._connection_lock:
            return self._connection_state == ConnectionState.CONNECTED
    
    def get_connection_status(self) -> ConnectionStatus:
        """
        Get detailed connection status
        
        Returns:
            ConnectionStatus object with current status
        """
        with self._connection_lock:
            return ConnectionStatus(
                interface_type="mqtt",
                state=self._connection_state,
                connected_since=self._connected_since,
                last_message_time=self._last_message_time,
                error_message=self._error_message,
                device_info={
                    "broker_url": self.config.broker_url,
                    "port": self.config.port,
                    "client_id": self.client_id,
                    "use_tls": self.config.use_tls,
                    "topic_prefix": self.config.topic_prefix
                },
                statistics=self._stats.copy()
            )
    
    def get_interface_type(self) -> str:
        """
        Get interface type identifier
        
        Returns:
            "mqtt"
        """
        return "mqtt"
    
    def add_message_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Add callback for incoming messages
        
        Args:
            callback: Function to call when messages are received
        """
        self._message_callbacks.append(callback)
    
    def remove_message_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """
        Remove message callback
        
        Args:
            callback: Callback function to remove
        """
        if callback in self._message_callbacks:
            self._message_callbacks.remove(callback)
    
    def subscribe_to_channels(self, channels: List[str]) -> bool:
        """
        Subscribe to specific channels for incoming messages
        
        Args:
            channels: List of channel names to subscribe to
            
        Returns:
            True if subscription successful, False otherwise
        """
        try:
            if not self.is_connected():
                self.logger.error("Cannot subscribe to channels: not connected")
                return False
            
            topics = self.message_handler.get_subscription_topics(channels)
            success = True
            
            for topic in topics:
                result = self.client.subscribe(topic, qos=self.config.qos)
                if result[0] != mqtt.MQTT_ERR_SUCCESS:
                    self.logger.error(f"Failed to subscribe to {topic}: {result}")
                    success = False
                else:
                    self.logger.debug(f"Subscribed to {topic}")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Error subscribing to channels: {e}")
            return False
    
    def get_broker_info(self) -> Dict[str, Any]:
        """
        Get information about the MQTT broker connection
        
        Returns:
            Dictionary with broker information
        """
        return {
            "broker_url": self.config.broker_url,
            "port": self.config.port,
            "client_id": self.client_id,
            "use_tls": self.config.use_tls,
            "topic_prefix": self.config.topic_prefix,
            "qos": self.config.qos,
            "keepalive": self.config.keepalive,
            "clean_session": self.config.clean_session
        }