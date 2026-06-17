from __future__ import annotations

from datetime import datetime

from arknights_mower.scheduler.constants import (
    WORKSHOP_FORMULA_SWIPE_DURATION,
    WORKSHOP_FORMULA_SWIPE_END,
    WORKSHOP_FORMULA_SWIPE_START,
    WORKSHOP_JIUSE_SKILL_REGION,
    WORKSHOP_JIUSE_SKILL_TARGET,
    WORKSHOP_TAB_POS,
)
from arknights_mower.scheduler.infra.workshop_scanner import (
    dashboard_item_valid,
    formula_item_center,
    read_number,
    scan_formula_items,
)
from arknights_mower.scheduler.services.workshop_service import (
    WorkshopCandidate,
    first_matching_candidate,
)
from arknights_mower.utils.log import logger


class WorkshopExecutorSupportMixin:
    def _select_formula(self) -> None:
        if self._active_tab is None and not self._open_next_tab():
            return
        scanned_items = scan_formula_items(self._recog)
        current_scan = [item.name for item in scanned_items]
        candidates = self._visible_candidates(scanned_items)
        selected = first_matching_candidate(
            [candidate for _, candidate in candidates],
            is_jiuselu=self._is_9colored,
            gap=self._gap,
        )
        if selected is not None:
            item = next(scan for scan, candidate in candidates if candidate == selected)
            self.infra.device.tap(*formula_item_center(item.box))
            self._formula_selected(selected)
            return
        for _, candidate in candidates:
            self._active_candidates.pop(candidate.formula_name, None)
        if current_scan == self._last_scan or not self._active_candidates:
            self._active_tab = None
            self._last_scan = []
            return
        self._last_scan = current_scan
        self.infra.device.swipe(
            *WORKSHOP_FORMULA_SWIPE_START,
            *WORKSHOP_FORMULA_SWIPE_END,
            WORKSHOP_FORMULA_SWIPE_DURATION,
        )

    def _open_next_tab(self) -> bool:
        if not self._tab_queue:
            logger.info("no selectable workshop material found")
            self._tasks.clear()
            return False
        self._active_tab, self._active_candidates = self._tab_queue.popleft()
        pos = WORKSHOP_TAB_POS.get(self._active_tab)
        if pos:
            self.infra.device.tap(*pos)
            return True
        return False

    def _visible_candidates(self, scanned_items):
        candidates = []
        for item in scanned_items:
            candidate = self._active_candidates.get(item.name)
            if candidate is None:
                continue
            if not item.valid:
                self._active_candidates.pop(item.name, None)
                continue
            candidates.append((item, candidate))
        return candidates

    def _formula_selected(self, selected: WorkshopCandidate) -> None:
        self._current_material = selected
        self._production_plan = None
        self._waiting_collect = False
        self._tasks.popleft()
        self._active_tab = None
        self._last_scan = []
        logger.info("selected workshop material: %s", selected.formula_name)

    def _collect_product(self) -> None:
        if self._recog is not None:
            self._recog.save_screencap("workshop")
        self._apply_mood_cost()
        self._production_plan = None
        self._waiting_collect = False
        self.infra.device.back()

    def _apply_mood_cost(self) -> None:
        if not self._is_9colored or self._production_plan is None:
            return
        operator = self._agent_operator()
        if operator is None:
            return
        operator.mood -= self._production_plan.estimated_mood_cost
        operator.time_stamp = datetime.now()
        logger.debug(
            "jiuselu workshop mood cost=%s",
            self._production_plan.estimated_mood_cost,
        )

    def _refresh_jiuselu_gap(self) -> bool:
        count = self._read_number(WORKSHOP_JIUSE_SKILL_REGION)
        if count < 0:
            logger.error("failed to read jiuselu skill count")
            return False
        self._gap = WORKSHOP_JIUSE_SKILL_TARGET - count
        logger.debug("jiuselu workshop skill gap=%s", self._gap)
        if self._gap > WORKSHOP_JIUSE_SKILL_TARGET:
            logger.error("invalid jiuselu skill count: %s", count)
            return False
        return True

    def _read_number(self, region: tuple[int, int, int, int]) -> int:
        for _ in range(4):
            try:
                return read_number(self._recog, region)
            except Exception as exc:
                logger.debug("read workshop number failed: %s", exc)
        return -1

    def _item_valid(self) -> bool:
        return dashboard_item_valid(self._recog)

    def _has_factory_warning(self) -> bool:
        return (
            self._recog is not None
            and self._recog.find("factory_warning") is not None
        )

    def _agent_mood(self) -> float:
        operator = self._agent_operator()
        return operator.mood if operator is not None else 24.0

    def _agent_operator(self, agent: str | None = None):
        state = getattr(self.infra, "state", None)
        operators = getattr(state, "operators", {}) if state is not None else {}
        return operators.get(agent or self._agent)

    def _mark_agent_exhausted(self) -> None:
        operator = self._agent_operator()
        if operator is not None:
            operator.mood = 0
            operator.time_stamp = datetime.now()

    def _get_factory_scene(self) -> str:
        s = self._update_scene()

        from arknights_mower.utils.scene import Scene

        if s == Scene.FACTORY_DASHBOARD:
            return "FACTORY_DASHBOARD"
        if s == Scene.FACTORY_FORMULA:
            return "FACTORY_FORMULA"
        if s == Scene.MATERIEL:
            return "FACTORY_PRODUCT_COLLECT"
        if s == Scene.FACTORY_PRODUCT_COLLECT:
            return "FACTORY_PRODUCT_COLLECT"
        if s == Scene.FACTORY_ROOM:
            return "FACTORY_ROOM"
        if s == Scene.INFRA_DETAILS:
            return "INFRA_DETAILS"
        if s == Scene.INFRA_DETAILS_OPEN:
            return "INFRA_DETAILS_OPEN"
        if s == Scene.INFRA_MAIN:
            return "INFRA_MAIN"
        if s == Scene.CONNECTING:
            return "CONNECTING"
        return "UNKNOWN"

    def _is_arrange_checkin_visible(self) -> bool:
        return (
            self._recog is not None
            and self._recog.find("arrange_check_in") is not None
        )

    def _navigate_infra(self) -> None:
        from arknights_mower.scheduler.scene import Scene as V2Scene

        self.infra.navigator.navigate(V2Scene.INFRA_MAIN)
        self.infra.navigator.enter_room("factory")
