"""
StockSage Configuration file for the AI-Powered Options Trading Bot
"""
from datetime import time

# Trading Parameters
TARGET_DELTA_LOW = 0.29  # Lower bound for target delta
TARGET_DELTA_HIGH = 0.36  # Upper bound for target delta
MAX_STOP_LOSS_TRIGGER = 4  # Max number of stop-loss triggers allowed

# Market Hours
MARKET_START_TIME = time(9, 15)
MARKET_END_TIME = time(14, 45)
TRADING_START_TIME = time(9, 40)

# Stop Loss Configuration by Day
STOP_LOSS_CONFIG = {
    "Tuesday": 30,  # Weekly expiry day - higher stop loss
    "Wednesday": 27,
    "Thursday": 25,
    "Friday": 25,
    "Monday": 30,
    "default": 25
}

# API Configuration
KITE_API_BASE_URL = "https://api.kite.trade"

# Logging Configuration
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'

# VIX Configuration
VIX_INSTRUMENT_TOKEN = '264969'
VIX_FETCH_INTERVAL = 240  # seconds
VIX_HISTORICAL_DAYS = 10  # Number of trading days for historical VIX calculation

# VIX-Based Delta Range Configuration
VIX_DELTA_THRESHOLD = 13  # VIX threshold below which to use wider delta range
VIX_DELTA_LOW = 0.30  # Lower delta when VIX < threshold
VIX_DELTA_HIGH = 0.40  # Higher delta when VIX < threshold
VIX_HEDGE_POINTS = 8  # Deprecated: kept for backward compatibility
VIX_HEDGE_POINTS_CANDR = 8  # Calendar-specific hedge trigger points

# VWAP Configuration
VWAP_MINUTES = 5  # Number of minutes to calculate VWAP
VWAP_ENABLED = True  # Enable/disable VWAP analysis
VWAP_PRIORITY = True  # Prioritize strikes below VWAP

# Enhanced VWAP Safety Configuration
VWAP_MIN_CANDLES = 150  # Minimum candles required for VWAP calculation
VWAP_MAX_PRICE_DIFF_PERCENT = 15  # Maximum allowed difference between VWAP and price (3.0%)
VWAP_USE_PREVIOUS_DAY = True  # Use previous day data if current day has insufficient candles
VWAP_MAX_DAYS_BACK = 10  # Maximum days to look back for working day data

# Greek analysis removed - not needed for core trading functionality
# Greek analysis data paths removed

# IV Configuration for RAAK Framework
MIN_IV_THRESHOLD = 8.8  # Minimum IV threshold for individual strikes (25.0%)

# Delta Range Configuration
DELTA_MIN = 0.29  # Minimum allowed delta for initial trade selection
DELTA_MAX = 0.36  # Maximum allowed delta for initial trade selection
DELTA_MONITORING_THRESHOLD = 0.22  # Threshold for monitoring - if delta goes below this, modify SL
DELTA_MONITORING_ENABLED = True  # Enable continuous delta monitoring

# IV Display Configuration
IV_DISPLAY_ENABLED = True  # Enable IV display in logs
IV_CALCULATION_METHOD = 'BLACK_SCHOLES'  # Method for IV calculation

# Hedge Configuration
HEDGE_POINTS_DIFFERENCE = 100  # Points difference for hedge strikes
HEDGE_TRIGGER_POINTS = 11  # Points at which to trigger hedge (generic)
HEDGE_TRIGGER_POINTS_STRANGLE = 11  # Strangle-specific hedge trigger points

# Price Difference Threshold
MAX_PRICE_DIFFERENCE_PERCENTAGE = 1.5  # Maximum allowed price difference between call and put

# Automatic Trading Configuration
AUTO_TRADE_ENABLED = True  # Enable automatic trade execution for perfect RAAK scores
AUTO_TRADE_MIN_SCORE = 4.0  # Minimum RAAK score required for automatic trading
AUTO_TRADE_CONFIRMATION = False  # Require user confirmation before auto-trading (set to True for safety)

# Rate Limiting and API Management
API_RATE_LIMIT_DELAY = 2.0  # Minimum delay between API calls (seconds)
API_MAX_RETRIES = 3  # Maximum number of retries for failed API calls
API_RETRY_DELAY = 30  # Delay before retrying after rate limit error (seconds)
OPTION_CHAIN_CACHE_DURATION = 300  # Cache option chain data for 5 minutes (seconds)
LTP_CACHE_DURATION = 10  # Cache LTP data for 10 seconds
VWAP_CACHE_DURATION = 60  # Cache VWAP data for 1 minute

# Book Profit 

INITIAL_PROFIT_BOOKING = 14
SECOND_PROFIT_BOOKING = 28 