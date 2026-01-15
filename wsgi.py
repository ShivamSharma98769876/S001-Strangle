"""
WSGI Entry Point for Azure App Service Deployment
This file provides the WSGI application object for Gunicorn
"""
import os
import re
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

# ===== WSGI PREFIX STRIP MIDDLEWARE =====
def _normalize_prefix(prefix: str) -> str:
    if not prefix:
        return ''
    if not prefix.startswith('/'):
        prefix = '/' + prefix
    return prefix.rstrip('/')

def _detect_prefix_from_path(path: str) -> str:
    if not path:
        return ''
    match = re.match(r'^(/s\d{3})(/|$)', path)
    return match.group(1) if match else ''

def prefix_strip_middleware(wsgi_app):
    """Strip reverse-proxy prefix (e.g., /s001) before Flask routing."""
    def middleware(environ, start_response):
        path_info = environ.get('PATH_INFO', '') or ''
        script_name = environ.get('SCRIPT_NAME', '') or ''

        configured_prefix = _normalize_prefix(
            os.getenv('PROXY_PREFIX') or os.getenv('APPLICATION_ROOT') or ''
        )
        prefix = configured_prefix or _detect_prefix_from_path(path_info)

        if prefix and path_info.startswith(prefix):
            environ['SCRIPT_NAME'] = script_name + prefix
            environ['PATH_INFO'] = path_info[len(prefix):] or '/'
            print(f"[WSGI] ✅ STRIPPED prefix '{prefix}' -> PATH_INFO='{environ['PATH_INFO']}'")

        return wsgi_app(environ, start_response)
    return middleware

# This is the WSGI application object that Gunicorn expects
application = prefix_strip_middleware(app)

# Also expose as 'app' for compatibility
app = application
__all__ = ['application', 'app']

# Log that WSGI is ready
print("[WSGI] ✓ WSGI application object ready")
print("[WSGI] ✓ Application can be accessed as 'application' or 'app'")
print("[WSGI] ✓ Ready for Gunicorn to start")
