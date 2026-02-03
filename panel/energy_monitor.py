#!/usr/bin/env python3
"""
轻量级实时能耗监控 - 命令行版本
"""

import os
import sys
import time
from datetime import datetime
from collections import deque

import psutil

try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

try:
    from pynvml import (
        nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex,
        nvmlDeviceGetName, nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage,
        nvmlDeviceGetMemoryInfo, NVMLError
    )
    nvmlInit()
    NVML_AVAILABLE = True
    NVML_DEVICE_COUNT = nvmlDeviceGetCount()
    print(f"[INFO] NVML initialized: {NVML_DEVICE_COUNT} GPU(s)")
except Exception as e:
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0
    print(f"[INFO] NVML not available: {e}")

UPDATE_INTERVAL = 1

class EnergyMonitor:
    def __init__(self):
        self.power_history = deque(maxlen=60)
        self.cpu_temp_history = deque(maxlen=60)
        self.gpu_temp_history = deque(maxlen=60)
        self._cpu_init = False
        self.wmi = None
        
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
    
    def get_cpu_temp(self):
        """获取 CPU 温度"""
        # 方法 1: WMI
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        celsius = tz.CurrentTemperature / 10.0 - 273.15
                        if 0 < celsius < 150:
                            return round(celsius, 1)
            except:
                pass
        
        # 方法 2: psutil
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                for key in ['coretemp', 'k10temp', 'cpu_thermal', 'acpitz']:
                    if key in temps:
                        return round(temps[key][0].current, 1)
        except:
            pass
        
        # 方法 3: 估算
        try:
            load = psutil.cpu_percent(interval=0.1)
            return round(40 + load * 0.6, 1)
        except:
            pass
        
        return None
    
    def get_gpu_info(self):
        """获取 GPU 信息"""
        info = {'name': None, 'temp': None, 'util': None, 'power': None}
        
        if not NVML_AVAILABLE:
            return info
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else str(name)
            except:
                info['name'] = "NVIDIA GPU"
            
            try:
                info['temp'] = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except:
                pass
            
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                info['util'] = util.gpu
            except:
                pass
            
            try:
                power = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(power / 1000.0, 1)
            except:
                pass
                
        except Exception as e:
            print(f"[ERROR] GPU: {e}")
        
        return info
    
    def display_dashboard(self):
        self.clear_screen()
        
        # 获取数据
        if not self._cpu_init:
            psutil.cpu_percent(interval=0.1)
            self._cpu_init = True
            time.sleep(0.3)
        
        cpu_usage = psutil.cpu_percent(interval=0.1)
        cpu_temp = self.get_cpu_temp()
        gpu_info = self.get_gpu_info()
        mem = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        
        # 获取进程
        processes = []
        total_power = 0
        for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                name = info['name'] or "Unknown"
                if name in ['System Idle Process', 'Registry']:
                    continue
                cpu = min(info['cpu_percent'] or 0, 100)
                mem_pct = info['memory_percent'] or 0
                power = 2.0 + cpu * 0.5 + mem_pct * 0.1
                total_power += power
                processes.append({'name': name[:25], 'cpu': cpu, 'mem': mem_pct, 'power': power})
            except:
                continue
        
        processes.sort(key=lambda x: x['power'], reverse=True)
        
        # 保存历史
        self.power_history.append(total_power)
        if cpu_temp:
            self.cpu_temp_history.append(cpu_temp)
        if gpu_info['temp']:
            self.gpu_temp_history.append(gpu_info['temp'])
        
        # 打印
        print("╔" + "═" * 76 + "╗")
        print(f"║{'⚡ ENERGY MONITOR':^76}║")
        print(f"║{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^76}║")
        print("╠" + "═" * 76 + "╣")
        
        # CPU
        temp_str = f"{cpu_temp:.1f}°C" if cpu_temp else "N/A"
        print(f"║ [CPU] Temp: {temp_str:>8}  Usage: {cpu_usage:>6.1f}%  Memory: {mem.percent:.1f}%       ║")
        
        # GPU
        if gpu_info['name']:
            gpu_temp = f"{gpu_info['temp']}°C" if gpu_info['temp'] else "N/A"
            gpu_util = f"{gpu_info['util']}%" if gpu_info['util'] is not None else "N/A"
            gpu_power = f"{gpu_info['power']}W" if gpu_info['power'] else "N/A"
            print("╠" + "═" * 76 + "╣")
            print(f"║ [GPU] {gpu_info['name'][:50]:<50}             ║")
            print(f"║       Temp: {gpu_temp:>8}  Util: {gpu_util:>6}  Power: {gpu_power:>6}              ║")
        
        # Battery
        if battery:
            print("╠" + "═" * 76 + "╣")
            status = "⚡ Charging" if battery.power_plugged else "🔋 Battery"
            print(f"║ [BATTERY] {battery.percent:.1f}%  {status:<20}                           ║")
        
        # Power & Processes
        print("╠" + "═" * 76 + "╣")
        print(f"║ [POWER] Total: {total_power:.1f}W                                          ║")
        print("║ Top Processes:                                                           ║")
        print("║ Rank │ Process                │ Power   │ CPU   │ Memory                 ║")
        print("║──────┼────────────────────────┼─────────┼───────┼────────────────────────║")
        
        for i, p in enumerate(processes[:6], 1):
            print(f"║ {i:>4} │ {p['name']:<22} │ {p['power']:>6.2f}W │ {p['cpu']:>5.1f}%│ {p['mem']:>6.1f}%              ║")
        
        print("╚" + "═" * 76 + "╝")
        
        # 温度趋势
        if len(self.cpu_temp_history) > 1:
            print("\n[CPU Temperature History]")
            recent = list(self.cpu_temp_history)[-10:]
            for t in recent:
                bar = "█" * int((t - 30) / 70 * 15) if t > 30 else ""
                print(f"  {bar:<15} {t:.1f}°C")
    
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def run(self):
        print("Starting Energy Monitor...")
        time.sleep(1)
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                self.display_dashboard()
                time.sleep(UPDATE_INTERVAL)
        except KeyboardInterrupt:
            print("\n\nStopped.")

if __name__ == "__main__":
    monitor = EnergyMonitor()
    monitor.run()
