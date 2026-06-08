from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.data import base_room_list
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.services.operator_service import need_to_refresh
from arknights_mower.utils.log import logger


class InfraScanPlanner(AbstractPlanner):
    frequency = timedelta(minutes=5)

    def _rooms_need_refresh(self, state) -> set[str]:
        rooms = set()
        for op in state.operators.values():
            if op.room not in base_room_list:
                continue
            if not op.is_high():
                continue
            if need_to_refresh(op):
                rooms.add(op.room)
        return rooms

    def condition(self, state) -> bool:
        return len(self._rooms_need_refresh(state)) > 0

    def make_task(self, state) -> Optional[SchedulerTask]:
        rooms = self._rooms_need_refresh(state)
        if not rooms:
            return None
        logger.info(f"InfraScan: {len(rooms)} rooms need refresh")
        return SchedulerTask(
            time=datetime.now(),
            type=TaskTypes.INFRA_SCAN,
            meta_data=",".join(rooms),
        )
