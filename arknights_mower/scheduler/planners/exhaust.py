from datetime import datetime

from arknights_mower.data import agent_list, base_room_list
from arknights_mower.scheduler.domain.task import SchedulerTask, TaskTypes
from arknights_mower.scheduler.planners.base import AbstractPlanner
from arknights_mower.scheduler.state import SchedulerState

TRADE_ORDER_AGENTS = ["但书", "龙舌兰", "佩佩", "可露希尔"]


class ExhaustPlanner(AbstractPlanner):
    def __init__(self, state: SchedulerState) -> None:
        self._state = state

    def plan(self, operator_name: str) -> None:
        op = self._state.operators.get(operator_name)
        if op is None:
            return
        candidates = [op.name]
        if op.group != "":
            group = self._state.groups.get(op.group)
            if group:
                candidates = group

        current_resting = len(self._state.dormitories) - self._state.available_free() - self._state.available_free("low")

        plan: dict[str, list[str]] = {}
        self._get_resting_plan(candidates, [], plan, current_resting)
        if plan:
            self._state.task_queue.push(
                SchedulerTask(
                    time=datetime.now(),
                    plan=plan,
                    type=TaskTypes.SHIFT_OFF,
                )
            )

    def _get_resting_plan(self, agents, exist_replacement, plan, current_resting):
        required = 0
        for x in agents:
            op = self._state.operators[x]
            if op.workaholic:
                continue
            required += 1
        if current_resting + required + len(exist_replacement) > len(self._state.dormitories):
            return

        fia_plan, _ = self._check_fia()
        agents.sort(
            key=lambda y: (
                y not in fia_plan if fia_plan else True,
                self._state.operators[y].current_room in ["factory", "train"],
                self._state.operators[y].current_mood() - self._state.operators[y].lower_limit,
            )
        )
        success = True
        __plan: dict[str, list[str]] = {}
        __replacement: list[str] = []
        for agent in agents:
            if not success:
                break
            x = self._state.operators[agent]
            if x.room not in base_room_list:
                success = False
                break
            if self._state.get_dorm_by_name(x.name)[0] is not None:
                success = False
                break
            _rep = next(
                (
                    obj for obj in x.replacement
                    if (
                        not (self._state.operators[obj].current_room != "" and not self._state.operators[obj].is_resting())
                    )
                    and obj not in TRADE_ORDER_AGENTS
                    and obj not in exist_replacement
                    and obj not in __replacement
                    and self._state.operators[obj].current_room != x.room
                ),
                None,
            )
            if _rep is not None:
                __replacement.append(_rep)
                if x.room not in __plan:
                    __plan[x.room] = ["Current"] * len(self._state.plan[x.room])
                __plan[x.room][x.index] = _rep
            else:
                success = False
        if success:
            exist_replacement.extend(__replacement)
            for idx, agent_name in enumerate(agents):
                op = self._state.operators[agent_name]
                if op.workaholic:
                    continue
                self._state.assign_dorm(agent_name)
            for k, v in __plan.items():
                if k not in plan:
                    plan[k] = __plan[k]
                for idx, name in enumerate(__plan[k]):
                    if plan[k][idx] == "Current" and name != "Current":
                        plan[k][idx] = name

    def _check_fia(self):
        if "菲亚梅塔" in self._state.operators and self._state.operators["菲亚梅塔"].room.startswith("dormitory"):
            fia = self._state.operators["菲亚梅塔"]
            return fia.replacement, fia.room
        return None, None
