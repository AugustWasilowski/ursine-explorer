#!/bin/bash
# ADS-B Monitor Installation Script for Raspberry Pi

set -e

echo "🛩️ Installing ADS-B Monitor..."

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install RTL-SDR tools and dump1090
echo "Installing RTL-SDR and dump1090..."
sudo apt install -y rtl-sdr dump1090-mutability python3 python3-pip

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install requests

# Create service user (optional, for security)
if ! id "adsb" &>/dev/null; then
    echo "Creating adsb user..."
    sudo useradd -r -s /bin/false adsb
    sudo usermod -a -G plugdev adsb  # For RTL-SDR access
fi

# Set up directories
echo "Setting up directories..."
sudo mkdir -p /opt/adsb-monitor
sudo cp monitor.py /opt/adsb-monitor/
sudo cp config.json /opt/adsb-monitor/
sudo chown -R adsb:adsb /opt/adsb-monitor

# Install systemd service
echo "Installing systemd service..."
sudo cp adsb-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload

# Configure dump1090
echo "Configuring dump1090..."
sudo systemctl enable dump1090-mutability
sudo systemctl start dump1090-mutability

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /opt/adsb-monitor/config.json with your Discord webhook and target ICAO codes"
echo "2. Test the monitor: sudo -u adsb python3 /opt/adsb-monitor/monitor.py"
echo "3. Enable the service: sudo systemctl enable adsb-monitor"
echo "4. Start the service: sudo systemctl start adsb-monitor"
echo "5. Check status: sudo systemctl status adsb-monitor"