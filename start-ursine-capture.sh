#!/bin/bash
# Ursine Capture - Complete System Startup Script
# Starts both receiver and dashboard processes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Ursine Capture - System Startup"
echo "================================"

# Check if we're in the right directory
if [[ ! -f "receiver.py" ]] || [[ ! -f "dashboard.py" ]]; then
    echo "Error: Not in Ursine Capture directory"
    echo "Please run this script from the directory containing receiver.py and dashboard.py"
    exit 1
fi

# Function to cleanup background processes
cleanup() {
    echo ""
    echo "Shutting down Ursine Capture..."
    if [[ -n "$RECEIVER_PID" ]]; then
        kill $RECEIVER_PID 2>/dev/null || true
        wait $RECEIVER_PID 2>/dev/null || true
    fi
    echo "Shutdown complete"
    exit 0
}

# Set up signal handlers
trap cleanup SIGINT SIGTERM

echo "Starting receiver process..."
python3 start-receiver.py &
RECEIVER_PID=$!

# Give receiver time to start
sleep 3

echo "Starting dashboard..."
echo "Note: Dashboard will take over the terminal"
echo "Press 'q' in dashboard to quit, or Ctrl+C to force quit"
echo ""

# Start dashboard in foreground
python3 start-dashboard.py

# If dashboard exits, cleanup receiver
cleanup