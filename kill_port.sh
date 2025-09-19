#!/bin/bash

# kill_port.sh - Find and kill processes using a specific port
# Usage: ./kill_port.sh [PORT]
# Example: ./kill_port.sh 30005

# Default port if none specified
DEFAULT_PORT=30005

# Get port from command line argument or use default
PORT=${1:-$DEFAULT_PORT}

echo "🔍 Searching for processes using port $PORT..."

# Find processes using the port
PIDS=$(lsof -ti:$PORT 2>/dev/null)

if [ -z "$PIDS" ]; then
    echo "✅ No processes found using port $PORT"
    exit 0
fi

echo "📋 Found processes using port $PORT:"
echo "----------------------------------------"

# Show process details
for PID in $PIDS; do
    PROCESS_INFO=$(ps -p $PID -o pid,ppid,cmd --no-headers 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "PID: $PID | $PROCESS_INFO"
    else
        echo "PID: $PID | (Process details unavailable)"
    fi
done

echo "----------------------------------------"

# Ask for confirmation
read -p "❓ Kill these processes? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🔫 Killing processes..."
    
    for PID in $PIDS; do
        echo "   Killing PID $PID..."
        kill -TERM $PID 2>/dev/null
        
        # Wait a moment for graceful shutdown
        sleep 1
        
        # Check if process is still running
        if kill -0 $PID 2>/dev/null; then
            echo "   Process $PID still running, force killing..."
            kill -KILL $PID 2>/dev/null
        fi
    done
    
    # Verify all processes are killed
    sleep 2
    REMAINING_PIDS=$(lsof -ti:$PORT 2>/dev/null)
    
    if [ -z "$REMAINING_PIDS" ]; then
        echo "✅ Successfully killed all processes using port $PORT"
    else
        echo "⚠️  Some processes may still be using port $PORT:"
        for PID in $REMAINING_PIDS; do
            echo "   PID $PID still running"
        done
    fi
else
    echo "❌ Operation cancelled"
    exit 1
fi

echo "🔍 Final check - processes using port $PORT:"
lsof -i:$PORT 2>/dev/null || echo "✅ Port $PORT is now free"
