# 内存访问模式与能源深度分析模块

## 概述

本模块为 `energydebug.ipynb` 添加了全面的内存访问模式与能源消耗分析功能，专门针对导师要求的以下分析场景设计：

1. **GPU与CPU内存访问差异**
2. **缓存友好 vs 缓存不友好的内存访问**
3. **统一内存 vs 分离内存**
4. **数据驻留策略**
5. **数据重用与时间局部性**
6. **堆分配 vs 栈分配**
7. **内存池 vs 每次分配**

同时提供实时监控系统，包括电池消耗计算、温度监控、进程级能耗追踪和可视化看板。

---

## 特性

### 🔬 内存访问模式分析

#### 1. GPU与CPU内存访问差异分析
```python
result = analyzer.analyze_gpu_cpu_memory_access(
    data_size_bytes=100*1024*1024,  # 100MB
    access_pattern='sequential',
    use_unified_memory=False
)
```
- 对比CPU和GPU内存访问的能源消耗
- 计算PCIe传输开销
- 评估统一内存的效益

#### 2. 缓存友好性分析
```python
df = analyzer.analyze_cache_friendliness(
    array_size=1000000,
    test_patterns=['sequential', 'blocked', 'strided', 'random']
)
```
- 分析四种典型访问模式
- 计算缓存命中率和未命中率
- 量化缓存未命中的能源惩罚

#### 3. 统一内存 vs 分离内存
```python
result = analyzer.analyze_unified_vs_separated_memory(
    data_size_bytes=50*1024*1024,
    access_ratio_cpu=0.3,
    migration_frequency=100
)
```
- 对比两种内存架构的能源效率
- 计算页错误和PCIe传输开销
- 提供使用建议

#### 4. 数据驻留策略分析
```python
result = analyzer.analyze_data_residency_strategy(
    data_size_bytes=100*1024*1024,
    cpu_access_frequency=1000,
    gpu_access_frequency=5000,
    strategy='prefetch'  # 'on_demand', 'prefetch', 'pinned', 'duplicate'
)
```
支持策略：
- **按需迁移** (`on_demand`): 适合平衡的CPU/GPU访问
- **预取到GPU** (`prefetch`): 适合GPU主导的工作负载
- **页锁定内存** (`pinned`): 适合频繁同步
- **双份存储** (`duplicate`): 适合高并发访问

#### 5. 时间局部性分析
```python
result = analyzer.analyze_temporal_locality(
    access_sequence=[0, 1, 2, 3, ...],  # 内存地址访问序列
    cache_size=32768
)
```
- 计算重用距离分布
- 评估时间局部性评分
- 提供优化建议

#### 6. 堆分配 vs 栈分配
```python
result = analyzer.analyze_heap_vs_stack(
    allocation_size=1024,
    allocation_count=10000,
    lifetime_seconds=0.001
)
```
- 对比malloc/free与栈分配的能源开销
- 考虑内存碎片影响
- 提供场景建议

#### 7. 内存池 vs 每次分配
```python
result = analyzer.analyze_memory_pool_vs_per_allocation(
    object_size=256,
    total_objects=100000,
    peak_concurrent_objects=5000,
    allocation_pattern='burst'  # 'uniform', 'burst', 'gradual'
)
```
- 对比内存池与动态分配的能源效率
- 计算盈亏平衡点
- 评估内存-能源权衡

---

### 📊 实时监控与看板

#### 启动实时监控
```python
# 创建监控器
monitor = create_monitor(analyzer)

# 开始监控
monitor.start_monitoring()

# 创建可视化看板
dashboard = create_dashboard(monitor)
display(dashboard.create_dashboard())
dashboard.start_auto_update(interval=2.0)
```

#### 获取电池消耗报告
```python
report = monitor.get_battery_consumption_report()

print(f"初始电量: {report['initial_percent']:.1f}%")
print(f"消耗电量: {report['consumed_percent']:.2f}%")
print(f"估算能耗: {report['estimated_energy_joules']:.2f} J")
print(f"平均功率: {report['average_power_watts']:.2f} W")
```

#### 监控指标
- **电池状态**: 电量百分比、充电状态、预估剩余时间
- **系统温度**: CPU温度、GPU温度、电池温度
- **进程能耗**: Top 20进程的能耗排行
- **实时功率**: 动态计算当前功率消耗

---

## 能源模型说明

### 基础能源参数

```python
ENERGY_PARAMS = {
    'P_idle_cpu': 10.0,           # CPU空闲功率 (W)
    'P_active_cpu': 65.0,         # CPU满载功率 (W)
    'P_idle_gpu': 5.0,            # GPU空闲功率 (W)
    'P_active_gpu': 150.0,        # GPU满载功率 (W)
    'E_per_access_cpu': 2.5e-9,   # CPU内存访问能耗 (2.5 nJ)
    'E_per_access_gpu': 1.0e-9,   # GPU内存访问能耗 (1 nJ)
    'E_cache_hit': 0.5e-9,        # L1缓存命中能耗 (0.5 nJ)
    'E_cache_miss_l3': 50e-9,     # L3缓存未命中能耗 (50 nJ)
    'E_page_fault': 10e-6,        # 页错误处理能耗 (10 µJ)
    'E_data_migration': 1e-6,     # 数据迁移能耗 (1 µJ/byte)
    'E_pci_transfer': 0.5e-6,     # PCIe传输能耗 (0.5 µJ/byte)
}
```

### 能耗计算公式

总能源 = (基础能耗 + 内存访问能耗 × 访问模式因子 + 缓存未命中惩罚 + 页错误能耗 + 数据迁移能耗) × 分配策略开销

---

## 磁盘空间优化

考虑到C盘<10G、D盘<70G的限制，模块采用了以下优化策略：

1. **流式数据处理**: 使用 `deque` 限制内存缓存大小
2. **压缩存储**: 结果使用gzip压缩保存
3. **自动清理**: 临时文件自动管理
4. **内存限制**: 可配置最大内存使用量（默认500MB）

```python
# 创建分析器时指定资源限制
analyzer = MemoryEnergyAnalyzer(
    max_memory_mb=500,      # 内存限制
    disk_limit_gb=5.0,       # 磁盘限制
    data_dir="./cache"       # 缓存目录（建议放在D盘）
)
```

---

## 使用示例

### 快速开始

```python
# 1. 导入模块
from memory_energy_analyzer import *

# 2. 创建分析器
analyzer = create_analyzer(data_dir="D:/analysis_cache")

# 3. 运行全面分析
results = run_comprehensive_memory_analysis(analyzer)

# 4. 可视化结果
visualize_memory_analysis_results(results)
```

### 实时监控示例

```python
# 启动监控
monitor = create_monitor(analyzer)
monitor.start_monitoring()

# 创建看板
dashboard = create_dashboard(monitor)
display(dashboard.create_dashboard())
dashboard.start_auto_update(interval=2.0)

# ... 运行您的任务 ...

# 停止并查看报告
monitor.stop_monitoring()
report = monitor.get_battery_consumption_report()
print(f"本次任务消耗电池: {report['consumed_percent']:.2f}%")
```

---

## 系统要求

### 必需依赖
- Python >= 3.8
- psutil (系统监控)
- numpy, pandas (数据处理)
- matplotlib, seaborn (可视化)
- ipywidgets (交互式看板)

### 可选依赖
- pynvml (NVIDIA GPU监控)
- pyopencl (跨平台GPU检测)
- wmi (Windows系统温度)

安装所有依赖：
```bash
pip install psutil numpy pandas matplotlib seaborn ipywidgets
pip install pynvml pyopencl wmi  # 可选
```

---

## 输出示例

### 全面分析输出
```
======================================================================
开始全面内存访问模式能源分析
======================================================================

[1/7] 分析GPU与CPU内存访问差异...
  CPU能耗: 0.005000 J
  GPU能耗: 0.002500 J

[2/7] 分析缓存友好性...
  pattern  cache_friendly  energy_joules
0  sequential          True       0.001200
1     blocked          True       0.001350
2     strided         False       0.008500
3      random         False       0.015000

[3/7] 对比统一内存与分离内存...
  统一内存能耗: 0.001500 J
  分离内存能耗: 0.001200 J
  建议: 分离内存更节能，且编程更简单

...
```

### 实时监控输出
```
监控开始 - 初始电量: 85.0%

============================================================
监控汇总
============================================================
电池消耗: 3.50%
估算能耗: 1.7500 Wh (6300.00 J)
累计监测能耗: 0.1250 J
最高CPU温度: 72.5°C
```

---

## 注意事项

1. **GPU监控**: 需要NVIDIA显卡和pynvml库
2. **电池监控**: 笔记本使用，台式机将显示"未检测到电池"
3. **温度读取**: 部分系统可能需要管理员权限
4. **能耗估算**: 基于理论模型，实际值可能有偏差
5. **磁盘空间**: 建议定期清理 `./analysis_cache` 目录

---

## 扩展开发

### 添加新的分析场景

```python
class MemoryEnergyAnalyzer:
    def analyze_new_scenario(self, ...):
        # 计算能源消耗
        energy = self._calculate_energy(...)
        
        # 记录结果
        pattern = MemoryAccessPattern(...)
        with self._lock:
            self.patterns.append(pattern)
        
        return result
```

### 自定义能源模型参数

```python
analyzer.ENERGY_PARAMS['P_active_cpu'] = 95.0  # 根据实际硬件调整
```

---

## 版本历史

- **v1.0.0** (2026-01-31): 初始版本，包含7种内存分析场景和实时监控系统
