import heapq
from datetime import datetime

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState


class IdlePlanner(AbstractPlanner):
    def __init__(self, state: SchedulerState) -> None:
        self._state = state

    def plan(self, plan: dict, time: datetime) -> None:
        config = self._state.config
        if not config or not config.free_room:
            return
        task_queue = self._state.task_queue

        for room, assignments in plan.items():
            for name in assignments:
                if name != "Current":
                    dorm_key, dorm = self._state.get_dorm_by_name(name)
                    if dorm and dorm.time and dorm.time < time:
                        self._add_release_dorm(task_queue, name)

        if not plan:
            waiting_list: list[tuple[int, float, str]] = []
            for name, op in self._state.operators.items():
                if (
                    not op.is_high()
                    and op.current_mood() < op.upper_limit
                    and op.current_room == ""
                    and name not in config.free_blacklist
                ):
                    heapq.heappush(
                        waiting_list,
                        (
                            1 if name in ["九色鹿", "年"] else 0,
                            (op.current_mood() - op.lower_limit) / (op.upper_limit - op.lower_limit),
                            name,
                        ),
                    )
            if not waiting_list:
                return

            new_plan: dict[str, list[str]] = {}
            for key, dorm in self._state.dormitories.items():
                if dorm.name not in self._state.operators:
                    continue
                if not waiting_list:
                    break
                agent = self._state.operators[dorm.name]
                if not agent.is_high() and (
                    agent.current_mood() >= agent.upper_limit
                    or (dorm.time is not None and dorm.time < datetime.now())
                ):
                    rest = heapq.heappop(waiting_list)
                    room_name, idx = key
                    if room_name not in new_plan:
                        new_plan[room_name] = ["Current"] * 5
                    new_plan[room_name][idx] = rest[2]
            if new_plan:
                task_queue.push(SchedulerTask(time=datetime.now(), plan=new_plan))

    def _add_release_dorm(self, task_queue, name: str) -> None:
        op = self._state.operators.get(name)
        if op is None or not op.current_room.startswith("dorm"):
            return
        dorm_key = (op.current_room, op.current_index)
        dorm = self._state.dormitories.get(dorm_key)
        if dorm and dorm.time and dorm.time > datetime.now():
            release_plan = {op.current_room: ["Current"] * 5}
            release_plan[op.current_room][op.current_index] = "Free"
            task_queue.push(
                SchedulerTask(
                    time=dorm.time,
                    type=TaskTypes.RELEASE_DORM,
                    plan=release_plan,
                    meta_data=name,
                )
            )
