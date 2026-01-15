# Main Application URL Configuration

## Summary
All references to the main application URL now use `StockSage.trade` as the default.

## Main Application URL Configuration

### Location: `src/config_dashboard.py`

**Default URL:** `https://StockSage.trade`

**Implementation:** Centralized function `get_main_app_url()` (line ~391)

```python
def get_main_app_url() -> str:
    """
    Get main application URL from environment variable.
    Defaults to StockSage.trade if not configured.
    """
    main_app_url = os.getenv('MAIN_APP_URL')
    if not main_app_url:
        # Use StockSage.trade as default
        main_app_url = "https://StockSage.trade"
        logger.info(f"[CONFIG] MAIN_APP_URL not set, using default: {main_app_url}")
    return main_app_url
```

## Environment Variable

**Variable Name:** `MAIN_APP_URL`

**Usage:** All code uses `get_main_app_url()` function (no hardcoded URLs)

**Current Behavior:** 
- If `MAIN_APP_URL` environment variable is set, it uses that value
- If not set, defaults to: `https://StockSage.trade`

## Other References

### 1. GitHub Workflow (`.github/workflows/main_a001-strangle.yml`)
- **Line 5:** Workflow name: `Build and deploy Python app to Azure Web App - A001-Strangle`
- **Line 64:** App name: `A001-Strangle`
- **Note:** This is the **current application** (A001-Strangle), not the main application (A000)

### 2. Error Messages (Multiple locations)
References to "main application" in error messages:
- `'JWT token required. Please navigate through main application to authenticate.'`
- `'Please Navigate through {main_app_url}'`
- `'Navigate through main application'`
- `'Invalid session. Access token not found. Please re-authenticate through the main application.'`

### 3. HTML Template (`src/templates/auth_required.html`)
- **Line 97:** `{{ message or 'Navigate through main application' }}`
- **Line 100:** Button text: `Go to Main Application`
- **Note:** Button currently links to `/` (root), not the actual main app URL

## Implementation Status

### ✅ Completed Changes

1. **Centralized URL Configuration**
   - Created `get_main_app_url()` function
   - All code uses this function (no hardcoded URLs)
   - Default set to `https://StockSage.trade`

2. **Updated All References**
   - `require_jwt_token_in_cloud()` - Uses `get_main_app_url()`
   - `require_authentication_page()` - Uses `get_main_app_url()`
   - `check_session_expiration()` - Uses `get_main_app_url()`
   - All error messages use `get_main_app_url()`

3. **HTML Template**
   - `auth_required.html` uses `main_app_url` from template context
   - Button links to main application URL

## Configuration

### Environment Variable (Optional)
Set `MAIN_APP_URL` in Azure Portal > Configuration > Application settings to override default.

**Default:** `https://StockSage.trade` (if not set)

## Files Updated

1. **`src/config_dashboard.py`** - ✅ All hardcoded URLs removed, using `get_main_app_url()`
2. **`src/templates/auth_required.html`** - ✅ Uses `main_app_url` from context
3. **`env_example.txt`** - ✅ Added `MAIN_APP_URL` documentation
