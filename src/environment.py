"""
Environment detection and configuration utilities
Supports both local and Azure cloud deployments
"""
import os
import logging
from pathlib import Path
import io
import threading
from datetime import date, datetime, timezone, timedelta
import sys

# ============================================================================
# IST TIMEZONE CONFIGURATION
# ============================================================================
# India Standard Time (IST) is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_time():
    """Get current time in IST timezone
    
    IMPORTANT: This function properly converts UTC time to IST.
    Azure systems typically run in UTC, so we need to convert UTC -> IST.
    """
    # Get current UTC time
    utc_now = datetime.now(timezone.utc)
    # Convert to IST
    ist_now = utc_now.astimezone(IST)
    return ist_now

def format_ist_time(dt=None):
    """Format datetime in IST format: hh:mm:ss AM/PM"""
    if dt is None:
        dt = get_ist_time()
    elif dt.tzinfo is None:
        # If no timezone, assume UTC and convert to IST
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    return dt.strftime('%I:%M:%S %p').lower()

def format_ist_datetime(dt=None):
    """Format datetime in IST format: YYYY-MM-DD hh:mm:ss"""
    if dt is None:
        dt = get_ist_time()
    elif dt.tzinfo is None:
        # If no timezone, assume UTC and convert to IST
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    return dt.strftime('%Y-%m-%d %H:%M:%S')

# ============================================================================
# AZURE BLOB STORAGE CONFIGURATION
# ============================================================================
# All Azure Blob Storage parameters are read from environment variables
# Set these in Azure Portal > App Service > Configuration > Application settings:
#   - AzureBlobStorageKey (or AZURE_BLOB_STORAGE_KEY)
#   - AZURE_BLOB_ACCOUNT_NAME
#   - AZURE_BLOB_CONTAINER_NAME
#   - AZURE_BLOB_LOGGING_ENABLED (true/yes/1/on to enable)
# 
# These values are loaded from src.config which reads from environment variables

# Safe formatter that handles Unicode encoding errors gracefully and uses IST timezone
class ISTFormatter(logging.Formatter):
    """Formatter that uses IST timezone for timestamps"""
    converter = lambda *args: get_ist_time().timetuple()
    
    def formatTime(self, record, datefmt=None):
        """Override formatTime to use IST"""
        ct = get_ist_time()
        if datefmt:
            s = ct.strftime(datefmt)
        else:
            s = ct.strftime('%Y-%m-%d %H:%M:%S')
            # Add milliseconds
            s = f"{s},{int(record.msecs):03d}"
        return s

class SafeFormatter(ISTFormatter):
    """Formatter that safely handles Unicode characters and uses IST timezone"""
    def format(self, record):
        try:
            return super().format(record)
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            # Fallback: replace problematic characters
            try:
                msg = record.getMessage()
                # Replace Unicode characters that can't be encoded
                safe_msg = msg.encode('ascii', 'replace').decode('ascii')
                record.msg = safe_msg
                return super().format(record)
            except Exception:
                # Last resort: return basic message with IST time
                ist_time = format_ist_datetime()
                return f"{ist_time} - {record.levelname} - {record.name} - {record.getMessage()}"

def is_azure_environment():
    """
    Detect if running in Azure App Service
    """
    # Azure App Service sets WEBSITE_INSTANCE_ID
    # Also check for other Azure-specific environment variables
    azure_indicators = [
        'WEBSITE_INSTANCE_ID',
        'WEBSITE_SITE_NAME',
        'WEBSITE_RESOURCE_GROUP',
        'APPSETTING_WEBSITE_SITE_NAME'
    ]
    return any(os.getenv(var) for var in azure_indicators)

def sanitize_account_name_for_filename(account_name):
    """
    Sanitize account name for use in filenames
    - Extract first name only (first word before space)
    - Replace spaces with underscores
    - Remove or replace special characters that might cause filesystem issues
    - Limit length to avoid filesystem path length issues
    """
    if not account_name:
        return 'TRADING_ACCOUNT'
    
    # Extract first name only (first word before space)
    first_name = account_name.split()[0] if account_name.split() else account_name
    
    # Remove or replace other problematic characters
    # Keep only alphanumeric, underscores, and hyphens
    import re
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', first_name)
    
    # Limit length to 30 characters to avoid filesystem issues
    if len(sanitized) > 30:
        sanitized = sanitized[:30]
    
    return sanitized if sanitized else 'TRADING_ACCOUNT'

def format_date_for_filename(date_obj):
    """
    Format date as YYYYMONDD (e.g., 2025Dec11)
    """
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    return f"{date_obj.year}{month_names[date_obj.month - 1]}{date_obj.day:02d}"

class AzureBlobStorageHandler(logging.Handler):
    """
    Custom logging handler that writes logs to Azure Blob Storage
    Supports both buffered mode (default) and streaming mode (real-time)
    """
    def __init__(self, connection_string, container_name, blob_path, account_name=None, streaming_mode=False, skip_container_check=False):
        super().__init__()
        self.connection_string = connection_string
        self.container_name = container_name
        self.blob_path = blob_path  # Full path including folder structure
        self.account_name = account_name
        self.streaming_mode = streaming_mode  # If True, flush immediately (real-time logs)
        self.buffer = io.StringIO()
        self.buffer_lock = threading.Lock()
        self.flush_interval = 30 if not streaming_mode else 0  # Flush immediately in streaming mode
        import time
        self.last_flush = time.time()
        self.container_checked = False
        # Skip container check during initialization for fast startup (prevents 504 timeout)
        # Container will be checked/created on first write
        if not skip_container_check:
            self._ensure_container_exists()
        else:
            # Defer container check to first write (non-blocking startup)
            self.container_checked = False
        
        if streaming_mode:
            print(f"[AZURE BLOB] Streaming mode ENABLED - logs will be written in real-time")
        else:
            print(f"[AZURE BLOB] Buffered mode - logs will be flushed every {self.flush_interval} seconds")
        
    def _ensure_container_exists(self):
        """Ensure the container exists in Azure Blob Storage"""
        try:
            from azure.storage.blob import BlobServiceClient
            from azure.core.exceptions import (
                ClientAuthenticationError, 
                HttpResponseError, 
                ResourceExistsError,
                ResourceNotFoundError,
                ServiceRequestError
            )
            
            blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
            container_client = blob_service_client.get_container_client(self.container_name)
            
            if container_client.exists():
                print(f"[AZURE BLOB] Container '{self.container_name}' already exists")
            else:
                print(f"[AZURE BLOB] Container '{self.container_name}' does not exist, creating...")
                container_client.create_container()
                print(f"[AZURE BLOB] ✓ Container '{self.container_name}' created successfully")
                
                # Verify container was created
                if container_client.exists():
                    print(f"[AZURE BLOB] ✓✓ Verified: Container '{self.container_name}' exists")
                else:
                    print(f"[AZURE BLOB] ⚠ Warning: Container '{self.container_name}' creation verification failed")
                    
        except ServiceRequestError as dns_error:
            # DNS resolution failure - storage account may not exist or network issue
            error_msg = str(dns_error)
            print(f"[AZURE BLOB] ✗✗✗ DNS/Network Error: Failed to resolve storage account hostname")
            print(f"[AZURE BLOB] Error Details: {error_msg}")
            print(f"[AZURE BLOB] ========================================")
            print(f"[AZURE BLOB] TROUBLESHOOTING:")
            # Get account name from config for error message
            try:
                _, _, _, account_name = _get_azure_blob_config()
                account_name_str = account_name if account_name else "check environment variables"
            except:
                account_name_str = "check environment variables"
            print(f"[AZURE BLOB] 1. Verify storage account name is correct: {account_name_str}")
            print(f"[AZURE BLOB] 2. Check if storage account exists in Azure Portal")
            print(f"[AZURE BLOB] 3. Verify network connectivity to Azure")
            print(f"[AZURE BLOB] 4. Check DNS resolution (storage account may have been deleted or renamed)")
            print(f"[AZURE BLOB] 5. Application will continue without Azure Blob Storage logging")
            print(f"[AZURE BLOB] ========================================")
            # Don't raise - allow application to continue without blob storage
            # This prevents the entire app from failing if blob storage is unavailable
            return
                    
        except ClientAuthenticationError as auth_error:
            print(f"[AZURE BLOB] ✗✗✗ AUTHENTICATION ERROR: Invalid credentials or connection string")
            print(f"[AZURE BLOB] Error Details: {auth_error}")
            print(f"[AZURE BLOB] ========================================")
            print(f"[AZURE BLOB] TROUBLESHOOTING:")
            print(f"[AZURE BLOB] 1. Check your connection string in environment.py")
            # Get account name from config for error message
            try:
                _, _, _, account_name = _get_azure_blob_config()
                account_name_str = account_name if account_name else "check environment variables"
            except:
                account_name_str = "check environment variables"
            print(f"[AZURE BLOB] 2. Verify Storage Account Name: {account_name_str}")
            print(f"[AZURE BLOB] 3. Verify Storage Account Key is correct")
            print(f"[AZURE BLOB] 4. Check if the storage account key has been rotated")
            print(f"[AZURE BLOB] 5. Go to Azure Portal > Storage Account > Access Keys")
            print(f"[AZURE BLOB]    and verify the key matches your connection string")
            print(f"[AZURE BLOB] ========================================")
            raise
            
        except HttpResponseError as http_error:
            error_code = getattr(http_error, 'status_code', 'Unknown')
            error_message = str(http_error)
            print(f"[AZURE BLOB] ✗✗✗ HTTP ERROR ({error_code}): {error_message}")
            print(f"[AZURE BLOB] ========================================")
            print(f"[AZURE BLOB] TROUBLESHOOTING:")
            
            if error_code == 403:
                print(f"[AZURE BLOB] ACCESS DENIED (403):")
                print(f"[AZURE BLOB] 1. Check if your storage account key has proper permissions")
                print(f"[AZURE BLOB] 2. Verify the storage account allows access from your location")
                print(f"[AZURE BLOB] 3. Check Network settings in Azure Portal:")
                print(f"[AZURE BLOB]    Storage Account > Networking > Firewalls and virtual networks")
                print(f"[AZURE BLOB] 4. Ensure 'Allow access from all networks' is enabled (for testing)")
                print(f"[AZURE BLOB] 5. Check if the storage account has IP restrictions")
            elif error_code == 404:
                # Get account name from config for error message
                try:
                    _, _, _, account_name = _get_azure_blob_config()
                    account_name_str = account_name if account_name else "check environment variables"
                except:
                    account_name_str = "check environment variables"
                print(f"[AZURE BLOB] NOT FOUND (404):")
                print(f"[AZURE BLOB] 1. Verify storage account name: {account_name_str}")
                print(f"[AZURE BLOB] 2. Check if the storage account exists in your Azure subscription")
                print(f"[AZURE BLOB] 3. Verify you're using the correct Azure region")
            elif error_code == 409:
                print(f"[AZURE BLOB] CONFLICT (409): Container may already exist or name is invalid")
            else:
                print(f"[AZURE BLOB] 1. Check Azure Portal for storage account status")
                print(f"[AZURE BLOB] 2. Verify network connectivity")
                print(f"[AZURE BLOB] 3. Check Azure Service Health for outages")
            print(f"[AZURE BLOB] ========================================")
            raise
            
        except ResourceExistsError:
            print(f"[AZURE BLOB] Container '{self.container_name}' already exists (ResourceExistsError)")
            
        except ResourceNotFoundError:
            # Get account name from config for error message
            try:
                _, _, _, account_name = _get_azure_blob_config()
                account_name_str = account_name if account_name else "check environment variables"
            except:
                account_name_str = "check environment variables"
            print(f"[AZURE BLOB] ✗✗✗ RESOURCE NOT FOUND:")
            print(f"[AZURE BLOB] Storage account or container not found")
            print(f"[AZURE BLOB] Verify storage account name: {account_name_str}")
            print(f"[AZURE BLOB] Verify container name: {self.container_name}")
            raise
            
        except Exception as e:
            error_type = type(e).__name__
            print(f"[AZURE BLOB] ✗✗✗ UNEXPECTED ERROR ({error_type}): {e}")
            print(f"[AZURE BLOB] ========================================")
            print(f"[AZURE BLOB] TROUBLESHOOTING:")
            print(f"[AZURE BLOB] 1. Check network connectivity to Azure")
            print(f"[AZURE BLOB] 2. Verify storage account is accessible")
            print(f"[AZURE BLOB] 3. Check Azure Portal > Storage Account > Overview")
            print(f"[AZURE BLOB] 4. Verify connection string format is correct")
            print(f"[AZURE BLOB] 5. Check if azure-storage-blob package is installed: pip install azure-storage-blob")
            print(f"[AZURE BLOB] ========================================")
            import traceback
            print(f"[AZURE BLOB] Full traceback: {traceback.format_exc()}")
            raise
    
    def emit(self, record):
        """Emit a log record to the buffer"""
        try:
            msg = self.format(record)
            with self.buffer_lock:
                self.buffer.write(msg + '\n')
                
                # In streaming mode, flush immediately for real-time logs
                if self.streaming_mode:
                    # Flush immediately in streaming mode
                    self._flush_to_blob()
                else:
                    # Buffered mode: flush if buffer is large enough or enough time has passed
                    import time
                    current_time = time.time()
                    if (self.buffer.tell() > 8192 or  # 8KB buffer
                        current_time - self.last_flush > self.flush_interval):
                        self._flush_to_blob()
        except Exception:
            self.handleError(record)
    
    def _flush_to_blob(self, force=False):
        """Flush buffer contents to Azure Blob Storage

        Args:
            force: If True, create blob even if buffer is empty (for initial blob creation)
        """
        # Check container on first flush if it wasn't checked during initialization (fast startup)
        if not self.container_checked:
            try:
                self._ensure_container_exists()
                self.container_checked = True
            except Exception as e:
                # If container check fails, log but continue (non-blocking)
                print(f"[AZURE BLOB] Container check deferred failed: {e}")
                self.container_checked = True  # Mark as checked to prevent retry loops
        
        try:
            with self.buffer_lock:
                # Get current buffer content
                self.buffer.seek(0)
                content = self.buffer.read()
                self.buffer.seek(0)
                self.buffer.truncate(0)
                
                # If buffer is empty and not forcing, skip
                if not content and not force:
                    return
                
                # Ensure we have at least a newline for empty blob creation
                if not content and force:
                    content = "\n"
                
                # Upload to Azure Blob Storage
                from azure.storage.blob import BlobServiceClient
                blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
                blob_client = blob_service_client.get_blob_client(
                    container=self.container_name,
                    blob=self.blob_path
                )
                
                # Append to existing blob or create new one
                existing_content = None
                try:
                    # Try to download existing content and append
                    existing_content = blob_client.download_blob().readall().decode('utf-8')
                    content = existing_content + content
                    print(f"[AZURE BLOB] Appending to existing blob (existing size: {len(existing_content)} bytes)")
                except Exception as download_error:
                    # Blob doesn't exist yet, create new one
                    print(f"[AZURE BLOB] Blob doesn't exist yet, creating new blob: {download_error}")
                
                # Upload the content (this creates the blob if it doesn't exist)
                try:
                    print(f"[AZURE BLOB] Attempting to upload {len(content)} bytes to {self.container_name}/{self.blob_path}")
                    print(f"[AZURE BLOB] Full blob path: {self.blob_path}")
                    print(f"[AZURE BLOB] This will create folder structure: {self.blob_path.split('/')[0]}/logs/")
                    blob_client.upload_blob(content, overwrite=True)
                    print(f"[AZURE BLOB] ✓ Upload successful: {len(content)} bytes uploaded to {self.container_name}/{self.blob_path}")
                    
                    import time
                    self.last_flush = time.time()
                    
                    # Verify blob exists immediately after upload
                    import time as time_module
                    time_module.sleep(0.5)  # Small delay for Azure to propagate
                    
                    verification_attempts = 3
                    blob_exists = False
                    for attempt in range(verification_attempts):
                        try:
                            if blob_client.exists():
                                blob_exists = True
                                print(f"[AZURE BLOB] ✓✓ Verified: Blob exists at {self.container_name}/{self.blob_path} (attempt {attempt + 1})")
                                break
                            else:
                                print(f"[AZURE BLOB] ⚠ Verification attempt {attempt + 1}: Blob not found yet, retrying...")
                                time_module.sleep(1)
                        except Exception as verify_error:
                            print(f"[AZURE BLOB] ⚠ Verification attempt {attempt + 1} failed: {verify_error}")
                            time_module.sleep(1)
                    
                    if not blob_exists:
                        print(f"[AZURE BLOB] ⚠⚠ WARNING: Blob verification failed after {verification_attempts} attempts")
                        print(f"[AZURE BLOB] Container: {self.container_name}, Blob path: {self.blob_path}")
                        print(f"[AZURE BLOB] Full URL would be: https://<account>.blob.core.windows.net/{self.container_name}/{self.blob_path}")
                        
                except Exception as upload_error:
                    error_type = type(upload_error).__name__
                    error_details = f"[AZURE BLOB] ✗✗ UPLOAD FAILED: {error_type}: {str(upload_error)}"
                    print(error_details)
                    
                    # Check for specific Azure errors
                    from azure.core.exceptions import (
                        ClientAuthenticationError,
                        HttpResponseError,
                        ResourceNotFoundError
                    )
                    
                    if isinstance(upload_error, ClientAuthenticationError):
                        print(f"[AZURE BLOB] ========================================")
                        print(f"[AZURE BLOB] AUTHENTICATION ERROR DURING UPLOAD:")
                        print(f"[AZURE BLOB] Your credentials are invalid or expired")
                        print(f"[AZURE BLOB] Action: Update connection string in environment.py")
                        print(f"[AZURE BLOB] ========================================")
                    elif isinstance(upload_error, HttpResponseError):
                        status_code = getattr(upload_error, 'status_code', 'Unknown')
                        print(f"[AZURE BLOB] ========================================")
                        print(f"[AZURE BLOB] HTTP ERROR ({status_code}) DURING UPLOAD:")
                        if status_code == 403:
                            print(f"[AZURE BLOB] ACCESS DENIED: Check container permissions")
                            print(f"[AZURE BLOB] Container: {self.container_name}")
                            print(f"[AZURE BLOB] Blob Path: {self.blob_path}")
                            print(f"[AZURE BLOB] Action: Verify storage account key has write permissions")
                        elif status_code == 404:
                            print(f"[AZURE BLOB] NOT FOUND: Container or blob path issue")
                            print(f"[AZURE BLOB] Container: {self.container_name}")
                            print(f"[AZURE BLOB] Blob Path: {self.blob_path}")
                            print(f"[AZURE BLOB] Action: Verify container exists and path is correct")
                        else:
                            print(f"[AZURE BLOB] Error Code: {status_code}")
                            print(f"[AZURE BLOB] Action: Check Azure Portal for storage account status")
                        print(f"[AZURE BLOB] ========================================")
                    elif isinstance(upload_error, ResourceNotFoundError):
                        print(f"[AZURE BLOB] ========================================")
                        print(f"[AZURE BLOB] RESOURCE NOT FOUND:")
                        print(f"[AZURE BLOB] Container '{self.container_name}' may not exist")
                        print(f"[AZURE BLOB] Action: Container will be created automatically on next attempt")
                        print(f"[AZURE BLOB] ========================================")
                    else:
                        print(f"[AZURE BLOB] ========================================")
                        print(f"[AZURE BLOB] UNEXPECTED ERROR TYPE: {error_type}")
                        print(f"[AZURE BLOB] Container: {self.container_name}")
                        print(f"[AZURE BLOB] Blob Path: {self.blob_path}")
                        print(f"[AZURE BLOB] ========================================")
                    
                    import traceback
                    print(f"[AZURE BLOB] Upload traceback: {traceback.format_exc()}")
                    raise  # Re-raise to be caught by outer exception handler
                
        except Exception as e:
            error_type = type(e).__name__
            error_msg = f"[AZURE BLOB] Error flushing to blob {self.container_name}/{self.blob_path}: {error_type}: {e}"
            print(error_msg)
            
            # Check for connection/network errors
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                print(f"[AZURE BLOB] ========================================")
                print(f"[AZURE BLOB] NETWORK/CONNECTION ERROR:")
                print(f"[AZURE BLOB] Unable to connect to Azure Blob Storage")
                print(f"[AZURE BLOB] Possible causes:")
                print(f"[AZURE BLOB] 1. Network connectivity issues")
                print(f"[AZURE BLOB] 2. Firewall blocking Azure endpoints")
                print(f"[AZURE BLOB] 3. Azure service outage")
                print(f"[AZURE BLOB] Action: Check network connectivity and Azure status")
                print(f"[AZURE BLOB] ========================================")
            
            import traceback
            print(f"[AZURE BLOB] Full traceback: {traceback.format_exc()}")
            
            # Put content back in buffer for retry if we have content
            if 'content' in locals() and content and content != "\n":
                with self.buffer_lock:
                    self.buffer.seek(0, 2)  # Seek to end
                    self.buffer.write(content)
                    print(f"[AZURE BLOB] Content saved to buffer for retry")
    
    def flush(self, force=False):
        """Flush any buffered logs to Azure Blob Storage

        Args:
            force: If True, create blob even if buffer is empty (for initial blob creation)
        """
        # Check container on first flush if it wasn't checked during initialization (fast startup)
        if not self.container_checked:
            try:
                self._ensure_container_exists()
                self.container_checked = True
            except Exception as e:
                # If container check fails, log but continue (non-blocking)
                print(f"[AZURE BLOB] Container check deferred failed: {e}")
                self.container_checked = True  # Mark as checked to prevent retry loops
        self._flush_to_blob(force=force)
        super().flush()
    
    def close(self):
        """Close the handler and flush any remaining logs"""
        try:
            # Force flush all remaining logs before closing
            self.flush(force=True)
            print(f"[AZURE BLOB] Handler closed and logs flushed: {self.container_name}/{self.blob_path}")
        except Exception as e:
            print(f"[AZURE BLOB] Error during close/flush: {e}")
        finally:
            super().close()

def test_azure_blob_access(connection_string=None, container_name=None):
    """
    Test Azure Blob Storage access and report any issues
    Returns: (success: bool, error_message: str, diagnostics: dict)
    """
    diagnostics = {
        'connection_test': False,
        'container_test': False,
        'write_test': False,
        'read_test': False,
        'errors': []
    }
    
    try:
        # Get credentials from environment variables if not provided
        if not connection_string:
            try:
                from src.config import AZURE_BLOB_CONNECTION_STRING, AZURE_BLOB_CONTAINER_NAME
            except ImportError:
                # Fallback for Azure environment where 'src' might not be in path
                import sys
                import os
                current_dir = os.path.dirname(os.path.abspath(__file__))
                parent_dir = os.path.dirname(current_dir)
                if parent_dir not in sys.path:
                    sys.path.insert(0, parent_dir)
                from src.config import AZURE_BLOB_CONNECTION_STRING, AZURE_BLOB_CONTAINER_NAME
            
            connection_string = AZURE_BLOB_CONNECTION_STRING
            if not container_name:
                container_name = AZURE_BLOB_CONTAINER_NAME
        
        if not connection_string:
            return False, "No connection string available from environment variables", diagnostics
        
        if not container_name:
            container_name = "test-container"
        
        from azure.storage.blob import BlobServiceClient
        from azure.core.exceptions import (
            ClientAuthenticationError,
            HttpResponseError,
            ResourceNotFoundError
        )
        
        print("[AZURE BLOB DIAGNOSTIC] Testing Azure Blob Storage access...")
        print(f"[AZURE BLOB DIAGNOSTIC] Container: {container_name}")
        
        # Test 1: Connection
        try:
            blob_service_client = BlobServiceClient.from_connection_string(connection_string)
            # Try to list containers to test connection
            list(blob_service_client.list_containers(max_results=1))
            diagnostics['connection_test'] = True
            print("[AZURE BLOB DIAGNOSTIC] ✓ Connection test: PASSED")
        except ClientAuthenticationError as e:
            diagnostics['errors'].append(f"Authentication failed: {e}")
            return False, f"Authentication Error: Invalid credentials - {e}", diagnostics
        except Exception as e:
            diagnostics['errors'].append(f"Connection failed: {e}")
            return False, f"Connection Error: {e}", diagnostics
        
        # Test 2: Container access
        try:
            container_client = blob_service_client.get_container_client(container_name)
            if container_client.exists():
                diagnostics['container_test'] = True
                print(f"[AZURE BLOB DIAGNOSTIC] ✓ Container '{container_name}' exists")
            else:
                print(f"[AZURE BLOB DIAGNOSTIC] ⚠ Container '{container_name}' does not exist, attempting to create...")
                try:
                    container_client.create_container()
                    diagnostics['container_test'] = True
                    print(f"[AZURE BLOB DIAGNOSTIC] ✓ Container '{container_name}' created successfully")
                except HttpResponseError as e:
                    if e.status_code == 403:
                        diagnostics['errors'].append(f"Container creation denied (403): Check permissions")
                        return False, "Access Denied: Cannot create container. Check storage account permissions.", diagnostics
                    else:
                        diagnostics['errors'].append(f"Container creation failed: {e}")
                        return False, f"Cannot create container: {e}", diagnostics
        except HttpResponseError as e:
            if e.status_code == 403:
                diagnostics['errors'].append(f"Container access denied (403)")
                return False, f"Access Denied: Cannot access container '{container_name}'. Check permissions.", diagnostics
            else:
                diagnostics['errors'].append(f"Container access error: {e}")
                return False, f"Container access error: {e}", diagnostics
        
        # Test 3: Write access
        try:
            import time as time_module
            test_blob_name = f"test_access_{int(time_module.time())}.txt"
            blob_client = blob_service_client.get_blob_client(
                container=container_name,
                blob=test_blob_name
            )
            blob_client.upload_blob("test", overwrite=True)
            diagnostics['write_test'] = True
            print(f"[AZURE BLOB DIAGNOSTIC] ✓ Write test: PASSED")
            
            # Test 4: Read access
            try:
                content = blob_client.download_blob().readall().decode('utf-8')
                if content == "test":
                    diagnostics['read_test'] = True
                    print(f"[AZURE BLOB DIAGNOSTIC] ✓ Read test: PASSED")
                
                # Cleanup test blob
                blob_client.delete_blob()
                print(f"[AZURE BLOB DIAGNOSTIC] ✓ Test blob cleaned up")
            except Exception as e:
                diagnostics['errors'].append(f"Read test failed: {e}")
                print(f"[AZURE BLOB DIAGNOSTIC] ⚠ Read test: FAILED - {e}")
        except HttpResponseError as e:
            if e.status_code == 403:
                diagnostics['errors'].append(f"Write access denied (403)")
                return False, "Access Denied: Cannot write to container. Check write permissions.", diagnostics
            else:
                diagnostics['errors'].append(f"Write test failed: {e}")
                return False, f"Write test failed: {e}", diagnostics
        
        if all([diagnostics['connection_test'], diagnostics['container_test'], diagnostics['write_test']]):
            print("[AZURE BLOB DIAGNOSTIC] ✓✓✓ ALL TESTS PASSED - Azure Blob Storage is accessible")
            return True, "All access tests passed", diagnostics
        else:
            return False, "Some tests failed", diagnostics
            
    except Exception as e:
        diagnostics['errors'].append(f"Unexpected error: {e}")
        import traceback
        print(f"[AZURE BLOB DIAGNOSTIC] ✗ Unexpected error: {traceback.format_exc()}")
        return False, f"Unexpected error: {e}", diagnostics

def _get_azure_blob_config():
    """
    Helper function to get Azure Blob Storage configuration from environment variables
    Returns: (connection_string, container_name, logging_enabled, account_name)
    """
    try:
        from src.config import (
            AZURE_BLOB_CONNECTION_STRING, 
            AZURE_BLOB_CONTAINER_NAME, 
            AZURE_BLOB_LOGGING_ENABLED,
            AZURE_BLOB_ACCOUNT_NAME
        )
        return (
            AZURE_BLOB_CONNECTION_STRING,
            AZURE_BLOB_CONTAINER_NAME,
            AZURE_BLOB_LOGGING_ENABLED,
            AZURE_BLOB_ACCOUNT_NAME
        )
    except ImportError:
        # Fallback for Azure environment where 'src' might not be in path
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from src.config import (
            AZURE_BLOB_CONNECTION_STRING, 
            AZURE_BLOB_CONTAINER_NAME, 
            AZURE_BLOB_LOGGING_ENABLED,
            AZURE_BLOB_ACCOUNT_NAME
        )
        return (
            AZURE_BLOB_CONNECTION_STRING,
            AZURE_BLOB_CONTAINER_NAME,
            AZURE_BLOB_LOGGING_ENABLED,
            AZURE_BLOB_ACCOUNT_NAME
        )

def setup_azure_blob_logging(account_name=None, logger_name='root', streaming_mode=False, skip_verification=False, broker_id=None):
    """
    Setup Azure Blob Storage logging handler
    Creates logs in Azure Blob Storage with folder structure: {account_name or broker_id}/logs/{filename}.log
    
    All Azure Blob Storage parameters are read from environment variables.
    Set these in Azure Portal > App Service > Configuration > Application settings:
      - AzureBlobStorageKey (or AZURE_BLOB_STORAGE_KEY)
      - AZURE_BLOB_ACCOUNT_NAME
      - AZURE_BLOB_CONTAINER_NAME
      - AZURE_BLOB_LOGGING_ENABLED (true/yes/1/on to enable)
    
    Args:
        account_name: Account name for folder structure (deprecated, use broker_id)
        logger_name: Logger name to attach handler to
        streaming_mode: Enable real-time streaming logs (recommended for log retention)
        skip_verification: If True, skip time-consuming verification (useful for fast startup)
        broker_id: Broker ID for multi-tenant log isolation (preferred over account_name)
    
    IMPORTANT: Logs are preserved across deployments by:
    1. Storing in Azure Blob Storage (persistent storage)
    2. Appending to existing blobs (never overwrites)
    3. Organized by broker_id/account for multi-tenant isolation
    4. Flushed on application shutdown via registered handlers
    """
    try:
        # Add prefix to identify if this is from trading strategy (has account_name) vs dashboard (no account_name)
        prefix = "[STRATEGY]" if account_name else "[DASHBOARD]"
        
        # Get credentials from environment variables (config.py)
        connection_string, container_name, logging_enabled, config_account_name = _get_azure_blob_config()
        
        print(f"{prefix} [AZURE BLOB] Using environment variables from config")
        if config_account_name:
            print(f"{prefix} [AZURE BLOB] Storage Account: {config_account_name}")
        print(f"{prefix} [AZURE BLOB] Container: {container_name}")
        
        # Always print diagnostic info (even if disabled)
        print(f"{prefix} [AZURE BLOB] Checking configuration...")
        print(f"{prefix} [AZURE BLOB] AZURE_BLOB_LOGGING_ENABLED = {logging_enabled}")
        print(f"{prefix} [AZURE BLOB] Connection string available: {connection_string is not None}")
        print(f"{prefix} [AZURE BLOB] Container name: {container_name}")
        if account_name:
            print(f"{prefix} [AZURE BLOB] Account name: {account_name} (will create folder: {sanitize_account_name_for_filename(account_name)})")
        
        if not logging_enabled:
            print(f"{prefix} [AZURE BLOB] Logging is DISABLED.")
            print(f"{prefix} [AZURE BLOB] Set AZURE_BLOB_LOGGING_ENABLED=True in Azure Portal or environment variables.")
            return None, None
        
        # Check if connection string is available
        if not connection_string:
            print(f"{prefix} [AZURE BLOB] ERROR: Azure Blob Storage connection string not available.")
            print(f"{prefix} [AZURE BLOB] Required environment variables in Azure Portal:")
            print(f"{prefix} [AZURE BLOB]   1. AzureBlobStorageKey = <your-storage-account-key>")
            print(f"{prefix} [AZURE BLOB]   2. AZURE_BLOB_ACCOUNT_NAME = <your-storage-account-name>")
            print(f"{prefix} [AZURE BLOB]   3. AZURE_BLOB_CONTAINER_NAME = <your-container-name>")
            print(f"{prefix} [AZURE BLOB]   4. AZURE_BLOB_LOGGING_ENABLED = True")
            print(f"{prefix} [AZURE BLOB] Go to: Azure Portal > App Service > Configuration > Application settings")
            return None, None
        
        # Test access before proceeding (optional diagnostic) - skip if fast startup needed
        if is_azure_environment() and not skip_verification:
            print(f"{prefix} [AZURE BLOB] Testing Azure Blob Storage access...")
            try:
                import time
                success, error_msg, diagnostics = test_azure_blob_access(connection_string, container_name)
                if not success:
                    print(f"{prefix} [AZURE BLOB] ⚠⚠⚠ ACCESS TEST FAILED: {error_msg}")
                    print(f"{prefix} [AZURE BLOB] Diagnostics: {diagnostics}")
                    print(f"{prefix} [AZURE BLOB] Continuing anyway - errors will be reported during actual operations")
                else:
                    print(f"{prefix} [AZURE BLOB] ✓ Access test passed - Azure Blob Storage is accessible")
            except Exception as test_error:
                print(f"{prefix} [AZURE BLOB] ⚠ Access test error (non-critical): {test_error}")
                print(f"{prefix} [AZURE BLOB] Continuing with blob logging setup...")
        elif skip_verification:
            print(f"{prefix} [AZURE BLOB] Skipping access test for fast startup (verification will happen on first log write)")
        
        logger = logging.getLogger(logger_name)
        
        # Determine blob path
        # IMPORTANT: Use broker_id for multi-tenant log isolation (preferred)
        # Fallback to account_name if broker_id not provided
        # Always create account folder structure for proper organization
        
        # Priority: broker_id > account_name > default
        identifier = broker_id or account_name
        
        if identifier and str(identifier).strip():
            # Use broker_id if available (for multi-tenant isolation)
            if broker_id:
                sanitized_account = str(broker_id).strip()
                # Sanitize broker_id for filename safety
                sanitized_account = sanitize_account_name_for_filename(sanitized_account)
                print(f"{prefix} [AZURE BLOB] Using broker_id for log isolation: '{broker_id}' -> '{sanitized_account}'")
            else:
                sanitized_account = sanitize_account_name_for_filename(str(account_name).strip())
                print(f"{prefix} [AZURE BLOB] Using account_name: '{account_name}' -> '{sanitized_account}'")
            
            # Validate sanitized account name is not empty
            if not sanitized_account or sanitized_account.strip() == '':
                print(f"{prefix} [AZURE BLOB] WARNING: Identifier '{identifier}' sanitized to empty string. Using default.")
                sanitized_account = "default_account"
        else:
            # In Azure, if no identifier provided, use default folder
            if is_azure_environment():
                sanitized_account = "default_account"
                print(f"{prefix} [AZURE BLOB] WARNING: No broker_id or account_name provided in Azure. Using default folder: '{sanitized_account}'")
            else:
                sanitized_account = "trading"
                print(f"{prefix} [AZURE BLOB] No identifier provided. Using folder: '{sanitized_account}'")
        
        # Ensure sanitized_account is not empty (final safety check)
        if not sanitized_account or sanitized_account.strip() == '':
            sanitized_account = "default_account"
            print(f"{prefix} [AZURE BLOB] CRITICAL: Sanitized account name was empty, using: '{sanitized_account}'")
        
        date_str = format_date_for_filename(date.today())
        # Folder structure: {sanitized_account_name}/logs/{sanitized_account}_{date_str}.log
        # Always use account folder structure to ensure proper organization
        blob_path = f"{sanitized_account}/logs/{sanitized_account}_{date_str}.log"
        print(f"{prefix} [AZURE BLOB] ========================================")
        print(f"{prefix} [AZURE BLOB] BLOB PATH CONFIGURATION:")
        print(f"{prefix} [AZURE BLOB]   Container: {container_name}")
        print(f"{prefix} [AZURE BLOB]   Account Folder: {sanitized_account}")
        print(f"{prefix} [AZURE BLOB]   Blob Path: {blob_path}")
        print(f"{prefix} [AZURE BLOB]   Full Location: {container_name}/{blob_path}")
        print(f"{prefix} [AZURE BLOB] ========================================")
        
        # Create Azure Blob handler
        try:
            # Skip container check during initialization if skip_verification is True (fast startup)
            # Container will be checked/created on first log write
            blob_handler = AzureBlobStorageHandler(
                connection_string=connection_string,
                container_name=container_name,
                blob_path=blob_path,
                account_name=account_name,
                streaming_mode=streaming_mode,  # Enable streaming for real-time logs
                skip_container_check=skip_verification  # Skip container check for fast startup
            )

            # Set formatter (same format as file handler)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            blob_handler.setFormatter(formatter)
        except Exception as handler_error:
            # Catch any errors during handler creation (including DNS errors from _ensure_container_exists)
            error_type = type(handler_error).__name__
            print(f"{prefix} [AZURE BLOB] ✗ Failed to create Azure Blob Storage handler: {error_type}: {handler_error}")
            print(f"{prefix} [AZURE BLOB] Application will continue without Azure Blob Storage logging")
            return None, None
        blob_handler.setLevel(logging.INFO)
        
        # Add handler to logger
        logger.addHandler(blob_handler)
        
        # Register handler for shutdown flush (if function exists)
        # This ensures logs are flushed on deployment/shutdown
        try:
            # Try to import register function from config_dashboard
            try:
                from src.config_dashboard import register_blob_handler
                register_blob_handler(blob_handler)
                print(f"{prefix} [AZURE BLOB] ✓ Handler registered for log retention on shutdown")
            except ImportError:
                # If config_dashboard not available (e.g., when running strategy standalone),
                # register directly in this module
                try:
                    # Create a simple registration mechanism if config_dashboard not available
                    if not hasattr(setup_azure_blob_logging, '_registered_handlers'):
                        setup_azure_blob_logging._registered_handlers = []
                    if blob_handler not in setup_azure_blob_logging._registered_handlers:
                        setup_azure_blob_logging._registered_handlers.append(blob_handler)
                        print(f"{prefix} [AZURE BLOB] ✓ Handler registered locally for log retention")
                except Exception:
                    pass  # Non-critical - logs will still be flushed on handler.close()
        except Exception as reg_error:
            print(f"{prefix} [AZURE BLOB] Warning: Could not register handler (non-critical): {reg_error}")
            # Non-critical - handler.close() will still flush logs
        
        # Write initial test message and verify (skip verification if fast startup needed)
        prefix = "[STRATEGY]" if account_name else "[DASHBOARD]"
        
        if not skip_verification:
            print(f"{prefix} [AZURE BLOB] Writing initial test message to blob...")
            logger.info(f"[AZURE BLOB] Azure Blob Storage logging initialized: {container_name}/{blob_path}")
            
            # Give a small delay to ensure the log message is written to buffer
            import time
            time.sleep(1.0)  # Increased delay to ensure message is in buffer
            
            # Force immediate flush of initial message (force=True ensures blob is created even if empty)
            print(f"{prefix} [AZURE BLOB] Flushing buffer to create blob...")
            try:
                blob_handler.flush(force=True)
                print(f"{prefix} [AZURE BLOB] Flush completed")
            except Exception as flush_error:
                print(f"{prefix} [AZURE BLOB] ✗ Flush failed: {flush_error}")
                import traceback
                print(f"{prefix} [AZURE BLOB] Flush traceback: {traceback.format_exc()}")
            
            # Verify blob was created with retries
            print(f"{prefix} [AZURE BLOB] Verifying blob creation...")
            blob_verified = False
            for verify_attempt in range(5):
                try:
                    from azure.storage.blob import BlobServiceClient
                    from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
                    
                    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
                    blob_client = blob_service_client.get_blob_client(
                        container=container_name,
                        blob=blob_path
                    )
                    if blob_client.exists():
                        print(f"{prefix} [AZURE BLOB] ✓✓✓ SUCCESS: Blob verified at attempt {verify_attempt + 1}")
                        # Get account name from config for URL
                        try:
                            _, _, _, account_name = _get_azure_blob_config()
                            account_name_str = account_name if account_name else "storage-account"
                        except:
                            account_name_str = "storage-account"
                        print(f"{prefix} [AZURE BLOB] Blob URL: https://{account_name_str}.blob.core.windows.net/{container_name}/{blob_path}")
                        blob_verified = True
                        break
                    else:
                        print(f"{prefix} [AZURE BLOB] ⚠ Verification attempt {verify_attempt + 1}: Blob not found, waiting...")
                        time.sleep(2)
                except ClientAuthenticationError as auth_error:
                    print(f"{prefix} [AZURE BLOB] ✗✗✗ AUTHENTICATION ERROR during verification: {auth_error}")
                    print(f"{prefix} [AZURE BLOB] Your credentials may be invalid. Check connection string.")
                    break  # Don't retry on auth errors
                except HttpResponseError as http_error:
                    status_code = getattr(http_error, 'status_code', 'Unknown')
                    print(f"{prefix} [AZURE BLOB] ✗✗✗ HTTP ERROR ({status_code}) during verification: {http_error}")
                    if status_code == 403:
                        print(f"{prefix} [AZURE BLOB] ACCESS DENIED: Check container and blob permissions")
                    break  # Don't retry on permission errors
                except Exception as verify_error:
                    error_type = type(verify_error).__name__
                    print(f"{prefix} [AZURE BLOB] ⚠ Verification attempt {verify_attempt + 1} error ({error_type}): {verify_error}")
                    if verify_attempt < 4:  # Don't sleep on last attempt
                        time.sleep(2)
            
            if not blob_verified:
                print(f"{prefix} [AZURE BLOB] ========================================")
                print(f"{prefix} [AZURE BLOB] ✗✗✗ WARNING: Blob verification FAILED after 5 attempts")
                print(f"{prefix} [AZURE BLOB] Container: {container_name}")
                print(f"{prefix} [AZURE BLOB] Blob path: {blob_path}")
                # Get account name from config for URL
                try:
                    _, _, _, account_name = _get_azure_blob_config()
                    account_name_str = account_name if account_name else "storage-account"
                except:
                    account_name_str = "storage-account"
                print(f"{prefix} [AZURE BLOB] Expected URL: https://{account_name_str}.blob.core.windows.net/{container_name}/{blob_path}")
                print(f"{prefix} [AZURE BLOB] ========================================")
                print(f"{prefix} [AZURE BLOB] TROUBLESHOOTING:")
                print(f"{prefix} [AZURE BLOB] 1. Go to Azure Portal > Storage Account > Containers")
                print(f"{prefix} [AZURE BLOB] 2. Check if container '{container_name}' exists")
                print(f"{prefix} [AZURE BLOB] 3. Verify blob path: {blob_path}")
                print(f"{prefix} [AZURE BLOB] 4. Check container access level (Private/Blob/Container)")
                print(f"{prefix} [AZURE BLOB] 5. Verify storage account key has read permissions")
                print(f"{prefix} [AZURE BLOB] 6. Check Azure Portal > Storage Account > Access Keys")
                print(f"{prefix} [AZURE BLOB] ========================================")
            
            print(f"{prefix} [AZURE BLOB] Logging to Azure Blob: {container_name}/{blob_path}")
            print(f"{prefix} [AZURE BLOB] Initial test message sent. Check container: {container_name}")
        else:
            # Fast startup mode: skip verification, just log that it's configured
            print(f"{prefix} [AZURE BLOB] Azure Blob Storage logging configured (fast startup mode)")
            print(f"{prefix} [AZURE BLOB] Blob path: {container_name}/{blob_path}")
            print(f"{prefix} [AZURE BLOB] Verification will happen on first log write")
            # Write a quick initialization message without waiting
            logger.info(f"[AZURE BLOB] Azure Blob Storage logging initialized: {container_name}/{blob_path}")
        
        if account_name:
            print(f"{prefix} [AZURE BLOB] Full blob path: {container_name}/{blob_path}")
        return blob_handler, blob_path
        
    except ImportError as e:
        print(f"[AZURE BLOB] Warning: Azure Blob Storage not available: {e}")
        return None, None
    except Exception as e:
        print(f"[AZURE BLOB] Warning: Failed to setup Azure Blob logging: {e}")
        import traceback
        print(traceback.format_exc())
        return None, None

def get_log_directory(account_name=None):
    """
    Get the appropriate log directory based on environment
    - Local: src/logs directory
    - Azure: /tmp/{account_name}/logs/ (account-specific directory in /tmp)
    """
    if is_azure_environment():
        # Azure: Use /tmp/{account_name}/logs/ structure
        if account_name:
            # Sanitize account name for directory name
            sanitized_account = sanitize_account_name_for_filename(account_name)
            log_dir = os.path.join('/tmp', sanitized_account, 'logs')
        else:
            # Fallback to /tmp/logs if no account name
            log_dir = '/tmp/logs'
    else:
        # Local: use src/logs directory
        current_dir = os.path.dirname(os.path.abspath(__file__))
        log_dir = os.path.join(current_dir, 'logs')
    
    # Create directory if it doesn't exist
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def setup_azure_logging(logger_name='root', account_name=None):
    """
    Setup logging for Azure App Service
    Azure automatically captures stdout/stderr, so we configure both file and console logging
    
    Logging Strategy:
    - File logs: /tmp/{account_name}/logs/ (ephemeral, cleared on deployment)
    - Azure Blob Storage: Persistent backup (survives deployments)
    
    This ensures:
    1. Same folder structure maintained (src/logs locally, /tmp/{account}/logs in Azure)
    2. Logs persist across deployments via Azure Blob Storage
    3. File logs available for immediate access during runtime
    
    CRITICAL FIX: Always add handlers to root logger to ensure logging.info() calls work
    """
    # Get both named logger and root logger
    logger = logging.getLogger(logger_name)
    root_logger = logging.getLogger()  # Root logger - this is what logging.info() uses
    
    # Get log directory (account-specific for Azure)
    log_dir = get_log_directory(account_name=account_name)
    
    # Create safe formatter that handles Unicode characters
    formatter = SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler (Azure captures stdout/stderr automatically)
    # Set stream encoding to UTF-8 for Windows compatibility
    console_handler = logging.StreamHandler()
    # On Windows, ensure stdout/stderr use UTF-8
    if sys.platform == 'win32':
        try:
            import codecs
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass  # Fallback to default if reconfigure fails
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # File handler for persistent logs - use account name if provided
    if account_name:
        # Sanitize account name for filename (first name only)
        sanitized_account = sanitize_account_name_for_filename(account_name)
        # Format date as YYYYMONDD (e.g., 2025Dec11)
        date_str = format_date_for_filename(date.today())
        log_file = os.path.join(log_dir, f'{sanitized_account}_{date_str}.log')
    else:
        log_file = os.path.join(log_dir, 'trading_bot.log')
    # Ensure directory exists before creating file handler
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    # Create file handler with immediate flush (unbuffered) and UTF-8 encoding
    try:
        # Use mode='a' for append, UTF-8 encoding, and errors='replace' to handle any Unicode issues
        # Note: FileHandler doesn't support errors parameter directly, but we use SafeFormatter
        file_handler = logging.FileHandler(log_file, encoding='utf-8', mode='a', delay=False)
        file_handler.setFormatter(formatter)  # SafeFormatter handles Unicode encoding errors
        file_handler.setLevel(logging.INFO)
        
        # CRITICAL FIX: Add handlers to ROOT logger (what logging.info() uses)
        # This ensures all logging.info() calls throughout the codebase write to file
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == log_file for h in root_logger.handlers):
            root_logger.addHandler(file_handler)
            root_logger.setLevel(logging.INFO)
        
        # Also add to named logger if it's different from root
        if logger_name != 'root' and logger != root_logger:
            if not any(isinstance(h, logging.FileHandler) and h.baseFilename == log_file for h in logger.handlers):
                logger.addHandler(file_handler)
                logger.setLevel(logging.INFO)
        
        # Add console handler to root logger as well
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            root_logger.addHandler(console_handler)
        
        # Ensure named logger propagates to root (default behavior, but make explicit)
        logger.propagate = True
        
        # FILE-BASED LOGGING + AZURE BLOB STORAGE (for persistence across deployments)
        # File logs in /tmp are ephemeral (cleared on deployment), but Azure Blob Storage persists
        prefix = "[STRATEGY]" if account_name else "[DASHBOARD]"
        print(f"{prefix} [LOG SETUP] File-based logging enabled: {log_file}")
        print(f"{prefix} [LOG SETUP] Note: /tmp logs are ephemeral - Azure Blob Storage will be used for persistence")
        logger.info(f"[LOG SETUP] File-based logging enabled: {log_file}")
        
        # Also setup Azure Blob Storage logging for persistence across deployments
        # This ensures logs survive even when /tmp is cleared
        try:
            # Try to get broker_id from session if available (for multi-tenant log isolation)
            broker_id = None
            try:
                from src.security.saas_session_manager import SaaSSessionManager
                broker_id = SaaSSessionManager.get_broker_id()
            except:
                pass
            
            blob_handler, blob_path = setup_azure_blob_logging(
                account_name=account_name,
                logger_name=logger_name,
                streaming_mode=True,  # Real-time streaming to blob for log retention
                skip_verification=True,  # Fast startup
                broker_id=broker_id  # Use broker_id for multi-tenant log isolation
            )
            if blob_handler:
                print(f"{prefix} [LOG SETUP] ✓ Azure Blob Storage logging enabled for persistence: {blob_path}")
                logger.info(f"[LOG SETUP] Azure Blob Storage logging enabled: {blob_path}")
            else:
                print(f"{prefix} [LOG SETUP] ⚠ Azure Blob Storage logging not available (check environment variables)")
                print(f"{prefix} [LOG SETUP] ⚠ WARNING: Logs in /tmp will be lost on deployment!")
        except Exception as blob_error:
            print(f"{prefix} [LOG SETUP] ⚠ Could not setup Azure Blob Storage: {blob_error}")
            print(f"{prefix} [LOG SETUP] ⚠ WARNING: Logs in /tmp will be lost on deployment!")
        
        # Force file creation by writing an initial log message
        # This ensures the file exists immediately
        # Use root logger to ensure it works
        root_logger.info(f"[LOG SETUP] Log file created at: {log_file}")
        root_logger.info(f"[LOG SETUP] Log directory: {log_dir}")
        file_handler.flush()  # Force write to disk
        os.fsync(file_handler.stream.fileno()) if hasattr(file_handler.stream, 'fileno') else None  # Force OS-level flush
        
        # Verify file was created and is writable
        if os.path.exists(log_file):
            try:
                # Test write access with UTF-8 encoding
                with open(log_file, 'a', encoding='utf-8', errors='replace') as test_file:
                    test_file.write("")
                # Use ASCII-safe characters for print statements to avoid encoding issues
                print(f"[LOG SETUP] SUCCESS: Log file created and writable: {log_file}")
            except Exception as write_test:
                print(f"[LOG SETUP] WARNING: Log file exists but may not be writable: {write_test}")
        else:
            print(f"[LOG SETUP] ERROR: Log file was NOT created: {log_file}")
        
        print(f"[LOG SETUP] Log file path: {log_file}")
        print(f"[LOG SETUP] Log directory: {log_dir}")
        print(f"[LOG SETUP] Root logger handlers: {len(root_logger.handlers)}")
        print(f"[LOG SETUP] Named logger handlers: {len(logger.handlers)}")
        
    except Exception as e:
        error_msg = f"[LOG SETUP] Failed to create log file {log_file}: {e}"
        print(error_msg)
        import traceback
        error_trace = traceback.format_exc()
        print(error_trace)
        # Try to log to root logger (might not have handlers yet)
        try:
            root_logger.error(error_msg)
            root_logger.error(error_trace)
        except:
            pass
        # Fallback: try to create at least console logging on root logger
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            root_logger.addHandler(console_handler)
            root_logger.setLevel(logging.INFO)
        return logger, None
    
    return logger, log_file

def setup_local_logging(log_dir=None, account_name=None, logger_name='root'):
    """
    Setup logging for local environment
    Logs are stored locally and also uploaded to Azure Blob Storage if enabled
    
    CRITICAL FIX: Always add handlers to root logger to ensure logging.info() calls work
    """
    # Get both named logger and root logger
    logger = logging.getLogger(logger_name)
    root_logger = logging.getLogger()  # Root logger - this is what logging.info() uses
    
    if log_dir is None:
        log_dir = get_log_directory()
    
    # Create safe formatter that handles Unicode characters
    formatter = SafeFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler with UTF-8 encoding for Windows
    console_handler = logging.StreamHandler()
    # On Windows, ensure stdout/stderr use UTF-8
    if sys.platform == 'win32':
        try:
            import codecs
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            if hasattr(sys.stderr, 'reconfigure'):
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass  # Fallback to default if reconfigure fails
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)
    
    # File handler with account name
    if account_name:
        # Sanitize account name for filename (first name only)
        sanitized_account = sanitize_account_name_for_filename(account_name)
        # Format date as YYYYMONDD (e.g., 2025Dec11)
        date_str = format_date_for_filename(date.today())
        log_filename = os.path.join(log_dir, f'{sanitized_account}_{date_str}.log')
    else:
        # Format date as YYYYMONDD
        date_str = format_date_for_filename(date.today())
        log_filename = os.path.join(log_dir, f'trading_{date_str}.log')
    
    # Ensure directory exists before creating file handler
    os.makedirs(os.path.dirname(log_filename), exist_ok=True)
    
    # Create file handler with UTF-8 encoding and safe formatter
    try:
        # Use UTF-8 encoding with SafeFormatter to handle Unicode characters
        file_handler = logging.FileHandler(log_filename, encoding='utf-8', mode='a', delay=False)
        file_handler.setFormatter(formatter)  # SafeFormatter handles Unicode encoding errors
        file_handler.setLevel(logging.INFO)
        
        # CRITICAL FIX: Add handlers to ROOT logger (what logging.info() uses)
        # This ensures all logging.info() calls throughout the codebase write to file
        if not any(isinstance(h, logging.FileHandler) and h.baseFilename == log_filename for h in root_logger.handlers):
            root_logger.addHandler(file_handler)
            root_logger.setLevel(logging.INFO)
        
        # Also add to named logger if it's different from root
        if logger_name != 'root' and logger != root_logger:
            if not any(isinstance(h, logging.FileHandler) and h.baseFilename == log_filename for h in logger.handlers):
                logger.addHandler(file_handler)
                logger.setLevel(logging.INFO)
        
        # Add console handler to root logger as well
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            root_logger.addHandler(console_handler)
        
        # Ensure named logger propagates to root (default behavior, but make explicit)
        logger.propagate = True
        
        # FILE-BASED LOGGING ONLY (like disciplined-Trader)
        # Azure Blob logging removed for better performance and simplicity
        prefix = "[STRATEGY]" if account_name else "[DASHBOARD]"
        print(f"{prefix} [LOG SETUP] Using file-based logging only (Azure Blob disabled)")
        logger.info(f"[LOG SETUP] File-based logging enabled: {log_filename}")
        
        # Force file creation by writing an initial log message
        # This ensures the file exists immediately
        # Use root logger to ensure it works
        root_logger.info(f"[LOG SETUP] Log file created at: {log_filename}")
        root_logger.info(f"[LOG SETUP] Log directory: {log_dir}")
        file_handler.flush()  # Force write to disk
        os.fsync(file_handler.stream.fileno()) if hasattr(file_handler.stream, 'fileno') else None  # Force OS-level flush
        
        # Verify file was created and is writable
        if os.path.exists(log_filename):
            try:
                # Test write access with UTF-8 encoding
                with open(log_filename, 'a', encoding='utf-8', errors='replace') as test_file:
                    test_file.write("")
                print(f"[LOG SETUP] SUCCESS: Log file created and writable: {log_filename}")
            except Exception as write_test:
                print(f"[LOG SETUP] WARNING: Log file exists but may not be writable: {write_test}")
        else:
            print(f"[LOG SETUP] ERROR: Log file was NOT created: {log_filename}")
        
        print(f"[LOG SETUP] Log file path: {log_filename}")
        print(f"[LOG SETUP] Log directory: {log_dir}")
        print(f"[LOG SETUP] Root logger handlers: {len(root_logger.handlers)}")
        print(f"[LOG SETUP] Named logger handlers: {len(logger.handlers)}")
        
    except Exception as e:
        error_msg = f"[LOG SETUP] Failed to create log file {log_filename}: {e}"
        print(error_msg)
        logging.error(error_msg)
        import traceback
        logging.error(traceback.format_exc())
        # Fallback: try to create at least console logging
        logger.addHandler(console_handler)
        logger.setLevel(logging.INFO)
        return logger, None
    
    return logger, log_filename

def setup_logging(account_name=None, logger_name='root'):
    """
    Universal logging setup that works in both local and Azure environments
    """
    # Add prefix to identify if this is from trading strategy (has account_name) vs dashboard (no account_name)
    prefix = "[STRATEGY]" if account_name else "[DASHBOARD]"
    print(f"{prefix} [SETUP LOGGING] Starting logging setup - account_name={account_name}, logger_name={logger_name}")
    
    if is_azure_environment():
        print(f"{prefix} [SETUP LOGGING] Azure environment detected")
        logger, log_file = setup_azure_logging(logger_name, account_name=account_name)
        logging.info(f"[ENV] Running in Azure App Service - Logs: {log_file}")
        logging.info(f"[ENV] Azure Log Stream: Available via Azure Portal > Log stream")
        if account_name:
            logging.info(f"[ENV] Account name: {account_name}")
            print(f"{prefix} [SETUP LOGGING] Strategy logs will be written to blob: {account_name}/logs/")
        print(f"{prefix} [SETUP LOGGING] Azure logging setup complete - log_file={log_file}")
        return logger, log_file
    else:
        logger, log_file = setup_local_logging(account_name=account_name, logger_name=logger_name)
        logging.info(f"[ENV] Running locally - Log file: {log_file}")
        if account_name:
            logging.info(f"[ENV] Account name: {account_name}")
        return logger, log_file

def get_config_value(key, default=None):
    """
    Get configuration value from environment variables (Azure) or config file (local)
    Azure App Service uses environment variables prefixed with APPSETTING_
    """
    # Try Azure App Service environment variable format
    azure_key = f'APPSETTING_{key}'
    value = os.getenv(azure_key)
    if value:
        return value
    
    # Try direct environment variable
    value = os.getenv(key)
    if value:
        return value
    
    # Fallback to default
    return default

