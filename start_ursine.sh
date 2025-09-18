#!/bin/bash
# Ursine Explorer startup script
# Starts both the ADS-B receiver and monitor

set -e

INSTALL_DIR="/opt/ursine-explorer"
cd "$INSTALL_DIR"

echo "🛩️ Starting Ursine Explorer..."

# Start ADS-B receiver in background
echo "📡 Starting GNU Radio ADS-B receiver..."
python3 adsb_receiver.py &
RECEIVER_PID=$!

# Wait a moment for receiver to start
sleep 5

# Start monitor
echo "👁️ Starting aircraft monitor..."
python3 monitor.py &
MONITOR_PID=$!

# Function to cleanup on exit
cleanup() {
    echo "🛑 Shutting down Ursine Explorer..."
    kill $RECEIVER_PID 2>/dev/null || true
    kill $MONITOR_PID 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap cleanup SIGTERM SIGINT

# Wait for processes
wait $RECEIVER_PID $MONITOR_PID