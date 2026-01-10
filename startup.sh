#!/bin/bash
# Azure App Service startup script for Linux
# This script is executed when the app starts
# OPTIMIZED: Dependencies should be installed during deployment, not at startup

echo "=========================================="
echo "Starting Trading Bot Dashboard (Azure)"
echo "=========================================="
echo "[STARTUP] $(date '+%Y-%m-%d %H:%M:%S') - Startup script executing"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "[STARTUP] Activating virtual environment..."
    source venv/bin/activate
fi

# SKIP dependency installation during startup - dependencies should be in deployment package
# This significantly speeds up startup time for Azure App Service
# If dependencies are missing, they should be installed during deployment/build
# Uncomment the following block ONLY if you need to install dependencies at runtime:
# if [ -f "requirements.txt" ]; then
#     echo "[STARTUP] Installing dependencies (this may take time)..."
#     pip install -r requirements.txt --quiet --no-cache-dir
# fi

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src"

# Get port from environment (Azure provides this)
# Azure App Service uses HTTP_PLATFORM_PORT or PORT
PORT=${PORT:-${HTTP_PLATFORM_PORT:-8080}}
echo "=========================================="
echo "[STARTUP] Port Configuration:"
echo "  PORT: ${PORT}"
echo "  HTTP_PLATFORM_PORT: ${HTTP_PLATFORM_PORT:-not set}"
echo "  Using port: $PORT"
echo "=========================================="

# Start the Flask dashboard application
# For Azure, we start the dashboard which provides the web interface
echo "[STARTUP] Starting Flask dashboard..."
cd "$(dirname "$0")" || exit 1

# Verify wsgi.py exists
if [ -f "wsgi.py" ]; then
    echo "[STARTUP] ✓ Found wsgi.py - using as WSGI entry point"
    WSGI_ENTRY="wsgi:app"
else
    echo "[STARTUP] ⚠ Warning: wsgi.py not found, will use direct import"
    WSGI_ENTRY="src.config_dashboard:app"
fi

# Try gunicorn first (better for production), fallback to Flask dev server
if command -v gunicorn &> /dev/null; then
    echo "[STARTUP] ✓ Gunicorn found - starting with gunicorn..."
    echo "[STARTUP]   Binding to: 0.0.0.0:$PORT"
    echo "[STARTUP]   Health check endpoint: /health or /healthz"
    echo "[STARTUP]   WSGI entry: $WSGI_ENTRY"
    echo "[STARTUP]   Starting worker..."
    echo "[STARTUP] $(date '+%Y-%m-%d %H:%M:%S') - Starting gunicorn server"
    
    # Use optimized gunicorn settings for Azure App Service
    # --preload: Load app before forking workers (faster startup)
    # --timeout 600: Long timeout for Azure startup probe
    # --workers 1: Single worker for Azure App Service
    # --threads 2: 2 threads per worker for concurrent requests
    # --access-logfile -: Log to stdout (captured by Azure)
    # --error-logfile -: Log errors to stdout (captured by Azure)
    exec gunicorn \
        --bind 0.0.0.0:$PORT \
        --timeout 600 \
        --workers 1 \
        --threads 2 \
        --access-logfile - \
        --error-logfile - \
        --log-level info \
        --preload \
        "$WSGI_ENTRY"
else
    echo "[STARTUP] ⚠ Gunicorn not found - using Flask development server (not recommended for production)"
    echo "[STARTUP] $(date '+%Y-%m-%d %H:%M:%S') - Starting Flask dev server"
    python -c "
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.config_dashboard import start_dashboard
import os
port = int(os.getenv('PORT', os.getenv('HTTP_PLATFORM_PORT', 8080)))
print(f'[STARTUP] Starting dashboard on port {port}...')
start_dashboard(host='0.0.0.0', port=port, debug=False)
"
fi

