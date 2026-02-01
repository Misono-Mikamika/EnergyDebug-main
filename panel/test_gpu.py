#!/usr/bin/env python3
"""测试 GPU 检测功能"""

import sys

# 测试 NVML
try:
    from pynvml import (
        nvmlInit, nvmlShutdown, nvmlDeviceGetCount, 
        nvmlDeviceGetHandleByIndex, nvmlDeviceGetName,
        nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage
    )
    
    nvmlInit()
    device_count = nvmlDeviceGetCount()
    print(f"✓ NVML initialized successfully")
    print(f"✓ Found {device_count} GPU(s)")
    
    if device_count > 0:
        handle = nvmlDeviceGetHandleByIndex(0)
        
        # 获取名称
        try:
            name = nvmlDeviceGetName(handle)
            name_str = name.decode('utf-8') if isinstance(name, bytes) else name
            print(f"✓ GPU Name: {name_str}")
        except Exception as e:
            print(f"✗ Failed to get GPU name: {e}")
        
        # 获取温度
        try:
            temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            print(f"✓ GPU Temperature: {temp}°C")
        except Exception as e:
            print(f"✗ Failed to get GPU temperature: {e}")
        
        # 获取使用率
        try:
            util = nvmlDeviceGetUtilizationRates(handle)
            print(f"✓ GPU Utilization: {util.gpu}%")
        except Exception as e:
            print(f"✗ Failed to get GPU utilization: {e}")
        
        # 获取功耗
        try:
            power_mw = nvmlDeviceGetPowerUsage(handle)
            power_w = power_mw / 1000.0
            print(f"✓ GPU Power: {power_w}W")
        except Exception as e:
            print(f"✗ Failed to get GPU power: {e}")
    
    nvmlShutdown()
    print("\n✓ All GPU tests passed!")
    
except ImportError as e:
    print(f"✗ NVML not installed: {e}")
    print("  Run: pip install nvidia-ml-py")
except Exception as e:
    print(f"✗ NVML error: {e}")
