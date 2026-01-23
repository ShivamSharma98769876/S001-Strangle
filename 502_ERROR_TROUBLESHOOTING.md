# 502 Bad Gateway Error Troubleshooting Guide

## Problem
Getting 502 Bad Gateway errors when accessing the application. This means the server/application is not responding properly.

## Common Causes

### 1. Application Not Running
- The Flask/Gunicorn server crashed during startup
- The application failed to start due to import errors
- The application is taking too long to start (timeout)

### 2. Server Overload
- Too many requests causing server to become unresponsive
- Memory issues causing worker crashes
- Database connection issues

### 3. Configuration Issues
- Wrong port configuration
- Missing environment variables
- Incorrect WSGI entry point

## Immediate Fixes Applied

### 1. Enhanced Error Handling in JavaScript
- ✅ Added 502 error detection and retry logic
- ✅ Longer retry delays for 502 errors (server restart scenarios)
- ✅ Graceful handling - won't crash the UI on 502 errors

### 2. Better Retry Strategy
- ✅ 502 errors now retry with exponential backoff (2s, 4s, 8s)
- ✅ Maximum retry delay of 10 seconds for 502 errors
- ✅ Automatic retry on next update cycle

## Diagnostic Steps

### Step 1: Check Azure Application Logs

1. Go to **Azure Portal** → Your App Service
2. Navigate to **Monitoring** → **Log stream** (real-time logs)
3. Look for:
   - Application startup errors
   - Import errors
   - Database connection errors
   - Worker crash messages

### Step 2: Check Application Health

Test the health endpoint:
```bash
curl https://your-app.azurewebsites.net/health
```

Expected: `{"status": "healthy", ...}`

If this fails, the application is not starting properly.

### Step 3: Check Gunicorn/Server Status

In Azure Portal → **Log stream**, look for:
- `[STARTUP] Starting gunicorn server`
- `[STARTUP] ✓ Gunicorn found`
- Any error messages during startup

### Step 4: Verify Environment Variables

Check Azure Portal → **Configuration** → **Application settings**:
- `PORT` or `HTTP_PLATFORM_PORT` is set
- Database connection strings are correct
- Any required API keys are set

## Common Solutions

### Solution 1: Restart the Application

1. Azure Portal → Your App Service
2. **Overview** → **Restart** button
3. Wait 2-3 minutes for restart
4. Check logs to verify successful startup

### Solution 2: Check for Import Errors

Look in logs for:
- `ImportError`
- `ModuleNotFoundError`
- `SyntaxError`

Fix any import issues in the code.

### Solution 3: Increase Timeout Settings

If application takes long to start:

1. Check `gunicorn.conf.py`:
   ```python
   timeout = 600  # Already set to 10 minutes
   ```

2. Check Azure → **Configuration** → **General settings**:
   - **Startup Command**: Should point to correct entry point
   - **Always On**: Enable if available

### Solution 4: Check Database Connections

If using a database:
- Verify connection string is correct
- Check if database server is accessible
- Verify firewall rules allow Azure IPs

### Solution 5: Reduce Worker Load

If server is overloaded:
- Check `gunicorn.conf.py` worker settings
- Consider increasing worker timeout
- Check for memory leaks in application code

## JavaScript Syntax Error (Line 3421)

The error "Unexpected end of input at line 3421" when the file only has ~2100 lines suggests:

### Possible Causes:
1. **File Truncation**: File not fully loaded
2. **Caching Issue**: Browser using old cached version
3. **Server Issue**: File not being served completely

### Solutions:

1. **Hard Refresh Browser**:
   - Windows: `Ctrl + Shift + R`
   - Mac: `Cmd + Shift + R`

2. **Clear Browser Cache**:
   - Open DevTools (F12)
   - Right-click refresh button → "Empty Cache and Hard Reload"

3. **Check File Size**:
   - Verify `dashboard.js` is complete
   - Check if file is being truncated during deployment

4. **Check Static File Serving**:
   - Verify Flask is serving static files correctly
   - Check if there are any proxy/rewrite rules affecting static files

## Prevention Measures

### 1. Application Startup Monitoring
- Health endpoint responds immediately
- Startup errors are logged clearly
- Graceful degradation on errors

### 2. Error Recovery
- Automatic retry on 502 errors
- Exponential backoff to prevent overload
- User-friendly error messages

### 3. Logging
- All errors are logged to Azure logs
- Startup sequence is logged
- Health check responses are logged

## Code Changes Summary

### Modified Files:
1. **src/static/js/dashboard.js**
   - Added 502 error detection
   - Enhanced retry logic with longer delays for 502
   - Graceful error handling for all endpoints

### Key Improvements:
- ✅ 502 errors are detected and retried automatically
- ✅ Longer retry delays for server restart scenarios
- ✅ UI continues to function even with temporary 502 errors
- ✅ Better error messages for debugging

## Next Steps

1. **Deploy Updated Code**: Deploy the fixes to Azure
2. **Monitor Logs**: Watch Azure logs for startup issues
3. **Test Health Endpoint**: Verify `/health` responds quickly
4. **Clear Browser Cache**: Hard refresh to fix JS syntax error
5. **Check Application Status**: Verify app is running in Azure Portal

## Expected Behavior After Fix

✅ 502 errors are automatically retried
✅ UI shows warning but continues to function
✅ Errors are logged for debugging
✅ Application recovers automatically when server restarts
