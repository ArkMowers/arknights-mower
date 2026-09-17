"""换班服务的候选筛选与排序/筛选目标推导。

对应拆分前的 `_get_target_sort`、`_get_target_filter`、
`_find_in_cache` / `_find_free_in_cache`（**已删**，见下）与 free 分支的入选判断。

## 自由人（Free）补位的入选判据 —— 裁定 14

重构前的 free 分支写成：

    if name not in self._agent_list or name in self._selected:
        continue

而 `_agent_list` 是**全体干员名集合**，面板上的名字几乎都命中它 ——
该条件几乎恒为 `False`，**等于没有筛选**。真正的空闲判定因此缺失。

对齐 legacy `solvers/base_schedule.py:2681` 的 `get_free_list`：

    free_list = [v.name for k, v in self.op_data.operators.items()
                 if v.name not in agents
                 and v.operator_type != "high"
                 and v.current_room == ""]        # ← 注意：这是**入选**条件

**`current_room == ""`（空闲、不在任何房间）恰恰是自由人的定义。**
⚠️ 方向不可反：要**排除**的是 `current_room != ""`（已在别处工作）的干员，
以及 `config.free_blacklist` 内的干员 —— 不是排除空闲的人。

因此 `SchedulerState` 的注入是**必需的**：只有它同时持有
`operators[name].current_room` 与 `config.free_blacklist`。
"""

from __future__ import annotations

from arknights_mower.scheduler.constants import (
    DEFAULT_FILTER,
    DEFAULT_SORT,
    DORM_SORT,
    SPECIAL_AGENT_ALL_FILTER,
)
from arknights_mower.utils.log import logger


class AgentSwapFilterMixin:
    """候选筛选与"该用哪个排序/筛选"的推导。"""

    # ------------------------------------------------------------ 自由人判定

    def _is_free_candidate(self, name: str) -> bool:
        """`name` 是否可以作为自由人补位候选。

        排除：本轮已选、非干员名、**已在别处工作**（`current_room != ""`）、
        `config.free_blacklist` 内的干员。
        允许：`current_room == ""`（空闲）或从未被观测到在职的干员。
        """
        if name in self._selected:
            return False
        if name not in self._agent_list:
            return False
        state = self._state
        if state is None:
            # 未注入 state：退化为拆分前的行为（不做空闲判定）
            return True
        operator = state.operators.get(name)
        if operator is not None and operator.current_room != "":
            return False
        if state.config is not None and state.config.is_free_blacklist(name):
            return False
        return True

    def _find_free_candidate(self, cache: list) -> tuple | None:
        """返回本页第一个可补位的自由人 `(name, box)`，没有则 `None`。"""
        for name, box in cache:
            if self._is_free_candidate(name):
                return (name, box)
        return None

    # ------------------------------------------------------- 排序/筛选目标

    def _get_target_sort(self, name: str, is_dorm: bool) -> tuple[str, bool]:
        if is_dorm:
            return DORM_SORT
        if name in self._agent_list:
            from arknights_mower.data import agent_arrange_order

            order = agent_arrange_order.get(
                name, [DEFAULT_SORT[0], str(DEFAULT_SORT[1]).lower()]
            )
            if isinstance(order, list) and len(order) >= 2:
                asc = order[1] == "true"
                return (order[0], asc)
        return DEFAULT_SORT

    def _get_target_filter(
        self, name: str, is_dorm: bool, is_production: bool
    ) -> str | None:
        if name == SPECIAL_AGENT_ALL_FILTER:
            return DEFAULT_FILTER
        ret = self._agent_profession.get(name, DEFAULT_FILTER)
        logger.info(f"AgentSwap: filter for {name}={ret}")
        return ret
