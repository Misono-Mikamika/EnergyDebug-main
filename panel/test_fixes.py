#!/usr/bin/env python3
"""测试修复效果"""

import platform
print(f"Platform: {platform.system()}")
print("=" * 60)

# 测试 1: CPU 温度（跨平台）
print("\n[TEST 1] CPU Temperature")
from energy_monitor_server import monitor

cpu_temp = monitor.get_cpu_temp()
print(f"  Result: {cpu_temp}°C")
print(f"  Status: {'OK' if cpu_temp else 'Using estimation'}")

# 测试 2: GPU 信息（带容错）
print("\n[TEST 2] GPU Info")
gpu_info = monitor.get_gpu_info()
print(f"  Name: {gpu_info.get('name', 'N/A')}")
print(f"  Temp: {gpu_info.get('temp', 'N/A')}°C")
print(f"  Util: {gpu_info.get('util', 'N/A')}%")
print(f"  Power: {gpu_info.get('power', 'N/A')}W")
print(f"  VRAM: {gpu_info.get('mem_used', 'N/A')}/{gpu_info.get('mem_total', 'N/A')}GB")

# 测试 3: 进程列表（包含 System Idle Process）
print("\n[TEST 3] Process List (including System Idle Process)")
processes, total = monitor.get_process_energy()
system_idle_found = any(p['name'] == 'System Idle Process' for p in processes)
print(f"  Total processes: {len(processes)}")
print(f"  System Idle Process found: {system_idle_found}")
print(f"  Top 5 processes:")
for i, p in enumerate(processes[:5], 1):
    cpu_str = f"{p['cpu']:.1f}%" if p['cpu'] <= 100 else f"{p['cpu']:.0f}%"
    print(f"    {i}. {p['name'][:25]:<25} CPU:{cpu_str:>6} Power:{p['power_w']:.2f}W")

# 测试 4: CPU 信息（包含功率和内存）
print("\n[TEST 4] CPU Info")
cpu_info = monitor.get_cpu_info()
print(f"  Usage: {cpu_info['usage']:.1f}%")
print(f"  Temp: {cpu_info.get('temp', 'N/A')}°C")
print(f"  Power: {cpu_info.get('power', 'N/A')}W (estimated)")
print(f"  Memory: {cpu_info.get('mem_usage', 'N/A')}%")

print("\n" + "=" * 60)
print("All tests completed!")
