#!/usr/bin/env python3
"""
Wrapper script to run the trading bot from the root directory
"""
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import and run the main script
if __name__ == "__main__":
    try:
        # Import the main script
        import importlib.util
        spec = importlib.util.spec_from_file_location("main_script", "src/Straddle10PointswithSL-Limit.py")
        main_script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main_script)
        
        # Run the main function if it exists
        if hasattr(main_script, 'main'):
            main_script.main()
        else:
            print("Main function not found in the script")
    except Exception as e:
        print(f"Error running trading script: {e}")
        import traceback
        traceback.print_exc()
