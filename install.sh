#!/bin/bash
# Ursine Explorer Installation Script for Raspberry Pi (Integrated pyModeS Version)

set -e

echo "🛩️ Installing Ursine Explorer (Integrated pyModeS Version)..."

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install system dependencies
echo "Installing system dependencies..."
sudo apt install -y \
    hackrf libhackrf-dev \
    python3 python3-pip python3-venv python3-dev \
    git build-essential pkg-config \
    libusb-1.0-0-dev libncurses-dev libncurses5-dev \
    curl wget netcat-openbsd \
    libffi-dev libssl-dev

# Install dump1090-fa (FlightAware version with HackRF support)
echo "Installing dump1090-fa..."

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

# Install Python dependencies (system packages first)
echo "Installing Python system dependencies..."
sudo apt install -y \
    python3-requests \
    python3-numpy \
    python3-serial \
    python3-setuptools \
    python3-wheel

# Install pip packages for pyModeS and additional dependencies
echo "Installing Python pip dependencies..."
sudo pip3 install --upgrade pip

# Install pyModeS and related packages
echo "Installing pyModeS and enhanced dependencies..."
sudo pip3 install \
    pyModeS \
    numpy \
    requests \
    pyserial \
    psutil \
    typing-extensions

# Verify pyModeS installation
echo "Verifying pyModeS installation..."
python3 -c "import pyModeS; print(f'✅ pyModeS version {pyModeS.__version__} installed successfully')" || {
    echo "❌ pyModeS installation failed, trying alternative method..."
    sudo pip3 install --no-cache-dir pyModeS
    python3 -c "import pyModeS; print(f'✅ pyModeS version {pyModeS.__version__} installed successfully')" || {
        echo "❌ pyModeS installation failed completely"
        exit 1
    }
}

# Create service user (optional, for security)
if ! id "ursine" &>/dev/null; then
    echo "Creating ursine user..."
    sudo useradd -r -s /bin/false ursine
    sudo usermod -a -G plugdev ursine  # For RTL-SDR access
fi

# Set up directories
echo "Setting up directories..."
sudo mkdir -p /opt/ursine-explorer
sudo mkdir -p /opt/ursine-explorer/pymodes_integration

# Copy integrated system files
echo "Installing integrated system files..."
sudo cp adsb_receiver_integrated.py /opt/ursine-explorer/
sudo cp adsb_dashboard.py /opt/ursine-explorer/
sudo cp start_integrated_system.py /opt/ursine-explorer/
sudo cp start_ursine_integrated.sh /opt/ursine-explorer/
sudo cp migrate_to_integrated.py /opt/ursine-explorer/
sudo cp validate_system.py /opt/ursine-explorer/
sudo cp test_integration.py /opt/ursine-explorer/
sudo cp config.json /opt/ursine-explorer/

# Copy legacy files for backward compatibility
if [ -f "adsb_receiver.py" ]; then
    sudo cp adsb_receiver.py /opt/ursine-explorer/
fi
if [ -f "monitor.py" ]; then
    sudo cp monitor.py /opt/ursine-explorer/
fi
if [ -f "start_ursine.sh" ]; then
    sudo cp start_ursine.sh /opt/ursine-explorer/
fi

# Copy pyModeS integration module
echo "Installing pyModeS integration module..."
sudo cp -r pymodes_integration/* /opt/ursine-explorer/pymodes_integration/

# Copy documentation
sudo cp INTEGRATION_COMPLETE.md /opt/ursine-explorer/
sudo cp QUICK_START.md /opt/ursine-explorer/
if [ -f "README.md" ]; then
    sudo cp README.md /opt/ursine-explorer/
fi

# Set permissions
sudo chmod +x /opt/ursine-explorer/adsb_receiver_integrated.py
sudo chmod +x /opt/ursine-explorer/adsb_dashboard.py
sudo chmod +x /opt/ursine-explorer/start_integrated_system.py
sudo chmod +x /opt/ursine-explorer/start_ursine_integrated.sh
sudo chmod +x /opt/ursine-explorer/migrate_to_integrated.py
sudo chmod +x /opt/ursine-explorer/validate_system.py
sudo chmod +x /opt/ursine-explorer/test_integration.py

# Set ownership
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

# Create updated systemd service for integrated system
echo "Creating systemd service for integrated system..."
sudo tee /etc/systemd/system/ursine-explorer.service > /dev/null <<EOF
[Unit]
Description=Ursine Explorer ADS-B Receiver (Integrated pyModeS Version)
After=network.target
Wants=network.target

[Service]
Type=simple
User=ursine
Group=ursine
WorkingDirectory=/opt/ursine-explorer
ExecStart=/usr/bin/python3 /opt/ursine-explorer/start_integrated_system.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ursine-explorer

# Environment variables
Environment=PYTHONPATH=/opt/ursine-explorer
Environment=PYTHONUNBUFFERED=1

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/ursine-explorer
ReadWritePaths=/tmp

[Install]
WantedBy=multi-user.target
EOF

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

if netstat -tulpn 2>/dev/null | grep -q ":8081 "; then
    echo "⚠️ Port 8081 is in use - this may cause conflicts"
    echo "   Run: sudo ./kill_port.sh 8081"
else
    echo "✅ Port 8081 is available"
fi

# Check Python dependencies
echo "Verifying Python dependencies..."
python3 -c "import requests, serial, numpy" 2>/dev/null && echo "✅ Basic Python dependencies are available" || echo "⚠️ Some basic Python dependencies may be missing"

python3 -c "import pyModeS; print(f'✅ pyModeS {pyModeS.__version__} is available')" 2>/dev/null || echo "⚠️ pyModeS is not available"

# Test integrated system import
echo "Testing integrated system..."
cd /opt/ursine-explorer
sudo -u ursine python3 -c "
import sys
sys.path.append('/opt/ursine-explorer')
try:
    from adsb_receiver_integrated import IntegratedADSBServer
    print('✅ Integrated system imports successfully')
except Exception as e:
    print(f'⚠️ Integrated system import failed: {e}')
" 2>/dev/null || echo "⚠️ Integrated system test failed"

# Run system validation
echo "Running system validation..."
cd /opt/ursine-explorer
sudo -u ursine timeout 30 python3 validate_system.py --quick 2>/dev/null && echo "✅ System validation passed" || echo "⚠️ System validation had issues (check logs)"

echo ""
echo "🎉 Installation complete!"
echo ""
echo "=== INTEGRATED URSINE EXPLORER SYSTEM ==="
echo ""
echo "Quick Start:"
echo "1. Edit configuration: sudo nano /opt/ursine-explorer/config.json"
echo "2. Test the system: cd /opt/ursine-explorer && sudo -u ursine python3 start_integrated_system.py"
echo "3. Enable service: sudo systemctl enable ursine-explorer"
echo "4. Start service: sudo systemctl start ursine-explorer"
echo ""
echo "System Management:"
echo "• Check status: sudo systemctl status ursine-explorer"
echo "• View logs: sudo journalctl -u ursine-explorer -f"
echo "• Stop service: sudo systemctl stop ursine-explorer"
echo "• Restart service: sudo systemctl restart ursine-explorer"
echo ""
echo "Access Points:"
echo "• HTTP API: http://localhost:8080/data/aircraft.json"
echo "• Enhanced API: http://localhost:8080/data/aircraft_enhanced.json"
echo "• System Status: http://localhost:8080/api/status"
echo "• Health Check: http://localhost:8080/api/health"
echo "• Control Interface: telnet localhost 8081"
echo ""
echo "Dashboard:"
echo "• Run: cd /opt/ursine-explorer && python3 adsb_dashboard.py"
echo "• Or auto-start: python3 start_integrated_system.py --dashboard"
echo ""
echo "Migration from Legacy System:"
echo "• Run: cd /opt/ursine-explorer && python3 migrate_to_integrated.py"
echo ""
echo "Troubleshooting:"
echo "• Validate system: cd /opt/ursine-explorer && python3 validate_system.py"
echo "• Run tests: cd /opt/ursine-explorer && python3 test_integration.py"
echo "• Check dependencies: python3 -c 'import pyModeS; print(pyModeS.__version__)'"
echo ""
echo "Documentation: /opt/ursine-explorer/INTEGRATION_COMPLETE.md"
echo ""
if [ -f "/opt/ursine-explorer/kill_port.sh" ]; then
    echo "If you encounter port conflicts, run: sudo /opt/ursine-explorer/kill_port.sh [PORT]"
else
    echo "If you encounter port conflicts, kill processes manually: sudo lsof -ti:[PORT] | xargs sudo kill -9"
fi