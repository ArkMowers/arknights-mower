from __future__ import annotations

from copy import deepcopy
from datetime import timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes


def format_task(task: SchedulerTask, time_offset: int = 0) -> SchedulerTask:
    result = deepcopy(task)
    result.time += timedelta(hours=time_offset)
    result.type = result.type.display_value
    if result.type == TaskTypes.NOT_SPECIFIC.display_value and result.meta_data:
        result.type = result.meta_data
    return result
