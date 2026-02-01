# Step 4 内存能源分析 - 使用说明

## 文件说明

| 文件 | 说明 |
|------|------|
| `energydebug.ipynb` | 原始 Notebook（未修改） |
| `energydebug_backup.ipynb` | 原始备份 |
| `energydebug_with_step4.ipynb` | ✅ **新增 Step 4 的完整 Notebook** |
| `memory_energy_analyzer.py` | 分析模块（约900行代码） |
| `MEMORY_ENERGY_ANALYSIS_README.md` | 详细文档 |

## 快速开始

1. **打开新 Notebook**
   ```bash
   # 使用 VS Code 打开
   code energydebug_with_step4.ipynb
   
   # 或使用 Jupyter
   jupyter notebook energydebug_with_step4.ipynb
   ```

2. **安装依赖**
   ```bash
   pip install psutil numpy pandas matplotlib seaborn ipywidgets
   # GPU监控可选
   pip install pynvml
   ```

3. **运行 Step 4**
   - 跳转到 Notebook 末尾的 **Step 4** 章节
   - 按顺序执行单元格

## Step 4 新增内容

### 分析场景（7个）
1. GPU vs CPU 内存访问差异
2. 缓存友好性分析
3. 统一内存 vs 分离内存
4. 数据驻留策略
5. 时间局部性分析
6. 堆分配 vs 栈分配
7. 内存池 vs 每次分配

### 实时监控功能
- 电池消耗百分比计算
- CPU/GPU/电池温度监控
- 进程级能耗追踪
- 可视化看板

### 磁盘空间优化
针对 C盘<10G, D盘<70G 的环境：
- 使用 `D:/energy_analysis_cache` 作为缓存目录
- 数据压缩存储（gzip，节省70-90%空间）
- 内存缓存限制（默认500MB）

## 使用示例

```python
# 导入模块
from memory_energy_analyzer import *

# 创建分析器
analyzer = create_analyzer(data_dir="D:/energy_analysis_cache")

# 运行全面分析
results = run_comprehensive_memory_analysis(analyzer)

# 可视化
visualize_memory_analysis_results(results)

# 启动实时监控
monitor = create_monitor(analyzer)
monitor.start_monitoring()

# 创建看板
dashboard = create_dashboard(monitor)
display(dashboard.create_dashboard())
dashboard.start_auto_update(interval=2.0)
```

## 注意事项

1. 原文件 `energydebug.ipynb` 保持未修改状态
2. 所有新功能在 `energydebug_with_step4.ipynb` 中
3. 分析模块 `memory_energy_analyzer.py` 需要与 Notebook 在同一目录
4. 首次运行时会自动创建缓存目录

## 故障排除

**问题**: VS Code 无法打开 notebook
- **解决**: 使用 `energydebug_with_step4.ipynb` 而非原文件

**问题**: 模块导入失败
- **解决**: 确认 `memory_energy_analyzer.py` 在同一目录

**问题**: 磁盘空间不足
- **解决**: 修改 `cache_dir` 到有足够空间的磁盘
