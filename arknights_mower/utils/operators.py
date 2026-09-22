import ast
import copy
from datetime import datetime, timedelta
from itertools import product

from evalidate import Expr, base_eval_model

from arknights_mower.utils import config
from arknights_mower.utils.manufacture_product import (
    MANUFACTURE_PRODUCTS,
    TRADE_PRODUCTS,
)
from arknights_mower.utils.plan import BaseProduct, Plan, PlanConfig
from arknights_mower.utils.resting_priority import (
    RestingTier,
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


def build_global_plan():
    """构建完整的 global_plan，包括 Plan 对象，用于运行时"""
    from ..utils import config
    from ..utils.logic_expression import get_logic_exp
    from ..utils.plan import Plan, PlanConfig, Room

    plan1 = {}
    default_products = {}
    plan = config.plan.model_dump(exclude_none=True)
    conf = config.conf
    plan_config = PlanConfig(
        rest_in_full=config.plan.conf.rest_in_full,
        exhaust_require=config.plan.conf.exhaust_require,
        resting_priority=config.plan.conf.resting_priority,
        resting_standby=config.plan.conf.resting_standby,
        ling_xi=config.plan.conf.ling_xi,
        workaholic=config.plan.conf.workaholic,
        free_blacklist=conf.free_blacklist,
        ope_resting_priority=config.plan.conf.ope_resting_priority,
        dorm_order=config.plan.conf.dorm_order,
        experimental_dorm_logic=conf.experimental_dorm_logic,
        resting_threshold=conf.resting_threshold,
        refresh_trading_config=config.plan.conf.refresh_trading,
        refresh_drained=config.plan.conf.refresh_drained,
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
            workaholic=i["conf"]["workaholic"],
            free_blacklist=i["conf"]["free_blacklist"],
            ope_resting_priority=i["conf"]["ope_resting_priority"],
            dorm_order=i["conf"].get("dorm_order", ""),
            dorm_order_override=i["conf"].get("dorm_order_override", False),
            experimental_dorm_logic=conf.experimental_dorm_logic,
            resting_standby=i["conf"].get("resting_standby", ""),
            resting_threshold=conf.resting_threshold,
            refresh_trading_config=i["conf"]["refresh_trading"],
            refresh_drained=i["conf"]["refresh_drained"],
            free_room=conf.free_room,
        )
        backup_trigger = get_logic_exp(i["trigger"]) if "trigger" in i else None
        backup_task = i.get("task")
        backup_trigger_timing = i.get("trigger_timing")
        backup_exit_trigger_timing = i.get("exit_trigger_timing")
        backup_plans.append(
            Plan(
                backup_plan,
                backup_config,
                trigger=backup_trigger,
                task=backup_task,
                trigger_timing=backup_trigger_timing,
                exit_trigger_timing=backup_exit_trigger_timing,
                name=i.get("name"),
                products=backup_products,
            )
        )
    plan["backup_plans"] = backup_plans

    return plan


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
    def experimental_dorm_logic(self):
        return bool(getattr(self.config, "experimental_dorm_logic", False))

    def swap_plan(self, condition, refresh=False):
        self.plan = copy.deepcopy(self.global_plan["default_plan"].plan)
        self.products = copy.deepcopy(self.global_plan["default_plan"].products)
        self.config: PlanConfig = copy.deepcopy(self.global_plan["default_plan"].config)
        for index, success in enumerate(condition):
            if success:
                self.plan, self.config = self.merge_plan(index, self.config, self.plan)
                self.products.update(self.global_plan["backup_plans"][index].products)
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
        experimental = self.experimental_dorm_logic
        saved_dorms = copy.deepcopy(self.all_dorms()) if update and experimental else []
        self.displaced_dorms = []
        self.groups = {}
        self.exhaust_agent = set()
        self.exhaust_group = set()
        self.rest_in_full_group = set()
        self.workaholic_agent = set()
        self.shadow_copy = copy.deepcopy(self.operators)
        self.operators = {}
        if not update or experimental:
            self.dorm = []
        self.group_dorm = []
        for room in self.plan.keys():
            for idx, data in enumerate(self.plan[room]):
                if data.agent not in agent_list and data.agent != "Free":
                    return f"干员名输入错误: 房间->{room}, 干员->{data.agent}"
                if data.agent in TRADE_ORDER_AGENTS:
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
                        experimental
                        and room.startswith("dorm")
                        and bool(data.group)
                        and data.agent not in ("Free", "菲亚梅塔")
                        and _replacement == "Free"
                    )
                    if _replacement == "Free" and not explicit_free:
                        return f"Free替换只能用于测试宿舍逻辑下的绑组宿舍干员: 房间->{room}"
                    if explicit_free:
                        continue
                    if _replacement not in agent_list and data.agent != "Free":
                        return f"干员名输入错误: 房间->{room}, 干员->{_replacement}"
                    if data.agent != "菲亚梅塔":
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
        # 测试逻辑的床位集合由当前合并后的排班生成；因此副表
        # 可以增减 Free 位置。宿舍常驻成员的替换显式填写 Free 时，该
        # 固定位在常驻成员随组离岗期间也作为动态 Free 床位。
        bed_plan = self.plan
        dorm_names = [k for k in bed_plan.keys() if k.startswith("dorm")]
        dorm_names.sort(key=lambda d: d, reverse=False)
        added = []
        # 竖向遍历出效率高到低
        for dorm in dorm_names if (not update or experimental) else []:
            free_found = False
            for _idx, _dorm in enumerate(bed_plan[dorm]):
                if _dorm.agent == "Free" and _idx <= 1:
                    if "波登可" not in [_agent.agent for _agent in bed_plan[dorm]]:
                        return "宿舍必须安排2个宿管"
                if _dorm.agent != "Free" and free_found:
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
        for dorm in dorm_names if (not update or experimental) else []:
            for _idx, _dorm in enumerate(bed_plan[dorm]):
                if _dorm.agent == "Free" and (dorm + str(_idx)) not in added:
                    self.dorm.append(Dormitory((dorm, _idx)))
                    added.append(dorm + str(_idx))
        if experimental:
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
        # 测试逻辑只保存四间宿舍的相对顺序；同一房间内按床位
        # 索引稳定排列，单回目标由入驻顺序确认逻辑重置。
        if experimental:
            room_order = dorm_room_order(self.config.dorm_order)
            self.config.dorm_order = room_order
            self.dorm.sort(
                key=lambda dorm: (
                    room_order.index(dorm.position[0]),
                    dorm.position[1],
                )
            )
        if not experimental and not update:
            dorm_order = [name for name in config.conf.dorm_order.split(",") if name]
            current_dorm_names = {
                dorm.position[0] + "_" + str(dorm.position[1]) for dorm in self.dorm
            }
            if dorm_order:
                if set(dorm_order) == current_dorm_names:
                    self.dorm.sort(
                        key=lambda dorm: dorm_order.index(
                            dorm.position[0] + "_" + str(dorm.position[1])
                        )
                    )
                else:
                    return (
                        "宿舍优先级和当前宿舍不匹配，请清除优先级自动排序或者自己更正"
                    )
        self.refresh_run_order_rooms()
        for key in self.groups:
            total_count = 0
            _replacement = []
            for name in self.groups[key]:
                operator = self.operators[name]
                if experimental and self.is_auto_free_dorm_operator(operator):
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
                if self.is_effective_free_slot(
                    dorm, active_groups={key} if experimental else None
                )
            )
            if required_beds > effective_dorm_count:
                if not experimental:
                    return f"{key} 分组无法排班,分组总数(不包含0心情工作){total_count}大于当前有效宿舍数{effective_dorm_count}"
                return f"{key} 分组无法排班,所需宿舍数{required_beds}大于当前有效宿舍数{effective_dorm_count}"
        if experimental:
            self.group_dorm = []
        if update and experimental:
            self.displaced_dorms = self.restore_dorm_state(saved_dorms)
        # 设定令夕模式的心情阈值
        self.init_mood_limit()
        for name in self.workaholic_agent:
            if name not in self.config.free_blacklist:
                self.config.free_blacklist.append(name)
        self.power_plant_count = sum(
            1
            for room in self.plan.values()
            if room and room[0].product == BaseProduct.Electricity
        )

    def set_mood_limit(self, name, upper_limit=24, lower_limit=0):
        if name in self.operators:
            self.operators[name].upper_limit = upper_limit
            self.operators[name].lower_limit = lower_limit

    def init_mood_limit(self):
        # 设置心情阈值 for 夕，令，
        if self.config.ling_xi == 1:
            self.set_mood_limit("令", upper_limit=12)
            self.set_mood_limit("夕", lower_limit=12)
        elif self.config.ling_xi == 2:
            self.set_mood_limit("夕", upper_limit=12)
            self.set_mood_limit("令", lower_limit=12)
        elif self.config.ling_xi == 0:
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
                for group_name in self.groups[self.operators[name].group]:
                    if group_name not in ["夕", "令"] and not self.operators[
                        group_name
                    ].room.startswith("dorm"):
                        if self.config.ling_xi in [1, 2]:
                            self.set_mood_limit(group_name, lower_limit=12)
                        elif self.config.ling_xi == 0:
                            self.set_mood_limit(group_name, lower_limit=0)
                finished.append(self.operators[name].group)

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
        """返回距离下一次停服大版本维护的小时数。"""
        info = NewsChecker.get_maintenance()
        if info is None or info.update_type != "major" or info.is_flash_update:
            return float("inf")
        return max(0.0, (info.start - datetime.now()).total_seconds() / 3600)

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
        """按生效排班和实际订单过滤跑单；卖玉及切换中的卖玉房间不插拔。"""
        return (
            room.startswith("room")
            and self.products.get(room) != "orundum"
            and self.facility_states.get(room, {}).get("product") != "orundum"
            and any(
                name in slot.replacement
                for slot in self.plan.get(room, [])
                for name in TRADE_ORDER_AGENTS
            )
        )

    def refresh_run_order_rooms(self):
        if self.experimental_dorm_logic:
            self.run_order_rooms = {
                room: self.run_order_rooms.get(room, {})
                for room in self.plan
                if self.is_run_order_room(room)
            }
            return
        for room, slots in self.plan.items():
            if room.startswith("room") and any(
                name in slot.replacement
                for slot in slots
                for name in TRADE_ORDER_AGENTS
            ):
                self.run_order_rooms[room] = {}

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
    ):
        """更新对象的详细信息，并记录到SQLite数据库
        参数:
        name(str): 对象的名称。
        mood(str): 当前的心情状态。
        current_room(str): 当前所在的房间名称(新)。
        current_index(int): 当前索引（新）。
        update_time(bool, 可选): 是否更新时间戳，默认为
        False 是否刷新时间

        返回: index 如果需要读取时间 None"""
        agent = self.operators[name]
        logger.debug(f"{name},{mood},{current_room},{current_index},{update_time}")
        if update_time:
            if agent.time_stamp is not None and agent.mood > mood:
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
        self.update_standby_low_priority(agent)
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
            time_elapsed = (agent["time"] - datetime.now()).total_seconds()
            _agent.exhaust_time = agent["time"]
            if _agent.mood > 0 and _agent.lower_limit > 0:
                _agent.exhaust_time = datetime.now() + timedelta(
                    seconds=(_agent.mood - _agent.lower_limit)
                    * time_elapsed
                    / _agent.mood
                )
            if time_elapsed < 0 or _agent.exhaust_time < datetime.now():
                _agent.exhaust_time = datetime.now()
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
                        op.mood = op.upper_limit
                        op.time_stamp = dorm.time
                        op.depletion_rate = 0
                        logger.debug(
                            f"检测到{op.name}心情恢复满，设置心情至{op.upper_limit}"
                        )

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
                    if _name not in self.operators.keys():
                        self.add(Operator(_name, ""))
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
            operator.depletion_rate = exist.depletion_rate
            operator.current_room = exist.current_room
            operator.current_index = exist.current_index
            operator.dorm_recovery_room = getattr(exist, "dorm_recovery_room", "")
            operator.resting_from_train = getattr(exist, "resting_from_train", False)
            operator.dorm_recovery_fixed = getattr(exist, "dorm_recovery_fixed", ())
            operator.standby_low_priority = getattr(
                exist, "standby_low_priority", False
            )
        self.operators[operator.name] = operator
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
            and (operator.group or self.experimental_dorm_logic)
            and not operator.room.startswith("dorm")
            and not operator.workaholic
            and not operator.exhaust_require
            and not operator.rest_in_full
            and (self.experimental_dorm_logic or not operator.is_workshop())
        ):
            operator.resting_priority = "standby"
        if operator.resting_priority != "standby":
            operator.standby_low_priority = False

    def _can_standby(self, op):
        """仅显式配置且没有强制恢复要求的主班可待命。"""
        return (
            op.is_high()
            and (op.group or self.experimental_dorm_logic)
            and op.resting_priority == "standby"
            and not getattr(op, "standby_low_priority", False)
            and not op.room.startswith("dorm")
            and not op.workaholic
            and not op.exhaust_require
            and not op.rest_in_full
            and (self.experimental_dorm_logic or not op.is_workshop())
        )

    def update_standby_low_priority(self, op, now=None):
        """候补低于急救线后升为低优，直到实际回班。

        急救线与现有急救模式共用同一计算：排班心情阈值乘全局
        急救阈值，并按干员自身心情上下限换算为绝对心情。
        """
        if not self.experimental_dorm_logic or not self.config.is_resting_standby(
            op.name
        ):
            op.standby_low_priority = False
            return
        if op.current_room == op.room and op.current_index == op.index:
            op.standby_low_priority = False
        mood = resting_mood(op, now)
        threshold = op.lower_limit + (op.upper_limit - op.lower_limit) * (
            self.config.resting_threshold * config.conf.rescue_threshold
        )
        if mood < threshold:
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
            member.is_high()
            and member.resting_priority == "high"
            and not member.room.startswith("dorm")
            and not member.workaholic
            and (self.experimental_dorm_logic or not member.is_workshop())
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
            not self.experimental_dorm_logic
            or not operator.group
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
        if not self.experimental_dorm_logic:
            return 0
        return sum(
            self.is_auto_free_dorm_operator(self.operators[name]) for name in names
        )

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

    def replacement_candidates(self, operator):
        """仅绑组宿舍的替班按心情排序；菲亚梅塔充能名单保留原顺序。"""
        candidates = [name for name in operator.replacement if name != "Free"]
        if not self.experimental_dorm_logic:
            if (
                not operator.room.startswith("dorm")
                or not operator.group
                or operator.name == "菲亚梅塔"
            ):
                return candidates
            now = datetime.now()

            def legacy_mood_order(name):
                candidate = self.operators.get(name)
                if (
                    candidate is None
                    or candidate.time_stamp is None
                    or not 0 <= candidate.mood <= 24
                ):
                    return (1, 0)
                return (0, candidate.current_mood(now))

            return sorted(candidates, key=legacy_mood_order)
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
        free_name = []
        # 一次性遍历 dorm。低优占位也必须消耗 low 配额，否则调度器会持续把
        # 已占用床位误判为空位；恢复完成的普通填充干员由不养闲人处理。
        for dorm in effective_dorms:
            if dorm.name == "" or dorm.name not in self.operators:
                continue
            op = self.operators[dorm.name]
            if not self.experimental_dorm_logic:
                if op.is_workshop():
                    continue
                if dorm.time is not None and dorm.time < time:
                    if op.is_high():
                        free_name.append(dorm.name)
                    continue
                if op.resting_priority == "high":
                    count_high += 1
                else:
                    count_low += 1
                continue
            if resting_tier(self, op.name) <= RestingTier.MAIN:
                count_high += 1
            else:
                count_low += 1
        available_high = max(0, dorm_count - count_high)
        available_low = total - count_low - max(count_high, dorm_count)
        if not self.experimental_dorm_logic:
            for name in free_name:
                logger.debug(f"检测到房间休息完毕，释放{name}宿舍位")
                if name in agent_list:
                    self.operators[name].mood = self.operators[name].upper_limit
                    self.operators[name].depletion_rate = 0
                    self.operators[name].time_stamp = time
        return available_high if free_type == "high" else available_low

    def active_high_resting_count(self, time=None):
        """正在占用恢复床位的主班人数。"""
        if time is None:
            time = datetime.now()
        if not self.experimental_dorm_logic:
            return sum(
                1
                for dorm in self.dorm
                if self.is_effective_free_slot(dorm)
                and dorm.name in self.operators
                and self.operators[dorm.name].is_high()
                and not self.operators[dorm.name].is_workshop()
                and not (dorm.time is not None and dorm.time < time)
            )
        return sum(
            1
            for dorm in self.dorm
            if self.is_effective_free_slot(dorm)
            and dorm.name in self.operators
            and self.operators[dorm.name].is_high()
            and resting_tier(self, dorm.name) != RestingTier.IDLE
        )

    def _slot_takable(self, dorm, protect_resting, requester=None, active_groups=None):
        """按严格层级接管；主班免额外心情门槛，同级恢复者不互踢。"""
        if not self.is_effective_free_slot(dorm, active_groups=active_groups):
            return False
        name = dorm.name
        if name == "" or name not in self.operators:
            return True
        op = self.operators[name]
        if not self.experimental_dorm_logic:
            if dorm.time is not None and dorm.time < datetime.now():
                return True
            if op.is_workshop() and requester is not None:
                incoming = self.operators[requester]
                return not incoming.is_workshop() and (
                    incoming.is_high() or incoming.current_mood() <= 22
                )
            if not op.is_high():
                return not (protect_resting and op.is_resting())
            return False
        # 已预留、尚未执行入驻的床位不能被本轮后续组重复分配。
        if (op.current_room, op.current_index) != dorm.position:
            return False
        tier = resting_tier(self, name)
        # 候补及以上只按层级、心情换床位顺序；一旦入住便不被其他休息者踢出。
        if tier <= RestingTier.STANDBY:
            return False
        if requester is None:
            return False
        incoming_tier = resting_tier(self, requester)
        if incoming_tier >= tier:
            return False
        if incoming_tier <= RestingTier.LOW_MAIN:
            return True
        if tier == RestingTier.IDLE:
            return resting_mood(self.operators[requester]) <= 22
        return (
            incoming_tier == RestingTier.STANDBY
            and tier == RestingTier.REPLACEMENT
            and not protect_resting
        )

    def _find_dorm_slot(self, name, used, *, group_resting=False, active_groups=None):
        operator = self.operators[name]
        if not self.experimental_dorm_logic:
            is_high = operator.resting_priority == "high" and not operator.is_workshop()
            can_take_over = is_high or (group_resting and self._can_standby(operator))
            max_count = sum(1 for key in self.plan if key.startswith("dorm"))
            if not is_high:
                for i in range(max_count, len(self.dorm)):
                    if i not in used and self._slot_takable(
                        self.dorm[i],
                        protect_resting=not can_take_over,
                        requester=name,
                    ):
                        return i
            return next(
                (
                    i
                    for i, dorm in enumerate(self.dorm)
                    if i not in used
                    and self._slot_takable(
                        dorm, protect_resting=not can_take_over, requester=name
                    )
                ),
                None,
            )
        if resting_tier(self, name) == RestingTier.EXCLUDED:
            return None
        is_high = resting_tier(self, name) <= RestingTier.MAIN
        # 候补接管普通替班只用于随组分床；主班跨级接管由共享判定处理。
        can_take_over = is_high or (group_resting and self._can_standby(operator))
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
                protect_resting=not can_take_over,
                requester=name,
                active_groups=active_groups,
            )
        ]
        now = datetime.now()

        def takeover_cost(index):
            bed = self.dorm[index]
            if not bed.name:
                return (0, 0, 0)
            tier, mood = resting_key(self, bed.name, now)
            # 先使用空位，再接管层级最低、同级心情最高的占位者。
            return (1, -tier, -mood)

        return min(candidates, key=takeover_cost, default=None)

    def has_resting_anchor(self, group=None):
        """是否已有能为候补提供回班时机的高优恢复者。"""
        return any(
            bed.name in self.operators
            and self.is_effective_free_slot(bed)
            and (op := self.operators[bed.name]).is_high()
            and op.resting_priority == "high"
            and (group is None or op.group == group)
            for bed in self.dorm
        )

    def standby_candidates(self, names):
        """返回本轮有床则休息、无床可待命的显式候补。"""
        # 高优确实需要恢复心情时才允许同组候补待命，避免满心情高优在选人
        # 阶段被释放后，整组既没有恢复心情者，也没有回班计时来源。
        anchor_groups = {
            op.group
            for op in (self.operators[n] for n in names)
            if op.group
            and op.is_high()
            and op.resting_priority == "high"
            and not op.workaholic
            and (self.experimental_dorm_logic or not op.is_workshop())
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
        used = set()
        assignments = []
        optional = self.standby_candidates(names)
        # 可待命者最后分床；其余成员沿用低优先选床顺序。
        if self.experimental_dorm_logic:
            ordered_names = sorted(
                names,
                key=lambda name: (
                    name in optional,
                    resting_key(self, name),
                ),
            )
        else:
            ordered_names = sorted(
                names,
                key=lambda name: (
                    self.operators[name].resting_priority == "standby",
                    self.operators[name].resting_priority == "high",
                ),
            )
        for name in ordered_names:
            index = self._find_dorm_slot(
                name,
                used,
                group_resting=True,
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
        backup_count = len(self.backup_plans)
        if backup_count == 0:
            return {"success": True, "message": "没有备用计划，无需验证"}

        def collect_agents(plan: Plan) -> set[str]:
            agents = set()
            for room_info in plan.plan.values():
                for op in room_info:
                    if op.agent not in ("Current", "Free"):
                        agents.add(op.agent)
            return agents

        agent_sets = [collect_agents(plan) for plan in self.backup_plans]
        adjacency = [set() for _ in range(backup_count)]
        for i in range(backup_count):
            for j in range(i + 1, backup_count):
                if agent_sets[i].intersection(agent_sets[j]):
                    adjacency[i].add(j)
                    adjacency[j].add(i)

        components: list[list[int]] = []
        visited = [False] * backup_count
        for i in range(backup_count):
            if visited[i]:
                continue
            stack = [i]
            component = []
            while stack:
                node = stack.pop()
                if visited[node]:
                    continue
                visited[node] = True
                component.append(node)
                stack.extend(adjacency[node])
            components.append(component)

        tested_conditions: set[tuple[bool, ...]] = set()
        tested_sequence: list[tuple[bool, ...]] = []

        def validate_condition(condition: list[bool]) -> tuple[bool, str]:
            key = tuple(condition)
            if key in tested_conditions:
                return True, ""
            tested_conditions.add(key)
            tested_sequence.append(key)
            logger.debug(f"验证副表条件：{condition}")
            validation_msg = self.swap_plan(condition, True)
            if validation_msg is not None:
                logger.info(
                    f"替换排班验证错误：{validation_msg}, 附表条件为 {condition}"
                )
                return False, validation_msg
            return True, ""

        success, msg = validate_condition([False] * backup_count)
        if not success:
            return {"success": False, "message": f"基础验证失败：{msg}"}

        for component in components:
            size = len(component)
            for combo in product([False, True], repeat=size):
                if not any(combo):
                    continue
                condition = [False] * backup_count
                for idx, flag in enumerate(combo):
                    condition[component[idx]] = flag
                success, msg = validate_condition(condition)
                if not success:
                    return {"success": False, "message": f"组件验证失败：{msg}"}

        self.swap_plan([False] * backup_count, True)
        return {
            "success": True,
            "message": f"验证成功，共验证 {len(tested_sequence)} 次",
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
    def is_workshop(self):
        """稳定版中可选的加工干员最低宿舍恢复优先级。"""
        conf = config.conf
        if not conf.workshop_low_priority_rest:
            return False
        names = (
            *getattr(conf, "fodder_operators", ()),
            *getattr(conf, "t5_operators", ()),
            *getattr(conf, "book_operators", ()),
        )
        return self.name in names or any(
            setting.operator == self.name
            for setting in (
                *getattr(conf, "workshop_settings", ()),
                *(getattr(conf, "workshop_manual_backup", None) or ()),
            )
        )

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
        # 测试宿舍逻辑：候补跌破急救线后，本轮休息周期锁定为低优。
        self.standby_low_priority = False
        self.dorm_recovery_room = ""
        self.resting_from_train = False
        self.dorm_recovery_fixed = ()
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
        self.workaholic = False
        self.arrange_order = ["技能", "false"]
        self.exhaust_time = None

    @property
    def current_room(self):
        return self._current_room

    @current_room.setter
    def current_room(self, value):
        if self._current_room != value:
            self.clear_dorm_recovery()
            self._current_room = value
            if Operators.current_room_changed_callback and (
                self.refresh_order_room[0] or self.refresh_drained
            ):
                Operators.current_room_changed_callback(self)
                logger.debug(
                    f"触发当前房间变更回调: {self.name} 现在在 {self._current_room}, 刷新交易所房间: {self.refresh_order_room}, 刷新疲劳: {self.refresh_drained}"
                )

    def clear_dorm_recovery(self):
        self.dorm_recovery_room = ""
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


def validate_backup_plans_offline():
    """独立的验证函数，不依赖于 BaseSchedulerSolver"""
    global_plan = build_global_plan()
    backup_plans = global_plan["backup_plans"]

    backup_count = len(backup_plans)
    if backup_count == 0:
        return {"success": True, "message": "没有备用计划，无需验证"}

    def collect_agents(plan: Plan) -> set[str]:
        agents = set()
        for room_info in plan.plan.values():
            for op in room_info:
                if op.agent not in ("Current", "Free"):
                    agents.add(op.agent)
        return agents

    agent_sets = [collect_agents(plan) for plan in backup_plans]
    adjacency = [set() for _ in range(backup_count)]
    for i in range(backup_count):
        for j in range(i + 1, backup_count):
            if agent_sets[i].intersection(agent_sets[j]):
                adjacency[i].add(j)
                adjacency[j].add(i)

    components: list[list[int]] = []
    visited = [False] * backup_count
    for i in range(backup_count):
        if visited[i]:
            continue
        stack = [i]
        component = []
        while stack:
            node = stack.pop()
            if visited[node]:
                continue
            visited[node] = True
            component.append(node)
            stack.extend(adjacency[node])
        components.append(component)

    tested_conditions: set[tuple[bool, ...]] = set()
    tested_sequence: list[tuple[bool, ...]] = []

    # 复制类方法中的验证逻辑
    for component in components:
        if len(component) == 1:
            continue
        # 检查连通分量中的计划是否有冲突
        for mask in product([False, True], repeat=len(component)):
            if mask in tested_conditions:
                continue
            tested_conditions.add(mask)
            tested_sequence.append(mask)
            active_plans = [
                backup_plans[i] for i, active in zip(component, mask) if active
            ]
            if not active_plans:
                continue
            combined_agents = set()
            for plan in active_plans:
                combined_agents.update(collect_agents(plan))
            if len(combined_agents) < sum(
                len(collect_agents(plan)) for plan in active_plans
            ):
                return {
                    "success": False,
                    "message": f"备用计划 {', '.join(str(i + 1) for i in component)} 中存在干员重复安排",
                }

    return {"success": True, "message": "备用计划验证通过"}
