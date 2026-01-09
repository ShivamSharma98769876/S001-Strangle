@echo off
REM Azure App Service startup script for Windows
REM This script is executed when the app starts on Windows App Service

echo Starting Trading Bot Application...

REM Set Python path
set PYTHONPATH=%PYTHONPATH%;%CD%;%CD%\src

REM Start the application
if exist "src\start_with_monitoring.py" (
    echo Starting with monitoring...
    python src\start_with_monitoring.py
) else (
    echo Starting main application...
    python src\Straddle10PointswithSL-Limit.py
)

