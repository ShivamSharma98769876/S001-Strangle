# PowerShell script to run Options Trading Bot with flexible parameters
# You can use .env file for API credentials OR provide them as command line parameters

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "           OPTIONS TRADING BOT - FLEXIBLE PARAMETERS" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ ERROR: Python is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Python and try again" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if main.py exists
if (-not (Test-Path "main.py")) {
    Write-Host "❌ ERROR: main.py not found in current directory" -ForegroundColor Red
    Write-Host "Please make sure you're running this from the correct directory" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "🚀 Starting Trading Bot with flexible parameters..." -ForegroundColor Green
Write-Host ""

# Method 1: Using .env file for API credentials (recommended)
Write-Host "Method 1: Using .env file for API credentials" -ForegroundColor Yellow
try {
    python run_trading_bot.py `
        --request-token "UMKd49IAwdYxP3bvT515LG9fl0EASTv0" `
        --call-quantity 75 `
        --put-quantity 75 `
        --cleanup-logs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Trading Bot execution completed successfully!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "❌ Trading Bot execution failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    }
} catch {
    Write-Host ""
    Write-Host "❌ Error running trading bot: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# Method 2: Providing API credentials as command line parameters
Write-Host "Method 2: Providing API credentials as command line parameters" -ForegroundColor Yellow
try {
    python run_trading_bot.py `
        --api-key "n683nqe7f3l7nzxl" `
        --api-secret "11krc3ysc604ppxsvq60862pnq73t4qi" `
        --request-token "UMKd49IAwdYxP3bvT515LG9fl0EASTv0" `
        --call-quantity 75 `
        --put-quantity 75 `
        --cleanup-logs
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "✅ Trading Bot execution completed successfully!" -ForegroundColor Green
    } else {
        Write-Host ""
        Write-Host "❌ Trading Bot execution failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    }
} catch {
    Write-Host ""
    Write-Host "❌ Error running trading bot: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"
