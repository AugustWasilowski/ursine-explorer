#!/usr/bin/env python3
"""
End-to-End System Validation for Ursine Explorer ADS-B Receiver
Validates complete system functionality with real data sources
"""

import json
import time
import requests
import socket
import threading
import subprocess
import sys
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging
import tempfile

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemValidator:
    """Comprehensive system validation"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config = self.load_config()
        self.validation_results: Dict[str, Dict[str, Any]] = {}
        self.test_server_process: Optional[subprocess.Popen] = None
        self.start_time = datetime.now()
        
    def load_config(self) -> dict:
        """Load system configuration"""
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}
    
    def log_result(self, test_name: str, success: bool, details: str = "", 
                   metrics: Dict[str, Any] = None):
        """Log validation result"""
        self.validation_results[test_name] = {
            'success': success,
            'details': details,
            'metrics': metrics or {},
            'timestamp': datetime.now().isoformat()
        }
        
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}: {details}")
    
    def validate_dependencies(self) -> bool:
        """Validate all system dependencies"""
        logger.info("Validating system dependencies...")
        
        # Check Python version
        python_version = sys.version_info
        if python_version < (3, 7):
            self.log_result("python_version", False, 
                          f"Python {python_version.major}.{python_version.minor} < 3.7")
            return False
        
        self.log_result("python_version", True, 
                       f"Python {python_version.major}.{python_version.minor}.{python_version.micro}")
        
        # Check required Python modules
        required_modules = [
            ('pyModeS', 'pyModeS'),
            ('numpy', 'numpy'),
            ('requests', 'requests'),
            ('serial', 'pyserial'),
            ('curses', 'curses (built-in)'),
            ('json', 'json (built-in)'),
            ('threading', 'threading (built-in)'),
            ('socket', 'socket (built-in)')
        ]
        
        missing_modules = []
        for module_name, package_name in required_modules:
            try:
                __import__(module_name)
                self.log_result(f"module_{module_name}", True, f"{package_name} available")
            except ImportError:
                missing_modules.append(package_name)
                self.log_result(f"module_{module_name}", False, f"{package_name} missing")
        
        if missing_modules:
            self.log_result("dependencies", False, 
                          f"Missing modules: {', '.join(missing_modules)}")
            return False
        
        # Check required files
        required_files = [
            'adsb_receiver_integrated.py',
            'adsb_dashboard.py',
            'pymodes_integration/__init__.py',
            'pymodes_integration/decoder.py',
            'pymodes_integration/aircraft.py',
            'pymodes_integration/message_source.py'
        ]
        
        missing_files = []
        for file_path in required_files:
            if os.path.exists(file_path):
                self.log_result(f"file_{file_path.replace('/', '_')}", True, f"{file_path} exists")
            else:
                missing_files.append(file_path)
                self.log_result(f"file_{file_path.replace('/', '_')}", False, f"{file_path} missing")
        
        if missing_files:
            self.log_result("required_files", False, 
                          f"Missing files: {', '.join(missing_files)}")
            return False
        
        self.log_result("dependencies", True, "All dependencies satisfied")
        return True
    
    def validate_configuration(self) -> bool:
        """Validate system configuration"""
        logger.info("Validating system configuration...")
        
        if not self.config:
            self.log_result("config_load", False, "Failed to load configuration")
            return False
        
        self.log_result("config_load", True, "Configuration loaded successfully")
        
        # Check required configuration sections
        required_sections = [
            'pymodes',
            'message_sources',
            'aircraft_tracking',
            'watchlist',
            'logging',
            'performance'
        ]
        
        missing_sections = []
        for section in required_sections:
            if section in self.config:
                self.log_result(f"config_{section}", True, f"{section} section present")
            else:
                missing_sections.append(section)
                self.log_result(f"config_{section}", False, f"{section} section missing")
        
        # Validate specific configuration values
        config_checks = [
            ('dump1090_host', str, 'localhost'),
            ('dump1090_port', int, 30005),
            ('receiver_control_port', int, 8081),
            ('target_icao_codes', list, [])
        ]
        
        for key, expected_type, default_value in config_checks:
            value = self.config.get(key, default_value)
            if isinstance(value, expected_type):
                self.log_result(f"config_value_{key}", True, f"{key} = {value}")
            else:
                self.log_result(f"config_value_{key}", False, 
                              f"{key} has wrong type: {type(value)} != {expected_type}")
        
        # Validate pyModeS configuration
        if 'pymodes' in self.config:
            pymodes_config = self.config['pymodes']
            if pymodes_config.get('enabled', True):
                self.log_result("pymodes_enabled", True, "pyModeS integration enabled")
            else:
                self.log_result("pymodes_enabled", False, "pyModeS integration disabled")
        
        success = len(missing_sections) == 0
        self.log_result("configuration", success, 
                       f"Configuration validation {'passed' if success else 'failed'}")
        return success
    
    def start_test_server(self) -> bool:
        """Start the integrated server for testing"""
        logger.info("Starting test server...")
        
        try:
            cmd = [sys.executable, 'adsb_receiver_integrated.py']
            
            self.test_server_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid
            )
            
            # Wait for server to start
            time.sleep(5)
            
            # Check if process is still running
            if self.test_server_process.poll() is None:
                self.log_result("server_start", True, 
                              f"Test server started (PID: {self.test_server_process.pid})")
                return True
            else:
                stdout, stderr = self.test_server_process.communicate()
                self.log_result("server_start", False, 
                              f"Server failed to start: {stderr.decode()}")
                return False
                
        except Exception as e:
            self.log_result("server_start", False, f"Failed to start server: {e}")
            return False
    
    def stop_test_server(self):
        """Stop the test server"""
        if self.test_server_process:
            try:
                logger.info("Stopping test server...")
                os.killpg(os.getpgid(self.test_server_process.pid), 15)  # SIGTERM
                
                try:
                    self.test_server_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(os.getpgid(self.test_server_process.pid), 9)  # SIGKILL
                    self.test_server_process.wait()
                
                self.log_result("server_stop", True, "Test server stopped")
            except Exception as e:
                self.log_result("server_stop", False, f"Error stopping server: {e}")
    
    def validate_http_api(self) -> bool:
        """Validate HTTP API endpoints"""
        logger.info("Validating HTTP API endpoints...")
        
        base_url = "http://localhost:8080"
        endpoints = [
            ('/data/aircraft.json', 'Aircraft data endpoint'),
            ('/data/aircraft_enhanced.json', 'Enhanced aircraft data endpoint'),
            ('/api/status', 'System status endpoint'),
            ('/api/stats', 'Statistics endpoint'),
            ('/api/health', 'Health check endpoint'),
            ('/api/sources', 'Message sources endpoint'),
            ('/api/decoder', 'Decoder metrics endpoint')
        ]
        
        api_success = True
        response_times = []
        
        for endpoint, description in endpoints:
            try:
                start_time = time.time()
                response = requests.get(f"{base_url}{endpoint}", timeout=10)
                response_time = time.time() - start_time
                response_times.append(response_time)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        self.log_result(f"api_{endpoint.replace('/', '_')}", True, 
                                      f"{description} - {response.status_code} - {response_time:.3f}s",
                                      {'response_time': response_time, 'data_size': len(str(data))})
                    except json.JSONDecodeError:
                        self.log_result(f"api_{endpoint.replace('/', '_')}", False, 
                                      f"{description} - Invalid JSON response")
                        api_success = False
                else:
                    self.log_result(f"api_{endpoint.replace('/', '_')}", False, 
                                  f"{description} - HTTP {response.status_code}")
                    api_success = False
                    
            except requests.RequestException as e:
                self.log_result(f"api_{endpoint.replace('/', '_')}", False, 
                              f"{description} - Request failed: {e}")
                api_success = False
        
        # Calculate API performance metrics
        if response_times:
            avg_response_time = sum(response_times) / len(response_times)
            max_response_time = max(response_times)
            
            self.log_result("api_performance", True, 
                          f"Avg: {avg_response_time:.3f}s, Max: {max_response_time:.3f}s",
                          {'avg_response_time': avg_response_time, 'max_response_time': max_response_time})
        
        self.log_result("http_api", api_success, 
                       f"HTTP API validation {'passed' if api_success else 'failed'}")
        return api_success
    
    def validate_control_interface(self) -> bool:
        """Validate control interface"""
        logger.info("Validating control interface...")
        
        try:
            control_port = self.config.get('receiver_control_port', 8081)
            
            # Test basic connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect(('localhost', control_port))
            
            # Send PING command
            sock.send(b"PING\n")
            response = sock.recv(1024).decode().strip()
            sock.close()
            
            if response == "OK":
                self.log_result("control_interface", True, 
                              f"Control interface responding on port {control_port}")
                return True
            else:
                self.log_result("control_interface", False, 
                              f"Unexpected response: {response}")
                return False
                
        except Exception as e:
            self.log_result("control_interface", False, 
                          f"Control interface test failed: {e}")
            return False
    
    def validate_message_processing(self) -> bool:
        """Validate message processing capabilities"""
        logger.info("Validating message processing...")
        
        try:
            # Get initial statistics
            response = requests.get("http://localhost:8080/api/stats", timeout=10)
            if response.status_code != 200:
                self.log_result("message_processing", False, "Cannot get initial stats")
                return False
            
            initial_stats = response.json()
            initial_messages = initial_stats.get('messages', {}).get('total_processed', 0)
            
            # Wait for some processing time
            time.sleep(10)
            
            # Get updated statistics
            response = requests.get("http://localhost:8080/api/stats", timeout=10)
            if response.status_code != 200:
                self.log_result("message_processing", False, "Cannot get updated stats")
                return False
            
            updated_stats = response.json()
            updated_messages = updated_stats.get('messages', {}).get('total_processed', 0)
            
            # Check if messages are being processed
            messages_processed = updated_messages - initial_messages
            decode_rate = updated_stats.get('messages', {}).get('decode_rate', 0)
            
            if messages_processed > 0:
                self.log_result("message_processing", True, 
                              f"Processed {messages_processed} messages, decode rate: {decode_rate:.1%}",
                              {'messages_processed': messages_processed, 'decode_rate': decode_rate})
                return True
            else:
                self.log_result("message_processing", False, 
                              "No messages processed in test period")
                return False
                
        except Exception as e:
            self.log_result("message_processing", False, 
                          f"Message processing validation failed: {e}")
            return False
    
    def validate_aircraft_tracking(self) -> bool:
        """Validate aircraft tracking functionality"""
        logger.info("Validating aircraft tracking...")
        
        try:
            # Get aircraft data
            response = requests.get("http://localhost:8080/data/aircraft.json", timeout=10)
            if response.status_code != 200:
                self.log_result("aircraft_tracking", False, "Cannot get aircraft data")
                return False
            
            aircraft_data = response.json()
            aircraft_list = aircraft_data.get('aircraft', [])
            
            # Check enhanced aircraft data
            response = requests.get("http://localhost:8080/data/aircraft_enhanced.json", timeout=10)
            if response.status_code == 200:
                enhanced_data = response.json()
                enhanced_aircraft = enhanced_data.get('aircraft', [])
                
                self.log_result("aircraft_tracking", True, 
                              f"Tracking {len(aircraft_list)} aircraft ({len(enhanced_aircraft)} enhanced)",
                              {'aircraft_count': len(aircraft_list), 'enhanced_count': len(enhanced_aircraft)})
                
                # Validate aircraft data structure
                if aircraft_list:
                    sample_aircraft = aircraft_list[0]
                    required_fields = ['hex', 'flight', 'lat', 'lon', 'alt_baro']
                    has_required_fields = all(field in sample_aircraft for field in required_fields)
                    
                    self.log_result("aircraft_data_structure", has_required_fields,
                                  f"Aircraft data structure {'valid' if has_required_fields else 'invalid'}")
                
                return True
            else:
                self.log_result("aircraft_tracking", False, "Cannot get enhanced aircraft data")
                return False
                
        except Exception as e:
            self.log_result("aircraft_tracking", False, 
                          f"Aircraft tracking validation failed: {e}")
            return False
    
    def validate_watchlist_functionality(self) -> bool:
        """Validate watchlist monitoring"""
        logger.info("Validating watchlist functionality...")
        
        try:
            # Check if watchlist is configured
            target_icao_codes = self.config.get('target_icao_codes', [])
            
            if not target_icao_codes:
                self.log_result("watchlist_config", True, "No watchlist configured (optional)")
                return True
            
            # Get system status to check watchlist
            response = requests.get("http://localhost:8080/api/status", timeout=10)
            if response.status_code != 200:
                self.log_result("watchlist_functionality", False, "Cannot get system status")
                return False
            
            status_data = response.json()
            watchlist_size = status_data.get('watchlist_size', 0)
            
            if watchlist_size == len(target_icao_codes):
                self.log_result("watchlist_functionality", True, 
                              f"Watchlist configured with {watchlist_size} entries")
                return True
            else:
                self.log_result("watchlist_functionality", False, 
                              f"Watchlist size mismatch: {watchlist_size} != {len(target_icao_codes)}")
                return False
                
        except Exception as e:
            self.log_result("watchlist_functionality", False, 
                          f"Watchlist validation failed: {e}")
            return False
    
    def validate_performance(self) -> bool:
        """Validate system performance"""
        logger.info("Validating system performance...")
        
        try:
            # Get performance metrics
            response = requests.get("http://localhost:8080/api/stats", timeout=10)
            if response.status_code != 200:
                self.log_result("performance", False, "Cannot get performance stats")
                return False
            
            stats = response.json()
            
            # Check message processing rate
            messages_per_second = stats.get('messages', {}).get('messages_per_second', 0)
            decode_rate = stats.get('messages', {}).get('decode_rate', 0)
            
            # Check source connectivity
            sources = stats.get('sources', {})
            sources_connected = sources.get('connected', 0)
            sources_total = sources.get('total', 0)
            
            # Performance thresholds
            performance_ok = True
            performance_details = []
            
            if messages_per_second < 1:
                performance_details.append(f"Low message rate: {messages_per_second:.1f}/s")
                performance_ok = False
            else:
                performance_details.append(f"Message rate: {messages_per_second:.1f}/s")
            
            if decode_rate < 0.5:  # Less than 50% decode rate might indicate issues
                performance_details.append(f"Low decode rate: {decode_rate:.1%}")
            else:
                performance_details.append(f"Decode rate: {decode_rate:.1%}")
            
            if sources_connected == 0:
                performance_details.append("No sources connected")
                performance_ok = False
            else:
                performance_details.append(f"Sources: {sources_connected}/{sources_total}")
            
            self.log_result("performance", performance_ok, 
                          "; ".join(performance_details),
                          {
                              'messages_per_second': messages_per_second,
                              'decode_rate': decode_rate,
                              'sources_connected': sources_connected
                          })
            
            return performance_ok
            
        except Exception as e:
            self.log_result("performance", False, f"Performance validation failed: {e}")
            return False
    
    def validate_error_handling(self) -> bool:
        """Validate error handling and recovery"""
        logger.info("Validating error handling...")
        
        try:
            # Test invalid API endpoints
            invalid_endpoints = [
                '/invalid/endpoint',
                '/data/nonexistent.json',
                '/api/invalid'
            ]
            
            error_handling_ok = True
            
            for endpoint in invalid_endpoints:
                response = requests.get(f"http://localhost:8080{endpoint}", timeout=5)
                if response.status_code == 404:
                    self.log_result(f"error_handling_{endpoint.replace('/', '_')}", True, 
                                  f"Correctly returned 404 for {endpoint}")
                else:
                    self.log_result(f"error_handling_{endpoint.replace('/', '_')}", False, 
                                  f"Unexpected status {response.status_code} for {endpoint}")
                    error_handling_ok = False
            
            # Test malformed requests
            try:
                response = requests.get("http://localhost:8080/data/aircraft.json?invalid=param", timeout=5)
                # Should handle gracefully, either 200 (ignoring param) or 400 (bad request)
                if response.status_code in [200, 400]:
                    self.log_result("error_handling_malformed", True, 
                                  f"Handled malformed request: {response.status_code}")
                else:
                    self.log_result("error_handling_malformed", False, 
                                  f"Unexpected response to malformed request: {response.status_code}")
                    error_handling_ok = False
            except Exception:
                self.log_result("error_handling_malformed", False, "Server crashed on malformed request")
                error_handling_ok = False
            
            self.log_result("error_handling", error_handling_ok, 
                          f"Error handling {'passed' if error_handling_ok else 'failed'}")
            return error_handling_ok
            
        except Exception as e:
            self.log_result("error_handling", False, f"Error handling validation failed: {e}")
            return False
    
    def validate_backward_compatibility(self) -> bool:
        """Validate backward compatibility with existing features"""
        logger.info("Validating backward compatibility...")
        
        try:
            # Test legacy aircraft.json format
            response = requests.get("http://localhost:8080/data/aircraft.json", timeout=10)
            if response.status_code != 200:
                self.log_result("backward_compatibility", False, "Legacy aircraft endpoint failed")
                return False
            
            data = response.json()
            
            # Check required legacy fields
            required_fields = ['now', 'messages', 'aircraft']
            has_required_fields = all(field in data for field in required_fields)
            
            if not has_required_fields:
                self.log_result("backward_compatibility", False, 
                              f"Missing legacy fields: {[f for f in required_fields if f not in data]}")
                return False
            
            # Check aircraft data format
            if data['aircraft']:
                sample_aircraft = data['aircraft'][0]
                legacy_aircraft_fields = ['hex', 'flight', 'alt_baro', 'gs', 'track', 'lat', 'lon']
                has_legacy_fields = any(field in sample_aircraft for field in legacy_aircraft_fields)
                
                if not has_legacy_fields:
                    self.log_result("backward_compatibility", False, "Aircraft data missing legacy fields")
                    return False
            
            self.log_result("backward_compatibility", True, 
                          "Legacy API format maintained")
            return True
            
        except Exception as e:
            self.log_result("backward_compatibility", False, 
                          f"Backward compatibility validation failed: {e}")
            return False
    
    def run_comprehensive_validation(self) -> bool:
        """Run complete system validation"""
        logger.info("Starting comprehensive system validation")
        logger.info("=" * 60)
        
        validation_steps = [
            ("Dependencies", self.validate_dependencies),
            ("Configuration", self.validate_configuration),
            ("Server Startup", self.start_test_server),
            ("HTTP API", self.validate_http_api),
            ("Control Interface", self.validate_control_interface),
            ("Message Processing", self.validate_message_processing),
            ("Aircraft Tracking", self.validate_aircraft_tracking),
            ("Watchlist Functionality", self.validate_watchlist_functionality),
            ("Performance", self.validate_performance),
            ("Error Handling", self.validate_error_handling),
            ("Backward Compatibility", self.validate_backward_compatibility)
        ]
        
        passed_tests = 0
        total_tests = len(validation_steps)
        
        try:
            for step_name, step_func in validation_steps:
                logger.info(f"\n--- {step_name} ---")
                
                try:
                    if step_func():
                        passed_tests += 1
                        logger.info(f"✅ {step_name} PASSED")
                    else:
                        logger.error(f"❌ {step_name} FAILED")
                except Exception as e:
                    logger.error(f"❌ {step_name} ERROR: {e}")
                    self.log_result(step_name.lower().replace(' ', '_'), False, f"Exception: {e}")
                
                # Brief pause between tests
                time.sleep(1)
        
        finally:
            # Always stop the test server
            self.stop_test_server()
        
        # Calculate overall results
        success_rate = passed_tests / total_tests
        overall_success = success_rate >= 0.8  # 80% pass rate required
        
        logger.info("\n" + "=" * 60)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Tests Passed: {passed_tests}/{total_tests} ({success_rate:.1%})")
        logger.info(f"Overall Result: {'✅ PASS' if overall_success else '❌ FAIL'}")
        logger.info(f"Validation Time: {(datetime.now() - self.start_time).total_seconds():.1f} seconds")
        
        return overall_success
    
    def generate_report(self) -> str:
        """Generate detailed validation report"""
        report_lines = [
            "Ursine Explorer ADS-B System Validation Report",
            "=" * 50,
            f"Generated: {datetime.now().isoformat()}",
            f"Configuration: {self.config_path}",
            f"Total Tests: {len(self.validation_results)}",
            ""
        ]
        
        # Summary
        passed = sum(1 for r in self.validation_results.values() if r['success'])
        failed = len(self.validation_results) - passed
        
        report_lines.extend([
            "SUMMARY:",
            f"  Passed: {passed}",
            f"  Failed: {failed}",
            f"  Success Rate: {passed/len(self.validation_results):.1%}",
            ""
        ])
        
        # Detailed results
        report_lines.append("DETAILED RESULTS:")
        for test_name, result in self.validation_results.items():
            status = "PASS" if result['success'] else "FAIL"
            report_lines.append(f"  [{status}] {test_name}: {result['details']}")
            
            if result['metrics']:
                for metric, value in result['metrics'].items():
                    report_lines.append(f"    {metric}: {value}")
        
        return "\n".join(report_lines)
    
    def save_report(self, filename: str = None):
        """Save validation report to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"validation_report_{timestamp}.txt"
        
        report = self.generate_report()
        
        with open(filename, 'w') as f:
            f.write(report)
        
        logger.info(f"Validation report saved to: {filename}")
        return filename


def main():
    """Main validation function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ursine Explorer ADS-B System Validator')
    parser.add_argument('--config', '-c', default='config.json', help='Configuration file path')
    parser.add_argument('--report', '-r', help='Save report to specific file')
    parser.add_argument('--quick', '-q', action='store_true', help='Quick validation (skip long tests)')
    
    args = parser.parse_args()
    
    print("Ursine Explorer ADS-B System Validation")
    print("=" * 50)
    
    validator = SystemValidator(args.config)
    
    try:
        success = validator.run_comprehensive_validation()
        
        # Generate and save report
        report_file = validator.save_report(args.report)
        
        print(f"\nValidation report saved to: {report_file}")
        
        if success:
            print("\n🎉 System validation PASSED!")
            print("The integrated ADS-B system is ready for production use.")
            sys.exit(0)
        else:
            print("\n⚠️  System validation FAILED!")
            print("Please review the validation report and fix identified issues.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\nValidation interrupted by user")
        validator.stop_test_server()
        sys.exit(1)
    except Exception as e:
        print(f"\nValidation error: {e}")
        validator.stop_test_server()
        sys.exit(1)


if __name__ == "__main__":
    main()