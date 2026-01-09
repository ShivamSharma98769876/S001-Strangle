"""
VIX Calculator for Average VIX Calculation
Calculates average VIX for the last trading days
"""
import logging
from datetime import datetime, timedelta, date
from kiteconnect import KiteConnect
from config import VIX_INSTRUMENT_TOKEN, VIX_HISTORICAL_DAYS


class VIXCalculator:
    def __init__(self, kite_client):
        """
        Initialize VIX Calculator
        
        Args:
            kite_client: KiteClient instance for API access
        """
        self.kite_client = kite_client
        self.kite = kite_client.kite
        
    def get_current_vix(self):
        """
        Get current VIX value
        
        Returns:
            float: Current VIX value or None if error
        """
        try:
            vix_data = self.kite.ltp(VIX_INSTRUMENT_TOKEN)
            current_vix = vix_data[VIX_INSTRUMENT_TOKEN]['last_price']
            logging.info(f"Current VIX: {current_vix}")
            return current_vix
        except Exception as e:
            logging.error(f"Error fetching current VIX: {e}")
            return None
    
    def get_historical_vix(self, days=None):
        """
        Get historical VIX data for the last N trading days (excluding current day)
        
        Args:
            days (int): Number of trading days to fetch (defaults to config value)
            
        Returns:
            list: List of VIX values for each day
        """
        if days is None:
            days = VIX_HISTORICAL_DAYS
            
        try:
            # Calculate date range - add extra days to account for weekends and holidays
            end_date = date.today()
            # Use more buffer days to ensure we get enough trading days
            buffer_days = max(days * 3, 30)  # At least 30 days buffer
            start_date = end_date - timedelta(days=buffer_days)
            
            logging.info(f"Fetching VIX historical data for last {days} trading days (from {start_date} to {end_date})")
            
            # Get historical data
            historical_data = self.kite.historical_data(
                instrument_token=int(VIX_INSTRUMENT_TOKEN),
                from_date=start_date,
                to_date=end_date,
                interval='day'
            )
            
            if not historical_data:
                logging.warning("No historical VIX data available")
                return []
            
            # Extract closing prices (VIX values) and sort by date
            vix_values = []
            for candle in historical_data:
                vix_values.append(candle['close'])
            
            # Return last N values (most recent trading days, excluding current day)
            result = vix_values[-days:] if len(vix_values) >= days else vix_values
            logging.info(f"Retrieved {len(result)} historical VIX values")
            return result
            
        except Exception as e:
            logging.error(f"Error fetching historical VIX data: {e}")
            return []
    
    def calculate_average_vix(self, days=None):
        """
        Calculate average VIX for the last N trading days INCLUDING current day VIX
        
        Args:
            days (int): Number of trading days to include in average (defaults to config value)
            
        Returns:
            dict: Dictionary containing average VIX and individual values
        """
        if days is None:
            days = VIX_HISTORICAL_DAYS
            
        try:
            # Get current VIX
            current_vix = self.get_current_vix()
            
            # Get historical VIX data (excluding current day)
            historical_vix_values = self.get_historical_vix(days - 1)  # Get one less day since we'll add current day
            
            if not historical_vix_values and current_vix is None:
                logging.warning("No VIX data available for average calculation")
                return {
                    'average_vix': None,
                    'vix_values': [],
                    'days_count': 0,
                    'current_vix': None
                }
            
            # Combine historical values with current VIX
            all_vix_values = historical_vix_values.copy()
            if current_vix is not None:
                all_vix_values.append(current_vix)
            
            # Calculate average including current day
            average_vix = sum(all_vix_values) / len(all_vix_values)
            
            result = {
                'average_vix': round(average_vix, 2),
                'vix_values': all_vix_values,
                'days_count': len(all_vix_values),
                'current_vix': current_vix,
                'historical_vix_values': historical_vix_values
            }
            
            logging.info(f"Average VIX for last {len(all_vix_values)} days (including current day): {average_vix:.2f}")
            return result
            
        except Exception as e:
            logging.error(f"Error calculating average VIX: {e}")
            return {
                'average_vix': None,
                'vix_values': [],
                'days_count': 0,
                'current_vix': None
            }
    
    def get_vix_summary(self, days=None):
        """
        Get comprehensive VIX summary including current, average, and trend
        
        Args:
            days (int): Number of trading days for average calculation (defaults to config value)
            
        Returns:
            dict: Comprehensive VIX summary
        """
        if days is None:
            days = VIX_HISTORICAL_DAYS
            
        try:
            vix_data = self.calculate_average_vix(days)
            
            if vix_data['average_vix'] is None:
                return vix_data
            
            # Calculate trend
            current_vix = vix_data['current_vix']
            average_vix = vix_data['average_vix']
            
            if current_vix and average_vix:
                if current_vix > average_vix:
                    trend = "Above Average"
                    trend_direction = "↗️"
                elif current_vix < average_vix:
                    trend = "Below Average"
                    trend_direction = "↘️"
                else:
                    trend = "At Average"
                    trend_direction = "➡️"
                
                difference = current_vix - average_vix
                difference_percent = (difference / average_vix) * 100
            else:
                trend = "Unknown"
                trend_direction = "❓"
                difference = 0
                difference_percent = 0
            
            vix_data.update({
                'trend': trend,
                'trend_direction': trend_direction,
                'difference': round(difference, 2),
                'difference_percent': round(difference_percent, 2)
            })
            
            return vix_data
            
        except Exception as e:
            logging.error(f"Error getting VIX summary: {e}")
            return {
                'average_vix': None,
                'current_vix': None,
                'trend': "Error",
                'trend_direction': "❌",
                'vix_values': [],
                'days_count': 0
            }
    
    def get_delta_recommendation(self):
        """
        Get delta range recommendation based on VIX levels
        
        Returns:
            dict: Delta recommendation with VIX analysis
        """
        try:
            from config import VIX_DELTA_THRESHOLD, VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS
            from config import TARGET_DELTA_LOW, TARGET_DELTA_HIGH, HEDGE_TRIGGER_POINTS
            
            vix_summary = self.get_vix_summary()
            average_vix = vix_summary.get('average_vix')
            
            if average_vix is None:
                return {
                    'delta_low': TARGET_DELTA_LOW,
                    'delta_high': TARGET_DELTA_HIGH,
                    'hedge_points': HEDGE_TRIGGER_POINTS,
                    'use_next_week_expiry': False,
                    'reason': 'VIX data unavailable - using default',
                    'vix_threshold': VIX_DELTA_THRESHOLD,
                    'average_vix': None
                }
            
            if average_vix < VIX_DELTA_THRESHOLD:
                return {
                    'delta_low': VIX_DELTA_LOW,
                    'delta_high': VIX_DELTA_HIGH,
                    'hedge_points': VIX_HEDGE_POINTS,
                    'use_next_week_expiry': True,
                    'reason': f'VIX {average_vix:.2f} < {VIX_DELTA_THRESHOLD} - using wider delta range',
                    'vix_threshold': VIX_DELTA_THRESHOLD,
                    'average_vix': average_vix
                }
            else:
                return {
                    'delta_low': TARGET_DELTA_LOW,
                    'delta_high': TARGET_DELTA_HIGH,
                    'hedge_points': HEDGE_TRIGGER_POINTS,
                    'use_next_week_expiry': False,
                    'reason': f'VIX {average_vix:.2f} >= {VIX_DELTA_THRESHOLD} - using default delta range',
                    'vix_threshold': VIX_DELTA_THRESHOLD,
                    'average_vix': average_vix
                }
                
        except Exception as e:
            logging.error(f"Error getting delta recommendation: {e}")
            return {
                'delta_low': TARGET_DELTA_LOW,
                'delta_high': TARGET_DELTA_HIGH,
                'hedge_points': HEDGE_TRIGGER_POINTS,
                'use_next_week_expiry': False,
                'reason': f'Error: {e}',
                'vix_threshold': VIX_DELTA_THRESHOLD,
                'average_vix': None
            }
