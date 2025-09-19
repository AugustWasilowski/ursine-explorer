#!/usr/bin/env python3
"""
Test script for Ursine Explorer ADS-B system integration
Tests the dump1090 integration, watchlist detection, and Meshtastic alerts
"""

import json
import time
import requests
import socket
import sys
import os
from datetime import datetime

def test_config():
    """Test configuration loading"""
    print("🔧 Testing configuration...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        required_fields = [
            'dump1090_host', 'dump1090_port', 'receiver_control_port',
            'target_icao_codes', 'frequency', 'lna_gain', 'vga_gain',
            'meshtastic_port', 'meshtastic_baud', 'log_alerts'
        ]
        
        missing_fields = [field for field in required_fields if field not in config]
        if missing_fields:
            print(f"❌ Missing config fields: {missing_fields}")
            return False
        
        print("✅ Configuration loaded successfully")
        print(f"   - dump1090: {config['dump1090_host']}:{config['dump1090_port']}")
        print(f"   - Control port: {config['receiver_control_port']}")
        print(f"   - Watchlist: {config['target_icao_codes']}")
        print(f"   - Meshtastic: {config['meshtastic_port']} @ {config['meshtastic_baud']} baud")
        return True
        
    except Exception as e:
        print(f"❌ Config test failed: {e}")
        return False

def test_receiver_connection():
    """Test connection to ADS-B receiver"""
    print("\n📡 Testing receiver connection...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        # Test control port
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((config['dump1090_host'], config['receiver_control_port']))
        
        # Send ping
        sock.send(b"PING\n")
        response = sock.recv(1024).decode().strip()
        sock.close()
        
        if response == "OK":
            print("✅ Receiver control connection successful")
            return True
        else:
            print(f"❌ Unexpected response: {response}")
            return False
            
    except ConnectionRefusedError:
        print("❌ Connection refused - is the receiver running?")
        return False
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def test_aircraft_data():
    """Test aircraft data API"""
    print("\n✈️ Testing aircraft data API...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        url = f"http://{config['dump1090_host']}:{config['dump1090_port']}/data/aircraft.json"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        
        data = response.json()
        
        print("✅ Aircraft data API accessible")
        print(f"   - Messages: {data.get('messages', 0)}")
        print(f"   - Aircraft count: {len(data.get('aircraft', []))}")
        
        # Check for watchlist aircraft
        watchlist_aircraft = []
        for aircraft in data.get('aircraft', []):
            if aircraft.get('is_watchlist', False):
                watchlist_aircraft.append(aircraft.get('hex', 'Unknown'))
        
        if watchlist_aircraft:
            print(f"   - Watchlist aircraft detected: {watchlist_aircraft}")
        else:
            print("   - No watchlist aircraft currently visible")
        
        return True
        
    except requests.RequestException as e:
        print(f"❌ Aircraft data API test failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Aircraft data test failed: {e}")
        return False

def test_receiver_status():
    """Test receiver status API"""
    print("\n📊 Testing receiver status...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((config['dump1090_host'], config['receiver_control_port']))
        
        sock.send(b"GET_STATUS\n")
        response = sock.recv(4096).decode().strip()
        sock.close()
        
        status = json.loads(response)
        
        print("✅ Receiver status retrieved")
        print(f"   - dump1090 running: {status.get('dump1090_running', False)}")
        print(f"   - Meshtastic connected: {status.get('meshtastic_connected', False)}")
        print(f"   - Aircraft count: {status.get('aircraft_count', 0)}")
        print(f"   - Watchlist count: {status.get('watchlist_count', 0)}")
        
        if 'stats' in status:
            stats = status['stats']
            print(f"   - Total aircraft seen: {stats.get('total_aircraft', 0)}")
            print(f"   - Watchlist alerts sent: {stats.get('watchlist_alerts', 0)}")
            print(f"   - dump1090 restarts: {stats.get('dump1090_restarts', 0)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Receiver status test failed: {e}")
        return False

def test_meshtastic_connection():
    """Test Meshtastic serial connection"""
    print("\n📻 Testing Meshtastic connection...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        meshtastic_port = config.get('meshtastic_port')
        if not meshtastic_port:
            print("⚠️ No Meshtastic port configured - skipping test")
            return True
        
        # Check if port exists
        if not os.path.exists(meshtastic_port):
            print(f"⚠️ Meshtastic port {meshtastic_port} not found - device may not be connected")
            return True
        
        # Try to open serial connection
        import serial
        try:
            ser = serial.Serial(
                port=meshtastic_port,
                baudrate=config.get('meshtastic_baud', 115200),
                timeout=1
            )
            ser.close()
            print("✅ Meshtastic port accessible")
            return True
        except serial.SerialException as e:
            print(f"⚠️ Meshtastic port access failed: {e}")
            return True  # Not a critical failure
        
    except ImportError:
        print("⚠️ pyserial not available - cannot test Meshtastic connection")
        return True
    except Exception as e:
        print(f"❌ Meshtastic test failed: {e}")
        return False

def test_alert_logging():
    """Test alert logging functionality"""
    print("\n📝 Testing alert logging...")
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        log_file = config.get('alert_log_file', 'alerts.log')
        
        # Test writing to log file
        test_message = f"TEST ALERT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        with open(log_file, 'a') as f:
            f.write(f"{test_message}\n")
        
        # Verify log file exists and is writable
        if os.path.exists(log_file):
            print(f"✅ Alert logging functional - log file: {log_file}")
            return True
        else:
            print("❌ Alert log file not created")
            return False
            
    except Exception as e:
        print(f"❌ Alert logging test failed: {e}")
        return False

def main():
    """Run all integration tests"""
    print("🛩️ Ursine Explorer Integration Test Suite")
    print("=" * 50)
    
    tests = [
        ("Configuration", test_config),
        ("Receiver Connection", test_receiver_connection),
        ("Aircraft Data API", test_aircraft_data),
        ("Receiver Status", test_receiver_status),
        ("Meshtastic Connection", test_meshtastic_connection),
        ("Alert Logging", test_alert_logging)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed! System is ready.")
        return 0
    else:
        print("⚠️ Some tests failed. Check the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
