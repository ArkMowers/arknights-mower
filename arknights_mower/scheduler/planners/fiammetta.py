from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState


class FiammettaPlanner(AbstractPlanner):
    def __init__(self, state: SchedulerState, fia_threshold: float = 0.9, fia_fool: bool = True) -> None:
        self._state = state
        self._fia_threshold = fia_threshold
        self._fia_fool = fia_fool

    def plan(self, task_time: datetime) -> bool:
        if "菲亚梅塔" not in self._state.operators:
            return False
        fia = self._state.operators["菲亚梅塔"]
        if not fia.room.startswith("dormitory"):
            return False
        fia_plan = fia.replacement
        fia_room = fia.room
        if not fia_plan:
            return False

        threshold = self._fia_threshold if self._fia_fool else 0.9
        target = None
        for operator in fia_plan:
            op = self._state.operators.get(operator)
            if op is None:
                continue
            operator_morale = op.current_mood()
            if operator_morale > threshold * 24:
                continue
            if op.rest_in_full and op.exhaust_require and not op.is_resting():
                continue
            if op.group:
                lowest = True
                for member in self._state.groups.get(op.group, []):
                    if member == operator:
                        continue
                    member_op = self._state.operators.get(member)
                    if member_op is None:
                        continue
                    if member_op.workaholic and member not in fia_plan:
                        continue
                    member_morale = member_op.current_mood()
                    if member_morale - member_op.lower_limit < operator_morale - op.lower_limit:
                        lowest = False
                        break
                if not lowest:
                    continue
            target = operator
            break

        if target is None and not self._fia_fool:
            best_op = fia_plan[0]
            best_mood = 24
            for op_name in fia_plan:
                op = self._state.operators.get(op_name)
                if op is None:
                    continue
                if op.rest_in_full and op.exhaust_require and not op.is_resting():
                    continue
                mood = op.current_mood()
                if mood < best_mood:
                    best_op = op_name
                    best_mood = mood
            target = best_op

        if target:
            self._state.task_queue.push(
                SchedulerTask(
                    time=task_time,
                    type=TaskTypes.FIAMMETTA,
                    plan={fia_room: [target, "菲亚梅塔"]},
                )
            )
            return True
        else:
            self._state.task_queue.push(
                SchedulerTask(
                    time=task_time + timedelta(hours=24 * (1 - threshold) / 2),
                    type=TaskTypes.FIAMMETTA,
                )
            )
            return False
