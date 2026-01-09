#!/usr/bin/env python3
"""
Trading Bot Runner Script
This script runs the main.py trading bot with API credentials from .env file and custom parameters.
Usage: python run_trading_bot.py --request-token TOKEN --call-quantity QTY --put-quantity QTY [--api-key KEY] [--api-secret SECRET]
"""

import subprocess
import sys
import os
import argparse
from datetime import datetime

# Import the environment loading function
try:
    from src.utils import load_environment
except ImportError:
    print("❌ Error: Cannot import load_environment from src.utils")
    print("Please make sure you're running this script from the correct directory")
    sys.exit(1)

def parse_arguments():
    """
    Parse command line arguments
    """
    parser = argparse.ArgumentParser(description='Run Options Trading Bot with API credentials from .env file')
    parser.add_argument('--request-token', required=True, help='Kite Request Token (Access Token)')
    parser.add_argument('--call-quantity', type=int, required=True, help='Call Quantity')
    parser.add_argument('--put-quantity', type=int, required=True, help='Put Quantity')
    parser.add_argument('--api-key', help='Kite API Key (overrides .env file value)')
    parser.add_argument('--api-secret', help='Kite API Secret (overrides .env file value)')
    parser.add_argument('--account', default='TRADING_ACCOUNT', help='Account identifier (default: TRADING_ACCOUNT)')
    parser.add_argument('--delta-low', type=float, default=0.29, help='Target Delta Low (default: 0.29)')
    parser.add_argument('--delta-high', type=float, default=0.35, help='Target Delta High (default: 0.35)')
    parser.add_argument('--cleanup-logs', action='store_true', help='Clean up old log files before starting')
    parser.add_argument('--log-days', type=int, default=30, help='Days to keep log files (default: 30)')
    
    return parser.parse_args()

def load_env_credentials():
    """
    Load API credentials from .env file
    """
    env_config = load_environment()
    
    api_key = env_config.get('api_key')
    api_secret = env_config.get('api_secret')
    
    if not api_key:
        print("❌ Error: KITE_API_KEY not found in .env file")
        print("Please create a .env file with your API credentials:")
        print("KITE_API_KEY=your_api_key_here")
        print("KITE_API_SECRET=your_api_secret_here")
        return None, None
    
    if not api_secret:
        print("❌ Error: KITE_API_SECRET not found in .env file")
        print("Please add KITE_API_SECRET to your .env file")
        return None, None
    
    return api_key, api_secret

def get_final_credentials(env_api_key, env_api_secret, args):
    """
    Get final API credentials, using command line args if provided, otherwise .env values
    """
    api_key = args.api_key if args.api_key else env_api_key
    api_secret = args.api_secret if args.api_secret else env_api_secret
    
    if not api_key:
        print("❌ Error: API Key not found")
        print("Please provide --api-key parameter or set KITE_API_KEY in .env file")
        return None, None
    
    if not api_secret:
        print("❌ Error: API Secret not found")
        print("Please provide --api-secret parameter or set KITE_API_SECRET in .env file")
        return None, None
    
    return api_key, api_secret

def run_trading_bot(args, api_key, api_secret):
    """
    Run the main.py trading bot with the provided parameters
    """
    
    # Build the command
    cmd = [
        sys.executable,  # Use the current Python interpreter
        "main.py",
        "--api-key", api_key,
        "--api-secret", api_secret,
        "--request-token", args.request_token,
        "--account", args.account,
        "--call-quantity", str(args.call_quantity),
        "--put-quantity", str(args.put_quantity),
        "--delta-low", str(args.delta_low),
        "--delta-high", str(args.delta_high),
        "--log-days", str(args.log_days)
    ]
    
    # Add optional parameters
    if args.cleanup_logs:
        cmd.append("--cleanup-logs")
    
    print("🚀 Starting Trading Bot...")
    print(f"📅 Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔑 API Key: {api_key[:8]}...{api_key[-4:]}")  # Show only first 8 and last 4 characters
    print(f"📊 Call Quantity: {args.call_quantity}")
    print(f"📉 Put Quantity: {args.put_quantity}")
    print(f"🎯 Delta Range: {args.delta_low:.2f} - {args.delta_high:.2f}")
    print(f"🏦 Account: {args.account}")
    print(f"🧹 Cleanup Logs: {args.cleanup_logs}")
    print("-" * 60)
    
    # Display VIX summary before starting
    try:
        from src.kite_client import KiteClient
        from src.utils import display_vix_summary
        
        # Create a temporary kite client for VIX display
        temp_kite = KiteClient(api_key, api_secret, request_token=args.request_token, account=args.account)
        display_vix_summary(temp_kite)
    except Exception as e:
        print(f"⚠️ Could not display VIX summary: {e}")
        print("-" * 60)
    
    try:
        # Run the main.py script
        result = subprocess.run(cmd, check=True, capture_output=False)
        print("\n✅ Trading bot completed successfully!")
        
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Trading bot failed with error code: {e.returncode}")
        return False
    except KeyboardInterrupt:
        print("\n⏹️ Trading bot stopped by user")
        return False
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        return False
    
    return True

def main():
    """
    Main function to run the trading bot
    """
    print("=" * 60)
    print("🤖 OPTIONS TRADING BOT RUNNER")
    print("=" * 60)
    
    # Parse command line arguments first
    try:
        args = parse_arguments()
    except SystemExit:
        print("\n💡 Example usage:")
        print("python run_trading_bot.py --request-token YOUR_TOKEN --call-quantity 50 --put-quantity 50")
        print("python run_trading_bot.py --api-key YOUR_KEY --api-secret YOUR_SECRET --request-token YOUR_TOKEN --call-quantity 50 --put-quantity 50")
        print("\n📝 Make sure your .env file contains:")
        print("KITE_API_KEY=your_api_key_here")
        print("KITE_API_SECRET=your_api_secret_here")
        return False
    
    # Load API credentials from .env file (if not provided as command line args)
    if not args.api_key or not args.api_secret:
        print("📁 Loading API credentials from .env file...")
        env_api_key, env_api_secret = load_env_credentials()
        
        if not env_api_key or not env_api_secret:
            return False
        
        print("✅ API credentials loaded from .env file!")
    else:
        print("🔑 Using API credentials from command line parameters...")
        env_api_key, env_api_secret = None, None
    
    # Get final credentials (command line args override .env values)
    api_key, api_secret = get_final_credentials(env_api_key, env_api_secret, args)
    
    if not api_key or not api_secret:
        return False
    
    print()
    
    # Check if main.py exists
    if not os.path.exists("main.py"):
        print("❌ Error: main.py not found in current directory")
        print("Please make sure you're running this script from the correct directory")
        return False
    
    # Run the trading bot
    success = run_trading_bot(args, api_key, api_secret)
    
    if success:
        print("\n🎉 Trading bot execution completed!")
    else:
        print("\n💥 Trading bot execution failed!")
    
    return success

if __name__ == "__main__":
    main()
