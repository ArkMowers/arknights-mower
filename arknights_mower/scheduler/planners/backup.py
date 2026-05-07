from copy import deepcopy

from arknights_mower.scheduler.domain.task import SchedulerTask
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState


class BackupPlanner(AbstractPlanner):
    def __init__(self, state: SchedulerState) -> None:
        self._state = state

    def plan(self, timing_value: int = 999) -> bool:
        if not self._state.backup_plans:
            return False
        new_task = False
        conditions = deepcopy(self._state.plan_condition)
        for idx, bp in enumerate(self._state.backup_plans):
            if bp.trigger is None:
                continue
            conditions[idx] = self._state.evaluate_expression(bp.trigger)
            if (
                self._state.plan_condition[idx] != conditions[idx]
                and bp.trigger_timing.value <= timing_value
            ):
                if bp.task and conditions[idx]:
                    new_task = True
                    self._state.task_queue.push(
                        SchedulerTask(
                            plan=deepcopy(bp.task),
                        )
                    )
            else:
                conditions[idx] = self._state.plan_condition[idx]
        if conditions != self._state.plan_condition:
            self._state.swap_plan(conditions, refresh=True)
            if not new_task:
                self._state.task_queue.push(SchedulerTask(plan={}))
        return new_task
