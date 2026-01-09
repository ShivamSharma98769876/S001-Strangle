#!/usr/bin/env python3
"""
Test script to debug parameter validation
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config_monitor import ConfigMonitor

def test_validation():
    """Test the validation function directly"""
    monitor = ConfigMonitor('config.py')
    
    # Test cases
    test_cases = [
        ('HEDGE_TRIGGER_POINTS_STRANGLE', '12'),
        ('HEDGE_TRIGGER_POINTS_STRANGLE', 12),
        ('HEDGE_TRIGGER_POINTS_STRANGLE', 12.0),
        ('HEDGE_TRIGGER_POINTS_STRANGLE', '11'),
        ('HEDGE_TRIGGER_POINTS_STRANGLE', 11),
    ]
    
    print("Testing parameter validation:")
    print("=" * 50)
    
    for param_name, value in test_cases:
        print(f"\nTesting: {param_name} = {value} (type: {type(value)})")
        result = monitor.validate_parameter(param_name, value)
        print(f"Result: {'VALID' if result else 'INVALID'}")
        
        if not result:
            print(f"❌ Validation failed for {param_name} = {value}")
        else:
            print(f"✅ Validation passed for {param_name} = {value}")

if __name__ == "__main__":
    test_validation()
