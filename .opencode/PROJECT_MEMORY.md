# arknights-mower v5 重构项目记忆

> 基线: `4.1.6` | 分支: `redesign` | 最后更新: 2026-05-07

## 架构总览

```
scheduler/                    ← 新世界, 纯 Python, 跨平台
├── domain/                   ← 纯数据类 + 派生属性
│   ├── operators.py          Operator + Dormitory + OperatorType + RestPriority
│   ├── task.py               SchedulerTask + TaskTypes
│   └── plan.py               PlanConfig + Room + Plan + BaseProduct
├── state.py                  SchedulerState
├── queue.py                  TaskQueue (heapq, 待加优先级窗口排序)
├── dispatch.py               TaskDispatch (DeviceError → reconnect → retry ×3)
├── device_port.py            DevicePort ABC (tap/swipe/screencap/reconnect)
├── graph.py                  SceneGraph + build_default_graph() (88 transitions)
├── navigator.py              Navigator (45 action handlers)
├── scene.py                  Scene IntEnum (151 scenes)
├── loop.py                   MainLoop (planner 轮询 + 任务调度)
├── errors.py                 6 exception classes
├── constants.py              游戏常量 + Workshop/AgentSelection 常量
├── bootstrap.py              生产入口: 初始化 Device/Recognizer/Navigator/AgentSelection
├── infra/
│   ├── __init__.py           InfraKit dataclass
│   ├── pc_device_port.py     DevicePort 实现 (包装 v1 Device)
│   ├── agent_selection.py    AgentSelection FSM (752 行)
│   ├── pause_controller.py   ABC
│   ├── thread_pause.py       Threading 实现
│   └── registry.py           STUB
├── planners/                 10 planners (3 新接口 + 6 旧接口 + 2 stub)
├── executors/                9 executors (workshop 迁移中, 8 stub)
├── services/                 plan_service + task_service
├── copilot/                  基础框架 (executor/loader 部分 stub)
└── database/                 sqlite + repositories (stub 居多)

utils/recognize/              拆分后的识别层
└── __init__.py               Recognizer (find() 策略 dispatch)
```

## 关键设计决策 (更新到当前)

1. **Data Class vs Service**: domain 只放派生属性, 业务逻辑移 service
2. **三层调度**: Planner(计划) → Dispatch(分发+重连) → Executor(执行+FSM)
3. **优先级抢占在 TaskQueue.pop()**: 出队时检查时间窗口内的优先级
4. **重连在 DevicePort 层**: executor 不处理, Dispatch 只调 device.reconnect()
5. **screencap 自愈 + tap/swipe 快速失败**: screencap while True 自恢复, tap/swipe 抛 DeviceError
6. **InfraKit**: dataclass 装 device/navigator/agent_selector/pause, bootsrap 构造, executor 共用
7. **AbstractExecutor 只收 InfraKit**: 不依赖具体平台实现
8. **Planner 无状态轮询**: frequency + condition + make_task
9. **跨平台 DevicePort.reconnect()**: 各平台自己实现

## InfraKit 架构

```python
@dataclass
class InfraKit:
    device: DevicePort
    navigator: Navigator       # navigation + scene dispatch
    agent_selector: AgentSelection  # agent arrangement FSM
    pause: PauseController

class AbstractExecutor(ABC):
    def __init__(self, infra: InfraKit):
        self.infra = infra
    # executors 通过 self.infra.xxx 访问所有基础设施
```

Bootstrap 组装:
```
v1 Device → PCDevicePort + Recognizer
                    ↓
              InfraKit(device, navigator, agent_selector)
                    ↓
              MainLoop(state, planners, dispatch, infra)
                    ↓
              dispatch.execute(task, infra)
                    ↓
              executor_cls(infra).execute(task)
```

## 已完成的迁移

| 模块 | 状态 | 说明 |
|------|------|------|
| DevicePort | ✅ | ABC + PCDevicePort + reconnect |
| Dispatch | ✅ | DeviceError retry ×3 |
| MainLoop | ✅ | Planner 轮询 + 任务调度 |
| Bootstrap | ✅ | 生产入口, InfraKit 组装 |
| WorkshopPlanner | ✅ | 库存检查 + 条件判断 |
| WorkshopExecutor | 🔶 FSM 骨架 | 导航/选人/加工流程连上, 缺完整 item_list 扫描 |
| AgentSelection | ✅ | 752 行 FSM (bug 已修) |
| Navigator | ✅ | 45 个 action handlers |

## 未完成 (Stub/待迁移)

### Executor (8 个 stub, 全需从 base_schedule.py 迁移)

| Executor | 状态 | 对应 v1 方法 |
|----------|------|-------------|
| shift.py | 🔶 stub | `infra_main()` 换班逻辑 |
| clue.py | 🔶 stub | `clue_new()` |
| run_order.py | 🔶 stub | `run_order_solver()` |
| exhaust.py | 🔶 stub | 用尽下班 |
| fiammetta.py | 🔶 stub | 菲亚梅塔阈值 |
| correction.py | 🔶 stub | 纠错 |
| skill.py | 🔶 stub | 技能专精 |

### Planner (需改成 AbstractPlanner 接口)

| Planner | 问题 |
|---------|------|
| ShiftPlanner | 旧接口, 不继承 AbstractPlanner |
| ExhaustPlanner | 同上 |
| FiammettaPlanner | 同上 |
| OrderPlanner | 同上 |
| IdlePlanner | 同上 |
| BackupPlanner | 同上 |
| CluePlanner | 🔶 stub |
| SkillPlanner | 🔶 stub |

### Infra
- `infra/registry.py` — STUB, 0 方法
- `hooks.py` — STUB, 空 LifecycleHook
- Navigator 的 `_tap()` 用硬编码 1920/1080, 应改为 SCREEN_W/SCREEN_H
- AgentSelection 有 5 处硬编码坐标

### Database
- `database/errors.py` — 只有通用 DatabaseError

## 下次 Pickup

### 🔴 当前阻塞项

1. **实机测试 WorkshopExecutor** — 需要验证 Navigator + AgentSelection 在实际设备上的表现
2. **FORMULA_SCAN state** — Workshop FSM 还缺少真正的 item_list 扫描逻辑 (从 v1 `generate_product` 迁移)
3. **TaskQueue 优先级窗口排序** — 实现类似 v1 `scheduling()` 的 pop 优先级逻辑

### 后续路线

1. 修完 Workshop 使其能跑通一次完整加工任务
2. ShiftExecutor (核心换班, 最常用)
3. 剩余 6 个 executor 逐个迁移
4. Planner 全部改为 AbstractPlanner 接口
5. 归档持久化 (存档恢复)
6. Email 通知 + MAA 集成 (作为 planner 任务)
