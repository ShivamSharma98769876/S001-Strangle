"""
Database Models for Positions, Trades, and Daily Statistics
Table names prefixed with 's001_' for this strategy
"""

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime
from typing import Optional
import os
import json
import threading
from pathlib import Path

Base = declarative_base()


class Position(Base):
    """Position data model"""
    __tablename__ = 's001_positions'
    
    id = Column(Integer, primary_key=True)
    broker_id = Column(String, nullable=False, index=True)  # User ID from Kite API
    instrument_token = Column(String, nullable=False, index=True)
    trading_symbol = Column(String, nullable=False)
    exchange = Column(String, nullable=False)
    entry_time = Column(DateTime, nullable=False, default=datetime.utcnow)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float)
    quantity = Column(Integer, nullable=False)
    lot_size = Column(Integer, default=1)
    unrealized_pnl = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    trades = relationship("Trade", back_populates="position")
    
    __table_args__ = (
        Index('idx_broker_instrument_active', 'broker_id', 'instrument_token', 'is_active'),
        Index('idx_broker_active', 'broker_id', 'is_active'),
    )


class Trade(Base):
    """Completed trade data model"""
    __tablename__ = 's001_trades'
    
    id = Column(Integer, primary_key=True)
    broker_id = Column(String, nullable=False, index=True)  # User ID from Kite API
    position_id = Column(Integer, ForeignKey('s001_positions.id'), nullable=True)
    instrument_token = Column(String, nullable=False, index=True)
    trading_symbol = Column(String, nullable=False)
    exchange = Column(String, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)  # Positive for BUY, Negative for SELL
    transaction_type = Column(String, nullable=False, default='BUY')  # 'BUY' or 'SELL'
    realized_pnl = Column(Float, nullable=False)
    is_profit = Column(Boolean, nullable=False)
    exit_type = Column(String, nullable=False)  # 'manual', 'auto_loss_limit', 'auto_trailing_sl'
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    position = relationship("Position", back_populates="trades")
    
    __table_args__ = (
        Index('idx_broker_trade_date', 'broker_id', 'exit_time'),
        Index('idx_broker_trade_symbol', 'broker_id', 'trading_symbol'),
    )


class DailyStats(Base):
    """Daily statistics model"""
    __tablename__ = 's001_daily_stats'
    
    id = Column(Integer, primary_key=True)
    broker_id = Column(String, nullable=False, index=True)  # User ID from Kite API
    date = Column(DateTime, nullable=False, index=True)
    total_realized_pnl = Column(Float, default=0.0)
    total_unrealized_pnl = Column(Float, default=0.0)
    protected_profit = Column(Float, default=0.0)
    number_of_trades = Column(Integer, default=0)
    daily_loss_used = Column(Float, default=0.0)
    daily_loss_limit = Column(Float, default=5000.0)
    loss_limit_hit = Column(Boolean, default=False)
    trading_blocked = Column(Boolean, default=False)
    trailing_sl_active = Column(Boolean, default=False)
    trailing_sl_level = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_broker_date', 'broker_id', 'date', unique=True),
    )


class AuditLog(Base):
    """Audit log for critical operations"""
    __tablename__ = 's001_audit_logs'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    action = Column(String, nullable=False)
    user = Column(String, nullable=True)
    details = Column(String, nullable=True)  # JSON string
    ip_address = Column(String, nullable=True)
    zerodha_client_id = Column(String, nullable=True, index=True)  # Broker ID from Zerodha
    
    __table_args__ = (
        Index('idx_audit_timestamp', 'timestamp'),
        Index('idx_audit_action', 'action'),
    )


class DailyPurgeFlag(Base):
    """Track daily purge status to avoid purging multiple times per day"""
    __tablename__ = 's001_daily_purge_flags'
    
    id = Column(Integer, primary_key=True)
    broker_id = Column(String, nullable=False, index=True)  # User ID from Kite API
    purge_date = Column(DateTime, nullable=False, index=True)  # Date when purge was done
    purge_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)  # Exact time of purge
    trades_deleted = Column(Integer, default=0)  # Number of trades deleted
    
    __table_args__ = (
        Index('idx_broker_purge_date', 'broker_id', 'purge_date', unique=True),
    )


class Candle(Base):
    """Candle/OHLCV data model for storing historical and live candle data"""
    __tablename__ = 's001_candles'
    
    id = Column(Integer, primary_key=True)
    segment = Column(String, nullable=False, index=True)  # 'NIFTY', 'BANKNIFTY', 'SENSEX'
    timestamp = Column(DateTime, nullable=False, index=True)
    interval = Column(String, nullable=False)  # '3minute', '5minute', '15minute', etc.
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, default=0.0)
    is_synthetic = Column(Boolean, default=False)  # True if created from LTP, False if from historical data
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_candle_segment_timestamp', 'segment', 'timestamp', 'interval'),
        Index('idx_candle_timestamp', 'timestamp'),
    )


class DatabaseManager:
    """Database connection and session management (Singleton pattern)"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, db_path: str = None, database_url: str = None):
        """Singleton pattern: ensure only one instance exists"""
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, db_path: str = None, database_url: str = None):
        # Skip initialization if already initialized
        if hasattr(self, '_initialized'):
            return
        
        import logging
        logger = logging.getLogger("database")
        
        # Check for DATABASE_URL environment variable first (highest priority)
        database_url = database_url or os.getenv('DATABASE_URL')
        
        # If not in environment, try to load from config.json
        if not database_url:
            try:
                config_dir = Path(__file__).parent.parent.parent / "config"
                config_file = config_dir / "config.json"
                if config_file.exists():
                    with open(config_file, 'r') as f:
                        config_data = json.load(f)
                    database_url = config_data.get('database_url')
                    if database_url:
                        logger.info("Loaded database_url from config.json")
            except Exception as e:
                logger.warning(f"Could not load database_url from config.json: {e}")
        
        # PostgreSQL is required - no SQLite fallback
        if not database_url:
            error_msg = (
                "DATABASE_URL is required but not found!\n"
                "Please set it in one of the following ways:\n"
                "1. Environment variable: set DATABASE_URL=postgresql://...\n"
                "2. config.json: Add 'database_url' field to config/config.json\n"
                "Example: \"database_url\": \"postgresql://user:pass@host:port/dbname\""
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        # Fix common typo: postgresSQL -> postgresql
        if database_url.startswith('postgresSQL://'):
            database_url = database_url.replace('postgresSQL://', 'postgresql://', 1)
        
        # Validate it's a PostgreSQL URL
        if not database_url.startswith('postgresql://'):
            error_msg = (
                f"Invalid database URL format. Must start with 'postgresql://'\n"
                f"Got: {database_url[:20]}..."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.database_url = database_url
        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600,   # Recycle connections after 1 hour
            echo=False  # Set to True for SQL query logging
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # Mark as initialized
        self._initialized = True
        
        logger.info(f"Database connection initialized (s001 tables)")
    
    def create_tables(self):
        """Create all tables (ignores existing tables/indexes)"""
        try:
            Base.metadata.create_all(bind=self.engine, checkfirst=True)
        except Exception as e:
            # Log but don't fail if tables/indexes already exist
            import logging
            logger = logging.getLogger("database")
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                logger.warning(f"Some tables/indexes already exist (non-critical): {e}")
            else:
                logger.error(f"Error creating tables: {e}")
                raise
    
    def get_session(self):
        """Get a database session"""
        return self.SessionLocal()
    
    def close(self):
        """Close database connection"""
        self.engine.dispose()
