#!/usr/bin/env python3
"""快速测试"""
from energy_monitor_dashboard import LightweightEnergyMonitor

monitor = LightweightEnergyMonitor(update_interval=1.0)

print("=" * 50)
print("功耗测试:")
power = monitor.get_current_power()
print(f"  总功耗: {power['total_w']:.2f} W")
print(f"  CPU: {power['cpu_w']:.2f} W")
print(f"  GPU: {power['gpu_w']:.2f} W")
print(f"  内存: {power['memory_w']:.2f} W")

print("=" * 50)
print("温度测试:")
temps = monitor.get_system_temperature()
print(f"  CPU: {temps.cpu_temp if temps.cpu_temp else 'N/A'}")
print(f"  GPU: {temps.gpu_temp if temps.gpu_temp else 'N/A'}")

print("=" * 50)
print("进程测试:")
processes = monitor.get_process_energy()
print(f"  找到 {len(processes)} 个进程")
if processes:
    print("  Top 3 进程:")
    for i, p in enumerate(processes[:3], 1):
        unit = 'W' if p.power_mw >= 1000 else 'mW'
        val = p.power_mw/1000 if p.power_mw >= 1000 else p.power_mw
        print(f"    {i}. {p.name[:20]:20s} {val:8.2f} {unit}  CPU:{p.cpu_percent:5.1f}%")

print("=" * 50)
print("所有测试通过!")
