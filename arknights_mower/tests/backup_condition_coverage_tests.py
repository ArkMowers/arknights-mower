"""静态条件分析保留全部可成立组合，未知条件不用于推断互斥。"""

from itertools import product
from types import SimpleNamespace

import pytest

from arknights_mower.utils import backup_validation
from arknights_mower.utils.backup_validation import possible_backup_conditions


def possibilities(*expressions, limit=16384):
    plans = [SimpleNamespace(trigger=expression) for expression in expressions]
    return set(possible_backup_conditions(plans, limit))


def test_opposite_working_conditions_share_the_same_state():
    assert possibilities(
        "op_data.operators['芬'].is_working() == True",
        'False == op_data.operators["芬"].is_working()',
    ) == {(False, True), (True, False)}


def test_nested_boolean_conditions_exclude_only_proven_contradictions():
    call = "op_data.operators['芬'].is_working()"
    other = "op_data.operators['讯使'].is_working()"
    expressions = [f"{call} and {other}", f"{call} and not {other}", f"not {call}"]
    assert possibilities(*expressions) == {
        (True, False, False),
        (False, True, False),
        (False, False, True),
    }


@pytest.mark.parametrize("comparison", ["==", "is", "!=", "is not"])
def test_boolean_comparisons_preserve_polarity(comparison):
    call = "op_data.operators['芬'].is_working()"
    assert possibilities(f"{call} {comparison} True", f"{call} {comparison} False") == {
        (False, True),
        (True, False),
    }


def test_nullable_party_conditions_are_complementary():
    assert possibilities(
        "op_data.party_time is None", "op_data.party_time != None"
    ) == {(False, True), (True, False)}


def test_room_equalities_share_values_and_include_unlisted_rooms():
    room = "op_data.operators['芬'].current_room"
    expressions = [
        f"{room} == 'central'",
        f"'meeting' == {room}",
        f"{room} != 'central'",
    ]
    assert possibilities(*expressions) == {
        (True, False, False),
        (False, True, True),
        (False, False, True),
    }


@pytest.mark.parametrize(
    "expressions",
    [
        (
            "op_data.operators['芬'].current_mood() < 8",
            "op_data.operators['芬'].current_mood() >= 8",
        ),
        ("op_data.rescue_needed()", "not op_data.rescue_needed()"),
    ],
)
def test_time_dependent_and_mutating_conditions_keep_independent_choices(expressions):
    assert possibilities(*expressions) == set(product([False, True], repeat=2))


def test_unknown_arithmetic_stays_conservative_and_is_not_executed():
    assert possibilities(
        "op_data.unsupported() > 8", "op_data.unsupported() < 4"
    ) == set(product([False, True], repeat=2))


def test_non_boolean_and_or_results_are_not_compared_as_boolean_values():
    assert (True, False) in possibilities(
        "op_data.numeric()", "(op_data.numeric() or False) == True"
    )


def test_unknown_expression_and_negation_keep_the_both_failed_case():
    assert possibilities("op_data.unsupported()", "not op_data.unsupported()") == set(
        product([False, True], repeat=2)
    )


def test_missing_operator_conditions_do_not_prove_exclusion():
    call = "op_data.operators['不存在'].is_working()"
    plans = [SimpleNamespace(trigger=f"{call} == {value}") for value in (True, False)]
    assert set(possible_backup_conditions(plans, 4, known_operators={"芬"})) == set(
        product([False, True], repeat=2)
    )


def test_missing_or_unparsed_conditions_keep_both_activation_choices():
    assert possibilities(None, "invalid (") == set(product([False, True], repeat=2))


def test_possible_combination_limit_is_independent_of_backup_count():
    room = "op_data.operators['芬'].current_room"
    assert (
        len(
            possibilities(
                *(f"{room} == 'room_{index}'" for index in range(20)), limit=21
            )
        )
        == 21
    )
    with pytest.raises(ValueError, match="验证未完成"):
        possibilities("op_data.a()", "op_data.b()", limit=2)


def test_condition_analysis_budget_never_silently_prunes_unknown_states(monkeypatch):
    monkeypatch.setattr(backup_validation, "MAX_CONDITION_STATES", 2)
    with pytest.raises(ValueError, match="状态数量超过分析上限"):
        possibilities("op_data.a()", "op_data.b()")


def test_generated_combinations_cover_concrete_room_and_boolean_assignments():
    room = "op_data.operators['芬'].current_room"
    working = "op_data.operators['芬'].is_working()"
    expressions = [
        f"{room} == 'central' and {working}",
        f"{room} != 'meeting'",
        f"not {working}",
    ]
    combinations = possibilities(*expressions)
    for current_room, works in product(
        ["central", "meeting", "", "dormitory_1"], [False, True]
    ):
        assert (
            current_room == "central" and works,
            current_room != "meeting",
            not works,
        ) in combinations


def test_unknown_trigger_does_not_retain_partial_analysis_states(monkeypatch):
    monkeypatch.setattr(backup_validation, "MAX_CONDITION_STATES", 2)
    assert possibilities(
        "op_data.operators['芬'].is_working() and op_data.unknown()"
    ) == {(False,), (True,)}


def test_resource_rejected_strings_do_not_prove_complementary_conditions():
    room = "op_data.operators['芬'].current_room"
    literal = repr("x" * 513)
    assert possibilities(f"{room} == {literal}", f"{room} != {literal}") == set(
        product([False, True], repeat=2)
    )


def test_default_budget_covers_fourteen_independent_triggers_and_rejects_fifteen():
    assert len(possibilities(*([None] * 14))) == 16384
    with pytest.raises(ValueError, match="组合数量超过校验上限 16384"):
        possibilities(*([None] * 15))


def test_analyzed_conditions_cover_real_runtime_expression_results():
    from arknights_mower.utils.operators import Operator, Operators
    from arknights_mower.utils.plan import Plan, PlanConfig

    data = Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": []}
    )
    data.operators["芬"] = Operator("芬", "central")
    working = "op_data.operators['芬'].is_working()"
    resting = "op_data.operators['芬'].is_resting()"
    room = "op_data.operators['芬'].current_room"
    expressions = [
        f"{working} == True",
        f"False is {working}",
        f"not ({working} or {resting})",
        f"({working} and not {resting}) != False",
        f"{room} == 'central'",
        f"'meeting' != {room}",
        "op_data.party_time is None",
        "op_data.party_time != None",
    ]
    combinations = possibilities(*expressions)
    for current_room, party in product(
        ["central", "meeting", "", "dormitory_1"], [None, object()]
    ):
        data.operators["芬"]._current_room = current_room
        data.party_time = party
        assert (
            tuple(
                bool(data.evaluate_expression(expression)) for expression in expressions
            )
            in combinations
        )


def test_same_room_product_conditions_share_quoted_and_named_constants():
    assert possibilities(
        "op_data.facility_product('room_1_1') == 'gold'",
        "exp3 == op_data.facility_product(room_1_1)",
        "op_data.facility_product(room_1_1) != gold",
    ) == {(True, False, False), (False, True, True), (False, False, True)}
    assert (True, True) in possibilities(
        "op_data.facility_product('room_1_1') == gold",
        "op_data.facility_product('room_1_2') == exp3",
    )


def test_invalid_product_room_does_not_prove_exclusion():
    assert possibilities(
        "op_data.facility_product('missing') == gold",
        "op_data.facility_product('missing') != gold",
    ) == set(product([False, True], repeat=2))


def test_product_conditions_cover_real_runtime_cached_and_baseline_values():
    from arknights_mower.utils.operators import Operators
    from arknights_mower.utils.plan import Plan, PlanConfig

    main = Plan({}, PlanConfig("", "", ""), products={"room_1_1": "gold"})
    data = Operators({"default_plan": main, "backup_plans": []})
    expressions = [
        "op_data.facility_product('room_1_1') == gold",
        "exp3 == op_data.facility_product(room_1_1)",
        "op_data.facility_product(room_1_1) != gold",
    ]
    combinations = possibilities(*expressions)
    for cached in (None, "gold", "exp3", "lmd"):
        data.facility_states = (
            {} if cached is None else {"room_1_1": {"product": cached}}
        )
        assert (
            tuple(
                bool(data.evaluate_expression(expression)) for expression in expressions
            )
            in combinations
        )
    main.products.clear()
    data.facility_states.clear()
    assert (
        tuple(bool(data.evaluate_expression(expression)) for expression in expressions)
        in combinations
    )


@pytest.mark.parametrize("phase", ["parsing", "enumeration", "sorting"])
def test_elapsed_budget_interrupts_analysis_without_becoming_an_unknown_condition(
    monkeypatch, phase
):
    clock = [100.0]
    monkeypatch.setattr(backup_validation, "monotonic", lambda: clock[0])
    if phase == "parsing":
        original = backup_validation.ast.parse

        def slow_parse(*args, **kwargs):
            tree = original(*args, **kwargs)
            clock[0] += 5
            return tree

        monkeypatch.setattr(backup_validation.ast, "parse", slow_parse)
    elif phase == "enumeration":
        original = backup_validation.product

        def slow_assignments(*args):
            for index, state in enumerate(original(*args)):
                if index == 2:
                    clock[0] += 5
                yield state

        monkeypatch.setattr(backup_validation, "product", slow_assignments)
    else:
        original = sorted

        def slow_sort(*args, **kwargs):
            result = original(*args, **kwargs)
            clock[0] += 5
            return result

        monkeypatch.setattr(backup_validation, "sorted", slow_sort, raising=False)
    plans = [
        SimpleNamespace(trigger=expression) for expression in ("unknown1", "unknown2")
    ]
    with pytest.raises(
        backup_validation.BackupValidationLimitExceeded, match="耗时预算"
    ):
        possible_backup_conditions(plans, 16384, deadline=105)
