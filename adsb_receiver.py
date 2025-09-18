#!/usr/bin/env python3
"""
GNU Radio ADS-B Receiver for HackRF
Receives ADS-B signals and outputs aircraft data in dump1090-compatible JSON format
"""

import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
import signal
import sys

try:
    from gnuradio import gr, blocks, filter, analog, digital
    import osmosdr  # Import osmosdr directly, not from gnuradio
    import numpy as np
except ImportError as e:
    print(f"GNU Radio not properly installed: {e}")
    print("Try: sudo apt install gnuradio gr-osmosdr")
    sys.exit(1)

class ADSBReceiver(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "ADS-B Receiver")
        
        # Variables
        self.samp_rate = 2000000
        self.center_freq = 1090000000
        
        # Blocks
        self.osmosdr_source = osmosdr.source(args="hackrf=0")
        self.osmosdr_source.set_sample_rate(self.samp_rate)
        self.osmosdr_source.set_center_freq(self.center_freq, 0)
        self.osmosdr_source.set_freq_corr(0, 0)
        self.osmosdr_source.set_dc_offset_mode(0, 0)
        self.osmosdr_source.set_iq_balance_mode(0, 0)
        self.osmosdr_source.set_gain_mode(False, 0)
        self.osmosdr_source.set_gain(14, 0)
        self.osmosdr_source.set_if_gain(20, 0)
        self.osmosdr_source.set_bb_gain(20, 0)
        self.osmosdr_source.set_antenna('', 0)
        self.osmosdr_source.set_bandwidth(0, 0)
        
        # Simplified approach - just magnitude detection for ADS-B
        self.complex_to_mag = blocks.complex_to_mag()
        
        # File sink for debugging (optional)
        self.file_sink = blocks.file_sink(gr.sizeof_float*1, "/tmp/adsb_output.dat", False)
        self.file_sink.set_unbuffered(False)
        
        # Connect blocks - simplified chain
        self.connect((self.osmosdr_source, 0), (self.complex_to_mag, 0))
        self.connect((self.complex_to_mag, 0), (self.file_sink, 0))

class ADSBHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/data/aircraft.json':
            # Mock aircraft data for now - in a real implementation,
            # this would decode actual ADS-B messages
            aircraft_data = {
                "now": time.time(),
                "messages": 0,
                "aircraft": []
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
        # Suppress HTTP server logs
        pass

class ADSBServer:
    def __init__(self, port=8080):
        self.port = port
        self.httpd = None
        self.receiver = None
        
    def start_receiver(self):
        """Start the GNU Radio ADS-B receiver"""
        try:
            print("Starting GNU Radio ADS-B receiver...")
            self.receiver = ADSBReceiver()
            self.receiver.start()
            print(f"✅ HackRF receiver started on 1090 MHz")
            return True
        except Exception as e:
            print(f"❌ Failed to start receiver: {e}")
            return False
    
    def start_http_server(self):
        """Start HTTP server for aircraft data"""
        try:
            self.httpd = HTTPServer(('localhost', self.port), ADSBHTTPHandler)
            print(f"✅ HTTP server started on port {self.port}")
            print(f"📡 Aircraft data available at: http://localhost:{self.port}/data/aircraft.json")
            self.httpd.serve_forever()
        except Exception as e:
            print(f"❌ Failed to start HTTP server: {e}")
    
    def stop(self):
        """Stop the receiver and HTTP server"""
        print("\n🛑 Shutting down ADS-B receiver...")
        if self.receiver:
            self.receiver.stop()
            self.receiver.wait()
        if self.httpd:
            self.httpd.shutdown()

def signal_handler(sig, frame):
    print('\n🛑 Received interrupt signal')
    if hasattr(signal_handler, 'server'):
        signal_handler.server.stop()
    sys.exit(0)

def main():
    print("🛩️ GNU Radio ADS-B Receiver for HackRF")
    print("=" * 40)
    
    server = ADSBServer()
    signal_handler.server = server
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start receiver
    if not server.start_receiver():
        sys.exit(1)
    
    # Start HTTP server in a separate thread
    http_thread = threading.Thread(target=server.start_http_server)
    http_thread.daemon = True
    http_thread.start()
    
    print("\n📡 Receiver running... Press Ctrl+C to stop")
    print("🔍 Monitor with: curl http://localhost:8080/data/aircraft.json")
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()

if __name__ == "__main__":
    main()