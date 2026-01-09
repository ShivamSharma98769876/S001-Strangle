# Environment Setup Guide - Local & Cloud

## Overview

The system automatically detects whether it's running in **local development** or **cloud production** environment and configures itself accordingly. No manual configuration changes needed when switching between environments!

---

## 🔄 Automatic Environment Detection

The system detects the environment based on:

### Local/Development Environment
- No cloud platform indicators detected
- `FLASK_ENV` not set to 'production'
- Uses HTTP (not HTTPS) for session cookies
- Uses Flask's built-in session storage

### Cloud/Production Environment
- Detects Azure (`WEBSITE_SITE_NAME`, `HTTP_PLATFORM_PORT`, `PORT`)
- Detects AWS (`AWS_EXECUTION_ENV`, `LAMBDA_TASK_ROOT`)
- Detects GCP (`GAE_ENV`, `GCLOUD_PROJECT`)
- `FLASK_ENV=production` explicitly set
- Uses HTTPS for session cookies
- Uses Redis if `REDIS_URL` is set, otherwise Flask's built-in storage

---

## 🏠 Local Development Setup

### Quick Start

1. **No environment variables needed for basic setup:**
   ```bash
   # Just run the application
   python src/config_dashboard.py
   # Or
   flask run
   ```

2. **Optional: Set local database (if using database):**
   ```bash
   export DATABASE_URL="postgresql://user:pass@localhost:5432/dbname"
   ```

3. **Optional: Set secret key (recommended):**
   ```bash
   export FLASK_SECRET_KEY="your-local-secret-key"
   ```

### Local Configuration

- ✅ **HTTP** (not HTTPS) - Session cookies work over HTTP
- ✅ **In-memory sessions** - Flask's built-in storage
- ✅ **Port 8080** (default) or from config
- ✅ **No Redis required**
- ✅ **Development-friendly** - Easy debugging

### Local Testing

```bash
# Start application
python src/config_dashboard.py

# Or with Flask
export FLASK_APP=src.config_dashboard
flask run --port 8080

# Access at: http://localhost:8080
```

---

## ☁️ Cloud Deployment Setup

### Quick Start

1. **Set required environment variables:**
   ```bash
   export FLASK_SECRET_KEY="your-production-secret-key"
   export DATABASE_URL="postgresql://user:pass@host:port/db"
   ```

2. **Optional: Set Redis (only if multi-server):**
   ```bash
   export REDIS_URL="redis://your-redis-host:6379"
   ```

3. **Deploy:**
   ```bash
   gunicorn -w 1 -b 0.0.0.0:8080 src.config_dashboard:app
   ```

### Cloud Configuration (Auto-detected)

- ✅ **HTTPS** - Session cookies use Secure flag
- ✅ **Port from environment** - Auto-detects `PORT` or `HTTP_PLATFORM_PORT`
- ✅ **Redis if available** - Uses Redis if `REDIS_URL` is set
- ✅ **Flask sessions if no Redis** - Falls back to Flask's built-in storage
- ✅ **Production-ready** - Secure and optimized

### Cloud Platform Examples

#### Azure App Service
```bash
# Environment variables automatically detected:
# - HTTP_PLATFORM_PORT (auto-set by Azure)
# - WEBSITE_SITE_NAME (auto-set by Azure)

# Just set your variables:
export FLASK_SECRET_KEY="your-secret"
export DATABASE_URL="your-db-url"
```

#### AWS Elastic Beanstalk / EC2
```bash
# Environment variables automatically detected:
# - PORT (auto-set by AWS)

export FLASK_SECRET_KEY="your-secret"
export DATABASE_URL="your-db-url"
export FLASK_ENV="production"  # Optional, but recommended
```

#### Google Cloud Platform
```bash
# Environment variables automatically detected:
# - PORT (auto-set by GCP)
# - GAE_ENV (auto-set by GCP)

export FLASK_SECRET_KEY="your-secret"
export DATABASE_URL="your-db-url"
```

---

## 🔧 Configuration Details

### Session Storage

**Local:**
- Uses Flask's built-in in-memory session storage
- No Redis needed
- Sessions work perfectly for development

**Cloud (Single Server):**
- Uses Flask's built-in in-memory session storage (if no Redis)
- Works perfectly for single server deployments
- No Redis required

**Cloud (Multi-Server):**
- Uses Redis if `REDIS_URL` is set
- Automatically switches to distributed sessions
- Required for load-balanced deployments

### Session Cookies

**Local:**
- `SESSION_COOKIE_SECURE = False` (works over HTTP)
- `SESSION_COOKIE_HTTPONLY = True` (security)
- `SESSION_COOKIE_SAMESITE = 'Lax'` (CSRF protection)

**Cloud:**
- `SESSION_COOKIE_SECURE = True` (HTTPS only)
- `SESSION_COOKIE_HTTPONLY = True` (security)
- `SESSION_COOKIE_SAMESITE = 'Lax'` (CSRF protection)

### Port Configuration

**Local:**
- Default: `8080` (from config)
- Can be overridden: `export DASHBOARD_PORT=3000`

**Cloud:**
- Auto-detects from `PORT` or `HTTP_PLATFORM_PORT`
- No manual configuration needed

---

## 📋 Environment Variables Reference

### Required (Both Environments)

```bash
# Secret key for session encryption
FLASK_SECRET_KEY="your-secret-key"

# Database connection
DATABASE_URL="postgresql://user:pass@host:port/db"
```

### Optional (Cloud Only)

```bash
# Explicitly set production mode
FLASK_ENV="production"

# Redis for distributed sessions (multi-server only)
REDIS_URL="redis://host:port"

# Azure Blob Storage (optional)
AZURE_BLOB_ACCOUNT_NAME="account-name"
AZURE_BLOB_CONTAINER_NAME="container-name"
AZURE_BLOB_STORAGE_KEY="storage-key"
```

### Optional (Local Only)

```bash
# Override default port
DASHBOARD_PORT=3000

# Override default host
DASHBOARD_HOST=127.0.0.1
```

---

## 🧪 Testing Environment Detection

### Check Current Environment

The application logs the detected environment on startup:

```
[ENV] Environment detected: LOCAL/DEVELOPMENT
# or
[ENV] Environment detected: PRODUCTION/CLOUD
```

### Test Local Environment

```bash
# No environment variables needed
python src/config_dashboard.py

# Should see:
# [ENV] Environment detected: LOCAL/DEVELOPMENT
# [SESSION] Using Flask's built-in session storage
```

### Test Cloud Environment

```bash
# Simulate cloud environment
export FLASK_ENV=production
python src/config_dashboard.py

# Should see:
# [ENV] Environment detected: PRODUCTION/CLOUD
# [SESSION] Using Flask's built-in session storage
```

---

## 🔄 Seamless Switching

### From Local to Cloud

1. **Deploy to cloud** (no code changes needed)
2. **Set environment variables** on cloud platform
3. **System auto-detects** cloud environment
4. **Works immediately** - no configuration changes

### From Cloud to Local

1. **Run locally** (no code changes needed)
2. **System auto-detects** local environment
3. **Uses HTTP** instead of HTTPS
4. **Works immediately** - no configuration changes

---

## ✅ Verification Checklist

### Local Environment
- [ ] Application starts without errors
- [ ] Accessible at `http://localhost:8080`
- [ ] Sessions work (can authenticate)
- [ ] No Redis errors in logs
- [ ] Logs show: `Environment detected: LOCAL/DEVELOPMENT`

### Cloud Environment
- [ ] Application starts without errors
- [ ] Accessible via HTTPS
- [ ] Sessions work (can authenticate)
- [ ] Port auto-detected from environment
- [ ] Logs show: `Environment detected: PRODUCTION/CLOUD`
- [ ] Secure cookies enabled (HTTPS)

---

## 🎯 Summary

**The system works seamlessly in both environments:**

✅ **Local Development:**
- No special configuration needed
- HTTP sessions work
- Easy debugging
- Fast development cycle

✅ **Cloud Production:**
- Auto-detects cloud platform
- HTTPS sessions enabled
- Port auto-detected
- Production-ready security

✅ **No Code Changes:**
- Same codebase for both environments
- Automatic environment detection
- Configuration adapts automatically
- Deploy anywhere, works everywhere

**Just set environment variables and deploy!** 🚀
