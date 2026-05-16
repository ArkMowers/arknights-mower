from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta

from arknights_mower.scheduler.constants import WORKSHOP_AGENT_JIUSE, WORKSHOP_TAB_POS
from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger


class WorkshopExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=5)

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._agent = ""
        self._is_9colored = False
        self._tab_queue: deque = deque()

    def execute(self, task: SchedulerTask) -> None:
        self._agent = task.meta_data
        self._is_9colored = self._agent == WORKSHOP_AGENT_JIUSE

        from arknights_mower.scheduler.scene import Scene as V2Scene

        self._navigate(V2Scene.INFRA_MAIN)
        self._gather_inventory()
        self._process_workshop()

    def _navigate(self, target) -> None:
        self.infra.navigator.navigate(target)

    def _gather_inventory(self) -> None:
        from arknights_mower.data import workshop_formula
        from arknights_mower.solvers.record import get_inventory_counts
        from arknights_mower.utils import config

        inventory = get_inventory_counts()
        if not inventory:
            self._tab_queue = deque()
            return

        item_list = next(
            (s.items for s in config.conf.workshop_settings if s.operator == self._agent),
            [],
        )
        seen = set()
        group = {}
        for item in item_list:
            for name in item.item_names:
                if name in seen:
                    continue
                seen.add(name)
                metadata = workshop_formula[name]
                normalized = name if not name.startswith("家具零件") else "家具零件"
                if (
                    normalized in inventory
                    and inventory[normalized] < item.self_upper_limit
                    and all(
                        child in inventory
                        and inventory[child] > item.children_lower_limit
                        for child in metadata["items"]
                    )
                ):
                    if self._is_9colored and metadata["apCost"] > 4:
                        continue
                    tab = metadata["tab"]
                    if tab not in group:
                        group[tab] = {}
                    group[tab][normalized] = item
        self._tab_queue = deque(group.items())

    def _process_workshop(self) -> None:
        start = datetime.now()
        unknown_cnt = 0

        while True:
            self.check_pause()
            if datetime.now() - start > self.MAX_DURATION:
                raise TimeoutError("workshop processing timed out")

            scene = self._get_factory_scene()

            if self._is_arrange_checkin_visible():
                self.infra.device.tap(0.25, 0.95)
                continue

            if scene == "UNKNOWN":
                unknown_cnt += 1
                if unknown_cnt > 5:
                    self._navigate_infra()
                    unknown_cnt = 0
                continue

            if scene == "CONNECTING":
                continue

            if scene == "FACTORY_DASHBOARD":
                if not self._tab_queue:
                    break
                self.infra.device.tap(0.45, 0.65)

            elif scene == "FACTORY_FORMULA":
                self._select_formula()

            elif scene == "FACTORY_PRODUCT_COLLECT":
                self.infra.device.back()

            else:
                break

    def _get_factory_scene(self) -> str:
        s = self._update_scene()

        from arknights_mower.utils.scene import Scene

        if s == Scene.FACTORY_DASHBOARD:
            return "FACTORY_DASHBOARD"
        if s == Scene.FACTORY_FORMULA:
            return "FACTORY_FORMULA"
        if s == Scene.FACTORY_PRODUCT_COLLECT:
            return "FACTORY_PRODUCT_COLLECT"
        if s == Scene.CONNECTING:
            return "CONNECTING"
        return "UNKNOWN"

    def _is_arrange_checkin_visible(self) -> bool:
        return self._recog is not None and self._recog.find("arrange_check_in") is not None

    def _navigate_infra(self) -> None:
        from arknights_mower.scheduler.scene import Scene as V2Scene

        self.infra.navigator.navigate(V2Scene.INFRA_MAIN)
        self.infra.navigator.enter_room("factory")

    def _select_formula(self) -> None:
        if not self._tab_queue:
            return
        tab, _ = self._tab_queue.popleft()
        pos = WORKSHOP_TAB_POS.get(tab)
        if pos:
            self.infra.device.tap(*pos)
