#!/usr/bin/env python3
"""
轻量级实时能耗监控 - 命令行版本
修复版：跨平台兼容、容错增强
"""

import os
import sys
import time
import platform
from datetime import datetime
from collections import deque

import psutil

# 平台检测
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# WMI 支持（仅 Windows）
WMI_AVAILABLE = False
wmi_module = None
if IS_WINDOWS:
    try:
        import wmi
        wmi_module = wmi
        WMI_AVAILABLE = True
    except ImportError:
        pass

# NVML GPU 支持
NVML_AVAILABLE = False
NVML_DEVICE_COUNT = 0
nvml_handle = None

def init_nvml():
    """初始化 NVML"""
    global NVML_AVAILABLE, NVML_DEVICE_COUNT, nvml_handle
    try:
        from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex
        nvmlInit()
        NVML_DEVICE_COUNT = nvmlDeviceGetCount()
        if NVML_DEVICE_COUNT > 0:
            nvml_handle = nvmlDeviceGetHandleByIndex(0)
        NVML_AVAILABLE = True
        return True
    except:
        return False

init_nvml()

UPDATE_INTERVAL = 1

class EnergyMonitor:
    def __init__(self):
        self.power_history = deque(maxlen=60)
        self.cpu_temp_history = deque(maxlen=60)
        self.gpu_temp_history = deque(maxlen=60)
        self._cpu_init = False
        self._last_valid_cpu_temp = None
        self._last_valid_gpu_temp = None
        self._last_gpu_info = {}
        self.wmi = None
        
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi_module.WMI()
            except:
                pass
    
    def get_cpu_temp(self):
        """获取 CPU 温度 - 跨平台"""
        temp = None
        
        # Windows: WMI 多种尝试
        if IS_WINDOWS and self.wmi:
            for cls_name in ['MSAcpi_ThermalZoneTemperature', 'Win32_TemperatureProbe', 
                            'CIM_TemperatureSensor']:
                try:
                    sensors = getattr(self.wmi, cls_name)()
                    for sensor in sensors:
                        current = getattr(sensor, 'CurrentTemperature', None) or \
                                 getattr(sensor, 'Temperature', None)
                        if current:
                            if current > 2730:
                                celsius = current / 10.0 - 273.15
                            elif current > 273:
                                celsius = current - 273.15
                            else:
                                celsius = current
                            if 0 < celsius < 150:
                                temp = round(celsius, 1)
                                self._last_valid_cpu_temp = temp
                                return temp
                except:
                    continue
        
        # Linux: lm-sensors
        elif IS_LINUX:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ['coretemp', 'k10temp', 'cpu_thermal']:
                        if key in temps and temps[key]:
                            t = temps[key][0].current
                            if t and 0 < t < 150:
                                temp = round(t, 1)
                                self._last_valid_cpu_temp = temp
                                return temp
            except:
                pass
        
        # 估算
        try:
            load = psutil.cpu_percent(interval=0.1)
            temp = round(35 + load * 0.5, 1)
        except:
            pass
        
        if temp is None and self._last_valid_cpu_temp:
            return self._last_valid_cpu_temp
        if temp:
            self._last_valid_cpu_temp = temp
        return temp
    
    def get_gpu_info(self):
        """获取 GPU 信息 - 带容错"""
        info = {'name': None, 'temp': None, 'util': None, 'power': None}
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            from pynvml import (
                nvmlDeviceGetName, nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
                nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage,
                nvmlDeviceGetMemoryInfo
            )
            handle = nvml_handle
            
            # 名称
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else str(name)
            except:
                info['name'] = self._last_gpu_info.get('name', "NVIDIA GPU")
            
            # 温度 - 带校验
            try:
                t = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
                if 0 < t < 120:
                    info['temp'] = t
                    self._last_valid_gpu_temp = t
                elif self._last_valid_gpu_temp:
                    info['temp'] = self._last_valid_gpu_temp
            except:
                if self._last_valid_gpu_temp:
                    info['temp'] = self._last_valid_gpu_temp
            
            # 使用率
            try:
                u = nvmlDeviceGetUtilizationRates(handle)
                info['util'] = u.gpu if 0 <= u.gpu <= 100 else 0
            except:
                pass
            
            # 功耗
            try:
                p = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(p / 1000.0, 1) if p > 0 else None
            except:
                pass
            
            # 显存
            try:
                m = nvmlDeviceGetMemoryInfo(handle)
                info['mem_used'] = round(m.used / 1024**3, 1)
                info['mem_total'] = round(m.total / 1024**3, 1)
            except:
                pass
            
            self._last_gpu_info = {k: v for k, v in info.items() if v is not None}
            
        except Exception as e:
            info.update(self._last_gpu_info)
        
        return info
    
    def display_dashboard(self):
        self.clear_screen()
        
        # 获取数据
        if not self._cpu_init:
            psutil.cpu_percent(interval=None)
            self._cpu_init = True
            time.sleep(0.5)
        
        cpu_usage = psutil.cpu_percent(interval=0.1)
        cpu_temp = self.get_cpu_temp()
        cpu_power = round(15.0 + cpu_usage * 0.5, 1)
        
        gpu_info = self.get_gpu_info()
        mem = psutil.virtual_memory()
        battery = psutil.sensors_battery()
        
        # 获取进程 - 包含 System Idle Process
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                name = info['name'] or "Unknown"
                
                if name == 'Registry':
                    continue
                
                cpu = info['cpu_percent'] or 0
                # 保留 System Idle Process 原始值
                if name != 'System Idle Process':
                    cpu = min(cpu, 100)
                
                mem_pct = info['memory_percent'] or 0
                
                if name == 'System Idle Process':
                    power = 0.1
                else:
                    power = 2.0 + (cpu * 0.5) + (mem_pct * 0.1)
                
                total_power += power
                
                processes.append({
                    'name': name[:28],
                    'cpu': cpu,
                    'mem': mem_pct,
                    'power': power
                })
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
        print("╔" + "═" * 78 + "╗")
        print(f"║{'⚡ ENERGY MONITOR':^78}║")
        print(f"║{datetime.now().strftime('%Y-%m-%d %H:%M:%S'):^78}║")
        print("╠" + "═" * 78 + "╣")
        
        # CPU
        temp_str = f"{cpu_temp:.1f}°C" if cpu_temp else "N/A"
        print(f"║ [CPU] Temp: {temp_str:>8}  Usage: {cpu_usage:>6.1f}%  Power: {cpu_power:>6.1f}W      ║")
        print(f"║       Memory: {mem.percent:>5.1f}%                                           ║")
        
        # GPU
        if gpu_info['name']:
            gpu_temp = f"{gpu_info['temp']}°C" if gpu_info['temp'] else "N/A"
            gpu_util = f"{gpu_info['util']}%" if gpu_info['util'] is not None else "N/A"
            gpu_power = f"{gpu_info['power']}W" if gpu_info['power'] else "N/A"
            gpu_mem = f"{gpu_info.get('mem_used')}/{gpu_info.get('mem_total')}GB" if gpu_info.get('mem_used') else "N/A"
            print("╠" + "═" * 78 + "╣")
            print(f"║ [GPU] {gpu_info['name'][:50]:<50}       ║")
            print(f"║       Temp: {gpu_temp:>8}  Util: {gpu_util:>6}  Power: {gpu_power:>6}  VRAM: {gpu_mem:<12} ║")
        
        # Battery
        if battery:
            print("╠" + "═" * 78 + "╣")
            status = "⚡ Charging" if battery.power_plugged else "🔋 Battery"
            print(f"║ [BATTERY] {battery.percent:.1f}%  {status:<20}                           ║")
        
        # Power & Processes
        print("╠" + "═" * 78 + "╣")
        print(f"║ [POWER] Total: {total_power:.1f}W                                        ║")
        print("║ Top Processes (including System Idle Process):                             ║")
        print("║ Rank │ Process                │ Power   │ CPU    │ Memory                 ║")
        print("║──────┼────────────────────────┼─────────┼────────┼────────────────────────║")
        
        for i, p in enumerate(processes[:8], 1):
            cpu_str = f"{p['cpu']:.1f}%" if p['cpu'] <= 100 else f"{p['cpu']:.0f}%"
            print(f"║ {i:>4} │ {p['name']:<22} │ {p['power']:>6.2f}W │ {cpu_str:>6} │ {p['mem']:>6.1f}%             ║")
        
        print("╚" + "═" * 78 + "╝")
        
        # 趋势
        if len(self.cpu_temp_history) > 1:
            print("\n[CPU Temperature History]")
            recent = list(self.cpu_temp_history)[-10:]
            for t in recent:
                bar = "█" * int((t - 30) / 70 * 15) if t > 30 else ""
                print(f"  {bar:<15} {t:.1f}°C")
    
    def clear_screen(self):
        os.system('cls' if os.name == 'nt' else 'clear')
    
    def run(self):
        print(f"Energy Monitor - {platform.system()}")
        print("Initializing...")
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
