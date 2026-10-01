"""从共享条件状态生成副表开关组合；未知条件保留独立的真假可能。"""

import ast
from itertools import product

from arknights_mower.data import base_room_list
from arknights_mower.utils.manufacture_product import (
    MANUFACTURE_PRODUCTS,
    TRADE_PRODUCTS,
)

MAX_CONDITION_STATES = 262144
BOOLEAN_METHODS = {"is_working", "is_resting"}
STRING_CONSTANTS = (
    set(base_room_list) | MANUFACTURE_PRODUCTS.keys() | TRADE_PRODUCTS.keys()
)


class BackupValidationLimitExceeded(ValueError):
    """条件分析或组合检查超出预算；不表示已确认排班错误。"""


def _string_literal(node):
    if isinstance(node, ast.Constant) and type(node.value) is str:
        return node.value
    if isinstance(node, ast.Name) and node.id in STRING_CONSTANTS:
        return node.id
    return None


def _operator_owner(owner, known_operators):
    return (
        isinstance(owner, ast.Subscript)
        and isinstance(owner.value, ast.Attribute)
        and owner.value.attr == "operators"
        and isinstance(owner.value.value, ast.Name)
        and owner.value.value.id == "op_data"
        and isinstance(owner.slice, ast.Constant)
        and isinstance(owner.slice.value, str)
        and (known_operators is None or owner.slice.value in known_operators)
    )


def _state_method(node, known_operators):
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and not node.args
        and not node.keywords
        and _operator_owner(node.func.value, known_operators)
    ):
        return node.func.attr
    return None


def _returns_boolean(node, known_operators):
    if isinstance(node, ast.Constant):
        return type(node.value) is bool
    if isinstance(node, ast.Compare):
        return True
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return True
    if isinstance(node, ast.BoolOp):
        return all(_returns_boolean(child, known_operators) for child in node.values)
    return _state_method(node, known_operators) in BOOLEAN_METHODS


def possible_backup_conditions(backups, combination_limit, *, known_operators=None):
    """仅删除条件逻辑能证明不成立的组合，不读取驻员或执行导入表达式。"""
    domains = {}

    def unknown(key):
        key = ("boolean", key)
        condition_domains.setdefault(key, None)
        return lambda state: state[key]

    def formula(node):
        if isinstance(node, ast.BoolOp):
            children = [formula(child) for child in node.values]
            combine = all if isinstance(node.op, ast.And) else any
            return lambda state: combine(child(state) for child in children)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            child = formula(node.operand)
            return lambda state: not child(state)
        if isinstance(node, ast.Constant) and (
            type(node.value) is bool or node.value is None
        ):
            return lambda state: bool(node.value)
        if isinstance(node, ast.Tuple) and not node.elts:
            return lambda state: False
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            left, right, comparison = node.left, node.comparators[0], type(node.ops[0])
            # 支持将常量写在等式左侧。
            if (
                isinstance(left, ast.Constant) or _string_literal(left) is not None
            ) and not isinstance(right, ast.Constant):
                left, right = right, left
            try:
                value = ast.literal_eval(right)
            except (ValueError, TypeError):
                value = _string_literal(right)
                if value is None:
                    value = ...
            if (
                type(value) is bool
                and comparison in (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)
                and _returns_boolean(left, known_operators)
            ):
                child = formula(left)
                expected = value if comparison in (ast.Eq, ast.Is) else not value
                return lambda state: bool(child(state)) == expected
            if (
                value is None
                and comparison in (ast.Eq, ast.NotEq, ast.Is, ast.IsNot)
                and isinstance(left, ast.Attribute)
                and left.attr == "party_time"
                and isinstance(left.value, ast.Name)
                and left.value.id == "op_data"
            ):
                child = unknown(("null", ast.dump(left)))
                expected = comparison in (ast.Eq, ast.Is)
                return lambda state: child(state) == expected
            if type(value) is str and comparison in (ast.Eq, ast.NotEq):
                key = None
                if (
                    isinstance(left, ast.Attribute)
                    and left.attr == "current_room"
                    and _operator_owner(left.value, known_operators)
                ):
                    key = ("room", ast.dump(left))
                elif (
                    isinstance(left, ast.Call)
                    and isinstance(left.func, ast.Attribute)
                    and isinstance(left.func.value, ast.Name)
                    and left.func.value.id == "op_data"
                    and left.func.attr == "facility_product"
                    and len(left.args) == 1
                    and not left.keywords
                    and _string_literal(left.args[0]) in base_room_list
                ):
                    key = ("product", _string_literal(left.args[0]))
                if key is not None:
                    condition_domains.setdefault(key, set()).add(value)
                    expected = comparison is ast.Eq
                    return lambda state: (state[key] == value) == expected
        if _state_method(node, known_operators) in BOOLEAN_METHODS:
            return unknown(ast.dump(node))
        # 未知调用可能抛异常，异常使整条条件为假，不能按普通布尔取反推断。
        raise ValueError("unsupported condition")

    conditions = []
    for index, backup in enumerate(backups):
        condition_domains = {}
        try:
            source = str(backup.trigger)
            if backup.trigger is None or len(source) > 2048:
                raise ValueError("unknown condition")
            tree = ast.parse(source, mode="eval")
            nodes = list(ast.walk(tree))
            if len(nodes) > 128 or any(
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and len(node.value) > 512
                for node in nodes
            ):
                raise ValueError("complex condition")
            conditions.append(formula(tree.body))
        except (SyntaxError, ValueError, RecursionError, OverflowError):
            condition_domains = {}
            conditions.append(unknown(("unparsed", index)))
        for key, literals in condition_domains.items():
            if literals is None:
                domains[key] = None
            else:
                domains.setdefault(key, set()).update(literals)

    values = []
    state_count = 1
    for literals in domains.values():
        if literals is None:
            domain = [False, True]
        else:
            # 未列出的房间或产物统一保留一个代表值，不限制实际状态。
            domain = [*sorted(literals), object()]
        state_count *= len(domain)
        if state_count > MAX_CONDITION_STATES:
            raise BackupValidationLimitExceeded(
                "验证未完成：触发条件状态数量超过分析上限"
            )
        values.append(domain)

    combinations = set()
    for assignment in product(*values):
        state = dict(zip(domains, assignment))
        flags = tuple(bool(condition(state)) for condition in conditions)
        combinations.add(flags)
        if len(combinations) > combination_limit:
            raise BackupValidationLimitExceeded(
                f"验证未完成：可能生效的副表组合数量超过校验上限 {combination_limit}"
            )
    return sorted(combinations, key=lambda flags: (sum(flags), flags))
