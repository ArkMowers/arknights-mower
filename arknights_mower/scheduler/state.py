from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Optional

from arknights_mower.data import base_room_list
from arknights_mower.scheduler.domain.operators import Dormitory, Operator
from arknights_mower.scheduler.domain.plan import Plan, PlanConfig, Room
from arknights_mower.scheduler.queue import TaskQueue
from arknights_mower.scheduler.services.plan_service import merge_config
from arknights_mower.scheduler.services.state_services import (
    count_available_free,
    operator_not_valid,
    predict_operator_exhaust,
)
from arknights_mower.scheduler.state_init import StateInitMixin
from arknights_mower.scheduler.state_plan_load import StatePlanLoadMixin


class SchedulerState(StatePlanLoadMixin, StateInitMixin):
    def __init__(self, global_plan: Optional[dict] = None) -> None:
        self.operators: dict[str, Operator] = {}
        self.groups: dict[str, list[str]] = {}
        self.dormitories: dict[tuple[str, int], Dormitory] = {}
        self.task_queue: TaskQueue = TaskQueue()
        self.plan: dict[str, list[Room]] = {}
        self.config: Optional[PlanConfig] = None
        self.planned: bool = False
        self.error: bool = False

        self.exhaust_agent: set[str] = set()
        self.exhaust_group: set[str] = set()
        self.workaholic_agent: set[str] = set()
        self.rest_in_full_group: set[str] = set()
        self.run_order_rooms: dict = {}
        self.power_plant_count: int = 0
        self.true_exhaust_room: set[str] = {"central"}

        self._global_plan = global_plan or {}
        self._from_old_plan()

        self._backup_plans: list[Plan] = self._global_plan.get("backup_plans", [])
        self.plan_condition: list[bool] = []
        self._shadow_copy: dict[str, Operator] = {}

        # C5：无条件调用，对齐 v1 `utils/operators.py:145`。
        # `swap_plan` 在 default_plan 缺失时早退，`_backup_plans` 为空时
        # 循环体不执行，只从 default_plan 深拷贝出 plan/config —— 因此安全。
        self.swap_plan([False] * len(self._backup_plans))

        error = self._init_and_validate()
        if error:
            from arknights_mower.scheduler.errors import ConfigError

            raise ConfigError(error)

    def restore_snapshot(self, data: dict) -> None:
        """Restore operator mood data from snapshot (mode 0/1)."""
        for name, fields in data.items():
            if name not in self.operators:
                continue
            op = self.operators[name]
            op.mood = fields.get("mood", 24.0)
            ts = fields.get("time_stamp")
            if ts:
                op.time_stamp = datetime.fromisoformat(ts)
            op.current_room = fields.get("current_room", "")
            op.current_index = fields.get("current_index", -1)
            op.depletion_rate = fields.get("depletion_rate", 0.0)

    def save_snapshot(self) -> dict:
        """Serialize operator mood data for persistence."""
        data = {}
        for name, op in self.operators.items():
            if op.time_stamp is None:
                continue
            data[name] = {
                "mood": op.mood,
                "time_stamp": op.time_stamp.isoformat(),
                "current_room": op.current_room,
                "current_index": op.current_index,
                "depletion_rate": op.depletion_rate,
            }
        return data

    def save_tasks(self) -> list:
        tasks = []
        for t in self.task_queue.all_tasks():
            tasks.append({
                "time": t.time.isoformat(),
                "type": t.type.value,
                "plan": t.plan,
                "meta_data": t.meta_data,
                "adjusted": t.adjusted,
            })
        return tasks

    def restore_tasks(self, data: list) -> None:
        from arknights_mower.scheduler.domain.task import SchedulerTask, set_type_enum

        for item in data:
            task = SchedulerTask(
                time=datetime.fromisoformat(item["time"]),
                type=set_type_enum(item.get("type", "")),
                plan=item.get("plan", {}),
                meta_data=item.get("meta_data", ""),
                adjusted=item.get("adjusted", False),
            )
            self.task_queue.push(task)

    @property
    def backup_plans(self) -> list[Plan]:
        return self._backup_plans

    def swap_plan(self, condition: list[bool], refresh: bool = False) -> Optional[str]:
        default_plan = self._global_plan.get("default_plan")
        if default_plan is None:
            return None
        self.plan = deepcopy(default_plan.plan)
        self.config = deepcopy(default_plan.config)
        for index, success in enumerate(condition):
            if success:
                self.plan, self.config = self._merge_plan(
                    index, self.config, self.plan
                )
        self.plan_condition = condition
        return None

    def _merge_plan(
        self,
        idx: int,
        ext_config: PlanConfig,
        default_plan: Optional[dict[str, list[Room]]] = None,
    ) -> tuple[dict[str, list[Room]], PlanConfig]:
        if default_plan is None:
            default_plan = deepcopy(self._global_plan["default_plan"].plan)
        backup = deepcopy(self._backup_plans[idx])
        for key, value in backup.plan.items():
            if key in default_plan:
                for i, operator in enumerate(value):
                    if operator.agent != "Current":
                        default_plan[key][i] = operator
        return default_plan, merge_config(ext_config, backup.config)

    def get_dormitory(self, room: str, index: int) -> Optional[Dormitory]:
        return self.dormitories.get((room, index))

    def not_valid(self, operator: Operator) -> bool:
        return operator_not_valid(operator)

    def predict_exhaust(self, operator: Operator) -> datetime:
        return predict_operator_exhaust(operator)

    def available_free(self, free_type: str = "high") -> int:
        return count_available_free(self, free_type)

    def assign_dorm(self, name: str) -> None:
        op = self.operators.get(name)
        if op is None:
            return
        for dorm in self.dormitories.values():
            if dorm.name == "":
                dorm.name = name
                dorm.time = None
                return

    def get_dorm_by_name(self, name: str) -> tuple:
        op = self.operators.get(name)
        if op is None:
            return (None, None)
        key = (op.current_room, op.current_index)
        return key, self.dormitories.get(key)

    def evaluate_expression(self, expression: str) -> bool:
        try:
            from evalidate import Expr, base_eval_model

            model = {e: e for e in base_room_list}
            model["op_data"] = self
            eval_model = base_eval_model.clone()
            eval_model.nodes.extend(["Call", "Attribute", "Is", "IsNot"])
            eval_model.attributes.extend(
                ["operators", "party_time", "is_working", "is_resting", "current_mood", "current_room"]
            )
            return Expr(expression, eval_model).eval(model)
        except Exception:
            return False
