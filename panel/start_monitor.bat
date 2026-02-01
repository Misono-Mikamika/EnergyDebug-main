@echo off
chcp 65001 >nul
echo ==========================================
echo    Energy Monitor Web Dashboard
echo ==========================================
echo.

echo Checking dependencies...
pip install flask flask-cors psutil wmi nvidia-ml-py -q 2>nul

echo.
echo Starting server...
echo ==========================================
python energy_monitor_server.py
pause
