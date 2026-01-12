from datetime import date, datetime, time, timedelta
import logging
from kiteconnect import KiteConnect
from scipy.stats import norm
import math
import time as time_module
import sys
import os
# Add parent directory and current directory to path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from config import *  # Import all configuration parameters

# Import environment detection and logging utilities
from environment import is_azure_environment, setup_logging, get_config_value, sanitize_account_name_for_filename, get_ist_time, format_ist_time, IST

# Import config monitoring system
from config_monitor import initialize_config_monitor, start_config_monitoring, stop_config_monitoring, get_config_monitor

# Import P&L recorder - must be after logging setup or handle import error gracefully
PnLRecorder = None
try:
    from pnl_recorder import PnLRecorder
except ImportError as e:
    # Logging might not be initialized yet, so use print or pass silently
    # The error will be handled when we try to use PnLRecorder
    pass

# Greek analysis removed - core trading functionality only

global Input_account, Input_api_key, Input_api_secret, Input_request_token
# client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
# client = openai.OpenAI(api_key="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")
# Input user account and API details - moved to main function
Input_account = None
Input_api_key = None
Input_api_secret = None
Input_request_token = None

api_key = None
api_secret = None
request_token = None
account = None

# Trading quantities
call_quantity = 1
put_quantity = 1
today_sl = 0

# Initialize Kite Connect API
kite = KiteConnect(api_key=api_key)
kite.set_access_token(request_token)

# Setup logging to file and console with Unicode handling
import sys

# Create a custom formatter that handles Unicode gracefully and uses IST timezone
class ISTFormatter(logging.Formatter):
    """Formatter that uses IST timezone for timestamps"""
    converter = lambda *args: get_ist_time().timetuple()
    
    def formatTime(self, record, datefmt=None):
        """Override formatTime to use IST"""
        ct = get_ist_time()
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            s = ct.strftime('%Y-%m-%d %H:%M:%S')
            # Add milliseconds
            s = f"{s},{int(record.msecs):03d}"
        return s

class SafeFormatter(ISTFormatter):
    """Formatter that safely handles Unicode characters and uses IST timezone"""
    def format(self, record):
        try:
            return super().format(record)
        except UnicodeEncodeError:
            # Fallback: replace problematic characters
            msg = record.getMessage()
            safe_msg = msg.encode('ascii', 'replace').decode('ascii')
            record.msg = safe_msg
            return super().format(record)

# Configure logging with safe Unicode handling and IST timezone
formatter = SafeFormatter('%(asctime)s - %(levelname)s - %(message)s')

# File handler with UTF-8 encoding - will be set in main function
file_handler = None

# Console handler with error handling
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[console_handler]
)

# Greek analysis removed - core trading functionality only

# Use configuration from config.py instead of hardcoded values
# TARGET_DELTA_LOW = 0.29  # Lower bound for target delta
# TARGET_DELTA_HIGH = 0.35  # Upper bound for target delta
stop_loss_trigger_count = 0  # Tracks stop-loss triggers
market_closed = False  # Flag to track if market has closed
# MAX_STOP_LOSS_TRIGGER = 3  # Max number of stop-loss triggers allowed

# VWAP Configuration - now imported from config.py
# VWAP_MINUTES = 5  # Number of minutes to calculate VWAP
# VWAP_ENABLED = True  # Enable/disable VWAP analysis
# VWAP_PRIORITY = True  # Prioritize strikes below VWAP

last_vix_fetch_time = None  # Track last time VIX was fetched
last_hedge_fetch_time = None  # Track last time VIX was fetched
india_vix = None  # Store fetched VIX value for reuse

# API Rate Limiting and Caching
last_api_call_time = None  # Track last API call time
option_chain_cache = None  # Cache for option chain data
option_chain_cache_time = None  # Cache timestamp
ltp_cache = {}  # Cache for LTP data
ltp_cache_time = {}  # Cache timestamps for LTP data
vwap_cache = {}  # Cache for VWAP data
vwap_cache_time = {}  # Cache timestamps for VWAP data

# Retry configuration for robust API calls
MAX_LTP_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 10.0
CONSECUTIVE_ERROR_THRESHOLD = 5  # Alert after this many consecutive errors
consecutive_ltp_errors = 0  # Track consecutive LTP fetch errors
last_error_alert_time = None  # Track last alert time for throttling

# Retryable error patterns (server-side/transient issues)
RETRYABLE_ERROR_PATTERNS = [
    "504",
    "502",
    "503",
    "gateway time-out",
    "gateway timeout",
    "connection reset",
    "connection refused",
    "connection timed out",
    "request failed",
    "kt-quotes",
    "couldn't parse the json",
    "server didn't respond",
    "too many requests",
    "rate limit",
    "network is unreachable",
    "temporary failure",
]


def is_retryable_error(error_message: str) -> bool:
    """Check if an error is retryable (transient/server-side)"""
    error_lower = error_message.lower()
    return any(pattern in error_lower for pattern in RETRYABLE_ERROR_PATTERNS)


def retry_api_call(api_func, *args, max_retries=MAX_LTP_RETRIES, **kwargs):
    """
    Execute an API call with exponential backoff retry logic.
    
    Args:
        api_func: API function to execute
        *args: Positional arguments to pass to api_func
        max_retries: Maximum number of retry attempts
        **kwargs: Keyword arguments to pass to api_func
        
    Returns:
        Result of api_func if successful
        
    Raises:
        Last exception if all retries fail
    """
    last_exception = None
    backoff = INITIAL_BACKOFF_SECONDS
    
    for attempt in range(max_retries + 1):
        try:
            return api_func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_msg = str(e)
            
            if not is_retryable_error(error_msg):
                # Non-retryable error, don't retry
                raise
            
            if attempt < max_retries:
                logging.warning(
                    f"Retryable API error (attempt {attempt + 1}/{max_retries + 1}): {error_msg}. "
                    f"Retrying in {backoff:.1f}s..."
                )
                time_module.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
    
    raise last_exception


def handle_ltp_error(symbol, error):
    """Handle LTP fetch errors with appropriate logging and alerting"""
    global consecutive_ltp_errors, last_error_alert_time
    
    error_msg = str(error)
    consecutive_ltp_errors += 1
    
    # Determine log level based on error type
    if is_retryable_error(error_msg):
        # Transient errors - log as warning (less noise)
        logging.warning(f"Transient error fetching LTP for {symbol}: {error_msg}")
    else:
        # Non-transient errors - log as error
        logging.error(f"Error fetching LTP for {symbol}: {error_msg}")
    
    # Alert if too many consecutive errors
    if consecutive_ltp_errors >= CONSECUTIVE_ERROR_THRESHOLD:
        current_time = datetime.now()
        error_alert_cooldown = 300  # Alert at most every 5 minutes
        should_alert = (
            last_error_alert_time is None or
            (current_time - last_error_alert_time).total_seconds() > error_alert_cooldown
        )
        
        if should_alert:
            logging.error(
                f"⚠️ ALERT: {consecutive_ltp_errors} consecutive LTP fetch errors! "
                f"Kite API may be experiencing issues. Last error: {error_msg}"
            )
            last_error_alert_time = current_time


def reset_ltp_error_counter():
    """Reset the consecutive LTP error counter on successful fetch"""
    global consecutive_ltp_errors
    consecutive_ltp_errors = 0


def enforce_rate_limit():
    """Enforce rate limiting between API calls"""
    global last_api_call_time
    if last_api_call_time is not None:
        time_since_last_call = (datetime.now() - last_api_call_time).total_seconds()
        if time_since_last_call < API_RATE_LIMIT_DELAY:
            sleep_time = API_RATE_LIMIT_DELAY - time_since_last_call
            logging.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time_module.sleep(sleep_time)
    last_api_call_time = datetime.now()

def clear_old_cache():
    """Clear old cache entries to prevent memory issues"""
    global ltp_cache, ltp_cache_time, vwap_cache, vwap_cache_time
    
    current_time = datetime.now()
    
    # Clear old LTP cache entries
    expired_ltp_keys = [key for key, timestamp in ltp_cache_time.items() 
                        if (current_time - timestamp).total_seconds() > LTP_CACHE_DURATION * 2]
    for key in expired_ltp_keys:
        del ltp_cache[key]
        del ltp_cache_time[key]
    
    # Clear old VWAP cache entries
    expired_vwap_keys = [key for key, timestamp in vwap_cache_time.items() 
                         if (current_time - timestamp).total_seconds() > VWAP_CACHE_DURATION * 2]
    for key in expired_vwap_keys:
        del vwap_cache[key]
        del vwap_cache_time[key]
    
    if expired_ltp_keys or expired_vwap_keys:
        logging.debug(f"Cleared {len(expired_ltp_keys)} LTP and {len(expired_vwap_keys)} VWAP cache entries")

def fetch_option_chain():
    """Fetch NIFTY option chain data with caching, retry logic, and rate limiting"""
    global option_chain_cache, option_chain_cache_time
    
    # Check cache first
    if (option_chain_cache is not None and 
        option_chain_cache_time is not None and
        (datetime.now() - option_chain_cache_time).total_seconds() < OPTION_CHAIN_CACHE_DURATION):
        logging.info(f"Using cached option chain data (age: {(datetime.now() - option_chain_cache_time).total_seconds():.0f}s)")
        return option_chain_cache
    
    # Enforce rate limiting
    enforce_rate_limit()
    
    logging.info("Fetching option chain data")
    backoff = INITIAL_BACKOFF_SECONDS
    
    for attempt in range(API_MAX_RETRIES):
        try:
            instrument = 'NIFTY'
            instruments = kite.instruments('NFO')
            options = [i for i in instruments if i['segment'] == 'NFO-OPT' and i.get('name') == instrument]
            
            # Update cache
            option_chain_cache = options
            option_chain_cache_time = datetime.now()
            
            logging.info(f"Fetched {len(options)} options")
            return options
            
        except Exception as e:
            error_msg = str(e)
            
            if is_retryable_error(error_msg):
                if attempt < API_MAX_RETRIES - 1:
                    logging.warning(
                        f"Retryable error fetching option chain (attempt {attempt + 1}/{API_MAX_RETRIES}): {error_msg}. "
                        f"Retrying in {backoff:.1f}s..."
                    )
                    time_module.sleep(backoff)
                    backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                    continue
                else:
                    logging.warning(f"All {API_MAX_RETRIES} attempts failed. Using cached data if available.")
                    if option_chain_cache is not None:
                        cache_age = (datetime.now() - option_chain_cache_time).total_seconds()
                        logging.info(f"Returning cached option chain data (age: {cache_age:.0f}s)")
                        return option_chain_cache
                    else:
                        logging.error("No cached option chain data available")
                        return []
            else:
                logging.error(f"Non-retryable error fetching option chain: {error_msg}")
                # Still try cached data for any error
                if option_chain_cache is not None:
                    logging.info("Returning cached option chain data due to error")
                    return option_chain_cache
                return []
    
    return []


def get_cached_ltp(symbol):
    """Get LTP with caching, retry logic, and graceful error handling"""
    global ltp_cache, ltp_cache_time
    
    current_time = datetime.now()
    
    # Check cache first
    if (symbol in ltp_cache and 
        symbol in ltp_cache_time and
        (current_time - ltp_cache_time[symbol]).total_seconds() < LTP_CACHE_DURATION):
        logging.debug(f"Using cached LTP for {symbol}: {ltp_cache[symbol]}")
        return ltp_cache[symbol]
    
    # Enforce rate limiting
    enforce_rate_limit()
    
    try:
        # Use retry logic for API call
        ltp_data = retry_api_call(kite.ltp, symbol)
        ltp = ltp_data[symbol]['last_price']
        
        # Update cache
        ltp_cache[symbol] = ltp
        ltp_cache_time[symbol] = current_time
        
        # Reset error counter on success
        reset_ltp_error_counter()
        
        logging.debug(f"Fetched fresh LTP for {symbol}: {ltp}")
        return ltp
        
    except Exception as e:
        # Handle the error with appropriate logging
        handle_ltp_error(symbol, e)
        
        # Return cached value if available (allow stale cache during errors)
        if symbol in ltp_cache:
            cache_age = (current_time - ltp_cache_time.get(symbol, datetime.min)).total_seconds()
            # Allow stale cache up to 5x duration during errors
            if cache_age < LTP_CACHE_DURATION * 5:
                logging.info(f"Using cached LTP for {symbol}: {ltp_cache[symbol]} (age: {cache_age:.0f}s)")
                return ltp_cache[symbol]
            else:
                logging.warning(f"Cached LTP for {symbol} is too stale ({cache_age:.0f}s old)")
        
        return None

def get_india_vix():
    """Get India VIX with caching and graceful error handling"""
    global last_vix_fetch_time, india_vix
    current_time = datetime.now()

    # Fetch VIX only if 2 minutes have passed since the last fetch
    if last_vix_fetch_time is None or (current_time - last_vix_fetch_time).total_seconds() > 120:
        instrument_token = '264969'  # NIFTY VIX instrument token
        try:
            # Use cached LTP function for VIX (now has built-in retry logic)
            vix_price = get_cached_ltp(instrument_token)
            if vix_price is not None:
                india_vix = vix_price
                last_vix_fetch_time = current_time
                logging.info(f"Fetched India VIX: {india_vix} at {last_vix_fetch_time}")
            elif india_vix is not None:
                # Failed to fetch but have cached value
                logging.warning(f"Using previously cached India VIX: {india_vix}")
            else:
                # No cached VIX available - wait and retry once
                logging.warning("No cached VIX available, waiting 30s before retry...")
                time_module.sleep(30)
                vix_price = get_cached_ltp(instrument_token)
                if vix_price is not None:
                    india_vix = vix_price
                    last_vix_fetch_time = datetime.now()
                    logging.info(f"Fetched India VIX on retry: {india_vix}")
                else:
                    # Still failed - use a conservative default
                    india_vix = 15.0  # Conservative default VIX
                    logging.warning(f"Failed to fetch VIX, using default value: {india_vix}")
        except Exception as e:
            error_msg = str(e)
            if is_retryable_error(error_msg):
                logging.warning(f"Transient error fetching India VIX: {error_msg}")
            else:
                logging.error(f"Error fetching India VIX: {error_msg}")
            
            # Use cached value or default
            if india_vix is None:
                india_vix = 15.0  # Conservative default
                logging.warning(f"Using default VIX value: {india_vix}")
            else:
                logging.info(f"Using cached India VIX: {india_vix}")

    return india_vix / 100  # Return the latest VIX divided by 100 for annual volatility


def calculate_ivr(current_iv, historical_iv_data=None):
    """
    Calculate Implied Volatility Rank (IVR).
    
    Args:
        current_iv (float): Current implied volatility
        historical_iv_data (list): Historical IV data for percentile calculation
    
    Returns:
        float: IVR value (0-100)
    """
    # logging.info(f"IVR Calculation:111111")
    try:
        if historical_iv_data is None:
            # logging.info(f"IVR Calculation:2222")

            # For now, use a simple calculation based on current IV
            # In a real implementation, you would use historical IV data
            # This is a placeholder - you should implement proper IVR calculation
            base_iv = 20.0  # Assume base IV of 20%
            max_iv = 80.0   # Assume max IV of 80%
            
            # if current_iv <= base_iv:
            #     ivr = 0.0
            # elif current_iv >= max_iv:
            #     ivr = 100.0
            # else:
            #     ivr = ((current_iv - base_iv) / (max_iv - base_iv)) * 100

            ivr= 100 * max(0.0, min(1.0, (current_iv - base_iv) / max(max_iv - base_iv, 1e-9)))
                
            logging.info(f"IVR Calculation: Current IV={current_iv:.2f}%, IVR={ivr:.1f}% (placeholder calculation)")
            return ivr
        else:
            # Calculate percentile rank from historical data

            # logging.info(f"IVR Calculation:3333")
            if not historical_iv_data:
                return 50.0  # Default to 50% if no historical data
            
            # Sort historical data and find percentile
            sorted_iv = sorted(historical_iv_data)
            rank = 0
            for iv in sorted_iv:
                if current_iv > iv:
                    rank += 1
            
            ivr = (rank / len(sorted_iv)) * 100
            logging.info(f"IVR Calculation: Current IV={current_iv:.2f}%, IVR={ivr:.1f}% (percentile rank)")
            return ivr
            
    except Exception as e:
        logging.error(f"Error calculating IVR: {e}")
        return 50.0  # Default to 50% on error


# def check_go_no_go_conditions(call_strike, put_strike, underlying_price, call_vwap, put_vwap, implied_volatility_rank, call_delta, put_delta):
#     """
#     Implements the Go/No-Go checklist for each strike pair based on the formula and conditions.
    
#     Formula: D% = (S - VWAP| / VWAP) * 100
#     Where:
#     - S = Spot Price (underlying_price)
#     - VWAP = Volume Weighted Average Price
    
#     Go Conditions:
#     1. D% ≤ 0.5%
#     2. IVR ≥ 50%
#     3. Strikes at Δ 0.29–0.35
    
#     Args:
#         call_strike (dict): Call option strike details
#         put_strike (dict): Put option strike details
#         underlying_price (float): Current underlying price (S)
#         call_vwap (float): Call option VWAP
#         put_vwap (float): Put option VWAP
#         implied_volatility_rank (float): IVR value (0-100%)
#         call_delta (float): Call option delta
#         put_delta (float): Put option delta (absolute value)
    
#     Returns:
#         dict: Contains individual strike analysis and overall pair decision
#     """
#     try:
#         # Calculate D% (Distance percentage from VWAP) for each strike
#         # We need to get the strike prices from the VWAP data
#         call_strike_price = call_strike['strike']
#         put_strike_price = put_strike['strike']
        
#         # Calculate distance percentage for each strike from their respective VWAP
#         # Use strike price vs strike VWAP for distance calculation
#         call_distance_percentage = (abs(call_strike_price - call_vwap) / call_vwap) * 100 if call_vwap is not None else 0
#         put_distance_percentage = (abs(put_strike_price - put_vwap) / put_vwap) * 100 if put_vwap is not None else 0

#         logging.info(f" call_distance_percentage :{ call_distance_percentage} { call_strike_price} { call_vwap}")
#         logging.info(f" put_distance_percentage :{ put_distance_percentage} { put_strike_price} { put_vwap}")
        
#         # Check each condition
#         call_distance_ok = call_distance_percentage <= 0.5  # D% ≤ 0.5%
#         put_distance_ok = put_distance_percentage <= 0.5  # D% ≤ 0.5%
#         condition1_met = call_distance_ok and put_distance_ok  # Both strikes must meet distance criteria
        
#         condition2_met = implied_volatility_rank >= 50  # IVR ≥ 50%
        
#         # Check if deltas are within 0.15-0.20 range (using absolute values)
#         call_delta_abs = abs(call_delta)
#         put_delta_abs = abs(put_delta)
        
#         # Individual strike delta checks
#         call_delta_ok = TARGET_DELTA_LOW <= call_delta_abs <= TARGET_DELTA_HIGH
#         put_delta_ok = TARGET_DELTA_LOW <= put_delta_abs <= TARGET_DELTA_HIGH
#         condition3_met = call_delta_ok and put_delta_ok
        
#         # All conditions must be met for GO decision
#         go_decision = "Yes" if (condition1_met and condition2_met and condition3_met) else "No"
        
#         # Individual strike analysis
#         call_strike_analysis = {
#             'strike': call_strike['strike'],
#             'tradingsymbol': call_strike['tradingsymbol'],
#             'delta': call_delta,
#             'delta_abs': call_delta_abs,
#             'delta_ok': call_delta_ok,
#             'delta_range': f"{TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
#             'distance_percentage': call_distance_percentage,
#             'distance_ok': call_distance_ok,
#             'status': "GO" if (call_delta_ok and call_distance_ok) else "NO-GO",
#             'delta_reason': f"Delta {call_delta_abs:.3f} {'within' if call_delta_ok else 'outside'} range {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
#             'distance_reason': f"Distance {call_distance_percentage:.3f}% {'within' if call_distance_ok else 'exceeds'} 0.5% threshold",
#             'reason': f"Delta: {call_delta_abs:.3f} ({'OK' if call_delta_ok else 'FAIL'}), Distance: {call_distance_percentage:.3f}% ({'OK' if call_distance_ok else 'FAIL'})"
#         }
        
#         put_strike_analysis = {
#             'strike': put_strike['strike'],
#             'tradingsymbol': put_strike['tradingsymbol'],
#             'delta': put_delta,
#             'delta_abs': put_delta_abs,
#             'delta_ok': put_delta_ok,
#             'delta_range': f"{TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
#             'distance_percentage': put_distance_percentage,
#             'distance_ok': put_distance_ok,
#             'status': "GO" if (put_delta_ok and put_distance_ok) else "NO-GO",
#             'delta_reason': f"Delta {put_delta_abs:.3f} {'within' if put_delta_ok else 'outside'} range {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
#             'distance_reason': f"Distance {put_distance_percentage:.3f}% {'within' if put_distance_ok else 'exceeds'} 0.5% threshold",
#             'reason': f"Delta: {put_delta_abs:.3f} ({'OK' if put_delta_ok else 'FAIL'}), Distance: {put_distance_percentage:.3f}% ({'OK' if put_distance_ok else 'FAIL'})"
#         }
        
#         # Prepare detailed analysis
#         analysis = {
#             'go_decision': go_decision,
#             'call_distance_percentage': call_distance_percentage,
#             'put_distance_percentage': put_distance_percentage,
#             'condition1_met': condition1_met,
#             'condition2_met': condition2_met,
#             'condition3_met': condition3_met,
#             'call_delta_abs': call_delta_abs,
#             'put_delta_abs': put_delta_abs,
#             'call_strike': call_strike,
#             'put_strike': put_strike,
#             'call_strike_analysis': call_strike_analysis,
#             'put_strike_analysis': put_strike_analysis,
#             'details': {
#                 'condition1': f"Both strikes D% <= 0.5%: Call={call_distance_percentage:.3f}%, Put={put_distance_percentage:.3f}% {'OK' if condition1_met else 'FAIL'} (threshold: 0.5%)",
#                 'condition2': f"IVR >= 50%: {implied_volatility_rank:.1f}% {'OK' if condition2_met else 'FAIL'} (threshold: 50%)",
#                 'condition3': f"Delta {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}: Call={call_delta_abs:.3f}, Put={put_delta_abs:.3f} {'OK' if condition3_met else 'FAIL'} (range: {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH})"
#             }
#         }
        
#         # Log the analysis
#         logging.info(f"\n{'='*60}")
#         logging.info(f"GO/NO-GO CHECKLIST ANALYSIS FOR STRIKE PAIR:")
#         logging.info(f"Call Strike: {call_strike['tradingsymbol']} (Strike: {call_strike['strike']})")
#         logging.info(f"Put Strike: {put_strike['tradingsymbol']} (Strike: {put_strike['strike']})")
#         logging.info(f"Underlying Price (S): {underlying_price:.2f}")
#         logging.info(f"Call VWAP: {call_vwap:.2f}" if call_vwap is not None else "Call VWAP: N/A")
#         logging.info(f"Put VWAP: {put_vwap:.2f}" if put_vwap is not None else "Put VWAP: N/A")
#         logging.info(f"Implied Volatility Rank (IVR): {implied_volatility_rank:.1f}%")
        
#         # Individual strike analysis
#         logging.info(f"\nINDIVIDUAL STRIKE ANALYSIS:")
#         logging.info(f"CALL STRIKE: {call_strike_analysis['tradingsymbol']}")
#         logging.info(f"  Strike Price: {call_strike_analysis['strike']}")
#         logging.info(f"  Strike VWAP: {call_vwap:.2f}" if call_vwap is not None else "  Strike VWAP: N/A")
#         logging.info(f"  Distance from Strike VWAP: {call_strike_analysis['distance_percentage']:.3f}%")
#         logging.info(f"  Delta: {call_strike_analysis['delta']:.3f} (abs: {call_strike_analysis['delta_abs']:.3f})")
#         logging.info(f"  Target Delta Range: {call_strike_analysis['delta_range']}")
#         logging.info(f"  Status: {call_strike_analysis['status']}")
#         logging.info(f"  Distance Check: {call_strike_analysis['distance_reason']}")
#         logging.info(f"  Delta Check: {call_strike_analysis['delta_reason']}")
#         logging.info(f"  Overall Reason: {call_strike_analysis['reason']}")
        
#         logging.info(f"PUT STRIKE: {put_strike_analysis['tradingsymbol']}")
#         logging.info(f"  Strike Price: {put_strike_analysis['strike']}")
#         logging.info(f"  Strike VWAP: {put_vwap:.2f}" if put_vwap is not None else "  Strike VWAP: N/A")
#         logging.info(f"  Distance from Strike VWAP: {put_strike_analysis['distance_percentage']:.3f}%")
#         logging.info(f"  Delta: {put_strike_analysis['delta']:.3f} (abs: {put_strike_analysis['delta_abs']:.3f})")
#         logging.info(f"  Target Delta Range: {put_strike_analysis['delta_range']}")
#         logging.info(f"  Status: {put_strike_analysis['status']}")
#         logging.info(f"  Distance Check: {put_strike_analysis['distance_reason']}")
#         logging.info(f"  Delta Check: {put_strike_analysis['delta_reason']}")
#         logging.info(f"  Overall Reason: {put_strike_analysis['reason']}")
        
#         logging.info(f"\nOVERALL CONDITIONS CHECK:")
#         logging.info(f"1. {analysis['details']['condition1']}")
#         logging.info(f"2. {analysis['details']['condition2']}")
#         logging.info(f"3. {analysis['details']['condition3']}")
#         logging.info(f"\nPAIR DECISION: {go_decision}")
#         logging.info(f"{'='*60}")
        
#         return analysis
        
#     except Exception as e:
#         logging.error(f"Error in check_go_no_go_conditions: {e}")
#         return {
#             'go_decision': 'No',
#             'error': str(e),
#             'details': {
#                 'condition1': 'Error calculating D%',
#                 'condition2': 'Error checking IVR',
#                 'condition3': 'Error checking deltas'
#             }
#         }


def check_go_no_go_conditions(call_strike, put_strike, underlying_price, call_vwap, put_vwap, call_delta, put_delta, call_iv=None, put_iv=None, delta_low=None, delta_high=None):
    """
    Implements the RAAK Framework for strangle trade decision making.
    
    RAAK Framework Rules (User Priority Order):
    1. Price Difference Condition: Most important with weightage 2.0 (Price diff <= MAX_PRICE_DIFFERENCE_PERCENTAGE)
    2. High IV Condition: Individual strike IV must be >= MIN_IV_THRESHOLD (Higher priority)
    3. Delta Condition: Select CE & PE strikes with delta between TARGET_DELTA_LOW-TARGET_DELTA_HIGH
    4. VWAP Condition: Distance from VWAP scoring system (Lowest priority)
    
    Scoring System (Total: 5.0 points):
    - Price diff <= MAX_PRICE_DIFFERENCE_PERCENTAGE → +2.0 (CRITICAL - Primary Filter)
    - Both strikes IV >= MIN_IV_THRESHOLD → +1.5 (HIGH PRIORITY - Second Priority)
    - Both CE & PE Delta in TARGET_DELTA_LOW-TARGET_DELTA_HIGH → +1.0 (Third Priority)
    - VWAP Distance <= {VWAP_MAX_PRICE_DIFF_PERCENT}% → +0.5 (Fourth Priority)
    - VWAP Distance {VWAP_MAX_PRICE_DIFF_PERCENT}%-{VWAP_MAX_PRICE_DIFF_PERCENT * 2}% → +0.25
    - VWAP Distance > {VWAP_MAX_PRICE_DIFF_PERCENT * 2}% → 0
    
    Decision Rules:
    - Score >= 4.5 → GO Trade [SAFE] (Safe strangle setup, proceed with full position)
    - Score 3.5–4.4 → Caution Trade [WARNING] (Take reduced lot size or hedge using Iron Condor / spreads)
    - Score < 3.5 → NO-GO [REJECT] (Skip the trade)
    
    Args:
        call_strike (dict): Call option strike details (must include 'strike', 'tradingsymbol', 'last_price')
        put_strike (dict): Put option strike details (must include 'strike', 'tradingsymbol', 'last_price')
        underlying_price (float): Current underlying price (S)
        call_vwap (float): Call option VWAP
        put_vwap (float): Put option VWAP
        call_delta (float): Call option delta
        put_delta (float): Put option delta (absolute value)
        call_iv (float): Call option implied volatility
        put_iv (float): Put option implied volatility
    
    Returns:
        dict: Contains RAAK Framework analysis and scoring-based decision
    """
    try:
        # Extract option last traded prices - fetch if not available
        if 'last_price' not in call_strike or call_strike['last_price'] is None or call_strike['last_price'] == 0:
            try:
                call_symbol = f"NFO:{call_strike['tradingsymbol']}"
                call_ltp = get_cached_ltp(call_symbol)
                if call_ltp is not None:
                    logging.info(f"Fetched call LTP for {call_strike['tradingsymbol']}: {call_ltp}")
                else:
                    logging.warning(f"No LTP data found for {call_strike['tradingsymbol']}")
                    call_ltp = 0
            except Exception as e:
                logging.error(f"Error fetching call LTP for {call_strike['tradingsymbol']}: {e}")
                call_ltp = 0
        else:
            call_ltp = call_strike['last_price']
            
        if 'last_price' not in put_strike or put_strike['last_price'] is None or put_strike['last_price'] == 0:
            try:
                put_symbol = f"NFO:{put_strike['tradingsymbol']}"
                put_ltp = get_cached_ltp(put_symbol)
                if put_ltp is not None:
                    logging.info(f"Fetched put LTP for {put_strike['tradingsymbol']}: {put_ltp}")
                else:
                    logging.warning(f"No LTP data found for {put_strike['tradingsymbol']}")
                    put_ltp = 0
            except Exception as e:
                logging.error(f"Error fetching put LTP for {put_strike['tradingsymbol']}: {e}")
                put_ltp = 0
        else:
            put_ltp = put_strike['last_price']

        # Calculate distance percentage for each strike using LTP vs VWAP
        # Handle cases where LTP is 0 or VWAP is not available
        if call_ltp > 0 and call_vwap and call_vwap > 0:
            call_distance_percentage = (abs(call_ltp - call_vwap) / call_vwap) * 100
        else:
            # Fallback: use strike price if LTP is not available
            if call_vwap and call_vwap > 0:
                call_strike_price = call_strike['strike']
                call_distance_percentage = (abs(call_strike_price - call_vwap) / call_vwap) * 100
                logging.warning(f"Using strike price for call distance calculation - Strike: {call_strike_price}, VWAP: {call_vwap}")
            else:
                call_distance_percentage = 0
                logging.warning(f"Call LTP and VWAP invalid - LTP: {call_ltp}, VWAP: {call_vwap}")
            
        if put_ltp > 0 and put_vwap and put_vwap > 0:
            put_distance_percentage = (abs(put_ltp - put_vwap) / put_vwap) * 100
        else:
            # Fallback: use strike price if LTP is not available
            if put_vwap and put_vwap > 0:
                put_strike_price = put_strike['strike']
                put_distance_percentage = (abs(put_strike_price - put_vwap) / put_vwap) * 100
                logging.warning(f"Using strike price for put distance calculation - Strike: {put_strike_price}, VWAP: {put_vwap}")
            else:
                put_distance_percentage = 0
                logging.warning(f"Put LTP and VWAP invalid - LTP: {put_ltp}, VWAP: {put_vwap}")

        logging.info(f" call_distance_percentage : {call_distance_percentage:.3f}% | LTP={call_ltp} | VWAP={call_vwap}")
        logging.info(f" put_distance_percentage  : {put_distance_percentage:.3f}% | LTP={put_ltp} | VWAP={put_vwap}")

        # RAAK Framework Scoring System
        score = 0.0
        score_details = []
        
        # 1. Price Difference Condition: Most important with weightage 2
        price_diff_condition_met = False
        if call_ltp > 0 and put_ltp > 0:
            price_diff = abs(call_ltp - put_ltp)
            price_diff_percentage = price_diff / ((call_ltp + put_ltp) / 2) * 100
            
            if price_diff_percentage <= MAX_PRICE_DIFFERENCE_PERCENTAGE:
                score += 2.0  # Double weightage for price difference
                score_details.append(f"Price diff <= {MAX_PRICE_DIFFERENCE_PERCENTAGE}%: +2.0 (Call: {call_ltp:.2f}, Put: {put_ltp:.2f}, Diff: {price_diff_percentage:.2f}%)")
                price_diff_condition_met = True
            else:
                score_details.append(f"Price diff > {MAX_PRICE_DIFFERENCE_PERCENTAGE}%: +0.0 (Diff: {price_diff_percentage:.2f}%)")
        else:
            score_details.append("Price data not available: +0.0")
        
        # 2. IV Condition: Both strikes IV >= MIN_IV_THRESHOLD → +1.5 (Higher priority)
        iv_condition_met = False
        if call_iv is not None and put_iv is not None:
            if call_iv >= MIN_IV_THRESHOLD and put_iv >= MIN_IV_THRESHOLD:
                score += 1.5  # Increased weight for High IV priority
                score_details.append(f"Both IVs >= {MIN_IV_THRESHOLD}%: +1.5 (High IV Priority)")
                iv_condition_met = True
            else:
                score_details.append(f"IV condition not met (threshold: {MIN_IV_THRESHOLD}%): +0.0")
        else:
            score_details.append("IV data not available: +0.0")
        
        # 3. Delta Condition: Both CE & PE Delta in delta range → +1.0
        # Use VIX-based delta range if provided, otherwise use default TARGET_DELTA range
        if delta_low is None:
            delta_low = TARGET_DELTA_LOW
        if delta_high is None:
            delta_high = TARGET_DELTA_HIGH
            
        # Validate delta range consistency for RAAK framework
        validate_delta_range_consistency(delta_low, delta_high, "RAAK framework analysis")
            
        call_delta_abs = abs(call_delta)
        put_delta_abs = abs(put_delta)
        call_delta_ok = delta_low <= call_delta_abs <= delta_high
        put_delta_ok = delta_low <= put_delta_abs <= delta_high
        
        if call_delta_ok and put_delta_ok:
            score += 1.0
            score_details.append(f"Both deltas in range ({delta_low:.2f}-{delta_high:.2f}): +1.0")
        else:
            score_details.append(f"Delta condition not met (range: {delta_low:.2f}-{delta_high:.2f}): +0.0")
        
        # 4. VWAP Condition: Distance scoring system → +0.5 (Lower priority)
        # Calculate average distance for both strikes
        avg_distance = (call_distance_percentage + put_distance_percentage) / 2
        
        if avg_distance <= VWAP_MAX_PRICE_DIFF_PERCENT:
            score += 0.5  # Reduced weight for VWAP (lowest priority)
            score_details.append(f"VWAP Distance <= {VWAP_MAX_PRICE_DIFF_PERCENT}% (avg: {avg_distance:.2f}%): +0.5")
        elif avg_distance <= VWAP_MAX_PRICE_DIFF_PERCENT * 2:
            score += 0.25  # Reduced weight for partial VWAP
            score_details.append(f"VWAP Distance {VWAP_MAX_PRICE_DIFF_PERCENT}%-{VWAP_MAX_PRICE_DIFF_PERCENT * 2}% (avg: {avg_distance:.2f}%): +0.25")
        else:
            score_details.append(f"VWAP Distance > {VWAP_MAX_PRICE_DIFF_PERCENT * 2}% (avg: {avg_distance:.2f}%): +0.0")
        
        # Decision based on score (now out of 5.0 total: 2.0 + 1.5 + 1.0 + 0.5)
        if score >= 4.5:  # Adjusted for new max score of 5.0
            go_decision = "GO Trade [SAFE]"
            decision_reason = "Safe strangle setup, proceed with full position"
        elif score >= 3.5:  # Adjusted threshold
            go_decision = "Caution Trade [WARNING]"
            decision_reason = "Take reduced lot size or hedge using Iron Condor / spreads"
        else:
            go_decision = "NO-GO [REJECT]"
            decision_reason = "Skip the trade - insufficient score"
        
        # Legacy condition checks for backward compatibility
        call_distance_ok = call_distance_percentage <= VWAP_MAX_PRICE_DIFF_PERCENT  # Using configurable threshold
        put_distance_ok = put_distance_percentage <= VWAP_MAX_PRICE_DIFF_PERCENT
        condition1_met = price_diff_condition_met  # Price difference condition (most important)
        condition2_met = iv_condition_met  # IV condition
        condition3_met = call_delta_ok and put_delta_ok
        
        # Individual strike analysis
        call_strike_analysis = {
            'strike': call_strike['strike'],
            'tradingsymbol': call_strike['tradingsymbol'],
            'ltp': call_ltp,
            'delta': call_delta,
            'delta_abs': call_delta_abs,
            'delta_ok': call_delta_ok,
            'delta_range': f"{TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
            'distance_percentage': call_distance_percentage,
            'distance_ok': call_distance_ok,
            'status': "GO" if (call_delta_ok and call_distance_ok) else "NO-GO",
            'delta_reason': f"Delta {call_delta_abs:.3f} {'within' if call_delta_ok else 'outside'} range {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
            'distance_reason': f"Distance {call_distance_percentage:.3f}% {'within' if call_distance_ok else 'exceeds'} 2.0% threshold",
            'reason': f"Delta: {call_delta_abs:.3f} ({'OK' if call_delta_ok else 'FAIL'}), Distance: {call_distance_percentage:.3f}% ({'OK' if call_distance_ok else 'FAIL'})"
        }
        
        put_strike_analysis = {
            'strike': put_strike['strike'],
            'tradingsymbol': put_strike['tradingsymbol'],
            'ltp': put_ltp,
            'delta': put_delta,
            'delta_abs': put_delta_abs,
            'delta_ok': put_delta_ok,
            'delta_range': f"{TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
            'distance_percentage': put_distance_percentage,
            'distance_ok': put_distance_ok,
            'status': "GO" if (put_delta_ok and put_distance_ok) else "NO-GO",
            'delta_reason': f"Delta {put_delta_abs:.3f} {'within' if put_delta_ok else 'outside'} range {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}",
            'distance_reason': f"Distance {put_distance_percentage:.3f}% {'within' if put_distance_ok else 'exceeds'} 2.0% threshold",
            'reason': f"Delta: {put_delta_abs:.3f} ({'OK' if put_delta_ok else 'FAIL'}), Distance: {put_distance_percentage:.3f}% ({'OK' if put_distance_ok else 'FAIL'})"
        }
        
        analysis = {
            'go_decision': go_decision,
            'decision_reason': decision_reason,
            'raak_score': score,
            'score_details': score_details,
            'call_distance_percentage': call_distance_percentage,
            'put_distance_percentage': put_distance_percentage,
            'avg_vwap_distance': avg_distance,
            'price_diff_percentage': price_diff_percentage if 'price_diff_percentage' in locals() else None,
            'condition1_met': condition1_met,
            'condition2_met': condition2_met,
            'condition3_met': condition3_met,
            'call_delta_abs': call_delta_abs,
            'put_delta_abs': put_delta_abs,
            'call_strike': call_strike,
            'put_strike': put_strike,
            'call_strike_analysis': call_strike_analysis,
            'put_strike_analysis': put_strike_analysis,
            'call_iv': call_iv,
            'put_iv': put_iv,
            'iv_condition_met': iv_condition_met,
            'price_diff_condition_met': price_diff_condition_met,
            'details': {
                'condition1': f"Price diff <= {MAX_PRICE_DIFFERENCE_PERCENTAGE}%: {'OK' if condition1_met else 'FAIL'} (threshold: {MAX_PRICE_DIFFERENCE_PERCENTAGE}%)",
                'condition2': f"Both IVs >= {MIN_IV_THRESHOLD}%: Call={call_iv:.1f}%, Put={put_iv:.1f}% {'OK' if condition2_met else 'FAIL'} (threshold: {MIN_IV_THRESHOLD}%)",
                'condition3': f"Delta {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH}: Call={call_delta_abs:.3f}, Put={put_delta_abs:.3f} {'OK' if condition3_met else 'FAIL'} (range: {TARGET_DELTA_LOW}-{TARGET_DELTA_HIGH})",
                'raak_framework': f"RAAK Score: {score:.1f}/4.0 - {decision_reason}"
            }
        }

        # No color codes - plain text output
        GREEN = ''
        RED = ''
        YELLOW = ''
        BLUE = ''
        BOLD = ''
        RESET = ''
        
        # Streamlined Logging - Focus on Key Metrics
        logging.info(f"\n{'='*50}")
        logging.info(f"RAAK FRAMEWORK ANALYSIS:")
        logging.info(f"Pair: {call_strike['tradingsymbol']} | {put_strike['tradingsymbol']}")
        
        # Key Metrics Summary (Reduced logging)
        price_diff_info = f"Price Diff: {price_diff_percentage:.2f}%" if 'price_diff_percentage' in locals() else "Price Diff: N/A"
        logging.info(f"Call: {call_ltp:.2f} | Put: {put_ltp:.2f} | {price_diff_info}")
        logging.info(f"Call IV: {call_iv:.1f}% | Put IV: {put_iv:.1f}% | Call Delta: {call_delta_abs:.3f} | Put Delta: {put_delta_abs:.3f}")

        # RAAK Score Summary
        logging.info(f"\nRAAK SCORE: {score:.1f}/5.0")
        
        # Quick Score Breakdown (Only show key points)
        for detail in score_details:
            if "+2.0" in detail:
                logging.info(f"  [CRITICAL] {detail}")
            elif "+1.5" in detail:
                logging.info(f"  [HIGH PRIORITY] {detail}")
            elif "+1.0" in detail:
                logging.info(f"  [PASS] {detail}")
            elif "+0.5" in detail:
                logging.info(f"  [PARTIAL] {detail}")
            elif "+0.25" in detail:
                logging.info(f"  [LOW PARTIAL] {detail}")
            else:
                logging.info(f"  [FAIL] {detail}")
        
        # Final Decision
        logging.info(f"\nDECISION: {go_decision}")
        logging.info(f"{'='*50}")
        
        return analysis
        
    except Exception as e:
        logging.error(f"Error in check_go_no_go_conditions: {e}")
        return {
            'go_decision': 'No',
            'error': str(e),
            'details': {
                'condition1': 'Error calculating D%',
                'condition2': 'Error checking IVR',
                'condition3': 'Error checking deltas'
            }
        }


def find_most_recent_working_day(start_date, max_days_back=None):
    """
    Find the most recent working day by checking for data availability
    
    Args:
        start_date (datetime): Starting date to check from
        max_days_back (int): Maximum number of days to look back (uses config if None)
        
    Returns:
        datetime: Most recent working day or None if not found
    """
    if max_days_back is None:
        max_days_back = VWAP_MAX_DAYS_BACK
    
    try:
        # Use NIFTY 50 as a reference instrument to check working days
        nifty_token = '256265'  # NIFTY 50 instrument token
        
        for days_back in range(max_days_back):
            check_date = start_date - timedelta(days=days_back)
            check_date_str = check_date.strftime('%Y-%m-%d')
            
            try:
                # Try to get historical data for this date
                data = kite.historical_data(
                    instrument_token=nifty_token,
                    from_date=check_date_str,
                    to_date=check_date_str,
                    interval='minute'
                )
                
                if data and len(data) > 0:
                    logging.debug(f"Found working day: {check_date_str} with {len(data)} candles")
                    return check_date
                    
            except Exception as e:
                logging.debug(f"No data for {check_date_str}: {e}")
                continue
        
        logging.warning(f"No working day found in last {max_days_back} days")
        return None
        
    except Exception as e:
        logging.error(f"Error finding working day: {e}")
        return None


def get_instrument_token(symbol):
    """Get instrument token for a given symbol"""
    try:
        # Extract the instrument name from symbol
        if ':' in symbol:
            exchange, tradingsymbol = symbol.split(':', 1)
        else:
            tradingsymbol = symbol
            exchange = 'NFO'
        
        logging.debug(f"Looking for instrument token: {tradingsymbol} in exchange: {exchange}")
        
        # Get instruments for the exchange
        instruments = kite.instruments(exchange)
        
        # Find the matching instrument
        for instrument in instruments:
            if instrument['tradingsymbol'] == tradingsymbol:
                logging.debug(f"Found instrument token: {instrument['instrument_token']} for {tradingsymbol}")
                return instrument['instrument_token']
        
        logging.error(f"Instrument token not found for {symbol} (tradingsymbol: {tradingsymbol})")
        return None
        
    except Exception as e:
        logging.error(f"Error getting instrument token for {symbol}: {e}")
        return None





def calculate_vwap(symbol, minutes=None):
    """
    Calculate VWAP (Volume Weighted Average Price) for a given symbol with caching and rate limiting
    
    Args:
        symbol (str): Trading symbol (e.g., 'NFO:NIFTY24JAN19000CE')
        minutes (int): Number of minutes to look back for VWAP calculation
        
    Returns:
        float: VWAP value or None if calculation fails
    """
    global vwap_cache, vwap_cache_time
    
    if minutes is None:
        minutes = VWAP_MIN_CANDLES  # Use minimum candles requirement
    
    # Create cache key
    cache_key = f"{symbol}_{minutes}"
    
    # Check cache first
    current_time = datetime.now()
    if (cache_key in vwap_cache and 
        cache_key in vwap_cache_time and
        (current_time - vwap_cache_time[cache_key]).total_seconds() < VWAP_CACHE_DURATION):
        logging.debug(f"Using cached VWAP for {symbol}: {vwap_cache[cache_key]:.2f}")
        return vwap_cache[cache_key]
    
    # Enforce rate limiting
    enforce_rate_limit()
        
    try:
        # Get instrument token first
        instrument_token = get_instrument_token(symbol)
        if instrument_token is None:
            logging.warning(f"Could not get instrument token for {symbol}")
            return None
        
        # Calculate the time range for VWAP calculation
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=minutes)
        
        # Format times for API call
        from_date = start_time.strftime('%Y-%m-%d')
        to_date = end_time.strftime('%Y-%m-%d')
        
        logging.debug(f"Fetching historical data for {symbol} from {from_date} to {to_date}")
        
        # Get historical data
        historical_data = kite.historical_data(
            instrument_token=instrument_token,
            from_date=from_date,
            to_date=to_date,
            interval='minute'
        )
        
        # If we don't have enough candles and previous day data is enabled, try previous working days
        if (not historical_data or len(historical_data) < VWAP_MIN_CANDLES) and VWAP_USE_PREVIOUS_DAY:
            logging.info(f"Insufficient candles ({len(historical_data) if historical_data else 0}), fetching previous working day data")
            
            # Find the most recent working day
            working_day = find_most_recent_working_day(end_time - timedelta(days=1))
            
            if working_day:
                # Calculate working day range
                working_day_start = working_day - timedelta(minutes=VWAP_MIN_CANDLES)
                
                working_from_date = working_day_start.strftime('%Y-%m-%d')
                working_to_date = working_day.strftime('%Y-%m-%d')
                
                logging.info(f"Fetching data from working day {working_to_date} for {symbol}")
                
                working_day_data = kite.historical_data(
                    instrument_token=instrument_token,
                    from_date=working_from_date,
                    to_date=working_to_date,
                    interval='minute'
                )
                
                if working_day_data:
                    # Combine current day and working day data
                    if historical_data:
                        historical_data = working_day_data + historical_data
                        logging.info(f"Combined data: {len(historical_data)} candles (current: {len(historical_data) - len(working_day_data)}, working day: {len(working_day_data)})")
                    else:
                        historical_data = working_day_data
                        logging.info(f"Using working day data: {len(historical_data)} candles from {working_to_date}")
                else:
                    logging.warning(f"No data available for working day {working_to_date}")
            else:
                logging.warning("No working day found, cannot fetch additional data")
        
        if not historical_data:
            logging.warning(f"No historical data available for {symbol} (token: {instrument_token})")
            return None
        
        if len(historical_data) < VWAP_MIN_CANDLES:
            logging.warning(f"Insufficient candles for {symbol}: {len(historical_data)} < {VWAP_MIN_CANDLES}")
            return None
        
        # Calculate VWAP
        total_volume_price = 0
        total_volume = 0
        
        for candle in historical_data:
            # Use typical price (high + low + close) / 3
            typical_price = (candle['high'] + candle['low'] + candle['close']) / 3
            volume = candle.get('volume', 0)
            
            total_volume_price += typical_price * volume
            total_volume += volume
        
        if total_volume == 0:
            logging.warning(f"No volume data available for {symbol}")
            return None
        
        vwap = total_volume_price / total_volume
        
        # Update cache
        vwap_cache[cache_key] = vwap
        vwap_cache_time[cache_key] = current_time
        
        logging.info(f"VWAP for {symbol}: {vwap:.2f} (based on {len(historical_data)} candles)")
        return vwap
        
    except Exception as e:
        error_msg = str(e)
        if "Too many requests" in error_msg:
            logging.warning(f"Rate limit hit while calculating VWAP for {symbol}. Using cached value if available.")
            return vwap_cache.get(cache_key, None)
        else:
            logging.error(f"Error calculating VWAP for {symbol}: {e}")
            return None


def get_strike_vwap_data(strike, underlying_price=None):
    """
    Get VWAP and IV data for a strike option
    
    Args:
        strike (dict): Strike option data
        underlying_price (float): Current underlying price for IV calculation
        
    Returns:
        dict: Dictionary containing LTP, VWAP, and IV data
    """
    symbol = f"NFO:{strike['tradingsymbol']}"
    
    try:
        # Use cached LTP to reduce API calls
        ltp = get_cached_ltp(symbol)
        if ltp is None:
            logging.warning(f"Could not fetch LTP for {symbol}")
            return {
                'symbol': symbol,
                'ltp': None,
                'vwap': None,
                'iv': None,
                'strike_price': strike['strike'],
                'instrument_type': strike['instrument_type']
            }
            
        vwap = calculate_vwap(symbol, minutes=VWAP_MIN_CANDLES)
        
        # Calculate IV if underlying price is provided and IV display is enabled
        iv = None
        if underlying_price and IV_DISPLAY_ENABLED:
            iv = calculate_iv(strike, underlying_price, ltp)
        
        return {
            'symbol': symbol,
            'ltp': ltp,
            'vwap': vwap,
            'iv': iv,
            'strike_price': strike['strike'],
            'instrument_type': strike['instrument_type']
        }
    except Exception as e:
        logging.error(f"Error getting VWAP data for {symbol}: {e}")
        return {
            'symbol': symbol,
            'ltp': None,
            'vwap': None,
            'iv': None,
            'strike_price': strike['strike'],
            'instrument_type': strike['instrument_type']
        }


def calculate_delta(option, underlying_price, risk_free_rate=0.05):
    try:
        strike_price = option['strike']
        expiry = option['expiry']
        today = datetime.now().date()
        if isinstance(expiry, str):
            expiry = datetime.strptime(expiry, '%Y-%m-%d').date()
        days_to_expiry = (expiry - today).days / 365.0
        if days_to_expiry <= 0:
            logging.error(f"Invalid days to expiry: {days_to_expiry} for option {option['tradingsymbol']}")
            return None

        # Get the volatility (VIX)
        volatility = get_india_vix()

        # Black-Scholes d1 calculation for delta
        d1 = (math.log(underlying_price / strike_price) + (risk_free_rate + (volatility ** 2) / 2) * days_to_expiry) / (
                volatility * math.sqrt(days_to_expiry))
        if option['instrument_type'] == 'CE':  # Call Option
            delta = norm.cdf(d1)
        else:  # Put Option
            delta = -norm.cdf(-d1)

        return abs(delta)  # Absolute value of delta for comparison
    except Exception as e:
        if "Too many requests" in str(e):
            logging.error("Too many requests - waiting before retrying...")
            time_module.sleep(45)
            return calculate_delta(option, underlying_price, risk_free_rate)
        else:
            logging.error(f"Error calculating delta: {e}")
            return None


def check_vwap_safety(call_data, put_data):
    """
    Check if both strikes meet VWAP safety conditions
    
    Args:
        call_data (dict): Call strike data with LTP and VWAP
        put_data (dict): Put strike data with LTP and VWAP
        
    Returns:
        dict: Safety check results with detailed information
    """
    try:
        # Check if VWAP data is available
        if call_data['vwap'] is None or put_data['vwap'] is None:
            return {
                'safe': False,
                'reason': 'VWAP data not available',
                'call_below_vwap': False,
                'put_below_vwap': False,
                'call_vwap_diff_percent': None,
                'put_vwap_diff_percent': None
            }
        
        # Check if both strikes are below their respective VWAP
        call_below_vwap = call_data['ltp'] < call_data['vwap']
        put_below_vwap = put_data['ltp'] < put_data['vwap']
        
        # Calculate percentage difference (VWAP - Price) / VWAP * 100
        call_vwap_diff_percent = ((call_data['vwap'] - call_data['ltp']) / call_data['vwap']) * 100
        put_vwap_diff_percent = ((put_data['vwap'] - put_data['ltp']) / put_data['vwap']) * 100
        
        # Check if both are within the 1.5% limit
        call_within_limit = call_vwap_diff_percent <= VWAP_MAX_PRICE_DIFF_PERCENT
        put_within_limit = put_vwap_diff_percent <= VWAP_MAX_PRICE_DIFF_PERCENT
        
        # Overall safety check
        safe = (call_below_vwap and put_below_vwap and call_within_limit and put_within_limit)
        
        return {
            'safe': safe,
            'reason': 'All conditions met' if safe else 'VWAP safety conditions not met',
            'call_below_vwap': call_below_vwap,
            'put_below_vwap': put_below_vwap,
            'call_vwap_diff_percent': call_vwap_diff_percent,
            'put_vwap_diff_percent': put_vwap_diff_percent,
            'call_within_limit': call_within_limit,
            'put_within_limit': put_within_limit
        }
        
    except Exception as e:
        logging.error(f"Error checking VWAP safety: {e}")
        return {
            'safe': False,
            'reason': f'Error in VWAP safety check: {e}',
            'call_below_vwap': False,
            'put_below_vwap': False,
            'call_vwap_diff_percent': None,
            'put_vwap_diff_percent': None
        }


def calculate_iv(option, underlying_price, option_price, risk_free_rate=0.05):
    """
    Calculate Implied Volatility (IV) for an option using Newton-Raphson method
    
    Args:
        option (dict): Option data
        underlying_price (float): Current underlying price
        option_price (float): Current option price
        risk_free_rate (float): Risk-free interest rate
        
    Returns:
        float: Implied volatility as percentage or None if calculation fails
    """
    try:
        strike_price = option['strike']
        expiry = option['expiry']
        today = datetime.now().date()
        if isinstance(expiry, str):
            expiry = datetime.strptime(expiry, '%Y-%m-%d').date()
        days_to_expiry = (expiry - today).days / 365.0
        
        if days_to_expiry <= 0:
            logging.error(f"Invalid days to expiry: {days_to_expiry} for option {option['tradingsymbol']}")
            return None
        
        # Newton-Raphson method to find IV
        sigma = 0.5  # Initial guess
        tolerance = 0.0001
        max_iterations = 100
        
        for i in range(max_iterations):
            # Calculate option price with current sigma
            d1 = (math.log(underlying_price / strike_price) + (risk_free_rate + (sigma ** 2) / 2) * days_to_expiry) / (
                    sigma * math.sqrt(days_to_expiry))
            d2 = d1 - sigma * math.sqrt(days_to_expiry)
            
            if option['instrument_type'] == 'CE':  # Call Option
                theoretical_price = underlying_price * norm.cdf(d1) - strike_price * math.exp(-risk_free_rate * days_to_expiry) * norm.cdf(d2)
            else:  # Put Option
                theoretical_price = strike_price * math.exp(-risk_free_rate * days_to_expiry) * norm.cdf(-d2) - underlying_price * norm.cdf(-d1)
            
            # Calculate vega (derivative of price with respect to volatility)
            vega = underlying_price * math.sqrt(days_to_expiry) * norm.pdf(d1)
            
            # Newton-Raphson update
            price_diff = theoretical_price - option_price
            if abs(price_diff) < tolerance:
                break
                
            sigma_new = sigma - price_diff / vega
            if abs(sigma_new - sigma) < tolerance:
                break
                
            sigma = max(0.001, sigma_new)  # Ensure sigma is positive
        
        return sigma * 100  # Return as percentage
        
    except Exception as e:
        logging.error(f"Error calculating IV for {option['tradingsymbol']}: {e}")
        return None


# def find_strikes(options, underlying_price, target_delta_low, target_delta_high):
#     atm_strike = round(underlying_price / 50) * 50
#     logging.info(f"ATM strike: {atm_strike}")
#     global call_sl_to_be_placed
#     global put_sl_to_be_placed
#
#     logging.info(f"Finding strikes with delta between {target_delta_low} and {target_delta_high} within {atm_strike - 500} to {atm_strike + 500}")
#     try:
#         call_strikes = []
#         put_strikes = []
#         for o in options:
#             if atm_strike - 500 <= o['strike'] <= atm_strike + 500:
#                 delta = calculate_delta(o, underlying_price)
#                 if delta is None:
#                     continue
#                 if target_delta_low <= delta <= target_delta_high:
#                     if o['instrument_type'] == 'CE':
#                         call_strikes.append(o)
#                     elif o['instrument_type'] == 'PE':
#                         put_strikes.append(o)
#         if not call_strikes or not put_strikes:
#             logging.warning("No strikes found with the desired delta range.")
#             return None
#         call_strikes.sort(key=lambda x: x['strike'])
#         put_strikes.sort(key=lambda x: x['strike'])
#         best_pair = None
#         min_price_diff = float('inf')
#         for call in call_strikes:
#             for put in put_strikes:
#                 try:
#                     call_price = kite.ltp(call['exchange'] + ':' + call['tradingsymbol'])[call['exchange'] + ':' + call['tradingsymbol']]['last_price']
#                     put_price = kite.ltp(put['exchange'] + ':' + put['tradingsymbol'])[put['exchange'] + ':' + put['tradingsymbol']]['last_price']
#                     price_diff = abs(call_price - put_price)
#                     price_diff_percentage = price_diff / ((call_price + put_price) / 2) * 100
#                     logging.info(f"Pair found: Call {call['tradingsymbol']}, Put {put['tradingsymbol']}, call_delta {calculate_delta(call, underlying_price)}, put_delta {calculate_delta(put, underlying_price)}")
#                     logging.info(f"call_price: {call_price}, put_price: {put_price}, price_diff: {price_diff}, price_diff_percentage {price_diff_percentage}, today_sl  {today_sl}")
#                     if abs(price_diff_percentage) <= 1.5:
#                         min_price_diff = price_diff
#                         best_pair = (call, put)
#                         call_sl_to_be_placed = round((call_price * today_sl) / 100)
#                         put_sl_to_be_placed = round((put_price * today_sl) / 100)
#                         logging.info(f"call_price: {call_price}, put_price: {put_price}, min_price_diff: {min_price_diff}, price_diff_percentage {price_diff_percentage}, today_sl  {today_sl} ,call_sl_to_be_placed {call_sl_to_be_placed}, put_sl_to_be_placed  {put_sl_to_be_placed}")
#                 except Exception as e:
#                     logging.error(f"Error fetching LTP or calculating price diff: {e}")
#                     time_module.sleep(30)
#         if best_pair:
#             logging.info(f"Best pair found: Call {best_pair[0]['tradingsymbol']} Put {best_pair[1]['tradingsymbol']} with price difference {min_price_diff:.2f}")
#         else:
#             logging.warning("No suitable pairs found.")
#         return best_pair
#     except Exception as e:
#         logging.error(f"Error finding strikes: {e}")
#         return None
def find_strikes(options, underlying_price, target_delta_low, target_delta_high, today_sl):
    atm_strike = round(underlying_price / 50) * 50
    logging.info(f"ATM strike: {atm_strike}")
    global call_sl_to_be_placed
    global put_sl_to_be_placed

    logging.info(f"Finding strikes with initial delta range {target_delta_low} to {target_delta_high} within {atm_strike - 500} to {atm_strike + 500}")
    if VWAP_ENABLED:
        logging.info(f"Enhanced VWAP analysis enabled (Min Candles: {VWAP_MIN_CANDLES}, Max Diff: {VWAP_MAX_PRICE_DIFF_PERCENT}%)")
        logging.info(f"Delta monitoring threshold: {DELTA_MONITORING_THRESHOLD} (will modify SL if delta goes below this)")

    try:
        call_strikes = []
        put_strikes = []
        option_summary = []

        for o in options:
            if atm_strike - 500 <= o['strike'] <= atm_strike + 500:
                delta = calculate_delta(o, underlying_price)
                if delta is None:
                    continue
                o['delta'] = delta
                if target_delta_low <= delta <= target_delta_high:
                    if o['instrument_type'] == 'CE':
                        call_strikes.append(o)
                    elif o['instrument_type'] == 'PE':
                        put_strikes.append(o)
                option_summary.append(o)

        if not call_strikes or not put_strikes:
            logging.warning("No strikes found with the desired delta range.")
            return None

        call_strikes.sort(key=lambda x: x['strike'])
        put_strikes.sort(key=lambda x: x['strike'])

        best_pair = None
        min_price_diff = float('inf')
        suitable_pairs = []
        all_pairs = []  # Store all pairs for analysis

        for call in call_strikes:
            for put in put_strikes:
                try:
                    # PRIMARY CONDITION: Check price difference first to save compute power
                    # Get basic LTP prices first (lightweight operation) with retry logic
                    call_price = get_cached_ltp(call['exchange'] + ':' + call['tradingsymbol'])
                    put_price = get_cached_ltp(put['exchange'] + ':' + put['tradingsymbol'])
                    
                    if call_price is None or put_price is None:
                        continue
                        
                    price_diff = abs(call_price - put_price)
                    price_diff_percentage = price_diff / ((call_price + put_price) / 2) * 100
                    
                    # PRIMARY FILTER: Only proceed with expensive calculations if price difference is acceptable
                    if abs(price_diff_percentage) > MAX_PRICE_DIFFERENCE_PERCENTAGE:
                        # Log skipped pair for transparency
                        logging.info(f"SKIPPED: {call['tradingsymbol']} | {put['tradingsymbol']} Price:| {call_price} { put_price} | Price Diff: {price_diff_percentage:.2f}% > {MAX_PRICE_DIFFERENCE_PERCENTAGE}%")
                        continue
                    
                    # Only now perform expensive VWAP and IV calculations for qualifying pairs
                    if VWAP_ENABLED:
                        # Get VWAP and IV data for both strikes
                        call_vwap_data = get_strike_vwap_data(call, underlying_price)
                        put_vwap_data = get_strike_vwap_data(put, underlying_price)
                        
                        call_vwap = call_vwap_data['vwap']
                        put_vwap = put_vwap_data['vwap']
                        call_iv = call_vwap_data['iv']
                        put_iv = put_vwap_data['iv']
                    else:
                        # Fallback to simple LTP without VWAP
                        call_vwap = None
                        put_vwap = None
                        call_iv = None
                        put_iv = None
                    
                    # Check VWAP safety conditions (only if VWAP is enabled)
                    if VWAP_ENABLED:
                        vwap_safety = check_vwap_safety(call_vwap_data, put_vwap_data)
                    else:
                        vwap_safety = {'safe': True, 'reason': 'VWAP disabled'}
                    
                    # Log essential information for each pair (Reduced logging)
                    logging.info(f"\n{'='*60}")
                    logging.info(f"ANALYZING: {call['tradingsymbol']} | {put['tradingsymbol']}")
                    logging.info(f"Prices: Call={call_price:.2f} | Put={put_price:.2f} | Diff={price_diff_percentage:.2f}%")
                    logging.info(f"IVs: Call={call_iv:.1f}% | Put={put_iv:.1f}% | Deltas: Call={call['delta']:.3f} | Put={put['delta']:.3f}")
                    
                    # Perform RAAK Framework analysis (always execute regardless of VWAP safety)
                    go_no_go_result = check_go_no_go_conditions(
                        call_strike=call,
                        put_strike=put,
                        underlying_price=underlying_price,
                        call_vwap=call_vwap,
                        put_vwap=put_vwap,
                        call_delta=call['delta'],
                        put_delta=put['delta'],
                        call_iv=call_iv,
                        put_iv=put_iv,
                        delta_low=target_delta_low,
                        delta_high=target_delta_high
                    )
                    
                    # Log VWAP safety status separately
                    if VWAP_ENABLED and not vwap_safety['safe']:
                        logging.info(f"VWAP Safety: FAILED")
                    
                    # Store all pairs for analysis
                    pair_info = {
                        'call': call,
                        'put': put,
                        'call_price': call_price,
                        'put_price': put_price,
                        'call_vwap': call_vwap,
                        'put_vwap': put_vwap,
                        'call_iv': call_iv,
                        'put_iv': put_iv,
                        'call_delta': call['delta'],
                        'put_delta': put['delta'],
                        'price_diff': price_diff,
                        'price_diff_percentage': price_diff_percentage,
                        'vwap_safety': vwap_safety,
                        'within_price_limit': abs(price_diff_percentage) <= MAX_PRICE_DIFFERENCE_PERCENTAGE,
                        'go_no_go_result': go_no_go_result
                    }
                    
                    all_pairs.append(pair_info)
                    
                    # Since we already filtered by price difference, all pairs reaching here are suitable
                    suitable_pairs.append(pair_info)
                    
                    # RAAK Framework decision logic - prioritize RAAK score over VWAP safety
                    go_decision = go_no_go_result['go_decision']
                    raak_score = go_no_go_result['raak_score']
                    
                    if "GO Trade [SAFE]" in go_decision:  # Score >= 3.5
                        if price_diff < min_price_diff:
                            min_price_diff = price_diff
                            best_pair = (call, put)
                            call_sl_to_be_placed = round((call_price * today_sl) / 100)
                            put_sl_to_be_placed = round((put_price * today_sl) / 100)
                            
                            # Log VWAP safety status
                            if VWAP_ENABLED:
                                if vwap_safety['safe']:
                                    logging.info(f"[BEST] {call['tradingsymbol']} | {put['tradingsymbol']} | Score: {raak_score:.1f} | Price Diff: {price_diff_percentage:.2f}% | VWAP: SAFE")
                                else:
                                    logging.info(f"[BEST] {call['tradingsymbol']} | {put['tradingsymbol']} | Score: {raak_score:.1f} | Price Diff: {price_diff_percentage:.2f}% | VWAP: UNSAFE (but RAAK score high enough)")
                            else:
                                logging.info(f"[BEST] {call['tradingsymbol']} | {put['tradingsymbol']} | Score: {raak_score:.1f} | Price Diff: {price_diff_percentage:.2f}% | VWAP: DISABLED")
                                
                    elif "Caution Trade [WARNING]" in go_decision:  # Score 2.5-3.0
                        logging.info(f"[CAUTION] {call['tradingsymbol']} | {put['tradingsymbol']} | Score: {raak_score:.1f}")
                    elif "NO-GO [REJECT]" in go_decision:  # Score < 2.5
                        logging.info(f"[REJECT] {call['tradingsymbol']} | {put['tradingsymbol']} | Score: {raak_score:.1f}")
                    
                    # Log VWAP status separately for information
                    if VWAP_ENABLED and not vwap_safety['safe']:
                        logging.info(f"[VWAP-UNSAFE] {call['tradingsymbol']} | {put['tradingsymbol']}")
                                
                except Exception as e:
                    logging.error(f"Error analyzing strike pair {call['tradingsymbol']} - {put['tradingsymbol']}: {e}")
                    time_module.sleep(30)

        # No color codes - plain text output
        GREEN = ''
        RED = ''
        YELLOW = ''
        BLUE = ''
        BOLD = ''
        RESET = ''

        # Log summary of all pairs analyzed
        if all_pairs:
            logging.info(f"\n{'='*80}")
            logging.info(f"ALL PAIRS ANALYSIS SUMMARY:")
            logging.info(f"Total pairs analyzed: {len(all_pairs)}")
            logging.info(f"Pairs within price limit ({MAX_PRICE_DIFFERENCE_PERCENTAGE}%): {len(suitable_pairs)}")
            
            # RAAK Framework Summary
            go_trade_pairs = [p for p in all_pairs if "GO Trade [SAFE]" in p['go_no_go_result']['go_decision']]
            caution_trade_pairs = [p for p in all_pairs if "Caution Trade [WARNING]" in p['go_no_go_result']['go_decision']]
            no_go_pairs = [p for p in all_pairs if "NO-GO [REJECT]" in p['go_no_go_result']['go_decision']]
            
            logging.info(f"\n{'='*50}")
            logging.info(f"[SUMMARY] RAAK FRAMEWORK SUMMARY:")
            logging.info(f"GO Trade (Score >= 3.5): {len(go_trade_pairs)}")
            logging.info(f"Caution Trade (Score 2.5-3.0): {len(caution_trade_pairs)}")
            logging.info(f"NO-GO (Score < 2.5): {len(no_go_pairs)}")
            
            # Auto-trading status
            if AUTO_TRADE_ENABLED:
                perfect_score_pairs = [p for p in all_pairs if p['go_no_go_result']['raak_score'] >= AUTO_TRADE_MIN_SCORE]
                logging.info(f"\n[AUTO-TRADE] STATUS:")
                logging.info(f"Auto-trading: ENABLED")
                logging.info(f"Min score for auto-trade: {AUTO_TRADE_MIN_SCORE}")
                logging.info(f"Pairs eligible for auto-trade: {len(perfect_score_pairs)}")
                if AUTO_TRADE_CONFIRMATION:
                    logging.info(f"User confirmation: REQUIRED")
                else:
                    logging.info(f"User confirmation: NOT REQUIRED")
            else:
                logging.info(f"\n[AUTO-TRADE] STATUS: DISABLED")
            
            # Quick Pair Summary
            logging.info(f"\nPAIR ANALYSIS:")
            for i, pair in enumerate(all_pairs, 1):
                raak_score = pair['go_no_go_result']['raak_score']
                if raak_score >= 3.5:
                    status = "GO"
                elif raak_score >= 2.5:
                    status = "CAUTION"
                else:
                    status = "NO-GO"
                
                price_diff = pair.get('price_diff_percentage', 0)
                logging.info(f"{i}. {status} | {pair['call']['tradingsymbol']} | {pair['put']['tradingsymbol']} | Score: {raak_score:.1f}/4.0 | Price Diff: {price_diff:.2f}%")

        logging.info(f"\n{'='*60}")
        logging.info(f"[FLOW] CHECKING BEST PAIR SELECTION:")
        logging.info(f"best_pair exists: {best_pair is not None}")
        if best_pair:
            logging.info(f"best_pair type: {type(best_pair)}")
            logging.info(f"best_pair content: {best_pair}")
        
        if best_pair:
            call, put = best_pair
            logging.info(f"Call strike: {call['tradingsymbol']}")
            logging.info(f"Put strike: {put['tradingsymbol']}")
            
            # Find the pair info for the best pair
            best_pair_info = next((p for p in all_pairs 
                             if p['call']['tradingsymbol'] == call['tradingsymbol'] 
                             and p['put']['tradingsymbol'] == put['tradingsymbol']), None)
            
            # Log individual strike details with IV if available
            if best_pair_info:
                call_iv_str = f" | IV: {best_pair_info['call_iv']:.1f}%" if best_pair_info.get('call_iv') is not None else ""
                put_iv_str = f" | IV: {best_pair_info['put_iv']:.1f}%" if best_pair_info.get('put_iv') is not None else ""
                logging.info(f"Call strike details: {call['tradingsymbol']} | Delta: {call['delta']:.3f}{call_iv_str}")
                logging.info(f"Put strike details:  {put['tradingsymbol']} | Delta: {put['delta']:.3f}{put_iv_str}")
            
            logging.info(f"best_pair_info found: {best_pair_info is not None}")
            
            if best_pair_info:
                logging.info(f"\n{'='*60}")
                logging.info(f"[BEST] FINAL SELECTION - BEST PAIR:")
                
                # Key metrics for best pair
                raak_score = best_pair_info['go_no_go_result']['raak_score']
                raak_decision = best_pair_info['go_no_go_result']['go_decision']
                
                logging.info(f"Call: {call['tradingsymbol']} | Price: {best_pair_info['call_price']:.2f} | Delta: {best_pair_info['call_delta']:.3f} | IV: {best_pair_info['call_iv']:.1f}%")
                logging.info(f"Put:  {put['tradingsymbol']} | Price: {best_pair_info['put_price']:.2f} | Delta: {best_pair_info['put_delta']:.3f} | IV: {best_pair_info['put_iv']:.1f}%")
                # Safely format price difference
                price_diff = best_pair_info.get('price_diff_percentage')
                price_diff_str = f"{price_diff:.2f}%" if price_diff is not None else "N/A"
                logging.info(f"Price Diff: {price_diff_str} | RAAK Score: {raak_score:.1f}/4.0")
                logging.info(f"RAAK Decision: {raak_decision}")
                
                # VWAP Safety Check
                if VWAP_ENABLED:
                    if best_pair_info['vwap_safety']['safe']:
                        logging.info(f"[PASS] VWAP Safety: PASSED")
                    else:
                        logging.info(f"[FAIL] VWAP Safety: FAILED")
                else:
                    logging.info(f"[PASS] Price-based selection: ENABLED")
                
                # AUTOMATIC TRADE EXECUTION FOR PERFECT RAAK SCORE
                logging.info(f"\n{'='*60}")
                logging.info(f"[AUTO-TRADE] CHECKING CONDITIONS:")
                logging.info(f"Auto-trade enabled: {AUTO_TRADE_ENABLED}")
                logging.info(f"RAAK Score: {raak_score:.1f}/5.0")
                logging.info(f"Auto-trade threshold: {AUTO_TRADE_MIN_SCORE}")
                logging.info(f"Score >= Threshold: {raak_score >= AUTO_TRADE_MIN_SCORE}")
                
                if AUTO_TRADE_ENABLED and raak_score >= AUTO_TRADE_MIN_SCORE:
                    logging.info(f"\n{'='*60}")
                    logging.info(f"[AUTO-TRADE] PERFECT RAAK SCORE DETECTED!")
                    logging.info(f"Score: {raak_score:.1f}/5.0 - Automatically executing trade...")
                    
                    # Check VWAP safety status
                    if VWAP_ENABLED and best_pair_info and not best_pair_info['vwap_safety']['safe']:
                        logging.warning(f"[WARNING] VWAP Safety Check FAILED - Trade will proceed due to high RAAK score")
                        
                        # Safely format VWAP distance values
                        call_distance = best_pair_info.get('call_distance_percentage')
                        put_distance = best_pair_info.get('put_distance_percentage')
                        
                        call_distance_str = f"{call_distance:.2f}%" if call_distance is not None else "N/A"
                        put_distance_str = f"{put_distance:.2f}%" if put_distance is not None else "N/A"
                        
                        logging.warning(f"[WARNING] Call VWAP Distance: {call_distance_str}")
                        logging.warning(f"[WARNING] Put VWAP Distance: {put_distance_str}")
                    
                    # Check if user confirmation is required
                    if AUTO_TRADE_CONFIRMATION:
                        logging.info(f"[CONFIRMATION] Auto-trade confirmation required. Please confirm in config.py")
                        logging.info(f"[INFO] RAAK Score {raak_score:.1f}/4.0 - Manual confirmation required")
                        return best_pair
                    
                    try:
                        # Check if market has been closed by monitor_trades
                        if market_closed:
                            logging.warning("[MARKET CLOSED] Skipping trade execution - market closed flag is set")
                            return None  # Return None to indicate no trade should be executed
                        
                        # Check if we're in market hours
                        # CRITICAL FIX: Use IST time instead of system time (Azure runs in UTC)
                        now = get_ist_time().time()
                        market_start = time(9, 15)
                        market_end = time(14, 57)
                        is_amo = not (market_start <= now <= market_end)
                        
                        if is_amo:
                            logging.info(f"[INFO] Market closed - placing AMO orders")
                        else:
                            logging.info(f"[INFO] Market open - placing regular orders")
                        
                        # Place main orders
                        logging.info(f"[ORDER] Placing Call order: {call['tradingsymbol']}")
                        call_order_id = place_order(call, kite.TRANSACTION_TYPE_SELL, is_amo, call_quantity)
                        
                        logging.info(f"[ORDER] Placing Put order: {put['tradingsymbol']}")
                        put_order_id = place_order(put, kite.TRANSACTION_TYPE_SELL, is_amo, put_quantity)
                        
                        if call_order_id and put_order_id:
                            logging.info(f"[SUCCESS] Main orders placed successfully!")
                            logging.info(f"Call Order ID: {call_order_id}")
                            logging.info(f"Put Order ID: {put_order_id}")
                            
                            # Place stop-loss orders
                            try:
                                logging.info(f"[SL] Placing stop-loss orders...")
                                
                                # Get LTPs for stop-loss calculation using cached function
                                call_ltp = get_cached_ltp(f"NFO:{call['tradingsymbol']}")
                                put_ltp = get_cached_ltp(f"NFO:{put['tradingsymbol']}")
                                
                                if call_ltp is None or put_ltp is None:
                                    logging.error("Could not fetch LTPs for stop-loss calculation")
                                    raise Exception("LTP data unavailable for stop-loss calculation")
                                
                                # Calculate stop-loss prices
                                call_sl_price = call_ltp + call_sl_to_be_placed
                                put_sl_price = put_ltp + put_sl_to_be_placed
                                
                                logging.info(f"[SL] Call SL Price: {call_ltp:.2f} + {call_sl_to_be_placed} = {call_sl_price:.2f}")
                                logging.info(f"[SL] Put SL Price: {put_ltp:.2f} + {put_sl_to_be_placed} = {put_sl_price:.2f}")
                                
                                # Place stop-loss orders
                                call_sl_order_id = place_stop_loss_order(call, kite.TRANSACTION_TYPE_SELL, call_sl_price, call_quantity)
                                put_sl_order_id = place_stop_loss_order(put, kite.TRANSACTION_TYPE_SELL, put_sl_price, put_quantity)
                                
                                if call_sl_order_id and put_sl_order_id:
                                    logging.info(f"[SUCCESS] Stop-loss orders placed successfully!")
                                    logging.info(f"Call SL Order ID: {call_sl_order_id}")
                                    logging.info(f"Put SL Order ID: {put_sl_order_id}")
                                    
                                    # Start monitoring trades
                                    logging.info(f"[MONITOR] Starting trade monitoring...")
                                    # Get VIX-based hedge points and expiry strategy for monitoring
                                    _, _, vix_hedge_points, vix_use_next_week = get_vix_based_delta_range()
                                    logging.info(f"[MONITOR] Using VIX-based hedge points: {vix_hedge_points}, next week expiry: {vix_use_next_week}")
                                    # For Calendar main trade, re-entries after SL should use TARGET_DELTA range
                                    monitor_trades(
                                        call_order_id,
                                        put_order_id,
                                        call,
                                        put,
                                        call_sl_order_id,
                                        put_sl_order_id,
                                        TARGET_DELTA_HIGH,
                                        TARGET_DELTA_LOW,
                                        TARGET_DELTA_HIGH,
                                        hedge_points=vix_hedge_points,
                                        use_next_week_expiry=vix_use_next_week,
                                    )
                                    
                                else:
                                    logging.error(f"[ERROR] Failed to place stop-loss orders")
                                    if not call_sl_order_id:
                                        logging.error(f"Call SL order failed")
                                    if not put_sl_order_id:
                                        logging.error(f"Put SL order failed")
                                        
                            except Exception as e:
                                logging.error(f"[ERROR] Error placing stop-loss orders: {e}")
                                
                        else:
                            logging.error(f"[ERROR] Failed to place main orders")
                            if not call_order_id:
                                logging.error(f"Call order failed")
                            if not put_order_id:
                                logging.error(f"Put order failed")
                                
                    except Exception as e:
                        logging.error(f"[ERROR] Error in automatic trade execution: {e}")
                        logging.error(f"Trade execution failed - manual intervention required")
                        
                elif AUTO_TRADE_ENABLED:
                    logging.info(f"[INFO] RAAK Score {raak_score:.1f}/5.0 - Below auto-trade threshold ({AUTO_TRADE_MIN_SCORE})")
                else:
                    logging.info(f"[INFO] RAAK Score {raak_score:.1f}/5.0 - Auto-trading disabled in config")
                    
            else:
                logging.info(f"[OK] Best pair selected for trading: {call['tradingsymbol']} and {put['tradingsymbol']}")
        else:
            logging.warning("No suitable trading pair found.")
            logging.info(f"[FLOW] best_pair_info was None - this is why auto-trade didn't execute")

        
            
        logging.info(f"\n{'='*60}")
        logging.info(f"[FLOW] RETURNING FROM find_strikes:")
        logging.info(f"Returning best_pair: {best_pair}")
        logging.info(f"best_pair type: {type(best_pair) if best_pair else 'None'}")
        
        # Include LTP and IV information if available
        if best_pair and len(best_pair) == 2:
            call_strike, put_strike = best_pair
            try:
                # Get current LTPs
                call_ltp = get_cached_ltp(f"NFO:{call_strike['tradingsymbol']}")
                put_ltp = get_cached_ltp(f"NFO:{put_strike['tradingsymbol']}")
                
                # Get IVs if available in best_pair_info
                call_iv_str = ""
                put_iv_str = ""
                if best_pair_info and 'call_iv' in best_pair_info and best_pair_info['call_iv'] is not None:
                    call_iv_str = f" | IV: {best_pair_info['call_iv']:.1f}%"
                if best_pair_info and 'put_iv' in best_pair_info and best_pair_info['put_iv'] is not None:
                    put_iv_str = f" | IV: {best_pair_info['put_iv']:.1f}%"
                
                logging.info(f"Call: {call_strike['tradingsymbol']} | LTP: {call_ltp:.2f} | Delta: {call_strike.get('delta', 'N/A'):.3f}{call_iv_str}")
                logging.info(f"Put:  {put_strike['tradingsymbol']} | LTP: {put_ltp:.2f} | Delta: {put_strike.get('delta', 'N/A'):.3f}{put_iv_str}")
            except Exception as e:
                logging.warning(f"Could not fetch LTP/IV details for FLOW logging: {e}")
        
        return best_pair

    except Exception as e:
        logging.error(f"Error in find_strikes: {e}")
        return None


def place_order(strike, transaction_type, is_amo, quantity):
    order_variety = kite.VARIETY_AMO if is_amo else kite.VARIETY_REGULAR
    logging.info(f"Placing {'AMO' if is_amo else 'market'} order for {strike['tradingsymbol']} with transaction type {transaction_type}")
    try:
        # Get lot size from config (imported via 'from config import *')
        try:
            lot_size = LOT_SIZE
        except NameError:
            # Fallback if LOT_SIZE not defined in config
            lot_size = 75
        
        # Validate quantity is a multiple of lot_size
        if quantity % lot_size != 0:
            # Round down to nearest multiple of lot_size
            rounded_quantity = (quantity // lot_size) * lot_size
            if rounded_quantity < lot_size:
                logging.error(f"Quantity {quantity} is too small. Minimum is {lot_size}. Cannot place order.")
                return None
            logging.warning(f"Quantity {quantity} is not a multiple of {lot_size}. Rounding down to {rounded_quantity}")
            quantity = rounded_quantity
        
        # Use cached LTP to reduce API calls
        symbol = strike['exchange'] + ':' + strike['tradingsymbol']
        ltp = get_cached_ltp(symbol)
        
        if ltp is None:
            logging.error(f"Could not fetch LTP for {strike['tradingsymbol']}")
            return None
            
        limit_price = ltp
        order_id = kite.place_order(
            variety=order_variety,
            exchange=kite.EXCHANGE_NFO,
            tradingsymbol=strike['tradingsymbol'],
            transaction_type=transaction_type,
            quantity=quantity,
            order_type=kite.ORDER_TYPE_MARKET,
            price=limit_price,
            product=kite.PRODUCT_NRML,
            tag="S001"
        )
        logging.info(f"Order placed successfully. ID: {order_id}, LTP : {ltp}, Quantity: {quantity}")
        return order_id
    except Exception as e:
        logging.error(f"Error placing order: {e}")
        time_module.sleep(3)
        return None


def place_stop_loss_order(strike, transaction_type, stop_loss_price, quantity):
    logging.info(f"Placing stop-loss order for {strike['tradingsymbol']} with transaction type {transaction_type} and SL price {stop_loss_price}")
    try:
        # Get lot size from config (imported via 'from config import *')
        try:
            lot_size = LOT_SIZE
        except NameError:
            # Fallback if LOT_SIZE not defined in config
            lot_size = 75
        
        # Validate quantity is a multiple of lot_size
        if quantity % lot_size != 0:
            # Round down to nearest multiple of lot_size
            rounded_quantity = (quantity // lot_size) * lot_size
            if rounded_quantity < lot_size:
                logging.error(f"Quantity {quantity} is too small. Minimum is {lot_size}. Cannot place stop-loss order.")
                return None
            logging.warning(f"Quantity {quantity} is not a multiple of {lot_size}. Rounding down to {rounded_quantity}")
            quantity = rounded_quantity
        
        order_id = kite.place_order(
            variety=kite.VARIETY_REGULAR,
            exchange=kite.EXCHANGE_NFO,
            tradingsymbol=strike['tradingsymbol'],
            transaction_type=kite.TRANSACTION_TYPE_BUY if transaction_type == kite.TRANSACTION_TYPE_SELL else kite.TRANSACTION_TYPE_SELL,
            quantity=quantity,
            price=stop_loss_price + 1,
            order_type=kite.ORDER_TYPE_SL,
            trigger_price=stop_loss_price,
            product=kite.PRODUCT_NRML,
            tag="S001"
        )
        logging.info(f"Stop-loss order placed successfully. ID: {order_id}, Quantity: {quantity}")
        return order_id
    except Exception as e:
        logging.error(f"Error placing stop-loss order: {e}")
        time_module.sleep(3)
        return None


def exit_trade(order_id, strike):
    """Cancels an active order based on the order_id."""
    try:
        kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
        logging.info(f"Exited trade for {strike['tradingsymbol']} with order ID: {order_id}")
    except Exception as e:
        logging.error(f"Error exiting trade for {strike['tradingsymbol']}: {e}")
        time_module.sleep(5)


def square_off_all_non_equity_positions():
    """
    Square off all non-equity open positions (NFO, CDS, MCX)
    """
    global kite
    try:
        logging.info("[MARKET CLOSE] Starting to square off all non-equity positions...")
        
        # Get all positions
        positions = kite.positions()
        
        if not positions or 'net' not in positions:
            logging.info("[MARKET CLOSE] No positions found to square off")
            return
        
        squared_off_count = 0
        failed_count = 0
        
        for position in positions['net']:
            quantity = position.get('quantity', 0)
            exchange = position.get('exchange', '')
            
            # Skip if no quantity or not non-equity
            if quantity == 0:
                continue
            
            # Only process non-equity positions (NFO, CDS, MCX)
            if exchange not in ['NFO', 'CDS', 'MCX']:
                continue
            
            tradingsymbol = position.get('tradingsymbol', '')
            product = position.get('product', 'NRML')
            
            try:
                # Determine opposite transaction type
                # If quantity is positive (long), we need to sell
                # If quantity is negative (short), we need to buy
                if quantity > 0:
                    transaction_type = kite.TRANSACTION_TYPE_SELL
                else:
                    transaction_type = kite.TRANSACTION_TYPE_BUY
                    quantity = abs(quantity)  # Make quantity positive
                
                # Get LTP for the instrument
                symbol = f"{exchange}:{tradingsymbol}"
                ltp = get_cached_ltp(symbol)
                
                if ltp is None:
                    logging.warning(f"[MARKET CLOSE] Could not fetch LTP for {tradingsymbol}, skipping")
                    failed_count += 1
                    continue
                
                # Map exchange string to Kite constant
                exchange_map = {
                    'NFO': kite.EXCHANGE_NFO,
                    'CDS': kite.EXCHANGE_CDS,
                    'MCX': kite.EXCHANGE_MCX
                }
                kite_exchange = exchange_map.get(exchange, exchange)
                
                # Place market order to square off
                order_id = kite.place_order(
                    variety=kite.VARIETY_REGULAR,
                    exchange=kite_exchange,
                    tradingsymbol=tradingsymbol,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    order_type=kite.ORDER_TYPE_MARKET,
                    price=ltp,
                    product=product,
                    tag="S001"
                )
                
                logging.info(f"[MARKET CLOSE] Squared off {tradingsymbol}: Qty={quantity}, Type={transaction_type}, OrderID={order_id}")
                squared_off_count += 1
                time_module.sleep(0.5)  # Small delay between orders
                
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error squaring off {tradingsymbol}: {e}")
                failed_count += 1
                continue
        
        logging.info(f"[MARKET CLOSE] Square off complete: {squared_off_count} positions squared off, {failed_count} failed")
        
    except Exception as e:
        logging.error(f"[MARKET CLOSE] Error in square_off_all_non_equity_positions: {e}")


def cancel_all_sl_orders():
    """
    Cancel all pending stop-loss orders
    """
    global kite
    try:
        logging.info("[MARKET CLOSE] Starting to cancel all SL orders...")
        
        # Get all orders
        orders = kite.orders()
        
        if not orders:
            logging.info("[MARKET CLOSE] No orders found to cancel")
            return
        
        cancelled_count = 0
        failed_count = 0
        
        for order in orders:
            # Check if it's a stop-loss order and still pending
            order_type = order.get('order_type', '')
            status = order.get('status', '')
            order_id = order.get('order_id', '')
            
            # Filter for SL orders that are still pending (not COMPLETE or CANCELLED)
            if (order_type == 'SL' or order_type == 'SL-M') and status in ['OPEN', 'TRIGGER PENDING']:
                try:
                    kite.cancel_order(variety=kite.VARIETY_REGULAR, order_id=order_id)
                    tradingsymbol = order.get('tradingsymbol', 'N/A')
                    logging.info(f"[MARKET CLOSE] Cancelled SL order: {tradingsymbol}, OrderID={order_id}")
                    cancelled_count += 1
                    time_module.sleep(0.3)  # Small delay between cancellations
                    
                except Exception as e:
                    logging.error(f"[MARKET CLOSE] Error cancelling SL order {order_id}: {e}")
                    failed_count += 1
                    continue
        
        logging.info(f"[MARKET CLOSE] SL order cancellation complete: {cancelled_count} cancelled, {failed_count} failed")
        
    except Exception as e:
        logging.error(f"[MARKET CLOSE] Error in cancel_all_sl_orders: {e}")


def modify_stop_loss_order(order_id, new_trigger_price, new_limit_price):
    """Modifies the stop-loss order with new trigger and limit prices."""
    if not order_id:
        logging.warning("Cannot modify stop-loss order: order_id is None")
        return None
        
    try:
        modified_order_id = kite.modify_order(
            variety=kite.VARIETY_REGULAR,
            order_id=order_id,
            trigger_price=new_trigger_price,
            price=new_limit_price
        )
        logging.info(f"Modified stop-loss order. New trigger price: {new_trigger_price:.3f}, limit price: {new_limit_price:.3f}, Order ID: {modified_order_id}")
        return modified_order_id
    except Exception as e:
        error_msg = str(e)
        if "does not exist" in error_msg:
            logging.warning(f"Order {order_id} no longer exists, skipping modification")
        else:
            logging.error(f"Error modifying stop-loss order: {e}")
        time_module.sleep(3)
        return None


def monitor_trades(call_order_id, put_order_id, call_strike, put_strike, call_sl_order_id, put_sl_order_id, target_delta_high, delta_low=None, delta_high=None, hedge_points=None, use_next_week_expiry=False):
    end_time = MARKET_END_TIME
    loss_taken = 0
    hedge_taken = False
    global stop_loss_trigger_count
    global market_closed
    global kite
    global account
    global PnLRecorder
    
    # Flags to track if SL has been modified for delta threshold
    call_sl_modified_for_delta = False
    put_sl_modified_for_delta = False
    logging.info("Delta monitoring flags initialized: Call_SL_Modified=False, Put_SL_Modified=False")

    try:
        call_initial_price = get_cached_ltp(f"NFO:{call_strike['tradingsymbol']}")
        put_initial_price = get_cached_ltp(f"NFO:{put_strike['tradingsymbol']}")
        if call_initial_price is None or put_initial_price is None:
            logging.error("Could not fetch initial prices for premium calculation")
            call_initial_price = call_initial_price or 0
            put_initial_price = put_initial_price or 0
        initial_total_premium = call_initial_price + put_initial_price
        logging.info(f"Initial Total Premium Received: {initial_total_premium:.3f}")
    except Exception as e:
        logging.error(f"Error calculating initial total premium: {e}")
        return

    adjusted_for_14_points = False
    adjusted_for_28_points = False
    New_trade_taken = False
    profit_booking_occurred = False  # Flag to prevent new trades after profit booking

    while True:
        # CRITICAL FIX: Use IST time instead of system time (Azure runs in UTC)
        now = get_ist_time().time()

        # Stop trades if stop-loss has been triggered maximum times
        if stop_loss_trigger_count >= MAX_STOP_LOSS_TRIGGER:
            logging.warning(f"[WARNING] STOP-LOSS LIMIT REACHED: {stop_loss_trigger_count}/{MAX_STOP_LOSS_TRIGGER}")
            logging.warning(f"[WARNING] GRACEFUL EXIT: No more trades will be taken for this session")
            logging.info(f"Final Summary - Initial Premium: {initial_total_premium:.3f} | Loss Taken: {loss_taken:.3f} | Final P&L: {initial_total_premium - current_total_premium - loss_taken:.3f}")
            
            # Graceful exit - don't try to modify non-existent orders
            try:
                # Only modify if orders still exist
                if call_sl_order_id:
                    modify_stop_loss_order(call_sl_order_id, call_ltp + 1, call_ltp + 2)
                if put_sl_order_id:
                    modify_stop_loss_order(put_sl_order_id, put_ltp + 1, put_ltp + 2)
            except Exception as e:
                logging.info(f"Order modification skipped during exit: {e}")
            
            # Set global flag to prevent any re-entry anywhere
            global market_closed
            market_closed = True
            
            break

        # Exit trades and modify stop-loss at market close (HIGHEST PRIORITY)
        if now >= end_time:
            logging.info("[MARKET CLOSE] Market is closing, modifying stop-loss orders.")
            try:
                # Only modify if orders still exist
                if call_sl_order_id:
                    modify_stop_loss_order(call_sl_order_id, call_ltp + 1, call_ltp + 2)
                if put_sl_order_id:
                    modify_stop_loss_order(put_sl_order_id, put_ltp + 1, put_ltp + 2)
            except Exception as e:
                logging.info(f"Order modification skipped during market close: {e}")
            
            # Save P&L before market close
            try:
                if PnLRecorder is not None:
                    # Get broker_id from environment variable (set by dashboard) or use account
                    broker_id = os.getenv('BROKER_ID') or os.getenv('ZERODHA_ID') or account
                    pnl_recorder = PnLRecorder(broker_id=broker_id, account=account)
                    pnl_recorder.save_daily_pnl(kite, broker_id=broker_id)
                    logging.info(f"[MARKET CLOSE] Daily P&L saved successfully for broker_id: {broker_id}")
                else:
                    logging.warning("[MARKET CLOSE] PnLRecorder not available, skipping P&L save")
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error saving P&L: {e}")
            
            # Cancel all SL orders
            try:
                cancel_all_sl_orders()
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error cancelling SL orders: {e}")
            
            # Square off all non-equity positions
            try:
                square_off_all_non_equity_positions()
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error squaring off positions: {e}")
            
            # Set global market closed flag to prevent new trades
            market_closed = True
            logging.warning("[MARKET CLOSED] No new trades will be taken for this session")
            
            break

        try:
            underlying_price = get_cached_ltp("NSE:NIFTY 50")
            call_ltp = get_cached_ltp(f"NFO:{call_strike['tradingsymbol']}")
            put_ltp = get_cached_ltp(f"NFO:{put_strike['tradingsymbol']}")
            
            if underlying_price is None or call_ltp is None or put_ltp is None:
                logging.warning("Could not fetch prices, using cached values or skipping this iteration")
                if underlying_price is None:
                    underlying_price = get_cached_ltp("NSE:NIFTY 50")  # Try once more
                if call_ltp is None or put_ltp is None:
                    time_module.sleep(2)  # Brief wait before retry
                    call_ltp = call_ltp or get_cached_ltp(f"NFO:{call_strike['tradingsymbol']}")
                    put_ltp = put_ltp or get_cached_ltp(f"NFO:{put_strike['tradingsymbol']}")
            
            if call_ltp is None or put_ltp is None:
                logging.error("Could not fetch option prices after retry, skipping this iteration")
                time_module.sleep(5)
                continue
                
            current_total_premium = call_ltp + put_ltp

            # Handle new trade taken scenario
            if New_trade_taken:
                # Update initial premium for new trade and adjust loss calculation
                initial_total_premium = current_total_premium
                current_total_premium = current_total_premium + loss_taken
                New_trade_taken = False
                # logging.info(f"[NEW TRADE] Initial premium updated to: {initial_total_premium:.3f}")

            logging.info(f"Initial Total Premium: {initial_total_premium:.3f} | Current Total Premium: {current_total_premium:.3f} | Loss Taken: {loss_taken:.3f}")
            
            # Calculate total profit/loss (simplified calculation)
            total_pnl = initial_total_premium - current_total_premium - loss_taken
            
            # Color code P&L: Green for positive, Orange for negative
            if total_pnl >= 0:
                color_code = "\033[92m"  # Green
                color_name = "Green"
            else:
                color_code = "\033[93m"  # Orange/Yellow
                color_name = "Orange"
            
            reset_code = "\033[0m"  # Reset color
            logging.info(f"Total Profit and Loss: {color_code}{total_pnl:.3f}{reset_code} ({color_name})")

            # Adjust stop-loss orders if premium reduces
            if not adjusted_for_14_points and initial_total_premium - current_total_premium >= loss_taken + INITIAL_PROFIT_BOOKING:
                logging.info(f"Total premium reduced by {initial_total_premium - current_total_premium} points, modifying stop-loss orders.")
                modify_stop_loss_order(call_sl_order_id, call_ltp + 1, call_ltp + 2)
                modify_stop_loss_order(put_sl_order_id, put_ltp + 1, put_ltp + 2)
                adjusted_for_14_points = True
                
                # Exit after first profit booking - no further processing
                profit_booking_occurred = True  # Set flag to prevent new trades
                logging.warning(f"[PROFIT BOOKING] Initial profit target reached: {INITIAL_PROFIT_BOOKING} points")
                logging.warning(f"[PROFIT BOOKING] GRACEFUL EXIT: No more trades will be taken for this session")
                logging.info(f"Final Summary - Initial Premium: {initial_total_premium:.3f} | Loss Taken: {loss_taken:.3f} | Final P&L: {initial_total_premium - current_total_premium - loss_taken:.3f}")
                
                # Set global flag so outer loops will not start new trades
                market_closed = True
                break

            if not adjusted_for_28_points and initial_total_premium - current_total_premium >= loss_taken + SECOND_PROFIT_BOOKING:
                logging.info(f"Total premium reduced by {initial_total_premium - current_total_premium} points, modifying stop-loss orders.")
                modify_stop_loss_order(call_sl_order_id, call_ltp + 1, call_ltp + 2)
                modify_stop_loss_order(put_sl_order_id, put_ltp + 1, put_ltp + 2)
                adjusted_for_28_points = True
                
                # Exit after second profit booking - no further processing
                profit_booking_occurred = True  # Set flag to prevent new trades
                logging.warning(f"[PROFIT BOOKING] Second profit target reached: {SECOND_PROFIT_BOOKING} points")
                logging.warning(f"[PROFIT BOOKING] GRACEFUL EXIT: No more trades will be taken for this session")
                logging.info(f"Final Summary - Initial Premium: {initial_total_premium:.3f} | Loss Taken: {loss_taken:.3f} | Final P&L: {initial_total_premium - current_total_premium - loss_taken:.3f}")
                
                # Set global flag so outer loops will not start new trades
                market_closed = True
                break

            # Take Hedges when profit points are received (VIX-based or default)
            hedge_trigger_points = hedge_points if hedge_points is not None else HEDGE_TRIGGER_POINTS
            if not hedge_taken and initial_total_premium - current_total_premium >= loss_taken + hedge_trigger_points:
                logging.info(
                    f"Total premium reduced by {initial_total_premium - current_total_premium- loss_taken } points, Taking Hedges (trigger: {hedge_trigger_points} points).")

                try:
                    call_hedge, put_hedge = find_hedges(call_strike, put_strike, use_next_week_expiry)
                    
                    # Calculate hedge quantities (half of original, rounded to nearest multiple of 75)
                    call_hedge_quantity = calculate_hedge_quantity(call_quantity)
                    put_hedge_quantity = calculate_hedge_quantity(put_quantity)
                    
                    # Place hedge buy orders with calculated quantities
                    if call_hedge:
                        place_order(call_hedge, kite.TRANSACTION_TYPE_BUY, False, call_hedge_quantity)
                        logging.info(f"Call hedge placed: {call_hedge['tradingsymbol']} with quantity {call_hedge_quantity}")
                    if put_hedge:
                        place_order(put_hedge, kite.TRANSACTION_TYPE_BUY, False, put_hedge_quantity)
                        logging.info(f"Put hedge placed: {put_hedge['tradingsymbol']} with quantity {put_hedge_quantity}")
                    
                    hedge_taken = True
                    logging.info(f"Hedge orders placed successfully - Call hedge qty: {call_hedge_quantity}, Put hedge qty: {put_hedge_quantity}")
                except Exception as e:
                    logging.error(f"Error placing Hedge orders: {e}")
                    # Set hedge_taken to True to prevent repeated attempts
                    hedge_taken = True
                    logging.warning("Hedge placement failed, but flag set to prevent repeated attempts")
            else:
                logging.info(f"Waiting for Hedges : {now}")

        except Exception as e:
            logging.error(f"Error monitoring trades: {e}")

        call_delta = calculate_delta(call_strike, underlying_price)
        put_delta = calculate_delta(put_strike, underlying_price)

        # Enhanced delta range monitoring
        if DELTA_MONITORING_ENABLED:
            # Check if delta is below monitoring threshold (0.26)
            call_delta_below_threshold = call_delta < DELTA_MONITORING_THRESHOLD
            put_delta_below_threshold = put_delta < DELTA_MONITORING_THRESHOLD
            
            # Calculate IV for individual strikes if IV display is enabled
            call_iv = None
            put_iv = None
            if IV_DISPLAY_ENABLED:
                try:
                    call_iv = calculate_iv(call_strike, underlying_price, call_ltp)
                    put_iv = calculate_iv(put_strike, underlying_price, put_ltp)
                except Exception as e:
                    logging.warning(f"Error calculating IV for delta monitoring: {e}")
            
            # Log delta monitoring with IV information
            call_iv_str = f" | IV: {call_iv:.1f}%" if call_iv is not None else ""
            put_iv_str = f" | IV: {put_iv:.1f}%" if put_iv is not None else ""
            
            logging.info(f"Delta Monitoring - Call: {call_delta:.3f} ({'WARNING' if call_delta_below_threshold else 'OK'} threshold: {DELTA_MONITORING_THRESHOLD}) [SL Modified: {call_sl_modified_for_delta}]{call_iv_str}")
            logging.info(f"Delta Monitoring - Put:  {put_delta:.3f} ({'WARNING' if put_delta_below_threshold else 'OK'} threshold: {DELTA_MONITORING_THRESHOLD}) [SL Modified: {put_sl_modified_for_delta}]{put_iv_str}")
            
            # Check if either delta is below the monitoring threshold
            if call_delta_below_threshold or put_delta_below_threshold:
                # Update stop-loss for the side with low delta (only once per side)
                if call_delta_below_threshold and not call_sl_modified_for_delta:
                    logging.warning(f"Call delta ({call_delta:.3f}) below threshold ({DELTA_MONITORING_THRESHOLD}), updating stop-loss")
                    modify_stop_loss_order(call_sl_order_id, call_ltp + 1, call_ltp + 2)
                    call_sl_modified_for_delta = True
                    logging.info(f"Call SL modified for delta threshold. Flag set to prevent further modifications.")
                elif call_delta_below_threshold and call_sl_modified_for_delta:
                    logging.info(f"Call delta ({call_delta:.3f}) still below threshold ({DELTA_MONITORING_THRESHOLD}), but SL already modified.")
                
                if put_delta_below_threshold and not put_sl_modified_for_delta:
                    logging.warning(f"Put delta ({put_delta:.3f}) below threshold ({DELTA_MONITORING_THRESHOLD}), updating stop-loss")
                    modify_stop_loss_order(put_sl_order_id, put_ltp + 1, put_ltp + 2)
                    put_sl_modified_for_delta = True
                    logging.info(f"Put SL modified for delta threshold. Flag set to prevent further modifications.")
                elif put_delta_below_threshold and put_sl_modified_for_delta:
                    logging.info(f"Put delta ({put_delta:.3f}) still below threshold ({DELTA_MONITORING_THRESHOLD}), but SL already modified.")
        else:
            # Legacy delta monitoring
            if abs(call_delta) > TARGET_DELTA_HIGH + 0.1 or abs(put_delta) > TARGET_DELTA_HIGH + 0.1:
                logging.info("Delta exceeded the limit, exiting trades and re-entering")
                exit_trade(call_order_id, call_strike)
                exit_trade(put_order_id, put_strike)
                time_module.sleep(10)
                
                # Get VIX-based delta range for re-entry
                delta_low, delta_high, hedge_points, use_next_week = get_vix_based_delta_range()
                logging.info(f"Re-entry using delta range: {delta_low:.2f} - {delta_high:.2f}")
                execute_trade(delta_low, delta_high, hedge_points, use_next_week)
                break

        try:
            call_order_status = kite.order_history(call_sl_order_id)[-1]['status']
            put_order_status = kite.order_history(put_sl_order_id)[-1]['status']
            logging.info(f"call_order_status: {call_order_status}, put_order_status: {put_order_status}")
            if call_order_status == 'COMPLETE':
                logging.info(f"Call stop-loss order {call_sl_order_id} triggered, finding new call strike")
                stop_loss_trigger_count += 1
                if stop_loss_trigger_count < MAX_STOP_LOSS_TRIGGER:
                    time_module.sleep(5)
                    new_strike = find_new_strike(underlying_price, call_strike, 'CE', 
                                               VIX_DELTA_LOW if use_next_week_expiry else TARGET_DELTA_LOW,
                                               VIX_DELTA_HIGH if use_next_week_expiry else TARGET_DELTA_HIGH)
                    if new_strike and not adjusted_for_14_points and not adjusted_for_28_points and not profit_booking_occurred:
                        new_order_id = place_order(new_strike, kite.TRANSACTION_TYPE_SELL, False, call_quantity)
                        if new_order_id:
                            # Place new stop-loss order
                            call_ltp = get_cached_ltp(f"NFO:{new_strike['tradingsymbol']}")
                            if call_ltp is None:
                                logging.error(f"Could not fetch LTP for new call strike {new_strike['tradingsymbol']}")
                                time_module.sleep(2)
                                call_ltp = get_cached_ltp(f"NFO:{new_strike['tradingsymbol']}") or 0
                            sl_price = call_ltp + call_sl_to_be_placed
                            new_sl_order_id = place_stop_loss_order(new_strike, kite.TRANSACTION_TYPE_SELL, sl_price, call_quantity)
                            call_order_id, call_sl_order_id, call_strike = new_order_id, new_sl_order_id, new_strike
                            
                            # Calculate loss from the previous trade (only if it's an actual loss)
                            # If current_total_premium < initial_total_premium, it's a profit (e.g., delta < 0.225 scenario)
                            # and should NOT be added to loss_taken
                            if current_total_premium > initial_total_premium:
                                loss_taken += (current_total_premium - initial_total_premium)
                                logging.info(f"Call strike replaced (LOSS). Loss: {current_total_premium - initial_total_premium:.3f} | Total loss taken: {loss_taken:.3f}")
                            else:
                                # This is a profit scenario (premium reduced, e.g., delta < 0.225)
                                profit_realized = initial_total_premium - current_total_premium
                                logging.info(f"Call strike replaced (PROFIT). Profit: {profit_realized:.3f} | Total loss taken: {loss_taken:.3f} (unchanged)")
                            
                            New_trade_taken = True
                            # Reset the flag for new call strike
                            call_sl_modified_for_delta = False
                            logging.info("Call SL modification flag reset for new strike")
                    elif profit_booking_occurred:
                        logging.info(f"[PROFIT BOOKING] Preventing new call strike placement - profit booking has occurred")

            if put_order_status == 'COMPLETE':
                logging.info(f"Put stop-loss order {put_sl_order_id} triggered, finding new put strike")
                stop_loss_trigger_count += 1
                if stop_loss_trigger_count < MAX_STOP_LOSS_TRIGGER:
                    new_strike = find_new_strike(underlying_price, put_strike, 'PE',
                                               VIX_DELTA_LOW if use_next_week_expiry else TARGET_DELTA_LOW,
                                               VIX_DELTA_HIGH if use_next_week_expiry else TARGET_DELTA_HIGH)
                    time_module.sleep(15)
                    if new_strike and not adjusted_for_14_points and not adjusted_for_28_points and not profit_booking_occurred:
                        new_order_id = place_order(new_strike, kite.TRANSACTION_TYPE_SELL, False, put_quantity)
                        if new_order_id:
                            # Place new stop-loss order
                            put_ltp = get_cached_ltp(f"NFO:{new_strike['tradingsymbol']}")
                            if put_ltp is None:
                                logging.error(f"Could not fetch LTP for new put strike {new_strike['tradingsymbol']}")
                                time_module.sleep(2)
                                put_ltp = get_cached_ltp(f"NFO:{new_strike['tradingsymbol']}") or 0
                            sl_price = put_ltp + put_sl_to_be_placed
                            new_sl_order_id = place_stop_loss_order(new_strike, kite.TRANSACTION_TYPE_SELL, sl_price, put_quantity)
                            put_order_id, put_sl_order_id, put_strike = new_order_id, new_sl_order_id, new_strike
                            
                            # Calculate loss from the previous trade (only if it's an actual loss)
                            # If current_total_premium < initial_total_premium, it's a profit (e.g., delta < 0.225 scenario)
                            # and should NOT be added to loss_taken
                            if current_total_premium > initial_total_premium:
                                loss_taken += (current_total_premium - initial_total_premium)
                                logging.info(f"Put strike replaced (LOSS). Loss: {current_total_premium - initial_total_premium:.3f} | Total loss taken: {loss_taken:.3f}")
                            else:
                                # This is a profit scenario (premium reduced, e.g., delta < 0.225)
                                profit_realized = initial_total_premium - current_total_premium
                                logging.info(f"Put strike replaced (PROFIT). Profit: {profit_realized:.3f} | Total loss taken: {loss_taken:.3f} (unchanged)")
                            
                            New_trade_taken = True
                            # Reset the flag for new put strike
                            put_sl_modified_for_delta = False
                            logging.info("Put SL modification flag reset for new strike")
                    elif profit_booking_occurred:
                        logging.info(f"[PROFIT BOOKING] Preventing new put strike placement - profit booking has occurred")

        except Exception as e:
            logging.error(f"Error checking stop-loss orders: {e}")

        time_module.sleep(3)


def find_new_strike(underlying_price, old_strike, option_type, delta_low=None, delta_high=None):
    try:
        # Use provided delta range or get VIX-based range as fallback
        if delta_low is None or delta_high is None:
            # Get VIX-based delta range for new strike selection
            vix_delta_low, vix_delta_high, _, _ = get_vix_based_delta_range()
            if delta_low is None:
                delta_low = vix_delta_low
            if delta_high is None:
                delta_high = vix_delta_high
            
            # Log the delta range being used for new strike selection
            logging.info(f"[NEW STRIKE SELECTION] Using delta range: {delta_low:.2f}-{delta_high:.2f} for {option_type}")
            
        # Validate delta range consistency
        validate_delta_range_consistency(delta_low, delta_high, f"new {option_type} strike selection")
            
        options = fetch_option_chain()
        if not options:
            logging.error("No options fetched.")
            return None

        new_strikes = [o for o in options if o['instrument_type'] == option_type and o['expiry'] == old_strike['expiry']]
        
        # Use provided delta range for new strike selection
        for strike in new_strikes:
            delta = calculate_delta(strike, underlying_price)
            if delta and delta_low <= delta <= delta_high:
                logging.info(f"Found new {option_type} strike: {strike['tradingsymbol']} with delta: {delta:.3f} (range: {delta_low:.2f}-{delta_high:.2f})")
                return strike
        
        logging.warning(f"No suitable {option_type} strike found within delta range {delta_low:.2f}-{delta_high:.2f}")
        return None
    except Exception as e:
        logging.error(f"Error finding new strike: {e}")
        return None


def get_next_week_expiry(options):
    """Get the next valid future expiry date for the configured expiry day (Thursday for Nifty 50)."""
    expiries = sorted(set(o['expiry'] for o in options))
    today = date.today()
    
    # Find all expiries after today
    future_expiries = []
    for expiry in expiries:
        if isinstance(expiry, str):
            expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        else:
            expiry_date = expiry
        if expiry_date > today:
            future_expiries.append(expiry_date)
    
    # Return the first future expiry (immediate next expiry day)
    if len(future_expiries) >= 1:
        next_expiry = future_expiries[0]
        # Verify it's actually the correct day of week
        expiry_weekday = next_expiry.strftime('%A')
        if expiry_weekday == EXPIRY_DAY:
            logging.info(f"Next {EXPIRY_DAY} expiry selected: {next_expiry}")
            return next_expiry
        else:
            logging.warning(f"Next expiry {next_expiry} is on {expiry_weekday}, not {EXPIRY_DAY}. Using it anyway.")
            return next_expiry
        
    return None


def get_next_expiry_after(options, current_expiry):
    """Return the first available expiry strictly after current_expiry."""
    expiries = sorted(set(o['expiry'] for o in options))
    # Normalize current_expiry to date
    if isinstance(current_expiry, str):
        try:
            current_expiry_date = datetime.strptime(current_expiry, '%Y-%m-%d').date()
        except Exception:
            current_expiry_date = current_expiry
    else:
        current_expiry_date = current_expiry

    for expiry in expiries:
        if isinstance(expiry, str):
            expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        else:
            expiry_date = expiry
        if expiry_date > current_expiry_date:
            return expiry_date
    return None

def is_expiry_within_2_days(expiry_date):
    today = date.today()
    # logging.info(f"trade expiry selected1111111111: {expiry_date}")
    
    return (expiry_date - today).days < 2


def execute_trade(target_delta_low, target_delta_high, hedge_points=None, use_next_week_expiry=False):
    global last_hedge_fetch_time
    current_time = datetime.now()

    # Check clock and flag before starting
    # CRITICAL FIX: Use IST time instead of system time (Azure runs in UTC)
    now_time = get_ist_time().time()
    if now_time >= MARKET_END_TIME:
        logging.warning("[MARKET CLOSED] Market is already closed, exiting execute_trade immediately")
        return
    if market_closed:
        logging.warning("[MARKET CLOSED] Market is already closed, exiting execute_trade immediately")
        return

    while True:
        try:
            # Hard guard: if market was closed by monitor_trades, exit immediately
            if market_closed:
                logging.warning("[MARKET CLOSED] Exiting execute_trade - market closed flag is set")
                return
            # Clear old cache entries periodically
            clear_old_cache()
            
            options = fetch_option_chain()
            if not options:
                logging.error("No options fetched.")
                logging.info(f"Waiting {API_RETRY_DELAY} seconds before retrying...")
                time_module.sleep(API_RETRY_DELAY)
                continue

            current_expiry = options[0]['expiry']
            if isinstance(current_expiry, str):
                current_expiry = datetime.strptime(current_expiry, '%Y-%m-%d').date()

            # Determine main trade expiry based purely on proximity to expiry day
            # Rule: If current expiry is within 2 days, use the next expiry after the current one; otherwise use current expiry
            if is_expiry_within_2_days(current_expiry):
                desired_expiry = get_next_expiry_after(options, current_expiry)
                if desired_expiry is None:
                    logging.warning("[EXPIRY] No later expiry available; skipping main trade this cycle")
                    continue
                logging.info(f"[EXPIRY] Current expiry within 2 days; selecting next {EXPIRY_DAY} expiry: {desired_expiry}")
                options = [o for o in options if o['expiry'] == desired_expiry]
            else:
                logging.info(f"[EXPIRY] Using current {EXPIRY_DAY} expiry: {current_expiry}")
                options = [o for o in options if o['expiry'] == current_expiry]

            # Use cached LTP for underlying price
            underlying_price = get_cached_ltp("NSE:NIFTY 50")
            if underlying_price is None:
                logging.error("Could not fetch underlying price")
                logging.info(f"Waiting {API_RETRY_DELAY} seconds before retrying...")
                time_module.sleep(API_RETRY_DELAY)
                continue

            # Check if market has been closed by monitor_trades
            if market_closed:
                logging.warning("[MARKET CLOSED] Exiting execute_trade - market closed flag is set")
                return
            
            strikes = find_strikes(options, underlying_price, target_delta_low, target_delta_high, today_sl)
            if not strikes:
                logging.warning("No suitable strikes found. Retrying...")
                time_module.sleep(10)
                continue

            call_strike, put_strike = strikes

            # CRITICAL FIX: Use IST time instead of system time (Azure runs in UTC)
            now = get_ist_time().time()
            market_start = time(9, 15)
            market_end = time(14, 50)
            is_amo = not (market_start <= now <= market_end)
            logging.info(f"Script call_sl_to_be_placed, {call_sl_to_be_placed}")
            logging.info(f"Script put_sl_to_be_placed, {put_sl_to_be_placed}")

            # Final guard right before placing orders
            if market_closed:
                logging.warning("[MARKET CLOSED] Exiting before order placement - market closed flag is set")
                return

            # Place main orders
            call_order_id = place_order(call_strike, kite.TRANSACTION_TYPE_SELL, is_amo, call_quantity)
            put_order_id = place_order(put_strike, kite.TRANSACTION_TYPE_SELL, is_amo, put_quantity)

            if call_order_id and put_order_id:
                # Now place stop-loss orders
                try:
                    # Get LTPs using cached function
                    call_ltp = get_cached_ltp(f"NFO:{call_strike['tradingsymbol']}")
                    put_ltp = get_cached_ltp(f"NFO:{put_strike['tradingsymbol']}")
                    
                    if call_ltp is None or put_ltp is None:
                        logging.error("Could not fetch LTPs for stop-loss calculation")
                        continue

                    # Calculate stop-loss prices
                    call_sl_price = call_ltp + call_sl_to_be_placed
                    put_sl_price = put_ltp + put_sl_to_be_placed

                    # Place stop-loss orders
                    call_sl_order_id = place_stop_loss_order(call_strike, kite.TRANSACTION_TYPE_SELL, call_sl_price, call_quantity)
                    put_sl_order_id = place_stop_loss_order(put_strike, kite.TRANSACTION_TYPE_SELL, put_sl_price, put_quantity)

                    if call_sl_order_id and put_sl_order_id:
                        # Proceed to monitor trades
                        monitor_trades(call_order_id, put_order_id, call_strike, put_strike, call_sl_order_id, put_sl_order_id, target_delta_high, target_delta_low, target_delta_high, hedge_points, use_next_week_expiry)
                        break
                    else:
                        logging.error("Failed to place stop-loss orders.")
                        # Handle accordingly
                except Exception as e:
                    logging.error(f"Error placing stop-loss orders: {e}")
                    # Handle accordingly
            else:
                logging.error("Failed to place main orders.")
                # Handle accordingly
                
        except Exception as e:
            logging.error(f"Error in main execution loop: {e}")
            logging.info(f"Waiting {API_RETRY_DELAY} seconds before retrying...")
            time_module.sleep(API_RETRY_DELAY)
            continue


def main():
    global Input_account, Input_api_key, Input_api_secret, Input_request_token, api_key, api_secret, request_token, account, kite, today_sl, call_quantity, put_quantity, PnLRecorder
    
    logging.info("Script started")
    
    # Get user account and API details
    print("\n" + "=" * 60)
    print("API CREDENTIALS SETUP")
    print("=" * 60)
    
    # Check if running in Azure - try to get credentials from stdin first (when started as subprocess)
    # If stdin is available and has data, use that (dashboard passes credentials via stdin)
    # Otherwise, try to get from web interface API
    if is_azure_environment():
        logging.info("[ENV] Azure environment detected")
        
        # First, try to read from stdin (when started as subprocess by dashboard)
        # Dashboard passes credentials via stdin in this order:
        # Account\nApi_key\nApi_secret\nRequest_Token\nCall_Quantity\nPut_Quantity\n
        stdin_available = False
        try:
            import sys
            import select
            # Check if stdin is a TTY (interactive) or has data
            # When started as subprocess with stdin=PIPE, stdin is not a TTY but has data
            if not sys.stdin.isatty():
                # stdin is a pipe (subprocess mode) - try to read with timeout
                logging.info("[ENV] stdin is a pipe, attempting to read credentials from stdin (subprocess mode)")
                try:
                    # Use select with timeout to check if data is available (Unix/Linux)
                    # On Windows, select might not work, so we'll try reading directly
                    if hasattr(select, 'select'):
                        # Unix/Linux: Check if stdin has data
                        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                        if ready:
                            Input_account = input().strip() if not Input_account else Input_account
                            Input_api_key = input().strip() if not Input_api_key else Input_api_key
                            Input_api_secret = input().strip() if not Input_api_secret else Input_api_secret
                            Input_request_token = input().strip() if not Input_request_token else Input_request_token
                            # Also read call_quantity and put_quantity (but we'll use them later)
                            try:
                                call_quantity = int(input().strip())
                                put_quantity = int(input().strip())
                            except:
                                pass
                            stdin_available = True
                            logging.info(f"[ENV] Credentials read from stdin for account: {Input_account}")
                    else:
                        # Windows: Try reading directly (might block, but dashboard sends immediately)
                        Input_account = input().strip() if not Input_account else Input_account
                        Input_api_key = input().strip() if not Input_api_key else Input_api_key
                        Input_api_secret = input().strip() if not Input_api_secret else Input_api_secret
                        Input_request_token = input().strip() if not Input_request_token else Input_request_token
                        # Also read call_quantity and put_quantity
                        try:
                            call_quantity = int(input().strip())
                            put_quantity = int(input().strip())
                        except:
                            pass
                        stdin_available = True
                        logging.info(f"[ENV] Credentials read from stdin for account: {Input_account}")
                except (EOFError, ValueError) as stdin_error:
                    # stdin read failed - will try API method
                    logging.debug(f"[ENV] Could not read from stdin: {stdin_error}, will try API method")
                    pass
        except Exception as stdin_error:
            # stdin not available or error - try API method
            logging.debug(f"[ENV] stdin check failed: {stdin_error}, trying API method")
            pass
        
        # If stdin didn't work, try to get credentials from dashboard API
        if not stdin_available and not all([Input_account, Input_api_key, Input_api_secret, Input_request_token]):
            logging.info("[ENV] Waiting for credentials from web interface API")
            # Try to get credentials from dashboard API
            max_retries = 60  # Wait up to 5 minutes (60 * 5 seconds)
            retry_count = 0
            credentials_set = False
            
            while retry_count < max_retries and not credentials_set:
                try:
                    import requests
                    # Try to get credentials from local dashboard
                    dashboard_port = int(os.getenv('HTTP_PLATFORM_PORT', os.getenv('PORT', 8080)))
                    response = requests.get(
                        f'http://localhost:{dashboard_port}/api/trading/get-credentials',
                        timeout=2
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get('success') and data.get('credentials'):
                            creds = data['credentials']
                            Input_account = creds.get('account')
                            Input_api_key = creds.get('api_key')
                            Input_api_secret = creds.get('api_secret')
                            Input_request_token = creds.get('request_token')
                            credentials_set = True
                            logging.info(f"[ENV] Credentials retrieved from web interface for account: {Input_account}")
                            break
                except Exception as e:
                    # Credentials not set yet, wait and retry
                    if retry_count % 12 == 0:  # Log every minute
                        logging.info(f"[ENV] Waiting for credentials... ({retry_count * 5} seconds)")
                    time_module.sleep(5)  # Wait 5 seconds before retry
                    retry_count += 1
            
            if not credentials_set:
                logging.error("[ENV] Credentials not set via web interface!")
                logging.error("[ENV] Please visit the web interface to enter credentials")
                logging.error("[ENV] The application will continue waiting, but trading will not start until credentials are provided")
    else:
        # Local environment - prompt for credentials via CLI
        if not Input_account:
            Input_account = input("Account: ").strip()
        if not Input_api_key:
            Input_api_key = input("Api_key: ").strip()
        if not Input_api_secret:
            Input_api_secret = input("Api_Secret: ").strip()
        if not Input_request_token:
            Input_request_token = input("Request_Token: ").strip()
    
    # Validate credentials are provided
    if not all([Input_account, Input_api_key, Input_api_secret, Input_request_token]):
        if is_azure_environment():
            # On Azure, credentials should have been retrieved above
            # If we reach here, they weren't set - log and return
            logging.warning("[ENV] Credentials not yet available. Please set them via the web interface.")
            logging.warning("[ENV] Visit the web interface URL to enter credentials.")
            logging.warning("[ENV] The application will continue running, but trading will not start until credentials are provided.")
            # Return early - don't start trading without credentials
            return
        else:
            error_msg = "Missing required API credentials. Please provide all credentials."
            logging.error(error_msg)
            raise ValueError(error_msg)
    
    api_key = Input_api_key
    api_secret = Input_api_secret
    request_token = Input_request_token
    account = Input_account
    
    # Reinitialize Kite Connect API with credentials
    kite = KiteConnect(api_key=api_key)
    kite.set_access_token(request_token)
    
    # Initialize P&L Recorder (broker_id-wise for multi-user isolation)
    # Get broker_id from environment variable (set by dashboard) or use account
    broker_id = os.getenv('BROKER_ID') or os.getenv('ZERODHA_ID') or account
    if PnLRecorder is not None:
        pnl_recorder = PnLRecorder(broker_id=broker_id, account=account)
        logging.info(f"[P&L RECORDER] Initialized for broker_id '{broker_id}' (Zerodha ID) - will save daily P&L before market close")
    else:
        logging.warning("[P&L RECORDER] Not available - P&L recording will be disabled")
    
    # Setup logging for both local and Azure environments
    try:
        # Print diagnostic message before setting up logging (helps identify strategy start in log stream)
        print(f"[STRATEGY] Starting logging setup for account: {Input_account}")
        print(f"[STRATEGY] Azure environment: {is_azure_environment()}")
        
        logger, log_filename = setup_logging(account_name=Input_account)
        
        # Print confirmation after logging setup
        if is_azure_environment():
            print(f"[STRATEGY] Azure Blob logging should be configured. Check blob container for logs.")
        
        # Also add file handler to existing logger for backward compatibility
        global file_handler
        file_handler = None
        if log_filename:
            # Check if file exists (it should after setup_logging)
            if os.path.exists(log_filename):
                # File handler is already added by setup_logging, but we keep reference
                for handler in logging.getLogger().handlers:
                    if isinstance(handler, logging.FileHandler) and handler.baseFilename == log_filename:
                        file_handler = handler
                        break
            else:
                # File doesn't exist - log warning
                warning_msg = f"[LOG] Warning: Log file was not created at {log_filename}"
                print(warning_msg)
                logging.warning(warning_msg)
        
        # Log the file path prominently
        if log_filename:
            log_msg = f"[LOG] Log file path: {log_filename}"
            print(log_msg)
            logging.info(log_msg)
            
            # Verify file exists
            if os.path.exists(log_filename):
                file_size = os.path.getsize(log_filename)
                print(f"[LOG] Log file exists, size: {file_size} bytes")
                logging.info(f"[LOG] Log file exists, size: {file_size} bytes")
            else:
                print(f"[LOG] WARNING: Log file does not exist at {log_filename}")
                logging.warning(f"[LOG] WARNING: Log file does not exist at {log_filename}")
        
        if is_azure_environment():
            azure_msg = f"[LOG] Azure Log Stream: View logs in Azure Portal > Log stream"
            print(azure_msg)
            logging.info(azure_msg)
            if log_filename:
                azure_files_msg = f"[LOG] Azure Log Files: Available at {log_filename}"
            else:
                azure_files_msg = f"[LOG] Azure Log Files: Directory /tmp/{sanitize_account_name_for_filename(Input_account) if Input_account else 'logs'}/logs/"
            print(azure_files_msg)
            logging.info(azure_files_msg)
        
        print("[OK] API credentials set successfully")
        logging.info("[OK] API credentials set successfully")
    except Exception as e:
        error_msg = f"[ERROR] Failed to setup logging: {e}"
        print(error_msg)
        import traceback
        traceback.print_exc()
        logging.error(f"{error_msg}\n{traceback.format_exc()}")
        # Continue execution even if logging setup fails
        logger = logging.getLogger()
        log_filename = None
    print("=" * 60)
    
    # Calculate today's stop loss
    current_day = datetime.now().strftime('%A')
    today_sl = STOP_LOSS_CONFIG.get(current_day, STOP_LOSS_CONFIG['default'])
    logging.info(f"today_sl: {today_sl}, {current_day}")
    
    # Get trading quantities from user
    print("\n" + "=" * 60)
    print("TRADING QUANTITY SETUP")
    print("=" * 60)
    
    try:
        # Get lot size from config (imported via 'from config import *')
        try:
            lot_size = LOT_SIZE
        except NameError:
            # Fallback if LOT_SIZE not defined in config
            lot_size = 65
        
        # Check if quantities were already read from stdin earlier (lines 2556-2571)
        # If call_quantity and put_quantity are still default (1), we need to read them
        quantities_already_read = (call_quantity > 1 and put_quantity > 1)
        
        if quantities_already_read:
            # Quantities were already read from stdin in the credentials section
            logging.info(f"[QUANTITY] Using quantities already read from stdin: Call={call_quantity}, Put={put_quantity}")
            print(f"[OK] Quantities received from dashboard: Call={call_quantity}, Put={put_quantity}")
        else:
            # Quantities not yet read - read from stdin or prompt
            if is_azure_environment():
                # On Azure, quantities should have been passed via stdin from dashboard
                # If not already read, this is likely a direct script execution
                logging.warning("[QUANTITY] Quantities not received via stdin, attempting to read now...")
                try:
                    call_input = input("Enter Call Quantity: ").strip()
                    put_input = input("Enter Put Quantity: ").strip()
                    call_quantity = int(call_input)
                    put_quantity = int(put_input)
                except (EOFError, ValueError) as e:
                    # stdin exhausted or invalid - use default quantities based on lot_size
                    default_qty = lot_size * 3  # Default to 3 lots (195 for lot_size=65)
                    call_quantity = default_qty
                    put_quantity = default_qty
                    logging.warning(f"[QUANTITY] Could not read quantities: {e}. Using default: {default_qty}")
                    print(f"[OK] Using default quantities (3 lots): Call={call_quantity}, Put={put_quantity}")
            else:
                # Local: try stdin first (if called from dashboard), otherwise prompt
                try:
                    call_quantity = int(input("Enter Call Quantity: ").strip())
                    put_quantity = int(input("Enter Put Quantity: ").strip())
                except (EOFError, ValueError):
                    # If stdin is empty or invalid, use defaults or prompt
                    default_qty = lot_size * 3  # Default to 3 lots
                    try:
                        call_quantity = int(input(f"Enter Call Quantity (default {default_qty}): ").strip() or str(default_qty))
                        put_quantity = int(input(f"Enter Put Quantity (default {default_qty}): ").strip() or str(default_qty))
                    except (EOFError, ValueError):
                        call_quantity = default_qty
                        put_quantity = default_qty
        
        # Validate quantities are multiples of lot_size
        if call_quantity % lot_size != 0:
            rounded_call = (call_quantity // lot_size) * lot_size
            if rounded_call < lot_size:
                rounded_call = lot_size
            logging.warning(f"Call Quantity {call_quantity} is not a multiple of {lot_size}. Rounding down to {rounded_call}")
            call_quantity = rounded_call
        
        if put_quantity % lot_size != 0:
            rounded_put = (put_quantity // lot_size) * lot_size
            if rounded_put < lot_size:
                rounded_put = lot_size
            logging.warning(f"Put Quantity {put_quantity} is not a multiple of {lot_size}. Rounding down to {rounded_put}")
            put_quantity = rounded_put
        
        print(f"[OK] Final Call Quantity: {call_quantity}")
        print(f"[OK] Final Put Quantity: {put_quantity}")
        print("=" * 60)
        
    except (ValueError, EOFError) as e:
        # Get lot size for default calculation
        try:
            lot_size = LOT_SIZE
        except NameError:
            lot_size = 65
        default_qty = lot_size * 3  # Default to 3 lots
        print(f"[ERROR] Invalid quantity entered: {e}. Using default values.")
        call_quantity = default_qty
        put_quantity = default_qty
        print(f"[OK] Using default quantities - Call: {call_quantity}, Put: {put_quantity}")
    
    # Initialize config monitoring system
    try:
        config_monitor = initialize_config_monitor('config.py')
        start_config_monitoring()
        logging.info("[CONFIG MONITOR] Real-time config monitoring enabled")
    except Exception as e:
        logging.error(f"[CONFIG MONITOR] Failed to initialize monitoring: {e}")
    
    target_time = TRADING_START_TIME
    end_time = MARKET_END_TIME
    
    # Log timezone and trading start time for debugging
    current_ist = get_ist_time()
    logging.info(f"[TIME CHECK] Current IST datetime: {current_ist.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logging.info(f"[TIME CHECK] Current IST time: {current_ist.time()}")
    logging.info(f"[TIME CHECK] TRADING_START_TIME: {TRADING_START_TIME}")
    logging.info(f"[TIME CHECK] MARKET_END_TIME: {end_time}")
    logging.info(f"[TIME CHECK] Condition check: {current_ist.time()} >= {TRADING_START_TIME} = {current_ist.time() >= TRADING_START_TIME}")
    
    # Greek analysis removed - core trading functionality only

    while True:
        # CRITICAL FIX: Use IST time instead of system time (Azure runs in UTC)
        now = get_ist_time().time()
        try:
            underlying_price = get_cached_ltp('NSE:NIFTY 50')
            if underlying_price is not None:
                logging.info(f"Underlying price: {underlying_price}")
            else:
                logging.error("Could not fetch underlying price")
        except Exception as e:
            logging.error(f"Error fetching underlying price: {e}")
        
        # Greek analysis removed - core trading functionality only
        
        # Hard market close guard even if no base trade is taken
        if now >= end_time:
            logging.warning("[MARKET CLOSED] Skipping new trade execution - market end time reached")
            
            # Save P&L before market close (in case no trades were taken)
            try:
                if PnLRecorder is not None:
                    # Get broker_id from environment variable (set by dashboard) or use account
                    broker_id = os.getenv('BROKER_ID') or os.getenv('ZERODHA_ID') or account
                    pnl_recorder = PnLRecorder(broker_id=broker_id, account=account)
                    pnl_recorder.save_daily_pnl(kite, broker_id=broker_id)
                    logging.info(f"[MARKET CLOSE] Daily P&L saved successfully for broker_id: {broker_id}")
                else:
                    logging.warning("[MARKET CLOSE] PnLRecorder not available, skipping P&L save")
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error saving P&L: {e}")
            
            # Cancel all SL orders
            try:
                cancel_all_sl_orders()
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error cancelling SL orders: {e}")
            
            # Square off all non-equity positions
            try:
                square_off_all_non_equity_positions()
            except Exception as e:
                logging.error(f"[MARKET CLOSE] Error squaring off positions: {e}")
            
            break

        # Enhanced logging for time check
        time_check_result = now >= target_time
        if not time_check_result:
            logging.info(f"[TIME CHECK] Waiting for trading start time. Current IST: {now}, Required: {target_time}, Check: {time_check_result}")
        
        if now >= target_time:
            logging.info("Executing trade")
            logging.info(f"[TIME CHECK] Trading start time reached! Current IST: {now}, Target: {target_time}")
            
            # Get VIX-based delta range
            delta_low, delta_high, hedge_points, use_next_week = get_vix_based_delta_range()
            logging.info(f"Using delta range: {delta_low:.2f} - {delta_high:.2f}, hedge points: {hedge_points}, next week expiry: {use_next_week}")
            
            execute_trade(delta_low, delta_high, hedge_points, use_next_week)
            
            # Check if market was closed during execution
            if market_closed:
                logging.warning("[MARKET CLOSED] Bot execution completed due to market close")
                break
            else:
                logging.info("Trade execution completed")
                break

        time_module.sleep(30)

# ------------------------------
# FIND HEDGE STRIKES
# ------------------------------
def calculate_hedge_quantity(original_quantity):
    """
    Calculate hedge quantity as half of the original quantity, rounded DOWN to the nearest multiple of LOT_SIZE.
    
    Args:
        original_quantity (int): The original call or put quantity
        
    Returns:
        int: Hedge quantity rounded down to nearest multiple of LOT_SIZE
    """
    # Get lot size from config (imported via 'from config import *')
    try:
        lot_size = LOT_SIZE
    except NameError:
        # Fallback if LOT_SIZE not defined in config
        lot_size = 75
    
    # Calculate half of the original quantity
    half_quantity = original_quantity / 2
    
    # Round DOWN to the nearest multiple of lot_size
    hedge_quantity = (int(half_quantity) // lot_size) * lot_size
    
    # Ensure minimum quantity is lot_size (if original quantity is very small)
    hedge_quantity = max(lot_size, hedge_quantity)
    
    logging.info(f"Hedge quantity calculation: Original={original_quantity}, Half={half_quantity:.1f}, Rounded DOWN to {lot_size}s={hedge_quantity}")
    
    return int(hedge_quantity)


def find_hedges(call_strike, put_strike, use_next_week_expiry=False):
    """
    Find hedge strikes based on VIX-based strategy:
    - VIX < VIX_DELTA_THRESHOLD: Calendar Strategy (hedges from next {EXPIRY_DAY} expiry)
    - VIX >= VIX_DELTA_THRESHOLD: Strangle Strategy (hedges from same week's expiry)
    
    For sold Call -> Buy hedge 100 points higher.
    For sold Put  -> Buy hedge 100 points lower.
    """
    options = fetch_option_chain()
    if not options:
        logging.error("No options fetched.")
        return None, None

    # Determine target expiry for hedges dynamically based on main trade expiry
    main_trade_expiry = call_strike['expiry']
    if use_next_week_expiry:
        # Calendar Strategy: hedges use the next expiry AFTER main trade expiry
        strategy_name = "Calendar Strategy"
        retries = 0
        max_retries = 3
        target_expiry = None
        while retries <= max_retries and target_expiry is None:
            next_after_main = get_next_expiry_after(options, main_trade_expiry)
            if next_after_main:
                target_expiry = next_after_main
                logging.info(f"[CALENDAR] Hedge expiry set to next after main trade: {target_expiry}")
                break
            if retries < max_retries:
                logging.warning("[CALENDAR] No later expiry available; waiting and re-fetching option chain before taking hedge")
                time_module.sleep(API_RETRY_DELAY)
                options = fetch_option_chain()
                if not options:
                    logging.error("No options fetched while retrying for hedge expiry")
                    time_module.sleep(API_RETRY_DELAY)
                retries += 1
            else:
                break
        if target_expiry is None:
            logging.error("[CALENDAR] No later expiry found after retries; skipping hedge placement for now")
            return None, None
    else:
        # Strangle Strategy: hedges use the same expiry as main trade
        strategy_name = "Strangle Strategy"
        target_expiry = main_trade_expiry
        logging.info(f"[STRANGLE] Hedge expiry matches main trade expiry: {target_expiry}")

    # Determine hedge offsets by strategy
    if use_next_week_expiry:
        # Calendar: keep existing 100 point wings
        ce_offset = +100
        pe_offset = -100
    else:
        # Strangle: CE -50, PE +50
        ce_offset = -50
        pe_offset = +50

    # Find call hedge
    call_hedge = next(
        (o for o in options
         if o['strike'] == call_strike['strike'] + ce_offset
         and o['instrument_type'] == 'CE'
         and o['expiry'] == target_expiry),
        None
    )
    
    # Find put hedge
    put_hedge = next(
        (o for o in options
         if o['strike'] == put_strike['strike'] + pe_offset
         and o['instrument_type'] == 'PE'
         and o['expiry'] == target_expiry),
        None
    )
    
    # Log hedge results
    if call_hedge:
        logging.info(f"[{strategy_name}] Call hedge found: {call_hedge['tradingsymbol']} ({'+' if ce_offset>=0 else ''}{ce_offset} from {call_strike['strike']} CE)")
    else:
        logging.warning(f"[{strategy_name}] No call hedge found at {call_strike['strike'] + ce_offset} CE in {target_expiry}")
        
    if put_hedge:
        logging.info(f"[{strategy_name}] Put hedge found: {put_hedge['tradingsymbol']} ({'+' if pe_offset>=0 else ''}{pe_offset} from {put_strike['strike']} PE)")
    else:
        logging.warning(f"[{strategy_name}] No put hedge found at {put_strike['strike'] + pe_offset} PE in {target_expiry}")

    return call_hedge, put_hedge

def get_vix_based_delta_range():
    """
    Get delta range based on VIX levels
    
    Returns:
        tuple: (delta_low, delta_high, hedge_points, use_next_week_expiry)
    """
    try:
        # Get current VIX
        current_vix = get_india_vix()
        if current_vix is None:
            logging.warning("Unable to get current VIX, using VIX-based delta range as fallback")
            # Use VIX-based range even if VIX retrieval fails to maintain consistency
            return VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS_CANDR, True
        
        current_vix_display = current_vix * 100  # Convert back to display format
        
        # Get historical VIX data for average calculation
        try:
            # Calculate date range for historical data
            end_date = date.today()
            start_date = end_date - timedelta(days=30)  # 30 days buffer
            
            historical_data = kite.historical_data(
                instrument_token=int(VIX_INSTRUMENT_TOKEN),
                from_date=start_date,
                to_date=end_date,
                interval='day'
            )
            
            if historical_data:
                # Get last (VIX_HISTORICAL_DAYS - 1) days of historical data
                days_for_historical = VIX_HISTORICAL_DAYS - 1
                historical_vix_values = [candle['close'] for candle in historical_data[-days_for_historical:]]
                
                # Combine with current VIX for average
                all_vix_values = historical_vix_values + [current_vix_display]
                average_vix = sum(all_vix_values) / len(all_vix_values)
                
                # Check if average VIX is below threshold
                if average_vix < VIX_DELTA_THRESHOLD:
                    logging.info(f"[CALENDAR STRATEGY] Average VIX {average_vix:.2f} < {VIX_DELTA_THRESHOLD}, using wider delta range with next week hedges")
                    return VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS_CANDR, True
                else:
                    logging.info(f"[STRANGLE STRATEGY] Average VIX {average_vix:.2f} >= {VIX_DELTA_THRESHOLD}, using default delta range with same week hedges")
                    return TARGET_DELTA_LOW, TARGET_DELTA_HIGH, HEDGE_TRIGGER_POINTS_STRANGLE, False
            else:
                logging.warning("Unable to fetch historical VIX data, using VIX-based delta range as fallback")
                return VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS_CANDR, True
        except Exception as e:
            logging.error(f"Error calculating VIX average for delta range: {e}")
            return VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS_CANDR, True
            
    except Exception as e:
        logging.error(f"Error getting VIX-based delta range: {e}")
        return VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS_CANDR, True

def validate_delta_range_consistency(delta_low, delta_high, context=""):
    """
    Validate that delta range is consistent with VIX-based strategy
    
    Args:
        delta_low (float): Lower delta bound
        delta_high (float): Upper delta bound  
        context (str): Context for logging (e.g., "new strike selection", "RAAK framework")
    
    Returns:
        bool: True if range is consistent, False otherwise
    """
    try:
        # Get current VIX-based range for comparison
        vix_delta_low, vix_delta_high, _, _ = get_vix_based_delta_range()
        
        # Check if provided range matches VIX-based range
        if abs(delta_low - vix_delta_low) < 0.01 and abs(delta_high - vix_delta_high) < 0.01:
            logging.info(f"[DELTA VALIDATION] {context}: Range {delta_low:.2f}-{delta_high:.2f} matches VIX-based range [OK]")
            return True
        else:
            logging.warning(f"[DELTA VALIDATION] {context}: Range {delta_low:.2f}-{delta_high:.2f} differs from VIX-based range {vix_delta_low:.2f}-{vix_delta_high:.2f} [WARNING]")
            return False
    except Exception as e:
        logging.error(f"[DELTA VALIDATION] Error validating delta range: {e}")
        return False

def display_vix_analysis():
    """Display VIX analysis including current and average VIX"""
    try:
        print("\n" + "="*60)
        print("[VIX ANALYSIS]")
        print("="*60)
        
        # Get current VIX
        current_vix = get_india_vix()
        if current_vix is None:
            print("[ERROR] Unable to fetch current VIX")
            return
        
        current_vix_display = current_vix * 100  # Convert back to display format
        print(f"[CURRENT] VIX: {current_vix_display:.2f}")
        
        # Get historical VIX data for average calculation
        try:
            # Calculate date range for historical data
            end_date = date.today()
            start_date = end_date - timedelta(days=30)  # 30 days buffer
            
            historical_data = kite.historical_data(
                instrument_token=int(VIX_INSTRUMENT_TOKEN),
                from_date=start_date,
                to_date=end_date,
                interval='day'
            )
            
            if historical_data:
                # Get last (VIX_HISTORICAL_DAYS - 1) days of historical data (to combine with current day)
                days_for_historical = VIX_HISTORICAL_DAYS - 1
                historical_vix_values = [candle['close'] for candle in historical_data[-days_for_historical:]]
                
                # Combine with current VIX for VIX_HISTORICAL_DAYS average
                all_vix_values = historical_vix_values + [current_vix_display]
                average_vix = sum(all_vix_values) / len(all_vix_values)
                
                print(f"[AVERAGE] VIX ({VIX_HISTORICAL_DAYS} days): {average_vix:.2f}")
                
                # Calculate trend
                if current_vix_display > average_vix:
                    trend = "[UP] Above Average"
                    difference = current_vix_display - average_vix
                    difference_percent = (difference / average_vix) * 100
                elif current_vix_display < average_vix:
                    trend = "[DOWN] Below Average"
                    difference = current_vix_display - average_vix
                    difference_percent = (difference / average_vix) * 100
                else:
                    trend = "[FLAT] At Average"
                    difference = 0
                    difference_percent = 0
                
                print(f"[TREND] {trend}")
                if difference != 0:
                    print(f"[DIFF] {difference:+.2f} ({difference_percent:+.1f}%)")
                
                # Display individual VIX values
                print(f"[HISTORY] Last {VIX_HISTORICAL_DAYS} days VIX: {', '.join([f'{v:.2f}' for v in all_vix_values])}")
                
                
                # Display VIX-based delta recommendation
                try:
                    print(f"\n[VIX-BASED DELTA RECOMMENDATION]")
                    
                    # Check if average VIX is below threshold
                    if average_vix < VIX_DELTA_THRESHOLD:
                        print(f"   Strategy: [CALENDAR] CALENDAR STRATEGY")
                        print(f"   Delta Range: {VIX_DELTA_LOW:.2f} - {VIX_DELTA_HIGH:.2f} (VIX-based)")
                        print(f"   Hedge Points: {VIX_HEDGE_POINTS_CANDR}")
                        print(f"   Hedge Expiry: Next Week")
                        print(f"   Reason: VIX {average_vix:.2f} < {VIX_DELTA_THRESHOLD} - using wider delta range with next week hedges")
                    else:
                        print(f"   Strategy: [STRANGLE] STRANGLE STRATEGY")
                        print(f"   Delta Range: {TARGET_DELTA_LOW:.2f} - {TARGET_DELTA_HIGH:.2f} (Default)")
                        print(f"   Hedge Points: {HEDGE_TRIGGER_POINTS}")
                        print(f"   Hedge Expiry: Same Week")
                        print(f"   Reason: VIX {average_vix:.2f} >= {VIX_DELTA_THRESHOLD} - using default delta range with same week hedges")
                except Exception as e:
                    print(f"[WARNING] Could not get delta recommendation: {e}")
            else:
                print("[WARNING] Unable to fetch historical VIX data")
                print(f"[CURRENT] VIX: {current_vix_display:.2f}")
        except Exception as e:
            logging.error(f"Error calculating VIX average: {e}")
            print(f"[CURRENT] VIX: {current_vix_display:.2f}")
            print("[WARNING] Unable to calculate average VIX")
        
        print("="*60)
        print()
        
    except Exception as e:
        logging.error(f"Error displaying VIX analysis: {e}")
        print("[ERROR] Error displaying VIX analysis")

if __name__ == "__main__":
    # Global variables are now initialized at module level
    call_sl_to_be_placed = 0
    put_sl_to_be_placed = 0
    loss_taken = 0
    
    try:
        main()
    except KeyboardInterrupt:
        logging.info("[CONFIG MONITOR] Shutting down gracefully...")
        stop_config_monitoring()
        logging.info("[CONFIG MONITOR] Config monitoring stopped")
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        stop_config_monitoring()
    finally:
        # Ensure config monitoring is stopped
        stop_config_monitoring()

    # Quantities are now handled in the main function

    logging.info(f"api_key : {Input_api_key}")
    logging.info(f"api_secret : {Input_api_secret}")
    logging.info(f"request_token : {Input_request_token}")
    logging.info(f"Account : {Input_account}")

    # today_sl is now calculated in main() function

    # Display VIX analysis before starting trading
    display_vix_analysis()

    main()
