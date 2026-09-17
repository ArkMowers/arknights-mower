"""换班服务的扫描、翻页与**末尾检测**。

对应拆分前的 `_do_scan` 与 `_do_select` 上半段（翻页部分）。

这里承载 **BUG-2 / BUG-3 的修复**：两者本是**同一条语句** ——
重构前 `_do_select` 里是

    cur_names = [c[0] for c in self._cache]
    if cur_names == self._last_names:          # ← BUG-3：这个比较被删了
        logger.error("... reached end of list ...")
        return []                              # ← BUG-2：静默返回

「翻到底检测」（BUG-3 丢失的比较）与「静默返回」（BUG-2）必须**一并修**：
只把 `return []` 改成抛异常而不恢复比较，就根本没有"翻到底"的判据，
只剩 `MAX_PAGE` 兜底；只恢复比较而不改返回，失败仍被上报为"成功"。
"""

from __future__ import annotations

from arknights_mower.scheduler.constants import MAX_PAGE, SCREEN_H, SCREEN_W
from arknights_mower.scheduler.services.agent_swap_errors import AgentSwapError
from arknights_mower.scheduler.steps import Step, StepRetry
from arknights_mower.utils.log import logger


class AgentSwapScanMixin:
    """面板扫描与向前翻页。"""

    def _do_scan(self) -> list[Step] | None:
        self._recog.update()
        self._cache = self._operator_list_fn(
            self._recog.img, full_scan=(self._last_filter == "ALL")
        )
        names = [r[0] if isinstance(r, tuple) else r for r in self._cache]
        logger.info(
            f"AgentSwap: scan page={self._page_count} "
            f"filter={self._last_filter} names={names}"
        )
        if not self._cache:
            raise StepRetry

        target = self._pending[0] if self._pending else None
        self._found_target = False
        for name, box in self._cache:
            if name not in self._pending:
                continue
            logger.info(f"AgentSwap: tap {name} at {box}")
            self._tap_center(box)
            self._pending.remove(name)
            self._selected.append(name)
            if name == target:
                self._found_target = True

        return [Step("select", self._scene_check, self._do_select)]

    def _swipe_next(self) -> None:
        img = self._screencap()
        ret = self._operator_list_fn(img, full_scan=False)
        if ret and len(ret) >= 2:
            st = ret[-2][1]
            ed = ret[0][1]
            st_x = st[0][0]
            st_y = st[0][1]
            ed_x = ed[0][0]
            delta = ed_x - st_x
            if delta < 0:
                self._device.swipe_noinertia(
                    (st_x / SCREEN_W, st_y / SCREEN_H),
                    (delta, 0),
                )
                return
        self._device.swipe(
            960 / SCREEN_W,
            540 / SCREEN_H,
            100 / SCREEN_W,
            540 / SCREEN_H,
            duration=300,
        )

    # ------------------------------------------------------------ 末尾检测

    def _check_end_of_list(self) -> None:
        """本页与上一页完全相同 → 已经翻到底，目标不存在。

        **BUG-3**：`_last_names` 必须被**比较**，否则它只是个只写变量。
        **BUG-2**：命中即抛 `AgentSwapError`，**不得**静默 `return []` ——
        静默返回会让 `Dispatch` 把失败判定为"成功"，`state.error` 永远是 `False`。
        """
        cur_names = [c[0] for c in self._cache]
        if cur_names == self._last_names:
            logger.error(
                f"AgentSwap: reached end of list, target={self._pending} not found"
            )
            raise AgentSwapError(
                f"AgentSwap: reached end of list, target={self._pending} not found"
            )
        self._last_names = cur_names

    def _advance_page(self) -> list[Step] | None:
        """翻到下一页；已到 `MAX_PAGE` 则抛 `AgentSwapError`（BUG-2 的第二处）。"""
        if self._page_count >= MAX_PAGE:
            logger.error("AgentSwap: max page reached")
            raise AgentSwapError("AgentSwap: max page reached")

        logger.info(f"AgentSwap: swipe page={self._page_count}")
        self._swipe_next()
        self._page_count += 1
        return [Step("scan", self._scene_check, self._do_scan)]
