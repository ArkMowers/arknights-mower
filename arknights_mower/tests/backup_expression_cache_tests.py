"""副表条件复用已校验的编译结果，每次读取当前预演状态。"""

import copy
import ctypes
import gc
import weakref
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock

import pytest

from arknights_mower.utils import operators
from arknights_mower.utils.logic_expression import get_logic_exp
from arknights_mower.utils.operators import Operator, Operators
from arknights_mower.utils.plan import Plan, PlanConfig


def make_data():
    model = Operators(
        {
            "default_plan": Plan({}, PlanConfig("", "", "")),
            "backup_plans": [],
        }
    )
    model.operators["芬"] = Operator("芬", "central", mood=3)
    assert model.evaluate_expression("True") is True
    return model


@pytest.fixture(autouse=True)
def isolated_cache():
    operators._compile_expression.cache_clear()
    yield
    operators._compile_expression.cache_clear()


@pytest.fixture
def data():
    return make_data()


@pytest.mark.parametrize(
    "function,args,expected",
    [
        ("max", ["3", "9", "4"], 9),
        ("min", ["3", "9", "4"], 3),
        ("sum", ["3", "9", "4"], 16),
        ("any", ["False", "True", "False"], True),
        ("all", ["True", "False", "True"], False),
        ("abs", ["-8"], 8),
    ],
)
def test_evaluates_saved_function_conditions(data, function, args, expected):
    source = str(get_logic_exp({"function": function, "args": args}))
    assert data.evaluate_expression(source) == expected


def test_nested_functions_read_current_operator_state(data):
    source = str(
        get_logic_exp(
            {
                "left": {
                    "function": "max",
                    "args": [
                        "op_data.operators['芬'].current_mood()",
                        {"function": "abs", "args": ["-8"]},
                    ],
                },
                "operator": ">=",
                "right": "10",
            }
        )
    )
    assert data.evaluate_expression(source) is False
    data.operators["芬"].mood = 12
    assert data.evaluate_expression(source) is True


def test_reuses_compilation_while_reading_current_and_projected_mood(data, monkeypatch):
    compile_expression = Mock(wraps=operators.Expr)
    monkeypatch.setattr(operators, "Expr", compile_expression)
    expression = "op_data.operators['芬'].current_mood() < 8"

    assert data.evaluate_expression(expression) is True
    projected = data.project_arrangements([])
    projected.operators["芬"].mood = 12
    assert projected.evaluate_expression(expression) is False
    assert data.evaluate_expression(expression) is True
    assert data.operators["芬"].mood == 3
    assert compile_expression.call_count == 1


@pytest.mark.parametrize("permission", ["nodes", "attributes"])
def test_cached_expression_obeys_each_models_current_permissions(data, permission):
    create_capsule = ctypes.pythonapi.PyCapsule_New
    create_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    create_capsule.restype = ctypes.py_object
    capsule = create_capsule(ctypes.c_void_p(42), None, None)
    data.eval_model.imported_functions["__builtins__"] = {"runtime_handle": capsule}
    expression = "op_data.party_time is None"
    assert data.evaluate_expression(expression) is True
    restricted = copy.copy(data)
    restricted.eval_model = copy.copy(data.eval_model)
    setattr(
        restricted.eval_model, permission, list(getattr(data.eval_model, permission))
    )
    assert (
        restricted.eval_model.imported_functions["__builtins__"]["runtime_handle"]
        is capsule
    )
    removed = "Is" if permission == "nodes" else "party_time"
    getattr(restricted.eval_model, permission).remove(removed)

    assert restricted.evaluate_expression(expression) is None
    assert data.evaluate_expression(expression) is True
    getattr(data.eval_model, permission).remove(removed)
    assert data.evaluate_expression(expression) is None


def test_evaluation_keeps_permission_model_unchanged_and_cache_key_stable():
    model = Operators(
        {
            "default_plan": Plan({}, PlanConfig("", "", "")),
            "backup_plans": [],
        }
    )
    imported_functions = model.eval_model.imported_functions.copy()
    before = operators._compile_expression.cache_info()

    assert model.evaluate_expression("True") is True
    assert model.eval_model.imported_functions == imported_functions
    assert model.evaluate_expression("True") is True
    after = operators._compile_expression.cache_info()
    assert after.misses - before.misses == 1
    assert after.hits - before.hits == 1
    assert model.eval_model.clone() == model.eval_model


def test_cached_builtin_call_obeys_allowed_function_changes(data):
    expression = "len('abc') == 3"
    data.eval_model.allowed_functions.append("len")
    assert data.evaluate_expression(expression) is True
    data.eval_model.allowed_functions.remove("len")
    assert data.evaluate_expression(expression) is None


def test_cached_imported_call_reads_current_function_and_name_permissions(data):
    expression = "sample() == 3"
    data.eval_model.imported_functions["sample"] = lambda: 3
    assert data.evaluate_expression(expression) is True
    data.eval_model.imported_functions["sample"] = lambda: 4
    assert data.evaluate_expression(expression) is False
    del data.eval_model.imported_functions["sample"]
    assert data.evaluate_expression(expression) is None


@pytest.mark.parametrize(
    ("expression", "reason"),
    [
        ("1" * 2049, "表达式过长"),
        (" + ".join(["1"] * 80), "表达式过于复杂"),
        (str(2**300), "整数常量过大"),
        (repr("x" * 513), "字符串常量过长"),
        ("'x' * 2", "乘法仅支持数值表达式"),
        ("2 ** 65", "幂运算指数必须是 0 到 64 的整数常量"),
        ("((2 ** 64) ** 64) ** 2", "幂运算结果过大"),
        ("op_data.__class__", "Attribute __class__ is not allowed"),
        ("__import__('os')", "Call to function __import__() is not allowed"),
        ("invalid (", "was never closed"),
    ],
)
def test_rejected_expressions_preserve_errors_and_never_enter_cache(
    data, monkeypatch, expression, reason
):
    errors = Mock()
    monkeypatch.setattr(operators.logger, "exception", errors)
    initial_size = operators._compile_expression.cache_info().currsize

    for _ in range(2):
        assert data.evaluate_expression(expression) is None
        assert reason in errors.call_args.args[0]
    assert errors.call_count == 2
    assert operators._compile_expression.cache_info().currsize == initial_size


def test_runtime_failure_does_not_cache_missing_operator_result(data, monkeypatch):
    expression = "op_data.operators['红'].current_mood() < 8"
    errors = Mock()
    monkeypatch.setattr(operators.logger, "exception", errors)
    assert data.evaluate_expression(expression) is None
    assert errors.call_args.args[0] == "附表格式出错: '红'"

    data.operators["红"] = Operator("红", "central", mood=4)
    assert data.evaluate_expression(expression) is True


def test_cache_evicts_old_compilation_and_keeps_recently_used_conditions(
    data, monkeypatch
):
    compile_expression = Mock(wraps=operators.Expr)
    monkeypatch.setattr(operators, "Expr", compile_expression)
    for index in range(256):
        assert data.evaluate_expression(f"{index} < 1000") is True
    assert operators._compile_expression.cache_info().currsize == 256

    assert data.evaluate_expression("0 < 1000") is True
    assert data.evaluate_expression("256 < 1000") is True
    assert data.evaluate_expression("0 < 1000") is True
    assert compile_expression.call_count == 257
    assert data.evaluate_expression("1 < 1000") is True
    assert compile_expression.call_count == 258
    assert operators._compile_expression.cache_info().currsize == 256


def test_cache_does_not_retain_operators_or_imported_runtime_handles():
    class RuntimeHandle:
        def __deepcopy__(self, memo):
            raise AssertionError("runtime handle must not be copied")

    model = make_data()
    model.eval_model.imported_functions["runtime_handle"] = RuntimeHandle()
    handle = weakref.ref(model.eval_model.imported_functions["runtime_handle"])
    source = weakref.ref(model)
    assert (
        model.evaluate_expression("op_data.operators['芬'].current_mood() < 8") is True
    )

    projected = copy.deepcopy(model, {id(model.eval_model): model.eval_model})
    assert projected.eval_model is model.eval_model
    assert projected.operators["芬"] is not model.operators["芬"]
    del projected, model
    gc.collect()
    assert source() is None
    assert handle() is None


def test_concurrent_evaluations_share_code_without_mixing_operator_state():
    start = Barrier(8)

    def evaluate(index):
        model = make_data()
        model.operators["芬"].mood = index
        start.wait(timeout=5)
        return [
            model.evaluate_expression("op_data.operators['芬'].current_mood()")
            for _ in range(3)
        ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        result = list(executor.map(evaluate, range(8)))
    assert result == [[index] * 3 for index in range(8)]
    assert operators._compile_expression.cache_info().currsize <= 256
