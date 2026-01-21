"""
Config Monitor Module for Real-time Parameter Updates
Monitors config.py for changes and auto-reloads parameters without system restart
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import json
import copy

class ConfigChangeHandler(FileSystemEventHandler):
    """Handles config file changes and triggers reload"""
    
    def __init__(self, config_monitor):
        self.config_monitor = config_monitor
        self.last_modified = 0
        
    def on_modified(self, event):
        if event.is_directory:
            return
            
        # Check if it's the config file
        if event.src_path.endswith('config.py'):
            current_time = time.time()
            # Avoid multiple triggers for same change
            if current_time - self.last_modified > 1:
                self.last_modified = current_time
                logging.info(f"[CONFIG MONITOR] Config file changed: {event.src_path}")
                self.config_monitor.reload_config()

class ConfigMonitor:
    """Main config monitoring class with auto-reload functionality"""
    
    def __init__(self, config_path='config.py'):
        self.config_path = config_path
        self.observer = None
        self.is_monitoring = False
        self.config_backup = {}
        self.config_history = []
        self.max_history = 50  # Keep last 50 config changes
        
        # Parameters to monitor for changes
        self.monitored_params = [
            'VIX_HEDGE_POINTS_CANDR',
            'HEDGE_TRIGGER_POINTS_STRANGLE', 
            'TARGET_DELTA_LOW',
            'TARGET_DELTA_HIGH',
            'VIX_DELTA_LOW',
            'VIX_DELTA_HIGH',
            'VIX_DELTA_THRESHOLD',
            'STOP_LOSS_CONFIG',
            'VWAP_MAX_PRICE_DIFF_PERCENT',
            'DELTA_MONITORING_THRESHOLD',
            'DELTA_MONITORING_THRESHOLD_HIGH_VIX',
            'DELTA_MONITORING_THRESHOLD_LOW_VIX',
            'INITIAL_PROFIT_BOOKING',
            'SECOND_PROFIT_BOOKING'
        ]
        
        # Initialize config backup
        self.backup_current_config()
        
    def start_monitoring(self):
        """Start monitoring config file for changes"""
        if self.is_monitoring:
            logging.warning("[CONFIG MONITOR] Already monitoring config file")
            return
            
        try:
            # Create observer and event handler
            self.observer = Observer()
            event_handler = ConfigChangeHandler(self)
            
            # Watch the directory containing config.py
            config_dir = os.path.dirname(os.path.abspath(self.config_path))
            self.observer.schedule(event_handler, config_dir, recursive=False)
            
            # Start monitoring
            self.observer.start()
            self.is_monitoring = True
            
            logging.info(f"[CONFIG MONITOR] Started monitoring: {self.config_path}")
            logging.info(f"[CONFIG MONITOR] Monitored parameters: {', '.join(self.monitored_params)}")
            
        except Exception as e:
            logging.error(f"[CONFIG MONITOR] Failed to start monitoring: {e}")
            
    def stop_monitoring(self):
        """Stop monitoring config file"""
        if self.observer and self.is_monitoring:
            self.observer.stop()
            self.observer.join()
            self.is_monitoring = False
            logging.info("[CONFIG MONITOR] Stopped monitoring config file")
            
    def backup_current_config(self):
        """Backup current config values"""
        try:
            # Import current config
            if os.path.exists(self.config_path):
                # Clear any existing config imports
                if 'config' in sys.modules:
                    del sys.modules['config']
                    
                # Import fresh config
                import importlib.util
                spec = importlib.util.spec_from_file_location("config", self.config_path)
                config_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config_module)
                
                # Backup monitored parameters
                self.config_backup = {}
                for param in self.monitored_params:
                    if hasattr(config_module, param):
                        self.config_backup[param] = getattr(config_module, param)
                        
                logging.info(f"[CONFIG MONITOR] Backed up {len(self.config_backup)} parameters")
                
        except Exception as e:
            logging.error(f"[CONFIG MONITOR] Failed to backup config: {e}")
            
    def reload_config(self):
        """Reload config and update global variables"""
        try:
            # Backup current values before reload
            old_config = copy.deepcopy(self.config_backup)
            
            # Clear config module from cache
            if 'config' in sys.modules:
                del sys.modules['config']
                
            # Reload config
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", self.config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            
            # Check for changes in monitored parameters
            changes = {}
            for param in self.monitored_params:
                if hasattr(config_module, param):
                    new_value = getattr(config_module, param)
                    old_value = self.config_backup.get(param)
                    
                    # Only consider it a change if:
                    # 1. Values are actually different
                    # 2. Both values are not None/undefined
                    # 3. The change is meaningful (not just type conversion)
                    if (new_value != old_value and 
                        new_value is not None and old_value is not None and
                        str(new_value) != str(old_value)):
                        changes[param] = {
                            'old': old_value,
                            'new': new_value
                        }
                        
            # Update backup with new values
            self.config_backup = {}
            for param in self.monitored_params:
                if hasattr(config_module, param):
                    self.config_backup[param] = getattr(config_module, param)
                    
            # Log changes
            if changes:
                self.log_config_changes(changes)
                
                # Update global variables in main strategy
                self.update_global_variables(config_module)
                
                logging.info(f"[CONFIG MONITOR] Reloaded config with {len(changes)} changes")
            else:
                logging.info("[CONFIG MONITOR] Config reloaded - no monitored parameters changed")
                
        except Exception as e:
            logging.error(f"[CONFIG MONITOR] Failed to reload config: {e}")
            # Attempt rollback on error
            self.rollback_config(old_config)
            
    def log_config_changes(self, changes):
        """Log config changes with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for param, change in changes.items():
            change_log = {
                'timestamp': timestamp,
                'parameter': param,
                'old_value': change['old'],
                'new_value': change['new']
            }
            
            self.config_history.append(change_log)
            
            # Keep only last max_history entries
            if len(self.config_history) > self.max_history:
                self.config_history = self.config_history[-self.max_history:]
                
            # Format values for logging
            old_str = self._format_value_for_log(change['old'])
            new_str = self._format_value_for_log(change['new'])
            logging.info(f"[CONFIG CHANGE] {param}: {old_str} → {new_str}")
            
    def _format_value_for_log(self, value):
        """Format value for logging display"""
        if value is None:
            return 'None'
        elif isinstance(value, dict):
            return f"dict({len(value)} keys)"
        elif isinstance(value, (list, tuple)):
            return f"{type(value).__name__}({len(value)} items)"
        else:
            return str(value)
            
    def update_global_variables(self, config_module):
        """Update global variables in the main strategy"""
        try:
            # Get the main module (strategy file)
            main_module = sys.modules.get('__main__')
            if main_module:
                for param in self.monitored_params:
                    if hasattr(config_module, param):
                        new_value = getattr(config_module, param)
                        setattr(main_module, param, new_value)
                        
            logging.info("[CONFIG MONITOR] Updated global variables in main strategy")
            
        except Exception as e:
            logging.error(f"[CONFIG MONITOR] Failed to update global variables: {e}")
            
    def rollback_config(self, old_config):
        """Rollback to previous config values"""
        try:
            logging.warning("[CONFIG MONITOR] Attempting rollback due to config reload error")
            
            # Restore old values
            self.config_backup = old_config
            
            # Update global variables with old values
            main_module = sys.modules.get('__main__')
            if main_module:
                for param, value in old_config.items():
                    setattr(main_module, param, value)
                    
            logging.info("[CONFIG MONITOR] Rollback completed")
            
        except Exception as e:
            logging.error(f"[CONFIG MONITOR] Rollback failed: {e}")
            
    def get_config_history(self):
        """Get configuration change history"""
        return self.config_history
        
    def get_current_config(self):
        """Get current configuration values"""
        return self.config_backup.copy()
        
    def validate_parameter(self, param_name, value):
        """Validate parameter value before applying"""
        # Convert string to appropriate type if needed
        try:
            if isinstance(value, str):
                if '.' in value:
                    value = float(value)
                else:
                    value = int(value)
        except (ValueError, TypeError):
            logging.error(f"[CONFIG VALIDATION] Failed to convert value '{value}' for parameter '{param_name}'")
            return False
            
        validation_rules = {
            'VIX_HEDGE_POINTS_CANDR': lambda x: isinstance(x, (int, float)) and 0 < x <= 100,
            'HEDGE_TRIGGER_POINTS_STRANGLE': lambda x: isinstance(x, (int, float)) and 0 < x <= 100,
            'TARGET_DELTA_LOW': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'TARGET_DELTA_HIGH': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'VIX_DELTA_LOW': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'VIX_DELTA_HIGH': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'VIX_DELTA_THRESHOLD': lambda x: isinstance(x, (int, float)) and 0 < x <= 100,
            'DELTA_MONITORING_THRESHOLD': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'DELTA_MONITORING_THRESHOLD_HIGH_VIX': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'DELTA_MONITORING_THRESHOLD_LOW_VIX': lambda x: isinstance(x, (int, float)) and 0 < x < 1,
            'INITIAL_PROFIT_BOOKING': lambda x: isinstance(x, (int, float)) and 0 < x <= 200,
            'SECOND_PROFIT_BOOKING': lambda x: isinstance(x, (int, float)) and 0 < x <= 200
        }
        
        if param_name in validation_rules:
            result = validation_rules[param_name](value)
            logging.info(f"[CONFIG VALIDATION] {param_name} = {value} (type: {type(value)}) -> {'VALID' if result else 'INVALID'}")
            return result
        return True  # No validation rule = assume valid
        
    def export_config_history(self, filename='config_history.json'):
        """Export configuration history to JSON file"""
        try:
            with open(filename, 'w') as f:
                json.dump(self.config_history, f, indent=2, default=str)
            logging.info(f"[CONFIG MONITOR] Exported history to {filename}")
        except Exception as e:
            logging.error(f"[CONFIG MONITOR] Failed to export history: {e}")

# Global config monitor instance
config_monitor = None

def initialize_config_monitor(config_path='config.py'):
    """Initialize the global config monitor"""
    global config_monitor
    config_monitor = ConfigMonitor(config_path)
    return config_monitor

def start_config_monitoring():
    """Start config monitoring"""
    global config_monitor
    if config_monitor:
        config_monitor.start_monitoring()
    else:
        logging.error("[CONFIG MONITOR] Config monitor not initialized")

def stop_config_monitoring():
    """Stop config monitoring"""
    global config_monitor
    if config_monitor:
        config_monitor.stop_monitoring()

def get_config_monitor():
    """Get the global config monitor instance"""
    return config_monitor
