#!/bin/bash
# Simple startup script for Ursine Explorer Integrated System

set -e

echo "🛩️ Starting Ursine Explorer (Integrated pyModeS Version)..."

# Check if we're in the right directory
if [ ! -f "adsb_receiver_integrated.py" ]; then
    echo "❌ adsb_receiver_integrated.py not found in current directory"
    echo "Please run this script from the Ursine Explorer directory"
    exit 1
fi

# Check dependencies
echo "Checking dependencies..."
python3 -c "import pyModeS, numpy, requests, serial" 2>/dev/null || {
    echo "❌ Missing dependencies. Please install with:"
    echo "pip3 install pyModeS numpy requests pyserial"
    exit 1
}

echo "✅ Dependencies OK"

# Check configuration
if [ ! -f "config.json" ]; then
    echo "⚠️ config.json not found, creating default..."
    cat > config.json << 'EOF'
{
    "dump1090_host": "localhost",
    "dump1090_port": 30005,
    "receiver_control_port": 8081,
    "frequency": 1090000000,
    "lna_gain": 40,
    "vga_gain": 20,
    "enable_hackrf_amp": true,
    "target_icao_codes": [],
    "meshtastic_port": null,
    "meshtastic_baud": 115200,
    "log_alerts": true,
    "alert_log_file": "alerts.log",
    "alert_interval_sec": 300,
    "dump1090_path": "/usr/local/bin/dump1090",
    "watchdog_timeout_sec": 60,
    "poll_interval_sec": 1,
    
    "pymodes": {
        "enabled": true,
        "reference_position": {
            "latitude": null,
            "longitude": null
        }
    }
}
EOF
    echo "✅ Default config.json created"
fi

# Parse command line arguments
START_DASHBOARD=false
RUN_TESTS=false
VALIDATE_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--dashboard)
            START_DASHBOARD=true
            shift
            ;;
        -t|--test)
            RUN_TESTS=true
            shift
            ;;
        -v|--validate)
            VALIDATE_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -d, --dashboard    Start dashboard automatically"
            echo "  -t, --test         Run integration tests"
            echo "  -v, --validate     Run system validation only"
            echo "  -h, --help         Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                 Start the integrated system"
            echo "  $0 --dashboard     Start system with dashboard"
            echo "  $0 --test          Run tests"
            echo "  $0 --validate      Validate system setup"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Run tests if requested
if [ "$RUN_TESTS" = true ]; then
    echo "Running integration tests..."
    python3 test_integration.py
    exit $?
fi

# Run validation if requested
if [ "$VALIDATE_ONLY" = true ]; then
    echo "Running system validation..."
    python3 validate_system.py
    exit $?
fi

# Check if ports are available
check_port() {
    local port=$1
    local service=$2
    
    if netstat -tulpn 2>/dev/null | grep -q ":$port "; then
        echo "⚠️ Port $port is in use by another process"
        echo "This may cause conflicts with $service"
        echo "You may need to stop other ADS-B services first"
        return 1
    fi
    return 0
}

echo "Checking ports..."
check_port 8080 "HTTP API" || echo "  Continuing anyway..."
check_port 8081 "Control Interface" || echo "  Continuing anyway..."

# Start the system
echo ""
echo "Starting Integrated ADS-B System..."
echo "=================================="

if [ "$START_DASHBOARD" = true ]; then
    echo "Starting with dashboard..."
    python3 start_integrated_system.py --dashboard
else
    echo "Starting receiver only..."
    echo "To start dashboard separately, run: python3 adsb_dashboard.py"
    echo ""
    python3 start_integrated_system.py
fi