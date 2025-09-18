#!/bin/bash
# Ursine Explorer Installation Script for Raspberry Pi

set -e

echo "🛩️ Installing Ursine Explorer..."

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install HackRF and GNU Radio tools
echo "Installing HackRF and GNU Radio tools..."
sudo apt install -y hackrf libhackrf-dev gnuradio gr-osmosdr python3 python3-pip

# Install Python dependencies
echo "Installing Python dependencies..."
sudo apt install -y python3-requests python3-full python3-numpy

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
sudo cp start_ursine.sh /opt/ursine-explorer/
sudo cp config.json /opt/ursine-explorer/
sudo chmod +x /opt/ursine-explorer/adsb_receiver.py
sudo chmod +x /opt/ursine-explorer/start_ursine.sh
sudo chown -R ursine:ursine /opt/ursine-explorer

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

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /opt/ursine-explorer/config.json with your Discord webhook and target ICAO codes"
echo "2. Test the ADS-B receiver: sudo -u ursine python3 /opt/ursine-explorer/adsb_receiver.py"
echo "3. Test the monitor: sudo -u ursine python3 /opt/ursine-explorer/monitor.py"
echo "4. Enable the service: sudo systemctl enable ursine-explorer"
echo "5. Start the service: sudo systemctl start ursine-explorer"
echo "6. Check status: sudo systemctl status ursine-explorer"