"""
Logging Helper for Multi-User Support
Provides utilities for logging with broker_id context
"""

import logging
from flask import has_request_context
from src.security.saas_session_manager import SaaSSessionManager

logger = logging.getLogger(__name__)


def get_broker_id_context():
    """
    Get broker_id from session if available.
    Returns broker_id or None if not in request context or not authenticated.
    """
    if has_request_context():
        try:
            return SaaSSessionManager.get_broker_id()
        except Exception:
            return None
    return None


def log_with_broker_id(level, message, broker_id=None, **kwargs):
    """
    Log message with broker_id context.
    
    Args:
        level: Logging level (logging.INFO, logging.ERROR, etc.)
        message: Log message
        broker_id: Optional broker_id (auto-detected from session if not provided)
        **kwargs: Additional keyword arguments for logging
    """
    # Get broker_id if not provided
    if broker_id is None:
        broker_id = get_broker_id_context()
    
    # Format message with broker_id context
    if broker_id:
        formatted_message = f"[broker_id: {broker_id}] {message}"
    else:
        formatted_message = f"[broker_id: unknown] {message}"
    
    # Log with appropriate level
    logger.log(level, formatted_message, **kwargs)


def info(message, broker_id=None, **kwargs):
    """Log info message with broker_id context"""
    log_with_broker_id(logging.INFO, message, broker_id, **kwargs)


def error(message, broker_id=None, **kwargs):
    """Log error message with broker_id context"""
    log_with_broker_id(logging.ERROR, message, broker_id, **kwargs)


def warning(message, broker_id=None, **kwargs):
    """Log warning message with broker_id context"""
    log_with_broker_id(logging.WARNING, message, broker_id, **kwargs)


def debug(message, broker_id=None, **kwargs):
    """Log debug message with broker_id context"""
    log_with_broker_id(logging.DEBUG, message, broker_id, **kwargs)
