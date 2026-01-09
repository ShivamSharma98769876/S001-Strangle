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
from src.config_dashboard import app

# This is the WSGI application object that Gunicorn expects
application = app

# Also expose as 'app' for compatibility
__all__ = ['application', 'app']
