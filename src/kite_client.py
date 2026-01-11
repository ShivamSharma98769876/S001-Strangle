"""
Kite Connect API Client Wrapper
"""
import logging
from kiteconnect import KiteConnect
from datetime import datetime, date, timedelta
import time as time_module
from config import VIX_INSTRUMENT_TOKEN, VIX_FETCH_INTERVAL, VWAP_MINUTES


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
        """Get the current price of the underlying asset"""
        try:
            ltp_data = self.kite.ltp(symbol)
            return ltp_data[symbol]["last_price"]
        except Exception as e:
            logging.error(f"Error fetching underlying price: {e}")
            return None
    
    def get_india_vix(self):
        """Get India VIX with caching to avoid excessive API calls"""
        current_time = datetime.now()
        
        # Fetch VIX only if enough time has passed since last fetch
        if (self.last_vix_fetch_time is None or 
            (current_time - self.last_vix_fetch_time).total_seconds() > VIX_FETCH_INTERVAL):
            try:
                vix_data = self.kite.ltp(VIX_INSTRUMENT_TOKEN)
                self.india_vix = vix_data[VIX_INSTRUMENT_TOKEN]['last_price']
                self.last_vix_fetch_time = current_time
                logging.info(f"Fetched India VIX: {self.india_vix} at {self.last_vix_fetch_time}")
            except Exception as e:
                logging.error(f"Error fetching India VIX: {e}")
                time_module.sleep(45)
                return self.get_india_vix()
        
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
        """Get Last Traded Price for a symbol"""
        try:
            ltp_data = self.kite.ltp(symbol)
            return ltp_data[symbol]['last_price']
        except Exception as e:
            logging.error(f"Error fetching LTP for {symbol}: {e}")
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
