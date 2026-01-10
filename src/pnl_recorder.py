"""
P&L Recorder Module
Saves daily P&L data for non-equity trades to local files
"""
import json
import csv
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Optional


class PnLRecorder:
    """Records and manages daily P&L data"""
    
    def __init__(self, data_dir: str = "pnl_data", broker_id: Optional[str] = None, account: Optional[str] = None):
        """
        Initialize P&L Recorder
        
        Args:
            data_dir: Directory to store P&L data files
            broker_id: Zerodha ID (broker_id) - primary identifier for multi-user isolation
            account: Account identifier (deprecated, use broker_id instead)
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        # Use broker_id as primary identifier, fallback to account for backward compatibility
        self.broker_id = broker_id or account or 'default'
        self.account = self.broker_id  # Keep account for backward compatibility
        # Sanitize broker_id for filename (remove special characters)
        self.safe_account = self._sanitize_account_name(self.broker_id)
        self.json_file = self.data_dir / f"daily_pnl_{self.safe_account}.json"
        self.csv_file = self.data_dir / f"daily_pnl_{self.safe_account}.csv"
    
    def _sanitize_account_name(self, account: str) -> str:
        """
        Sanitize account name for use in filenames
        
        Args:
            account: Account identifier
            
        Returns:
            Sanitized account name safe for filenames
        """
        # Replace special characters with underscores
        import re
        safe_name = re.sub(r'[^\w\-_]', '_', account)
        # Remove multiple consecutive underscores
        safe_name = re.sub(r'_+', '_', safe_name)
        # Remove leading/trailing underscores
        safe_name = safe_name.strip('_')
        return safe_name or 'default'
        
    def get_non_equity_pnl(self, kite) -> Dict:
        """
        Get total P&L for non-equity trades (options, futures) from Kite API
        
        Args:
            kite: KiteConnect instance
            
        Returns:
            Dictionary containing P&L data
        """
        try:
            positions = kite.positions()
            
            if not positions or 'net' not in positions:
                logging.warning("No positions data available")
                return {
                    'total_pnl': 0.0,
                    'non_equity_pnl': 0.0,
                    'equity_pnl': 0.0,
                    'positions_count': 0,
                    'non_equity_positions': []
                }
            
            total_pnl = 0.0
            non_equity_pnl = 0.0
            equity_pnl = 0.0
            non_equity_positions = []
            
            for position in positions['net']:
                if position['quantity'] == 0:
                    continue
                    
                pnl = position.get('pnl', 0.0)
                total_pnl += pnl
                
                # Filter non-equity trades (options, futures)
                # Non-equity segments: NFO (Futures & Options), CDS (Currency Derivatives), MCX (Commodities)
                exchange = position.get('exchange', '')
                product = position.get('product', '')
                
                # Check if it's non-equity (NFO, CDS, MCX)
                if exchange in ['NFO', 'CDS', 'MCX']:
                    non_equity_pnl += pnl
                    non_equity_positions.append({
                        'tradingsymbol': position.get('tradingsymbol', 'N/A'),
                        'exchange': exchange,
                        'product': product,
                        'quantity': position.get('quantity', 0),
                        'pnl': pnl,
                        'pnl_percentage': position.get('pnl_percentage', 0.0),
                        'average_price': position.get('average_price', 0.0),
                        'last_price': position.get('last_price', 0.0)
                    })
                else:
                    equity_pnl += pnl
            
            return {
                'total_pnl': round(total_pnl, 2),
                'non_equity_pnl': round(non_equity_pnl, 2),
                'equity_pnl': round(equity_pnl, 2),
                'positions_count': len(non_equity_positions),
                'non_equity_positions': non_equity_positions
            }
            
        except Exception as e:
            logging.error(f"Error fetching P&L from Kite API: {e}")
            return {
                'total_pnl': 0.0,
                'non_equity_pnl': 0.0,
                'equity_pnl': 0.0,
                'positions_count': 0,
                'non_equity_positions': [],
                'error': str(e)
            }
    
    def save_daily_pnl(self, kite, broker_id: Optional[str] = None, account: Optional[str] = None) -> bool:
        """
        Save today's P&L data to JSON and CSV files (broker_id-wise)
        
        Args:
            kite: KiteConnect instance
            broker_id: Zerodha ID (broker_id) - primary identifier (preferred)
            account: Account identifier (deprecated, use broker_id instead)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Use provided broker_id, then account (for backward compatibility), then instance broker_id
            record_broker_id = broker_id or account or self.broker_id
            record_account = record_broker_id  # Use broker_id as account identifier
            
            # Get P&L data
            pnl_data = self.get_non_equity_pnl(kite)
            
            # Add metadata
            today = date.today()
            timestamp = datetime.now()
            
            daily_record = {
                'date': today.isoformat(),
                'timestamp': timestamp.isoformat(),
                'broker_id': record_broker_id,  # Primary identifier
                'account': record_account,  # Keep for backward compatibility
                'non_equity_pnl': pnl_data['non_equity_pnl'],
                'total_pnl': pnl_data['total_pnl'],
                'equity_pnl': pnl_data['equity_pnl'],
                'positions_count': pnl_data['positions_count'],
                'positions': pnl_data['non_equity_positions']
            }
            
            # Save to JSON
            self._save_to_json(daily_record)
            
            # Save to CSV
            self._save_to_csv(daily_record)
            
            logging.info(f"[P&L RECORD] Saved daily P&L for broker_id '{record_broker_id}': "
                       f"Non-Equity: ₹{pnl_data['non_equity_pnl']:.2f}, "
                       f"Total: ₹{pnl_data['total_pnl']:.2f}, Positions: {pnl_data['positions_count']}")
            logging.info(f"[P&L RECORD] Saved to JSON: {self.json_file}")
            logging.info(f"[P&L RECORD] Saved to CSV: {self.csv_file}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error saving daily P&L: {e}")
            return False
    
    def _save_to_json(self, daily_record: Dict):
        """Save daily record to account-specific JSON file"""
        try:
            # Load existing data
            if self.json_file.exists():
                with open(self.json_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'records': [], 'account': daily_record['account']}
            
            # Check if record for today already exists (for this account)
            today = daily_record['date']
            account = daily_record['account']
            records = data.get('records', [])
            
            # Remove existing record for today and this account
            records = [r for r in records if not (r.get('date') == today and r.get('account') == account)]
            
            # Add new record
            records.append(daily_record)
            
            # Sort by date (newest first)
            records.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            data['records'] = records
            data['account'] = account
            data['last_updated'] = datetime.now().isoformat()
            
            # Save to file
            with open(self.json_file, 'w') as f:
                json.dump(data, f, indent=2)
            
        except Exception as e:
            logging.error(f"Error saving to JSON: {e}")
            raise
    
    def _save_to_csv(self, daily_record: Dict):
        """Save daily record to account-specific CSV file"""
        try:
            # Check if CSV file exists
            file_exists = self.csv_file.exists()
            
            # Prepare CSV row
            row = {
                'date': daily_record['date'],
                'timestamp': daily_record['timestamp'],
                'account': daily_record['account'],
                'non_equity_pnl': daily_record['non_equity_pnl'],
                'total_pnl': daily_record['total_pnl'],
                'equity_pnl': daily_record['equity_pnl'],
                'positions_count': daily_record['positions_count']
            }
            
            # Write to CSV
            if file_exists:
                # Read existing records
                with open(self.csv_file, 'r', newline='') as read_f:
                    reader = csv.DictReader(read_f)
                    existing_records = list(reader)
                
                # Remove existing record for today and this account
                today = row['date']
                account = row['account']
                existing_records = [r for r in existing_records 
                                  if not (r.get('date') == today and r.get('account') == account)]
                
                # Write all records back
                with open(self.csv_file, 'w', newline='') as write_f:
                    writer = csv.DictWriter(write_f, fieldnames=row.keys())
                    writer.writeheader()
                    writer.writerows(existing_records)
                    writer.writerow(row)
            else:
                # Create new file
                with open(self.csv_file, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=row.keys())
                    writer.writeheader()
                    writer.writerow(row)
            
        except Exception as e:
            logging.error(f"Error saving to CSV: {e}")
            raise
    
    def get_historical_pnl(self, start_date: Optional[date] = None, end_date: Optional[date] = None, 
                           broker_id: Optional[str] = None, account: Optional[str] = None) -> List[Dict]:
        """
        Get historical P&L records for this broker_id
        
        Args:
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            broker_id: Zerodha ID filter (preferred, uses instance broker_id if not provided)
            account: Account filter (deprecated, use broker_id instead)
            
        Returns:
            List of P&L records
        """
        try:
            if not self.json_file.exists():
                return []
            
            with open(self.json_file, 'r') as f:
                data = json.load(f)
            
            records = data.get('records', [])
            # Use broker_id if provided, then account (for backward compatibility), then instance broker_id
            filter_broker_id = broker_id or account or self.broker_id
            
            # Filter by broker_id (preferred) or account (backward compatibility)
            records = [r for r in records if (r.get('broker_id') == filter_broker_id or r.get('account') == filter_broker_id)]
            
            # Filter by date range if provided
            if start_date or end_date:
                filtered = []
                for record in records:
                    record_date = datetime.fromisoformat(record['date']).date()
                    if start_date and record_date < start_date:
                        continue
                    if end_date and record_date > end_date:
                        continue
                    filtered.append(record)
                return filtered
            
            return records
            
        except Exception as e:
            logging.error(f"Error reading historical P&L: {e}")
            return []
    
    @classmethod
    def get_all_accounts_pnl(cls, data_dir: str = "pnl_data", start_date: Optional[date] = None, 
                             end_date: Optional[date] = None) -> Dict[str, List[Dict]]:
        """
        Get P&L records for all accounts
        
        Args:
            data_dir: Directory containing P&L data files
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            
        Returns:
            Dictionary mapping account names to their P&L records
        """
        try:
            data_path = Path(data_dir)
            if not data_path.exists():
                return {}
            
            all_accounts_data = {}
            
            # Find all account-specific JSON files
            json_files = list(data_path.glob("daily_pnl_*.json"))
            
            for json_file in json_files:
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    
                    account = data.get('account', 'unknown')
                    records = data.get('records', [])
                    
                    # Filter by date range if provided
                    if start_date or end_date:
                        filtered = []
                        for record in records:
                            record_date = datetime.fromisoformat(record['date']).date()
                            if start_date and record_date < start_date:
                                continue
                            if end_date and record_date > end_date:
                                continue
                            filtered.append(record)
                        records = filtered
                    
                    if records:
                        all_accounts_data[account] = records
                        
                except Exception as e:
                    logging.warning(f"Error reading P&L file {json_file}: {e}")
                    continue
            
            return all_accounts_data
            
        except Exception as e:
            logging.error(f"Error reading all accounts P&L: {e}")
            return {}

