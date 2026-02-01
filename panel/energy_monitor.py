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

# NVML GPU 支持
try:
    from pynvml import (
        nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetName, nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage
    )
    nvmlInit()
    NVML_AVAILABLE = True
    NVML_DEVICE_COUNT = nvmlDeviceGetCount()
    print(f"[INFO] NVML initialized: {NVML_DEVICE_COUNT} GPU(s) detected")
except Exception as e:
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0
    print(f"[INFO] NVML not available: {e}")

# 配置
UPDATE_INTERVAL = 1
HISTORY_LENGTH = 60

class EnergyMonitor:
    def __init__(self):
        self.process_history = deque(maxlen=HISTORY_LENGTH)
        self.power_history = deque(maxlen=HISTORY_LENGTH)
        self.temp_history = deque(maxlen=HISTORY_LENGTH)
        self.gpu_util_history = deque(maxlen=HISTORY_LENGTH)
        self.cpu_usage = 0
        self.wmi = None
        self._cpu_init = False
        
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
    
    def get_cpu_usage(self):
        """获取 CPU 使用率（需要初始化）"""
        if not self._cpu_init:
            psutil.cpu_percent(interval=None)
            self._cpu_init = True
            return 0
        return psutil.cpu_percent(interval=None)
    
    def get_cpu_temp(self):
        """获取 CPU 温度"""
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        return tz.CurrentTemperature / 10.0 - 273.15
            except:
                pass
        # 基于负载估算
        return 40 + self.cpu_usage * 0.5
    
    def get_gpu_info(self):
        """获取 GPU 信息：温度、使用率、功耗、名称"""
        info = {'temp': None, 'util': None, 'power': None, 'name': None}
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            
            # GPU 名称
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else name
            except:
                info['name'] = "NVIDIA GPU"
            
            # GPU 温度
            try:
                info['temp'] = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except:
                pass
            
            # GPU 使用率
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                info['util'] = util.gpu
            except:
                pass
            
            # GPU 功耗 (毫瓦转瓦)
            try:
                power_mw = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(power_mw / 1000.0, 1)
            except:
                pass
                
        except Exception as e:
            pass
        
        return info
    
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
                
                # 估算功耗
                power_w = 5.0 + (cpu * 0.3) + (mem * 0.05)
                total_power += power_w
                
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'][:25],
                    'cpu': cpu,
                    'mem': mem,
                    'power_w': power_w,
                    'power_mw': power_w * 1000
                })
            except:
                continue
        
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
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
        self.cpu_usage = self.get_cpu_usage()
        mem_usage = psutil.virtual_memory().percent
        temps = {
            'cpu': self.get_cpu_temp(),
            'gpu': None,
            'battery': self.get_battery_temp()
        }
        gpu_info = self.get_gpu_info()
        if gpu_info['temp']:
            temps['gpu'] = gpu_info['temp']
        
        battery = self.get_battery_info()
        processes, total_power = self.get_process_energy()
        
        # 保存历史
        self.power_history.append(total_power)
        self.temp_history.append(temps['cpu'])
        if gpu_info['util']:
            self.gpu_util_history.append(gpu_info['util'])
        
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
        
        cpu_bar = self.format_bar(min(temps['cpu'] or 0, 100), 100, 12)
        gpu_bar = self.format_bar(min(temps['gpu'] or 0, 100), 100, 12) if temps['gpu'] else "N/A"
        print(f"║ CPU: {cpu_str:>6} {cpu_bar}  GPU: {gpu_str:>6} {gpu_bar}  Battery: {batt_str:>6}    ║")
        
        # GPU 信息
        if gpu_info['name']:
            print("╠" + "═" * 78 + "╣")
            print(f"║ [GPU: {gpu_info['name'][:25]:<25}]                                    ║")
            util_str = f"{gpu_info['util']:.1f}%" if gpu_info['util'] else "N/A"
            power_str = f"{gpu_info['power']:.1f}W" if gpu_info['power'] else "N/A"
            print(f"║   Utilization: {util_str:>6}    Power: {power_str:>6}    Temp: {gpu_str:>6}              ║")
        
        # 系统功耗
        print("╠" + "═" * 78 + "╣")
        print("║ [SYSTEM POWER]                                                             ║")
        cpu_bar = self.format_bar(self.cpu_usage, 100, 12)
        mem_bar = self.format_bar(mem_usage, 100, 12)
        print(f"║ Total: {total_power:>6.1f}W   CPU: {self.cpu_usage:>5.1f}% {cpu_bar}   Mem: {mem_usage:>5.1f}% {mem_bar}  ║")
        
        # 电池状态
        if battery:
            print("╠" + "═" * 78 + "╣")
            print("║ [BATTERY]                                                                  ║")
            batt_bar = self.format_bar(battery['percent'], 100, 20)
            status = "⚡ CHARGING " if battery['plugged'] else "🔋 DISCHARGING"
            print(f"║ {batt_bar} {battery['percent']:>5.1f}%  {status:<15}  {battery['time_left']:<12}        ║")
        
        # 高耗能进程
        print("╠" + "═" * 78 + "╣")
        print("║ [TOP ENERGY CONSUMING PROCESSES]                                           ║")
        print("║ Rank │ Process Name              │  Power   │    %    │ CPU%  │ Mem%       ║")
        print("║──────┼───────────────────────────┼──────────┼─────────┼───────┼────────────║")
        
        for i, p in enumerate(processes[:8], 1):
            name = p['name'][:25]
            print(f"║ {i:>4} │ {name:<25} │ {p['power_w']:>6.1f}W  │ {p['percent']:>5.1f}% │ {p['cpu']:>5.1f} │ {p['mem']:>6.1f}     ║")
        
        print("╚" + "═" * 78 + "╝")
        
        # 趋势图
        print("\n[POWER TREND - Last 60 seconds]")
        if len(self.power_history) > 1:
            recent = list(self.power_history)[-30:]
            max_p = max(recent) if recent else 1
            min_p = min(recent) if recent else 0
            if max_p == min_p:
                max_p = min_p + 1
            
            for p in recent[-10:]:
                height = int((p - min_p) / (max_p - min_p) * 15)
                bar = '█' * height + '░' * (15 - height)
                print(f" {bar} {p:>6.1f}W")
        
        # GPU 使用率趋势
        if len(self.gpu_util_history) > 1:
            print("\n[GPU UTILIZATION TREND]")
            recent = list(self.gpu_util_history)[-10:]
            for u in recent:
                height = int(u / 100 * 15)
                bar = '█' * height + '░' * (15 - height)
                print(f" {bar} {u:>5.1f}%")
    
    def run(self):
        """运行监控循环"""
        print("Starting Energy Monitor...")
        print("Initializing CPU monitor (please wait)...")
        self.get_cpu_usage()  # 初始化
        time.sleep(1)
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
