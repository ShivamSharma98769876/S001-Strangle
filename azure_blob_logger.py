"""
Azure Blob Storage Logger
A standalone Python program to write logs to Azure Blob Storage.

Usage:
    python azure_blob_logger.py

Configuration:
    Update the Azure credentials in the CONFIGURATION section below.
"""

import logging
import sys
import threading
from datetime import datetime
from azure.storage.blob import BlobServiceClient
from azure.core.exceptions import AzureError
import io
import traceback

# ============================================================================
# CONFIGURATION - Update these values with your Azure Blob Storage credentials
# ============================================================================

# Option 1: Use Connection String (Recommended - easiest to use)
CONNECTION_STRING = "DefaultEndpointsProtocol=https;AccountName=s0001;AccountKey=o1t4swp/blCqs68G8ibe3J2p17FBf5FIGTRqr2iFeif/KsZXPNShmyVMZuBKbFtzU2csyjmPXhhF+AStCPP2xA==;EndpointSuffix=core.windows.net"

# Option 2: Use individual credentials (Alternative method)
STORAGE_ACCOUNT_NAME = "s0001"
STORAGE_ACCOUNT_KEY = "o1t4swp/blCqs68G8ibe3J2p17FBf5FIGTRqr2iFeif/KsZXPNShmyVMZuBKbFtzU2csyjmPXhhF+AStCPP2xA=="
CONTAINER_NAME = "str-container1"

# Blob path where logs will be stored (folder structure in blob)
# Example: "logs/app_logs.log" will create a "logs" folder in the container
BLOB_LOG_PATH = f"logs/app_{datetime.now().strftime('%Y%m%d')}.log"

# ============================================================================
# Azure Blob Storage Handler Class
# ============================================================================

class AzureBlobHandler(logging.Handler):
    """
    Custom logging handler that writes logs to Azure Blob Storage.
    Buffers log messages and uploads them to Azure Blob Storage.
    """
    
    def __init__(self, connection_string, container_name, blob_path):
        super().__init__()
        self.connection_string = connection_string
        self.container_name = container_name
        self.blob_path = blob_path
        self.buffer = io.StringIO()
        self.buffer_lock = threading.Lock()
        
    def emit(self, record):
        """Add log record to buffer"""
        try:
            msg = self.format(record)
            with self.buffer_lock:
                self.buffer.write(msg + '\n')
        except Exception:
            self.handleError(record)
    
    def flush(self):
        """Upload buffered logs to Azure Blob Storage"""
        try:
            with self.buffer_lock:
                if self.buffer.tell() == 0:
                    return  # No content to upload
                
                content = self.buffer.getvalue()
                self.buffer.seek(0)
                self.buffer.truncate(0)
            
            if not content.strip():
                return
            
            # Connect to Azure Blob Storage
            blob_service_client = BlobServiceClient.from_connection_string(
                self.connection_string
            )
            
            # Get blob client
            blob_client = blob_service_client.get_blob_client(
                container=self.container_name,
                blob=self.blob_path
            )
            
            # Check if blob exists and append to it, or create new
            try:
                existing_content = blob_client.download_blob().readall().decode('utf-8')
                new_content = existing_content + content
            except Exception:
                # Blob doesn't exist, create new
                new_content = content
            
            # Upload to Azure Blob Storage
            blob_client.upload_blob(new_content, overwrite=True)
            
            print(f"[SUCCESS] Logs written to Azure Blob: {self.container_name}/{self.blob_path}")
            
        except AzureError as e:
            print(f"[ERROR] Azure Blob Storage error: {e}")
            traceback.print_exc()
        except Exception as e:
            print(f"[ERROR] Failed to write logs to Azure Blob: {e}")
            traceback.print_exc()
    
    def close(self):
        """Flush remaining logs before closing"""
        self.flush()
        super().close()


# ============================================================================
# Main Program
# ============================================================================

def setup_logger(connection_string, container_name, blob_path):
    """
    Setup logger with Azure Blob Storage handler
    """
    # Create logger
    logger = logging.getLogger('AzureBlobLogger')
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create Azure Blob handler
    blob_handler = AzureBlobHandler(
        connection_string=connection_string,
        container_name=container_name,
        blob_path=blob_path
    )
    blob_handler.setLevel(logging.DEBUG)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    blob_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(blob_handler)
    
    # Also add console handler for immediate feedback
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger, blob_handler


def ensure_container_exists(connection_string, container_name):
    """
    Ensure the container exists in Azure Blob Storage
    """
    try:
        blob_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        
        # Try to get container properties (will raise exception if doesn't exist)
        container_client = blob_service_client.get_container_client(container_name)
        try:
            container_client.get_container_properties()
            print(f"[INFO] Container '{container_name}' already exists")
            return True
        except Exception:
            # Container doesn't exist, create it
            print(f"[INFO] Container '{container_name}' does not exist, creating...")
            container_client.create_container()
            print(f"[SUCCESS] Container '{container_name}' created successfully")
            return True
            
    except AzureError as e:
        print(f"[ERROR] Failed to ensure container exists: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        traceback.print_exc()
        return False


def main():
    """
    Main function to demonstrate Azure Blob Storage logging
    """
    print("=" * 70)
    print("Azure Blob Storage Logger")
    print("=" * 70)
    print()
    
    # Determine which connection method to use
    if CONNECTION_STRING and "YOUR_" not in CONNECTION_STRING:
        # Use connection string
        connection_string = CONNECTION_STRING
        container_name = CONTAINER_NAME if "YOUR_" not in CONTAINER_NAME else "logs"
        print("[INFO] Using Connection String method")
    elif (STORAGE_ACCOUNT_NAME and STORAGE_ACCOUNT_KEY and 
          "YOUR_" not in STORAGE_ACCOUNT_NAME and "YOUR_" not in STORAGE_ACCOUNT_KEY):
        # Build connection string from individual credentials
        connection_string = (
            f"DefaultEndpointsProtocol=https;"
            f"AccountName={STORAGE_ACCOUNT_NAME};"
            f"AccountKey={STORAGE_ACCOUNT_KEY};"
            f"EndpointSuffix=core.windows.net"
        )
        container_name = CONTAINER_NAME if "YOUR_" not in CONTAINER_NAME else "logs"
        print("[INFO] Using Individual Credentials method")
    else:
        print("[ERROR] Please configure your Azure Blob Storage credentials!")
        print()
        print("You need to update one of the following in the CONFIGURATION section:")
        print("  1. CONNECTION_STRING (recommended)")
        print("  2. STORAGE_ACCOUNT_NAME, STORAGE_ACCOUNT_KEY, and CONTAINER_NAME")
        print()
        print("Example CONNECTION_STRING format:")
        print("  DefaultEndpointsProtocol=https;AccountName=mystorageaccount;AccountKey=abc123...;EndpointSuffix=core.windows.net")
        return
    
    # Ensure container exists
    print(f"[INFO] Checking container: {container_name}")
    if not ensure_container_exists(connection_string, container_name):
        print("[ERROR] Failed to create/verify container. Please check your credentials.")
        return
    
    # Setup logger
    print(f"[INFO] Setting up logger...")
    logger, blob_handler = setup_logger(connection_string, container_name, BLOB_LOG_PATH)
    
    # Write test logs
    print()
    print("[INFO] Writing test logs to Azure Blob Storage...")
    print("-" * 70)
    
    logger.info("=" * 70)
    logger.info("Azure Blob Storage Logger - Test Session Started")
    logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    logger.debug("This is a DEBUG level message")
    logger.info("This is an INFO level message")
    logger.warning("This is a WARNING level message")
    logger.error("This is an ERROR level message")
    
    logger.info("-" * 70)
    logger.info("Sample log entries:")
    logger.info("  - Application started successfully")
    logger.info("  - Connected to Azure Blob Storage")
    logger.info("  - Configuration loaded")
    logger.info("  - Ready to process requests")
    
    logger.info("-" * 70)
    logger.info(f"Log file location: {container_name}/{BLOB_LOG_PATH}")
    logger.info("=" * 70)
    logger.info("Azure Blob Storage Logger - Test Session Completed")
    logger.info("=" * 70)
    
    # Flush logs to Azure Blob Storage
    print()
    print("[INFO] Flushing logs to Azure Blob Storage...")
    blob_handler.flush()
    
    print()
    print("[SUCCESS] Logs have been written to Azure Blob Storage!")
    print(f"[INFO] Container: {container_name}")
    print(f"[INFO] Blob path: {BLOB_LOG_PATH}")
    print()
    print("You can verify the logs in Azure Portal:")
    print(f"  https://portal.azure.com > Storage Account > Containers > {container_name}")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Program interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)

