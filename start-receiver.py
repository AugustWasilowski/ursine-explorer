#!/usr/bin/env python3
"""
Ursine Capture - Receiver Startup Script
Simple script to start the ADS-B receiver process with proper error handling.
"""

import sys
import os
import subprocess
import time
import signal
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are available."""
    try:
        import pymodes
        print("✓ pyModeS available")
    except ImportError:
        print("✗ pyModeS not found. Run installer.py first.")
        return False
    
    # Check if dump1090 is available
    dump1090_paths = [
        "/usr/bin/dump1090-fa",
        "/usr/local/bin/dump1090-fa",
        "/opt/dump1090-fa/dump1090-fa"
    ]
    
    dump1090_found = False
    for path in dump1090_paths:
        if os.path.exists(path):
            print(f"✓ dump1090-fa found at {path}")
            dump1090_found = True
            break
    
    if not dump1090_found:
        print("✗ dump1090-fa not found. Run installer.py first.")
        return False
    
    return True

def check_config():
    """Check if configuration file exists."""
    config_path = Path("config.json")
    if not config_path.exists():
        print("✗ config.json not found. Run installer.py first or create manually.")
        return False
    
    print("✓ Configuration file found")
    return True

def start_receiver():
    """Start the receiver process."""
    if not check_dependencies():
        return False
    
    if not check_config():
        return False
    
    print("\nStarting Ursine Capture Receiver...")
    print("Press Ctrl+C to stop")
    print("-" * 50)
    
    try:
        # Start receiver.py
        process = subprocess.Popen([
            sys.executable, "receiver.py"
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            print("\nShutting down receiver...")
            process.terminate()
            process.wait()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Monitor process output
        for line in process.stdout:
            print(line.strip())
        
        return_code = process.wait()
        if return_code != 0:
            print(f"Receiver exited with code {return_code}")
            return False
        
    except FileNotFoundError:
        print("✗ receiver.py not found in current directory")
        return False
    except Exception as e:
        print(f"✗ Error starting receiver: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("Ursine Capture - Receiver Startup")
    print("=" * 40)
    
    success = start_receiver()
    sys.exit(0 if success else 1)