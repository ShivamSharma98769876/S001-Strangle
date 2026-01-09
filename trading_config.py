# Trading Bot Configuration
# Modify these values as needed for your trading strategy

# API Credentials (from InstallLibs.py)
API_KEY = "n683nqe7f3l7nzxl"
API_SECRET = "11krc3ysc604ppxsvq60862pnq73t4qi"
REQUEST_TOKEN = "qed5J2DoHsmx37m990hcN1fLuYsMpaCY"

# Trading Parameters
CALL_QUANTITY = 50      # Number of call options to trade
PUT_QUANTITY = 50       # Number of put options to trade

# Delta Range (for options selection)
DELTA_LOW = 0.29        # Minimum delta value
DELTA_HIGH = 0.35       # Maximum delta value

# Account Information
ACCOUNT = "TRADING_ACCOUNT"

# Logging Settings
CLEANUP_LOGS = True     # Clean up old log files before starting
LOG_DAYS = 30          # Number of days to keep log files

# Additional Settings
ENV_FILE = None         # Path to .env file (if using environment variables)

