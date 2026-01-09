"""
VIX-Based Delta Range Manager
Manages dynamic delta range selection based on VIX levels and hedge logic
"""
import logging
from datetime import datetime, date, timedelta
from config import (
    VIX_DELTA_THRESHOLD, VIX_DELTA_LOW, VIX_DELTA_HIGH, VIX_HEDGE_POINTS,
    TARGET_DELTA_LOW, TARGET_DELTA_HIGH, HEDGE_TRIGGER_POINTS
)


class VIXDeltaManager:
    def __init__(self, vix_calculator):
        """
        Initialize VIX Delta Manager
        
        Args:
            vix_calculator: VIXCalculator instance for VIX data
        """
        self.vix_calculator = vix_calculator
        self.current_delta_low = TARGET_DELTA_LOW
        self.current_delta_high = TARGET_DELTA_HIGH
        self.current_hedge_points = HEDGE_TRIGGER_POINTS
        self.using_vix_based_delta = False
        self.next_week_expiry_used = False
        
        logging.info(f"VIXDeltaManager initialized with threshold: {VIX_DELTA_THRESHOLD}")
    
    def get_delta_range(self):
        """
        Get the appropriate delta range based on current VIX levels
        
        Returns:
            tuple: (delta_low, delta_high, hedge_points, use_next_week_expiry)
        """
        try:
            # Get current VIX average
            vix_summary = self.vix_calculator.get_vix_summary()
            average_vix = vix_summary.get('average_vix')
            
            if average_vix is None:
                logging.warning("Unable to get VIX data, using default delta range")
                return self._get_default_delta_range()
            
            # Check if average VIX is below threshold
            if average_vix < VIX_DELTA_THRESHOLD:
                logging.info(f"Average VIX ({average_vix:.2f}) is below threshold ({VIX_DELTA_THRESHOLD}), using VIX-based delta range")
                self.using_vix_based_delta = True
                self.current_delta_low = VIX_DELTA_LOW
                self.current_delta_high = VIX_DELTA_HIGH
                self.current_hedge_points = VIX_HEDGE_POINTS
                self.next_week_expiry_used = True
                
                return (
                    VIX_DELTA_LOW,
                    VIX_DELTA_HIGH,
                    VIX_HEDGE_POINTS,
                    True  # Use next week expiry
                )
            else:
                logging.info(f"Average VIX ({average_vix:.2f}) is above threshold ({VIX_DELTA_THRESHOLD}), using default delta range")
                self.using_vix_based_delta = False
                return self._get_default_delta_range()
                
        except Exception as e:
            logging.error(f"Error getting delta range based on VIX: {e}")
            return self._get_default_delta_range()
    
    def _get_default_delta_range(self):
        """
        Get default delta range configuration
        
        Returns:
            tuple: (delta_low, delta_high, hedge_points, use_next_week_expiry)
        """
        self.current_delta_low = TARGET_DELTA_LOW
        self.current_delta_high = TARGET_DELTA_HIGH
        self.current_hedge_points = HEDGE_TRIGGER_POINTS
        self.next_week_expiry_used = False
        
        return (
            TARGET_DELTA_LOW,
            TARGET_DELTA_HIGH,
            HEDGE_TRIGGER_POINTS,
            False  # Use current week expiry
        )
    
    def get_current_delta_range(self):
        """
        Get the currently active delta range
        
        Returns:
            tuple: (delta_low, delta_high)
        """
        return (self.current_delta_low, self.current_delta_high)
    
    def get_current_hedge_points(self):
        """
        Get the currently active hedge trigger points
        
        Returns:
            int: Hedge trigger points
        """
        return self.current_hedge_points
    
    def should_use_next_week_expiry(self):
        """
        Check if next week expiry should be used
        
        Returns:
            bool: True if next week expiry should be used
        """
        return self.next_week_expiry_used
    
    def is_using_vix_based_delta(self):
        """
        Check if currently using VIX-based delta range
        
        Returns:
            bool: True if using VIX-based delta range
        """
        return self.using_vix_based_delta
    
    def get_vix_status(self):
        """
        Get current VIX status and delta configuration
        
        Returns:
            dict: VIX status information
        """
        try:
            vix_summary = self.vix_calculator.get_vix_summary()
            average_vix = vix_summary.get('average_vix')
            current_vix = vix_summary.get('current_vix')
            
            return {
                'current_vix': current_vix,
                'average_vix': average_vix,
                'threshold': VIX_DELTA_THRESHOLD,
                'using_vix_based_delta': self.using_vix_based_delta,
                'delta_low': self.current_delta_low,
                'delta_high': self.current_delta_high,
                'hedge_points': self.current_hedge_points,
                'use_next_week_expiry': self.next_week_expiry_used,
                'reason': self._get_delta_reason(average_vix)
            }
        except Exception as e:
            logging.error(f"Error getting VIX status: {e}")
            return {
                'current_vix': None,
                'average_vix': None,
                'threshold': VIX_DELTA_THRESHOLD,
                'using_vix_based_delta': False,
                'delta_low': self.current_delta_low,
                'delta_high': self.current_delta_high,
                'hedge_points': self.current_hedge_points,
                'use_next_week_expiry': False,
                'reason': 'Error fetching VIX data'
            }
    
    def _get_delta_reason(self, average_vix):
        """
        Get the reason for current delta configuration
        
        Args:
            average_vix: Current average VIX value
            
        Returns:
            str: Reason for delta configuration
        """
        if average_vix is None:
            return "Using default delta range (VIX data unavailable)"
        elif average_vix < VIX_DELTA_THRESHOLD:
            return f"Using VIX-based delta range (VIX {average_vix:.2f} < {VIX_DELTA_THRESHOLD})"
        else:
            return f"Using default delta range (VIX {average_vix:.2f} >= {VIX_DELTA_THRESHOLD})"
    
    def log_delta_configuration(self):
        """
        Log the current delta configuration
        """
        status = self.get_vix_status()
        
        logging.info("=" * 60)
        logging.info("VIX-BASED DELTA CONFIGURATION")
        logging.info("=" * 60)
        logging.info(f"Current VIX: {status['current_vix']:.2f}" if status['current_vix'] else "Current VIX: N/A")
        logging.info(f"Average VIX: {status['average_vix']:.2f}" if status['average_vix'] else "Average VIX: N/A")
        logging.info(f"VIX Threshold: {status['threshold']}")
        logging.info(f"Using VIX-based Delta: {status['using_vix_based_delta']}")
        logging.info(f"Delta Range: {status['delta_low']:.2f} - {status['delta_high']:.2f}")
        logging.info(f"Hedge Points: {status['hedge_points']}")
        logging.info(f"Use Next Week Expiry: {status['use_next_week_expiry']}")
        logging.info(f"Reason: {status['reason']}")
        logging.info("=" * 60)
