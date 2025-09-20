"""
Unit tests for MQTT interface components

Tests the MQTTConfig, MQTTMessageHandler, and MeshtasticMQTTInterface classes
to ensure proper MQTT functionality and message handling.
"""

import json
import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from typing import Dict, Any

# Import the classes to test
from .mqtt_interface import MQTTMessageHandler, MeshtasticMQTTInterface
from .data_classes import MQTTConfig, ChannelConfig, ConnectionState, MessagePriority
from .exceptions import MeshtasticConnectionError, MeshtasticConfigError


class TestMQTTConfig(unittest.TestCase):
    """Test MQTTConfig data class"""
    
    def test_mqtt_config_creation(self):
        """Test basic MQTT config creation"""
        config = MQTTConfig(
            broker_url="mqtt.example.com",
            port=1883,
            username="testuser",
            password="testpass"
        )
        
        self.assertEqual(config.broker_url, "mqtt.example.com")
        self.assertEqual(config.port, 1883)
        self.assertEqual(config.username, "testuser")
        self.assertEqual(config.password, "testpass")
        self.assertEqual(config.qos, 0)  # default
        self.assertEqual(config.topic_prefix, "msh/US")  # default
    
    def test_mqtt_config_defaults(self):
        """Test MQTT config with default values"""
        config = MQTTConfig(broker_url="test.broker.com")
        
        self.assertEqual(config.port, 1883)
        self.assertEqual(config.qos, 0)
        self.assertEqual(config.keepalive, 60)
        self.assertEqual(config.topic_prefix, "msh/US")
        self.assertFalse(config.use_tls)
        self.assertTrue(config.clean_session)
        self.assertIsNone(config.username)
        self.assertIsNone(config.password)
    
    def test_mqtt_config_validation(self):
        """Test MQTT config validation"""
        # Test empty broker URL
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="")
        
        # Test invalid port
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", port=0)
        
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", port=70000)
        
        # Test invalid QoS
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", qos=3)
        
        # Test invalid keepalive
        with self.assertRaises(ValueError):
            MQTTConfig(broker_url="test.com", keepalive=0)
    
    def test_mqtt_config_serialization(self):
        """Test MQTT config to/from dict conversion"""
        config = MQTTConfig(
            broker_url="mqtt.test.com",
            port=8883,
            username="user",
            password="pass",
            use_tls=True,
            qos=1
        )
        
        # Test to_dict
        config_dict = config.to_dict()
        expected_keys = [
            'broker_url', 'port', 'username', 'password', 'use_tls',
            'client_id', 'topic_prefix', 'qos', 'keepalive', 'clean_session',
            'will_topic', 'will_message'
        ]
        
        for key in expected_keys:
            self.assertIn(key, config_dict)
        
        # Test from_dict
        restored_config = MQTTConfig.from_dict(config_dict)
        self.assertEqual(restored_config.broker_url, config.broker_url)
        self.assertEqual(restored_config.port, config.port)
        self.assertEqual(restored_config.username, config.username)
        self.assertEqual(restored_config.use_tls, config.use_tls)
        self.assertEqual(restored_config.qos, config.qos)


class TestMQTTMessageHandler(unittest.TestCase):
    """Test MQTTMessageHandler class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.config = MQTTConfig(
            broker_url="test.broker.com",
            topic_prefix="msh/US",
            client_id="test_client"
        )
        self.handler = MQTTMessageHandler(self.config)
    
    def test_format_outgoing_message(self):
        """Test formatting outgoing messages"""
        alert_data = {
            "content": "Test aircraft alert",
            "aircraft_icao": "ABC123",
            "alert_type": "watchlist"
        }
        
        formatted = self.handler.format_outgoing_message(alert_data, "LongFast")
        
        # Should be valid JSON
        parsed = json.loads(formatted)
        
        self.assertIn("timestamp", parsed)
        self.assertEqual(parsed["channel"], "LongFast")
        self.assertEqual(parsed["source"], "ursine_explorer_adsb")
        self.assertEqual(parsed["message_type"], "aircraft_alert")
        self.assertEqual(parsed["data"], alert_data)
    
    def test_format_outgoing_message_error_handling(self):
        """Test error handling in message formatting"""
        # Test with problematic data that might cause JSON serialization issues
        class UnserializableObject:
            def __str__(self):
                raise Exception("Cannot serialize")
        
        alert_data = {
            "content": "Test message",
            "problematic_data": UnserializableObject()
        }
        
        # Should fall back to simple text format
        formatted = self.handler.format_outgoing_message(alert_data, "LongFast")
        self.assertIn("ADSB Alert", formatted)
    
    def test_parse_incoming_message_json(self):
        """Test parsing incoming JSON messages"""
        message_data = {
            "timestamp": "2024-01-01T12:00:00",
            "channel": "LongFast",
            "content": "Test message from mesh"
        }
        
        payload = json.dumps(message_data).encode('utf-8')
        topic = "msh/US/2/json/LongFast/!12345678"
        
        parsed = self.handler.parse_incoming_message(topic, payload)
        
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["topic"], topic)
        self.assertEqual(parsed["parsed_data"], message_data)
        self.assertIn("timestamp", parsed)
    
    def test_parse_incoming_message_text(self):
        """Test parsing incoming plain text messages"""
        message_text = "Plain text message from mesh"
        payload = message_text.encode('utf-8')
        topic = "msh/US/2/text/LongFast/!12345678"
        
        parsed = self.handler.parse_incoming_message(topic, payload)
        
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["topic"], topic)
        self.assertEqual(parsed["parsed_data"]["content"], message_text)
        self.assertEqual(parsed["raw_message"], message_text)
    
    def test_parse_incoming_message_invalid(self):
        """Test parsing invalid incoming messages"""
        # Test with invalid UTF-8
        payload = b'\xff\xfe\xfd'
        topic = "msh/US/2/json/LongFast/!12345678"
        
        parsed = self.handler.parse_incoming_message(topic, payload)
        self.assertIsNone(parsed)
    
    def test_get_topic_for_channel(self):
        """Test topic generation for channels"""
        topic = self.handler.get_topic_for_channel("LongFast", "json")
        
        # Should follow format: msh/US/2/json/LongFast/!xxxxxxxx
        parts = topic.split('/')
        self.assertEqual(len(parts), 6)
        self.assertEqual(parts[0], "msh")
        self.assertEqual(parts[1], "US")
        self.assertEqual(parts[2], "2")
        self.assertEqual(parts[3], "json")
        self.assertEqual(parts[4], "LongFast")
        self.assertTrue(parts[5].startswith("!"))
    
    def test_get_subscription_topics(self):
        """Test subscription topic generation"""
        channels = ["LongFast", "SecureChannel"]
        topics = self.handler.get_subscription_topics(channels)
        
        self.assertEqual(len(topics), 2)
        
        # Each topic should be a wildcard pattern for the channel
        for i, channel in enumerate(channels):
            expected = f"msh/US/2/+/{channel}/+"
            self.assertEqual(topics[i], expected)


class TestMeshtasticMQTTInterface(unittest.TestCase):
    """Test MeshtasticMQTTInterface class"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mqtt_config = MQTTConfig(
            broker_url="test.broker.com",
            port=1883,
            client_id="test_client"
        )
        
        self.channels = [
            ChannelConfig(name="LongFast", channel_number=0),
            ChannelConfig(name="SecureChannel", psk="dGVzdGtleQ==", channel_number=1)
        ]
        
        # Mock the MQTT client to avoid actual network connections
        with patch('pymodes_integration.meshtastic_enhanced.mqtt_interface.mqtt.Client'):
            self.interface = MeshtasticMQTTInterface(self.mqtt_config, self.channels)
    
    def test_interface_initialization(self):
        """Test MQTT interface initialization"""
        self.assertEqual(self.interface.config, self.mqtt_config)
        self.assertEqual(len(self.interface.channels), 2)
        self.assertIn("LongFast", self.interface.channels)
        self.assertIn("SecureChannel", self.interface.channels)
        self.assertEqual(self.interface.get_interface_type(), "mqtt")
    
    def test_get_connection_status(self):
        """Test connection status reporting"""
        status = self.interface.get_connection_status()
        
        self.assertEqual(status.interface_type, "mqtt")
        self.assertEqual(status.state, ConnectionState.DISCONNECTED)
        self.assertIsNotNone(status.device_info)
        self.assertIn("broker_url", status.device_info)
        self.assertIn("client_id", status.device_info)
    
    def test_is_connected_initial_state(self):
        """Test initial connection state"""
        self.assertFalse(self.interface.is_connected())
    
    @patch('pymodes_integration.meshtastic_enhanced.mqtt_interface.mqtt.Client')
    def test_connect_success(self, mock_client_class):
        """Test successful MQTT connection"""
        # Setup mock client
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.connect.return_value = None
        
        # Create new interface with mocked client
        interface = MeshtasticMQTTInterface(self.mqtt_config, self.channels)
        
        # Simulate successful connection by manually setting state
        # (in real usage, this would be set by the on_connect callback)
        def simulate_connect(*args, **kwargs):
            interface._connection_state = ConnectionState.CONNECTED
            interface._connected_since = datetime.now()
        
        mock_client.connect.side_effect = simulate_connect
        
        # Test connection
        result = interface.connect()
        
        # Verify client setup
        mock_client.username_pw_set.assert_not_called()  # No auth configured
        mock_client.connect.assert_called_once()
        mock_client.loop_start.assert_called_once()
    
    @patch('pymodes_integration.meshtastic_enhanced.mqtt_interface.mqtt.Client')
    def test_connect_with_authentication(self, mock_client_class):
        """Test MQTT connection with authentication"""
        # Setup config with auth
        auth_config = MQTTConfig(
            broker_url="test.broker.com",
            username="testuser",
            password="testpass"
        )
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        interface = MeshtasticMQTTInterface(auth_config, self.channels)
        
        # Simulate successful connection
        def simulate_connect(*args, **kwargs):
            interface._connection_state = ConnectionState.CONNECTED
            interface._connected_since = datetime.now()
        
        mock_client.connect.side_effect = simulate_connect
        
        interface.connect()
        
        # Verify authentication was set
        mock_client.username_pw_set.assert_called_once_with("testuser", "testpass")
    
    @patch('pymodes_integration.meshtastic_enhanced.mqtt_interface.mqtt.Client')
    def test_connect_with_tls(self, mock_client_class):
        """Test MQTT connection with TLS"""
        # Setup config with TLS
        tls_config = MQTTConfig(
            broker_url="test.broker.com",
            use_tls=True
        )
        
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        interface = MeshtasticMQTTInterface(tls_config, self.channels)
        
        # Simulate successful connection
        def simulate_connect(*args, **kwargs):
            interface._connection_state = ConnectionState.CONNECTED
            interface._connected_since = datetime.now()
        
        mock_client.connect.side_effect = simulate_connect
        
        interface.connect()
        
        # Verify TLS was configured
        mock_client.tls_set.assert_called_once()
    
    def test_send_message_not_connected(self):
        """Test sending message when not connected"""
        result = self.interface.send_message("Test message")
        self.assertFalse(result)
    
    @patch('pymodes_integration.meshtastic_enhanced.mqtt_interface.mqtt.Client')
    def test_send_message_success(self, mock_client_class):
        """Test successful message sending"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Mock successful publish
        mock_result = Mock()
        mock_result.rc = 0  # MQTT_ERR_SUCCESS
        mock_client.publish.return_value = mock_result
        
        interface = MeshtasticMQTTInterface(self.mqtt_config, self.channels)
        interface._connection_state = ConnectionState.CONNECTED
        
        result = interface.send_message("Test message", "LongFast")
        
        self.assertTrue(result)
        mock_client.publish.assert_called_once()
        
        # Verify statistics were updated
        self.assertEqual(interface._stats["messages_sent"], 1)
        self.assertGreater(interface._stats["bytes_sent"], 0)
    
    def test_disconnect(self):
        """Test MQTT disconnection"""
        # Mock the client
        self.interface.client = Mock()
        
        self.interface.disconnect()
        
        self.interface.client.loop_stop.assert_called_once()
        self.interface.client.disconnect.assert_called_once()
        self.assertEqual(self.interface._connection_state, ConnectionState.DISCONNECTED)
    
    def test_message_callbacks(self):
        """Test message callback functionality"""
        callback1 = Mock()
        callback2 = Mock()
        
        # Add callbacks
        self.interface.add_message_callback(callback1)
        self.interface.add_message_callback(callback2)
        
        self.assertEqual(len(self.interface._message_callbacks), 2)
        
        # Remove callback
        self.interface.remove_message_callback(callback1)
        self.assertEqual(len(self.interface._message_callbacks), 1)
        self.assertIn(callback2, self.interface._message_callbacks)
    
    def test_get_broker_info(self):
        """Test broker information retrieval"""
        info = self.interface.get_broker_info()
        
        expected_keys = [
            "broker_url", "port", "client_id", "use_tls", 
            "topic_prefix", "qos", "keepalive", "clean_session"
        ]
        
        for key in expected_keys:
            self.assertIn(key, info)
        
        self.assertEqual(info["broker_url"], self.mqtt_config.broker_url)
        self.assertEqual(info["port"], self.mqtt_config.port)


class TestMQTTIntegration(unittest.TestCase):
    """Integration tests for MQTT components"""
    
    def setUp(self):
        """Set up integration test fixtures"""
        self.mqtt_config = MQTTConfig(
            broker_url="test.broker.com",
            topic_prefix="test/msh",
            client_id="integration_test"
        )
        
        self.channels = [
            ChannelConfig(name="TestChannel", channel_number=0),
            ChannelConfig(name="SecureTest", psk="dGVzdA==", channel_number=1)
        ]
    
    @patch('pymodes_integration.meshtastic_enhanced.mqtt_interface.mqtt.Client')
    def test_end_to_end_message_flow(self, mock_client_class):
        """Test complete message flow from send to receive"""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Setup successful publish
        mock_result = Mock()
        mock_result.rc = 0
        mock_client.publish.return_value = mock_result
        
        interface = MeshtasticMQTTInterface(self.mqtt_config, self.channels)
        interface._connection_state = ConnectionState.CONNECTED
        
        # Add message callback to capture received messages
        received_messages = []
        interface.add_message_callback(lambda msg: received_messages.append(msg))
        
        # Send a message
        success = interface.send_message("Integration test message", "TestChannel")
        self.assertTrue(success)
        
        # Simulate receiving a message by calling the on_message callback
        test_message = {
            "timestamp": datetime.now().isoformat(),
            "content": "Response message"
        }
        
        mock_msg = Mock()
        mock_msg.topic = "test/msh/2/json/TestChannel/!12345678"
        mock_msg.payload = json.dumps(test_message).encode('utf-8')
        
        # Trigger the on_message callback
        interface.client.on_message(mock_client, None, mock_msg)
        
        # Verify message was received and processed
        self.assertEqual(len(received_messages), 1)
        self.assertEqual(received_messages[0]["topic"], mock_msg.topic)
        self.assertEqual(received_messages[0]["parsed_data"], test_message)
    
    def test_channel_topic_consistency(self):
        """Test that topics are generated consistently for channels"""
        handler = MQTTMessageHandler(self.mqtt_config)
        
        # Generate topics for different message types
        json_topic = handler.get_topic_for_channel("TestChannel", "json")
        text_topic = handler.get_topic_for_channel("TestChannel", "text")
        
        # Both should have same base but different message type
        json_parts = json_topic.split('/')
        text_parts = text_topic.split('/')
        
        # Everything should be same except message type (index 3)
        self.assertEqual(json_parts[:3], text_parts[:3])  # prefix, region, hop
        self.assertEqual(json_parts[4:], text_parts[4:])  # channel, node_id
        self.assertEqual(json_parts[3], "json")
        self.assertEqual(text_parts[3], "text")
        self.assertEqual(json_parts[4], "TestChannel")  # Channel name
        self.assertEqual(text_parts[4], "TestChannel")  # Channel name


if __name__ == '__main__':
    # Configure logging for tests
    import logging
    logging.basicConfig(level=logging.DEBUG)
    
    # Run tests
    unittest.main()