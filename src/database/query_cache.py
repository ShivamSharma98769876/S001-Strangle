"""
Query Cache Manager
Provides centralized caching for frequently accessed database queries.
Thread-safe caching with TTL support for multi-tenant applications.
Adapted from disciplined-Trader for Strangle10Points strategy
"""
import threading
import time
import os
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class QueryCache:
    """Thread-safe query cache with TTL support"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._stats = {
            'hits': 0,
            'misses': 0,
            'invalidations': 0
        }
        # Feature flag to enable/disable caching
        self._enabled = os.getenv('ENABLE_QUERY_CACHE', 'true').lower() == 'true'
    
    def is_enabled(self) -> bool:
        """Check if caching is enabled"""
        return self._enabled
    
    def enable(self):
        """Enable caching"""
        self._enabled = True
        logger.info("Query cache enabled")
    
    def disable(self):
        """Disable caching"""
        self._enabled = False
        self.clear()
        logger.info("Query cache disabled")
    
    def get(self, key: str, broker_id: Optional[str] = None) -> Optional[Any]:
        """Get cached value if not expired"""
        if not self._enabled:
            return None
        
        full_key = self._make_key(key, broker_id)
        with self._lock:
            if full_key in self._cache:
                entry = self._cache[full_key]
                if time.time() < entry['expires_at']:
                    self._stats['hits'] += 1
                    logger.debug(f"Cache HIT: {full_key}")
                    return entry['value']
                else:
                    # Expired, remove it
                    del self._cache[full_key]
                    logger.debug(f"Cache EXPIRED: {full_key}")
            self._stats['misses'] += 1
            logger.debug(f"Cache MISS: {full_key}")
            return None
    
    def set(self, key: str, value: Any, ttl_seconds: float, broker_id: Optional[str] = None):
        """Cache value with TTL"""
        if not self._enabled:
            return
        
        full_key = self._make_key(key, broker_id)
        with self._lock:
            self._cache[full_key] = {
                'value': value,
                'expires_at': time.time() + ttl_seconds,
                'created_at': time.time()
            }
            logger.debug(f"Cache SET: {full_key} (TTL: {ttl_seconds}s)")
    
    def invalidate(self, key_pattern: str, broker_id: Optional[str] = None):
        """Invalidate cache entries matching pattern"""
        if not self._enabled:
            return
        
        full_key_pattern = self._make_key(key_pattern, broker_id)
        with self._lock:
            keys_to_remove = [
                k for k in self._cache.keys()
                if full_key_pattern in k or k.startswith(full_key_pattern)
            ]
            for key in keys_to_remove:
                del self._cache[key]
                self._stats['invalidations'] += 1
            if keys_to_remove:
                logger.debug(f"Cache INVALIDATED: {len(keys_to_remove)} entries matching '{full_key_pattern}'")
    
    def clear(self, broker_id: Optional[str] = None):
        """Clear all cache entries for broker or all entries"""
        with self._lock:
            if broker_id:
                pattern = f"{broker_id}:"
                keys_to_remove = [k for k in self._cache.keys() if k.startswith(pattern)]
                for key in keys_to_remove:
                    del self._cache[key]
                logger.info(f"Cache cleared for broker: {broker_id} ({len(keys_to_remove)} entries)")
            else:
                count = len(self._cache)
                self._cache.clear()
                logger.info(f"Cache cleared: {count} entries removed")
    
    def cleanup_expired(self):
        """Remove expired entries from cache"""
        if not self._enabled:
            return
        
        current_time = time.time()
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if current_time >= v['expires_at']
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def _make_key(self, key: str, broker_id: Optional[str] = None) -> str:
        """Create cache key with broker_id prefix"""
        if broker_id is None:
            # Try to get from context if available
            try:
                from src.security.saas_session_manager import SaaSSessionManager
                broker_id = SaaSSessionManager.get_broker_id() or 'default'
            except ImportError:
                broker_id = 'default'
        return f"{broker_id}:{key}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self._lock:
            # Clean up expired entries before calculating stats
            self.cleanup_expired()
            
            total_requests = self._stats['hits'] + self._stats['misses']
            hit_rate = (self._stats['hits'] / total_requests * 100) if total_requests > 0 else 0
            
            return {
                **self._stats,
                'total_requests': total_requests,
                'hit_rate': round(hit_rate, 2),
                'cache_size': len(self._cache),
                'enabled': self._enabled
            }
    
    def log_stats(self):
        """Log cache statistics"""
        stats = self.get_stats()
        logger.info(
            f"Query Cache Stats - Hits: {stats['hits']}, Misses: {stats['misses']}, "
            f"Hit Rate: {stats['hit_rate']}%, Size: {stats['cache_size']}, "
            f"Invalidations: {stats['invalidations']}, Enabled: {stats['enabled']}"
        )


# Global cache instance
_query_cache = QueryCache()


def get_query_cache() -> QueryCache:
    """Get global query cache instance"""
    return _query_cache
