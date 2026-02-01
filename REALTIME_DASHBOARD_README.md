# EnergyDebug 实时能耗看板

基于 `energydebug_backup.ipynb` 数据集实现的实时系统监控看板。

## 文件说明

- `energy_realtime_dashboard.ipynb` - 实时看板主文件（27个单元格）
- 不修改原有代码，独立运行

## 功能特性

### 1. 高耗能进程监控
- 实时显示系统中最耗能的 Top 5 进程
- 显示 CPU 使用率、内存占用、估算能耗（kJ）

### 2. 硬件温度检测
- **CPU 温度**：通过 WMI 或基于负载估算
- **GPU 温度**：通过 WMI VideoController（需驱动支持）
- **电池温度**：通过 WMI Battery 类
- **电池状态**：电量百分比、充电状态

### 3. 能耗趋势分析
- 基于历史数据的多维度能耗对比图
- 能耗时间线可视化
- 各镜像能效统计

### 4. 图像检测
- 异常能耗镜像检测
- 能效分类（高/中/低效）
- 检测报告自动生成

## 使用方法

1. 打开 `energy_realtime_dashboard.ipynb`
2. 按顺序运行单元格（Shift + Enter）
3. 查看实时看板输出和图表

### 关键单元格
- **单元格 8**: 运行一次实时监控演示
- **单元格 11**: 启动持续监控（可选，默认60秒）
- **单元格 13**: 导出 JSON 检测报告

## 依赖说明

仅使用已有依赖，无需额外安装：
- psutil 7.1.3+ （系统监控）
- pandas 2.3.3+ （数据处理）
- numpy 2.3.4+ （数值计算）
- matplotlib 3.10.7+ （可视化）

**注意**：WMI 模块用于增强温度检测，可选安装：
```bash
pip install wmi --no-cache-dir
```

## 空间优化设计

考虑到 C 盘剩余空间不足 5GB：
- 无大型 ML 库依赖
- 数据流式处理，内存友好
- 报告导出为 JSON，体积小巧
- 使用 `--no-cache-dir` 避免 pip 缓存

## 数据结构

复用原有数据集结构：
```
data/
  {workload}/
    energy/
      {image}@sha256.../
        run-{n}.tsv   # CSV格式，包含能耗数据
```

## 工作负载支持

默认加载 `redis-server`，可修改为：
- memcpy-benchmark
- memcpy-benchmark-12
- memcpy-benchmark-cached
- postgres-server
- tcp-benchmark-1/2

修改 `WORKLOAD` 变量即可切换。
