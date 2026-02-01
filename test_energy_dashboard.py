#!/usr/bin/env python3
"""
能耗看板功能测试脚本
验证所有核心功能是否正常工作
"""

import time
import sys

def test_imports():
    """测试依赖导入"""
    print("=" * 60)
    print("测试依赖导入")
    print("=" * 60)
    
    tests = [
        ("psutil", "psutil"),
        ("numpy", "numpy"),
        ("matplotlib", "matplotlib"),
        ("nvidia-ml-py", "pynvml"),
        ("wmi", "wmi"),
        ("ipywidgets", "ipywidgets"),
    ]
    
    for name, module in tests:
        try:
            __import__(module)
            print(f"[OK] {name:20s} - 已安装")
        except ImportError:
            print(f"[SKIP] {name:20s} - 未安装 (可选)")
    
    print()


def test_monitor_basic():
    """测试监控器基础功能"""
    print("=" * 60)
    print("测试监控器基础功能")
    print("=" * 60)
    
    from energy_monitor_dashboard import LightweightEnergyMonitor
    
    monitor = LightweightEnergyMonitor(update_interval=1.0)
    print("[OK] 监控器创建成功")
    
    # 测试功耗读取
    power = monitor.get_current_power()
    print(f"[OK] 功耗读取成功:")
    print(f"  - 总功耗: {power['total_w']:.2f} W")
    print(f"  - CPU: {power['cpu_w']:.2f} W")
    print(f"  - GPU: {power['gpu_w']:.2f} W")
    print(f"  - 内存: {power['memory_w']:.2f} W")
    
    # 测试温度读取
    temps = monitor.get_system_temperature()
    print(f"[OK] 温度读取成功:")
    print(f"  - CPU: {temps.cpu_temp if temps.cpu_temp else '未检测到'}")
    print(f"  - GPU: {temps.gpu_temp if temps.gpu_temp else '未检测到'}")
    
    # 测试进程能耗
    processes = monitor.get_process_energy()
    print(f"[OK] 进程能耗读取成功，获取到 {len(processes)} 个进程")
    
    if processes:
        print("  Top 5 进程:")
        for i, p in enumerate(processes[:5], 1):
            unit = "W" if p.power_mw >= 1000 else "mW"
            value = p.power_mw/1000 if p.power_mw >= 1000 else p.power_mw
            print(f"    {i}. {p.name[:25]:25s} {value:8.2f} {unit}  CPU:{p.cpu_percent:5.1f}%")
    
    print()
    return monitor


def test_monitor_session(monitor):
    """测试监控会话"""
    print("=" * 60)
    print("测试监控会话 (5秒)")
    print("=" * 60)
    
    monitor.start_monitoring()
    print("[OK] 监控已启动")
    
    for i in range(5):
        time.sleep(1)
        power = monitor.get_current_power()
        print(f"  [{i+1}s] 总功耗: {power['total_w']:.2f} W")
    
    monitor.stop_monitoring()
    
    stats = monitor.get_session_stats()
    print(f"[OK] 监控已停止")
    print(f"  会话时长: {stats.get('duration_formatted', '--')}")
    print(f"  累计能耗: {stats.get('total_energy_joules', 0):.3f} J")
    print(f"  平均功耗: {stats.get('avg_power_w', 0):.2f} W")
    print()


def test_battery():
    """测试电池信息"""
    print("=" * 60)
    print("测试电池信息")
    print("=" * 60)
    
    try:
        import psutil
        battery = psutil.sensors_battery()
        if battery:
            print(f"[OK] 电池检测成功:")
            print(f"  - 电量: {battery.percent:.1f}%")
            print(f"  - 电源状态: {'已连接' if battery.power_plugged else '使用电池'}")
            if battery.secsleft != psutil.POWER_TIME_UNLIMITED:
                print(f"  - 预计剩余: {battery.secsleft/60:.1f} 分钟")
        else:
            print("[WARN] 未检测到电池（可能为台式机）")
    except Exception as e:
        print(f"[ERR] 电池读取失败: {e}")
    
    print()


def test_visualization():
    """测试可视化功能"""
    print("=" * 60)
    print("测试可视化功能")
    print("=" * 60)
    
    try:
        from energy_monitor_dashboard import create_monitor, create_dashboard
        
        monitor = create_monitor(update_interval=1.0)
        dashboard = create_dashboard(monitor)
        print("[OK] 看板创建成功")
        print("  使用 dashboard.start_display() 启动终端看板")
        print("  使用 dashboard.stop_display() 停止")
        
        # 快速测试一次渲染
        monitor.start_monitoring()
        time.sleep(1.5)
        
        # 获取统计数据
        stats = monitor.get_session_stats()
        print(f"\n  当前统计:")
        print(f"  - 运行时长: {stats.get('duration_formatted', '--')}")
        print(f"  - 累计能耗: {stats.get('total_energy_joules', 0):.3f} J")
        
        monitor.stop_monitoring()
        
    except Exception as e:
        print(f"[ERR] 可视化测试失败: {e}")
    
    print()


def test_notebook_components():
    """测试 Jupyter 组件（不启动 GUI）"""
    print("=" * 60)
    print("测试 Jupyter 组件")
    print("=" * 60)
    
    try:
        from energy_dashboard_notebook import LightweightEnergyMonitor, MatplotlibEnergyDashboard
        
        monitor = LightweightEnergyMonitor(update_interval=1.0)
        dashboard = MatplotlibEnergyDashboard(monitor)
        print("[OK] MatplotlibDashboard 创建成功")
        
        # 测试图表设置
        dashboard.setup_plot(figsize=(10, 8))
        print("[OK] 图表设置成功")
        
        # 模拟一些数据
        import numpy as np
        for i in range(10):
            power = monitor.get_current_power()
            temps = monitor.get_system_temperature()
            dashboard.timestamps.append(i)
            dashboard.power_total.append(power['total_w'])
            dashboard.power_cpu.append(power['cpu_w'])
            dashboard.temp_cpu.append(temps.cpu_temp or 40 + np.random.random() * 10)
        
        print("[OK] 数据模拟成功")
        
    except Exception as e:
        print(f"[ERR] Jupyter 组件测试失败: {e}")
    
    print()


def print_usage_examples():
    """打印使用示例"""
    print("=" * 60)
    print("使用示例")
    print("=" * 60)
    
    print("""
1. 终端看板（最简单）:
   from energy_monitor_dashboard import quick_monitor
   quick_monitor(60)  # 监控 60 秒

2. Jupyter Notebook:
   from energy_dashboard_notebook import create_jupyter_dashboard
   dashboard, monitor = create_jupyter_dashboard()
   display(dashboard)

3. Matplotlib 实时看板:
   from energy_dashboard_notebook import run_matplotlib_dashboard
   run_matplotlib_dashboard(60)

4. 自定义监控:
   from energy_monitor_dashboard import create_monitor, create_dashboard
   monitor = create_monitor(update_interval=1.0)
   dashboard = create_dashboard(monitor)
   monitor.start_monitoring()
   dashboard.start_display()
   # ... 运行一段时间 ...
   dashboard.stop_display()
   monitor.stop_monitoring()
""")


def main():
    """主测试函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "能耗看板功能测试" + " " * 27 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    test_imports()
    
    try:
        monitor = test_monitor_basic()
        test_monitor_session(monitor)
        test_battery()
        test_visualization()
        test_notebook_components()
        print_usage_examples()
        
        print("=" * 60)
        print("所有测试完成！")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
