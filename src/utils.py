"""
Utility functions for the trading bot
"""
import logging
import os
from datetime import date
from dotenv import load_dotenv

def setup_logging(account):
    """Setup logging configuration"""
    # Create Log directory if it doesn't exist
    log_dir = "Log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        print(f"Created Log directory: {log_dir}")
    
    # Create log filename with full path
    log_filename = os.path.join(log_dir, f'{account}_{date.today()}_trading_log.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    
    print(f"Log file created: {log_filename}")
    return log_filename

def load_environment():
    """Load environment variables from .env file"""
    load_dotenv()
    
    return {
        'api_key': os.getenv('KITE_API_KEY'),
        'api_secret': os.getenv('KITE_API_SECRET'),
        'request_token': os.getenv('KITE_REQUEST_TOKEN'),
        'account': os.getenv('KITE_ACCOUNT')
    }

def validate_inputs(api_key, api_secret, request_token, account, call_quantity, put_quantity):
    """Validate user inputs"""
    errors = []
    
    if not api_key:
        errors.append("API Key is required")
    if not api_secret:
        errors.append("API Secret is required")
    if not request_token:
        errors.append("Request Token is required")
    if not account:
        errors.append("Account is required")
    if not call_quantity or call_quantity <= 0:
        errors.append("Call quantity must be a positive number")
    if not put_quantity or put_quantity <= 0:
        errors.append("Put quantity must be a positive number")
    
    return errors

def format_currency(amount):
    """Format amount as currency"""
    return f"₹{amount:,.2f}"

def format_percentage(value):
    """Format value as percentage"""
    return f"{value:.2f}%"

def get_log_directory():
    """Get the log directory path"""
    return "Log"

def cleanup_old_logs(days_to_keep=30):
    """Clean up log files older than specified days"""
    import glob
    from datetime import datetime, timedelta
    
    log_dir = get_log_directory()
    if not os.path.exists(log_dir):
        return
    
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=days_to_keep)
    
    # Find all log files
    log_pattern = os.path.join(log_dir, "*.log")
    log_files = glob.glob(log_pattern)
    
    deleted_count = 0
    for log_file in log_files:
        try:
            # Get file modification time
            file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
            if file_time < cutoff_date:
                os.remove(log_file)
                deleted_count += 1
                print(f"Deleted old log file: {log_file}")
        except Exception as e:
            print(f"Error deleting log file {log_file}: {e}")
    
    if deleted_count > 0:
        print(f"Cleaned up {deleted_count} old log files")
    else:
        print("No old log files to clean up")

def display_vix_summary(kite_client, days=None):
    """
    Display VIX summary at program startup
    
    Args:
        kite_client: KiteClient instance
        days (int): Number of trading days for average calculation (defaults to config value)
    """
    try:
        from src.vix_calculator import VIXCalculator
        from config import VIX_HISTORICAL_DAYS
        
        if days is None:
            days = VIX_HISTORICAL_DAYS
        
        print("\n" + "="*60)
        print("📊 VIX ANALYSIS")
        print("="*60)
        
        vix_calc = VIXCalculator(kite_client)
        vix_summary = vix_calc.get_vix_summary(days)
        
        if vix_summary['average_vix'] is not None:
            print(f"📈 Current VIX: {vix_summary['current_vix']:.2f}")
            print(f"📊 Average VIX ({vix_summary['days_count']} days): {vix_summary['average_vix']:.2f}")
            print(f"📉 Trend: {vix_summary['trend_direction']} {vix_summary['trend']}")
            
            if vix_summary['difference'] != 0:
                print(f"📊 Difference: {vix_summary['difference']:+.2f} ({vix_summary['difference_percent']:+.1f}%)")
            
            # Display individual VIX values
            if vix_summary['vix_values']:
                print(f"📋 Last {len(vix_summary['vix_values'])} days VIX: {', '.join([f'{v:.2f}' for v in vix_summary['vix_values']])}")
            
            # Market sentiment based on VIX
            current_vix = vix_summary['current_vix']
            if current_vix:
                if current_vix < 15:
                    sentiment = "🟢 Low Volatility (Bullish)"
                elif current_vix < 25:
                    sentiment = "🟡 Moderate Volatility (Neutral)"
                elif current_vix < 35:
                    sentiment = "🟠 High Volatility (Caution)"
                else:
                    sentiment = "🔴 Very High Volatility (Bearish)"
                
                print(f"🎯 Market Sentiment: {sentiment}")
                
                # Display VIX-based delta recommendation
                try:
                    delta_recommendation = vix_calc.get_delta_recommendation()
                    print(f"\n📊 VIX-Based Delta Recommendation:")
                    print(f"   Delta Range: {delta_recommendation['delta_low']:.2f} - {delta_recommendation['delta_high']:.2f}")
                    print(f"   Hedge Points: {delta_recommendation['hedge_points']}")
                    print(f"   Next Week Expiry: {'Yes' if delta_recommendation['use_next_week_expiry'] else 'No'}")
                    print(f"   Reason: {delta_recommendation['reason']}")
                except Exception as e:
                    print(f"⚠️ Could not get delta recommendation: {e}")
        else:
            print("❌ Unable to fetch VIX data")
        
        print("="*60)
        print()
        
    except Exception as e:
        print(f"❌ Error displaying VIX summary: {e}")
        print("="*60)
        print()