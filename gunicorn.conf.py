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
worker_class = "sync"
worker_connections = 1000
timeout = 600  # 10 minutes - long timeout for slow startup
keepalive = 5

# Threading (if using threads worker class)
threads = 2

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
max_requests = 1000
max_requests_jitter = 50

# Worker timeout for handling requests
# worker_tmp_dir - leave as default (None) for portability

# SSL (if needed in future)
# keyfile = None
# certfile = None
