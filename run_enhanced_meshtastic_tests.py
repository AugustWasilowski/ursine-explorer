#!/usr/bin/env python3
"""
Simple test runner for enhanced Meshtastic unit tests

This script runs all the unit tests for the enhanced Meshtastic components
and provides a summary of results.
"""

import sys
import os
import unittest
import importlib

# Add the pymodes_integration directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'pymodes_integration'))

def run_test_module(module_name):
    """Run tests from a specific module"""
    try:
        module = importlib.import_module(f'pymodes_integration.meshtastic_enhanced.{module_name}')
        loader = unittest.TestLoader()
        suite = loader.loadTestsFromModule(module)
        runner = unittest.TextTestRunner(verbosity=1)
        result = runner.run(suite)
        return result.wasSuccessful(), result.testsRun, len(result.failures), len(result.errors)
    except ImportError as e:
        print(f"Could not import {module_name}: {e}")
        return False, 0, 0, 1

def main():
    """Run all enhanced Meshtastic unit tests"""
    print("Enhanced Meshtastic Integration - Unit Test Suite")
    print("=" * 60)
    
    # Test modules to run
    test_modules = [
        'test_foundation',
        'test_channel_manager', 
        'test_encryption',
        'test_mqtt_interface',
        'test_message_routing',
        'test_message_formatter',
        'test_position_formatter',
        'test_diagnostics',
        'test_enhanced_serial_interface',
        'test_utils'
    ]
    
    total_tests = 0
    total_failures = 0
    total_errors = 0
    successful_modules = 0
    
    for module_name in test_modules:
        print(f"\nRunning {module_name}...")
        success, tests, failures, errors = run_test_module(module_name)
        
        total_tests += tests
        total_failures += failures
        total_errors += errors
        
        if success:
            successful_modules += 1
            print(f"✓ {module_name}: {tests} tests passed")
        else:
            print(f"✗ {module_name}: {tests} tests, {failures} failures, {errors} errors")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Modules: {successful_modules}/{len(test_modules)} passed")
    print(f"Total Tests: {total_tests}")
    print(f"Failures: {total_failures}")
    print(f"Errors: {total_errors}")
    
    overall_success = total_failures == 0 and total_errors == 0
    if overall_success:
        print("✓ ALL UNIT TESTS PASSED")
        return 0
    else:
        print("✗ SOME TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())