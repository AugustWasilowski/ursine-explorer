"""
pyModeS Integration Module for UrsineExplorer ADS-B Receiver

This module provides integration with the pyModeS library for robust ADS-B message
decoding and processing. It maintains backward compatibility with the existing
UrsineExplorer system while leveraging pyModeS's proven algorithms.
"""

from .config import PyModeSConfig
from .decoder import PyModeSDecode
from .message_source import MessageSourceManager, MessageSource
from .aircraft import EnhancedAircraft

__version__ = "1.0.0"
__all__ = [
    "PyModeSConfig",
    "PyModeSDecode", 
    "MessageSourceManager",
    "MessageSource",
    "EnhancedAircraft"
]