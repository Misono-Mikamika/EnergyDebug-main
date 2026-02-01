# Energy Monitor 更新说明

## 2024 更新内容

### 1. CPU 使用率修复
- 修复了 CPU 使用率始终为 0 的问题
- 添加了正确的初始化机制，首次调用后等待数据累积

### 2. GPU 支持增强 (需要 nvidia-ml-py)
安装命令：
```bash
pip install nvidia-ml-py
```

新增 GPU 监测内容：
- **GPU 温度** (°C)
- **GPU 使用率** (%)
- **GPU 功耗** (W)
- **GPU 名称** 显示

### 3. 界面更新

#### Web 版本 (energy_monitor_server.py + energy_dashboard.html)
新增 GPU 信息卡片：
```
┌─────────────────────────────┐
│ 🎮 GPU Status               │
│ NVIDIA GeForce RTX 3060     │
│ ┌──────────┬──────────┐     │
│ │ Temp:    │ Util:    │     │
│ │ 62°C     │ 45%      │     │
│ ├──────────┼──────────┤     │
│ │ Power:   │ Status:  │     │
│ │ 85W      │ Active   │     │
│ └──────────┴──────────┘     │
└─────────────────────────────┘
```

新增 GPU 使用率趋势图 (60秒历史)

#### 命令行版本 (energy_monitor.py)
新增 GPU 信息行：
```
[GPU: NVIDIA GeForce RTX 3060                 ]
  Utilization:  45.0%    Power:   85.0W    Temp:   62.0°C
```

新增 GPU 使用率趋势图

## 文件清单

| 文件 | 说明 |
|------|------|
| energy_monitor_server.py | Flask Web 服务器 (修复 CPU + 新增 GPU) |
| energy_dashboard.html | Web 前端 (新增 GPU 卡片和图表) |
| energy_monitor.py | 命令行版本 (修复 CPU + 新增 GPU) |
| start_monitor.bat | Windows 启动脚本 |
| requirements.txt | 依赖列表 |

## 使用方法

### Web 版本
```bash
cd panel
pip install -r requirements.txt
python energy_monitor_server.py
# 浏览器访问 http://127.0.0.1:5000
```

### 命令行版本
```bash
cd panel
python energy_monitor.py
```

## 注意事项

1. **NVIDIA GPU 支持**：需要安装 NVIDIA 显卡驱动和 nvidia-ml-py
2. **CPU 使用率**：启动后需等待 1-2 秒才能获取准确数据
3. **权限**：某些系统信息可能需要管理员权限
