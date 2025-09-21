#!/usr/bin/env python3
"""
System monitoring and health check script for Ursine Capture.
Can be run independently to check system health and perform basic recovery.
"""

import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils import (setup_logging, check_process_running, kill_process, run_command,
                  error_handler, ErrorSeverity, ComponentType, get_hackrf_info)
from config import Config


logger = logging.getLogger(__name__)


class SystemMonitor:
    """Comprehensive system monitoring and health checking."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.status_file = Path("status.json")
        self.aircraft_file = Path("aircraft.json")
        self.log_file = Path("ursine-receiver.log")
        
        # Health thresholds
        self.max_error_rate = 10  # errors per hour
        self.max_message_age = 300  # seconds
        self.min_message_rate = 1.0  # messages per second
        self.max_consecutive_errors = 5
        
    def check_system_health(self) -> Dict[str, Any]:
        """Perform comprehensive system health check."""
        try:
            health_report = {
                "timestamp": datetime.now().isoformat(),
                "overall_status": "UNKNOWN",
                "components": {},
                "metrics": {},
                "recommendations": [],
                "critical_issues": [],
                "warnings": []
            }
            
            # Check individual components
            health_report["components"]["receiver"] = self._check_receiver_process()
            health_report["components"]["dump1090"] = self._check_dump1090()
            health_report["components"]["hackrf"] = self._check_hackrf()
            health_report["components"]["meshtastic"] = self._check_meshtastic()
            health_report["components"]["config"] = self._check_configuration()
            health_report["components"]["files"] = self._check_files()
            
            # Calculate metrics
            health_report["metrics"] = self._calculate_metrics()
            
            # Analyze health and generate recommendations
            self._analyze_health(health_report)
            
            # Determine overall status
            health_report["overall_status"] = self._determine_overall_status(health_report)
            
            return health_report
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.HIGH,
                f"Error during system health check: {str(e)}",
                error_code="HEALTH_CHECK_ERROR"
            )
            return {
                "timestamp": datetime.now().isoformat(),
                "overall_status": "ERROR",
                "error": str(e)
            }
    
    def _check_receiver_process(self) -> Dict[str, Any]:
        """Check receiver process health."""
        try:
            is_running = check_process_running("python") and check_process_running("receiver.py")
            
            # Check if status file is being updated
            status_age = 0
            if self.status_file.exists():
                status_age = (datetime.now() - datetime.fromtimestamp(
                    self.status_file.stat().st_mtime)).total_seconds()
            
            return {
                "status": "RUNNING" if is_running else "STOPPED",
                "process_running": is_running,
                "status_file_age": status_age,
                "status_file_fresh": status_age < 60,
                "health": "HEALTHY" if is_running and status_age < 60 else "UNHEALTHY"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "health": "ERROR"
            }
    
    def _check_dump1090(self) -> Dict[str, Any]:
        """Check dump1090 process health."""
        try:
            is_running = check_process_running("dump1090")
            
            # Try to connect to dump1090 TCP port
            tcp_accessible = False
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(("localhost", 30005))
                tcp_accessible = result == 0
                sock.close()
            except:
                pass
            
            return {
                "status": "RUNNING" if is_running else "STOPPED",
                "process_running": is_running,
                "tcp_accessible": tcp_accessible,
                "health": "HEALTHY" if is_running and tcp_accessible else "UNHEALTHY"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "health": "ERROR"
            }
    
    def _check_hackrf(self) -> Dict[str, Any]:
        """Check HackRF device health."""
        try:
            hackrf_info = get_hackrf_info()
            
            return {
                "status": "CONNECTED" if hackrf_info.get("connected", False) else "DISCONNECTED",
                "connected": hackrf_info.get("connected", False),
                "info": hackrf_info,
                "health": "HEALTHY" if hackrf_info.get("connected", False) else "UNHEALTHY"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "health": "ERROR"
            }
    
    def _check_meshtastic(self) -> Dict[str, Any]:
        """Check Meshtastic device health."""
        try:
            meshtastic_config = self.config.get_meshtastic_config()
            
            # Check if device file exists
            device_exists = Path(meshtastic_config.port).exists()
            
            # Try to open serial port briefly
            port_accessible = False
            try:
                import serial
                ser = serial.Serial(meshtastic_config.port, meshtastic_config.baud, timeout=1)
                port_accessible = True
                ser.close()
            except:
                pass
            
            return {
                "status": "ACCESSIBLE" if port_accessible else "INACCESSIBLE",
                "device_exists": device_exists,
                "port_accessible": port_accessible,
                "port": meshtastic_config.port,
                "health": "HEALTHY" if port_accessible else "DEGRADED"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "health": "ERROR"
            }
    
    def _check_configuration(self) -> Dict[str, Any]:
        """Check configuration health."""
        try:
            config_data = self.config.load()
            is_valid = self.config.validate(config_data)
            
            # Check if config file is recent
            config_age = 0
            if self.config.config_path.exists():
                config_age = (datetime.now() - datetime.fromtimestamp(
                    self.config.config_path.stat().st_mtime)).total_seconds()
            
            return {
                "status": "VALID" if is_valid else "INVALID",
                "valid": is_valid,
                "file_age": config_age,
                "watchlist_size": len(config_data.get("watchlist", [])),
                "health": "HEALTHY" if is_valid else "UNHEALTHY"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "health": "ERROR"
            }
    
    def _check_files(self) -> Dict[str, Any]:
        """Check critical file health."""
        try:
            files_status = {}
            
            # Check status.json
            if self.status_file.exists():
                status_age = (datetime.now() - datetime.fromtimestamp(
                    self.status_file.stat().st_mtime)).total_seconds()
                files_status["status_json"] = {
                    "exists": True,
                    "age": status_age,
                    "fresh": status_age < 60
                }
            else:
                files_status["status_json"] = {"exists": False}
            
            # Check aircraft.json
            if self.aircraft_file.exists():
                aircraft_age = (datetime.now() - datetime.fromtimestamp(
                    self.aircraft_file.stat().st_mtime)).total_seconds()
                files_status["aircraft_json"] = {
                    "exists": True,
                    "age": aircraft_age,
                    "fresh": aircraft_age < 60
                }
            else:
                files_status["aircraft_json"] = {"exists": False}
            
            # Check log file
            if self.log_file.exists():
                log_size = self.log_file.stat().st_size
                files_status["log_file"] = {
                    "exists": True,
                    "size_mb": round(log_size / 1024 / 1024, 2),
                    "large": log_size > 100 * 1024 * 1024  # > 100MB
                }
            else:
                files_status["log_file"] = {"exists": False}
            
            all_critical_exist = (files_status.get("status_json", {}).get("exists", False) and
                                files_status.get("aircraft_json", {}).get("exists", False))
            
            return {
                "status": "HEALTHY" if all_critical_exist else "DEGRADED",
                "files": files_status,
                "health": "HEALTHY" if all_critical_exist else "DEGRADED"
            }
            
        except Exception as e:
            return {
                "status": "ERROR",
                "error": str(e),
                "health": "ERROR"
            }
    
    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate system performance metrics."""
        try:
            metrics = {}
            
            # Load status data if available
            if self.status_file.exists():
                try:
                    with open(self.status_file, 'r') as f:
                        status_data = json.load(f)
                    
                    metrics["message_rate"] = status_data.get("message_rate", 0)
                    metrics["aircraft_count"] = status_data.get("aircraft_count", 0)
                    metrics["error_count"] = len(status_data.get("errors", []))
                    metrics["uptime"] = status_data.get("uptime", "0s")
                    
                except:
                    pass
            
            # Calculate error rate from error handler
            recent_errors = error_handler.get_recent_errors(hours=1)
            metrics["error_rate_per_hour"] = len(recent_errors)
            metrics["critical_errors"] = len([e for e in recent_errors if e.severity == ErrorSeverity.CRITICAL])
            
            return metrics
            
        except Exception as e:
            return {"error": str(e)}
    
    def _analyze_health(self, health_report: Dict[str, Any]) -> None:
        """Analyze health report and generate recommendations."""
        try:
            components = health_report["components"]
            metrics = health_report["metrics"]
            recommendations = health_report["recommendations"]
            critical_issues = health_report["critical_issues"]
            warnings = health_report["warnings"]
            
            # Check for critical issues
            if not components.get("receiver", {}).get("process_running", False):
                critical_issues.append("Receiver process is not running")
                recommendations.append("Start the receiver process: python receiver.py")
            
            if not components.get("dump1090", {}).get("process_running", False):
                critical_issues.append("dump1090 process is not running")
                recommendations.append("Check HackRF connection and restart dump1090")
            
            if not components.get("hackrf", {}).get("connected", False):
                critical_issues.append("HackRF device is not connected")
                recommendations.append("Check HackRF USB connection and drivers")
            
            # Check for warnings
            if metrics.get("message_rate", 0) < self.min_message_rate:
                warnings.append(f"Low message rate: {metrics.get('message_rate', 0):.1f} msg/s")
                recommendations.append("Check antenna connection and positioning")
            
            if metrics.get("error_rate_per_hour", 0) > self.max_error_rate:
                warnings.append(f"High error rate: {metrics.get('error_rate_per_hour', 0)} errors/hour")
                recommendations.append("Check system logs for recurring issues")
            
            if not components.get("meshtastic", {}).get("port_accessible", False):
                warnings.append("Meshtastic device is not accessible")
                recommendations.append("Check Meshtastic USB connection and permissions")
            
            # File-related warnings
            files = components.get("files", {}).get("files", {})
            if not files.get("status_json", {}).get("fresh", False):
                warnings.append("Status file is not being updated regularly")
                recommendations.append("Check if receiver process is running properly")
            
            if files.get("log_file", {}).get("large", False):
                warnings.append("Log file is very large")
                recommendations.append("Consider rotating or archiving log files")
            
        except Exception as e:
            logger.error(f"Error analyzing health: {e}")
    
    def _determine_overall_status(self, health_report: Dict[str, Any]) -> str:
        """Determine overall system status."""
        try:
            critical_issues = health_report.get("critical_issues", [])
            warnings = health_report.get("warnings", [])
            
            if len(critical_issues) > 0:
                return "CRITICAL"
            elif len(warnings) > 2:
                return "DEGRADED"
            elif len(warnings) > 0:
                return "WARNING"
            else:
                return "HEALTHY"
                
        except Exception as e:
            return "ERROR"
    
    def perform_basic_recovery(self) -> Dict[str, Any]:
        """Perform basic system recovery actions."""
        try:
            recovery_report = {
                "timestamp": datetime.now().isoformat(),
                "actions_taken": [],
                "success": False,
                "errors": []
            }
            
            # Check if receiver is running
            if not check_process_running("receiver.py"):
                recovery_report["actions_taken"].append("Attempted to restart receiver process")
                # Note: In a real implementation, you'd start the receiver here
                # For now, just log the action
                logger.info("Would restart receiver process")
            
            # Check if dump1090 is running
            if not check_process_running("dump1090"):
                recovery_report["actions_taken"].append("Attempted to restart dump1090")
                # Kill any existing dump1090 processes
                if kill_process("dump1090"):
                    recovery_report["actions_taken"].append("Killed existing dump1090 processes")
                
                # Try to start dump1090 (simplified)
                success, stdout, stderr = run_command([
                    "/usr/bin/dump1090-fa", "--device-type", "hackrf", 
                    "--gain", "40", "--freq", "1090100000", "--net", "--quiet"
                ], timeout=10)
                
                if success:
                    recovery_report["actions_taken"].append("Successfully started dump1090")
                else:
                    recovery_report["errors"].append(f"Failed to start dump1090: {stderr}")
            
            # Check HackRF
            hackrf_info = get_hackrf_info()
            if not hackrf_info.get("connected", False):
                recovery_report["actions_taken"].append("Checked HackRF connection")
                recovery_report["errors"].append("HackRF not connected - manual intervention required")
            
            recovery_report["success"] = len(recovery_report["errors"]) == 0
            return recovery_report
            
        except Exception as e:
            return {
                "timestamp": datetime.now().isoformat(),
                "success": False,
                "error": str(e)
            }
    
    def generate_health_report(self, output_file: str = None) -> str:
        """Generate a comprehensive health report."""
        try:
            health_data = self.check_system_health()
            
            # Generate human-readable report
            report_lines = [
                "URSINE CAPTURE SYSTEM HEALTH REPORT",
                "=" * 40,
                f"Generated: {health_data['timestamp']}",
                f"Overall Status: {health_data['overall_status']}",
                ""
            ]
            
            # Component status
            report_lines.append("COMPONENT STATUS:")
            for component, status in health_data.get("components", {}).items():
                health = status.get("health", "UNKNOWN")
                report_lines.append(f"  {component.upper()}: {health}")
            
            report_lines.append("")
            
            # Metrics
            if health_data.get("metrics"):
                report_lines.append("SYSTEM METRICS:")
                for metric, value in health_data["metrics"].items():
                    report_lines.append(f"  {metric}: {value}")
                report_lines.append("")
            
            # Critical issues
            if health_data.get("critical_issues"):
                report_lines.append("CRITICAL ISSUES:")
                for issue in health_data["critical_issues"]:
                    report_lines.append(f"  • {issue}")
                report_lines.append("")
            
            # Warnings
            if health_data.get("warnings"):
                report_lines.append("WARNINGS:")
                for warning in health_data["warnings"]:
                    report_lines.append(f"  • {warning}")
                report_lines.append("")
            
            # Recommendations
            if health_data.get("recommendations"):
                report_lines.append("RECOMMENDATIONS:")
                for rec in health_data["recommendations"]:
                    report_lines.append(f"  • {rec}")
                report_lines.append("")
            
            report_text = "\n".join(report_lines)
            
            # Save to file if requested
            if output_file:
                with open(output_file, 'w') as f:
                    f.write(report_text)
                    f.write("\n\nRAW DATA:\n")
                    f.write(json.dumps(health_data, indent=2))
            
            return report_text
            
        except Exception as e:
            return f"Error generating health report: {e}"


def main():
    """Main system monitor entry point."""
    try:
        setup_logging("system-monitor.log")
        
        if len(sys.argv) < 2:
            print("Usage: python system_monitor.py <command> [options]")
            print("Commands:")
            print("  health    - Check system health")
            print("  recover   - Perform basic recovery")
            print("  report    - Generate detailed report")
            print("  monitor   - Continuous monitoring")
            sys.exit(1)
        
        command = sys.argv[1].lower()
        config_path = sys.argv[2] if len(sys.argv) > 2 else "config.json"
        
        monitor = SystemMonitor(config_path)
        
        if command == "health":
            health_data = monitor.check_system_health()
            print(json.dumps(health_data, indent=2))
            
        elif command == "recover":
            recovery_data = monitor.perform_basic_recovery()
            print(json.dumps(recovery_data, indent=2))
            
        elif command == "report":
            output_file = sys.argv[3] if len(sys.argv) > 3 else "health_report.txt"
            report = monitor.generate_health_report(output_file)
            print(report)
            print(f"\nDetailed report saved to: {output_file}")
            
        elif command == "monitor":
            print("Starting continuous monitoring (Ctrl+C to stop)...")
            try:
                while True:
                    health_data = monitor.check_system_health()
                    status = health_data.get("overall_status", "UNKNOWN")
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    print(f"[{timestamp}] System Status: {status}")
                    
                    if status in ["CRITICAL", "DEGRADED"]:
                        print("  Issues detected:")
                        for issue in health_data.get("critical_issues", []):
                            print(f"    CRITICAL: {issue}")
                        for warning in health_data.get("warnings", []):
                            print(f"    WARNING: {warning}")
                    
                    time.sleep(30)  # Check every 30 seconds
                    
            except KeyboardInterrupt:
                print("\nMonitoring stopped")
                
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"System monitor error: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()