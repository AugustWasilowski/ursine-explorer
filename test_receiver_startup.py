#!/usr/bin/env python3
"""
Test script to verify receiver starts and stops cleanly
"""

import time
import signal
import sys
import threading

# Import the receiver
from adsb_receiver import ADSBServer

def test_startup_shutdown():
    """Test receiver startup and shutdown"""
    print("🧪 Testing ADS-B Receiver Startup/Shutdown")
    print("=" * 50)
    
    server = ADSBServer()
    
    try:
        # Test receiver startup
        print("1️⃣ Testing receiver startup...")
        if server.start_receiver():
            print("✅ Receiver started successfully")
            
            # Let it run for a few seconds
            print("2️⃣ Running for 3 seconds...")
            time.sleep(3)
            
            # Test shutdown
            print("3️⃣ Testing shutdown...")
            server.stop()
            print("✅ Shutdown completed")
            
            return True
        else:
            print("❌ Failed to start receiver")
            return False
            
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user")
        server.stop()
        return False
    except Exception as e:
        print(f"❌ Test failed: {e}")
        server.stop()
        return False

def test_signal_handling():
    """Test signal handling"""
    print("\n🧪 Testing Signal Handling")
    print("=" * 30)
    
    def signal_handler(sig, frame):
        print('\n🛑 Signal received - testing clean shutdown')
        sys.exit(0)
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    server = ADSBServer()
    
    try:
        if server.start_receiver():
            print("✅ Receiver started")
            print("💡 Press Ctrl+C to test signal handling...")
            
            # Wait for signal
            while True:
                time.sleep(1)
                
    except KeyboardInterrupt:
        print("\n🛑 KeyboardInterrupt caught")
        server.stop()
    except SystemExit:
        print("\n🔄 SystemExit caught")
        server.stop()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        server.stop()

if __name__ == "__main__":
    print("🛩️ ADS-B Receiver Test Suite")
    print("=" * 40)
    
    # Test 1: Basic startup/shutdown
    if test_startup_shutdown():
        print("\n✅ Basic test passed")
    else:
        print("\n❌ Basic test failed")
        sys.exit(1)
    
    # Test 2: Signal handling (interactive)
    print("\n" + "=" * 40)
    response = input("Run signal handling test? (y/n): ")
    if response.lower() == 'y':
        test_signal_handling()
    
    print("\n🎯 All tests completed!")