# Session Management Module - Complete Guide

## Overview

The **SaaS Session Management Module** (`SaaSSessionManager`) is a Flask-based session management system designed for multi-tenant SaaS applications. It provides secure, server-side session management that supports multiple users across multiple devices.

## Key Features

✅ **Server-Side Storage**: Credentials stored in Flask session (server-side), never in browser localStorage  
✅ **Multi-Device Support**: Each device/browser gets its own independent session  
✅ **Multi-User Support**: Multiple users can use the application simultaneously  
✅ **Automatic Expiration**: Sessions expire after 24 hours of inactivity  
✅ **Device Identification**: Unique device ID generation for tracking  
✅ **Security**: HTTPOnly cookies, Secure cookies (HTTPS), SameSite protection  
✅ **Modular Design**: Can be easily integrated into other Flask applications  

---

## Architecture

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    User's Browser                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Session Cookie (HttpOnly, Secure)                   │  │
│  │  - Contains session ID only                          │  │
│  │  - No credentials stored                             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ HTTP Request with Cookie
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    Flask Server                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Flask Session (Server-Side)                          │  │
│  │  - api_key                                            │  │
│  │  - api_secret                                         │  │
│  │  - access_token                                       │  │
│  │  - user_id / broker_id                                │  │
│  │  - device_id                                          │  │
│  │  - session expiration                                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SaaSSessionManager                                   │  │
│  │  - store_credentials()                                │  │
│  │  - get_credentials()                                  │  │
│  │  - is_authenticated()                                 │  │
│  │  - clear_credentials()                                │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Multi-User, Multi-Device Support

```
User A - Device 1          User B - Device 1          User A - Device 2
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│ Session Cookie 1│       │ Session Cookie 2│       │ Session Cookie 3│
│ device_id: abc  │       │ device_id: xyz  │       │ device_id: def  │
│ user_id: A      │       │ user_id: B      │       │ user_id: A      │
└─────────────────┘       └─────────────────┘       └─────────────────┘
         │                        │                        │
         └────────────────────────┼────────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │  Flask Server   │
                          │                 │
                          │ Session Store:  │
                          │ - Session 1:    │
                          │   User A, Dev 1 │
                          │ - Session 2:     │
                          │   User B, Dev 1 │
                          │ - Session 3:    │
                          │   User A, Dev 2 │
                          └─────────────────┘
```

**Key Points:**
- Each browser/device gets a unique session cookie
- Each session stores credentials independently
- Same user can have multiple active sessions (multi-device)
- Different users have completely isolated sessions

---

## Module Location

```
src/security/saas_session_manager.py
```

## Installation & Setup

### 1. Copy the Module

Copy `src/security/saas_session_manager.py` to your application's security module.

### 2. Configure Flask Session

In your Flask application initialization:

```python
from flask import Flask
import secrets
import os
from datetime import timedelta

app = Flask(__name__)

# Configure Flask session for SaaS
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'  # HTTPS only in production
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF protection
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # 24 hour sessions

# Optional: Use server-side session storage (Redis, database, etc.)
# from flask_session import Session
# app.config['SESSION_TYPE'] = 'redis'
# Session(app)
```

### 3. Import the Module

```python
from src.security.saas_session_manager import SaaSSessionManager
```

---

## API Reference

### Core Methods

#### `SaaSSessionManager.store_credentials()`

Store credentials in server-side session.

**Parameters:**
- `api_key` (str, required): API key
- `api_secret` (str, required): API secret
- `access_token` (str, required): Access token
- `request_token` (str, optional): Request token
- `user_id` (str, optional): User ID
- `broker_id` (str, optional): Broker ID
- `email` (str, optional): User email
- `full_name` (str, optional): User full name
- `device_id` (str, optional): Device ID (auto-generated if not provided)

**Returns:** None

**Example:**
```python
SaaSSessionManager.store_credentials(
    api_key="UK9394",
    api_secret="secret123",
    access_token="token456",
    user_id="user123",
    broker_id="UK9394",
    email="user@example.com",
    full_name="John Doe"
)
```

---

#### `SaaSSessionManager.get_credentials()`

Get all credentials from server session.

**Returns:** Dict with keys:
- `api_key` (str)
- `api_secret` (str)
- `access_token` (str)
- `request_token` (str)
- `user_id` (str)
- `broker_id` (str)
- `email` (str)
- `full_name` (str)
- `device_id` (str)
- `authenticated` (bool)

**Example:**
```python
creds = SaaSSessionManager.get_credentials()
if creds['authenticated']:
    api_key = creds['api_key']
    access_token = creds['access_token']
```

---

#### `SaaSSessionManager.is_authenticated()`

Check if current session is authenticated and not expired.

**Returns:** bool

**Example:**
```python
if SaaSSessionManager.is_authenticated():
    # User is authenticated
    creds = SaaSSessionManager.get_credentials()
else:
    # User needs to authenticate
    return redirect('/login')
```

---

#### `SaaSSessionManager.clear_credentials()`

Clear all credentials from server session (logout).

**Returns:** None

**Example:**
```python
@app.route('/logout', methods=['POST'])
def logout():
    SaaSSessionManager.clear_credentials()
    return jsonify({"success": True})
```

---

#### `SaaSSessionManager.get_user_id()`

Get user ID from session.

**Returns:** str or None

---

#### `SaaSSessionManager.get_broker_id()`

Get broker ID from session.

**Returns:** str or None

---

#### `SaaSSessionManager.get_access_token()`

Get access token from session.

**Returns:** str or None

---

#### `SaaSSessionManager.get_device_id()`

Get device ID from session.

**Returns:** str or None

---

#### `SaaSSessionManager.extend_session()`

Extend session expiration time by 24 hours.

**Returns:** None

---

#### `SaaSSessionManager.generate_device_id()`

Generate a unique device ID based on MAC address and system info.

**Returns:** str (16-character hex hash)

---

## Complete Integration Example

### Backend (Flask)

```python
from flask import Flask, request, jsonify, session
from src.security.saas_session_manager import SaaSSessionManager
import secrets
import os
from datetime import timedelta

app = Flask(__name__)

# Configure Flask session
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)

# Authentication endpoint
@app.route('/api/auth/authenticate', methods=['POST'])
def authenticate():
    data = request.json
    api_key = data.get('api_key')
    api_secret = data.get('api_secret')
    request_token = data.get('request_token')
    
    # Authenticate with external service (e.g., Zerodha)
    # ... authentication logic ...
    access_token = "obtained_access_token"
    user_id = "user123"
    broker_id = "UK9394"
    
    # Store credentials in server-side session
    SaaSSessionManager.store_credentials(
        api_key=api_key,
        api_secret=api_secret,
        access_token=access_token,
        request_token=request_token,
        user_id=user_id,
        broker_id=broker_id,
        email=data.get('email'),
        full_name=data.get('full_name')
    )
    
    return jsonify({
        "success": True,
        "message": "Authentication successful",
        "device_id": SaaSSessionManager.get_device_id()
    })

# Check authentication status
@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    is_authenticated = SaaSSessionManager.is_authenticated()
    
    if not is_authenticated:
        return jsonify({
            "authenticated": False,
            "message": "Not authenticated"
        })
    
    creds = SaaSSessionManager.get_credentials()
    return jsonify({
        "authenticated": True,
        "user_id": creds.get('user_id'),
        "broker_id": creds.get('broker_id'),
        "device_id": creds.get('device_id'),
        "email": creds.get('email'),
        "full_name": creds.get('full_name')
    })

# Get credentials (for API calls)
@app.route('/api/auth/credentials', methods=['GET'])
def get_credentials():
    if not SaaSSessionManager.is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    
    creds = SaaSSessionManager.get_credentials()
    # Return only non-sensitive info
    return jsonify({
        "user_id": creds.get('user_id'),
        "broker_id": creds.get('broker_id'),
        "has_access_token": bool(creds.get('access_token'))
    })

# Logout endpoint
@app.route('/api/auth/logout', methods=['POST'])
def logout():
    SaaSSessionManager.clear_credentials()
    return jsonify({
        "success": True,
        "message": "Logged out successfully"
    })

# Protected endpoint example
@app.route('/api/user/profile', methods=['GET'])
def get_profile():
    if not SaaSSessionManager.is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    
    user_id = SaaSSessionManager.get_user_id()
    broker_id = SaaSSessionManager.get_broker_id()
    
    # Use credentials for API calls
    creds = SaaSSessionManager.get_credentials()
    # ... make API calls with creds['access_token'] ...
    
    return jsonify({
        "user_id": user_id,
        "broker_id": broker_id
    })

if __name__ == '__main__':
    app.run(debug=True)
```

---

### Frontend (JavaScript)

```javascript
// Authentication
async function authenticate(apiKey, apiSecret, requestToken) {
    const response = await fetch('/api/auth/authenticate', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            api_key: apiKey,
            api_secret: apiSecret,
            request_token: requestToken
        }),
        credentials: 'include'  // Important: Include cookies
    });
    
    const data = await response.json();
    if (data.success) {
        console.log('Authenticated! Device ID:', data.device_id);
        // Credentials are stored in server session automatically
        // No need to store in localStorage
    }
}

// Check authentication status
async function checkAuthStatus() {
    const response = await fetch('/api/auth/status', {
        credentials: 'include'  // Include session cookie
    });
    
    const data = await response.json();
    if (data.authenticated) {
        console.log('User is authenticated:', data.user_id);
        return true;
    } else {
        console.log('User is not authenticated');
        return false;
    }
}

// Logout
async function logout() {
    const response = await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include'
    });
    
    const data = await response.json();
    if (data.success) {
        console.log('Logged out successfully');
        // Redirect to login page
        window.location.href = '/login';
    }
}

// Make authenticated API calls
async function makeAuthenticatedRequest(url, options = {}) {
    // Session cookie is automatically included
    const response = await fetch(url, {
        ...options,
        credentials: 'include'  // Include session cookie
    });
    
    if (response.status === 401) {
        // Not authenticated - redirect to login
        window.location.href = '/login';
        return null;
    }
    
    return response.json();
}
```

---

## Integration Steps for Other Applications

### Step 1: Copy the Module

1. Copy `src/security/saas_session_manager.py` to your application
2. Ensure dependencies are installed:
   ```bash
   pip install flask
   ```

### Step 2: Configure Flask Session

Add to your Flask app initialization:

```python
from flask import Flask
import secrets
import os
from datetime import timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY', secrets.token_hex(32))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)
```

### Step 3: Replace localStorage with Session Manager

**Before (Non-SaaS):**
```python
# ❌ DON'T DO THIS
# Storing credentials in request/response
return jsonify({"access_token": access_token})  # Sent to client
```

**After (SaaS-Compliant):**
```python
# ✅ DO THIS
# Store in server session
SaaSSessionManager.store_credentials(
    api_key=api_key,
    api_secret=api_secret,
    access_token=access_token,
    user_id=user_id
)
# Don't send credentials to client
return jsonify({"success": True})
```

### Step 4: Update Authentication Endpoints

Replace credential storage:
```python
# Old way
session['api_key'] = api_key
session['access_token'] = access_token

# New way
SaaSSessionManager.store_credentials(
    api_key=api_key,
    api_secret=api_secret,
    access_token=access_token,
    user_id=user_id
)
```

### Step 5: Update Protected Endpoints

Add authentication check:
```python
@app.route('/api/protected', methods=['GET'])
def protected_endpoint():
    if not SaaSSessionManager.is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    
    # Get credentials for API calls
    creds = SaaSSessionManager.get_credentials()
    access_token = creds['access_token']
    
    # Use access_token for external API calls
    # ...
```

### Step 6: Update Frontend

Remove localStorage usage:
```javascript
// ❌ Remove this
localStorage.setItem('access_token', token);
const token = localStorage.getItem('access_token');

// ✅ Use this instead
// Credentials are automatically managed by server session
// Just include credentials: 'include' in fetch calls
fetch('/api/endpoint', {
    credentials: 'include'  // Includes session cookie
});
```

---

## Advanced Usage

### Custom Session Storage (Redis/Database)

For production applications, you may want to use Redis or database for session storage:

```python
from flask_session import Session
import redis

app = Flask(__name__)

# Configure Redis session storage
app.config['SESSION_TYPE'] = 'redis'
app.config['SESSION_REDIS'] = redis.from_url('redis://localhost:6379')
app.config['SESSION_PERMANENT'] = True
app.config['SESSION_USE_SIGNER'] = True
app.config['SESSION_KEY_PREFIX'] = 'saas_session:'

Session(app)

# Now SaaSSessionManager will use Redis for session storage
```

### Session Expiration Handling

```python
@app.before_request
def check_session_expiration():
    """Check and extend session on each request"""
    if SaaSSessionManager.is_authenticated():
        # Extend session on activity
        SaaSSessionManager.extend_session()
```

### Multi-Tenant Isolation

```python
@app.route('/api/user/data', methods=['GET'])
def get_user_data():
    if not SaaSSessionManager.is_authenticated():
        return jsonify({"error": "Not authenticated"}), 401
    
    # Get user-specific broker_id from session
    broker_id = SaaSSessionManager.get_broker_id()
    
    # Query database filtered by broker_id (multi-tenant isolation)
    data = db.query.filter_by(broker_id=broker_id).all()
    
    return jsonify({"data": data})
```

---

## Security Best Practices

1. **Always use HTTPS in production**
   ```python
   app.config['SESSION_COOKIE_SECURE'] = True  # HTTPS only
   ```

2. **Use HTTPOnly cookies** (prevents XSS)
   ```python
   app.config['SESSION_COOKIE_HTTPONLY'] = True
   ```

3. **Use SameSite protection** (prevents CSRF)
   ```python
   app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
   ```

4. **Never send credentials to client**
   ```python
   # ❌ DON'T
   return jsonify({"access_token": access_token})
   
   # ✅ DO
   SaaSSessionManager.store_credentials(access_token=access_token)
   return jsonify({"success": True})
   ```

5. **Validate session on every request**
   ```python
   @app.before_request
   def require_auth():
       if request.endpoint not in ['login', 'static']:
           if not SaaSSessionManager.is_authenticated():
               return jsonify({"error": "Not authenticated"}), 401
   ```

---

## Testing

### Test Multi-Device Support

```python
def test_multi_device():
    # Simulate Device 1
    with app.test_client() as client1:
        # Authenticate Device 1
        client1.post('/api/auth/authenticate', json={...})
        assert SaaSSessionManager.is_authenticated() == True
    
    # Simulate Device 2 (different session)
    with app.test_client() as client2:
        # Device 2 should not be authenticated
        assert SaaSSessionManager.is_authenticated() == False
        # Device 2 must authenticate separately
        client2.post('/api/auth/authenticate', json={...})
        assert SaaSSessionManager.is_authenticated() == True
```

### Test Session Expiration

```python
def test_session_expiration():
    # Store credentials
    SaaSSessionManager.store_credentials(...)
    assert SaaSSessionManager.is_authenticated() == True
    
    # Manually expire session
    session[SaaSSessionManager.SESSION_EXPIRES_AT] = (datetime.now() - timedelta(hours=1)).isoformat()
    
    # Should be expired
    assert SaaSSessionManager.is_authenticated() == False
```

---

## Troubleshooting

### Issue: Sessions not persisting

**Solution:** Ensure `session.permanent = True` is set (handled automatically by `store_credentials()`)

### Issue: Credentials accessible in JavaScript

**Solution:** Ensure `SESSION_COOKIE_HTTPONLY = True` is set

### Issue: Sessions work in dev but not production

**Solution:** Ensure `SESSION_COOKIE_SECURE = True` in production (HTTPS required)

### Issue: CORS issues with session cookies

**Solution:** Configure CORS to allow credentials:
```python
from flask_cors import CORS
CORS(app, supports_credentials=True)
```

---

## Benefits

✅ **True Multi-Tenant**: Each user/device has isolated session  
✅ **Security**: Credentials never leave server  
✅ **Scalability**: Works with Redis/database for distributed systems  
✅ **Modular**: Can be integrated into any Flask application  
✅ **Standards-Compliant**: Follows Flask session best practices  
✅ **Production-Ready**: Includes expiration, security headers, etc.  

---

## Summary

The `SaaSSessionManager` module provides a complete, production-ready session management solution for Flask applications. It ensures:

1. **Security**: Credentials stored server-side only
2. **Isolation**: Each user/device has independent session
3. **Scalability**: Works with distributed session storage
4. **Simplicity**: Easy to integrate and use

Simply copy the module, configure Flask session, and replace localStorage with `SaaSSessionManager` methods.

---

## Related Documentation

For **Kite Connection** and how it's **sustained** using session management, see:
- **[KITE_CONNECTION_AND_SESSION_GUIDE.md](KITE_CONNECTION_AND_SESSION_GUIDE.md)** - Complete guide on:
  - How Kite connection is established on dashboard
  - How connection is sustained across requests
  - Session-scoped KiteClient creation pattern
  - Complete authentication flow
  - Frontend and backend integration examples

For **multi-user strategy execution** and how multiple users can run strategies simultaneously:
- **[MULTI_USER_STRATEGY_EXECUTION_GUIDE.md](MULTI_USER_STRATEGY_EXECUTION_GUIDE.md)** - Complete guide on:
  - How strategies are isolated per user session
  - Multiple users running same strategy with different parameters
  - Per-user agent managers and KiteClient instances
  - Database and log file isolation
  - Complete examples and architecture diagrams
