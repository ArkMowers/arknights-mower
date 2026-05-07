from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum, auto

from arknights_mower.scheduler.constants import WORKSHOP_AGENT_JIUSE, WORKSHOP_FURNITURE_PREFIX
from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.executors.base import AbstractExecutor
from arknights_mower.utils.log import logger


class WorkshopState(Enum):
    ENTER_ROOM = auto()
    DASHBOARD_ENTER = auto()
    FORMULA_SELECT = auto()
    FORMULA_SCAN = auto()
    PROCESS = auto()
    COLLECT = auto()
    DONE = auto()


class WorkshopExecutor(AbstractExecutor):
    MAX_DURATION = timedelta(minutes=5)

    def __init__(self, infra) -> None:
        super().__init__(infra)
        self._agent = ""
        self._state = WorkshopState.ENTER_ROOM

    def execute(self, task: SchedulerTask) -> None:
        self._agent = task.meta_data
        self._state = WorkshopState.ENTER_ROOM
        start_time = datetime.now()

        while self._state != WorkshopState.DONE:
            self.check_pause()
            if datetime.now() - start_time > self.MAX_DURATION:
                raise TimeoutError("workshop execution timed out")
            getattr(self, f"_state_{self._state.name.lower()}")()
            self.infra.device.screencap()

    def _state_enter_room(self) -> None:
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
        is_9colored = self._agent == WORKSHOP_AGENT_JIUSE
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
                    if is_9colored and workshop_formula[name]["apCost"] > 4:
                        continue
                    tab = workshop_formula[name]["tab"]
                    if tab not in group:
                        group[tab] = {}
                    group[tab][name] = item

        self._state = WorkshopState.FORMULA_SELECT

    def _state_formula_select(self) -> None:
        self._state = WorkshopState.DONE

    def _state_formula_scan(self) -> None:
        self._state = WorkshopState.PROCESS

    def _state_process(self) -> None:
        self._state = WorkshopState.COLLECT

    def _state_collect(self) -> None:
        self._state = WorkshopState.DONE
