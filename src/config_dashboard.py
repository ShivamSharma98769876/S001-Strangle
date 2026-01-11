"""
Web Dashboard for Real-time Config Parameter Management
Provides web interface for monitoring and updating trading parameters
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
import threading
import time
import logging
import secrets

# Disable Azure Monitor OpenTelemetry if not properly configured
# This prevents "Bad Request" errors when Application Insights is misconfigured
if not os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING'):
    os.environ.setdefault('APPLICATIONINSIGHTS_ENABLE_AGENT', 'false')
    # Suppress OpenTelemetry errors
    logging.getLogger('azure.monitor.opentelemetry').setLevel(logging.CRITICAL)

# Add parent directory to path for config imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(parent_dir)
sys.path.append(current_dir)

# Import config monitor
from config_monitor import get_config_monitor

# Import session manager
from src.security.saas_session_manager import SaaSSessionManager

# Azure Blob Storage diagnostic info - moved to lazy loading to speed up startup
# This will be printed after health endpoint is registered

# Import dashboard configuration
try:
    # Try importing from src.config first (since config.py is in src/)
    try:
        from src import config
    except ImportError:
        # Fallback to direct import if src is not in path
        import config
    
    DASHBOARD_HOST = getattr(config, 'DASHBOARD_HOST', '0.0.0.0')
    DASHBOARD_PORT = getattr(config, 'DASHBOARD_PORT', 8080)
    LOT_SIZE = getattr(config, 'LOT_SIZE', 75)  # Get lot size from config
    
    # Check for Azure environment - Azure provides port via HTTP_PLATFORM_PORT
    if os.getenv('HTTP_PLATFORM_PORT'):
        DASHBOARD_PORT = int(os.getenv('HTTP_PLATFORM_PORT'))
        print(f"[CONFIG] Azure environment detected - using port from HTTP_PLATFORM_PORT: {DASHBOARD_PORT}")
    elif os.getenv('PORT'):  # Alternative Azure port variable
        DASHBOARD_PORT = int(os.getenv('PORT'))
        print(f"[CONFIG] Azure environment detected - using port from PORT: {DASHBOARD_PORT}")
    
    print(f"[CONFIG] Loaded dashboard config: host={DASHBOARD_HOST}, port={DASHBOARD_PORT}")
except (ImportError, AttributeError) as e:
    # Fallback defaults if config not available
    DASHBOARD_HOST = '0.0.0.0'
    # Check for Azure port
    if os.getenv('HTTP_PLATFORM_PORT'):
        DASHBOARD_PORT = int(os.getenv('HTTP_PLATFORM_PORT'))
    elif os.getenv('PORT'):
        DASHBOARD_PORT = int(os.getenv('PORT'))
    else:
        DASHBOARD_PORT = 8080
    print(f"[CONFIG] Using default config (import error: {e}): host={DASHBOARD_HOST}, port={DASHBOARD_PORT}")

# Get the directory of this file
current_dir = os.path.dirname(os.path.abspath(__file__))
static_folder = os.path.join(current_dir, 'static')
template_folder = os.path.join(current_dir, 'templates')

app = Flask(__name__, 
            static_folder=static_folder,
            static_url_path='/static',
            template_folder=template_folder)

# CRITICAL: Register health endpoint IMMEDIATELY after app creation
# This must be done before any other operations to ensure Azure startup probe works
# These endpoints must respond in < 1 second to pass Azure startup probe
@app.route('/health')
@app.route('/healthz')
def health_check_early():
    """
    Health check endpoint for Azure App Service startup probe - must respond immediately.
    This endpoint has ZERO dependencies and responds instantly.
    """
    # Return immediately - absolutely minimal response (no imports, no dependencies)
    # This is critical for Azure startup probe to succeed
    return {'status': 'healthy', 'service': 'trading-bot-dashboard'}, 200

# Note: Root route '/' will be defined later for the dashboard
# Health endpoints above are registered first to ensure they work immediately

# Initialize basic logging early (before environment detection)
# Full logging setup with file handler will be done later
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Console output only for now
)
logger = logging.getLogger(__name__)

# Detect environment (local vs cloud)
def is_production_environment():
    """Detect if running in production/cloud environment"""
    # Check multiple indicators
    flask_env = os.getenv('FLASK_ENV', '').lower()
    is_azure = os.getenv('WEBSITE_SITE_NAME') or os.getenv('HTTP_PLATFORM_PORT') or os.getenv('PORT')
    is_aws = os.getenv('AWS_EXECUTION_ENV') or os.getenv('LAMBDA_TASK_ROOT')
    is_gcp = os.getenv('GAE_ENV') or os.getenv('GCLOUD_PROJECT')
    
    # Production if explicitly set or running on cloud platform
    return flask_env == 'production' or bool(is_azure or is_aws or is_gcp)

IS_PRODUCTION = is_production_environment()
IS_LOCAL = not IS_PRODUCTION

logger.info(f"[ENV] Environment detected: {'PRODUCTION/CLOUD' if IS_PRODUCTION else 'LOCAL/DEVELOPMENT'}")

# Configure Flask session for SaaS (works in both local and cloud)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
app.config['SESSION_COOKIE_SECURE'] = IS_PRODUCTION  # HTTPS only in production/cloud
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # 24 hour sessions

# Session storage: Auto-detect and configure
# - Local: Uses Flask's built-in in-memory session storage (no Redis needed)
# - Cloud: Uses Redis if REDIS_URL is set, otherwise uses Flask's built-in storage
REDIS_URL = os.getenv('REDIS_URL')
if REDIS_URL:
    try:
        from flask_session import Session
        import redis
        
        app.config['SESSION_TYPE'] = 'redis'
        app.config['SESSION_REDIS'] = redis.from_url(REDIS_URL)
        app.config['SESSION_PERMANENT'] = True
        app.config['SESSION_USE_SIGNER'] = True
        app.config['SESSION_KEY_PREFIX'] = 'saas_session:'
        
        Session(app)
        logger.info("[SESSION] Redis session storage enabled (distributed sessions)")
    except ImportError:
        logger.warning("[SESSION] Redis not available. Using Flask's built-in session storage.")
    except Exception as e:
        logger.warning(f"[SESSION] Redis configuration failed: {e}. Using Flask's built-in session storage.")
else:
    # No Redis URL - use Flask's built-in session storage (perfect for local and single server cloud)
    # This is the SAME approach as disciplined-Trader - works perfectly for single instance with multiple sessions
    logger.info("[SESSION] Using Flask's built-in session storage (works for local and single server cloud)")
    logger.info("[SESSION] ✅ Single instance mode: Multiple sessions supported (no Redis needed)")

# Setup file logging (logger already initialized above)
# Add file handler to existing logger
file_handler = logging.FileHandler('dashboard.log', encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

# Print Azure Blob Storage diagnostic info AFTER health endpoint is registered (lazy loading)
# This ensures health endpoint responds immediately
def print_azure_blob_diagnostics():
    """Print Azure Blob Storage configuration (called after health endpoint is ready)"""
    try:
        azure_blob_key = os.getenv('AzureBlobStorageKey')
        azure_blob_account = os.getenv('AZURE_BLOB_ACCOUNT_NAME')
        azure_blob_container = os.getenv('AZURE_BLOB_CONTAINER_NAME')
        azure_blob_enabled = os.getenv('AZURE_BLOB_LOGGING_ENABLED', 'False')
        logger.info("=" * 60)
        logger.info("[STARTUP] Azure Blob Storage Configuration:")
        logger.info(f"  AzureBlobStorageKey: {'SET' if azure_blob_key else 'NOT SET'}")
        logger.info(f"  AZURE_BLOB_ACCOUNT_NAME: '{azure_blob_account}' ({'SET' if azure_blob_account else 'NOT SET'})")
        logger.info(f"  AZURE_BLOB_CONTAINER_NAME: '{azure_blob_container}' ({'SET' if azure_blob_container else 'NOT SET'})")
        logger.info(f"  AZURE_BLOB_LOGGING_ENABLED: '{azure_blob_enabled}' -> {azure_blob_enabled.lower() == 'true'}")
        logger.info("=" * 60)
    except Exception as e:
        logger.warning(f"Error printing Azure Blob diagnostics: {e}")

# Call diagnostics after a short delay (non-blocking)
import threading
threading.Timer(1.0, print_azure_blob_diagnostics).start()

# Setup Azure Blob Storage logging if enabled
# Try to get account name from saved token first
def setup_dashboard_blob_logging():
    """Setup Azure Blob logging for dashboard with account name from saved token"""
    try:
        from src.environment import setup_azure_blob_logging, is_azure_environment
        if is_azure_environment():
            # Try to get account name from saved token
            account_name_for_logging = None
            
            # Check if kite_api_key is defined (it might not be at startup)
            try:
                global kite_api_key
                if kite_api_key:
                    saved_token, saved_account_name = load_access_token(kite_api_key)
                    if saved_account_name:
                        account_name_for_logging = saved_account_name
                        print(f"[STARTUP] Using account name from saved token: {account_name_for_logging}")
            except (NameError, AttributeError):
                # kite_api_key not defined yet, try to load from token file directly
                try:
                    if os.path.exists(TOKEN_STORAGE_FILE):
                        with open(TOKEN_STORAGE_FILE, 'r') as f:
                            tokens = json.load(f)
                            # Get first account name from tokens
                            for api_key, token_data in tokens.items():
                                if isinstance(token_data, dict) and token_data.get('account_name'):
                                    account_name_for_logging = token_data.get('account_name')
                                    print(f"[STARTUP] Using account name from token file: {account_name_for_logging}")
                                    break
                except Exception as e:
                    print(f"[STARTUP] Could not load account name from token file: {e}")
            
            # Also check global account_holder_name if available
            try:
                global account_holder_name
                if not account_name_for_logging and account_holder_name:
                    account_name_for_logging = account_holder_name
                    print(f"[STARTUP] Using account name from global variable: {account_name_for_logging}")
            except (NameError, AttributeError):
                pass
            
            print("[STARTUP] Azure environment detected - setting up Azure Blob Storage logging...")
            if account_name_for_logging:
                print(f"[STARTUP] Account name for logging: {account_name_for_logging}")
            
            # Use skip_verification=True for fast startup (prevents 504 timeout)
            # Verification will happen on first log write
            blob_handler, blob_path = setup_azure_blob_logging(
                account_name=account_name_for_logging, 
                logger_name=__name__,
                streaming_mode=True,  # Enable streaming logs
                skip_verification=True  # Skip network calls during startup (fast startup)
            )
            if blob_handler:
                logger.info(f"[STARTUP] Azure Blob Storage logging enabled: {blob_path}")
                print(f"[STARTUP] ✓ Azure Blob Storage logging configured: {blob_path}")
                return blob_handler, blob_path
            else:
                print("[STARTUP] ✗ Azure Blob Storage logging NOT configured (check environment variables)")
                return None, None
    except Exception as e:
        print(f"[STARTUP] Warning: Could not setup Azure Blob Storage logging: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None

# CRITICAL: Azure Blob Storage setup moved to lazy loading (background thread)
# This prevents blocking startup and 504 timeout errors
# The health endpoint must respond immediately, so blob storage setup happens after
def setup_blob_logging_lazy():
    """Setup Azure Blob logging in background thread (non-blocking)"""
    try:
        # Wait a moment to ensure health endpoint is ready
        time.sleep(2)
        setup_dashboard_blob_logging()
    except Exception as e:
        logger.warning(f"Error in lazy blob logging setup: {e}")

# Start blob logging setup in background thread (non-blocking)
blob_setup_thread = threading.Thread(target=setup_blob_logging_lazy, daemon=True)
blob_setup_thread.start()

logger.info("[DASHBOARD] Dashboard application initialized (Azure Blob Storage setup in background)")

# Authentication decorator for routes that require JWT token
def require_authentication(f):
    """Decorator to require authentication for API routes - STRICT on cloud environments"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # On cloud/production, enforce strict authentication
        if IS_PRODUCTION:
            # Double-check authentication is valid
            if not SaaSSessionManager.is_authenticated():
                logging.warning(f"[AUTH] Unauthorized API access attempt to {request.path} from {request.remote_addr} on cloud environment")
                return jsonify({
                    'success': False,
                    'error': 'Authentication required. This API endpoint is protected and requires JWT token authentication.',
                    'requires_auth': True
                }), 401
            
            # Additional check: ensure access token exists in session
            creds = SaaSSessionManager.get_credentials()
            if not creds.get('access_token'):
                logging.warning(f"[AUTH] Missing access token for API {request.path} from {request.remote_addr} on cloud environment")
                return jsonify({
                    'success': False,
                    'error': 'Invalid session. Access token not found. Please re-authenticate.',
                    'requires_auth': True
                }), 401
        else:
            # Local environment - still check but less strict
            if not SaaSSessionManager.is_authenticated():
                return jsonify({
                    'success': False,
                    'error': 'JWT token not associated. Please navigate through main application to authenticate.',
                    'requires_auth': True
                }), 401
        return f(*args, **kwargs)
    return decorated_function

def require_authentication_page(f):
    """Decorator to require authentication for page routes"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not SaaSSessionManager.is_authenticated():
            return render_template('auth_required.html', 
                                 message='JWT token not associated. Please navigate through main application to authenticate.'), 401
        return f(*args, **kwargs)
    return decorated_function

def _format_config_value(value):
    """Convert config values to readable strings for display."""
    try:
        if isinstance(value, (dict, list)):
            return json.dumps(value, indent=2)
        return str(value)
    except Exception:
        return "<unavailable>"

@app.route('/admin/panel')
@require_authentication_page
def admin_panel():
    """Simple admin page to view current config constants."""
    config_items = []

    # Use already-imported config module if available
    config_module = globals().get('config')

    if not config_module:
        logger.error("[ADMIN] Config module not available; cannot render admin panel")
    else:
        for attr in sorted(a for a in dir(config_module) if a.isupper() and not a.startswith('_')):
            value = getattr(config_module, attr, None)
            config_items.append({
                'name': attr,
                'value': _format_config_value(value),
                'type': type(value).__name__ if value is not None else 'unknown'
            })

    return render_template(
        'admin_panel.html',
        config_items=config_items
    )

# Session management: Extend session on each request
@app.before_request
def check_session_expiration():
    """Check and extend session on each request, enforce authentication on cloud for protected routes"""
    # List of routes that require authentication (especially on cloud)
    protected_routes = ['/live/', '/admin/panel', '/api/live-trader/', '/api/strategy/', '/api/trading/']
    
    # Check if this is a protected route
    is_protected = any(request.path.startswith(route) for route in protected_routes)
    
    # On cloud/production, strictly enforce authentication for protected routes
    if IS_PRODUCTION and is_protected:
        if not SaaSSessionManager.is_authenticated():
            logging.warning(f"[AUTH] Unauthorized access attempt to protected route {request.path} from {request.remote_addr} on cloud")
            # Return JSON for API routes, HTML for page routes
            if request.path.startswith('/api/'):
                return jsonify({
                    'success': False,
                    'error': 'Navigate through main application',
                    'requires_auth': True
                }), 401
            else:
                return render_template('auth_required.html', 
                                     message='Navigate through main application'), 401
        
        # Additional check: ensure access token exists
        creds = SaaSSessionManager.get_credentials()
        if not creds.get('access_token'):
            logging.warning(f"[AUTH] Missing access token for protected route {request.path} from {request.remote_addr} on cloud")
            if request.path.startswith('/api/'):
                return jsonify({
                    'success': False,
                    'error': 'Navigate through main application',
                    'requires_auth': True
                }), 401
            else:
                return render_template('auth_required.html', 
                                     message='Invalid session. Access token not found. Please re-authenticate through the main application.'), 401
    
    # Extend session on activity if authenticated
    if SaaSSessionManager.is_authenticated():
        # Extend session on activity
        SaaSSessionManager.extend_session()

# Global config monitor reference
config_monitor = None

# Per-session strategy managers: keyed by broker_id + device_id for true isolation
# Format: {f"{broker_id}_{device_id}": StrategyManager instance}
_strategy_managers = {}  # Dict[str, 'StrategyManager']
_strategy_managers_lock = threading.Lock()  # Thread-safe access

# Legacy global variables (kept for backward compatibility, but should use per-session managers)
strategy_thread = None
strategy_bot = None
strategy_process = None
strategy_running = False
# In-memory buffer to store subprocess output for real-time log display
strategy_output_buffer = []  # List of log lines from subprocess
strategy_output_lock = threading.Lock()  # Thread-safe access to buffer
MAX_BUFFER_SIZE = 1000  # Maximum number of lines to keep in buffer

class StrategyManager:
    """Per-session strategy manager for independent strategy execution per account/device"""
    def __init__(self, broker_id: str, device_id: str, account_name: str = None):
        self.broker_id = broker_id
        self.device_id = device_id
        self.account_name = account_name or broker_id
        self.strategy_process = None
        self.strategy_running = False
        self.strategy_output_buffer = []
        self.strategy_output_lock = threading.Lock()
        self.process_id = None
        logging.info(f"[STRATEGY MANAGER] Created for broker_id={broker_id}, device_id={device_id}, account={self.account_name}")
    
    def is_running(self) -> bool:
        """Check if strategy is actually running"""
        if self.strategy_process is None:
            return False
        try:
            poll_result = self.strategy_process.poll()
            if poll_result is None:
                return True
            else:
                # Process terminated
                self.strategy_running = False
                self.strategy_process = None
                return False
        except Exception:
            self.strategy_running = False
            self.strategy_process = None
            return False
    
    def stop(self):
        """Stop the strategy process"""
        if self.strategy_process:
            try:
                logging.info(f"[STRATEGY MANAGER] [{self.account_name}] Stopping strategy (PID: {self.process_id})")
                self.strategy_process.terminate()
                import time
                time.sleep(2)
                if self.strategy_process.poll() is None:
                    self.strategy_process.kill()
                self.strategy_process.wait(timeout=3)
            except Exception as e:
                logging.error(f"[STRATEGY MANAGER] [{self.account_name}] Error stopping process: {e}")
                try:
                    self.strategy_process.kill()
                except:
                    pass
            finally:
                self.strategy_process = None
                self.process_id = None
        self.strategy_running = False
    
    def get_logs(self, max_lines: int = 100) -> list:
        """Get recent logs from buffer"""
        with self.strategy_output_lock:
            return self.strategy_output_buffer[-max_lines:] if self.strategy_output_buffer else []

def get_strategy_manager() -> StrategyManager:
    """Get or create strategy manager for current session (broker_id + device_id)"""
    broker_id = SaaSSessionManager.get_broker_id()
    device_id = SaaSSessionManager.get_device_id()
    
    if not broker_id:
        logging.warning("[STRATEGY MANAGER] No broker_id in session")
        return None
    
    # Use composite key for true multi-device isolation
    manager_key = f"{broker_id}_{device_id}"
    
    with _strategy_managers_lock:
        if manager_key not in _strategy_managers:
            creds = SaaSSessionManager.get_credentials()
            account_name = creds.get('full_name') or creds.get('broker_id') or broker_id
            _strategy_managers[manager_key] = StrategyManager(
                broker_id=broker_id,
                device_id=device_id,
                account_name=account_name
            )
        return _strategy_managers[manager_key]

# Global Kite client for authentication (can be used independently)
kite_client_global = None
kite_api_key = None
kite_api_secret = None
account_holder_name = None  # Store account holder name from profile
strategy_account_name = None  # Store account name used when starting strategy (for log retrieval)

# Token persistence file path
TOKEN_STORAGE_FILE = os.path.join(current_dir, 'kite_tokens.json')

# Global trading credentials (for main trading script)
trading_credentials = {
    'account': None,
    'api_key': None,
    'api_secret': None,
    'request_token': None,
    'set': False
}

def set_config_monitor(monitor):
    """Set the global config monitor reference"""
    global config_monitor
    config_monitor = monitor

# Token Persistence Functions
def save_access_token(api_key, access_token, account_name=None):
    """Save access token to file for persistence"""
    try:
        tokens = {}
        if os.path.exists(TOKEN_STORAGE_FILE):
            try:
                with open(TOKEN_STORAGE_FILE, 'r') as f:
                    tokens = json.load(f)
            except (json.JSONDecodeError, IOError):
                tokens = {}
        
        tokens[api_key] = {
            'access_token': access_token,
            'account_name': account_name,
            'saved_at': datetime.now().isoformat()
        }
        
        with open(TOKEN_STORAGE_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        
        logging.info(f"[TOKEN] Saved access token for API key: {api_key[:8]}...")
        return True
    except Exception as e:
        logging.error(f"[TOKEN] Error saving token: {e}")
        return False

def load_access_token(api_key):
    """Load access token from file"""
    try:
        if os.path.exists(TOKEN_STORAGE_FILE):
            with open(TOKEN_STORAGE_FILE, 'r') as f:
                tokens = json.load(f)
                if api_key in tokens:
                    token_data = tokens[api_key]
                    logging.info(f"[TOKEN] Loaded access token for API key: {api_key[:8]}...")
                    return token_data.get('access_token'), token_data.get('account_name')
    except Exception as e:
        logging.error(f"[TOKEN] Error loading token: {e}")
    return None, None

def validate_kite_connection(kite_client, retry_count=2):
    """Validate Kite connection with retry logic"""
    if not kite_client or not hasattr(kite_client, 'kite'):
        return False, "Kite client not initialized"
    
    for attempt in range(retry_count + 1):
        try:
            profile = kite_client.kite.profile()
            return True, profile
        except Exception as e:
            error_msg = str(e).lower()
            if attempt < retry_count:
                logging.warning(f"[CONNECTION] Validation attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(0.5)  # Brief delay before retry
            else:
                if "invalid" in error_msg or "expired" in error_msg or "token" in error_msg:
                    return False, "Token expired or invalid"
                elif "network" in error_msg or "timeout" in error_msg or "connection" in error_msg:
                    return False, "Network error"
                else:
                    return False, f"Connection error: {str(e)[:100]}"
    
    return False, "Connection validation failed"

def reconnect_kite_client():
    """Attempt to reconnect using saved token"""
    global kite_client_global, kite_api_key, kite_api_secret, account_holder_name
    
    if not kite_api_key:
        logging.warning("[RECONNECT] No API key available for reconnection")
        return False
    
    access_token, saved_account_name = load_access_token(kite_api_key)
    if not access_token:
        logging.warning("[RECONNECT] No saved token found")
        return False
    
    try:
        try:
            from src.kite_client import KiteClient
        except ImportError:
            from kite_client import KiteClient
        
        kite_client_global = KiteClient(
            kite_api_key,
            kite_api_secret or '',
            access_token=access_token,
            account='DASHBOARD'
        )
        
        # Validate connection
        is_valid, result = validate_kite_connection(kite_client_global)
        if is_valid:
            profile = result
            account_holder_name = profile.get('user_name') or profile.get('user_id') or saved_account_name or 'Trading Account'
            kite_client_global.account = account_holder_name
            logging.info(f"[RECONNECT] Successfully reconnected. Account: {account_holder_name}")
            
            # Re-setup Azure Blob logging with the correct account name
            try:
                from src.environment import setup_azure_blob_logging, is_azure_environment
                if is_azure_environment() and account_holder_name:
                    print(f"[RECONNECT] Re-setting up Azure Blob Storage logging with account: {account_holder_name}")
                    # Remove old blob handler if exists
                    logger = logging.getLogger(__name__)
                    for handler in logger.handlers[:]:
                        if hasattr(handler, 'container_name'):  # Azure Blob handler
                            logger.removeHandler(handler)
                            handler.close()
                    
                    # Setup new blob handler with correct account name
                    blob_handler, blob_path = setup_azure_blob_logging(
                        account_name=account_holder_name,
                        logger_name=__name__,
                        streaming_mode=True
                    )
                    if blob_handler:
                        logger.info(f"[RECONNECT] Azure Blob Storage logging updated: {blob_path}")
                        print(f"[RECONNECT] ✓ Azure Blob Storage logging updated with account: {account_holder_name}")
            except Exception as e:
                print(f"[RECONNECT] Warning: Could not update Azure Blob logging: {e}")
            return True
        else:
            logging.warning(f"[RECONNECT] Reconnection failed: {result}")
            kite_client_global = None
            return False
    except Exception as e:
        logging.error(f"[RECONNECT] Error during reconnection: {e}")
        kite_client_global = None
        return False

@app.route('/favicon.ico')
def favicon():
    """Return empty favicon to prevent 404 errors"""
    from flask import Response
    return Response('', mimetype='image/x-icon')

# Health endpoint is already registered at the top of the file (line ~95)
# This ensures it's available immediately when the app is imported

@app.route('/')
def dashboard():
    """Main dashboard page - Zero Touch Strangle landing page"""
    import os
    from environment import is_azure_environment
    
    # Always show the landing page first
    # Get API key for authentication link (if available)
    api_key = None
    try:
        global kite_api_key
        if kite_api_key:
            api_key = kite_api_key
        else:
            # Try to get from environment or config
            api_key = os.getenv('KITE_API_KEY')
    except:
        pass
    
    # Get account holder name if authenticated
    global account_holder_name
    account_name_display = account_holder_name if account_holder_name else None
    
    # Pass account name to template
    return render_template('config_dashboard.html', 
                         api_key=api_key, 
                         is_azure=is_azure_environment(),
                         account_holder_name=account_name_display)

@app.route('/credentials')
def credentials_input():
    """Credentials input page for Azure"""
    return render_template('credentials_input.html')

@app.route('/api/config/current')
def get_current_config():
    """Get current configuration values"""
    try:
        monitor = get_config_monitor()
        if monitor:
            current_config = monitor.get_current_config()
            return jsonify({
                'status': 'success',
                'config': current_config,
                'timestamp': datetime.now().isoformat()
            })
        else:
            # Fallback: try to get config directly
            try:
                import config
                config_dict = {
                    'VIX_HEDGE_POINTS_CANDR': getattr(config, 'VIX_HEDGE_POINTS_CANDR', 8),
                    'HEDGE_TRIGGER_POINTS_STRANGLE': getattr(config, 'HEDGE_TRIGGER_POINTS_STRANGLE', 12),
                    'TARGET_DELTA_LOW': getattr(config, 'TARGET_DELTA_LOW', 0.29),
                    'TARGET_DELTA_HIGH': getattr(config, 'TARGET_DELTA_HIGH', 0.36),
                    'MAX_STOP_LOSS_TRIGGER': getattr(config, 'MAX_STOP_LOSS_TRIGGER', 6),
                    'VIX_DELTA_LOW': getattr(config, 'VIX_DELTA_LOW', 0.30),
                    'VIX_DELTA_HIGH': getattr(config, 'VIX_DELTA_HIGH', 0.40),
                    'VIX_DELTA_THRESHOLD': getattr(config, 'VIX_DELTA_THRESHOLD', 13),
                    'VIX_HEDGE_POINTS_CANDR': getattr(config, 'VIX_HEDGE_POINTS_CANDR', 16),
                    'DELTA_MONITORING_THRESHOLD': getattr(config, 'DELTA_MONITORING_THRESHOLD', 0.225),
                    'DELTA_MIN': getattr(config, 'DELTA_MIN', 0.29),
                    'DELTA_MAX': getattr(config, 'DELTA_MAX', 0.36),
                    'HEDGE_TRIGGER_POINTS': getattr(config, 'HEDGE_TRIGGER_POINTS', 16),
                    'HEDGE_TRIGGER_POINTS_STRANGLE': getattr(config, 'HEDGE_TRIGGER_POINTS_STRANGLE', 16),
                    'HEDGE_POINTS_DIFFERENCE': getattr(config, 'HEDGE_POINTS_DIFFERENCE', 100),
                    'VWAP_MINUTES': getattr(config, 'VWAP_MINUTES', 5),
                    'VWAP_MAX_PRICE_DIFF_PERCENT': getattr(config, 'VWAP_MAX_PRICE_DIFF_PERCENT', 15),
                    'VWAP_MIN_CANDLES': getattr(config, 'VWAP_MIN_CANDLES', 150),
                    'INITIAL_PROFIT_BOOKING': getattr(config, 'INITIAL_PROFIT_BOOKING', 32),
                    'SECOND_PROFIT_BOOKING': getattr(config, 'SECOND_PROFIT_BOOKING', 40),
                    'MAX_PRICE_DIFFERENCE_PERCENTAGE': getattr(config, 'MAX_PRICE_DIFFERENCE_PERCENTAGE', 1.5),
                    'STOP_LOSS_CONFIG': getattr(config, 'STOP_LOSS_CONFIG', {
                        'Tuesday': 30,
                        'Wednesday': 30,
                        'Thursday': 30,
                        'Friday': 30,
                        'Monday': 30,
                        'default': 30
                    })
                }
                return jsonify({
                    'status': 'success',
                    'config': config_dict,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({
                    'status': 'error',
                    'message': f'Config monitor not initialized and fallback failed: {str(e)}'
                }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/config/lot-size', methods=['GET'])
def get_lot_size():
    """Get lot size from config"""
    try:
        return jsonify({
            'success': True,
            'lot_size': LOT_SIZE
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'lot_size': 75  # Fallback default
        }), 500

@app.route('/api/config/history')
def get_config_history():
    """Get configuration change history"""
    try:
        monitor = get_config_monitor()
        if monitor:
            history = monitor.get_config_history()
            return jsonify({
                'status': 'success',
                'history': history,
                'count': len(history)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Config monitor not initialized'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/config/update', methods=['POST'])
def update_config():
    """Update configuration parameter"""
    try:
        data = request.get_json()
        param_name = data.get('parameter')
        new_value = data.get('value')
        
        if not param_name or new_value is None:
            return jsonify({
                'status': 'error',
                'message': 'Parameter name and value required'
            }), 400
            
        # Validate parameter
        monitor = get_config_monitor()
        if monitor:
            print(f"[DEBUG] Validating {param_name} = '{new_value}' (type: {type(new_value)})")
            if not monitor.validate_parameter(param_name, new_value):
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid value for parameter {param_name}. Please check the value range and type.'
                }), 400
        else:
            # If no monitor available, do basic validation
            print(f"[DEBUG] No config monitor available, doing basic validation for {param_name} = '{new_value}'")
            try:
                # Basic type conversion and range check
                if isinstance(new_value, str):
                    if '.' in new_value:
                        new_value = float(new_value)
                    else:
                        new_value = int(new_value)
                
                # Basic range validation for known parameters
                if param_name == 'HEDGE_TRIGGER_POINTS_STRANGLE':
                    if not (isinstance(new_value, (int, float)) and 0 < new_value <= 100):
                        return jsonify({
                            'status': 'error',
                            'message': f'Invalid value for parameter {param_name}. Must be between 0 and 100.'
                        }), 400
            except (ValueError, TypeError):
                return jsonify({
                    'status': 'error',
                    'message': f'Invalid value for parameter {param_name}. Please enter a valid number.'
                }), 400
            
        # Convert value to appropriate type if needed
        if isinstance(new_value, dict):
            # Already a dict, use as is
            pass
        elif isinstance(new_value, str):
            # Try to convert to number if possible
            try:
                if '.' in new_value:
                    new_value = float(new_value)
                else:
                    new_value = int(new_value)
            except ValueError:
                # Keep as string
                pass
        
        # Update config file
        success = update_config_file(param_name, new_value)
        
        if success:
            # Trigger config reload if monitor is available
            monitor = get_config_monitor()
            if monitor:
                try:
                    monitor.reload_config()
                except Exception as reload_error:
                    print(f"Warning: Config reload failed: {reload_error}")
            
            return jsonify({
                'status': 'success',
                'message': f'Updated {param_name} to {new_value}',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to update parameter {param_name}. Check if the parameter exists in config.py'
            }), 500
            
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/config/export')
def export_config():
    """Export configuration history"""
    try:
        monitor = get_config_monitor()
        if monitor:
            filename = f'config_history_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
            monitor.export_config_history(filename)
            return jsonify({
                'status': 'success',
                'message': f'Exported to {filename}',
                'filename': filename
            })
        else:
            return jsonify({
                'status': 'error',
                'message': 'Config monitor not initialized'
            }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/trading/positions')
def get_trading_positions():
    """Get current trading positions and P&L"""
    try:
        # Try to get positions from the main strategy
        import sys
        main_module = sys.modules.get('__main__')
        
        positions = []
        total_pnl = 0
        
        # Check if we have access to kite object and positions
        if hasattr(main_module, 'kite') and main_module.kite:
            try:
                # Get positions from Kite API
                kite_positions = main_module.kite.positions()
                
                if kite_positions and 'net' in kite_positions:
                    for position in kite_positions['net']:
                        if position['quantity'] != 0:  # Only show active positions
                            pnl = position.get('pnl', 0)
                            total_pnl += pnl
                            
                            positions.append({
                                'instrument': position.get('tradingsymbol', 'N/A'),
                                'product': position.get('product', 'NRML'),
                                'quantity': position.get('quantity', 0),
                                'average_price': position.get('average_price', 0),
                                'last_price': position.get('last_price', 0),
                                'pnl': pnl,
                                'pnl_percentage': position.get('pnl_percentage', 0),
                                'day_change': position.get('day_change', 0),
                                'day_change_percentage': position.get('day_change_percentage', 0)
                            })
            except Exception as e:
                # Fallback: return mock data for demo
                positions = [
                    {
                        'instrument': 'NIFTY 4th NOV 25900 PE NFO',
                        'product': 'NRML',
                        'quantity': 150,
                        'average_price': 104.25,
                        'last_price': 98.35,
                        'pnl': -885.00,
                        'pnl_percentage': -5.66,
                        'day_change': -5.90,
                        'day_change_percentage': -5.66
                    },
                    {
                        'instrument': 'NIFTY 4th NOV 26400 CE NFO',
                        'product': 'NRML',
                        'quantity': 150,
                        'average_price': 97.95,
                        'last_price': 98.25,
                        'pnl': 45.00,
                        'pnl_percentage': 0.31,
                        'day_change': 0.30,
                        'day_change_percentage': 0.31
                    }
                ]
                total_pnl = -840.00
        
        return jsonify({
            'status': 'success',
            'positions': positions,
            'total_pnl': total_pnl,
            'position_count': len(positions),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/trading/set-credentials', methods=['POST'])
def set_trading_credentials():
    """Set credentials for the main trading script (used on Azure)"""
    try:
        global trading_credentials
        
        data = request.get_json()
        
        account = data.get('account', '').strip()
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        request_token = data.get('request_token', '').strip()
        
        if not all([account, api_key, api_secret, request_token]):
            return jsonify({
                'success': False,
                'error': 'All fields are required: account, api_key, api_secret, request_token'
            }), 400
        
        # Store credentials
        trading_credentials = {
            'account': account,
            'api_key': api_key,
            'api_secret': api_secret,
            'request_token': request_token,
            'set': True
        }
        
        logging.info(f"[CREDENTIALS] Credentials set for account: {account}")
        
        return jsonify({
            'success': True,
            'message': 'Credentials set successfully'
        })
    except Exception as e:
        logging.error(f"[CREDENTIALS] Error setting credentials: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/trading/credentials-status', methods=['GET'])
def get_credentials_status():
    """Check if credentials are set"""
    global trading_credentials
    return jsonify({
        'credentials_set': trading_credentials['set'],
        'account': trading_credentials['account'] if trading_credentials['set'] else None
    })

@app.route('/api/trading/get-credentials', methods=['GET'])
def get_trading_credentials():
    """Get credentials for the main trading script (internal use)"""
    global trading_credentials
    if trading_credentials['set']:
        return jsonify({
            'success': True,
            'credentials': {
                'account': trading_credentials['account'],
                'api_key': trading_credentials['api_key'],
                'api_secret': trading_credentials['api_secret'],
                'request_token': trading_credentials['request_token']
            }
        })
    else:
        return jsonify({
            'success': False,
            'error': 'Credentials not set'
        }), 404

@app.route('/api/trading/status')
def get_trading_status():
    """Get current trading status"""
    try:
        import sys
        main_module = sys.modules.get('__main__')
        
        status = {
            'is_trading_active': False,
            'current_time': datetime.now().strftime('%H:%M:%S'),
            'market_status': 'Unknown',
            'active_trades': 0,
            'total_pnl': 0
        }
        
        # Check if trading is active
        if hasattr(main_module, 'kite') and main_module.kite:
            try:
                # Get market status
                market_status = main_module.kite.instruments('NSE')
                if market_status:
                    status['market_status'] = 'Open'
                    status['is_trading_active'] = True
            except:
                status['market_status'] = 'Closed'
        
        return jsonify({
            'status': 'success',
            'data': status,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# New Dashboard API Endpoints
@app.route('/api/dashboard/metrics')
@require_authentication
def get_dashboard_metrics():
    """Get Total Day P&L for trades with tag='S001'"""
    try:
        global strategy_bot, kite_client_global
        
        total_day_pnl = 0.0
        
        # Try to get orders with tag="S001" and calculate P&L
        kite_client = None
        if strategy_bot and hasattr(strategy_bot, 'kite_client'):
            kite_client = strategy_bot.kite_client
        elif kite_client_global:
            kite_client = kite_client_global
        
        if kite_client and hasattr(kite_client, 'kite'):
            try:
                # Get all orders
                orders = kite_client.kite.orders()
                
                # Filter orders by tag="S001" and get today's date
                today = datetime.now().date()
                s001_tradingsymbols = set()
                
                for order in orders:
                    if order.get('tag') == 'S001':
                        # Check if order is from today
                        order_timestamp = order.get('order_timestamp', '')
                        if order_timestamp:
                            try:
                                order_date = datetime.strptime(order_timestamp, '%Y-%m-%d %H:%M:%S').date()
                                if order_date == today:
                                    tradingsymbol = order.get('tradingsymbol', '')
                                    exchange = order.get('exchange', 'NFO')
                                    if tradingsymbol:
                                        s001_tradingsymbols.add((exchange, tradingsymbol))
                            except:
                                pass
                
                # Get positions and match with S001 orders
                try:
                    positions = kite_client.kite.positions()
                    if positions and 'net' in positions:
                        for pos in positions['net']:
                            if pos.get('quantity', 0) != 0:
                                tradingsymbol = pos.get('tradingsymbol', '')
                                exchange = pos.get('exchange', 'NFO')
                                
                                # Check if this position matches any S001 order
                                if (exchange, tradingsymbol) in s001_tradingsymbols:
                                    total_day_pnl += pos.get('pnl', 0)
                except Exception as e:
                    print(f"Error checking positions: {e}")
                    
            except Exception as e:
                print(f"Error calculating Total Day P&L: {e}")
        
        return jsonify({
            'status': 'success',
            'totalDayPnl': round(total_day_pnl, 2)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'totalDayPnl': 0.0
        }), 500

@app.route('/api/dashboard/positions')
@require_authentication
def get_dashboard_positions():
    """Get all positions (active and inactive) for dashboard"""
    try:
        global strategy_bot, kite_client_global
        
        positions = []
        total_pnl = 0.0
        
        kite_client = None
        if strategy_bot and hasattr(strategy_bot, 'kite_client'):
            kite_client = strategy_bot.kite_client
        elif kite_client_global:
            kite_client = kite_client_global
        
        if kite_client and hasattr(kite_client, 'kite'):
            try:
                kite_positions = kite_client.kite.positions()
                if kite_positions and 'net' in kite_positions:
                    # Get all positions including inactive ones (quantity = 0)
                    for pos in kite_positions['net']:
                        # Include all positions, even with quantity 0 (inactive)
                        pnl = pos.get('pnl', 0)
                        total_pnl += pnl
                        
                        positions.append({
                            'symbol': pos.get('tradingsymbol', 'N/A'),
                            'exchange': pos.get('exchange', 'NFO'),
                            'product': pos.get('product', 'NRML'),
                            'entryPrice': pos.get('average_price', 0),
                            'currentPrice': pos.get('last_price', 0),
                            'quantity': pos.get('quantity', 0),
                            'pnl': pnl,
                            'pnlPercentage': pos.get('pnl_percentage', 0),
                            'dayChange': pos.get('day_change', 0),
                            'dayChangePercentage': pos.get('day_change_percentage', 0),
                            'isActive': pos.get('quantity', 0) != 0
                        })
            except Exception as e:
                print(f"Error fetching positions: {e}")
        
        return jsonify({
            'status': 'success',
            'positions': positions,
            'totalPnl': round(total_pnl, 2)
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashboard/trade-history')
@require_authentication
def get_trade_history():
    """Get trade history from s001_trades database table"""
    try:
        date_filter = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
        show_all = request.args.get('all', 'false').lower() == 'true'
        
        trades = []
        summary = {
            'totalTrades': 0,
            'totalProfit': 0.0,
            'totalLoss': 0.0,
            'netPnl': 0.0,
            'winRate': 0.0
        }
        
        # Try to use database first
        try:
            from src.database.models import DatabaseManager
            from src.database.repository import TradeRepository
            from datetime import date as date_type
            
            db_manager = DatabaseManager()
            trade_repo = TradeRepository(db_manager)
            session = db_manager.get_session()
            
            try:
                # Get broker_id from session (SaaS-compliant)
                broker_id = SaaSSessionManager.get_broker_id()
                if not broker_id:
                    # Fallback to default if not authenticated
                    broker_id = 'default'
                
                # Parse date filter
                trade_date = datetime.strptime(date_filter, '%Y-%m-%d').date() if date_filter else date_type.today()
                
                # Get trades from database
                if show_all:
                    db_trades = trade_repo.get_all_trades(session, broker_id)
                else:
                    db_trades = trade_repo.get_trades_by_date(session, broker_id, trade_date, show_all)
                
                for trade in db_trades:
                    trades.append({
                        'symbol': trade.trading_symbol,
                        'entry_time': trade.entry_time.isoformat() if trade.entry_time else '',
                        'exit_time': trade.exit_time.isoformat() if trade.exit_time else '',
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price,
                        'quantity': trade.quantity,
                        'pnl': trade.realized_pnl,
                        'trade_type': trade.transaction_type
                    })
                    
                    # Update summary
                    summary['totalTrades'] += 1
                    if trade.realized_pnl >= 0:
                        summary['totalProfit'] += trade.realized_pnl
                    else:
                        summary['totalLoss'] += abs(trade.realized_pnl)
                    summary['netPnl'] += trade.realized_pnl
                
                # Calculate win rate
                if summary['totalTrades'] > 0:
                    winning_trades = sum(1 for t in trades if t['pnl'] >= 0)
                    summary['winRate'] = (winning_trades / summary['totalTrades']) * 100
                
            finally:
                session.close()
        except Exception as db_error:
            # Fallback to JSON file if database not available
            logger.warning(f"Database not available, using JSON fallback: {db_error}")
            try:
                pnl_data_path = os.path.join('src', 'pnl_data', 'daily_pnl.json')
                if os.path.exists(pnl_data_path):
                    with open(pnl_data_path, 'r') as f:
                        pnl_data = json.load(f)
                        
                    # Filter by date if needed
                    for trade in pnl_data.get('trades', []):
                        trade_date = trade.get('date', '')
                        if show_all or trade_date == date_filter:
                            trades.append({
                                'symbol': trade.get('symbol', 'N/A'),
                                'entry_time': trade.get('entry_time', ''),
                                'exit_time': trade.get('exit_time', ''),
                                'entry_price': trade.get('entry_price', 0),
                                'exit_price': trade.get('exit_price', 0),
                                'quantity': trade.get('quantity', 0),
                                'pnl': trade.get('pnl', 0),
                                'trade_type': trade.get('type', 'SELL')
                            })
                            
                            # Update summary
                            summary['totalTrades'] += 1
                            if trade.get('pnl', 0) >= 0:
                                summary['totalProfit'] += trade.get('pnl', 0)
                            else:
                                summary['totalLoss'] += abs(trade.get('pnl', 0))
                            summary['netPnl'] += trade.get('pnl', 0)
                    
                    # Calculate win rate
                    if summary['totalTrades'] > 0:
                        winning_trades = sum(1 for t in trades if t['pnl'] >= 0)
                        summary['winRate'] = (winning_trades / summary['totalTrades']) * 100
            except Exception as e:
                logger.error(f"Error loading trade history from JSON: {e}")
        
        return jsonify({
            'status': 'success',
            'trades': trades,
            'summary': summary
        })
    except Exception as e:
        logger.error(f"Error in get_trade_history: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashboard/cumulative-pnl')
@require_authentication
def get_cumulative_pnl():
    """Get cumulative P&L from s001_trades database table"""
    try:
        from src.database.models import DatabaseManager
        from src.database.repository import TradeRepository
        from datetime import date, timedelta
        
        db_manager = DatabaseManager()
        trade_repo = TradeRepository(db_manager)
        session = db_manager.get_session()
        
        try:
            # Get broker_id from session (SaaS-compliant)
            broker_id = SaaSSessionManager.get_broker_id()
            if not broker_id:
                # Fallback to default if not authenticated
                broker_id = 'default'
            
            today = date.today()
            start_of_year = date(today.year, 1, 1)
            start_of_month = date(today.year, today.month, 1)
            start_of_week = today - timedelta(days=today.weekday())
            start_of_day = today
            
            # Calculate cumulative P&L for different periods
            all_time_pnl = trade_repo.get_cumulative_pnl(session, broker_id, date(2020, 1, 1), today)
            year_pnl = trade_repo.get_cumulative_pnl(session, broker_id, start_of_year, today)
            month_pnl = trade_repo.get_cumulative_pnl(session, broker_id, start_of_month, today)
            week_pnl = trade_repo.get_cumulative_pnl(session, broker_id, start_of_week, today)
            day_pnl = trade_repo.get_cumulative_pnl(session, broker_id, start_of_day, today)
            
            return jsonify({
                'status': 'success',
                'all_time': all_time_pnl,
                'year': year_pnl,
                'month': month_pnl,
                'week': week_pnl,
                'day': day_pnl
            })
        finally:
            session.close()
    except Exception as e:
        logger.error(f"Error getting cumulative P&L: {e}")
        # Return zeros if database not available
        return jsonify({
            'status': 'success',
            'all_time': 0.0,
            'year': 0.0,
            'month': 0.0,
            'week': 0.0,
            'day': 0.0
        })

@app.route('/api/database/init', methods=['POST'])
def init_database():
    """Initialize database tables (s001_*)"""
    try:
        from src.database.models import DatabaseManager
        
        db_manager = DatabaseManager()
        db_manager.create_tables()
        
        return jsonify({
            'status': 'success',
            'message': 'Database tables initialized successfully (s001_*)',
            'tables': [
                's001_positions',
                's001_trades',
                's001_daily_stats',
                's001_audit_logs',
                's001_daily_purge_flags',
                's001_candles'
            ]
        })
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/dashboard/status')
@require_authentication
def get_dashboard_status():
    """Get dashboard status including daily loss from s001_daily_stats"""
    try:
        from src.database.models import DatabaseManager
        from src.database.repository import DailyStatsRepository
        
        db_manager = DatabaseManager()
        daily_stats_repo = DailyStatsRepository(db_manager)
        session = db_manager.get_session()
        
        try:
            # Get broker_id from session (SaaS-compliant)
            broker_id = SaaSSessionManager.get_broker_id()
            if not broker_id:
                # Fallback to default if not authenticated
                broker_id = 'default'
            
            daily_loss_used = daily_stats_repo.get_daily_loss(session, broker_id)
            daily_loss_limit = daily_stats_repo.get_daily_loss_limit(session, broker_id)
            
            return jsonify({
                'status': 'success',
                'daily_loss_used': daily_loss_used,
                'daily_loss_limit': daily_loss_limit
            })
        finally:
            session.close()
    except Exception as e:
        logger.warning(f"Database not available for status, using defaults: {e}")
        # Return defaults if database not available
        return jsonify({
            'status': 'success',
            'daily_loss_used': 0.0,
            'daily_loss_limit': 5000.0
        })

@app.route('/api/dashboard/pnl-chart')
@require_authentication
def get_pnl_chart_data():
    """Get P&L chart data"""
    try:
        # Generate sample time labels (last 30 data points)
        labels = []
        current_pnl = []
        protected_profit = []
        total_pnl = []
        
        # Generate sample data (in real implementation, fetch from actual P&L records)
        import random
        base_time = datetime.now()
        for i in range(30):
            time_label = (base_time.replace(second=0, microsecond=0) - 
                         timedelta(minutes=30-i)).strftime('%H:%M:%S')
            labels.append(time_label)
            
            # Sample data - replace with actual data
            current_pnl.append(random.uniform(-100, 100))
            protected_profit.append(random.uniform(0, 200))
            total_pnl.append(random.uniform(-50, 150))
        
        return jsonify({
            'status': 'success',
            'labels': labels,
            'currentPnl': current_pnl,
            'protectedProfit': protected_profit,
            'totalPnl': total_pnl
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/strategy/start', methods=['POST'])
def start_strategy():
    """Start the trading strategy"""
    try:
        global strategy_thread, strategy_bot, strategy_running
        
        if strategy_running:
            return jsonify({
                'status': 'error',
                'message': 'Strategy is already running'
            }), 400
        
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['apiKey', 'apiSecret', 'requestToken', 'account', 'callQuantity', 'putQuantity']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'status': 'error',
                    'message': f'Missing required field: {field}'
                }), 400
        
        # Store API credentials globally for authentication
        global kite_api_key, kite_api_secret, kite_client_global
        kite_api_key = data['apiKey']
        kite_api_secret = data['apiSecret']
        
        # Import TradingBot
        from src.trading_bot import TradingBot
        
        # Create bot instance
        strategy_bot = TradingBot(
            data['apiKey'],
            data['apiSecret'],
            data['requestToken'],
            data['account'],
            data['callQuantity'],
            data['putQuantity']
        )
        
        # Also create global kite client for authentication
        try:
            from src.kite_client import KiteClient
            kite_client_global = strategy_bot.kite_client
        except:
            pass
        
        # Start bot in separate thread
        def run_bot():
            global strategy_running
            try:
                strategy_running = True
                strategy_bot.run()
            except Exception as e:
                print(f"Strategy error: {e}")
            finally:
                strategy_running = False
        
        strategy_thread = threading.Thread(target=run_bot, daemon=True)
        strategy_thread.start()
        
        return jsonify({
            'status': 'success',
            'message': 'Strategy started successfully'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/live/', methods=['GET'], strict_slashes=False)
@require_authentication_page
def live_trader_page():
    """Live Trader dedicated page - Requires authentication (STRICT on cloud) - OPTIMIZED"""
    try:
        # Get credentials from session ONCE (optimized - no duplicate calls)
        creds = SaaSSessionManager.get_credentials()
        
        # Quick authentication check (decorator already validated, but double-check for cloud)
        if IS_PRODUCTION and not creds.get('access_token'):
            logging.warning(f"[LIVE TRADER] Unauthorized access attempt from {request.remote_addr} on cloud - missing access token")
            return render_template('auth_required.html', 
                                 message='Authentication required. Access token not found. Please authenticate through the main application.'), 401
        
        # Get account name (optimized - single call)
        account_name_display = creds.get('full_name') or creds.get('account_name') or 'Trading Account'
        
        # Sync global variables from session (lazy - only if needed)
        global account_holder_name, kite_api_key, kite_api_secret, kite_client_global
        account_holder_name = account_name_display
        
        # Lazy initialization of KiteClient - only if not already set and credentials exist
        # This avoids unnecessary initialization on every page load
        if creds.get('access_token') and creds.get('api_key') and creds.get('api_secret'):
            kite_api_key = creds.get('api_key', '')
            kite_api_secret = creds.get('api_secret', '')
            
            # Only create KiteClient if not already initialized (avoid re-initialization)
            if not kite_client_global or not hasattr(kite_client_global, 'access_token') or kite_client_global.access_token != creds.get('access_token'):
                try:
                    from src.kite_client import KiteClient
                except ImportError:
                    from kite_client import KiteClient
                kite_client_global = KiteClient(
                    kite_api_key,
                    kite_api_secret,
                    access_token=creds.get('access_token'),
                    account=account_name_display
                )
        
        # Render template immediately (no database initialization here)
        return render_template('live_trader.html', account_holder_name=account_name_display)
    except Exception as e:
        logging.error(f"[LIVE TRADER] Error loading page: {e}")
        return f"Error loading Live Trader page: {str(e)}", 500

@app.route('/api/live-trader/logs', methods=['GET'])
@require_authentication
def get_live_trader_logs():
    """Get Live Trader logs for current session"""
    try:
        # Get per-session strategy manager
        manager = get_strategy_manager()
        creds = SaaSSessionManager.get_credentials()
        account_name = creds.get('full_name') or creds.get('broker_id') or 'Unknown'
        broker_id = creds.get('broker_id') or SaaSSessionManager.get_broker_id()
        
        logs = []
        
        # First, try to get logs from per-session buffer
        if manager:
            buffer_logs = manager.get_logs(max_lines=500)
            if buffer_logs:
                logs.extend(buffer_logs)
                logging.debug(f"[LOGS] [{account_name}] Retrieved {len(buffer_logs)} lines from per-session buffer")
        
        # Import environment functions at the start
        from datetime import date
        from environment import format_date_for_filename, is_azure_environment, sanitize_account_name_for_filename
        
        # Try to read from log file if strategy is running
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        src_dir = os.path.join(script_dir, 'src')  # Log files are in src directory
        src_logs_dir = os.path.join(src_dir, 'logs')  # Log files are in src/logs directory (local)
        
        # Look for today's log file
        today = date.today().strftime('%Y-%m-%d')  # For backward compatibility searches
        today_formatted = format_date_for_filename(date.today())  # New format: YYYYMONDD
        
        # Try to find log files
        log_files = []
        
        # CRITICAL: Get broker_id from session (SaaS-compliant multi-user isolation)
        # MUST use broker_id only - no fallback to account name for security
        broker_id = SaaSSessionManager.get_broker_id()
        
        if not broker_id:
            # If no broker_id, user is not properly authenticated - return error
            logging.error("[LOGS] No broker_id found in session - user not authenticated")
            return jsonify({
                'success': False,
                'error': 'User not authenticated. Please log in again.',
                'logs': ['[ERROR] Authentication required. Please log in to view logs.'],
                'log_file_path': None,
                'log_files_found': 0
            }), 401
        
        # Use broker_id for log file matching (multi-user isolation)
        # broker_id is the Zerodha ID and is the primary identifier
        account = broker_id
        logging.info(f"[LOGS] [{account_name}] [broker_id: {broker_id}] Using broker_id from session for log matching (Zerodha ID)")
        
        # Simplify: Only look for today's log file in format: {broker_id}_{YYYYMONDD}.log
        # Get sanitized broker_id (first name only)
        if account:
            sanitized_account = sanitize_account_name_for_filename(account)
            log_filename = f'{sanitized_account}_{today_formatted}.log'
            logging.info(f"[LOGS] [broker_id: {broker_id}] Looking for today's log file: '{log_filename}' (sanitized: '{sanitized_account}')")
            
            # LOCAL ENVIRONMENT: Check src/logs directory
            if not is_azure_environment():
                # Ensure directory exists
                if not os.path.exists(src_logs_dir):
                    try:
                        os.makedirs(src_logs_dir, exist_ok=True)
                        logging.info(f"[LOGS] Created src/logs directory: {src_logs_dir}")
                    except Exception as e:
                        logging.warning(f"[LOGS] Could not create src/logs directory: {e}")
                
                # Look for today's log file in src/logs
                today_log_path = os.path.join(src_logs_dir, log_filename)
                if os.path.exists(today_log_path):
                    log_files.append(today_log_path)
                    logging.info(f"[LOGS] ✓ Found today's log file: {today_log_path}")
                else:
                    logging.info(f"[LOGS] Today's log file does not exist: {today_log_path}")
            
            # AZURE ENVIRONMENT: Check /tmp/{account}/logs/ directory
            else:
                from environment import get_log_directory
                if account:
                    sanitized_account = sanitize_account_name_for_filename(account)
                    azure_log_dir = os.path.join('/tmp', sanitized_account, 'logs')
                else:
                    azure_log_dir = '/tmp/logs'
                
                # Ensure directory exists
                os.makedirs(azure_log_dir, exist_ok=True)
                logging.info(f"[LOGS] Azure environment - checking log directory: {azure_log_dir}")
                
                # Verify directory is writable (test write permissions)
                try:
                    test_file = os.path.join(azure_log_dir, '.test_write')
                    with open(test_file, 'w') as f:
                        f.write('test')
                    os.remove(test_file)
                    logging.info(f"[LOGS] Directory is writable: {azure_log_dir}")
                except Exception as perm_error:
                    logging.error(f"[LOGS] Directory may not be writable: {azure_log_dir}, error: {perm_error}")
                
                # Look for today's log file
                today_log_path = os.path.join(azure_log_dir, log_filename)
                if os.path.exists(today_log_path):
                    log_files.append(today_log_path)
                    file_size = os.path.getsize(today_log_path)
                    logging.info(f"[LOGS] ✓ Found today's log file: {today_log_path} (size: {file_size} bytes)")
                else:
                    logging.info(f"[LOGS] Today's log file does not exist: {today_log_path}")
                    # Check if strategy process is running - if not, that's why no log file exists
                    if strategy_process is None:
                        logging.warning(f"[LOGS] Strategy process is not running - log file will be created when strategy starts")
                    elif strategy_process is not None:
                        try:
                            if strategy_process.poll() is None:
                                logging.info(f"[LOGS] Strategy process is running (PID: {strategy_process.pid}) - log file should be created soon")
                            else:
                                logging.warning(f"[LOGS] Strategy process terminated (return code: {strategy_process.returncode}) - may have crashed before creating log file")
                        except:
                            pass
                    # List files in directory for debugging
                    try:
                        if os.path.exists(azure_log_dir):
                            all_files = os.listdir(azure_log_dir)
                            logging.info(f"[LOGS] Files in Azure log directory: {all_files}")
                            if not all_files:
                                logging.info(f"[LOGS] Directory is empty - strategy may not have started logging yet")
                    except Exception as e:
                        logging.warning(f"[LOGS] Could not list Azure log directory: {e}")
        
        # FIRST: Check subprocess output buffer (real-time logs) - this should always be checked
        subprocess_logs = []
        with strategy_output_lock:
            subprocess_logs = list(strategy_output_buffer)  # Copy buffer
        
        if subprocess_logs:
            logging.info(f"[LOGS] Found {len(subprocess_logs)} lines in subprocess output buffer")
            # Log first few lines for debugging
            preview_lines = subprocess_logs[:5] if len(subprocess_logs) >= 5 else subprocess_logs
            logging.info(f"[LOGS] Buffer preview (first {len(preview_lines)} lines): {preview_lines}")
            # Add subprocess logs to all_lines (these are the most recent/real-time)
            all_lines = list(subprocess_logs)
        else:
            all_lines = []
            logging.info(f"[LOGS] No subprocess output in buffer yet (strategy may be starting or not running)")
            # Check if strategy process exists and provide detailed diagnostics
            if strategy_process is not None:
                try:
                    poll_result = strategy_process.poll()
                    if poll_result is None:
                        logging.info(f"[LOGS] Strategy process is running (PID: {strategy_process.pid}) but no output in buffer yet")
                        logging.info(f"[LOGS] Process may still be initializing - logs should appear shortly")
                        # Check if log file exists but is empty (process just started)
                        if is_azure_environment() and account:
                            from environment import sanitize_account_name_for_filename
                            sanitized_account = sanitize_account_name_for_filename(account)
                            azure_log_dir = os.path.join('/tmp', sanitized_account, 'logs')
                            today_log_path = os.path.join(azure_log_dir, log_filename)
                            if os.path.exists(today_log_path):
                                file_size = os.path.getsize(today_log_path)
                                logging.info(f"[LOGS] Log file exists but may be empty (size: {file_size} bytes)")
                    else:
                        logging.warning(f"[LOGS] Strategy process terminated (return code: {poll_result}) - no output captured")
                        logging.warning(f"[LOGS] Strategy may have crashed - check error logs or restart the strategy")
                except Exception as e:
                    logging.warning(f"[LOGS] Could not check strategy process status: {e}")
            else:
                logging.warning(f"[LOGS] Strategy process is None - strategy may not be running")
                logging.warning(f"[LOGS] Start the strategy first to generate logs")
        
        # THEN: Check log files (as fallback/persistent storage)
        if not log_files:
            logging.warning(f"[LOGS] [broker_id: {broker_id}] No log files found for broker_id: {broker_id}, date: {today}")
            # Log checked directories based on environment
            if is_azure_environment():
                # For error message, try to get account-specific directory
                from environment import sanitize_account_name_for_filename
                if account:
                    sanitized_account = sanitize_account_name_for_filename(account)
                    checked_dirs = f"Azure log directory: /tmp/{sanitized_account}/logs/"
                else:
                    checked_dirs = f"Azure log directory: /tmp/logs/"
            else:
                checked_dirs = f"src_logs_dir={src_logs_dir}, src_dir={src_dir}, root={script_dir}"
            logging.warning(f"[LOGS] Checked directories: {checked_dirs}")
            
            # List existing files for debugging
            if is_azure_environment():
                # Use account-specific directory: /tmp/{account_name}/logs/
                if account:
                    sanitized_account = sanitize_account_name_for_filename(account)
                    azure_log_dir = os.path.join('/tmp', sanitized_account, 'logs')
                else:
                    azure_log_dir = '/tmp/logs'
                # Ensure directory exists (create if it doesn't)
                os.makedirs(azure_log_dir, exist_ok=True)
                try:
                    existing_files = os.listdir(azure_log_dir)
                    logging.info(f"[LOGS] Files in Azure log directory ({azure_log_dir}): {existing_files}")
                except Exception as e:
                    logging.warning(f"[LOGS] Could not list Azure log directory: {e}")
            else:
                if os.path.exists(src_logs_dir):
                    try:
                        existing_files = os.listdir(src_logs_dir)
                        logging.info(f"[LOGS] Files in src/logs: {existing_files}")
                    except:
                        pass
            
            # If we have subprocess logs, return them even if no log files exist
            if subprocess_logs:
                logging.info(f"[LOGS] Returning {len(subprocess_logs)} lines from subprocess buffer (no log files found yet)")
                # Remove duplicates while preserving order
                seen = set()
                unique_logs = []
                for log in subprocess_logs:
                    if log not in seen:
                        seen.add(log)
                        unique_logs.append(log)
                
                return jsonify({
                    'success': True,
                    'logs': unique_logs[-1000:],  # Last 1000 entries
                    'log_file_path': None,
                    'message': f'Showing real-time logs from strategy ({len(unique_logs)} lines). Log files will appear once strategy writes to disk.'
                })
            
            # Only return empty if we have neither subprocess logs nor log files
            env_msg = "Azure log directory" if is_azure_environment() else "src/logs, src, root"
            return jsonify({
                'success': True,
                'logs': [],
                'log_file_path': None,
                'message': f'No log files found for account: {account}, date: {today}. Checked: {env_msg}. Logs will appear once the strategy starts.'
            })
        
        # Read last 500 lines from log files (increased to show more logs)
        # Prioritize: read from first file (most relevant) first, then others
        log_files_read = []
        for log_path in log_files:
            try:
                logging.info(f"[LOGS] Attempting to read log file: {log_path}")
                if not os.path.exists(log_path):
                    logging.warning(f"[LOGS] Log file does not exist: {log_path}")
                    continue
                    
                # Check file size
                file_size = os.path.getsize(log_path)
                logging.info(f"[LOGS] Log file size: {file_size} bytes")
                
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    # Get last 500 lines from each file to show more detailed logs
                    file_lines = lines[-500:] if len(lines) > 500 else lines
                    # Merge file lines with subprocess buffer (avoid duplicates)
                    # File logs are older, subprocess buffer has latest
                    # Combine: file logs + new subprocess logs not in file
                    existing_texts = set(all_lines)  # What we already have
                    for file_line in file_lines:
                        file_line_stripped = file_line.strip()
                        if file_line_stripped and file_line_stripped not in existing_texts:
                            all_lines.append(file_line_stripped)
                            existing_texts.add(file_line_stripped)
                    
                    log_files_read.append(log_path)
                    logging.info(f"[LOGS] Successfully read {len(file_lines)} lines from {log_path} (total lines in file: {len(lines)})")
            except PermissionError as e:
                logging.error(f"[LOGS] Permission denied reading log file {log_path}: {e}")
            except Exception as e:
                logging.error(f"[LOGS] Error reading log file {log_path}: {e}")
                import traceback
                logging.error(f"[LOGS] Traceback: {traceback.format_exc()}")
                pass
        
        if log_files_read:
            logging.info(f"[LOGS] Successfully read from {len(log_files_read)} log file(s): {log_files_read}")
        elif subprocess_logs:
            logging.info(f"[LOGS] Using subprocess output buffer ({len(subprocess_logs)} lines) - log file not found yet")
        else:
            logging.warning(f"[LOGS] No log files were successfully read from {len(log_files)} attempted file(s) and no subprocess output available")
        
        # Show ALL logs (remove filtering to display complete log details)
        # Sort by timestamp if available, otherwise keep order
        # Use all_lines which already contains subprocess buffer + file logs
        for line in all_lines[-1000:]:  # Show last 1000 lines (increased for better visibility)
            if isinstance(line, str):
                line = line.strip()
            else:
                line = str(line).strip()
            if line:  # Only add non-empty lines
                logs.append(line)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_logs = []
        for log in logs:
            if log not in seen:
                seen.add(log)
                unique_logs.append(log)
        
        # Include log file path and any error messages in response
        response_data = {
            'success': True,
            'logs': unique_logs[-1000:],  # Last 1000 entries (increased for better visibility)
            'log_file_path': log_files[0] if log_files else None,  # Return log file path for reference
            'log_files_found': len(log_files),
            'log_files_read': len(log_files_read),
            'log_files': log_files_read if log_files_read else log_files[:5]  # Show up to 5 file paths
        }
        
        # Add log file path and debug info to logs for visibility
        if log_files and log_files[0]:
            log_path_msg = f"[LOG SETUP] Log file path: {log_files[0]}"
            # Check if already in logs to avoid duplicates
            if not any(log_path_msg in log for log in unique_logs):
                unique_logs.insert(0, log_path_msg)
            
            # Add info about log file search
            if response_data.get('log_files_found', 0) > 0:
                search_info = f"[LOG SETUP] Found {response_data['log_files_found']} log file(s), read {response_data['log_files_read']} successfully"
                if search_info not in unique_logs:
                    unique_logs.insert(1, search_info)
        else:
            # No log files found - add helpful message with strategy status
            strategy_status_msg = ""
            if strategy_process is None:
                strategy_status_msg = "[LOG SETUP] Strategy process is not running. Please start the strategy to generate logs."
            else:
                try:
                    poll_result = strategy_process.poll()
                    if poll_result is None:
                        strategy_status_msg = f"[LOG SETUP] Strategy process is running (PID: {strategy_process.pid}) but no logs yet. Logs should appear shortly."
                    else:
                        strategy_status_msg = f"[LOG SETUP] Strategy process terminated (return code: {poll_result}). The strategy may have crashed. Please restart the strategy."
                except:
                    strategy_status_msg = "[LOG SETUP] Strategy process status unknown. Please check if the strategy is running."
            
            if not strategy_status_msg:
                strategy_status_msg = "[LOG SETUP] No log files found yet. Logs will appear here once the strategy starts running."
            
            if strategy_status_msg not in unique_logs:
                unique_logs.insert(0, strategy_status_msg)
            
            # Also add directory info for Azure
            if is_azure_environment() and account:
                from environment import sanitize_account_name_for_filename
                sanitized_account = sanitize_account_name_for_filename(account)
                azure_log_dir = os.path.join('/tmp', sanitized_account, 'logs')
                dir_info = f"[LOG SETUP] Log directory: {azure_log_dir}"
                if dir_info not in unique_logs:
                    unique_logs.insert(1, dir_info)
        
        response_data['logs'] = unique_logs[-500:]
        return jsonify(response_data)
    except Exception as e:
        import traceback
        error_traceback = traceback.format_exc()
        logging.error(f"[LOGS] Error in get_live_trader_logs: {e}\n{error_traceback}")
        
        # Return error in logs so it shows up in Live Trading Log section
        error_logs = [
            f"[ERROR] Failed to retrieve logs: {str(e)}",
            f"[ERROR] Traceback: {error_traceback[:500]}"  # Limit traceback length
        ]
        
        return jsonify({
            'success': False,
            'error': str(e),
            'logs': error_logs,  # Include error in logs so it shows on screen
            'log_file_path': None,
            'log_files_found': 0
        }), 500

@app.route('/api/live-trader/status', methods=['GET'])
@require_authentication
def live_trader_status():
    """Get Live Trader engine status for current session"""
    try:
        # Get per-session strategy manager
        manager = get_strategy_manager()
        if not manager:
            return jsonify({
                'running': False,
                'strategy_running': False,
                'error': 'No session found'
            }), 401
        
        # Check actual process status
        actual_running = manager.is_running()
        manager.strategy_running = actual_running
        
        creds = SaaSSessionManager.get_credentials()
        account_name = creds.get('full_name') or creds.get('broker_id') or 'Unknown'
        
        logging.debug(f"[LIVE TRADER STATUS] [{account_name}] Status - running: {actual_running}")
        
        return jsonify({
            'running': actual_running,
            'strategy_running': actual_running,
            'process_id': manager.process_id if actual_running else None,
            'account_name': account_name,
            'broker_id': manager.broker_id
        })
    except Exception as e:
        logging.error(f"[LIVE TRADER STATUS] Error: {e}")
        import traceback
        logging.error(f"[LIVE TRADER STATUS] Traceback: {traceback.format_exc()}")
        return jsonify({
            'running': False,
            'strategy_running': False,
            'error': str(e)
        }), 500

@app.route('/api/live-trader/start', methods=['POST'])
@require_authentication
def start_live_trader():
    """Start Live Trader by running Straddle10PointswithSL-Limit.py - Per-session isolated"""
    try:
        # Get per-session strategy manager
        manager = get_strategy_manager()
        if not manager:
            return jsonify({
                'success': False,
                'error': 'No session found. Please authenticate first.'
            }), 401
        
        # Get credentials from session
        creds = SaaSSessionManager.get_credentials()
        broker_id = creds.get('broker_id') or SaaSSessionManager.get_broker_id()
        account_name = creds.get('full_name') or creds.get('broker_id') or broker_id or 'TRADING_ACCOUNT'
        
        # Update manager account name if needed
        if account_name != manager.account_name:
            manager.account_name = account_name
        
        # Check if strategy is already running for this session
        if manager.is_running():
            logging.warning(f"[LIVE TRADER] [{account_name}] Strategy is already running (PID: {manager.process_id})")
            return jsonify({
                'success': False,
                'error': f'Strategy is already running for account {account_name}',
                'account_name': account_name,
                'broker_id': broker_id
            }), 400
        
        # Stop any existing process (cleanup)
        if manager.strategy_process:
            manager.stop()
        
        data = request.get_json()
        call_quantity = data.get('callQuantity')
        put_quantity = data.get('putQuantity')
        
        if not call_quantity or not put_quantity:
            return jsonify({
                'success': False,
                'error': 'Call Quantity and Put Quantity are required'
            }), 400
        
        # Convert to integers
        try:
            call_quantity = int(call_quantity)
            put_quantity = int(put_quantity)
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'Call Quantity and Put Quantity must be valid numbers'
            }), 400
        
        # Validate quantities are multiples of LOT_SIZE (from config)
        if call_quantity % LOT_SIZE != 0:
            return jsonify({
                'success': False,
                'error': f'Call Quantity must be a multiple of {LOT_SIZE}. You entered {call_quantity}. Nearest valid: {(call_quantity // LOT_SIZE) * LOT_SIZE}'
            }), 400
        
        if put_quantity % LOT_SIZE != 0:
            return jsonify({
                'success': False,
                'error': f'Put Quantity must be a multiple of {LOT_SIZE}. You entered {put_quantity}. Nearest valid: {(put_quantity // LOT_SIZE) * LOT_SIZE}'
            }), 400
        
        # Get credentials from session
        api_key = creds.get('api_key')
        api_secret = creds.get('api_secret')
        access_token = creds.get('access_token')
        
        # Log credential status for debugging with account name
        logging.info(f"[LIVE TRADER] [{account_name}] Credentials check - api_key: {'SET' if api_key else 'NOT SET'}, api_secret: {'SET' if api_secret else 'NOT SET'}, access_token: {'SET' if access_token else 'NOT SET'}, broker_id: {broker_id}")
        
        # Validate that we have all required credentials
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key not available. Please authenticate first.'
            }), 401
        
        # API secret is required for the strategy to work properly
        if not api_secret:
            logging.warning("[LIVE TRADER] API secret not available - cannot start strategy")
            return jsonify({
                'success': False,
                'error': 'API secret is required to start the trading strategy. Please re-authenticate and provide your API secret. Click on "Authenticated" status badge to update your credentials.',
                'requires_api_secret': True
            }), 400
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token not available. Please authenticate first.'
            }), 401
        
        # Use account name from session (already set above)
        account = account_name
        
        # Get the strategy file path
        # Use the correct path: PythonProgram\Strangle10Points\src\Straddle10PointswithSL-Limit.py
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # The file is in src directory (same directory as config_dashboard.py)
        # config_dashboard.py is at: PythonProgram\Strangle10Points\src\config_dashboard.py
        # Strategy file is at: PythonProgram\Strangle10Points\src\Straddle10PointswithSL-Limit.py
        strategy_file = os.path.join(script_dir, 'src', 'Straddle10PointswithSL-Limit.py')
        
        # Verify the file exists
        if not os.path.exists(strategy_file):
            # Try absolute path as fallback
            abs_path = r'C:\Users\SharmaS8\OneDrive - Unisys\Shivam Imp Documents-2024 June\PythonProgram\Strangle10Points\src\Straddle10PointswithSL-Limit.py'
            if os.path.exists(abs_path):
                strategy_file = abs_path
            else:
                # Last fallback: check old location (root directory)
                old_path = os.path.join(script_dir, 'Straddle10PointswithSL-Limit.py')
                if os.path.exists(old_path):
                    strategy_file = old_path
                else:
                    # Log error for debugging
                    print(f"[ERROR] Strategy file not found. Checked:")
                    print(f"  1. {os.path.join(script_dir, 'src', 'Straddle10PointswithSL-Limit.py')}")
                    print(f"  2. {abs_path}")
                    print(f"  3. {old_path}")
        
        if not os.path.exists(strategy_file):
            return jsonify({
                'success': False,
                'error': f'Strategy file not found: {strategy_file}'
            }), 404
        
        # Run the strategy file as subprocess
        # The file expects 6 inputs in order:
        # 1. Account (line 24)
        # 2. Api_key (line 25)
        # 3. Api_Secret (line 26)
        # 4. Request_Token (line 27) - we'll use access_token
        # 5. Call Quantity (line 2504)
        # 6. Put Quantity (line 2505)
        
        # Use a threading event to signal when process is created
        process_ready = threading.Event()
        process_error = [None]  # Use list to allow modification from inner function
        
        def run_strategy(manager_ref, account_name_param, broker_id_param):
            """Run strategy in background thread with per-session manager"""
            try:
                manager_ref.strategy_running = True
                
                # Clear output buffer when starting new strategy
                with manager_ref.strategy_output_lock:
                    manager_ref.strategy_output_buffer = []
                    logging.info(f"[LIVE TRADER] [{account_name_param}] Cleared output buffer for new strategy run")
                
                logging.info(f"[LIVE TRADER] [{account_name_param}] Starting strategy with broker_id: {broker_id_param} (Zerodha ID - will be used for log file matching)")
                
                # Prepare input string for stdin (matching the exact order of input() calls)
                # Use broker_id as account identifier for consistency
                inputs = f"{broker_id}\n{api_key}\n{api_secret}\n{access_token}\n{call_quantity}\n{put_quantity}\n"
                
                # Run the strategy file
                # Use the directory containing the strategy file as working directory
                # This ensures relative imports and log file creation work correctly
                strategy_cwd = os.path.dirname(strategy_file) if os.path.exists(strategy_file) else script_dir
                
                # Log the paths for debugging
                logging.info(f"[LIVE TRADER] Strategy file: {strategy_file}")
                logging.info(f"[LIVE TRADER] Working directory: {strategy_cwd}")
                logging.info(f"[LIVE TRADER] File exists: {os.path.exists(strategy_file)}")
                logging.info(f"[LIVE TRADER] Python executable: {sys.executable}")
                
                try:
                    # Ensure environment variables are passed to subprocess
                    # By default, subprocess inherits parent's environment, but we make it explicit
                    env = os.environ.copy()
                    # Add PYTHONUNBUFFERED to ensure real-time output
                    env['PYTHONUNBUFFERED'] = '1'
                    # Add broker_id to environment for strategy file to use
                    if broker_id:
                        env['BROKER_ID'] = broker_id
                        env['ZERODHA_ID'] = broker_id  # Alias for clarity
                    manager_ref.strategy_process = subprocess.Popen(
                        [sys.executable, '-u', strategy_file],  # -u flag for unbuffered output
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        cwd=strategy_cwd,
                        env=env,  # Explicitly pass environment variables
                        bufsize=0  # Unbuffered for real-time output
                    )
                    
                    manager_ref.process_id = manager_ref.strategy_process.pid
                    logging.info(f"[LIVE TRADER] [{account_name_param}] Process created successfully (PID: {manager_ref.process_id})")
                    
                    # Send inputs immediately
                    manager_ref.strategy_process.stdin.write(inputs)
                    manager_ref.strategy_process.stdin.flush()
                    manager_ref.strategy_process.stdin.close()
                    
                    # Signal that process is ready
                    process_ready.set()
                    
                    # Don't wait for completion - let it run in background
                    # Monitor the process in background
                    def monitor_process():
                        # Store local reference to avoid race conditions
                        proc = manager_ref.strategy_process
                        if proc is None:
                            return
                        
                        try:
                            # Read output in background and store in buffer for real-time display
                            logging.info(f"[STRATEGY] [{account_name_param}] Monitor thread started, reading subprocess output...")
                            line_count = 0
                            for line in proc.stdout:
                                line_text = line.strip()
                                if line_text:  # Only store non-empty lines
                                    line_count += 1
                                    # Log to dashboard logger with account name
                                    logging.info(f"[STRATEGY] [{account_name_param}] {line_text}")
                                    
                                    # Store in buffer for real-time log display
                                    with manager_ref.strategy_output_lock:
                                        manager_ref.strategy_output_buffer.append(line_text)
                                        # Keep buffer size manageable
                                        if len(manager_ref.strategy_output_buffer) > MAX_BUFFER_SIZE:
                                            manager_ref.strategy_output_buffer = manager_ref.strategy_output_buffer[-MAX_BUFFER_SIZE:]
                                    
                                    # Log every 10 lines to confirm we're capturing output
                                    if line_count % 10 == 0:
                                        logging.info(f"[STRATEGY] [{account_name_param}] Captured {line_count} lines so far, buffer size: {len(manager_ref.strategy_output_buffer)}")
                            
                            logging.info(f"[STRATEGY] [{account_name_param}] Monitor thread finished, captured {line_count} total lines")
                        except Exception as e:
                            logging.error(f"[STRATEGY] [{account_name_param}] Monitor error: {e}")
                            import traceback
                            logging.error(f"[STRATEGY] [{account_name_param}] Monitor traceback: {traceback.format_exc()}")
                        finally:
                            # Check if process has terminated
                            try:
                                if proc is not None and proc.poll() is not None:
                                    returncode = proc.returncode
                                    logging.info(f"[STRATEGY] [{account_name_param}] Process terminated with return code: {returncode}")
                                    manager_ref.strategy_running = False
                                    # Only set to None if it's still the same process
                                    if manager_ref.strategy_process == proc:
                                        manager_ref.strategy_process = None
                                        manager_ref.process_id = None
                            except Exception as e:
                                logging.warning(f"[STRATEGY] [{account_name_param}] Error checking process status: {e}")
                                manager_ref.strategy_running = False
                                if manager_ref.strategy_process == proc:
                                    manager_ref.strategy_process = None
                                    manager_ref.process_id = None
                    
                    monitor_thread = threading.Thread(target=monitor_process, daemon=True)
                    monitor_thread.start()
                    
                except Exception as popen_error:
                    error_msg = f"Failed to create subprocess: {popen_error}"
                    logging.error(f"[LIVE TRADER] [{account_name_param}] {error_msg}")
                    import traceback
                    logging.error(f"[LIVE TRADER] [{account_name_param}] Traceback: {traceback.format_exc()}")
                    process_error[0] = error_msg
                    manager_ref.strategy_running = False
                    manager_ref.strategy_process = None
                    manager_ref.process_id = None
                    process_ready.set()  # Signal even on error so main thread can check
                
            except Exception as e:
                error_msg = f"Error running strategy: {e}"
                logging.error(f"[LIVE TRADER] [{account_name_param}] {error_msg}")
                import traceback
                logging.error(f"[LIVE TRADER] [{account_name_param}] Traceback: {traceback.format_exc()}")
                process_error[0] = error_msg
                manager_ref.strategy_running = False
                if manager_ref.strategy_process:
                    try:
                        manager_ref.strategy_process.terminate()
                    except:
                        pass
                manager_ref.strategy_process = None
                manager_ref.process_id = None
                process_ready.set()  # Signal even on error so main thread can check
        
        # Start strategy in background thread with manager reference
        strategy_thread = threading.Thread(target=run_strategy, args=(manager, account_name, broker_id), daemon=True)
        strategy_thread.start()
        
        # Wait for process to be created (with timeout)
        if process_ready.wait(timeout=3.0):
            # Check if there was an error
            if process_error[0]:
                manager.strategy_running = False
                logging.error(f"[LIVE TRADER] [{account_name}] Strategy process creation failed: {process_error[0]}")
                return jsonify({
                    'success': False,
                    'error': f'Failed to start strategy process: {process_error[0]}',
                    'account_name': account_name,
                    'broker_id': broker_id
                }), 500
            
            # Check if process started successfully
            if manager.strategy_process is None:
                manager.strategy_running = False
                logging.error(f"[LIVE TRADER] [{account_name}] Strategy process is None after creation")
                return jsonify({
                    'success': False,
                    'error': 'Failed to start strategy process - process is None',
                    'account_name': account_name,
                    'broker_id': broker_id
                }), 500
        else:
            # Timeout waiting for process
            manager.strategy_running = False
            logging.error(f"[LIVE TRADER] [{account_name}] Timeout waiting for strategy process to start")
            return jsonify({
                'success': False,
                'error': 'Timeout waiting for strategy process to start. Please check logs for details.',
                'account_name': account_name,
                'broker_id': broker_id
            }), 500
        
        # Check if process has already terminated with error
        if manager.strategy_process is not None and manager.strategy_process.poll() is not None:
            returncode = manager.strategy_process.returncode
            manager.strategy_running = False
            error_msg = f'Strategy process exited immediately with code {returncode}'
            logging.error(f"[LIVE TRADER] [{account_name}] {error_msg}")
            return jsonify({
                'success': False,
                'error': error_msg,
                'account_name': account_name,
                'broker_id': broker_id
            }), 500
        
        # Process started successfully
        logging.info(f"[LIVE TRADER] [{account_name}] Strategy process started successfully (PID: {manager.process_id})")
        return jsonify({
            'success': True,
            'message': f'Live Trader started successfully for account {account_name}',
            'process_id': manager.process_id,
            'account_name': account_name,
            'broker_id': broker_id
        })
        
    except Exception as e:
        creds = SaaSSessionManager.get_credentials()
        account_name = creds.get('full_name') or creds.get('broker_id') or 'Unknown'
        logging.error(f"[LIVE TRADER] [{account_name}] Error starting Live Trader: {e}")
        import traceback
        logging.error(f"[LIVE TRADER] [{account_name}] Traceback: {traceback.format_exc()}")
        return jsonify({
            'success': False,
            'error': f'Failed to start Live Trader: {str(e)}',
            'account_name': account_name
        }), 500

@app.route('/api/live-trader/stop', methods=['POST'])
@require_authentication
def stop_live_trader():
    """Stop Live Trader for current session"""
    try:
        # Get per-session strategy manager
        manager = get_strategy_manager()
        if not manager:
            return jsonify({
                'success': False,
                'error': 'No session found. Please authenticate first.'
            }), 401
        
        creds = SaaSSessionManager.get_credentials()
        account_name = creds.get('full_name') or creds.get('broker_id') or 'Unknown'
        
        # Check if strategy is running
        if not manager.is_running():
            return jsonify({
                'success': False,
                'error': f'Strategy is not running for account {account_name}',
                'account_name': account_name
            }), 400
        
        logging.info(f"[LIVE TRADER] [{account_name}] Stopping strategy (PID: {manager.process_id})")
        
        # Stop the strategy
        manager.stop()
        
        return jsonify({
            'success': True,
            'message': f'Strategy stopped successfully for account {account_name}',
            'account_name': account_name,
            'broker_id': manager.broker_id
        })
        
    except Exception as e:
        creds = SaaSSessionManager.get_credentials()
        account_name = creds.get('full_name') or creds.get('broker_id') or 'Unknown'
        logging.error(f"[LIVE TRADER] [{account_name}] Error stopping strategy: {e}")
        return jsonify({
            'success': False,
            'error': str(e),
            'account_name': account_name
        }), 500

@app.route('/api/strategy/stop', methods=['POST'])
def stop_strategy():
    """Stop the trading strategy (legacy endpoint - redirects to per-session stop)"""
    try:
        # Check if authenticated, if so use per-session manager
        if SaaSSessionManager.is_authenticated():
            return stop_live_trader()
        
        # Legacy global stop (for backward compatibility)
        global strategy_bot, strategy_process, strategy_running
        
        # Check actual process status
        actual_running = False
        if strategy_process is not None:
            poll_result = strategy_process.poll()
            if poll_result is None:
                actual_running = True
            else:
                # Process already terminated
                logging.info("[STRATEGY] Process already terminated with return code: {}".format(poll_result))
                strategy_running = False
                strategy_process = None
        
        if not actual_running and not strategy_running:
            return jsonify({
                'status': 'error',
                'message': 'Strategy is not running'
            }), 400
        
        logging.info("[STRATEGY] Stopping strategy (PID: {})".format(strategy_process.pid if strategy_process else 'N/A'))
        
        # Stop TradingBot if running
        if strategy_bot:
            strategy_bot.stop_requested = True
        
        # Stop subprocess if running
        if strategy_process:
            try:
                strategy_process.terminate()
                # Wait a bit for graceful shutdown
                import time
                time.sleep(2)
                if strategy_process.poll() is None:
                    strategy_process.kill()
                strategy_process.wait(timeout=3)
            except Exception as e:
                print(f"Error stopping process: {e}")
                try:
                    strategy_process.kill()
                except:
                    pass
            finally:
                strategy_process = None
        
        strategy_running = False
        
        return jsonify({
            'status': 'success',
            'message': 'Strategy stop requested'
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# Authentication API Endpoints
@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Check authentication status (SaaS-compliant) - Only returns authenticated=True if access_token exists"""
    try:
        is_authenticated = SaaSSessionManager.is_authenticated()
        
        if not is_authenticated:
            return jsonify({
                'authenticated': False,
                'has_access_token': False,
                'message': 'Not authenticated'
            })
        
        creds = SaaSSessionManager.get_credentials()
        has_access_token = bool(creds.get('access_token'))
        
        # CRITICAL: Only return authenticated=True if access_token exists
        # This prevents showing as connected when session exists but no valid token
        return jsonify({
            'authenticated': has_access_token,  # Only true if access_token exists
            'has_access_token': has_access_token,
            'user_id': creds.get('user_id'),
            'broker_id': creds.get('broker_id'),
            'device_id': creds.get('device_id'),
            'email': creds.get('email'),
            'full_name': creds.get('full_name'),
            'account_name': creds.get('full_name') or 'Trading Account'
        })
    except Exception as e:
        logging.error(f"[AUTH] Error checking auth status: {e}")
        return jsonify({
            'authenticated': False,
            'has_access_token': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/details', methods=['GET'])
def auth_details():
    """Get authentication details for populating form fields"""
    try:
        is_authenticated = SaaSSessionManager.is_authenticated()
        
        if not is_authenticated:
            return jsonify({
                'success': True,
                'details': {}
            })
        
        creds = SaaSSessionManager.get_credentials()
        return jsonify({
            'success': True,
            'details': {
                'api_key': creds.get('api_key', ''),
                'api_secret': creds.get('api_secret', ''),
                'access_token': creds.get('access_token', ''),
                'request_token': creds.get('request_token', ''),
                'email': creds.get('email', ''),
                'broker': creds.get('broker_id', ''),
                'user_id': creds.get('user_id', ''),
                'account_name': creds.get('full_name', '') or 'Trading Account',
                'full_name': creds.get('full_name', '')
            }
        })
    except Exception as e:
        logging.error(f"[AUTH] Error getting auth details: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout and clear session credentials"""
    try:
        SaaSSessionManager.clear_credentials()
        return jsonify({
            'success': True,
            'message': 'Logged out successfully'
        })
    except Exception as e:
        logger.error(f"[AUTH] Error during logout: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/disconnect', methods=['POST'])
def disconnect_zerodha():
    """Disconnect from Zerodha account - clear credentials and invalidate session (SaaS-compliant)"""
    try:
        # Get user info before clearing
        user_id = SaaSSessionManager.get_user_id()
        broker_id = SaaSSessionManager.get_broker_id()
        
        # Clear server-side session (SaaS-compliant)
        SaaSSessionManager.clear_credentials()
        
        # Clear global kite client
        global kite_client_global, kite_api_key, kite_api_secret, account_holder_name, strategy_account_name
        if kite_client_global:
            try:
                # Close any connections if needed
                if hasattr(kite_client_global, 'kite'):
                    kite_client_global.kite = None
            except:
                pass
        kite_client_global = None
        kite_api_key = None
        kite_api_secret = None
        account_holder_name = None
        strategy_account_name = None
        
        # Clear stored tokens file
        try:
            if os.path.exists(TOKEN_STORAGE_FILE):
                tokens = {}
                with open(TOKEN_STORAGE_FILE, 'r') as f:
                    tokens = json.load(f)
                # Clear all tokens
                tokens.clear()
                with open(TOKEN_STORAGE_FILE, 'w') as f:
                    json.dump(tokens, f, indent=2)
        except Exception as e:
            logger.warning(f"[DISCONNECT] Could not clear token file: {e}")
        
        logger.info(f"[AUTH] User disconnected from Zerodha account (user: {user_id}, broker: {broker_id})")
        
        return jsonify({
            'success': True,
            'message': 'Disconnected successfully'
        })
    except Exception as e:
        logger.error(f"[AUTH] Error during disconnect: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/set-credentials', methods=['POST'])
def set_credentials():
    """Set API credentials for authentication"""
    try:
        global kite_api_key, kite_api_secret
        
        data = request.get_json()
        kite_api_key = data.get('api_key', '').strip()
        kite_api_secret = data.get('api_secret', '').strip()
        
        if not kite_api_key or not kite_api_secret:
            return jsonify({
                'success': False,
                'error': 'API key and secret are required'
            }), 400
        
        return jsonify({
            'success': True,
            'message': 'API credentials set successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    """Authenticate with Zerodha using request token"""
    try:
        global strategy_bot, kite_client_global, kite_api_key, kite_api_secret
        
        data = request.get_json() or {}
        request_token = data.get('request_token', '').strip()
        incoming_api_key = data.get('api_key', '').strip()
        incoming_api_secret = data.get('api_secret', '').strip()
        
        if not request_token:
            return jsonify({
                'success': False,
                'error': 'Request token is required'
            }), 400
        
        # Allow API key/secret to be provided in the same call
        if incoming_api_key and incoming_api_secret:
            kite_api_key = incoming_api_key
            kite_api_secret = incoming_api_secret
        elif incoming_api_key or incoming_api_secret:
            return jsonify({
                'success': False,
                'error': 'Both API key and API secret are required'
            }), 400
        
        # Need API key and secret for authentication
        if not kite_api_key or not kite_api_secret:
            return jsonify({
                'success': False,
                'error': 'API credentials not configured. Please provide API key and secret.'
            }), 400
        
        # Create or update global kite client
        try:
            try:
                from src.kite_client import KiteClient  # when running from repo root
            except ImportError:
                from kite_client import KiteClient       # fallback when src on PYTHONPATH
            kite_client_global = KiteClient(
                kite_api_key,
                kite_api_secret,
                request_token=request_token,
                account='DASHBOARD'
            )
            
            # Verify authentication by getting profile
            is_valid, result = validate_kite_connection(kite_client_global)
            if not is_valid:
                raise Exception(result)
            
            profile = result
            
            # Extract and store account holder name
            global account_holder_name, strategy_account_name
            account_holder_name = profile.get('user_name') or profile.get('user_id') or 'Trading Account'
            kite_client_global.account = account_holder_name  # Update account name in client
            # Keep strategy account name in sync for log matching
            strategy_account_name = account_holder_name
            
            # Extract user_id and broker_id from profile
            user_id = profile.get('user_id') or profile.get('user_name') or kite_api_key
            broker_id = profile.get('user_id') or kite_api_key  # Use user_id as broker_id
            
            # Store credentials in server-side session (SaaS-compliant)
            SaaSSessionManager.store_credentials(
                api_key=kite_api_key,
                api_secret=kite_api_secret,
                access_token=kite_client_global.access_token,
                request_token=request_token,
                user_id=user_id,
                broker_id=broker_id,
                email=profile.get('email'),
                full_name=account_holder_name
            )
            
            # Save token for persistence (backup)
            if kite_client_global.access_token:
                save_access_token(kite_api_key, kite_client_global.access_token, account_holder_name)
            
            logging.info(f"[AUTH] [broker_id: {broker_id}] Account holder name: {account_holder_name}")
            
            # Re-setup Azure Blob logging with the correct account name for streaming logs
            try:
                from src.environment import setup_azure_blob_logging, is_azure_environment
                if is_azure_environment() and account_holder_name:
                    print(f"[AUTH] Re-setting up Azure Blob Storage logging with account: {account_holder_name}")
                    # Remove old blob handler if exists
                    logger = logging.getLogger(__name__)
                    for handler in logger.handlers[:]:
                        if hasattr(handler, 'container_name'):  # Azure Blob handler
                            logger.removeHandler(handler)
                            handler.close()
                    
                    # Setup new blob handler with correct account name
                    blob_handler, blob_path = setup_azure_blob_logging(
                        account_name=account_holder_name,
                        logger_name=__name__,
                        streaming_mode=True
                    )
                    if blob_handler:
                        logger.info(f"[AUTH] Azure Blob Storage logging updated: {blob_path}")
                        print(f"[AUTH] ✓ Azure Blob Storage logging updated with account: {account_holder_name}")
            except Exception as e:
                print(f"[AUTH] Warning: Could not update Azure Blob logging: {e}")
            
            return jsonify({
                'success': True,
                'message': 'Authentication successful',
                'account_name': account_holder_name,
                'broker_id': broker_id,
                'device_id': SaaSSessionManager.get_device_id()
            })
        except Exception as e:
            logger.error("[AUTH] Authentication failed: {}".format(str(e)))
            import traceback
            logger.error("[AUTH] Traceback: {}".format(traceback.format_exc()))
            return jsonify({
                'success': False,
                'error': f'Authentication failed: {str(e)}'
            }), 401
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/auth/generate-access-token', methods=['POST'])
def generate_access_token():
    """Generate access token from request token (alias for authenticate)"""
    try:
        data = request.get_json() or {}
        request_token = data.get('request_token', '').strip()
        api_key = data.get('api_key', '').strip()
        api_secret = data.get('api_secret', '').strip()
        
        if not request_token:
            return jsonify({
                'success': False,
                'error': 'Request token is required'
            }), 400
        
        if not api_key or not api_secret:
            return jsonify({
                'success': False,
                'error': 'API key and secret are required'
            }), 400
        
        # Use the authenticate endpoint logic
        try:
            from src.kite_client import KiteClient
        except ImportError:
            from kite_client import KiteClient
        
        kite_client = KiteClient(
            api_key,
            api_secret,
            request_token=request_token,
            account='DASHBOARD'
        )
        
        # Verify authentication
        is_valid, result = validate_kite_connection(kite_client)
        if not is_valid:
            return jsonify({
                'success': False,
                'error': result
            }), 401
        
        profile = result
        user_id = profile.get('user_id') or profile.get('user_name') or api_key
        broker_id = profile.get('user_id') or api_key
        account_name = profile.get('user_name') or profile.get('user_id') or 'Trading Account'
        
        # Store credentials in session
        SaaSSessionManager.store_credentials(
            api_key=api_key,
            api_secret=api_secret,
            access_token=kite_client.access_token,
            request_token=request_token,
            user_id=user_id,
            broker_id=broker_id,
            email=profile.get('email'),
            full_name=account_name
        )
        
        return jsonify({
            'success': True,
            'access_token': kite_client.access_token,
            'message': 'Access token generated successfully'
        })
    except Exception as e:
        logger.error(f"[AUTH] Error generating access token: {e}")
        return jsonify({
            'success': False,
            'error': f'Failed to generate access token: {str(e)}'
        }), 500

@app.route('/api/auth/set-access-token', methods=['POST'])
def set_access_token():
    """Set access token directly (if user already has one)"""
    try:
        global strategy_bot, kite_client_global, kite_api_key, kite_api_secret
        
        data = request.get_json() or {}
        access_token = data.get('access_token', '').strip()
        api_key = data.get('api_key', '').strip() or kite_api_key  # Allow overriding API key
        api_secret_override = data.get('api_secret', '').strip()
        
        if api_secret_override:
            kite_api_secret = api_secret_override  # persist secret if provided
        
        if not access_token:
            return jsonify({
                'success': False,
                'error': 'Access token is required'
            }), 400
        
        if not api_key:
            return jsonify({
                'success': False,
                'error': 'API key is required. Please provide it in the form or configure it when starting the strategy.'
            }), 400
        
        # Create or update global kite client with access token
        try:
            try:
                from src.kite_client import KiteClient
            except ImportError:
                from kite_client import KiteClient
            # Use api_secret_override if provided, otherwise use stored kite_api_secret
            api_secret_to_use = api_secret_override or kite_api_secret or ''
            kite_client_global = KiteClient(
                api_key,
                api_secret_to_use,  # Store api_secret in KiteClient so it's available later
                access_token=access_token,
                account='DASHBOARD'
            )
            
            # Ensure api_secret is stored in the client (even if empty, so we know it was checked)
            if api_secret_to_use:
                logging.info("[AUTH] API secret stored in KiteClient")
            else:
                logging.warning("[AUTH] API secret is empty - strategy may fail to start without it")
            
            # Verify the token works by getting profile
            is_valid, result = validate_kite_connection(kite_client_global)
            if not is_valid:
                raise Exception(result)
            
            profile = result
            
            # Extract and store account holder name
            global account_holder_name, strategy_account_name
            account_holder_name = profile.get('user_name') or profile.get('user_id') or 'Trading Account'
            kite_client_global.account = account_holder_name  # Update account name in client
            # Keep strategy account name in sync for log matching
            strategy_account_name = account_holder_name
            
            # Extract user_id and broker_id from profile
            user_id = profile.get('user_id') or profile.get('user_name') or api_key
            broker_id = profile.get('user_id') or api_key  # Use user_id as broker_id
            
            # Store credentials in server-side session (SaaS-compliant)
            SaaSSessionManager.store_credentials(
                api_key=api_key,
                api_secret=api_secret_to_use,
                access_token=access_token,
                user_id=user_id,
                broker_id=broker_id,
                email=profile.get('email'),
                full_name=account_holder_name
            )
            
            # Save token for persistence (backup)
            if kite_client_global.access_token:
                save_access_token(api_key, kite_client_global.access_token, account_holder_name)
            
            logging.info(f"[AUTH] [broker_id: {broker_id}] Account holder name: {account_holder_name}")
            
            # Re-setup Azure Blob logging with the correct account name for streaming logs
            try:
                from src.environment import setup_azure_blob_logging, is_azure_environment
                if is_azure_environment() and account_holder_name:
                    print(f"[AUTH] Re-setting up Azure Blob Storage logging with account: {account_holder_name}")
                    # Remove old blob handler if exists
                    logger = logging.getLogger(__name__)
                    for handler in logger.handlers[:]:
                        if hasattr(handler, 'container_name'):  # Azure Blob handler
                            logger.removeHandler(handler)
                            handler.close()
                    
                    # Setup new blob handler with correct account name
                    blob_handler, blob_path = setup_azure_blob_logging(
                        account_name=account_holder_name,
                        logger_name=__name__,
                        streaming_mode=True
                    )
                    if blob_handler:
                        logger.info(f"[AUTH] Azure Blob Storage logging updated: {blob_path}")
                        print(f"[AUTH] ✓ Azure Blob Storage logging updated with account: {account_holder_name}")
            except Exception as e:
                print(f"[AUTH] Warning: Could not update Azure Blob logging: {e}")
            
            # Store API key if provided
            if data.get('api_key'):
                kite_api_key = api_key
            
            return jsonify({
                'success': True,
                'message': 'Connected successfully',
                'authenticated': True,
                'account_name': account_holder_name
            })
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Invalid or expired access token: {str(e)}'
            }), 401
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/connectivity', methods=['GET'])
def check_connectivity():
    """Check system connectivity status"""
    try:
        global strategy_bot, kite_client_global
        
        # CRITICAL: First check if user is authenticated via session
        is_authenticated = SaaSSessionManager.is_authenticated()
        
        connectivity = {
            'connected': False,
            'api_connected': False,
            'websocket_connected': False,
            'api_authenticated': False,
            'last_check': datetime.now().isoformat(),
            'status_message': 'Not Authenticated'
        }
        
        # If not authenticated, return immediately
        if not is_authenticated:
            return jsonify(connectivity)
        
        # Try to load credentials from session and sync with global client
        try:
            creds = SaaSSessionManager.get_credentials()
            if creds.get('access_token') and not kite_client_global:
                # Try to recreate kite client from session credentials
                global kite_api_key, kite_api_secret
                kite_api_key = creds.get('api_key', '')
                kite_api_secret = creds.get('api_secret', '')
                if kite_api_key and kite_api_secret and creds.get('access_token'):
                    try:
                        from src.kite_client import KiteClient
                    except ImportError:
                        from kite_client import KiteClient
                    kite_client_global = KiteClient(
                        kite_api_key,
                        kite_api_secret,
                        access_token=creds.get('access_token'),
                        account=creds.get('full_name', 'DASHBOARD')
                    )
        except Exception as e:
            logging.warning(f"[CONNECTIVITY] Could not sync session credentials: {e}")
        
        # Check global kite client first
        if kite_client_global and hasattr(kite_client_global, 'kite'):
            is_valid, result = validate_kite_connection(kite_client_global)
            if is_valid:
                connectivity['api_authenticated'] = True
                connectivity['api_connected'] = True
                connectivity['status_message'] = 'API Connected'
            else:
                connectivity['api_authenticated'] = kite_client_global.access_token is not None
                connectivity['api_connected'] = False
                connectivity['status_message'] = f'API Error: {result[:50]}'
                
                # Try auto-reconnection
                if kite_api_key:
                    if reconnect_kite_client():
                        connectivity['api_authenticated'] = True
                        connectivity['api_connected'] = True
                        connectivity['status_message'] = 'API Connected (reconnected)'
        
        # Also check bot's kite client
        if not connectivity['api_connected'] and strategy_bot and hasattr(strategy_bot, 'kite_client'):
            try:
                if hasattr(strategy_bot.kite_client, 'kite'):
                    strategy_bot.kite_client.kite.profile()
                    connectivity['api_authenticated'] = True
                    connectivity['api_connected'] = True
                    connectivity['status_message'] = 'API Connected'
            except Exception as api_error:
                if not connectivity['status_message']:
                    connectivity['api_authenticated'] = strategy_bot.kite_client.access_token is not None if hasattr(strategy_bot.kite_client, 'access_token') else False
                    connectivity['api_connected'] = False
                    connectivity['status_message'] = f'API Error: {str(api_error)[:50]}'
        
        if not connectivity['status_message']:
            connectivity['status_message'] = 'Not Authenticated'
        
        connectivity['connected'] = connectivity['api_connected']
        
        return jsonify(connectivity)
    except Exception as e:
        return jsonify({
            'connected': False,
            'api_connected': False,
            'websocket_connected': False,
            'error': str(e),
            'status_message': f'Error: {str(e)}'
        }), 500

def update_config_file(param_name, new_value):
    """Update parameter in config.py file"""
    try:
        # Determine config file path - check both locations
        config_path = os.path.join('src', 'config.py')
        if not os.path.exists(config_path):
            config_path = 'config.py'
        if not os.path.exists(config_path):
            # Try absolute path
            import sys
            if 'src' in sys.path:
                config_path = os.path.join(sys.path[0], 'src', 'config.py')
            else:
                config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.py')
        
        # Read current config file
        with open(config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        # Handle dictionary values (like STOP_LOSS_CONFIG)
        if isinstance(new_value, dict):
            # Find the start of the dictionary
            start_idx = None
            
            for i, line in enumerate(lines):
                if line.strip().startswith(f'{param_name} ='):
                    start_idx = i
                    break
            
            if start_idx is None:
                print(f"Parameter {param_name} not found in config file")
                return False
            
            # Find the end of the dictionary (matching braces)
            brace_count = 0
            end_idx = start_idx
            found_opening = False
            
            for i in range(start_idx, len(lines)):
                line = lines[i]
                brace_count += line.count('{')
                brace_count -= line.count('}')
                if '{' in line:
                    found_opening = True
                if found_opening and brace_count == 0:
                    end_idx = i
                    break
            
            # Build dictionary string with proper formatting
            dict_lines = [f'{param_name} = {{\n']
            for key, value in new_value.items():
                dict_lines.append(f'    "{key}": {value},\n')
            dict_lines.append('}')
            
            # Extract comment from original start line if exists
            comment = ''
            if '#' in lines[start_idx]:
                comment = ' #' + lines[start_idx].split('#', 1)[1].strip()
            dict_lines[-1] = dict_lines[-1].rstrip('\n') + comment + '\n'
            
            # Replace the dictionary block
            lines = lines[:start_idx] + dict_lines + lines[end_idx+1:]
            updated = True
        else:
            # Handle simple values
            updated = False
            for i, line in enumerate(lines):
                if line.strip().startswith(f'{param_name} ='):
                    # Extract the comment if it exists
                    comment = ''
                    if '#' in line:
                        comment = ' #' + line.split('#', 1)[1].strip()
                    
                    # Format the value appropriately
                    if isinstance(new_value, str):
                        value_str = f"'{new_value}'"
                    elif isinstance(new_value, bool):
                        value_str = str(new_value)
                    elif isinstance(new_value, float):
                        value_str = str(new_value)
                    else:
                        value_str = str(new_value)
                    
                    # Update the line
                    lines[i] = f'{param_name} = {value_str}{comment}\n'
                    updated = True
                    break
                    
        if not updated:
            print(f"Parameter {param_name} not found in config file")
            return False
            
        # Write updated config back to file
        with open(config_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
            
        print(f"Successfully updated {param_name} = {new_value}")
        return True
        
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        return False
    except PermissionError:
        print(f"Permission denied: Cannot write to {config_path}")
        return False
    except Exception as e:
        print(f"Error updating config file: {e}")
        import traceback
        traceback.print_exc()
        return False

def initialize_dashboard():
    """Initialize dashboard and attempt to reconnect if token exists"""
    global kite_api_key
    try:
        # Try to load saved token if API key is available
        if kite_api_key:
            logging.info("[INIT] Attempting to reconnect with saved token...")
            if reconnect_kite_client():
                logging.info("[INIT] Successfully reconnected on startup")
            else:
                logging.info("[INIT] No valid saved token found or reconnection failed")
    except Exception as e:
        logging.warning(f"[INIT] Error during initialization: {e}")

def start_dashboard(host=None, port=None, debug=False):
    """Start the config dashboard web server"""
    try:
        # Use config values if not provided
        if host is None:
            host = DASHBOARD_HOST
        if port is None:
            port = DASHBOARD_PORT
        
        print("=" * 60)
        print(f"[CONFIG DASHBOARD] Starting web server")
        print(f"[CONFIG DASHBOARD] Host: {host}")
        print(f"[CONFIG DASHBOARD] Port: {port}")
        print(f"[CONFIG DASHBOARD] Dashboard URL: http://{host}:{port}")
        print(f"[CONFIG DASHBOARD] Configuration loaded from: src/config.py")
        print("=" * 60)
        
        # Log startup info with broker_id context if available
        try:
            broker_id = SaaSSessionManager.get_broker_id()
            if broker_id:
                logging.info(f"[DASHBOARD] Starting Flask app on {host}:{port} (broker_id: {broker_id})")
            else:
                logging.info(f"[DASHBOARD] Starting Flask app on {host}:{port}")
        except:
            logging.info(f"[DASHBOARD] Starting Flask app on {host}:{port}")
        logging.info(f"[DASHBOARD] Dashboard will be available at http://{host}:{port}")
        
        # Initialize dashboard in background thread (non-blocking for Azure startup probe)
        # This allows the health check endpoint to respond immediately
        init_thread = threading.Thread(target=initialize_dashboard, daemon=True)
        init_thread.start()
        logging.info("[DASHBOARD] Dashboard initialization started in background thread")
        
        # Run Flask app (blocking call)
        app.run(host=host, port=port, debug=debug, use_reloader=False)
    except Exception as e:
        error_msg = f"[DASHBOARD] Failed to start dashboard: {e}"
        print(error_msg)
        logging.error(error_msg)
        import traceback
        traceback_str = traceback.format_exc()
        logging.error(f"[DASHBOARD] Traceback: {traceback_str}")
        print(traceback_str)
        raise  # Re-raise to see error in Azure logs

if __name__ == '__main__':
    start_dashboard()
