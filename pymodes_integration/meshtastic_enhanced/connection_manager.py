"""
Connection Manager for enhanced Meshtastic integration

This module implements the ConnectionManager class that handles interface
registration, health monitoring, failover logic, and comprehensive status reporting
for all Meshtastic interfaces.
"""

import logging
import threading
import time
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum

from .interfaces import MeshtasticInterface
from .data_classes import (
    ConnectionStatus, ConnectionState, AlertMessage, 
    MessagePriority, RoutingPolicy
)
from .exceptions import MeshtasticError, ConnectionError


logger = logging.getLogger(__name__)


class InterfacePriority(Enum):
    """Interface priority levels for load balancing and failover"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


class InterfaceMetrics:
    """Tracks performance and health metrics for an interface"""
    
    def __init__(self, interface: MeshtasticInterface):
        self.interface = interface
        self.interface_type = interface.get_interface_type()
        self.priority = InterfacePriority.MEDIUM
        
        # Connection metrics
        self.connection_attempts = 0
        self.successful_connections = 0
        self.connection_failures = 0
        self.last_connection_attempt: Optional[datetime] = None
        self.last_successful_connection: Optional[datetime] = None
        self.total_uptime = timedelta()
        self.current_session_start: Optional[datetime] = None
        
        # Message metrics
        self.messages_sent = 0
        self.messages_failed = 0
        self.consecutive_failures = 0
        self.last_message_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        
        # Performance metrics
        self.response_times: deque = deque(maxlen=100)
        self.average_response_time = 0.0
        self.min_response_time = float('inf')
        self.max_response_time = 0.0
        
        # Health status
        self.is_healthy = True
        self.health_score = 100.0  # 0-100 scale
        self.health_check_failures = 0
        self.last_health_check: Optional[datetime] = None
        self.error_history: deque = deque(maxlen=50)
        
        # Load balancing
        self.current_load = 0
        self.max_load = 100
        self.load_history: deque = deque(maxlen=60)  # Last 60 measurements
        
    def record_connection_attempt(self) -> None:
        """Record a connection attempt"""
        self.connection_attempts += 1
        self.last_connection_attempt = datetime.now()
    
    def record_successful_connection(self) -> None:
        """Record a successful connection"""
        self.successful_connections += 1
        self.last_successful_connection = datetime.now()
        self.current_session_start = datetime.now()
        self.consecutive_failures = 0
        self.health_check_failures = 0
        self._update_health_score()
    
    def record_connection_failure(self, error: str) -> None:
        """Record a connection failure"""
        self.connection_failures += 1
        self.consecutive_failures += 1
        self.error_history.append({
            'timestamp': datetime.now(),
            'type': 'connection',
            'error': error
        })
        self._update_health_score()
    
    def record_message_success(self, response_time: float = 0.0) -> None:
        """Record a successful message delivery"""
        self.messages_sent += 1
        self.last_message_time = datetime.now()
        self.consecutive_failures = 0
        
        if response_time > 0:
            self.response_times.append(response_time)
            self._update_response_time_stats()
        
        self._update_health_score()
    
    def record_message_failure(self, error: str) -> None:
        """Record a message delivery failure"""
        self.messages_failed += 1
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now()
        
        self.error_history.append({
            'timestamp': datetime.now(),
            'type': 'message',
            'error': error
        })
        
        self._update_health_score()
    
    def record_health_check(self, success: bool, error: str = None) -> None:
        """Record a health check result"""
        self.last_health_check = datetime.now()
        
        if success:
            self.health_check_failures = 0
        else:
            self.health_check_failures += 1
            if error:
                self.error_history.append({
                    'timestamp': datetime.now(),
                    'type': 'health_check',
                    'error': error
                })
        
        self._update_health_score()
    
    def update_session_uptime(self) -> None:
        """Update total uptime if currently connected"""
        if self.current_session_start and self.interface.is_connected():
            session_duration = datetime.now() - self.current_session_start
            self.total_uptime += session_duration
            self.current_session_start = datetime.now()
    
    def update_load(self, current_load: int) -> None:
        """Update current load metrics"""
        self.current_load = max(0, min(100, current_load))
        self.load_history.append({
            'timestamp': datetime.now(),
            'load': self.current_load
        })
    
    def _update_response_time_stats(self) -> None:
        """Update response time statistics"""
        if not self.response_times:
            return
        
        times = list(self.response_times)
        self.average_response_time = sum(times) / len(times)
        self.min_response_time = min(self.min_response_time, min(times))
        self.max_response_time = max(self.max_response_time, max(times))
    
    def _update_health_score(self) -> None:
        """Calculate and update health score based on various metrics"""
        score = 100.0
        
        # Connection success rate (40% weight)
        if self.connection_attempts > 0:
            connection_rate = self.successful_connections / self.connection_attempts
            score *= 0.6 + (0.4 * connection_rate)
        
        # Message success rate (30% weight)
        total_messages = self.messages_sent + self.messages_failed
        if total_messages > 0:
            message_rate = self.messages_sent / total_messages
            score *= 0.7 + (0.3 * message_rate)
        
        # Consecutive failures penalty (20% weight)
        if self.consecutive_failures > 0:
            failure_penalty = min(0.8, self.consecutive_failures * 0.1)
            score *= (1.0 - failure_penalty)
        
        # Health check failures penalty (10% weight)
        if self.health_check_failures > 0:
            health_penalty = min(0.5, self.health_check_failures * 0.1)
            score *= (1.0 - health_penalty)
        
        self.health_score = max(0.0, min(100.0, score))
        self.is_healthy = self.health_score >= 50.0
    
    @property
    def success_rate(self) -> float:
        """Calculate overall success rate"""
        total_attempts = self.messages_sent + self.messages_failed
        if total_attempts == 0:
            return 1.0
        return self.messages_sent / total_attempts
    
    @property
    def availability(self) -> float:
        """Calculate availability percentage"""
        if self.connection_attempts == 0:
            return 0.0
        return self.successful_connections / self.connection_attempts
    
    @property
    def current_session_duration(self) -> Optional[timedelta]:
        """Get current session duration if connected"""
        if self.current_session_start and self.interface.is_connected():
            return datetime.now() - self.current_session_start
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization"""
        return {
            'interface_type': self.interface_type,
            'priority': self.priority.name,
            'connection_attempts': self.connection_attempts,
            'successful_connections': self.successful_connections,
            'connection_failures': self.connection_failures,
            'messages_sent': self.messages_sent,
            'messages_failed': self.messages_failed,
            'consecutive_failures': self.consecutive_failures,
            'success_rate': self.success_rate,
            'availability': self.availability,
            'health_score': self.health_score,
            'is_healthy': self.is_healthy,
            'average_response_time': self.average_response_time,
            'min_response_time': self.min_response_time if self.min_response_time != float('inf') else None,
            'max_response_time': self.max_response_time,
            'current_load': self.current_load,
            'total_uptime_seconds': self.total_uptime.total_seconds(),
            'current_session_duration': self.current_session_duration.total_seconds() if self.current_session_duration else None,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None,
            'last_health_check': self.last_health_check.isoformat() if self.last_health_check else None,
            'recent_errors': list(self.error_history)[-5:]  # Last 5 errors
        }


class ConnectionManager:
    """
    Manages the lifecycle of Meshtastic interfaces with health monitoring,
    failover logic, priority management, and comprehensive status reporting.
    """
    
    def __init__(self, failover_enabled: bool = True, health_check_interval: int = 60):
        """
        Initialize ConnectionManager
        
        Args:
            failover_enabled: Whether automatic failover is enabled
            health_check_interval: Health check interval in seconds
        """
        self.failover_enabled = failover_enabled
        self.health_check_interval = health_check_interval
        self.logger = logging.getLogger(__name__)
        
        # Interface management
        self._interfaces: Dict[str, MeshtasticInterface] = {}
        self._metrics: Dict[str, InterfaceMetrics] = {}
        self._interface_priorities: Dict[str, InterfacePriority] = {}
        
        # State management
        self._primary_interface: Optional[str] = None
        self._active_interfaces: Set[str] = set()
        self._failed_interfaces: Set[str] = set()
        self._lock = threading.RLock()
        
        # Health monitoring
        self._health_monitor_thread: Optional[threading.Thread] = None
        self._shutdown_requested = False
        self._last_failover_time: Optional[datetime] = None
        self._failover_count = 0
        
        # Load balancing
        self._load_balancer_enabled = False
        self._round_robin_index = 0
        
        self.logger.info("ConnectionManager initialized")
    
    def add_interface(self, interface: MeshtasticInterface, 
                     priority: InterfacePriority = InterfacePriority.MEDIUM,
                     is_primary: bool = False) -> None:
        """
        Add an interface to the connection manager
        
        Args:
            interface: MeshtasticInterface to add
            priority: Priority level for this interface
            is_primary: Whether this should be the primary interface
        """
        with self._lock:
            interface_id = f"{interface.get_interface_type()}_{id(interface)}"
            
            self._interfaces[interface_id] = interface
            self._metrics[interface_id] = InterfaceMetrics(interface)
            self._metrics[interface_id].priority = priority
            self._interface_priorities[interface_id] = priority
            
            # Set as primary if requested or if it's the first interface
            if is_primary or not self._primary_interface:
                self._primary_interface = interface_id
            
            # Add to active interfaces if connected
            if interface.is_connected():
                self._active_interfaces.add(interface_id)
                self._metrics[interface_id].record_successful_connection()
            
            self.logger.info(f"Added interface: {interface_id} (priority: {priority.name})")
    
    def remove_interface(self, interface: MeshtasticInterface) -> None:
        """
        Remove an interface from the connection manager
        
        Args:
            interface: MeshtasticInterface to remove
        """
        with self._lock:
            interface_id = None
            for iid, iface in self._interfaces.items():
                if iface is interface:
                    interface_id = iid
                    break
            
            if not interface_id:
                self.logger.warning("Interface not found for removal")
                return
            
            # Clean up interface
            self._interfaces.pop(interface_id, None)
            self._metrics.pop(interface_id, None)
            self._interface_priorities.pop(interface_id, None)
            self._active_interfaces.discard(interface_id)
            self._failed_interfaces.discard(interface_id)
            
            # Update primary interface if needed
            if self._primary_interface == interface_id:
                self._primary_interface = self._select_new_primary()
            
            self.logger.info(f"Removed interface: {interface_id}")
    
    def get_active_interfaces(self) -> List[MeshtasticInterface]:
        """
        Get list of currently active (connected) interfaces
        
        Returns:
            List of active MeshtasticInterface objects
        """
        with self._lock:
            return [self._interfaces[iid] for iid in self._active_interfaces 
                   if iid in self._interfaces]
    
    def get_primary_interface(self) -> Optional[MeshtasticInterface]:
        """
        Get the primary interface
        
        Returns:
            Primary MeshtasticInterface or None if not available
        """
        with self._lock:
            if self._primary_interface and self._primary_interface in self._interfaces:
                return self._interfaces[self._primary_interface]
            return None
    
    def get_best_interface(self, routing_policy: RoutingPolicy = RoutingPolicy.PRIMARY) -> Optional[MeshtasticInterface]:
        """
        Get the best interface based on routing policy and health metrics
        
        Args:
            routing_policy: Routing policy to use for selection
            
        Returns:
            Best MeshtasticInterface or None if none available
        """
        with self._lock:
            if not self._active_interfaces:
                return None
            
            if routing_policy == RoutingPolicy.PRIMARY:
                return self.get_primary_interface()
            
            elif routing_policy == RoutingPolicy.LOAD_BALANCE:
                return self._get_least_loaded_interface()
            
            else:  # Default to best health score
                return self._get_healthiest_interface()
    
    def _get_healthiest_interface(self) -> Optional[MeshtasticInterface]:
        """Get interface with highest health score"""
        best_interface = None
        best_score = -1
        
        for interface_id in self._active_interfaces:
            if interface_id in self._metrics:
                metrics = self._metrics[interface_id]
                if metrics.health_score > best_score:
                    best_score = metrics.health_score
                    best_interface = self._interfaces[interface_id]
        
        return best_interface
    
    def _get_least_loaded_interface(self) -> Optional[MeshtasticInterface]:
        """Get interface with lowest current load"""
        best_interface = None
        lowest_load = float('inf')
        
        for interface_id in self._active_interfaces:
            if interface_id in self._metrics:
                metrics = self._metrics[interface_id]
                if metrics.current_load < lowest_load:
                    lowest_load = metrics.current_load
                    best_interface = self._interfaces[interface_id]
        
        return best_interface
    
    def handle_failover(self) -> bool:
        """
        Handle automatic failover to backup interfaces
        
        Returns:
            True if failover was successful, False otherwise
        """
        if not self.failover_enabled:
            return False
        
        with self._lock:
            self.logger.info("Handling failover...")
            
            # Update interface states
            self._update_interface_states()
            
            # Check if primary interface is still healthy
            primary = self.get_primary_interface()
            if primary and primary.is_connected():
                primary_id = self._get_interface_id(primary)
                if primary_id and self._metrics[primary_id].is_healthy:
                    return True  # Primary is still good
            
            # Find best alternative interface
            new_primary = self._select_new_primary()
            if new_primary and new_primary != self._primary_interface:
                old_primary = self._primary_interface
                self._primary_interface = new_primary
                self._failover_count += 1
                self._last_failover_time = datetime.now()
                
                self.logger.info(f"Failover completed: {old_primary} -> {new_primary}")
                return True
            
            self.logger.warning("Failover failed: no suitable backup interface available")
            return False
    
    def _select_new_primary(self) -> Optional[str]:
        """Select new primary interface based on priority and health"""
        if not self._active_interfaces:
            return None
        
        # Sort by priority (higher first) then by health score
        candidates = []
        for interface_id in self._active_interfaces:
            if interface_id in self._metrics and interface_id in self._interface_priorities:
                metrics = self._metrics[interface_id]
                priority = self._interface_priorities[interface_id]
                candidates.append((interface_id, priority.value, metrics.health_score))
        
        if not candidates:
            return None
        
        # Sort by priority (descending) then health score (descending)
        candidates.sort(key=lambda x: (x[1], x[2]), reverse=True)
        return candidates[0][0]
    
    def _get_interface_id(self, interface: MeshtasticInterface) -> Optional[str]:
        """Get interface ID for a given interface object"""
        for iid, iface in self._interfaces.items():
            if iface is interface:
                return iid
        return None
    
    def update_interface_health(self) -> None:
        """Update health status for all interfaces"""
        with self._lock:
            self._update_interface_states()
            
            for interface_id, interface in self._interfaces.items():
                metrics = self._metrics[interface_id]
                
                try:
                    # Test connection
                    is_connected = interface.is_connected()
                    
                    if is_connected:
                        metrics.record_health_check(True)
                        self._active_interfaces.add(interface_id)
                        self._failed_interfaces.discard(interface_id)
                    else:
                        metrics.record_health_check(False, "Interface not connected")
                        self._active_interfaces.discard(interface_id)
                        self._failed_interfaces.add(interface_id)
                
                except Exception as e:
                    metrics.record_health_check(False, str(e))
                    self._active_interfaces.discard(interface_id)
                    self._failed_interfaces.add(interface_id)
                    self.logger.error(f"Health check failed for {interface_id}: {e}")
    
    def _update_interface_states(self) -> None:
        """Update active/failed interface sets based on current connection status"""
        for interface_id, interface in self._interfaces.items():
            if interface.is_connected():
                if interface_id not in self._active_interfaces:
                    self._active_interfaces.add(interface_id)
                    self._failed_interfaces.discard(interface_id)
                    self.logger.info(f"Interface {interface_id} became active")
            else:
                if interface_id in self._active_interfaces:
                    self._active_interfaces.discard(interface_id)
                    self._failed_interfaces.add(interface_id)
                    self.logger.warning(f"Interface {interface_id} became inactive")
    
    def record_message_result(self, interface: MeshtasticInterface, 
                            success: bool, response_time: float = 0.0, 
                            error: str = None) -> None:
        """
        Record the result of a message transmission
        
        Args:
            interface: Interface that handled the message
            success: Whether the message was successful
            response_time: Response time in seconds
            error: Error message if failed
        """
        interface_id = self._get_interface_id(interface)
        if not interface_id or interface_id not in self._metrics:
            return
        
        metrics = self._metrics[interface_id]
        
        if success:
            metrics.record_message_success(response_time)
        else:
            metrics.record_message_failure(error or "Unknown error")
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        Get comprehensive health status for all interfaces
        
        Returns:
            Dictionary with detailed health information
        """
        with self._lock:
            status = {
                'timestamp': datetime.now().isoformat(),
                'total_interfaces': len(self._interfaces),
                'active_interfaces': len(self._active_interfaces),
                'failed_interfaces': len(self._failed_interfaces),
                'primary_interface': self._primary_interface,
                'failover_enabled': self.failover_enabled,
                'failover_count': self._failover_count,
                'last_failover': self._last_failover_time.isoformat() if self._last_failover_time else None,
                'interfaces': {}
            }
            
            for interface_id, metrics in self._metrics.items():
                interface = self._interfaces[interface_id]
                connection_status = interface.get_connection_status()
                
                status['interfaces'][interface_id] = {
                    'connection_status': connection_status.to_dict(),
                    'metrics': metrics.to_dict(),
                    'is_active': interface_id in self._active_interfaces,
                    'is_primary': interface_id == self._primary_interface,
                    'priority': self._interface_priorities[interface_id].name
                }
            
            return status
    
    def start_health_monitoring(self) -> None:
        """Start background health monitoring"""
        if self._health_monitor_thread and self._health_monitor_thread.is_alive():
            return
        
        self._shutdown_requested = False
        self._health_monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            name="ConnectionManagerHealthMonitor",
            daemon=True
        )
        self._health_monitor_thread.start()
        self.logger.info("Health monitoring started")
    
    def _health_monitor_loop(self) -> None:
        """Background health monitoring loop"""
        while not self._shutdown_requested:
            try:
                self.update_interface_health()
                
                # Trigger failover if needed
                if self.failover_enabled:
                    self.handle_failover()
                
                time.sleep(self.health_check_interval)
                
            except Exception as e:
                self.logger.error(f"Health monitoring error: {e}")
                time.sleep(min(self.health_check_interval, 30))
    
    def stop_health_monitoring(self) -> None:
        """Stop background health monitoring"""
        self._shutdown_requested = True
        if self._health_monitor_thread and self._health_monitor_thread.is_alive():
            self._health_monitor_thread.join(timeout=5)
        self.logger.info("Health monitoring stopped")
    
    def shutdown(self) -> None:
        """Shutdown the connection manager"""
        self.logger.info("Shutting down ConnectionManager...")
        
        self.stop_health_monitoring()
        
        with self._lock:
            # Update uptime for all connected interfaces
            for metrics in self._metrics.values():
                metrics.update_session_uptime()
            
            # Clear all data
            self._interfaces.clear()
            self._metrics.clear()
            self._interface_priorities.clear()
            self._active_interfaces.clear()
            self._failed_interfaces.clear()
            self._primary_interface = None
        
        self.logger.info("ConnectionManager shutdown completed")