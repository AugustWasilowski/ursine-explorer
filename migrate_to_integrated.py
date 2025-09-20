#!/usr/bin/env python3
"""
Migration Script for Ursine Explorer ADS-B Receiver
Migrates from legacy system to integrated pyModeS version
"""

import json
import os
import shutil
import sys
from datetime import datetime
from typing import Dict, Any, List
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ADSBMigration:
    """Handles migration from legacy to integrated system"""
    
    def __init__(self):
        self.backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.migration_log = []
        
    def log_step(self, message: str, success: bool = True):
        """Log migration step"""
        status = "SUCCESS" if success else "FAILED"
        log_entry = f"[{status}] {message}"
        self.migration_log.append(log_entry)
        
        if success:
            logger.info(message)
        else:
            logger.error(message)
    
    def backup_files(self) -> bool:
        """Create backup of existing files"""
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            
            files_to_backup = [
                'adsb_receiver.py',
                'adsb_dashboard.py', 
                'config.json',
                'adsb_receiver.log',
                'alerts.log'
            ]
            
            backed_up = []
            for file in files_to_backup:
                if os.path.exists(file):
                    shutil.copy2(file, self.backup_dir)
                    backed_up.append(file)
            
            self.log_step(f"Backed up {len(backed_up)} files to {self.backup_dir}")
            return True
            
        except Exception as e:
            self.log_step(f"Backup failed: {e}", False)
            return False
    
    def migrate_config(self) -> bool:
        """Migrate configuration to new format"""
        try:
            # Load existing config
            if not os.path.exists('config.json'):
                self.log_step("No existing config.json found, will create default")
                return self.create_default_config()
            
            with open('config.json', 'r') as f:
                old_config = json.load(f)
            
            # Create new config structure
            new_config = self.convert_config(old_config)
            
            # Write new config
            with open('config.json', 'w') as f:
                json.dump(new_config, f, indent=4)
            
            self.log_step("Configuration migrated successfully")
            return True
            
        except Exception as e:
            self.log_step(f"Config migration failed: {e}", False)
            return False
    
    def convert_config(self, old_config: Dict[str, Any]) -> Dict[str, Any]:
        """Convert old config format to new integrated format"""
        
        # Start with new structure
        new_config = {
            # Preserve existing settings
            "dump1090_host": old_config.get("dump1090_host", "localhost"),
            "dump1090_port": old_config.get("dump1090_port", 30005),
            "receiver_control_port": old_config.get("receiver_control_port", 8081),
            "frequency": old_config.get("frequency", 1090000000),
            "lna_gain": old_config.get("lna_gain", 40),
            "vga_gain": old_config.get("vga_gain", 20),
            "enable_hackrf_amp": old_config.get("enable_hackrf_amp", True),
            "target_icao_codes": old_config.get("target_icao_codes", []),
            "meshtastic_port": old_config.get("meshtastic_port"),
            "meshtastic_baud": old_config.get("meshtastic_baud", 115200),
            "log_alerts": old_config.get("log_alerts", True),
            "alert_log_file": old_config.get("alert_log_file", "alerts.log"),
            "alert_interval_sec": old_config.get("alert_interval_sec", 300),
            "dump1090_path": old_config.get("dump1090_path", "/usr/bin/dump1090-fa"),
            "watchdog_timeout_sec": old_config.get("watchdog_timeout_sec", 60),
            "poll_interval_sec": old_config.get("poll_interval_sec", 1),
            
            # Add new pyModeS configuration
            "pymodes": {
                "enabled": True,
                "reference_position": {
                    "latitude": old_config.get("reference_latitude"),
                    "longitude": old_config.get("reference_longitude")
                },
                "cpr_settings": {
                    "global_position_timeout": 10,
                    "local_position_range_nm": 180,
                    "surface_position_timeout": 25
                },
                "message_validation": {
                    "enable_crc_check": True,
                    "enable_format_validation": True,
                    "enable_range_validation": True,
                    "max_message_age_sec": 60
                },
                "decoder_settings": {
                    "supported_message_types": ["DF4", "DF5", "DF17", "DF18", "DF20", "DF21"],
                    "enable_enhanced_decoding": True,
                    "decode_comm_b": True,
                    "decode_bds": True
                }
            },
            
            # Configure message sources
            "message_sources": [
                {
                    "name": "dump1090_primary",
                    "type": "dump1090",
                    "enabled": True,
                    "host": old_config.get("dump1090_host", "localhost"),
                    "port": old_config.get("dump1090_port", 30005),
                    "format": "beast",
                    "reconnect_interval_sec": 5,
                    "max_reconnect_attempts": 10,
                    "buffer_size": 8192
                }
            ],
            
            # Aircraft tracking settings
            "aircraft_tracking": {
                "aircraft_timeout_sec": old_config.get("aircraft_timeout_sec", 300),
                "position_timeout_sec": 60,
                "cleanup_interval_sec": 30,
                "max_aircraft_count": 10000,
                "enable_data_validation": True,
                "conflict_resolution": "newest_wins",
                "track_surface_vehicles": True,
                "minimum_message_count": 2
            },
            
            # Watchlist configuration
            "watchlist": {
                "enabled": len(old_config.get("target_icao_codes", [])) > 0,
                "sources": ["target_icao_codes"],
                "check_icao": True,
                "check_callsign": True,
                "case_sensitive": False,
                "pattern_matching": False,
                "alert_throttling": {
                    "enabled": True,
                    "min_interval_sec": old_config.get("alert_interval_sec", 300),
                    "max_alerts_per_hour": 10,
                    "escalation_enabled": False
                }
            },
            
            # Logging configuration
            "logging": {
                "level": "INFO",
                "enable_message_stats": True,
                "enable_aircraft_events": True,
                "enable_connection_events": True,
                "enable_decode_errors": True,
                "stats_interval_sec": 60,
                "log_file": "adsb_receiver.log",
                "max_log_size_mb": 100,
                "backup_count": 5
            },
            
            # Performance settings
            "performance": {
                "message_batch_size": 100,
                "processing_interval_ms": 100,
                "memory_limit_mb": 512,
                "enable_profiling": False,
                "gc_interval_sec": 300
            }
        }
        
        # Preserve any custom settings
        for key, value in old_config.items():
            if key not in new_config:
                new_config[key] = value
                self.log_step(f"Preserved custom setting: {key}")
        
        return new_config
    
    def create_default_config(self) -> bool:
        """Create default configuration file"""
        try:
            default_config = {
                "dump1090_host": "localhost",
                "dump1090_port": 30005,
                "receiver_control_port": 8081,
                "frequency": 1090000000,
                "lna_gain": 40,
                "vga_gain": 20,
                "enable_hackrf_amp": True,
                "target_icao_codes": [],
                "meshtastic_port": None,
                "meshtastic_baud": 115200,
                "log_alerts": True,
                "alert_log_file": "alerts.log",
                "alert_interval_sec": 300,
                "dump1090_path": "/usr/bin/dump1090-fa",
                "watchdog_timeout_sec": 60,
                "poll_interval_sec": 1,
                
                "pymodes": {
                    "enabled": True,
                    "reference_position": {
                        "latitude": None,
                        "longitude": None
                    },
                    "cpr_settings": {
                        "global_position_timeout": 10,
                        "local_position_range_nm": 180,
                        "surface_position_timeout": 25
                    },
                    "message_validation": {
                        "enable_crc_check": True,
                        "enable_format_validation": True,
                        "enable_range_validation": True,
                        "max_message_age_sec": 60
                    },
                    "decoder_settings": {
                        "supported_message_types": ["DF4", "DF5", "DF17", "DF18", "DF20", "DF21"],
                        "enable_enhanced_decoding": True,
                        "decode_comm_b": True,
                        "decode_bds": True
                    }
                },
                
                "message_sources": [
                    {
                        "name": "dump1090_primary",
                        "type": "dump1090",
                        "enabled": True,
                        "host": "localhost",
                        "port": 30005,
                        "format": "beast",
                        "reconnect_interval_sec": 5,
                        "max_reconnect_attempts": 10,
                        "buffer_size": 8192
                    }
                ],
                
                "aircraft_tracking": {
                    "aircraft_timeout_sec": 300,
                    "position_timeout_sec": 60,
                    "cleanup_interval_sec": 30,
                    "max_aircraft_count": 10000,
                    "enable_data_validation": True,
                    "conflict_resolution": "newest_wins",
                    "track_surface_vehicles": True,
                    "minimum_message_count": 2
                },
                
                "watchlist": {
                    "enabled": False,
                    "sources": ["target_icao_codes"],
                    "check_icao": True,
                    "check_callsign": True,
                    "case_sensitive": False,
                    "pattern_matching": False,
                    "alert_throttling": {
                        "enabled": True,
                        "min_interval_sec": 300,
                        "max_alerts_per_hour": 10,
                        "escalation_enabled": False
                    }
                },
                
                "logging": {
                    "level": "INFO",
                    "enable_message_stats": True,
                    "enable_aircraft_events": True,
                    "enable_connection_events": True,
                    "enable_decode_errors": True,
                    "stats_interval_sec": 60,
                    "log_file": "adsb_receiver.log",
                    "max_log_size_mb": 100,
                    "backup_count": 5
                },
                
                "performance": {
                    "message_batch_size": 100,
                    "processing_interval_ms": 100,
                    "memory_limit_mb": 512,
                    "enable_profiling": False,
                    "gc_interval_sec": 300
                }
            }
            
            with open('config.json', 'w') as f:
                json.dump(default_config, f, indent=4)
            
            self.log_step("Created default configuration file")
            return True
            
        except Exception as e:
            self.log_step(f"Failed to create default config: {e}", False)
            return False
    
    def check_dependencies(self) -> bool:
        """Check if required dependencies are available"""
        try:
            # Check pyModeS
            try:
                import pyModeS
                self.log_step(f"pyModeS version {pyModeS.__version__} found")
            except ImportError:
                self.log_step("pyModeS not found - install with: pip install pyModeS", False)
                return False
            
            # Check other dependencies
            required_modules = ['numpy', 'requests', 'serial']
            missing_modules = []
            
            for module in required_modules:
                try:
                    __import__(module)
                except ImportError:
                    missing_modules.append(module)
            
            if missing_modules:
                self.log_step(f"Missing modules: {', '.join(missing_modules)}", False)
                return False
            
            self.log_step("All required dependencies found")
            return True
            
        except Exception as e:
            self.log_step(f"Dependency check failed: {e}", False)
            return False
    
    def create_startup_script(self) -> bool:
        """Create startup script for integrated system"""
        try:
            startup_script = '''#!/bin/bash
# Ursine Explorer ADS-B Receiver Startup Script (Integrated Version)

# Set working directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Start the integrated receiver
echo "Starting Ursine Explorer ADS-B Receiver (Integrated)..."
python3 adsb_receiver_integrated.py

# Deactivate virtual environment if it was activated
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
fi
'''
            
            with open('start_integrated.sh', 'w') as f:
                f.write(startup_script)
            
            # Make executable
            os.chmod('start_integrated.sh', 0o755)
            
            self.log_step("Created startup script: start_integrated.sh")
            return True
            
        except Exception as e:
            self.log_step(f"Failed to create startup script: {e}", False)
            return False
    
    def create_dashboard_script(self) -> bool:
        """Create dashboard startup script"""
        try:
            dashboard_script = '''#!/bin/bash
# Ursine Explorer Dashboard Startup Script (Compatible with Integrated Version)

# Set working directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Start the dashboard
echo "Starting Ursine Explorer Dashboard..."
python3 adsb_dashboard.py

# Deactivate virtual environment if it was activated
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
fi
'''
            
            with open('start_dashboard.sh', 'w') as f:
                f.write(dashboard_script)
            
            # Make executable
            os.chmod('start_dashboard.sh', 0o755)
            
            self.log_step("Created dashboard script: start_dashboard.sh")
            return True
            
        except Exception as e:
            self.log_step(f"Failed to create dashboard script: {e}", False)
            return False
    
    def validate_migration(self) -> bool:
        """Validate that migration was successful"""
        try:
            # Check that integrated file exists
            if not os.path.exists('adsb_receiver_integrated.py'):
                self.log_step("Integrated receiver file not found", False)
                return False
            
            # Check config file
            if not os.path.exists('config.json'):
                self.log_step("Configuration file not found", False)
                return False
            
            # Try to load and validate config
            with open('config.json', 'r') as f:
                config = json.load(f)
            
            required_sections = ['pymodes', 'message_sources', 'aircraft_tracking', 'watchlist']
            for section in required_sections:
                if section not in config:
                    self.log_step(f"Missing config section: {section}", False)
                    return False
            
            # Try to import integrated module
            sys.path.insert(0, '.')
            try:
                import adsb_receiver_integrated
                self.log_step("Integrated module imports successfully")
            except ImportError as e:
                self.log_step(f"Failed to import integrated module: {e}", False)
                return False
            
            self.log_step("Migration validation successful")
            return True
            
        except Exception as e:
            self.log_step(f"Migration validation failed: {e}", False)
            return False
    
    def run_migration(self) -> bool:
        """Run complete migration process"""
        logger.info("Starting ADS-B Receiver Migration")
        logger.info("=" * 50)
        
        steps = [
            ("Checking dependencies", self.check_dependencies),
            ("Creating backup", self.backup_files),
            ("Migrating configuration", self.migrate_config),
            ("Creating startup scripts", self.create_startup_script),
            ("Creating dashboard script", self.create_dashboard_script),
            ("Validating migration", self.validate_migration)
        ]
        
        for step_name, step_func in steps:
            logger.info(f"Step: {step_name}")
            if not step_func():
                logger.error(f"Migration failed at step: {step_name}")
                return False
        
        logger.info("=" * 50)
        logger.info("Migration completed successfully!")
        logger.info("")
        logger.info("Next steps:")
        logger.info("1. Review the migrated config.json file")
        logger.info("2. Test the integrated system: python3 adsb_receiver_integrated.py")
        logger.info("3. Use the dashboard: python3 adsb_dashboard.py")
        logger.info("4. Or use the startup scripts: ./start_integrated.sh")
        logger.info("")
        logger.info(f"Backup of original files created in: {self.backup_dir}")
        
        return True
    
    def print_migration_log(self):
        """Print complete migration log"""
        logger.info("\nMigration Log:")
        logger.info("-" * 30)
        for entry in self.migration_log:
            print(entry)


def main():
    """Main migration function"""
    print("Ursine Explorer ADS-B Receiver Migration Tool")
    print("=" * 50)
    print("This tool will migrate your system to the integrated pyModeS version.")
    print("")
    
    # Confirm migration
    response = input("Do you want to proceed with the migration? (y/N): ")
    if response.lower() not in ['y', 'yes']:
        print("Migration cancelled.")
        return
    
    # Run migration
    migration = ADSBMigration()
    success = migration.run_migration()
    
    # Print log
    migration.print_migration_log()
    
    if success:
        print("\n✅ Migration completed successfully!")
        sys.exit(0)
    else:
        print("\n❌ Migration failed. Check the log above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()