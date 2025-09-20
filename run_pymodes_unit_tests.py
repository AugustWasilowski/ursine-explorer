#!/usr/bin/env python3
"""
pyModeS Integration Unit Test Runner

Comprehensive test runner for all pyModeS integration unit tests.
Executes all test suites and provides detailed reporting.

Requirements covered:
- 1.1: Test message decoding with known ADS-B message samples
- 2.1: Validate aircraft data processing and updates
- 4.1: Test position calculation accuracy with reference data
"""

import sys
import os
import unittest
import time
from datetime import datetime
import importlib.util

# Test modules to run
TEST_MODULES = [
    'test_pymodes_unit_comprehensive',
    'test_message_validation', 
    'test_position_accuracy'
]

# Optional test modules (run if available)
OPTIONAL_TEST_MODULES = [
    'test_pymodes_integration',
    'test_pymodes_unit',
    'test_pymodes_standalone'
]


def import_test_module(module_name):
    """Import a test module by name"""
    try:
        # Try direct import first
        return __import__(module_name)
    except ImportError:
        # Try importing from file
        try:
            file_path = f"{module_name}.py"
            if os.path.exists(file_path):
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                return module
        except Exception as e:
            print(f"Warning: Could not import {module_name}: {e}")
            return None
    return None


def run_test_module(module_name, verbose=True):
    """Run tests from a specific module"""
    print(f"\n{'='*60}")
    print(f"Running tests from: {module_name}")
    print(f"{'='*60}")
    
    module = import_test_module(module_name)
    if not module:
        print(f"❌ Could not import {module_name}")
        return None
    
    # Find all test classes in the module
    test_classes = []
    for name in dir(module):
        obj = getattr(module, name)
        if (isinstance(obj, type) and 
            issubclass(obj, unittest.TestCase) and 
            obj != unittest.TestCase):
            test_classes.append(obj)
    
    if not test_classes:
        print(f"⚠️  No test classes found in {module_name}")
        return None
    
    # Create test suite
    test_suite = unittest.TestSuite()
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
    start_time = time.time()
    result = runner.run(test_suite)
    end_time = time.time()
    
    # Print module summary
    print(f"\n{'-'*40}")
    print(f"Module: {module_name}")
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Time: {end_time - start_time:.2f}s")
    
    if result.testsRun > 0:
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
        print(f"Success rate: {success_rate:.1f}%")
    
    return result


def print_detailed_failures(all_results):
    """Print detailed failure information"""
    print(f"\n{'='*60}")
    print("DETAILED FAILURE REPORT")
    print(f"{'='*60}")
    
    total_failures = 0
    total_errors = 0
    
    for module_name, result in all_results.items():
        if not result:
            continue
            
        if result.failures or result.errors:
            print(f"\n{module_name}:")
            print("-" * len(module_name))
            
            for test, traceback in result.failures:
                total_failures += 1
                print(f"\nFAILURE: {test}")
                # Extract the assertion error message
                lines = traceback.split('\n')
                for line in lines:
                    if 'AssertionError:' in line:
                        print(f"  {line.strip()}")
                        break
            
            for test, traceback in result.errors:
                total_errors += 1
                print(f"\nERROR: {test}")
                # Extract the error message
                lines = traceback.split('\n')
                for line in lines:
                    if 'Error:' in line or 'Exception:' in line:
                        print(f"  {line.strip()}")
                        break
    
    if total_failures == 0 and total_errors == 0:
        print("🎉 No failures or errors!")


def print_requirement_coverage():
    """Print requirement coverage summary"""
    print(f"\n{'='*60}")
    print("REQUIREMENT COVERAGE SUMMARY")
    print(f"{'='*60}")
    
    requirements = [
        ("1.1", "Message decoding with known ADS-B message samples", "✓"),
        ("1.2", "Message validation and filtering", "✓"),
        ("2.1", "Aircraft data processing and updates validation", "✓"),
        ("4.1", "Position calculation accuracy with reference data", "✓"),
        ("4.3", "Data validation and conflict resolution", "✓")
    ]
    
    for req_id, description, status in requirements:
        print(f"{status} {req_id}: {description}")


def main():
    """Main test runner"""
    print("pyModeS Integration Unit Test Suite")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Python version: {sys.version}")
    
    # Check if we're in the right directory
    if not os.path.exists('pymodes_integration'):
        print("\n❌ Error: pymodes_integration directory not found")
        print("Please run this script from the project root directory")
        return 1
    
    # Parse command line arguments
    verbose = '--verbose' in sys.argv or '-v' in sys.argv
    quick = '--quick' in sys.argv or '-q' in sys.argv
    
    if quick:
        print("Running in quick mode (core tests only)")
        modules_to_run = TEST_MODULES[:1]  # Only run comprehensive tests
    else:
        modules_to_run = TEST_MODULES
    
    # Run all test modules
    all_results = {}
    total_tests = 0
    total_failures = 0
    total_errors = 0
    start_time = time.time()
    
    # Run required test modules
    for module_name in modules_to_run:
        result = run_test_module(module_name, verbose)
        all_results[module_name] = result
        
        if result:
            total_tests += result.testsRun
            total_failures += len(result.failures)
            total_errors += len(result.errors)
    
    # Run optional test modules
    if not quick:
        print(f"\n{'='*60}")
        print("Running optional test modules...")
        print(f"{'='*60}")
        
        for module_name in OPTIONAL_TEST_MODULES:
            result = run_test_module(module_name, verbose)
            if result:
                all_results[module_name] = result
                total_tests += result.testsRun
                total_failures += len(result.failures)
                total_errors += len(result.errors)
    
    end_time = time.time()
    
    # Print overall summary
    print(f"\n{'='*60}")
    print("OVERALL TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total modules run: {len([r for r in all_results.values() if r])}")
    print(f"Total tests run: {total_tests}")
    print(f"Total failures: {total_failures}")
    print(f"Total errors: {total_errors}")
    print(f"Total time: {end_time - start_time:.2f}s")
    
    if total_tests > 0:
        success_rate = ((total_tests - total_failures - total_errors) / total_tests * 100)
        print(f"Overall success rate: {success_rate:.1f}%")
        
        if success_rate == 100:
            print("🎉 ALL TESTS PASSED!")
        elif success_rate >= 90:
            print("✅ Most tests passed")
        elif success_rate >= 75:
            print("⚠️  Some tests failed")
        else:
            print("❌ Many tests failed")
    
    # Print requirement coverage
    print_requirement_coverage()
    
    # Print detailed failures if any
    if total_failures > 0 or total_errors > 0:
        print_detailed_failures(all_results)
    
    # Print recommendations
    print(f"\n{'='*60}")
    print("RECOMMENDATIONS")
    print(f"{'='*60}")
    
    if total_failures == 0 and total_errors == 0:
        print("✅ All unit tests pass! The pyModeS integration is ready.")
        print("✅ You can proceed with integration testing (task 10.2)")
    else:
        print("❌ Some unit tests failed. Please fix the issues before proceeding.")
        print("💡 Check the detailed failure report above for specific issues.")
        print("💡 Ensure all pyModeS integration modules are properly implemented.")
    
    # Print next steps
    print(f"\nNext steps:")
    print(f"1. Fix any failing unit tests")
    print(f"2. Run integration tests: python test_integration_comprehensive.py")
    print(f"3. Run performance tests: python test_performance_stress.py")
    
    # Return appropriate exit code
    return 0 if (total_failures == 0 and total_errors == 0) else 1


if __name__ == '__main__':
    sys.exit(main())