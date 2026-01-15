# Database Query Analysis - Dashboard

## Summary
This document analyzes all database queries running on the dashboard and their frequencies.

---

## 🔄 **AUTOMATIC/PERIODIC QUERIES** (High Frequency)

### 1. `/api/dashboard/positions` 
**Frequency:** Every **5 seconds** (12 queries/minute, 720 queries/hour)
**Called from:** `config_dashboard.html` - `startAutoRefresh()` function

**Database Queries:**
- `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE`
- **Query Type:** READ
- **Tables:** `s001_positions`
- **Notes:** 
  - Creates new DB session each call
  - If `?sync=true` parameter is passed, also triggers position sync (multiple queries)

**When sync=true (optional):**
- Multiple queries during position sync:
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE` (before sync)
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND instrument_token = ? AND is_active = TRUE` (per position)
  - `INSERT INTO s001_positions ...` or `UPDATE s001_positions ...` (per position)
  - `INSERT INTO s001_trades ...` (when positions close)
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE` (after sync)

---

### 2. `/api/dashboard/metrics`
**Frequency:** Every **5 seconds** (12 queries/minute, 720 queries/hour)
**Called from:** `config_dashboard.html` - `startAutoRefresh()` function

**Database Queries:**
- **NONE** - This endpoint does NOT query database
- **Query Type:** N/A
- **Notes:** 
  - Only queries Zerodha API (kite.orders(), kite.positions())
  - No database queries

---

### 3. `/api/auth/status`
**Frequency:** Every **5 seconds** (12 queries/minute, 720 queries/hour)
**Called from:** `config_dashboard.html` - `setInterval(checkAuthStatus, 5000)`

**Database Queries:**
- **NONE** - This endpoint does NOT query database
- **Query Type:** N/A
- **Notes:** 
  - Only checks session data (in-memory)
  - No database queries

---

### 4. `/api/live-trader/status`
**Frequency:** Every **8 seconds** (7.5 queries/minute, 450 queries/hour)
**Called from:** `live_trader.html` - `setInterval(checkStatus, 8000)`

**Database Queries:**
- **NONE** - This endpoint does NOT query database
- **Query Type:** N/A
- **Notes:** 
  - Only checks in-memory strategy manager state
  - No database queries

---

### 5. `/api/live-trader/logs`
**Frequency:** Every **5 seconds** (12 queries/minute, 720 queries/hour)
**Called from:** `live_trader.html` - `setInterval(loadLogs, 5000)`
**Note:** When strategy is running, frequency increases to every **3 seconds** (20 queries/minute, 1200 queries/hour)

**Database Queries:**
- **NONE** - This endpoint does NOT query database
- **Query Type:** N/A
- **Notes:** 
  - Only reads from in-memory buffer or log files
  - No database queries

---

## 📊 **ON-DEMAND QUERIES** (User-Triggered)

### 6. `/api/dashboard/trade-history`
**Frequency:** On-demand (when user requests trade history)
**Called from:** User interaction (date filter change, page load)

**Database Queries:**
- `SELECT * FROM s001_trades WHERE broker_id = ? AND DATE(exit_time) = ? ORDER BY exit_time DESC`
- OR (if show_all=true): `SELECT * FROM s001_trades WHERE broker_id = ? ORDER BY exit_time DESC LIMIT 1000`
- **Query Type:** READ
- **Tables:** `s001_trades`
- **Frequency:** ~1-5 times per user session

---

### 7. `/api/dashboard/cumulative-pnl`
**Frequency:** On-demand (when user views P&L chart or metrics)
**Called from:** User interaction (chart load, metrics refresh)

**Database Queries:**
- `SELECT SUM(realized_pnl) FROM s001_trades WHERE broker_id = ? AND exit_time >= ? AND exit_time <= ?` (5 queries total)
  - All-time P&L: `exit_time >= '2020-01-01' AND exit_time <= today`
  - Year P&L: `exit_time >= start_of_year AND exit_time <= today`
  - Month P&L: `exit_time >= start_of_month AND exit_time <= today`
  - Week P&L: `exit_time >= start_of_week AND exit_time <= today`
  - Day P&L: `exit_time >= start_of_day AND exit_time <= today`
- **Query Type:** READ (Aggregate)
- **Tables:** `s001_trades`
- **Frequency:** ~1-3 times per user session

---

### 8. `/api/dashboard/status`
**Frequency:** On-demand (when dashboard status is checked)
**Called from:** User interaction or page load

**Database Queries:**
- `SELECT * FROM s001_daily_stats WHERE broker_id = ? AND DATE(date) = ?`
- **Query Type:** READ
- **Tables:** `s001_daily_stats`
- **Frequency:** ~1-2 times per user session

---

### 9. `/api/sync/positions` (POST)
**Frequency:** Manual trigger (user clicks "Sync Positions" button)
**Called from:** User action

**Database Queries:**
- Multiple queries during sync:
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE` (before sync)
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND instrument_token = ? AND is_active = TRUE` (per position check)
  - `INSERT INTO s001_positions ...` (new positions) OR `UPDATE s001_positions ...` (existing positions)
  - `INSERT INTO s001_trades ...` (when positions close)
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE` (after sync)
- **Query Type:** READ + WRITE
- **Tables:** `s001_positions`, `s001_trades`
- **Frequency:** ~1-5 times per day per user

---

### 10. `/api/sync/orders` (POST)
**Frequency:** Manual trigger (user clicks "Sync Orders" button)
**Called from:** User action

**Database Queries:**
- **Position Sync Phase:**
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE` (before sync)
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND instrument_token = ? AND is_active = TRUE` (per position)
  - `UPDATE s001_positions ...` (position updates)
  - `INSERT INTO s001_trades ...` (closed positions)
  - `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE` (after sync - 2 queries)
  
- **Order Sync Phase:**
  - `SELECT * FROM s001_trades WHERE broker_id = ? ORDER BY exit_time DESC LIMIT 1000` (duplicate check)
  - `INSERT INTO s001_trades ...` (per matched trade pair)
  
- **Query Type:** READ + WRITE
- **Tables:** `s001_positions`, `s001_trades`
- **Frequency:** ~1-3 times per day per user

---

### 11. `/api/database/init` (POST)
**Frequency:** One-time setup (when user initializes database)
**Called from:** User action (admin panel)

**Database Queries:**
- `CREATE TABLE IF NOT EXISTS s001_positions ...`
- `CREATE TABLE IF NOT EXISTS s001_trades ...`
- `CREATE TABLE IF NOT EXISTS s001_daily_stats ...`
- `CREATE TABLE IF NOT EXISTS s001_audit_logs ...`
- `CREATE TABLE IF NOT EXISTS s001_daily_purge_flags ...`
- `CREATE TABLE IF NOT EXISTS s001_candles ...`
- **Query Type:** DDL (Data Definition)
- **Tables:** All s001_* tables
- **Frequency:** Once per database setup

---

## 📈 **QUERY FREQUENCY SUMMARY**

### Per Minute (Active Dashboard Session):
| Endpoint | Frequency | DB Queries/Min | Notes |
|----------|-----------|----------------|-------|
| `/api/dashboard/positions` | Every 5s | **12 queries/min** | READ only (unless sync=true) |
| `/api/dashboard/metrics` | Every 5s | **0 queries/min** | No DB queries |
| `/api/auth/status` | Every 5s | **0 queries/min** | No DB queries |
| `/api/live-trader/status` | Every 8s | **0 queries/min** | No DB queries |
| `/api/live-trader/logs` | Every 5s (3s when running) | **0 queries/min** | No DB queries |
| **TOTAL AUTOMATIC** | | **~12 queries/min** | Only positions endpoint |

### Per Hour (Active Dashboard Session):
- **Automatic Queries:** ~720 queries/hour (positions endpoint only)
- **On-Demand Queries:** ~10-50 queries/hour (user interactions)
- **Total:** ~730-770 queries/hour

### Per Day (Active User):
- **Automatic Queries:** ~17,280 queries/day (if dashboard open 24 hours)
- **On-Demand Queries:** ~100-500 queries/day
- **Sync Operations:** ~5-20 queries/day (manual syncs)
- **Total:** ~17,385-17,800 queries/day per active user

---

## 🔍 **QUERY BREAKDOWN BY TABLE**

### `s001_positions` Table:
- **Read Queries:** ~720/hour (from `/api/dashboard/positions`)
- **Write Queries:** ~5-20/hour (from sync operations)
- **Total:** ~725-740 queries/hour

### `s001_trades` Table:
- **Read Queries:** ~10-50/hour (from trade history, cumulative P&L)
- **Write Queries:** ~5-20/hour (from sync operations)
- **Total:** ~15-70 queries/hour

### `s001_daily_stats` Table:
- **Read Queries:** ~1-5/hour (from dashboard status)
- **Write Queries:** ~0-5/hour (from daily stats updates)
- **Total:** ~1-10 queries/hour

---

## ⚠️ **OPTIMIZATION RECOMMENDATIONS**

1. **Cache Positions Query:**
   - Current: 12 queries/minute (every 5 seconds)
   - Recommendation: Add Redis/memory cache with 2-5 second TTL
   - Impact: Reduce to ~12-30 queries/minute (instead of 720/hour)

2. **Batch Cumulative P&L:**
   - Current: 5 separate SUM queries
   - Recommendation: Single query with CASE statements or materialized view
   - Impact: Reduce from 5 queries to 1 query

3. **Connection Pooling:**
   - Ensure proper connection pooling is configured
   - Current: New session per request (may create many connections)

4. **Index Optimization:**
   - Ensure indexes exist on:
     - `s001_positions(broker_id, is_active)`
     - `s001_trades(broker_id, exit_time)`
     - `s001_daily_stats(broker_id, date)`

5. **Reduce Position Query Frequency:**
   - Current: Every 5 seconds
   - Recommendation: Increase to 10-15 seconds for non-critical updates
   - Impact: Reduce queries by 50-66%

---

## 📝 **NOTES**

- Most frequent query: `SELECT * FROM s001_positions WHERE broker_id = ? AND is_active = TRUE`
- No database queries from metrics, auth status, live trader status, or logs endpoints
- All queries are filtered by `broker_id` for multi-tenancy
- Position sync operations can generate 10-50+ queries per sync depending on number of positions
- Order sync operations can generate 20-100+ queries per sync depending on number of orders
