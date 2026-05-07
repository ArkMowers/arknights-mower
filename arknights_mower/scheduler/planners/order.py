from datetime import datetime, timedelta

from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState


TRADE_ORDER_AGENTS = ["但书", "龙舌兰", "佩佩", "可露希尔"]


class OrderPlanner(AbstractPlanner):
    def __init__(self, state: SchedulerState) -> None:
        self._state = state

    def plan_room(self, room: str, run_order_time: datetime) -> None:
        plan = self._state.plan
        if room not in plan:
            return
        existing = self._state.task_queue.find(
            task_type=TaskTypes.RUN_ORDER,
            meta_data=room,
        )
        if existing:
            return
        in_out_plan = {room: ["Current"] * len(plan[room])}
        for idx, x in enumerate(plan[room]):
            if any(
                any(char in replacement_str for replacement_str in x.replacement)
                for char in TRADE_ORDER_AGENTS
            ):
                if x.replacement:
                    in_out_plan[room][idx] = x.replacement[0]
        self._state.task_queue.push(
            SchedulerTask(
                time=run_order_time,
                plan=in_out_plan,
                type=TaskTypes.RUN_ORDER,
                meta_data=room,
            )
        )

    def plan_all(self, run_order_rooms: dict, get_run_order_time) -> None:
        for room in run_order_rooms:
            room_time = get_run_order_time(room)
            if room_time:
                self.plan_room(room, room_time)
