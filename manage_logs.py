#!/usr/bin/env python3
"""
Log Management Script for Options Trading Bot
"""
import os
import glob
import argparse
from datetime import datetime, timedelta
from src.utils import get_log_directory, cleanup_old_logs

def list_logs():
    """List all log files in the Log directory"""
    log_dir = get_log_directory()
    
    if not os.path.exists(log_dir):
        print("❌ Log directory does not exist")
        return
    
    log_files = glob.glob(os.path.join(log_dir, "*.log"))
    
    if not log_files:
        print("📁 No log files found in Log directory")
        return
    
    print(f"📁 Found {len(log_files)} log file(s) in {log_dir}/")
    print("-" * 80)
    
    for log_file in sorted(log_files, key=os.path.getmtime, reverse=True):
        file_size = os.path.getsize(log_file)
        file_time = datetime.fromtimestamp(os.path.getmtime(log_file))
        file_name = os.path.basename(log_file)
        
        # Convert file size to human readable format
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        
        print(f"📄 {file_name}")
        print(f"   📅 Modified: {file_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"   📊 Size: {size_str}")
        print()

def show_log_stats():
    """Show statistics about log files"""
    log_dir = get_log_directory()
    
    if not os.path.exists(log_dir):
        print("❌ Log directory does not exist")
        return
    
    log_files = glob.glob(os.path.join(log_dir, "*.log"))
    
    if not log_files:
        print("📁 No log files found")
        return
    
    total_size = sum(os.path.getsize(f) for f in log_files)
    oldest_file = min(log_files, key=os.path.getmtime)
    newest_file = max(log_files, key=os.path.getmtime)
    
    oldest_time = datetime.fromtimestamp(os.path.getmtime(oldest_file))
    newest_time = datetime.fromtimestamp(os.path.getmtime(newest_file))
    
    print("📊 Log Files Statistics")
    print("-" * 40)
    print(f"📁 Total files: {len(log_files)}")
    print(f"📊 Total size: {total_size / (1024 * 1024):.2f} MB")
    print(f"📅 Oldest log: {oldest_time.strftime('%Y-%m-%d')}")
    print(f"📅 Newest log: {newest_time.strftime('%Y-%m-%d')}")
    print(f"📅 Date range: {(newest_time - oldest_time).days} days")

def main():
    parser = argparse.ArgumentParser(description='Log Management for Options Trading Bot')
    parser.add_argument('--list', action='store_true', help='List all log files')
    parser.add_argument('--stats', action='store_true', help='Show log statistics')
    parser.add_argument('--cleanup', action='store_true', help='Clean up old log files')
    parser.add_argument('--days', type=int, default=30, help='Days to keep when cleaning up (default: 30)')
    
    args = parser.parse_args()
    
    if not any([args.list, args.stats, args.cleanup]):
        # Default action: list logs
        args.list = True
    
    if args.list:
        list_logs()
    
    if args.stats:
        print()
        show_log_stats()
    
    if args.cleanup:
        print()
        print("🧹 Cleaning up old log files...")
        cleanup_old_logs(args.days)

if __name__ == "__main__":
    main()
