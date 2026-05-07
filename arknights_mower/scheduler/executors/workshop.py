from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional

from arknights_mower.scheduler.constants import (
    WORKSHOP_AGENT_JIUSE,
    WORKSHOP_FURNITURE_PREFIX,
    WORKSHOP_TAB_POS,
)
from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger


class WorkshopState(Enum):
    ENTER_ROOM = auto()
    ARRANGE_AGENT = auto()
    DASHBOARD_ENTER = auto()
    FORMULA_SELECT = auto()
    FORMULA_SCAN = auto()
    PROCESS = auto()
    COLLECT = auto()
    RESTORE = auto()
    DONE = auto()


class WorkshopExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=5)

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._agent = ""
        self._is_9colored = False
        self._group = {}
        self._tab_queue: deque = deque()
        self._state = WorkshopState.ENTER_ROOM
        self._original_current = ""
        self._original_room = ""
        self._original_index = -1
        self._start_time = datetime.now()

    def execute(self, task: SchedulerTask) -> None:
        self._agent = task.meta_data
        self._is_9colored = self._agent == WORKSHOP_AGENT_JIUSE
        self._state = WorkshopState.ENTER_ROOM
        self._start_time = datetime.now()

        while self._state != WorkshopState.DONE:
            self.check_pause()
            if datetime.now() - self._start_time > self.MAX_DURATION:
                raise TimeoutError("workshop execution timed out")
            getattr(self, f"_state_{self._state.name.lower()}")()
            self.infra.device.screencap()

    def _state_enter_room(self) -> None:
        from arknights_mower.scheduler.scene import Scene

        self.infra.navigator.navigate(Scene.INFRA_MAIN)
        self._state = WorkshopState.ARRANGE_AGENT

    def _state_arrange_agent(self) -> None:
        self.infra.agent_selector.run(
            [self._agent], "factory", fast_mode=True
        )
        self._state = WorkshopState.DASHBOARD_ENTER

    def _state_dashboard_enter(self) -> None:
        from arknights_mower.data import workshop_formula
        from arknights_mower.solvers.record import get_inventory_counts
        from arknights_mower.utils import config

        inventory_data = get_inventory_counts()
        if self._agent not in [s.operator for s in config.conf.workshop_settings]:
            self._state = WorkshopState.DONE
            return

        item_list = next(
            s.items for s in config.conf.workshop_settings if s.operator == self._agent
        )
        seen = set()
        group = {}
        for item in item_list:
            for name in item.item_names:
                if name in seen:
                    continue
                seen.add(name)
                metadata = workshop_formula[name]
                if name.startswith(WORKSHOP_FURNITURE_PREFIX):
                    name = WORKSHOP_FURNITURE_PREFIX
                if (
                    name in inventory_data
                    and inventory_data[name] < item.self_upper_limit
                    and all(
                        child_name in inventory_data
                        and inventory_data[child_name] > item.children_lower_limit
                        for child_name in metadata["items"]
                    )
                ):
                    if self._is_9colored and metadata["apCost"] > 4:
                        continue
                    tab = metadata["tab"]
                    if tab not in group:
                        group[tab] = {}
                    group[tab][name] = item

        self._group = group
        self._tab_queue = deque(group.items())
        self._state = WorkshopState.FORMULA_SELECT

    def _state_formula_select(self) -> None:
        if not self._tab_queue:
            self._state = WorkshopState.DONE
            return
        tab, _ = self._tab_queue.popleft()
        pos = WORKSHOP_TAB_POS.get(tab)
        if pos:
            self.infra.device.tap(*pos)
        self._state = WorkshopState.FORMULA_SCAN

    def _state_formula_scan(self) -> None:
        self._state = WorkshopState.PROCESS

    def _state_process(self) -> None:
        self.infra.device.tap(0.84, 0.4)
        self.infra.device.tap(0.88, 0.88)
        self._state = WorkshopState.COLLECT

    def _state_collect(self) -> None:
        self.infra.device.back()
        self._state = WorkshopState.RESTORE

    def _state_restore(self) -> None:
        self._state = WorkshopState.DONE
