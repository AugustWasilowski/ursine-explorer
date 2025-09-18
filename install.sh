#!/bin/bash
# Ursine Explorer Installation Script for Raspberry Pi

set -e

echo "🛩️ Installing Ursine Explorer..."

# Update system
echo "Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install RTL-SDR tools and dump1090
echo "Installing RTL-SDR and dump1090..."
sudo apt install -y rtl-sdr dump1090-mutability python3 python3-pip

# Install Python dependencies
echo "Installing Python dependencies..."
sudo apt install -y python3-requests python3-full

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
sudo cp config.json /opt/ursine-explorer/
sudo chown -R ursine:ursine /opt/ursine-explorer

# Install systemd service
echo "Installing systemd service..."
sudo cp ursine-explorer.service /etc/systemd/system/
sudo systemctl daemon-reload

# Configure dump1090
echo "Configuring dump1090..."
sudo systemctl enable dump1090-mutability
sudo systemctl start dump1090-mutability

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit /opt/ursine-explorer/config.json with your Discord webhook and target ICAO codes"
echo "2. Test the monitor: sudo -u ursine python3 /opt/ursine-explorer/monitor.py"
echo "3. Enable the service: sudo systemctl enable ursine-explorer"
echo "4. Start the service: sudo systemctl start ursine-explorer"
echo "5. Check status: sudo systemctl status ursine-explorer"