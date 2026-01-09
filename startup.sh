#!/bin/bash
# Azure App Service startup script for Linux
# This script is executed when the app starts

echo "=========================================="
echo "Starting Trading Bot Dashboard (Azure)"
echo "=========================================="

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
fi

# Install dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install -r requirements.txt --quiet
fi

# Set Python path
export PYTHONPATH="${PYTHONPATH}:$(pwd):$(pwd)/src"

# Get port from environment (Azure provides this)
PORT=${PORT:-${HTTP_PLATFORM_PORT:-8080}}
echo "Using port: $PORT"

# Start the Flask dashboard application
# For Azure, we start the dashboard which provides the web interface
echo "Starting Flask dashboard..."
cd "$(dirname "$0")" || exit 1

# Try gunicorn first (better for production), fallback to Flask dev server
if command -v gunicorn &> /dev/null; then
    echo "Starting with gunicorn..."
    exec gunicorn --bind 0.0.0.0:$PORT --timeout 600 --workers 1 --threads 2 --access-logfile - --error-logfile - --log-level info "src.config_dashboard:app"
else
    echo "Starting with Flask (gunicorn not found, using dev server)..."
    python -c "
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.config_dashboard import start_dashboard
import os
port = int(os.getenv('PORT', os.getenv('HTTP_PLATFORM_PORT', 8080)))
print(f'Starting dashboard on port {port}...')
start_dashboard(host='0.0.0.0', port=port, debug=False)
"
fi

