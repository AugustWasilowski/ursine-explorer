#!/usr/bin/env python3
"""
GNU Radio ADS-B Receiver for HackRF
Receives ADS-B signals and outputs aircraft data in dump1090-compatible JSON format
"""

import json
import time
import threading
import socket
import socketserver
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
        self._running = False
        
        try:
            # Blocks
            self.osmosdr_source = osmosdr.source(args="hackrf=0")
            self.osmosdr_source.set_sample_rate(self.samp_rate)
            self.osmosdr_source.set_center_freq(self.center_freq, 0)
            self.osmosdr_source.set_freq_corr(0, 0)
            self.osmosdr_source.set_dc_offset_mode(0, 0)
            self.osmosdr_source.set_iq_balance_mode(0, 0)
            self.osmosdr_source.set_gain_mode(False, 0)  # Manual gain control
            
            # Optimized gain settings for ADS-B reception
            self.osmosdr_source.set_gain(40, 0)      # RF gain: 40 dB (was 14)
            self.osmosdr_source.set_if_gain(32, 0)   # IF gain: 32 dB (was 20) 
            self.osmosdr_source.set_bb_gain(32, 0)   # BB gain: 32 dB (was 20)
            
            self.osmosdr_source.set_antenna('', 0)
            self.osmosdr_source.set_bandwidth(0, 0)  # Use default bandwidth
            
            # Simplified approach - just magnitude detection for ADS-B
            self.complex_to_mag = blocks.complex_to_mag()
            
            # File sink for debugging (optional)
            self.file_sink = blocks.file_sink(gr.sizeof_float*1, "/tmp/adsb_output.dat", False)
            self.file_sink.set_unbuffered(False)
            
            # Connect blocks - simplified chain
            self.connect((self.osmosdr_source, 0), (self.complex_to_mag, 0))
            self.connect((self.complex_to_mag, 0), (self.file_sink, 0))
            
        except Exception as e:
            print(f"❌ Failed to initialize GNU Radio blocks: {e}")
            raise
    
    def start(self):
        """Override start to track running state"""
        try:
            result = super().start()
            self._running = True
            return result
        except Exception as e:
            print(f"❌ Failed to start GNU Radio: {e}")
            raise
    
    def stop(self):
        """Override stop for better cleanup"""
        if self._running:
            try:
                super().stop()
                self._running = False
            except Exception as e:
                print(f"⚠️ Error stopping GNU Radio: {e}")
    
    def wait(self):
        """Override wait with timeout"""
        if self._running:
            try:
                super().wait()
            except Exception as e:
                print(f"⚠️ Error waiting for GNU Radio: {e}")

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

class ControlHandler(socketserver.BaseRequestHandler):
    """Handle control commands from dashboard"""
    
    def handle(self):
        try:
            data = self.request.recv(1024).decode().strip()
            print(f"🔧 Received command: {data}")
            
            if ':' in data:
                command, value = data.split(':', 1)
                value = float(value)
            else:
                command = data
                value = None
            
            # Get the server instance
            server = self.server.adsb_server
            success = False
            
            if command == 'PING':
                success = True  # Simple ping response
            elif command == 'SET_RF_GAIN' and value is not None:
                success = server.set_rf_gain(value)
            elif command == 'SET_IF_GAIN' and value is not None:
                success = server.set_if_gain(value)
            elif command == 'SET_BB_GAIN' and value is not None:
                success = server.set_bb_gain(value)
            elif command == 'SET_SAMPLE_RATE' and value is not None:
                success = server.set_sample_rate(value)
            elif command == 'SET_CENTER_FREQ' and value is not None:
                success = server.set_center_freq(value)
            
            response = "OK" if success else "ERROR"
            self.request.sendall(response.encode())
            
        except Exception as e:
            self.request.sendall(b"ERROR")

class ADSBServer:
    def __init__(self, port=8080, control_port=8081):
        self.port = port
        self.control_port = control_port
        self.httpd = None
        self.control_server = None
        self.receiver = None
        
    def start_receiver(self):
        """Start the GNU Radio ADS-B receiver"""
        try:
            print("Starting GNU Radio ADS-B receiver...")
            self.receiver = ADSBReceiver()
            self.receiver.start()
            print(f"✅ HackRF receiver started on 1090 MHz")
            
            # Give it a moment to initialize
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"❌ Failed to start receiver: {e}")
            if self.receiver:
                try:
                    self.receiver.stop()
                except:
                    pass
            return False
    
    def set_rf_gain(self, gain: float) -> bool:
        """Set RF gain on HackRF"""
        try:
            if self.receiver and 0 <= gain <= 47:
                self.receiver.osmosdr_source.set_gain(gain, 0)
                print(f"🔧 RF Gain set to {gain} dB")
                return True
        except Exception as e:
            print(f"❌ Failed to set RF gain: {e}")
        return False
    
    def set_if_gain(self, gain: float) -> bool:
        """Set IF gain on HackRF"""
        try:
            if self.receiver and 0 <= gain <= 47:
                self.receiver.osmosdr_source.set_if_gain(gain, 0)
                print(f"🔧 IF Gain set to {gain} dB")
                return True
        except Exception as e:
            print(f"❌ Failed to set IF gain: {e}")
        return False
    
    def set_bb_gain(self, gain: float) -> bool:
        """Set BB gain on HackRF"""
        try:
            if self.receiver and 0 <= gain <= 62:
                self.receiver.osmosdr_source.set_bb_gain(gain, 0)
                print(f"🔧 BB Gain set to {gain} dB")
                return True
        except Exception as e:
            print(f"❌ Failed to set BB gain: {e}")
        return False
    
    def set_sample_rate(self, rate: float) -> bool:
        """Set sample rate on HackRF"""
        try:
            if self.receiver and 1000000 <= rate <= 20000000:
                self.receiver.osmosdr_source.set_sample_rate(rate)
                print(f"🔧 Sample rate set to {rate/1e6:.1f} MHz")
                return True
        except Exception as e:
            print(f"❌ Failed to set sample rate: {e}")
        return False
    
    def set_center_freq(self, freq: float) -> bool:
        """Set center frequency on HackRF"""
        try:
            if self.receiver and 1000000 <= freq <= 6000000000:
                self.receiver.osmosdr_source.set_center_freq(freq, 0)
                print(f"🔧 Center frequency set to {freq/1e6:.1f} MHz")
                return True
        except Exception as e:
            print(f"❌ Failed to set center frequency: {e}")
        return False
    
    def start_control_server(self):
        """Start control server for dashboard commands"""
        try:
            self.control_server = socketserver.TCPServer(('localhost', self.control_port), ControlHandler)
            self.control_server.adsb_server = self  # Pass reference to self
            print(f"✅ Control server started on port {self.control_port}")
            self.control_server.serve_forever()
        except Exception as e:
            print(f"❌ Failed to start control server: {e}")
    
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
        
        # Stop GNU Radio flowgraph first (most important for clean shutdown)
        if self.receiver:
            try:
                print("🔧 Stopping GNU Radio flowgraph...")
                self.receiver.stop()
                
                # Use a timeout for waiting
                def wait_with_timeout():
                    try:
                        self.receiver.wait()
                    except Exception as e:
                        print(f"⚠️ GNU Radio wait error: {e}")
                
                wait_thread = threading.Thread(target=wait_with_timeout)
                wait_thread.daemon = True
                wait_thread.start()
                wait_thread.join(timeout=3.0)  # 3 second timeout
                
                if wait_thread.is_alive():
                    print("⚠️ GNU Radio wait timeout - forcing shutdown")
                else:
                    print("✅ GNU Radio stopped")
                    
            except Exception as e:
                print(f"⚠️ GNU Radio stop error: {e}")
        
        # Stop HTTP server
        if self.httpd:
            try:
                print("🔧 Stopping HTTP server...")
                self.httpd.shutdown()
                self.httpd.server_close()
                print("✅ HTTP server stopped")
            except Exception as e:
                print(f"⚠️ HTTP server stop error: {e}")
        
        # Stop control server
        if self.control_server:
            try:
                print("🔧 Stopping control server...")
                self.control_server.shutdown()
                self.control_server.server_close()
                print("✅ Control server stopped")
            except Exception as e:
                print(f"⚠️ Control server stop error: {e}")
        
        print("✅ Shutdown complete")

def signal_handler(sig, frame):
    print('\n🛑 Received interrupt signal')
    if hasattr(signal_handler, 'server'):
        try:
            signal_handler.server.stop()
        except Exception as e:
            print(f"⚠️ Error during shutdown: {e}")
    
    # Force exit if needed
    print("🔄 Forcing exit...")
    import os
    os._exit(0)

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
    
    # Start control server in a separate thread
    control_thread = threading.Thread(target=server.start_control_server)
    control_thread.daemon = True
    control_thread.start()
    
    print("\n📡 Receiver running... Press Ctrl+C to stop")
    print("🔍 Monitor with: curl http://localhost:8080/data/aircraft.json")
    print("⚙️ Control via dashboard on port 8081")
    
    try:
        # Keep the main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Keyboard interrupt received")
        server.stop()
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        server.stop()
    finally:
        print("🔄 Exiting main thread...")
        sys.exit(0)

if __name__ == "__main__":
    main()