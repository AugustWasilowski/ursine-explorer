#!/usr/bin/env python3
"""
Ursine Capture - Dashboard Startup Script
Simple script to start the terminal dashboard with proper error handling.
"""

import sys
import os
import subprocess
import time
from pathlib import Path

def check_dependencies():
    """Check if required dependencies are available."""
    try:
        import curses
        print("✓ curses available")
    except ImportError:
        print("✗ curses not found. Install python3-curses package.")
        return False
    
    return True

def check_data_files():
    """Check if data files from receiver exist."""
    aircraft_file = Path("aircraft.json")
    status_file = Path("status.json")
    
    if not aircraft_file.exists():
        print("⚠ aircraft.json not found. Dashboard will show empty until receiver starts.")
    else:
        print("✓ aircraft.json found")
    
    if not status_file.exists():
        print("⚠ status.json not found. Status display will be limited until receiver starts.")
    else:
        print("✓ status.json found")
    
    return True

def check_config():
    """Check if configuration file exists."""
    config_path = Path("config.json")
    if not config_path.exists():
        print("✗ config.json not found. Run installer.py first or create manually.")
        return False
    
    print("✓ Configuration file found")
    return True

def start_dashboard():
    """Start the dashboard process."""
    if not check_dependencies():
        return False
    
    if not check_config():
        return False
    
    check_data_files()
    
    print("\nStarting Ursine Capture Dashboard...")
    print("Make sure your terminal is at least 80x24 characters")
    print("Press 'q' in the dashboard to quit")
    print("-" * 50)
    
    # Give user a moment to read the message
    time.sleep(2)
    
    try:
        # Start dashboard.py
        result = subprocess.run([
            sys.executable, "dashboard.py"
        ], check=False)
        
        return result.returncode == 0
        
    except FileNotFoundError:
        print("✗ dashboard.py not found in current directory")
        return False
    except Exception as e:
        print(f"✗ Error starting dashboard: {e}")
        return False

if __name__ == "__main__":
    print("Ursine Capture - Dashboard Startup")
    print("=" * 40)
    
    success = start_dashboard()
    sys.exit(0 if success else 1)