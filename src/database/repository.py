"""
Database Repository for CRUD operations on s001_ prefixed tables
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, func, desc
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
from .models import Position, Trade, DailyStats, DailyPurgeFlag
import logging

logger = logging.getLogger("database")


class PositionRepository:
    """Repository for Position operations"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def create(self, session: Session, position_data: dict) -> Position:
        """Create a new position"""
        position = Position(**position_data)
        session.add(position)
        session.commit()
        session.refresh(position)
        
        # Invalidate position cache
        try:
            from .shared_data_service import SharedDataService
            shared_data = SharedDataService(self.db_manager)
            broker_id = position_data.get('broker_id')
            if broker_id:
                shared_data.invalidate_position_cache(broker_id)
        except Exception as cache_error:
            # Don't fail position creation if cache invalidation fails
            logger.debug(f"Cache invalidation failed (non-critical): {cache_error}")
        
        return position
    
    def get_active_positions(self, session: Session, broker_id: str) -> List[Position]:
        """Get all active positions for a broker"""
        return session.query(Position).filter(
            and_(
                Position.broker_id == broker_id,
                Position.is_active == True
            )
        ).all()
    
    def get_by_instrument(self, session: Session, broker_id: str, instrument_token: str) -> Optional[Position]:
        """Get position by instrument token"""
        return session.query(Position).filter(
            and_(
                Position.broker_id == broker_id,
                Position.instrument_token == instrument_token,
                Position.is_active == True
            )
        ).first()
    
    def update_price(self, session: Session, position_id: int, current_price: float, unrealized_pnl: float):
        """Update position current price and unrealized P&L"""
        position = session.query(Position).filter(Position.id == position_id).first()
        if position:
            position.current_price = current_price
            position.unrealized_pnl = unrealized_pnl
            position.updated_at = datetime.utcnow()
            session.commit()
    
    def deactivate(self, session: Session, position_id: int):
        """Deactivate a position"""
        position = session.query(Position).filter(Position.id == position_id).first()
        if position:
            position.is_active = False
            position.updated_at = datetime.utcnow()
            session.commit()


class TradeRepository:
    """Repository for Trade operations"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def create(self, session: Session, trade_data: dict) -> Trade:
        """Create a new trade"""
        trade = Trade(**trade_data)
        session.add(trade)
        session.commit()
        session.refresh(trade)
        
        # Invalidate trade cache
        try:
            from .shared_data_service import SharedDataService
            shared_data = SharedDataService(self.db_manager)
            broker_id = trade_data.get('broker_id')
            if broker_id:
                # Invalidate cache for the trade date
                if hasattr(trade, 'exit_time') and trade.exit_time:
                    from datetime import date as date_type
                    trade_date = trade.exit_time.date() if isinstance(trade.exit_time, datetime) else trade.exit_time
                    shared_data.invalidate_trade_cache(broker_id, trade_date=trade_date)
        except Exception as cache_error:
            # Don't fail trade creation if cache invalidation fails
            logger.debug(f"Cache invalidation failed (non-critical): {cache_error}")
        
        return trade
    
    def get_trades_by_date(self, session: Session, broker_id: str, trade_date: date, show_all: bool = False) -> List[Trade]:
        """Get trades for a specific date"""
        query = session.query(Trade).filter(
            and_(
                Trade.broker_id == broker_id,
                func.date(Trade.exit_time) == trade_date
            )
        )
        
        if not show_all:
            # Only show today's trades by default
            today = date.today()
            query = query.filter(func.date(Trade.exit_time) == today)
        
        return query.order_by(desc(Trade.exit_time)).all()
    
    def get_all_trades(self, session: Session, broker_id: str, limit: int = 1000) -> List[Trade]:
        """Get all trades for a broker"""
        return session.query(Trade).filter(
            Trade.broker_id == broker_id
        ).order_by(desc(Trade.exit_time)).limit(limit).all()
    
    def get_cumulative_pnl(self, session: Session, broker_id: str, start_date: date, end_date: date) -> float:
        """Get cumulative P&L for a date range"""
        result = session.query(func.sum(Trade.realized_pnl)).filter(
            and_(
                Trade.broker_id == broker_id,
                func.date(Trade.exit_time) >= start_date,
                func.date(Trade.exit_time) <= end_date
            )
        ).scalar()
        return result or 0.0
    
    def purge_day_minus_one_trades(self, session: Session, broker_id: str) -> int:
        """Purge trades from day-1 (yesterday)"""
        yesterday = date.today() - timedelta(days=1)
        deleted_count = session.query(Trade).filter(
            and_(
                Trade.broker_id == broker_id,
                func.date(Trade.exit_time) == yesterday
            )
        ).delete()
        session.commit()
        return deleted_count
    
    def is_purge_done_for_today(self, session: Session, broker_id: str) -> bool:
        """Check if purge has been done today"""
        today = date.today()
        flag = session.query(DailyPurgeFlag).filter(
            and_(
                DailyPurgeFlag.broker_id == broker_id,
                func.date(DailyPurgeFlag.purge_date) == today
            )
        ).first()
        return flag is not None
    
    def mark_purge_done(self, session: Session, broker_id: str, trades_deleted: int):
        """Mark purge as done for today"""
        today = date.today()
        flag = DailyPurgeFlag(
            broker_id=broker_id,
            purge_date=today,
            trades_deleted=trades_deleted
        )
        session.add(flag)
        session.commit()


class DailyStatsRepository:
    """Repository for DailyStats operations"""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def get_or_create(self, session: Session, broker_id: str, stats_date: date) -> DailyStats:
        """Get or create daily stats for a date"""
        stats = session.query(DailyStats).filter(
            and_(
                DailyStats.broker_id == broker_id,
                func.date(DailyStats.date) == stats_date
            )
        ).first()
        
        if not stats:
            stats = DailyStats(
                broker_id=broker_id,
                date=datetime.combine(stats_date, datetime.min.time())
            )
            session.add(stats)
            session.commit()
            session.refresh(stats)
        
        return stats
    
    def update_daily_loss(self, session: Session, broker_id: str, loss_amount: float):
        """Update daily loss used"""
        today = date.today()
        stats = self.get_or_create(session, broker_id, today)
        stats.daily_loss_used = loss_amount
        stats.updated_at = datetime.utcnow()
        session.commit()
    
    def get_daily_loss(self, session: Session, broker_id: str) -> float:
        """Get today's daily loss used"""
        today = date.today()
        stats = session.query(DailyStats).filter(
            and_(
                DailyStats.broker_id == broker_id,
                func.date(DailyStats.date) == today
            )
        ).first()
        return stats.daily_loss_used if stats else 0.0
    
    def get_daily_loss_limit(self, session: Session, broker_id: str) -> float:
        """Get daily loss limit"""
        today = date.today()
        stats = session.query(DailyStats).filter(
            and_(
                DailyStats.broker_id == broker_id,
                func.date(DailyStats.date) == today
            )
        ).first()
        return stats.daily_loss_limit if stats else 5000.0
