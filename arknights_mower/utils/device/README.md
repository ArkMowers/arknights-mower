# 设备控制实现导航

本目录负责一个明确绑定的设备实例及其外部 I/O。调用者从 [DeviceControl](application.py) 获取结果；游戏操作通过 [Device](device.py) 使用截图和输入能力。完整行为要求见[设备控制规范](../../../docs/subsystems/device-control.md)。

| 责任 | 实现入口 | 定向回归 |
| :--- | :--- | :--- |
| 应用边界、启动、取消与关闭 | [application.py](application.py) | [device_application_tests.py](../../tests/device_application_tests.py)、[关闭回归](../../tests/device_control_shutdown_tests.py) |
| 会话观察、实例绑定与恢复决策 | [session.py](session.py)、[recovery.py](recovery.py) | [device_session_tests.py](../../tests/device_session_tests.py)、[调用者回归](../../tests/device_session_caller_tests.py) |
| 生产 ADB、模拟器及有限预算 I/O | [session_io.py](session_io.py)、[manager_io.py](manager_io.py)、[io_budget.py](io_budget.py) | [会话 I/O 回归](../../tests/device_session_io_tests.py)、[预算回归](../../tests/device_io_budget_tests.py) |
| 准备与独立连接检查 | [preparation.py](preparation.py)、[preflight.py](preflight.py) | [准备回归](../../tests/device_preparation_tests.py)、[preflight 回归](../../tests/device_preflight_tests.py) |
| 截图与输入后端的选择和操作 | [device.py](device.py)、[screenshot_backend.py](screenshot_backend.py)、[touch_backend.py](touch_backend.py) | [截图回归](../../tests/device_screenshot_backend_tests.py)、[输入回归](../../tests/device_touch_tests.py) |

平台适配涉及发现、实例身份、管理命令和会话 I/O。新增平台或预设从[添加模拟器预设](../../../docs/cookbook/adding-simulator-preset.md)开始；排查现有行为从[设备故障排查](../../../docs/cookbook/device-troubleshooting.md)开始。

本目录的修改入口规则见 [AGENTS.md](AGENTS.md)，测试执行方式见[测试导航](../../tests/README.md)。
