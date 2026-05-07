from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Optional

from arknights_mower.data import agent_arrange_order, agent_list, base_room_list
from arknights_mower.scheduler.constants import DORM_ROOM_PREFIX, FacilityType
from arknights_mower.scheduler.domain.operators import Dormitory, Operator, OperatorType, RestPriority
from arknights_mower.scheduler.domain.plan import BaseProduct, Plan, PlanConfig, Room
from arknights_mower.scheduler.queue import TaskQueue
from arknights_mower.scheduler.services.plan_service import is_refresh_trading, merge_config
from arknights_mower.utils.log import logger

_TRADE_ORDER_AGENTS = ["但书", "龙舌兰", "佩佩", "可露希尔"]


class SchedulerState:
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

        if self._backup_plans:
            self.swap_plan([False] * len(self._backup_plans))

        error = self._init_and_validate()
        if error:
            from arknights_mower.scheduler.errors import ConfigError

            raise ConfigError(error)

    @property
    def backup_plans(self) -> list[Plan]:
        return self._backup_plans

    def _from_old_plan(self) -> None:
        from arknights_mower.utils.plan import (
            BaseProduct as OldBaseProduct,
            Plan as OldPlan,
            PlanConfig as OldPlanConfig,
        )

        def _product_map(p):
            if isinstance(p, OldBaseProduct):
                return BaseProduct(p.value)
            return p

        def _convert_rooms(old_rooms):
            return [
                Room(
                    agent=r.agent,
                    group=r.group,
                    replacement=list(r.replacement),
                    facility=r.facility,
                    product=_product_map(r.product),
                )
                for r in old_rooms
            ]

        def _convert_config(old_config):
            return PlanConfig(
                rest_in_full=list(old_config.rest_in_full),
                exhaust_require=list(old_config.exhaust_require),
                resting_priority=list(old_config.resting_priority),
                ling_xi=old_config.ling_xi,
                workaholic=list(old_config.workaholic),
                free_blacklist=list(old_config.free_blacklist),
                ope_resting_priority=list(old_config.ope_resting_priority),
                resting_threshold=old_config.resting_threshold,
                refresh_trading_config=list(old_config.refresh_trading_config),
                refresh_drained=list(old_config.refresh_drained),
                free_room=old_config.free_room,
            )

        default_plan = self._global_plan.get("default_plan")
        if default_plan is not None and isinstance(default_plan, OldPlan):
            new_config = _convert_config(default_plan.config)
            new_plan_dict = {}
            for room_name, old_rooms in default_plan.plan.items():
                new_plan_dict[room_name] = _convert_rooms(old_rooms)
            trigger_str = (
                str(default_plan.trigger) if default_plan.trigger is not None else ""
            )
            new_default = Plan(
                plan=new_plan_dict,
                config=new_config,
                trigger=trigger_str,
                task=deepcopy(default_plan.task) if default_plan.task else None,
                trigger_timing=default_plan.trigger_timing,
                name=default_plan.name or "",
            )
            self._global_plan["default_plan"] = new_default

        old_backups = self._global_plan.get("backup_plans", [])
        if old_backups and isinstance(old_backups[0], OldPlan):
            new_backups = []
            for bp in old_backups:
                new_config = _convert_config(bp.config)
                new_plan_dict = {}
                for room_name, old_rooms in bp.plan.items():
                    new_plan_dict[room_name] = _convert_rooms(old_rooms)
                trigger_str = str(bp.trigger) if bp.trigger is not None else ""
                new_bp = Plan(
                    plan=new_plan_dict,
                    config=new_config,
                    trigger=trigger_str,
                    task=deepcopy(bp.task) if bp.task else None,
                    trigger_timing=bp.trigger_timing,
                    name=bp.name or "",
                )
                new_backups.append(new_bp)
            self._global_plan["backup_plans"] = new_backups

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

    def need_to_refresh(self, operator: Operator, h: float = 2, r: str = "") -> bool:
        if operator.name in ["歌蕾蒂娅", "见行者"]:
            h = 0.5
        if (
            operator.time_stamp is None
            or (
                operator.time_stamp is not None
                and operator.time_stamp + timedelta(hours=h) < datetime.now()
            )
            or (
                r.startswith(DORM_ROOM_PREFIX)
                and not operator.room.startswith(DORM_ROOM_PREFIX)
            )
        ):
            return True
        return False

    def not_valid(self, operator: Operator) -> bool:
        if operator.room == FacilityType.TRAIN.value:
            return False
        if operator.operator_type == OperatorType.HIGH:
            if operator.workaholic:
                return (
                    operator.current_room != operator.room
                    or operator.index != operator.current_index
                )
            if not operator.room.startswith(
                DORM_ROOM_PREFIX
            ) and operator.current_room.startswith(DORM_ROOM_PREFIX):
                if operator.mood == -1 or operator.mood == 24:
                    return True
                else:
                    return False
            return (
                self.need_to_refresh(operator, 2.5)
                or operator.current_room != operator.room
                or operator.index != operator.current_index
            )
        return False

    def predict_exhaust(self, operator: Operator) -> datetime:
        if (
            operator.workaholic
            or operator.exhaust_require
            or operator.room in [FacilityType.FACTORY.value, FacilityType.TRAIN.value]
        ):
            return datetime.now() + timedelta(hours=24)
        remaining_mood = operator.mood - operator.lower_limit
        depletion_rate = operator.depletion_rate
        if operator.time_stamp and depletion_rate > 0:
            predict = operator.time_stamp + timedelta(
                hours=((remaining_mood / depletion_rate) - 0.5)
            )
            if operator.exhaust_time is not None:
                return min(predict, operator.exhaust_time)
            else:
                return predict
        elif remaining_mood <= 0:
            return datetime.now()
        return datetime.now() + timedelta(hours=24)

    def available_free(self, free_type: str = "high") -> int:
        dorm_count = sum(1 for key in self.plan if key.startswith("dorm"))
        total = len(self.dormitories)
        count_high = 0
        count_low = 0
        for dorm in self.dormitories.values():
            if dorm.name == "" or (dorm.name in self.operators and not self.operators[dorm.name].is_high()):
                continue
            if dorm.name in self.operators:
                op = self.operators[dorm.name]
                if op.is_high_priority():
                    count_high += 1
                else:
                    count_low += 1
        available_high = max(0, dorm_count - count_high)
        available_low = total - count_low - max(count_high, dorm_count)
        return available_high if free_type == "high" else available_low

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

    def _init_and_validate(self, update: bool = False) -> Optional[str]:
        from arknights_mower.utils import config

        self.exhaust_agent = set()
        self.exhaust_group = set()
        self.rest_in_full_group = set()
        self.workaholic_agent = set()
        self._shadow_copy = deepcopy(self.operators)
        self.operators = {}
        self.groups = {}

        for room_name in self.plan:
            for idx, data in enumerate(self.plan[room_name]):
                if data.agent not in agent_list and data.agent != "Free":
                    return f"干员名输入错误: 房间->{room_name}, 干员->{data.agent}"
                if data.agent in _TRADE_ORDER_AGENTS:
                    return f"高效组不可用龙舌兰，但书,佩佩，可露希尔 房间->{room_name}, 干员->{data.agent}"
                if data.agent == "菲亚梅塔" and idx == 1:
                    return f"菲亚梅塔不能安排在2号位置 房间->{room_name}"
                if data.agent == "菲亚梅塔" and not room_name.startswith(DORM_ROOM_PREFIX):
                    return "菲亚梅塔必须安排在宿舍"
                if data.agent == "Free" and not room_name.startswith(DORM_ROOM_PREFIX):
                    return f"Free只能安排在宿舍 房间->{room_name}"
                if data.agent in self.operators and data.agent != "Free":
                    return f"高效组干员不可重复 房间->{room_name},{self.operators[data.agent].room}, 干员->{data.agent}"
                self._add_operator(data, room_name, idx)

        missing_replacements = []
        for room_name in self.plan:
            if room_name.startswith(DORM_ROOM_PREFIX) and len(self.plan[room_name]) != 5:
                return f"宿舍 {room_name} 人数少于5人"
            for idx, data in enumerate(self.plan[room_name]):
                if sum(any(char in r for char in _TRADE_ORDER_AGENTS) for r in data.replacement) > 1:
                    return f"替换组不可同时安排龙舌兰, 但书或者佩佩 房间->{room_name}, 干员->{data.agent}"
                if "菲亚梅塔" in data.replacement:
                    return f"替换组不可安排菲亚梅塔 房间->{room_name}, 干员->{data.agent}"
                r_count = len(data.replacement)
                if any(char in r for r in data.replacement for char in _TRADE_ORDER_AGENTS):
                    r_count -= 1
                if r_count <= 0 and ((data.agent != "Free" and not room_name.startswith(DORM_ROOM_PREFIX)) or data.agent == "菲亚梅塔"):
                    missing_replacements.append(data.agent)
                for rep in data.replacement:
                    if rep not in agent_list and data.agent != "Free":
                        return f"干员名输入错误: 房间->{room_name}, 干员->{rep}"
                    if data.agent != "菲亚梅塔":
                        if rep in self.operators and self.operators[rep].is_high():
                            return f"替换组不可用高效组干员: 房间->{room_name}, 干员->{rep}"
                        self._add_operator(Room(rep, ""), room_name, idx, operator_type="low")
                    else:
                        if rep not in self.operators:
                            return f"菲亚梅塔替换不在高效组列: 房间->{room_name}, 干员->{rep}"
                        if rep in self.operators and not self.operators[rep].is_high():
                            return f"菲亚梅塔替换只能为高效组干员: 房间->{room_name}, 干员->{rep}"
        if "菲亚梅塔" in missing_replacements:
            return "菲亚梅塔替换缺失"
        if missing_replacements:
            return f"以下干员替换组缺失：{','.join(missing_replacements)}"

        error = self._build_dormitories(update)
        if error:
            return error

        if not update:
            if config.conf.dorm_order == "":
                config.conf.dorm_order = ",".join(
                    f"{dorm.position[0]}_{dorm.position[1]}"
                    for dorm in self.dormitories.values()
                )
                config.save_conf()
            else:
                dorm_order = config.conf.dorm_order.split(",")
                current = {
                    f"{d.position[0]}_{d.position[1]}"
                    for d in self.dormitories.values()
                }
                saved = set(dorm_order)
                if saved != current:
                    return "宿舍优先级和当前宿舍不匹配，请清除优先级自动排序或者自己更正"
                items = list(self.dormitories.items())
                items.sort(
                    key=lambda kv: dorm_order.index(
                        f"{kv[1].position[0]}_{kv[1].position[1]}"
                    )
                )
                self.dormitories = dict(items)
        else:
            for key, value in self._shadow_copy.items():
                if key not in self.operators:
                    self._add_operator(
                        Room(value.name, ""),
                        value.room,
                        value.index,
                        operator_type=value.operator_type.value,
                    )

        for room_name in self.plan:
            if not room_name.startswith("room"):
                continue
            if any(char in op.replacement for op in self.plan[room_name] for char in _TRADE_ORDER_AGENTS):
                self.run_order_rooms[room_name] = {}

        for key in self.groups:
            total_count = 0
            _replacement = []
            for name in self.groups[key]:
                candidate = next(
                    (
                        r
                        for r in self.operators[name].replacement
                        if r not in _replacement and r not in _TRADE_ORDER_AGENTS
                    ),
                    None,
                )
                if candidate is None:
                    return f"{key} 分组无法排班,替换组数量不够"
                _replacement.append(candidate)
                if self.operators[name].workaholic:
                    continue
                total_count += 1
            if total_count > len(self.dormitories):
                return f"{key} 分组无法排班,分组总数(不包含0心情工作){total_count}大于总宿舍数{len(self.dormitories)}"

        self._init_mood_limit()
        if self.config:
            for name in self.workaholic_agent:
                if name not in self.config.free_blacklist:
                    self.config.free_blacklist.append(name)
        self.power_plant_count = sum(
            1
            for room in self.plan.values()
            if room and room[0].product == BaseProduct.ELECTRICITY
        )
        return None

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
