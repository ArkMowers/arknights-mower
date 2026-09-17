"""换班服务的编排入口 —— `AgentSwapService`。

按职责拆分后的结构（AGENTS.md：一个 class 一个文件、每个文件 ≤300 行）：

| 文件 | 职责 |
|---|---|
| `agent_swap_errors.py` | `AgentSwapError`（失败信号）+ 去重前置 |
| `agent_swap_base.py` | 依赖注入、步骤队列循环、设备/识别原语 |
| `agent_swap_arrange.py` | 排序方向与职介筛选原语 |
| `agent_swap_scan.py` | 面板扫描、翻页、**末尾检测（BUG-3）** |
| `agent_swap_filter.py` | **自由人空闲判定**、候选筛选、排序/筛选目标 |
| `agent_swap_select.py` | 选人决策与落位（`_do_select`/`_do_sort`） |
| `agent_swap_train.py` | 训练位专用流程 `_run_train` |

拆分是**行为保持型重构**：同一 mock 场景下的 tap/swipe 序列必须逐字一致。

**BUG-2 / BUG-3**（翻到底静默返回）见 `agent_swap_scan.py`。
"""

from __future__ import annotations

from typing import Optional

from arknights_mower.scheduler.services.agent_swap_arrange import AgentSwapArrangeMixin
from arknights_mower.scheduler.services.agent_swap_base import AgentSwapBase
from arknights_mower.scheduler.services.agent_swap_errors import (
    AgentSwapError,
    dedup_agents,
)
from arknights_mower.scheduler.services.agent_swap_filter import AgentSwapFilterMixin
from arknights_mower.scheduler.services.agent_swap_scan import AgentSwapScanMixin
from arknights_mower.scheduler.services.agent_swap_select import AgentSwapSelectMixin
from arknights_mower.scheduler.services.agent_swap_train import AgentSwapTrainMixin
from arknights_mower.scheduler.steps import Step
from arknights_mower.utils.log import logger

__all__ = ["AgentSwapError", "AgentSwapService"]


class AgentSwapService(
    AgentSwapBase,
    AgentSwapArrangeMixin,
    AgentSwapScanMixin,
    AgentSwapFilterMixin,
    AgentSwapSelectMixin,
    AgentSwapTrainMixin,
):
    """把"房间该有哪些干员"落成实际点击。

    构造签名由 `AgentSwapBase.__init__` 提供（含 `state` 注入点）。
    """

    def run(
        self,
        room: str,
        agents: list[str],
        *,
        train_index: int = 0,
        current_operators: Optional[list[str]] = None,
    ) -> bool:
        logger.info(f"AgentSwap: {room} target={agents}")
        if room == "train":
            return self._run_train(agents, train_index)

        self._room = room
        self._is_dorm = room.startswith("dorm")
        self._is_production = room.startswith("room")

        agents = dedup_agents(agents)
        logger.info(f"AgentSwap: after dedup {agents}")
        self._agents = agents

        self._to_uncheck = []
        if current_operators:
            for i, cur in enumerate(current_operators):
                if cur and cur not in agents:
                    self._to_uncheck.append(i)
            logger.info(
                f"AgentSwap: current room={current_operators}, "
                f"uncheck slots={self._to_uncheck}"
            )
            if (
                not self._to_uncheck
                and len(current_operators) >= len(agents)
                and all(
                    current_operators[i] == agents[i] for i in range(len(agents))
                )
            ):
                logger.info("AgentSwap: room already correct, skip")
                return True
        self._pending = [a for a in agents if a != "Free"]
        self._free_count = agents.count("Free")
        self._selected: list[str] = []
        if current_operators:
            for i in range(len(current_operators)):
                if i not in self._to_uncheck and current_operators[i] in self._pending:
                    self._pending.remove(current_operators[i])
                    self._selected.append(current_operators[i])
                    logger.info(
                        f"AgentSwap: skip {current_operators[i]}, already in slot {i}"
                    )
        self._last_filter = "ALL"
        self._page_count = 0
        self._last_names: Optional[list[str]] = None
        self._cache: list = []
        self._found_target = False

        steps: list[Step] = []
        if self._to_uncheck:
            steps.append(Step("uncheck", self._scene_check, self._do_uncheck))
        steps.append(Step("prepare", self._scene_check, self._do_prepare))

        return self._run_steps(steps)
