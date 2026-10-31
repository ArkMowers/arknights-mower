import ast
import copy
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from functools import lru_cache
from time import monotonic
from typing import Any, Literal, overload

from evalidate import EvalModel, ExecutionException, Expr, base_eval_model

from arknights_mower.utils import config
from arknights_mower.utils.calculated_mood import measure_mood_calculation
from arknights_mower.utils.config.plan_advanced import export_advanced_settings
from arknights_mower.utils.manufacture_product import (
    MANUFACTURE_PRODUCTS,
    TRADE_PRODUCTS,
)
from arknights_mower.utils.plan import (
    RIGHT_SIDE_ROOM_CAPACITY,
    BaseProduct,
    PlanConfig,
    effective_dorm_order,
)
from arknights_mower.utils.resting_priority import (
    RestingTier,
    bed_takeover_allowed,
    has_resting_mood,
    is_full_dorm_filler,
    is_full_dynamic_candidate,
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
_OPERATOR_SCALAR_TYPES = frozenset({type(None), bool, int, float, complex, str, bytes})
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
_MAX_COMPILED_EXPRESSIONS = 256
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
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = node.func.id
        if node.keywords:
            return None
        if function in ("any", "all") and len(node.args) == 1:
            return 1
        if function == "abs" and len(node.args) == 1:
            return _numeric_result_bits(node.args[0])
        if function in ("max", "min") and len(node.args) >= 2:
            args = node.args
        elif (
            function == "sum"
            and len(node.args) == 1
            and isinstance(node.args[0], ast.List)
        ):
            args = node.args[0].elts
        else:
            return None
        bits = [_numeric_result_bits(arg) for arg in args]
        if any(value is None for value in bits):
            return None
        result_bits = max(bits, default=1)
        if function == "sum" and args:
            result_bits += (len(args) - 1).bit_length()
        return result_bits
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


@lru_cache(maxsize=_MAX_COMPILED_EXPRESSIONS)
def _compile_expression(
    expression, nodes, attributes, allowed_functions, imported_names
):
    """最多保留 256 条已校验代码；许可变化另行校验，旧项按 LRU 淘汰。"""
    _validate_expression_resources(expression)
    permissions = EvalModel(
        nodes=list(nodes),
        attributes=list(attributes),
        allowed_functions=list(allowed_functions),
        imported_functions=dict.fromkeys(imported_names),
    )
    return Expr(expression, permissions).code


@overload
def build_global_plan(
    *,
    include_source: Literal[False] = False,
    plan_model: config.PlanModel | None = None,
    conf_model: config.Conf | None = None,
) -> dict[str, Any]: ...


@overload
def build_global_plan(
    *,
    include_source: Literal[True],
    plan_model: config.PlanModel | None = None,
    conf_model: config.Conf | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]: ...


def build_global_plan(
    *,
    include_source: bool = False,
    plan_model: config.PlanModel | None = None,
    conf_model: config.Conf | None = None,
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, Any]]:
    """构建完整的 global_plan，包括 Plan 对象，用于运行时"""
    from ..utils import config
    from ..utils.logic_expression import get_logic_exp
    from ..utils.plan import Plan, PlanConfig, Room

    plan1 = {}
    default_products = {}
    source_model = (plan_model if plan_model is not None else config.plan).model_copy(
        deep=True
    )
    plan = source_model.model_dump(exclude_none=True)
    source_plan = copy.deepcopy(plan) if include_source else None
    conf = conf_model if conf_model is not None else config.conf
    if source_plan is not None:
        source_plan["advanced_settings"] = export_advanced_settings(conf)
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
        group_resting_thresholds=conf.group_resting_thresholds,
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
                group_bindings=op.get("group_bindings", []),
            )
            for op in obj["plans"]
        ]
    # 默认任务
    plan["default_plan"] = Plan(plan1, plan_config, products=default_products)
    # 备用自定义任务
    groups = {
        group["id"]: get_logic_exp(copy.deepcopy(group["trigger"]))
        for group in plan["backup_groups"]
    }
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
                    group_bindings=op.get("group_bindings", []),
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
            group_resting_thresholds=conf.group_resting_thresholds,
            refresh_trading_config=i["conf"]["refresh_trading"],
            refresh_drained=i["conf"]["refresh_drained"],
            free_room=conf.free_room,
            removed_operators=i["conf"].get("removed_operators", {}),
        )
        backup_trigger = get_logic_exp(i["trigger"]) if "trigger" in i else None
        backup_task = i.get("task")
        backup_plans.append(
            Plan(
                backup_plan,
                backup_config,
                trigger=backup_trigger,
                task=backup_task,
                group_tasks=i.get("group_tasks", []),
                name=i.get("name"),
                products=backup_products,
                group_ids=i["group_ids"],
                backup_type=i["type"],
                group_triggers={
                    key: groups[key] for key in i["group_ids"] if key != "default"
                },
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
    backup_group = "default"
    backup_groups = ()
    shadow_copy = {}
    current_room_changed_callback = None
    first_init = True

    def __init__(self, plan, *, runtime_conf=None, facility_levels=None):
        self.runtime_conf = runtime_conf
        self.facility_levels = copy.deepcopy(
            facility_levels
            if facility_levels is not None
            else getattr(config.plan, "facility_levels", {})
        )
        from arknights_mower.utils.calculated_mood import CalculatedMood

        self.mood_model = CalculatedMood()
        self.operators = {}
        self.groups = {}
        self.group_shift_state = {}
        self.group_recovery_full_members = {}
        self.group_recovery_return_time = {}
        self.urgent_recovery_supporters = {}
        self.exhaust_agent = set()
        self.exhaust_group = set()
        self.rest_in_full_group = set()
        self.dorm = []
        self.displaced_dorms = []
        self.group_dorm = []
        self.idle_dorm_search_exhausted = False
        self.idle_dorm_search_stopped_at = None
        self.dorm_mood_estimates = {}
        self.recall_recovery_rates = {}
        self.emergency_reserved_agents = set()
        self.emergency_dorm_agents = set()
        self.workaholic_agent = set()
        self.free_blacklist = []
        self.global_plan = plan
        self.backup_plans = plan["backup_plans"]
        self.backup_groups = plan.get("backup_groups", [])
        self.backup_group = "default"
        # 切换默认排班
        self.swap_plan([False] * (len(self.backup_plans)))
        self.run_order_rooms = {}
        self.clues = []
        self.current_room_changed_callback = None
        self.party_time = None
        self.facility_states = {}
        self.room_observations = {}
        self.reserved_product_beds = {}
        self.reserved_product_replacements = set()
        self.profession_filter = set(agent_arrange_order["职介选择开关"])
        self.eval_model = base_eval_model.clone()
        self.eval_model.nodes.extend(
            ["Call", "Attribute", "Is", "IsNot", "Mult", "FloorDiv", "Pow", "List"]
        )
        self.eval_model.allowed_functions.extend(
            ["max", "min", "sum", "any", "all", "abs"]
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
        return self.emergency_run_order_replacements is None and bool(
            self.maintenance_primary_slots
        )

    def evaluate_backup_selection(self):
        from arknights_mower.utils.backup_groups import select_backup_plans
        from arknights_mower.utils.logic_expression import get_logic_exp

        groups = [
            {**group, "trigger": get_logic_exp(copy.deepcopy(group["trigger"]))}
            for group in self.backup_groups
        ]
        now = getattr(self, "_projection_now", None) or datetime.now()
        missing = object()
        clocks = [
            (obj, getattr(obj, "_projection_now", missing))
            for obj in (self, *self.operators.values())
        ]
        try:
            # 分组条件和各副表条件共用同刻心情，沿用已有的投影查询缓存。
            for obj, _ in clocks:
                obj._projection_now = now
            return select_backup_plans(
                self.backup_plans,
                groups,
                lambda trigger: bool(self.evaluate_expression(str(trigger))),
                current_group=self.backup_group,
                current=self.plan_condition,
            )
        finally:
            for obj, previous in clocks:
                if previous is missing:
                    del obj._projection_now
                else:
                    obj._projection_now = previous

    def swap_plan(self, condition, refresh=False, *, backup_group=None):
        from arknights_mower.utils.backup_validation import validate_backup_facilities

        if error := validate_backup_facilities(
            self.global_plan["default_plan"],
            [
                backup
                for backup, enabled in zip(self.backup_plans, condition)
                if enabled
            ],
            product_switching_enabled=getattr(
                getattr((self.runtime_conf or config.conf), "product_switching", None),
                "enable",
                False,
            ),
        ):
            return error
        self.emergency_run_order_replacements = None
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
                maintenance = backup.uses_condition(
                    "major_maintenance_remaining_hours",
                    backup_group or self.backup_group,
                )
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
        if backup_group is not None:
            self.backup_group = backup_group
        if refresh:
            self.first_init = True
            error = self.init_and_validate(True)
            self.first_init = False
            if error:
                return error

    def merge_plan(self, idx, ext_config, default_plan=None):
        if default_plan is None:
            default_plan = copy.deepcopy(self.global_plan["default_plan"].plan)
        plan = self.global_plan["backup_plans"][idx]
        # 更新切换排班表
        for key, value in plan.plan.items():
            if key in RIGHT_SIDE_ROOM_CAPACITY:
                if not value:
                    continue
                target = default_plan.setdefault(key, [])
                for index, operator in enumerate(value):
                    if index >= len(target):
                        target.append(copy.deepcopy(operator))
                    elif operator.agent != "Current":
                        target[index] = copy.deepcopy(operator)
            elif key in default_plan:
                for idx, operator in enumerate(value):
                    if operator.agent != "Current":
                        default_plan[key][idx] = copy.deepcopy(operator)
        return default_plan, ext_config.merge_config(plan.config)

    def init_and_validate(self, update=False):
        from arknights_mower.utils.backup_validation import validate_trade_order_targets

        primary = self.global_plan["default_plan"]
        if error := validate_trade_order_targets(
            primary.plan, primary.products, label="主表"
        ):
            return error
        for name in self.config.operator_mood_limits:
            if name not in agent_list:
                return f"心情上下限中的干员名无效：{name}"
        for name in self.config.free_room_exclusions:
            if name and name not in agent_list:
                return f"宿舍保留中的干员名无效：{name}"
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
        planned_names = self.planned_operator_names()
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
                if data.group_bindings:
                    groups = [binding["group"].strip() for binding in data.bindings]
                    if len(groups) != len(set(groups)):
                        return f"{data.agent}的多绑组名称不能重复，空绑组最多填写一次"
                    if data.agent in ("Free", "菲亚梅塔"):
                        return f"{data.agent}不能配置多绑组"
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
                        group_bindings=data.bindings if data.group_bindings else None,
                    ),
                    planned_names=planned_names,
                )
        binding_members = {}
        for op in self.operators.values():
            groups = (
                [binding["group"] for binding in op.group_bindings]
                if op.multi_group
                else [op.group]
            )
            for group in groups:
                if group:
                    binding_members.setdefault(group, []).append(op.name)
        zero_mood_groups = {
            group
            for group, members in binding_members.items()
            if all(self.operators[name].workaholic for name in members)
        }
        missing_replacements = []
        for room in self.plan.keys():
            if room.startswith("dorm") and len(self.plan[room]) != 5:
                return f"宿舍 {room} 人数少于5人"
            for idx, data in enumerate(self.plan[room]):
                # 菲亚梅塔替换组做特例判断
                for binding in data.bindings:
                    replacements = binding["replacement"]
                    optional = (
                        data.agent != "菲亚梅塔"
                        and not room.startswith("dorm")
                        and self.operators[data.agent].workaholic
                        and (
                            not binding["group"] or binding["group"] in zero_mood_groups
                        )
                    )
                    if data.group_bindings and not replacements and not optional:
                        return f"{data.agent}的每个绑组都需要替班"
                    if sum(name in replacements for name in TRADE_ORDER_AGENTS) > 1:
                        return f"替换组不可同时安排多个跑单干员 房间->{room}, 干员->{data.agent}"
                    if "菲亚梅塔" in replacements:
                        return (
                            f"替换组不可安排菲亚梅塔 房间->{room}, 干员->{data.agent}"
                        )
                    if (
                        not optional
                        and not any(
                            name not in TRADE_ORDER_AGENTS for name in replacements
                        )
                        and (
                            (data.agent != "Free" and not room.startswith("dorm"))
                            or data.agent == "菲亚梅塔"
                        )
                    ):
                        missing_replacements.append(data.agent)
                for _replacement in data.all_replacements:
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
                        cover = self.operators.get(_replacement)
                        if cover is not None and cover.is_high():
                            if any(
                                _replacement in binding["replacement"]
                                and not self.is_same_group_primary_replacement(
                                    self.operators[data.agent],
                                    _replacement,
                                    binding["group"],
                                )
                                for binding in data.bindings
                            ):
                                return f"替换组不可用高效组干员: 房间->{room}, 干员->{_replacement}"
                        else:
                            self.add(
                                Operator(_replacement, ""), planned_names=planned_names
                            )
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
                if (
                    _slot.group
                    and "Free" in _slot.all_replacements
                    and key not in added
                ):
                    self.dorm.append(Dormitory((dorm, index)))
                    added.append(key)
        for name in self.config.free_room_exclusions:
            if name and name not in self.operators:
                self.add(Operator(name, ""), planned_names=planned_names)
        if update:
            for key, value in self.shadow_copy.items():
                if key not in self.operators:
                    self.add(Operator(key, ""), planned_names=planned_names)
        self.config.dorm_order = effective_dorm_order(self.config.dorm_order)
        room_order = [
            room for room in self.config.dorm_order if not room.endswith("_low")
        ]
        self.dorm.sort(
            key=lambda bed: (room_order.index(bed.position[0]), bed.position[1])
        )
        self.refresh_run_order_rooms()
        from arknights_mower.utils.exhaust_replacement import match_replacements

        for key, members in binding_members.items():
            self.groups.setdefault(key, [])
            members = self.shift_group_members(key)
            if key in zero_mood_groups and not any(
                self.operators[name].room.startswith("dorm") for name in members
            ):
                configured = {}
                for name in members:
                    candidates = [
                        cover
                        for cover in self.operators[name].replacements_for_group(key)
                        if cover not in TRADE_ORDER_AGENTS
                    ]
                    if candidates:
                        configured[name] = candidates
                if configured and match_replacements(configured) is None:
                    return f"{key} 分组无法排班,替换组数量不够"
                continue
            working_members = tuple(
                name
                for name in members
                if not self.operators[name].room.startswith("dorm")
            )
            working = tuple(
                name for name in working_members if not self.operators[name].workaholic
            )
            # 全零心情工作组不触发普通轮休，不要求决定上下班的主班。
            if (working or not working_members) and not any(
                self.is_group_shift_anchor(self.operators[name]) for name in members
            ):
                return (
                    f"{key} 缺少决定上下班的工作主班：至少需要一名非宿舍、"
                    "非零心情工作、非多绑组且非候补的主班"
                )
            mandatory = tuple(
                name for name in working if not self._can_standby(self.operators[name])
            )
            required = set(mandatory)
            replacement_options = {}
            for name in members:
                operator = self.operators[name]
                replacements = operator.replacements_for_group(key)
                if operator.room.startswith("dorm") and "Free" in replacements:
                    # 显式 Free 只负责开启“随组离岗时转为 Free”，不参与
                    # 组内替班唯一性校验。
                    continue
                replacement_options[name] = [
                    r for r in replacements if r not in TRADE_ORDER_AGENTS
                ]
            effective_dorm_count = sum(
                1
                for dorm in self.dorm
                if (slot := self.plan[dorm.position[0]][dorm.position[1]]).agent
                == "Free"
                or any(
                    binding["group"] == key and "Free" in binding["replacement"]
                    for binding in slot.bindings
                )
            )
            for preferred in ((), required):
                assignments = match_replacements(
                    replacement_options, preferred=preferred
                )
                if assignments is None:
                    return f"{key} 分组无法排班,替换组数量不够"
                required_beds = len(required - set(assignments.values()))
                if required_beds <= effective_dorm_count:
                    break
            else:
                return f"{key} 分组无法排班,所需宿舍数{required_beds}大于当前有效宿舍数{effective_dorm_count}"
        self.group_dorm = [
            Dormitory((room, index))
            for room, slots in self.plan.items()
            if room.startswith("dorm")
            for index, slot in enumerate(slots)
            if any(
                name != "Free"
                and self.is_same_group_primary_replacement(
                    self.operators[slot.agent], name, binding["group"]
                )
                and not self.operators[name].room.startswith("dorm")
                for binding in slot.bindings
                if "Free" not in binding["replacement"]
                for name in binding["replacement"]
            )
        ]
        if update:
            self.displaced_dorms = self.restore_dorm_state(saved_dorms)
        # 应用心情上下限：个人设置优先，其次令夕模式、全体设置。
        self.init_mood_limit(planned_names=planned_names)
        for name in self.workaholic_agent:
            if name not in self.config.free_blacklist:
                self.config.free_blacklist.append(name)
        self.power_plant_count = sum(
            1
            for room in self.plan.values()
            if room and room[0].product == BaseProduct.Electricity
        )
        self.refresh_dorm_manager_flags(force=True)
        from arknights_mower.utils.backup_group_tasks import validate_group_tasks

        try:
            validate_group_tasks(self)
        except ValueError as error:
            return str(error)

    def refresh_dorm_manager_flags(self, *, force=False):
        """标记配置中的宿舍成员及其替班；资源未变时不再匹配。"""
        from arknights_mower.utils import dorm_skills

        if not force and getattr(self, "_dorm_skill_generation", -1) == (
            dorm_skills.resource_generation
        ):
            return
        planned = {
            name
            for room, slots in self.plan.items()
            if room.startswith("dorm")
            for slot in slots
            for name in (slot.agent, *slot.all_replacements)
            if name in self.operators
        }
        for name, op in self.operators.items():
            op.single_recovery_manager = name in planned and (
                dorm_skills.is_single_recovery_manager(name)
            )
        self._dorm_skill_generation = dorm_skills.resource_generation

    @property
    def mood_calculation_enabled(self):
        conf = getattr(self, "runtime_conf", None) or config.conf
        enabled = bool(getattr(conf, "test_mood_calculation", False))
        if hasattr(self, "mood_model"):
            self.mood_model.enabled = enabled
        return enabled

    @measure_mood_calculation
    def calculated_mood(self, name, now=None):
        if not self.mood_calculation_enabled:
            return None
        from arknights_mower.utils.calculated_mood import sync_model

        return sync_model(
            self, getattr(self, "_projection_now", None), advance_clock=False
        ).value(name, now or getattr(self, "_projection_now", None))

    @measure_mood_calculation
    def calculated_mood_rate(self, name, now=None):
        if not self.mood_calculation_enabled:
            return None
        from arknights_mower.utils.calculated_mood import sync_model

        now = now or getattr(self, "_projection_now", None)
        model = sync_model(self, getattr(self, "_projection_now", None))
        if now is not None:
            model = copy.deepcopy(model)
            model.advance(now)
        return model._rates().get(name) if name in model.moods else None

    @measure_mood_calculation
    def calculated_mood_deadline(self, name, target, now=None, max_hours=240):
        if not self.mood_calculation_enabled:
            return None
        if target == 0 and name in self.operators:
            observed = self.operators[name].working_zero_deadline(
                now or getattr(self, "_projection_now", None)
            )
            if observed is not None:
                return observed
        from arknights_mower.utils.calculated_mood import sync_model

        now = now or getattr(self, "_projection_now", None)
        model = sync_model(
            self, getattr(self, "_projection_now", None), advance_clock=False
        )
        cached = getattr(self, "_projection_deadlines", None)
        key = (name, target, max_hours, now)
        if cached is not None and key in cached:
            due = cached[key]
            return max(now, due) if due is not None and now is not None else due
        due = model.deadline(name, target, now, max_hours)
        if cached is not None:
            cached[key] = due
        return due

    def set_mood_limit(
        self, name, upper_limit=24, lower_limit=0, *, planned_names=None
    ):
        if name in self.operators and (
            self.is_planned_operator(name)
            if planned_names is None
            else name in planned_names
        ):
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
            name == slot.agent or name in slot.all_replacements
            for slots in self.plan.values()
            for slot in slots
        )

    def planned_operator_names(self):
        names = set(self.emergency_dorm_agents)
        for slots in self.plan.values():
            for slot in slots:
                names.add(slot.agent)
                names.update(slot.all_replacements)
        return names

    def custom_mood_limits(self, name, *, planned_names=None):
        limits = self.config.custom_mood_limits(name)
        if limits is None:
            return None
        planned = (
            self.is_planned_operator(name)
            if planned_names is None
            else name in planned_names
        )
        return limits if planned else None

    def rest_mood_complete(self, name):
        from arknights_mower.utils.dorm_candidates import dorm_candidate_mood

        op = self.operators.get(name)
        mood = dorm_candidate_mood(self, name)
        return (
            self.has_rest_mood_limit(name)
            and op is not None
            and mood is not None
            and (
                mood >= op.upper_limit
                or not op.current_room
                and getattr(op, "rest_mood_release_limit", None) == op.upper_limit
            )
        )

    def is_free_room_excluded(self, name):
        """宿舍保留禁止自动清退为空闲，不限制换床或合法工作安排。"""
        return (
            (bool(name))
            and name in getattr(self.config, "free_room_exclusions", ())
            and resting_tier(self, name) != RestingTier.EXCLUDED
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
            op is not None
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

    def apply_custom_mood_limits(self, operator, *, planned_names=None):
        limits = self.custom_mood_limits(operator.name, planned_names=planned_names)
        if limits is not None:
            self.set_mood_limit(
                operator.name,
                lower_limit=limits["lower"],
                upper_limit=limits["upper"],
                planned_names=planned_names,
            )

    def apply_ling_xi_mood_limits(self, *, planned_names=None):
        # 设置心情阈值 for 夕，令，
        if self.config.ling_xi == 1:
            self.set_mood_limit("令", upper_limit=12, planned_names=planned_names)
            self.set_mood_limit("夕", lower_limit=12, planned_names=planned_names)
        elif self.config.ling_xi == 2:
            self.set_mood_limit("夕", upper_limit=12, planned_names=planned_names)
            self.set_mood_limit("令", lower_limit=12, planned_names=planned_names)
        elif self.config.ling_xi in (0, 3):
            self.set_mood_limit("夕", planned_names=planned_names)
            self.set_mood_limit("令", planned_names=planned_names)
        # 设置同组心情阈值
        finished = []
        for name in ["夕", "令"]:
            if (
                name in self.operators
                and not self.operators[name].room.startswith("dorm")
                and not self.operators[name].multi_group
                and self.operators[name].group != ""
                and self.operators[name].group not in finished
            ):
                for group_name in self.groups.get(self.operators[name].group, []):
                    if group_name not in ["夕", "令"] and not self.operators[
                        group_name
                    ].room.startswith("dorm"):
                        if self.config.ling_xi in [1, 2]:
                            self.set_mood_limit(
                                group_name, lower_limit=12, planned_names=planned_names
                            )
                        elif self.config.ling_xi in (0, 3):
                            self.set_mood_limit(
                                group_name, lower_limit=0, planned_names=planned_names
                            )
                finished.append(self.operators[name].group)
        for name, limits in self.config.operator_mood_limits.items():
            self.set_mood_limit(
                name,
                lower_limit=limits["lower"],
                upper_limit=limits["upper"],
                planned_names=planned_names,
            )

    def init_mood_limit(self, *, planned_names=None):
        if planned_names is None:
            planned_names = self.planned_operator_names()
        previous = getattr(self, "_applied_mood_limits", {})
        for op in self.operators.values():
            op.lower_limit, op.upper_limit = 0, 24

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
                self.set_mood_limit(
                    TOTTER, upper_limit=12, lower_limit=8, planned_names=planned_names
                )
            else:
                self.set_mood_limit(
                    TOTTER, upper_limit=24, lower_limit=20, planned_names=planned_names
                )

        for op in self.operators.values():
            self.apply_custom_mood_limits(op, planned_names=planned_names)
        # 按个人设置、令夕模式、全体设置的优先顺序收敛。
        self.apply_ling_xi_mood_limits(planned_names=planned_names)
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
            code = _compile_expression(
                expression,
                tuple(self.eval_model.nodes),
                tuple(self.eval_model.attributes),
                tuple(self.eval_model.allowed_functions),
                tuple(self.eval_model.imported_functions),
            )
            model = {e: e for e in base_room_list}
            model.update({e: e for e in MANUFACTURE_PRODUCTS | TRADE_PRODUCTS})
            model.update({e: e for e in FACILITY_TYPE_IDS.values()})
            model["op_data"] = self
            # 代码缓存不保留运行时对象；每次从当前模型和驻员状态求值。
            try:
                return eval(code, self.eval_model.imported_functions.copy(), model)
            except Exception as e:
                raise ExecutionException(e) from e
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
            counts = getattr(self, "_projection_inventory", None)
            if counts is None:
                counts = get_inventory_counts(list(experience_values))
            return sum(
                counts.get(name, 0) * value for name, value in experience_values.items()
            )
        allowed_items = {"赤金", "源石碎片", "固源岩", "装置", "龙门币"}
        if item_name not in allowed_items:
            raise ValueError(f"不支持的副表仓库资源：{item_name}")
        counts = getattr(self, "_projection_inventory", None)
        if counts is None:
            counts = get_inventory_counts([item_name])
        return counts.get(item_name, 0)

    def major_maintenance_remaining_hours(
        self, duration_operator=None, duration_hours=None
    ) -> float:
        """按总停止时长筛选后返回提前小时数；零时长只匹配不限条件。"""
        if duration_operator is not None or duration_hours is not None:
            if (
                duration_operator not in ("<", "<=", "==", "!=", ">=", ">")
                or type(duration_hours) not in (int, float)
                or not math.isfinite(duration_hours)
                or duration_hours < 0
            ):
                raise ValueError("停止时长条件需要比较符和非负有限小时数")
        info = (
            self._projection_maintenance
            if hasattr(self, "_projection_maintenance")
            else NewsChecker.get_major_maintenance(datetime.now())
        )
        if info is None or info.update_type != "major" or info.is_flash_update:
            return float("inf")
        if duration_operator is not None:
            duration = (info.end - info.start).total_seconds() / 3600
            if (
                duration <= 0
                or info.manual
                and not info.restart_after_update
                or not {
                    "<": duration < duration_hours,
                    "<=": duration <= duration_hours,
                    "==": duration == duration_hours,
                    "!=": duration != duration_hours,
                    ">=": duration >= duration_hours,
                    ">": duration > duration_hours,
                }[duration_operator]
            ):
                return float("inf")
        hours = (
            info.start - (getattr(self, "_projection_now", None) or datetime.now())
        ).total_seconds() / 3600
        if info.manual and info.active_at(datetime.now()):
            return 0.0
        return hours if hours > 0 else float("inf")

    def next_major_maintenance_check(self, now=None):
        """在维护条件阈值时唤醒调度器；停服由现有维护流程接管。"""
        thresholds = [
            hours
            for backup in self.backup_plans
            for hours in backup.major_maintenance_thresholds
        ]
        from arknights_mower.utils.logic_expression import get_logic_exp
        from arknights_mower.utils.plan import Plan

        thresholds.extend(
            hours
            for group in self.backup_groups
            if group["id"] != "default"
            for hours in Plan.maintenance_thresholds(
                get_logic_exp(copy.deepcopy(group["trigger"]))
            )
        )
        if not thresholds:
            return None
        info = NewsChecker.get_major_maintenance(now or datetime.now())
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

    def shift_group_members(self, group):
        """Return the group's fixed members and every configured follower once."""
        return list(
            dict.fromkeys(
                [
                    *[
                        name
                        for name in self.groups.get(group, [])
                        if not self.operators[name].multi_group
                    ],
                    *[
                        op.name
                        for op in self.operators.values()
                        if op.multi_group
                        and any(
                            binding["group"] == group for binding in op.group_bindings
                        )
                    ],
                ]
            )
        )

    def select_group_binding(self, name, group):
        """Select a validated binding without changing the persisted Scheduling Plan."""
        op = self.operators[name]
        if op.independent_rest:
            group = ""
        if not op.multi_group or not any(
            binding["group"] == group for binding in op.group_bindings
        ):
            return
        replacements = list(op.replacements_for_group(group))
        if op.group != group:
            if op.group:
                self.groups[op.group] = [
                    member for member in self.groups.get(op.group, []) if member != name
                ]
            if group and name not in self.groups.setdefault(group, []):
                self.groups[group].append(name)
        op.group, op.replacement = group, replacements

    def arrangement_group_transitions(self, plan, *, group_transitions=None):
        """Resolve explicit fixed-worker targets over pending state without committing it."""
        transitions = {}
        for room, names in plan.items():
            for index, name in enumerate(names):
                slots = self.plan.get(room, [])
                if index >= len(slots) or name in ("", "Current", "Free"):
                    continue
                op = self.operators.get(slots[index].agent)
                if op is None or not op.group or not self.is_group_shift_anchor(op):
                    continue
                if name == op.name:
                    transitions[op.group] = False
                elif name in op.replacement:
                    transitions.setdefault(op.group, True)
        # 全组切为零心情工作后没有触发成员；仅完整回岗安排能结束原休息状态。
        for group, resting in getattr(self, "group_shift_state", {}).items():
            if not resting or not self.is_workaholic_group(group):
                continue
            members = [
                self.operators[name]
                for name in self.shift_group_members(group)
                if not self.operators[name].multi_group
            ]
            explicit_return = any(
                not op.room.startswith("dorm")
                and plan.get(op.room, [])[op.index : op.index + 1] == [op.name]
                for op in members
            )
            if explicit_return and all(
                plan.get(op.room, [])[op.index : op.index + 1] == [op.name]
                or (
                    plan.get(op.room, [])[op.index : op.index + 1] in ([], ["Current"])
                    and (op.current_room, op.current_index) == (op.room, op.index)
                )
                for op in members
            ):
                transitions[group] = False
        return {**(group_transitions or {}), **transitions}

    def resting_binding_groups(self, operator, transitions=None):
        transitions = transitions or {}
        return [
            binding["group"]
            for binding in operator.group_bindings
            if binding["group"]
            and transitions.get(
                binding["group"], self.group_is_resting(binding["group"])
            )
        ]

    def shared_replacements(self, operator, groups):
        """Intersect every dependent binding in configured candidate order."""
        if not groups:
            return list(operator.replacement)
        return [
            name
            for name in operator.replacements_for_group(groups[0])
            if all(
                name in operator.replacements_for_group(group) for group in groups[1:]
            )
        ]

    def commit_group_shifts(self, transitions):
        """Commit completed arrangements, or transitions on an isolated projection."""
        for group in self.groups:
            if group not in self.group_shift_state:
                self.group_shift_state[group] = self.group_is_resting(group)
        recovery = getattr(self, "group_recovery_full_members", {})
        anchors = dict(getattr(self, "group_recovery_return_time", {}))
        for group, resting in transitions.items():
            if self.group_shift_state.get(group) != resting:
                recovery.pop(group, None)
                anchors.pop(group, None)
        self.group_recovery_full_members = recovery
        self.group_recovery_return_time = anchors
        self.group_shift_state.update(transitions)
        for op in self.operators.values():
            if op.multi_group:
                groups = self.resting_binding_groups(op)
                if groups:
                    self.select_group_binding(
                        op.name, op.group if op.group in groups else groups[0]
                    )

    def restore_group_shift_state(self, saved=None, recovery=None, return_time=None):
        """Legacy snapshots infer rest only from ordinary fixed members."""
        self.group_shift_state = {
            group: resting
            for group, resting in (saved or {}).items()
            if type(resting) is bool
        }
        self.group_recovery_full_members = {
            group: list(names)
            for group, names in (recovery or {}).items()
            if self.group_shift_state.get(group) and isinstance(names, (list, tuple))
        }
        self.group_recovery_return_time = {
            group: at
            for group, at in (return_time or {}).items()
            if group in self.group_recovery_full_members and isinstance(at, datetime)
        }
        self.commit_group_shifts({})

    def working_replacement_assignments(self, names, plan=None):
        """取得本次成员仍承担的其他主班工作岗位。"""
        names = set(names)
        plan = plan or {}
        sources = {}
        for name in names:
            op = self.operators[name]
            if not op.is_working():
                continue
            target = plan.get(op.current_room, [])[
                op.current_index : op.current_index + 1
            ]
            if not target or target[0] in ("Current", name):
                sources[op.current_room, op.current_index] = name
        sources.update(
            {
                (room, index): name
                for room, row in plan.items()
                if not room.startswith("dorm")
                for index, name in enumerate(row)
                if name in names
            }
        )
        assignments = {}
        for (room, index), name in sources.items():
            op = self.operators[name]
            slots = self.plan.get(room, [])
            if (room, index) == (op.room, op.index) or not 0 <= index < len(slots):
                continue
            owner = self.operators.get(slots[index].agent)
            if (
                owner is not None
                and owner.name not in names
                and self.is_same_group_primary_replacement(owner, name)
            ):
                assignments[owner.name] = name
        return assignments

    def working_replacement_blockers(self, names, plan=None):
        """共享成员保留工作替班岗位；实际离岗仍须完成交接。"""
        plan = plan or {}
        return {
            self.operators[owner].group
            for owner, name in self.working_replacement_assignments(names, plan).items()
            if not self.operators[name].multi_group
            or any(
                target == name
                and (room, index)
                != (self.operators[owner].room, self.operators[owner].index)
                for room, row in plan.items()
                for index, target in enumerate(row)
            )
        }

    def normalize_shared_arrangement(
        self,
        plan,
        transitions=None,
        *,
        reserved_replacements=None,
        explicit_slots=(),
        excluded_names=(),
    ):
        """Keep shared covers until all dependent groups return; reject conflicts.

        The caller owns the plan. No live occupancy or group state is modified.
        """
        from arknights_mower.utils.exhaust_replacement import match_replacements

        excluded_names = set(excluded_names)
        transitions = (
            self.arrangement_group_transitions(plan)
            if transitions is None
            else transitions
        )
        shifting = {
            name
            for group, resting in transitions.items()
            if resting
            for name in self.shift_group_members(group)
            if name not in excluded_names
        }
        if self.working_replacement_blockers(shifting, plan):
            return False
        followers = [
            op
            for op in self.operators.values()
            if op.multi_group
            and op.name not in excluded_names
            and not (
                (actual := self.get_current_operator(op.room, op.index)) is not None
                and actual.name in excluded_names
            )
            and (op.room, op.index) not in explicit_slots
            and (
                op.index < len(plan.get(op.room, []))
                or any(b["group"] in transitions for b in op.group_bindings)
            )
        ]
        # These sources leave only if the complete matching succeeds, so a
        # same-group fixed dormitory target can use them in this arrangement.
        departing = {
            op.name
            for op in followers
            if (op.current_room, op.current_index) == (op.room, op.index)
            and self.resting_binding_groups(op, transitions)
        }
        changes, options = {}, {}
        managed = {(op.room, op.index) for op in followers}
        reserved = (
            {
                name
                for room, names in plan.items()
                for index, name in enumerate(names)
                if (room, index) not in managed and name not in ("Free", "Current", "")
            }
            | set(
                self.reserved_product_replacements
                if reserved_replacements is None
                else reserved_replacements
            )
            | excluded_names
        )
        for op in followers:
            target = plan.get(op.room, [])[op.index : op.index + 1]
            relevant = any(b["group"] in transitions for b in op.group_bindings)
            groups = self.resting_binding_groups(op, transitions)
            if not groups:
                if (
                    op.independent_rest
                    and op.is_resting()
                    and (relevant or target != [op.name])
                ):
                    groups = [""]
                elif relevant:
                    changes[op.name] = op.name
                    continue
                else:
                    continue
            candidates = self.shared_replacements(op, groups)
            if not candidates:
                return False
            actual = self.get_current_operator(op.room, op.index)
            if "Free" in candidates and op.room.startswith("dorm"):
                # A shared open bed keeps its current recovering occupant.
                desired = (
                    target[0]
                    if target and target[0] not in (op.name, "Current")
                    else actual.name
                    if actual and actual.name != op.name
                    else "Free"
                )
                if (
                    (not target or target[0] in (op.name, "Current"))
                    and actual is not None
                    and any(
                        name == actual.name and (room, index) != (op.room, op.index)
                        for room, names in plan.items()
                        for index, name in enumerate(names)
                    )
                ):
                    desired = "Free"
                if desired not in ("Free", "Current", ""):
                    # Named recovery occupants compete with working covers in
                    # the same matching, regardless of slot iteration order.
                    options[op.name] = [desired] if desired not in reserved else []
                else:
                    changes[op.name] = desired
                continue
            preferred = ([actual.name] if actual else []) + (target or [])
            candidates = list(
                dict.fromkeys(n for n in [*preferred, *candidates] if n in candidates)
            )
            options[op.name] = [
                name
                for name in candidates
                if name not in reserved
                and name in self.operators
                and (
                    actual is not None
                    and actual.name == name
                    or not self.operators[name].current_room
                    or self.operators[name].is_resting()
                    and not self.is_dorm_replacement(name)
                    or (
                        (source := self.operators[name]).current_room in plan
                        and 0 <= source.current_index < len(plan[source.current_room])
                        and plan[source.current_room][source.current_index]
                        not in ("Current", name)
                    )
                    or (
                        name in departing
                        or any(name in names for names in plan.values())
                    )
                    and any(
                        self.is_same_group_primary_replacement(op, name, group)
                        for group in groups
                    )
                )
            ]
        assignments = match_replacements(options)
        if assignments is None:
            return False
        changes.update(assignments)
        for name, desired in changes.items():
            op = self.operators[name]
            actual = self.get_current_operator(op.room, op.index)
            if actual is not None and actual.name == desired:
                desired = "Current"
            if desired != "Current" or op.room in plan:
                plan.setdefault(op.room, ["Current"] * len(self.plan[op.room]))[
                    op.index
                ] = desired
        for room in list(plan):
            if all(name == "Current" for name in plan[room]):
                del plan[room]
        return True

    def _group_moods(self, group: str) -> list[float]:
        members = self.groups.get(group)
        if not members:
            raise ValueError(f"不存在的绑组：{group}")
        moods = [
            self.operators[name].current_mood()
            for name in members
            if self.is_group_shift_anchor(self.operators[name])
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
        self,
        room: str,
        facility: str,
        product: str | None = None,
        updated_at: str | None = None,
    ) -> None:
        """记录生产设施最近一次从游戏界面识别到的实际状态。"""
        supported = facility in FACILITY_TYPE_IDS.values() and (
            product is None
            or (facility == "manufacture" and product in MANUFACTURE_PRODUCTS)
            or (facility == "trade" and product in TRADE_PRODUCTS)
        )
        if room not in base_room_list or not supported:
            raise ValueError(f"不支持的设施状态：{room}, {facility}, {product}")
        previous = self.facility_states.get(room, {})
        if product is None and previous.get("facility") == facility:
            product = previous.get("product")
        self.facility_states[room] = {
            "facility": facility,
            "product": product,
            "updated_at": updated_at or datetime.now().isoformat(timespec="seconds"),
        }

    def run_order_replacements(self, room):
        """救急跑单名单独立于冻结的正常排班。"""
        if self.emergency_run_order_replacements is not None:
            return self.emergency_run_order_replacements.get(room, [])
        return [slot.all_replacements for slot in self.plan.get(room, [])]

    def is_run_order_room(self, room: str) -> bool:
        """按维护副表、生效排班和实际订单过滤跑单。"""
        return (
            not self.run_order_paused
            and room.startswith("room")
            and self.products.get(room) != "orundum"
            and self.facility_states.get(room, {}).get("product") != "orundum"
            and any(
                name in replacements
                for replacements in self.run_order_replacements(room)
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
        """返回实际读取的设施类型；未读取时返回未知。"""
        if room not in base_room_list:
            raise ValueError(f"不支持的设施位置：{room}")
        return self.facility_states.get(room, {}).get("facility")

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
        if room in RIGHT_SIDE_ROOM_CAPACITY:
            capacity = (
                1
                if room == "recycle" and getattr(self, "recycle_capacity", 2) == 1
                else RIGHT_SIDE_ROOM_CAPACITY[room]
            )
            res = [""] * capacity
        else:
            res = [obj.agent for obj in self.plan[room]]
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

    def restore_dorm_state(self, saved_dorms, *, group_transitions=None):
        """按床位恢复宿舍状态，保留当前排班生成的顺序和床位集合。"""
        saved_by_position = defaultdict(list)
        for dorm in saved_dorms:
            if hasattr(dorm, "position") and dorm.name:
                saved_by_position[tuple(dorm.position)].append(dorm)
        active_groups = {
            group for group, resting in (group_transitions or {}).items() if resting
        }
        inactive_groups = {
            group for group, resting in (group_transitions or {}).items() if not resting
        }
        restored = set()
        for dorm in self.all_dorms():
            if dorm not in self.group_dorm and not self.is_effective_free_slot(
                dorm, active_groups=active_groups, inactive_groups=inactive_groups
            ):
                continue
            position = tuple(dorm.position)
            current = self.get_current_operator(*position)
            saved = next(
                (
                    saved
                    for saved in saved_by_position[position]
                    if (current is None or current.name == saved.name)
                    and self.is_recovery_dorm(
                        dorm, saved.name, group_transitions=group_transitions
                    )
                ),
                None,
            )
            if saved is not None:
                dorm.name, dorm.time = saved.name, saved.time
                restored.add((position, saved.name))
        return [
            dorm
            for dorm in saved_dorms
            if dorm.name and (tuple(dorm.position), dorm.name) not in restored
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
        *,
        group_transitions=None,
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
        _, previous_bed = self.get_dorm_by_name(
            name, group_transitions=group_transitions
        )
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
            from arknights_mower.utils.recall_estimates import observe_work_rate

            learned_rate = observe_work_rate(
                agent,
                mood,
                current_room,
                current_index,
                datetime.now(),
                preserve=preserve_depletion_rate or mood == 0,
            )
            agent.mood_is_prediction = False
            agent.work_rate_sample_eligible = (
                not preserve_depletion_rate and 0 < mood < 24
            )
            if learned_rate is not None:
                agent.depletion_rate = learned_rate
                logger.debug(f"更新 {agent.name} 心情掉率为：{agent.depletion_rate}")
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
            idx, dorm = self.get_dorm_by_name(name, group_transitions=group_transitions)
            if dorm and dorm.name == name:
                dorm.reset()
        if update_time or (agent.current_room, agent.current_index) != (
            current_room,
            current_index,
        ):
            agent.exhaust_time = None
            logger.debug(f"{name} 观测或位置变化，清除旧工作期限")
        agent.current_room = current_room
        agent.current_index = current_index
        agent.mood = mood
        if self.mood_calculation_enabled:
            if current_room == "train":
                agent.depletion_rate = 0
            self.mood_model.move(name, current_room, current_index)
            if update_time:
                self.mood_model.observe(name, mood)
        if returned_to_post and not to_dorm and not preserve_depletion_rate:
            # 实际回班结束本人的本轮恢复；临时换组后离岗不能重新加入旧等待。
            for group, names in self.group_recovery_full_members.items():
                self.group_recovery_full_members[group] = [
                    member for member in names if member != name
                ]
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
        if current_room == "train" and current_index == 0:
            agent.resting_from_train = True
        elif (current_room and not to_dorm) or mood >= 24:
            agent.resting_from_train = False
        if mood >= 24:
            agent.clear_dorm_recovery()
        # 如果是高效组且没有记录时间，则返还index
        if to_dorm:
            idx, dorm = self.get_dorm_by_name(name, group_transitions=group_transitions)
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

    def invalidate_dorm_time(self, room):
        """实际宿舍阵容变化后，整房恢复时间等待最终阵容实读。"""
        for bed in self.all_dorms():
            if bed.position[0] == room:
                bed.time = None
        for op in self.operators.values():
            if op.current_room == room:
                op.dorm_recovery_observation = None

    def refresh_dorm_time(self, room, index, agent, *, group_transitions=None):
        _name = agent["agent"]
        operator = self.operators.get(_name)
        if (
            room.startswith("dorm")
            and operator is not None
            and (
                getattr(operator, "current_room", None),
                getattr(operator, "current_index", None),
            )
            == (room, index)
            and operator.time_stamp is not None
            and not getattr(operator, "mood_is_prediction", False)
            and 0 <= operator.mood <= 24
            and isinstance(agent.get("time"), datetime)
        ):
            operator.dorm_recovery_observation = (
                (room, index),
                operator.time_stamp,
                agent["time"],
            )
        # 此方法也会作为无界函数绑定到轻量读房测试对象，避免依赖对象上存在
        # all_dorms 方法；旧对象没有 group_dorm 时按普通 Free 床位处理。
        dorms = [*self.dorm, *getattr(self, "group_dorm", [])]
        for dorm in dorms:
            if dorm.position[0] == room and dorm.position[1] == index:
                if not Operators.is_recovery_dorm(
                    self, dorm, _name, group_transitions=group_transitions
                ):
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
                    from arknights_mower.utils.recall_estimates import (
                        observe_recovery_rate,
                    )

                    observe_recovery_rate(self, dorm)
                break
        # 记录真实用尽时间
        if room in self.true_exhaust_room and _name in self.operators.keys():
            _agent = self.operators[_name]
            _agent.exhaust_time = Operator.exhaust_time_at_lower_limit(
                _agent, agent["time"]
            )
            logger.debug(f"{_name} 真实用尽时间：{_agent.exhaust_time}")
            return

    def correct_dorm(self, *, group_transitions=None):
        for dorm in self.all_dorms():
            if dorm.name != "" and dorm.name in self.operators.keys():
                if not self.is_recovery_dorm(
                    dorm, dorm.name, group_transitions=group_transitions
                ):
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
                    if (
                        not self.mood_calculation_enabled
                        and dorm.time is not None
                        and dorm.time < datetime.now()
                    ):
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

    def get_refresh_index(self, room, plan, *, group_transitions=None):
        """动态恢复位置共用计时读取，不受满心情清退开关影响。"""
        if not room.startswith("dorm"):
            return []
        recovery_beds = [bed for bed in self.all_dorms() if bed.position[0] == room]
        ret = []
        for i, name in enumerate(plan):
            if name == "Current":
                current = self.get_current_operator(room, i)
                name = current.name if current is not None else None
            if any(
                bed.position[1] == i
                and self.is_recovery_dorm(
                    bed, name, group_transitions=group_transitions
                )
                for bed in recovery_beds
            ):
                ret.append(i)
        return ret

    def get_dorm_by_name(self, name, *, group_transitions=None):
        if name not in self.operators:
            return None, None
        _op = self.operators[name]
        logger.debug(name)
        for idx, dorm in enumerate(self.all_dorms()):
            if (
                dorm.position[0] == _op.current_room
                and dorm.position[1] == _op.current_index
                and self.is_recovery_dorm(
                    dorm, name, group_transitions=group_transitions
                )
            ):
                logger.debug(idx)
                logger.debug(dorm)
                return idx, dorm
        return None, None

    def add(self, operator, *, planned_names=None):
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
            if (
                operator.multi_group
                and not operator.independent_rest
                and any(
                    binding["group"] == exist.group
                    for binding in operator.group_bindings
                )
            ):
                operator.group = exist.group
                operator.replacement = list(
                    operator.replacements_for_group(exist.group)
                )
            if hasattr(exist, "_projected_mood_resting"):
                operator._projected_mood_resting = exist._projected_mood_resting
            operator.mood = exist.mood
            operator.time_stamp = exist.time_stamp
            operator.mood_is_prediction = getattr(exist, "mood_is_prediction", False)
            operator.depletion_rate = exist.depletion_rate
            operator.work_rate_sample_eligible = getattr(
                exist, "work_rate_sample_eligible", True
            )
            operator.recall_work_rate = getattr(exist, "recall_work_rate", None)
            operator.recall_work_rate_checked = getattr(
                exist, "recall_work_rate_checked", False
            )
            if getattr(self, "_projection_now", None) is not None:
                operator._current_room = exist.current_room
                operator.__dict__["current_index"] = exist.current_index
            else:
                operator.current_room = exist.current_room
                operator.current_index = exist.current_index
            operator.dorm_position_version = getattr(exist, "dorm_position_version", 0)
            operator.dorm_recovery_room = getattr(exist, "dorm_recovery_room", "")
            operator.dorm_recovery_index = getattr(exist, "dorm_recovery_index", -1)
            operator.dorm_recovery_observation = getattr(
                exist, "dorm_recovery_observation", None
            )
            operator.resting_from_train = getattr(exist, "resting_from_train", False)
            operator.dorm_recovery_fixed = getattr(exist, "dorm_recovery_fixed", ())
            operator.dorm_mood_fallback = getattr(exist, "dorm_mood_fallback", "")
            operator.dorm_mood_peers = getattr(exist, "dorm_mood_peers", {}).copy()
            operator.idle_rest_check = getattr(exist, "idle_rest_check", None)
            operator.rest_mood_release_limit = getattr(
                exist, "rest_mood_release_limit", None
            )
            operator.temporary_dorm_fill = getattr(exist, "temporary_dorm_fill", False)
            operator.individual_return_window = getattr(
                exist, "individual_return_window", None
            )
        self.operators[operator.name] = operator
        if self.mood_calculation_enabled:
            operator._mood_model = self.mood_model
            operator._mood_conf = self.runtime_conf or config.conf
            operator._projection_now = getattr(self, "_projection_now", None)
            operator._projection_deadlines = getattr(
                self, "_projection_deadlines", None
            )
        self.apply_custom_mood_limits(operator, planned_names=planned_names)
        self.apply_ling_xi_mood_limits(planned_names=planned_names)
        # 需要用尽心情干员逻辑
        if (
            operator.exhaust_require
            and (not operator.multi_group or operator.independent_rest)
            and not (operator.group and operator.room.startswith("dorm"))
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
        if (
            operator.rest_in_full
            and not operator.multi_group
            and not (operator.group and operator.room.startswith("dorm"))
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

    def is_group_shift_anchor(self, op):
        """只有普通固定工作主班参与绑组上下班，候补不参与。"""
        return (
            op.is_high()
            and not op.multi_group
            and not op.workaholic
            and not op.room.startswith("dorm")
            and not self._can_standby(op)
        )

    def workaholic_follows_resting_group(self, op):
        """零心情成员不触发换班，但仍等待普通工作主班所在组回班。"""
        return bool(
            op.workaholic
            and op.group
            and not op.multi_group
            and not op.room.startswith("dorm")
            and self.group_is_resting(op.group)
            and any(
                self.is_group_shift_anchor(self.operators[name])
                for name in self.groups.get(op.group, ())
            )
        )

    def is_workaholic_group(self, group):
        """只含零心情固定工作主班的组无需继续等待普通恢复触发。"""
        workers = [
            self.operators[name]
            for name in self.shift_group_members(group)
            if not self.operators[name].room.startswith("dorm")
            and not self.operators[name].multi_group
        ]
        return bool(workers) and all(op.workaholic for op in workers)

    def resting_threshold_for(self, op):
        override = getattr(self.config, "resting_threshold_override", None)
        if override is not None:
            return override
        thresholds = getattr(self.config, "group_resting_thresholds", {})
        if op.group and not op.multi_group:
            return thresholds.get(op.group, self.config.resting_threshold)
        return self.config.resting_threshold

    def rescue_mood_threshold(self, op):
        """按个人心情上下限换算现有急救阈值。"""
        return op.lower_limit + (op.upper_limit - op.lower_limit) * (
            self.resting_threshold_for(op)
            * (self.runtime_conf or config.conf).rescue_threshold
        )

    def resting_mood_threshold(self, op):
        threshold = op.lower_limit + (
            op.upper_limit - op.lower_limit
        ) * self.resting_threshold_for(op)
        return (
            threshold
            if self.custom_mood_limits(op.name) is not None
            else int(threshold)
        )

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
        return (
            bool(self.resting_binding_groups(op))
            if op.multi_group
            else self.group_is_resting(op.group)
        )

    def has_dorm_groups(self):
        """仅实际填写了宿舍组名的配置启用宿舍绑组处理。"""
        return any(
            op.group and op.room.startswith("dorm") for op in self.operators.values()
        )

    def group_is_resting(self, group):
        """Confirmed state survives bed release; unknown legacy groups use anchors."""
        if group in self.group_shift_state:
            return self.group_shift_state[group]
        return any(
            self.is_group_shift_anchor(self.operators[name])
            and self.operators[name].is_resting()
            for name in self.groups.get(group, [])
        )

    def is_same_group_primary_replacement(self, operator, name, group=None):
        """同一非空组内，不同主班可按对应绑组的配置互填替班。"""
        if group is None and operator.independent_rest:
            return any(
                self.is_same_group_primary_replacement(operator, name, binding)
                for binding in self.resting_binding_groups(operator)
            )
        cover = self.operators.get(name)
        group = operator.group if group is None else group
        return bool(
            operator.is_high()
            and cover is not None
            and cover.is_high()
            and group
            and (
                any(binding["group"] == group for binding in cover.group_bindings)
                if cover.multi_group
                else group == cover.group
            )
            and name in operator.replacements_for_group(group)
            and operator.name != name
        )

    def is_auto_free_dorm_operator(self, operator, *, group_transitions=None):
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
        replacements = (
            self.shared_replacements(
                operator, self.resting_binding_groups(operator, group_transitions)
            )
            if operator.multi_group
            else operator.replacement
        )
        return "Free" in replacements

    def is_auto_free_dorm_slot(self, room, index, *, group_transitions=None):
        slots = self.plan.get(room, [])
        if not room.startswith("dorm") or not 0 <= index < len(slots):
            return False
        resident = self.operators.get(slots[index].agent)
        return resident is not None and self.is_auto_free_dorm_operator(
            resident, group_transitions=group_transitions
        )

    def is_dynamic_dorm_position(
        self, room, index, name=None, *, group_transitions=None
    ):
        """判断某位置在当前阵容中是否按动态床位处理。"""
        slots = self.plan.get(room, [])
        if not room.startswith("dorm") or not 0 <= index < len(slots):
            return False
        slot = slots[index]
        if slot.agent == "Free":
            return True
        if not self.is_auto_free_dorm_slot(
            room, index, group_transitions=group_transitions
        ):
            return False
        # 固定宿舍干员本人在位时仍是宿管，不是休息者。
        return name is None or name not in (slot.agent, "Current")

    def is_dorm_replacement(self, name):
        """已在固定宿舍岗位上的替班不能被其他岗位借走。"""
        op = self.operators[name]
        return self.is_dorm_replacement_for_slot(
            name, op.current_room, op.current_index
        )

    def is_dorm_replacement_for_slot(
        self, name, room, index, *, group_transitions=None
    ):
        """按目标位置识别绑组宿舍替班，也用于尚未入驻时的选人保护。"""
        slots = self.plan.get(room, [])
        if not room.startswith("dorm") or not 0 <= index < len(slots):
            return False
        slot = slots[index]
        return bool(
            slot.group
            and slot.agent not in ("Free", "菲亚梅塔")
            and not self.is_auto_free_dorm_slot(
                room, index, group_transitions=group_transitions
            )
            and name in slot.all_replacements
        )

    def group_dorm_bed_count(self, group):
        """按目标组的配置成员和替班列计算恢复位置，入住仍须完整匹配。"""
        count = 0
        for name in self.shift_group_members(group):
            operator = self.operators[name]
            if not operator.room.startswith("dorm"):
                continue
            replacements = operator.replacements_for_group(group)
            if "Free" in replacements or any(
                self.is_same_group_primary_replacement(operator, cover, group)
                and not self.operators[cover].room.startswith("dorm")
                and not self.operators[cover].workaholic
                for cover in replacements
            ):
                count += 1
        return count

    def project_arrangements(self, plans, *, now=None, runtime_conf=None):
        """按执行顺序推演排班后的驻员和恢复床位，不产生实际换人副作用。

        阵容未变的宿舍保留恢复时间；受影响宿舍等待最终阵容实读。
        产物切换和回班规划共用这一份位置语义，不能只改工位而留下旧床位。
        """
        projected = copy.copy(self)
        projected.runtime_conf = runtime_conf or self.runtime_conf or config.conf
        projected._projection_now = now or getattr(self, "_projection_now", None)
        projected.recall_recovery_rates = dict(
            getattr(self, "recall_recovery_rates", {})
        )
        memo = {}
        if self.mood_calculation_enabled:
            projected.mood_model = copy.deepcopy(self.mood_model, memo)
        projected.operators = copy.deepcopy(self.operators, memo)
        if self.mood_calculation_enabled:
            for op in projected.operators.values():
                op._mood_model = projected.mood_model
        projected.groups = copy.deepcopy(self.groups)
        projected.group_shift_state = dict(self.group_shift_state)
        projected.group_recovery_full_members = copy.deepcopy(
            getattr(self, "group_recovery_full_members", {})
        )
        projected.group_recovery_return_time = dict(
            getattr(self, "group_recovery_return_time", {})
        )
        projected.urgent_recovery_supporters = copy.deepcopy(
            getattr(self, "urgent_recovery_supporters", {})
        )
        projected.dorm = copy.deepcopy(self.dorm)
        projected.group_dorm = copy.deepcopy(getattr(self, "group_dorm", []))
        projected._apply_projected_arrangements(plans, now=projected._projection_now)
        return projected

    def _apply_projected_arrangements(self, plans, *, now=None):
        """仅在调用方独占的隔离副本上推进驻员和床位，不再复制副本。"""
        self._projection_now = now or getattr(self, "_projection_now", None)
        now = self._projection_now or datetime.now()
        if self.mood_calculation_enabled:
            self.mood_model.advance(now)
        if getattr(self, "_projection_now", None) is not None:
            self._projection_deadlines = {}
        for op in self.operators.values():
            # 位置预演保留原心情的房间状态，不把入宿意图当作实读。
            if not hasattr(op, "_projected_mood_resting"):
                op._projected_mood_resting = op.is_resting()
        for plan in plans:
            previous_positions = {
                name: (op.current_room, op.current_index)
                for name, op in self.operators.items()
            }
            self.commit_group_shifts(self.arrangement_group_transitions(plan))
            changed_slots = {
                (room, index)
                for room, names in plan.items()
                for index, name in enumerate(names)
                if name != "Current"
                and (
                    (
                        occupant.name
                        if (occupant := self.get_current_operator(room, index))
                        is not None
                        else ""
                    )
                    != ("" if name == "Free" else name)
                )
            }
            changed_dorms = {
                room for room, _ in changed_slots if room.startswith("dorm")
            }
            changed_dorms.update(
                op.current_room
                for room, names in plan.items()
                for index, name in enumerate(names)
                if (op := self.operators.get(name)) is not None
                and op.current_room.startswith("dorm")
                and (op.current_room, op.current_index) != (room, index)
            )
            recovery_times = {
                bed.name: (bed.position, bed.time)
                for bed in self.all_dorms()
                if bed.name
            }
            for op in self.operators.values():
                if (op.current_room, op.current_index) in changed_slots:
                    op._current_room = ""
                    op.__dict__["current_index"] = -1
            for room, names in plan.items():
                for index, name in enumerate(names):
                    if name in self.operators:
                        op = self.operators[name]
                        # 投影统一在末尾同步模型，不能通过属性通知推进真实时钟。
                        op._current_room = room
                        op.__dict__["current_index"] = index
                        op.rest_mood_release_limit = None
            for op in self.operators.values():
                if previous_positions[op.name] != (op.current_room, op.current_index):
                    op.clear_dorm_recovery()
                    op.dorm_position_version = (
                        getattr(op, "dorm_position_version", 0) + 1
                    )
                if not op.is_resting():
                    op.temporary_dorm_fill = False
            for bed in self.all_dorms():
                occupant = self.get_current_operator(*bed.position)
                if occupant is not None and self.is_recovery_dorm(bed, occupant.name):
                    bed.name = occupant.name
                    old_position, old_time = recovery_times.get(
                        occupant.name, (None, None)
                    )
                    bed.time = (
                        old_time
                        if old_position == bed.position
                        and bed.position[0] not in changed_dorms
                        else None
                    )
                else:
                    bed.reset()

        if self.mood_calculation_enabled:
            from arknights_mower.utils.calculated_mood import sync_model

            sync_model(self, max(now, self.mood_model.at or datetime.min))
            for op in self.operators.values():
                op._projection_now = self._projection_now
                op._projection_deadlines = getattr(self, "_projection_deadlines", None)

    def all_dorms(self):
        """返回动态床位与只供配置内同组工作替班恢复的固定床位。"""
        return [*self.dorm, *getattr(self, "group_dorm", [])]

    def get_group_dorm(self, room, index):
        return next(
            (
                dorm
                for dorm in getattr(self, "group_dorm", [])
                if dorm.position == (room, index)
            ),
            None,
        )

    def is_recovery_dorm(self, dorm, name, *, group_transitions=None):
        """动态位置只跟踪实际休息者，不跟踪回归的固定宿舍成员。"""
        if dorm in self.dorm:
            room, index = dorm.position
            return self.is_dynamic_dorm_position(
                room, index, name, group_transitions=group_transitions
            )
        if dorm in getattr(self, "group_dorm", []):
            room, index = dorm.position
            slots = self.plan.get(room, [])
            if not 0 <= index < len(slots):
                return False
            resident = self.operators.get(slots[index].agent)
            cover = self.operators.get(name)
            if (
                resident is None
                or cover is None
                or cover.room.startswith("dorm")
                or self.is_auto_free_dorm_operator(
                    resident, group_transitions=group_transitions
                )
            ):
                return False
            groups = (
                self.resting_binding_groups(resident, group_transitions)
                or [resident.group]
                if resident.multi_group
                else [resident.group]
            )
            return any(
                self.is_same_group_primary_replacement(resident, name, group)
                for group in groups
            )
        return False

    def replacement_exhausted(self, name, now=None, *, operator=None):
        """按有效排班判断替班心情；唯一普通替班与零心情工作不被下限拦截。"""
        if self.config.is_workaholic(name):
            return False
        if operator is not None:
            if operator.room.startswith("dorm"):
                return False
            replacements = (
                self.shared_replacements(
                    operator, self.resting_binding_groups(operator)
                )
                if operator.multi_group
                else operator.replacement
            )
            ordinary = {
                cover
                for cover in replacements
                if cover != "Free" and cover not in TRADE_ORDER_AGENTS
            }
            if ordinary == {name}:
                return False
        from arknights_mower.utils.dorm_candidates import dorm_candidate_mood

        candidate = self.operators.get(name)
        mood = dorm_candidate_mood(self, name, now)
        return (
            candidate is not None and mood is not None and mood <= candidate.lower_limit
        )

    def replacement_candidates(self, operator, *, replacement_override=None):
        """工作替班按配置顺序取用；未豁免的耗尽候补稳定移到末尾。"""
        replacements = (
            self.shared_replacements(operator, self.resting_binding_groups(operator))
            if operator.multi_group
            else operator.replacement
        )
        if replacement_override is not None:
            replacements = replacement_override
        candidates = [
            name
            for name in replacements
            if name != "Free"
            and not (operator.room.startswith("dorm") and self.rest_mood_complete(name))
        ]
        if not operator.room.startswith("dorm") and operator.name != "菲亚梅塔":
            now = getattr(self, "_projection_now", None) or datetime.now()

            def exhausted_last(name):
                return (self.replacement_exhausted(name, now, operator=operator),)

            # 候补列表本身就是效率优先级；仍可工作的候补严格保持配置顺序。
            # 未豁免且到个人下限的候补只移到列表末尾，不从候补集合中删除，
            # 避免其他分床/预留逻辑失去对该干员的完整候补关系。
            return sorted(candidates, key=exhausted_last)
        if (
            not operator.room.startswith("dorm")
            or not operator.group
            or operator.name == "菲亚梅塔"
        ):
            return candidates
        now = getattr(self, "_projection_now", None) or datetime.now()

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
                and not v.multi_group
                and v.operator_type != "low"
                and not v.workaholic
                and (not v.group or self.is_group_shift_anchor(v))
                and not self.is_standby(k)
            ):
                mood = v.current_mood()
                if not isinstance(mood, (int, float)) or not 0 <= mood <= 24:
                    continue
                current_mood += mood - v.lower_limit
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
        resident = self.operators.get(slot.agent)
        if resident is None:
            return False
        groups = (
            [binding["group"] for binding in resident.group_bindings]
            if resident.multi_group
            else [resident.group]
        )
        active_groups = set(active_groups or ())
        inactive_groups = set(inactive_groups or ())
        resting = [
            group
            for group in groups
            if group
            and group not in inactive_groups
            and (group in active_groups or self.group_is_resting(group))
        ]
        if resting:
            return all(
                "Free" in resident.replacements_for_group(group) for group in resting
            )
        # 已经有普通休息者实际入住或被本轮预约时，在固定成员回班前仍有效。
        return bool(
            resident.group
            and "Free" in resident.replacement
            and not inactive_groups.intersection(groups)
            and dorm.name
            and dorm.name != resident.name
        )

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

    def dorm_capacity_allows(
        self, name, position, *, active_groups=None, plan=None, group_transitions=None
    ):
        """绑组 Free 按数量供同组工作主班及后三层使用，不绑定物理位置。"""
        if resting_tier(self, name) > RestingTier.PRIORITY_REPLACEMENT:
            return True
        if not any(
            slot.agent != "Free" and "Free" in slot.all_replacements
            for room, slots in self.plan.items()
            if room.startswith("dorm")
            for slot in slots
        ):
            return True
        plan = plan or {}
        # 已执行的工作房间会移出 plan；任务仍持有尚待读房确认的完整换班状态。
        transitions = self.arrangement_group_transitions(
            plan, group_transitions=group_transitions
        )
        transitions.update({group: True for group in active_groups or ()})
        active = {group for group, resting in transitions.items() if resting}
        inactive = {group for group, resting in transitions.items() if not resting}
        beds = {bed.position: bed for bed in self.dorm}
        moving = {
            member
            for row in plan.values()
            for member in row
            if member not in ("", "Current", "Free")
        } | {name}
        capacities, residents = [], set()
        for room, slots in self.plan.items():
            if not room.startswith("dorm"):
                continue
            for index, slot in enumerate(slots):
                location = (room, index)
                current = self.get_current_operator(room, index)
                bed = beds.get(location) or Dormitory(
                    location, current.name if current else ""
                )
                if not self.is_effective_free_slot(
                    bed, active_groups=active, inactive_groups=inactive
                ):
                    continue
                if slot.agent == "Free":
                    capacities.append(None)
                else:
                    owner = self.operators[slot.agent]
                    groups = (
                        [binding["group"] for binding in owner.group_bindings]
                        if owner.multi_group
                        else [owner.group]
                    )
                    capacities.append(
                        {
                            group
                            for group in groups
                            if "Free" in owner.replacements_for_group(group)
                            and group not in inactive
                            and (group in active or self.group_is_resting(group))
                        }
                    )
                row = plan.get(room, [])
                resident = row[index] if index < len(row) else "Current"
                if resident == "Current":
                    # 缓存姓名可能陈旧；预约由调用方的明确安排覆盖实际驻员。
                    resident = current.name if current else ""
                    if resident in moving:
                        resident = ""
                if location == position:
                    resident = name
                if (
                    resident in self.operators
                    and resident != slot.agent
                    and resting_tier(self, resident) <= RestingTier.PRIORITY_REPLACEMENT
                ):
                    residents.add(resident)

        # 给受保护住员匹配额度；后三层可使用任意剩余额度。
        # 复用替班匹配，使跨组主班让出普通额度，不受实际床号影响。
        from arknights_mower.utils.exhaust_replacement import match_replacements

        residents.add(name)
        choices = {}
        for resident in sorted(residents):
            op = self.operators.get(resident)
            groups = (
                {binding["group"] for binding in op.group_bindings}
                if op is not None and op.multi_group
                else {op.group}
                if op is not None
                else set()
            )
            choices[resident] = sorted(
                [
                    index
                    for index, allowed in enumerate(capacities)
                    if allowed is None
                    or op is not None
                    and op.is_high()
                    and not op.room.startswith("dorm")
                    and groups.intersection(allowed)
                ],
                # 同组主班优先计入绑组动态额度，普通额度留给其他前四层。
                key=lambda index: capacities[index] is None,
            )
        return (
            match_replacements(
                choices,
                preferred={
                    index
                    for index, groups in enumerate(capacities)
                    if groups is not None
                },
            )
            is not None
        )

    def _slot_takable(
        self,
        dorm,
        requester=None,
        active_groups=None,
        plan=None,
        group_transitions=None,
    ):
        """有效动态床位按共享恢复层级决定是否允许接管。"""
        transitions = self.arrangement_group_transitions(
            plan or {}, group_transitions=group_transitions
        )
        transitions.update({group: True for group in active_groups or ()})
        active = {group for group, resting in transitions.items() if resting}
        inactive = {group for group, resting in transitions.items() if not resting}
        if not self.is_effective_free_slot(
            dorm, active_groups=active, inactive_groups=inactive
        ):
            return False
        if requester is not None and not self.dorm_capacity_allows(
            requester, dorm.position, plan=plan, group_transitions=transitions
        ):
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
            and self.is_recovery_dorm(
                dorm, resident.name, group_transitions=transitions
            )
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
        if requester is None:
            return False
        return bed_takeover_allowed(self, requester, name)

    def dorm_roommates(self, room, index=None, *, plan=None):
        """合并实际驻员、床位预约和本轮明确安排，排除离岗及被替换者。"""
        plan = plan or {}
        moving = {
            name
            for row in plan.values()
            for name in row
            if name not in ("", "Free", "Current")
        }
        beds = {bed.position: bed for bed in self.all_dorms()}
        row = plan.get(room, [])
        names = []
        for position in range(len(self.plan.get(room, []))):
            if position == index:
                continue
            if position < len(row) and row[position] != "Current":
                name = row[position]
            else:
                current = self.get_current_operator(room, position)
                name = current.name if current else ""
                bed = beds.get((room, position))
                if bed is not None and bed.name:
                    name = bed.name
                if name in moving:
                    continue
            if name not in ("", "Free", "Current"):
                names.append(name)
        return names

    def dorm_isolation_cost(self, name, room, index=None, *, plan=None):
        """统计入住后的同组室友人数，供分床和入住前交换使用。"""
        if not (self.runtime_conf or config.conf).dorm_isolation:
            return 0
        roommates = set(self.dorm_roommates(room, index, plan=plan))
        roommates.discard(name)
        cost = 0
        for group in (self.runtime_conf or config.conf).dorm_isolation:
            if name not in group:
                continue
            shared = roommates.intersection(group)
            cost += len(shared)
        return cost

    def ordered_dorms(self, *, active_groups=None, inactive_groups=None):
        """按高优位和低优位选项排列有效床位；未列低优位按宿舍顺序补后。"""
        order = effective_dorm_order(self.config.dorm_order)
        order += [
            f"{room}_low"
            for room in order.copy()
            if not room.endswith("_low") and f"{room}_low" not in order
        ]
        rank = {value: index for index, value in enumerate(order)}
        effective = {
            bed.position
            for bed in self.dorm
            if self.is_effective_free_slot(
                bed, active_groups=active_groups, inactive_groups=inactive_groups
            )
        }
        first = {}
        for room, index in effective:
            first[room] = min(first.get(room, index), index)

        def key(bed):
            room, index = bed.position
            option = room if first.get(room) == index else f"{room}_low"
            return bed.position not in effective, rank.get(option, len(rank)), index

        return sorted(self.dorm, key=key)

    def _find_dorm_slot(
        self, name, used, *, active_groups=None, plan=None, isolation=True
    ):
        from arknights_mower.utils.dorm_recovery import single_recovery_bed_cost
        from arknights_mower.utils.dorm_skills import is_single_recovery_manager

        if self.rest_mood_complete(name) and not self.is_free_room_excluded(name):
            return None
        if resting_tier(self, name) == RestingTier.EXCLUDED:
            return None
        is_high = resting_tier(self, name) <= RestingTier.MAIN
        max_count = sum(1 for key in self.plan if key.startswith("dorm"))
        indices = {bed.position: index for index, bed in enumerate(self.dorm)}
        order = [
            indices[bed.position]
            for bed in self.ordered_dorms(active_groups=active_groups)
        ]
        explicit_order = any(item.endswith("_low") for item in self.config.dorm_order)
        if not is_high and not explicit_order:
            order = order[max_count:] + order[:max_count]
        candidates = [
            i
            for i in order
            if i not in used
            and self._slot_takable(
                self.dorm[i],
                requester=name,
                active_groups=active_groups,
                plan=plan,
            )
        ]
        now = getattr(self, "_projection_now", None) or datetime.now()
        compatible_beds = [
            self.dorm[index]
            for index in order
            if self.is_effective_free_slot(
                self.dorm[index], active_groups=active_groups
            )
        ]
        single_manager = is_single_recovery_manager(name)

        def takeover_cost(index):
            bed = self.dorm[index]
            single_cost = (
                single_recovery_bed_cost(bed, compatible_beds) if single_manager else 0
            )
            if not bed.name:
                return (
                    0,
                    0,
                    single_cost,
                    0,
                    self.dorm_isolation_cost(name, *bed.position, plan=plan)
                    if isolation
                    else 0,
                )
            tier, recovery_order = resting_key(self, bed.name, now)
            # 先使用空位和已回满补位者，再按层级接管未完成恢复者。
            return (
                1 if is_full_dorm_filler(self, bed.name, now) else 2,
                -tier,
                single_cost,
                self.dorm_isolation_cost(name, *bed.position, plan=plan)
                if isolation
                else 0,
                -recovery_order,
            )

        return min(candidates, key=takeover_cost, default=None)

    def has_resting_anchor(self, group=None):
        """是否已有能为候补提供回班时机的必需恢复者。"""
        return any(
            bed.name in self.operators
            and self.is_effective_free_slot(bed)
            and (op := self.operators[bed.name]).is_high()
            and self.is_group_shift_anchor(op)
            and (op.current_room, op.current_index) == bed.position
            and has_resting_mood(op)
            and resting_mood(op) < op.upper_limit
            and not self.rest_mood_complete(op.name)
            and (group is None or op.group == group)
            for bed in self.all_dorms()
        )

    def standby_candidates(self, names):
        """返回本轮有床则休息、无床可待命的显式候补。"""
        # 必需组员确实需要恢复心情时才允许同组候补待命，避免满心情组员在选人
        # 阶段被释放后，整组既没有恢复心情者，也没有回班计时来源。
        anchor_groups = {
            op.group
            for op in (self.operators[n] for n in names)
            if (op.group and op.is_high() and self.is_group_shift_anchor(op))
            and not op.room.startswith("dorm")
            and 0 <= op.mood < op.upper_limit
            and op.current_mood() < op.upper_limit
        }

        def has_anchor(group):
            return bool(group) and (
                group in anchor_groups or self.has_resting_anchor(group)
            )

        return {
            name
            for name in names
            if self._can_standby(self.operators[name])
            and (
                has_anchor(self.operators[name].group)
                or self.operators[name].independent_rest
                and any(
                    has_anchor(binding["group"])
                    for binding in self.operators[name].group_bindings
                )
                or not self.operators[name].group
                and not self.operators[name].independent_rest
                and self.has_resting_anchor()
            )
        }

    def assign_dorm_group(
        self, names, active_groups=None, plan=None, *, reserved_slots=()
    ):
        """先保障必需床位；候补有床则休息，无床则随组离岗待命。"""
        # 保留干员随组离岗仍须有床；上限完成不能授权将其安排为空闲。
        names = [
            name
            for name in names
            if not self.rest_mood_complete(name) or self.is_free_room_excluded(name)
        ]
        used = {
            index
            for index, bed in enumerate(self.dorm)
            if bed.position in reserved_slots
        }
        assignments = []
        optional = {
            name
            for name in self.standby_candidates(names)
            if not self.is_free_room_excluded(name)
        }
        ordered_names = sorted(
            names,
            key=lambda name: (
                name in optional,
                is_full_dynamic_candidate(self, name),
                resting_key(self, name),
            ),
        )
        pending = copy.deepcopy(plan or {})
        for name in ordered_names:
            index = self._find_dorm_slot(
                name, used, active_groups=active_groups, plan=pending
            )
            if index is None:
                if name in optional:
                    continue
                logger.debug(f"没有足够宿舍位可安排整组必需休息成员{names}")
                return None
            used.add(index)
            assignments.append((name, index))
            room, position = self.dorm[index].position
            pending.setdefault(room, ["Current"] * len(self.plan[room]))[position] = (
                name
            )

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

    def _schedule_validation_key(self):
        """Identify all effective configuration consumed by merged-plan validation."""
        return (
            tuple(
                (
                    room,
                    tuple(
                        (
                            slot.agent,
                            slot.facility,
                            slot.product,
                            tuple(
                                (binding["group"], tuple(binding["replacement"]))
                                for binding in slot.bindings
                            ),
                        )
                        for slot in slots
                    ),
                )
                for room, slots in self.plan.items()
            ),
            json.dumps(vars(self.config), sort_keys=True, default=sorted),
            tuple(sorted(self.products.items())),
            tuple(sorted(self.maintenance_primary_slots)),
            tuple(
                sorted(
                    (task["group"], task["action"], task.get("mode", "once"))
                    for backup, active in zip(self.backup_plans, self.plan_condition)
                    if active
                    for task in backup.group_tasks
                )
            ),
        )

    def validate_backup_plans(
        self, *, max_seconds=None, check_owned=True, refresh_roster=True
    ):
        """独立检查可能的副表组合；可选耗时预算覆盖条件分析和组合检查。"""
        from arknights_mower.utils.backup_validation import (
            BackupValidationLimitExceeded,
            check_validation_deadline,
            possible_backup_conditions,
            validate_backup_facilities,
        )
        from arknights_mower.utils.schedule_roster import validate_owned_operators

        if error := validate_backup_facilities(
            self.global_plan["default_plan"],
            self.backup_plans,
            product_switching_enabled=getattr(
                getattr((self.runtime_conf or config.conf), "product_switching", None),
                "enable",
                False,
            ),
        ):
            return {"success": False, "status": "failed", "message": error}
        if check_owned:
            error = (
                validate_owned_operators(self.global_plan)
                if refresh_roster
                else validate_owned_operators(self.global_plan, refresh=False)
            )
            if error:
                return {"success": False, "status": "failed", "message": error}

        baseline = Operators(self.global_plan, runtime_conf=self.runtime_conf)
        validated = {baseline._schedule_validation_key()}
        if error := baseline.init_and_validate():
            return {
                "success": False,
                "status": "failed",
                "message": f"基础验证失败：{error}",
            }
        backup_count = len(self.backup_plans)
        deadline = None if max_seconds is None else monotonic() + max_seconds
        tested_count = 1
        # 仅按条件证明互斥；主力不重叠不能证明合并配置互不影响。
        try:
            combinations = possible_backup_conditions(
                self.backup_plans,
                MAX_BACKUP_VALIDATION_COMBINATIONS,
                known_operators=baseline.operators,
                deadline=deadline,
                groups=self.backup_groups,
            )
            for flags in combinations:
                check_validation_deadline(deadline)
                condition = list(flags)
                # 每个组合从独立模型开始，失败及检查顺序都不影响实际排班和驻员。
                simulation = copy.copy(baseline)
                simulation.operators, simulation.dorm = {}, []
                error = simulation.swap_plan(condition)
                if error is None:
                    key = simulation._schedule_validation_key()
                    if key in validated:
                        check_validation_deadline(deadline)
                        continue
                    error = simulation.init_and_validate(True)
                    simulation.first_init = False
                    tested_count += 1
                    if error is None:
                        validated.add(key)
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
                check_validation_deadline(deadline)
        except BackupValidationLimitExceeded as error:
            return {
                "success": False,
                "status": "incomplete",
                "reason": str(error),
                "message": f"{error}，已验证 {tested_count} 次。主表已通过检查，允许启动；实际生效的副表组合由运行时检查。",
            }
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
    def __deepcopy__(self, memo):
        """直接复用标量，隔离可变字段和扩展字段，并保留副本内部引用关系。"""
        cloned = type(self).__new__(type(self))
        memo[id(self)] = cloned
        if id(self.__dict__) in memo:
            cloned.__dict__ = memo[id(self.__dict__)]
            return cloned
        state = {}
        memo[id(self.__dict__)] = state
        cloned.__dict__ = state
        for key, value in self.__dict__.items():
            state[key] = (
                value
                if type(value) in _OPERATOR_SCALAR_TYPES
                else copy.deepcopy(value, memo)
            )
        return cloned

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
        group_bindings=None,
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
        self.group_bindings = copy.deepcopy(group_bindings or [])
        if self.independent_rest:
            self.group = ""
            self.replacement = list(self.replacements_for_group(""))
        self.resting_priority = resting_priority
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
        self.individual_return_window = None
        self._current_room = None
        self.current_room = current_room
        self.exhaust_require = exhaust_require
        self.upper_limit = upper_limit
        self.rest_in_full = rest_in_full
        self.mood = mood
        self.current_index = current_index
        self.lower_limit = lower_limit
        self.depletion_rate = depletion_rate
        self.work_rate_sample_eligible = True
        self.time_stamp = time_stamp
        self.mood_is_prediction = False
        self.workaholic = False
        self.arrange_order = ["技能", "false"]
        self.exhaust_time = None

    @property
    def multi_group(self):
        return len(getattr(self, "group_bindings", ())) > 1

    @property
    def independent_rest(self):
        """工作主班的空绑组提供个人轮休，具名绑组的岗位替班优先。"""
        return (
            self.multi_group
            and not self.room.startswith("dorm")
            and any(binding["group"] == "" for binding in self.group_bindings)
        )

    def replacements_for_group(self, group):
        if self.multi_group:
            return next(
                binding["replacement"]
                for binding in self.group_bindings
                if binding["group"] == group
            )
        return self.replacement

    @property
    def current_room(self):
        return self._current_room

    @current_room.setter
    def current_room(self, value):
        if self._current_room != value:
            self.exhaust_time = None
            model = getattr(self, "_mood_model", None)
            if (
                model is not None
                and model.enabled
                and getattr(
                    getattr(self, "_mood_conf", None), "test_mood_calculation", False
                )
            ):
                model.move(self.name, value or "", self.current_index)
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
            self.exhaust_time = None
            model = getattr(self, "_mood_model", None)
            if (
                model is not None
                and model.enabled
                and getattr(
                    getattr(self, "_mood_conf", None), "test_mood_calculation", False
                )
            ):
                model.move(self.name, self.current_room or "", value)
            self.dorm_position_version = getattr(self, "dorm_position_version", 0) + 1
            self.clear_dorm_recovery()
        self.__dict__["current_index"] = value

    def clear_dorm_recovery(self):
        self.dorm_recovery_room = ""
        self.dorm_recovery_index = -1
        self.dorm_recovery_fixed = ()
        self.dorm_recovery_observation = None

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
        model = getattr(self, "_mood_model", None)
        if (
            model is not None
            and model.enabled
            and getattr(
                getattr(self, "_mood_conf", None), "test_mood_calculation", False
            )
        ):
            if self.operator_type != "high":
                return False
            if (
                not self.workaholic
                and not self.room.startswith("dorm")
                and self.is_resting()
            ):
                return (
                    self.current_mood() < 0 or self.current_mood() >= self.upper_limit
                )
            return self.current_room != self.room or self.index != self.current_index
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
        time = time or getattr(self, "_projection_now", None)
        model = getattr(self, "_mood_model", None)
        if (
            model is not None
            and model.enabled
            and getattr(
                getattr(self, "_mood_conf", None), "test_mood_calculation", False
            )
            and self.current_room != "train"
        ):
            value = model.value(self.name, time)
            return value if value is not None else -1
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

    def working_zero_deadline(self, now=None):
        """零读数优先使用同岗位实读工作期限，不把显示精度当作耗尽。"""
        now = now or getattr(self, "_projection_now", None) or datetime.now()
        if (
            self.mood == 0
            and self.is_working()
            and self.exhaust_time is not None
            and self.time_stamp is not None
            and self.time_stamp <= now
            and not self.mood_is_prediction
        ):
            return max(now, self.exhaust_time)
        return None

    def exhaust_time_at_lower_limit(self, zero_time, now=None):
        """按本次读到的心情，把游戏的归零倒计时换算到设置下限。"""
        now = now or datetime.now()
        if self.mood > 0 and self.lower_limit > 0:
            zero_time = now + (zero_time - now) * (
                (self.mood - self.lower_limit) / self.mood
            )
        return max(now, zero_time)

    def predict_exhaust(self, now=None):
        if self.workaholic or self.exhaust_require or self.room in ["factory", "train"]:
            return datetime.now() + timedelta(hours=24)
        now = now or getattr(self, "_projection_now", None) or datetime.now()
        observed = self.working_zero_deadline(now) if self.lower_limit == 0 else None
        if observed is not None:
            return max(now, observed - timedelta(minutes=30))
        model = getattr(self, "_mood_model", None)
        if (
            model is not None
            and model.enabled
            and getattr(
                getattr(self, "_mood_conf", None), "test_mood_calculation", False
            )
            and self.room not in ("factory", "train")
        ):
            now = now or getattr(self, "_projection_now", None) or datetime.now()
            cached = getattr(self, "_projection_deadlines", None)
            key = (self.name, self.lower_limit, 240, now)
            if cached is not None and key in cached:
                deadline = cached[key]
            else:
                deadline = model.deadline(self.name, self.lower_limit, now)
                if cached is not None:
                    cached[key] = deadline
            return (
                max(now, deadline - timedelta(minutes=30))
                if deadline
                else now + timedelta(hours=24)
            )
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
