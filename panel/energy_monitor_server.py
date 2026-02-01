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

try:
    from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex
    from pynvml import nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU
    nvmlInit()
    NVML_AVAILABLE = True
    NVML_DEVICE_COUNT = nvmlDeviceGetCount()
except:
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

# 全局数据缓存
class MonitorData:
    def __init__(self):
        self.processes = []
        self.temps = {'cpu': 0, 'gpu': None, 'battery': None}
        self.battery = None
        self.total_power = 0
        self.power_history = deque(maxlen=60)
        self.temp_history = deque(maxlen=60)
        self.wmi = None
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
        self.lock = threading.Lock()
    
    def get_cpu_temp(self):
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        return tz.CurrentTemperature / 10.0 - 273.15
            except:
                pass
        cpu_load = psutil.cpu_percent()
        return 40 + cpu_load * 0.5
    
    def get_gpu_temp(self):
        if NVML_AVAILABLE and NVML_DEVICE_COUNT > 0:
            try:
                handle = nvmlDeviceGetHandleByIndex(0)
                return nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except:
                pass
        return None
    
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
                processes, total_power = self.get_process_energy()
                temps = {
                    'cpu': round(self.get_cpu_temp(), 1),
                    'gpu': self.get_gpu_temp(),
                    'battery': self.get_battery_temp()
                }
                battery = self.get_battery_info()
                
                with self.lock:
                    self.processes = processes
                    self.temps = temps
                    self.battery = battery
                    self.total_power = round(total_power, 1)
                    self.power_history.append(total_power)
                    self.temp_history.append(temps['cpu'])
                
                time.sleep(1)
            except Exception as e:
                print(f"Update error: {e}")
                time.sleep(1)
    
    def get_data(self):
        with self.lock:
            return {
                'processes': self.processes,
                'temps': self.temps,
                'battery': self.battery,
                'total_power': self.total_power,
                'power_history': list(self.power_history),
                'cpu_usage': psutil.cpu_percent(),
                'mem_usage': psutil.virtual_memory().percent,
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
    # 启动后台更新线程
    update_thread = threading.Thread(target=monitor.update, daemon=True)
    update_thread.start()
    
    print("="*60)
    print("Energy Monitor Web Server")
    print("="*60)
    print("Open http://127.0.0.1:5000 in your browser")
    print("Press Ctrl+C to stop")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
