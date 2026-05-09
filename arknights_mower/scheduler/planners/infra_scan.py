from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.data import base_room_list
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.utils.log import logger


class InfraScanPlanner(AbstractPlanner):
    frequency = timedelta(minutes=5)
    TIMEOUT = timedelta(hours=2)
    SPECIAL_TIMEOUT = {"歌蕾蒂娅": timedelta(hours=0.5), "见行者": timedelta(hours=0.5)}

    def condition(self, state) -> bool:
        now = datetime.now()
        for op in state.operators.values():
            if not op.room or op.room not in base_room_list:
                continue
            timeout = self.SPECIAL_TIMEOUT.get(op.name, self.TIMEOUT)
            if (
                op.time_stamp is None
                or op.time_stamp + timeout < now
            ):
                return True
        return False

    def make_task(self, state) -> Optional[SchedulerTask]:
        rooms = {
            op.room
            for op in state.operators.values()
            if op.room in base_room_list
        }
        if not rooms:
            return None
        logger.info(f"InfraScan: {len(rooms)} rooms need refresh")
        return SchedulerTask(
            time=datetime.now(),
            type=TaskTypes.INFRA_SCAN,
            meta_data=",".join(rooms),
        )
