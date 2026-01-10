"""
WSGI Entry Point for Azure App Service Deployment
This file provides the WSGI application object for Gunicorn
"""
import os
import sys

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Import the Flask app from config_dashboard
# This import will execute all module-level code in config_dashboard.py
# The health endpoint should be available immediately after this import
# CRITICAL: Health endpoints are registered at the very top of config_dashboard.py
# (right after Flask app creation) to ensure they work even if other imports fail
try:
    # Minimal logging for faster startup - health endpoint must respond quickly
    from src.config_dashboard import app
except Exception as e:
    # Create a minimal app for error reporting if import fails
    import traceback
    traceback.print_exc()
    from flask import Flask
    app = Flask(__name__)
    @app.route('/health')
    @app.route('/healthz')
    def health_error():
        return {'status': 'error', 'message': 'App import failed'}, 500
    raise

# This is the WSGI application object that Gunicorn expects
application = app

# Also expose as 'app' for compatibility
__all__ = ['application', 'app']

# Log that WSGI is ready
print("[WSGI] ✓ WSGI application object ready")
print("[WSGI] ✓ Application can be accessed as 'application' or 'app'")
print("[WSGI] ✓ Ready for Gunicorn to start")
