from __future__ import annotations

from typing import Optional

from arknights_mower.data import agent_arrange_order
from arknights_mower.scheduler.constants import DORM_ROOM_PREFIX
from arknights_mower.scheduler.domain.operators import (
    Dormitory,
    Operator,
    OperatorType,
    RestPriority,
)
from arknights_mower.scheduler.services.plan_service import is_refresh_trading


class StateInitMixin:
    """`SchedulerState` 的初始化 Mixin：构建干员表与宿舍表。

    Mixin 只读写宿主 `SchedulerState` 的字段/方法，不定义 `__init__`，
    因此不参与 `SchedulerState` 的构造顺序（MRO 中位于 `SchedulerState` 之前）。
    """

    def _add_operator(self, data, room_name: str, idx: int, operator_type: str = "high") -> None:
        op = Operator(
            name=data.agent,
            room=room_name,
            index=idx,
            group=data.group,
            replacement=list(data.replacement),
            operator_type=OperatorType(operator_type),
        )
        if self.config:
            if self.config.is_resting_priority(op.name):
                op.resting_priority = RestPriority.LOW
            op.exhaust_require = self.config.is_exhaust_require(op.name)
            op.rest_in_full = self.config.is_rest_in_full(op.name)
            op.workaholic = self.config.is_workaholic(op.name)
            op.refresh_order_room = is_refresh_trading(self.config, op.name)
            op.refresh_drained = self.config.is_refresh_drained(op.name)
        if op.name in agent_arrange_order:
            op.arrange_order = agent_arrange_order[op.name]
        if op.name in self._shadow_copy:
            exist = self._shadow_copy[op.name]
            op.mood = exist.mood
            op.time_stamp = exist.time_stamp
            op.depletion_rate = exist.depletion_rate
            op.current_room = exist.current_room
            op.current_index = exist.current_index
        self.operators[op.name] = op
        if op.exhaust_require:
            self.exhaust_agent.add(op.name)
            if op.group:
                self.exhaust_group.add(op.group)
        if op.group:
            if op.group not in self.groups:
                self.groups[op.group] = [op.name]
            else:
                self.groups[op.group].append(op.name)
        if op.workaholic:
            self.workaholic_agent.add(op.name)
        if op.rest_in_full and op.group:
            self.rest_in_full_group.add(op.group)

    def _build_dormitories(self, update: bool = False) -> Optional[str]:
        self.dormitories = {}
        dorm_names = sorted(
            [k for k in self.plan if k.startswith(DORM_ROOM_PREFIX)],
            reverse=False,
        )
        added = []
        if not update:
            for dorm in dorm_names:
                free_found = False
                for _idx, _dorm_item in enumerate(self.plan[dorm]):
                    if _dorm_item.agent == "Free" and _idx <= 1:
                        if "波登可" not in [a.agent for a in self.plan[dorm]]:
                            return "宿舍必须安排2个宿管"
                    if _dorm_item.agent != "Free" and free_found:
                        return "Free必须连续且安排在宿管后"
                    if (
                        _dorm_item.agent == "Free"
                        and not free_found
                        and f"{dorm}{_idx}" not in added
                    ):
                        self.dormitories[(dorm, _idx)] = Dormitory((dorm, _idx))
                        added.append(f"{dorm}{_idx}")
                        free_found = True
                        continue
                if not free_found:
                    return "宿舍必须安排至少一个Free"
            for dorm in dorm_names:
                for _idx, _dorm_item in enumerate(self.plan[dorm]):
                    if _dorm_item.agent == "Free" and f"{dorm}{_idx}" not in added:
                        self.dormitories[(dorm, _idx)] = Dormitory((dorm, _idx))
                        added.append(f"{dorm}{_idx}")
        return None

    def _init_mood_limit(self) -> None:
        def _set_mood_limit(name, upper_limit=24, lower_limit=0):
            if name in self.operators:
                self.operators[name].upper_limit = float(upper_limit)
                self.operators[name].lower_limit = float(lower_limit)

        if self.config is None:
            return
        if self.config.ling_xi == 1:
            _set_mood_limit("令", upper_limit=12)
            _set_mood_limit("夕", lower_limit=12)
        elif self.config.ling_xi == 2:
            _set_mood_limit("夕", upper_limit=12)
            _set_mood_limit("令", lower_limit=12)
        elif self.config.ling_xi == 0:
            _set_mood_limit("夕")
            _set_mood_limit("令")

        finished = []
        for name in ["夕", "令"]:
            if (
                name in self.operators
                and self.operators[name].group
                and self.operators[name].group not in finished
            ):
                for group_name in self.groups.get(self.operators[name].group, []):
                    if group_name not in ["夕", "令"]:
                        if self.config.ling_xi in [1, 2]:
                            _set_mood_limit(group_name, lower_limit=12)
                        elif self.config.ling_xi == 0:
                            _set_mood_limit(group_name, lower_limit=0)
                finished.append(self.operators[name].group)

        TOTTER = "铅踝"
        VERMEIL = "红云"
        if (
            TOTTER in self.operators
            and self.operators[TOTTER].operator_type == OperatorType.HIGH
        ):
            if (
                VERMEIL in self.operators
                and self.operators[VERMEIL].operator_type == OperatorType.HIGH
                and self.operators[VERMEIL].room == self.operators[TOTTER].room
            ):
                _set_mood_limit(TOTTER, upper_limit=12, lower_limit=8)
            else:
                _set_mood_limit(TOTTER, upper_limit=24, lower_limit=20)
