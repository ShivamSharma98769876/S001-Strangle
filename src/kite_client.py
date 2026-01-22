"""
Kite Connect API Client Wrapper
"""
import logging
from kiteconnect import KiteConnect
from datetime import datetime, date, timedelta
import time as time_module
from config import VIX_INSTRUMENT_TOKEN, VIX_FETCH_INTERVAL, VWAP_MINUTES

# Retry configuration
MAX_RETRIES = 3
MAX_RETRIES_GATEWAY_TIMEOUT = 5  # More retries for gateway timeout errors
INITIAL_BACKOFF_SECONDS = 1.0
INITIAL_BACKOFF_GATEWAY_TIMEOUT = 2.0  # Longer initial backoff for gateway timeouts
MAX_BACKOFF_SECONDS = 10.0
CONSECUTIVE_ERROR_THRESHOLD = 5  # Alert after this many consecutive errors

# Retryable error patterns (server-side/transient issues)
RETRYABLE_ERROR_PATTERNS = [
    "504",
    "502",
    "503",
    "gateway time-out",
    "gateway timeout",
    "connection reset",
    "connection refused",
    "connection timed out",
    "request failed",
    "kt-quotes",
    "couldn't parse the json",
    "server didn't respond",
    "too many requests",
    "rate limit",
    "network is unreachable",
    "temporary failure",
]


def is_retryable_error(error_message: str) -> bool:
    """Check if an error is retryable (transient/server-side)"""
    error_lower = error_message.lower()
    return any(pattern in error_lower for pattern in RETRYABLE_ERROR_PATTERNS)


def retry_with_backoff(func, *args, max_retries=MAX_RETRIES, **kwargs):
    """
    Execute a function with exponential backoff retry logic.
    Uses more retries and longer backoff for gateway timeout errors (504).
    
    Args:
        func: Function to execute
        *args: Positional arguments to pass to func
        max_retries: Maximum number of retry attempts (default)
        **kwargs: Keyword arguments to pass to func
        
    Returns:
        Result of func if successful, None if all retries fail
    """
    last_exception = None
    backoff = INITIAL_BACKOFF_SECONDS
    effective_max_retries = max_retries
    attempt = 0
    
    while attempt <= effective_max_retries:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            error_msg = str(e)
            
            if not is_retryable_error(error_msg):
                # Non-retryable error, don't retry
                logging.error(f"Non-retryable error: {error_msg}")
                raise
            
            # Check if this is a gateway timeout error (504) on first attempt
            if attempt == 0:
                is_gateway_timeout = "504" in error_msg or "gateway time-out" in error_msg.lower() or "gateway timeout" in error_msg.lower()
                if is_gateway_timeout:
                    # Use more retries and longer backoff for gateway timeouts
                    effective_max_retries = MAX_RETRIES_GATEWAY_TIMEOUT
                    backoff = INITIAL_BACKOFF_GATEWAY_TIMEOUT
                    logging.info(f"Detected gateway timeout error, using extended retry strategy ({effective_max_retries} retries)")
            
            if attempt < effective_max_retries:
                logging.warning(
                    f"Retryable error (attempt {attempt + 1}/{effective_max_retries + 1}): {error_msg}. "
                    f"Retrying in {backoff:.1f}s..."
                )
                time_module.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                attempt += 1
            else:
                logging.warning(
                    f"All {effective_max_retries + 1} attempts failed. Last error: {error_msg}"
                )
                break
    
    raise last_exception


class KiteClient:
    def __init__(self, api_key, api_secret, request_token=None, access_token=None, account=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.request_token = request_token
        self.access_token = access_token
        self.account = account
        
        # Initialize Kite Connect
        self.kite = KiteConnect(api_key=api_key)
        
        # Set access token if provided directly
        if access_token:
            if not access_token.strip():
                raise ValueError("Access token cannot be empty")
            self.kite.set_access_token(access_token)
        # Note: If request_token is provided, use authenticate() method explicitly
        # This matches the working implementation pattern
        elif request_token:
            # For backward compatibility, still try to generate automatically
            # But prefer using authenticate() method explicitly
            # Validate API secret is provided before attempting token generation
            if not self.api_secret or not self.api_secret.strip():
                raise ValueError(
                    "API secret is required to generate access token from request token. "
                    "Please provide a valid API secret."
                )
            if not request_token.strip():
                raise ValueError("Request token cannot be empty")
            
            # generate_access_token will raise ValueError if it fails
            self.access_token = self.generate_access_token(request_token)
            # If we get here, access_token was successfully generated
            self.kite.set_access_token(self.access_token)
        
        # VIX caching
        self.last_vix_fetch_time = None
        self.india_vix = None
        
        # LTP caching for fallback
        self.ltp_cache = {}
        self.ltp_cache_time = {}
        self.ltp_cache_duration = 60  # Cache duration in seconds
        
        # Consecutive error tracking
        self.consecutive_ltp_errors = 0
        self.last_error_alert_time = None
        self.error_alert_cooldown = 300  # Alert at most every 5 minutes
        
        logging.info(f"KiteClient initialized for account: {account}")
    
    def generate_access_token(self, request_token):
        """
        Generate access token from request token
        
        Args:
            request_token (str): The request token from Kite Connect
            
        Returns:
            str: Access token
            
        Raises:
            ValueError: If API secret is missing, request token is invalid, or checksum validation fails
        """
        if not self.api_secret or not self.api_secret.strip():
            error_msg = "API secret is required but not provided"
            logging.error(f"Error generating access token: {error_msg}")
            raise ValueError(error_msg)
        
        if not request_token or not request_token.strip():
            error_msg = "Request token is required but not provided"
            logging.error(f"Error generating access token: {error_msg}")
            raise ValueError(error_msg)
        
        try:
            logging.info("Generating access token from request token...")
            logging.debug(f"Using API key: {self.api_key[:8]}... (truncated)")
            logging.debug(f"Request token length: {len(request_token)}")
            logging.debug(f"API secret length: {len(self.api_secret)}")
            
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            access_token = data["access_token"]
            self.access_token = access_token
            self.kite.set_access_token(self.access_token)
            logging.info("Access token generated successfully")
            return access_token
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error generating access token: {error_msg}")
            
            # Provide more specific error messages
            if "checksum" in error_msg.lower():
                detailed_error = (
                    f"Invalid checksum error. This usually means:\n"
                    f"1. API secret is incorrect or doesn't match the API key\n"
                    f"2. Request token is invalid or expired\n"
                    f"3. Request token was generated with a different API key\n"
                    f"4. API secret contains extra whitespace or special characters\n"
                    f"Original error: {error_msg}"
                )
                logging.error(detailed_error)
                raise ValueError(detailed_error) from e
            elif "invalid" in error_msg.lower() or "expired" in error_msg.lower():
                detailed_error = (
                    f"Invalid or expired request token. Please generate a new request token.\n"
                    f"Original error: {error_msg}"
                )
                logging.error(detailed_error)
                raise ValueError(detailed_error) from e
            else:
                # Re-raise the original exception with context
                raise ValueError(
                    f"Failed to generate access token: {error_msg}\n"
                    f"Please verify your API credentials and request token are correct."
                ) from e
    
    def authenticate(self, request_token):
        """
        Authenticate with Zerodha using request token (matches working implementation)
        This method explicitly handles authentication and is preferred over auto-generation in __init__
        
        Args:
            request_token (str): The request token from Kite Connect
            
        Returns:
            bool: True if authentication successful, False otherwise
            
        Raises:
            ValueError: If API secret is missing, request token is invalid, or checksum validation fails
        """
        if not self.api_secret or not self.api_secret.strip():
            error_msg = "API secret is required but not provided"
            logging.error(f"Authentication failed: {error_msg}")
            raise ValueError(error_msg)
        
        if not request_token or not request_token.strip():
            error_msg = "Request token is required but not provided"
            logging.error(f"Authentication failed: {error_msg}")
            raise ValueError(error_msg)
        
        try:
            if not self.kite:
                self.kite = KiteConnect(api_key=self.api_key)
            
            logging.info("Authenticating with Zerodha using request token...")
            logging.debug(f"Using API key: {self.api_key[:8]}... (truncated)")
            logging.debug(f"Request token length: {len(request_token)}")
            logging.debug(f"API secret length: {len(self.api_secret)}")
            
            data = self.kite.generate_session(request_token, api_secret=self.api_secret)
            self.access_token = data['access_token']
            self.kite.set_access_token(self.access_token)
            self.request_token = request_token  # Store for reference
            logging.info("Successfully authenticated with Zerodha Kite Connect")
            return True
        except Exception as e:
            error_msg = str(e)
            logging.error(f"Authentication failed: {error_msg}")
            self.access_token = None
            
            # Provide more specific error messages
            if "checksum" in error_msg.lower():
                detailed_error = (
                    f"Invalid checksum error. This usually means:\n"
                    f"1. API secret is incorrect or doesn't match the API key\n"
                    f"2. Request token is invalid or expired\n"
                    f"3. Request token was generated with a different API key\n"
                    f"4. API secret contains extra whitespace or special characters\n"
                    f"Original error: {error_msg}"
                )
                logging.error(detailed_error)
                raise ValueError(detailed_error) from e
            elif "invalid" in error_msg.lower() or "expired" in error_msg.lower():
                detailed_error = (
                    f"Invalid or expired request token. Please generate a new request token.\n"
                    f"Original error: {error_msg}"
                )
                logging.error(detailed_error)
                raise ValueError(detailed_error) from e
            else:
                # Re-raise the original exception with context
                raise ValueError(
                    f"Failed to authenticate: {error_msg}\n"
                    f"Please verify your API credentials and request token are correct."
                ) from e
    
    def get_underlying_price(self, symbol="NSE:NIFTY 50"):
        """Get the current price of the underlying asset with retry and caching"""
        try:
            # Try to fetch with retry logic
            ltp_data = retry_with_backoff(self.kite.ltp, symbol)
            price = ltp_data[symbol]["last_price"]
            
            # Update cache on success
            self.ltp_cache[symbol] = price
            self.ltp_cache_time[symbol] = datetime.now()
            
            # Reset consecutive error counter on success
            self.consecutive_ltp_errors = 0
            
            return price
        except Exception as e:
            self._handle_ltp_error(symbol, e)
            return self._get_cached_ltp(symbol)
    
    def get_india_vix(self):
        """Get India VIX with caching and retry logic to avoid excessive API calls"""
        current_time = datetime.now()
        
        # Fetch VIX only if enough time has passed since last fetch
        if (self.last_vix_fetch_time is None or 
            (current_time - self.last_vix_fetch_time).total_seconds() > VIX_FETCH_INTERVAL):
            try:
                # Use retry logic for VIX fetch
                vix_data = retry_with_backoff(self.kite.ltp, VIX_INSTRUMENT_TOKEN)
                self.india_vix = vix_data[VIX_INSTRUMENT_TOKEN]['last_price']
                self.last_vix_fetch_time = current_time
                logging.info(f"Fetched India VIX: {self.india_vix} at {self.last_vix_fetch_time}")
            except Exception as e:
                error_msg = str(e)
                if is_retryable_error(error_msg):
                    logging.warning(f"Transient error fetching India VIX: {error_msg}")
                else:
                    logging.error(f"Error fetching India VIX: {error_msg}")
                
                # If we have a cached VIX value, use it
                if self.india_vix is not None:
                    logging.info(f"Using cached India VIX: {self.india_vix}")
                else:
                    # No cached value - wait and retry once more
                    logging.warning("No cached VIX available, waiting 30s before retry...")
                    time_module.sleep(30)
                    try:
                        vix_data = retry_with_backoff(self.kite.ltp, VIX_INSTRUMENT_TOKEN)
                        self.india_vix = vix_data[VIX_INSTRUMENT_TOKEN]['last_price']
                        self.last_vix_fetch_time = datetime.now()
                        logging.info(f"Fetched India VIX on retry: {self.india_vix}")
                    except Exception as retry_error:
                        logging.error(f"Failed to fetch VIX after retry: {retry_error}")
                        # Return a default VIX value to prevent crashes
                        if self.india_vix is None:
                            self.india_vix = 15.0  # Conservative default
                            logging.warning(f"Using default VIX value: {self.india_vix}")
        
        return self.india_vix / 100  # Return annualized volatility
    
    def fetch_option_chain(self):
        """Fetch NIFTY option chain data"""
        logging.info("Fetching option chain data")
        try:
            instrument = 'NIFTY'
            instruments = self.kite.instruments('NFO')
            options = [i for i in instruments if i['segment'] == 'NFO-OPT' and i.get('name') == instrument]
            logging.info(f"Fetched {len(options)} options")
            return options
        except Exception as e:
            logging.error(f"Error fetching option chain: {e}")
            return []
    
    def get_ltp(self, symbol):
        """Get Last Traded Price for a symbol with retry and caching"""
        try:
            # Try to fetch with retry logic
            ltp_data = retry_with_backoff(self.kite.ltp, symbol)
            price = ltp_data[symbol]['last_price']
            
            # Update cache on success
            self.ltp_cache[symbol] = price
            self.ltp_cache_time[symbol] = datetime.now()
            
            # Reset consecutive error counter on success
            self.consecutive_ltp_errors = 0
            
            return price
        except Exception as e:
            self._handle_ltp_error(symbol, e)
            return self._get_cached_ltp(symbol)
    
    def _handle_ltp_error(self, symbol, error):
        """Handle LTP fetch errors with appropriate logging and alerting"""
        error_msg = str(error)
        self.consecutive_ltp_errors += 1
        
        # Determine log level based on error type
        if is_retryable_error(error_msg):
            # Transient errors - log as warning (less noise)
            logging.warning(f"Transient error fetching LTP for {symbol}: {error_msg}")
        else:
            # Non-transient errors - log as error
            logging.error(f"Error fetching LTP for {symbol}: {error_msg}")
        
        # Alert if too many consecutive errors
        if self.consecutive_ltp_errors >= CONSECUTIVE_ERROR_THRESHOLD:
            current_time = datetime.now()
            should_alert = (
                self.last_error_alert_time is None or
                (current_time - self.last_error_alert_time).total_seconds() > self.error_alert_cooldown
            )
            
            if should_alert:
                logging.error(
                    f"⚠️ ALERT: {self.consecutive_ltp_errors} consecutive LTP fetch errors! "
                    f"API may be experiencing issues. Last error: {error_msg}"
                )
                self.last_error_alert_time = current_time
    
    def _get_cached_ltp(self, symbol):
        """Get cached LTP value if available and not too stale"""
        if symbol in self.ltp_cache:
            cache_age = (datetime.now() - self.ltp_cache_time.get(symbol, datetime.min)).total_seconds()
            cached_value = self.ltp_cache[symbol]
            
            if cache_age < self.ltp_cache_duration * 5:  # Allow stale cache up to 5x duration during errors
                logging.info(f"Using cached LTP for {symbol}: {cached_value} (age: {cache_age:.0f}s)")
                return cached_value
            else:
                logging.warning(f"Cached LTP for {symbol} is too stale ({cache_age:.0f}s old)")
        
        return None
    
    def calculate_vwap(self, symbol, minutes=None):
        """
        Calculate VWAP (Volume Weighted Average Price) for a given symbol
        
        Args:
            symbol (str): Trading symbol (e.g., 'NFO:NIFTY24JAN19000CE')
            minutes (int): Number of minutes to look back for VWAP calculation
            
        Returns:
            float: VWAP value or None if calculation fails
        """
        if minutes is None:
            minutes = VWAP_MINUTES
            
        try:
            # Get instrument token first
            instrument_token = self._get_instrument_token(symbol)
            if instrument_token is None:
                logging.warning(f"Could not get instrument token for {symbol}")
                return None
            
            # Calculate the time range for VWAP calculation
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=minutes)
            
            # Format times for API call
            from_date = start_time.strftime('%Y-%m-%d')
            to_date = end_time.strftime('%Y-%m-%d')
            
            logging.debug(f"Fetching historical data for {symbol} from {from_date} to {to_date}")
            
            # Get historical data
            historical_data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval='minute'
            )
            
            if not historical_data:
                logging.warning(f"No historical data available for {symbol} (token: {instrument_token})")
                return None
            
            # Calculate VWAP
            total_volume_price = 0
            total_volume = 0
            
            for candle in historical_data:
                # Use typical price (high + low + close) / 3
                typical_price = (candle['high'] + candle['low'] + candle['close']) / 3
                volume = candle.get('volume', 0)
                
                total_volume_price += typical_price * volume
                total_volume += volume
            
            if total_volume == 0:
                logging.warning(f"No volume data available for {symbol}")
                return None
            
            vwap = total_volume_price / total_volume
            logging.info(f"VWAP for {symbol}: {vwap:.2f} (based on {len(historical_data)} candles)")
            return vwap
            
        except Exception as e:
            logging.error(f"Error calculating VWAP for {symbol}: {e}")
            return None
    
    def _get_instrument_token(self, symbol):
        """Get instrument token for a given symbol"""
        try:
            # Extract the instrument name from symbol
            if ':' in symbol:
                exchange, tradingsymbol = symbol.split(':', 1)
            else:
                tradingsymbol = symbol
                exchange = 'NFO'
            
            logging.debug(f"Looking for instrument token: {tradingsymbol} in exchange: {exchange}")
            
            # Get instruments for the exchange
            instruments = self.kite.instruments(exchange)
            
            # Find the matching instrument
            for instrument in instruments:
                if instrument['tradingsymbol'] == tradingsymbol:
                    logging.debug(f"Found instrument token: {instrument['instrument_token']} for {tradingsymbol}")
                    return instrument['instrument_token']
            
            logging.error(f"Instrument token not found for {symbol} (tradingsymbol: {tradingsymbol})")
            logging.debug(f"Available instruments count: {len(instruments)}")
            # Log first few instruments for debugging
            for i, instrument in enumerate(instruments[:5]):
                logging.debug(f"Sample instrument {i+1}: {instrument.get('tradingsymbol', 'N/A')}")
            return None
            
        except Exception as e:
            logging.error(f"Error getting instrument token for {symbol}: {e}")
            return None
    
    def get_strike_vwap_data(self, strike):
        """
        Get VWAP data for a strike option
        
        Args:
            strike (dict): Strike option data
            
        Returns:
            dict: Dictionary containing LTP and VWAP data
        """
        symbol = f"NFO:{strike['tradingsymbol']}"
        
        try:
            ltp = self.get_ltp(symbol)
            vwap = self.calculate_vwap(symbol, minutes=VWAP_MINUTES)
            
            return {
                'symbol': symbol,
                'ltp': ltp,
                'vwap': vwap,
                'strike_price': strike['strike'],
                'instrument_type': strike['instrument_type']
            }
        except Exception as e:
            logging.error(f"Error getting VWAP data for {symbol}: {e}")
            return {
                'symbol': symbol,
                'ltp': None,
                'vwap': None,
                'strike_price': strike['strike'],
                'instrument_type': strike['instrument_type']
            }
    
    def place_order(self, strike, transaction_type, is_amo, quantity):
        """Place an order"""
        order_variety = self.kite.VARIETY_AMO if is_amo else self.kite.VARIETY_REGULAR
        logging.info(f"Placing {'AMO' if is_amo else 'market'} order for {strike['tradingsymbol']}")
        
        try:
            ltp = self.get_ltp(strike['exchange'] + ':' + strike['tradingsymbol'])
            if ltp is None:
                return None
                
            order_id = self.kite.place_order(
                variety=order_variety,
                exchange=self.kite.EXCHANGE_NFO,
                tradingsymbol=strike['tradingsymbol'],
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=self.kite.ORDER_TYPE_MARKET,
                price=ltp,
                product=self.kite.PRODUCT_NRML,
                tag="S001"
            )
            logging.info(f"Order placed successfully. ID: {order_id}, LTP: {ltp}")
            return order_id
        except Exception as e:
            logging.error(f"Error placing order: {e}")
            time_module.sleep(3)
            return None
    
    def place_stop_loss_order(self, strike, transaction_type, stop_loss_price, quantity):
        """Place a stop-loss order"""
        logging.info(f"Placing stop-loss order for {strike['tradingsymbol']} at {stop_loss_price}")
        
        try:
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=self.kite.EXCHANGE_NFO,
                tradingsymbol=strike['tradingsymbol'],
                transaction_type=self.kite.TRANSACTION_TYPE_BUY if transaction_type == self.kite.TRANSACTION_TYPE_SELL else self.kite.TRANSACTION_TYPE_SELL,
                quantity=quantity,
                price=stop_loss_price + 1,
                order_type=self.kite.ORDER_TYPE_SL,
                trigger_price=stop_loss_price,
                product=self.kite.PRODUCT_NRML,
                tag="S001"
            )
            logging.info(f"Stop-loss order placed successfully. ID: {order_id}")
            return order_id
        except Exception as e:
            logging.error(f"Error placing stop-loss order: {e}")
            time_module.sleep(3)
            return None
    
    def cancel_order(self, order_id):
        """Cancel an order"""
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            logging.info(f"Order cancelled successfully. ID: {order_id}")
            return True
        except Exception as e:
            logging.error(f"Error cancelling order {order_id}: {e}")
            return False
    
    def modify_order(self, order_id, new_trigger_price, new_limit_price):
        """Modify an existing order"""
        try:
            modified_order_id = self.kite.modify_order(
                variety=self.kite.VARIETY_REGULAR,
                order_id=order_id,
                trigger_price=new_trigger_price,
                price=new_limit_price
            )
            logging.info(f"Order modified successfully. New trigger: {new_trigger_price}, limit: {new_limit_price}")
            return modified_order_id
        except Exception as e:
            logging.error(f"Error modifying order {order_id}: {e}")
            return None
    
    def get_order_status(self, order_id):
        """Get the status of an order"""
        try:
            order_history = self.kite.order_history(order_id)
            return order_history[-1]['status'] if order_history else None
        except Exception as e:
            logging.error(f"Error getting order status for {order_id}: {e}")
            return None
    
    def get_positions(self):
        """
        Get all current positions from Kite
        
        Returns:
            list: List of position dictionaries with quantity, tradingsymbol, exchange, product, etc.
        """
        try:
            positions = self.kite.positions()
            # Return day positions (net positions for today)
            day_positions = positions.get('day', [])
            logging.info(f"Fetched {len(day_positions)} day positions from Kite")
            return day_positions
        except Exception as e:
            logging.error(f"Error fetching positions: {e}")
            return []
    
    def get_net_positions(self):
        """
        Get net positions (combined day and overnight positions)
        
        Returns:
            list: List of net position dictionaries
        """
        try:
            positions = self.kite.positions()
            # Return net positions
            net_positions = positions.get('net', [])
            logging.info(f"Fetched {len(net_positions)} net positions from Kite")
            return net_positions
        except Exception as e:
            logging.error(f"Error fetching net positions: {e}")
            return []
    
    def place_market_order(self, tradingsymbol, exchange, transaction_type, quantity, product="NRML", tag="S001"):
        """
        Place a market order
        
        Args:
            tradingsymbol: Trading symbol (e.g., 'NIFTY24JAN19000CE')
            exchange: Exchange ('NFO', 'NSE', etc.)
            transaction_type: 'BUY' or 'SELL'
            quantity: Order quantity
            product: Product type ('NRML' or 'MIS')
            tag: Order tag
            
        Returns:
            str: Order ID if successful, None otherwise
        """
        try:
            # Convert transaction_type string to Kite constant
            if transaction_type.upper() == 'BUY':
                txn_type = self.kite.TRANSACTION_TYPE_BUY
            else:
                txn_type = self.kite.TRANSACTION_TYPE_SELL
            
            # Convert product string to Kite constant
            if product.upper() == 'MIS':
                product_type = self.kite.PRODUCT_MIS
            else:
                product_type = self.kite.PRODUCT_NRML
            
            order_id = self.kite.place_order(
                variety=self.kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                transaction_type=txn_type,
                quantity=quantity,
                order_type=self.kite.ORDER_TYPE_MARKET,
                product=product_type,
                tag=tag
            )
            logging.info(f"Market order placed successfully. ID: {order_id}, Symbol: {tradingsymbol}, Type: {transaction_type}, Qty: {quantity}")
            return order_id
        except Exception as e:
            logging.error(f"Error placing market order for {tradingsymbol}: {e}")
            return None
    
    def square_off_position(self, tradingsymbol, exchange, quantity, product="NRML"):
        """
        Square off a specific position
        
        Args:
            tradingsymbol: Trading symbol
            exchange: Exchange
            quantity: Position quantity (positive for long, negative for short)
            product: Product type
            
        Returns:
            str: Order ID if successful, None otherwise
        """
        try:
            # Determine transaction type: if quantity > 0 (long), SELL to close; if < 0 (short), BUY to close
            transaction_type = "SELL" if quantity > 0 else "BUY"
            
            order_id = self.place_market_order(
                tradingsymbol=tradingsymbol,
                exchange=exchange,
                transaction_type=transaction_type,
                quantity=abs(quantity),
                product=product,
                tag="S001"
            )
            
            if order_id:
                logging.info(f"Position squared off: {tradingsymbol}, Order ID: {order_id}")
            return order_id
        except Exception as e:
            logging.error(f"Error squaring off position {tradingsymbol}: {e}")
            return None
    
    def square_off_all_positions(self, tag_filter="S001", allowed_symbols=None):
        """
        Square off positions, optionally filtered by allowed symbols
        
        This method fetches all current positions and places market orders to close them.
        Used for emergency square-off at market close or when needed.
        
        Args:
            tag_filter: Tag to use for square-off orders (default: 'S001')
            allowed_symbols: List of tradingsymbols to square off. If None, squares off all positions.
                            If provided, only positions matching these symbols will be closed.
        
        Returns:
            list: List of order IDs for successful square-off orders
        """
        try:
            positions = self.get_positions()
            order_ids = []
            
            for pos in positions:
                quantity = pos.get('quantity', 0)
                tradingsymbol = pos.get('tradingsymbol')
                
                if quantity == 0:
                    continue  # Skip positions with zero quantity
                
                # Filter by allowed symbols if provided
                if allowed_symbols is not None:
                    if tradingsymbol not in allowed_symbols:
                        logging.debug(f"Skipping position {tradingsymbol} - not in allowed symbols list")
                        continue
                
                try:
                    exchange = pos.get('exchange', 'NFO')
                    product = pos.get('product', 'NRML')
                    
                    # Determine transaction type
                    # If quantity is positive, it's a long position, so SELL to close
                    # If quantity is negative, it's a short position, so BUY to close
                    transaction_type = "SELL" if quantity > 0 else "BUY"
                    
                    logging.info(f"Squaring off position: {tradingsymbol}, Qty: {quantity}, Type: {transaction_type}, Tag: {tag_filter}")
                    
                    order_id = self.place_market_order(
                        tradingsymbol=tradingsymbol,
                        exchange=exchange,
                        transaction_type=transaction_type,
                        quantity=abs(quantity),
                        product=product,
                        tag=tag_filter
                    )
                    
                    if order_id:
                        order_ids.append(order_id)
                        logging.info(f"Squared off position: {tradingsymbol}, Order ID: {order_id}")
                    
                    time_module.sleep(0.1)  # Small delay between orders to avoid rate limiting
                except Exception as e:
                    logging.error(f"Error squaring off position {tradingsymbol}: {e}")
                    continue
            
            logging.info(f"Square off complete. Squared off {len(order_ids)} positions with tag '{tag_filter}'")
            return order_ids
        except Exception as e:
            logging.error(f"Error squaring off positions: {e}")
            return []
    
    def get_orders_by_tag(self, tag="S001"):
        """
        Get all orders with a specific tag
        
        Args:
            tag: Order tag to filter by (default: 'S001')
            
        Returns:
            list: List of orders with the specified tag
        """
        try:
            all_orders = self.kite.orders()
            filtered_orders = [order for order in all_orders if order.get('tag') == tag]
            logging.info(f"Found {len(filtered_orders)} orders with tag '{tag}'")
            return filtered_orders
        except Exception as e:
            logging.error(f"Error fetching orders by tag: {e}")
            return []
    
    def get_positions_by_symbols(self, symbols):
        """
        Get positions that match specific trading symbols
        
        Args:
            symbols: List of trading symbols to filter
            
        Returns:
            list: List of positions matching the symbols
        """
        try:
            all_positions = self.get_positions()
            filtered_positions = [
                pos for pos in all_positions 
                if pos.get('tradingsymbol') in symbols and pos.get('quantity', 0) != 0
            ]
            logging.info(f"Found {len(filtered_positions)} positions matching specified symbols")
            return filtered_positions
        except Exception as e:
            logging.error(f"Error fetching positions by symbols: {e}")
            return []
