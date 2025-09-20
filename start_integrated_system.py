#!/usr/bin/env python3
"""
Startup Script for Integrated Ursine Explorer ADS-B Receiver
Handles system startup, monitoring, and graceful shutdown
"""

import os
import sys
import time
import signal
import subprocess
import threading
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import argparse

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('startup.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SystemManager:
    """Manages the integrated ADS-B system startup and monitoring"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        
        # System status
        self.status = {
            'start_time': None,
            'receiver_running': False,
            'dashboard_running': False,
            'dump1090_running': False,
            'last_health_check': None,
            'restart_count': 0,
            'error_count': 0
        }
    
    def load_config(self) -> dict:
        """Load system configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file {self.config_path} not found, using defaults")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {}
    
    def check_dependencies(self) -> bool:
        """Check if all required dependencies are available"""
        logger.info("Checking system dependencies...")
        
        # Check Python modules
        required_modules = [
            'pyModeS', 'numpy', 'requests', 'serial', 'curses'
        ]
        
        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
                logger.debug(f"✓ {module} available")
            except ImportError:
                missing_modules.append(module)
                logger.error(f"✗ {module} missing")
        
        if missing_modules:
            logger.error(f"Missing required modules: {', '.join(missing_modules)}")
            logger.error("Install with: pip install " + " ".join(missing_modules))
            return False
        
        # Check required files
        required_files = [
            'adsb_receiver_integrated.py',
            'adsb_dashboard.py',
            'pymodes_integration/__init__.py'
        ]
        
        missing_files = []
        for file in required_files:
            if not os.path.exists(file):
                missing_files.append(file)
                logger.error(f"✗ {file} missing")
            else:
                logger.debug(f"✓ {file} available")
        
        if missing_files:
            logger.error(f"Missing required files: {', '.join(missing_files)}")
            return False
        
        # Check dump1090 if configured
        dump1090_path = self.config.get('dump1090_path', '/usr/bin/dump1090-fa')
        if os.path.exists(dump1090_path):
            logger.info(f"✓ dump1090 found at {dump1090_path}")
        else:
            logger.warning(f"dump1090 not found at {dump1090_path}")
            logger.warning("dump1090 functionality may be limited")
        
        logger.info("Dependency check completed")
        return True
    
    def start_receiver(self) -> bool:
        """Start the integrated ADS-B receiver"""
        logger.info("Starting integrated ADS-B receiver...")
        
        try:
            cmd = [sys.executable, 'adsb_receiver_integrated.py']
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid  # Create new process group
            )
            
            self.processes['receiver'] = process
            self.status['receiver_running'] = True
            
            logger.info(f"ADS-B receiver started (PID: {process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start ADS-B receiver: {e}")
            return False
    
    def start_dashboard(self, auto_start: bool = False) -> bool:
        """Start the dashboard (optional)"""
        if not auto_start:
            return True  # Skip if not auto-starting
        
        logger.info("Starting dashboard...")
        
        try:
            cmd = [sys.executable, 'adsb_dashboard.py']
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            self.processes['dashboard'] = process
            self.status['dashboard_running'] = True
            
            logger.info(f"Dashboard started (PID: {process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start dashboard: {e}")
            return False
    
    def start_dump1090(self) -> bool:
        """Start dump1090 if configured"""
        if not self.config.get('start_dump1090', False):
            logger.info("dump1090 auto-start disabled in config")
            return True
        
        logger.info("Starting dump1090...")
        
        try:
            dump1090_path = self.config.get('dump1090_path', '/usr/bin/dump1090-fa')
            
            if not os.path.exists(dump1090_path):
                logger.error(f"dump1090 not found at {dump1090_path}")
                return False
            
            # Build dump1090 command
            cmd = [
                dump1090_path,
                '--device-type', 'hackrf',
                '--freq', str(self.config.get('frequency', 1090000000)),
                '--net',
                '--net-bo-port', str(self.config.get('dump1090_port', 30005)),
                '--net-sbs-port', '30003',
                '--write-json', '/tmp/adsb_json',
                '--write-json-every', '1'
            ]
            
            # Add gain settings
            if self.config.get('enable_hackrf_amp', True):
                cmd.append('--enable-amp')
            
            lna_gain = self.config.get('lna_gain', 40)
            vga_gain = self.config.get('vga_gain', 20)
            cmd.extend(['--lna-gain', str(lna_gain)])
            cmd.extend(['--vga-gain', str(vga_gain)])
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            self.processes['dump1090'] = process
            self.status['dump1090_running'] = True
            
            logger.info(f"dump1090 started (PID: {process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start dump1090: {e}")
            return False
    
    def stop_process(self, name: str) -> bool:
        """Stop a specific process"""
        if name not in self.processes:
            return True
        
        process = self.processes[name]
        logger.info(f"Stopping {name} (PID: {process.pid})...")
        
        try:
            # Send SIGTERM to process group
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            
            # Wait for graceful shutdown
            try:
                process.wait(timeout=10)
                logger.info(f"{name} stopped gracefully")
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't stop gracefully
                logger.warning(f"Force killing {name}")
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                process.wait()
            
            del self.processes[name]
            self.status[f'{name}_running'] = False
            return True
            
        except Exception as e:
            logger.error(f"Error stopping {name}: {e}")
            return False
    
    def stop_all(self):
        """Stop all processes"""
        logger.info("Stopping all processes...")
        
        # Stop in reverse order
        for name in ['dashboard', 'receiver', 'dump1090']:
            self.stop_process(name)
        
        self.running = False
        logger.info("All processes stopped")
    
    def check_process_health(self, name: str) -> bool:
        """Check if a process is still running and healthy"""
        if name not in self.processes:
            return False
        
        process = self.processes[name]
        
        # Check if process is still running
        if process.poll() is not None:
            logger.warning(f"Process {name} has terminated (exit code: {process.returncode})")
            del self.processes[name]
            self.status[f'{name}_running'] = False
            return False
        
        return True
    
    def restart_process(self, name: str) -> bool:
        """Restart a specific process"""
        logger.info(f"Restarting {name}...")
        
        # Stop the process
        self.stop_process(name)
        time.sleep(2)  # Brief pause
        
        # Start it again
        if name == 'receiver':
            return self.start_receiver()
        elif name == 'dashboard':
            return self.start_dashboard(True)
        elif name == 'dump1090':
            return self.start_dump1090()
        
        return False
    
    def monitor_system(self):
        """Monitor system health and restart processes if needed"""
        logger.info("System monitoring started")
        
        while self.running:
            try:
                time.sleep(30)  # Check every 30 seconds
                
                if not self.running:
                    break
                
                self.status['last_health_check'] = datetime.now()
                
                # Check each process
                for name in list(self.processes.keys()):
                    if not self.check_process_health(name):
                        logger.warning(f"Process {name} is not healthy, attempting restart...")
                        
                        if self.restart_process(name):
                            logger.info(f"Successfully restarted {name}")
                            self.status['restart_count'] += 1
                        else:
                            logger.error(f"Failed to restart {name}")
                            self.status['error_count'] += 1
                
                # Log status periodically
                if self.status['restart_count'] > 0 or self.status['error_count'] > 0:
                    logger.info(f"System status: {self.status['restart_count']} restarts, {self.status['error_count']} errors")
                
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                self.status['error_count'] += 1
                time.sleep(5)  # Brief pause on error
        
        logger.info("System monitoring stopped")
    
    def start_system(self, start_dashboard: bool = False) -> bool:
        """Start the complete system"""
        logger.info("Starting Ursine Explorer ADS-B System")
        logger.info("=" * 50)
        
        self.status['start_time'] = datetime.now()
        self.running = True
        
        # Check dependencies first
        if not self.check_dependencies():
            logger.error("Dependency check failed, cannot start system")
            return False
        
        # Start components in order
        components = [
            ("dump1090", self.start_dump1090),
            ("receiver", self.start_receiver),
            ("dashboard", lambda: self.start_dashboard(start_dashboard))
        ]
        
        for name, start_func in components:
            if not start_func():
                logger.error(f"Failed to start {name}, aborting system startup")
                self.stop_all()
                return False
            time.sleep(2)  # Brief pause between starts
        
        # Start monitoring
        self.monitor_thread = threading.Thread(
            target=self.monitor_system,
            name="SystemMonitor",
            daemon=True
        )
        self.monitor_thread.start()
        
        logger.info("=" * 50)
        logger.info("✅ System started successfully!")
        logger.info("")
        logger.info("System Status:")
        logger.info(f"  Receiver: {'✓' if self.status['receiver_running'] else '✗'}")
        logger.info(f"  Dashboard: {'✓' if self.status['dashboard_running'] else '✗'}")
        logger.info(f"  dump1090: {'✓' if self.status['dump1090_running'] else '✗'}")
        logger.info("")
        logger.info("Access points:")
        logger.info("  HTTP API: http://localhost:8080/data/aircraft.json")
        logger.info("  Control: telnet localhost 8081")
        logger.info("  Dashboard: Run 'python3 adsb_dashboard.py' in another terminal")
        logger.info("")
        logger.info("Press Ctrl+C to stop the system")
        
        return True
    
    def get_status(self) -> dict:
        """Get current system status"""
        return {
            **self.status,
            'uptime_seconds': (datetime.now() - self.status['start_time']).total_seconds() if self.status['start_time'] else 0,
            'processes': {name: proc.pid for name, proc in self.processes.items()}
        }
    
    def print_status(self):
        """Print current system status"""
        status = self.get_status()
        
        print("\nSystem Status:")
        print("-" * 30)
        print(f"Running: {self.running}")
        print(f"Uptime: {status['uptime_seconds']:.0f} seconds")
        print(f"Receiver: {'✓' if status['receiver_running'] else '✗'}")
        print(f"Dashboard: {'✓' if status['dashboard_running'] else '✗'}")
        print(f"dump1090: {'✓' if status['dump1090_running'] else '✗'}")
        print(f"Restarts: {status['restart_count']}")
        print(f"Errors: {status['error_count']}")
        
        if status['processes']:
            print("\nProcess PIDs:")
            for name, pid in status['processes'].items():
                print(f"  {name}: {pid}")


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {signum}, shutting down system...")
    if hasattr(signal_handler, 'manager'):
        signal_handler.manager.stop_all()
    sys.exit(0)


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Ursine Explorer ADS-B System Manager')
    parser.add_argument('--config', '-c', default='config.json', help='Configuration file path')
    parser.add_argument('--dashboard', '-d', action='store_true', help='Auto-start dashboard')
    parser.add_argument('--status', '-s', action='store_true', help='Show status and exit')
    parser.add_argument('--test', '-t', action='store_true', help='Run system tests')
    
    args = parser.parse_args()
    
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        manager = SystemManager(args.config)
        signal_handler.manager = manager  # Store reference for signal handler
        
        if args.test:
            # Run integration tests
            logger.info("Running system tests...")
            import subprocess
            result = subprocess.run([sys.executable, 'test_integration.py'], 
                                  capture_output=True, text=True)
            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)
            sys.exit(result.returncode)
        
        if args.status:
            # Just show status
            manager.print_status()
            return
        
        # Start the system
        if manager.start_system(start_dashboard=args.dashboard):
            # Keep running until interrupted
            try:
                while manager.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
        else:
            logger.error("Failed to start system")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"System error: {e}")
        raise
    finally:
        if 'manager' in locals():
            manager.stop_all()


if __name__ == "__main__":
    main()