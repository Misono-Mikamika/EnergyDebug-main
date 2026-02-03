# Energy Monitor 修复说明

## 修复的问题

### 问题 1：psutil sensors_temperatures 跨平台兼容性
**问题描述**：
- `psutil.sensors_temperatures()` 仅在 Linux/macOS 上可用
- Windows 平台调用会直接报错
- 代码没有平台判断

**修复方案**：
```python
# 添加平台检测
IS_WINDOWS = platform.system() == "Windows"
IS_LINUX = platform.system() == "Linux"

# Windows 只使用 WMI，不使用 sensors_temperatures
if IS_WINDOWS and self.wmi:
    # 尝试多种 WMI 类
    for cls_name in ['MSAcpi_ThermalZoneTemperature', ...]
    
# Linux 才使用 sensors_temperatures
elif IS_LINUX:
    temps = psutil.sensors_temperatures()
```

### 问题 2：WMI 采集容错性不足
**问题描述**：
- 仅依赖 `MSAcpi_ThermalZoneTemperature` 类
- 该类在很多设备上不存在
- 没有备用方案

**修复方案**：
```python
# 尝试多种 WMI 类
wmi_classes = [
    'MSAcpi_ThermalZoneTemperature',
    'Win32_TemperatureProbe',
    'CIM_TemperatureSensor',
    'Win32_PerfFormattedData_Counters_ThermalZoneInformation'
]

for cls_name in wmi_classes:
    try:
        sensors = getattr(self.wmi, cls_name)()
        # 处理温度值...
    except:
        continue  # 失败则尝试下一个类
```

### 问题 3：GPU 采集缺乏容错和状态保持
**问题描述**：
- NVML 调用失败直接返回 None
- 没有重新初始化逻辑
- 温度从 57°C 跌到 0°C
- 没有数据范围校验

**修复方案**：
```python
class MonitorData:
    def __init__(self):
        # 状态保持
        self._last_valid_gpu_temp = None
        self._last_gpu_info = {}
    
    def get_gpu_info(self):
        try:
            # 温度有效性校验
            if 0 < temp < 120:
                info['temp'] = temp
                self._last_valid_gpu_temp = temp
            elif self._last_valid_gpu_temp:
                info['temp'] = self._last_valid_gpu_temp
                
        except Exception as e:
            # 失败时使用上次有效状态
            info.update(self._last_gpu_info)
```

### 问题 4：进程过滤矛盾
**问题描述**：
- 用户要求显示 System Idle Process
- 代码却过滤掉了该进程

**修复方案**：
```python
# 修复前（过滤掉）
if name in ['System Idle Process', 'Registry', 'System']:
    continue

# 修复后（保留）
if name == 'Registry':  # 只过滤 Registry
    continue

# System Idle Process 特殊处理
if name == 'System Idle Process':
    cpu_display = cpu  # 显示实际值（可能>100%）
    power_w = 0.1      # 低功耗
else:
    cpu_display = min(cpu, 100)  # 其他进程限制100%
    power_w = 2.0 + cpu * 0.5 + mem * 0.1
```

## 新增功能

### CPU 状态卡增强
- Power (Est.)：估算功耗 = 15W 基础 + 0.5W × 使用率%
- Memory：系统内存占用百分比

### GPU 状态卡增强
- Power Draw：从 NVML 读取的实际功耗
- VRAM：显存使用/总量（GB）

### System Idle Process
- 现在显示在进程列表中
- 显示实际 CPU 占用率（可能超过 100%）
- 低功耗估算（0.1W）

## 文件修改

| 文件 | 修改内容 |
|------|----------|
| `energy_monitor_server.py` | 跨平台兼容、WMI 多类尝试、GPU 状态保持、System Idle Process 保留 |
| `energy_monitor.py` | 同步更新命令行版本 |

## 运行测试

```bash
cd panel
python energy_monitor_server.py
```

访问 http://127.0.0.1:5000

## 预期输出

```
Platform: Windows
[INFO] WMI module loaded
[INFO] NVML initialized: 1 GPU(s)
============================================================
Energy Monitor Web Server
============================================================
```

界面应正确显示：
- CPU 温度（WMI 或估算）
- GPU 温度（NVML）
- System Idle Process 在进程列表中
- CPU/GPU 功率和内存占用
