#!/usr/bin/env python3
"""
轻量级实时能耗监控 Web 服务
提供 REST API 和 Web 前端
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify
from flask_cors import CORS

import psutil

try:
    import wmi
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

# NVML 初始化
try:
    from pynvml import (
        nvmlInit, nvmlShutdown, nvmlDeviceGetCount, 
        nvmlDeviceGetHandleByIndex, nvmlDeviceGetName,
        nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage
    )
    nvmlInit()
    NVML_AVAILABLE = True
    NVML_DEVICE_COUNT = nvmlDeviceGetCount()
    print(f"NVML initialized: {NVML_DEVICE_COUNT} GPU(s) detected")
except Exception as e:
    print(f"NVML not available: {e}")
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

class MonitorData:
    def __init__(self):
        self.processes = []
        self.temps = {'cpu': 0, 'gpu': None, 'battery': None}
        self.gpu_info = {'temp': None, 'util': None, 'power': None, 'name': None}
        self.battery = None
        self.total_power = 0
        self.power_history = deque(maxlen=60)
        self.temp_history = deque(maxlen=60)
        self.gpu_util_history = deque(maxlen=60)
        self.cpu_usage = 0
        self.mem_usage = 0
        self.wmi = None
        
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
        
        self.lock = threading.Lock()
        self._cpu_percent_init = False
    
    def get_cpu_temp(self):
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        return tz.CurrentTemperature / 10.0 - 273.15
            except:
                pass
        return 40 + self.cpu_usage * 0.5
    
    def get_gpu_info(self):
        info = {'temp': None, 'util': None, 'power': None, 'name': None}
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else name
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
                power_mw = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(power_mw / 1000.0, 1)
            except:
                pass
                
        except Exception as e:
            print(f"GPU info error: {e}")
        
        return info
    
    def get_battery_temp(self):
        if self.wmi:
            try:
                for bat in self.wmi.Win32_Battery():
                    if hasattr(bat, 'Temperature') and bat.Temperature:
                        return float(bat.Temperature)
            except:
                pass
        return None
    
    def get_battery_info(self):
        battery = psutil.sensors_battery()
        if battery:
            time_left = "N/A"
            if not battery.power_plugged and battery.secsleft > 0:
                hours = battery.secsleft // 3600
                mins = (battery.secsleft % 3600) // 60
                time_left = f"{hours}h {mins}m"
            return {
                'percent': battery.percent,
                'plugged': battery.power_plugged,
                'time_left': time_left
            }
        return None
    
    def get_process_energy(self):
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                cpu = info['cpu_percent'] or 0
                mem = info['memory_percent'] or 0
                power_w = 5.0 + (cpu * 0.3) + (mem * 0.05)
                total_power += power_w
                
                processes.append({
                    'pid': info['pid'],
                    'name': info['name'][:30],
                    'cpu': round(cpu, 1),
                    'mem': round(mem, 1),
                    'power_w': round(power_w, 2),
                    'power_mw': round(power_w * 1000, 0)
                })
            except:
                continue
        
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
        for p in processes:
            p['percent'] = round((p['power_w'] / total_power * 100), 1) if total_power > 0 else 0
        
        return processes[:10], total_power
    
    def update(self):
        while True:
            try:
                if not self._cpu_percent_init:
                    psutil.cpu_percent(interval=None)
                    self._cpu_percent_init = True
                    time.sleep(0.5)
                
                self.cpu_usage = psutil.cpu_percent(interval=None)
                self.mem_usage = psutil.virtual_memory().percent
                
                processes, total_power = self.get_process_energy()
                cpu_temp = self.get_cpu_temp()
                gpu_info = self.get_gpu_info()
                battery = self.get_battery_info()
                battery_temp = self.get_battery_temp()
                
                temps = {
                    'cpu': round(cpu_temp, 1),
                    'gpu': gpu_info['temp'],
                    'battery': battery_temp
                }
                
                with self.lock:
                    self.processes = processes
                    self.temps = temps
                    self.gpu_info = gpu_info
                    self.battery = battery
                    self.total_power = round(total_power, 1)
                    self.power_history.append(total_power)
                    self.temp_history.append(cpu_temp)
                    if gpu_info['util'] is not None:
                        self.gpu_util_history.append(gpu_info['util'])
                
                time.sleep(1)
                
            except Exception as e:
                print(f"Update error: {e}")
                time.sleep(1)
    
    def get_data(self):
        with self.lock:
            return {
                'processes': list(self.processes),
                'temps': dict(self.temps),
                'gpu_info': dict(self.gpu_info),
                'battery': self.battery,
                'total_power': self.total_power,
                'power_history': list(self.power_history),
                'gpu_util_history': list(self.gpu_util_history),
                'cpu_usage': self.cpu_usage,
                'mem_usage': self.mem_usage,
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
