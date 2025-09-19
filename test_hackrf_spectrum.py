#!/usr/bin/env python3
"""
Simple HackRF spectrum test
Tests if HackRF is receiving any signals at all
"""

import numpy as np
import matplotlib.pyplot as plt
import time
import sys

try:
    from gnuradio import gr, blocks, fft
    import osmosdr
except ImportError as e:
    print(f"GNU Radio not installed: {e}")
    sys.exit(1)

class SpectrumTest(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "HackRF Spectrum Test")
        
        # Parameters
        self.samp_rate = 2000000  # 2 MHz
        self.center_freq = 1090000000  # 1090 MHz
        self.fft_size = 1024
        
        # HackRF source
        self.osmosdr_source = osmosdr.source(args="hackrf=0")
        self.osmosdr_source.set_sample_rate(self.samp_rate)
        self.osmosdr_source.set_center_freq(self.center_freq, 0)
        self.osmosdr_source.set_freq_corr(0, 0)
        self.osmosdr_source.set_dc_offset_mode(0, 0)
        self.osmosdr_source.set_iq_balance_mode(0, 0)
        self.osmosdr_source.set_gain_mode(False, 0)
        
        # Test different gain settings
        self.osmosdr_source.set_gain(40, 0)      # RF gain
        self.osmosdr_source.set_if_gain(32, 0)   # IF gain
        self.osmosdr_source.set_bb_gain(32, 0)   # BB gain
        
        # FFT and file sink
        self.fft = fft.fft_vcc(self.fft_size, True, (), True)
        self.complex_to_mag_squared = blocks.complex_to_mag_squared(self.fft_size)
        self.vector_to_stream = blocks.vector_to_stream(gr.sizeof_float*1, self.fft_size)
        self.file_sink = blocks.file_sink(gr.sizeof_float*1, "/tmp/hackrf_test_spectrum.dat", False)
        
        # Connect blocks
        self.connect((self.osmosdr_source, 0), (self.fft, 0))
        self.connect((self.fft, 0), (self.complex_to_mag_squared, 0))
        self.connect((self.complex_to_mag_squared, 0), (self.vector_to_stream, 0))
        self.connect((self.vector_to_stream, 0), (self.file_sink, 0))

def test_hackrf():
    print("🔧 Testing HackRF spectrum reception...")
    print("This will run for 10 seconds and save spectrum data")
    
    try:
        # Create and start flowgraph
        tb = SpectrumTest()
        tb.start()
        print("✅ HackRF started, collecting data...")
        
        # Run for 10 seconds
        time.sleep(10)
        
        # Stop flowgraph
        tb.stop()
        tb.wait()
        print("✅ Data collection complete")
        
        # Analyze the data
        analyze_spectrum_data()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False
    
    return True

def analyze_spectrum_data():
    """Analyze the collected spectrum data"""
    filename = "/tmp/hackrf_test_spectrum.dat"
    fft_size = 1024
    
    try:
        # Read the data
        data = np.fromfile(filename, dtype=np.float32)
        print(f"📊 Read {len(data)} samples from {filename}")
        
        if len(data) < fft_size:
            print("❌ Not enough data collected")
            return
        
        # Take the last complete FFT frame
        num_frames = len(data) // fft_size
        print(f"📊 Found {num_frames} FFT frames")
        
        if num_frames == 0:
            print("❌ No complete FFT frames found")
            return
        
        # Get the last frame
        last_frame = data[-fft_size:]
        
        # Convert to dB
        last_frame = np.maximum(last_frame, 1e-12)  # Avoid log(0)
        db_data = 10 * np.log10(last_frame)
        db_data = np.fft.fftshift(db_data)
        
        # Calculate statistics
        min_power = np.min(db_data)
        max_power = np.max(db_data)
        avg_power = np.mean(db_data)
        std_power = np.std(db_data)
        
        print(f"📊 Spectrum Analysis:")
        print(f"   Min Power: {min_power:.1f} dB")
        print(f"   Max Power: {max_power:.1f} dB")
        print(f"   Avg Power: {avg_power:.1f} dB")
        print(f"   Std Dev:   {std_power:.1f} dB")
        print(f"   Dynamic Range: {max_power - min_power:.1f} dB")
        
        # Check if we're seeing reasonable signal levels
        if max_power > -50:
            print("✅ Strong signals detected!")
        elif max_power > -70:
            print("⚠️ Moderate signals detected")
        else:
            print("❌ Very weak or no signals detected")
            print("   Try adjusting antenna or gain settings")
        
        # Check for noise floor
        if std_power > 5:
            print("✅ Good signal variation (not just noise)")
        else:
            print("⚠️ Low signal variation - might be mostly noise")
        
        # Simple text plot
        print(f"\n📈 Simple Spectrum Plot (last {fft_size} bins):")
        plot_spectrum_text(db_data)
        
    except Exception as e:
        print(f"❌ Error analyzing data: {e}")

def plot_spectrum_text(db_data, width=80):
    """Create a simple text-based spectrum plot"""
    # Normalize data for plotting
    min_val = np.min(db_data)
    max_val = np.max(db_data)
    
    if max_val <= min_val:
        print("No variation in data")
        return
    
    # Downsample to fit width
    if len(db_data) > width:
        indices = np.linspace(0, len(db_data)-1, width, dtype=int)
        plot_data = db_data[indices]
    else:
        plot_data = db_data
    
    # Normalize to 0-10 range for text plotting
    normalized = (plot_data - min_val) / (max_val - min_val)
    heights = (normalized * 10).astype(int)
    
    # Create text plot
    for row in range(10, -1, -1):
        line = ""
        for height in heights:
            if height >= row:
                line += "█"
            else:
                line += " "
        
        # Add scale
        db_level = min_val + (row / 10.0) * (max_val - min_val)
        print(f"{db_level:6.1f} |{line}")
    
    # Add frequency axis
    print("       " + "─" * len(heights))
    print(f"       1088 MHz{' ' * (len(heights)-20)}1092 MHz")

def main():
    print("🛩️ HackRF ADS-B Spectrum Test")
    print("=" * 40)
    
    if not test_hackrf():
        print("❌ Test failed")
        sys.exit(1)
    
    print("\n✅ Test completed successfully!")
    print("If you see strong signals, your HackRF is working.")
    print("If not, try:")
    print("  - Check antenna connection")
    print("  - Try different gain settings")
    print("  - Check for interference")
    print("  - Verify HackRF is properly connected")

if __name__ == "__main__":
    main()