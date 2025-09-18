#!/usr/bin/env python3
"""
Simple HackRF test without GNU Radio osmosdr
"""

import subprocess
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

class SimpleADSBHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/data/aircraft.json':
            # Simple mock data for testing
            aircraft_data = {
                "now": time.time(),
                "messages": 0,
                "aircraft": [
                    {
                        "hex": "a12345",
                        "flight": "TEST123",
                        "alt_baro": 35000,
                        "gs": 450,
                        "track": 180
                    }
                ]
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(aircraft_data).encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass

def test_hackrf():
    """Test if HackRF is accessible"""
    try:
        result = subprocess.run(['hackrf_info'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ HackRF detected and accessible")
            return True
        else:
            print(f"❌ HackRF error: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ HackRF test failed: {e}")
        return False

def main():
    print("🛩️ Simple ADS-B Test Server")
    print("=" * 30)
    
    # Test HackRF
    if not test_hackrf():
        print("Please check HackRF connection and permissions")
        return
    
    # Start simple HTTP server
    print("🌐 Starting test HTTP server on port 8080...")
    httpd = HTTPServer(('localhost', 8080), SimpleADSBHandler)
    
    print("✅ Test server running!")
    print("📡 Test with: curl http://localhost:8080/data/aircraft.json")
    print("Press Ctrl+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Stopping test server...")
        httpd.shutdown()

if __name__ == "__main__":
    main()