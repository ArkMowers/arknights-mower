import unittest

import pytest
from pydantic import ValidationError

from arknights_mower.utils.config.plan import (
    BackupGroup,
    BackupPlan,
    Trigger,
    contains_retired_rescue_condition,
)
from arknights_mower.utils.logic_expression import get_logic_exp

dict_minus = {"left": "114514", "operator": "-", "right": "1919810"}


class TestLogicExpression(unittest.TestCase):
    def test_single(self):
        self.assertEqual(str(get_logic_exp({"left": "114514"})), "(114514  )")

    def test_flat(self):
        self.assertEqual(str(get_logic_exp(dict_minus)), "(114514 - 1919810)")

    def test_nested(self):
        self.assertEqual(
            str(get_logic_exp({"left": "hi", "operator": "and", "right": dict_minus})),
            "(hi and (114514 - 1919810))",
        )


@pytest.mark.parametrize(
    "function,args,expected",
    [
        ("max", ["1", "9", "3"], "max(1, 9, 3)"),
        ("min", ["1", "9", "3"], "min(1, 9, 3)"),
        ("sum", ["1", "9", "3"], "sum([1, 9, 3])"),
        ("any", ["True", "False"], "any([True, False])"),
        ("all", ["True", "False"], "all([True, False])"),
        ("abs", ["-8"], "abs(-8)"),
    ],
)
def test_function_survives_config_round_trip(function, args, expected):
    node = {"function": function, "args": args}
    source = {"left": node, "operator": "==", "right": "1"}
    saved = Trigger.model_validate_json(
        Trigger.model_validate(source).model_dump_json()
    )
    assert saved.model_dump() == source
    assert str(get_logic_exp(saved.model_dump())) == f"({expected} == 1)"
    for model in (BackupGroup, BackupPlan):
        result = model.model_validate(
            {"name": "函数条件", "id": "group", "trigger": node}
        )
        assert result.trigger.model_dump() == node


def test_nested_function_and_binary_arguments():
    source = {
        "function": "max",
        "args": [
            "3",
            {"left": "2", "operator": "+", "right": "8"},
            {"function": "min", "args": ["4", "7"]},
        ],
    }
    assert str(get_logic_exp(source)) == "max(3, (2 + 8), min(4, 7))"


@pytest.mark.parametrize(
    "node",
    [
        {"function": "max", "args": ["1"]},
        {"function": "min", "args": []},
        {"function": "abs", "args": ["1", "2"]},
        {"function": "sum", "args": []},
        {"function": "eval", "args": ["1"]},
    ],
)
def test_invalid_function_is_rejected(node):
    with pytest.raises(ValidationError):
        Trigger.model_validate({"left": node})
    with pytest.raises(ValueError):
        get_logic_exp(node)


def test_retired_condition_is_recognized_inside_function_arguments():
    assert contains_retired_rescue_condition(
        {"function": "any", "args": ["False", {"left": "op_data.rescue_needed()"}]}
    )
    assert not contains_retired_rescue_condition(
        {"function": "any", "args": ['"op_data.rescue_needed()"']}
    )
