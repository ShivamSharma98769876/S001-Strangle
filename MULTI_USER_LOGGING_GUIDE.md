# Multi-User Logging Guide

## Overview

This guide explains how logs are maintained and isolated for multiple users in the system.

---

## Current Logging Architecture

### Log Isolation Strategy

**Per-User Log Files:**
- Each user's logs are stored in separate files based on `broker_id`
- Log files are named: `{broker_id}_{date}.log`
- Complete isolation between users

**Log Storage Locations:**

**Local Environment:**
```
src/logs/
  ├── UK9394_2026Jan09.log    (User A - broker_id: UK9394)
  ├── UK1234_2026Jan09.log    (User B - broker_id: UK1234)
  └── dashboard.log            (Dashboard system logs)
```

**Cloud Environment (Azure):**
```
/tmp/{broker_id}/logs/
  ├── UK9394/
  │   └── logs/
  │       └── UK9394_2026Jan09.log
  └── UK1234/
      └── logs/
          └── UK1234_2026Jan09.log
```

**Azure Blob Storage:**
```
Container: str-container1
  ├── UK9394/
  │   └── logs/
  │       └── UK9394_2026Jan09.log
  └── UK1234/
      └── logs/
          └── UK1234_2026Jan09.log
```

---

## Log Types

### 1. Dashboard Logs

**File:** `dashboard.log` (shared, but entries include broker_id)

**Content:**
- Dashboard startup/shutdown
- Authentication events (with broker_id)
- API requests (with broker_id)
- System-level events

**Isolation:**
- Log entries include `broker_id` in the message
- Example: `[AUTH] User authenticated - broker_id: UK9394`

### 2. Strategy Execution Logs

**File:** `{broker_id}_{date}.log`

**Content:**
- Strategy execution logs
- Trade execution logs
- Position management logs
- Error logs specific to user

**Isolation:**
- Separate file per user (broker_id)
- Complete isolation

### 3. Azure Blob Storage Logs

**Path:** `{broker_id}/logs/{broker_id}_{date}.log`

**Content:**
- Same as strategy logs
- Uploaded to Azure Blob Storage
- Persistent across server restarts

**Isolation:**
- Separate folder per user (broker_id)
- Complete isolation

---

## Implementation Details

### Log File Naming

**Format:** `{broker_id}_{YYYYMONDD}.log`

**Examples:**
- `UK9394_2026Jan09.log` - User A's logs for Jan 9, 2026
- `UK1234_2026Jan09.log` - User B's logs for Jan 9, 2026

### Log Entry Format

**Standard Format:**
```
{timestamp} - {logger_name} - {level} - [broker_id: {broker_id}] {message}
```

**Example:**
```
2026-01-09 10:30:45 - trading_bot - INFO - [broker_id: UK9394] Position opened: NIFTY25JAN25900PE
2026-01-09 10:30:46 - trading_bot - INFO - [broker_id: UK1234] Position opened: NIFTY25JAN25900PE
```

### Log Context

All log entries should include `broker_id` for proper isolation:

```python
# Get broker_id from session
broker_id = SaaSSessionManager.get_broker_id()

# Log with broker_id context
logger.info(f"[broker_id: {broker_id}] User action: {action}")
```

---

## Log Retrieval

### Dashboard Logs

**Endpoint:** `/api/live-trader/logs`

**Behavior:**
1. Gets `broker_id` from current session
2. Looks for log file: `{broker_id}_{date}.log`
3. Returns only that user's logs
4. Complete isolation - users cannot see each other's logs

### Log File Location

**Local:**
- `src/logs/{broker_id}_{date}.log`

**Cloud (Azure):**
- `/tmp/{broker_id}/logs/{broker_id}_{date}.log`

**Azure Blob:**
- `{broker_id}/logs/{broker_id}_{date}.log`

---

## Multi-User Log Isolation

### Scenario: 3 Users Running Strategies

**User A (broker_id: UK9394):**
- Log file: `UK9394_2026Jan09.log`
- Location: `src/logs/UK9394_2026Jan09.log` (local)
- Azure Blob: `UK9394/logs/UK9394_2026Jan09.log`

**User B (broker_id: UK1234):**
- Log file: `UK1234_2026Jan09.log`
- Location: `src/logs/UK1234_2026Jan09.log` (local)
- Azure Blob: `UK1234/logs/UK1234_2026Jan09.log`

**User C (broker_id: UK5678):**
- Log file: `UK5678_2026Jan09.log`
- Location: `src/logs/UK5678_2026Jan09.log` (local)
- Azure Blob: `UK5678/logs/UK5678_2026Jan09.log`

**Result:**
- ✅ Complete isolation - each user has separate log files
- ✅ No data leakage between users
- ✅ Easy to identify which user's logs you're viewing

---

## Logging Best Practices

### 1. Always Include broker_id

```python
# ✅ Good
broker_id = SaaSSessionManager.get_broker_id()
logger.info(f"[broker_id: {broker_id}] Trade executed: {trade_id}")

# ❌ Bad (no broker_id context)
logger.info(f"Trade executed: {trade_id}")
```

### 2. Use Session Context

```python
# Get broker_id from session
broker_id = SaaSSessionManager.get_broker_id()
if broker_id:
    logger.info(f"[broker_id: {broker_id}] Action performed")
else:
    logger.warning("Action performed without broker_id context")
```

### 3. Log File Naming

```python
# Use broker_id for log file naming
broker_id = SaaSSessionManager.get_broker_id()
log_file = f"{broker_id}_{date_str}.log"
```

---

## Log Cleanup

### Automatic Cleanup

Logs are organized by date, making cleanup easy:

```bash
# Remove logs older than 30 days
find src/logs -name "*.log" -mtime +30 -delete
```

### Per-User Cleanup

```bash
# Remove logs for specific user older than 30 days
find src/logs -name "UK9394_*.log" -mtime +30 -delete
```

---

## Log Access Control

### Dashboard Log Retrieval

**Endpoint:** `/api/live-trader/logs`

**Security:**
- Gets `broker_id` from current session
- Only returns logs for that `broker_id`
- Users cannot access other users' logs

**Implementation:**
```python
@app.route('/api/live-trader/logs')
def get_live_trader_logs():
    # Get broker_id from session
    broker_id = SaaSSessionManager.get_broker_id()
    
    # Only return logs for this user
    log_file = f"{broker_id}_{date}.log"
    # ... read and return logs
```

---

## Summary

**Log Isolation:**
- ✅ Separate log files per user (broker_id)
- ✅ Separate directories per user (cloud)
- ✅ Separate Azure Blob folders per user
- ✅ Log entries include broker_id context

**Log Retrieval:**
- ✅ Users can only see their own logs
- ✅ Log retrieval filtered by session broker_id
- ✅ Complete isolation between users

**Log Storage:**
- ✅ Local: `src/logs/{broker_id}_{date}.log`
- ✅ Cloud: `/tmp/{broker_id}/logs/{broker_id}_{date}.log`
- ✅ Azure Blob: `{broker_id}/logs/{broker_id}_{date}.log`

**Multi-User Support:**
- ✅ Each user has isolated log files
- ✅ No data leakage between users
- ✅ Easy to identify and manage per-user logs
