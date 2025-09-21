#!/usr/bin/env python3
"""
One-command installation and system setup for Ursine Capture.
"""

import os
import sys
import subprocess
import logging
import platform
import glob
from datetime import datetime
from pathlib import Path
from utils import setup_logging, run_command, check_process_running
from config import Config


logger = logging.getLogger(__name__)


class UrsineInstaller:
    """Handles installation and setup of Ursine Capture system."""
    
    def __init__(self):
        self.config = Config()
        self.detected_hardware = {}
        self.system_info = self._detect_system()
        
    def _detect_system(self) -> dict:
        """Detect system information and capabilities."""
        logger.info("Detecting system information...")
        
        system_info = {
            "os": platform.system(),
            "distribution": "",
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "has_apt": False,
            "has_yum": False,
            "has_systemd": False
        }
        
        # Detect Linux distribution
        if system_info["os"] == "Linux":
            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("ID="):
                            system_info["distribution"] = line.split("=")[1].strip().strip('"')
                            break
            except FileNotFoundError:
                pass
            
            # Check package managers
            system_info["has_apt"] = os.path.exists("/usr/bin/apt-get")
            system_info["has_yum"] = os.path.exists("/usr/bin/yum")
            system_info["has_systemd"] = os.path.exists("/bin/systemctl")
        
        logger.info(f"Detected system: {system_info['os']} {system_info['distribution']} {system_info['architecture']}")
        return system_info
    
    def detect_hardware(self) -> dict:
        """Detect connected hardware devices."""
        logger.info("Detecting hardware...")
        
        hardware = {
            "hackrf_detected": False,
            "hackrf_info": "",
            "meshtastic_ports": [],
            "usb_devices": []
        }
        
        # Detect HackRF
        try:
            success, stdout, stderr = run_command(["hackrf_info"], timeout=10)
            if success and "Found HackRF" in stdout:
                hardware["hackrf_detected"] = True
                hardware["hackrf_info"] = stdout.strip()
                logger.info("✓ HackRF One detected")
            else:
                logger.info("✗ HackRF One not detected")
        except Exception as e:
            logger.debug(f"HackRF detection error: {e}")
        
        # Detect potential Meshtastic devices (USB serial ports)
        try:
            # Common USB serial device patterns
            usb_patterns = [
                "/dev/ttyUSB*",
                "/dev/ttyACM*", 
                "/dev/cu.usbserial*",  # macOS
                "/dev/cu.usbmodem*"    # macOS
            ]
            
            for pattern in usb_patterns:
                devices = glob.glob(pattern)
                for device in devices:
                    if os.path.exists(device):
                        hardware["meshtastic_ports"].append(device)
                        logger.info(f"Found USB serial device: {device}")
            
            if hardware["meshtastic_ports"]:
                logger.info(f"✓ Found {len(hardware['meshtastic_ports'])} potential Meshtastic device(s)")
            else:
                logger.info("✗ No USB serial devices detected")
                
        except Exception as e:
            logger.debug(f"USB device detection error: {e}")
        
        # Get USB device list for reference
        try:
            success, stdout, stderr = run_command(["lsusb"], timeout=5)
            if success:
                hardware["usb_devices"] = [line.strip() for line in stdout.split('\n') if line.strip()]
        except Exception:
            pass  # lsusb may not be available on all systems
        
        self.detected_hardware = hardware
        return hardware
    
    def install_dependencies(self) -> bool:
        """Install Python packages and system dependencies."""
        logger.info("Installing dependencies...")
        
        # System packages needed
        system_packages = []
        if self.system_info["has_apt"]:
            system_packages = [
                "python3-pip",
                "python3-dev", 
                "build-essential",
                "libusb-1.0-0-dev",
                "pkg-config"
            ]
        elif self.system_info["has_yum"]:
            system_packages = [
                "python3-pip",
                "python3-devel",
                "gcc",
                "libusb1-devel",
                "pkgconfig"
            ]
        
        # Install system packages
        if system_packages:
            logger.info("Installing system packages...")
            try:
                if self.system_info["has_apt"]:
                    success, stdout, stderr = run_command([
                        "sudo", "apt-get", "update"
                    ], timeout=60)
                    if not success:
                        logger.warning("Could not update package list")
                    
                    success, stdout, stderr = run_command([
                        "sudo", "apt-get", "install", "-y"
                    ] + system_packages, timeout=300)
                    
                elif self.system_info["has_yum"]:
                    success, stdout, stderr = run_command([
                        "sudo", "yum", "install", "-y"
                    ] + system_packages, timeout=300)
                
                if not success:
                    logger.warning(f"Some system packages may not have installed: {stderr}")
                else:
                    logger.info("System packages installed successfully")
                    
            except Exception as e:
                logger.warning(f"Error installing system packages: {e}")
        
        # Python packages
        python_packages = [
            "pyModeS>=2.13.0",
            "psutil>=5.8.0", 
            "pyserial>=3.5",
            "meshtastic>=2.0.0",
            "numpy>=1.20.0"  # Required by pyModeS
        ]
        
        try:
            # Upgrade pip first
            logger.info("Upgrading pip...")
            success, stdout, stderr = run_command([
                sys.executable, "-m", "pip", "install", "--upgrade", "pip"
            ], timeout=60)
            if not success:
                logger.warning("Could not upgrade pip")
            
            # Install packages
            for package in python_packages:
                logger.info(f"Installing Python package: {package}")
                success, stdout, stderr = run_command([
                    sys.executable, "-m", "pip", "install", package
                ], timeout=120)
                if not success:
                    logger.error(f"Failed to install {package}: {stderr}")
                    # Try without version constraint
                    base_package = package.split(">=")[0]
                    logger.info(f"Retrying without version constraint: {base_package}")
                    success, stdout, stderr = run_command([
                        sys.executable, "-m", "pip", "install", base_package
                    ], timeout=120)
                    if not success:
                        logger.error(f"Failed to install {base_package}: {stderr}")
                        return False
                    
            logger.info("Python dependencies installed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error installing dependencies: {e}")
            return False
    
    def setup_dump1090(self) -> bool:
        """Configure dump1090-fa installation."""
        logger.info("Setting up dump1090-fa...")
        
        try:
            # Check if dump1090-fa is already installed
            success, stdout, stderr = run_command(["which", "dump1090-fa"], timeout=10)
            if success:
                logger.info("✓ dump1090-fa already installed")
                # Test that it works
                success, stdout, stderr = run_command(["dump1090-fa", "--help"], timeout=10)
                if success:
                    logger.info("✓ dump1090-fa is functional")
                    return True
                else:
                    logger.warning("dump1090-fa found but not functional, reinstalling...")
            
            # Install dump1090-fa based on system
            if self.system_info["has_apt"]:
                logger.info("Installing dump1090-fa via apt...")
                
                # Add FlightAware repository for latest version
                success, stdout, stderr = run_command([
                    "sudo", "apt-get", "update"
                ], timeout=60)
                if not success:
                    logger.warning("Could not update package list")
                
                # Try to install dump1090-fa
                success, stdout, stderr = run_command([
                    "sudo", "apt-get", "install", "-y", "dump1090-fa"
                ], timeout=300)
                
                if not success:
                    logger.warning("Standard dump1090-fa installation failed, trying alternatives...")
                    # Try dump1090-mutability as fallback
                    success, stdout, stderr = run_command([
                        "sudo", "apt-get", "install", "-y", "dump1090-mutability"
                    ], timeout=300)
                    
                    if not success:
                        logger.error(f"Failed to install any dump1090 variant: {stderr}")
                        return False
                    else:
                        logger.info("✓ dump1090-mutability installed as fallback")
                        return True
                
            elif self.system_info["has_yum"]:
                logger.info("Installing dump1090 via yum...")
                # For RHEL/CentOS, we may need to build from source or use EPEL
                success, stdout, stderr = run_command([
                    "sudo", "yum", "install", "-y", "epel-release"
                ], timeout=60)
                
                success, stdout, stderr = run_command([
                    "sudo", "yum", "install", "-y", "dump1090"
                ], timeout=300)
                
                if not success:
                    logger.warning("Package manager installation failed, manual installation may be required")
                    return False
            else:
                logger.error("Unsupported package manager for automatic dump1090 installation")
                return False
                
            # Verify installation
            success, stdout, stderr = run_command(["which", "dump1090-fa"], timeout=10)
            if not success:
                success, stdout, stderr = run_command(["which", "dump1090"], timeout=10)
                
            if success:
                logger.info("✓ dump1090 installed successfully")
                return True
            else:
                logger.error("dump1090 installation verification failed")
                return False
                
        except Exception as e:
            logger.error(f"Error setting up dump1090: {e}")
            return False
    
    def setup_hackrf(self) -> bool:
        """Configure HackRF drivers and permissions."""
        logger.info("Setting up HackRF...")
        
        try:
            # Install HackRF tools based on system
            if self.system_info["has_apt"]:
                logger.info("Installing HackRF tools via apt...")
                success, stdout, stderr = run_command([
                    "sudo", "apt-get", "install", "-y", "hackrf", "libhackrf-dev", "libhackrf0"
                ], timeout=300)
                if not success:
                    logger.warning(f"Could not install HackRF tools: {stderr}")
                    
            elif self.system_info["has_yum"]:
                logger.info("Installing HackRF tools via yum...")
                success, stdout, stderr = run_command([
                    "sudo", "yum", "install", "-y", "hackrf", "hackrf-devel"
                ], timeout=300)
                if not success:
                    logger.warning(f"Could not install HackRF tools: {stderr}")
            
            # Set up udev rules for HackRF access
            udev_rules = """# HackRF One
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="6089", GROUP="plugdev", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="604b", GROUP="plugdev", MODE="0666"
SUBSYSTEM=="usb", ATTRS{idVendor}=="1d50", ATTRS{idProduct}=="cc15", GROUP="plugdev", MODE="0666"
"""
            
            try:
                with open("/tmp/hackrf.rules", "w") as f:
                    f.write(udev_rules)
                
                success, stdout, stderr = run_command([
                    "sudo", "cp", "/tmp/hackrf.rules", "/etc/udev/rules.d/52-hackrf.rules"
                ])
                if success:
                    logger.info("✓ HackRF udev rules installed")
                    
                    # Reload udev rules
                    success, stdout, stderr = run_command([
                        "sudo", "udevadm", "control", "--reload-rules"
                    ])
                    success, stdout, stderr = run_command([
                        "sudo", "udevadm", "trigger"
                    ])
                else:
                    logger.warning("Could not install udev rules")
                    
                # Clean up temp file
                os.remove("/tmp/hackrf.rules")
                
            except Exception as e:
                logger.warning(f"Error setting up udev rules: {e}")
            
            # Add user to plugdev group for USB access
            username = os.getenv("USER")
            if username:
                success, stdout, stderr = run_command([
                    "sudo", "usermod", "-a", "-G", "plugdev", username
                ])
                if success:
                    logger.info(f"✓ Added {username} to plugdev group")
                    logger.info("Note: You may need to log out and back in for group changes to take effect")
                else:
                    logger.warning("Could not add user to plugdev group")
            
            # Test HackRF detection
            hardware = self.detect_hardware()
            if hardware["hackrf_detected"]:
                logger.info("✓ HackRF One detected and accessible")
            else:
                logger.warning("✗ HackRF One not detected (may need to be connected or permissions applied)")
                    
            logger.info("HackRF setup completed")
            return True
            
        except Exception as e:
            logger.error(f"Error setting up HackRF: {e}")
            return False
    
    def create_config(self) -> bool:
        """Generate initial configuration file with hardware detection."""
        logger.info("Creating configuration file with hardware detection...")
        
        try:
            # Detect hardware first
            hardware = self.detect_hardware()
            
            # Load default config (will create file if not exists)
            config_data = self.config.load()
            
            # Update configuration based on detected hardware
            if hardware["meshtastic_ports"]:
                # Use the first detected USB serial port
                config_data["meshtastic"]["port"] = hardware["meshtastic_ports"][0]
                logger.info(f"✓ Set Meshtastic port to: {hardware['meshtastic_ports'][0]}")
            else:
                logger.info("No USB serial devices detected, using default Meshtastic port")
            
            # Set dump1090 path based on what's available
            dump1090_paths = [
                "/usr/bin/dump1090-fa",
                "/usr/bin/dump1090",
                "/usr/local/bin/dump1090-fa",
                "/usr/local/bin/dump1090"
            ]
            
            for path in dump1090_paths:
                if os.path.exists(path):
                    config_data["receiver"]["dump1090_path"] = path
                    logger.info(f"✓ Set dump1090 path to: {path}")
                    break
            else:
                logger.warning("dump1090 not found in standard locations, using default path")
            
            # Add hardware detection results as comments in config
            config_data["_hardware_detection"] = {
                "hackrf_detected": hardware["hackrf_detected"],
                "meshtastic_ports_found": hardware["meshtastic_ports"],
                "detection_timestamp": str(datetime.now()),
                "system_info": self.system_info
            }
            
            # Save the updated configuration
            self.config.save(config_data)
            
            # Validate the configuration
            if self.config.validate(config_data):
                logger.info("✓ Configuration file created successfully with hardware detection")
                return True
            else:
                logger.error("Generated configuration is invalid")
                return False
                
        except Exception as e:
            logger.error(f"Error creating configuration: {e}")
            return False
    
    def verify_installation(self) -> bool:
        """Test all components work."""
        logger.info("Verifying installation...")
        
        verification_results = {
            "python_imports": False,
            "dump1090": False,
            "hackrf_tools": False,
            "hackrf_device": False,
            "meshtastic_ports": False,
            "configuration": False,
            "core_files": False
        }
        
        try:
            # Check Python imports
            test_imports = [
                ("pyModeS", "pyModeS"),
                ("psutil", "psutil"),
                ("serial", "pyserial"),
                ("meshtastic", "meshtastic"),
                ("numpy", "numpy")
            ]
            
            import_success = True
            for module_name, package_name in test_imports:
                try:
                    __import__(module_name)
                    logger.info(f"✓ {package_name} import successful")
                except ImportError as e:
                    logger.error(f"✗ {package_name} import failed: {e}")
                    import_success = False
            
            verification_results["python_imports"] = import_success
            
            # Check dump1090 variants
            dump1090_variants = ["dump1090-fa", "dump1090"]
            dump1090_working = False
            
            for variant in dump1090_variants:
                success, stdout, stderr = run_command([variant, "--help"], timeout=10)
                if success:
                    logger.info(f"✓ {variant} is working")
                    dump1090_working = True
                    break
            
            if not dump1090_working:
                logger.error("✗ No working dump1090 variant found")
            
            verification_results["dump1090"] = dump1090_working
                
            # Check HackRF tools
            success, stdout, stderr = run_command(["hackrf_info"], timeout=10)
            if success:
                logger.info("✓ HackRF tools are working")
                verification_results["hackrf_tools"] = True
                
                # Check if HackRF device is actually connected
                if "Found HackRF" in stdout:
                    logger.info("✓ HackRF device detected and accessible")
                    verification_results["hackrf_device"] = True
                else:
                    logger.warning("✗ HackRF tools work but no device detected")
            else:
                logger.error("✗ HackRF tools test failed")
            
            # Check for USB serial devices (potential Meshtastic)
            hardware = self.detect_hardware()
            if hardware["meshtastic_ports"]:
                logger.info(f"✓ Found {len(hardware['meshtastic_ports'])} USB serial device(s)")
                verification_results["meshtastic_ports"] = True
            else:
                logger.warning("✗ No USB serial devices found for Meshtastic")
            
            # Check configuration
            config_data = self.config.load()
            if self.config.validate(config_data):
                logger.info("✓ Configuration is valid")
                verification_results["configuration"] = True
            else:
                logger.error("✗ Configuration validation failed")
            
            # Check core files exist
            core_files = [
                "receiver.py",
                "dashboard.py", 
                "config.py",
                "aircraft.py",
                "utils.py",
                "config.json"
            ]
            
            files_exist = True
            for filename in core_files:
                if os.path.exists(filename):
                    logger.info(f"✓ {filename} exists")
                else:
                    logger.error(f"✗ {filename} missing")
                    files_exist = False
            
            verification_results["core_files"] = files_exist
            
            # Summary
            logger.info("\n" + "="*50)
            logger.info("INSTALLATION VERIFICATION SUMMARY")
            logger.info("="*50)
            
            total_checks = len(verification_results)
            passed_checks = sum(verification_results.values())
            
            for check, result in verification_results.items():
                status = "✓ PASS" if result else "✗ FAIL"
                logger.info(f"{check.replace('_', ' ').title()}: {status}")
            
            logger.info(f"\nOverall: {passed_checks}/{total_checks} checks passed")
            
            # Determine if installation is successful
            critical_checks = ["python_imports", "configuration", "core_files"]
            critical_passed = all(verification_results[check] for check in critical_checks)
            
            if critical_passed:
                logger.info("✓ Installation verification PASSED (critical components working)")
                if not verification_results["hackrf_device"]:
                    logger.info("Note: Connect HackRF One device for full functionality")
                if not verification_results["meshtastic_ports"]:
                    logger.info("Note: Connect Meshtastic device for alert functionality")
                return True
            else:
                logger.error("✗ Installation verification FAILED (critical components missing)")
                return False
                
        except Exception as e:
            logger.error(f"Error during verification: {e}")
            return False
    
    def install(self, test_mode: bool = False) -> bool:
        """Run complete installation process."""
        logger.info("="*60)
        logger.info("URSINE CAPTURE INSTALLATION")
        logger.info("="*60)
        logger.info(f"System: {self.system_info['os']} {self.system_info['distribution']}")
        logger.info(f"Architecture: {self.system_info['architecture']}")
        logger.info(f"Python: {self.system_info['python_version']}")
        logger.info("="*60)
        
        try:
            steps = [
                ("Detecting hardware", self.detect_hardware),
                ("Installing dependencies", self.install_dependencies),
                ("Setting up dump1090", self.setup_dump1090),
                ("Setting up HackRF", self.setup_hackrf),
                ("Creating configuration", self.create_config),
                ("Verifying installation", self.verify_installation)
            ]
            
            if test_mode:
                logger.info("Running in TEST MODE - skipping system modifications")
                steps = [
                    ("Detecting hardware", self.detect_hardware),
                    ("Creating configuration", self.create_config),
                    ("Verifying installation", self.verify_installation)
                ]
            
            for i, (step_name, step_func) in enumerate(steps, 1):
                logger.info(f"\n[{i}/{len(steps)}] {step_name}...")
                logger.info("-" * 40)
                
                if step_func == self.detect_hardware:
                    # Hardware detection returns dict, not bool
                    result = step_func()
                    success = True  # Detection always "succeeds"
                else:
                    success = step_func()
                
                if not success:
                    logger.error(f"Installation failed at step: {step_name}")
                    self._print_troubleshooting_info()
                    return False
                    
            logger.info("\n" + "="*60)
            logger.info("INSTALLATION COMPLETED SUCCESSFULLY!")
            logger.info("="*60)
            self._print_usage_instructions()
            
            return True
            
        except KeyboardInterrupt:
            logger.info("\nInstallation cancelled by user")
            return False
        except Exception as e:
            logger.error(f"Installation failed with error: {e}")
            self._print_troubleshooting_info()
            return False
    
    def _print_usage_instructions(self) -> None:
        """Print usage instructions after successful installation."""
        logger.info("\nTo start the Ursine Capture system:")
        logger.info("  1. Start the receiver (in one terminal):")
        logger.info("     python3 receiver.py")
        logger.info("")
        logger.info("  2. Start the dashboard (in another terminal):")
        logger.info("     python3 dashboard.py")
        logger.info("")
        logger.info("Configuration file: config.json")
        logger.info("Log files: ursine-capture.log, ursine-install.log")
        logger.info("")
        
        # Hardware-specific notes
        if not self.detected_hardware.get("hackrf_detected", False):
            logger.info("NOTE: Connect your HackRF One device before starting")
        
        if not self.detected_hardware.get("meshtastic_ports", []):
            logger.info("NOTE: Connect your Meshtastic device for alert functionality")
        
        logger.info("For troubleshooting, see the log files or run with --test-mode")
    
    def _print_troubleshooting_info(self) -> None:
        """Print troubleshooting information on installation failure."""
        logger.info("\n" + "="*60)
        logger.info("TROUBLESHOOTING INFORMATION")
        logger.info("="*60)
        logger.info("If installation failed, try:")
        logger.info("1. Run with --test-mode to skip system modifications")
        logger.info("2. Check the log file: ursine-install.log")
        logger.info("3. Ensure you have sudo privileges for system packages")
        logger.info("4. Make sure your system is up to date")
        logger.info("")
        logger.info("Manual installation steps:")
        logger.info("- Install Python packages: pip3 install pyModeS psutil pyserial meshtastic")
        logger.info("- Install dump1090-fa: sudo apt-get install dump1090-fa")
        logger.info("- Install HackRF tools: sudo apt-get install hackrf")
        logger.info("- Add user to plugdev group: sudo usermod -a -G plugdev $USER")
        logger.info("")
        logger.info("For support, check the README.md file or project documentation")
    
    def test_installation(self) -> bool:
        """Run installation tests without making system changes."""
        logger.info("Running installation tests...")
        return self.install(test_mode=True)


def main():
    """Main installation entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Ursine Capture Installation Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 installer.py                    # Full installation
  python3 installer.py --test-mode        # Test without system changes
  python3 installer.py --verify-only      # Only verify existing installation
  python3 installer.py --detect-hardware  # Only detect hardware
        """
    )
    
    parser.add_argument(
        "--test-mode", 
        action="store_true",
        help="Run in test mode (skip system modifications)"
    )
    
    parser.add_argument(
        "--verify-only",
        action="store_true", 
        help="Only verify existing installation"
    )
    
    parser.add_argument(
        "--detect-hardware",
        action="store_true",
        help="Only detect and report hardware"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging("ursine-install.log", level=log_level)
    
    installer = UrsineInstaller()
    
    try:
        if args.detect_hardware:
            logger.info("Hardware Detection Mode")
            hardware = installer.detect_hardware()
            
            print("\nHardware Detection Results:")
            print("=" * 40)
            print(f"HackRF Detected: {'Yes' if hardware['hackrf_detected'] else 'No'}")
            if hardware['hackrf_info']:
                print(f"HackRF Info: {hardware['hackrf_info']}")
            
            print(f"USB Serial Ports: {len(hardware['meshtastic_ports'])}")
            for port in hardware['meshtastic_ports']:
                print(f"  - {port}")
            
            if hardware['usb_devices']:
                print(f"USB Devices: {len(hardware['usb_devices'])}")
                for device in hardware['usb_devices'][:5]:  # Show first 5
                    print(f"  - {device}")
                if len(hardware['usb_devices']) > 5:
                    print(f"  ... and {len(hardware['usb_devices']) - 5} more")
            
            success = True
            
        elif args.verify_only:
            logger.info("Verification Only Mode")
            success = installer.verify_installation()
            
        else:
            success = installer.install(test_mode=args.test_mode)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        logger.info("Installation cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()