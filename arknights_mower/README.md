# Mower 后端源码地图

后端把 Web 请求和配置转换为设备操作与游戏任务。开发环境与产品使用见[项目首页](../README.md)；Python 修改约束见 [AGENTS.md](AGENTS.md)。

| 责任 | 实现入口 | 下一步 |
| :--- | :--- | :--- |
| HTTP 服务、任务控制与功能路由 | [server.py](../server.py)、[views/](views/) | [系统架构](../docs/architecture.md)、[前端开发](../ui/README.md) |
| 运行初始化与调度器装配 | [__main__.py](__main__.py) 的 `main`、`initialize` | [solver 导航](solvers/README.md) |
| 游戏任务与基建调度 | [solvers/](solvers/) | [基建调度规范](../docs/subsystems/base-scheduler.md) |
| 设备控制、会话与平台适配 | [DeviceControl](utils/device/application.py)、[device/](utils/device/README.md) | [设备控制规范](../docs/subsystems/device-control.md) |
| 配置模型与运行状态 | [utils/config/](utils/config/)、[Operators](utils/operators.py) | [领域定义](../CONTEXT.md)、相关子系统说明 |
| 离线行为验证 | [tests/](tests/README.md) | 按改动行为选择定向测试 |

处理故障时先找到外部调用者，再跟到拥有状态或副作用的模块。目录地图用于定位；具体返回值、失败处理和持久化保证仍由所属子系统说明定义。
