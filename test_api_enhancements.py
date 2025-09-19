#!/usr/bin/env python3
"""
Test script for the enhanced HTTP API server
Tests the new endpoints, error handling, and rate limiting
"""

import requests
import json
import time
from datetime import datetime

def test_api_endpoints():
    """Test all the new API endpoints"""
    base_url = "http://localhost:8080"
    
    endpoints = [
        "/data/aircraft.json",
        "/data/aircraft_enhanced.json", 
        "/data/fft.json",
        "/api/status",
        "/api/stats",
        "/api/health",
        "/api/sources",
        "/api/decoder"
    ]
    
    print("Testing API Endpoints")
    print("=" * 50)
    
    for endpoint in endpoints:
        try:
            print(f"\nTesting {endpoint}...")
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            
            print(f"Status Code: {response.status_code}")
            print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
            print(f"Content-Length: {response.headers.get('Content-Length', 'N/A')}")
            print(f"Rate Limit Remaining: {response.headers.get('X-RateLimit-Remaining', 'N/A')}")
            print(f"API Version: {response.headers.get('X-API-Version', 'N/A')}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"Response keys: {list(data.keys())}")
                if 'aircraft' in data:
                    print(f"Aircraft count: {len(data['aircraft'])}")
                print("✓ Success")
            else:
                print(f"✗ Failed: {response.text}")
                
        except requests.exceptions.RequestException as e:
            print(f"✗ Connection error: {e}")
        except Exception as e:
            print(f"✗ Error: {e}")

def test_error_handling():
    """Test error handling and validation"""
    base_url = "http://localhost:8080"
    
    print("\n\nTesting Error Handling")
    print("=" * 50)
    
    # Test 404 error
    print("\nTesting 404 error...")
    try:
        response = requests.get(f"{base_url}/api/nonexistent", timeout=5)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 404:
            error_data = response.json()
            print(f"Error response: {json.dumps(error_data, indent=2)}")
            print("✓ 404 handling works")
        else:
            print("✗ Expected 404")
    except Exception as e:
        print(f"✗ Error: {e}")
    
    # Test parameter validation
    print("\nTesting parameter validation...")
    try:
        response = requests.get(f"{base_url}/api/stats?invalid_param=test", timeout=5)
        print(f"Status Code: {response.status_code}")
        if response.status_code == 400:
            error_data = response.json()
            print(f"Validation error: {error_data.get('message', 'N/A')}")
            print("✓ Parameter validation works")
        else:
            print("✗ Expected 400 for invalid parameter")
    except Exception as e:
        print(f"✗ Error: {e}")

def test_rate_limiting():
    """Test rate limiting functionality"""
    base_url = "http://localhost:8080"
    
    print("\n\nTesting Rate Limiting")
    print("=" * 50)
    
    print("Making rapid requests to test rate limiting...")
    
    # Make many requests quickly
    for i in range(10):
        try:
            response = requests.get(f"{base_url}/api/health", timeout=5)
            remaining = response.headers.get('X-RateLimit-Remaining', 'N/A')
            print(f"Request {i+1}: Status {response.status_code}, Remaining: {remaining}")
            
            if response.status_code == 429:
                print("✓ Rate limiting activated")
                rate_limit_data = response.json()
                print(f"Rate limit response: {json.dumps(rate_limit_data, indent=2)}")
                break
                
        except Exception as e:
            print(f"✗ Error on request {i+1}: {e}")
        
        time.sleep(0.1)  # Small delay between requests

def test_enhanced_aircraft_data():
    """Test the enhanced aircraft data endpoint"""
    base_url = "http://localhost:8080"
    
    print("\n\nTesting Enhanced Aircraft Data")
    print("=" * 50)
    
    try:
        # Test legacy endpoint
        print("Testing legacy aircraft endpoint...")
        response = requests.get(f"{base_url}/data/aircraft.json", timeout=5)
        if response.status_code == 200:
            legacy_data = response.json()
            print(f"Legacy aircraft count: {len(legacy_data.get('aircraft', []))}")
            if legacy_data.get('aircraft'):
                sample_aircraft = legacy_data['aircraft'][0]
                print(f"Legacy fields: {list(sample_aircraft.keys())}")
        
        # Test enhanced endpoint
        print("\nTesting enhanced aircraft endpoint...")
        response = requests.get(f"{base_url}/data/aircraft_enhanced.json", timeout=5)
        if response.status_code == 200:
            enhanced_data = response.json()
            print(f"Enhanced aircraft count: {len(enhanced_data.get('aircraft', []))}")
            print(f"Enhanced fields available: {list(enhanced_data.get('enhanced_fields', {}).keys())}")
            if enhanced_data.get('aircraft'):
                sample_aircraft = enhanced_data['aircraft'][0]
                print(f"Sample aircraft fields: {list(sample_aircraft.keys())}")
                if 'enhanced' in sample_aircraft:
                    print(f"Enhanced data fields: {list(sample_aircraft['enhanced'].keys())}")
        
        print("✓ Enhanced aircraft data endpoint works")
        
    except Exception as e:
        print(f"✗ Error testing enhanced aircraft data: {e}")

if __name__ == "__main__":
    print("ADS-B API Enhancement Test Suite")
    print("=" * 60)
    print(f"Test started at: {datetime.now().isoformat()}")
    
    test_api_endpoints()
    test_error_handling()
    test_rate_limiting()
    test_enhanced_aircraft_data()
    
    print(f"\nTest completed at: {datetime.now().isoformat()}")
    print("\nNote: Some tests may fail if the ADS-B server is not running")
    print("Start the server with: python3 adsb_receiver.py")