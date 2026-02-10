#!/usr/bin/env python3
"""
轻量级实时能耗监控看板
实时显示高耗能进程、温度检测、能耗趋势
"""

import os
import sys
import time
import json
import psutil
from datetime import datetime
from collections import deque

# 尝试导入温度检测库
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

try:
    from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex
    from pynvml import nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU
    nvmlInit()
    NVML_AVAILABLE = True
    NVML_DEVICE_COUNT = nvmlDeviceGetCount()
except:
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0

# 配置
UPDATE_INTERVAL = 1  # 秒
HISTORY_LENGTH = 60  # 保存60秒历史

class EnergyMonitor:
    def __init__(self):
        self.process_history = deque(maxlen=HISTORY_LENGTH)
        self.power_history = deque(maxlen=HISTORY_LENGTH)
        self.temp_history = deque(maxlen=HISTORY_LENGTH)
        self.wmi = None
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
    
    def get_cpu_temp(self):
        """获取CPU温度"""
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        return tz.CurrentTemperature / 10.0 - 273.15
            except:
                pass
        # 估算
        cpu_load = psutil.cpu_percent()
        return 40 + cpu_load * 0.5
    
    def get_gpu_temp(self):
        """获取GPU温度"""
        if NVML_AVAILABLE and NVML_DEVICE_COUNT > 0:
            try:
                handle = nvmlDeviceGetHandleByIndex(0)
                return nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except:
                pass
        return None
    
    def get_battery_temp(self):
        """获取电池温度"""
        if self.wmi:
            try:
                for bat in self.wmi.Win32_Battery():
                    if hasattr(bat, 'Temperature') and bat.Temperature:
                        return float(bat.Temperature)
            except:
                pass
        return None
    
    def get_battery_info(self):
        """获取电池信息"""
        battery = psutil.sensors_battery()
        if battery:
            hours_left = "N/A"
            if not battery.power_plugged and battery.secsleft > 0:
                hours = battery.secsleft // 3600
                mins = (battery.secsleft % 3600) // 60
                hours_left = f"{hours}h {mins}m"
            
            return {
                'percent': battery.percent,
                'plugged': battery.power_plugged,
                'time_left': hours_left
            }
        return None
    
    def get_process_energy(self):
        """获取进程能耗信息"""
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                cpu = info['cpu_percent'] or 0
                mem = info['memory_percent'] or 0
                
                # 估算功耗: 基础5W + CPU贡献 + 内存贡献
                power_w = 5.0 + (cpu * 0.3) + (mem * 0.05)
                total_power += power_w
                
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'][:25],
                    'cpu': cpu,
                    'mem': mem,
                    'power_w': power_w,
                    'power_mw': power_w * 1000  # 毫瓦
                })
            except:
                continue
        
        # 按功耗排序
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
        # 计算百分比
        for p in processes:
            p['percent'] = (p['power_w'] / total_power * 100) if total_power > 0 else 0
        
        return processes, total_power
    
    def clear_screen(self):
        """清屏"""
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def format_bar(self, value, max_val=100, width=20):
        """格式化进度条"""
        filled = int(value / max_val * width)
        return '█' * filled + '░' * (width - filled)
    
    def display_dashboard(self):
        """显示实时看板"""
        self.clear_screen()
        
        # 获取数据
        temps = {
            'cpu': self.get_cpu_temp(),
            'gpu': self.get_gpu_temp(),
            'battery': self.get_battery_temp()
        }
        battery = self.get_battery_info()
        processes, total_power = self.get_process_energy()
        
        # 保存历史
        self.temp_history.append(temps)
        self.power_history.append(total_power)
        
        # 打印看板
        print("╔" + "═" * 78 + "╗")
        print(f"║{'ENERGY MONITOR - Real-time Dashboard':^78}║")
        print(f"║{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^78}║")
        print("╠" + "═" * 78 + "╣")
        
        # 温度区域
        print("║ [HARDWARE TEMPERATURE]                                                     ║")
        cpu_str = f"{temps['cpu']:.1f}°C" if temps['cpu'] else "N/A"
        gpu_str = f"{temps['gpu']:.1f}°C" if temps['gpu'] else "N/A"
        batt_str = f"{temps['battery']:.1f}°C" if temps['battery'] else "N/A"
        
        cpu_bar = self.format_bar(min(temps['cpu'] or 0, 100), 100, 15)
        print(f"║ CPU: {cpu_str:>6} {cpu_bar}  GPU: {gpu_str:>6}  Battery: {batt_str:>6}      ║")
        
        # 电池状态
        if battery:
            print("╠" + "═" * 78 + "╣")
            print("║ [BATTERY STATUS]                                                           ║")
            batt_bar = self.format_bar(battery['percent'], 100, 25)
            status = "⚡ Charging" if battery['plugged'] else "🔋 Discharging"
            print(f"║ {batt_bar} {battery['percent']:>5.1f}%  {status:<15} Time: {battery['time_left']:<10} ║")
        
        # 系统功耗
        print("╠" + "═" * 78 + "╣")
        print("║ [SYSTEM POWER]                                                             ║")
        cpu_usage = psutil.cpu_percent()
        mem_usage = psutil.virtual_memory().percent
        print(f"║ Total Power: {total_power:>6.1f} W    CPU: {cpu_usage:>5.1f}%    Memory: {mem_usage:>5.1f}%              ║")
        
        # 高耗能进程
        print("╠" + "═" * 78 + "╣")
        print("║ [TOP ENERGY CONSUMING PROCESSES]                                           ║")
        print("║ Rank │ Process Name              │  Power   │    %    │ CPU%  │ Memory%   ║")
        print("║──────┼───────────────────────────┼──────────┼─────────┼───────┼───────────║")
        
        for i, p in enumerate(processes[:8], 1):
            name = p['name'][:25]
            print(f"║ {i:>4} │ {name:<25} │ {p['power_w']:>6.1f}W  │ {p['percent']:>5.1f}% │ {p['cpu']:>5.1f} │ {p['mem']:>7.1f}   ║")
        
        print("╚" + "═" * 78 + "╝")
        
        # 简单趋势图（使用字符）
        if len(self.power_history) > 1:
            print("\n[Power Trend (W)]")
            recent = list(self.power_history)[-30:]
            max_p = max(recent) if recent else 1
            min_p = min(recent) if recent else 0
            if max_p == min_p:
                max_p = min_p + 1
            
            for p in recent:
                height = int((p - min_p) / (max_p - min_p) * 10)
                bar = '█' * height + '░' * (10 - height)
                print(f" {bar} {p:.1f}W")
    
    def run(self):
        """运行监控循环"""
        print("Starting Energy Monitor...")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.display_dashboard()
                time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")

if __name__ == "__main__":
    monitor = EnergyMonitor()
    monitor.run()
