# Gunicorn Sendfile Error Fix

## Problem
```
ValueError: non-blocking sockets are not supported
```
This error occurs when Gunicorn tries to use `sendfile()` optimization for static files with `gthread` worker class on non-blocking sockets.

## Root Cause
- Gunicorn's `gthread` worker class uses non-blocking sockets
- `sendfile()` system call doesn't work with non-blocking sockets
- This happens when serving static files (like `dashboard.js`)

## Solution Applied

### 1. Force Sync Worker Class
**File: `gunicorn.conf.py`**
- ✅ Set `worker_class = "sync"` (explicitly, not gthread)
- ✅ Added comments explaining why sync is required

**File: `startup.sh`**
- ✅ Added `--worker-class sync` to command line
- ✅ Removed `--threads 2` (not used with sync worker)

### 2. Custom Static File Handler
**File: `src/config_dashboard.py`**
- ✅ Added custom `/static/<path:filename>` route
- ✅ Uses `send_from_directory()` which doesn't trigger sendfile()
- ✅ Files are read into memory and sent normally

### 3. Flask Configuration
- ✅ Added `SEND_FILE_MAX_AGE_DEFAULT` configuration
- ✅ Ensures proper caching headers

## Changes Made

### gunicorn.conf.py
```python
worker_class = "sync"  # Must be sync, not gthread
threads = 1  # Not used with sync worker
```

### startup.sh
```bash
--worker-class sync  # Explicitly set sync worker
# Removed --threads 2 (not compatible with sync)
```

### src/config_dashboard.py
```python
@app.route('/static/<path:filename>')
def custom_static(filename):
    """Custom static handler that avoids sendfile() issues"""
    from flask import send_from_directory
    return send_from_directory(app.static_folder, filename)
```

## Why This Works

1. **Sync Worker**: Uses blocking sockets, which support sendfile()
2. **Custom Handler**: Bypasses Gunicorn's sendfile optimization
3. **Flask send_from_directory**: Reads file into memory, avoiding sendfile()

## Verification

After deploying, check logs for:
- ✅ No more "non-blocking sockets are not supported" errors
- ✅ Static files serve successfully
- ✅ Worker class shows as "sync" in logs

## Alternative Solutions (if issue persists)

If the error still occurs:

1. **Disable sendfile in Gunicorn** (if possible in future versions)
2. **Use gevent worker** (if async needed):
   ```python
   worker_class = "gevent"
   ```
3. **Serve static files via CDN** (Azure Blob Storage + CDN)

## Notes

- Sync worker is single-threaded but works reliably
- For Azure App Service, sync worker is sufficient
- Custom static handler ensures compatibility
- Flask's built-in static handler will still work as fallback
