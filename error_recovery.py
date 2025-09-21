#!/usr/bin/env python3
"""
Automated error recovery and notification system for Ursine Capture.
Monitors system health and performs automatic recovery actions.
"""

import json
import logging
import smtplib
import time
from datetime import datetime, timedelta
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils import (setup_logging, check_process_running, kill_process, run_command,
                  error_handler, ErrorSeverity, ComponentType)
from config import Config
from system_monitor import SystemMonitor


logger = logging.getLogger(__name__)


class ErrorRecoverySystem:
    """Automated error recovery and notification system."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.monitor = SystemMonitor(config_path)
        
        # Recovery settings
        self.max_recovery_attempts = 3
        self.recovery_cooldown = 300  # 5 minutes between recovery attempts
        self.last_recovery_attempt = {}
        self.recovery_history = []
        
        # Notification settings
        self.notification_config = self._load_notification_config()
        self.last_notification_time = {}
        self.notification_cooldown = 1800  # 30 minutes between similar notifications
        
        # Monitoring settings
        self.check_interval = 60  # Check every minute
        self.critical_check_interval = 10  # Check every 10 seconds when critical
        
    def _load_notification_config(self) -> Dict[str, Any]:
        """Load notification configuration."""
        try:
            notification_file = Path("notification_config.json")
            if notification_file.exists():
                with open(notification_file, 'r') as f:
                    return json.load(f)
            else:
                # Create default notification config
                default_config = {
                    "email": {
                        "enabled": False,
                        "smtp_server": "smtp.gmail.com",
                        "smtp_port": 587,
                        "username": "",
                        "password": "",
                        "from_address": "",
                        "to_addresses": [],
                        "subject_prefix": "[Ursine Capture Alert]"
                    },
                    "webhook": {
                        "enabled": False,
                        "url": "",
                        "headers": {}
                    },
                    "log_only": {
                        "enabled": True
                    }
                }
                
                with open(notification_file, 'w') as f:
                    json.dump(default_config, f, indent=2)
                
                logger.info(f"Created default notification config: {notification_file}")
                return default_config
                
        except Exception as e:
            logger.error(f"Error loading notification config: {e}")
            return {"log_only": {"enabled": True}}
    
    def start_monitoring(self) -> None:
        """Start continuous monitoring and recovery."""
        try:
            logger.info("Starting error recovery monitoring...")
            
            consecutive_critical = 0
            max_consecutive_critical = 5
            
            while True:
                try:
                    # Check system health
                    health_data = self.monitor.check_system_health()
                    overall_status = health_data.get("overall_status", "UNKNOWN")
                    
                    logger.debug(f"System status: {overall_status}")
                    
                    # Handle different status levels
                    if overall_status == "CRITICAL":
                        consecutive_critical += 1
                        self._handle_critical_status(health_data)
                        
                        if consecutive_critical >= max_consecutive_critical:
                            self._handle_persistent_critical(health_data)
                            consecutive_critical = 0
                        
                        # Use shorter check interval for critical issues
                        time.sleep(self.critical_check_interval)
                        
                    elif overall_status == "DEGRADED":
                        consecutive_critical = 0
                        self._handle_degraded_status(health_data)
                        time.sleep(self.check_interval)
                        
                    elif overall_status == "WARNING":
                        consecutive_critical = 0
                        self._handle_warning_status(health_data)
                        time.sleep(self.check_interval)
                        
                    else:  # HEALTHY or UNKNOWN
                        consecutive_critical = 0
                        time.sleep(self.check_interval)
                    
                    # Clean up old recovery history
                    self._cleanup_recovery_history()
                    
                except KeyboardInterrupt:
                    logger.info("Monitoring stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in monitoring loop: {e}")
                    time.sleep(self.check_interval)
                    
        except Exception as e:
            logger.error(f"Fatal error in monitoring: {e}")
            raise
    
    def _handle_critical_status(self, health_data: Dict[str, Any]) -> None:
        """Handle critical system status."""
        try:
            critical_issues = health_data.get("critical_issues", [])
            
            logger.warning(f"Critical status detected: {critical_issues}")
            
            # Send immediate notification
            self._send_notification(
                "CRITICAL",
                "Critical system issues detected",
                health_data,
                force=True
            )
            
            # Attempt recovery for each critical issue
            for issue in critical_issues:
                if "receiver process" in issue.lower():
                    self._recover_receiver_process()
                elif "dump1090" in issue.lower():
                    self._recover_dump1090()
                elif "hackrf" in issue.lower():
                    self._recover_hackrf()
                    
        except Exception as e:
            logger.error(f"Error handling critical status: {e}")
    
    def _handle_degraded_status(self, health_data: Dict[str, Any]) -> None:
        """Handle degraded system status."""
        try:
            warnings = health_data.get("warnings", [])
            
            logger.info(f"Degraded status detected: {warnings}")
            
            # Send notification (with cooldown)
            self._send_notification(
                "DEGRADED",
                "System performance degraded",
                health_data
            )
            
            # Attempt minor recovery actions
            for warning in warnings:
                if "meshtastic" in warning.lower():
                    self._recover_meshtastic()
                elif "message rate" in warning.lower():
                    self._check_antenna_connection()
                    
        except Exception as e:
            logger.error(f"Error handling degraded status: {e}")
    
    def _handle_warning_status(self, health_data: Dict[str, Any]) -> None:
        """Handle warning system status."""
        try:
            warnings = health_data.get("warnings", [])
            
            logger.info(f"Warning status detected: {warnings}")
            
            # Send notification (with longer cooldown)
            self._send_notification(
                "WARNING",
                "System warnings detected",
                health_data,
                cooldown_multiplier=2
            )
            
        except Exception as e:
            logger.error(f"Error handling warning status: {e}")
    
    def _handle_persistent_critical(self, health_data: Dict[str, Any]) -> None:
        """Handle persistent critical issues."""
        try:
            logger.critical("Persistent critical issues detected - escalating response")
            
            # Send urgent notification
            self._send_notification(
                "URGENT",
                "URGENT: Persistent critical system failure",
                health_data,
                force=True
            )
            
            # Perform full system recovery
            self._perform_full_system_recovery()
            
            # Log emergency state
            emergency_log = {
                "timestamp": datetime.now().isoformat(),
                "event": "persistent_critical_failure",
                "health_data": health_data,
                "recovery_history": self.recovery_history[-10:]  # Last 10 attempts
            }
            
            with open("emergency_log.json", 'w') as f:
                json.dump(emergency_log, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error handling persistent critical: {e}")
    
    def _recover_receiver_process(self) -> bool:
        """Attempt to recover receiver process."""
        try:
            recovery_key = "receiver_process"
            
            if not self._can_attempt_recovery(recovery_key):
                return False
            
            logger.info("Attempting receiver process recovery...")
            
            # Kill existing receiver processes
            if kill_process("receiver.py"):
                logger.info("Killed existing receiver processes")
                time.sleep(3)
            
            # Try to start receiver
            success, stdout, stderr = run_command([
                "python", "receiver.py"
            ], timeout=10)
            
            recovery_success = success and check_process_running("receiver.py")
            
            self._record_recovery_attempt(recovery_key, recovery_success, 
                                        f"Receiver restart: {stdout if success else stderr}")
            
            if recovery_success:
                logger.info("Receiver process recovery successful")
            else:
                logger.error(f"Receiver process recovery failed: {stderr}")
            
            return recovery_success
            
        except Exception as e:
            logger.error(f"Error recovering receiver process: {e}")
            return False
    
    def _recover_dump1090(self) -> bool:
        """Attempt to recover dump1090 process."""
        try:
            recovery_key = "dump1090"
            
            if not self._can_attempt_recovery(recovery_key):
                return False
            
            logger.info("Attempting dump1090 recovery...")
            
            # Kill existing dump1090 processes
            if kill_process("dump1090"):
                logger.info("Killed existing dump1090 processes")
                time.sleep(2)
            
            # Get radio config
            radio_config = self.config.get_radio_config()
            
            # Try to start dump1090
            cmd = [
                "/usr/bin/dump1090-fa",
                "--device-type", "hackrf",
                "--gain", str(radio_config.lna_gain),
                "--freq", str(radio_config.frequency),
                "--net",
                "--net-sbs-port", "30003",
                "--net-bi-port", "30005",
                "--quiet"
            ]
            
            success, stdout, stderr = run_command(cmd, timeout=15)
            
            # Check if dump1090 is actually running
            time.sleep(3)
            recovery_success = check_process_running("dump1090")
            
            self._record_recovery_attempt(recovery_key, recovery_success,
                                        f"dump1090 restart: {stdout if success else stderr}")
            
            if recovery_success:
                logger.info("dump1090 recovery successful")
            else:
                logger.error(f"dump1090 recovery failed: {stderr}")
            
            return recovery_success
            
        except Exception as e:
            logger.error(f"Error recovering dump1090: {e}")
            return False
    
    def _recover_hackrf(self) -> bool:
        """Attempt to recover HackRF connection."""
        try:
            recovery_key = "hackrf"
            
            if not self._can_attempt_recovery(recovery_key):
                return False
            
            logger.info("Attempting HackRF recovery...")
            
            # Check HackRF info
            success, stdout, stderr = run_command(["hackrf_info"], timeout=10)
            
            recovery_success = success and "Found HackRF" in stdout
            
            self._record_recovery_attempt(recovery_key, recovery_success,
                                        f"HackRF check: {stdout if success else stderr}")
            
            if recovery_success:
                logger.info("HackRF recovery successful")
            else:
                logger.error(f"HackRF recovery failed: {stderr}")
                logger.info("HackRF may need manual reconnection")
            
            return recovery_success
            
        except Exception as e:
            logger.error(f"Error recovering HackRF: {e}")
            return False
    
    def _recover_meshtastic(self) -> bool:
        """Attempt to recover Meshtastic connection."""
        try:
            recovery_key = "meshtastic"
            
            if not self._can_attempt_recovery(recovery_key):
                return False
            
            logger.info("Attempting Meshtastic recovery...")
            
            # Check if Meshtastic device exists
            meshtastic_config = self.config.get_meshtastic_config()
            device_exists = Path(meshtastic_config.port).exists()
            
            recovery_success = device_exists
            
            self._record_recovery_attempt(recovery_key, recovery_success,
                                        f"Meshtastic device check: {meshtastic_config.port}")
            
            if recovery_success:
                logger.info("Meshtastic device found")
            else:
                logger.warning("Meshtastic device not found - may need manual reconnection")
            
            return recovery_success
            
        except Exception as e:
            logger.error(f"Error recovering Meshtastic: {e}")
            return False
    
    def _check_antenna_connection(self) -> None:
        """Check antenna connection (informational)."""
        try:
            logger.info("Low message rate detected - check antenna connection and positioning")
            
            # Log antenna check recommendation
            self._record_recovery_attempt("antenna_check", False, 
                                        "Manual antenna check recommended")
            
        except Exception as e:
            logger.error(f"Error in antenna check: {e}")
    
    def _perform_full_system_recovery(self) -> bool:
        """Perform full system recovery."""
        try:
            logger.warning("Performing full system recovery...")
            
            recovery_steps = []
            overall_success = True
            
            # Step 1: Kill all processes
            recovery_steps.append("Stopping all processes...")
            kill_process("receiver.py")
            kill_process("dump1090")
            time.sleep(5)
            
            # Step 2: Check HackRF
            recovery_steps.append("Checking HackRF connection...")
            hackrf_ok = self._recover_hackrf()
            if not hackrf_ok:
                overall_success = False
            
            # Step 3: Restart dump1090
            recovery_steps.append("Restarting dump1090...")
            dump1090_ok = self._recover_dump1090()
            if not dump1090_ok:
                overall_success = False
            
            # Step 4: Restart receiver
            recovery_steps.append("Restarting receiver...")
            receiver_ok = self._recover_receiver_process()
            if not receiver_ok:
                overall_success = False
            
            # Step 5: Check Meshtastic
            recovery_steps.append("Checking Meshtastic...")
            self._recover_meshtastic()
            
            # Record full recovery attempt
            self._record_recovery_attempt("full_system_recovery", overall_success,
                                        f"Steps: {'; '.join(recovery_steps)}")
            
            if overall_success:
                logger.info("Full system recovery completed successfully")
            else:
                logger.error("Full system recovery completed with errors")
            
            return overall_success
            
        except Exception as e:
            logger.error(f"Error in full system recovery: {e}")
            return False
    
    def _can_attempt_recovery(self, recovery_key: str) -> bool:
        """Check if recovery can be attempted (cooldown and attempt limits)."""
        try:
            current_time = time.time()
            
            # Check cooldown
            if recovery_key in self.last_recovery_attempt:
                time_since_last = current_time - self.last_recovery_attempt[recovery_key]
                if time_since_last < self.recovery_cooldown:
                    logger.debug(f"Recovery for {recovery_key} in cooldown "
                               f"({self.recovery_cooldown - time_since_last:.0f}s remaining)")
                    return False
            
            # Check attempt limits (last hour)
            recent_attempts = [
                attempt for attempt in self.recovery_history
                if (attempt["recovery_key"] == recovery_key and
                    current_time - attempt["timestamp"] < 3600)
            ]
            
            if len(recent_attempts) >= self.max_recovery_attempts:
                logger.warning(f"Max recovery attempts for {recovery_key} reached in last hour")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking recovery eligibility: {e}")
            return False
    
    def _record_recovery_attempt(self, recovery_key: str, success: bool, details: str) -> None:
        """Record a recovery attempt."""
        try:
            current_time = time.time()
            
            recovery_record = {
                "timestamp": current_time,
                "recovery_key": recovery_key,
                "success": success,
                "details": details,
                "datetime": datetime.now().isoformat()
            }
            
            self.recovery_history.append(recovery_record)
            self.last_recovery_attempt[recovery_key] = current_time
            
            # Limit history size
            if len(self.recovery_history) > 100:
                self.recovery_history = self.recovery_history[-100:]
            
            logger.info(f"Recovery attempt recorded: {recovery_key} - "
                       f"{'SUCCESS' if success else 'FAILED'}")
            
        except Exception as e:
            logger.error(f"Error recording recovery attempt: {e}")
    
    def _cleanup_recovery_history(self) -> None:
        """Clean up old recovery history."""
        try:
            current_time = time.time()
            cutoff_time = current_time - 86400  # 24 hours
            
            self.recovery_history = [
                record for record in self.recovery_history
                if record["timestamp"] > cutoff_time
            ]
            
        except Exception as e:
            logger.error(f"Error cleaning up recovery history: {e}")
    
    def _send_notification(self, severity: str, subject: str, health_data: Dict[str, Any],
                          force: bool = False, cooldown_multiplier: float = 1.0) -> None:
        """Send notification via configured methods."""
        try:
            notification_key = f"{severity}_{subject}"
            current_time = time.time()
            
            # Check cooldown (unless forced)
            if not force and notification_key in self.last_notification_time:
                cooldown = self.notification_cooldown * cooldown_multiplier
                time_since_last = current_time - self.last_notification_time[notification_key]
                if time_since_last < cooldown:
                    logger.debug(f"Notification {notification_key} in cooldown")
                    return
            
            # Send via configured methods
            if self.notification_config.get("email", {}).get("enabled", False):
                self._send_email_notification(severity, subject, health_data)
            
            if self.notification_config.get("webhook", {}).get("enabled", False):
                self._send_webhook_notification(severity, subject, health_data)
            
            if self.notification_config.get("log_only", {}).get("enabled", True):
                self._send_log_notification(severity, subject, health_data)
            
            self.last_notification_time[notification_key] = current_time
            
        except Exception as e:
            logger.error(f"Error sending notification: {e}")
    
    def _send_email_notification(self, severity: str, subject: str, health_data: Dict[str, Any]) -> None:
        """Send email notification."""
        try:
            email_config = self.notification_config["email"]
            
            # Create message
            msg = MimeMultipart()
            msg['From'] = email_config["from_address"]
            msg['To'] = ", ".join(email_config["to_addresses"])
            msg['Subject'] = f"{email_config['subject_prefix']} {severity}: {subject}"
            
            # Create body
            body = f"""
Ursine Capture System Alert

Severity: {severity}
Subject: {subject}
Timestamp: {datetime.now().isoformat()}

System Status: {health_data.get('overall_status', 'UNKNOWN')}

Critical Issues:
{chr(10).join(f"  • {issue}" for issue in health_data.get('critical_issues', []))}

Warnings:
{chr(10).join(f"  • {warning}" for warning in health_data.get('warnings', []))}

Recommendations:
{chr(10).join(f"  • {rec}" for rec in health_data.get('recommendations', []))}

Component Status:
"""
            
            for component, status in health_data.get("components", {}).items():
                body += f"  {component.upper()}: {status.get('health', 'UNKNOWN')}\n"
            
            msg.attach(MimeText(body, 'plain'))
            
            # Send email
            server = smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"])
            server.starttls()
            server.login(email_config["username"], email_config["password"])
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email notification sent: {severity}")
            
        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
    
    def _send_webhook_notification(self, severity: str, subject: str, health_data: Dict[str, Any]) -> None:
        """Send webhook notification."""
        try:
            import requests
            
            webhook_config = self.notification_config["webhook"]
            
            payload = {
                "severity": severity,
                "subject": subject,
                "timestamp": datetime.now().isoformat(),
                "health_data": health_data
            }
            
            response = requests.post(
                webhook_config["url"],
                json=payload,
                headers=webhook_config.get("headers", {}),
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"Webhook notification sent: {severity}")
            else:
                logger.error(f"Webhook notification failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending webhook notification: {e}")
    
    def _send_log_notification(self, severity: str, subject: str, health_data: Dict[str, Any]) -> None:
        """Send log notification."""
        try:
            log_level = {
                "CRITICAL": logging.CRITICAL,
                "URGENT": logging.CRITICAL,
                "DEGRADED": logging.WARNING,
                "WARNING": logging.WARNING
            }.get(severity, logging.INFO)
            
            logger.log(log_level, f"NOTIFICATION [{severity}]: {subject}")
            
            if health_data.get("critical_issues"):
                logger.log(log_level, f"Critical Issues: {health_data['critical_issues']}")
            
            if health_data.get("warnings"):
                logger.log(log_level, f"Warnings: {health_data['warnings']}")
                
        except Exception as e:
            logger.error(f"Error sending log notification: {e}")


def main():
    """Main error recovery entry point."""
    try:
        setup_logging("error-recovery.log")
        
        config_path = sys.argv[1] if len(sys.argv) > 1 else "config.json"
        
        recovery_system = ErrorRecoverySystem(config_path)
        recovery_system.start_monitoring()
        
    except KeyboardInterrupt:
        logger.info("Error recovery system stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in recovery system: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()