# Step 2: Graph / Navigation

> 估算: 2-3 天

## 目标

把当前 `utils/graph.py`(497 行, 继承 BaseSolver) 重写为纯 SceneGraph + Navigator, 解耦导航逻辑和设备操作。

## 当前问题

- `@edge` 装饰器定义 transition, 回调函数依赖 `BaseSolver` (`solver.tap()`, `solver.find()`)
- 导航逻辑和点击逻辑在一个类里
- 无法脱离模拟器测试

## 新架构

```
scheduler/graph.py          SceneGraph (纯数据)
scheduler/navigator.py      Navigator (依赖 DevicePort + Recognizer)
```

### SceneGraph — 纯数据

```python
# scheduler/graph.py
@dataclass
class SceneTransition:
    target: Scene
    action: str          # symbolic action name, 由 Navigator 解析执行
    weight: float = 1.0  # 路径搜索权重

class SceneGraph:
    """有向图, 每个节点是一个 Scene, 每条边是一个 Transition"""

    def __init__(self):
        self._graph = nx.DiGraph()

    def add_transition(self, from_scene: Scene, to_scene: Scene,
                       action: str, weight: float = 1.0):
        self._graph.add_edge(from_scene, to_scene,
                             action=action, weight=weight)

    def find_path(self, current: Scene, target: Scene) -> list[SceneTransition]:
        """networkx 最短路径 → list of transitions"""
        ...

    def can_reach(self, current: Scene, target: Scene) -> bool:
        """是否存在路径"""
        ...

    # 装饰器风格的注册接口 (可选)
    def transition(self, from_scene: Scene, to_scene: Scene, weight: float = 1.0):
        def decorator(action_fn):
            self.add_transition(from_scene, to_scene, action_fn.__name__, weight)
            return action_fn
        return decorator
```

### Navigator — 执行层

```python
# scheduler/navigator.py
class Navigator:
    def __init__(self, device: DevicePort, graph: SceneGraph,
                 recognizer: Recognizer):
        self._device = device
        self._graph = graph
        self._recognizer = recognizer

    def navigate(self, target: Scene) -> bool:
        """从当前场景导航到目标场景"""
        current = self._recognizer.get_scene()
        path = self._graph.find_path(current, target)
        if path is None:
            return False
        for transition in path:
            self._execute(transition)
        return True

    def _execute(self, transition: SceneTransition):
        """通过 action 名分发到具体处理函数"""
        handler = getattr(self, f'_action_{transition.action}')
        handler()

    # ===== action handlers =====
    # 从旧 graph.py 的 @edge 函数迁入, 但改为调用 DevicePort + Recognizer

    def _action_back_to_index(self):
        """从任意页返回首页"""
        self._device.tap(...)  # 按场景裁剪不同的返回操作

    def _action_index_to_infra(self):
        """首页 → 基建"""
        self._device.tap(1410/1920, 870/1080)  # 比例坐标

    # ... 其余 ~50 个 action handlers
```

### 迁移策略

旧 `utils/graph.py` 保留不动, `scheduler/graph.py` + `scheduler/navigator.py` 新建:

1. 把 `Scene` 枚举迁入 `scheduler/constants.py`
2. 重写 `SceneGraph`, 支持 `add_transition` + `find_path`
3. 重写 `Navigator`, 从旧 `@edge` 函数逐条 copy action handler, 改为比例坐标
4. 截图回放对比: 旧 graph + BaseSolver vs 新 Navigator + DevicePort, 输入相同场景序列, 输出相同 tap 序列

### 坐标约定

Navigator action handler 中的比例坐标写入 `scheduler/constants.py` 作为具名常量，禁止手写 `1410/1920` 表达式：

```python
# constants.py
NAV_INDEX_TO_INFRA = (1410 / 1920, 870 / 1080)

# navigator.py
self._device.tap(*NAV_INDEX_TO_INFRA)
```

### 旧 utils 依赖

Step 2 中，新建的 SceneGraph 是纯数据类，不依赖 utils。Navigator 可以依赖：
- `scheduler/device_port.py` — DevicePort 抽象
- `utils/recognize.py` — Recognizer (过渡期允许，Step 3 再清理)
- `utils/scene.py` — Scene 枚举 (迁入 constants.py 后替换)

### 后续集成

Step 5 (Full Chain) 时, 将 `Navigator` 注入 `MainLoop`, 替换旧 `graph.py` 的调用点。

## 验证

- 单元测试: SceneGraph.find_path(Scene.A, Scene.B) → 返回正确路径
- 截图回放: 50+ 场景迁移路径, 新旧输出一致
- 手动测试: 从任意页面导航到基建/招募/仓库/邮件
