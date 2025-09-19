"""
pyModeS Integration Module for UrsineExplorer ADS-B Receiver

This module provides integration with the pyModeS library for robust ADS-B message
decoding and processing. It maintains backward compatibility with the existing
UrsineExplorer system while leveraging pyModeS's proven algorithms.
"""

from .config import PyModeSConfig
from .decoder import PyModeSDecode
from .message_source import MessageSourceManager, MessageSource, Dump1090Source, NetworkSource, DummyMessageSource
from .aircraft import EnhancedAircraft
from .validator import MessageValidator, ValidationConfig, MessageType as ValidatorMessageType
from .decoded_message import DecodedMessage, MessageBatch, PositionData, VelocityData, IdentificationData, MessageMetadata, MessageType, DataQuality
from .adsb_logger import ADSBLogger, LogCategory, MessageStats, AircraftStats, ConnectionStats, PerformanceMetrics, get_logger, initialize_logger, shutdown_logger
from .performance_monitor import PerformanceMonitor, ProcessingMetrics, MemoryMetrics, NetworkMetrics, AlertMetrics, SystemMetrics, get_performance_monitor, initialize_performance_monitor, shutdown_performance_monitor

__version__ = "1.0.0"
__all__ = [
    "PyModeSConfig",
    "PyModeSDecode", 
    "MessageSourceManager",
    "MessageSource",
    "Dump1090Source",
    "NetworkSource", 
    "DummyMessageSource",
    "EnhancedAircraft",
    "MessageValidator",
    "ValidationConfig",
    "ValidatorMessageType",
    "DecodedMessage",
    "MessageBatch",
    "PositionData",
    "VelocityData", 
    "IdentificationData",
    "MessageMetadata",
    "MessageType",
    "DataQuality",
    "ADSBLogger",
    "LogCategory",
    "MessageStats",
    "AircraftStats", 
    "ConnectionStats",
    "PerformanceMetrics",
    "get_logger",
    "initialize_logger",
    "shutdown_logger",
    "PerformanceMonitor",
    "ProcessingMetrics",
    "MemoryMetrics",
    "NetworkMetrics",
    "AlertMetrics",
    "SystemMetrics",
    "get_performance_monitor",
    "initialize_performance_monitor",
    "shutdown_performance_monitor"
]