#!/bin/bash

echo "=========================================="
echo "   Energy Monitor Web Dashboard"
echo "=========================================="
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt -q

echo ""
echo "Starting server..."
echo "Open http://127.0.0.1:5000 in your browser"
echo "Press Ctrl+C to stop"
echo ""

python3 energy_monitor_server.py
