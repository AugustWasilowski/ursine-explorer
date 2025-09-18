#!/usr/bin/env python3
"""
Simple test script to verify receiver connection
"""

import socket
import sys

def test_receiver_connection(host='localhost', port=8081):
    """Test connection to ADS-B receiver control port"""
    try:
        print(f"Testing connection to {host}:{port}...")
        
        # Test PING command
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        print("✅ Connected successfully")
        
        # Send PING
        sock.send(b"PING\n")
        response = sock.recv(1024).decode().strip()
        print(f"📡 PING response: {response}")
        
        sock.close()
        
        if response == "OK":
            print("✅ Receiver is responding correctly")
            return True
        else:
            print(f"❌ Unexpected response: {response}")
            return False
            
    except ConnectionRefusedError:
        print("❌ Connection refused - is the receiver running?")
        return False
    except socket.timeout:
        print("❌ Connection timeout")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_gain_setting(host='localhost', port=8081):
    """Test setting RF gain"""
    try:
        print(f"\nTesting gain setting...")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((host, port))
        
        # Send RF gain command
        sock.send(b"SET_RF_GAIN:35\n")
        response = sock.recv(1024).decode().strip()
        print(f"📡 SET_RF_GAIN response: {response}")
        
        sock.close()
        
        if response == "OK":
            print("✅ Gain setting successful")
            return True
        else:
            print(f"❌ Gain setting failed: {response}")
            return False
            
    except Exception as e:
        print(f"❌ Gain test error: {e}")
        return False

if __name__ == "__main__":
    print("🛩️ ADS-B Receiver Connection Test")
    print("=" * 40)
    
    # Test basic connection
    if test_receiver_connection():
        # Test gain setting
        test_gain_setting()
    else:
        print("\n💡 Make sure to start the receiver first:")
        print("   python adsb_receiver.py")
        sys.exit(1)
    
    print("\n🎯 Connection test complete!")