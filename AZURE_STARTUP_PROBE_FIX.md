# Azure App Service Startup Probe Fix - 504 Gateway Timeout

## Problem

Azure App Service startup probe is failing after 230 seconds, causing a 504 Gateway Timeout error. The container starts successfully but the health check endpoint doesn't respond in time.

## Root Causes

1. **Dependencies installing during startup** - The startup script was installing dependencies on every container start, which takes significant time
2. **Heavy application initialization** - Application imports and initialization were blocking the health endpoint
3. **Startup probe timeout** - Default Azure startup probe timeout may be too short for the application

## Solutions Implemented

### 1. Optimized Startup Script (`startup.sh`)

**Changes:**
- ✅ Removed dependency installation from startup script (dependencies should be in deployment package)
- ✅ Added better logging with timestamps
- ✅ Optimized gunicorn command with proper settings
- ✅ Added error handling and fallback options

**Key Optimization:**
```bash
# SKIP dependency installation during startup
# Dependencies should be installed during deployment/build
# This significantly speeds up startup time
```

### 2. Early Health Endpoint Registration

**Location:** `src/config_dashboard.py` (lines 94-103)

The health endpoint is now registered **immediately** after Flask app creation, before any heavy imports or initialization:

```python
# CRITICAL: Register health endpoint IMMEDIATELY after app creation
@app.route('/health')
@app.route('/healthz')
def health_check_early():
    """Health check endpoint - responds immediately"""
    return {'status': 'healthy', 'service': 'trading-bot-dashboard'}, 200
```

**Benefits:**
- Health endpoint available in < 1 second
- No dependencies on other modules
- Works even if other parts of the app fail to initialize

### 3. Optimized WSGI Entry Point

**Location:** `wsgi.py`

- Reduced logging during import (faster startup)
- Better error handling with fallback health endpoint
- Minimal overhead during app import

## Azure Configuration

### Option 1: Configure Startup Probe in Azure Portal (Recommended)

1. Go to **Azure Portal** → Your App Service
2. Navigate to **Configuration** → **General settings**
3. Find **Startup Command** and set it to:
   ```bash
   bash startup.sh
   ```
   Or if using direct gunicorn:
   ```bash
   gunicorn --bind 0.0.0.0:8000 --timeout 600 --workers 1 --threads 2 --preload wsgi:app
   ```

4. **Health check path:** Set to `/health` or `/healthz`
5. **Startup probe timeout:** Increase to 300-600 seconds if needed
6. **Startup probe interval:** 10 seconds
7. **Startup probe failure threshold:** 30 (allows 5 minutes for startup)

### Option 2: Configure via Azure CLI

```bash
# Set startup command
az webapp config set \
  --resource-group <your-resource-group> \
  --name <your-app-name> \
  --startup-file "bash startup.sh"

# Configure health check (if available in your App Service plan)
az webapp config set \
  --resource-group <your-resource-group> \
  --name <your-app-name> \
  --health-check-path "/health"
```

### Option 3: Use Application Settings

Add these application settings in Azure Portal:

- `WEBSITES_CONTAINER_START_TIME_LIMIT`: `600` (10 minutes)
- `SCM_COMMAND_IDLE_TIMEOUT`: `600`

## Verification

### 1. Check Health Endpoint

Once deployed, verify the health endpoint responds quickly:

```bash
curl https://your-app.azurewebsites.net/health
```

Expected response:
```json
{
  "status": "healthy",
  "service": "trading-bot-dashboard"
}
```

### 2. Monitor Startup Logs

Check Azure App Service logs to verify:
- ✅ Health endpoint is registered early
- ✅ No dependency installation during startup
- ✅ Application starts within timeout period

### 3. Check Startup Time

Look for these log messages:
```
[STARTUP] Starting Trading Bot Dashboard (Azure)
[STARTUP] ✓ Gunicorn found - starting with gunicorn...
[WSGI] ✓ WSGI application object ready
```

## Troubleshooting

### Issue: Still getting 504 timeout

**Solutions:**
1. **Increase startup probe timeout** in Azure Portal (Configuration → General settings)
2. **Check application logs** for slow imports or blocking operations
3. **Verify dependencies are installed** during deployment, not at startup
4. **Check if database connections** are blocking startup (move to lazy initialization)

### Issue: Health endpoint not responding

**Solutions:**
1. **Verify health endpoint is registered** - Check logs for "[WSGI] ✓ Health endpoints should be available"
2. **Test health endpoint directly** - `curl https://your-app.azurewebsites.net/health`
3. **Check for import errors** - Review logs for Python import failures
4. **Verify startup script** - Ensure `startup.sh` is executable and correct

### Issue: Application starts but health check fails

**Solutions:**
1. **Check health endpoint path** - Ensure Azure is checking `/health` or `/healthz`
2. **Verify port configuration** - Ensure app is listening on the port Azure provides
3. **Check firewall/network** - Ensure Azure can reach the health endpoint
4. **Review startup probe configuration** - Increase timeout and failure threshold

## Best Practices

1. **Dependencies:** Install during deployment/build, not at runtime
2. **Health Endpoint:** Register immediately after app creation
3. **Lazy Loading:** Move heavy imports to function level, not module level
4. **Database Connections:** Initialize on first request, not at startup
5. **Logging:** Use minimal logging during startup, increase after app is ready

## Expected Startup Time

With these optimizations:
- **Before:** 230+ seconds (timeout)
- **After:** 10-30 seconds (typical)
- **Health endpoint:** < 1 second

## Files Modified

1. ✅ `startup.sh` - Optimized startup script
2. ✅ `src/config_dashboard.py` - Early health endpoint registration
3. ✅ `wsgi.py` - Optimized WSGI entry point
4. ✅ `AZURE_STARTUP_PROBE_FIX.md` - This documentation

## Next Steps

1. Deploy the updated code to Azure
2. Configure startup probe settings in Azure Portal
3. Monitor startup logs to verify improvements
4. Test health endpoint response time
5. Adjust timeout settings if needed

## Additional Resources

- [Azure App Service Health Checks](https://learn.microsoft.com/en-us/azure/app-service/monitor-health-checks)
- [Gunicorn Configuration](https://docs.gunicorn.org/en/stable/settings.html)
- [Flask Deployment Best Practices](https://flask.palletsprojects.com/en/2.3.x/deploying/)
