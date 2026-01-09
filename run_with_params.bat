@echo off
echo ============================================================
echo           OPTIONS TRADING BOT - FLEXIBLE PARAMETERS
echo ============================================================
echo.

REM Example 1: Using .env file for API credentials (recommended)
echo Method 1: Using .env file for API credentials
python run_trading_bot.py ^
    --request-token "UMKd49IAwdYxP3bvT515LG9fl0EASTv0" ^
    --call-quantity 75 ^
    --put-quantity 75 ^
    --cleanup-logs

echo.
echo ============================================================
echo.

REM Example 2: Providing API credentials as command line parameters
echo Method 2: Providing API credentials as command line parameters
python run_trading_bot.py ^
    --api-key "n683nqe7f3l7nzxl" ^
    --api-secret "11krc3ysc604ppxsvq60862pnq73t4qi" ^
    --request-token "UMKd49IAwdYxP3bvT515LG9fl0EASTv0" ^
    --call-quantity 75 ^
    --put-quantity 75 ^
    --cleanup-logs

echo.
echo Trading Bot execution completed.
pause
