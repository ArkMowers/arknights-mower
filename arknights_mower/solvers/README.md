# 游戏任务与调度实现

这里包含具体游戏任务和基建调度。运行装配从 [__main__.py](../__main__.py) 进入；公共场景导航由 [SceneGraphSolver](../utils/graph.py) 提供。

| 修改对象 | 源码入口 | 规则说明或验证入口 |
| :--- | :--- | :--- |
| 排班计划、执行顺序、状态提交与恢复 | [BaseSchedulerSolver](base_schedule.py) | [基建调度规范](../../docs/subsystems/base-scheduler.md)、[调度回归](../tests/base_scheduler_tests.py) |
| 基建页面上的干员选择与房间操作 | [BaseMixin](base_mixin.py) 及其实际 solver 调用者 | [调度回归](../tests/base_scheduler_tests.py)；按修改方法选择测试 |
| 专精状态读取与支持干员操作 | [mastery.py](mastery.py)、[mastery_reader.py](mastery_reader.py)、[mastery_support_runtime.py](mastery_support_runtime.py) | [基建调度规范](../../docs/subsystems/base-scheduler.md)、[测试导航](../tests/README.md) |
| 自动作战 | [OperationSolver](operation.py) | [本地作战规范](../../docs/subsystems/local-operation.md) |
| 场景转换与页面识别 | [navigation.py](navigation.py)、[公共场景图](../utils/graph.py) | [系统架构](../../docs/architecture.md)、[测试导航](../tests/README.md) |

排班问题还需要跟到 [Operators](../utils/operators.py)、[计划模型](../utils/plan.py) 和[调度任务](../utils/scheduler_task.py)。通过所属子系统说明确认 Actual Occupancy 与 Projected Occupancy 的边界，再检查实际调用链中的状态变化。

本目录继承[后端约束](../AGENTS.md)。定向离线测试从仓库根目录运行；测试结果的范围见[测试导航](../tests/README.md)。
