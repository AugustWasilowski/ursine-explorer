"""
Comprehensive diagnostics and monitoring for enhanced Meshtastic integration

This module implements the MeshtasticDiagnostics class that provides
comprehensive diagnostics for connection health monitoring, message delivery
statistics, performance metrics, interface testing, and configuration validation.
"""

import logging
import time
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

from .interfaces import DiagnosticsInterface, MeshtasticInterface
from .data_classes import (
    MeshtasticConfig, ChannelConfig, MQTTConfig, AlertMessage,
    ConnectionStatus, ConnectionState, MessagePriority
)
from .meshtastic_manager import MeshtasticManager
from .connection_manager import ConnectionManager
from .message_router import MessageRouter
from .channel_manager import ChannelManager
from .exceptions import (
    MeshtasticError, MeshtasticConfigError, MeshtasticConnectionError,
    ConfigurationError, ConnectionError
)


logger = logging.getLogger(__name__)


class DiagnosticTest:
    """Represents a single diagnostic test result"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.passed = False
        self.error_message: Optional[str] = None
        self.details: Dict[str, Any] = {}
        self.execution_time: float = 0.0
        self.timestamp = datetime.now()
    
    def mark_passed(self, details: Dict[str, Any] = None) -> None:
        """Mark test as passed with optional details"""
        self.passed = True
        self.error_message = None
        if details:
            self.details.update(details)
    
    def mark_failed(self, error_message: str, details: Dict[str, Any] = None) -> None:
        """Mark test as failed with error message and optional details"""
        self.passed = False
        self.error_message = error_message
        if details:
            self.details.update(details)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert test result to dictionary"""
        return {
            'name': self.name,
            'description': self.description,
            'passed': self.passed,
            'error_message': self.error_message,
            'details': self.details,
            'execution_time': self.execution_time,
            'timestamp': self.timestamp.isoformat()
        }


class PerformanceMetrics:
    """Tracks performance metrics for Meshtastic operations"""
    
    def __init__(self):
        self.message_latencies: List[float] = []
        self.connection_times: List[float] = []
        self.throughput_samples: List[Tuple[datetime, int]] = []  # (timestamp, messages_per_minute)
        self.error_rates: List[Tuple[datetime, float]] = []  # (timestamp, error_rate_percentage)
        self.memory_usage: List[Tuple[datetime, float]] = []  # (timestamp, memory_mb)
        self.cpu_usage: List[Tuple[datetime, float]] = []  # (timestamp, cpu_percentage)
        
        # Aggregated metrics
        self.total_messages_processed = 0
        self.total_errors = 0
        self.start_time = datetime.now()
    
    def record_message_latency(self, latency: float) -> None:
        """Record message delivery latency"""
        self.message_latencies.append(latency)
        self.total_messages_processed += 1
        
        # Keep only last 1000 samples
        if len(self.message_latencies) > 1000:
            self.message_latencies = self.message_latencies[-1000:]
    
    def record_connection_time(self, connection_time: float) -> None:
        """Record interface connection time"""
        self.connection_times.append(connection_time)
        
        # Keep only last 100 samples
        if len(self.connection_times) > 100:
            self.connection_times = self.connection_times[-100:]
    
    def record_error(self) -> None:
        """Record an error occurrence"""
        self.total_errors += 1
    
    def record_throughput_sample(self, messages_count: int) -> None:
        """Record throughput sample"""
        self.throughput_samples.append((datetime.now(), messages_count))
        
        # Keep only last 60 samples (1 hour if sampled every minute)
        if len(self.throughput_samples) > 60:
            self.throughput_samples = self.throughput_samples[-60:]
    
    def record_error_rate_sample(self, error_rate: float) -> None:
        """Record error rate sample"""
        self.error_rates.append((datetime.now(), error_rate))
        
        # Keep only last 60 samples
        if len(self.error_rates) > 60:
            self.error_rates = self.error_rates[-60:]
    
    def get_average_latency(self) -> float:
        """Get average message latency"""
        return sum(self.message_latencies) / len(self.message_latencies) if self.message_latencies else 0.0
    
    def get_p95_latency(self) -> float:
        """Get 95th percentile latency"""
        if not self.message_latencies:
            return 0.0
        sorted_latencies = sorted(self.message_latencies)
        index = int(0.95 * len(sorted_latencies))
        return sorted_latencies[index] if index < len(sorted_latencies) else sorted_latencies[-1]
    
    def get_average_connection_time(self) -> float:
        """Get average connection time"""
        return sum(self.connection_times) / len(self.connection_times) if self.connection_times else 0.0
    
    def get_current_error_rate(self) -> float:
        """Get current error rate as percentage"""
        if self.total_messages_processed == 0:
            return 0.0
        return (self.total_errors / self.total_messages_processed) * 100.0
    
    def get_uptime_seconds(self) -> float:
        """Get system uptime in seconds"""
        return (datetime.now() - self.start_time).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary"""
        return {
            'total_messages_processed': self.total_messages_processed,
            'total_errors': self.total_errors,
            'current_error_rate': self.get_current_error_rate(),
            'average_latency': self.get_average_latency(),
            'p95_latency': self.get_p95_latency(),
            'average_connection_time': self.get_average_connection_time(),
            'uptime_seconds': self.get_uptime_seconds(),
            'throughput_samples': [(ts.isoformat(), count) for ts, count in self.throughput_samples[-10:]],
            'error_rate_samples': [(ts.isoformat(), rate) for ts, rate in self.error_rates[-10:]]
        }


class MeshtasticDiagnostics(DiagnosticsInterface):
    """
    Comprehensive diagnostics for enhanced Meshtastic integration
    
    Provides connection health monitoring, message delivery statistics,
    performance metrics, interface testing, and configuration validation.
    """
    
    def __init__(self, manager: Optional[MeshtasticManager] = None):
        """
        Initialize diagnostics system
        
        Args:
            manager: Optional MeshtasticManager instance to monitor
        """
        self.manager = manager
        self.logger = logging.getLogger(__name__)
        self.performance_metrics = PerformanceMetrics()
        
        # Test results cache
        self._last_test_results: Dict[str, DiagnosticTest] = {}
        self._last_full_test_time: Optional[datetime] = None
        
        # Configuration validation cache
        self._last_config_validation: Optional[Tuple[datetime, List[str]]] = None
        
        self.logger.info("MeshtasticDiagnostics initialized")
    
    def get_connection_health(self) -> Dict[str, Any]:
        """
        Get comprehensive connection health information for all components
        
        Returns:
            Dictionary with health status for all components
        """
        health_info = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'unknown',
            'manager_status': {},
            'interfaces': {},
            'connection_manager': {},
            'message_router': {},
            'channel_manager': {},
            'performance_metrics': self.performance_metrics.to_dict()
        }
        
        if not self.manager:
            health_info['overall_status'] = 'no_manager'
            health_info['error'] = 'No MeshtasticManager instance provided'
            return health_info
        
        try:
            # Get manager status
            manager_status = self.manager.get_connection_status()
            health_info['manager_status'] = manager_status
            
            # Determine overall status based on manager initialization and interfaces
            if not manager_status.get('initialized', False):
                health_info['overall_status'] = 'not_initialized'
            else:
                # Check interface health
                interfaces = manager_status.get('interfaces', {})
                healthy_interfaces = 0
                total_interfaces = len(interfaces)
                
                for interface_name, interface_status in interfaces.items():
                    is_connected = interface_status.get('connection_status', {}).get('state') == 'connected'
                    if is_connected:
                        healthy_interfaces += 1
                    
                    health_info['interfaces'][interface_name] = {
                        'connected': is_connected,
                        'health_score': interface_status.get('metrics', {}).get('health_score', 0),
                        'success_rate': interface_status.get('metrics', {}).get('success_rate', 0),
                        'last_message_time': interface_status.get('connection_status', {}).get('last_message_time'),
                        'error_message': interface_status.get('connection_status', {}).get('error_message')
                    }
                
                # Determine overall status
                if healthy_interfaces == 0:
                    health_info['overall_status'] = 'all_interfaces_down'
                elif healthy_interfaces < total_interfaces:
                    health_info['overall_status'] = 'partial_connectivity'
                else:
                    health_info['overall_status'] = 'healthy'
            
            # Get connection manager status if available
            if hasattr(self.manager, 'connection_manager') and self.manager.connection_manager:
                cm_status = self.manager.connection_manager.get_health_status()
                health_info['connection_manager'] = {
                    'active_interfaces': cm_status.get('active_interfaces', 0),
                    'failed_interfaces': cm_status.get('failed_interfaces', 0),
                    'failover_count': cm_status.get('failover_count', 0),
                    'last_failover': cm_status.get('last_failover'),
                    'primary_interface': cm_status.get('primary_interface')
                }
            
            # Get message router status if available
            if hasattr(self.manager, 'message_router') and self.manager.message_router:
                router_stats = self.manager.message_router.get_delivery_stats()
                health_info['message_router'] = {
                    'success_rate': router_stats.get('success_rate', 0),
                    'total_messages': router_stats.get('total_messages', 0),
                    'active_interfaces': router_stats.get('active_interfaces', 0),
                    'routing_policy': router_stats.get('routing_policy', 'unknown')
                }
            
            # Get channel manager status if available
            if hasattr(self.manager, 'channel_manager') and self.manager.channel_manager:
                health_info['channel_manager'] = {
                    'total_channels': len(self.manager.channel_manager.channels),
                    'default_channel': self.manager.channel_manager.default_channel_name,
                    'encrypted_channels': len([ch for ch in self.manager.channel_manager.channels if ch.is_encrypted])
                }
            
        except Exception as e:
            self.logger.error(f"Error getting connection health: {e}")
            health_info['overall_status'] = 'error'
            health_info['error'] = str(e)
        
        return health_info
    
    def get_message_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive message delivery and processing statistics
        
        Returns:
            Dictionary with message statistics
        """
        stats = {
            'timestamp': datetime.now().isoformat(),
            'performance_metrics': self.performance_metrics.to_dict(),
            'manager_stats': {},
            'router_stats': {},
            'interface_stats': {}
        }
        
        if not self.manager:
            stats['error'] = 'No MeshtasticManager instance provided'
            return stats
        
        try:
            # Get manager statistics
            manager_status = self.manager.get_connection_status()
            if 'statistics' in manager_status:
                manager_stats = manager_status['statistics']
                stats['manager_stats'] = {
                    'messages_sent': manager_stats.get('messages_sent', 0),
                    'messages_failed': manager_stats.get('messages_failed', 0),
                    'serial_messages': manager_stats.get('serial_messages', 0),
                    'mqtt_messages': manager_stats.get('mqtt_messages', 0),
                    'failovers': manager_stats.get('failovers', 0),
                    'uptime_seconds': (datetime.now() - manager_stats.get('start_time', datetime.now())).total_seconds()
                }
            
            # Get message router statistics
            if hasattr(self.manager, 'message_router') and self.manager.message_router:
                router_stats = self.manager.message_router.get_delivery_stats()
                stats['router_stats'] = router_stats
            
            # Get interface-specific statistics
            interfaces = manager_status.get('interfaces', {})
            for interface_name, interface_status in interfaces.items():
                metrics = interface_status.get('metrics', {})
                stats['interface_stats'][interface_name] = {
                    'messages_sent': metrics.get('messages_sent', 0),
                    'messages_failed': metrics.get('messages_failed', 0),
                    'success_rate': metrics.get('success_rate', 0),
                    'average_response_time': metrics.get('average_response_time', 0),
                    'consecutive_failures': metrics.get('consecutive_failures', 0),
                    'health_score': metrics.get('health_score', 0)
                }
        
        except Exception as e:
            self.logger.error(f"Error getting message statistics: {e}")
            stats['error'] = str(e)
        
        return stats
    
    def test_all_interfaces(self) -> Dict[str, bool]:
        """
        Test connectivity of all configured interfaces
        
        Returns:
            Dictionary mapping interface names to test results
        """
        if not self.manager:
            return {'error': 'No MeshtasticManager instance provided'}
        
        results = {}
        
        try:
            # Test basic connectivity
            connectivity_results = self.manager.test_connectivity()
            results.update(connectivity_results)
            
            # Perform more detailed tests
            detailed_results = self._perform_detailed_interface_tests()
            
            # Merge results
            for interface_name, detailed_result in detailed_results.items():
                if interface_name in results:
                    # Combine basic connectivity with detailed test
                    results[interface_name] = results[interface_name] and detailed_result
                else:
                    results[interface_name] = detailed_result
            
            # Cache results
            self._last_full_test_time = datetime.now()
            
        except Exception as e:
            self.logger.error(f"Error testing interfaces: {e}")
            results['error'] = str(e)
        
        return results
    
    def _perform_detailed_interface_tests(self) -> Dict[str, bool]:
        """Perform detailed tests on all interfaces"""
        results = {}
        
        if not self.manager or not hasattr(self.manager, 'interfaces'):
            return results
        
        # Test serial interface if available
        if hasattr(self.manager, 'serial_interface') and self.manager.serial_interface:
            results['serial'] = self._test_serial_interface(self.manager.serial_interface)
        
        # Test MQTT interface if available
        if hasattr(self.manager, 'mqtt_interface') and self.manager.mqtt_interface:
            results['mqtt'] = self._test_mqtt_interface(self.manager.mqtt_interface)
        
        return results
    
    def _test_serial_interface(self, interface) -> bool:
        """Test serial interface functionality"""
        test = DiagnosticTest("serial_interface_test", "Test serial interface connectivity and functionality")
        
        try:
            start_time = time.time()
            
            # Test connection status
            if not interface.is_connected():
                test.mark_failed("Interface not connected")
                return False
            
            # Test device info retrieval
            device_info = interface.get_device_info()
            if not device_info:
                test.mark_failed("Could not retrieve device information")
                return False
            
            # Test connection status retrieval
            connection_status = interface.get_connection_status()
            if connection_status.state != ConnectionState.CONNECTED:
                test.mark_failed(f"Connection state is {connection_status.state.value}, expected connected")
                return False
            
            test.execution_time = time.time() - start_time
            test.mark_passed({
                'device_info': device_info,
                'connection_status': connection_status.to_dict()
            })
            
            self._last_test_results['serial_interface'] = test
            return True
            
        except Exception as e:
            test.mark_failed(f"Serial interface test failed: {str(e)}")
            self._last_test_results['serial_interface'] = test
            return False
    
    def _test_mqtt_interface(self, interface) -> bool:
        """Test MQTT interface functionality"""
        test = DiagnosticTest("mqtt_interface_test", "Test MQTT interface connectivity and functionality")
        
        try:
            start_time = time.time()
            
            # Test connection status
            if not interface.is_connected():
                test.mark_failed("MQTT interface not connected")
                return False
            
            # Test connection status retrieval
            connection_status = interface.get_connection_status()
            if connection_status.state != ConnectionState.CONNECTED:
                test.mark_failed(f"Connection state is {connection_status.state.value}, expected connected")
                return False
            
            test.execution_time = time.time() - start_time
            test.mark_passed({
                'connection_status': connection_status.to_dict()
            })
            
            self._last_test_results['mqtt_interface'] = test
            return True
            
        except Exception as e:
            test.mark_failed(f"MQTT interface test failed: {str(e)}")
            self._last_test_results['mqtt_interface'] = test
            return False
    
    def validate_configuration(self) -> List[str]:
        """
        Validate current configuration and return any issues
        
        Returns:
            List of configuration issues (empty if valid)
        """
        # Check cache first
        if self._last_config_validation:
            cache_time, cached_issues = self._last_config_validation
            if datetime.now() - cache_time < timedelta(minutes=5):
                return cached_issues
        
        issues = []
        
        if not self.manager:
            issues.append("No MeshtasticManager instance provided for validation")
            return issues
        
        try:
            config = self.manager.config
            
            # Validate basic configuration
            issues.extend(self._validate_basic_config(config))
            
            # Validate channel configuration
            issues.extend(self._validate_channel_config(config))
            
            # Validate MQTT configuration if present
            if config.mqtt:
                issues.extend(self._validate_mqtt_config(config.mqtt))
            
            # Validate connection mode compatibility
            issues.extend(self._validate_connection_mode(config))
            
            # Validate message settings
            issues.extend(self._validate_message_settings(config))
            
            # Cache results
            self._last_config_validation = (datetime.now(), issues)
            
        except Exception as e:
            self.logger.error(f"Error during configuration validation: {e}")
            issues.append(f"Configuration validation error: {str(e)}")
        
        return issues
    
    def _validate_basic_config(self, config: MeshtasticConfig) -> List[str]:
        """Validate basic configuration settings"""
        issues = []
        
        # Validate connection mode
        if config.connection_mode not in ["serial", "mqtt", "dual"]:
            issues.append(f"Invalid connection mode: {config.connection_mode}")
        
        # Validate timeouts and intervals
        if config.connection_timeout <= 0:
            issues.append(f"Connection timeout must be positive: {config.connection_timeout}")
        
        if config.retry_interval <= 0:
            issues.append(f"Retry interval must be positive: {config.retry_interval}")
        
        if config.health_check_interval <= 0:
            issues.append(f"Health check interval must be positive: {config.health_check_interval}")
        
        # Validate message settings
        if config.max_message_length < 10:
            issues.append(f"Max message length too small: {config.max_message_length}")
        
        if config.message_format not in ["standard", "compact", "json"]:
            issues.append(f"Invalid message format: {config.message_format}")
        
        return issues
    
    def _validate_channel_config(self, config: MeshtasticConfig) -> List[str]:
        """Validate channel configuration"""
        issues = []
        
        if not config.channels:
            issues.append("No channels configured")
            return issues
        
        # Check for duplicate channel names
        channel_names = [ch.name for ch in config.channels]
        if len(channel_names) != len(set(channel_names)):
            issues.append("Duplicate channel names found")
        
        # Check for duplicate channel numbers
        channel_numbers = [ch.channel_number for ch in config.channels]
        if len(channel_numbers) != len(set(channel_numbers)):
            issues.append("Duplicate channel numbers found")
        
        # Validate each channel
        for i, channel in enumerate(config.channels):
            try:
                # Channel validation is handled by ChannelConfig.__post_init__
                pass
            except ValueError as e:
                issues.append(f"Channel {i} ({channel.name}): {str(e)}")
        
        # Check default channel exists
        default_channel_names = [ch.name for ch in config.channels]
        if config.default_channel not in default_channel_names:
            issues.append(f"Default channel '{config.default_channel}' not found in configured channels")
        
        return issues
    
    def _validate_mqtt_config(self, mqtt_config: MQTTConfig) -> List[str]:
        """Validate MQTT configuration"""
        issues = []
        
        try:
            # MQTT config validation is handled by MQTTConfig.__post_init__
            pass
        except ValueError as e:
            issues.append(f"MQTT configuration error: {str(e)}")
        
        # Additional MQTT-specific validations
        if not mqtt_config.broker_url.strip():
            issues.append("MQTT broker URL cannot be empty")
        
        if mqtt_config.port <= 0 or mqtt_config.port > 65535:
            issues.append(f"Invalid MQTT port: {mqtt_config.port}")
        
        if mqtt_config.keepalive <= 0:
            issues.append(f"MQTT keepalive must be positive: {mqtt_config.keepalive}")
        
        return issues
    
    def _validate_connection_mode(self, config: MeshtasticConfig) -> List[str]:
        """Validate connection mode compatibility"""
        issues = []
        
        if config.connection_mode in ["serial", "dual"]:
            # Validate serial settings
            if not config.meshtastic_port:
                issues.append("Serial port must be specified for serial/dual mode")
            
            if config.meshtastic_baud not in [9600, 19200, 38400, 57600, 115200]:
                issues.append(f"Unusual baud rate: {config.meshtastic_baud}")
        
        if config.connection_mode in ["mqtt", "dual"]:
            # Validate MQTT settings
            if not config.mqtt:
                issues.append("MQTT configuration required for mqtt/dual mode")
        
        return issues
    
    def _validate_message_settings(self, config: MeshtasticConfig) -> List[str]:
        """Validate message-related settings"""
        issues = []
        
        # Check message length vs format
        if config.message_format == "json" and config.max_message_length < 50:
            issues.append("JSON message format requires larger max_message_length (recommended: 200+)")
        
        if config.message_format == "compact" and config.max_message_length > 100:
            issues.append("Compact message format is designed for shorter messages")
        
        return issues
    
    def get_diagnostic_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive diagnostic report
        
        Returns:
            Complete diagnostic report with all available information
        """
        report = {
            'timestamp': datetime.now().isoformat(),
            'connection_health': self.get_connection_health(),
            'message_statistics': self.get_message_statistics(),
            'interface_tests': self.test_all_interfaces(),
            'configuration_validation': self.validate_configuration(),
            'performance_metrics': self.performance_metrics.to_dict(),
            'test_results': {name: test.to_dict() for name, test in self._last_test_results.items()},
            'system_info': self._get_system_info()
        }
        
        # Add recommendations based on findings
        report['recommendations'] = self._generate_recommendations(report)
        
        return report
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information"""
        import platform
        import sys
        
        return {
            'python_version': sys.version,
            'platform': platform.platform(),
            'architecture': platform.architecture(),
            'processor': platform.processor(),
            'hostname': platform.node()
        }
    
    def _generate_recommendations(self, report: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on diagnostic report"""
        recommendations = []
        
        # Check overall health
        overall_status = report.get('connection_health', {}).get('overall_status')
        if overall_status == 'all_interfaces_down':
            recommendations.append("All interfaces are down - check device connections and network settings")
        elif overall_status == 'partial_connectivity':
            recommendations.append("Some interfaces are down - consider enabling failover or checking failed interfaces")
        
        # Check configuration issues
        config_issues = report.get('configuration_validation', [])
        if config_issues:
            recommendations.append(f"Configuration has {len(config_issues)} issues - review and fix configuration errors")
        
        # Check performance metrics
        perf_metrics = report.get('performance_metrics', {})
        error_rate = perf_metrics.get('current_error_rate', 0)
        if error_rate > 10:
            recommendations.append(f"High error rate ({error_rate:.1f}%) - investigate connection stability")
        
        avg_latency = perf_metrics.get('average_latency', 0)
        if avg_latency > 5.0:
            recommendations.append(f"High message latency ({avg_latency:.2f}s) - check network performance")
        
        # Check interface tests
        interface_tests = report.get('interface_tests', {})
        failed_tests = [name for name, result in interface_tests.items() if not result]
        if failed_tests:
            recommendations.append(f"Interface tests failed for: {', '.join(failed_tests)}")
        
        return recommendations
    
    def record_message_latency(self, latency: float) -> None:
        """Record message delivery latency for performance tracking"""
        self.performance_metrics.record_message_latency(latency)
    
    def record_connection_time(self, connection_time: float) -> None:
        """Record interface connection time for performance tracking"""
        self.performance_metrics.record_connection_time(connection_time)
    
    def record_error(self) -> None:
        """Record an error occurrence for performance tracking"""
        self.performance_metrics.record_error()
    
    def reset_metrics(self) -> None:
        """Reset all performance metrics"""
        self.performance_metrics = PerformanceMetrics()
        self._last_test_results.clear()
        self._last_config_validation = None
        self.logger.info("Diagnostics metrics reset")