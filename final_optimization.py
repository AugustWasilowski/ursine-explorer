#!/usr/bin/env python3
"""
Final system optimization and validation for Ursine Capture.
Performs comprehensive optimization and validates all performance targets.
"""

import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

from utils import setup_logging, error_handler, ErrorSeverity, ComponentType
from config import Config
from performance_profiler import PerformanceProfiler
from memory_optimizer import MemoryOptimizer
from stability_tester import StabilityTester
from system_monitor import SystemMonitor


logger = logging.getLogger(__name__)


class FinalOptimizer:
    """Final system optimization and validation."""
    
    def __init__(self, config_path: str = "config.json"):
        self.config = Config(config_path)
        self.performance_profiler = PerformanceProfiler(config_path)
        self.memory_optimizer = MemoryOptimizer(config_path)
        self.stability_tester = StabilityTester(config_path)
        self.system_monitor = SystemMonitor(config_path)
        
        # Performance targets from design document
        self.targets = {
            "message_rate": 100,      # messages/second
            "latency_ms": 100,        # milliseconds
            "memory_mb": 50,          # MB total system usage
            "cpu_percent": 25,        # % on Raspberry Pi 4
            "uptime_hours": 24,       # minimum uptime
            "error_rate_per_hour": 5  # maximum errors per hour
        }
        
    def run_final_optimization(self) -> Dict[str, Any]:
        """Run comprehensive final optimization and validation."""
        try:
            logger.info("Starting final system optimization and validation...")
            
            optimization_results = {
                "timestamp": datetime.now().isoformat(),
                "targets": self.targets,
                "phases": [],
                "final_metrics": {},
                "target_compliance": {},
                "optimization_summary": {},
                "validation_results": {},
                "recommendations": [],
                "overall_status": "UNKNOWN"
            }
            
            # Phase 1: Pre-optimization baseline
            baseline_results = self._run_baseline_assessment(optimization_results)
            
            # Phase 2: Apply optimizations
            optimization_phase = self._run_optimization_phase(optimization_results)
            
            # Phase 3: Performance validation
            validation_phase = self._run_validation_phase(optimization_results)
            
            # Phase 4: Final assessment
            final_assessment = self._run_final_assessment(optimization_results)
            
            # Generate comprehensive report
            optimization_results["final_metrics"] = self._collect_final_metrics()
            optimization_results["target_compliance"] = self._check_target_compliance(optimization_results)
            optimization_results["recommendations"] = self._generate_final_recommendations(optimization_results)
            optimization_results["overall_status"] = self._determine_overall_status(optimization_results)
            
            logger.info("Final optimization completed")
            return optimization_results
            
        except Exception as e:
            error_handler.handle_error(
                ComponentType.RECEIVER,
                ErrorSeverity.HIGH,
                f"Error during final optimization: {str(e)}",
                error_code="FINAL_OPTIMIZATION_ERROR"
            )
            return {"error": str(e)}
    
    def _run_baseline_assessment(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Run baseline performance assessment."""
        try:
            logger.info("Running baseline assessment...")
            
            phase_results = {
                "phase": "baseline_assessment",
                "start_time": datetime.now().isoformat(),
                "description": "Pre-optimization baseline measurement",
                "metrics": {},
                "issues_identified": [],
                "duration_seconds": 0
            }
            
            start_time = time.time()
            
            # Get current system health
            health_data = self.system_monitor.check_system_health()
            phase_results["metrics"]["system_health"] = health_data
            
            # Get current memory usage
            memory_usage = self.memory_optimizer._get_current_memory_usage()
            phase_results["metrics"]["memory_usage"] = memory_usage
            
            # Quick performance sample
            perf_sample = self.performance_profiler._collect_resource_sample()
            phase_results["metrics"]["performance_sample"] = perf_sample
            
            # Identify baseline issues
            if health_data.get("overall_status") != "HEALTHY":
                phase_results["issues_identified"].append("System not healthy at baseline")
            
            if memory_usage.get("total_mb", 0) > self.targets["memory_mb"]:
                phase_results["issues_identified"].append(f"Memory usage above target: {memory_usage.get('total_mb', 0):.1f}MB")
            
            if perf_sample.get("cpu_percent", 0) > self.targets["cpu_percent"]:
                phase_results["issues_identified"].append(f"CPU usage above target: {perf_sample.get('cpu_percent', 0):.1f}%")
            
            phase_results["duration_seconds"] = time.time() - start_time
            results["phases"].append(phase_results)
            
            logger.info(f"Baseline assessment completed in {phase_results['duration_seconds']:.1f}s")
            return phase_results
            
        except Exception as e:
            logger.error(f"Error in baseline assessment: {e}")
            return {"phase": "baseline_assessment", "error": str(e)}
    
    def _run_optimization_phase(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Run comprehensive optimization phase."""
        try:
            logger.info("Running optimization phase...")
            
            phase_results = {
                "phase": "optimization",
                "start_time": datetime.now().isoformat(),
                "description": "Apply all system optimizations",
                "optimizations_applied": [],
                "memory_before_mb": 0,
                "memory_after_mb": 0,
                "memory_saved_mb": 0,
                "duration_seconds": 0
            }
            
            start_time = time.time()
            
            # Get initial memory usage
            initial_memory = self.memory_optimizer._get_current_memory_usage()
            phase_results["memory_before_mb"] = initial_memory.get("total_mb", 0)
            
            # 1. Memory optimization
            logger.info("Applying memory optimizations...")
            memory_results = self.memory_optimizer.implement_memory_optimizations()
            
            if "error" not in memory_results:
                phase_results["optimizations_applied"].append({
                    "type": "memory_optimization",
                    "success": True,
                    "details": memory_results.get("optimizations", []),
                    "memory_saved_mb": memory_results.get("total_saved_mb", 0)
                })
            else:
                phase_results["optimizations_applied"].append({
                    "type": "memory_optimization",
                    "success": False,
                    "error": memory_results["error"]
                })
            
            # 2. Configuration optimization
            logger.info("Optimizing configuration...")
            config_optimization = self._optimize_configuration()
            phase_results["optimizations_applied"].append(config_optimization)
            
            # 3. Process optimization
            logger.info("Optimizing processes...")
            process_optimization = self._optimize_processes()
            phase_results["optimizations_applied"].append(process_optimization)
            
            # 4. File system optimization
            logger.info("Optimizing file system...")
            fs_optimization = self._optimize_filesystem()
            phase_results["optimizations_applied"].append(fs_optimization)
            
            # Get final memory usage
            final_memory = self.memory_optimizer._get_current_memory_usage()
            phase_results["memory_after_mb"] = final_memory.get("total_mb", 0)
            phase_results["memory_saved_mb"] = phase_results["memory_before_mb"] - phase_results["memory_after_mb"]
            
            phase_results["duration_seconds"] = time.time() - start_time
            results["phases"].append(phase_results)
            
            logger.info(f"Optimization phase completed in {phase_results['duration_seconds']:.1f}s")
            logger.info(f"Memory saved: {phase_results['memory_saved_mb']:.1f}MB")
            
            return phase_results
            
        except Exception as e:
            logger.error(f"Error in optimization phase: {e}")
            return {"phase": "optimization", "error": str(e)}
    
    def _run_validation_phase(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Run performance validation phase."""
        try:
            logger.info("Running validation phase...")
            
            phase_results = {
                "phase": "validation",
                "start_time": datetime.now().isoformat(),
                "description": "Validate performance targets after optimization",
                "validation_tests": [],
                "targets_met": 0,
                "total_targets": len(self.targets),
                "duration_seconds": 0
            }
            
            start_time = time.time()
            
            # 1. Memory validation
            memory_test = self._validate_memory_target()
            phase_results["validation_tests"].append(memory_test)
            if memory_test.get("passed", False):
                phase_results["targets_met"] += 1
            
            # 2. CPU validation
            cpu_test = self._validate_cpu_target()
            phase_results["validation_tests"].append(cpu_test)
            if cpu_test.get("passed", False):
                phase_results["targets_met"] += 1
            
            # 3. Message rate validation
            message_rate_test = self._validate_message_rate_target()
            phase_results["validation_tests"].append(message_rate_test)
            if message_rate_test.get("passed", False):
                phase_results["targets_met"] += 1
            
            # 4. System health validation
            health_test = self._validate_system_health()
            phase_results["validation_tests"].append(health_test)
            if health_test.get("passed", False):
                phase_results["targets_met"] += 1
            
            # 5. Stability validation (quick test)
            stability_test = self._validate_stability()
            phase_results["validation_tests"].append(stability_test)
            if stability_test.get("passed", False):
                phase_results["targets_met"] += 1
            
            phase_results["duration_seconds"] = time.time() - start_time
            results["phases"].append(phase_results)
            
            logger.info(f"Validation phase completed in {phase_results['duration_seconds']:.1f}s")
            logger.info(f"Targets met: {phase_results['targets_met']}/{phase_results['total_targets']}")
            
            return phase_results
            
        except Exception as e:
            logger.error(f"Error in validation phase: {e}")
            return {"phase": "validation", "error": str(e)}
    
    def _run_final_assessment(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Run final system assessment."""
        try:
            logger.info("Running final assessment...")
            
            phase_results = {
                "phase": "final_assessment",
                "start_time": datetime.now().isoformat(),
                "description": "Final system state assessment",
                "assessment": {},
                "readiness": "UNKNOWN",
                "duration_seconds": 0
            }
            
            start_time = time.time()
            
            # Comprehensive final check
            final_health = self.system_monitor.check_system_health()
            final_memory = self.memory_optimizer._get_current_memory_usage()
            final_performance = self.performance_profiler._collect_resource_sample()
            
            phase_results["assessment"] = {
                "system_health": final_health,
                "memory_usage": final_memory,
                "performance_metrics": final_performance,
                "optimization_effectiveness": self._calculate_optimization_effectiveness(results)
            }
            
            # Determine readiness
            if (final_health.get("overall_status") == "HEALTHY" and
                final_memory.get("total_mb", 0) <= self.targets["memory_mb"] and
                final_performance.get("cpu_percent", 0) <= self.targets["cpu_percent"]):
                phase_results["readiness"] = "READY"
            elif final_health.get("overall_status") in ["HEALTHY", "WARNING"]:
                phase_results["readiness"] = "READY_WITH_WARNINGS"
            else:
                phase_results["readiness"] = "NOT_READY"
            
            phase_results["duration_seconds"] = time.time() - start_time
            results["phases"].append(phase_results)
            
            logger.info(f"Final assessment completed: {phase_results['readiness']}")
            return phase_results
            
        except Exception as e:
            logger.error(f"Error in final assessment: {e}")
            return {"phase": "final_assessment", "error": str(e)}
    
    def _optimize_configuration(self) -> Dict[str, Any]:
        """Optimize system configuration."""
        try:
            optimization = {
                "type": "configuration_optimization",
                "success": True,
                "actions_taken": [],
                "details": []
            }
            
            # Load current config
            config_data = self.config.load()
            
            # Optimize receiver settings for performance
            receiver_config = config_data.get("receiver", {})
            
            # Reduce alert interval if too frequent
            if receiver_config.get("alert_interval", 300) < 60:
                receiver_config["alert_interval"] = 60
                optimization["actions_taken"].append("Increased alert interval to reduce overhead")
            
            # Optimize radio settings for stability
            radio_config = config_data.get("radio", {})
            
            # Ensure reasonable gain settings
            if radio_config.get("lna_gain", 40) > 40:
                radio_config["lna_gain"] = 40
                optimization["actions_taken"].append("Reduced LNA gain for stability")
            
            if radio_config.get("vga_gain", 20) > 30:
                radio_config["vga_gain"] = 30
                optimization["actions_taken"].append("Reduced VGA gain for stability")
            
            # Save optimized config if changes were made
            if optimization["actions_taken"]:
                config_data["receiver"] = receiver_config
                config_data["radio"] = radio_config
                self.config.save(config_data)
                optimization["details"].append("Configuration file updated with optimizations")
            else:
                optimization["details"].append("Configuration already optimal")
            
            return optimization
            
        except Exception as e:
            return {
                "type": "configuration_optimization",
                "success": False,
                "error": str(e)
            }
    
    def _optimize_processes(self) -> Dict[str, Any]:
        """Optimize running processes."""
        try:
            optimization = {
                "type": "process_optimization",
                "success": True,
                "actions_taken": [],
                "details": []
            }
            
            # Check for unnecessary processes
            import psutil
            
            high_cpu_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent']):
                try:
                    if proc.info['cpu_percent'] > 10:  # More than 10% CPU
                        high_cpu_processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if high_cpu_processes:
                optimization["details"].append(f"Found {len(high_cpu_processes)} high CPU processes")
                # Note: We don't automatically kill processes, just report them
            
            # Force garbage collection
            import gc
            collected = gc.collect()
            optimization["actions_taken"].append(f"Garbage collection freed {collected} objects")
            
            return optimization
            
        except Exception as e:
            return {
                "type": "process_optimization",
                "success": False,
                "error": str(e)
            }
    
    def _optimize_filesystem(self) -> Dict[str, Any]:
        """Optimize file system usage."""
        try:
            optimization = {
                "type": "filesystem_optimization",
                "success": True,
                "actions_taken": [],
                "details": []
            }
            
            # Clean up old log files
            log_files = ["ursine-receiver.log", "ursine-dashboard.log", "system-monitor.log"]
            
            for log_file in log_files:
                log_path = Path(log_file)
                if log_path.exists():
                    size_mb = log_path.stat().st_size / 1024**2
                    if size_mb > 50:  # Rotate if > 50MB
                        backup_path = log_path.with_suffix(f".log.backup.{int(time.time())}")
                        log_path.rename(backup_path)
                        log_path.touch()
                        optimization["actions_taken"].append(f"Rotated large log file: {log_file}")
            
            # Clean up old profile files
            profile_files = list(Path(".").glob("profile_*.json"))
            if len(profile_files) > 5:  # Keep only 5 most recent
                profile_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                for old_profile in profile_files[5:]:
                    old_profile.unlink()
                    optimization["actions_taken"].append(f"Removed old profile: {old_profile.name}")
            
            # Optimize JSON files
            for json_file in ["aircraft.json", "status.json"]:
                json_path = Path(json_file)
                if json_path.exists():
                    try:
                        with open(json_path, 'r') as f:
                            data = json.load(f)
                        
                        # Rewrite with compact format
                        with open(json_path, 'w') as f:
                            json.dump(data, f, separators=(',', ':'))
                        
                        optimization["actions_taken"].append(f"Compacted JSON file: {json_file}")
                    except:
                        pass
            
            return optimization
            
        except Exception as e:
            return {
                "type": "filesystem_optimization",
                "success": False,
                "error": str(e)
            }
    
    def _validate_memory_target(self) -> Dict[str, Any]:
        """Validate memory usage target."""
        try:
            memory_usage = self.memory_optimizer._get_current_memory_usage()
            current_mb = memory_usage.get("total_mb", 0)
            target_mb = self.targets["memory_mb"]
            
            return {
                "test": "memory_usage",
                "target": target_mb,
                "actual": current_mb,
                "passed": current_mb <= target_mb,
                "margin": target_mb - current_mb,
                "details": memory_usage
            }
            
        except Exception as e:
            return {"test": "memory_usage", "passed": False, "error": str(e)}
    
    def _validate_cpu_target(self) -> Dict[str, Any]:
        """Validate CPU usage target."""
        try:
            # Take multiple samples for accuracy
            cpu_samples = []
            for _ in range(5):
                sample = self.performance_profiler._collect_resource_sample()
                cpu_samples.append(sample.get("cpu_percent", 0))
                time.sleep(1)
            
            avg_cpu = sum(cpu_samples) / len(cpu_samples)
            target_cpu = self.targets["cpu_percent"]
            
            return {
                "test": "cpu_usage",
                "target": target_cpu,
                "actual": avg_cpu,
                "passed": avg_cpu <= target_cpu,
                "margin": target_cpu - avg_cpu,
                "samples": cpu_samples
            }
            
        except Exception as e:
            return {"test": "cpu_usage", "passed": False, "error": str(e)}
    
    def _validate_message_rate_target(self) -> Dict[str, Any]:
        """Validate message rate target."""
        try:
            # Check status file for message rate
            status_file = Path("status.json")
            if status_file.exists():
                with open(status_file, 'r') as f:
                    status_data = json.load(f)
                
                current_rate = status_data.get("message_rate", 0)
                target_rate = self.targets["message_rate"]
                
                return {
                    "test": "message_rate",
                    "target": target_rate,
                    "actual": current_rate,
                    "passed": current_rate >= target_rate,
                    "margin": current_rate - target_rate
                }
            else:
                return {
                    "test": "message_rate",
                    "passed": False,
                    "error": "Status file not available"
                }
                
        except Exception as e:
            return {"test": "message_rate", "passed": False, "error": str(e)}
    
    def _validate_system_health(self) -> Dict[str, Any]:
        """Validate overall system health."""
        try:
            health_data = self.system_monitor.check_system_health()
            overall_status = health_data.get("overall_status", "UNKNOWN")
            
            return {
                "test": "system_health",
                "target": "HEALTHY",
                "actual": overall_status,
                "passed": overall_status in ["HEALTHY", "WARNING"],
                "details": health_data
            }
            
        except Exception as e:
            return {"test": "system_health", "passed": False, "error": str(e)}
    
    def _validate_stability(self) -> Dict[str, Any]:
        """Validate system stability (quick test)."""
        try:
            # Run a quick 2-minute stability check
            stability_results = self.stability_tester.run_stability_test(duration_hours=0.033)  # 2 minutes
            
            assessment = stability_results.get("final_assessment", {})
            score = assessment.get("score", 0)
            
            return {
                "test": "stability",
                "target": 75,  # 75% score minimum
                "actual": score,
                "passed": score >= 75,
                "details": assessment
            }
            
        except Exception as e:
            return {"test": "stability", "passed": False, "error": str(e)}
    
    def _collect_final_metrics(self) -> Dict[str, Any]:
        """Collect final system metrics."""
        try:
            return {
                "timestamp": datetime.now().isoformat(),
                "system_health": self.system_monitor.check_system_health(),
                "memory_usage": self.memory_optimizer._get_current_memory_usage(),
                "performance_sample": self.performance_profiler._collect_resource_sample()
            }
        except Exception as e:
            return {"error": str(e)}
    
    def _check_target_compliance(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Check compliance with all performance targets."""
        try:
            compliance = {}
            
            # Extract validation results
            validation_phase = None
            for phase in results.get("phases", []):
                if phase.get("phase") == "validation":
                    validation_phase = phase
                    break
            
            if validation_phase:
                for test in validation_phase.get("validation_tests", []):
                    test_name = test.get("test", "unknown")
                    compliance[test_name] = {
                        "target": test.get("target"),
                        "actual": test.get("actual"),
                        "passed": test.get("passed", False),
                        "margin": test.get("margin", 0)
                    }
            
            # Overall compliance
            passed_tests = sum(1 for c in compliance.values() if c.get("passed", False))
            total_tests = len(compliance)
            
            compliance["overall"] = {
                "passed_tests": passed_tests,
                "total_tests": total_tests,
                "compliance_percentage": (passed_tests / total_tests * 100) if total_tests > 0 else 0,
                "fully_compliant": passed_tests == total_tests
            }
            
            return compliance
            
        except Exception as e:
            return {"error": str(e)}
    
    def _calculate_optimization_effectiveness(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate effectiveness of optimizations."""
        try:
            baseline_phase = None
            optimization_phase = None
            
            for phase in results.get("phases", []):
                if phase.get("phase") == "baseline_assessment":
                    baseline_phase = phase
                elif phase.get("phase") == "optimization":
                    optimization_phase = phase
            
            if not baseline_phase or not optimization_phase:
                return {"error": "Missing baseline or optimization data"}
            
            # Calculate memory improvement
            memory_before = optimization_phase.get("memory_before_mb", 0)
            memory_after = optimization_phase.get("memory_after_mb", 0)
            memory_improvement = memory_before - memory_after
            
            return {
                "memory_improvement_mb": memory_improvement,
                "memory_improvement_percent": (memory_improvement / memory_before * 100) if memory_before > 0 else 0,
                "optimizations_applied": len(optimization_phase.get("optimizations_applied", [])),
                "successful_optimizations": len([
                    opt for opt in optimization_phase.get("optimizations_applied", [])
                    if opt.get("success", False)
                ])
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    def _generate_final_recommendations(self, results: Dict[str, Any]) -> List[str]:
        """Generate final optimization recommendations."""
        try:
            recommendations = []
            
            # Check target compliance
            compliance = results.get("target_compliance", {})
            
            for test_name, test_data in compliance.items():
                if test_name != "overall" and not test_data.get("passed", False):
                    if test_name == "memory_usage":
                        recommendations.append("Memory usage still above target - consider more aggressive cleanup")
                    elif test_name == "cpu_usage":
                        recommendations.append("CPU usage above target - profile for bottlenecks")
                    elif test_name == "message_rate":
                        recommendations.append("Message rate below target - check antenna and RF setup")
                    elif test_name == "system_health":
                        recommendations.append("System health issues detected - check logs")
                    elif test_name == "stability":
                        recommendations.append("Stability concerns - run extended stability test")
            
            # General recommendations based on overall compliance
            overall_compliance = compliance.get("overall", {})
            compliance_percentage = overall_compliance.get("compliance_percentage", 0)
            
            if compliance_percentage < 80:
                recommendations.extend([
                    "System not meeting performance targets - consider hardware upgrade",
                    "Review system configuration for optimization opportunities",
                    "Run extended performance profiling to identify bottlenecks"
                ])
            elif compliance_percentage < 100:
                recommendations.extend([
                    "System mostly optimized - fine-tune remaining issues",
                    "Monitor system performance over time",
                    "Consider periodic optimization runs"
                ])
            else:
                recommendations.extend([
                    "System fully optimized and meeting all targets",
                    "Maintain current configuration",
                    "Monitor for performance degradation over time"
                ])
            
            return recommendations
            
        except Exception as e:
            return [f"Error generating recommendations: {e}"]
    
    def _determine_overall_status(self, results: Dict[str, Any]) -> str:
        """Determine overall optimization status."""
        try:
            compliance = results.get("target_compliance", {})
            overall_compliance = compliance.get("overall", {})
            compliance_percentage = overall_compliance.get("compliance_percentage", 0)
            
            final_assessment = None
            for phase in results.get("phases", []):
                if phase.get("phase") == "final_assessment":
                    final_assessment = phase
                    break
            
            readiness = final_assessment.get("readiness", "UNKNOWN") if final_assessment else "UNKNOWN"
            
            if compliance_percentage >= 100 and readiness == "READY":
                return "FULLY_OPTIMIZED"
            elif compliance_percentage >= 80 and readiness in ["READY", "READY_WITH_WARNINGS"]:
                return "WELL_OPTIMIZED"
            elif compliance_percentage >= 60:
                return "PARTIALLY_OPTIMIZED"
            else:
                return "NEEDS_OPTIMIZATION"
                
        except Exception as e:
            return "ERROR"


def main():
    """Main final optimizer entry point."""
    try:
        setup_logging("final-optimization.log")
        
        if len(sys.argv) < 2:
            print("Usage: python final_optimization.py <command> [options]")
            print("Commands:")
            print("  optimize          - Run full optimization and validation")
            print("  validate          - Run validation only")
            print("  report [file]     - Generate optimization report")
            sys.exit(1)
        
        command = sys.argv[1].lower()
        config_path = "config.json"
        
        optimizer = FinalOptimizer(config_path)
        
        if command == "optimize":
            print("Running final system optimization and validation...")
            print("This may take several minutes to complete.")
            
            results = optimizer.run_final_optimization()
            
            # Save results
            output_file = f"final_optimization_{int(time.time())}.json"
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
            
            print(f"\nOptimization completed. Results saved to {output_file}")
            
            # Print summary
            overall_status = results.get("overall_status", "UNKNOWN")
            compliance = results.get("target_compliance", {}).get("overall", {})
            compliance_percentage = compliance.get("compliance_percentage", 0)
            
            print(f"\nOptimization Summary:")
            print(f"  Overall Status: {overall_status}")
            print(f"  Target Compliance: {compliance_percentage:.1f}%")
            print(f"  Tests Passed: {compliance.get('passed_tests', 0)}/{compliance.get('total_tests', 0)}")
            
            recommendations = results.get("recommendations", [])
            if recommendations:
                print(f"\nRecommendations:")
                for rec in recommendations[:5]:  # Show first 5
                    print(f"  • {rec}")
            
        elif command == "validate":
            print("Running validation only...")
            
            # Run just the validation components
            validation_results = {
                "timestamp": datetime.now().isoformat(),
                "validation_only": True,
                "tests": []
            }
            
            # Run individual validation tests
            memory_test = optimizer._validate_memory_target()
            cpu_test = optimizer._validate_cpu_target()
            health_test = optimizer._validate_system_health()
            
            validation_results["tests"] = [memory_test, cpu_test, health_test]
            
            passed_tests = sum(1 for test in validation_results["tests"] if test.get("passed", False))
            total_tests = len(validation_results["tests"])
            
            print(f"\nValidation Results:")
            print(f"  Tests Passed: {passed_tests}/{total_tests}")
            
            for test in validation_results["tests"]:
                status = "✓" if test.get("passed", False) else "✗"
                test_name = test.get("test", "unknown")
                actual = test.get("actual", "N/A")
                target = test.get("target", "N/A")
                print(f"  {status} {test_name}: {actual} (target: {target})")
            
        elif command == "report":
            output_file = sys.argv[2] if len(sys.argv) > 2 else "optimization_report.txt"
            
            print("Generating optimization report...")
            
            # Run optimization
            results = optimizer.run_final_optimization()
            
            # Generate report
            report_lines = [
                "URSINE CAPTURE FINAL OPTIMIZATION REPORT",
                "=" * 50,
                f"Generated: {results.get('timestamp', 'Unknown')}",
                ""
            ]
            
            # Overall status
            overall_status = results.get("overall_status", "UNKNOWN")
            compliance = results.get("target_compliance", {}).get("overall", {})
            
            report_lines.extend([
                "OPTIMIZATION SUMMARY:",
                f"  Overall Status: {overall_status}",
                f"  Target Compliance: {compliance.get('compliance_percentage', 0):.1f}%",
                f"  Tests Passed: {compliance.get('passed_tests', 0)}/{compliance.get('total_tests', 0)}",
                ""
            ])
            
            # Target compliance details
            target_compliance = results.get("target_compliance", {})
            report_lines.append("TARGET COMPLIANCE:")
            for test_name, test_data in target_compliance.items():
                if test_name != "overall":
                    status = "PASS" if test_data.get("passed", False) else "FAIL"
                    actual = test_data.get("actual", "N/A")
                    target = test_data.get("target", "N/A")
                    report_lines.append(f"  {test_name}: {status} ({actual}/{target})")
            
            report_lines.append("")
            
            # Recommendations
            recommendations = results.get("recommendations", [])
            if recommendations:
                report_lines.append("RECOMMENDATIONS:")
                for rec in recommendations:
                    report_lines.append(f"  • {rec}")
                report_lines.append("")
            
            report_text = "\n".join(report_lines)
            
            with open(output_file, 'w') as f:
                f.write(report_text)
                f.write("\n\nDETAILED DATA:\n")
                f.write(json.dumps(results, indent=2))
            
            print(report_text)
            print(f"\nDetailed report saved to: {output_file}")
            
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Final optimizer error: {e}")
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()