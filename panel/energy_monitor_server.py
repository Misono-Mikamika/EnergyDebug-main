#!/usr/bin/env python3
"""
轻量级实时能耗监控 Web 服务
提供 REST API 和 Web 前端
"""

import os
import sys
import time
import threading
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify
from flask_cors import CORS

import psutil

# WMI 支持
try:
    import wmi
    WMI_AVAILABLE = True
    print("[INFO] WMI module loaded successfully")
except ImportError:
    WMI_AVAILABLE = False
    print("[WARNING] WMI module not available")

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
    print(f"[WARNING] NVML not available: {e}")
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

class MonitorData:
    def __init__(self):
        self.processes = []
        self.cpu_info = {'usage': 0, 'temp': None, 'freq': 0, 'cores': 0}
        self.gpu_info = {'temp': None, 'util': None, 'power': None, 'name': None}
        self.battery = None
        self.total_power = 0
        self.power_history = deque(maxlen=60)
        self.cpu_temp_history = deque(maxlen=60)
        self.gpu_temp_history = deque(maxlen=60)
        self.wmi = None
        
        # 初始化 WMI
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
                print("[INFO] WMI initialized")
            except Exception as e:
                print(f"[WARNING] WMI init failed: {e}")
        
        self.lock = threading.Lock()
        self._cpu_init = False
        self.cpu_cores = psutil.cpu_count()
        self.cpu_logical = psutil.cpu_count(logical=True)
    
    def get_cpu_temp(self):
        """获取 CPU 温度 - 多种方法尝试"""
        temp = None
        
        # 方法 1: WMI (Windows)
        if self.wmi:
            try:
                thermal_zones = self.wmi.MSAcpi_ThermalZoneTemperature()
                for tz in thermal_zones:
                    if hasattr(tz, 'CurrentTemperature'):
                        # WMI 返回的是开尔文 * 10
                        kelvin = tz.CurrentTemperature / 10.0
                        celsius = kelvin - 273.15
                        if 0 < celsius < 150:  # 合理范围检查
                            temp = round(celsius, 1)
                            print(f"[DEBUG] WMI CPU Temp: {temp}°C")
                            return temp
            except Exception as e:
                print(f"[DEBUG] WMI temp error: {e}")
        
        # 方法 2: psutil sensors_temperatures (Linux)
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                print(f"[DEBUG] Available temp sensors: {list(temps.keys())}")
                
                # 尝试常见的 CPU 温度键名
                for key in ['coretemp', 'k10temp', 'cpu_thermal', 'cpu-thermal', 
                           'acpitz', 'zenpower', 'it8688']:
                    if key in temps:
                        for entry in temps[key]:
                            if entry.current and 0 < entry.current < 150:
                                temp = round(entry.current, 1)
                                print(f"[DEBUG] psutil CPU Temp ({key}): {temp}°C")
                                return temp
        except Exception as e:
            print(f"[DEBUG] psutil sensors error: {e}")
        
        # 方法 3: 基于 CPU 负载估算
        try:
            cpu_load = psutil.cpu_percent(interval=0.1)
            # 基础 40°C + 每 1% 负载增加 0.6°C
            estimated = 40 + (cpu_load * 0.6)
            temp = round(estimated, 1)
            print(f"[DEBUG] Estimated CPU Temp: {temp}°C (load: {cpu_load}%)")
            return temp
        except Exception as e:
            print(f"[DEBUG] Estimation error: {e}")
        
        return temp
    
    def get_gpu_temp(self):
        """获取 GPU 温度"""
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return None
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            print(f"[DEBUG] GPU Temp: {temp}°C")
            return temp
        except Exception as e:
            print(f"[DEBUG] GPU temp error: {e}")
            return None
    
    def get_gpu_info(self):
        """获取 GPU 完整信息"""
        info = {
            'temp': None, 'util': None, 'power': None, 'name': None,
            'mem_used': None, 'mem_total': None, 'mem_percent': None
        }
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            
            # GPU 名称
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else str(name)
            except:
                info['name'] = "NVIDIA GPU"
            
            # GPU 温度
            try:
                info['temp'] = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except Exception as e:
                print(f"[DEBUG] GPU temp error: {e}")
            
            # GPU 使用率
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                info['util'] = util.gpu
            except Exception as e:
                print(f"[DEBUG] GPU util error: {e}")
            
            # GPU 功耗
            try:
                power_mw = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(power_mw / 1000.0, 1)
            except:
                pass
            
            # GPU 显存
            try:
                mem = nvmlDeviceGetMemoryInfo(handle)
                info['mem_used'] = round(mem.used / 1024**3, 1)
                info['mem_total'] = round(mem.total / 1024**3, 1)
                info['mem_percent'] = round((mem.used / mem.total) * 100, 1)
            except:
                pass
                
        except Exception as e:
            print(f"[ERROR] GPU info error: {e}")
        
        return info
    
    def get_cpu_info(self):
        """获取 CPU 完整信息"""
        info = {
            'usage': 0, 'temp': None, 'freq': 0,
            'cores': self.cpu_cores, 'logical': self.cpu_logical
        }
        
        # 初始化 CPU 使用率
        if not self._cpu_init:
            psutil.cpu_percent(interval=0.1)
            self._cpu_init = True
            time.sleep(0.3)
        
        # 获取使用率
        try:
            info['usage'] = psutil.cpu_percent(interval=0.1)
        except:
            pass
        
        # 获取频率
        try:
            freq = psutil.cpu_freq()
            if freq:
                info['freq'] = round(freq.current, 0)
        except:
            pass
        
        # 获取温度
        info['temp'] = self.get_cpu_temp()
        
        return info
    
    def get_battery_info(self):
        """获取电池信息"""
        battery = psutil.sensors_battery()
        if not battery:
            return None
        
        info = {
            'percent': battery.percent,
            'plugged': battery.power_plugged,
            'time_left': "N/A",
            'status': "Unknown"
        }
        
        if battery.power_plugged:
            info['status'] = "Charging"
            info['time_left'] = "Fully charged" if battery.percent >= 99 else "Calculating..."
        elif battery.secsleft == psutil.POWER_TIME_UNLIMITED:
            info['status'] = "AC Power"
            info['time_left'] = "∞"
        elif battery.secsleft > 0:
            hours = battery.secsleft // 3600
            mins = (battery.secsleft % 3600) // 60
            info['time_left'] = f"{hours}h {mins}m"
            info['status'] = "Discharging"
        
        return info
    
    def get_process_energy(self):
        """获取进程能耗"""
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                name = info['name'] or "Unknown"
                
                # 过滤系统空闲进程
                if name in ['System Idle Process', 'Registry', 'System']:
                    continue
                
                cpu = info['cpu_percent'] or 0
                if cpu > 100:
                    cpu = min(cpu, 100)
                
                mem = info['memory_percent'] or 0
                power_w = 2.0 + (cpu * 0.5) + (mem * 0.1)
                total_power += power_w
                
                processes.append({
                    'pid': info['pid'],
                    'name': name[:28],
                    'cpu': round(cpu, 1),
                    'mem': round(mem, 1),
                    'power_w': round(power_w, 2),
                    'percent': 0
                })
            except:
                continue
        
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
        for p in processes:
            p['percent'] = round((p['power_w'] / total_power * 100), 1) if total_power > 0 else 0
        
        return processes[:12], round(total_power, 1)
    
    def update(self):
        """后台更新循环"""
        print("[INFO] Monitor update thread started")
        
        while True:
            try:
                # 获取 CPU 信息
                cpu_info = self.get_cpu_info()
                
                # 获取 GPU 信息
                gpu_info = self.get_gpu_info()
                
                # 获取内存使用率
                mem = psutil.virtual_memory()
                
                # 获取进程和功耗
                processes, total_power = self.get_process_energy()
                
                # 获取电池
                battery = self.get_battery_info()
                
                # 更新历史数据
                with self.lock:
                    self.cpu_info = cpu_info
                    self.cpu_info['mem_usage'] = mem.percent
                    self.gpu_info = gpu_info
                    self.processes = processes
                    self.battery = battery
                    self.total_power = total_power
                    
                    # 保存历史
                    self.power_history.append(total_power)
                    if cpu_info['temp']:
                        self.cpu_temp_history.append(cpu_info['temp'])
                    if gpu_info['temp']:
                        self.gpu_temp_history.append(gpu_info['temp'])
                
                # 调试输出
                print(f"[DEBUG] CPU: {cpu_info['temp']}°C, GPU: {gpu_info['temp']}°C, "
                      f"CPU Usage: {cpu_info['usage']:.1f}%")
                
                time.sleep(1)
                
            except Exception as e:
                print(f"[ERROR] Update error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)
    
    def get_data(self):
        """获取当前数据"""
        with self.lock:
            return {
                'processes': list(self.processes),
                'cpu_info': dict(self.cpu_info),
                'gpu_info': dict(self.gpu_info),
                'battery': self.battery,
                'total_power': self.total_power,
                'power_history': list(self.power_history),
                'cpu_temp_history': list(self.cpu_temp_history),
                'gpu_temp_history': list(self.gpu_temp_history),
                'timestamp': datetime.now().strftime('%H:%M:%S')
            }

monitor = MonitorData()

@app.route('/')
def index():
    return render_template('energy_dashboard.html')

@app.route('/api/data')
def get_data():
    return jsonify(monitor.get_data())

if __name__ == '__main__':
    update_thread = threading.Thread(target=monitor.update, daemon=True)
    update_thread.start()
    
    print("="*60)
    print("Energy Monitor Web Server")
    print("="*60)
    print("Open http://127.0.0.1:5000 in your browser")
    print("Press Ctrl+C to stop")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
