#!/usr/bin/env python3
"""
Test script to verify Azure Blob Storage logging is working
Run this in Azure App Service to diagnose logging issues
"""
import os
import sys
import logging
from datetime import date

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("Azure Blob Storage Logging Diagnostic")
print("=" * 60)
print()

# Check environment variables
print("1. Checking Environment Variables:")
print("-" * 40)
azure_blob_storage_key = os.getenv('AzureBlobStorageKey')
azure_blob_account_name = os.getenv('AZURE_BLOB_ACCOUNT_NAME')
azure_blob_container_name = os.getenv('AZURE_BLOB_CONTAINER_NAME')
azure_blob_logging_enabled = os.getenv('AZURE_BLOB_LOGGING_ENABLED', 'False').lower()

print(f"  AzureBlobStorageKey: {'SET' if azure_blob_storage_key else 'NOT SET'}")
print(f"  AZURE_BLOB_ACCOUNT_NAME: {azure_blob_account_name if azure_blob_account_name else 'NOT SET'}")
print(f"  AZURE_BLOB_CONTAINER_NAME: {azure_blob_container_name if azure_blob_container_name else 'NOT SET'}")
print(f"  AZURE_BLOB_LOGGING_ENABLED: {azure_blob_logging_enabled}")
print()

# Check config
print("2. Checking Configuration:")
print("-" * 40)
try:
    from src.config import (
        AZURE_BLOB_CONNECTION_STRING,
        AZURE_BLOB_CONTAINER_NAME,
        AZURE_BLOB_LOGGING_ENABLED
    )
    print(f"  Connection String: {'SET' if AZURE_BLOB_CONNECTION_STRING else 'NOT SET'}")
    print(f"  Container Name: {AZURE_BLOB_CONTAINER_NAME if AZURE_BLOB_CONTAINER_NAME else 'NOT SET'}")
    print(f"  Logging Enabled: {AZURE_BLOB_LOGGING_ENABLED}")
    if AZURE_BLOB_CONNECTION_STRING:
        # Mask the key for security
        conn_str = AZURE_BLOB_CONNECTION_STRING
        if 'AccountKey=' in conn_str:
            parts = conn_str.split('AccountKey=')
            if len(parts) > 1:
                key_part = parts[1].split(';')[0]
                masked = conn_str.replace(key_part, '***MASKED***')
                print(f"  Connection String (masked): {masked}")
except Exception as e:
    print(f"  ERROR loading config: {e}")
print()

# Test Azure Blob Storage connection
print("3. Testing Azure Blob Storage Connection:")
print("-" * 40)
try:
    from azure.storage.blob import BlobServiceClient
    
    if AZURE_BLOB_CONNECTION_STRING and AZURE_BLOB_CONTAINER_NAME:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_BLOB_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_BLOB_CONTAINER_NAME)
        
        # Check if container exists
        exists = container_client.exists()
        print(f"  Container exists: {exists}")
        
        if not exists:
            print("  Creating container...")
            container_client.create_container()
            print("  Container created successfully")
        
        # List blobs
        print("  Listing blobs in container:")
        blobs = list(container_client.list_blobs())
        print(f"  Found {len(blobs)} blob(s)")
        for blob in blobs[:5]:  # Show first 5
            print(f"    - {blob.name} ({blob.size} bytes)")
        if len(blobs) > 5:
            print(f"    ... and {len(blobs) - 5} more")
    else:
        print("  SKIPPED: Connection string or container name not set")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    print(traceback.format_exc())
print()

# Test logging setup
print("4. Testing Logging Setup:")
print("-" * 40)
try:
    from src.environment import setup_azure_blob_logging
    
    blob_handler, blob_path = setup_azure_blob_logging(account_name="TEST_ACCOUNT", logger_name='test_logger')
    
    if blob_handler:
        print(f"  ✓ Blob handler created successfully")
        print(f"  Blob path: {blob_path}")
        
        # Create test logger
        test_logger = logging.getLogger('test_logger')
        test_logger.setLevel(logging.INFO)
        
        # Write test log
        print("  Writing test log message...")
        test_logger.info("TEST: This is a test log message from diagnostic script")
        
        # Force flush
        print("  Flushing logs to Azure Blob Storage...")
        blob_handler.flush()
        
        # Wait a moment
        import time
        time.sleep(2)
        
        # Verify blob was created
        try:
            blob_client = container_client.get_blob_client(blob_path)
            if blob_client.exists():
                content = blob_client.download_blob().readall().decode('utf-8')
                print(f"  ✓ Blob created successfully!")
                print(f"  Blob size: {len(content)} bytes")
                print(f"  First 200 chars: {content[:200]}")
            else:
                print(f"  ✗ Blob does not exist yet (may need to wait for flush)")
        except Exception as e:
            print(f"  ERROR checking blob: {e}")
    else:
        print("  ✗ Blob handler not created")
        print("  Check environment variables and configuration")
except Exception as e:
    print(f"  ERROR: {e}")
    import traceback
    print(traceback.format_exc())
print()

print("=" * 60)
print("Diagnostic Complete")
print("=" * 60)

