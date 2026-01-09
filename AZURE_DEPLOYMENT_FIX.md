# Azure Deployment Fix - Startup Command Issue

## Problem

Azure App Service was configured with:
```bash
gunicorn app:app --bind 0.0.0.0:8000 --timeout 600
```

But `app.py` is a **Streamlit application**, not a Flask/WSGI app. This causes the error:
```
Failed to find attribute 'app' in 'app'.
[ERROR] Worker (pid:2122) exited with code 4
[ERROR] Reason: App failed to load.
```

## Solution

A `wsgi.py` file has been created that properly imports the Flask application from `src.config_dashboard`.

## Fix Steps

### 1. Update Azure Portal Configuration

1. Go to **Azure Portal**
2. Navigate to your **App Service**
3. Go to **Configuration** > **General settings**
4. Find **Startup Command**
5. Change it to:
   ```bash
   gunicorn wsgi:app --bind 0.0.0.0:8000 --timeout 600
   ```
6. Click **Save**
7. Restart your App Service

### 2. Verify the Fix

After restarting, check the logs. You should see:
```
[2026-01-09 XX:XX:XX +0000] [XXXX] [INFO] Starting gunicorn XX.X.X
[2026-01-09 XX:XX:XX +0000] [XXXX] [INFO] Listening at: http://0.0.0.0:8000 (XXXX)
[2026-01-09 XX:XX:XX +0000] [XXXX] [INFO] Using worker: sync
[2026-01-09 XX:XX:XX +0000] [XXXX] [INFO] Booting worker with pid: XXXX
```

**No more errors about "Failed to find attribute 'app'"**

## Alternative Startup Commands

If `wsgi:app` doesn't work, you can also use:
```bash
gunicorn src.config_dashboard:app --bind 0.0.0.0:8000 --timeout 600
```

## Files Changed

1. ✅ Created `wsgi.py` - WSGI entry point for deployment
2. ✅ Updated `startup.sh` - Now checks for `wsgi.py` first
3. ✅ Updated `CLOUD_CONFIGURATION_GUIDE.md` - Added troubleshooting section

## Important Notes

- **Do NOT** use `gunicorn app:app` - `app.py` is for Streamlit, not Flask
- The `wsgi.py` file is the standard WSGI entry point for production deployments
- Both `wsgi:app` and `src.config_dashboard:app` will work, but `wsgi:app` is preferred
