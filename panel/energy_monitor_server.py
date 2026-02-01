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
        nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage,
        nvmlDeviceGetMemoryInfo, nvmlDeviceGetFanSpeed,
        NVMLError
    )
    nvmlInit()
    NVML_AVAILABLE = True
    NVML_DEVICE_COUNT = nvmlDeviceGetCount()
    print(f"[INFO] NVML initialized: {NVML_DEVICE_COUNT} GPU(s) detected")
except Exception as e:
    print(f"[INFO] NVML not available: {e}")
    NVML_AVAILABLE = False
    NVML_DEVICE_COUNT = 0

app = Flask(__name__, template_folder='.', static_folder='.')
CORS(app)

class MonitorData:
    def __init__(self):
        self.processes = []
        self.cpu_info = {'temp': None, 'usage': 0, 'freq': 0, 'cores': 0}
        self.gpu_info = {'temp': None, 'util': None, 'power': None, 'name': None, 'mem_used': None, 'mem_total': None, 'fan': None}
        self.battery = None
        self.total_power = 0
        self.power_history = deque(maxlen=60)
        self.cpu_temp_history = deque(maxlen=60)
        self.gpu_temp_history = deque(maxlen=60)
        self.wmi = None
        
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi.WMI()
            except:
                pass
        
        self.lock = threading.Lock()
        self._cpu_init = False
        self.cpu_cores = psutil.cpu_count()
        self.cpu_logical = psutil.cpu_count(logical=True)
    
    def get_cpu_info(self):
        """获取完整的CPU信息"""
        info = {
            'usage': 0,
            'temp': None,
            'freq': 0,
            'cores': self.cpu_cores,
            'logical': self.cpu_logical,
            'per_cpu': []
        }
        
        # CPU使用率 - 需要正确的初始化
        if not self._cpu_init:
            psutil.cpu_percent(interval=0.1)
            self._cpu_init = True
            time.sleep(0.3)
        
        info['usage'] = psutil.cpu_percent(interval=0.1)
        info['per_cpu'] = psutil.cpu_percent(percpu=True)
        
        # CPU频率
        try:
            freq = psutil.cpu_freq()
            if freq:
                info['freq'] = round(freq.current, 0)
        except:
            pass
        
        # CPU温度 - 尝试多种方法
        temps = self.get_cpu_temp()
        if temps:
            info['temp'] = temps
        
        return info
    
    def get_cpu_temp(self):
        """获取CPU温度"""
        # 方法1: WMI
        if self.wmi:
            try:
                for tz in self.wmi.MSAcpi_ThermalZoneTemperature():
                    if hasattr(tz, 'CurrentTemperature'):
                        return round(tz.CurrentTemperature / 10.0 - 273.15, 1)
            except:
                pass
        
        # 方法2: psutil sensors_temperatures
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # 尝试常见的CPU温度键名
                for key in ['coretemp', 'k10temp', 'cpu-thermal', 'cpu_thermal']:
                    if key in temps:
                        for entry in temps[key]:
                            if entry.current:
                                return round(entry.current, 1)
        except:
            pass
        
        return None
    
    def get_gpu_info(self):
        """获取GPU完整信息"""
        info = {
            'temp': None, 
            'util': None, 
            'power': None, 
            'name': None,
            'mem_used': None,
            'mem_total': None,
            'mem_percent': None,
            'fan': None
        }
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            handle = nvmlDeviceGetHandleByIndex(0)
            
            # GPU名称
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else str(name)
            except:
                info['name'] = "NVIDIA GPU"
            
            # GPU温度
            try:
                info['temp'] = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
            except NVMLError as e:
                print(f"[GPU Temp Error] {e}")
            
            # GPU使用率
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                info['util'] = util.gpu
            except NVMLError as e:
                print(f"[GPU Util Error] {e}")
            
            # GPU功耗
            try:
                power_mw = nvmlDeviceGetPowerUsage(handle)
                info['power'] = round(power_mw / 1000.0, 1)
            except NVMLError as e:
                pass
            
            # GPU显存
            try:
                mem = nvmlDeviceGetMemoryInfo(handle)
                info['mem_used'] = round(mem.used / 1024**3, 1)  # GB
                info['mem_total'] = round(mem.total / 1024**3, 1)  # GB
                info['mem_percent'] = round((mem.used / mem.total) * 100, 1)
            except NVMLError as e:
                pass
            
            # GPU风扇转速
            try:
                info['fan'] = nvmlDeviceGetFanSpeed(handle)
            except:
                pass
                
        except Exception as e:
            print(f"[GPU Error] {e}")
        
        return info
    
    def get_battery_info(self):
        """获取详细的电池信息"""
        battery = psutil.sensors_battery()
        if not battery:
            return None
        
        info = {
            'percent': battery.percent,
            'plugged': battery.power_plugged,
            'secsleft': battery.secsleft,
            'time_left': "N/A",
            'status': "Unknown",
            'health': "Good"  # 模拟值，psutil不提供健康度
        }
        
        # 时间计算
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
        else:
            info['status'] = "Calculating"
        
        # 电池温度
        if self.wmi:
            try:
                for bat in self.wmi.Win32_Battery():
                    if hasattr(bat, 'Temperature') and bat.Temperature:
                        info['temp'] = float(bat.Temperature)
                        break
            except:
                pass
        
        return info
    
    def get_process_energy(self):
        """获取进程能耗信息 - 过滤System Idle Process"""
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status']):
            try:
                info = proc.info
                name = info['name'] or "Unknown"
                
                # 过滤系统空闲进程和无效进程
                if name in ['System Idle Process', 'Registry', 'System']:
                    continue
                
                cpu = info['cpu_percent'] or 0
                # 限制CPU使用率显示（多核系统可能超过100%）
                if cpu > 100:
                    cpu = min(cpu, 100)
                
                mem = info['memory_percent'] or 0
                status = info['status'] or "running"
                
                # 更精确的功耗估算
                base_power = 2.0  # 基础功耗
                cpu_power = cpu * 0.5  # CPU贡献
                mem_power = mem * 0.1  # 内存贡献
                power_w = base_power + cpu_power + mem_power
                total_power += power_w
                
                processes.append({
                    'pid': info['pid'],
                    'name': name[:30],
                    'cpu': round(cpu, 1),
                    'mem': round(mem, 1),
                    'power_w': round(power_w, 2),
                    'status': status
                })
            except:
                continue
        
        # 按功耗排序
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
        # 计算百分比
        for p in processes:
            p['percent'] = round((p['power_w'] / total_power * 100), 1) if total_power > 0 else 0
        
        return processes[:12], total_power
    
    def update(self):
        """后台更新循环"""
        while True:
            try:
                # 获取CPU信息
                cpu_info = self.get_cpu_info()
                mem_usage = psutil.virtual_memory().percent
                
                # 获取GPU信息
                gpu_info = self.get_gpu_info()
                
                # 获取进程和功耗
                processes, total_power = self.get_process_energy()
                
                # 获取电池
                battery = self.get_battery_info()
                
                # 更新历史数据
                with self.lock:
                    self.cpu_info = cpu_info
                    self.cpu_info['mem_usage'] = mem_usage
                    self.gpu_info = gpu_info
                    self.processes = processes
                    self.battery = battery
                    self.total_power = round(total_power, 1)
                    self.power_history.append(total_power)
                    if cpu_info['temp']:
                        self.cpu_temp_history.append(cpu_info['temp'])
                    if gpu_info['temp']:
                        self.gpu_temp_history.append(gpu_info['temp'])
                
                time.sleep(1)
                
            except Exception as e:
                print(f"[Update Error] {e}")
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
