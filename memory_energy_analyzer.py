#!/usr/bin/env python3
"""
内存访问模式与能源深度分析模块
Memory Access Pattern & Energy Deep Analysis Module

针对磁盘空间优化（C盘<10G, D盘<70G）- 使用流式处理和压缩存储
"""

import psutil
import time
import json
import gzip
import threading
import os
import tempfile
import warnings
from collections import deque
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple, Callable, Any
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display, clear_output
import ipywidgets as widgets

# 尝试导入GPU监控库
try:
    import pynvml
    HAS_PYNVML = True
except ImportError:
    HAS_PYNVML = False
    warnings.warn("pynvml not installed, GPU monitoring will be limited")

# 尝试导入温度监控
try:
    import wmi
    HAS_WMI = True
except ImportError:
    HAS_WMI = False

# 尝试导入OpenCL用于跨平台GPU检测
try:
    import pyopencl as cl
    HAS_PYOPENCL = True
except ImportError:
    HAS_PYOPENCL = False


# =============================================================================
# 数据类定义
# =============================================================================

@dataclass
class MemoryAccessPattern:
    """内存访问模式数据结构"""
    pattern_type: str  # 'sequential', 'random', 'strided', 'blocked'
    cache_friendly: bool
    memory_type: str  # 'unified', 'separated', 'pinned', 'managed'
    allocation_strategy: str  # 'heap', 'stack', 'pool', 'per_call'
    data_residency: str  # 'cpu', 'gpu', 'migrated', 'prefetched'
    access_count: int
    cache_miss_rate: float
    page_faults: int
    energy_consumption: float  # Joules
    timestamp: float
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class BatteryStatus:
    """电池状态数据结构"""
    percent: float
    power_plugged: bool
    estimated_remaining_time: Optional[float]  # seconds
    voltage: Optional[float]
    current: Optional[float]
    design_capacity: Optional[float]  # Wh
    full_charge_capacity: Optional[float]  # Wh
    cycle_count: Optional[int]
    temperature: Optional[float]  # Celsius
    
    def get_consumed_percent(self, initial_percent: float) -> float:
        """计算已消耗的电池百分比"""
        return max(0, initial_percent - self.percent)
    
    def estimate_energy_consumed_wh(self, initial_percent: float) -> float:
        """估算已消耗的能源(Wh)"""
        if self.full_charge_capacity:
            consumed_percent = self.get_consumed_percent(initial_percent)
            return self.full_charge_capacity * consumed_percent / 100.0
        return 0.0


@dataclass
class SystemTemperature:
    """系统温度数据结构"""
    cpu_temp: Optional[float]
    gpu_temp: Optional[float]
    battery_temp: Optional[float]
    ambient_temp: Optional[float]
    hotspot_temp: Optional[float]
    timestamp: float


@dataclass
class ProcessEnergy:
    """进程级能耗数据结构"""
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    energy_estimate: float  # Estimated Joules
    io_read_bytes: int
    io_write_bytes: int
    timestamp: float


@dataclass
class GPUMemoryInfo:
    """GPU内存信息"""
    gpu_id: int
    total_memory: int  # bytes
    free_memory: int
    used_memory: int
    memory_type: str  # 'dedicated', 'shared', 'unified'
    temperature: Optional[float]
    power_draw: Optional[float]  # Watts
    utilization: Optional[float]  # percent


# =============================================================================
# 核心分析器类
# =============================================================================

class MemoryEnergyAnalyzer:
    """
    内存访问模式与能源消耗分析器
    支持低磁盘空间模式（流式处理+压缩）
    """
    
    # 能源模型参数（基于典型硬件功耗研究）
    ENERGY_PARAMS = {
        'P_idle_cpu': 10.0,  # Watts
        'P_idle_gpu': 5.0,
        'P_active_cpu': 65.0,
        'P_active_gpu': 150.0,
        'E_per_access_cpu': 2.5e-9,  # 2.5 nJ
        'E_per_access_gpu': 1.0e-9,  # 1 nJ (HBM)
        'E_cache_hit': 0.5e-9,  # 0.5 nJ
        'E_cache_miss_l1': 5e-9,  # 5 nJ
        'E_cache_miss_l2': 15e-9,  # 15 nJ
        'E_cache_miss_l3': 50e-9,  # 50 nJ
        'E_page_fault': 10e-6,  # 10 µJ
        'E_data_migration': 1e-6,  # 1 µJ per byte
        'E_pci_transfer': 0.5e-6,  # 0.5 µJ per byte (PCIe)
    }
    
    def __init__(self, max_memory_mb: int = 500, disk_limit_gb: float = 5.0, 
                 data_dir: Optional[str] = None):
        """
        初始化分析器
        
        Args:
            max_memory_mb: 内存中保留的最大数据量(MB)
            disk_limit_gb: 磁盘使用限制(GB)
            data_dir: 数据存储目录，默认使用临时目录
        """
        self.max_memory_mb = max_memory_mb
        self.disk_limit_gb = disk_limit_gb
        
        # 使用临时目录或指定目录
        if data_dir is None:
            data_dir = tempfile.gettempdir()
        self.data_dir = Path(data_dir) / "energy_analysis"
        self.data_dir.mkdir(exist_ok=True)
        
        # 内存缓存（限制大小）
        self.patterns: deque = deque(maxlen=10000)
        self.energy_history: deque = deque(maxlen=10000)
        self.temperature_history: deque = deque(maxlen=5000)
        self.process_history: deque = deque(maxlen=5000)
        
        self._lock = threading.Lock()
        self._file_counter = 0
        
        # 初始化NVML（如果可用）
        self._init_gpu_monitoring()
        
    def _init_gpu_monitoring(self):
        """初始化GPU监控"""
        self.gpu_available = False
        self.nvml_initialized = False
        
        if HAS_PYNVML:
            try:
                pynvml.nvmlInit()
                self.gpu_count = pynvml.nvmlDeviceGetCount()
                self.gpu_handles = [
                    pynvml.nvmlDeviceGetHandleByIndex(i) 
                    for i in range(self.gpu_count)
                ]
                self.gpu_available = True
                self.nvml_initialized = True
                print(f"✓ GPU监控已初始化，检测到 {self.gpu_count} 个GPU")
            except Exception as e:
                print(f"⚠ GPU监控初始化失败: {e}")
        
        # 检测OpenCL设备
        self.opencl_devices = []
        if HAS_PYOPENCL:
            try:
                platforms = cl.get_platforms()
                for platform in platforms:
                    devices = platform.get_devices()
                    self.opencl_devices.extend(devices)
                print(f"✓ OpenCL设备: {len(self.opencl_devices)} 个")
            except:
                pass
    
    def __del__(self):
        """清理资源"""
        if self.nvml_initialized:
            try:
                pynvml.nvmlShutdown()
            except:
                pass
    
    # ========================================================================
    # 1. GPU与CPU内存访问差异分析
    # ========================================================================
    
    def analyze_gpu_cpu_memory_access(
        self,
        data_size_bytes: int,
        access_pattern: str = 'sequential',
        iterations: int = 1000,
        use_unified_memory: bool = False
    ) -> Dict[str, Any]:
        """
        分析GPU与CPU内存访问的能源差异
        
        Returns:
            包含CPU和GPU能耗对比结果的字典
        """
        results = {
            'cpu': {},
            'gpu': {},
            'comparison': {}
        }
        
        # CPU内存访问分析
        cpu_pattern = self.analyze_memory_pattern(
            pattern_type=access_pattern,
            memory_type='separated' if not use_unified_memory else 'unified',
            data_residency='cpu',
            access_count=iterations,
            data_size=data_size_bytes
        )
        results['cpu'] = {
            'energy_joules': cpu_pattern.energy_consumption,
            'estimated_time_ms': self._estimate_execution_time(
                'cpu', access_pattern, data_size_bytes, iterations
            ),
            'bandwidth_gbps': self._estimate_bandwidth('cpu', access_pattern)
        }
        
        # GPU内存访问分析
        if self.gpu_available:
            gpu_pattern = self.analyze_memory_pattern(
                pattern_type=access_pattern,
                memory_type='unified' if use_unified_memory else 'separated',
                data_residency='gpu',
                access_count=iterations,
                data_size=data_size_bytes
            )
            
            # 计算PCIe传输开销（如果是分离内存）
            pcie_overhead = 0
            if not use_unified_memory:
                pcie_overhead = data_size_bytes * 2 * self.ENERGY_PARAMS['E_pci_transfer']  # 往返
            
            results['gpu'] = {
                'energy_joules': gpu_pattern.energy_consumption + pcie_overhead,
                'estimated_time_ms': self._estimate_execution_time(
                    'gpu', access_pattern, data_size_bytes, iterations
                ),
                'bandwidth_gbps': self._estimate_bandwidth('gpu', access_pattern),
                'pcie_overhead_joules': pcie_overhead if not use_unified_memory else 0
            }
            
            # 对比分析
            results['comparison'] = {
                'energy_ratio_gpu_to_cpu': results['gpu']['energy_joules'] / max(results['cpu']['energy_joules'], 1e-9),
                'speedup_gpu_vs_cpu': results['cpu']['estimated_time_ms'] / max(results['gpu']['estimated_time_ms'], 1),
                'efficiency_improvement': (
                    results['cpu']['energy_joules'] / results['cpu']['estimated_time_ms'] * 1000
                ) / (
                    results['gpu']['energy_joules'] / results['gpu']['estimated_time_ms'] * 1000
                ),
                'unified_memory_benefit': use_unified_memory
            }
        else:
            results['gpu'] = {'error': 'GPU not available'}
            results['comparison'] = {'error': 'Cannot compare without GPU'}
        
        return results
    
    # ========================================================================
    # 2. 缓存友好性分析
    # ========================================================================
    
    def analyze_cache_friendliness(
        self,
        array_size: int,
        element_size: int = 8,
        test_patterns: List[str] = None
    ) -> pd.DataFrame:
        """
        分析不同内存访问模式的缓存友好性和能源消耗
        
        Args:
            array_size: 数组元素数量
            element_size: 每个元素的字节数
            test_patterns: 要测试的访问模式列表
        
        Returns:
            DataFrame包含各模式的分析结果
        """
        if test_patterns is None:
            test_patterns = ['sequential', 'blocked', 'strided', 'random']
        
        results = []
        total_bytes = array_size * element_size
        
        # 缓存参数假设
        cache_line_size = 64  # bytes
        l1_cache_size = 32 * 1024  # 32 KB
        l2_cache_size = 256 * 1024  # 256 KB
        l3_cache_size = 8 * 1024 * 1024  # 8 MB
        
        for pattern in test_patterns:
            # 计算缓存命中率（简化模型）
            if pattern == 'sequential':
                cache_miss_rate = max(0.01, cache_line_size / element_size / array_size)
                temporal_locality = 1.0
            elif pattern == 'blocked':
                block_size = min(l1_cache_size // element_size, 256)
                cache_miss_rate = max(0.02, 1.0 / block_size)
                temporal_locality = 0.9
            elif pattern == 'strided':
                stride = max(1, array_size // 100)
                cache_miss_rate = min(0.5, stride * element_size / cache_line_size)
                temporal_locality = 0.3
            elif pattern == 'random':
                cache_miss_rate = 0.3 + (total_bytes / l3_cache_size) * 0.4
                temporal_locality = 0.1
            else:
                cache_miss_rate = 0.1
                temporal_locality = 0.5
            
            cache_miss_rate = min(0.9, max(0.01, cache_miss_rate))
            
            # 计算能源消耗
            pattern_result = self.analyze_memory_pattern(
                pattern_type=pattern,
                cache_miss_rate=cache_miss_rate,
                access_count=array_size,
                temporal_locality=temporal_locality
            )
            
            results.append({
                'pattern': pattern,
                'cache_friendly': pattern_result.cache_friendly,
                'cache_miss_rate': cache_miss_rate,
                'temporal_locality': temporal_locality,
                'energy_joules': pattern_result.energy_consumption,
                'energy_per_access_nj': pattern_result.energy_consumption / array_size * 1e9,
                'estimated_performance_score': 1.0 / (1.0 + cache_miss_rate * 10)
            })
        
        return pd.DataFrame(results)
    
    # ========================================================================
    # 3. 统一内存 vs 分离内存分析
    # ========================================================================
    
    def analyze_unified_vs_separated_memory(
        self,
        data_size_bytes: int,
        access_ratio_cpu: float = 0.3,  # CPU访问比例
        migration_frequency: int = 10,  # 数据迁移次数
    ) -> Dict[str, Any]:
        """
        对比统一内存(Unified Memory)和分离内存的能源消耗
        """
        results = {
            'unified_memory': {},
            'separated_memory': {},
            'recommendation': ''
        }
        
        # 统一内存分析
        # 优势：自动迁移，编程简单
        # 劣势：页错误开销，不可控迁移
        unified_pattern = self.analyze_memory_pattern(
            pattern_type='sequential',
            memory_type='unified',
            data_residency='migrated',
            access_count=data_size_bytes // 64,  # 假设cache line大小
            page_faults=migration_frequency * 10  # 每次迁移可能触发多个页错误
        )
        
        # 分离内存分析
        # 优势：完全控制，无意外迁移
        # 劣势：显式管理开销，PCIe传输
        cpu_access_bytes = int(data_size_bytes * access_ratio_cpu)
        gpu_access_bytes = data_size_bytes - cpu_access_bytes
        
        # CPU部分
        cpu_pattern = self.analyze_memory_pattern(
            pattern_type='sequential',
            memory_type='separated',
            data_residency='cpu',
            access_count=cpu_access_bytes // 64
        )
        
        # GPU部分
        gpu_pattern = self.analyze_memory_pattern(
            pattern_type='sequential',
            memory_type='separated',
            data_residency='gpu',
            access_count=gpu_access_bytes // 64
        )
        
        # PCIe传输开销（初始传输）
        pcie_energy = data_size_bytes * self.ENERGY_PARAMS['E_pci_transfer']
        
        results['unified_memory'] = {
            'total_energy_joules': unified_pattern.energy_consumption,
            'page_fault_overhead': unified_pattern.page_faults * self.ENERGY_PARAMS['E_page_fault'],
            'programming_complexity': 'Low',
            'control_level': 'Automatic',
            'best_for': 'Data with unpredictable access patterns'
        }
        
        results['separated_memory'] = {
            'total_energy_joules': cpu_pattern.energy_consumption + gpu_pattern.energy_consumption + pcie_energy,
            'pcie_transfer_overhead': pcie_energy,
            'programming_complexity': 'High',
            'control_level': 'Full',
            'best_for': 'Predictable data access, performance-critical code'
        }
        
        # 给出建议
        energy_diff = results['separated_memory']['total_energy_joules'] - results['unified_memory']['total_energy_joules']
        
        if energy_diff < -0.1:  # 分离内存更节能
            results['recommendation'] = f"分离内存更节能 ({abs(energy_diff):.4f} J)，适合当前数据访问模式"
        elif energy_diff > 0.1:  # 统一内存更节能
            results['recommendation'] = f"统一内存更节能 ({energy_diff:.4f} J)，且编程更简单"
        else:
            results['recommendation'] = "两种内存模式能耗相近，建议优先考虑编程复杂度"
        
        results['energy_difference_joules'] = energy_diff
        
        return results
    
    # ========================================================================
    # 4. 数据驻留策略分析
    # ========================================================================
    
    def analyze_data_residency_strategy(
        self,
        data_size_bytes: int,
        cpu_access_frequency: float,  # 每秒CPU访问次数
        gpu_access_frequency: float,  # 每秒GPU访问次数
        strategy: str = 'on_demand'  # 'on_demand', 'prefetch', 'pinned', 'duplicate'
    ) -> Dict[str, Any]:
        """
        分析不同数据驻留策略的能源效率
        
        Strategies:
        - on_demand: 按需迁移（统一内存默认）
        - prefetch: 预取到GPU
        - pinned: 使用页锁定内存
        - duplicate: CPU/GPU各保留一份
        """
        results = {'strategy': strategy, 'data_size_mb': data_size_bytes / (1024*1024)}
        
        # 计算访问比
        total_access = cpu_access_frequency + gpu_access_frequency
        cpu_ratio = cpu_access_frequency / total_access if total_access > 0 else 0.5
        gpu_ratio = gpu_access_frequency / total_access if total_access > 0 else 0.5
        
        if strategy == 'on_demand':
            # 按需迁移：每次访问不同设备时触发页错误
            migrations_per_second = min(cpu_access_frequency, gpu_access_frequency)
            page_faults = int(migrations_per_second * 10)  # 假设每次迁移10个页
            energy = page_faults * self.ENERGY_PARAMS['E_page_fault']
            overhead = 'High' if migrations_per_second > 10 else 'Medium'
            
        elif strategy == 'prefetch':
            # 预取：一次性的传输开销
            transfer_energy = data_size_bytes * self.ENERGY_PARAMS['E_pci_transfer']
            # GPU访问效率高，但CPU访问需要回传
            cpu_access_energy = cpu_access_frequency * self.ENERGY_PARAMS['E_per_access_cpu'] * 10  # 惩罚
            gpu_access_energy = gpu_access_frequency * self.ENERGY_PARAMS['E_per_access_gpu']
            energy = transfer_energy + cpu_access_energy + gpu_access_energy
            overhead = 'Low' if gpu_ratio > 0.8 else 'Medium'
            
        elif strategy == 'pinned':
            # 页锁定内存：无页错误，但分配开销大
            allocation_energy = data_size_bytes * 5e-6  # 额外分配开销
            access_energy = total_access * self.ENERGY_PARAMS['E_per_access_cpu'] * 0.9  # 略高效
            energy = allocation_energy + access_energy
            overhead = 'Low'
            
        elif strategy == 'duplicate':
            # 双份存储：存储开销，但访问最快
            storage_energy = data_size_bytes * 2 * 1e-9 * 3600  # 保持双份的能耗
            cpu_access_energy = cpu_access_frequency * self.ENERGY_PARAMS['E_per_access_cpu']
            gpu_access_energy = gpu_access_frequency * self.ENERGY_PARAMS['E_per_access_gpu']
            energy = storage_energy + cpu_access_energy + gpu_access_energy
            overhead = 'Low'
            
        else:
            energy = 0
            overhead = 'Unknown'
        
        results.update({
            'estimated_energy_joules_per_second': energy,
            'memory_overhead': overhead,
            'suitable_for': self._get_residency_recommendation(strategy, cpu_ratio, gpu_ratio),
            'bandwidth_efficiency': self._estimate_residency_bandwidth(strategy)
        })
        
        return results
    
    # ========================================================================
    # 5. 数据重用与时间局部性分析
    # ========================================================================
    
    def analyze_temporal_locality(
        self,
        access_sequence: List[int],  # 内存地址访问序列
        cache_size: int = 32768,  # L1 cache大小（字节）
        cache_line_size: int = 64
    ) -> Dict[str, Any]:
        """
        分析时间局部性及其对能源的影响
        """
        results = {}
        
        # 计算重用距离
        reuse_distances = []
        last_access = {}
        
        for i, addr in enumerate(access_sequence):
            if addr in last_access:
                reuse_distances.append(i - last_access[addr])
            last_access[addr] = i
        
        # 计算时间局部性指标
        if reuse_distances:
            avg_reuse_distance = np.mean(reuse_distances)
            max_reuse_distance = max(reuse_distances)
            
            # 缓存命中估计
            cache_lines = cache_size // cache_line_size
            cache_hits = sum(1 for d in reuse_distances if d < len(access_sequence) * 0.1)
            cache_miss_rate = 1.0 - (cache_hits / len(access_sequence)) if access_sequence else 1.0
            
            # 时间局部性评分 (0-1)
            temporal_locality = 1.0 / (1.0 + avg_reuse_distance / len(access_sequence))
        else:
            avg_reuse_distance = float('inf')
            cache_miss_rate = 1.0
            temporal_locality = 0.0
        
        # 计算能源影响
        access_pattern = self.analyze_memory_pattern(
            pattern_type='sequential' if self._is_sequential(access_sequence) else 'random',
            cache_miss_rate=cache_miss_rate,
            access_count=len(access_sequence),
            temporal_locality=temporal_locality
        )
        
        results = {
            'temporal_locality_score': temporal_locality,
            'average_reuse_distance': avg_reuse_distance,
            'cache_miss_rate': cache_miss_rate,
            'energy_consumption_joules': access_pattern.energy_consumption,
            'energy_per_access': access_pattern.energy_consumption / max(len(access_sequence), 1),
            'optimization_suggestions': self._get_locality_suggestions(temporal_locality, cache_miss_rate)
        }
        
        return results
    
    # ========================================================================
    # 6. 堆分配 vs 栈分配分析
    # ========================================================================
    
    def analyze_heap_vs_stack(
        self,
        allocation_size: int,
        allocation_count: int,
        lifetime_seconds: float = 0.001
    ) -> Dict[str, Any]:
        """
        对比堆分配和栈分配的能源消耗
        """
        results = {
            'heap': {},
            'stack': {}
        }
        
        # 堆分配分析
        # 开销：malloc/free系统调用，内存碎片，潜在锁竞争
        heap_allocation_overhead = 100e-9  # 100 ns malloc开销
        heap_deallocation_overhead = 50e-9  # 50 ns free开销
        heap_fragmentation_factor = 1.2  # 20%碎片开销
        
        heap_energy = allocation_count * (
            heap_allocation_overhead + 
            heap_deallocation_overhead + 
            lifetime_seconds * 0.1  # 内存保持开销
        ) * self.ENERGY_PARAMS['P_active_cpu']
        
        heap_memory_overhead = allocation_size * heap_fragmentation_factor
        
        results['heap'] = {
            'allocation_energy_joules': heap_energy,
            'memory_overhead_bytes': heap_memory_overhead - allocation_size,
            'fragmentation_factor': heap_fragmentation_factor,
            'lifetime_flexibility': 'Flexible',
            'thread_safety': 'Yes (with locks)',
            'max_size': 'Limited by heap',
            'suitable_for': 'Large objects, long lifetime, dynamic size'
        }
        
        # 栈分配分析
        # 开销：仅SP移动，极快，自动释放
        stack_allocation_overhead = 5e-9  # 5 ns（单个指令）
        stack_deallocation_overhead = 2e-9  # 2 ns
        
        stack_energy = allocation_count * (
            stack_allocation_overhead + 
            stack_deallocation_overhead
        ) * self.ENERGY_PARAMS['P_active_cpu']
        
        results['stack'] = {
            'allocation_energy_joules': stack_energy,
            'memory_overhead_bytes': 0,
            'fragmentation_factor': 1.0,
            'lifetime_flexibility': 'Function scope only',
            'thread_safety': 'Yes (thread-local)',
            'max_size': 'Limited by stack size (~1-8MB)',
            'suitable_for': 'Small objects, short lifetime, fixed size'
        }
        
        # 对比
        energy_ratio = heap_energy / max(stack_energy, 1e-12)
        results['comparison'] = {
            'heap_to_stack_energy_ratio': energy_ratio,
            'energy_savings_if_using_stack': f"{(1 - 1/energy_ratio)*100:.1f}%" if energy_ratio > 1 else "N/A",
            'recommendation': self._get_allocation_recommendation(
                allocation_size, allocation_count, lifetime_seconds
            )
        }
        
        return results
    
    # ========================================================================
    # 7. 内存池 vs 每次分配分析
    # ========================================================================
    
    def analyze_memory_pool_vs_per_allocation(
        self,
        object_size: int,
        total_objects: int,
        peak_concurrent_objects: int,
        allocation_pattern: str = 'uniform'  # 'uniform', 'burst', 'gradual'
    ) -> Dict[str, Any]:
        """
        对比内存池和每次动态分配的能源效率
        """
        results = {
            'memory_pool': {},
            'per_allocation': {}
        }
        
        total_memory_needed = object_size * total_objects
        peak_memory = object_size * peak_concurrent_objects
        
        # 内存池分析
        # 优势：预分配，无运行时分配开销，内存局部性好
        # 劣势：可能占用更多内存（预分配峰值），碎片化
        
        pool_initialization_overhead = peak_memory * 2e-6  # 初始化能耗
        pool_allocation_cost = 1e-9  # 极低的分配开销（仅指针移动）
        pool_deallocation_cost = 1e-9
        pool_memory_overhead = 1.1  # 10%管理开销
        
        # 根据分配模式调整
        pattern_factor = {'uniform': 1.0, 'burst': 1.5, 'gradual': 0.8}
        pf = pattern_factor.get(allocation_pattern, 1.0)
        
        pool_energy = (
            pool_initialization_overhead +
            total_objects * (pool_allocation_cost + pool_deallocation_cost) * pf
        ) * self.ENERGY_PARAMS['P_active_cpu']
        
        results['memory_pool'] = {
            'total_energy_joules': pool_energy,
            'initialization_energy': pool_initialization_overhead * self.ENERGY_PARAMS['P_active_cpu'],
            'per_operation_energy': (pool_allocation_cost + pool_deallocation_cost) * self.ENERGY_PARAMS['P_active_cpu'],
            'memory_overhead_factor': pool_memory_overhead,
            'peak_memory_reserved': peak_memory * pool_memory_overhead,
            'allocation_latency': 'O(1) - constant',
            'cache_locality': 'High',
            'suitable_for': 'High-frequency allocations, fixed-size objects'
        }
        
        # 每次动态分配分析
        malloc_cost = 100e-9
        free_cost = 50e-9
        lock_contention_factor = 1.0 + (total_objects / 10000) * 0.5  # 锁竞争
        
        per_alloc_energy = (
            total_objects * (malloc_cost + free_cost) * lock_contention_factor * pf
        ) * self.ENERGY_PARAMS['P_active_cpu']
        
        results['per_allocation'] = {
            'total_energy_joules': per_alloc_energy,
            'initialization_energy': 0,
            'per_operation_energy': (malloc_cost + free_cost) * lock_contention_factor * self.ENERGY_PARAMS['P_active_cpu'],
            'memory_overhead_factor': 1.3,  # 更多碎片
            'peak_memory_reserved': peak_memory * 1.3,
            'allocation_latency': 'O(log n) - depends on heap state',
            'cache_locality': 'Low-Medium',
            'suitable_for': 'Variable-size objects, low-frequency allocations'
        }
        
        # 对比
        savings = per_alloc_energy - pool_energy
        results['comparison'] = {
            'energy_savings_with_pool_joules': savings,
            'energy_savings_percent': (savings / max(per_alloc_energy, 1e-12)) * 100,
            'memory_tradeoff': f"内存池多占用 {((pool_memory_overhead - 1.3) * 100):.0f}%",
            'break_even_point': f"约 {int(pool_initialization_overhead / ((malloc_cost + free_cost - pool_allocation_cost - pool_deallocation_cost) * pf))} 次分配",
            'recommendation': 'Use memory pool' if savings > 0.01 else 'Either is fine'
        }
        
        return results
    
    # ========================================================================
    # 核心分析函数
    # ========================================================================
    
    def analyze_memory_pattern(
        self,
        pattern_type: str,
        memory_type: str = 'unified',
        allocation_strategy: str = 'heap',
        data_residency: str = 'cpu',
        cache_miss_rate: float = 0.0,
        page_faults: int = 0,
        access_count: int = 1,
        temporal_locality: float = 0.5,
        data_size: int = 0,
        duration_seconds: float = None
    ) -> MemoryAccessPattern:
        """
        分析特定内存访问模式的能源消耗
        """
        P = self.ENERGY_PARAMS
        
        # 计算执行时间（如果未提供）
        if duration_seconds is None:
            duration_seconds = self._estimate_execution_time(
                data_residency, pattern_type, data_size, access_count
            ) / 1000.0
        
        # 基础能耗
        if data_residency in ['gpu', 'migrated']:
            P_idle = P['P_idle_gpu']
            P_active = P['P_active_gpu']
            E_per_access = P['E_per_access_gpu']
        else:
            P_idle = P['P_idle_cpu']
            P_active = P['P_active_cpu']
            E_per_access = P['E_per_access_cpu']
        
        # 活动因子
        activity_factor = min(1.0, access_count / (duration_seconds * 1e6 + 1))
        P_avg = P_idle + (P_active - P_idle) * activity_factor
        E_base = P_avg * duration_seconds
        
        # 内存访问能耗
        cache_hits = int(access_count * (1 - cache_miss_rate))
        cache_misses = access_count - cache_hits
        
        # 分层缓存模型
        l1_misses = int(cache_misses * 0.7)
        l2_misses = int(cache_misses * 0.25)
        l3_misses = cache_misses - l1_misses - l2_misses
        
        E_mem = (
            cache_hits * P['E_cache_hit'] +
            l1_misses * P['E_cache_miss_l1'] +
            l2_misses * P['E_cache_miss_l2'] +
            l3_misses * P['E_cache_miss_l3']
        )
        
        # 时间局部性奖励
        locality_bonus = 1.0 - temporal_locality * 0.3
        E_mem *= locality_bonus
        
        # 页错误能耗
        E_fault = page_faults * P['E_page_fault']
        
        # 数据迁移能耗
        E_migrate = 0.0
        if data_residency == 'migrated' and data_size > 0:
            E_migrate = data_size * P['E_data_migration']
        
        # 分配策略开销
        allocation_overhead = {
            'heap': 1.0,
            'stack': 0.8,
            'pool': 0.7,
            'per_call': 1.3
        }
        
        # 访问模式效率
        pattern_efficiency = {
            'sequential': 1.0,
            'blocked': 1.0,
            'strided': 1.3,
            'random': 1.8
        }
        
        total_energy = (
            E_base +
            E_mem * pattern_efficiency.get(pattern_type, 1.0) +
            E_fault +
            E_migrate
        ) * allocation_overhead.get(allocation_strategy, 1.0)
        
        cache_friendly = (
            pattern_type in ['sequential', 'blocked'] and 
            cache_miss_rate < 0.1 and 
            temporal_locality > 0.5
        )
        
        pattern = MemoryAccessPattern(
            pattern_type=pattern_type,
            cache_friendly=cache_friendly,
            memory_type=memory_type,
            allocation_strategy=allocation_strategy,
            data_residency=data_residency,
            access_count=access_count,
            cache_miss_rate=cache_miss_rate,
            page_faults=page_faults,
            energy_consumption=total_energy,
            timestamp=time.time()
        )
        
        with self._lock:
            self.patterns.append(pattern)
            self.energy_history.append({
                'timestamp': pattern.timestamp,
                'energy': total_energy,
                'pattern': pattern_type
            })
        
        return pattern
    
    # ========================================================================
    # 辅助函数
    # ========================================================================
    
    def _estimate_execution_time(self, device: str, pattern: str, 
                                  data_size: int, iterations: int) -> float:
        """估算执行时间（毫秒）"""
        # 简化的性能模型
        bandwidth = self._estimate_bandwidth(device, pattern)
        return (data_size * iterations / (bandwidth * 1e9)) * 1000  # ms
    
    def _estimate_bandwidth(self, device: str, pattern: str) -> float:
        """估算内存带宽(GB/s)"""
        if device == 'cpu':
            base_bw = 50.0  # DDR4/5
        else:
            base_bw = 900.0  # HBM2/3
        
        efficiency = {
            'sequential': 0.9,
            'blocked': 0.85,
            'strided': 0.4,
            'random': 0.1
        }
        
        return base_bw * efficiency.get(pattern, 0.7)
    
    def _is_sequential(self, sequence: List[int]) -> bool:
        """检测访问序列是否顺序"""
        if len(sequence) < 2:
            return True
        diffs = [sequence[i+1] - sequence[i] for i in range(len(sequence)-1)]
        return all(d == diffs[0] for d in diffs) and diffs[0] > 0
    
    def _get_allocation_recommendation(self, size: int, count: int, lifetime: float) -> str:
        """给出分配策略建议"""
        if size > 1024 * 1024:  # > 1MB
            return "Heap - Object too large for stack"
        if lifetime > 1.0:  # > 1 second
            return "Heap - Lifetime exceeds function scope"
        if count > 1000:
            return "Stack - High frequency, consider memory pool"
        return "Stack - Small, short-lived object"
    
    def _get_residency_recommendation(self, strategy: str, cpu_ratio: float, gpu_ratio: float) -> str:
        """给出数据驻留策略建议"""
        if strategy == 'on_demand':
            return "Balanced CPU/GPU access or unpredictable patterns"
        elif strategy == 'prefetch':
            return "GPU-dominant workload (>80% GPU access)"
        elif strategy == 'pinned':
            return "Frequent CPU-GPU synchronization"
        elif strategy == 'duplicate':
            return "High-frequency concurrent access from both"
        return "General purpose"
    
    def _estimate_residency_bandwidth(self, strategy: str) -> float:
        """估算驻留策略的带宽效率"""
        efficiency = {
            'on_demand': 0.7,
            'prefetch': 0.9,
            'pinned': 0.85,
            'duplicate': 0.95
        }
        return efficiency.get(strategy, 0.7)
    
    def _get_locality_suggestions(self, locality: float, miss_rate: float) -> List[str]:
        """给出局部性优化建议"""
        suggestions = []
        if locality < 0.3:
            suggestions.append("考虑数据重排以提高时间局部性")
        if miss_rate > 0.2:
            suggestions.append("使用分块(blocking)技术提高缓存命中率")
        if miss_rate > 0.5:
            suggestions.append("数据量可能超过缓存容量，考虑流式处理")
        return suggestions if suggestions else ["局部性良好"]


# =============================================================================
# 实时监控与电池计算类
# =============================================================================

class RealTimeEnergyMonitor:
    """
    实时能耗监控器
    提供电池消耗计算、温度监控、进程级能耗追踪
    """
    
    def __init__(self, analyzer: MemoryEnergyAnalyzer, update_interval: float = 1.0):
        """
        Args:
            analyzer: MemoryEnergyAnalyzer实例
            update_interval: 更新间隔（秒）
        """
        self.analyzer = analyzer
        self.update_interval = update_interval
        self.running = False
        self.monitor_thread = None
        
        # 电池信息
        self.battery_initial = None
        self.battery_history: deque = deque(maxlen=1000)
        
        # 温度历史
        self.temperature_history: deque = deque(maxlen=1000)
        
        # 进程历史
        self.process_history: deque = deque(maxlen=1000)
        
        # 累计能耗
        self.total_energy_joules = 0.0
        self.energy_by_component = {
            'cpu': 0.0,
            'gpu': 0.0,
            'memory': 0.0,
            'io': 0.0
        }
        
        # WMI接口（Windows）
        self.wmi_interface = None
        if HAS_WMI:
            try:
                self.wmi_interface = wmi.WMI()
            except:
                pass
        
    def get_battery_status(self) -> Optional[BatteryStatus]:
        """获取电池状态"""
        try:
            battery = psutil.sensors_battery()
            if battery is None:
                return None
            
            status = BatteryStatus(
                percent=battery.percent,
                power_plugged=battery.power_plugged,
                estimated_remaining_time=battery.secsleft if battery.secsleft != psutil.POWER_TIME_UNLIMITED else None,
                voltage=None,
                current=None,
                design_capacity=None,
                full_charge_capacity=None,
                cycle_count=None,
                temperature=None
            )
            
            # 尝试通过WMI获取更详细的信息
            if self.wmi_interface:
                try:
                    for bat in self.wmi_interface.Win32_Battery():
                        status.design_capacity = getattr(bat, 'DesignCapacity', None)
                        if status.design_capacity:
                            status.design_capacity *= 1e-3  # mWh to Wh
                except:
                    pass
            
            return status
        except Exception as e:
            print(f"获取电池状态失败: {e}")
            return None
    
    def get_system_temperature(self) -> SystemTemperature:
        """获取系统温度"""
        temps = SystemTemperature(
            cpu_temp=None,
            gpu_temp=None,
            battery_temp=None,
            ambient_temp=None,
            hotspot_temp=None,
            timestamp=time.time()
        )
        
        # CPU温度
        try:
            if hasattr(psutil, 'sensors_temperatures'):
                sensors = psutil.sensors_temperatures()
                if sensors:
                    for name, entries in sensors.items():
                        if entries:
                            temps.cpu_temp = entries[0].current
                            break
        except:
            pass
        
        # GPU温度
        if self.analyzer.gpu_available and HAS_PYNVML:
            try:
                handle = self.analyzer.gpu_handles[0]
                temps.gpu_temp = pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
            except:
                pass
        
        return temps
    
    def get_process_energy(self) -> List[ProcessEnergy]:
        """获取各进程的能耗估算"""
        processes = []
        current_time = time.time()
        
        # 获取CPU总使用率作为参考
        cpu_percent_total = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        
        # 获取当前进程列表
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 
                                          'memory_percent', 'memory_info',
                                          'io_counters']):
            try:
                info = proc.info
                
                # 估算该进程的能耗
                # 简化模型：按CPU使用率比例分配总能耗
                if cpu_percent_total > 0:
                    energy_share = (info['cpu_percent'] or 0) / cpu_percent_total
                else:
                    energy_share = 0
                
                # 基础功耗约10W + 活动功耗
                estimated_power = 10 + 50 * (info['cpu_percent'] or 0) / 100 / cpu_count
                estimated_energy = estimated_power * self.update_interval * energy_share
                
                proc_energy = ProcessEnergy(
                    pid=info['pid'],
                    name=info['name'] or 'Unknown',
                    cpu_percent=info['cpu_percent'] or 0,
                    memory_percent=info['memory_percent'] or 0,
                    memory_mb=(info['memory_info'].rss / (1024*1024)) if info['memory_info'] else 0,
                    energy_estimate=estimated_energy,
                    io_read_bytes=info['io_counters'].read_bytes if info['io_counters'] else 0,
                    io_write_bytes=info['io_counters'].write_bytes if info['io_counters'] else 0,
                    timestamp=current_time
                )
                
                processes.append(proc_energy)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # 按能耗排序
        processes.sort(key=lambda x: x.energy_estimate, reverse=True)
        return processes[:20]  # 返回Top 20
    
    def start_monitoring(self):
        """开始实时监控"""
        self.running = True
        self.battery_initial = self.get_battery_status()
        
        if self.battery_initial:
            print(f"监控开始 - 初始电量: {self.battery_initial.percent}%")
        else:
            print("监控开始（未检测到电池）")
        
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """停止监控"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        
        # 输出汇总
        self._print_summary()
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            try:
                # 电池状态
                battery = self.get_battery_status()
                if battery:
                    self.battery_history.append(battery)
                
                # 温度
                temps = self.get_system_temperature()
                self.temperature_history.append(temps)
                
                # 进程能耗
                processes = self.get_process_energy()
                self.process_history.append({
                    'timestamp': time.time(),
                    'processes': processes
                })
                
                # 累计能耗
                self.total_energy_joules += sum(p.energy_estimate for p in processes)
                
                time.sleep(self.update_interval)
            except Exception as e:
                print(f"监控循环错误: {e}")
                time.sleep(self.update_interval)
    
    def _print_summary(self):
        """打印监控汇总"""
        print("\n" + "="*60)
        print("监控汇总")
        print("="*60)
        
        if self.battery_initial and self.battery_history:
            current = self.battery_history[-1]
            consumed = self.battery_initial.get_consumed_percent(current.percent)
            energy_wh = self.battery_initial.estimate_energy_consumed_wh(current.percent)
            
            print(f"电池消耗: {consumed:.2f}%")
            print(f"估算能耗: {energy_wh:.4f} Wh ({energy_wh*3600:.2f} J)")
        
        print(f"累计监测能耗: {self.total_energy_joules:.4f} J")
        
        if self.temperature_history:
            max_temp = max((t.cpu_temp or 0) for t in self.temperature_history)
            print(f"最高CPU温度: {max_temp:.1f}°C")
    
    def get_battery_consumption_report(self) -> Dict[str, Any]:
        """获取电池消耗报告"""
        if not self.battery_history or not self.battery_initial:
            return {'error': 'No battery data available'}
        
        current = self.battery_history[-1]
        
        report = {
            'initial_percent': self.battery_initial.percent,
            'current_percent': current.percent,
            'consumed_percent': self.battery_initial.get_consumed_percent(current.percent),
            'estimated_energy_wh': self.battery_initial.estimate_energy_consumed_wh(current.percent),
            'estimated_energy_joules': self.battery_initial.estimate_energy_consumed_wh(current.percent) * 3600,
            'power_plugged': current.power_plugged,
            'monitoring_duration_seconds': len(self.battery_history) * self.update_interval,
            'average_power_watts': None
        }
        
        if report['monitoring_duration_seconds'] > 0:
            report['average_power_watts'] = report['estimated_energy_joules'] / report['monitoring_duration_seconds']
        
        return report


# =============================================================================
# 可视化仪表板
# =============================================================================

class EnergyDashboard:
    """
    能源监控实时看板
    使用ipywidgets实现交互式可视化
    """
    
    def __init__(self, monitor: RealTimeEnergyMonitor):
        self.monitor = monitor
        self.widgets = {}
        self.output = None
        self.update_thread = None
        self.running = False
    
    def create_dashboard(self):
        """创建仪表板UI"""
        # 电池状态显示
        self.widgets['battery'] = widgets.FloatProgress(
            value=100,
            min=0,
            max=100,
            description='电池:',
            bar_style='success',
            orientation='horizontal'
        )
        
        self.widgets['battery_text'] = widgets.Label(value="100%")
        
        # 温度显示
        self.widgets['cpu_temp'] = widgets.Label(value="CPU: --°C")
        self.widgets['gpu_temp'] = widgets.Label(value="GPU: --°C")
        
        # 能耗显示
        self.widgets['energy'] = widgets.Label(value="累计能耗: 0 J")
        self.widgets['power'] = widgets.Label(value="当前功率: 0 W")
        
        # 进程列表
        self.widgets['process_list'] = widgets.Textarea(
            value='进程能耗排行:\n',
            disabled=True,
            layout=widgets.Layout(width='100%', height='200px')
        )
        
        # 创建布局
        battery_box = widgets.HBox([
            self.widgets['battery'],
            self.widgets['battery_text']
        ])
        
        temp_box = widgets.VBox([
            self.widgets['cpu_temp'],
            self.widgets['gpu_temp']
        ])
        
        stats_box = widgets.VBox([
            self.widgets['energy'],
            self.widgets['power']
        ])
        
        dashboard = widgets.VBox([
            widgets.HTML('<h3>⚡ 实时能源监控看板</h3>'),
            battery_box,
            widgets.HBox([temp_box, stats_box]),
            self.widgets['process_list']
        ])
        
        return dashboard
    
    def update(self):
        """更新仪表板数据"""
        # 电池
        battery = self.monitor.get_battery_status()
        if battery:
            self.widgets['battery'].value = battery.percent
            self.widgets['battery_text'].value = f"{battery.percent:.1f}%"
            
            if battery.percent < 20:
                self.widgets['battery'].bar_style = 'danger'
            elif battery.percent < 50:
                self.widgets['battery'].bar_style = 'warning'
            else:
                self.widgets['battery'].bar_style = 'success'
        
        # 温度
        temps = self.monitor.get_system_temperature()
        if temps.cpu_temp:
            self.widgets['cpu_temp'].value = f"CPU: {temps.cpu_temp:.1f}°C"
        if temps.gpu_temp:
            self.widgets['gpu_temp'].value = f"GPU: {temps.gpu_temp:.1f}°C"
        
        # 能耗
        self.widgets['energy'].value = f"累计能耗: {self.monitor.total_energy_joules:.4f} J"
        
        # 进程
        processes = self.monitor.get_process_energy()
        process_text = "进程能耗排行 (Top 10):\n" + "-" * 40 + "\n"
        for i, p in enumerate(processes[:10], 1):
            process_text += f"{i}. {p.name[:20]:20s} {p.energy_estimate*1000:8.4f} mJ\n"
        self.widgets['process_list'].value = process_text
    
    def start_auto_update(self, interval: float = 2.0):
        """开始自动更新"""
        self.running = True
        
        def update_loop():
            while self.running:
                try:
                    self.update()
                    time.sleep(interval)
                except:
                    break
        
        self.update_thread = threading.Thread(target=update_loop)
        self.update_thread.daemon = True
        self.update_thread.start()
    
    def stop_auto_update(self):
        """停止自动更新"""
        self.running = False


# =============================================================================
# 批量对比分析函数
# =============================================================================

def run_comprehensive_memory_analysis(analyzer: MemoryEnergyAnalyzer) -> Dict[str, Any]:
    """
    运行全面的内存访问模式能源分析
    """
    print("="*70)
    print("开始全面内存访问模式能源分析")
    print("="*70)
    
    results = {}
    
    # 1. GPU vs CPU内存访问
    print("\n[1/7] 分析GPU与CPU内存访问差异...")
    results['gpu_cpu_comparison'] = analyzer.analyze_gpu_cpu_memory_access(
        data_size_bytes=100*1024*1024,  # 100MB
        access_pattern='sequential',
        iterations=10000,
        use_unified_memory=False
    )
    print(f"  CPU能耗: {results['gpu_cpu_comparison']['cpu']['energy_joules']:.6f} J")
    if 'gpu' in results['gpu_cpu_comparison'] and 'energy_joules' in results['gpu_cpu_comparison']['gpu']:
        print(f"  GPU能耗: {results['gpu_cpu_comparison']['gpu']['energy_joules']:.6f} J")
    
    # 2. 缓存友好性分析
    print("\n[2/7] 分析缓存友好性...")
    results['cache_analysis'] = analyzer.analyze_cache_friendliness(
        array_size=1000000,
        element_size=8
    )
    print(results['cache_analysis'].to_string(index=False))
    
    # 3. 统一内存 vs 分离内存
    print("\n[3/7] 对比统一内存与分离内存...")
    results['memory_architecture'] = analyzer.analyze_unified_vs_separated_memory(
        data_size_bytes=50*1024*1024,
        access_ratio_cpu=0.3,
        migration_frequency=100
    )
    print(f"  统一内存能耗: {results['memory_architecture']['unified_memory']['total_energy_joules']:.6f} J")
    print(f"  分离内存能耗: {results['memory_architecture']['separated_memory']['total_energy_joules']:.6f} J")
    print(f"  建议: {results['memory_architecture']['recommendation']}")
    
    # 4. 数据驻留策略
    print("\n[4/7] 分析数据驻留策略...")
    strategies = ['on_demand', 'prefetch', 'pinned', 'duplicate']
    results['residency_strategies'] = []
    for strategy in strategies:
        res = analyzer.analyze_data_residency_strategy(
            data_size_bytes=100*1024*1024,
            cpu_access_frequency=1000,
            gpu_access_frequency=5000,
            strategy=strategy
        )
        results['residency_strategies'].append(res)
        print(f"  {strategy}: {res['estimated_energy_joules_per_second']:.6f} J/s")
    
    # 5. 时间局部性分析
    print("\n[5/7] 分析时间局部性...")
    # 生成测试访问序列
    sequential_access = list(range(10000))
    random_access = np.random.randint(0, 10000, 10000).tolist()
    
    results['temporal_locality'] = {
        'sequential': analyzer.analyze_temporal_locality(sequential_access),
        'random': analyzer.analyze_temporal_locality(random_access)
    }
    print(f"  顺序访问局部性评分: {results['temporal_locality']['sequential']['temporal_locality_score']:.3f}")
    print(f"  随机访问局部性评分: {results['temporal_locality']['random']['temporal_locality_score']:.3f}")
    
    # 6. 堆分配 vs 栈分配
    print("\n[6/7] 对比堆分配与栈分配...")
    results['allocation_comparison'] = analyzer.analyze_heap_vs_stack(
        allocation_size=1024,  # 1KB
        allocation_count=10000,
        lifetime_seconds=0.001
    )
    print(f"  堆分配能耗: {results['allocation_comparison']['heap']['allocation_energy_joules']:.8f} J")
    print(f"  栈分配能耗: {results['allocation_comparison']['stack']['allocation_energy_joules']:.8f} J")
    print(f"  能耗比(堆/栈): {results['allocation_comparison']['comparison']['heap_to_stack_energy_ratio']:.2f}x")
    
    # 7. 内存池 vs 每次分配
    print("\n[7/7] 对比内存池与每次分配...")
    results['pool_comparison'] = analyzer.analyze_memory_pool_vs_per_allocation(
        object_size=256,
        total_objects=100000,
        peak_concurrent_objects=5000,
        allocation_pattern='burst'
    )
    print(f"  内存池能耗: {results['pool_comparison']['memory_pool']['total_energy_joules']:.6f} J")
    print(f"  每次分配能耗: {results['pool_comparison']['per_allocation']['total_energy_joules']:.6f} J")
    print(f"  使用内存池节省: {results['pool_comparison']['comparison']['energy_savings_percent']:.1f}%")
    
    print("\n" + "="*70)
    print("分析完成！")
    print("="*70)
    
    return results


def visualize_memory_analysis_results(results: Dict[str, Any], figsize=(16, 12)):
    """
    可视化内存分析结果
    """
    fig, axes = plt.subplots(2, 3, figsize=figsize)
    
    # 1. GPU vs CPU能耗对比
    ax = axes[0, 0]
    if 'gpu_cpu_comparison' in results and 'cpu' in results['gpu_cpu_comparison']:
        cpu_energy = results['gpu_cpu_comparison']['cpu']['energy_joules']
        gpu_energy = results['gpu_cpu_comparison']['gpu'].get('energy_joules', 0)
        
        bars = ax.bar(['CPU', 'GPU'], [cpu_energy, gpu_energy], 
                      color=['#3498db', '#e74c3c'])
        ax.set_ylabel('Energy (Joules)')
        ax.set_title('GPU vs CPU Memory Access Energy')
        for bar in bars:
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                   f'{height:.2e}',
                   ha='center', va='bottom', fontsize=9)
    
    # 2. 缓存友好性分析
    ax = axes[0, 1]
    if 'cache_analysis' in results:
        df = results['cache_analysis']
        ax.barh(df['pattern'], df['energy_joules'], 
                color=['#2ecc71' if cf else '#e74c3c' 
                       for cf in df['cache_friendly']])
        ax.set_xlabel('Energy (Joules)')
        ax.set_title('Cache Friendliness vs Energy')
    
    # 3. 统一内存 vs 分离内存
    ax = axes[0, 2]
    if 'memory_architecture' in results:
        unified = results['memory_architecture']['unified_memory']['total_energy_joules']
        separated = results['memory_architecture']['separated_memory']['total_energy_joules']
        bars = ax.bar(['Unified', 'Separated'], [unified, separated],
                     color=['#9b59b6', '#f39c12'])
        ax.set_ylabel('Energy (Joules)')
        ax.set_title('Unified vs Separated Memory')
    
    # 4. 数据驻留策略
    ax = axes[1, 0]
    if 'residency_strategies' in results:
        strategies = [r['strategy'] for r in results['residency_strategies']]
        energies = [r['estimated_energy_joules_per_second'] for r in results['residency_strategies']]
        ax.bar(strategies, energies, color='#1abc9c')
        ax.set_ylabel('Energy (J/s)')
        ax.set_title('Data Residency Strategy Comparison')
        ax.tick_params(axis='x', rotation=45)
    
    # 5. 堆 vs 栈分配
    ax = axes[1, 1]
    if 'allocation_comparison' in results:
        heap = results['allocation_comparison']['heap']['allocation_energy_joules']
        stack = results['allocation_comparison']['stack']['allocation_energy_joules']
        bars = ax.bar(['Heap', 'Stack'], [heap, stack],
                     color=['#e67e22', '#16a085'])
        ax.set_ylabel('Energy (Joules)')
        ax.set_title('Heap vs Stack Allocation')
    
    # 6. 内存池 vs 每次分配
    ax = axes[1, 2]
    if 'pool_comparison' in results:
        pool = results['pool_comparison']['memory_pool']['total_energy_joules']
        per_alloc = results['pool_comparison']['per_allocation']['total_energy_joules']
        bars = ax.bar(['Memory Pool', 'Per-allocation'], [pool, per_alloc],
                     color=['#27ae60', '#c0392b'])
        ax.set_ylabel('Energy (Joules)')
        ax.set_title('Memory Pool vs Per-allocation')
    
    plt.tight_layout()
    plt.suptitle('Memory Access Pattern Energy Analysis', fontsize=16, y=1.02)
    plt.show()


# =============================================================================
# 便捷使用函数
# =============================================================================

def create_analyzer(data_dir: Optional[str] = None) -> MemoryEnergyAnalyzer:
    """创建分析器实例（便捷函数）"""
    return MemoryEnergyAnalyzer(data_dir=data_dir)


def create_monitor(analyzer: Optional[MemoryEnergyAnalyzer] = None) -> RealTimeEnergyMonitor:
    """创建监控器实例（便捷函数）"""
    if analyzer is None:
        analyzer = create_analyzer()
    return RealTimeEnergyMonitor(analyzer)


def create_dashboard(monitor: RealTimeEnergyMonitor) -> EnergyDashboard:
    """创建仪表板实例（便捷函数）"""
    return EnergyDashboard(monitor)


# 模块版本
__version__ = '1.0.0'
__all__ = [
    'MemoryEnergyAnalyzer',
    'RealTimeEnergyMonitor', 
    'EnergyDashboard',
    'BatteryStatus',
    'SystemTemperature',
    'ProcessEnergy',
    'MemoryAccessPattern',
    'run_comprehensive_memory_analysis',
    'visualize_memory_analysis_results',
    'create_analyzer',
    'create_monitor',
    'create_dashboard'
]
