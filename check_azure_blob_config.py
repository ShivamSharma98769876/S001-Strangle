#!/usr/bin/env python3
"""
Diagnostic script to check Azure Blob Storage configuration
Run this in Azure App Service SSH/Console to diagnose issues
"""

import os
import sys

print("=" * 60)
print("Azure Blob Storage Configuration Diagnostic")
print("=" * 60)
print()

# Check each required environment variable
required_vars = {
    'AzureBlobStorageKey': 'Azure Blob Storage account key',
    'AZURE_BLOB_ACCOUNT_NAME': 'Storage account name',
    'AZURE_BLOB_CONTAINER_NAME': 'Container name',
    'AZURE_BLOB_LOGGING_ENABLED': 'Enable/disable logging flag'
}

print("1. Checking Environment Variables:")
print("-" * 60)
all_set = True
for var_name, description in required_vars.items():
    value = os.getenv(var_name)
    if value:
        if var_name == 'AzureBlobStorageKey':
            # Don't show the full key, just indicate it's set
            masked_value = value[:10] + "..." + value[-10:] if len(value) > 20 else "***"
            print(f"   ✓ {var_name:30} = {masked_value} (SET)")
        elif var_name == 'AZURE_BLOB_LOGGING_ENABLED':
            is_enabled = value.lower() == 'true'
            status = "✓ ENABLED" if is_enabled else "✗ DISABLED"
            print(f"   {status} {var_name:30} = '{value}'")
            if not is_enabled:
                print(f"      ⚠ WARNING: Must be exactly 'True' (case-sensitive)")
                all_set = False
        else:
            print(f"   ✓ {var_name:30} = '{value}' (SET)")
    else:
        print(f"   ✗ {var_name:30} = NOT SET")
        print(f"      ⚠ MISSING: {description}")
        all_set = False

print()
print("2. Testing Connection String Construction:")
print("-" * 60)

# Try to construct connection string (same logic as config.py)
azure_blob_account_name = os.getenv('AZURE_BLOB_ACCOUNT_NAME', '')
azure_blob_storage_key = os.getenv('AzureBlobStorageKey', '')

if azure_blob_account_name and azure_blob_storage_key:
    connection_string = (
        f"DefaultEndpointsProtocol=https;"
        f"AccountName={azure_blob_account_name};"
        f"AccountKey={azure_blob_storage_key};"
        f"EndpointSuffix=core.windows.net"
    )
    print(f"   ✓ Connection string can be constructed")
    print(f"   ✓ Account name: {azure_blob_account_name}")
    print(f"   ✓ Storage key: {'SET' if azure_blob_storage_key else 'NOT SET'}")
else:
    print(f"   ✗ Connection string CANNOT be constructed")
    if not azure_blob_account_name:
        print(f"      ⚠ Missing: AZURE_BLOB_ACCOUNT_NAME")
    if not azure_blob_storage_key:
        print(f"      ⚠ Missing: AzureBlobStorageKey")

print()
print("3. Checking Logging Status:")
print("-" * 60)

azure_blob_logging_enabled = os.getenv('AZURE_BLOB_LOGGING_ENABLED', 'False')
is_enabled = azure_blob_logging_enabled.lower() == 'true'

if is_enabled:
    print(f"   ✓ Logging is ENABLED")
else:
    print(f"   ✗ Logging is DISABLED")
    print(f"      Current value: '{azure_blob_logging_enabled}'")
    print(f"      Required value: 'True' (exact case)")

print()
print("4. Summary:")
print("-" * 60)

if all_set and is_enabled:
    print("   ✓ All environment variables are set correctly!")
    print("   ✓ Azure Blob Storage logging should be working")
    print()
    print("   If logs still don't appear:")
    print("   1. Wait 30+ seconds for first flush")
    print("   2. Check container: " + os.getenv('AZURE_BLOB_CONTAINER_NAME', 'NOT SET'))
    print("   3. Look for logs in: {account_name}/logs/{account_name}_{date}.log")
else:
    print("   ✗ Configuration is incomplete or incorrect")
    print()
    print("   To fix:")
    print("   1. Go to Azure Portal > App Service > Configuration > Application settings")
    print("   2. Add/Edit the missing or incorrect variables:")
    print()
    if not azure_blob_storage_key:
        print("      Name: AzureBlobStorageKey")
        print("      Value: <your-storage-account-key>")
        print()
    if not azure_blob_account_name:
        print("      Name: AZURE_BLOB_ACCOUNT_NAME")
        print("      Value: s0001strangle")
        print()
    if not os.getenv('AZURE_BLOB_CONTAINER_NAME'):
        print("      Name: AZURE_BLOB_CONTAINER_NAME")
        print("      Value: s0001strangle")
        print()
    if not is_enabled:
        print("      Name: AZURE_BLOB_LOGGING_ENABLED")
        print("      Value: True  (must be exactly 'True', case-sensitive)")
        print()
    print("   3. Click 'Save' and wait for app to restart")

print()
print("=" * 60)

