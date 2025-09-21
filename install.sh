#!/bin/bash
# Ursine Capture - Installation Script
# One-command setup for ADS-B monitoring system

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging
LOG_FILE="ursine-install.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
    echo -e "$1"
}

success() {
    log "${GREEN}✓${NC} $1"
}

warning() {
    log "${YELLOW}⚠${NC} $1"
}

error() {
    log "${RED}✗${NC} $1"
}

info() {
    log "${BLUE}ℹ${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        error "Don't run this script as root. It will use sudo when needed."
        exit 1
    fi
}

# Detect system
detect_system() {
    info "Detecting system..."
    
    OS=$(uname -s)
    ARCH=$(uname -m)
    
    case "$OS" in
        Linux*)
            if command -v apt-get >/dev/null 2>&1; then
                PKG_MANAGER="apt"
                INSTALL_CMD="sudo apt-get install -y"
                UPDATE_CMD="sudo apt-get update"
            elif command -v yum >/dev/null 2>&1; then
                PKG_MANAGER="yum"
                INSTALL_CMD="sudo yum install -y"
                UPDATE_CMD="sudo yum update"
            elif command -v dnf >/dev/null 2>&1; then
                PKG_MANAGER="dnf"
                INSTALL_CMD="sudo dnf install -y"
                UPDATE_CMD="sudo dnf update"
            else
                error "Unsupported package manager. Please install dependencies manually."
                exit 1
            fi
            ;;
        Darwin*)
            if command -v brew >/dev/null 2>&1; then
                PKG_MANAGER="brew"
                INSTALL_CMD="brew install"
                UPDATE_CMD="brew update"
            else
                error "Homebrew not found. Please install Homebrew first: https://brew.sh"
                exit 1
            fi
            ;;
        *)
            error "Unsupported operating system: $OS"
            exit 1
            ;;
    esac
    
    success "System: $OS $ARCH, Package manager: $PKG_MANAGER"
}

# Install system packages
install_system_packages() {
    info "Installing system packages..."
    
    case "$PKG_MANAGER" in
        apt)
            $UPDATE_CMD || warning "Could not update package list"
            
            PACKAGES="python3 python3-pip python3-dev build-essential libusb-1.0-0-dev pkg-config"
            
            # Try to install dump1090-fa
            if $INSTALL_CMD dump1090-fa 2>/dev/null; then
                success "dump1090-fa installed"
            else
                warning "dump1090-fa not available, trying dump1090-mutability"
                if $INSTALL_CMD dump1090-mutability 2>/dev/null; then
                    success "dump1090-mutability installed"
                else
                    warning "No dump1090 variant available in repositories"
                fi
            fi
            
            # Try to install HackRF tools
            if $INSTALL_CMD hackrf libhackrf-dev libhackrf0 2>/dev/null; then
                success "HackRF tools installed"
            else
                warning "HackRF tools not available in repositories"
            fi
            
            $INSTALL_CMD $PACKAGES
            ;;
            
        yum|dnf)
            $UPDATE_CMD || warning "Could not update package list"
            
            PACKAGES="python3 python3-pip python3-devel gcc libusb1-devel pkgconfig"
            $INSTALL_CMD $PACKAGES
            
            # Try EPEL for additional packages
            if command -v yum >/dev/null 2>&1; then
                sudo yum install -y epel-release 2>/dev/null || true
            fi
            
            warning "dump1090 and HackRF tools may need manual installation on RHEL/CentOS"
            ;;
            
        brew)
            $UPDATE_CMD || warning "Could not update Homebrew"
            
            PACKAGES="python3 libusb pkg-config"
            $INSTALL_CMD $PACKAGES
            
            # Try to install HackRF
            if $INSTALL_CMD hackrf 2>/dev/null; then
                success "HackRF tools installed"
            else
                warning "HackRF tools not available via Homebrew"
            fi
            
            warning "dump1090 may need manual installation on macOS"
            ;;
    esac
    
    success "System packages installation completed"
}

# Install Python packages
install_python_packages() {
    info "Installing Python packages..."
    
    # Check if we're in a virtual environment
    if [[ -n "$VIRTUAL_ENV" ]]; then
        info "Using virtual environment: $VIRTUAL_ENV"
        PIP_CMD="pip"
    else
        info "Installing system-wide (use virtual environment if preferred)"
        PIP_CMD="pip3"
        
        # Try to upgrade pip
        python3 -m pip install --upgrade pip --user 2>/dev/null || true
    fi
    
    # Install packages from requirements.txt if it exists
    if [[ -f "requirements.txt" ]]; then
        info "Installing from requirements.txt..."
        $PIP_CMD install -r requirements.txt
    else
        # Install essential packages directly
        info "Installing essential packages..."
        PYTHON_PACKAGES=(
            "psutil>=5.8.0"
            "numpy>=1.21.0"
            "requests>=2.25.0"
            "pyModeS>=2.13.0"
            "pyserial>=3.5"
            "meshtastic>=2.0.0"
            "paho-mqtt>=1.6.0"
            "cryptography>=3.4.8"
        )
        
        for package in "${PYTHON_PACKAGES[@]}"; do
            info "Installing $package..."
            if $PIP_CMD install "$package"; then
                success "$package installed"
            else
                # Try without version constraint
                base_package=$(echo "$package" | cut -d'>' -f1)
                warning "Retrying $base_package without version constraint..."
                if $PIP_CMD install "$base_package"; then
                    success "$base_package installed"
                else
                    error "Failed to install $base_package"
                    return 1
                fi
            fi
        done
    fi
    
    success "Python packages installation completed"
}

# Setup HackRF permissions
setup_hackrf_permissions() {
    info "Setting up HackRF permissions..."
    
    if [[ "$OS" == "Linux" ]]; then
        # Create udev rules
        UDEV_RULES="/etc/udev/rules.d/52-hackrf.rules"
        
        cat << 'EOF' | sudo tee "$UDEV_RULES" > /dev/null
# HackRF One
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="6089", GROUP="plugdev", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="604b", GROUP="plugdev", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="cc15", GROUP="plugdev", MODE="0666"
EOF
        
        success "HackRF udev rules installed"
        
        # Add user to plugdev group
        if sudo usermod -a -G plugdev "$USER" 2>/dev/null; then
            success "Added $USER to plugdev group"
            warning "You may need to log out and back in for group changes to take effect"
        else
            warning "Could not add user to plugdev group"
        fi
        
        # Reload udev rules
        sudo udevadm control --reload-rules 2>/dev/null || true
        sudo udevadm trigger 2>/dev/null || true
        
    else
        info "Skipping udev rules setup on non-Linux system"
    fi
}

# Detect hardware
detect_hardware() {
    info "Detecting hardware..."
    
    HACKRF_DETECTED=false
    MESHTASTIC_PORTS=()
    
    # Check for HackRF
    if command -v hackrf_info >/dev/null 2>&1; then
        if hackrf_info 2>/dev/null | grep -q "Found HackRF"; then
            HACKRF_DETECTED=true
            success "HackRF One detected and accessible"
        else
            warning "HackRF tools available but no device detected"
        fi
    else
        warning "HackRF tools not found"
    fi
    
    # Check for USB serial devices (potential Meshtastic)
    shopt -s nullglob
    for port in /dev/ttyUSB* /dev/ttyACM* /dev/cu.usbserial* /dev/cu.usbmodem*; do
        if [[ -e "$port" ]]; then
            MESHTASTIC_PORTS+=("$port")
        fi
    done
    shopt -u nullglob
    
    if [[ ${#MESHTASTIC_PORTS[@]} -gt 0 ]]; then
        success "Found ${#MESHTASTIC_PORTS[@]} USB serial device(s): ${MESHTASTIC_PORTS[*]}"
    else
        warning "No USB serial devices found for Meshtastic"
    fi
}

# Create configuration
create_config() {
    info "Creating configuration file..."
    
    CONFIG_FILE="config.json"
    
    # Find dump1090 path
    DUMP1090_PATH=""
    for path in /usr/bin/dump1090-fa /usr/bin/dump1090 /usr/local/bin/dump1090-fa /usr/local/bin/dump1090; do
        if [[ -x "$path" ]]; then
            DUMP1090_PATH="$path"
            break
        fi
    done
    
    if [[ -z "$DUMP1090_PATH" ]]; then
        DUMP1090_PATH="/usr/bin/dump1090-fa"
        warning "dump1090 not found, using default path: $DUMP1090_PATH"
    else
        success "Found dump1090 at: $DUMP1090_PATH"
    fi
    
    # Set Meshtastic port
    MESHTASTIC_PORT="/dev/ttyUSB0"
    if [[ ${#MESHTASTIC_PORTS[@]} -gt 0 ]]; then
        MESHTASTIC_PORT="${MESHTASTIC_PORTS[0]}"
        success "Set Meshtastic port to: $MESHTASTIC_PORT"
    else
        info "Using default Meshtastic port: $MESHTASTIC_PORT"
    fi
    
    # Create config file
    cat << EOF > "$CONFIG_FILE"
{
  "receiver": {
    "dump1090_path": "$DUMP1090_PATH",
    "frequency": 1090000000,
    "gain": 40,
    "update_interval": 1.0,
    "cleanup_interval": 30
  },
  "meshtastic": {
    "enabled": true,
    "port": "$MESHTASTIC_PORT",
    "channel": 0,
    "alert_cooldown": 300
  },
  "watchlist": {
    "enabled": true,
    "aircraft": [],
    "alert_on_new": false
  },
  "dashboard": {
    "update_interval": 0.5,
    "max_aircraft_display": 50,
    "show_ground": false
  },
  "logging": {
    "level": "INFO",
    "file": "ursine-capture.log",
    "max_size_mb": 10,
    "backup_count": 3
  },
  "_hardware_detection": {
    "hackrf_detected": $HACKRF_DETECTED,
    "meshtastic_ports": [$(if [[ ${#MESHTASTIC_PORTS[@]} -gt 0 ]]; then printf '"%s",' "${MESHTASTIC_PORTS[@]}" | sed 's/,$//'; fi)]
  }
}
EOF
    
    success "Configuration file created: $CONFIG_FILE"
}

# Verify installation
verify_installation() {
    info "Verifying installation..."
    
    CHECKS_PASSED=0
    TOTAL_CHECKS=0
    
    # Check Python imports
    info "Checking Python imports..."
    PYTHON_PACKAGES=("pyModeS" "psutil" "serial" "meshtastic" "numpy")
    
    for package in "${PYTHON_PACKAGES[@]}"; do
        ((TOTAL_CHECKS++))
        if python3 -c "import $package" 2>/dev/null; then
            success "$package import successful"
            ((CHECKS_PASSED++))
        else
            error "$package import failed"
        fi
    done
    
    # Check dump1090
    ((TOTAL_CHECKS++))
    if command -v dump1090-fa >/dev/null 2>&1 || command -v dump1090 >/dev/null 2>&1; then
        success "dump1090 available"
        ((CHECKS_PASSED++))
    else
        error "dump1090 not found"
    fi
    
    # Check HackRF tools
    ((TOTAL_CHECKS++))
    if command -v hackrf_info >/dev/null 2>&1; then
        success "HackRF tools available"
        ((CHECKS_PASSED++))
    else
        error "HackRF tools not found"
    fi
    
    # Check core files
    CORE_FILES=("receiver.py" "dashboard.py" "config.py" "aircraft.py" "utils.py")
    for file in "${CORE_FILES[@]}"; do
        ((TOTAL_CHECKS++))
        if [[ -f "$file" ]]; then
            success "$file exists"
            ((CHECKS_PASSED++))
        else
            error "$file missing"
        fi
    done
    
    # Check config file
    ((TOTAL_CHECKS++))
    if [[ -f "config.json" ]]; then
        success "config.json exists"
        ((CHECKS_PASSED++))
    else
        error "config.json missing"
    fi
    
    echo
    info "Verification Summary: $CHECKS_PASSED/$TOTAL_CHECKS checks passed"
    
    # Determine success
    CRITICAL_CHECKS=5  # Python imports
    if [[ $CHECKS_PASSED -ge $CRITICAL_CHECKS ]]; then
        success "Installation verification PASSED"
        return 0
    else
        error "Installation verification FAILED"
        return 1
    fi
}

# Print usage instructions
print_usage() {
    echo
    info "Installation completed! To start Ursine Capture:"
    echo
    echo "  1. Start the complete system:"
    echo "     ./start-ursine-capture.sh"
    echo
    echo "  2. Or start components individually:"
    echo "     python3 start-receiver.py    # In one terminal"
    echo "     python3 start-dashboard.py   # In another terminal"
    echo
    echo "Configuration: config.json"
    echo "Logs: ursine-capture.log, ursine-install.log"
    echo
    
    if [[ "$HACKRF_DETECTED" != "true" ]]; then
        warning "Connect your HackRF One device before starting"
    fi
    
    if [[ ${#MESHTASTIC_PORTS[@]} -eq 0 ]]; then
        warning "Connect your Meshtastic device for alert functionality"
    fi
}

# Main installation function
main() {
    echo "Ursine Capture - Installation Script"
    echo "===================================="
    echo
    
    # Parse arguments
    TEST_MODE=false
    VERIFY_ONLY=false
    DETECT_ONLY=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --test-mode)
                TEST_MODE=true
                shift
                ;;
            --verify-only)
                VERIFY_ONLY=true
                shift
                ;;
            --detect-hardware)
                DETECT_ONLY=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo
                echo "Options:"
                echo "  --test-mode        Run without making system changes"
                echo "  --verify-only      Only verify existing installation"
                echo "  --detect-hardware  Only detect and report hardware"
                echo "  --help, -h         Show this help message"
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Initialize log
    echo "Installation started at $(date)" > "$LOG_FILE"
    
    check_root
    detect_system
    
    if [[ "$DETECT_ONLY" == "true" ]]; then
        detect_hardware
        echo
        echo "Hardware Detection Results:"
        echo "=========================="
        echo "HackRF Detected: $HACKRF_DETECTED"
        echo "USB Serial Ports: ${#MESHTASTIC_PORTS[@]}"
        for port in "${MESHTASTIC_PORTS[@]}"; do
            echo "  - $port"
        done
        exit 0
    fi
    
    if [[ "$VERIFY_ONLY" == "true" ]]; then
        detect_hardware
        if verify_installation; then
            exit 0
        else
            exit 1
        fi
    fi
    
    # Full installation
    if [[ "$TEST_MODE" == "true" ]]; then
        info "Running in TEST MODE - skipping system modifications"
    else
        install_system_packages
        setup_hackrf_permissions
    fi
    
    install_python_packages
    detect_hardware
    create_config
    
    if verify_installation; then
        success "Installation completed successfully!"
        print_usage
        exit 0
    else
        error "Installation failed. Check $LOG_FILE for details."
        exit 1
    fi
}

# Run main function
main "$@"