@echo off
chcp 65001 >nul
echo ==========================================
echo    Energy Monitor Web Dashboard
echo ==========================================
echo.
echo Installing dependencies...
pip install flask flask-cors psutil wmi nvidia-ml-py pywin32 -q 2>nul
echo.
echo Starting server on http://127.0.0.1:5000
echo Press Ctrl+C to stop
echo ==========================================
python energy_monitor_server.py
pause
