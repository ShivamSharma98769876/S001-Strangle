# Database Setup for S001 Strategy

## Overview
This strategy uses database tables prefixed with `s001_` to store trading data. The same database can be used for multiple strategies, with each strategy having its own table prefix.

## Database Tables

All tables are prefixed with `s001_`:

1. **s001_positions** - Active and inactive positions
2. **s001_trades** - Completed trades
3. **s001_daily_stats** - Daily statistics and loss tracking
4. **s001_audit_logs** - Audit trail for critical operations
5. **s001_daily_purge_flags** - Track daily purge operations
6. **s001_candles** - OHLCV candle data

## Configuration

### 1. Database URL
Set the `DATABASE_URL` environment variable or add it to `config/config.json`:

```json
{
  "database_url": "postgresql://user:password@host:port/dbname"
}
```

### 2. Strategy Tag
When placing orders through Kite API, use tag `S001`:

```python
order_id = kite.place_order(
    variety=kite.VARIETY_REGULAR,
    exchange="NFO",
    tradingsymbol="NIFTY25JAN25900PE",
    transaction_type=kite.TRANSACTION_TYPE_SELL,
    quantity=75,
    product=kite.PRODUCT_NRML,
    order_type=kite.ORDER_TYPE_MARKET,
    tag="S001"  # Use S001 tag for this strategy
)
```

### 3. Initialize Database Tables

To create the tables, call the initialization endpoint:

```bash
POST /api/database/init
```

Or programmatically:

```python
from src.database.models import DatabaseManager

db_manager = DatabaseManager()
db_manager.create_tables()
```

## Usage

### Recording Trades

```python
from src.database.models import DatabaseManager
from src.database.repository import TradeRepository

db_manager = DatabaseManager()
trade_repo = TradeRepository(db_manager)
session = db_manager.get_session()

try:
    trade_data = {
        'broker_id': 'your_broker_id',
        'trading_symbol': 'NIFTY25JAN25900PE',
        'exchange': 'NFO',
        'entry_time': datetime.now(),
        'exit_time': datetime.now(),
        'entry_price': 100.0,
        'exit_price': 95.0,
        'quantity': 75,
        'transaction_type': 'SELL',
        'realized_pnl': 375.0,
        'is_profit': True,
        'exit_type': 'manual'
    }
    
    trade = trade_repo.create(session, trade_data)
finally:
    session.close()
```

### Querying Trades

```python
# Get today's trades
trades = trade_repo.get_trades_by_date(session, broker_id, date.today())

# Get all trades
trades = trade_repo.get_all_trades(session, broker_id)

# Get cumulative P&L
pnl = trade_repo.get_cumulative_pnl(session, broker_id, start_date, end_date)
```

## Dashboard Integration

The dashboard automatically uses the `s001_` tables:

- `/api/dashboard/trade-history` - Fetches from `s001_trades`
- `/api/dashboard/cumulative-pnl` - Calculates from `s001_trades`
- `/api/dashboard/status` - Gets daily loss from `s001_daily_stats`

## Notes

- All table names use lowercase `s001_` prefix
- Order tags use uppercase `S001` in Kite API
- The same PostgreSQL database can host multiple strategies (s001, s002, etc.)
- Each strategy's data is isolated by table prefix
