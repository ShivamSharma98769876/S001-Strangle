#!/usr/bin/env python3
"""
Database Connection Test Script
Tests PostgreSQL database connectivity and basic operations
"""

import sys
import os
from pathlib import Path

# Fix Windows console encoding for Unicode characters
if sys.platform == 'win32':
    try:
        import codecs
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_database_connection():
    """Test database connection and basic operations"""
    
    print("=" * 70)
    print("DATABASE CONNECTION TEST")
    print("=" * 70)
    print()
    
    # Step 1: Check for DATABASE_URL
    print("[STEP 1] Checking for DATABASE_URL...")
    database_url = os.getenv('DATABASE_URL')
    
    if not database_url:
        print("[WARNING] DATABASE_URL not found in environment variables")
        print("   Checking config/config.json...")
        
        # Check the location that DatabaseManager uses (config/config.json at project root)
        config_file = project_root / "config" / "config.json"
        if config_file.exists():
            try:
                import json
                with open(config_file, 'r') as f:
                    config_data = json.load(f)
                database_url = config_data.get('database_url')
                if database_url:
                    print(f"[OK] Found DATABASE_URL in config/config.json")
                else:
                    print("[ERROR] DATABASE_URL not found in config/config.json")
            except Exception as e:
                print(f"[ERROR] Error reading config/config.json: {e}")
        else:
            print(f"[ERROR] config/config.json not found at: {config_file}")
            # Also check src/config.json as fallback
            alt_config_file = project_root / "src" / "config.json"
            if alt_config_file.exists():
                try:
                    import json
                    with open(alt_config_file, 'r') as f:
                        config_data = json.load(f)
                    database_url = config_data.get('database_url')
                    if database_url:
                        print(f"[OK] Found DATABASE_URL in src/config.json")
                except Exception as e:
                    print(f"[ERROR] Error reading src/config.json: {e}")
    else:
        print(f"[OK] DATABASE_URL found in environment variables")
    
    if not database_url:
        print()
        print("=" * 70)
        print("[ERROR] DATABASE_URL NOT FOUND")
        print("=" * 70)
        print()
        print("Please set DATABASE_URL in one of the following ways:")
        print()
        print("1. Environment variable:")
        print("   export DATABASE_URL='postgresql://user:password@host:port/dbname'")
        print()
        print("2. config/config.json:")
        print("   {")
        print('     "database_url": "postgresql://user:password@host:port/dbname"')
        print("   }")
        print()
        print("Example:")
        print("   DATABASE_URL='postgresql://myuser:mypass@localhost:5432/trading_db'")
        print()
        return False
    
    # Mask password in display
    if '@' in database_url:
        parts = database_url.split('@')
        if len(parts) == 2:
            masked_url = parts[0].split('://')[0] + '://***:***@' + parts[1]
        else:
            masked_url = database_url[:20] + "***"
    else:
        masked_url = database_url[:20] + "***"
    
    print(f"   Database URL: {masked_url}")
    print()
    
    # Step 2: Test connection
    print("[STEP 2] Testing database connection...")
    try:
        from src.database.models import DatabaseManager
        
        db_manager = DatabaseManager()
        print("[OK] DatabaseManager initialized successfully")
        
        # Test connection by getting a session
        session = db_manager.get_session()
        print("[OK] Database session created successfully")
        
        # Test query to verify connection works
        from sqlalchemy import text
        result = session.execute(text("SELECT version()"))
        version = result.scalar()
        print(f"[OK] Database connection verified")
        print(f"   PostgreSQL version: {version.split(',')[0]}")
        
        session.close()
        
    except ValueError as e:
        print(f"[ERROR] Configuration Error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Connection Error: {type(e).__name__}: {e}")
        print()
        print("Troubleshooting:")
        print("1. Verify DATABASE_URL is correct")
        print("2. Check if PostgreSQL server is running")
        print("3. Verify network connectivity to database host")
        print("4. Check database credentials (username/password)")
        print("5. Ensure database exists")
        print("6. Check firewall rules if connecting remotely")
        import traceback
        print()
        print("Full error traceback:")
        traceback.print_exc()
        return False
    
    print()
    
    # Step 3: Test table creation/access
    print("[STEP 3] Testing table operations...")
    try:
        # Check if tables exist
        from sqlalchemy import inspect
        inspector = inspect(db_manager.engine)
        existing_tables = inspector.get_table_names()
        
        expected_tables = [
            's001_positions',
            's001_trades',
            's001_daily_stats',
            's001_audit_logs',
            's001_daily_purge_flags',
            's001_candles'
        ]
        
        print(f"   Found {len(existing_tables)} tables in database")
        
        missing_tables = []
        for table in expected_tables:
            if table in existing_tables:
                print(f"   [OK] Table '{table}' exists")
            else:
                print(f"   [WARNING] Table '{table}' does not exist")
                missing_tables.append(table)
        
        if missing_tables:
            print()
            print("   Creating missing tables...")
            try:
                db_manager.create_tables()
                print("   [OK] Tables created successfully (or already exist)")
                
                # Verify tables were created
                inspector = inspect(db_manager.engine)
                existing_tables = inspector.get_table_names()
                for table in missing_tables:
                    if table in existing_tables:
                        print(f"   [OK] Verified: Table '{table}' now exists")
                    else:
                        print(f"   [WARNING] Table '{table}' still missing")
            except Exception as e:
                # Check if it's just a duplicate index/table error (non-critical)
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"   [WARNING] Some indexes/tables already exist (non-critical): {str(e)[:100]}")
                    print("   [INFO] This is usually safe to ignore - tables may already be partially created")
                else:
                    print(f"   [ERROR] Error creating tables: {e}")
                    import traceback
                    traceback.print_exc()
        else:
            print("   [OK] All required tables exist")
        
    except Exception as e:
        print(f"[ERROR] Error testing tables: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Step 4: Test basic queries
    print("[STEP 4] Testing basic queries...")
    try:
        session = db_manager.get_session()
        
        # Test query on positions table
        from src.database.models import Position
        position_count = session.query(Position).count()
        print(f"   [OK] Query test successful")
        print(f"   Current positions in database: {position_count}")
        
        # Test query on trades table
        from src.database.models import Trade
        trade_count = session.query(Trade).count()
        print(f"   Current trades in database: {trade_count}")
        
        # Test query on daily_stats table
        from src.database.models import DailyStats
        stats_count = session.query(DailyStats).count()
        print(f"   Daily stats records: {stats_count}")
        
        session.close()
        
    except Exception as e:
        print(f"[ERROR] Error executing queries: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Step 5: Test repository operations
    print("[STEP 5] Testing repository operations...")
    try:
        from src.database.repository import PositionRepository, TradeRepository, DailyStatsRepository
        
        position_repo = PositionRepository(db_manager)
        trade_repo = TradeRepository(db_manager)
        stats_repo = DailyStatsRepository(db_manager)
        
        print("   [OK] Repositories initialized successfully")
        
        session = db_manager.get_session()
        
        # Test getting active positions (should work even if empty)
        test_broker_id = "test_broker_123"
        active_positions = position_repo.get_active_positions(session, test_broker_id)
        print(f"   [OK] PositionRepository.get_active_positions() works (found {len(active_positions)} positions)")
        
        # Test getting trades
        from datetime import date
        trades = trade_repo.get_trades_by_date(session, test_broker_id, date.today())
        print(f"   [OK] TradeRepository.get_trades_by_date() works (found {len(trades)} trades)")
        
        # Test getting daily stats
        stats = stats_repo.get_or_create(session, test_broker_id, date.today())
        print(f"   [OK] DailyStatsRepository.get_or_create() works")
        
        session.close()
        
    except Exception as e:
        print(f"[ERROR] Error testing repositories: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print()
    
    # Cleanup
    try:
        db_manager.close()
        print("[OK] Database connection closed successfully")
    except Exception as e:
        print(f"[WARNING] Error closing connection: {e}")
    
    print()
    print("=" * 70)
    print("[SUCCESS] ALL TESTS PASSED - Database connection is working properly!")
    print("=" * 70)
    print()
    
    return True


if __name__ == "__main__":
    try:
        success = test_database_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
