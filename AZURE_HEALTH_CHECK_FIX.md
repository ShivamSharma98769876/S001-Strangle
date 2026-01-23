# Azure Health Check Fix Guide

## Problem
Azure App Service is reporting the application as unhealthy. The health check probe is failing.

## Root Causes
1. Health endpoint might be slow (> 1 second response time)
2. Health endpoint might be blocked by authentication middleware
3. Health endpoint might be returning errors
4. Azure might be configured with wrong health check path

## Fixes Applied

### 1. Optimized Health Endpoint (`src/config_dashboard.py`)
- ✅ Health check now returns immediately (checked FIRST in before_request)
- ✅ Added HEAD method support (Azure sometimes uses HEAD requests)
- ✅ Uses proper JSON response with jsonify
- ✅ Added timestamp for debugging

### 2. Optimized Before Request Handler
- ✅ Health paths are checked FIRST before any authentication
- ✅ Health endpoints skip ALL processing (no session checks, no JWT validation)
- ✅ Returns immediately for health checks

## Azure Configuration Steps

### Step 1: Verify Health Check Path in Azure Portal

1. Go to Azure Portal → Your App Service
2. Navigate to **Settings** → **Health check**
3. Verify the health check path is set to one of:
   - `/health` (recommended)
   - `/healthz`
4. If not set, configure it to `/health`

### Step 2: Configure Health Check Settings

In Azure Portal → **Settings** → **Health check**:

- **Enable**: ✅ Enabled
- **Path**: `/health`
- **Interval**: 30 seconds (default)
- **Unhealthy threshold**: 3 (default)
- **Healthy threshold**: 1 (default)

### Step 3: Verify Application Logs

Check Azure App Service logs for:
- Health endpoint responses
- Any errors during startup
- Slow response times

**To view logs:**
1. Azure Portal → Your App Service
2. **Monitoring** → **Log stream** (for real-time logs)
3. **Monitoring** → **Logs** (for historical logs)

### Step 4: Test Health Endpoint Manually

Test the health endpoint directly:

```bash
# Test from command line
curl https://your-app.azurewebsites.net/health

# Expected response:
{"status": "healthy", "service": "trading-bot-dashboard", "timestamp": "2024-..."}
```

Or test in browser:
- Navigate to: `https://your-app.azurewebsites.net/health`
- Should return JSON with status "healthy"

## Troubleshooting

### If Health Check Still Fails:

1. **Check Response Time**
   - Health endpoint must respond in < 1 second
   - Check logs for slow operations during startup

2. **Check for Errors**
   - Review application logs for exceptions
   - Check if health endpoint is being called
   - Verify no authentication errors

3. **Verify Path Configuration**
   - Ensure Azure health check path matches `/health` or `/healthz`
   - Check if proxy/rewrite rules are affecting the path

4. **Check Application Startup**
   - Verify application starts successfully
   - Check for slow imports or initialization
   - Review `start_with_monitoring.py` for startup issues

5. **Test Locally**
   ```bash
   # Run locally and test health endpoint
   python src/start_with_monitoring.py
   curl http://localhost:8080/health
   ```

## Code Changes Summary

### Modified Files:
1. **src/config_dashboard.py**
   - Health endpoint now checks path FIRST
   - Added HEAD method support
   - Improved JSON response
   - Health checks skip all middleware

### Health Endpoint Implementation:
```python
@app.route('/health', methods=['GET', 'HEAD'])
@app.route('/healthz', methods=['GET', 'HEAD'])
def health_check_early():
    """Health check - responds immediately, no dependencies"""
    from flask import jsonify
    return jsonify({
        'status': 'healthy',
        'service': 'trading-bot-dashboard',
        'timestamp': datetime.now().isoformat()
    }), 200
```

## Expected Behavior

✅ Health endpoint should:
- Respond in < 100ms
- Return HTTP 200 status
- Return valid JSON
- Work without authentication
- Work during application startup

## Next Steps

1. Deploy the updated code to Azure
2. Verify health check path in Azure Portal
3. Monitor logs for health check requests
4. Wait 2-3 minutes for Azure to re-evaluate health status
5. Check Azure Portal → **Health check** status

## Additional Notes

- Health endpoint is registered IMMEDIATELY after Flask app creation
- Health endpoint has ZERO dependencies (no database, no imports)
- Health endpoint bypasses ALL authentication and middleware
- Health endpoint supports both GET and HEAD methods
