#!/usr/bin/env python3
"""
轻量级实时能耗监控看板 - 命令行版本
实时显示高耗能进程、温度检测、能耗趋势
"""

import os
import sys
import time
from datetime import datetime
from collections import deque

import psutil

# WMI 支持
try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

# NVML GPU 支持
try:
    from pynvml import (
        nvmlInit, nvmlShutdown, nvmlDeviceGetCount, 
        nvmlDeviceGetHandleByIndex, nvmlDeviceGetName,
        nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage,
        nvmlDeviceGetMemoryInfo, NVMLError
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
        self.power_history = deque(maxlen=HISTORY_LENGTH)
        self.cpu_temp_history = deque(maxlen=HISTORY_LENGTH)
        self.gpu_temp_history = deque(maxlen=HISTORY_LENGTH)
        self.cpu_cores = psutil.cpu_count()
        self.cpu_logical = psutil.cpu_count(logical=True)
        self._cpu_init = False
        self.wmi = None
        
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
    
    def get_cpu_info(self):
        """获取完整的CPU信息"""
        info = {'usage': 0, 'temp': None, 'freq': 0}
        
        # 初始化CPU使用率
        if not self._cpu_init:
            psutil.cpu_percent(interval=0.1)
            self._cpu_init = True
            time.sleep(0.3)
        
        info['usage'] = psutil.cpu_percent(interval=0.1)
        
        try:
            freq = psutil.cpu_freq()
            if freq:
                info['freq'] = round(freq.current, 0)
        except:
            pass
        
        # CPU温度
        info['temp'] = self.get_cpu_temp()
        
        return info
    
    def get_cpu_temp(self):
        """获取CPU温度"""
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        return round(tz.CurrentTemperature / 10.0 - 273.15, 1)
            except:
                pass
        
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ['coretemp', 'k10temp', 'cpu-thermal']:
                    if key in temps:
                        return round(temps[key][0].current, 1)
        except:
            pass
        
        return None
    
    def get_gpu_info(self):
        """获取GPU信息"""
        info = {
            'name': None, 'temp': None, 'util': None, 
            'power': None, 'mem_used': None, 'mem_total': None
        }
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            
            # 名称
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else str(name)
            except:
                info['name'] = "NVIDIA GPU"
            
            # 温度
            try:
                info['temp'] = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except:
                pass
            
            # 使用率
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                info['util'] = util.gpu
            except:
                pass
            
            # 功耗
            try:
                power_mw = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(power_mw / 1000.0, 1)
            except:
                pass
            
            # 显存
            try:
                mem = nvmlDeviceGetMemoryInfo(handle)
                info['mem_used'] = round(mem.used / 1024**3, 1)
                info['mem_total'] = round(mem.total / 1024**3, 1)
            except:
                pass
                
        except Exception as e:
            pass
        
        return info
    
    def get_battery_info(self):
        """获取电池信息"""
        battery = psutil.sensors_battery()
        if not battery:
            return None
        
        info = {
            'percent': battery.percent,
            'plugged': battery.power_plugged,
            'time_left': "N/A"
        }
        
        if battery.power_plugged:
            info['time_left'] = "Charging" if battery.percent < 99 else "Fully Charged"
        elif battery.secsleft > 0:
            hours = battery.secsleft // 3600
            mins = (battery.secsleft % 3600) // 60
            info['time_left'] = f"{hours}h {mins}m"
        
        return info
    
    def get_process_energy(self):
        """获取进程能耗"""
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                info = proc.info
                name = info['name'] or "Unknown"
                
                # 过滤系统进程
                if name in ['System Idle Process', 'Registry']:
                    continue
                
                cpu = info['cpu_percent'] or 0
                if cpu > 100:
                    cpu = min(cpu, 100)
                
                mem = info['memory_percent'] or 0
                power_w = 2.0 + (cpu * 0.5) + (mem * 0.1)
                total_power += power_w
                
                processes.append({
                    'name': name[:28],
                    'cpu': cpu,
                    'mem': mem,
                    'power_w': power_w,
                    'percent': 0,
                    'status': info['status'] or 'running'
                })
            except:
                continue
        
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
        for p in processes:
            p['percent'] = (p['power_w'] / total_power * 100) if total_power > 0 else 0
        
        return processes[:10], total_power
    
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def display_dashboard(self):
        self.clear_screen()
        
        # 获取数据
        cpu_info = self.get_cpu_info()
        gpu_info = self.get_gpu_info()
        battery = self.get_battery_info()
        processes, total_power = self.get_process_energy()
        mem = psutil.virtual_memory()
        
        # 保存历史
        self.power_history.append(total_power)
        if cpu_info['temp']:
            self.cpu_temp_history.append(cpu_info['temp'])
        if gpu_info['temp']:
            self.gpu_temp_history.append(gpu_info['temp'])
        
        # 打印看板
        print("╔" + "═" * 78 + "╗")
        print(f"║{'⚡ ENERGY MONITOR - Real-time Dashboard':^78}║")
        print(f"║{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^78}║")
        print("╠" + "═" * 78 + "╣")
        
        # CPU 信息
        cpu_temp_str = f"{cpu_info['temp']:.1f}°C" if cpu_info['temp'] else "N/A"
        print(f"║ [CPU] {self.cpu_cores} Cores / {self.cpu_logical} Threads                                        ║")
        print(f"║   Temperature: {cpu_temp_str:>8}  Usage: {cpu_info['usage']:>5.1f}%  Frequency: {cpu_info['freq']:>4.0f} MHz      ║")
        
        # GPU 信息
        if gpu_info['name']:
            print("╠" + "═" * 78 + "╣")
            gpu_name = gpu_info['name'][:50]
            gpu_temp = f"{gpu_info['temp']}°C" if gpu_info['temp'] else "N/A"
            gpu_util = f"{gpu_info['util']}%" if gpu_info['util'] is not None else "N/A"
            gpu_power = f"{gpu_info['power']}W" if gpu_info['power'] else "N/A"
            gpu_mem = f"{gpu_info['mem_used']}/{gpu_info['mem_total']}GB" if gpu_info['mem_used'] else "N/A"
            print(f"║ [GPU] {gpu_name:<56} ║")
            print(f"║   Temp: {gpu_temp:>8}  Util: {gpu_util:>6}  Power: {gpu_power:>6}  VRAM: {gpu_mem:<12} ║")
        
        # 系统功耗
        print("╠" + "═" * 78 + "╣")
        print(f"║ [SYSTEM]  Total Power: {total_power:>7.1f}W  Memory: {mem.percent:>5.1f}% ({mem.used//1024**3}GB used)     ║")
        
        # 电池
        if battery:
            status = "⚡ Charging" if battery['plugged'] else "🔋 Battery"
            print(f"║ [BATTERY] {battery['percent']:>5.1f}%  {status:<15}  {battery['time_left']:<20}      ║")
        
        # 进程列表
        print("╠" + "═" * 78 + "╣")
        print("║ Top Energy Consuming Processes:                                            ║")
        print("║ Rank │ Process                    │ Power   │ Share │  CPU  │ Memory      ║")
        print("║──────┼────────────────────────────┼─────────┼───────┼───────┼─────────────║")
        
        for i, p in enumerate(processes[:8], 1):
            status_icon = "●" if p['status'] == 'running' else "○"
            print(f"║ {i:>4} │ {p['name']:<26} │ {p['power_w']:>6.2f}W │ {p['percent']:>5.1f}%│ {p['cpu']:>5.1f}%│ {p['mem']:>6.1f}% {status_icon}    ║")
        
        print("╚" + "═" * 78 + "╝")
        
        # 趋势图
        print("\n[CPU Temperature Trend - Last 30 seconds]")
        if len(self.cpu_temp_history) > 1:
            recent = list(self.cpu_temp_history)[-30:]
            for temp in recent[-10:]:
                bar = "█" * int((temp - 30) / 70 * 20) if temp > 30 else ""
                print(f"  {bar:<20} {temp:.1f}°C")
        
        if gpu_info['temp']:
            print("\n[GPU Temperature]")
            print(f"  Current: {gpu_info['temp']}°C")
    
    def run(self):
        print("Starting Energy Monitor...")
        print("Initializing (please wait)...")
        self.get_cpu_info()  # 初始化
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
