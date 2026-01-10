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
try:
    from src.config_dashboard import app
    print("[WSGI] Successfully imported Flask app from config_dashboard")
except Exception as e:
    print(f"[WSGI] ERROR: Failed to import Flask app: {e}")
    import traceback
    traceback.print_exc()
    # Create a minimal app for error reporting
    from flask import Flask
    app = Flask(__name__)
    @app.route('/health')
    def health_error():
        return {'status': 'error', 'message': 'App import failed'}, 500
    raise

# This is the WSGI application object that Gunicorn expects
application = app

# Also expose as 'app' for compatibility
__all__ = ['application', 'app']

# Log that WSGI is ready
print("[WSGI] WSGI application object ready")
print(f"[WSGI] Health endpoint should be available at /health")
