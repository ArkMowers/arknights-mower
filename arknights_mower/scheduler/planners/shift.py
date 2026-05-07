from collections import defaultdict
from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState


class ShiftPlanner(AbstractPlanner):
    def __init__(self, state: SchedulerState, merge_interval: int = 5) -> None:
        self._state = state
        self._merge_interval = merge_interval

    def plan(self) -> None:
        tasks = [
            t for t in self._state.task_queue.all_tasks()
            if t.type not in [TaskTypes.SHIFT_ON, TaskTypes.RELEASE_DORM]
        ]

        total_agent: list = sorted(
            (
                v for v in self._state.operators.values()
                if v.is_high() and not v.room.startswith("dorm") and not v.is_resting()
            ),
            key=lambda x: x.current_mood() - x.lower_limit,
        )

        min_resting_time = datetime.max
        for agent in total_agent:
            predicted = self._state.predict_exhaust(agent)
            min_resting_time = min(min_resting_time, max(predicted, datetime.now() + timedelta(minutes=30)))

        grouped_dorms: dict[str, list] = defaultdict(list)
        free_rooms = []
        for dorm in self._state.dormitories.values():
            if not dorm.name or dorm.name not in self._state.operators:
                continue
            op = self._state.operators[dorm.name]
            grouped_dorms[op.group].append(dorm)
            if not op.is_high():
                free_rooms.append(dorm)

        new_task: dict[datetime, tuple[list, bool | None]] = {}
        for group_name, dorms in grouped_dorms.items():
            _high_dorms = [
                d for d in dorms
                if self._state.operators[d.name].is_high()
                and self._state.operators[d.name].is_high_priority()
            ]
            high_dorms = _high_dorms if _high_dorms else [
                d for d in dorms if self._state.operators[d.name].is_high()
            ]
            rest_in_full_dorms = [
                d for d in high_dorms if self._state.operators[d.name].rest_in_full
            ]

            if high_dorms and group_name:
                base_time = high_dorms[0].time
                max_rest_in_full_time = None
                if rest_in_full_dorms:
                    max_rest_in_full_time = max(
                        (d.time for d in rest_in_full_dorms if d.time is not None), default=None
                    )
                nearest_dorm = min(
                    (d for d in high_dorms if d.time is not None),
                    key=lambda d: d.time, default=None
                )

                if max_rest_in_full_time:
                    task_time = max_rest_in_full_time
                elif nearest_dorm:
                    task_time = min(nearest_dorm.time, min_resting_time)
                else:
                    continue

                if task_time not in new_task:
                    new_task[task_time] = (high_dorms, len(rest_in_full_dorms) > 0)
                else:
                    new_task[task_time] = (
                        new_task[task_time][0] + high_dorms,
                        new_task[task_time][1] or len(rest_in_full_dorms) > 0,
                    )

            if high_dorms and not group_name:
                for room in high_dorms:
                    if room.time and room.name:
                        op = self._state.operators[room.name]
                        rest_in_full = op.rest_in_full
                        task_time = room.time if rest_in_full else min(room.time, min_resting_time)
                        if task_time not in new_task:
                            new_task[task_time] = ([room], rest_in_full)
                        else:
                            new_task[task_time] = (
                                new_task[task_time][0] + [room],
                                new_task[task_time][1] or rest_in_full,
                            )

        config = self._state.config
        if config and config.free_room:
            for room in free_rooms:
                min_resting_time += timedelta(seconds=10)
                if room.time and room.name:
                    task_time = min(room.time, min_resting_time)
                    if task_time < datetime.now():
                        continue
                    if task_time not in new_task:
                        new_task[task_time] = ([room], None)
                    else:
                        new_task[task_time] = (
                            new_task[task_time][0] + [room],
                            new_task[task_time][1],
                        )

        result = self._generate_plan_by_dorm(new_task)
        for t in result:
            self._state.task_queue.push(t)

    def _generate_plan_by_dorm(self, tasks: dict) -> list[SchedulerTask]:
        if not tasks:
            return []
        ordered = sorted(tasks.items())
        result: list[SchedulerTask] = []
        planned: set[str] = set()
        current_time = datetime.now()
        for time_, (dorms, rest_in_full) in ordered:
            plan: dict[str, list[str]] = {}
            exhaust_exist = False
            for room in dorms:
                if room.name in planned:
                    continue
                op = self._state.operators[room.name]
                if op.exhaust_require:
                    exhaust_exist = True
                if not op.is_high():
                    if op.current_room not in plan:
                        plan[op.current_room] = ["Current"] * len(self._state.plan[op.current_room])
                    plan[op.current_room][op.current_index] = "Free"
                else:
                    agents = self._state.groups.get(op.group, [op.name]) if op.group else [op.name]
                    for agent in agents:
                        o = self._state.operators.get(agent)
                        if o is None:
                            continue
                        if o.room not in plan:
                            plan[o.room] = ["Current"] * len(self._state.plan[o.room])
                        plan[o.room][o.index] = agent
                        planned.add(o.name)

            if rest_in_full:
                if exhaust_exist:
                    time_ = max(time_, current_time)
                else:
                    time_ = max(time_ - timedelta(minutes=8), current_time)
                result.append(SchedulerTask(time=time_, plan=plan, type=TaskTypes.SHIFT_ON))
            else:
                if rest_in_full is None and not (self._state.config and self._state.config.free_room):
                    continue
                result.append(
                    SchedulerTask(
                        time=max(time_, current_time - timedelta(seconds=1)),
                        plan=plan,
                        type=TaskTypes.RELEASE_DORM if rest_in_full is None else TaskTypes.SHIFT_ON,
                    )
                )
        return result
