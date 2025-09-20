"""
Message routing and delivery system for enhanced Meshtastic integration

This module implements the MessageRouter class that coordinates message
delivery across multiple Meshtastic interfaces with routing policies,
health monitoring, and automatic failover.
"""

import logging
import threading
import time
from typing import Dict, List, Any, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict, deque

from .interfaces import MeshtasticInterface, MessageRouterInterface
from .data_classes import (
    AlertMessage, ConnectionStatus, ConnectionState, 
    RoutingPolicy, MessagePriority
)
from .exceptions import MeshtasticError, ConnectionError, RoutingError


logger = logging.getLogger(__name__)


class InterfaceHealth:
    """Tracks health metrics for a Meshtastic interface"""
    
    def __init__(self, interface: MeshtasticInterface):
        self.interface = interface
        self.success_count = 0
        self.failure_count = 0
        self.last_success_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        self.consecutive_failures = 0
        self.average_response_time = 0.0
        self.response_times: deque = deque(maxlen=100)  # Keep last 100 response times
        self.is_healthy = True
        self.health_check_failures = 0
        self.last_health_check: Optional[datetime] = None
        
    def record_success(self, response_time: float = 0.0) -> None:
        """Record a successful message delivery"""
        self.success_count += 1
        self.last_success_time = datetime.now()
        self.consecutive_failures = 0
        self.health_check_failures = 0
        
        if response_time > 0:
            self.response_times.append(response_time)
            self.average_response_time = sum(self.response_times) / len(self.response_times)
        
        # Mark as healthy if we had consecutive failures
        if not self.is_healthy and self.consecutive_failures == 0:
            self.is_healthy = True
            logger.info(f"Interface {self.interface.get_interface_type()} marked as healthy")
    
    def record_failure(self, error_message: str = "") -> None:
        """Record a failed message delivery"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.consecutive_failures += 1
        
        # Mark as unhealthy after 3 consecutive failures
        if self.consecutive_failures >= 3 and self.is_healthy:
            self.is_healthy = False
            logger.warning(f"Interface {self.interface.get_interface_type()} marked as unhealthy after {self.consecutive_failures} failures")
    
    def record_health_check(self, success: bool) -> None:
        """Record health check result"""
        self.last_health_check = datetime.now()
        if success:
            self.health_check_failures = 0
            if not self.is_healthy:
                self.is_healthy = True
                logger.info(f"Interface {self.interface.get_interface_type()} health check passed - marked as healthy")
        else:
            self.health_check_failures += 1
            if self.health_check_failures >= 3 and self.is_healthy:
                self.is_healthy = False
                logger.warning(f"Interface {self.interface.get_interface_type()} health check failed {self.health_check_failures} times - marked as unhealthy")
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage"""
        total = self.success_count + self.failure_count
        if total == 0:
            return 100.0
        return (self.success_count / total) * 100.0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get health statistics"""
        return {
            'interface_type': self.interface.get_interface_type(),
            'is_healthy': self.is_healthy,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'success_rate': self.success_rate,
            'consecutive_failures': self.consecutive_failures,
            'average_response_time': self.average_response_time,
            'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
            'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'health_check_failures': self.health_check_failures
        }


class MessageRouter(MessageRouterInterface):
    """
    Routes messages across multiple Meshtastic interfaces with health monitoring
    and automatic failover capabilities.
    """
    
    def __init__(self, health_check_interval: int = 60):
        """
        Initialize the message router
        
        Args:
            health_check_interval: Interval in seconds between health checks
        """
        self.interfaces: List[MeshtasticInterface] = []
        self.interface_health: Dict[str, InterfaceHealth] = {}
        self.routing_policy = RoutingPolicy.ALL
        self.primary_interface: Optional[MeshtasticInterface] = None
        self.health_check_interval = health_check_interval
        self.delivery_stats = {
            'total_messages': 0,
            'successful_deliveries': 0,
            'failed_deliveries': 0,
            'retry_attempts': 0,
            'interface_stats': defaultdict(lambda: {'sent': 0, 'success': 0, 'failed': 0})
        }
        
        # Threading for health monitoring
        self._health_check_thread: Optional[threading.Thread] = None
        self._health_check_stop_event = threading.Event()
        self._lock = threading.RLock()
        
        # Message tracking
        self.pending_confirmations: Dict[str, Set[str]] = {}  # message_id -> set of interface_types
        self.message_history: deque = deque(maxlen=1000)  # Keep last 1000 messages
        
        logger.info("MessageRouter initialized")
    
    def add_interface(self, interface: MeshtasticInterface) -> None:
        """
        Add an interface to the router
        
        Args:
            interface: MeshtasticInterface to add
        """
        with self._lock:
            if interface not in self.interfaces:
                self.interfaces.append(interface)
                interface_type = interface.get_interface_type()
                self.interface_health[interface_type] = InterfaceHealth(interface)
                
                # Set first interface as primary if none set
                if self.primary_interface is None:
                    self.primary_interface = interface
                    logger.info(f"Set {interface_type} as primary interface")
                
                logger.info(f"Added {interface_type} interface to router")
                
                # Start health monitoring if this is the first interface
                if len(self.interfaces) == 1:
                    self._start_health_monitoring()
    
    def remove_interface(self, interface: MeshtasticInterface) -> None:
        """
        Remove an interface from the router
        
        Args:
            interface: MeshtasticInterface to remove
        """
        with self._lock:
            if interface in self.interfaces:
                self.interfaces.remove(interface)
                interface_type = interface.get_interface_type()
                
                if interface_type in self.interface_health:
                    del self.interface_health[interface_type]
                
                # Update primary interface if removed
                if self.primary_interface == interface:
                    self.primary_interface = self.interfaces[0] if self.interfaces else None
                    if self.primary_interface:
                        logger.info(f"Updated primary interface to {self.primary_interface.get_interface_type()}")
                
                logger.info(f"Removed {interface_type} interface from router")
                
                # Stop health monitoring if no interfaces left
                if not self.interfaces:
                    self._stop_health_monitoring()
    
    def set_routing_policy(self, policy: RoutingPolicy) -> None:
        """
        Set the message routing policy
        
        Args:
            policy: RoutingPolicy to use
        """
        self.routing_policy = policy
        logger.info(f"Routing policy set to {policy.value}")
    
    def set_primary_interface(self, interface: MeshtasticInterface) -> None:
        """
        Set the primary interface for routing policies that use it
        
        Args:
            interface: Interface to set as primary
        """
        if interface in self.interfaces:
            self.primary_interface = interface
            logger.info(f"Primary interface set to {interface.get_interface_type()}")
        else:
            raise ValueError("Interface must be added to router before setting as primary")
    
    def route_message(self, message: AlertMessage, routing_policy: str = None) -> List[bool]:
        """
        Route a message through available interfaces based on routing policy
        
        Args:
            message: AlertMessage to route
            routing_policy: Override routing policy for this message
            
        Returns:
            List of success status for each interface attempted
        """
        if not self.interfaces:
            logger.error("No interfaces available for message routing")
            return []
        
        # Use provided policy or default
        policy = RoutingPolicy(routing_policy) if routing_policy else self.routing_policy
        
        # Get target interfaces based on policy
        target_interfaces = self._get_target_interfaces(policy, message)
        
        if not target_interfaces:
            logger.error(f"No healthy interfaces available for routing policy {policy.value}")
            return []
        
        # Track message
        message_id = f"{message.timestamp.isoformat()}_{hash(message.content)}"
        self.delivery_stats['total_messages'] += 1
        
        results = []
        successful_deliveries = 0
        
        for interface in target_interfaces:
            interface_type = interface.get_interface_type()
            health = self.interface_health[interface_type]
            
            try:
                start_time = time.time()
                
                # Attempt message delivery
                success = interface.send_message(message.content, message.channel)
                
                response_time = time.time() - start_time
                
                # Update statistics
                self.delivery_stats['interface_stats'][interface_type]['sent'] += 1
                
                if success:
                    health.record_success(response_time)
                    self.delivery_stats['interface_stats'][interface_type]['success'] += 1
                    successful_deliveries += 1
                    results.append(True)
                    logger.debug(f"Message delivered successfully via {interface_type}")
                else:
                    health.record_failure("Send message returned False")
                    self.delivery_stats['interface_stats'][interface_type]['failed'] += 1
                    results.append(False)
                    logger.warning(f"Message delivery failed via {interface_type}")
                    
            except Exception as e:
                health.record_failure(str(e))
                self.delivery_stats['interface_stats'][interface_type]['failed'] += 1
                results.append(False)
                logger.error(f"Exception during message delivery via {interface_type}: {e}")
        
        # Update overall statistics
        if successful_deliveries > 0:
            self.delivery_stats['successful_deliveries'] += 1
        else:
            self.delivery_stats['failed_deliveries'] += 1
        
        # Store message in history
        self.message_history.append({
            'message_id': message_id,
            'timestamp': message.timestamp,
            'content': message.content[:50] + "..." if len(message.content) > 50 else message.content,
            'channel': message.channel,
            'priority': message.priority.value,
            'target_interfaces': [i.get_interface_type() for i in target_interfaces],
            'results': results,
            'successful_deliveries': successful_deliveries
        })
        
        return results
    
    def _get_target_interfaces(self, policy: RoutingPolicy, message: AlertMessage) -> List[MeshtasticInterface]:
        """
        Get target interfaces based on routing policy
        
        Args:
            policy: Routing policy to apply
            message: Message being routed (for priority-based decisions)
            
        Returns:
            List of interfaces to target
        """
        healthy_interfaces = [
            interface for interface in self.interfaces
            if self.interface_health[interface.get_interface_type()].is_healthy
            and interface.is_connected()
        ]
        
        if not healthy_interfaces:
            # If no healthy interfaces, try all interfaces for critical messages
            if message.priority == MessagePriority.CRITICAL:
                logger.warning("No healthy interfaces available, attempting all interfaces for critical message")
                return self.interfaces
            else:
                return []
        
        if policy == RoutingPolicy.ALL:
            return healthy_interfaces
        
        elif policy == RoutingPolicy.PRIMARY:
            if self.primary_interface and self.primary_interface in healthy_interfaces:
                return [self.primary_interface]
            elif healthy_interfaces:
                # Fallback to first healthy interface
                return [healthy_interfaces[0]]
            else:
                return []
        
        elif policy == RoutingPolicy.FALLBACK:
            if self.primary_interface and self.primary_interface in healthy_interfaces:
                return [self.primary_interface]
            else:
                # Use all other healthy interfaces as fallback
                fallback_interfaces = [i for i in healthy_interfaces if i != self.primary_interface]
                return fallback_interfaces if fallback_interfaces else healthy_interfaces
        
        elif policy == RoutingPolicy.LOAD_BALANCE:
            # Simple round-robin load balancing
            if healthy_interfaces:
                # Use message hash to determine interface
                interface_index = hash(message.content) % len(healthy_interfaces)
                return [healthy_interfaces[interface_index]]
            else:
                return []
        
        else:
            logger.error(f"Unknown routing policy: {policy}")
            return healthy_interfaces
    
    def _start_health_monitoring(self) -> None:
        """Start the health monitoring thread"""
        if self._health_check_thread is None or not self._health_check_thread.is_alive():
            self._health_check_stop_event.clear()
            self._health_check_thread = threading.Thread(
                target=self._health_check_loop,
                name="MeshtasticHealthMonitor",
                daemon=True
            )
            self._health_check_thread.start()
            logger.info("Health monitoring started")
    
    def _stop_health_monitoring(self) -> None:
        """Stop the health monitoring thread"""
        if self._health_check_thread and self._health_check_thread.is_alive():
            self._health_check_stop_event.set()
            self._health_check_thread.join(timeout=5)
            logger.info("Health monitoring stopped")
    
    def _health_check_loop(self) -> None:
        """Main health monitoring loop"""
        while not self._health_check_stop_event.is_set():
            try:
                self._perform_health_checks()
            except Exception as e:
                logger.error(f"Error during health check: {e}")
            
            # Wait for next check or stop event
            self._health_check_stop_event.wait(self.health_check_interval)
    
    def _perform_health_checks(self) -> None:
        """Perform health checks on all interfaces"""
        with self._lock:
            for interface in self.interfaces:
                interface_type = interface.get_interface_type()
                health = self.interface_health[interface_type]
                
                try:
                    # Check connection status
                    is_connected = interface.is_connected()
                    connection_status = interface.get_connection_status()
                    
                    # Consider interface healthy if connected and no recent errors
                    is_healthy = (
                        is_connected and 
                        connection_status.state == ConnectionState.CONNECTED and
                        connection_status.error_message is None
                    )
                    
                    health.record_health_check(is_healthy)
                    
                    logger.debug(f"Health check for {interface_type}: {'healthy' if is_healthy else 'unhealthy'}")
                    
                except Exception as e:
                    health.record_health_check(False)
                    logger.warning(f"Health check failed for {interface_type}: {e}")
    
    def get_delivery_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive delivery statistics
        
        Returns:
            Dictionary with delivery statistics
        """
        with self._lock:
            # Calculate overall success rate
            total_attempts = self.delivery_stats['successful_deliveries'] + self.delivery_stats['failed_deliveries']
            success_rate = (self.delivery_stats['successful_deliveries'] / total_attempts * 100) if total_attempts > 0 else 0
            
            # Get interface health stats
            interface_health_stats = {}
            for interface_type, health in self.interface_health.items():
                interface_health_stats[interface_type] = health.get_stats()
            
            return {
                'total_messages': self.delivery_stats['total_messages'],
                'successful_deliveries': self.delivery_stats['successful_deliveries'],
                'failed_deliveries': self.delivery_stats['failed_deliveries'],
                'success_rate': success_rate,
                'retry_attempts': self.delivery_stats['retry_attempts'],
                'interface_stats': dict(self.delivery_stats['interface_stats']),
                'interface_health': interface_health_stats,
                'active_interfaces': len([i for i in self.interfaces if i.is_connected()]),
                'total_interfaces': len(self.interfaces),
                'routing_policy': self.routing_policy.value,
                'primary_interface': self.primary_interface.get_interface_type() if self.primary_interface else None
            }
    
    def get_message_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent message history
        
        Args:
            limit: Maximum number of messages to return
            
        Returns:
            List of message history entries
        """
        with self._lock:
            return list(self.message_history)[-limit:]
    
    def get_healthy_interfaces(self) -> List[MeshtasticInterface]:
        """
        Get list of currently healthy interfaces
        
        Returns:
            List of healthy interfaces
        """
        with self._lock:
            return [
                interface for interface in self.interfaces
                if self.interface_health[interface.get_interface_type()].is_healthy
                and interface.is_connected()
            ]
    
    def force_health_check(self) -> None:
        """Force an immediate health check of all interfaces"""
        self._perform_health_checks()
    
    def reset_statistics(self) -> None:
        """Reset all delivery statistics"""
        with self._lock:
            self.delivery_stats = {
                'total_messages': 0,
                'successful_deliveries': 0,
                'failed_deliveries': 0,
                'retry_attempts': 0,
                'interface_stats': defaultdict(lambda: {'sent': 0, 'success': 0, 'failed': 0})
            }
            
            # Reset interface health stats
            for health in self.interface_health.values():
                health.success_count = 0
                health.failure_count = 0
                health.consecutive_failures = 0
                health.response_times.clear()
                health.average_response_time = 0.0
            
            self.message_history.clear()
            logger.info("Message router statistics reset")
    
    def shutdown(self) -> None:
        """Shutdown the message router and cleanup resources"""
        logger.info("Shutting down message router")
        self._stop_health_monitoring()
        
        with self._lock:
            self.interfaces.clear()
            self.interface_health.clear()
            self.primary_interface = None
        
        logger.info("Message router shutdown complete")