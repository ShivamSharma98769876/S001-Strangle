"""
VIX Calculator for Average VIX Calculation
Calculates average VIX and 90th percentile VIX for the last trading days
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
    
    def _calculate_percentile(self, values, percentile):
        """
        Calculate percentile of a list of values
        
        Args:
            values (list): List of numeric values
            percentile (float): Percentile to calculate (0-100)
            
        Returns:
            float: Percentile value or None if empty
        """
        if not values:
            return None
        
        sorted_values = sorted(values)
        index = (percentile / 100.0) * (len(sorted_values) - 1)
        
        # Handle integer index
        if index.is_integer():
            return sorted_values[int(index)]
        
        # Interpolate for fractional index
        lower_index = int(index)
        upper_index = lower_index + 1
        
        if upper_index >= len(sorted_values):
            return sorted_values[-1]
        
        lower_value = sorted_values[lower_index]
        upper_value = sorted_values[upper_index]
        fraction = index - lower_index
        
        return lower_value + (upper_value - lower_value) * fraction
    
    def calculate_percentile_vix(self, percentile=90, days=None):
        """
        Calculate percentile VIX for the last N trading days INCLUDING current day VIX
        
        Args:
            percentile (float): Percentile to calculate (defaults to 90 for 90th percentile)
            days (int): Number of trading days to include (defaults to config value)
            
        Returns:
            dict: Dictionary containing percentile VIX and individual values
        """
        if days is None:
            days = VIX_HISTORICAL_DAYS
            
        try:
            # Get current VIX
            current_vix = self.get_current_vix()
            
            # Get historical VIX data (excluding current day)
            historical_vix_values = self.get_historical_vix(days - 1)  # Get one less day since we'll add current day
            
            if not historical_vix_values and current_vix is None:
                logging.warning(f"No VIX data available for {percentile}th percentile calculation")
                return {
                    'percentile_vix': None,
                    'vix_values': [],
                    'days_count': 0,
                    'current_vix': None,
                    'percentile': percentile
                }
            
            # Combine historical values with current VIX
            all_vix_values = historical_vix_values.copy()
            if current_vix is not None:
                all_vix_values.append(current_vix)
            
            # Calculate percentile including current day
            percentile_vix = self._calculate_percentile(all_vix_values, percentile)
            
            result = {
                'percentile_vix': round(percentile_vix, 2) if percentile_vix is not None else None,
                'vix_values': all_vix_values,
                'days_count': len(all_vix_values),
                'current_vix': current_vix,
                'historical_vix_values': historical_vix_values,
                'percentile': percentile
            }
            
            logging.info(f"{percentile}th percentile VIX for last {len(all_vix_values)} days (including current day): {percentile_vix:.2f}" if percentile_vix else f"{percentile}th percentile VIX: N/A")
            return result
            
        except Exception as e:
            logging.error(f"Error calculating {percentile}th percentile VIX: {e}")
            return {
                'percentile_vix': None,
                'vix_values': [],
                'days_count': 0,
                'current_vix': None,
                'percentile': percentile
            }
    
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
        Get comprehensive VIX summary including current, average, 90th percentile, and trend
        
        Args:
            days (int): Number of trading days for calculations (defaults to config value)
            
        Returns:
            dict: Comprehensive VIX summary
        """
        if days is None:
            days = VIX_HISTORICAL_DAYS
            
        try:
            # Get average VIX data
            vix_data = self.calculate_average_vix(days)
            
            # Get 90th percentile VIX data
            percentile_data = self.calculate_percentile_vix(percentile=90, days=days)
            
            # Merge percentile data into vix_data
            vix_data['percentile_90_vix'] = percentile_data.get('percentile_vix')
            
            if vix_data['average_vix'] is None:
                return vix_data
            
            # Calculate trend
            current_vix = vix_data['current_vix']
            average_vix = vix_data['average_vix']
            percentile_90_vix = vix_data.get('percentile_90_vix')
            
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
                'percentile_90_vix': None,
                'current_vix': None,
                'trend': "Error",
                'trend_direction': "❌",
                'vix_values': [],
                'days_count': 0
            }
    
    def get_delta_recommendation(self):
        """
        Get delta range recommendation based on 90th percentile VIX levels (for trade decisions)
        
        Returns:
            dict: Delta recommendation with VIX analysis
        """
        try:
            from config import VIX_DELTA_THRESHOLD, VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS
            from config import TARGET_DELTA_LOW, TARGET_DELTA_HIGH, HEDGE_TRIGGER_POINTS
            
            vix_summary = self.get_vix_summary()
            # Use 90th percentile VIX for trade decisions instead of average
            percentile_90_vix = vix_summary.get('percentile_90_vix')
            average_vix = vix_summary.get('average_vix')  # Keep for reference
            
            if percentile_90_vix is None:
                return {
                    'delta_low': TARGET_DELTA_LOW,
                    'delta_high': TARGET_DELTA_HIGH,
                    'hedge_points': HEDGE_TRIGGER_POINTS,
                    'use_next_week_expiry': False,
                    'reason': 'VIX data unavailable - using default',
                    'vix_threshold': VIX_DELTA_THRESHOLD,
                    'percentile_90_vix': None,
                    'average_vix': average_vix
                }
            
            # Use 90th percentile VIX for threshold comparison
            if percentile_90_vix < VIX_DELTA_THRESHOLD:
                return {
                    'delta_low': VIX_DELTA_LOW,
                    'delta_high': VIX_DELTA_HIGH,
                    'hedge_points': VIX_HEDGE_POINTS,
                    'use_next_week_expiry': True,
                    'reason': f'90th percentile VIX {percentile_90_vix:.2f} < {VIX_DELTA_THRESHOLD} - using wider delta range',
                    'vix_threshold': VIX_DELTA_THRESHOLD,
                    'percentile_90_vix': percentile_90_vix,
                    'average_vix': average_vix
                }
            else:
                return {
                    'delta_low': TARGET_DELTA_LOW,
                    'delta_high': TARGET_DELTA_HIGH,
                    'hedge_points': HEDGE_TRIGGER_POINTS,
                    'use_next_week_expiry': False,
                    'reason': f'90th percentile VIX {percentile_90_vix:.2f} >= {VIX_DELTA_THRESHOLD} - using default delta range',
                    'vix_threshold': VIX_DELTA_THRESHOLD,
                    'percentile_90_vix': percentile_90_vix,
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
                'percentile_90_vix': None,
                'average_vix': None
            }
