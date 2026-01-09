# PowerShell script to run the Options Trading Bot
# Run this script with: .\run_trading_bot.ps1

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "                OPTIONS TRADING BOT RUNNER" -ForegroundColor Cyan
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

# Check if run_trading_bot.py exists
if (-not (Test-Path "run_trading_bot.py")) {
    Write-Host "❌ ERROR: run_trading_bot.py not found in current directory" -ForegroundColor Red
    Write-Host "Please make sure all required files are present" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "🚀 Starting Trading Bot..." -ForegroundColor Green
Write-Host ""

try {
    # Run the Python script
    python run_trading_bot.py
    
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

