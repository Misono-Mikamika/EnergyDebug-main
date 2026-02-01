# Energy Monitor Web Dashboard

轻量级实时能耗监控 Web 看板，提供美观的网页界面展示系统功耗、进程能耗、温度监测和趋势图表。

## 功能特性

- **实时数据更新**: 每秒自动刷新
- **硬件温度监测**: CPU、GPU、电池温度
- **进程能耗排行**: Top 10 高耗能进程及占比
- **系统功耗统计**: 总功耗、CPU/内存使用率
- **电池状态**: 剩余电量、充放电状态、预计使用时间
- **趋势图表**: 60 秒功耗和温度历史曲线
- **响应式设计**: 适配不同屏幕尺寸

## 文件说明

| 文件 | 说明 |
|------|------|
| `energy_monitor_server.py` | Flask 后端服务 (5.9 KB) |
| `energy_dashboard.html` | 前端页面 (17.6 KB) |
| `requirements.txt` | Python 依赖列表 |
| `start_monitor.bat` | Windows 启动脚本 |
| `start_monitor.sh` | Linux/Mac 启动脚本 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

或一键启动（自动安装依赖）：

**Windows:**
```bash
start_monitor.bat
```

**Linux/Mac:**
```bash
chmod +x start_monitor.sh
./start_monitor.sh
```

### 2. 启动服务

```bash
python energy_monitor_server.py
```

### 3. 访问看板

打开浏览器访问: http://127.0.0.1:5000

## 界面预览

```
┌─────────────────────────────────────────────────────────────┐
│                    ⚡ Energy Monitor                         │
│                         19:50:04                            │
├──────────────────┬──────────────────┬───────────────────────┤
│  🌡️ Temperature  │   ⚡ System Power │     🔋 Battery        │
│  CPU: 45°C       │   1497.2 Watts   │     100% 🔌 Charging  │
│  GPU: 62°C       │   CPU: 15%       │     Time: N/A         │
│  Battery: 35°C   │   Mem: 62%       │                       │
├──────────────────┴──────────────────┴───────────────────────┤
│  🔥 Top Energy Consuming Processes                          │
│  Rank │ Process      │ Power  │ Share │ CPU% │ Memory%      │
│  1    │ python.exe   │ 12.5W  │ 35.2% │ 15%  │ 45%          │
│  2    │ chrome.exe   │ 8.3W   │ 23.4% │ 8%   │ 12%          │
├──────────────────────────┬──────────────────────────────────┤
│  📊 Power Trend (60s)    │  🌡️ CPU Temp Trend (60s)        │
│  [Chart]                 │  [Chart]                         │
└──────────────────────────┴──────────────────────────────────┘
```

## API 接口

- `GET /` - 返回前端页面
- `GET /api/data` - 返回 JSON 格式的实时数据

数据格式：
```json
{
  "processes": [...],
  "temps": {"cpu": 45.2, "gpu": 62, "battery": 35},
  "battery": {"percent": 100, "plugged": true, "time_left": "N/A"},
  "total_power": 1497.2,
  "power_history": [...],
  "cpu_usage": 15.3,
  "mem_usage": 62.5,
  "timestamp": "19:50:04"
}
```

## 可选依赖

- `nvidia-ml-py`: NVIDIA GPU 温度检测
- `WMI`: Windows 电池温度检测

## 技术栈

- **后端**: Python Flask + psutil
- **前端**: 原生 HTML/CSS/JavaScript + Chart.js
- **通信**: HTTP REST API + 轮询 (1秒间隔)

## 注意事项

1. 需要管理员/root权限获取某些进程信息
2. GPU 温度需要 NVIDIA 显卡和相应驱动
3. 电池信息需要笔记本或带电池的设备
