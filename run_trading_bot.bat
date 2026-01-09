@echo off
echo ============================================================
echo                OPTIONS TRADING BOT RUNNER
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python and try again
    pause
    exit /b 1
)

REM Check if main.py exists
if not exist "main.py" (
    echo ERROR: main.py not found in current directory
    echo Please make sure you're running this from the correct directory
    pause
    exit /b 1
)

echo Starting Trading Bot...
echo.

REM Run the Python script
python run_trading_bot.py

echo.
echo Trading Bot execution completed.
pause

