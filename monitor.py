#!/usr/bin/env python3
"""
Ursine Explorer - ADS-B Aircraft Monitor
Monitors dump1090 output for specific ICAO codes and sends Discord notifications
"""

import json
import time
import requests
import subprocess
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, Optional

class ADSBMonitor:
    def __init__(self, config_path: str = "config.json"):
        self.config = self.load_config(config_path)
        self.tracked_aircraft: Dict[str, dict] = {}
        self.notified_aircraft: Set[str] = set()
        self.setup_logging()
        
    def load_config(self, config_path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logging.error(f"Config file {config_path} not found")
            raise
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in {config_path}")
            raise
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = self.config.get('log_level', 'INFO')
        
        # Use the same directory as the script for log file
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        log_file = os.path.join(script_dir, 'ursine-explorer.log')
        
        logging.basicConfig(
            level=getattr(logging, log_level),
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    def get_dump1090_data(self) -> Optional[dict]:
        """Fetch aircraft data from dump1090"""
        try:
            url = f"http://{self.config['dump1090_host']}:{self.config['dump1090_port']}/data/aircraft.json"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logging.warning(f"Failed to fetch dump1090 data: {e}")
            return None
    
    def send_discord_notification(self, aircraft: dict):
        """Send Discord webhook notification"""
        icao = aircraft.get('hex', 'Unknown').upper()
        callsign = aircraft.get('flight', 'Unknown').strip()
        altitude = aircraft.get('alt_baro', 'Unknown')
        speed = aircraft.get('gs', 'Unknown')
        track = aircraft.get('track', 'Unknown')
        
        embed = {
            "title": f"🛩️ Target Aircraft Detected: {icao}",
            "color": 0x00ff00,
            "fields": [
                {"name": "ICAO Code", "value": icao, "inline": True},
                {"name": "Callsign", "value": callsign, "inline": True},
                {"name": "Altitude", "value": f"{altitude} ft" if altitude != 'Unknown' else 'Unknown', "inline": True},
                {"name": "Speed", "value": f"{speed} kts" if speed != 'Unknown' else 'Unknown', "inline": True},
                {"name": "Track", "value": f"{track}°" if track != 'Unknown' else 'Unknown', "inline": True},
                {"name": "Time", "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
            ],
            "timestamp": datetime.now().isoformat()
        }
        
        payload = {
            "embeds": [embed]
        }
        
        try:
            response = requests.post(self.config['discord_webhook'], json=payload, timeout=10)
            response.raise_for_status()
            logging.info(f"Discord notification sent for {icao}")
        except requests.RequestException as e:
            logging.error(f"Failed to send Discord notification: {e}")
    
    def process_aircraft(self, aircraft_data: dict):
        """Process aircraft data and check for target ICAO codes"""
        if not aircraft_data or 'aircraft' not in aircraft_data:
            return
        
        current_time = datetime.now()
        target_icaos = set(code.lower() for code in self.config['target_icao_codes'])
        
        for aircraft in aircraft_data['aircraft']:
            icao = aircraft.get('hex', '').lower()
            
            if not icao:
                continue
            
            # Update tracked aircraft
            self.tracked_aircraft[icao] = {
                'data': aircraft,
                'last_seen': current_time
            }
            
            # Check if this is a target aircraft
            if icao in target_icaos:
                # Check if we haven't notified about this aircraft recently
                cooldown_minutes = self.config.get('notification_cooldown_minutes', 30)
                
                if icao not in self.notified_aircraft:
                    self.send_discord_notification(aircraft)
                    self.notified_aircraft.add(icao)
                    logging.info(f"New target aircraft detected: {icao.upper()}")
        
        # Clean up old aircraft data
        cutoff_time = current_time - timedelta(minutes=5)
        self.tracked_aircraft = {
            icao: data for icao, data in self.tracked_aircraft.items()
            if data['last_seen'] > cutoff_time
        }
        
        # Reset notification cooldown for aircraft no longer visible
        visible_icaos = set(aircraft.get('hex', '').lower() for aircraft in aircraft_data['aircraft'])
        self.notified_aircraft = self.notified_aircraft.intersection(visible_icaos)
    
    def run(self):
        """Main monitoring loop"""
        logging.info("Starting Ursine Explorer...")
        logging.info(f"Monitoring ICAO codes: {', '.join(self.config['target_icao_codes'])}")
        
        while True:
            try:
                aircraft_data = self.get_dump1090_data()
                if aircraft_data:
                    self.process_aircraft(aircraft_data)
                
                time.sleep(self.config.get('poll_interval_seconds', 5))
                
            except KeyboardInterrupt:
                logging.info("Shutting down Ursine Explorer...")
                break
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                time.sleep(10)  # Wait before retrying

if __name__ == "__main__":
    monitor = ADSBMonitor()
    monitor.run()