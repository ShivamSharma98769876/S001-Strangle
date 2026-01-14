"""
Date and Time Utility Functions
"""

from datetime import datetime
from pytz import timezone

IST = timezone('Asia/Kolkata')


def get_current_ist_time() -> datetime:
    """Get current time in IST"""
    return datetime.now(IST)
