"""
Command Line Interface for Options Trading Bot
"""
import argparse
import logging
from datetime import datetime
from src.trading_bot import TradingBot
from src.utils import setup_logging, load_environment, validate_inputs, cleanup_old_logs

def main():
    parser = argparse.ArgumentParser(description='Options Trading Bot CLI')
    parser.add_argument('--api-key', help='Kite API Key')
    parser.add_argument('--api-secret', help='Kite API Secret')
    parser.add_argument('--request-token', help='Kite Request Token')
    parser.add_argument('--account', help='Trading Account')
    parser.add_argument('--call-quantity', type=int, default=50, help='Call Quantity (default: 50)')
    parser.add_argument('--put-quantity', type=int, default=50, help='Put Quantity (default: 50)')
    parser.add_argument('--delta-low', type=float, default=0.29, help='Target Delta Low (default: 0.29)')
    parser.add_argument('--delta-high', type=float, default=0.35, help='Target Delta High (default: 0.35)')
    parser.add_argument('--env-file', help='Path to .env file')
    parser.add_argument('--cleanup-logs', action='store_true', help='Clean up old log files before starting')
    parser.add_argument('--log-days', type=int, default=30, help='Days to keep log files (default: 30)')
    
    args = parser.parse_args()
    
    # Load environment variables if .env file is specified
    if args.env_file:
        import os
        os.environ['ENV_FILE'] = args.env_file
    
    # Try to load from environment if not provided as arguments
    env_config = load_environment()
    
    api_key = args.api_key or env_config.get('api_key')
    api_secret = args.api_secret or env_config.get('api_secret')
    request_token = args.request_token or env_config.get('request_token')
    account = args.account or env_config.get('account')
    
    # Validate inputs
    errors = validate_inputs(api_key, api_secret, request_token, account, args.call_quantity, args.put_quantity)
    
    if errors:
        print("❌ Validation errors:")
        for error in errors:
            print(f"  - {error}")
        return
    
    # Clean up old logs if requested
    if args.cleanup_logs:
        print("🧹 Cleaning up old log files...")
        cleanup_old_logs(args.log_days)
        print()
    
    # Setup logging
    log_filename = setup_logging(account)
    print(f"📝 Logging to: {log_filename}")
    
    # Create and run bot
    try:
        print("🚀 Starting Options Trading Bot...")
        print(f"📊 Account: {account}")
        print(f"📈 Call Quantity: {args.call_quantity}")
        print(f"📉 Put Quantity: {args.put_quantity}")
        print(f"🎯 Delta Range: {args.delta_low:.2f} - {args.delta_high:.2f}")
        print(f"⏰ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("-" * 50)
        
        # Create bot instance first to get kite client
        bot = TradingBot(api_key, api_secret, request_token, account, args.call_quantity, args.put_quantity)
        
        # Display VIX summary before starting trading
        from src.utils import display_vix_summary
        display_vix_summary(bot.kite_client)
        
        bot.run()
        
    except KeyboardInterrupt:
        print("\n⏹️ Bot stopped by user")
    except Exception as e:
        print(f"❌ Bot error: {e}")
        logging.error(f"Bot error: {e}")

if __name__ == "__main__":
    main()
