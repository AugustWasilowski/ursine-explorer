#!/bin/bash
# Ursine Explorer Installation Script for Raspberry Pi

set -e

echo "🛩️ Installing Ursine Explorer..."

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install HackRF and dump1090
echo "Installing HackRF and dump1090..."
sudo apt install -y hackrf libhackrf-dev python3 python3-pip

# Install dump1090-fa (FlightAware version with HackRF support)
echo "Installing dump1090-fa..."
sudo apt install -y git build-essential pkg-config libusb-1.0-0-dev libncurses-dev libncurses5-dev

# Clean up any existing dump1090 build
rm -rf /tmp/dump1090

cd /tmp
echo "Cloning dump1090 repository..."
git clone https://github.com/flightaware/dump1090.git
cd dump1090

echo "Building dump1090 with HackRF support..."
# Make sure HackRF support is enabled
export PKG_CONFIG_PATH=/usr/lib/pkgconfig:$PKG_CONFIG_PATH

# Check if HackRF libraries are available
if pkg-config --exists libhackrf; then
    echo "HackRF libraries found, building with HackRF support..."
    make
else
    echo "HackRF libraries not found, building without HackRF support..."
    echo "This will only support RTL-SDR devices"
    make
fi

if [ $? -eq 0 ]; then
    echo "Installing dump1090..."
    sudo make install
    
    # Verify installation
    if command -v dump1090-fa >/dev/null 2>&1; then
        echo "✅ dump1090-fa installed successfully at $(which dump1090-fa)"
        echo "Testing HackRF support..."
        dump1090-fa --help | grep -i hackrf && echo "✅ HackRF support enabled" || echo "⚠️ HackRF support not available"
    else
        echo "⚠️ dump1090-fa not found in PATH, checking /usr/local/bin..."
        if [ -f "/usr/local/bin/dump1090-fa" ]; then
            echo "✅ dump1090-fa found at /usr/local/bin/dump1090-fa"
            echo "Note: You may need to add /usr/local/bin to your PATH"
            echo "Testing HackRF support..."
            /usr/local/bin/dump1090-fa --help | grep -i hackrf && echo "✅ HackRF support enabled" || echo "⚠️ HackRF support not available"
        else
            echo "❌ dump1090-fa installation verification failed"
            echo "Trying alternative installation method..."
            # Try installing via apt if available
            sudo apt install -y dump1090-fa || echo "Package not available, manual build required"
        fi
    fi
else
    echo "❌ dump1090 build failed"
    echo "Trying to install via package manager..."
    sudo apt install -y dump1090-fa || echo "Package not available"
    exit 1
fi

cd /
rm -rf /tmp/dump1090

# Install Python dependencies
echo "Installing Python dependencies..."
sudo apt install -y python3-requests python3-full python3-numpy python3-serial

# Create service user (optional, for security)
if ! id "ursine" &>/dev/null; then
    echo "Creating ursine user..."
    sudo useradd -r -s /bin/false ursine
    sudo usermod -a -G plugdev ursine  # For RTL-SDR access
fi

# Set up directories
echo "Setting up directories..."
sudo mkdir -p /opt/ursine-explorer
sudo cp monitor.py /opt/ursine-explorer/
sudo cp adsb_receiver.py /opt/ursine-explorer/
sudo cp adsb_dashboard.py /opt/ursine-explorer/
sudo cp start_ursine.sh /opt/ursine-explorer/
sudo cp config.json /opt/ursine-explorer/
sudo chmod +x /opt/ursine-explorer/adsb_receiver.py
sudo chmod +x /opt/ursine-explorer/adsb_dashboard.py
sudo chmod +x /opt/ursine-explorer/start_ursine.sh
sudo chown -R ursine:ursine /opt/ursine-explorer

# Check for existing services that might conflict
echo "Checking for existing ADS-B services..."
if systemctl is-active --quiet dump1090-mutability; then
    echo "⚠️  dump1090-mutability service is running and will conflict with Ursine Explorer"
    echo "Stopping dump1090-mutability service..."
    sudo systemctl stop dump1090-mutability
    sudo systemctl disable dump1090-mutability
    echo "✅ dump1090-mutability service stopped and disabled"
fi

if systemctl is-active --quiet dump1090; then
    echo "⚠️  dump1090 service is running and will conflict with Ursine Explorer"
    echo "Stopping dump1090 service..."
    sudo systemctl stop dump1090
    sudo systemctl disable dump1090
    echo "✅ dump1090 service stopped and disabled"
fi

# Check for existing Ursine Explorer service
if systemctl is-active --quiet ursine-explorer; then
    echo "⚠️  Ursine Explorer service is already running"
    echo "Stopping existing Ursine Explorer service..."
    sudo systemctl stop ursine-explorer
fi

# Install systemd service
echo "Installing systemd service..."
sudo cp ursine-explorer.service /etc/systemd/system/
sudo systemctl daemon-reload

# Set up HackRF permissions
echo "Setting up HackRF permissions..."
sudo usermod -a -G plugdev ursine
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="6089", GROUP="plugdev", MODE="0664"' | sudo tee /etc/udev/rules.d/53-hackrf.rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# Post-installation verification
echo "Running post-installation verification..."

# Check if dump1090 binary exists and works
if [ -f "/usr/local/bin/dump1090" ]; then
    echo "✅ dump1090 binary found at /usr/local/bin/dump1090"
    # Test if it can start (without actually running)
    timeout 2 /usr/local/bin/dump1090 --help >/dev/null 2>&1 && echo "✅ dump1090 binary is functional" || echo "⚠️ dump1090 binary may have issues"
else
    echo "❌ dump1090 binary not found at /usr/local/bin/dump1090"
fi

# Check HackRF device
if lsusb | grep -q "1d50:6089"; then
    echo "✅ HackRF device detected"
else
    echo "⚠️ HackRF device not detected - make sure it's connected"
fi

# Check if ports are free
if netstat -tulpn 2>/dev/null | grep -q ":30005 "; then
    echo "⚠️ Port 30005 is in use - this may cause conflicts"
    echo "   Run: sudo ./kill_port.sh 30005"
else
    echo "✅ Port 30005 is available"
fi

if netstat -tulpn 2>/dev/null | grep -q ":8080 "; then
    echo "⚠️ Port 8080 is in use - this may cause conflicts"
    echo "   Run: sudo ./kill_port.sh 8080"
else
    echo "✅ Port 8080 is available"
fi

# Check Python dependencies
python3 -c "import requests, serial, numpy" 2>/dev/null && echo "✅ Python dependencies are available" || echo "⚠️ Some Python dependencies may be missing"

echo ""
echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /opt/ursine-explorer/config.json with your target ICAO codes and Meshtastic settings"
echo "2. Test the system: sudo -u ursine python3 /opt/ursine-explorer/adsb_receiver.py"
echo "3. Enable the service: sudo systemctl enable ursine-explorer"
echo "4. Start the service: sudo systemctl start ursine-explorer"
echo "5. Check status: sudo systemctl status ursine-explorer"
echo "6. View logs: sudo journalctl -u ursine-explorer -f"
echo ""
echo "If you encounter port conflicts, run: sudo ./kill_port.sh [PORT]"