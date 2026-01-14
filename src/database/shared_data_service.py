"""
Shared Data Service
Consolidates frequently accessed data queries with caching.
Reduces redundant database queries by providing cached access to common data.
Adapted from disciplined-Trader for Strangle10Points strategy
"""
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from .models import DatabaseManager, Position, Trade, DailyStats
from .repository import PositionRepository, TradeRepository, DailyStatsRepository
from .query_cache import get_query_cache
import logging

logger = logging.getLogger(__name__)


class SharedDataService:
    """Centralized service for shared database queries with caching"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.position_repo = PositionRepository(db_manager)
        self.trade_repo = TradeRepository(db_manager)
        self.stats_repo = DailyStatsRepository(db_manager)
        self.cache = get_query_cache()
    
    def get_active_positions_cached(self, broker_id: str, ttl_seconds: float = 2.0) -> List[Position]:
        """
        Get active positions with caching.
        
        Args:
            broker_id: Broker ID for filtering
            ttl_seconds: Cache TTL in seconds (default: 2 seconds)
        
        Returns:
            List of active Position objects
        
        TTL: 2 seconds balances freshness with performance.
        Cache is invalidated on position sync or update.
        """
        cache_key = "active_positions"
        
        # Try cache first
        cached = self.cache.get(cache_key, broker_id)
        if cached is not None:
            return cached
        
        # Cache miss - fetch from database
        logger.debug(f"Cache miss for active_positions, fetching from database")
        session = self.db_manager.get_session()
        try:
            positions = self.position_repo.get_active_positions(session, broker_id)
        finally:
            session.close()
        
        # Cache result
        self.cache.set(cache_key, positions, ttl_seconds, broker_id)
        
        return positions
    
    def get_protected_profit_cached(
        self, 
        broker_id: str,
        trade_date: date, 
        ttl_seconds: float = 5.0
    ) -> float:
        """
        Get protected profit with caching.
        
        Args:
            broker_id: Broker ID for filtering
            trade_date: Date to get protected profit for
            ttl_seconds: Cache TTL in seconds (default: 5 seconds)
        
        Returns:
            Protected profit amount (sum of realized P&L for the date)
        
        TTL: 5 seconds (SUM query is expensive).
        Cache is invalidated on trade creation or deletion.
        """
        cache_key = f"protected_profit:{trade_date.isoformat()}"
        
        # Try cache first
        cached = self.cache.get(cache_key, broker_id)
        if cached is not None:
            return cached
        
        # Cache miss - fetch from database
        logger.debug(f"Cache miss for protected_profit:{trade_date.isoformat()}, fetching from database")
        session = self.db_manager.get_session()
        try:
            from datetime import timedelta
            start_date = trade_date
            end_date = trade_date
            profit = self.trade_repo.get_cumulative_pnl(session, broker_id, start_date, end_date)
        finally:
            session.close()
        
        # Cache result
        self.cache.set(cache_key, profit, ttl_seconds, broker_id)
        
        return profit
    
    def get_trades_by_date_cached(
        self,
        broker_id: str,
        trade_date: date,
        ttl_seconds: float = 10.0
    ) -> List[Trade]:
        """
        Get trades by date with caching.
        
        Args:
            broker_id: Broker ID for filtering
            trade_date: Date to get trades for
            ttl_seconds: Cache TTL in seconds (default: 10 seconds)
        
        Returns:
            List of Trade objects for the date
        
        TTL: 10 seconds (trades don't change frequently).
        Cache is invalidated on trade creation for that date.
        """
        cache_key = f"trades_by_date:{trade_date.isoformat()}"
        
        # Try cache first
        cached = self.cache.get(cache_key, broker_id)
        if cached is not None:
            return cached
        
        # Cache miss - fetch from database
        logger.debug(f"Cache miss for trades_by_date:{trade_date.isoformat()}, fetching from database")
        session = self.db_manager.get_session()
        try:
            trades = self.trade_repo.get_trades_by_date(session, broker_id, trade_date, show_all=False)
        finally:
            session.close()
        
        # Cache result
        self.cache.set(cache_key, trades, ttl_seconds, broker_id)
        
        return trades
    
    def invalidate_position_cache(self, broker_id: Optional[str] = None):
        """Invalidate position-related caches"""
        if broker_id:
            self.cache.invalidate("active_positions", broker_id)
            logger.debug(f"Invalidated position cache for broker: {broker_id}")
    
    def invalidate_trade_cache(self, broker_id: Optional[str] = None, trade_date: Optional[date] = None):
        """
        Invalidate trade-related caches.
        
        Args:
            broker_id: Broker ID (optional)
            trade_date: Specific date to invalidate, or None for all trade caches
        """
        if broker_id:
            if trade_date:
                self.cache.invalidate(f"trades_by_date:{trade_date.isoformat()}", broker_id)
                self.cache.invalidate(f"protected_profit:{trade_date.isoformat()}", broker_id)
                logger.debug(f"Invalidated trade cache for date: {trade_date.isoformat()}")
            else:
                self.cache.invalidate("trades_by_date", broker_id)
                self.cache.invalidate("protected_profit", broker_id)
                logger.debug(f"Invalidated all trade caches for broker: {broker_id}")
    
    def invalidate_stats_cache(self, broker_id: Optional[str] = None):
        """Invalidate daily stats cache"""
        if broker_id:
            self.cache.invalidate("daily_stats_today", broker_id)
            logger.debug(f"Invalidated stats cache for broker: {broker_id}")
    
    def invalidate_all_caches(self, broker_id: Optional[str] = None):
        """Invalidate all caches for current broker"""
        if broker_id:
            self.cache.clear(broker_id)
            logger.info(f"Invalidated all caches for broker: {broker_id}")
