#!/bin/bash
# Ursine Explorer Docker Installation Script

set -e

echo "🐳 Installing Ursine Explorer with Docker..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "✅ Docker installed. Please log out and back in for group changes to take effect."
    echo "Then run this script again."
    exit 0
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose installed"
fi

# Check for HackRF device
echo "Checking for HackRF device..."
if lsusb | grep -q "1d50:6089"; then
    echo "✅ HackRF device detected"
else
    echo "⚠️ HackRF device not detected - make sure it's connected"
    echo "   The container will start but may not receive ADS-B data"
fi

# Check if ports are free
echo "Checking port availability..."
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

# Build and start the container
echo "Building Ursine Explorer Docker image..."
docker-compose build

echo "Starting Ursine Explorer..."
docker-compose up -d

# Wait for container to start
echo "Waiting for container to start..."
sleep 5

# Check container status
if docker-compose ps | grep -q "Up"; then
    echo "✅ Ursine Explorer is running!"
    echo ""
    echo "Container status:"
    docker-compose ps
    echo ""
    echo "View logs: docker-compose logs -f"
    echo "Stop: docker-compose down"
    echo "Restart: docker-compose restart"
    echo ""
    echo "HTTP API: http://localhost:8080/data/aircraft.json"
    echo "Control port: localhost:8081"
else
    echo "❌ Container failed to start"
    echo "Check logs: docker-compose logs"
    exit 1
fi

echo ""
echo "✅ Docker installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit config.json with your target ICAO codes and Meshtastic settings"
echo "2. Restart container: docker-compose restart"
echo "3. View logs: docker-compose logs -f"
echo "4. Test API: curl http://localhost:8080/data/aircraft.json"
