"""
Gunicorn configuration file for Azure App Service
This file is automatically detected by Gunicorn when present
"""
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', os.getenv('HTTP_PLATFORM_PORT', '8080'))}"
backlog = 2048

# Worker processes
workers = 1  # Single worker for Azure App Service
# Use sync worker to avoid sendfile issues with non-blocking sockets
# gthread worker causes "ValueError: non-blocking sockets are not supported" when using sendfile
worker_class = "sync"
worker_connections = 1000
timeout = 600  # 10 minutes - long timeout for slow startup
keepalive = 5

# Threading (if using threads worker class)
# Note: threads are not used with sync worker class
threads = 1  # Set to 1 for sync worker (threads not used)

# Logging
accesslog = "-"  # Log to stdout (captured by Azure)
errorlog = "-"  # Log errors to stdout (captured by Azure)
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "trading-bot-dashboard"

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Preload app (loads app before forking workers - faster startup)
preload_app = True

# Graceful timeout (time to wait for workers to finish)
graceful_timeout = 30

# Maximum requests per worker before restart (helps prevent memory leaks)
# Set to 0 to disable automatic restarts (workers will only restart on errors)
# With logs endpoint called every 3 seconds, 1000 requests = ~50 minutes
# Increased to prevent frequent restarts during active usage
max_requests = 0  # Disable automatic restarts - let workers run until error
max_requests_jitter = 0

# Worker timeout for handling requests
# worker_tmp_dir - leave as default (None) for portability

# SSL (if needed in future)
# keyfile = None
# certfile = None
