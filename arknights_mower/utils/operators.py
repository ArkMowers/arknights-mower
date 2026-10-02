import ast
import copy
from datetime import datetime, timedelta
from typing import Any, Literal, overload

from evalidate import Expr, base_eval_model

from arknights_mower.utils import config
from arknights_mower.utils.manufacture_product import (
    MANUFACTURE_PRODUCTS,
    TRADE_PRODUCTS,
)
from arknights_mower.utils.plan import BaseProduct, PlanConfig
from arknights_mower.utils.resting_priority import (
    RestingTier,
    has_resting_mood,
    resting_key,
    resting_mood,
    resting_tier,
)

from ..data import agent_arrange_order, agent_list, base_room_list
from ..solvers.record import get_inventory_counts, save_action_to_sqlite_decorator
from ..utils.log import logger
from ..utils.news_checker import NewsChecker

# 赤金交易订单干员常量
TRADE_ORDER_AGENTS = ["但书", "龙舌兰", "佩佩", "可露希尔"]
DORMITORY_ROOMS = [f"dormitory_{index}" for index in range(1, 5)]
MAX_BACKUP_VALIDATION_COMBINATIONS = 16384
FACILITY_TYPE_IDS = {
    "贸易站": "trade",
    "制造站": "manufacture",
    "发电站": "power",
}

_MAX_EXPRESSION_LENGTH = 2048
_MAX_EXPRESSION_NODES = 128
_MAX_INTEGER_LITERAL_BITS = 256
_MAX_STRING_LITERAL_LENGTH = 512
_MAX_POWER_EXPONENT = 64
_MAX_NUMERIC_RESULT_BITS = 4096
_NUMERIC_EXPRESSION_CALLS = {
    "current_mood",
    "facility_operator_count",
    "facility_product_count",
    "facility_product_type_count",
    "group_max_mood",
    "group_min_mood",
    "inventory_count",
    "major_maintenance_remaining_hours",
}


def dorm_room_order(values, rooms=None):
    """将旧床位顺序折叠为宿舍房间顺序。

    旧值如 ``dormitory_2_3`` 保留其首次出现的房间；缺失的房间
    按 1→4 补齐。这样升级后仍保留原先的房间相对优先级，同时
    床位数随主副表变化时不再使排序失效。
    """
    rooms = list(rooms or DORMITORY_ROOMS)
    result = []
    for value in values:
        room = value
        parts = value.rsplit("_", 1)
        if len(parts) == 2 and parts[0] in rooms and parts[1].isdigit():
            room = parts[0]
        if room in rooms and room not in result:
            result.append(room)
    result.extend(room for room in rooms if room not in result)
    return result


def _integer_literal(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, (ast.UAdd, ast.USub))
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, int)
    ):
        value = node.operand.value
        return value if isinstance(node.op, ast.UAdd) else -value
    return None


def _numeric_result_bits(node: ast.AST) -> int | None:
    """保守估算整数结果位数；非数值或无法确定时返回 None。"""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return 1
        if isinstance(node.value, int):
            return max(1, node.value.bit_length())
        if isinstance(node.value, (float, complex)):
            return 64
        return None
    if isinstance(node, ast.UnaryOp):
        return _numeric_result_bits(node.operand)
    if isinstance(node, (ast.Compare, ast.BoolOp)):
        return 1
    if isinstance(node, ast.IfExp):
        body_bits = _numeric_result_bits(node.body)
        else_bits = _numeric_result_bits(node.orelse)
        if body_bits is None or else_bits is None:
            return None
        return max(body_bits, else_bits)
    if isinstance(node, ast.BinOp):
        left_bits = _numeric_result_bits(node.left)
        right_bits = _numeric_result_bits(node.right)
        if left_bits is None or right_bits is None:
            return None
        if isinstance(node.op, ast.Pow):
            exponent = _integer_literal(node.right)
            if exponent is None or not 0 <= exponent <= _MAX_POWER_EXPONENT:
                return None
            return max(1, left_bits * exponent)
        if isinstance(node.op, ast.Mult):
            return left_bits + right_bits
        if isinstance(node.op, (ast.Add, ast.Sub)):
            return max(left_bits, right_bits) + 1
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            return max(left_bits, right_bits)
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return 64 if node.func.attr in _NUMERIC_EXPRESSION_CALLS else None
    return None


def _validate_expression_resources(expression: str) -> None:
    """在 evalidate 执行前拦截可能产生超大中间值的表达式。"""
    if len(expression) > _MAX_EXPRESSION_LENGTH:
        raise ValueError("表达式过长")
    tree = ast.parse(expression, mode="eval")
    nodes = list(ast.walk(tree))
    if len(nodes) > _MAX_EXPRESSION_NODES:
        raise ValueError("表达式过于复杂")

    for node in nodes:
        if isinstance(node, ast.Constant):
            if (
                isinstance(node.value, int)
                and node.value.bit_length() > _MAX_INTEGER_LITERAL_BITS
            ):
                raise ValueError("整数常量过大")
            if (
                isinstance(node.value, (str, bytes))
                and len(node.value) > _MAX_STRING_LITERAL_LENGTH
            ):
                raise ValueError("字符串常量过长")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            result_bits = _numeric_result_bits(node)
            if result_bits is None:
                raise ValueError("乘法仅支持数值表达式")
            if result_bits > _MAX_NUMERIC_RESULT_BITS:
                raise ValueError("乘法结果过大")
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
            exponent = _integer_literal(node.right)
            result_bits = _numeric_result_bits(node)
            if exponent is None or not 0 <= exponent <= _MAX_POWER_EXPONENT:
                raise ValueError(
                    f"幂运算指数必须是 0 到 {_MAX_POWER_EXPONENT} 的整数常量"
                )
            if result_bits is None or result_bits > _MAX_NUMERIC_RESULT_BITS:
                raise ValueError("幂运算结果过大")


@overload
def build_global_plan(*, include_source: Literal[False] = False) -> dict[str, Any]: ...


@overload
def build_global_plan(
    *, include_source: Literal[True]
) -> tuple[dict[str, Any], dict[str, Any]]: ...


def build_global_plan(
    *, include_source: bool = False
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
    """构建完整的 global_plan，包括 Plan 对象，用于运行时"""
    from ..utils import config
    from ..utils.logic_expression import get_logic_exp
    from ..utils.plan import Plan, PlanConfig, Room

    plan1 = {}
    default_products = {}
    source_model = config.plan.model_copy(deep=True)
    plan = source_model.model_dump(exclude_none=True)
    source_plan = copy.deepcopy(plan) if include_source else None
    conf = config.conf
    plan_config = PlanConfig(
        rest_in_full=source_model.conf.rest_in_full,
        exhaust_require=source_model.conf.exhaust_require,
        resting_priority=source_model.conf.resting_priority,
        resting_priority_replacement=source_model.conf.resting_priority_replacement,
        free_room_exclusions=source_model.conf.free_room_exclusions,
        resting_standby=source_model.conf.resting_standby,
        ling_xi=source_model.conf.ling_xi,
        mood_limits=plan["conf"].get("mood_limits"),
        operator_mood_limits=plan["conf"].get("operator_mood_limits", {}),
        workaholic=source_model.conf.workaholic,
        free_blacklist=conf.free_blacklist,
        ope_resting_priority=source_model.conf.ope_resting_priority,
        dorm_order=source_model.conf.dorm_order,
        resting_threshold=conf.resting_threshold,
        refresh_trading_config=source_model.conf.refresh_trading,
        refresh_drained=source_model.conf.refresh_drained,
        free_room=conf.free_room,
    )
    for room, obj in plan[plan["default"]].items():
        if product_id := obj.get("product"):
            default_products[room] = product_id
        plan1[room] = [
            Room(
                op["agent"],
                op["group"],
                op["replacement"],
                obj["name"],
                obj["product"] if "product" in obj else "",
            )
            for op in obj["plans"]
        ]
    # 默认任务
    plan["default_plan"] = Plan(plan1, plan_config, products=default_products)
    # 备用自定义任务
    backup_plans: list[Plan] = []

    for i in plan["backup_plans"]:
        backup_plan: dict[str, Room] = {}
        backup_products = {}
        for room, obj in i["plan"].items():
            if product_id := obj.get("product"):
                backup_products[room] = product_id
            backup_plan[room] = [
                Room(
                    op["agent"],
                    op["group"],
                    op["replacement"],
                    obj["name"],
                    obj["product"] if "product" in obj else "",
                )
                for op in obj["plans"]
            ]
        backup_config = PlanConfig(
            i["conf"]["rest_in_full"],
            i["conf"]["exhaust_require"],
            i["conf"]["resting_priority"],
            ling_xi=i["conf"]["ling_xi"],
            mood_limits=i["conf"].get("mood_limits"),
            operator_mood_limits=i["conf"].get("operator_mood_limits", {}),
            workaholic=i["conf"]["workaholic"],
            free_blacklist=i["conf"]["free_blacklist"],
            ope_resting_priority=i["conf"]["ope_resting_priority"],
            dorm_order=i["conf"].get("dorm_order", ""),
            dorm_order_override=i["conf"].get("dorm_order_override", False),
            resting_standby=i["conf"].get("resting_standby", ""),
            free_room_exclusions=i["conf"].get("free_room_exclusions", ""),
            resting_priority_replacement=i["conf"].get(
                "resting_priority_replacement", ""
            ),
            resting_threshold=conf.resting_threshold,
            refresh_trading_config=i["conf"]["refresh_trading"],
            refresh_drained=i["conf"]["refresh_drained"],
            free_room=conf.free_room,
        )
        backup_trigger = get_logic_exp(i["trigger"]) if "trigger" in i else None
        backup_task = i.get("task")
        backup_plans.append(
            Plan(
                backup_plan,
                backup_config,
                trigger=backup_trigger,
                task=backup_task,
                name=i.get("name"),
                products=backup_products,
            )
        )
    plan["backup_plans"] = backup_plans

    return (plan, source_plan) if include_source else plan


class Operators:
    config = None
    operators = None
    groups = None
    dorm = []
    plan = None

    global_plan = None
    plan_condition = []
    shadow_copy = {}
    current_room_changed_callback = None
    first_init = True

    def __init__(self, plan):
        self.operators = {}
        self.groups = {}
        self.exhaust_agent = set()
        self.exhaust_group = set()
        self.rest_in_full_group = set()
        self.dorm = []
        self.displaced_dorms = []
        self.group_dorm = []
        self.idle_dorm_search_exhausted = False
        self.idle_dorm_search_stopped_at = None
        self.dorm_mood_estimates = {}
        self.emergency_dorm_agents = set()
        self.workaholic_agent = set()
        self.free_blacklist = []
        self.global_plan = plan
        self.backup_plans = plan["backup_plans"]
        # 切换默认排班
        self.swap_plan([False] * (len(self.backup_plans)))
        self.run_order_rooms = {}
        self.clues = []
        self.current_room_changed_callback = None
        self.party_time = None
        self.facility_states = {}
        self.reserved_product_beds = {}
        self.reserved_product_replacements = set()
        self.profession_filter = set(agent_arrange_order["职介选择开关"])
        self.eval_model = base_eval_model.clone()
        self.eval_model.nodes.extend(
            ["Call", "Attribute", "Is", "IsNot", "Mult", "FloorDiv", "Pow"]
        )
        self.eval_model.attributes.extend(
            [
                "operators",
                "party_time",
                "is_working",
                "is_resting",
                "current_mood",
                "current_room",
                "inventory_count",
                "facility_type",
                "facility_product",
                "facility_operator_count",
                "facility_product_count",
                "facility_product_type_count",
                "facility_has_mastery_plan",
                "facility_is_training",
                "major_maintenance_remaining_hours",
                "group_min_mood",
                "group_max_mood",
            ]
        )
        self.power_plant_count = 0
        self.true_exhaust_room = set(["central"])

    def __repr__(self):
        return f"Operators(operators={self.operators})"

    @property
    def run_order_paused(self) -> bool:
        return bool(self.maintenance_primary_slots)

    def swap_plan(self, condition, refresh=False):
        self.emergency_dorm_agents.clear()
        self.plan = copy.deepcopy(self.global_plan["default_plan"].plan)
        self.products = copy.deepcopy(self.global_plan["default_plan"].products)
        self.config: PlanConfig = copy.deepcopy(self.global_plan["default_plan"].config)
        self.maintenance_primary_slots = set()
        for index, success in enumerate(condition):
            if success:
                self.plan, self.config = self.merge_plan(index, self.config, self.plan)
                backup = self.global_plan["backup_plans"][index]
                self.products.update(backup.products)
                maintenance = backup.uses_major_maintenance_condition
                for room, slots in backup.plan.items():
                    if room not in self.plan:
                        continue
                    for slot_index, slot in enumerate(slots):
                        if slot.agent == "Current":
                            continue
                        self.maintenance_primary_slots.discard((room, slot_index))
                        if maintenance and slot.agent in TRADE_ORDER_AGENTS:
                            self.maintenance_primary_slots.add((room, slot_index))
        self.plan_condition = condition
        if refresh:
            self.first_init = True
            error = self.init_and_validate(True)
            self.first_init = False
            if error:
                return error

    def merge_plan(self, idx, ext_config, default_plan=None):
        if default_plan is None:
            default_plan = copy.deepcopy(self.global_plan["default_plan"].plan)
        plan = copy.deepcopy(self.global_plan["backup_plans"][idx])
        # 更新切换排班表
        for key, value in plan.plan.items():
            if key in default_plan:
                for idx, operator in enumerate(value):
                    if operator.agent != "Current":
                        default_plan[key][idx] = operator
        return default_plan, ext_config.merge_config(plan.config)

    def init_and_validate(self, update=False):
        for name in self.config.operator_mood_limits:
            if name not in agent_list:
                return f"心情上下限中的干员名无效：{name}"
        saved_dorms = copy.deepcopy(self.all_dorms()) if (update) else []
        self.displaced_dorms = []
        self.groups = {}
        self.exhaust_agent = set()
        self.exhaust_group = set()
        self.rest_in_full_group = set()
        self.workaholic_agent = set()
        self.shadow_copy = copy.deepcopy(self.operators)
        self.operators = {}
        self.dorm = []
        self.group_dorm = []
        for room in self.plan.keys():
            for idx, data in enumerate(self.plan[room]):
                if data.agent not in agent_list and data.agent != "Free":
                    return f"干员名输入错误: 房间->{room}, 干员->{data.agent}"
                if (
                    data.agent in TRADE_ORDER_AGENTS
                    and (room, idx) not in self.maintenance_primary_slots
                ):
                    return f"高效组不可用龙舌兰，但书,佩佩，可露希尔 房间->{room}, 干员->{data.agent}"
                if data.agent == "菲亚梅塔" and idx == 1:
                    return f"菲亚梅塔不能安排在2号位置 房间->{room}, 干员->{data.agent}"
                if data.agent == "菲亚梅塔" and not room.startswith("dorm"):
                    return "菲亚梅塔必须安排在宿舍"
                if data.agent == "Free" and not room.startswith("dorm"):
                    return f"Free只能安排在宿舍 房间->{room}, 干员->{data.agent}"
                if data.group and data.agent in ["Free", "菲亚梅塔"]:
                    return f"{data.agent}不能参与宿舍绑组换班"
                if data.agent in self.operators and data.agent != "Free":
                    return f"高效组干员不可重复 房间->{room},{self.operators[data.agent].room}, 干员->{data.agent}"
                self.add(
                    Operator(
                        data.agent,
                        room,
                        idx,
                        data.group,
                        data.replacement,
                        "high",
                        operator_type="high",
                    )
                )
        missing_replacements = []
        for room in self.plan.keys():
            if room.startswith("dorm") and len(self.plan[room]) != 5:
                return f"宿舍 {room} 人数少于5人"
            for idx, data in enumerate(self.plan[room]):
                # 菲亚梅塔替换组做特例判断
                if (
                    sum(
                        [
                            any(
                                char in replacement_str
                                for replacement_str in data.replacement
                            )
                            for char in TRADE_ORDER_AGENTS
                        ]
                    )
                    > 1
                ):
                    return f"替换组不可同时安排龙舌兰, 但书或者佩佩 房间->{room}, 干员->{data.agent}"
                if "菲亚梅塔" in data.replacement:
                    return f"替换组不可安排菲亚梅塔 房间->{room}, 干员->{data.agent}"
                r_count = len(data.replacement)
                if any(
                    char in replacement_str
                    for replacement_str in data.replacement
                    for char in TRADE_ORDER_AGENTS
                ):
                    r_count -= 1
                if r_count <= 0 and (
                    (data.agent != "Free" and (not room.startswith("dorm")))
                    or data.agent == "菲亚梅塔"
                ):
                    missing_replacements.append(data.agent)
                for _replacement in data.replacement:
                    explicit_free = (
                        (room.startswith("dorm"))
                        and bool(data.group)
                        and data.agent not in ("Free", "菲亚梅塔")
                        and _replacement == "Free"
                    )
                    if _replacement == "Free" and not explicit_free:
                        return f"Free替换只能用于绑组宿舍干员: 房间->{room}"
                    if explicit_free:
                        continue
                    if _replacement not in agent_list and data.agent != "Free":
                        return f"干员名输入错误: 房间->{room}, 干员->{_replacement}"
                    if data.agent != "菲亚梅塔":
                        # 暂停跑单时保留原表的跑单标记，不将主班降为替班。
                        if (
                            self.run_order_paused
                            and _replacement in TRADE_ORDER_AGENTS
                            and _replacement in self.operators
                            and self.operators[_replacement].is_high()
                        ):
                            continue
                        # 普通替换
                        if (
                            _replacement in self.operators
                            and self.operators[_replacement].is_high()
                        ):
                            return f"替换组不可用高效组干员: 房间->{room}, 干员->{_replacement}"
                        self.add(Operator(_replacement, ""))
                    else:
                        if _replacement not in self.operators:
                            return f"菲亚梅塔替换不在高效组列: 房间->{room}, 干员->{_replacement}"
                        if (
                            _replacement in self.operators
                            and not self.operators[_replacement].is_high()
                        ):
                            return f"菲亚梅塔替换只能为高效组干员: 房间->{room}, 干员->{_replacement}"
        # 判定替换缺失
        if "菲亚梅塔" in missing_replacements:
            return "菲亚梅塔替换缺失"
        if len(missing_replacements):
            return f"以下干员替换组缺失：{','.join(missing_replacements)}"
        # 床位集合由当前合并后的排班生成；因此副表
        # 可以增减 Free 位置。宿舍常驻成员的替换显式填写 Free 时，该
        # 固定位在常驻成员随组离岗期间也作为动态 Free 床位。
        bed_plan = self.plan
        dorm_names = [k for k in bed_plan.keys() if k.startswith("dorm")]
        dorm_names.sort(key=lambda d: d, reverse=False)
        added = []
        # 竖向遍历出效率高到低
        for dorm in dorm_names:
            free_found = False
            for _idx, _dorm in enumerate(bed_plan[dorm]):
                if _dorm.agent == "Free" and _idx <= 1:
                    if "波登可" not in [_agent.agent for _agent in bed_plan[dorm]]:
                        return "宿舍必须安排2个宿管"
                # The merged backup may replace individual Free beds.
                if _dorm.agent != "Free" and free_found and not (update):
                    return "Free必须连续且安排在宿管后"
                if (
                    _dorm.agent == "Free"
                    and not free_found
                    and (dorm + str(_idx)) not in added
                ):
                    self.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
                    free_found = True
                    continue
            if not free_found:
                return "宿舍必须安排至少一个Free"
        # 稳定逻辑保留原先的“每间宿舍首张 Free 优先”排序。
        for dorm in dorm_names:
            for _idx, _dorm in enumerate(bed_plan[dorm]):
                if _dorm.agent == "Free" and (dorm + str(_idx)) not in added:
                    self.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
        for dorm in dorm_names:
            for index, _slot in enumerate(bed_plan[dorm]):
                key = dorm + str(index)
                if self.is_auto_free_dorm_slot(dorm, index) and key not in added:
                    self.dorm.append(Dormitory((dorm, index)))
                    added.append(key)
        if update:
            for key, value in self.shadow_copy.items():
                if key not in self.operators:
                    self.add(Operator(key, ""))
        room_order = dorm_room_order(self.config.dorm_order)
        self.config.dorm_order = room_order
        self.dorm.sort(
            key=lambda dorm: (
                room_order.index(dorm.position[0]),
                dorm.position[1],
            )
        )
        self.refresh_run_order_rooms()
        for key in self.groups:
            total_count = 0
            _replacement = []
            for name in self.groups[key]:
                operator = self.operators[name]
                if self.is_auto_free_dorm_operator(operator):
                    # 显式 Free 只负责开启“随组离岗时转为 Free”，不参与
                    # 组内替班唯一性校验。
                    continue
                _candidate = next(
                    (
                        r
                        for r in self.operators[name].replacement
                        if r not in _replacement and r not in TRADE_ORDER_AGENTS
                    ),
                    None,
                )
                if _candidate is None:
                    return f"{key} 分组无法排班,替换组数量不够"
                else:
                    _replacement.append(_candidate)
                if self.operators[name].workaholic or self.operators[
                    name
                ].room.startswith("dorm"):
                    continue
                total_count += 1
            if (
                any(self.operators[n].room.startswith("dorm") for n in self.groups[key])
                and not total_count
            ):
                return f"{key} 宿舍绑组需要至少一名可轮休的非宿舍干员"
            required_beds = total_count
            effective_dorm_count = sum(
                1
                for dorm in self.dorm
                if self.is_effective_free_slot(dorm, active_groups=({key}))
            )
            if required_beds > effective_dorm_count:
                return f"{key} 分组无法排班,所需宿舍数{required_beds}大于当前有效宿舍数{effective_dorm_count}"
        self.group_dorm = []
        if update:
            self.displaced_dorms = self.restore_dorm_state(saved_dorms)
        # 应用心情上下限：个人设置优先，其次令夕模式、全体设置。
        self.init_mood_limit()
        for name in self.workaholic_agent:
            if name not in self.config.free_blacklist:
                self.config.free_blacklist.append(name)
        self.power_plant_count = sum(
            1
            for room in self.plan.values()
            if room and room[0].product == BaseProduct.Electricity
        )
        self.refresh_dorm_manager_flags(force=True)

    def refresh_dorm_manager_flags(self, *, force=False):
        """只标记宿舍前两位及其替班；资源未变时不再匹配。"""
        from arknights_mower.utils import dorm_skills

        if not force and getattr(self, "_dorm_skill_generation", -1) == (
            dorm_skills.resource_generation
        ):
            return
        planned = {
            name
            for room, slots in self.plan.items()
            if room.startswith("dorm")
            for slot in slots[:2]
            for name in (slot.agent, *slot.replacement)
            if name in self.operators
        }
        for name, op in self.operators.items():
            op.single_recovery_manager = name in planned and (
                dorm_skills.is_single_recovery_manager(name)
            )
        self._dorm_skill_generation = dorm_skills.resource_generation

    def set_mood_limit(self, name, upper_limit=24, lower_limit=0):
        if name in self.operators and self.is_planned_operator(name):
            self.operators[name].upper_limit = upper_limit
            self.operators[name].lower_limit = lower_limit

    def has_rest_mood_limit(self, name):
        """仅个人设置和令夕上限强制离宿；全体设置是回满目标。"""
        return self.is_planned_operator(name) and (
            (name in self.config.operator_mood_limits)
            or name == {1: "令", 2: "夕"}.get(self.config.ling_xi)
        )

    def is_planned_operator(self, name):
        return name in self.emergency_dorm_agents or any(
            name == slot.agent or name in slot.replacement
            for slots in self.plan.values()
            for slot in slots
        )

    def custom_mood_limits(self, name):
        return (
            self.config.custom_mood_limits(name)
            if (self.is_planned_operator(name))
            else None
        )

    def rest_mood_complete(self, name):
        op = self.operators.get(name)
        return (
            self.has_rest_mood_limit(name)
            and op is not None
            and has_resting_mood(op)
            and (
                resting_mood(op) >= op.upper_limit
                or (not op.current_room)
                and getattr(op, "rest_mood_release_limit", None) == op.upper_limit
            )
        )

    def is_free_room_excluded(self, name):
        """名单内入住者不被清退或接管床位；达到个人上限仍须离宿。"""
        return (
            (bool(name))
            and getattr(self.config, "free_room", False)
            and name in getattr(self.config, "free_room_exclusions", ())
            and resting_tier(self, name) != RestingTier.EXCLUDED
            and not self.rest_mood_complete(name)
        )

    def stop_idle_dorm_search(self, now=None):
        """最低候选实读也已满时关闭共享搜索；重复读数不延长等待。"""
        if not self.idle_dorm_search_exhausted:
            self.idle_dorm_search_exhausted = True
            self.idle_dorm_search_stopped_at = now or datetime.now()
            logger.info("游戏最低心情候选也已回满，停止本轮主动查找休息者")

    def refresh_idle_dorm_search(self, reason=None, now=None, *, names=None):
        """事件只刷新相关候选；停止满 1 小时后刷新全部候选。"""
        now = now or datetime.now()
        if reason is None:
            if (
                not self.idle_dorm_search_exhausted
                or self.idle_dorm_search_stopped_at is None
                or now - self.idle_dorm_search_stopped_at < timedelta(hours=1)
            ):
                return False
            reason = "停止搜索已满 1 小时"
        self.idle_dorm_search_exhausted = False
        self.idle_dorm_search_stopped_at = None
        if names is None:
            self.dorm_mood_estimates.clear()
            names = self.operators
        else:
            names = set(names)
            for name in names:
                self.dorm_mood_estimates.pop(name, None)
        # 不动床位及预计回满时间，只撤销上一轮搜索产生的临时保护。
        for name in names:
            op = self.operators.get(name)
            if op is None:
                continue
            op.dorm_mood_fallback = ""
            op.dorm_mood_peers = {}
            op.idle_rest_check = None
        logger.info(f"重新开放宿舍空闲干员搜索：{reason}")
        return True

    def is_full_dorm_fallback(self, name):
        """游戏心情升序选出的替班也已满时，停止本轮无效清退。"""
        op = self.operators.get(name)
        return bool(
            (self.config.free_room)
            and op is not None
            and op.current_room.startswith("dorm")
            and getattr(op, "dorm_mood_fallback", "") == op.current_room
            and resting_tier(self, name) != RestingTier.EXCLUDED
            and has_resting_mood(op)
            and resting_mood(op) >= op.upper_limit
            and not self.has_rest_mood_limit(name)
        )

    def skip_idle_dorm_release(self, name):
        return self.is_free_room_excluded(name) or self.is_full_dorm_fallback(name)

    def idle_rest_checked(self, name):
        """同批最低者也达到上限后，空闲期间不重复试住；不伪造缓存心情。"""
        op = self.operators.get(name)
        checked = getattr(op, "idle_rest_check", None)
        return bool(
            (op is not None)
            and not op.current_room
            and checked is not None
            and checked[0] >= op.upper_limit
            and checked[1:] == (op.mood, op.time_stamp)
        )

    def apply_custom_mood_limits(self, operator):
        limits = self.custom_mood_limits(operator.name)
        if limits is not None:
            self.set_mood_limit(
                operator.name, lower_limit=limits["lower"], upper_limit=limits["upper"]
            )

    def apply_ling_xi_mood_limits(self):
        # 设置心情阈值 for 夕，令，
        if self.config.ling_xi == 1:
            self.set_mood_limit("令", upper_limit=12)
            self.set_mood_limit("夕", lower_limit=12)
        elif self.config.ling_xi == 2:
            self.set_mood_limit("夕", upper_limit=12)
            self.set_mood_limit("令", lower_limit=12)
        elif self.config.ling_xi in (0, 3):
            self.set_mood_limit("夕")
            self.set_mood_limit("令")
        # 设置同组心情阈值
        finished = []
        for name in ["夕", "令"]:
            if (
                name in self.operators
                and not self.operators[name].room.startswith("dorm")
                and self.operators[name].group != ""
                and self.operators[name].group not in finished
            ):
                for group_name in self.groups.get(self.operators[name].group, []):
                    if group_name not in ["夕", "令"] and not self.operators[
                        group_name
                    ].room.startswith("dorm"):
                        if self.config.ling_xi in [1, 2]:
                            self.set_mood_limit(group_name, lower_limit=12)
                        elif self.config.ling_xi in (0, 3):
                            self.set_mood_limit(group_name, lower_limit=0)
                finished.append(self.operators[name].group)
        for name, limits in self.config.operator_mood_limits.items():
            self.set_mood_limit(
                name, lower_limit=limits["lower"], upper_limit=limits["upper"]
            )

    def init_mood_limit(self):
        previous = getattr(self, "_applied_mood_limits", {})
        for op in self.operators.values():
            op.lower_limit, op.upper_limit = 0, 24
        self.apply_ling_xi_mood_limits()

        # 设置铅踝心情阈值
        # 三种情况：
        # 1. 铅踝不是主力：不管
        # 2. 铅踝是红云组主力，设置心情上限 12、下限 8，效率 37%
        # 3. 铅踝是普通主力：设置心情下限 20，效率 30%
        TOTTER = "铅踝"
        VERMEIL = "红云"
        if TOTTER in self.operators and self.operators[TOTTER].operator_type == "high":
            if (
                VERMEIL in self.operators
                and self.operators[VERMEIL].operator_type == "high"
                and self.operators[VERMEIL].room == self.operators[TOTTER].room
            ):
                self.set_mood_limit(TOTTER, upper_limit=12, lower_limit=8)
            else:
                self.set_mood_limit(TOTTER, upper_limit=24, lower_limit=20)

        for op in self.operators.values():
            self.apply_custom_mood_limits(op)
        # 按个人设置、令夕模式、全体设置的优先顺序收敛。
        self.apply_ling_xi_mood_limits()
        # 已读倒计时指向旧上限，切表后按同一恢复速度换算到新上限。
        for bed in self.all_dorms():
            op = self.operators.get(bed.name)
            if op is None or bed.time is None:
                continue
            old_upper = previous.get(op.name, op.upper_limit)
            if old_upper == op.upper_limit:
                continue
            if not has_resting_mood(op):
                bed.time = None
                op.time_stamp = None
            elif op.mood >= op.upper_limit:
                bed.time = datetime.now()
            elif old_upper > op.mood:
                bed.time = op.time_stamp + (bed.time - op.time_stamp) * (
                    (op.upper_limit - op.mood) / (old_upper - op.mood)
                )
            else:
                # 旧目标已完成，无法反推恢复速度，交给现有读房流程重采样。
                bed.time = None
                op.time_stamp = None
        self._applied_mood_limits = {
            name: op.upper_limit for name, op in self.operators.items()
        }

    def evaluate_expression(self, expression):
        try:
            _validate_expression_resources(expression)
            model = {e: e for e in base_room_list}
            model.update({e: e for e in MANUFACTURE_PRODUCTS | TRADE_PRODUCTS})
            model.update({e: e for e in FACILITY_TYPE_IDS.values()})
            model["op_data"] = self
            result = Expr(expression, self.eval_model).eval(model)
            return result
        except Exception as e:
            logger.exception(f"附表格式出错: {e}")
            return None

    def inventory_count(self, item_name: str) -> int:
        """返回副表条件可用的仓库数量。"""
        if item_name == "全部经验（计算）":
            experience_values = {
                "基础作战记录": 200,
                "初级作战记录": 400,
                "中级作战记录": 1000,
                "高级作战记录": 2000,
            }
            counts = get_inventory_counts(list(experience_values))
            return sum(
                counts.get(name, 0) * value for name, value in experience_values.items()
            )
        allowed_items = {"赤金", "源石碎片", "固源岩", "装置", "龙门币"}
        if item_name not in allowed_items:
            raise ValueError(f"不支持的副表仓库资源：{item_name}")
        return get_inventory_counts([item_name]).get(item_name, 0)

    def major_maintenance_remaining_hours(self) -> float:
        """返回停服大更新开始前的小时数；已停服时条件不成立。"""
        info = NewsChecker.get_maintenance()
        if info is None or info.update_type != "major" or info.is_flash_update:
            return float("inf")
        hours = (info.start - datetime.now()).total_seconds() / 3600
        return hours if hours > 0 else float("inf")

    def next_major_maintenance_check(self, now=None):
        """在维护条件阈值时唤醒调度器；停服由现有维护流程接管。"""
        thresholds = [
            hours
            for backup in self.backup_plans
            for hours in backup.major_maintenance_thresholds
        ]
        if not thresholds:
            return None
        info = NewsChecker.get_maintenance()
        if info is None or info.update_type != "major" or info.is_flash_update:
            return None
        now = now or datetime.now()
        times = []
        for hours in thresholds:
            try:
                times.append(info.start - timedelta(hours=hours))
            except OverflowError:
                # 极大的提前量已成立，不需要安排未来的阈值检查。
                continue
        return min((time for time in times if time > now), default=None)

    def _group_moods(self, group: str) -> list[float]:
        members = self.groups.get(group)
        if not members:
            raise ValueError(f"不存在的绑组：{group}")
        moods = [
            self.operators[name].current_mood()
            for name in members
            if not self.operators[name].workaholic
        ]
        if not moods:
            raise ValueError(f"绑组内没有可统计心情的干员：{group}")
        return moods

    def group_min_mood(self, group: str) -> float:
        """排除0心情工作干员后返回指定绑组的最小心情。"""
        return min(self._group_moods(group))

    def group_max_mood(self, group: str) -> float:
        """排除0心情工作干员后返回指定绑组的最大心情。"""
        return max(self._group_moods(group))

    def update_facility_state(
        self, room: str, facility: str, product: str, updated_at: str | None = None
    ) -> None:
        """记录生产设施最近一次从游戏界面识别到的实际状态。"""
        supported = (facility == "manufacture" and product in MANUFACTURE_PRODUCTS) or (
            facility == "trade" and product in TRADE_PRODUCTS
        )
        if room not in base_room_list or not supported:
            raise ValueError(f"不支持的设施状态：{room}, {facility}, {product}")
        self.facility_states[room] = {
            "facility": facility,
            "product": product,
            "updated_at": updated_at or datetime.now().isoformat(timespec="seconds"),
        }

    def is_run_order_room(self, room: str) -> bool:
        """按维护副表、生效排班和实际订单过滤跑单。"""
        return (
            not self.run_order_paused
            and room.startswith("room")
            and self.products.get(room) != "orundum"
            and self.facility_states.get(room, {}).get("product") != "orundum"
            and any(
                name in slot.replacement
                for slot in self.plan.get(room, [])
                for name in TRADE_ORDER_AGENTS
            )
        )

    def refresh_run_order_rooms(self):
        self.run_order_rooms = {
            room: self.run_order_rooms.get(room, {})
            for room in self.plan
            if self.is_run_order_room(room)
        }
        return

    def facility_product(self, room: str) -> str | None:
        """返回指定设施产物；未读取实际状态时使用主表配置。"""
        if room not in base_room_list:
            raise ValueError(f"不支持的设施位置：{room}")
        cached = self.facility_states.get(room, {}).get("product")
        if cached in MANUFACTURE_PRODUCTS | TRADE_PRODUCTS:
            return cached
        return self.global_plan["default_plan"].products.get(room)

    def facility_type(self, room: str) -> str | None:
        """从当前排班复用指定位置的设施类型。"""
        if room not in base_room_list:
            raise ValueError(f"不支持的设施位置：{room}")
        room_plan = self.plan.get(room) or []
        if not room_plan:
            return None
        return FACILITY_TYPE_IDS.get(getattr(room_plan[0], "facility", None))

    def facility_operator_count(self, room: str) -> int:
        """根据已有干员位置缓存返回指定设施的进驻干员数量。"""
        if room not in base_room_list:
            raise ValueError(f"不支持的设施位置：{room}")
        return sum(
            operator.current_room == room for operator in self.operators.values()
        )

    @staticmethod
    def _validate_training_room(room: str) -> None:
        if room != "train":
            raise ValueError(f"不支持的训练室位置：{room}")

    def facility_has_mastery_plan(self, room: str) -> bool:
        """复用专精计划库，判断训练室是否存在未完结的计划。"""
        self._validate_training_room(room)
        from arknights_mower.utils.mastery_db import get_reconcile_plans

        return bool(get_reconcile_plans())

    def facility_is_training(self, room: str) -> bool:
        """复用专精计划状态，判断训练室是否正在训练。"""
        self._validate_training_room(room)
        from arknights_mower.utils.mastery_db import get_active_plan

        plan = get_active_plan()
        return plan is not None and plan.get("status") == "training"

    def facility_product_count(self, product: str) -> int:
        """返回当前生产指定产物或订单类型的设施数量。"""
        if product not in MANUFACTURE_PRODUCTS | TRADE_PRODUCTS:
            raise ValueError(f"不支持的产物或订单类型：{product}")
        rooms = (
            self.global_plan["default_plan"].products.keys()
            | self.facility_states.keys()
        )
        return sum(self.facility_product(room) == product for room in rooms)

    def facility_product_type_count(self) -> int:
        """返回当前产物和订单类型的种类数，缓存为空时使用主表。"""
        rooms = (
            self.global_plan["default_plan"].products.keys()
            | self.facility_states.keys()
        )
        return len(
            {
                product
                for room in rooms
                if (product := self.facility_product(room))
                in MANUFACTURE_PRODUCTS | TRADE_PRODUCTS
            }
        )

    def get_current_room(self, room, bypass=False, current_index=None):
        room_data = {
            v.current_index: v
            for k, v in self.operators.items()
            if v.current_room == room
        }
        # 训练室的两个槽位由设施决定，自动专精不要求静态排班配置该房间。
        # 只读取缓存，不向排班表补人，避免常规排班接管自动专精。
        res = [""] * 2 if room == "train" else [obj.agent for obj in self.plan[room]]
        not_found = False
        for idx, op in enumerate(res):
            if idx in room_data:
                res[idx] = room_data[idx].name
            else:
                res[idx] = ""
                if current_index is not None and idx not in current_index:
                    continue
                not_found = True
        if not_found and not bypass:
            return None
        else:
            return res

    def predict_fia(self, operators, fia_mood, hours=240):
        recover_hours = (24 - fia_mood) / 2
        for agent in operators:
            agent.mood -= agent.depletion_rate * recover_hours
            if agent.mood < 0.0:
                return False
        if recover_hours >= hours or 0 < recover_hours < 1:
            return True
        operators.sort(
            key=lambda x: (x.mood - x.lower_limit) / (x.upper_limit - x.lower_limit),
            reverse=False,
        )
        fia_mood = operators[0].mood
        operators[0].mood = 24
        return self.predict_fia(operators, fia_mood, hours - recover_hours)

    def reset_dorm_time(self):
        for name in self.operators.keys():
            agent = self.operators[name]
            if agent.room.startswith("dorm"):
                agent.time_stamp = None

    def restore_dorm_state(self, saved_dorms):
        """按床位恢复宿舍状态，保留当前排班生成的顺序和床位集合。"""
        saved_by_position = {
            tuple(dorm.position): dorm
            for dorm in saved_dorms
            if hasattr(dorm, "position")
        }
        restored = set()
        for dorm in self.all_dorms():
            if saved := saved_by_position.get(tuple(dorm.position)):
                if self.is_effective_free_slot(dorm) and self.is_recovery_dorm(
                    dorm, saved.name
                ):
                    dorm.name = saved.name
                    dorm.time = saved.time
                    restored.add(tuple(dorm.position))
        return [
            dorm
            for dorm in saved_dorms
            if dorm.name and tuple(dorm.position) not in restored
        ]

    @save_action_to_sqlite_decorator
    def update_detail(
        self,
        name,
        mood,
        current_room,
        current_index,
        update_time=False,
        related_operator=None,
        preserve_depletion_rate=False,
    ):
        """更新对象的详细信息，并记录到SQLite数据库
        参数:
        name(str): 对象的名称。
        mood(str): 当前的心情状态。
        current_room(str): 当前所在的房间名称(新)。
        current_index(int): 当前索引（新）。
        update_time(bool, 可选): 是否更新时间戳，默认为
        False 是否刷新时间
        preserve_depletion_rate(bool): 临时充能换位保留工作消耗速度，仍更新心情采样。

        返回: index 如果需要读取时间 None"""
        agent = self.operators[name]
        if update_time or (agent.current_room, agent.current_index) != (
            current_room,
            current_index,
        ):
            self.dorm_mood_estimates.pop(name, None)
        retained_time = None
        _, previous_bed = self.get_dorm_by_name(name)
        if (
            previous_bed is not None
            and previous_bed.name == name
            and previous_bed.position == (current_room, current_index)
        ):
            retained_time = previous_bed.time
        returned_to_post = (agent.current_room, agent.current_index) != (
            agent.room,
            agent.index,
        ) and (current_room, current_index) == (agent.room, agent.index)
        logger.debug(f"{name},{mood},{current_room},{current_index},{update_time}")
        if update_time:
            agent.mood_is_prediction = False
            if (
                not preserve_depletion_rate
                and agent.time_stamp is not None
                and agent.mood > mood
            ):
                time_difference = datetime.now() - agent.time_stamp
                if time_difference > timedelta(minutes=29):
                    logger.debug("开始计算心情掉率")
                    logger.debug(
                        f"当前心情：{mood},上次{agent.mood},上次时间{agent.time_stamp}"
                    )
                    agent.depletion_rate = (
                        (agent.mood - mood) * 3600 / time_difference.total_seconds()
                    )
                    logger.debug(
                        f"更新 {agent.name} 心情掉率为：{agent.depletion_rate}"
                    )
            agent.time_stamp = datetime.now()
        from_dorm = agent.current_room.startswith("dorm")
        to_dorm = current_room.startswith("dorm")
        if from_dorm and not to_dorm:
            if update_time:
                self.time_stamp = datetime.now()
            else:
                self.time_stamp = None
            if not preserve_depletion_rate:
                agent.depletion_rate = 0
        if from_dorm:
            idx, dorm = self.get_dorm_by_name(name)
            if dorm and dorm.name == name:
                dorm.reset()
        if current_room not in self.true_exhaust_room:
            agent.exhaust_time = None
            logger.debug(f"{name} 退出{current_room}，重置真实用尽时间")
        agent.current_room = current_room
        agent.current_index = current_index
        agent.mood = mood
        if update_time:
            agent.idle_rest_check = None
            if (
                current_room == getattr(agent, "dorm_mood_fallback", "")
            ) and 0 <= mood <= 24:
                for peer_name, stamp in getattr(agent, "dorm_mood_peers", {}).items():
                    peer = self.operators.get(peer_name)
                    if (
                        peer is not None
                        and not peer.current_room
                        and peer.time_stamp == stamp
                        and mood >= peer.upper_limit
                    ):
                        peer.idle_rest_check = (
                            peer.upper_limit,
                            peer.mood,
                            peer.time_stamp,
                        )
            agent.dorm_mood_peers = {}
        if update_time and 0 <= mood < agent.upper_limit:
            # 最低者确实需要恢复时，之后回满仍按普通不养闲人处理。
            agent.dorm_mood_fallback = ""
        self.update_standby_low_priority(agent, returned_to_post=returned_to_post)
        if current_room == "train" and current_index == 0:
            agent.resting_from_train = True
        elif (current_room and not to_dorm) or mood >= 24:
            agent.resting_from_train = False
        if mood >= 24:
            agent.clear_dorm_recovery()
        # 如果是高效组且没有记录时间，则返还index
        if to_dorm:
            idx, dorm = self.get_dorm_by_name(name)
            if dorm:
                dorm.name = name
                dorm.time = retained_time
                if dorm.time is None:
                    return current_index
        if agent.name == "菲亚梅塔" and (
            self.operators["菲亚梅塔"].time_stamp is None
            or self.operators["菲亚梅塔"].time_stamp < datetime.now()
        ):
            return current_index

    def refresh_dorm_time(self, room, index, agent):
        _name = agent["agent"]
        # 此方法也会作为无界函数绑定到轻量读房测试对象，避免依赖对象上存在
        # all_dorms 方法；旧对象没有 group_dorm 时按普通 Free 床位处理。
        dorms = [*self.dorm, *getattr(self, "group_dorm", [])]
        for dorm in dorms:
            if dorm.position[0] == room and dorm.position[1] == index:
                if not Operators.is_recovery_dorm(self, dorm, _name):
                    continue
                if (dorm.name == _name) and dorm.time is not None:
                    break
                if _name in self.operators.keys() or _name in agent_list:
                    _agent = self.operators[_name]
                    dorm.name = _name
                    # 如果干员有心情上限，则按比例修改休息时间
                    if _agent.mood != 24 and _agent.time_stamp:
                        sec_remaining = (
                            (_agent.upper_limit - _agent.mood)
                            * ((agent["time"] - _agent.time_stamp).total_seconds())
                            / (24 - _agent.mood)
                        )
                        dorm.time = _agent.time_stamp + timedelta(seconds=sec_remaining)
                    else:
                        dorm.time = agent["time"]
                break
        # 记录真实用尽时间
        if room in self.true_exhaust_room and _name in self.operators.keys():
            _agent = self.operators[_name]
            _agent.exhaust_time = Operator.exhaust_time_at_lower_limit(
                _agent, agent["time"]
            )
            logger.debug(f"{_name} 真实用尽时间：{_agent.exhaust_time}")
            return

    def correct_dorm(self):
        for dorm in self.all_dorms():
            if dorm.name != "" and dorm.name in self.operators.keys():
                if not self.is_recovery_dorm(dorm, dorm.name):
                    dorm.reset()
                    continue
                op = self.operators[dorm.name]
                if not (
                    dorm.position[0] == op.current_room
                    and dorm.position[1] == op.current_index
                ):
                    dorm.name = ""
                    dorm.time = None
                else:
                    if dorm.time is not None and dorm.time < datetime.now():
                        if (op.time_stamp is not None) and op.mood >= op.upper_limit:
                            # 全体上限不是实际心情封顶，保留已读到的较高心情及读数时间。
                            op.depletion_rate = 0
                            continue
                        op.mood = op.upper_limit
                        op.time_stamp = dorm.time
                        op.mood_is_prediction = True
                        op.depletion_rate = 0
                        logger.debug(f"检测到{op.name}心情恢复满，设置心情至{op.mood}")

    def get_train_support(self):
        for name in self.operators.keys():
            agent = self.operators[name]
            if agent.current_room == "train" and agent.current_index == 0:
                return agent.name
        return None

    def get_refresh_index(self, room, plan):
        ret = []
        if room.startswith("dorm") and self.config.free_room:
            return [i for i, slot in enumerate(self.plan[room]) if slot.agent == "Free"]
        for idx, dorm in enumerate(self.all_dorms()):
            if dorm.position[0] == room:
                for i, _name in enumerate(plan):
                    if _name in ("Free", "Current", "") or _name not in agent_list:
                        continue
                    if _name not in self.operators:
                        self.add(Operator(_name, ""))
                    if _name in self.operators:
                        if not self.config.free_room:
                            if self.operators[_name].is_high() and not self.operators[
                                _name
                            ].room.startswith("dorm"):
                                ret.append(i)
                        elif not self.operators[_name].room.startswith("dorm"):
                            ret.append(i)
                break
        return ret

    def get_dorm_by_name(self, name):
        if name not in self.operators:
            return None, None
        _op = self.operators[name]
        logger.debug(name)
        for idx, dorm in enumerate(self.all_dorms()):
            if (
                dorm.position[0] == _op.current_room
                and dorm.position[1] == _op.current_index
                and self.is_recovery_dorm(dorm, name)
            ):
                logger.debug(idx)
                logger.debug(dorm)
                return idx, dorm
        return None, None

    def add(self, operator):
        if operator.name not in agent_list:
            return
        if self.config.is_resting_priority(operator.name):
            operator.resting_priority = "low"
        operator.exhaust_require = self.config.is_exhaust_require(operator.name)
        operator.rest_in_full = self.config.is_rest_in_full(operator.name)
        operator.workaholic = self.config.is_workaholic(operator.name)
        operator.refresh_order_room = self.config.is_refresh_trading(operator.name)
        logger.debug(
            f"设置 {operator.name} 刷新交易房间: {operator.refresh_order_room}"
        )
        operator.refresh_drained = self.config.is_refresh_drained(operator.name)
        if operator.name in agent_arrange_order:
            operator.arrange_order = agent_arrange_order[operator.name]
        # 复制基建数据
        if operator.name in self.shadow_copy:
            exist = self.shadow_copy[operator.name]
            operator.mood = exist.mood
            operator.time_stamp = exist.time_stamp
            operator.mood_is_prediction = getattr(exist, "mood_is_prediction", False)
            operator.depletion_rate = exist.depletion_rate
            operator.current_room = exist.current_room
            operator.current_index = exist.current_index
            operator.dorm_position_version = getattr(exist, "dorm_position_version", 0)
            operator.dorm_recovery_room = getattr(exist, "dorm_recovery_room", "")
            operator.dorm_recovery_index = getattr(exist, "dorm_recovery_index", -1)
            operator.resting_from_train = getattr(exist, "resting_from_train", False)
            operator.dorm_recovery_fixed = getattr(exist, "dorm_recovery_fixed", ())
            operator.dorm_mood_fallback = getattr(exist, "dorm_mood_fallback", "")
            operator.dorm_mood_peers = getattr(exist, "dorm_mood_peers", {}).copy()
            operator.idle_rest_check = getattr(exist, "idle_rest_check", None)
            operator.rest_mood_release_limit = getattr(
                exist, "rest_mood_release_limit", None
            )
            operator.standby_low_priority = getattr(
                exist, "standby_low_priority", False
            )
            operator.temporary_dorm_fill = getattr(exist, "temporary_dorm_fill", False)
        self.operators[operator.name] = operator
        self.apply_custom_mood_limits(operator)
        self.apply_ling_xi_mood_limits()
        # 需要用尽心情干员逻辑
        if operator.exhaust_require and not (
            operator.group and operator.room.startswith("dorm")
        ):
            self.exhaust_agent.add(operator.name)
            if operator.group != "":
                self.exhaust_group.add(operator.group)
        # 干员分组逻辑
        if operator.group != "":
            if operator.group not in self.groups.keys():
                self.groups[operator.group] = [operator.name]
            else:
                self.groups[operator.group].append(operator.name)
        if operator.workaholic:
            self.workaholic_agent.add(operator.name)
        if operator.rest_in_full and not (
            operator.group and operator.room.startswith("dorm")
        ):
            if operator.group != "":
                self.rest_in_full_group.add(operator.group)
        if (
            self.config.is_resting_standby(operator.name)
            and operator.is_high()
            and not operator.room.startswith("dorm")
            and not operator.workaholic
            and not operator.exhaust_require
            and not self.config.is_rest_in_full(operator.name)
        ):
            operator.resting_priority = "standby"
        if operator.resting_priority != "standby":
            operator.standby_low_priority = False

    def _can_standby(self, op):
        """仅显式配置且没有强制恢复要求的主班可待命。"""
        return (
            (op.is_high())
            and op.resting_priority == "standby"
            and not op.room.startswith("dorm")
            and not op.workaholic
            and not op.exhaust_require
            and not self.config.is_rest_in_full(op.name)
        )

    def rescue_mood_threshold(self, op):
        """按个人心情上下限换算现有急救阈值。"""
        return op.lower_limit + (op.upper_limit - op.lower_limit) * (
            self.config.resting_threshold * config.conf.rescue_threshold
        )

    def resting_mood_threshold(self, op):
        threshold = (
            op.lower_limit
            + (op.upper_limit - op.lower_limit) * self.config.resting_threshold
        )
        return (
            threshold
            if self.custom_mood_limits(op.name) is not None
            else int(threshold)
        )

    def update_standby_low_priority(self, op, now=None, *, returned_to_post=False):
        """候补低于急救线后升为低优，直到实际回班。

        急救线与现有急救模式共用同一计算：排班心情阈值乘全局
        急救阈值，并按干员自身心情上下限换算为绝对心情。
        """
        if not self.config.is_resting_standby(op.name):
            op.standby_low_priority = False
            return
        # 回班是读取到的位置迁移事件；持续在岗的低心情候补仍需正常急救。
        if returned_to_post:
            op.standby_low_priority = False
            return
        mood = resting_mood(op, now)
        if mood < self.rescue_mood_threshold(op):
            op.standby_low_priority = True

    def is_standby(self, name):
        """从实际阵容识别候补待命，重启后也无需额外状态文件。"""
        op = self.operators[name]
        if not self._can_standby(op) or op.current_room:
            return False
        cover = self.get_current_operator(op.room, op.index)
        if (
            cover is None
            or cover.name not in op.replacement
            or cover.name in TRADE_ORDER_AGENTS
        ):
            return False
        if not op.group:
            return self.has_resting_anchor()
        return any(
            (
                member.is_high()
                and not self._can_standby(member)
                and not member.room.startswith("dorm")
                and not member.workaholic
            )
            and member.is_resting()
            and self.get_dorm_by_name(member.name)[0] is not None
            for member in (self.operators[n] for n in self.groups.get(op.group, []))
        )

    def has_dorm_groups(self):
        """仅实际填写了宿舍组名的配置启用宿舍绑组处理。"""
        return any(
            op.group and op.room.startswith("dorm") for op in self.operators.values()
        )

    def group_is_resting(self, group):
        """宿舍常驻成员不参与组的工作／休息状态判断。"""
        return any(
            not self.operators[name].room.startswith("dorm")
            and not self.operators[name].workaholic
            and self.operators[name].is_resting()
            for name in self.groups.get(group, [])
        )

    def is_auto_free_dorm_operator(self, operator):
        """宿舍替班显式填写 Free 时，该固定位按动态床使用。

        宿舍常驻成员随组离岗后，这个位置交给统一床位分配和
        不养闲人逻辑；填写任何具体干员仍按固定替班处理。
        """
        if (
            (not operator.group)
            or not operator.room.startswith("dorm")
            or operator.name == "菲亚梅塔"
        ):
            return False
        return "Free" in operator.replacement

    def is_auto_free_dorm_slot(self, room, index):
        slots = self.plan.get(room, [])
        if not room.startswith("dorm") or not 0 <= index < len(slots):
            return False
        resident = self.operators.get(slots[index].agent)
        return resident is not None and self.is_auto_free_dorm_operator(resident)

    def is_dynamic_dorm_position(self, room, index, name=None):
        """判断某位置在当前阵容中是否按动态床位处理。"""
        slots = self.plan.get(room, [])
        if not room.startswith("dorm") or not 0 <= index < len(slots):
            return False
        slot = slots[index]
        if slot.agent == "Free":
            return True
        if not self.is_auto_free_dorm_slot(room, index):
            return False
        # 固定宿舍干员本人在位时仍是宿管，不是休息者。
        return name is None or name not in (slot.agent, "Current")

    def is_dorm_replacement(self, name):
        """已在固定宿舍岗位上的替班不能被其他岗位借走。"""
        op = self.operators[name]
        return self.is_dorm_replacement_for_slot(
            name, op.current_room, op.current_index
        )

    def is_dorm_replacement_for_slot(self, name, room, index):
        """按目标位置识别绑组宿舍替班，也用于尚未入驻时的选人保护。"""
        slots = self.plan.get(room, [])
        if not room.startswith("dorm") or not 0 <= index < len(slots):
            return False
        slot = slots[index]
        return bool(
            slot.group
            and slot.agent not in ("Free", "菲亚梅塔")
            and not self.is_auto_free_dorm_slot(room, index)
            and name in slot.replacement
        )

    def group_dorm_bed_count(self, names):
        """返回本组随组离岗后会转换为动态 Free 的固定位置数。"""
        return sum(
            self.is_auto_free_dorm_operator(self.operators[name]) for name in names
        )

    def project_arrangements(self, plans):
        """按执行顺序推演排班后的驻员和恢复床位，不产生实际换人副作用。

        位置未变保留恢复时间；换床位或换宿舍后，由正常读房重新采样。
        产物切换和回班规划共用这一份位置语义，不能只改工位而留下旧床位。
        """
        projected = copy.copy(self)
        projected.operators = copy.deepcopy(self.operators)
        projected.dorm = copy.deepcopy(self.dorm)
        for plan in plans:
            changed_slots = {
                (room, index)
                for room, names in plan.items()
                for index, name in enumerate(names)
                if name != "Current"
            }
            recovery_times = {
                bed.name: (bed.position, bed.time) for bed in projected.dorm if bed.name
            }
            for op in projected.operators.values():
                if (op.current_room, op.current_index) in changed_slots:
                    op._current_room, op.current_index = "", -1
            for room, names in plan.items():
                for index, name in enumerate(names):
                    if name in projected.operators:
                        op = projected.operators[name]
                        # 不触发 current_room 的通知／记账回调。
                        op._current_room, op.current_index = room, index
                        op.rest_mood_release_limit = None
            for op in projected.operators.values():
                if not op.is_resting():
                    op.temporary_dorm_fill = False
            for bed in projected.dorm:
                occupant = projected.get_current_operator(*bed.position)
                if occupant is not None and projected.is_recovery_dorm(
                    bed, occupant.name
                ):
                    bed.name = occupant.name
                    old_position, old_time = recovery_times.get(
                        occupant.name, (None, None)
                    )
                    bed.time = old_time if (old_position == bed.position) else None
                else:
                    bed.reset()
        return projected

    def all_dorms(self):
        """返回全部潜在动态床位。"""
        return self.dorm

    def get_group_dorm(self, room, index):
        return next(
            (
                dorm
                for dorm in getattr(self, "group_dorm", [])
                if dorm.position == (room, index)
            ),
            None,
        )

    def is_recovery_dorm(self, dorm, name):
        """动态位置只跟踪实际休息者，不跟踪回归的固定宿舍成员。"""
        if dorm in self.dorm:
            room, index = dorm.position
            return self.is_dynamic_dorm_position(room, index, name)
        return False

    def replacement_exhausted(self, name, now=None):
        """仅对有效实测心情判断工作替班是否已到个人下限。"""
        candidate = self.operators.get(name)
        return (
            candidate is not None
            and candidate.time_stamp is not None
            and 0 <= candidate.mood <= 24
            and candidate.current_mood(now) <= candidate.lower_limit
        )

    def replacement_candidates(self, operator):
        """工作替班按配置顺序取用；已用尽候补稳定移到末尾。"""
        candidates = [
            name
            for name in operator.replacement
            if name != "Free"
            and not (operator.room.startswith("dorm") and self.rest_mood_complete(name))
        ]
        if not operator.room.startswith("dorm") and operator.name != "菲亚梅塔":
            now = datetime.now()

            def exhausted_last(name):
                return (self.replacement_exhausted(name, now),)

            # 候补列表本身就是效率优先级；仍可工作的候补严格保持配置顺序。
            # 真正到个人下限的候补只移到列表末尾，不从候补集合中删除，
            # 避免其他分床/预留逻辑失去对该干员的完整候补关系。
            return sorted(candidates, key=exhausted_last)
        if (
            not operator.room.startswith("dorm")
            or not operator.group
            or operator.name == "菲亚梅塔"
        ):
            return candidates
        now = datetime.now()

        def mood_order(name):
            candidate = self.operators.get(name)
            if (
                candidate is None
                or candidate.time_stamp is None
                or not 0 <= candidate.mood <= 24
            ):
                return (1, 0)
            # 与菲亚梅塔共用当前心情估算；宿舍替班按绝对心情排序，不扣下限。
            return (0, candidate.current_mood(now))

        return sorted(candidates, key=mood_order)

    def average_mood(self):
        total_mood = 0
        current_mood = 0
        count = 0
        for k, v in self.operators.items():
            if (
                not v.is_resting()
                and not (v.group and v.room.startswith("dorm"))
                and v.operator_type != "low"
                and not v.workaholic
                and not self.is_standby(k)
            ):
                current_mood += v.current_mood() - v.lower_limit
                total_mood += v.upper_limit - v.lower_limit
                count += 1
        if total_mood == 0:
            return 0
        logger.debug(
            f"当前工作总计高效组：{count}, 当前平均心情百分比 {current_mood / total_mood}"
        )
        return current_mood / total_mood

    def is_effective_free_slot(self, dorm, active_groups=None, inactive_groups=None):
        """判断潜在动态床位当前或本次规划中是否已经开放。"""
        room, index = dorm.position
        if room not in self.plan or not 0 <= index < len(self.plan[room]):
            return False
        slot = self.plan[room][index]
        if slot.agent == "Free":
            return True
        if not self.is_auto_free_dorm_slot(room, index):
            return False
        resident = self.operators[slot.agent]
        inactive_groups = set(inactive_groups or ())
        if resident.group in inactive_groups:
            return False
        if resident.group in set(active_groups or ()) or self.group_is_resting(
            resident.group
        ):
            return True
        # 已经有普通休息者实际入住或被本轮预约时，在固定成员回班前仍有效。
        return bool(dorm.name and dorm.name != resident.name)

    def available_free(self, free_type="high", time=None):
        if not time:
            time = datetime.now()

        effective_dorms = [
            dorm for dorm in self.dorm if self.is_effective_free_slot(dorm)
        ]
        dorm_count = len({dorm.position[0] for dorm in effective_dorms})
        total = len(effective_dorms)

        count_high = 0
        count_low = 0
        # 一次性遍历 dorm。低优占位也必须消耗 low 配额，否则调度器会持续把
        # 已占用床位误判为空位；恢复完成的普通填充干员由不养闲人处理。
        for dorm in effective_dorms:
            if dorm.name == "" or dorm.name not in self.operators:
                continue
            op = self.operators[dorm.name]
            if resting_tier(self, op.name) <= RestingTier.MAIN:
                count_high += 1
            else:
                count_low += 1
        available_high = max(0, dorm_count - count_high)
        available_low = total - count_low - max(count_high, dorm_count)
        return available_high if free_type == "high" else available_low

    def active_high_resting_count(self, time=None):
        """正在占用恢复床位的主班人数。"""
        if time is None:
            time = datetime.now()
        return sum(
            1
            for dorm in self.dorm
            if self.is_effective_free_slot(dorm)
            and dorm.name in self.operators
            and self.operators[dorm.name].is_high()
            and resting_tier(self, dorm.name) != RestingTier.IDLE
        )

    def _slot_takable(self, dorm, requester=None, active_groups=None):
        """普通和救急均按严格层级接管；排除与待执行预约保留床位。"""
        if not self.is_effective_free_slot(dorm, active_groups=active_groups):
            return False
        reserved_for = self.reserved_product_beds.get(dorm.position)
        if reserved_for and requester != reserved_for:
            if requester is None or resting_tier(self, requester) not in (
                RestingTier.PRIORITY_REPLACEMENT,
                RestingTier.REPLACEMENT,
                RestingTier.IDLE,
            ):
                return False
        name = dorm.name
        if (
            not name
            and (resident := self.get_current_operator(*dorm.position))
            and self.is_recovery_dorm(dorm, resident.name)
        ):
            name = resident.name
        if not name:
            return True
        op = self.operators.get(name)
        if op is None or self.is_free_room_excluded(name):
            return False
        # 已预留、尚未执行入驻的床位不能被本轮后续组重复分配。
        if (op.current_room, op.current_index) != dorm.position:
            return False
        return requester is not None and resting_tier(self, requester) < resting_tier(
            self, name
        )

    def _find_dorm_slot(self, name, used, *, active_groups=None):
        if self.rest_mood_complete(name):
            return None
        if resting_tier(self, name) == RestingTier.EXCLUDED:
            return None
        is_high = resting_tier(self, name) <= RestingTier.MAIN
        max_count = sum(1 for key in self.plan if key.startswith("dorm"))
        order = list(range(len(self.dorm)))
        if not is_high:
            order = order[max_count:] + order[:max_count]
        candidates = [
            i
            for i in order
            if i not in used
            and self._slot_takable(
                self.dorm[i],
                requester=name,
                active_groups=active_groups,
            )
        ]
        now = datetime.now()

        def takeover_cost(index):
            bed = self.dorm[index]
            if not bed.name:
                return (0, 0, 0)
            tier, recovery_order = resting_key(self, bed.name, now)
            # 先使用空位，再接管层级最低、同级距回满最近的占位者。
            return (1, -tier, -recovery_order)

        return min(candidates, key=takeover_cost, default=None)

    def has_resting_anchor(self, group=None):
        """是否已有能为候补提供回班时机的必需恢复者。"""
        return any(
            bed.name in self.operators
            and self.is_effective_free_slot(bed)
            and (op := self.operators[bed.name]).is_high()
            and not self._can_standby(op)
            and not self.rest_mood_complete(op.name)
            and (group is None or op.group == group)
            for bed in self.dorm
        )

    def standby_candidates(self, names):
        """返回本轮有床则休息、无床可待命的显式候补。"""
        # 必需组员确实需要恢复心情时才允许同组候补待命，避免满心情组员在选人
        # 阶段被释放后，整组既没有恢复心情者，也没有回班计时来源。
        anchor_groups = {
            op.group
            for op in (self.operators[n] for n in names)
            if (
                op.group
                and op.is_high()
                and not self._can_standby(op)
                and not op.workaholic
            )
            and not op.room.startswith("dorm")
            and 0 <= op.mood < op.upper_limit
            and op.current_mood() < op.upper_limit
        }
        return {
            name
            for name in names
            if self._can_standby(self.operators[name])
            and (
                self.operators[name].group in anchor_groups
                or not self.operators[name].group
                and self.has_resting_anchor()
            )
        }

    def assign_dorm_group(self, names, active_groups=None):
        """先保障必需床位；候补有床则休息，无床则随组离岗待命。"""
        # 达到个人上限后随组离岗即可，不再占床恢复。
        names = [name for name in names if not self.rest_mood_complete(name)]
        used = set()
        assignments = []
        optional = self.standby_candidates(names)
        ordered_names = sorted(
            names,
            key=lambda name: (
                name in optional,
                resting_key(self, name),
            ),
        )
        for name in ordered_names:
            index = self._find_dorm_slot(
                name,
                used,
                active_groups=active_groups,
            )
            if index is None:
                if name in optional:
                    continue
                logger.debug(f"没有足够宿舍位可安排整组必需休息成员{names}")
                return None
            used.add(index)
            assignments.append((name, index))

        rooms = []
        for name, index in assignments:
            room = self.dorm[index]
            logger.debug(f"安排{name}去{room.position}")
            room.name = name
            room.time = None
            rooms.append(room)
        for name in optional - {name for name, _ in assignments}:
            logger.debug(f"{name}随组下班待命，不占用其他主力的休息床位")
        return rooms

    def assign_dorm(self, name, is_new=False, used=None):
        if used is None:
            used = set()
        index = self._find_dorm_slot(name, used)
        if index is None:
            logger.debug(f"没有空闲宿舍位可安排{name}")
            return None
        used.add(index)
        _room = self.dorm[index]
        logger.debug(f"安排{name}去{_room.position}")
        _room.name = name
        _room.time = None
        return _room

    def get_current_operator(self, room, index):
        for key, value in self.operators.items():
            if value.current_room == room and value.current_index == index:
                return value
        return None

    def print(self):
        ret = "{"
        op = []
        dorm = []
        for k, v in self.operators.items():
            op.append("'" + k + "': " + str(vars(v)))
        ret += "'operators': {" + ",".join(op) + "},"
        for v in self.dorm:
            dorm.append(str(vars(v)))
        ret += "'dorms': [" + ",".join(dorm) + "]}"
        return ret

    def validate_backup_plans(self):
        """使用换班预演的合并校验检查可能的副表组合，保留当前排班与驻员。"""
        from arknights_mower.utils.backup_validation import (
            BackupValidationLimitExceeded,
            possible_backup_conditions,
        )
        from arknights_mower.utils.schedule_roster import validate_owned_operators

        if error := validate_owned_operators(self.global_plan):
            return {"success": False, "status": "failed", "message": error}

        baseline = Operators(self.global_plan)
        if error := baseline.init_and_validate():
            return {
                "success": False,
                "status": "failed",
                "message": f"基础验证失败：{error}",
            }
        backup_count = len(self.backup_plans)
        # 仅按条件证明互斥；主力不重叠不能证明合并配置互不影响。
        try:
            combinations = possible_backup_conditions(
                self.backup_plans,
                MAX_BACKUP_VALIDATION_COMBINATIONS,
                known_operators=baseline.operators,
            )
        except BackupValidationLimitExceeded as error:
            return {
                "success": False,
                "status": "incomplete",
                "message": f"{error}。主表已通过检查，允许启动；实际生效的副表组合由运行时检查。",
            }
        tested_count = 0
        for flags in combinations:
            condition = list(flags)
            # 每个组合从独立模型开始，失败及检查顺序都不影响实际排班和驻员。
            simulation = copy.copy(baseline)
            simulation.operators, simulation.dorm = {}, []
            error = simulation.swap_plan(condition, refresh=True)
            tested_count += 1
            if error is not None:
                active = "、".join(
                    backup.name or f"副表{index + 1}"
                    for index, (backup, enabled) in enumerate(
                        zip(self.backup_plans, flags)
                    )
                    if enabled
                )
                message = (
                    f"副表组合验证失败（{active}）：{error}"
                    if active
                    else f"基础验证失败：{error}"
                )
                logger.info(message)
                return {"success": False, "status": "failed", "message": message}
        if backup_count == 0:
            return {
                "success": True,
                "status": "passed",
                "message": "没有备用计划，基础验证通过",
            }
        return {
            "success": True,
            "status": "passed",
            "message": f"验证成功，共验证 {tested_count} 次",
        }


class Dormitory:
    def __init__(self, position, name="", time=None):
        self.position = position
        self.name = name
        self.time = time

    def __repr__(self):
        return (
            f"Dormitory(position={self.position},name='{self.name}',time='{self.time}')"
        )

    def reset(self):
        self.name = ""
        self.time = None


class Operator:
    def __init__(
        self,
        name,
        room,
        index=-1,
        group="",
        replacement=[],
        resting_priority="low",
        current_room="",
        exhaust_require=False,
        mood=24,
        upper_limit=24,
        rest_in_full=False,
        current_index=-1,
        lower_limit=0,
        operator_type="low",
        depletion_rate=0,
        time_stamp=None,
        refresh_order_room=None,
        refresh_drained=False,
    ):
        self.name = name
        if refresh_order_room is not None:
            self.refresh_order_room = refresh_order_room
            logger.debug(f"设置{self.name}刷新交易所房间为{self.refresh_order_room}")
        else:
            self.refresh_order_room = [False, []]
        self.refresh_drained = refresh_drained
        self.room = room
        self.operator_type = operator_type
        self.index = index
        self.group = group
        self.replacement = replacement
        self.resting_priority = resting_priority
        # 候补跌破急救线后，本轮休息周期锁定为低优。
        self.standby_low_priority = False
        self.dorm_recovery_room = ""
        self.dorm_recovery_index = -1
        self.resting_from_train = False
        self.rest_mood_release_limit = None
        # (单回宿管姓名, 床位, 移动版本)；旧缓存的全宿管姓名元组会自动失效。
        self.dorm_recovery_fixed = ()
        self.single_recovery_manager = False
        self.dorm_mood_fallback = ""
        self.dorm_mood_peers = {}
        self.idle_rest_check = None
        # 普通补床住客随时给主班让床，不计入集中恢复正式批次。
        self.temporary_dorm_fill = False
        self._current_room = None
        self.current_room = current_room
        self.exhaust_require = exhaust_require
        self.upper_limit = upper_limit
        self.rest_in_full = rest_in_full
        self.mood = mood
        self.current_index = current_index
        self.lower_limit = lower_limit
        self.depletion_rate = depletion_rate
        self.time_stamp = time_stamp
        self.mood_is_prediction = False
        self.workaholic = False
        self.arrange_order = ["技能", "false"]
        self.exhaust_time = None

    @property
    def current_room(self):
        return self._current_room

    @current_room.setter
    def current_room(self, value):
        if self._current_room != value:
            self.dorm_position_version = getattr(self, "dorm_position_version", 0) + 1
            was_working = self.is_working()
            self.idle_rest_check = None
            if value != getattr(self, "dorm_mood_fallback", ""):
                self.dorm_mood_fallback = ""
                self.dorm_mood_peers = {}
            self.clear_dorm_recovery()
            self._current_room = value
            if not value or not value.startswith("dorm"):
                self.temporary_dorm_fill = False
            if value:
                self.rest_mood_release_limit = None
            started_working = not was_working and self.is_working()
            if Operators.current_room_changed_callback and (
                started_working or self.refresh_order_room[0] or self.refresh_drained
            ):
                Operators.current_room_changed_callback(
                    self, started_working=started_working
                )
                logger.debug(
                    f"触发当前房间变更回调: {self.name} 现在在 {self._current_room}, 刷新交易所房间: {self.refresh_order_room}, 刷新疲劳: {self.refresh_drained}"
                )

    @property
    def current_index(self):
        # 保留旧 pickle 的字段名，升级和回退都能读取同一份床位缓存。
        return self.__dict__.get("current_index", -1)

    @current_index.setter
    def current_index(self, value):
        if self.current_index != value:
            self.dorm_position_version = getattr(self, "dorm_position_version", 0) + 1
            self.clear_dorm_recovery()
        self.__dict__["current_index"] = value

    def clear_dorm_recovery(self):
        self.dorm_recovery_room = ""
        self.dorm_recovery_index = -1
        self.dorm_recovery_fixed = ()

    def is_high(self):
        # 是否为高效组
        return self.operator_type == "high"

    def is_resting(self):
        return self.current_room.startswith("dorm")

    def is_working(self):
        return self.current_room in base_room_list and not self.is_resting()

    def need_to_refresh(self, h=2, r=""):
        # 是否需要读取心情
        if self.name in ["歌蕾蒂娅", "见行者"]:
            h = 0.5
        if (
            self.time_stamp is None
            or (
                self.time_stamp is not None
                and self.time_stamp + timedelta(hours=h) < datetime.now()
            )
            or (r.startswith("dorm") and not self.room.startswith("dorm"))
        ):
            return True

    def not_valid(self):
        if self.operator_type == "high":
            if self.workaholic:
                return (
                    self.current_room != self.room or self.index != self.current_index
                )
            if not self.room.startswith("dorm") and self.current_room.startswith(
                "dorm"
            ):
                if self.mood == -1 or self.mood == 24:
                    return True
                else:
                    return False
            return (
                self.need_to_refresh(2.5)
                or self.current_room != self.room
                or self.index != self.current_index
            )
        return False

    def current_mood(self, time=None):
        if not time:
            time = datetime.now()
        predict = self.mood
        if self.time_stamp is not None:
            predict = (
                self.mood
                - self.depletion_rate * (time - self.time_stamp).total_seconds() / 3600
            )
        if 0 <= predict <= 24:
            return predict
        else:
            return self.mood

    def exhaust_time_at_lower_limit(self, zero_time, now=None):
        """按本次读到的心情，把游戏的归零倒计时换算到设置下限。"""
        now = now or datetime.now()
        if self.mood > 0 and self.lower_limit > 0:
            zero_time = now + (zero_time - now) * (
                (self.mood - self.lower_limit) / self.mood
            )
        return max(now, zero_time)

    def predict_exhaust(self):
        if self.workaholic or self.exhaust_require or self.room in ["factory", "train"]:
            return datetime.now() + timedelta(hours=24)
        remaining_mood = self.mood - self.lower_limit  # 剩余心情
        depletion_rate = self.depletion_rate  # 心情掉率，小时单位
        # 计算到心情归零所需时间（小时），再加上当前时间戳
        if self.time_stamp and depletion_rate > 0:
            predict = self.time_stamp + timedelta(
                hours=((remaining_mood / depletion_rate) - 0.5)
            )
            if self.exhaust_time is not None:
                logger.debug(f"预测用尽时间:{predict}")
                logger.debug(f"真实用尽时间：{self.exhaust_time}")
                return min(predict, self.exhaust_time)
            else:
                return predict
        elif remaining_mood <= 0:
            return datetime.now()
        return datetime.now() + timedelta(hours=24)

    def __repr__(self):
        return f"Operator(name='{self.name}', room='{self.room}', index={self.index}, group='{self.group}', replacement={self.replacement}, resting_priority='{self.resting_priority}', current_room='{self.current_room}',exhaust_require={self.exhaust_require},mood={self.mood}, upper_limit={self.upper_limit}, rest_in_full={self.rest_in_full}, current_index={self.current_index}, lower_limit={self.lower_limit}, operator_type='{self.operator_type}',depletion_rate={self.depletion_rate},time_stamp='{self.time_stamp}',refresh_order_room = {self.refresh_order_room})"
