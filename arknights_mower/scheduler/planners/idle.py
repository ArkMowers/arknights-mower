from __future__ import annotations

from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner


class IdlePlanner(AbstractPlanner):
    frequency = timedelta(minutes=30)
    IDLE_HOURS = 1

    def condition(self, state) -> bool:
        return len(state.task_queue) == 0

    def make_task(self, state) -> SchedulerTask | None:
        return SchedulerTask(
            time=datetime.now() + timedelta(hours=self.IDLE_HOURS),
            type=TaskTypes.NOT_SPECIFIC,
        )
