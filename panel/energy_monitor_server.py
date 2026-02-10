#!/usr/bin/env python3
"""
轻量级实时能耗监控 Web 服务
修复版：跨平台兼容、容错增强、状态保持
"""

import os
import sys
import time
import threading
import platform
from datetime import datetime
from collections import deque
from flask import Flask, render_template, jsonify
from flask_cors import CORS

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
        print("[INFO] WMI module loaded")
    except ImportError:
        print("[WARNING] WMI not available, CPU temp will use estimation")

# NVML GPU 支持
NVML_AVAILABLE = False
NVML_DEVICE_COUNT = 0
nvml_handle = None

def init_nvml():
    """初始化 NVML，支持重新初始化"""
    global NVML_AVAILABLE, NVML_DEVICE_COUNT, nvml_handle
    try:
        from pynvml import nvmlInit, nvmlDeviceGetCount, nvmlDeviceGetHandleByIndex
        nvmlInit()
        NVML_DEVICE_COUNT = nvmlDeviceGetCount()
        if NVML_DEVICE_COUNT > 0:
            nvml_handle = nvmlDeviceGetHandleByIndex(0)
        NVML_AVAILABLE = True
        print(f"[INFO] NVML initialized: {NVML_DEVICE_COUNT} GPU(s)")
        return True
    except Exception as e:
        print(f"[WARNING] NVML init failed: {e}")
        NVML_AVAILABLE = False
        return False

# 首次初始化
init_nvml()

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
        
        # WMI 实例（仅 Windows）
        self.wmi = None
        if WMI_AVAILABLE:
            try:
                self.wmi = wmi_module.WMI()
                print("[INFO] WMI initialized")
            except Exception as e:
                print(f"[WARNING] WMI init failed: {e}")
        
        self.lock = threading.Lock()
        self._cpu_init = False
        self.cpu_cores = psutil.cpu_count()
        self.cpu_logical = psutil.cpu_count(logical=True)
        
        # 状态保持：用于容错
        self._last_valid_cpu_temp = None
        self._last_valid_gpu_temp = None
        self._last_valid_gpu_info = {}
    
    def get_cpu_temp(self):
        """
        获取 CPU 温度 - 跨平台兼容
        Windows: WMI 多种类尝试 -> 估算
        Linux: psutil sensors -> 估算
        """
        temp = None
        
        # Windows 平台：尝试多种 WMI 类
        if IS_WINDOWS and self.wmi:
            wmi_classes = [
                'MSAcpi_ThermalZoneTemperature',
                'Win32_TemperatureProbe',
                'CIM_TemperatureSensor',
                'Win32_PerfFormattedData_Counters_ThermalZoneInformation'
            ]
            
            for cls_name in wmi_classes:
                try:
                    sensors = getattr(self.wmi, cls_name)()
                    for sensor in sensors:
                        current = getattr(sensor, 'CurrentTemperature', None) or \
                                 getattr(sensor, 'Temperature', None)
                        if current:
                            # WMI 温度通常是开尔文 * 10
                            if current > 2730:  # 可能是开尔文 * 10
                                celsius = current / 10.0 - 273.15
                            elif current > 273:  # 可能是开尔文
                                celsius = current - 273.15
                            else:
                                celsius = current  # 已经是摄氏度
                            
                            if 0 < celsius < 150:
                                temp = round(celsius, 1)
                                self._last_valid_cpu_temp = temp
                                return temp
                except Exception:
                    continue
        
        # Linux 平台：使用 lm-sensors
        elif IS_LINUX:
            try:
                temps = psutil.sensors_temperatures()
                if temps:
                    for key in ['coretemp', 'k10temp', 'cpu_thermal', 'cpu-thermal', 'acpitz']:
                        if key in temps and temps[key]:
                            for entry in temps[key]:
                                if entry.current and 0 < entry.current < 150:
                                    temp = round(entry.current, 1)
                                    self._last_valid_cpu_temp = temp
                                    return temp
            except Exception as e:
                print(f"[DEBUG] Linux sensors error: {e}")
        
        # 通用估算方法
        try:
            cpu_load = psutil.cpu_percent(interval=0.1)
            # 基础 35°C + 每 1% 负载增加 0.5°C
            estimated = 35 + (cpu_load * 0.5)
            temp = round(estimated, 1)
        except:
            pass
        
        # 状态保持：如果获取失败，使用上次有效值
        if temp is None and self._last_valid_cpu_temp:
            return self._last_valid_cpu_temp
        
        if temp:
            self._last_valid_cpu_temp = temp
        
        return temp
    
    def get_gpu_info(self):
        """
        获取 GPU 信息 - 带容错和状态保持
        """
        info = {
            'temp': None, 'util': None, 'power': None, 'name': None,
            'mem_used': None, 'mem_total': None, 'mem_percent': None
        }
        
        if not NVML_AVAILABLE or NVML_DEVICE_COUNT == 0:
            return info
        
        try:
            from pynvml import (
                nvmlDeviceGetName, nvmlDeviceGetTemperature, NVML_TEMPERATURE_GPU,
                nvmlDeviceGetUtilizationRates, nvmlDeviceGetPowerUsage,
                nvmlDeviceGetMemoryInfo
            )
            
            handle = nvml_handle
            
            # GPU 名称
            try:
                name = nvmlDeviceGetName(handle)
                info['name'] = name.decode('utf-8') if isinstance(name, bytes) else str(name)
            except:
                info['name'] = self._last_valid_gpu_info.get('name', "NVIDIA GPU")
            
            # GPU 温度 - 带有效性校验
            try:
                temp = nvmlDeviceGetTemperature(handle, NVML_TEMPERATURE_GPU)
                if 0 < temp < 120:  # 合理温度范围
                    info['temp'] = temp
                    self._last_valid_gpu_temp = temp
                elif self._last_valid_gpu_temp:
                    info['temp'] = self._last_valid_gpu_temp
            except:
                if self._last_valid_gpu_temp:
                    info['temp'] = self._last_valid_gpu_temp
            
            # GPU 使用率
            try:
                util = nvmlDeviceGetUtilizationRates(handle)
                if 0 <= util.gpu <= 100:
                    info['util'] = util.gpu
            except:
                pass
            
            # GPU 功耗
            try:
                power_mw = nvmlDeviceGetPowerUsage(handle)
                if power_mw > 0:
                    info['power'] = round(power_mw / 1000.0, 1)
            except:
                pass
            
            # GPU 显存
            try:
                mem = nvmlDeviceGetMemoryInfo(handle)
                if mem.total > 0:
                    info['mem_used'] = round(mem.used / 1024**3, 1)
                    info['mem_total'] = round(mem.total / 1024**3, 1)
                    info['mem_percent'] = round((mem.used / mem.total) * 100, 1)
            except:
                pass
            
            # 保存有效状态
            self._last_valid_gpu_info = {k: v for k, v in info.items() if v is not None}
            
        except Exception as e:
            print(f"[DEBUG] GPU info error: {e}")
            # 使用上次有效状态
            info.update(self._last_valid_gpu_info)
        
        return info
    
    def get_cpu_info(self):
        """获取 CPU 完整信息"""
        info = {
            'usage': 0, 'temp': None, 'freq': 0,
            'cores': self.cpu_cores, 'logical': self.cpu_logical,
            'power': 0, 'mem_usage': 0
        }
        
        # 初始化 CPU 使用率
        if not self._cpu_init:
            psutil.cpu_percent(interval=None)
            self._cpu_init = True
            time.sleep(0.5)
        
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
        
        # 估算 CPU 功耗
        info['power'] = round(15.0 + (info['usage'] * 0.5), 1)
        
        # 获取系统内存使用率
        try:
            mem = psutil.virtual_memory()
            info['mem_usage'] = mem.percent
        except:
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
        """
        获取进程能耗 - 包含 System Idle Process
        不过滤 System Idle Process
        """
        processes = []
        total_power = 0
        
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                info = proc.info
                name = info['name'] or "Unknown"
                
                # 只过滤 Registry，保留 System Idle Process 和 System
                if name == 'Registry':
                    continue
                
                cpu = info['cpu_percent'] or 0
                # System Idle Process 显示实际值（可能超过100%）
                # 其他进程限制在100%
                if name != 'System Idle Process':
                    cpu = min(cpu, 100)
                
                mem = info['memory_percent'] or 0
                
                # System Idle Process 特殊功耗计算
                if name == 'System Idle Process':
                    power_w = 0.1  # 空闲进程低功耗
                else:
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
        
        # 按功耗排序
        processes.sort(key=lambda x: x['power_w'], reverse=True)
        
        # 计算百分比
        for p in processes:
            p['percent'] = round((p['power_w'] / total_power * 100), 1) if total_power > 0 else 0
        
        return processes[:12], round(total_power, 1)
    
    def update(self):
        """后台更新循环 - 带错误恢复"""
        print("[INFO] Monitor update thread started")
        
        while True:
            try:
                # 获取 CPU 信息
                cpu_info = self.get_cpu_info()
                
                # 获取 GPU 信息
                gpu_info = self.get_gpu_info()
                
                # 获取进程和功耗
                processes, total_power = self.get_process_energy()
                
                # 获取电池
                battery = self.get_battery_info()
                
                # 更新历史数据
                with self.lock:
                    self.cpu_info = cpu_info
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
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'platform': platform.system()
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
    print(f"Platform: {platform.system()}")
    print("="*60)
    print("Open http://127.0.0.1:5000 in your browser")
    print("Press Ctrl+C to stop")
    print("="*60)
    
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
