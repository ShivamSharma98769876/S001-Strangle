# Cumulative P&L Labels Fix Report

## Issue
The Cumulative Profit & Loss widget was displaying hardcoded labels:
- **Year (2025)** instead of current year (2026)
- **Month (Dec)** instead of current month (Jan)

The backend was correctly calculating P&L for the current year and month, but the frontend labels were hardcoded and not updating dynamically.

## Root Cause
The HTML template had hardcoded labels:
```html
<div class="metric-label" id="label-year">Year (2025)</div>
<div class="metric-label" id="label-month">Month (Dec)</div>
```

These labels were never updated by JavaScript, so they always showed the initial hardcoded values.

## Solution

### 1. Backend Changes (`src/config_dashboard.py`)
Updated the `/api/dashboard/cumulative-pnl` endpoint to return current year and month information:

```python
# Get month name for display
month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
current_month_name = month_names[today.month - 1]

return jsonify({
    'status': 'success',
    'all_time': all_time_pnl,
    'year': year_pnl,
    'month': month_pnl,
    'week': week_pnl,
    'day': day_pnl,
    'current_year': today.year,      # ✅ Added
    'current_month': current_month_name  # ✅ Added
})
```

### 2. Frontend HTML Changes (`src/templates/config_dashboard.html`)
Removed hardcoded year and month from labels:

**Before:**
```html
<div class="metric-label" id="label-year">Year (2025)</div>
<div class="metric-label" id="label-month">Month (Dec)</div>
```

**After:**
```html
<div class="metric-label" id="label-year">Year</div>
<div class="metric-label" id="label-month">Month</div>
```

### 3. Frontend JavaScript Changes (`src/static/js/dashboard.js`)
Updated two functions to dynamically set year and month labels:

#### `updateCumulativePnlMetrics()` function:
```javascript
// Update year and month labels dynamically
if (data.current_year) {
    const yearLabelEl = document.getElementById('label-year');
    if (yearLabelEl) {
        yearLabelEl.textContent = `Year (${data.current_year})`;
    }
}

if (data.current_month) {
    const monthLabelEl = document.getElementById('label-month');
    if (monthLabelEl) {
        monthLabelEl.textContent = `Month (${data.current_month})`;
    }
}
```

#### `updateCumulativePnl()` function:
Added the same label update logic to ensure labels are updated when data is refreshed.

## Files Modified

1. **`src/config_dashboard.py`** (lines ~1892-1916)
   - Added `current_year` and `current_month` to API response

2. **`src/templates/config_dashboard.html`** (lines ~1239, 1244)
   - Removed hardcoded "(2025)" and "(Dec)" from labels

3. **`src/static/js/dashboard.js`** (lines ~753-769, ~1229-1237)
   - Added dynamic label updates in `updateCumulativePnlMetrics()`
   - Added dynamic label updates in `updateCumulativePnl()`

## Expected Behavior

### Before Fix:
- ❌ Always showed "Year (2025)" regardless of current year
- ❌ Always showed "Month (Dec)" regardless of current month
- ✅ P&L values were correct for current period

### After Fix:
- ✅ Shows "Year (2026)" for current year (2026)
- ✅ Shows "Month (Jan)" for current month (January)
- ✅ Labels automatically update when year/month changes
- ✅ P&L values remain correct for current period

## Testing

To verify the fix:

1. **Check API Response:**
   - Call `/api/dashboard/cumulative-pnl`
   - Verify response includes `current_year: 2026` and `current_month: "Jan"`

2. **Check Frontend Display:**
   - Open dashboard
   - Verify Cumulative P&L widget shows:
     - "Year (2026)" instead of "Year (2025)"
     - "Month (Jan)" instead of "Month (Dec)"

3. **Test Dynamic Updates:**
   - Wait for next month (or manually change system date for testing)
   - Verify labels update automatically when month changes

## Status

✅ **Fixed**: Labels now dynamically display current year and month, matching the actual P&L data being shown.
