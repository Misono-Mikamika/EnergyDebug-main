#!/usr/bin/env python3
"""Test temperature reading"""

import psutil
import time

print("=== Temperature Test ===")

# Test WMI
try:
    import wmi
    w = wmi.WMI()
    print("[OK] WMI loaded")
    
    try:
        temps = w.MSAcpi_ThermalZoneTemperature()
        for tz in temps:
            if hasattr(tz, 'CurrentTemperature'):
                celsius = tz.CurrentTemperature / 10.0 - 273.15
                print(f"[OK] WMI CPU Temp: {celsius:.1f}C")
    except Exception as e:
        print(f"[ERR] WMI temp: {e}")
except ImportError:
    print("[ERR] WMI not available")

# Test psutil sensors
try:
    temps = psutil.sensors_temperatures()
    if temps:
        print(f"[OK] psutil sensors: {list(temps.keys())}")
        for name, entries in temps.items():
            for entry in entries:
                print(f"  - {name}: {entry.current}C")
    else:
        print("[WARN] psutil sensors empty")
except Exception as e:
    print(f"[ERR] psutil sensors: {e}")

# Test NVML
try:
    from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex
    from pynvml import nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU
    nvmlInit()
    count = nvmlDeviceGetCount()
    print(f"[OK] NVML: {count} GPU(s)")
    
    if count > 0:
        handle = nvmlDeviceGetHandleByIndex(0)
        temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
        print(f"[OK] GPU Temp: {temp}C")
except Exception as e:
    print(f"[ERR] NVML: {e}")

print("\nDone")
