#!/usr/bin/env python3
"""
Terminal Waterfall Display for ADS-B Debugging
Shows frequency spectrum over time using ASCII characters
"""

import numpy as np
import time
import curses
import threading
import signal
import sys
import os
from collections import deque
from datetime import datetime

class WaterfallViewer:
    def __init__(self, fft_file="/tmp/adsb_fft.dat", fft_size=1024):
        self.fft_file = fft_file
        self.fft_size = fft_size
        self.running = True
        
        # Waterfall parameters
        self.history_lines = 50  # Number of lines to keep in waterfall
        self.waterfall_data = deque(maxlen=self.history_lines)
        
        # Frequency parameters (for ADS-B at 1090 MHz)
        self.center_freq = 1090e6  # 1090 MHz
        self.sample_rate = 2e6     # 2 MHz sample rate
        self.decimation = 4        # Decimation factor from receiver
        self.effective_sample_rate = self.sample_rate / self.decimation
        
        # Calculate frequency bins
        self.freq_bins = np.fft.fftfreq(self.fft_size, 1/self.effective_sample_rate)
        self.freq_bins = np.fft.fftshift(self.freq_bins) + self.center_freq
        
        # Display parameters
        self.min_db = -80  # Minimum dB level
        self.max_db = -20  # Maximum dB level
        self.update_rate = 10  # Updates per second
        
        # ASCII characters for intensity (darkest to brightest)
        self.intensity_chars = " .:-=+*#%@"
        
        # Statistics
        self.stats = {
            'updates': 0,
            'file_size': 0,
            'last_update': None,
            'peak_freq': 0,
            'peak_power': -999,
            'avg_power': -999,
            'adsb_power': -999  # Power at 1090 MHz
        }
    
    def read_fft_data(self):
        """Read FFT data from file"""
        try:
            if not os.path.exists(self.fft_file):
                return None
            
            # Get file size
            file_size = os.path.getsize(self.fft_file)
            self.stats['file_size'] = file_size
            
            if file_size < self.fft_size * 4:  # 4 bytes per float
                return None
            
            # Read the last complete FFT frame
            with open(self.fft_file, 'rb') as f:
                # Seek to the last complete frame
                frames_available = file_size // (self.fft_size * 4)
                if frames_available == 0:
                    return None
                
                # Read the most recent frame
                f.seek(-self.fft_size * 4, 2)  # Seek to last frame
                data = np.frombuffer(f.read(self.fft_size * 4), dtype=np.float32)
                
                if len(data) == self.fft_size:
                    return data
                
        except Exception as e:
            # File might be being written to, try again later
            pass
        
        return None
    
    def process_fft_data(self, fft_data):
        """Process FFT data and update statistics"""
        if fft_data is None:
            return None
        
        # Convert to dB
        # Add small epsilon to avoid log(0)
        fft_data = np.maximum(fft_data, 1e-12)
        db_data = 10 * np.log10(fft_data)
        
        # FFT shift to center DC
        db_data = np.fft.fftshift(db_data)
        
        # Update statistics
        self.stats['updates'] += 1
        self.stats['last_update'] = datetime.now()
        self.stats['avg_power'] = np.mean(db_data)
        
        # Find peak
        peak_idx = np.argmax(db_data)
        self.stats['peak_power'] = db_data[peak_idx]
        self.stats['peak_freq'] = self.freq_bins[peak_idx]
        
        # Find power at ADS-B frequency (1090 MHz)
        adsb_idx = np.argmin(np.abs(self.freq_bins - 1090e6))
        self.stats['adsb_power'] = db_data[adsb_idx]
        
        return db_data
    
    def db_to_char(self, db_value):
        """Convert dB value to ASCII character"""
        # Normalize to 0-1 range
        normalized = (db_value - self.min_db) / (self.max_db - self.min_db)
        normalized = np.clip(normalized, 0, 1)
        
        # Convert to character index
        char_idx = int(normalized * (len(self.intensity_chars) - 1))
        return self.intensity_chars[char_idx]
    
    def draw_waterfall(self, stdscr, start_y, height, width):
        """Draw the waterfall display"""
        waterfall_height = min(height - start_y - 5, len(self.waterfall_data))
        
        if not self.waterfall_data:
            stdscr.addstr(start_y, 0, "Waiting for FFT data...", curses.A_DIM)
            return start_y + 1
        
        # Calculate frequency range to display (focus around 1090 MHz)
        center_bin = len(self.freq_bins) // 2
        bins_to_show = min(width - 10, len(self.freq_bins))
        start_bin = max(0, center_bin - bins_to_show // 2)
        end_bin = min(len(self.freq_bins), start_bin + bins_to_show)
        
        # Draw frequency scale
        freq_start = self.freq_bins[start_bin] / 1e6  # Convert to MHz
        freq_end = self.freq_bins[end_bin-1] / 1e6
        freq_scale = f"Frequency: {freq_start:.2f} - {freq_end:.2f} MHz (1090 MHz ADS-B)"
        stdscr.addstr(start_y, 0, freq_scale[:width-1], curses.A_BOLD)
        
        # Draw waterfall (newest at top)
        for i, line_data in enumerate(reversed(list(self.waterfall_data)[-waterfall_height:])):
            y = start_y + 1 + i
            if y >= height - 3:
                break
            
            # Convert dB values to characters
            line_chars = ""
            for bin_idx in range(start_bin, end_bin):
                if bin_idx < len(line_data):
                    char = self.db_to_char(line_data[bin_idx])
                    line_chars += char
                else:
                    line_chars += " "
            
            # Add time indicator for newest line
            if i == 0:
                time_str = datetime.now().strftime("%H:%M:%S")
                line_chars = line_chars[:width-10] + f" {time_str}"
            
            stdscr.addstr(y, 0, line_chars[:width-1])
        
        return start_y + waterfall_height + 2
    
    def draw_spectrum(self, stdscr, start_y, height, width):
        """Draw current spectrum as a simple bar chart"""
        if not self.waterfall_data:
            return start_y
        
        current_spectrum = self.waterfall_data[-1]  # Most recent
        
        # Find bins around 1090 MHz for detailed view
        adsb_freq = 1090e6
        freq_range = 5e6  # ±5 MHz around ADS-B frequency
        
        mask = (self.freq_bins >= adsb_freq - freq_range) & (self.freq_bins <= adsb_freq + freq_range)
        freq_subset = self.freq_bins[mask]
        spectrum_subset = current_spectrum[mask]
        
        if len(spectrum_subset) == 0:
            return start_y
        
        # Draw spectrum title
        stdscr.addstr(start_y, 0, "Current Spectrum (1085-1095 MHz):", curses.A_BOLD)
        start_y += 1
        
        # Simple bar chart
        chart_width = min(width - 20, len(spectrum_subset))
        if chart_width <= 0:
            return start_y + 1
        
        # Downsample if needed
        if len(spectrum_subset) > chart_width:
            indices = np.linspace(0, len(spectrum_subset)-1, chart_width, dtype=int)
            spectrum_subset = spectrum_subset[indices]
            freq_subset = freq_subset[indices]
        
        # Normalize for display
        min_val = np.min(spectrum_subset)
        max_val = np.max(spectrum_subset)
        
        if max_val > min_val:
            normalized = (spectrum_subset - min_val) / (max_val - min_val)
            bar_heights = (normalized * 10).astype(int)  # 0-10 scale
            
            # Draw bars
            for i, (freq, height_val, db_val) in enumerate(zip(freq_subset, bar_heights, spectrum_subset)):
                bar_char = "|" if height_val > 5 else ":" if height_val > 2 else "."
                
                # Highlight ADS-B frequency
                if abs(freq - adsb_freq) < 0.5e6:  # Within 0.5 MHz of 1090
                    attr = curses.A_BOLD | curses.color_pair(1)
                else:
                    attr = curses.A_NORMAL
                
                stdscr.addstr(start_y, i, bar_char, attr)
            
            # Add scale
            stdscr.addstr(start_y + 1, 0, f"Scale: {min_val:.1f} to {max_val:.1f} dB")
        
        return start_y + 3
    
    def draw_stats(self, stdscr, start_y, height, width):
        """Draw statistics"""
        stats_lines = [
            f"Updates: {self.stats['updates']} | File Size: {self.stats['file_size']} bytes",
            f"Peak: {self.stats['peak_power']:.1f} dB @ {self.stats['peak_freq']/1e6:.2f} MHz",
            f"Average Power: {self.stats['avg_power']:.1f} dB",
            f"ADS-B (1090 MHz): {self.stats['adsb_power']:.1f} dB",
        ]
        
        if self.stats['last_update']:
            age = (datetime.now() - self.stats['last_update']).total_seconds()
            stats_lines.append(f"Last Update: {age:.1f}s ago")
        
        for i, line in enumerate(stats_lines):
            if start_y + i < height - 1:
                stdscr.addstr(start_y + i, 0, line[:width-1])
        
        return start_y + len(stats_lines)
    
    def draw_controls(self, stdscr, height, width):
        """Draw control instructions"""
        controls = "Controls: q=quit | r=reset | +/-=adjust scale | Space=pause"
        stdscr.addstr(height - 1, 0, controls[:width-1], curses.A_DIM)
    
    def data_updater(self):
        """Background thread to read FFT data"""
        while self.running:
            fft_data = self.read_fft_data()
            if fft_data is not None:
                processed_data = self.process_fft_data(fft_data)
                if processed_data is not None:
                    self.waterfall_data.append(processed_data)
            
            time.sleep(1.0 / self.update_rate)
    
    def handle_input(self, stdscr):
        """Handle keyboard input"""
        stdscr.nodelay(True)
        paused = False
        
        while self.running:
            try:
                key = stdscr.getch()
                
                if key == ord('q') or key == ord('Q'):
                    self.running = False
                elif key == ord('r') or key == ord('R'):
                    self.waterfall_data.clear()
                    self.stats['updates'] = 0
                elif key == ord('+') or key == ord('='):
                    self.max_db += 5
                elif key == ord('-'):
                    self.max_db -= 5
                elif key == ord(' '):
                    paused = not paused
                    if paused:
                        # Stop data updates
                        pass
                    else:
                        # Resume data updates
                        pass
                        
            except curses.error:
                pass
            
            time.sleep(0.1)
    
    def run_display(self, stdscr):
        """Main display loop"""
        # Initialize colors
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)    # ADS-B frequency highlight
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Good signal
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Warning
        
        # Start background threads
        data_thread = threading.Thread(target=self.data_updater, daemon=True)
        data_thread.start()
        
        input_thread = threading.Thread(target=self.handle_input, args=(stdscr,), daemon=True)
        input_thread.start()
        
        while self.running:
            try:
                stdscr.clear()
                height, width = stdscr.getmaxyx()
                
                # Draw title
                title = "🌊 ADS-B Waterfall Viewer - Terminal Spectrum Display 🌊"
                stdscr.addstr(0, max(0, (width - len(title)) // 2), title, curses.A_BOLD)
                
                # Draw components
                y = 2
                y = self.draw_stats(stdscr, y, height, width)
                y += 1
                y = self.draw_spectrum(stdscr, y, height, width)
                y += 1
                y = self.draw_waterfall(stdscr, y, height, width)
                
                self.draw_controls(stdscr, height, width)
                
                stdscr.refresh()
                time.sleep(0.1)  # 10 FPS display update
                
            except curses.error:
                pass
            except KeyboardInterrupt:
                self.running = False
    
    def run(self):
        """Start the waterfall viewer"""
        try:
            curses.wrapper(self.run_display)
        except KeyboardInterrupt:
            pass
        finally:
            self.running = False

def signal_handler(sig, frame):
    print('\n🛑 Waterfall viewer stopped')
    sys.exit(0)

def main():
    print("🌊 Starting ADS-B Waterfall Viewer...")
    print("Make sure the ADS-B receiver is running to generate FFT data")
    print("Press Ctrl+C to stop")
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    viewer = WaterfallViewer()
    viewer.run()

if __name__ == "__main__":
    main()