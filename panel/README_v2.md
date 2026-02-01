# Energy Monitor v2.0 更新说明

## 主要改进

### 1. CPU 检测完善
- ✅ 修复 CPU 使用率始终为 0 的问题
- ✅ 添加 CPU 温度检测（WMI + sensors_temperatures）
- ✅ 添加 CPU 频率显示
- ✅ 添加 CPU 核心/线程数显示
- ✅ 添加 CPU 温度历史趋势图

### 2. GPU 检测完善
- ✅ 修复 GPU 温度和利用率显示为 N/A 的问题
- ✅ 添加 GPU 显存使用显示 (Used/Total GB)
- ✅ 添加 GPU 功耗显示
- ✅ 添加 GPU 温度历史趋势
- ✅ 优化 NVML 错误处理

### 3. 进程信息完善
- ✅ 过滤 System Idle Process（不再显示 1000%+ CPU）
- ✅ 限制 CPU 使用率最大显示 100%
- ✅ 添加进程状态显示（running/sleeping）
- ✅ 显示进程 PID（悬停提示）
- ✅ 优化功耗估算算法

### 4. 电池信息完善
- ✅ 添加电池状态显示（Charging/Discharging）
- ✅ 完善剩余时间计算
- ✅ 添加电源来源显示
- ✅ 优化充电完成状态显示

### 5. 界面优化
- ✅ 全新的暗色主题设计
- ✅ CPU 和 GPU 独立卡片
- ✅ 温度颜色指示（绿色/黄色/红色）
- ✅ 进度条可视化
- ✅ 更清晰的布局

## 文件更新

| 文件 | 更新内容 |
|------|----------|
| energy_monitor_server.py | 完全重写，修复 CPU/GPU 检测 |
| energy_monitor.py | 命令行版本同步更新 |
| energy_dashboard.html | 全新界面设计 |
| start_monitor.bat | 添加 pywin32 依赖 |

## 运行方法

### Web 版本（推荐）
```bash
cd panel
pip install flask flask-cors psutil wmi nvidia-ml-py pywin32
python energy_monitor_server.py
# 浏览器访问 http://127.0.0.1:5000
```

或双击 `start_monitor.bat`

### 命令行版本
```bash
cd panel
python energy_monitor.py
```

## 界面预览

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    ⚡ ENERGY MONITOR - Real-time Dashboard                   ║
║                              2026-02-01 23:49:26                             ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ [CPU] 6 Cores / 12 Threads                                                   ║
║   Temperature:  42.2°C  Usage:  15.3%  Frequency: 2500 MHz                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ [GPU] NVIDIA GeForce RTX 2050                                                ║
║   Temp:  45°C    Util:   23%    Power:   35W    VRAM: 3.2/4GB                ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ [SYSTEM]  Total Power:  1250.5W  Memory:  62.5% (16GB used)                  ║
║ [BATTERY] 100.0%  ⚡ Charging    Fully Charged                               ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ Top Energy Consuming Processes:                                              ║
║ Rank │ Process                    │ Power   │ Share │  CPU  │ Memory        ║
║──────┼────────────────────────────┼─────────┼───────┼───────┼───────────────║
║    1 │ chrome.exe                 │  45.20W │ 35.2%│  15.0%│  12.5% ●      ║
║    2 │ python.exe                 │  23.50W │ 18.3%│   8.5%│   3.2% ●      ║
╚══════════════════════════════════════════════════════════════════════════════╝
```

## 依赖安装

```bash
pip install flask flask-cors psutil wmi nvidia-ml-py pywin32
```

## 注意事项

1. **首次运行**：CPU 使用率需要 1-2 秒初始化
2. **GPU 检测**：需要 NVIDIA 显卡和驱动，安装 `nvidia-ml-py`
3. **权限**：建议以管理员身份运行以获得完整信息
4. **防火墙**：首次运行可能需要允许网络访问
