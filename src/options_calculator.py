"""
Options Calculator Module
Handles delta calculations, strike selection, and options analysis
"""
import logging
import math
from datetime import datetime, date, timedelta
from scipy.stats import norm
from config import (
    TARGET_DELTA_LOW, TARGET_DELTA_HIGH, 
    MAX_PRICE_DIFFERENCE_PERCENTAGE, HEDGE_POINTS_DIFFERENCE,
    VWAP_ENABLED, VWAP_PRIORITY, VWAP_MINUTES
)


class OptionsCalculator:
    def __init__(self, kite_client):
        self.kite_client = kite_client
    
    def calculate_delta(self, option, underlying_price, risk_free_rate=0.05):
        """Calculate delta for an option using Black-Scholes model"""
        try:
            strike_price = option['strike']
            expiry = option['expiry']
            today = datetime.now().date()
            
            if isinstance(expiry, str):
                expiry = datetime.strptime(expiry, '%Y-%m-%d').date()
            
            days_to_expiry = (expiry - today).days / 365.0
            if days_to_expiry <= 0:
                logging.error(f"Invalid days to expiry: {days_to_expiry} for option {option['tradingsymbol']}")
                return None

            # Get the volatility (VIX)
            volatility = self.kite_client.get_india_vix()

            # Black-Scholes d1 calculation for delta
            d1 = (math.log(underlying_price / strike_price) + 
                  (risk_free_rate + (volatility ** 2) / 2) * days_to_expiry) / (
                      volatility * math.sqrt(days_to_expiry))
            
            if option['instrument_type'] == 'CE':  # Call Option
                delta = norm.cdf(d1)
            else:  # Put Option
                delta = -norm.cdf(-d1)

            return abs(delta)  # Absolute value of delta for comparison
        except Exception as e:
            if "Too many requests" in str(e):
                logging.error("Too many requests - waiting before retrying...")
                import time
                time.sleep(45)
                return self.calculate_delta(option, underlying_price, risk_free_rate)
            else:
                logging.error(f"Error calculating delta: {e}")
                return None
    
    def find_strikes(self, options, underlying_price, target_delta_low, target_delta_high):
        """Find suitable call and put strikes based on delta criteria and VWAP analysis"""
        atm_strike = round(underlying_price / 50) * 50
        logging.info(f"ATM strike: {atm_strike}")

        logging.info(f"Finding strikes with delta between {target_delta_low} and {target_delta_high}")
        if VWAP_ENABLED:
            logging.info(f"VWAP analysis enabled (Priority: {VWAP_PRIORITY}, Minutes: {VWAP_MINUTES})")

        try:
            call_strikes = []
            put_strikes = []

            for option in options:
                if atm_strike - 500 <= option['strike'] <= atm_strike + 500:
                    delta = self.calculate_delta(option, underlying_price)
                    if delta is None:
                        continue
                    
                    option['delta'] = delta
                    if target_delta_low <= delta <= target_delta_high:
                        if option['instrument_type'] == 'CE':
                            call_strikes.append(option)
                        elif option['instrument_type'] == 'PE':
                            put_strikes.append(option)

            if not call_strikes or not put_strikes:
                logging.warning("No strikes found with the desired delta range.")
                return None

            call_strikes.sort(key=lambda x: x['strike'])
            put_strikes.sort(key=lambda x: x['strike'])

            best_pair = None
            min_price_diff = float('inf')
            suitable_pairs = []
            all_pairs = []  # Store all pairs for analysis

            for call in call_strikes:
                for put in put_strikes:
                    try:
                        # PRIMARY CONDITION: Check price difference first to save compute power
                        # Get basic LTP prices first (lightweight operation)
                        call_price = self.kite_client.get_ltp(f"NFO:{call['tradingsymbol']}")
                        put_price = self.kite_client.get_ltp(f"NFO:{put['tradingsymbol']}")
                        
                        if call_price is None or put_price is None:
                            continue
                            
                        price_diff = abs(call_price - put_price)
                        price_diff_percentage = price_diff / ((call_price + put_price) / 2) * 100
                        
                        # PRIMARY FILTER: Only proceed with expensive calculations if price difference is acceptable
                        if abs(price_diff_percentage) > MAX_PRICE_DIFFERENCE_PERCENTAGE:
                            # Log skipped pair for transparency
                            logging.info(f"SKIPPED: {call['tradingsymbol']} | {put['tradingsymbol']} | Price Diff: {price_diff_percentage:.2f}% > {MAX_PRICE_DIFFERENCE_PERCENTAGE}%")
                            continue
                        
                        # Only now perform expensive VWAP calculations for qualifying pairs
                        if VWAP_ENABLED:
                            # Get VWAP data for both strikes
                            call_vwap_data = self.kite_client.get_strike_vwap_data(call)
                            put_vwap_data = self.kite_client.get_strike_vwap_data(put)
                            
                            call_vwap = call_vwap_data['vwap']
                            put_vwap = put_vwap_data['vwap']
                        else:
                            call_vwap = None
                            put_vwap = None
                        
                        # Check VWAP conditions
                        call_below_vwap = call_vwap is not None and call_price < call_vwap
                        put_below_vwap = put_vwap is not None and put_price < put_vwap
                        both_below_vwap = call_below_vwap and put_below_vwap
                        
                        # Log detailed information for each pair (show all pairs regardless of conditions)
                        logging.info(f"\n{'='*60}")
                        logging.info(f"ANALYZING STRIKE PAIR:")
                        call_vwap_str = f"{call_vwap:.2f}" if call_vwap is not None else "N/A"
                        put_vwap_str = f"{put_vwap:.2f}" if put_vwap is not None else "N/A"
                        logging.info(f"Call: {call['tradingsymbol']} | Price: {call_price:.2f} | VWAP: {call_vwap_str} | Delta: {call['delta']:.3f}")
                        logging.info(f"Put:  {put['tradingsymbol']} | Price: {put_price:.2f} | VWAP: {put_vwap_str} | Delta: {put['delta']:.3f}")
                        logging.info(f"Price Difference: {price_diff:.2f} ({price_diff_percentage:.2f}%)")
                        if VWAP_ENABLED:
                            logging.info(f"Call below VWAP: {call_below_vwap}")
                            logging.info(f"Put below VWAP: {put_below_vwap}")
                            logging.info(f"Both below VWAP: {both_below_vwap}")
                        
                        # Store all pairs for analysis (not just those within price difference)
                        pair_info = {
                            'call': call,
                            'put': put,
                            'call_price': call_price,
                            'put_price': put_price,
                            'call_vwap': call_vwap,
                            'put_vwap': put_vwap,
                            'call_delta': call['delta'],
                            'put_delta': put['delta'],
                            'price_diff': price_diff,
                            'price_diff_percentage': price_diff_percentage,
                            'both_below_vwap': both_below_vwap,
                            'within_price_limit': abs(price_diff_percentage) <= MAX_PRICE_DIFFERENCE_PERCENTAGE
                        }
                        
                        all_pairs.append(pair_info)
                        
                        # Check if price difference is within acceptable range
                        if abs(price_diff_percentage) <= MAX_PRICE_DIFFERENCE_PERCENTAGE:
                            suitable_pairs.append(pair_info)
                            
                            # Prioritize pairs where both strikes are below VWAP
                            if VWAP_ENABLED and VWAP_PRIORITY and both_below_vwap:
                                if price_diff < min_price_diff:
                                    min_price_diff = price_diff
                                    best_pair = (call, put)
                                    logging.info(f"✅ NEW BEST PAIR (Both below VWAP): {call['tradingsymbol']} and {put['tradingsymbol']}")
                            elif best_pair is None:  # If no VWAP-suitable pair found, use price difference
                                if price_diff < min_price_diff:
                                    min_price_diff = price_diff
                                    best_pair = (call, put)
                                    if VWAP_ENABLED and VWAP_PRIORITY:
                                        logging.info(f"⚠️ FALLBACK BEST PAIR (Price-based): {call['tradingsymbol']} and {put['tradingsymbol']}")
                                    else:
                                        logging.info(f"✅ BEST PAIR (Price-based): {call['tradingsymbol']} and {put['tradingsymbol']}")
                                
                    except Exception as e:
                        logging.error(f"Error analyzing strike pair {call['tradingsymbol']} - {put['tradingsymbol']}: {e}")
                        import time
                        time.sleep(30)

            # Log summary of all pairs analyzed
            if all_pairs:
                logging.info(f"\n{'='*60}")
                logging.info(f"ALL PAIRS ANALYSIS SUMMARY:")
                logging.info(f"Total pairs analyzed: {len(all_pairs)}")
                logging.info(f"Pairs within price limit ({MAX_PRICE_DIFFERENCE_PERCENTAGE}%): {len(suitable_pairs)}")
            
                if VWAP_ENABLED:
                    vwap_suitable_pairs = [p for p in all_pairs if p['both_below_vwap']]
                    logging.info(f"Pairs with both strikes below VWAP: {len(vwap_suitable_pairs)}")
                    
                    # Show all pairs with their status
                    for i, pair in enumerate(all_pairs, 1):
                        price_status = "✅ WITHIN LIMIT" if pair['within_price_limit'] else "❌ EXCEEDS LIMIT"
                        vwap_status = "✅ VWAP-SUITABLE" if pair['both_below_vwap'] else "⚠️ VWAP-NOT-SUITABLE"
                        logging.info(f"{i}. {price_status} | {vwap_status} | Call: {pair['call']['tradingsymbol']} | Put: {pair['put']['tradingsymbol']} | Diff: {pair['price_diff_percentage']:.2f}%")
                else:
                    # Show all pairs with price status only
                    for i, pair in enumerate(all_pairs, 1):
                        price_status = "✅ WITHIN LIMIT" if pair['within_price_limit'] else "❌ EXCEEDS LIMIT"
                        logging.info(f"{i}. {price_status} | Call: {pair['call']['tradingsymbol']} | Put: {pair['put']['tradingsymbol']} | Diff: {pair['price_diff_percentage']:.2f}%")

            if not all_pairs:
                logging.warning("No strike pairs could be analyzed. This might be due to:")
                logging.warning("- Market being closed")
                logging.warning("- No options available for the current expiry")
                logging.warning("- API connection issues")
                logging.warning("- No strikes found within the delta range")
                return None
                
            if best_pair:
                call, put = best_pair
                # Find the pair info for the best pair
                best_pair_info = next((p for p in all_pairs 
                                     if p['call']['tradingsymbol'] == call['tradingsymbol'] 
                                     and p['put']['tradingsymbol'] == put['tradingsymbol']), None)
                
                if best_pair_info:
                    if VWAP_ENABLED and best_pair_info['both_below_vwap']:
                        logging.info(f"\n🎯 FINAL SELECTION - VWAP OPTIMAL:")
                        call_vwap_str = f"{best_pair_info['call_vwap']:.2f}" if best_pair_info['call_vwap'] is not None else "N/A"
                        put_vwap_str = f"{best_pair_info['put_vwap']:.2f}" if best_pair_info['put_vwap'] is not None else "N/A"
                        logging.info(f"Call: {call['tradingsymbol']} | Price: {best_pair_info['call_price']:.2f} | VWAP: {call_vwap_str} | Delta: {best_pair_info['call_delta']:.3f}")
                        logging.info(f"Put:  {put['tradingsymbol']} | Price: {best_pair_info['put_price']:.2f} | VWAP: {put_vwap_str} | Delta: {best_pair_info['put_delta']:.3f}")
                        logging.info(f"Price Difference: {best_pair_info['price_diff']:.2f} ({best_pair_info['price_diff_percentage']:.2f}%)")
                        logging.info(f"✅ BOTH STRIKES BELOW VWAP - SUITABLE FOR ENTRY")
                    elif VWAP_ENABLED and VWAP_PRIORITY:
                        logging.info(f"\n⚠️ FINAL SELECTION - PRICE-BASED (VWAP not optimal):")
                        call_vwap_str = f"{best_pair_info['call_vwap']:.2f}" if best_pair_info['call_vwap'] is not None else "N/A"
                        put_vwap_str = f"{best_pair_info['put_vwap']:.2f}" if best_pair_info['put_vwap'] is not None else "N/A"
                        logging.info(f"Call: {call['tradingsymbol']} | Price: {best_pair_info['call_price']:.2f} | VWAP: {call_vwap_str} | Delta: {best_pair_info['call_delta']:.3f}")
                        logging.info(f"Put:  {put['tradingsymbol']} | Price: {best_pair_info['put_price']:.2f} | VWAP: {put_vwap_str} | Delta: {best_pair_info['put_delta']:.3f}")
                        logging.info(f"Price Difference: {best_pair_info['price_diff']:.2f} ({best_pair_info['price_diff_percentage']:.2f}%)")
                        logging.info(f"⚠️ NOT BOTH BELOW VWAP - CONSIDER WAITING FOR BETTER ENTRY")
                    else:
                        logging.info(f"\n✅ FINAL SELECTION - PRICE-BASED:")
                        logging.info(f"Call: {call['tradingsymbol']} | Price: {best_pair_info['call_price']:.2f} | Delta: {best_pair_info['call_delta']:.3f}")
                        logging.info(f"Put:  {put['tradingsymbol']} | Price: {best_pair_info['put_price']:.2f} | Delta: {best_pair_info['put_delta']:.3f}")
                        logging.info(f"Price Difference: {best_pair_info['price_diff']:.2f} ({best_pair_info['price_diff_percentage']:.2f}%)")
                        logging.info(f"✅ SUITABLE FOR ENTRY")
                else:
                    logging.info(f"✅ Best pair selected: {call['tradingsymbol']} and {put['tradingsymbol']}")
            else:
                logging.warning("No suitable trading pair found.")
                
            return best_pair

        except Exception as e:
            logging.error(f"Error in find_strikes: {e}")
            return None
    
    def find_hedges(self, call_strike, put_strike, use_next_week_expiry=False):
        """
        Find hedge strikes for the current positions
        
        Args:
            call_strike: Call strike information
            put_strike: Put strike information  
            use_next_week_expiry: If True, use next week's expiry for hedges (Calendar Strategy)
                                 If False, use same week's expiry for hedges (Strangle Strategy)
        """
        options = self.kite_client.fetch_option_chain()
        if not options:
            logging.error("No options fetched for hedge selection.")
            return None, None

        # Determine target expiry for hedges
        if use_next_week_expiry:
            # Calendar Strategy: Use next week's expiry for hedges
            target_expiry = self.get_next_week_expiry(options)
            strategy_name = "Calendar Strategy"
            logging.info(f"[CALENDAR] Using next week's expiry for hedges: {target_expiry}")
        else:
            # Strangle Strategy: Use same week's expiry for hedges
            target_expiry = call_strike['expiry']
            strategy_name = "Strangle Strategy"
            logging.info(f"[STRANGLE] Using same week's expiry for hedges: {target_expiry}")

        call_hedge = next(
            (o for o in options
             if o['strike'] == call_strike['strike'] - HEDGE_POINTS_DIFFERENCE
             and o['instrument_type'] == 'CE'
             and o['expiry'] == target_expiry),
            None
        )
        
        put_hedge = next(
            (o for o in options
             if o['strike'] == put_strike['strike'] + HEDGE_POINTS_DIFFERENCE
             and o['instrument_type'] == 'PE'
             and o['expiry'] == target_expiry),
            None
        )
        
        # Log hedge results
        if call_hedge:
            logging.info(f"[{strategy_name}] Call hedge found: {call_hedge['tradingsymbol']} (100 points below {call_strike['strike']} CE)")
        else:
            logging.warning(f"[{strategy_name}] No call hedge found {HEDGE_POINTS_DIFFERENCE} points below {call_strike['strike']} CE in {target_expiry}")
            
        if put_hedge:
            logging.info(f"[{strategy_name}] Put hedge found: {put_hedge['tradingsymbol']} (100 points above {put_strike['strike']} PE)")
        else:
            logging.warning(f"[{strategy_name}] No put hedge found {HEDGE_POINTS_DIFFERENCE} points above {put_strike['strike']} PE in {target_expiry}")

        return call_hedge, put_hedge
    
    def find_new_strike(self, underlying_price, old_strike, option_type):
        """Find a new strike when stop-loss is triggered"""
        try:
            options = self.kite_client.fetch_option_chain()
            if not options:
                logging.error("No options fetched.")
                return None

            new_strikes = [o for o in options if o['instrument_type'] == option_type and o['expiry'] == old_strike['expiry']]
            
            for strike in new_strikes:
                delta = self.calculate_delta(strike, underlying_price)
                if delta and TARGET_DELTA_LOW <= delta <= TARGET_DELTA_HIGH:
                    return strike
            return None
        except Exception as e:
            logging.error(f"Error finding new strike: {e}")
            return None
    
    def get_current_week_tuesday_expiry(self):
        """Get the current week's Tuesday expiry date"""
        today = date.today()
        
        # Find the Tuesday of current week
        # Monday = 0, Tuesday = 1, ..., Sunday = 6
        days_until_tuesday = (1 - today.weekday()) % 7
        
        # If today is Tuesday, use today; otherwise find next Tuesday
        if today.weekday() == 1:  # Today is Tuesday
            current_week_expiry = today
        else:
            current_week_expiry = today + timedelta(days=days_until_tuesday)
        
        return current_week_expiry
    
    def get_next_week_expiry(self, options):
        """Get the next valid future Tuesday expiry date (first expiry after today).

        Note: On current Tuesday (expiry day) or when current expiry is within
        2 days, we want the immediate next Tuesday, not the one after.
        """
        expiries = sorted(set(o['expiry'] for o in options))
        today = date.today()
        
        # Find all expiries after today
        future_expiries = []
        for expiry in expiries:
            if isinstance(expiry, str):
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
            else:
                expiry_date = expiry
            if expiry_date > today:
                future_expiries.append(expiry_date)
        # Return the first future expiry (immediate next Tuesday)
        if len(future_expiries) >= 1:
            return future_expiries[0]
        return None
    
    def is_expiry_within_2_days(self, expiry_date):
        """Check if expiry is within 2 days"""
        today = date.today()
        if isinstance(expiry_date, str):
            expiry_date = datetime.strptime(expiry_date, '%Y-%m-%d').date()
        return (expiry_date - today).days <= 2
