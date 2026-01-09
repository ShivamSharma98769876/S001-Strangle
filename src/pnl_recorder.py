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
    
    def __init__(self, data_dir: str = "pnl_data"):
        """
        Initialize P&L Recorder
        
        Args:
            data_dir: Directory to store P&L data files
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self.json_file = self.data_dir / "daily_pnl.json"
        self.csv_file = self.data_dir / "daily_pnl.csv"
        
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
    
    def save_daily_pnl(self, kite, account: Optional[str] = None) -> bool:
        """
        Save today's P&L data to JSON and CSV files
        
        Args:
            kite: KiteConnect instance
            account: Account identifier (optional)
            
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            # Get P&L data
            pnl_data = self.get_non_equity_pnl(kite)
            
            # Add metadata
            today = date.today()
            timestamp = datetime.now()
            
            daily_record = {
                'date': today.isoformat(),
                'timestamp': timestamp.isoformat(),
                'account': account or 'default',
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
            
            logging.info(f"[P&L RECORD] Saved daily P&L: Non-Equity: ₹{pnl_data['non_equity_pnl']:.2f}, "
                       f"Total: ₹{pnl_data['total_pnl']:.2f}, Positions: {pnl_data['positions_count']}")
            
            return True
            
        except Exception as e:
            logging.error(f"Error saving daily P&L: {e}")
            return False
    
    def _save_to_json(self, daily_record: Dict):
        """Save daily record to JSON file"""
        try:
            # Load existing data
            if self.json_file.exists():
                with open(self.json_file, 'r') as f:
                    data = json.load(f)
            else:
                data = {'records': []}
            
            # Check if record for today already exists
            today = daily_record['date']
            records = data.get('records', [])
            
            # Remove existing record for today if any
            records = [r for r in records if r.get('date') != today]
            
            # Add new record
            records.append(daily_record)
            
            # Sort by date (newest first)
            records.sort(key=lambda x: x.get('date', ''), reverse=True)
            
            data['records'] = records
            data['last_updated'] = datetime.now().isoformat()
            
            # Save to file
            with open(self.json_file, 'w') as f:
                json.dump(data, f, indent=2)
                
            logging.info(f"[P&L RECORD] Saved to JSON: {self.json_file}")
            
        except Exception as e:
            logging.error(f"Error saving to JSON: {e}")
            raise
    
    def _save_to_csv(self, daily_record: Dict):
        """Save daily record to CSV file"""
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
            with open(self.csv_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=row.keys())
                
                # Write header if file is new
                if not file_exists:
                    writer.writeheader()
                
                # Check if record for today already exists
                if file_exists:
                    # Read existing records
                    with open(self.csv_file, 'r') as read_f:
                        reader = csv.DictReader(read_f)
                        existing_records = list(reader)
                    
                    # Remove existing record for today
                    existing_records = [r for r in existing_records if r.get('date') != row['date']]
                    
                    # Write all records back
                    with open(self.csv_file, 'w', newline='') as write_f:
                        writer = csv.DictWriter(write_f, fieldnames=row.keys())
                        writer.writeheader()
                        writer.writerows(existing_records)
                        writer.writerow(row)
                else:
                    writer.writerow(row) 
            
            logging.info(f"[P&L  RECORD] Saved to CSV: {self.csv_file}")
            
        except Exception as e:
            logging.error(f"Error saving to CSV: {e}")
            raise
    
    def get_historical_pnl(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[Dict]:
        """
        Get historical P&L records
        
        Args:
            start_date: Start date filter (optional)
            end_date: End date filter (optional)
            
        Returns:
            List of P&L records
        """
        try:
            if not self.json_file.exists():
                return []
            
            with open(self.json_file, 'r') as f:
                data = json.load(f)
            
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
                return filtered
            
            return records
            
        except Exception as e:
            logging.error(f"Error reading historical P&L: {e}")
            return []

