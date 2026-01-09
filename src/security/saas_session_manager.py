"""
SaaS Session Management Module
Provides secure, server-side session management for multi-tenant Flask applications.
"""

from flask import session
from datetime import datetime, timedelta
import hashlib
import platform
import uuid
import logging

logger = logging.getLogger(__name__)


class SaaSSessionManager:
    """
    Server-side session management for multi-user, multi-device SaaS applications.
    
    Features:
    - Credentials stored in Flask session (server-side), never in browser
    - Multi-device support: Each device/browser gets its own independent session
    - Multi-user support: Multiple users can use the application simultaneously
    - Automatic expiration: Sessions expire after 24 hours of inactivity
    - Device identification: Unique device ID generation for tracking
    """
    
    # Session keys
    SESSION_API_KEY = 'saas_api_key'
    SESSION_API_SECRET = 'saas_api_secret'
    SESSION_ACCESS_TOKEN = 'saas_access_token'
    SESSION_REQUEST_TOKEN = 'saas_request_token'
    SESSION_USER_ID = 'saas_user_id'
    SESSION_BROKER_ID = 'saas_broker_id'
    SESSION_EMAIL = 'saas_email'
    SESSION_FULL_NAME = 'saas_full_name'
    SESSION_DEVICE_ID = 'saas_device_id'
    SESSION_EXPIRES_AT = 'saas_expires_at'
    SESSION_AUTHENTICATED = 'saas_authenticated'
    
    @staticmethod
    def store_credentials(
        api_key: str,
        api_secret: str,
        access_token: str,
        request_token: str = None,
        user_id: str = None,
        broker_id: str = None,
        email: str = None,
        full_name: str = None,
        device_id: str = None
    ):
        """
        Store credentials in server-side session.
        
        Args:
            api_key: API key
            api_secret: API secret
            access_token: Access token
            request_token: Request token (optional)
            user_id: User ID (optional)
            broker_id: Broker ID (optional, defaults to api_key)
            email: User email (optional)
            full_name: User full name (optional)
            device_id: Device ID (optional, auto-generated if not provided)
        """
        # Use broker_id if provided, otherwise use api_key
        broker_id = broker_id or api_key
        
        # Generate device ID if not provided
        if not device_id:
            device_id = SaaSSessionManager.generate_device_id()
        
        # Set session as permanent (required for expiration)
        session.permanent = True
        
        # Store credentials
        session[SaaSSessionManager.SESSION_API_KEY] = api_key
        session[SaaSSessionManager.SESSION_API_SECRET] = api_secret
        session[SaaSSessionManager.SESSION_ACCESS_TOKEN] = access_token
        if request_token:
            session[SaaSSessionManager.SESSION_REQUEST_TOKEN] = request_token
        if user_id:
            session[SaaSSessionManager.SESSION_USER_ID] = user_id
        session[SaaSSessionManager.SESSION_BROKER_ID] = broker_id
        if email:
            session[SaaSSessionManager.SESSION_EMAIL] = email
        if full_name:
            session[SaaSSessionManager.SESSION_FULL_NAME] = full_name
        session[SaaSSessionManager.SESSION_DEVICE_ID] = device_id
        session[SaaSSessionManager.SESSION_AUTHENTICATED] = True
        
        # Set expiration (24 hours from now)
        expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
        session[SaaSSessionManager.SESSION_EXPIRES_AT] = expires_at
        
        logger.info(f"[SESSION] Credentials stored for broker_id={broker_id}, device_id={device_id}")
    
    @staticmethod
    def get_credentials() -> dict:
        """
        Get all credentials from server session.
        
        Returns:
            Dict with keys: api_key, api_secret, access_token, request_token,
            user_id, broker_id, email, full_name, device_id, authenticated
        """
        return {
            'api_key': session.get(SaaSSessionManager.SESSION_API_KEY),
            'api_secret': session.get(SaaSSessionManager.SESSION_API_SECRET),
            'access_token': session.get(SaaSSessionManager.SESSION_ACCESS_TOKEN),
            'request_token': session.get(SaaSSessionManager.SESSION_REQUEST_TOKEN),
            'user_id': session.get(SaaSSessionManager.SESSION_USER_ID),
            'broker_id': session.get(SaaSSessionManager.SESSION_BROKER_ID),
            'email': session.get(SaaSSessionManager.SESSION_EMAIL),
            'full_name': session.get(SaaSSessionManager.SESSION_FULL_NAME),
            'device_id': session.get(SaaSSessionManager.SESSION_DEVICE_ID),
            'authenticated': session.get(SaaSSessionManager.SESSION_AUTHENTICATED, False)
        }
    
    @staticmethod
    def is_authenticated() -> bool:
        """
        Check if current session is authenticated and not expired.
        
        Returns:
            bool: True if authenticated and not expired, False otherwise
        """
        if not session.get(SaaSSessionManager.SESSION_AUTHENTICATED, False):
            return False
        
        # Check expiration
        expires_at_str = session.get(SaaSSessionManager.SESSION_EXPIRES_AT)
        if not expires_at_str:
            return False
        
        try:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                logger.info("[SESSION] Session expired")
                SaaSSessionManager.clear_credentials()
                return False
        except (ValueError, TypeError):
            return False
        
        # Check required fields
        if not session.get(SaaSSessionManager.SESSION_ACCESS_TOKEN):
            return False
        
        return True
    
    @staticmethod
    def clear_credentials():
        """Clear all credentials from server session (logout)."""
        session.pop(SaaSSessionManager.SESSION_API_KEY, None)
        session.pop(SaaSSessionManager.SESSION_API_SECRET, None)
        session.pop(SaaSSessionManager.SESSION_ACCESS_TOKEN, None)
        session.pop(SaaSSessionManager.SESSION_REQUEST_TOKEN, None)
        session.pop(SaaSSessionManager.SESSION_USER_ID, None)
        session.pop(SaaSSessionManager.SESSION_BROKER_ID, None)
        session.pop(SaaSSessionManager.SESSION_EMAIL, None)
        session.pop(SaaSSessionManager.SESSION_FULL_NAME, None)
        session.pop(SaaSSessionManager.SESSION_DEVICE_ID, None)
        session.pop(SaaSSessionManager.SESSION_EXPIRES_AT, None)
        session.pop(SaaSSessionManager.SESSION_AUTHENTICATED, None)
        session.permanent = False
        
        logger.info("[SESSION] Credentials cleared")
    
    @staticmethod
    def get_user_id() -> str:
        """Get user ID from session."""
        return session.get(SaaSSessionManager.SESSION_USER_ID)
    
    @staticmethod
    def get_broker_id() -> str:
        """Get broker ID from session."""
        return session.get(SaaSSessionManager.SESSION_BROKER_ID)
    
    @staticmethod
    def get_access_token() -> str:
        """Get access token from session."""
        return session.get(SaaSSessionManager.SESSION_ACCESS_TOKEN)
    
    @staticmethod
    def get_device_id() -> str:
        """Get device ID from session."""
        return session.get(SaaSSessionManager.SESSION_DEVICE_ID)
    
    @staticmethod
    def extend_session():
        """Extend session expiration time by 24 hours."""
        if SaaSSessionManager.is_authenticated():
            expires_at = (datetime.now() + timedelta(hours=24)).isoformat()
            session[SaaSSessionManager.SESSION_EXPIRES_AT] = expires_at
            session.permanent = True
            logger.debug("[SESSION] Session extended")
    
    @staticmethod
    def generate_device_id() -> str:
        """
        Generate a unique device ID based on MAC address and system info.
        
        Returns:
            str: 16-character hex hash
        """
        try:
            # Get MAC address
            mac = ':'.join(['{:02x}'.format((uuid.getnode() >> elements) & 0xff) 
                           for elements in range(0, 8*6, 8)][::-1])
            
            # Get system info
            system_info = f"{platform.system()}_{platform.machine()}_{mac}"
            
            # Generate hash
            device_hash = hashlib.md5(system_info.encode()).hexdigest()[:16]
            
            return device_hash
        except Exception as e:
            logger.warning(f"[SESSION] Could not generate device ID: {e}, using random UUID")
            return uuid.uuid4().hex[:16]
