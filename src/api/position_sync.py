"""
Position Synchronization
Syncs positions from Zerodha API to local database
Adapted from disciplined-Trader for Strangle10Points strategy
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from pytz import UTC
import logging
from src.kite_client import KiteClient
from src.database.repository import PositionRepository, TradeRepository
from src.database.models import Position

logger = logging.getLogger(__name__)

# IST timezone for date operations
try:
    from src.utils.date_utils import IST
except ImportError:
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))


class PositionSync:
    """Synchronizes positions between Zerodha and local database"""
    
    def __init__(self, kite_client: KiteClient, position_repo: PositionRepository, trade_repo: Optional[TradeRepository] = None):
        self.kite_client = kite_client
        self.position_repo = position_repo
        # Initialize trade repository if not provided (for creating trades when positions close)
        if trade_repo is None:
            self.trade_repo = TradeRepository(position_repo.db_manager)
        else:
            self.trade_repo = trade_repo
    
    def _parse_order_timestamp(self, timestamp_str: str) -> datetime:
        """
        Parse order timestamp from Kite API.
        Kite returns timestamps in IST format: 'YYYY-MM-DD HH:MM:SS'
        """
        if not timestamp_str:
            return datetime.utcnow()
        
        try:
            if isinstance(timestamp_str, datetime):
                dt = timestamp_str
            else:
                # Parse as IST (Kite returns IST timestamps)
                dt = datetime.strptime(str(timestamp_str), '%Y-%m-%d %H:%M:%S')
            
            # If no timezone info, assume IST
            if dt.tzinfo is None:
                dt = IST.localize(dt)
            
            # Convert to UTC for storage
            return dt.astimezone(UTC).replace(tzinfo=None)
        except Exception as e:
            logger.debug(f"Error parsing timestamp '{timestamp_str}': {e}")
            return datetime.utcnow()
    
    def sync_positions_from_api(self, broker_id: str) -> List[Position]:
        """
        Fetch positions from Zerodha API and sync to database
        
        Args:
            broker_id: Broker ID for filtering positions
        
        Returns:
            List of synced positions
        """
        try:
            # Get positions from Zerodha
            api_positions = self.kite_client.get_positions()
            
            # Get all active positions from database BEFORE processing API positions
            # This helps us detect positions that disappeared from API (closed manually)
            db_active_positions = {}
            try:
                session = self.position_repo.db_manager.get_session()
                try:
                    active_positions = self.position_repo.get_active_positions(session, broker_id)
                    for pos in active_positions:
                        db_active_positions[str(pos.instrument_token)] = pos
                finally:
                    session.close()
            except Exception as e:
                logger.debug(f"Error getting active positions for sync: {e}")
            
            # Track which positions are still in API
            api_instrument_tokens = set()
            
            synced_positions = []
            
            for api_pos in api_positions:
                # Extract position data first (needed for all checks)
                trading_symbol = api_pos.get('tradingsymbol', '')
                exchange = api_pos.get('exchange', '')
                instrument_token = str(api_pos.get('instrument_token', ''))
                
                # Track this instrument as present in API
                api_instrument_tokens.add(instrument_token)
                
                # Exclude equity positions (NSE, BSE) if configured
                if self._should_exclude_equity(exchange):
                    logger.debug(f"Skipping equity position: {exchange}:{trading_symbol}")
                    continue
                
                # Get quantity with sign (preserve negative for SELL positions)
                # Zerodha API returns quantity with sign: positive for BUY, negative for SELL
                raw_quantity = api_pos.get('quantity', 0)
                quantity = int(raw_quantity)  # Can be negative for SELL
                
                # Check if position became inactive (quantity=0)
                # We still process it to mark it as inactive
                if quantity == 0:
                    # Check if we have an active position for this instrument
                    existing_position = None
                    try:
                        session = self.position_repo.db_manager.get_session()
                        try:
                            existing_position = self.position_repo.get_by_instrument(session, broker_id, instrument_token)
                        finally:
                            session.close()
                    except Exception:
                        pass
                    
                    # If we have an active position that became 0, mark it as inactive
                    # BUT preserve the original quantity for display purposes
                    if existing_position:
                        # Store original quantity before setting to 0 (for trade history display)
                        original_quantity = existing_position.quantity
                        
                        # Try to get exit price and time from orderbook
                        exit_price = api_pos.get('last_price', existing_position.current_price)
                        exit_time = datetime.utcnow()
                        
                        # Try to find the exit order from orderbook to get actual exit price and time
                        try:
                            if self.kite_client and hasattr(self.kite_client, 'kite'):
                                orders = self.kite_client.kite.orders()
                                # Find the most recent COMPLETE order for this symbol that would close the position
                                # For SELL positions (negative qty), look for BUY orders
                                # For BUY positions (positive qty), look for SELL orders
                                exit_transaction_type = "BUY" if original_quantity < 0 else "SELL"
                                
                                matching_orders = [
                                    o for o in orders
                                    if (o.get('tradingsymbol', '').upper() == trading_symbol.upper() and
                                        o.get('exchange', '').upper() == exchange.upper() and
                                        o.get('transaction_type', '').upper() == exit_transaction_type and
                                        o.get('status', '').upper() == 'COMPLETE' and
                                        o.get('filled_quantity', 0) > 0)
                                ]
                                
                                if matching_orders:
                                    # Sort by timestamp (most recent first)
                                    matching_orders.sort(
                                        key=lambda x: self._parse_order_timestamp(x.get('order_timestamp', '')),
                                        reverse=True
                                    )
                                    # Get the most recent exit order
                                    exit_order = matching_orders[0]
                                    exit_price = float(exit_order.get('average_price', exit_price))
                                    exit_time_str = exit_order.get('order_timestamp', '')
                                    if exit_time_str:
                                        try:
                                            exit_time = self._parse_order_timestamp(exit_time_str)
                                            # Convert to UTC if needed
                                            if exit_time.tzinfo:
                                                exit_time = exit_time.astimezone(UTC).replace(tzinfo=None)
                                        except:
                                            pass
                                    
                                    logger.info(
                                        f"Found exit order for {trading_symbol}: "
                                        f"Exit price=₹{exit_price:.2f}, Exit time={exit_time}"
                                    )
                        except Exception as e:
                            logger.debug(f"Could not fetch exit order from orderbook: {e}")
                        
                        # Update position to inactive
                        session = self.position_repo.db_manager.get_session()
                        try:
                            # Update all fields
                            existing_position.quantity = 0
                            existing_position.is_active = False
                            existing_position.current_price = exit_price  # Use exit price as current price
                            existing_position.updated_at = exit_time
                            
                            # Calculate P&L using original quantity
                            if existing_position.current_price and existing_position.entry_price:
                                from src.utils.position_utils import calculate_position_pnl
                                try:
                                    existing_position.unrealized_pnl = calculate_position_pnl(
                                        existing_position.entry_price,
                                        existing_position.current_price,
                                        original_quantity,  # Use original quantity for P&L calculation
                                        existing_position.lot_size or 1
                                    )
                                except ImportError:
                                    # Fallback P&L calculation if position_utils not available
                                    if original_quantity > 0:  # BUY
                                        existing_position.unrealized_pnl = (existing_position.current_price - existing_position.entry_price) * original_quantity
                                    else:  # SELL
                                        existing_position.unrealized_pnl = (existing_position.entry_price - existing_position.current_price) * abs(original_quantity)
                            
                            session.commit()
                            logger.debug(f"Successfully committed position {trading_symbol} as inactive (quantity=0)")
                            
                            # Create trade record for the closed position
                            try:
                                from src.utils.date_utils import get_current_ist_time
                                try:
                                    exit_time_ist = get_current_ist_time()
                                except ImportError:
                                    exit_time_ist = datetime.now(IST)
                                
                                # Convert entry_time to IST if needed
                                entry_time_ist = existing_position.entry_time
                                if entry_time_ist.tzinfo is None:
                                    entry_time_ist = entry_time_ist.replace(tzinfo=UTC).astimezone(IST)
                                else:
                                    entry_time_ist = entry_time_ist.astimezone(IST)
                                
                                # Determine transaction type from quantity sign
                                transaction_type = 'BUY' if original_quantity > 0 else 'SELL'
                                
                                # Create trade record
                                trade_data = {
                                    'broker_id': broker_id,
                                    'instrument_token': existing_position.instrument_token,
                                    'trading_symbol': trading_symbol,
                                    'exchange': exchange,
                                    'entry_time': entry_time_ist.replace(tzinfo=None),  # Store as naive UTC
                                    'exit_time': exit_time_ist.replace(tzinfo=None),  # Store as naive UTC
                                    'entry_price': existing_position.entry_price,
                                    'exit_price': exit_price,
                                    'quantity': original_quantity,  # Use original quantity (can be negative for SELL)
                                    'exit_type': 'manual',  # Manually closed (quantity=0)
                                    'position_id': existing_position.id,
                                    'transaction_type': transaction_type
                                }
                                
                                # Calculate realized P&L
                                if transaction_type == 'SELL':
                                    realized_pnl = (existing_position.entry_price - exit_price) * abs(original_quantity)
                                else:
                                    realized_pnl = (exit_price - existing_position.entry_price) * original_quantity
                                
                                trade_data['realized_pnl'] = realized_pnl
                                trade_data['is_profit'] = realized_pnl > 0
                                
                                trade_session = self.trade_repo.db_manager.get_session()
                                try:
                                    trade = self.trade_repo.create(trade_session, trade_data)
                                    logger.info(
                                        f"Created trade record for closed position {trading_symbol} (quantity=0): "
                                        f"P&L=₹{trade.realized_pnl:.2f}"
                                    )
                                finally:
                                    trade_session.close()
                            except Exception as trade_error:
                                # Don't fail position sync if trade creation fails
                                logger.warning(f"Could not create trade record for closed position {trading_symbol}: {trade_error}")
                        except Exception as commit_error:
                            session.rollback()
                            logger.error(f"Error committing position update: {commit_error}", exc_info=True)
                            raise
                        finally:
                            session.close()
                        logger.info(
                            f"Position {trading_symbol} marked as inactive (quantity=0, original qty was {original_quantity}, "
                            f"exit price=₹{exit_price:.2f})"
                        )
                    continue
                
                # Get prices
                entry_price = api_pos.get('average_price', 0.0)
                current_price = api_pos.get('last_price', entry_price)
                
                # Get lot size (default 1 for options)
                lot_size = api_pos.get('lot_size', 1)
                
                # Get existing position to detect quantity changes
                existing_position = None
                try:
                    session = self.position_repo.db_manager.get_session()
                    try:
                        existing_position = self.position_repo.get_by_instrument(session, broker_id, instrument_token)
                    finally:
                        session.close()
                except Exception:
                    pass
                
                old_quantity = existing_position.quantity if existing_position else 0
                
                # Create or update position in database (quantity can be negative for SELL)
                session = self.position_repo.db_manager.get_session()
                try:
                    if existing_position:
                        # Update existing position
                        existing_position.quantity = quantity
                        existing_position.current_price = current_price or existing_position.current_price
                        existing_position.updated_at = datetime.utcnow()
                        if current_price:
                            # Calculate P&L
                            try:
                                from src.utils.position_utils import calculate_position_pnl
                                existing_position.unrealized_pnl = calculate_position_pnl(
                                    existing_position.entry_price,
                                    current_price,
                                    quantity,
                                    lot_size
                                )
                            except ImportError:
                                # Fallback P&L calculation
                                if quantity > 0:  # BUY
                                    existing_position.unrealized_pnl = (current_price - existing_position.entry_price) * quantity
                                else:  # SELL
                                    existing_position.unrealized_pnl = (existing_position.entry_price - current_price) * abs(quantity)
                        session.commit()
                        session.refresh(existing_position)
                        position = existing_position
                    else:
                        # Create new position
                        position_data = {
                            'broker_id': broker_id,
                            'instrument_token': instrument_token,
                            'trading_symbol': trading_symbol,
                            'exchange': exchange,
                            'entry_price': entry_price,
                            'current_price': current_price or entry_price,
                            'quantity': quantity,
                            'lot_size': lot_size,
                            'unrealized_pnl': 0.0,
                            'is_active': True
                        }
                        position = self.position_repo.create(session, position_data)
                    
                    synced_positions.append(position)
                    
                    # Log quantity change if detected
                    if existing_position and old_quantity != quantity:
                        logger.info(
                            f"Quantity change detected for {trading_symbol}: "
                            f"{old_quantity} -> {quantity} (change: {quantity - old_quantity})"
                        )
                finally:
                    session.close()
            
            # After processing all API positions, check for positions that disappeared from API
            # These are positions that were in database but not in API response (manually closed)
            logger.info(
                f"Position sync: Found {len(db_active_positions)} active positions in DB, "
                f"{len(api_instrument_tokens)} positions in API response"
            )
            
            disappeared_count = 0
            for instrument_token, db_position in db_active_positions.items():
                if instrument_token not in api_instrument_tokens:
                    disappeared_count += 1
                    # Position exists in database but not in API - it was closed
                    logger.info(
                        f"Detected closed position (not in API): {db_position.trading_symbol} "
                        f"(Token: {instrument_token})"
                    )
                    
                    # Mark as inactive and try to get exit details from orderbook
                    original_quantity = db_position.quantity
                    exit_price = db_position.current_price or db_position.entry_price
                    exit_time = datetime.utcnow()
                    
                    # Try to find exit order from orderbook
                    try:
                        if self.kite_client and hasattr(self.kite_client, 'kite'):
                            orders = self.kite_client.kite.orders()
                            exit_transaction_type = "BUY" if original_quantity < 0 else "SELL"
                            
                            matching_orders = [
                                o for o in orders
                                if (o.get('tradingsymbol', '').upper() == db_position.trading_symbol.upper() and
                                    o.get('exchange', '').upper() == db_position.exchange.upper() and
                                    o.get('transaction_type', '').upper() == exit_transaction_type and
                                    o.get('status', '').upper() == 'COMPLETE' and
                                    o.get('filled_quantity', 0) > 0)
                            ]
                            
                            if matching_orders:
                                matching_orders.sort(
                                    key=lambda x: self._parse_order_timestamp(x.get('order_timestamp', '')),
                                    reverse=True
                                )
                                exit_order = matching_orders[0]
                                exit_price = float(exit_order.get('average_price', exit_price))
                                exit_time_str = exit_order.get('order_timestamp', '')
                                if exit_time_str:
                                    try:
                                        exit_time = self._parse_order_timestamp(exit_time_str)
                                        if exit_time.tzinfo:
                                            exit_time = exit_time.astimezone(UTC).replace(tzinfo=None)
                                    except:
                                        pass
                                
                                logger.info(
                                    f"Found exit order for {db_position.trading_symbol}: "
                                    f"Exit price=₹{exit_price:.2f}, Exit time={exit_time}"
                                )
                    except Exception as e:
                        logger.debug(f"Could not fetch exit order from orderbook: {e}")
                    
                    # Update position to inactive
                    session = self.position_repo.db_manager.get_session()
                    try:
                        db_position.quantity = 0
                        db_position.is_active = False
                        db_position.current_price = exit_price
                        db_position.updated_at = exit_time
                        
                        # Update P&L
                        if db_position.current_price:
                            try:
                                from src.utils.position_utils import calculate_position_pnl
                                db_position.unrealized_pnl = calculate_position_pnl(
                                    db_position.entry_price,
                                    db_position.current_price,
                                    original_quantity,
                                    db_position.lot_size or 1
                                )
                            except ImportError:
                                # Fallback P&L calculation
                                if original_quantity > 0:  # BUY
                                    db_position.unrealized_pnl = (db_position.current_price - db_position.entry_price) * original_quantity
                                else:  # SELL
                                    db_position.unrealized_pnl = (db_position.entry_price - db_position.current_price) * abs(original_quantity)
                        
                        session.commit()
                        logger.debug(f"Successfully committed position {db_position.trading_symbol} as inactive")
                        
                        # Create trade record for the closed position
                        try:
                            from src.utils.date_utils import get_current_ist_time
                            try:
                                exit_time_ist = get_current_ist_time()
                            except ImportError:
                                exit_time_ist = datetime.now(IST)
                            
                            # Convert entry_time to IST if needed
                            entry_time_ist = db_position.entry_time
                            if entry_time_ist.tzinfo is None:
                                entry_time_ist = entry_time_ist.replace(tzinfo=UTC).astimezone(IST)
                            else:
                                entry_time_ist = entry_time_ist.astimezone(IST)
                            
                            # Determine transaction type from quantity sign
                            transaction_type = 'BUY' if original_quantity > 0 else 'SELL'
                            
                            # Create trade record
                            trade_data = {
                                'broker_id': broker_id,
                                'instrument_token': db_position.instrument_token,
                                'trading_symbol': db_position.trading_symbol,
                                'exchange': db_position.exchange,
                                'entry_time': entry_time_ist.replace(tzinfo=None),
                                'exit_time': exit_time_ist.replace(tzinfo=None),
                                'entry_price': db_position.entry_price,
                                'exit_price': exit_price,
                                'quantity': original_quantity,
                                'exit_type': 'manual',
                                'position_id': db_position.id,
                                'transaction_type': transaction_type
                            }
                            
                            # Calculate realized P&L
                            if transaction_type == 'SELL':
                                realized_pnl = (db_position.entry_price - exit_price) * abs(original_quantity)
                            else:
                                realized_pnl = (exit_price - db_position.entry_price) * original_quantity
                            
                            trade_data['realized_pnl'] = realized_pnl
                            trade_data['is_profit'] = realized_pnl > 0
                            
                            trade_session = self.trade_repo.db_manager.get_session()
                            try:
                                trade = self.trade_repo.create(trade_session, trade_data)
                                logger.info(
                                    f"Created trade record for closed position {db_position.trading_symbol}: "
                                    f"P&L=₹{trade.realized_pnl:.2f}"
                                )
                            finally:
                                trade_session.close()
                        except Exception as trade_error:
                            # Don't fail position sync if trade creation fails
                            logger.warning(f"Could not create trade record for closed position {db_position.trading_symbol}: {trade_error}")
                    except Exception as commit_error:
                        session.rollback()
                        logger.error(f"Error committing position update: {commit_error}", exc_info=True)
                        raise
                    finally:
                        session.close()
                    
                    logger.info(
                        f"Position {db_position.trading_symbol} marked as inactive "
                        f"(disappeared from API, exit price=₹{exit_price:.2f})"
                    )
            
            if disappeared_count > 0:
                logger.info(
                    f"Position sync: Detected {disappeared_count} closed positions "
                    f"(not in API response, marked as inactive)"
                )
            
            logger.debug(f"Synced {len(synced_positions)} positions from API")
            
            # Invalidate position cache after sync
            try:
                from src.database.shared_data_service import SharedDataService
                shared_data = SharedDataService(self.position_repo.db_manager)
                shared_data.invalidate_position_cache(broker_id)
            except Exception as cache_error:
                logger.debug(f"Cache invalidation failed (non-critical): {cache_error}")
            
            return synced_positions
            
        except Exception as e:
            logger.error(f"Error syncing positions from API: {e}", exc_info=True)
            return []
    
    def _should_exclude_equity(self, exchange: str) -> bool:
        """
        Check if equity positions should be excluded based on config
        
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
