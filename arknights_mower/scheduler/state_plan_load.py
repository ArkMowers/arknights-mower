from __future__ import annotations

from copy import deepcopy
from typing import Optional

from arknights_mower.data import agent_list
from arknights_mower.scheduler.constants import DORM_ROOM_PREFIX, TRADE_ORDER_AGENTS
from arknights_mower.scheduler.domain.plan import BaseProduct, Plan, PlanConfig, Room


class StatePlanLoadMixin:
    """`SchedulerState` 的排班装载 Mixin：旧 plan 转换 + 校验/初始化。

    Mixin 只读写宿主 `SchedulerState` 的字段/方法（含 `StateInitMixin` 提供的
    `_add_operator` / `_build_dormitories` / `_init_mood_limit`），不定义 `__init__`。
    """

    def _from_old_plan(self) -> None:
        from arknights_mower.utils.plan import BaseProduct as OldBaseProduct
        from arknights_mower.utils.plan import Plan as OldPlan

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
                if data.agent in TRADE_ORDER_AGENTS:
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
                if sum(any(char in r for char in TRADE_ORDER_AGENTS) for r in data.replacement) > 1:
                    return f"替换组不可同时安排龙舌兰, 但书或者佩佩 房间->{room_name}, 干员->{data.agent}"
                if "菲亚梅塔" in data.replacement:
                    return f"替换组不可安排菲亚梅塔 房间->{room_name}, 干员->{data.agent}"
                r_count = len(data.replacement)
                if any(char in r for r in data.replacement for char in TRADE_ORDER_AGENTS):
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
            if any(char in op.replacement for op in self.plan[room_name] for char in TRADE_ORDER_AGENTS):
                self.run_order_rooms[room_name] = {}

        for key in self.groups:
            total_count = 0
            _replacement = []
            for name in self.groups[key]:
                candidate = next(
                    (
                        r
                        for r in self.operators[name].replacement
                        if r not in _replacement and r not in TRADE_ORDER_AGENTS
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
