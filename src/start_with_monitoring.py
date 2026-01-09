"""
Startup script for Trading Bot with Real-time Config Monitoring
Integrates config monitoring, web dashboard, and main strategy
"""

import os
import sys
import threading
import time
import logging
from datetime import datetime

# Disable Azure Monitor OpenTelemetry if not properly configured
# This prevents "Bad Request" errors when Application Insights is misconfigured
if not os.getenv('APPLICATIONINSIGHTS_CONNECTION_STRING'):
    os.environ.setdefault('APPLICATIONINSIGHTS_ENABLE_AGENT', 'false')
    # Suppress OpenTelemetry errors
    logging.getLogger('azure.monitor.opentelemetry').setLevel(logging.CRITICAL)

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import environment utilities
try:
    from environment import is_azure_environment, setup_logging, get_log_directory
except ImportError:
    # Fallback if environment module not available
    def is_azure_environment():
        return any(os.getenv(var) for var in ['WEBSITE_INSTANCE_ID', 'WEBSITE_SITE_NAME'])
    def get_log_directory():
        return os.path.dirname(os.path.abspath(__file__))

# Import dashboard configuration
try:
    import config
    DASHBOARD_HOST = getattr(config, 'DASHBOARD_HOST', '0.0.0.0')
    DASHBOARD_PORT = getattr(config, 'DASHBOARD_PORT', 8080)
except (ImportError, AttributeError):
    # Fallback defaults if config not available
    DASHBOARD_HOST = '0.0.0.0'
    DASHBOARD_PORT = 8080

def setup_logging():
    """Setup logging for the monitoring system"""
    if is_azure_environment():
        # Use environment-aware logging for Azure
        # For dashboard startup, we need fast initialization to prevent 504 timeout
        try:
            from environment import setup_azure_logging
            # Pass account_name=None for dashboard, which will trigger fast startup mode
            logger, log_file = setup_azure_logging(logger_name='config_monitor', account_name=None)
            logging.info(f"[ENV] Azure environment detected - Logs: {log_file}")
        except ImportError:
            # Fallback to basic logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[logging.StreamHandler()]
            )
    else:
        # Local environment - use file and console
        log_dir = get_log_directory(account_name=None)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, 'config_monitoring.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler()
            ]
        )

def start_config_dashboard():
    """Start the web dashboard in a separate thread"""
    try:
        from config_dashboard import start_dashboard
        logging.info(f"[DASHBOARD] Starting web dashboard on {DASHBOARD_HOST}:{DASHBOARD_PORT}...")
        # Pass None to use config values from config_dashboard.py
        start_dashboard(host=None, port=None, debug=False)
    except Exception as e:
        logging.error(f"[DASHBOARD] Failed to start dashboard: {e}")
        import traceback
        logging.error(f"[DASHBOARD] Traceback: {traceback.format_exc()}")
        # Re-raise to see error in Azure logs
        raise

def main():
    """Main startup function"""
    try:
        setup_logging()
        
        # Check if running in Azure - if so, just start dashboard (not the trading strategy)
        if is_azure_environment():
            print("=" * 60)
            print("TRADING BOT DASHBOARD (Azure Mode)")
            print("=" * 60)
            print("[AZURE] Azure environment detected")
            print(f"[AZURE] Starting dashboard on port: {DASHBOARD_PORT}")
            print("=" * 60)
            # Start dashboard directly (blocking call for Azure)
            start_config_dashboard()
            return  # Exit after dashboard starts (it runs forever)
        
        # Local environment: Start dashboard in thread, then run strategy
        print("=" * 60)
        print("TRADING BOT WITH REAL-TIME CONFIG MONITORING")
        print("=" * 60)
        print("Features:")
        print("[OK] Real-time config file monitoring")
        print("[OK] Auto-reload parameters without restart")
        print("[OK] Web dashboard for parameter management")
        print("[OK] Configuration change history tracking")
        print("[OK] Parameter validation and rollback")
        print("=" * 60)
        
        # Start web dashboard in background thread
        dashboard_thread = threading.Thread(target=start_config_dashboard, daemon=True)
        dashboard_thread.start()
        
        # Give dashboard time to start
        time.sleep(2)
        
        print(f"\nWeb Dashboard: http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
        print("Config Monitor: Active")
        print("Auto-reload: Enabled")
        print("\n" + "=" * 60)
        
    except Exception as e:
        logging.error(f"[STARTUP] Fatal error during startup: {e}")
        import traceback
        logging.error(f"[STARTUP] Traceback: {traceback.format_exc()}")
        print(f"[ERROR] Failed to start application: {e}")
        traceback.print_exc()
        sys.exit(1)
    
    try:
        # Import and run the main strategy
        import importlib.util
        
        # Get the correct path to the strategy file
        # Strategy file is at: PythonProgram\Strangle10Points\src\Straddle10PointswithSL-Limit.py
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        strategy_file = os.path.join(script_dir, 'src', 'Straddle10PointswithSL-Limit.py')
        
        # Fallback to absolute path if relative doesn't work
        if not os.path.exists(strategy_file):
            abs_path = r'C:\Users\SharmaS8\OneDrive - Unisys\Shivam Imp Documents-2024 June\PythonProgram\Strangle10Points\src\Straddle10PointswithSL-Limit.py'
            if os.path.exists(abs_path):
                strategy_file = abs_path
            else:
                # Last fallback: check old location
                old_path = os.path.join(script_dir, 'Straddle10PointswithSL-Limit.py')
                if os.path.exists(old_path):
                    strategy_file = old_path
        
        if not os.path.exists(strategy_file):
            logging.error(f"[STARTUP] Strategy file not found. Checked:")
            logging.error(f"  1. {os.path.join(script_dir, 'src', 'Straddle10PointswithSL-Limit.py')}")
            logging.error(f"  2. {abs_path if 'abs_path' in locals() else 'N/A'}")
            logging.error(f"  3. {os.path.join(script_dir, 'Straddle10PointswithSL-Limit.py')}")
            logging.error("[STARTUP] Please ensure the strategy file exists at one of these locations.")
            return
        
        logging.info(f"[STARTUP] Loading strategy from: {strategy_file}")
        spec = importlib.util.spec_from_file_location("strategy", strategy_file)
        strategy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(strategy_module)
        strategy_main = strategy_module.main
        
        logging.info("[STARTUP] Starting main trading strategy...")
        strategy_main()
        
    except KeyboardInterrupt:
        logging.info("[STARTUP] Shutdown requested by user")
    except Exception as e:
        logging.error(f"[STARTUP] Unexpected error: {e}")
    finally:
        logging.info("[STARTUP] Shutting down monitoring system...")
        print("\n[STOPPED] Config monitoring stopped")

if __name__ == "__main__":
    main()
