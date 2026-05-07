# Step 1: Architecture Redesign

> 估算: 2-3 天

## 目标

建好新世界骨架: 领域类型 + DevicePort 抽象 + 状态机规范。旧代码不动, 新代码可独立开发和测试。

## 交付物

```
scheduler/
├── __init__.py
├── errors.py              # 领域异常
├── state.py               # SchedulerState @dataclass
├── queue.py               # TaskQueue (push/pop/peek/find/remove)
├── dispatch.py            # TaskDispatch (type → executor)
├── device_port.py         # DevicePort ABC (新代码唯一 Device 依赖)
│
├── domain/
│   ├── __init__.py
│   ├── task.py            # SchedulerTask + TaskTypes (从 utils/ 迁入)
│   ├── operators.py       # Operator + Dormitory 纯数据类 (从 utils/ 迁入)
│   │                      # Operators (1127行业务逻辑类) 留 utils/ 等 Step 4
│   └── plan.py            # PlanConfig + Room + Plan (从 utils/ 迁入)
│
├── planners/
│   └── base.py            # AbstractPlanner (接口)
│
├── executors/
│   └── base.py            # AbstractExecutor (模板方法)
│
└── constants.py           # 枚举 + UI 坐标常量
```

## 关键设计

### DevicePort

`scheduler/device_port.py` — 新代码唯一依赖的设备抽象:

```python
class DevicePort(ABC):
    @abstractmethod
    def tap(self, x: float, y: float) -> None: ...
    @abstractmethod
    def swipe(self, x1: float, y1: float, x2: float, y2: float, duration: int = 100) -> None: ...
    @abstractmethod
    def screencap(self) -> np.ndarray: ...
    @abstractmethod
    def launch(self) -> None: ...
    @abstractmethod
    def exit(self) -> None: ...
    @abstractmethod
    def check_focus(self) -> bool: ...
```

PC 实现包装 `utils/device/Device`, Android 实现用 MediaProjection + AccessibilityService。

### 状态机规范

所有 UI 交互操作必须用显式状态机, 禁止 while+flag:

```python
# 好的: State enum + method dispatch
class AgentSelection:
    state: SelectionState
    def run(self):
        while self.state != SelectionState.DONE:
            handler = getattr(self, f'_state_{self.state.name}')
            self.state = handler()

# 也接受: @TransitionOn 装饰器模式 (scene dispatch)
@TransitionOn(Scene.INFRA_ARRANGE)
def on_arrange(self): ...
```

### SchedulerState

不引用 `utils.operators.Operators` 或 `utils.config.conf`，保持新代码零依赖旧 utils：

```python
@dataclass
class SchedulerState:
    operators: dict[str, Operator]   # 新 domain 的 Operator 纯数据类
    dormitories: list[Dormitory]
    queue: TaskQueue
    config: PlanConfig                # 新 domain 的 PlanConfig
    planned: bool = False
    error: bool = False
    # ... 运行时状态字段
```

## 允许的旧代码改动

此步不改任何旧代码。

## 验证

- `pytest` 单元测试通过 state/queue/dispatch
- `from scheduler.device_port import DevicePort` 可 import
- `from scheduler.domain.task import SchedulerTask` 可 import
