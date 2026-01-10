# Azure App Service Scaling Guide - Zero Downtime Deployment

## Problem

Your Azure App Service is currently configured to run on **only one instance**, which causes:
- ⚠️ **Downtime during platform upgrades** - Azure restarts instances during upgrades
- ⚠️ **No redundancy** - Single point of failure
- ⚠️ **Limited scalability** - Cannot handle traffic spikes

## Solution: Scale to Multiple Instances

Scaling to **2 or more instances** provides:
- ✅ **Zero downtime** - Azure upgrades instances one at a time
- ✅ **High availability** - If one instance fails, others continue serving traffic
- ✅ **Better performance** - Load distributed across multiple instances
- ✅ **Automatic failover** - Azure load balancer routes traffic to healthy instances

---

## Step 1: Scale Out in Azure Portal

### Option A: Manual Scaling (Recommended for Start)

1. Go to **Azure Portal** → Your App Service
2. Navigate to **Settings** → **Scale out (App Service plan)**
3. Under **Instance count**, change from `1` to `2` (or more)
4. Click **Save**
5. Wait 2-3 minutes for new instances to provision

**Cost Impact:**
- 2 instances = 2x the cost of 1 instance
- Consider your App Service Plan pricing tier

### Option B: Auto-scaling (Advanced)

1. Go to **Azure Portal** → Your App Service
2. Navigate to **Settings** → **Scale out (App Service plan)**
3. Select **Custom autoscale**
4. Configure rules:
   - **Scale based on:** CPU percentage, Memory, or Request count
   - **Instance range:** Min 2, Max 5 (adjust based on needs)
   - **Scale rules:** Add rules like "Scale out when CPU > 70%"

---

## Step 2: Configure Distributed Sessions (Required for Multiple Instances)

### Why This is Needed

**Important:** Your application currently works perfectly on a single instance with multiple sessions (just like your disciplined-Trader app). Flask's in-memory session storage handles multiple users on a single instance without any issues.

However, with multiple instances, each instance has its own memory. Flask's default in-memory session storage won't work because:
- User authenticates on Instance 1 → session stored in Instance 1's memory
- Next request goes to Instance 2 → session not found → user logged out

### Solution: Use Redis for Distributed Sessions

Your application **already supports Redis** - you just need to configure it!

**Note:** If you want to stay on a single instance (like disciplined-Trader), you don't need Redis. Your current setup already works perfectly for multiple sessions on a single instance.

### Step 2a: Create Azure Redis Cache

1. Go to **Azure Portal** → **Create a resource**
2. Search for **Azure Cache for Redis**
3. Click **Create**
4. Fill in:
   - **Subscription:** Your subscription
   - **Resource group:** Same as your App Service
   - **DNS name:** `your-app-redis` (must be unique)
   - **Location:** Same region as your App Service
   - **Pricing tier:** 
     - **Basic C0** (250 MB) - Good for testing (~$15/month)
     - **Standard C1** (1 GB) - Recommended for production (~$55/month)
5. Click **Create** and wait 5-10 minutes

### Step 2b: Get Redis Connection String

1. Go to your **Redis Cache** resource
2. Navigate to **Access keys**
3. Copy the **Primary connection string** (looks like: `your-redis.redis.cache.windows.net:6380,password=...`)

### Step 2c: Configure App Service

1. Go to your **App Service** → **Configuration** → **Application settings**
2. Click **+ New application setting**
3. Add:
   - **Name:** `REDIS_URL`
   - **Value:** `redis://:password@your-redis.redis.cache.windows.net:6380/0`
     - Replace `password` with the password from Step 2b
     - Replace `your-redis.redis.cache.windows.net` with your Redis hostname
     - The format should be: `redis://:PASSWORD@HOSTNAME:6380/0`
4. Click **Save**
5. **Restart** your App Service

### Step 2d: Verify Redis Connection

After restarting, check your App Service logs. You should see:
```
[SESSION] Redis session storage enabled (distributed sessions)
```

If you see:
```
[SESSION] Using Flask's built-in session storage (works for local and single server cloud)
```

Then Redis is not configured correctly. Check:
- `REDIS_URL` environment variable is set correctly
- Redis cache is running and accessible
- Connection string format is correct

---

## Step 3: Verify Multi-Instance Setup

### Test 1: Check Instance Count

1. Go to **Azure Portal** → Your App Service
2. Navigate to **Metrics**
3. Add metric: **Instance Count**
4. Verify it shows 2 (or your configured number)

### Test 2: Verify Session Persistence

1. Open your application in a browser
2. **Authenticate** and log in
3. **Refresh the page** multiple times
4. You should **stay logged in** (session persists across requests)

If you get logged out on refresh, Redis is not working correctly.

### Test 3: Check Load Distribution

1. Go to **Azure Portal** → Your App Service → **Metrics**
2. Add metrics:
   - **Requests** (total)
   - **Http Server Errors**
3. Generate some traffic to your app
4. Verify requests are being distributed (no errors)

---

## Configuration Summary

### Required Application Settings

```bash
# Redis for distributed sessions (REQUIRED for multiple instances)
REDIS_URL=redis://:password@your-redis.redis.cache.windows.net:6380/0

# Optional but recommended
FLASK_SECRET_KEY=your-secret-key-here
FLASK_ENV=production
```

### Current Application Support

✅ **Already Implemented:**
- Redis session storage support (automatic if `REDIS_URL` is set)
- Fallback to in-memory sessions (for single instance)
- Multi-user session isolation
- Session expiration (24 hours)

---

## Cost Considerations

### Instance Scaling

| Instances | Cost Multiplier | Downtime Risk |
|-----------|----------------|---------------|
| 1 | 1x | High (downtime during upgrades) |
| 2 | 2x | Low (zero downtime) |
| 3+ | 3x+ | Very Low (high availability) |

**Recommendation:** Start with **2 instances** for zero downtime, scale up if needed.

### Redis Cache Pricing

| Tier | Size | Price (approx) | Use Case |
|------|------|----------------|----------|
| Basic C0 | 250 MB | ~$15/month | Testing, low traffic |
| Standard C1 | 1 GB | ~$55/month | Production, moderate traffic |
| Standard C2 | 2.5 GB | ~$110/month | High traffic |

**Recommendation:** Start with **Standard C1** (1 GB) for production.

---

## Troubleshooting

### Issue: Sessions not persisting across instances

**Symptoms:**
- User gets logged out when refreshing
- Session data lost between requests

**Solutions:**
1. Verify `REDIS_URL` is set correctly in App Service Configuration
2. Check Redis cache is running (Azure Portal → Your Redis Cache → Overview)
3. Verify connection string format: `redis://:PASSWORD@HOSTNAME:6380/0`
4. Check App Service logs for Redis connection errors
5. Test Redis connection manually:
   ```bash
   # In Azure Cloud Shell or local terminal
   redis-cli -h your-redis.redis.cache.windows.net -p 6380 -a PASSWORD ping
   # Should return: PONG
   ```

### Issue: High costs with multiple instances

**Solutions:**
1. Use **auto-scaling** instead of fixed instance count
2. Set minimum to 2, maximum to 3-4
3. Scale down during off-peak hours
4. Monitor costs in Azure Cost Management

### Issue: Application errors after scaling

**Solutions:**
1. Check application logs for errors
2. Verify all environment variables are set on all instances
3. Ensure database connections can handle multiple instances
4. Check if any file-based storage needs to be moved to Azure Blob Storage

### Issue: Redis connection timeout

**Solutions:**
1. Ensure Redis cache is in the **same region** as App Service
2. Check Redis firewall rules (allow App Service IPs)
3. Verify Redis cache is not paused/stopped
4. Check Redis cache health in Azure Portal

---

## Best Practices

### 1. Always Use Redis for Multiple Instances

✅ **Do:** Set `REDIS_URL` when scaling to 2+ instances
❌ **Don't:** Use in-memory sessions with multiple instances

### 2. Start Small, Scale as Needed

✅ **Do:** Start with 2 instances, monitor, scale up if needed
❌ **Don't:** Over-provision instances unnecessarily

### 3. Monitor and Optimize

✅ **Do:**
- Monitor instance metrics (CPU, memory, requests)
- Use auto-scaling based on metrics
- Review costs regularly

❌ **Don't:**
- Set instance count too high without monitoring
- Ignore cost implications

### 4. Test Before Production

✅ **Do:**
- Test session persistence after scaling
- Verify zero-downtime during upgrades
- Test failover scenarios

---

## Quick Start Checklist

- [ ] Scale App Service to 2+ instances
- [ ] Create Azure Redis Cache
- [ ] Get Redis connection string
- [ ] Add `REDIS_URL` to App Service Configuration
- [ ] Restart App Service
- [ ] Verify Redis connection in logs
- [ ] Test session persistence
- [ ] Monitor instance metrics
- [ ] Configure auto-scaling (optional)

---

## Additional Resources

- [Azure App Service Scaling](https://learn.microsoft.com/en-us/azure/app-service/manage-scale-up)
- [Azure Cache for Redis](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/)
- [Flask-Session Documentation](https://flask-session.readthedocs.io/)
- [Azure App Service Pricing](https://azure.microsoft.com/en-us/pricing/details/app-service/windows/)

---

## Summary

**Current Status:** ⚠️ Single instance (downtime risk)

**Recommended Action:** 
1. Scale to **2 instances** for zero downtime
2. Set up **Azure Redis Cache** for distributed sessions
3. Configure `REDIS_URL` in App Service settings
4. Test and verify

**Expected Result:** ✅ Zero downtime deployments, high availability, better performance
