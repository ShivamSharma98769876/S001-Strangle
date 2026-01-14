"""
Order History Synchronization
Syncs completed orders from Zerodha and creates trade records
Adapted from disciplined-Trader for Strangle10Points strategy
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, date
import logging
from src.kite_client import KiteClient
from src.database.repository import TradeRepository, PositionRepository
from pytz import UTC

logger = logging.getLogger(__name__)

# IST timezone for date operations
try:
    from src.utils.date_utils import IST, get_current_ist_time
except ImportError:
    # Fallback: Use pytz for IST timezone (required for localize() method)
    from pytz import timezone as pytz_timezone
    IST = pytz_timezone('Asia/Kolkata')
    def get_current_ist_time():
        return datetime.now(IST)


class OrderSync:
    """Synchronizes order history from Zerodha and creates trade records"""
    
    def __init__(self, kite_client: KiteClient, trade_repo: TradeRepository, position_repo: PositionRepository):
        self.kite_client = kite_client
        self.trade_repo = trade_repo
        self.position_repo = position_repo
    
    def sync_orders_to_trades(self, broker_id: str, target_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """
        Fetch orders from Zerodha and create trade records for completed options orders
        
        Args:
            broker_id: Broker ID for filtering trades
            target_date: Optional date to filter orders (default: today in IST)
        
        Returns:
            List of created trade records
        """
        if not hasattr(self.kite_client, 'kite') or not self.kite_client.kite:
            logger.warning("Kite client not authenticated - cannot sync orders")
            return []
        
        try:
            # Default to today's date in IST if not specified
            if target_date is None:
                target_date = get_current_ist_time().date()
                logger.info(f"No target date specified, using today's date: {target_date}")
            
            # Get all orders from Zerodha
            try:
                all_orders = self.kite_client.kite.orders()
            except Exception as e:
                logger.error(f"Error fetching orders from Zerodha: {e}")
                return []
            
            logger.info(f"Fetched {len(all_orders)} orders from Zerodha, filtering for date: {target_date}")
            
            # Filter for non-equity orders - include COMPLETE and REJECTED orders
            # (REJECTED might have partial fills, COMPLETE are fully filled)
            # Exclude equity orders (NSE, BSE)
            non_equity_orders = []
            skipped_count = 0
            for order in all_orders:
                # Check order status - include COMPLETE and partially filled orders
                status = order.get('status', '').upper()
                # Skip only CANCELLED and PENDING orders
                if status in ['CANCELLED', 'PENDING', 'OPEN', 'TRIGGER PENDING']:
                    skipped_count += 1
                    continue
                
                # Include COMPLETE, REJECTED (might have fills), and other statuses with fills
                filled_qty = order.get('filled_quantity', 0)
                if filled_qty == 0 and status != 'COMPLETE':
                    skipped_count += 1
                    continue
                
                # Exclude equity orders (NSE, BSE)
                exchange = order.get('exchange', '').upper()
                
                if self._should_exclude_equity(exchange):
                    skipped_count += 1
                    continue
                
                # Filter by date - Zerodha timestamps are in IST
                order_time_str = order.get('order_timestamp', '')
                if order_time_str:
                    try:
                        # Handle both string and datetime objects
                        if isinstance(order_time_str, datetime):
                            order_time = order_time_str
                        else:
                            # Parse order timestamp - Zerodha format: "YYYY-MM-DD HH:MM:SS" (IST)
                            # Try multiple formats
                            order_time = None
                            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%d-%m-%Y %H:%M:%S']:
                                try:
                                    order_time = datetime.strptime(str(order_time_str), fmt)
                                    break
                                except ValueError:
                                    continue
                            
                            if order_time is None:
                                logger.warning(f"Could not parse order timestamp: {order_time_str}")
                                skipped_count += 1
                                continue
                        
                        # Zerodha timestamps are timezone-naive, assume IST
                        # Convert to IST timezone-aware datetime
                        if order_time.tzinfo is None:
                            order_time = IST.localize(order_time)
                        else:
                            order_time = order_time.astimezone(IST)
                        
                        # Compare dates in IST
                        order_date_ist = order_time.date()
                        if order_date_ist != target_date:
                            logger.debug(
                                f"Order {order.get('order_id')} date {order_date_ist} != target {target_date}, "
                                f"time: {order_time_str} -> {order_time}"
                            )
                            skipped_count += 1
                            continue
                        
                        logger.debug(
                            f"Including order {order.get('order_id')} at {order_time_str} "
                            f"(IST: {order_time}) for date {target_date}"
                        )
                    except Exception as e:
                        logger.warning(f"Error parsing order timestamp {order_time_str}: {e}")
                        skipped_count += 1
                        continue
                else:
                    # No timestamp - skip this order
                    logger.warning(f"Order {order.get('order_id')} has no timestamp, skipping")
                    skipped_count += 1
                    continue
                
                non_equity_orders.append(order)
            
            logger.info(
                f"Found {len(non_equity_orders)} completed non-equity orders for {target_date} "
                f"(skipped {skipped_count} orders)"
            )
            
            # Group orders by instrument and match BUY/SELL pairs
            # For each instrument, we need to match BUY and SELL orders
            created_trades = []
            processed_order_ids = set()
            
            # Track unmatched orders across all symbols
            total_unmatched_buys = 0
            total_unmatched_sells = 0
            
            # Group orders by trading symbol
            orders_by_symbol: Dict[str, List[Dict]] = {}
            for order in non_equity_orders:
                symbol = order.get('tradingsymbol', '')
                if symbol not in orders_by_symbol:
                    orders_by_symbol[symbol] = []
                orders_by_symbol[symbol].append(order)
            
            # Process each symbol's orders using FIFO matching
            for symbol, symbol_orders in orders_by_symbol.items():
                # Sort by timestamp
                symbol_orders.sort(key=lambda x: x.get('order_timestamp', ''))
                
                # Log symbol processing
                buy_count = sum(1 for o in symbol_orders if o.get('transaction_type', '').upper() == 'BUY')
                sell_count = sum(1 for o in symbol_orders if o.get('transaction_type', '').upper() == 'SELL')
                logger.info(f"Processing {symbol}: {len(symbol_orders)} orders ({buy_count} BUY, {sell_count} SELL)")
                
                # Use FIFO queue approach: track pending BUY and SELL orders
                pending_buys = []  # List of (order, remaining_qty)
                pending_sells = []  # List of (order, remaining_qty)
                
                for order in symbol_orders:
                    order_id = order.get('order_id')
                    if order_id in processed_order_ids:
                        continue
                    
                    transaction_type = order.get('transaction_type', '').upper()
                    filled_qty = order.get('filled_quantity', 0)
                    
                    if transaction_type == 'BUY':
                        # Try to match with pending SELL orders (short covering)
                        remaining_qty = filled_qty
                        matched_qty = 0  # Track how much was matched
                        while remaining_qty > 0 and pending_sells:
                            sell_order, sell_remaining = pending_sells[0]
                            
                            # Match quantity
                            match_qty = min(remaining_qty, sell_remaining)
                            matched_qty += match_qty  # Accumulate matched quantity
                            
                            # Create trade record
                            trade = self._create_trade_from_orders_partial(
                                broker_id, sell_order, order, match_qty, is_short=True
                            )
                            if trade:
                                created_trades.append(trade)
                            
                            # Update remaining quantities
                            remaining_qty -= match_qty
                            sell_remaining -= match_qty
                            
                            if sell_remaining == 0:
                                pending_sells.pop(0)
                                processed_order_ids.add(sell_order.get('order_id'))
                            else:
                                pending_sells[0] = (sell_order, sell_remaining)
                        
                        # Add remaining to pending BUYs (only if not fully matched)
                        if remaining_qty > 0:
                            pending_buys.append((order, remaining_qty))
                            logger.debug(f"  BUY order {order_id} partially matched: {matched_qty} matched, {remaining_qty} pending")
                        elif remaining_qty == 0 and filled_qty > 0:
                            # Fully matched, mark as processed
                            processed_order_ids.add(order_id)
                            logger.debug(f"  BUY order {order_id} fully matched")
                    
                    elif transaction_type == 'SELL':
                        # Try to match with pending BUY orders (long exit)
                        remaining_qty = filled_qty
                        matched_qty = 0  # Track how much was matched
                        while remaining_qty > 0 and pending_buys:
                            buy_order, buy_remaining = pending_buys[0]
                            
                            # Match quantity
                            match_qty = min(remaining_qty, buy_remaining)
                            matched_qty += match_qty  # Accumulate matched quantity
                            
                            # Create trade record
                            trade = self._create_trade_from_orders_partial(
                                broker_id, buy_order, order, match_qty, is_short=False
                            )
                            if trade:
                                created_trades.append(trade)
                            
                            # Update remaining quantities
                            remaining_qty -= match_qty
                            buy_remaining -= match_qty
                            
                            if buy_remaining == 0:
                                pending_buys.pop(0)
                                processed_order_ids.add(buy_order.get('order_id'))
                            else:
                                pending_buys[0] = (buy_order, buy_remaining)
                        
                        # Add remaining to pending SELLs (short positions)
                        if remaining_qty > 0:
                            pending_sells.append((order, remaining_qty))
                            logger.debug(f"  SELL order {order_id} partially matched: {matched_qty} matched, {remaining_qty} pending")
                        elif remaining_qty == 0 and filled_qty > 0:
                            # Fully matched, mark as processed
                            processed_order_ids.add(order_id)
                            logger.debug(f"  SELL order {order_id} fully matched")
                
                # Track unmatched orders for this symbol
                symbol_unmatched_buys = len(pending_buys)
                symbol_unmatched_sells = len(pending_sells)
                total_unmatched_buys += symbol_unmatched_buys
                total_unmatched_sells += symbol_unmatched_sells
                
                if symbol_unmatched_buys > 0 or symbol_unmatched_sells > 0:
                    logger.info(f"  {symbol}: {symbol_unmatched_buys} unmatched BUY, {symbol_unmatched_sells} unmatched SELL")
            
            # Log unmatched orders summary
            if total_unmatched_buys > 0 or total_unmatched_sells > 0:
                logger.warning(
                    f"⚠️ Unmatched orders after processing: {total_unmatched_buys} BUY orders, {total_unmatched_sells} SELL orders. "
                    f"These need matching pairs to create trades."
                )
            
            logger.info(f"✅ Created {len(created_trades)} trade records from orders")
            
            # Log summary of what happened
            if len(created_trades) == 0:
                logger.warning(
                    f"⚠️ No trades created! Summary:\n"
                    f"  - Total orders fetched: {len(all_orders)}\n"
                    f"  - Non-equity orders: {len(non_equity_orders)}\n"
                    f"  - Orders for target date ({target_date}): {len(non_equity_orders)}\n"
                    f"  - Unmatched BUY orders: {total_unmatched_buys}\n"
                    f"  - Unmatched SELL orders: {total_unmatched_sells}\n"
                    f"  - Possible reasons:\n"
                    f"    * Orders need BUY/SELL pairs to create trades\n"
                    f"    * All orders already matched (duplicates)\n"
                    f"    * Orders filtered out (wrong date, status, etc.)\n"
                    f"    * BrokerID not set (required for INSERT)"
                )
                
                # Log symbol breakdown for debugging
                for symbol, symbol_orders in orders_by_symbol.items():
                    buy_count = sum(1 for o in symbol_orders if o.get('transaction_type', '').upper() == 'BUY')
                    sell_count = sum(1 for o in symbol_orders if o.get('transaction_type', '').upper() == 'SELL')
                    logger.info(f"  Symbol {symbol}: {len(symbol_orders)} orders ({buy_count} BUY, {sell_count} SELL)")
            else:
                logger.info(f"✅ Successfully inserted {len(created_trades)} trades into database")
            
            return created_trades
            
        except Exception as e:
            logger.error(f"Error syncing orders to trades: {e}", exc_info=True)
            return []
    
    def _create_trade_from_orders_partial(
        self,
        broker_id: str,
        entry_order: Dict[str, Any],
        exit_order: Dict[str, Any],
        quantity: int,
        is_short: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Create a trade record from matched orders with partial quantity
        
        Args:
            broker_id: Broker ID for the trade
            entry_order: Entry order
            exit_order: Exit order
            quantity: Quantity to match
            is_short: True if this is a short position
        
        Returns:
            Created trade record dict or None
        """
        try:
            # Use the same prices from orders (average price)
            entry_price = float(entry_order.get('average_price', 0))
            exit_price = float(exit_order.get('average_price', 0))
            
            if entry_price == 0 or exit_price == 0:
                return None
            
            # Determine transaction type and quantity sign
            if is_short:
                transaction_type = 'SELL'
                qty = -abs(quantity)  # Negative for SELL
            else:
                transaction_type = 'BUY'
                qty = abs(quantity)  # Positive for BUY
            
            # Parse timestamps - Zerodha returns in IST
            entry_time_str = entry_order.get('order_timestamp', '')
            exit_time_str = exit_order.get('order_timestamp', '')
            
            try:
                # Handle both string and datetime objects
                if isinstance(entry_time_str, datetime):
                    entry_time = entry_time_str
                else:
                    # Parse timestamp
                    entry_time = None
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%d-%m-%Y %H:%M:%S']:
                        try:
                            entry_time = datetime.strptime(str(entry_time_str), fmt)
                            break
                        except ValueError:
                            continue
                    
                    if entry_time is None:
                        entry_time = get_current_ist_time()
                
                if entry_time.tzinfo is None:
                    entry_time = IST.localize(entry_time)
                else:
                    entry_time = entry_time.astimezone(IST)
            except Exception as e:
                logger.warning(f"Error parsing entry_time {entry_time_str}: {e}")
                entry_time = get_current_ist_time()
            
            try:
                # Handle both string and datetime objects
                if isinstance(exit_time_str, datetime):
                    exit_time = exit_time_str
                else:
                    # Parse timestamp
                    exit_time = None
                    for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%d-%m-%Y %H:%M:%S']:
                        try:
                            exit_time = datetime.strptime(str(exit_time_str), fmt)
                            break
                        except ValueError:
                            continue
                    
                    if exit_time is None:
                        exit_time = get_current_ist_time()
                
                if exit_time.tzinfo is None:
                    exit_time = IST.localize(exit_time)
                else:
                    exit_time = exit_time.astimezone(IST)
            except Exception as e:
                logger.warning(f"Error parsing exit_time {exit_time_str}: {e}")
                exit_time = get_current_ist_time()
            
            # Get instrument details
            trading_symbol = entry_order.get('tradingsymbol', '')
            exchange = entry_order.get('exchange', '')
            instrument_token = str(entry_order.get('instrument_token', ''))
            
            # Check if trade already exists (avoid duplicates)
            try:
                session = self.trade_repo.db_manager.get_session()
                try:
                    existing_trades = self.trade_repo.get_all_trades(session, broker_id, limit=1000)
                    for existing in existing_trades:
                        # Normalize timezones for comparison
                        existing_entry = existing.entry_time
                        existing_exit = existing.exit_time
                        
                        # Convert to IST if timezone-aware, or assume IST if naive
                        if existing_entry.tzinfo is None:
                            existing_entry = IST.localize(existing_entry)
                        else:
                            existing_entry = existing_entry.astimezone(IST)
                        
                        if existing_exit.tzinfo is None:
                            existing_exit = IST.localize(existing_exit)
                        else:
                            existing_exit = existing_exit.astimezone(IST)
                        
                        # Normalize new trade times to IST
                        if entry_time.tzinfo is None:
                            entry_time_normalized = IST.localize(entry_time)
                        else:
                            entry_time_normalized = entry_time.astimezone(IST)
                        
                        if exit_time.tzinfo is None:
                            exit_time_normalized = IST.localize(exit_time)
                        else:
                            exit_time_normalized = exit_time.astimezone(IST)
                        
                        if (existing.trading_symbol == trading_symbol and
                            abs((existing_entry - entry_time_normalized).total_seconds()) < 60 and
                            abs((existing_exit - exit_time_normalized).total_seconds()) < 60 and
                            abs(existing.entry_price - entry_price) < 0.01 and
                            abs(existing.exit_price - exit_price) < 0.01 and
                            abs(existing.quantity) == abs(qty)):
                            logger.info(f"⚠️ Trade already exists for {trading_symbol} at {entry_time_normalized} - skipping INSERT")
                            logger.debug(f"Existing trade: {existing.trading_symbol} | Entry: {existing_entry} | Exit: {existing_exit} | P&L: {existing.realized_pnl}")
                            return None
                finally:
                    session.close()
            except Exception as dup_check_error:
                logger.warning(f"Error checking for duplicate trades: {dup_check_error} - proceeding with trade creation")
            
            # Calculate realized P&L
            if transaction_type == 'SELL':
                # For SELL trades, profit when entry > exit
                realized_pnl = (entry_price - exit_price) * abs(qty)
            else:
                # For BUY trades, profit when exit > entry
                realized_pnl = (exit_price - entry_price) * qty
            
            # Create trade record
            try:
                trade_data = {
                    'broker_id': broker_id,
                    'instrument_token': instrument_token,
                    'trading_symbol': trading_symbol,
                    'exchange': exchange,
                    'entry_time': entry_time.replace(tzinfo=None),  # Store as naive UTC
                    'exit_time': exit_time.replace(tzinfo=None),  # Store as naive UTC
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'quantity': qty,
                    'exit_type': 'manual',
                    'transaction_type': transaction_type,
                    'realized_pnl': realized_pnl,
                    'is_profit': realized_pnl > 0
                }
                
                session = self.trade_repo.db_manager.get_session()
                try:
                    trade = self.trade_repo.create(session, trade_data)
                    
                    logger.info(
                        f"✅ INSERTED trade record: {trading_symbol} | "
                        f"{transaction_type} {abs(qty)} @ {entry_price} -> {exit_price} | "
                        f"P&L: ₹{trade.realized_pnl:.2f} | Trade ID: {trade.id}"
                    )
                    
                    return {
                        "id": trade.id,
                        "trading_symbol": trading_symbol,
                        "transaction_type": transaction_type,
                        "quantity": qty,
                        "realized_pnl": trade.realized_pnl
                    }
                finally:
                    session.close()
            except Exception as create_error:
                logger.error(
                    f"❌ Failed to INSERT trade: {trading_symbol} | "
                    f"Error: {create_error}",
                    exc_info=True
                )
                return None
            
        except Exception as e:
            logger.error(f"Error creating trade from orders: {e}", exc_info=True)
            return None
    
    def _should_exclude_equity(self, exchange: str) -> bool:
        """
        Check if equity orders should be excluded based on config
        
        Args:
            exchange: Exchange code
            
        Returns:
            True if equity and filtering is enabled, False otherwise
        """
        # Default to excluding equity (NSE, BSE) for options trading
        if not exchange:
            return False
        
        exchange_upper = exchange.upper()
        return exchange_upper in ['NSE', 'BSE']
