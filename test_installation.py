#!/usr/bin/env python3
"""
Test script to verify Options Trading Bot installation
"""
import sys
import os
import importlib

def test_imports():
    """Test if all required modules can be imported"""
    print("🔍 Testing imports...")
    
    required_modules = [
        'streamlit',
        'pandas',
        'plotly',
        'kiteconnect',
        'scipy',
        'numpy',
        'dotenv'
    ]
    
    failed_imports = []
    
    for module in required_modules:
        try:
            importlib.import_module(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            failed_imports.append(module)
    
    return len(failed_imports) == 0

def test_project_modules():
    """Test if project modules can be imported"""
    print("\n🔍 Testing project modules...")
    
    # Add src to path
    sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))
    
    project_modules = [
        'src.kite_client',
        'src.options_calculator',
        'src.trading_bot',
        'src.utils',
        'config'
    ]
    
    failed_imports = []
    
    for module in project_modules:
        try:
            importlib.import_module(module)
            print(f"✅ {module}")
        except ImportError as e:
            print(f"❌ {module}: {e}")
            failed_imports.append(module)
    
    return len(failed_imports) == 0

def test_configuration():
    """Test configuration loading"""
    print("\n🔍 Testing configuration...")
    
    try:
        from config import TARGET_DELTA_LOW, TARGET_DELTA_HIGH, STOP_LOSS_CONFIG
        print(f"✅ Delta range: {TARGET_DELTA_LOW} - {TARGET_DELTA_HIGH}")
        print(f"✅ Stop loss config: {len(STOP_LOSS_CONFIG)} days configured")
        return True
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        return False

def test_environment():
    """Test environment setup"""
    print("\n🔍 Testing environment...")
    
    env_file = ".env"
    if os.path.exists(env_file):
        print(f"✅ Environment file exists: {env_file}")
        return True
    else:
        print(f"⚠️ Environment file not found: {env_file}")
        print("   Run: cp env_example.txt .env")
        return False

def main():
    print("🧪 Options Trading Bot - Installation Test")
    print("=" * 50)
    
    all_tests_passed = True
    
    # Test imports
    if not test_imports():
        all_tests_passed = False
    
    # Test project modules
    if not test_project_modules():
        all_tests_passed = False
    
    # Test configuration
    if not test_configuration():
        all_tests_passed = False
    
    # Test environment
    if not test_environment():
        all_tests_passed = False
    
    print("\n" + "=" * 50)
    if all_tests_passed:
        print("🎉 All tests passed! Installation is successful.")
        print("\n📋 You can now:")
        print("1. Run the web interface: streamlit run app.py")
        print("2. Run the CLI: python main.py")
    else:
        print("❌ Some tests failed. Please check the errors above.")
        print("\n🔧 Try running: python setup.py")

if __name__ == "__main__":
    main()
