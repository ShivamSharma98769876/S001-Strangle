"""
Main Trading Bot Class
Orchestrates the entire options trading strategy
"""
import logging
import time as time_module
from datetime import datetime, time
from config import (
    TARGET_DELTA_LOW, TARGET_DELTA_HIGH, MAX_STOP_LOSS_TRIGGER,
    MARKET_START_TIME, MARKET_END_TIME, TRADING_START_TIME, SQUARE_OFF_TIME,
    STOP_LOSS_CONFIG, HEDGE_TRIGGER_POINTS, INITIAL_PROFIT_BOOKING, SECOND_PROFIT_BOOKING,
    SQUARE_OFF_MINUTES_BEFORE_CLOSE, STRATEGY_TAG
)
from src.kite_client import KiteClient
from src.options_calculator import OptionsCalculator
from src.vix_calculator import VIXCalculator
from src.vix_delta_manager import VIXDeltaManager
from src.environment import get_ist_time

# Greek analysis removed - not needed for core trading functionality

class TradingBot:
    def __init__(self, api_key, api_secret, request_token, account, call_quantity, put_quantity):
        self.kite_client = KiteClient(api_key, api_secret, request_token=request_token, account=account)
        self.calculator = OptionsCalculator(self.kite_client)
        self.vix_calculator = VIXCalculator(self.kite_client)
        self.vix_delta_manager = VIXDeltaManager(self.vix_calculator)
        self.call_quantity = call_quantity
        self.put_quantity = put_quantity
        self.account = account
        
        # Greek analysis removed - core trading functionality only
        
        # Trading state
        self.stop_loss_trigger_count = 0
        self.today_sl = self._get_today_stop_loss()
        
        # Stop flag for graceful shutdown
        self.stop_requested = False
        
        # Order tracking
        self.call_order_id = None
        self.put_order_id = None
        self.call_sl_order_id = None
        self.put_sl_order_id = None
        self.call_strike = None
        self.put_strike = None
        
        # Calculate stop loss amounts
        self.call_sl_to_be_placed = 0
        self.put_sl_to_be_placed = 0
        
        # Loss tracking
        self.loss_taken = 0
        self.new_trade_taken = False
        
        logging.info(f"TradingBot initialized for account: {account}")
        logging.info(f"Call quantity: {call_quantity}, Put quantity: {put_quantity}")
        logging.info(f"Today's stop loss: {self.today_sl}")
    
    def stop(self):
        """Request the bot to stop gracefully"""
        self.stop_requested = True
        logging.info("Stop request received. Bot will exit gracefully after current operations complete.")
    
    def _get_today_stop_loss(self):
        """Get stop loss percentage based on current day"""
        current_day = get_ist_time().strftime('%A')
        return STOP_LOSS_CONFIG.get(current_day, STOP_LOSS_CONFIG['default'])
    
    def execute_trade(self, target_delta_low, target_delta_high):
        """Execute the main trading strategy"""
        # Check if market is already closed before starting
        now = get_ist_time().time()
        if now >= MARKET_END_TIME:
            logging.warning("[MARKET CLOSED] Market is already closed, exiting execute_trade immediately")
            return
            
        while not self.stop_requested:
            options = self.kite_client.fetch_option_chain()
            if not options:
                logging.error("No options fetched.")
                time_module.sleep(30)
                continue

            current_expiry = options[0]['expiry']
            if isinstance(current_expiry, str):
                current_expiry = datetime.strptime(current_expiry, '%Y-%m-%d').date()

            if self.calculator.is_expiry_within_2_days(current_expiry):
                logging.info(f"Current expiry is within 2 days, finding next {EXPIRY_DAY} expiry")
                next_expiry = self.calculator.get_next_week_expiry(options)
                options = [o for o in options if o['expiry'] == next_expiry]
                logging.info(f"Next {EXPIRY_DAY} expiry: {next_expiry}")
            else:
                options = [o for o in options if o['expiry'] == current_expiry]

            underlying_price = self.kite_client.get_underlying_price()
            if underlying_price is None:
                logging.error("Error fetching underlying price")
                time_module.sleep(30)
                continue

            strikes = self.calculator.find_strikes(options, underlying_price, target_delta_low, target_delta_high)
            if not strikes:
                logging.warning("No suitable strikes found. Retrying...")
                time_module.sleep(10)
                continue

            self.call_strike, self.put_strike = strikes

            now = get_ist_time().time()
            is_amo = not (MARKET_START_TIME <= now <= MARKET_END_TIME)
            
            # Calculate stop loss amounts
            call_ltp = self.kite_client.get_ltp(f"NFO:{self.call_strike['tradingsymbol']}")
            put_ltp = self.kite_client.get_ltp(f"NFO:{self.put_strike['tradingsymbol']}")
            
            if call_ltp and put_ltp:
                self.call_sl_to_be_placed = round((call_ltp * self.today_sl) / 100)
                self.put_sl_to_be_placed = round((put_ltp * self.today_sl) / 100)
                
                logging.info(f"Call SL to be placed: {self.call_sl_to_be_placed}")
                logging.info(f"Put SL to be placed: {self.put_sl_to_be_placed}")

                # Place main orders
                self.call_order_id = self.kite_client.place_order(
                    self.call_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, is_amo, self.call_quantity
                )
                self.put_order_id = self.kite_client.place_order(
                    self.put_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, is_amo, self.put_quantity
                )

                if self.call_order_id and self.put_order_id:
                    # Place stop-loss orders
                    call_sl_price = call_ltp + self.call_sl_to_be_placed
                    put_sl_price = put_ltp + self.put_sl_to_be_placed

                    self.call_sl_order_id = self.kite_client.place_stop_loss_order(
                        self.call_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, 
                        call_sl_price, self.call_quantity
                    )
                    self.put_sl_order_id = self.kite_client.place_stop_loss_order(
                        self.put_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, 
                        put_sl_price, self.put_quantity
                    )

                    if self.call_sl_order_id and self.put_sl_order_id:
                        # Start monitoring trades
                        self.monitor_trades(target_delta_high)
                        break
                    else:
                        logging.error("Failed to place stop-loss orders.")
                else:
                    logging.error("Failed to place main orders.")
            else:
                logging.error("Failed to get LTP for strikes")
        
        if self.stop_requested:
            logging.info("Bot execution stopped due to stop request.")
            return
    
    def monitor_trades(self, target_delta_high):
        """Monitor and manage active trades"""
        end_time = MARKET_END_TIME
        self.loss_taken = 0
        hedge_taken = False
        square_off_executed = False  # Track if square-off has been executed

        try:
            call_initial_price = self.kite_client.get_ltp(f"NFO:{self.call_strike['tradingsymbol']}")
            put_initial_price = self.kite_client.get_ltp(f"NFO:{self.put_strike['tradingsymbol']}")
            initial_total_premium = call_initial_price + put_initial_price
            logging.info(f"Initial Total Premium Received: {initial_total_premium}")
        except Exception as e:
            logging.error(f"Error calculating initial total premium: {e}")
            return

        adjusted_for_14_points = False
        adjusted_for_28_points = False
        self.new_trade_taken = False

        while not self.stop_requested:
            now = get_ist_time().time()

            # Stop trades if stop-loss has been triggered three times
            if self.stop_loss_trigger_count >= MAX_STOP_LOSS_TRIGGER:
                logging.info("Stop-loss triggered three times. No more trades will be taken.")
                self._modify_stop_loss_orders()
                break

            # ============================================================
            # CRITICAL: Market Close Square-Off Logic (1 minute before close)
            # This MUST be checked BEFORE the market close check
            # ============================================================
            if not square_off_executed and now >= SQUARE_OFF_TIME:
                square_off_time_str = SQUARE_OFF_TIME.strftime("%H:%M")
                market_close_str = MARKET_END_TIME.strftime("%H:%M")
                
                logging.warning(
                    f"🕐 MARKET CLOSE APPROACHING - Initiating Square-Off at {square_off_time_str} IST "
                    f"(market closes at {market_close_str} IST, {SQUARE_OFF_MINUTES_BEFORE_CLOSE} minute(s) before close)"
                )
                
                # Execute square-off of all positions
                self._square_off_all_positions_at_market_close()
                square_off_executed = True
                
                logging.info("✅ Market close square-off completed. Exiting monitor loop.")
                break

            # Exit trades and modify stop-loss at market close (fallback - should not reach here)
            if now >= end_time:
                logging.info("Market is closing, modifying stop-loss orders.")
                self._modify_stop_loss_orders()
                break

            try:
                underlying_price = self.kite_client.get_underlying_price()
                call_ltp = self.kite_client.get_ltp(f"NFO:{self.call_strike['tradingsymbol']}")
                put_ltp = self.kite_client.get_ltp(f"NFO:{self.put_strike['tradingsymbol']}")
                
                if underlying_price is None or call_ltp is None or put_ltp is None:
                    continue
                    
                current_total_premium = call_ltp + put_ltp

                if self.new_trade_taken:
                    # When a new trade is taken after stop-loss, reset initial premium to new trade's premium
                    initial_total_premium = current_total_premium
                    self.new_trade_taken = False

                logging.info(f"Initial Total Premium: {initial_total_premium}, Current Total Premium: {current_total_premium}, Loss taken: {self.loss_taken}")
                
                total_pnl = initial_total_premium - current_total_premium - self.loss_taken
                logging.info(f"Total Profit and Loss: {total_pnl:.2f}")

                # Adjust stop-loss orders if premium reduces
                if not adjusted_for_14_points and initial_total_premium - current_total_premium >= self.loss_taken + INITIAL_PROFIT_BOOKING:
                    logging.info(f"Total premium reduced by {initial_total_premium - current_total_premium} points, modifying stop-loss orders.")
                    self._modify_stop_loss_orders()
                    adjusted_for_14_points = True
                    
                    # Exit after first profit booking - no further processing
                    logging.warning(f"[PROFIT BOOKING] Initial profit target reached: {INITIAL_PROFIT_BOOKING} points")
                    logging.warning(f"[PROFIT BOOKING] GRACEFUL EXIT: No more trades will be taken for this session")
                    logging.info(f"Final Summary - Initial Premium: {initial_total_premium:.3f} | Loss Taken: {self.loss_taken:.3f} | Final P&L: {initial_total_premium - current_total_premium - self.loss_taken:.3f}")
                    return

                if not adjusted_for_28_points and initial_total_premium - current_total_premium >= self.loss_taken + SECOND_PROFIT_BOOKING:
                    logging.info(f"Total premium reduced by {initial_total_premium - current_total_premium} points, modifying stop-loss orders.")
                    self._modify_stop_loss_orders()
                    adjusted_for_28_points = True
                    
                    # Exit after second profit booking - no further processing
                    logging.warning(f"[PROFIT BOOKING] Second profit target reached: {SECOND_PROFIT_BOOKING} points")
                    logging.warning(f"[PROFIT BOOKING] GRACEFUL EXIT: No more trades will be taken for this session")
                    logging.info(f"Final Summary - Initial Premium: {initial_total_premium:.3f} | Loss Taken: {self.loss_taken:.3f} | Final P&L: {initial_total_premium - current_total_premium - self.loss_taken:.3f}")
                    return

                # Take Hedges when trigger points are reached (VIX-based or default)
                # Get current hedge trigger points from VIXDeltaManager
                _, _, hedge_trigger_points, _ = self.vix_delta_manager.get_delta_range()
                if not hedge_taken and initial_total_premium - current_total_premium >= self.loss_taken + hedge_trigger_points:
                    logging.info(f"Taking hedges as premium reduced by {initial_total_premium - current_total_premium - self.loss_taken} points (trigger: {hedge_trigger_points} points)")
                    hedge_success = self._place_hedge_orders()
                    # Always set hedge_taken to True to prevent repeated attempts, regardless of success/failure
                    hedge_taken = True

            except Exception as e:
                logging.error(f"Error monitoring trades: {e}")

            # Check deltas
            call_delta = self.calculator.calculate_delta(self.call_strike, underlying_price)
            put_delta = self.calculator.calculate_delta(self.put_strike, underlying_price)
            logging.info(f"Call Delta: {call_delta}, Put Delta: {put_delta}, Underlying Price: {underlying_price}")

            if abs(call_delta) > target_delta_high + 0.1 or abs(put_delta) > target_delta_high + 0.1:
                logging.info("Delta exceeded the limit, exiting trades and re-entering")
                self._exit_trades()
                time_module.sleep(10)
                self.execute_trade(TARGET_DELTA_LOW, TARGET_DELTA_HIGH)
                break

            # Check stop-loss orders
            self._check_stop_loss_orders(underlying_price, initial_total_premium, current_total_premium)

            time_module.sleep(3)
        
        if self.stop_requested:
            logging.info("Trade monitoring stopped due to stop request.")
            # Clean up any open orders if stopping
            self._cleanup_on_stop()
            return
    
    def _modify_stop_loss_orders(self):
        """Modify stop-loss orders to current LTP"""
        try:
            call_ltp = self.kite_client.get_ltp(f"NFO:{self.call_strike['tradingsymbol']}")
            put_ltp = self.kite_client.get_ltp(f"NFO:{self.put_strike['tradingsymbol']}")
            
            if call_ltp and put_ltp:
                self.kite_client.modify_order(self.call_sl_order_id, call_ltp + 1, call_ltp + 2)
                self.kite_client.modify_order(self.put_sl_order_id, put_ltp + 1, put_ltp + 2)
        except Exception as e:
            logging.error(f"Error modifying stop-loss orders: {e}")
    
    def _place_hedge_orders(self):
        """Place hedge orders"""
        try:
            # Get delta range configuration from VIXDeltaManager
            delta_low, delta_high, hedge_points, use_next_week_expiry = self.vix_delta_manager.get_delta_range()
            
            # Log the strategy being used
            strategy_name = "Calendar Strategy" if use_next_week_expiry else "Strangle Strategy"
            logging.info(f"Using {strategy_name} for hedge placement (use_next_week_expiry: {use_next_week_expiry})")
            
            call_hedge, put_hedge = self.calculator.find_hedges(self.call_strike, self.put_strike, use_next_week_expiry)
            if call_hedge:
                self.kite_client.place_order(call_hedge, self.kite_client.kite.TRANSACTION_TYPE_BUY, False, self.call_quantity)
            if put_hedge:
                self.kite_client.place_order(put_hedge, self.kite_client.kite.TRANSACTION_TYPE_BUY, False, self.put_quantity)
            
            logging.info("Hedge orders placed successfully")
            return True
        except Exception as e:
            logging.error(f"Error placing hedge orders: {e}")
            logging.warning("Hedge placement failed, but will prevent repeated attempts")
            return False
    
    def _exit_trades(self):
        """Exit current trades"""
        if self.call_order_id:
            self.kite_client.cancel_order(self.call_order_id)
        if self.put_order_id:
            self.kite_client.cancel_order(self.put_order_id)
    
    def _cleanup_on_stop(self):
        """Clean up resources when bot is stopped"""
        try:
            logging.info("Cleaning up resources due to stop request...")
            
            # Cancel any pending orders if they exist
            if self.call_order_id:
                try:
                    self.kite_client.cancel_order(self.call_order_id)
                    logging.info(f"Cancelled call order: {self.call_order_id}")
                except Exception as e:
                    logging.error(f"Error cancelling call order: {e}")
            
            if self.put_order_id:
                try:
                    self.kite_client.cancel_order(self.put_order_id)
                    logging.info(f"Cancelled put order: {self.put_order_id}")
                except Exception as e:
                    logging.error(f"Error cancelling put order: {e}")
            
            if self.call_sl_order_id:
                try:
                    self.kite_client.cancel_order(self.call_sl_order_id)
                    logging.info(f"Cancelled call SL order: {self.call_sl_order_id}")
                except Exception as e:
                    logging.error(f"Error cancelling call SL order: {e}")
            
            if self.put_sl_order_id:
                try:
                    self.kite_client.cancel_order(self.put_sl_order_id)
                    logging.info(f"Cancelled put SL order: {self.put_sl_order_id}")
                except Exception as e:
                    logging.error(f"Error cancelling put SL order: {e}")
            
            logging.info("Cleanup completed successfully.")
            
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
    
    def _square_off_all_positions_at_market_close(self):
        """
        Square off all open positions at market close time.
        
        IMPORTANT: Only squares off positions created by this strategy (tag: S001).
        
        This method is called 1 minute before market close (configurable via SQUARE_OFF_MINUTES_BEFORE_CLOSE).
        It performs the following steps:
        1. Cancel all pending stop-loss orders (with S001 tag)
        2. Square off each tracked position individually (with S001 tag)
        3. Use emergency square-off via Kite API as fallback (only for our tracked symbols)
        """
        square_off_time_str = SQUARE_OFF_TIME.strftime("%H:%M")
        market_close_str = MARKET_END_TIME.strftime("%H:%M")
        
        logging.warning(
            f"🕐 Market Close Square-Off initiated at {square_off_time_str} IST "
            f"(market closes at {market_close_str} IST)"
        )
        logging.info(f"📋 Only squaring off positions with tag: '{STRATEGY_TAG}'")
        
        squared_off_count = 0
        failed_count = 0
        failed_positions = []
        
        # Build list of tracked symbols (only these will be squared off)
        tracked_symbols = []
        if self.call_strike:
            tracked_symbols.append(self.call_strike['tradingsymbol'])
        if self.put_strike:
            tracked_symbols.append(self.put_strike['tradingsymbol'])
        
        logging.info(f"📋 Tracked positions to square off (tag '{STRATEGY_TAG}'): {tracked_symbols}")
        
        # Step 1: Cancel all pending stop-loss orders first (only our orders)
        logging.info("Step 1: Cancelling all pending stop-loss orders (tag: S001)...")
        
        if self.call_sl_order_id:
            try:
                # Check if SL order is still pending before canceling
                sl_status = self.kite_client.get_order_status(self.call_sl_order_id)
                if sl_status and sl_status not in ['COMPLETE', 'CANCELLED', 'REJECTED']:
                    self.kite_client.cancel_order(self.call_sl_order_id)
                    logging.info(f"Cancelled Call SL order (tag: {STRATEGY_TAG}): {self.call_sl_order_id}")
            except Exception as e:
                logging.warning(f"Could not cancel Call SL order {self.call_sl_order_id}: {e}")
        
        if self.put_sl_order_id:
            try:
                # Check if SL order is still pending before canceling
                sl_status = self.kite_client.get_order_status(self.put_sl_order_id)
                if sl_status and sl_status not in ['COMPLETE', 'CANCELLED', 'REJECTED']:
                    self.kite_client.cancel_order(self.put_sl_order_id)
                    logging.info(f"Cancelled Put SL order (tag: {STRATEGY_TAG}): {self.put_sl_order_id}")
            except Exception as e:
                logging.warning(f"Could not cancel Put SL order {self.put_sl_order_id}: {e}")
        
        # Step 2: Square off tracked positions (CALL and PUT) - only our S001 positions
        logging.info(f"Step 2: Squaring off tracked positions (tag: {STRATEGY_TAG})...")
        
        positions_to_square_off = []
        
        # Add Call position if it exists
        if self.call_strike:
            positions_to_square_off.append({
                'name': 'CALL',
                'strike': self.call_strike,
                'quantity': self.call_quantity
            })
        
        # Add Put position if it exists
        if self.put_strike:
            positions_to_square_off.append({
                'name': 'PUT',
                'strike': self.put_strike,
                'quantity': self.put_quantity
            })
        
        if not positions_to_square_off:
            logging.info(f"ℹ️ No tracked positions to square off (tag: {STRATEGY_TAG})")
        
        for pos_info in positions_to_square_off:
            try:
                pos_name = pos_info['name']
                strike = pos_info['strike']
                quantity = pos_info['quantity']
                tradingsymbol = strike['tradingsymbol']
                
                logging.info(f"Squaring off {pos_name} position (tag: {STRATEGY_TAG}): {tradingsymbol}, Qty: {quantity}")
                
                # Get current LTP for logging purposes
                try:
                    current_ltp = self.kite_client.get_ltp(f"NFO:{tradingsymbol}")
                    logging.info(f"  Current LTP for {tradingsymbol}: {current_ltp}")
                except Exception as e:
                    logging.warning(f"  Could not fetch LTP for {tradingsymbol}: {e}")
                    current_ltp = None
                
                # Place BUY order to close the SHORT position (we sold options, so we need to buy back)
                # Using STRATEGY_TAG to ensure proper tagging
                order_id = self.kite_client.place_market_order(
                    tradingsymbol=tradingsymbol,
                    exchange='NFO',
                    transaction_type='BUY',  # Buy to close short position
                    quantity=quantity,
                    product='NRML',
                    tag=STRATEGY_TAG  # Use strategy tag (S001)
                )
                
                if order_id:
                    logging.info(
                        f"✅ {pos_name} position squared off successfully (tag: {STRATEGY_TAG}): "
                        f"{tradingsymbol}, Order ID: {order_id}"
                    )
                    squared_off_count += 1
                else:
                    logging.error(f"❌ Failed to square off {pos_name} position: {tradingsymbol} - No order ID returned")
                    failed_count += 1
                    failed_positions.append(tradingsymbol)
                
                # Small delay between orders to avoid rate limiting
                time_module.sleep(0.2)
                
            except Exception as e:
                pos_name = pos_info.get('name', 'UNKNOWN')
                tradingsymbol = pos_info.get('strike', {}).get('tradingsymbol', 'UNKNOWN')
                logging.error(f"❌ Error squaring off {pos_name} position ({tradingsymbol}): {e}")
                failed_count += 1
                failed_positions.append(tradingsymbol)
        
        # Step 3: Emergency fallback - if any positions failed, use square_off_all_positions
        # IMPORTANT: Only square off our tracked symbols (not all positions!)
        if failed_count > 0 and tracked_symbols:
            logging.warning(
                f"⚠️ {failed_count} position(s) failed to square off: {failed_positions}. "
                f"Attempting emergency square-off for tracked symbols only (tag: {STRATEGY_TAG})..."
            )
            try:
                # Only square off positions matching our tracked symbols
                emergency_order_ids = self.kite_client.square_off_all_positions(
                    tag_filter=STRATEGY_TAG,
                    allowed_symbols=tracked_symbols  # Only our positions!
                )
                if emergency_order_ids:
                    logging.info(
                        f"✅ Emergency square-off executed (tag: {STRATEGY_TAG}): "
                        f"{len(emergency_order_ids)} order(s) placed - {emergency_order_ids}"
                    )
                    squared_off_count += len(emergency_order_ids)
                else:
                    logging.warning("⚠️ Emergency square-off returned no orders. Positions may already be closed.")
            except Exception as e:
                logging.critical(
                    f"❌ CRITICAL: Emergency square-off also failed: {e}. "
                    f"Please manually close positions before market close!"
                )
        
        # Clear position tracking after square-off
        self.call_strike = None
        self.put_strike = None
        self.call_order_id = None
        self.put_order_id = None
        self.call_sl_order_id = None
        self.put_sl_order_id = None
        
        # Log summary
        logging.info(
            f"✅ Market Close Square-Off Summary (Tag: {STRATEGY_TAG}):\n"
            f"   - Time: {get_ist_time().strftime('%H:%M:%S')} IST\n"
            f"   - Positions squared off: {squared_off_count}\n"
            f"   - Failed: {failed_count}\n"
            f"   - Total processed: {squared_off_count + failed_count}\n"
            f"   - Tracked symbols: {tracked_symbols}"
        )
        
        if failed_count > 0:
            logging.critical(
                f"⚠️ WARNING: {failed_count} position(s) may not have been closed properly. "
                f"Please verify manually! (Tag: {STRATEGY_TAG})"
            )
    
    def _check_stop_loss_orders(self, underlying_price, initial_total_premium, current_total_premium):
        """Check and handle stop-loss order triggers"""
        try:
            call_order_status = self.kite_client.get_order_status(self.call_sl_order_id)
            put_order_status = self.kite_client.get_order_status(self.put_sl_order_id)
            
            if call_order_status == 'COMPLETE':
                logging.info(f"Call stop-loss order {self.call_sl_order_id} triggered")
                self.stop_loss_trigger_count += 1
                if self.stop_loss_trigger_count < MAX_STOP_LOSS_TRIGGER:
                    time_module.sleep(5)
                    new_strike = self.calculator.find_new_strike(underlying_price, self.call_strike, 'CE')
                    if new_strike:
                        new_order_id = self.kite_client.place_order(new_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, False, self.call_quantity)
                        if new_order_id:
                            call_ltp = self.kite_client.get_ltp(f"NFO:{new_strike['tradingsymbol']}")
                            if call_ltp:
                                sl_price = call_ltp + self.call_sl_to_be_placed
                                new_sl_order_id = self.kite_client.place_stop_loss_order(new_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, sl_price, self.call_quantity)
                                
                                # Calculate loss from the previous trade (only if it's an actual loss)
                                # If current_total_premium > initial_total_premium, it's a loss and should be added to loss_taken
                                # If current_total_premium <= initial_total_premium, it's a profit and should NOT be added to loss_taken
                                if current_total_premium > initial_total_premium:
                                    loss = current_total_premium - initial_total_premium
                                    self.loss_taken += loss
                                    logging.info(f"Call strike replaced (LOSS). Loss: {loss:.3f} | Total loss taken: {self.loss_taken:.3f}")
                                else:
                                    # This is a profit scenario (premium reduced)
                                    profit_realized = initial_total_premium - current_total_premium
                                    logging.info(f"Call strike replaced (PROFIT). Profit: {profit_realized:.3f} | Total loss taken: {self.loss_taken:.3f} (unchanged)")
                                
                                self.call_order_id, self.call_sl_order_id, self.call_strike = new_order_id, new_sl_order_id, new_strike
                                self.new_trade_taken = True

            if put_order_status == 'COMPLETE':
                logging.info(f"Put stop-loss order {self.put_sl_order_id} triggered")
                self.stop_loss_trigger_count += 1
                if self.stop_loss_trigger_count < MAX_STOP_LOSS_TRIGGER:
                    new_strike = self.calculator.find_new_strike(underlying_price, self.put_strike, 'PE')
                    time_module.sleep(15)
                    if new_strike:
                        new_order_id = self.kite_client.place_order(new_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, False, self.put_quantity)
                        if new_order_id:
                            put_ltp = self.kite_client.get_ltp(f"NFO:{new_strike['tradingsymbol']}")
                            if put_ltp:
                                sl_price = put_ltp + self.put_sl_to_be_placed
                                new_sl_order_id = self.kite_client.place_stop_loss_order(new_strike, self.kite_client.kite.TRANSACTION_TYPE_SELL, sl_price, self.put_quantity)
                                
                                # Calculate loss from the previous trade (only if it's an actual loss)
                                # If current_total_premium > initial_total_premium, it's a loss and should be added to loss_taken
                                # If current_total_premium <= initial_total_premium, it's a profit and should NOT be added to loss_taken
                                if current_total_premium > initial_total_premium:
                                    loss = current_total_premium - initial_total_premium
                                    self.loss_taken += loss
                                    logging.info(f"Put strike replaced (LOSS). Loss: {loss:.3f} | Total loss taken: {self.loss_taken:.3f}")
                                else:
                                    # This is a profit scenario (premium reduced)
                                    profit_realized = initial_total_premium - current_total_premium
                                    logging.info(f"Put strike replaced (PROFIT). Profit: {profit_realized:.3f} | Total loss taken: {self.loss_taken:.3f} (unchanged)")
                                
                                self.put_order_id, self.put_sl_order_id, self.put_strike = new_order_id, new_sl_order_id, new_strike
                                self.new_trade_taken = True

        except Exception as e:
            logging.error(f"Error checking stop-loss orders: {e}")
    
    def run(self):
        """Main run method"""
        logging.info("Trading bot started")
        
        # Greek analysis removed - core trading functionality only
        
        while not self.stop_requested:
            now = get_ist_time().time()
            underlying_price = self.kite_client.get_underlying_price()
            if underlying_price:
                logging.info(f"Underlying price: {underlying_price}")
            
            # Greek analysis removed - core trading functionality only
            
            if now >= TRADING_START_TIME:
                logging.info("Executing trade")
                
                # Get VIX-based delta range configuration
                delta_low, delta_high, hedge_points, use_next_week_expiry = self.vix_delta_manager.get_delta_range()
                
                # Log VIX configuration
                self.vix_delta_manager.log_delta_configuration()
                
                logging.info(f"Using delta range: {delta_low:.2f} - {delta_high:.2f}, hedge points: {hedge_points}, next week expiry: {use_next_week_expiry}")
                
                self.execute_trade(delta_low, delta_high)
                break

            time_module.sleep(30)
        
        if self.stop_requested:
            logging.info("Bot stopped due to stop request.")
        else:
            logging.info("Bot execution completed normally.")
