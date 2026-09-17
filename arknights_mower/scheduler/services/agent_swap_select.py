"""换班服务的选人决策与落位编排。

对应拆分前的 `_do_uncheck` / `_do_prepare` / `_do_select` / `_do_sort`。

⚠️ 两个 `return []` **不得改动** —— 它们是"正常完成"路径：
`return []` 表示"追加空队列"，队列循环随即结束并返回 `True`。
只有 `_advance_page()` 的 `max page reached` 与 `_check_end_of_list()`
的"翻到底"才是错误路径，它们抛 `AgentSwapError`。
"""

from __future__ import annotations

from arknights_mower.scheduler.constants import (
    AGENT_SELECT_POSITIONS,
    DEFAULT_FILTER,
    DEFAULT_SORT,
    INFRA_CLEAR_ALL,
)
from arknights_mower.scheduler.steps import Step, StepRetry
from arknights_mower.utils.log import logger

_POSITIONS = AGENT_SELECT_POSITIONS


class AgentSwapSelectMixin:
    """把已扫描到的候选变成点击动作与后续步骤。"""

    def _do_uncheck(self) -> list[Step] | None:
        while self._to_uncheck:
            idx = self._to_uncheck.pop(0)
            logger.info(f"AgentSwap: uncheck slot {idx}")
            self._tap_slot(idx)
        self._selected = [n for n in self._selected if n in self._agents]
        logger.info(f"AgentSwap: uncheck done, selected={self._selected}")
        return None

    def _do_prepare(self) -> list[Step] | None:
        target = self._pending[0] if self._pending else None
        if not target and self._free_count == 0:
            if not self._to_uncheck and len([a for a in self._agents if a != "Free"]) > 1:
                return [Step("sort", self._scene_check, self._do_sort)]
            logger.info("AgentSwap: nothing to do, done")
            return []
        if not target and self._free_count > 0:
            logger.info("AgentSwap: switching to free mode")
            return [Step("scan", self._scene_check, self._do_scan)]

        need_sort, need_asc = self._get_target_sort(target, self._is_dorm)
        cur_sort, cur_asc = self._detect_arrange(self._room)
        if cur_sort != need_sort or cur_asc != need_asc:
            logger.info(f"AgentSwap: switch sort {cur_sort} -> {need_sort} asc={need_asc}")
            self._tap_sort(need_sort, need_asc, self._room)
            raise StepRetry
        need_filter = self._get_target_filter(target, self._is_dorm, self._is_production)
        if need_filter is not None and need_filter != self._last_filter:
            logger.info(f"AgentSwap: switch filter {self._last_filter} -> {need_filter}")
            self._open_filter(need_filter)
            self._last_filter = need_filter
            self._page_count = 0
            raise StepRetry
        logger.info(f"AgentSwap: ready for target={target}")
        return [Step("scan", self._scene_check, self._do_scan)]

    def _do_select(self) -> list[Step] | None:
        if self._found_target:
            self._page_count = 0
            self._last_names = None
            if self._pending or self._free_count > 0:
                return [Step("prepare", self._scene_check, self._do_prepare)]
            logger.info("AgentSwap: all selected, sort")
            return [Step("sort", self._scene_check, self._do_sort)]

        if self._free_count > 0 and not self._pending:
            found = self._find_free_candidate(self._cache)
            if found is not None:
                name, box = found
                logger.info(f"AgentSwap: free tap {name}")
                self._tap_center(box)
                self._free_count -= 1
                # 与 legacy 一致：补位结果记入已选，并占用一个 Free 名额，
                # 否则 _do_sort 重建时会把它连同清空一起丢掉
                self._selected.append(name)
                self._agents[self._agents.index("Free")] = name
                if self._free_count == 0:
                    logger.info("AgentSwap: free done")
                    return [Step("sort", self._scene_check, self._do_sort)]
                return [Step("scan", self._scene_check, self._do_scan)]

        if not self._pending and self._free_count == 0:
            return [Step("sort", self._scene_check, self._do_sort)]

        # BUG-3：本页与上页相同 → 翻到底；命中即抛（BUG-2）
        self._check_end_of_list()
        return self._advance_page()

    def _do_sort(self) -> list[Step] | None:
        agents = [a for a in self._agents if a != "Free"]
        if len(agents) > 1:
            self._switch_filter_other(self._last_filter)
            self._open_filter(DEFAULT_FILTER)
            self._tap_sort(DEFAULT_SORT[0], DEFAULT_SORT[1], self._room)
            self._last_names = None
            exists = self._selected
            click_order = []
            for a in agents:
                if a in exists:
                    click_order.append(exists.index(a))
            self._device.tap(INFRA_CLEAR_ALL[0], INFRA_CLEAR_ALL[1])
            self._recog.update()
            for p_idx in click_order:
                pos = _POSITIONS[p_idx]
                self._device.tap(pos[0], pos[1])

        self._tap_sort(DEFAULT_SORT[0], DEFAULT_SORT[1], self._room)
        logger.info(f"AgentSwap: {self._room} done")
        return []