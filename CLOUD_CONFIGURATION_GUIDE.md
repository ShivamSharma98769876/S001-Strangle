# Cloud Configuration Guide

## Overview

This guide provides step-by-step instructions for configuring the application on cloud platforms (Azure, AWS, GCP).

---

## 📋 Required Environment Variables

### 1. **FLASK_SECRET_KEY** (REQUIRED)

**Purpose:** Encrypts session cookies and secures user sessions

**How to Generate:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Example:**
```bash
FLASK_SECRET_KEY="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6"
```

**⚠️ IMPORTANT:**
- Must be a strong, random secret (at least 32 characters)
- Keep this secret secure - never commit to version control
- Use the same secret across all servers if using load balancer

---

### 2. **DATABASE_URL** (REQUIRED)

**Purpose:** PostgreSQL database connection string

**Format:**
```
postgresql://username:password@host:port/database_name
```

**Example:**
```bash
DATABASE_URL="postgresql://myuser:mypassword@db.example.com:5432/trading_db"
```

**⚠️ IMPORTANT:**
- Database must be PostgreSQL (required by the application)
- Ensure database is accessible from your cloud server
- Use SSL connection if available: `postgresql://...?sslmode=require`

---

### 3. **FLASK_ENV** (RECOMMENDED)

**Purpose:** Sets production mode (enables HTTPS cookies, security features)

**Value:**
```bash
FLASK_ENV="production"
```

**What it enables:**
- Secure cookies (HTTPS only)
- Production security settings
- Optimized error handling

---

## 🔧 Optional Environment Variables

### 4. **REDIS_URL** (OPTIONAL - Only for Multi-Server)

**Purpose:** Redis connection for distributed session storage

**When to Use:**
- ✅ Multiple servers behind load balancer
- ✅ Need sessions to persist across server restarts
- ❌ **NOT needed for single server deployment**

**Format:**
```
redis://host:port
# or with password
redis://:password@host:port
```

**Example:**
```bash
REDIS_URL="redis://redis.example.com:6379"
```

**⚠️ Note:** For single cloud server, this is **NOT required**. The system automatically uses Flask's built-in session storage.

---

### 5. **AZURE_BLOB_ACCOUNT_NAME** (OPTIONAL)

**Purpose:** Azure Blob Storage account name for log storage

**Example:**
```bash
AZURE_BLOB_ACCOUNT_NAME="mystorageaccount"
```

---

### 6. **AZURE_BLOB_CONTAINER_NAME** (OPTIONAL)

**Purpose:** Azure Blob Storage container name for logs

**Example:**
```bash
AZURE_BLOB_CONTAINER_NAME="trading-logs"
```

---

### 7. **AZURE_BLOB_STORAGE_KEY** (OPTIONAL)

**Purpose:** Azure Blob Storage access key

**Example:**
```bash
AZURE_BLOB_STORAGE_KEY="your-storage-account-key"
```

**⚠️ Security:** Keep this secret secure - never commit to version control

---

### 8. **AZURE_BLOB_LOGGING_ENABLED** (OPTIONAL)

**Purpose:** Enable/disable Azure Blob Storage logging

**Values:**
```bash
AZURE_BLOB_LOGGING_ENABLED="True"   # Enable
AZURE_BLOB_LOGGING_ENABLED="False"  # Disable (default)
```

---

## ☁️ Platform-Specific Configuration

### Azure App Service

#### Step 1: Set Environment Variables

Go to: **Azure Portal > App Service > Configuration > Application settings**

Add the following:

| Name | Value | Example |
|------|-------|---------|
| `FLASK_SECRET_KEY` | Your generated secret | `a1b2c3d4...` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://...` |
| `FLASK_ENV` | `production` | `production` |
| `AZURE_BLOB_ACCOUNT_NAME` | Storage account name | `mystorageaccount` |
| `AZURE_BLOB_CONTAINER_NAME` | Container name | `trading-logs` |
| `AZURE_BLOB_STORAGE_KEY` | Storage key | `your-key` |
| `AZURE_BLOB_LOGGING_ENABLED` | `True` or `False` | `True` |

#### Step 2: Configure Startup Command

Go to: **Azure Portal > App Service > Configuration > General settings**

**Startup Command (Choose ONE):**

**Option 1 (Recommended - Standard WSGI):**
```bash
gunicorn wsgi:app --bind 0.0.0.0:8000 --timeout 600
```

**Option 2 (Alternative):**
```bash
gunicorn src.config_dashboard:app --bind 0.0.0.0:8000 --timeout 600
```

**⚠️ IMPORTANT:** 
- Do NOT use `gunicorn app:app` - `app.py` is a Streamlit application, not a Flask/WSGI app
- Azure automatically sets `HTTP_PLATFORM_PORT` - the system will auto-detect it
- The `wsgi.py` file provides the standard WSGI entry point for deployment

#### Step 3: Enable HTTPS

Go to: **Azure Portal > App Service > TLS/SSL settings**

- Enable HTTPS
- Configure SSL certificate (Let's Encrypt or custom)

#### Step 4: Verify Configuration

Check application logs:
```
[ENV] Environment detected: PRODUCTION/CLOUD
[SESSION] Using Flask's built-in session storage
```

---

### AWS Elastic Beanstalk

#### Step 1: Create `.ebextensions/01_environment.config`

```yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    FLASK_SECRET_KEY: "your-secret-key-here"
    DATABASE_URL: "postgresql://user:pass@host:port/db"
    FLASK_ENV: "production"
    AZURE_BLOB_ACCOUNT_NAME: "your-account"
    AZURE_BLOB_CONTAINER_NAME: "your-container"
    AZURE_BLOB_STORAGE_KEY: "your-key"
    AZURE_BLOB_LOGGING_ENABLED: "True"
```

#### Step 2: Create `Procfile`

```
web: gunicorn -w 1 -b 0.0.0.0:8000 src.config_dashboard:app
```

#### Step 3: Deploy

```bash
eb init
eb create
eb deploy
```

**Note:** AWS automatically sets `PORT` - the system will auto-detect it.

---

### AWS EC2 (Manual Deployment)

#### Step 1: SSH into EC2 Instance

```bash
ssh -i your-key.pem ec2-user@your-ec2-ip
```

#### Step 2: Set Environment Variables

Create `/etc/environment` or use `.env` file:

```bash
export FLASK_SECRET_KEY="your-secret-key"
export DATABASE_URL="postgresql://user:pass@host:port/db"
export FLASK_ENV="production"
```

#### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

#### Step 4: Run with Gunicorn

```bash
gunicorn -w 1 -b 0.0.0.0:8000 src.config_dashboard:app
```

#### Step 5: Use Systemd (Optional - for auto-start)

Create `/etc/systemd/system/trading-app.service`:

```ini
[Unit]
Description=Trading Dashboard
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/path/to/Strangle10Points
Environment="FLASK_SECRET_KEY=your-secret"
Environment="DATABASE_URL=postgresql://..."
Environment="FLASK_ENV=production"
ExecStart=/usr/local/bin/gunicorn -w 1 -b 0.0.0.0:8000 src.config_dashboard:app

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable trading-app
sudo systemctl start trading-app
```

---

### Google Cloud Platform (GCP)

#### Step 1: Set Environment Variables

Using `gcloud` CLI:

```bash
gcloud app deploy --set-env-vars \
  FLASK_SECRET_KEY="your-secret",\
  DATABASE_URL="postgresql://...",\
  FLASK_ENV="production"
```

Or in `app.yaml`:

```yaml
env_variables:
  FLASK_SECRET_KEY: "your-secret-key"
  DATABASE_URL: "postgresql://user:pass@host:port/db"
  FLASK_ENV: "production"
  AZURE_BLOB_ACCOUNT_NAME: "your-account"
  AZURE_BLOB_CONTAINER_NAME: "your-container"
  AZURE_BLOB_STORAGE_KEY: "your-key"
```

#### Step 2: Deploy

```bash
gcloud app deploy
```

**Note:** GCP automatically sets `PORT` and `GAE_ENV` - the system will auto-detect them.

---

## 🔒 Security Checklist

### Before Deployment

- [ ] **FLASK_SECRET_KEY** is set and is a strong random secret (32+ characters)
- [ ] **DATABASE_URL** uses SSL connection (`?sslmode=require`)
- [ ] **FLASK_ENV** is set to `production`
- [ ] HTTPS is enabled on your cloud platform
- [ ] Environment variables are set securely (not in code)
- [ ] Database credentials are secure
- [ ] Azure Blob Storage keys are secure (if used)

### After Deployment

- [ ] Application starts without errors
- [ ] Logs show: `Environment detected: PRODUCTION/CLOUD`
- [ ] HTTPS is working (check browser shows lock icon)
- [ ] Sessions work (can authenticate)
- [ ] Database connection works
- [ ] Multi-user isolation works (test with 2 users)

---

## 📊 Configuration Summary

### Minimum Required (Single Server)

```bash
FLASK_SECRET_KEY="your-secret-key"
DATABASE_URL="postgresql://user:pass@host:port/db"
FLASK_ENV="production"
```

### Recommended (Single Server)

```bash
FLASK_SECRET_KEY="your-secret-key"
DATABASE_URL="postgresql://user:pass@host:port/db"
FLASK_ENV="production"
AZURE_BLOB_ACCOUNT_NAME="your-account"
AZURE_BLOB_CONTAINER_NAME="your-container"
AZURE_BLOB_STORAGE_KEY="your-key"
AZURE_BLOB_LOGGING_ENABLED="True"
```

### Multi-Server (Load Balanced)

```bash
FLASK_SECRET_KEY="your-secret-key"
DATABASE_URL="postgresql://user:pass@host:port/db"
FLASK_ENV="production"
REDIS_URL="redis://host:port"  # Required for multi-server
AZURE_BLOB_ACCOUNT_NAME="your-account"
AZURE_BLOB_CONTAINER_NAME="your-container"
AZURE_BLOB_STORAGE_KEY="your-key"
AZURE_BLOB_LOGGING_ENABLED="True"
```

---

## 🧪 Verification Steps

### 1. Check Environment Detection

Look for this in application logs:
```
[ENV] Environment detected: PRODUCTION/CLOUD
```

### 2. Check Session Storage

Look for this in application logs:
```
[SESSION] Using Flask's built-in session storage
# or (if Redis is configured)
[SESSION] Redis session storage enabled (distributed sessions)
```

### 3. Test Authentication

1. Open your application URL
2. Click "Authenticate"
3. Enter your Zerodha credentials
4. Verify authentication succeeds
5. Check that session cookie is set (Secure, HttpOnly)

### 4. Test Multi-User Isolation

1. Authenticate as User A
2. Open a different browser (or incognito)
3. Authenticate as User B
4. Verify each user sees only their own data

---

## 🐛 Troubleshooting

### Issue: "Failed to find attribute 'app' in 'app'"

**Error Message:**
```
Failed to find attribute 'app' in 'app'.
[ERROR] Worker (pid:2122) exited with code 4
[ERROR] Reason: App failed to load.
```

**Cause:** Azure App Service is configured to use `gunicorn app:app`, but `app.py` is a Streamlit application, not a Flask/WSGI app.

**Solution:**
1. Go to **Azure Portal > App Service > Configuration > General settings**
2. Update **Startup Command** to:
   ```bash
   gunicorn wsgi:app --bind 0.0.0.0:8000 --timeout 600
   ```
3. Save the configuration
4. Restart the App Service

**Alternative:** If you prefer to use the direct import:
```bash
gunicorn src.config_dashboard:app --bind 0.0.0.0:8000 --timeout 600
```

### Issue: Application doesn't start

**Check:**
- All required environment variables are set
- Database is accessible from cloud server
- Port is available (check cloud platform port configuration)
- Startup command is correct (see above)

### Issue: Sessions not working

**Check:**
- `FLASK_SECRET_KEY` is set
- HTTPS is enabled (required for Secure cookies)
- `FLASK_ENV=production` is set

### Issue: Database connection fails

**Check:**
- `DATABASE_URL` is correct
- Database allows connections from cloud server IP
- Database credentials are correct
- SSL mode is configured if required

### Issue: Logs not appearing in Azure Blob

**Check:**
- `AZURE_BLOB_ACCOUNT_NAME` is set
- `AZURE_BLOB_CONTAINER_NAME` is set
- `AZURE_BLOB_STORAGE_KEY` is correct
- `AZURE_BLOB_LOGGING_ENABLED="True"` is set
- Storage account allows access from cloud server

---

## 📝 Quick Reference

### Environment Variables Table

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `FLASK_SECRET_KEY` | ✅ Yes | Auto-generated | Session encryption |
| `DATABASE_URL` | ✅ Yes | None | PostgreSQL connection |
| `FLASK_ENV` | ⚠️ Recommended | `development` | Production mode |
| `REDIS_URL` | ❌ No | None | Distributed sessions (multi-server only) |
| `AZURE_BLOB_ACCOUNT_NAME` | ❌ No | None | Azure Blob Storage |
| `AZURE_BLOB_CONTAINER_NAME` | ❌ No | None | Azure Blob Storage |
| `AZURE_BLOB_STORAGE_KEY` | ❌ No | None | Azure Blob Storage |
| `AZURE_BLOB_LOGGING_ENABLED` | ❌ No | `False` | Enable Azure logging |

### Auto-Detected Variables (No Configuration Needed)

- `PORT` - Auto-detected from cloud platform
- `HTTP_PLATFORM_PORT` - Auto-detected (Azure)
- `WEBSITE_SITE_NAME` - Auto-detected (Azure)
- `AWS_EXECUTION_ENV` - Auto-detected (AWS)
- `GAE_ENV` - Auto-detected (GCP)

---

## ✅ Summary

**For Single Cloud Server:**
1. Set `FLASK_SECRET_KEY` (required)
2. Set `DATABASE_URL` (required)
3. Set `FLASK_ENV=production` (recommended)
4. Deploy with gunicorn
5. ✅ Done! No Redis needed.

**For Multi-Server (Load Balanced):**
1. Set all single-server variables
2. Set `REDIS_URL` (required)
3. Deploy with gunicorn
4. ✅ Done!

**The system automatically:**
- Detects cloud environment
- Configures HTTPS cookies
- Uses appropriate session storage
- Detects port from environment

**Just set the environment variables and deploy!** 🚀
