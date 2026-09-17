"""`run_steps()` 队列模式的数据载体与控制流异常。

这三个符号原先定义在 `scheduler/executors/base.py`，但它们描述的是
**步骤队列本身的结构**，与执行器无关：

- `services/agent_swap_service.py` 需要 `Step`，于是产生了
  `services/ → executors/` 的**层级倒挂**（服务层不该依赖执行器层）。
- `executors/base.py` 因此只是"恰好先写了"的存放点，而不是语义归属。

本模块把它们下沉到 `scheduler/` 顶层，使执行器层与服务层可以**平级**引用。
`executors/base.py` 保留一行兼容再导出，既有 import 方无需改动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional


class StepRetry(Exception):
    """当前步骤原地重试：队列不推进，下一轮循环重新求值当前 `Step`。"""


class StepRestart(Exception):
    """整个队列从头开始：丢弃已完成的进度，回到初始 `steps` 列表。"""


@dataclass
class Step:
    """线性流程的一个步骤。

    `name` 仅用于日志；`enter(scene)` 判断当前场景是否满足本步骤的前置条件；
    `act()` 执行动作并可返回**追加步骤**（`None` 表示不追加）；
    `start` 为期望起始场景，不匹配时 `run_steps` 会先 `navigate(start)`。
    """

    name: str
    enter: Callable[[int], bool]
    act: Callable[[], Optional[list[Step]]] = field(default=lambda: None)
    start: int | None = None
