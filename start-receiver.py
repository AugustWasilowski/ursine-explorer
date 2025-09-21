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
    # Check if we're in a virtual environment
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    
    try:
        import pyModeS
        print("✓ pyModeS available")
    except ImportError:
        print("✗ pyModeS not found.")
        if not in_venv and os.path.exists("venv"):
            print("  Try: source venv/bin/activate && python3 start-receiver.py")
        else:
            print("  Run ./install.sh first.")
        return False
    
    # Check if dump1090 is available (check multiple variants)
    dump1090_paths = [
        "/usr/bin/dump1090-fa",
        "/usr/local/bin/dump1090-fa", 
        "/opt/dump1090-fa/dump1090-fa",
        "/usr/local/bin/dump1090",
        "/usr/bin/dump1090",
        "/usr/bin/dump1090-mutability"
    ]
    
    dump1090_found = False
    found_path = None
    for path in dump1090_paths:
        if os.path.exists(path):
            print(f"✓ dump1090 found at {path}")
            dump1090_found = True
            found_path = path
            break
    
    if not dump1090_found:
        print("✗ dump1090 not found. Run ./install.sh first.")
        print("  Checked paths:")
        for path in dump1090_paths:
            print(f"    {path}")
        return False
    
    return True

def check_config():
    """Check if configuration file exists and dump1090 path is valid."""
    config_path = Path("config.json")
    if not config_path.exists():
        print("✗ config.json not found. Run ./install.sh first.")
        return False
    
    print("✓ Configuration file found")
    
    # Check if the configured dump1090 path exists
    try:
        import json
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        dump1090_path = config.get("dump1090_path")
        if dump1090_path and os.path.exists(dump1090_path):
            print(f"✓ Configured dump1090 path exists: {dump1090_path}")
        elif dump1090_path:
            print(f"⚠ Configured dump1090 path not found: {dump1090_path}")
            print("  The receiver may still work if dump1090 is in PATH")
        
    except Exception as e:
        print(f"⚠ Could not validate dump1090 path in config: {e}")
    
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
    
    # Show environment info
    in_venv = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)
    print(f"Python: {sys.executable}")
    print(f"Virtual Environment: {'Yes' if in_venv else 'No'}")
    print(f"Working Directory: {os.getcwd()}")
    print()
    
    success = start_receiver()
    sys.exit(0 if success else 1)