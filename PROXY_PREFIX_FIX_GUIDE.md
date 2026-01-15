# Proxy Prefix Fix Guide (s001/s002)

This guide explains the exact fixes applied to support deployments behind a subpath
like `/s001` or `/s002`, so the same approach can be reused in other apps.

## Problem Summary

When the app is hosted under a subpath (example: `https://domain.com/s001/`), any
frontend call hard-coded to `/api/...` or `/live/...` goes to the root instead of
the prefixed path and returns **404 Not Found**.

## Fix Overview

There are two parts:

1) **Backend (WSGI prefix strip + route matching)**
2) **Frontend (prefix-aware URL builder for all requests)**

---

## 1) Backend Fix (WSGI Prefix Strip)

In `src/ui/dashboard.py`, the app already supports a `APPLICATION_ROOT` or prefix
and strips it in a WSGI middleware before Flask matches routes.

Key behavior:
- If request path starts with `/s001` or `/s002`, the prefix is stripped.
- `SCRIPT_NAME` is set to the prefix so Flask generates correct URLs.

If you deploy a new app under a prefix, ensure this prefix is configured and that
the WSGI middleware is enabled (see logs for `[WSGI] ✅ STRIPPED`).

---

## 2) Frontend Fix (Prefix-Aware API URLs)

Add a base path detector and `apiUrl()` helper in every HTML/JS where you make
network calls. This ensures every request uses the correct prefix.

### Base Path Helper (Reusable)

```javascript
// Detect base path from current URL (e.g., /s001 or /s002)
function getBasePath() {
    const pathname = window.location.pathname;
    const match = pathname.match(/^(\/[^\/]+)/);
    if (match && match[1] !== '/') {
        const basePath = match[1];
        if (basePath.match(/^\/s\d{3}$/)) {
            return basePath;
        }
    }
    return '';
}

const API_BASE_PATH = getBasePath();

function apiUrl(path) {
    const normalizedPath = path.startsWith('/') ? path : '/' + path;
    return API_BASE_PATH + normalizedPath;
}
```

### Replace Hard-Coded Paths

Replace this:
```javascript
fetch('/api/auth/set-access-token', ...)
```

With this:
```javascript
fetch(apiUrl('/api/auth/set-access-token'), ...)
```

This applies to **all** endpoints:
- `/api/*`
- `/live/*`
- `/admin/*`
- `/backtest/*`

### Also Update Downloads / Location Changes

Replace:
```javascript
window.location.href = `/live/logs/download?...`;
```

With:
```javascript
window.location.href = apiUrl(`/live/logs/download?...`);
```

---

## Applied in This Project

### Kite Auth (Dashboard)
- `src/ui/static/js/dashboard.js`
  - All API calls now use `apiUrl(...)`

### Live Trader
- `src/ui/templates/live_trader.html`
  - All `/live/*` calls use `apiUrl(...)`
  - Download URLs use `apiUrl(...)`

### Admin Panel
- `src/ui/templates/admin.html`
  - All `/admin/*` and `/api/*` calls use `apiUrl(...)`
  - Base path helper added inside the script tag

### Backtest
- `src/ui/templates/backtest.html`
  - All `/backtest/*` calls use `apiUrl(...)`
  - Base path helper added inside the script tag

---

## Verification Checklist

- Open DevTools → Network
- Ensure requests go to `/s001/api/...` or `/s001/live/...`
- Confirm server logs show the correct `PATH_INFO` and prefix stripping
- No 404s for API endpoints

---

## If You Use a Different Prefix Format

If your proxy prefix is not `s###` (ex: `/app1`), update the regex in
`getBasePath()`:

```javascript
if (basePath.match(/^\/app1$/)) {
    return basePath;
}
```

Or loosen the detection:
```javascript
if (basePath.length > 1) {
    return basePath;
}
```

---

## Quick Summary

- **Backend**: Strip prefix before Flask routes match
- **Frontend**: Use `apiUrl()` everywhere
- **Result**: All `/api` and `/live` endpoints work under `/s001` or `/s002`

