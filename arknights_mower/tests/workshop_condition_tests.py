from unittest.mock import MagicMock

import pytest

from arknights_mower.tests.workshop_plan_cache_tests import planning as planning
from arknights_mower.tests.workshop_plan_fixtures import next_skill as next_skill
from arknights_mower.utils import config
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.plan import Plan, PlanConfig


@pytest.fixture
def condition_data(planning, monkeypatch):
    from arknights_mower.solvers import record

    monkeypatch.setattr(record, "get_inventory_counts", lambda: dict(planning.stock))
    backup = Plan(
        {},
        PlanConfig("", "", ""),
        LogicExpression("op_data.facility_has_crafting_plan('factory')", "==", "True"),
    )
    return Operators(
        {"default_plan": Plan({}, PlanConfig("", "", "")), "backup_plans": [backup]}
    )


@pytest.mark.parametrize("ingredients", [0, 300])
@pytest.mark.parametrize("automation", [False, True])
def test_only_currently_craftable_growth_content_activates_backup(
    condition_data, planning, ingredients, automation
):
    planning.stock["技巧概要·卷2"] = ingredients
    config.conf.enable_mastery = automation
    before = config.conf.model_dump()
    for _ in range(3):
        assert condition_data.evaluate_backup_selection().conditions == [
            ingredients > 0
        ]
    assert config.conf.model_dump() == before
    config.save_conf.assert_not_called()


def test_finished_stock_and_removed_plans_release_backup(
    condition_data, planning, next_skill
):
    assert condition_data.evaluate_backup_selection().conditions == [True]
    planning.stock["技巧概要·卷3"] = 12
    assert condition_data.evaluate_backup_selection().conditions == [False]
    planning.stock["技巧概要·卷3"] = 0
    assert condition_data.evaluate_backup_selection().conditions == [True]
    next_skill.plans.clear()
    assert condition_data.evaluate_backup_selection().conditions == [False]


def test_manual_settings_do_not_count_as_growth_crafting(condition_data, next_skill):
    from arknights_mower.utils.config.conf import RIICPart

    next_skill.plans.clear()
    config.conf.workshop_settings = [
        RIICPart.WorkShopSetting(
            operator="赫拉格",
            items=[{"item_names": ["技巧概要·卷3"]}],
        )
    ]
    assert condition_data.evaluate_backup_selection().conditions == [False]


def test_crafting_content_does_not_require_available_operator(condition_data):
    config.conf.book_operators = []
    assert condition_data.evaluate_backup_selection().conditions == [True]


def test_projection_uses_latest_local_stock_without_saving(condition_data, planning):
    projected = condition_data.project_arrangements([])
    assert projected.evaluate_backup_selection().conditions == [True]
    planning.stock["技巧概要·卷3"] = 12
    assert projected.evaluate_backup_selection().conditions == [False]
    assert condition_data.plan_condition == [False]


@pytest.mark.parametrize("source", ["mastery", "growth"])
@pytest.mark.parametrize("failure", ["missing", "unreadable", "invalid_json"])
def test_unavailable_local_data_keeps_boolean_conditions_and_recovers(
    condition_data, next_skill, planning, monkeypatch, source, failure
):
    from pathlib import Path

    from arknights_mower.utils import operators

    if source == "growth":
        from arknights_mower.utils import mastery_recommendation as rec

        next_skill.plans.clear()
        skills = dict(rec.get_skill_data())
        skills["growth"] = {
            "characters": {
                "char_a": {
                    "modules": [
                        {
                            "id": "module_a",
                            "elite": 2,
                            "level": 1,
                            "materials": [{"id": "3303", "count": 2}],
                        }
                    ]
                }
            }
        }
        monkeypatch.setattr(rec, "get_skill_data", lambda: skills)
        planning.goals.append({"char_id": "char_a", "module_id": "module_a"})
    path = next_skill.cultivate
    original = path.read_bytes()
    error_log = MagicMock()
    monkeypatch.setattr(operators.logger, "exception", error_log)
    query = "op_data.facility_has_crafting_plan('factory')"
    assert condition_data.evaluate_expression(query) is True
    checks = [
        (f"{query} == True", False),
        (f"{query} == False", True),
        (f"not {query}", True),
        (f"{query} or True", True),
        (f"{query} and True", False),
        (f"any([{query}, True])", True),
        (f"all([not {query}, True])", True),
    ]
    condition_data.backup_plans = [
        Plan({}, PlanConfig("", "", ""), expression) for expression, _ in checks
    ]
    condition_data.plan_condition = [False] * len(checks)
    with monkeypatch.context() as unavailable:
        if failure == "missing":
            path.unlink()
        elif failure == "invalid_json":
            path.write_text("{", encoding="utf-8")
        else:
            read_bytes = Path.read_bytes

            def read(target):
                if target == path:
                    raise PermissionError("local growth data unavailable")
                return read_bytes(target)

            unavailable.setattr(Path, "read_bytes", read)
        for _ in range(3):
            for expression, expected in checks:
                assert condition_data.evaluate_expression(expression) is expected
            assert condition_data.evaluate_backup_selection().conditions == [
                expected for _, expected in checks
            ]
        error_log.assert_not_called()
        config.save_conf.assert_not_called()
    path.write_bytes(original)
    assert condition_data.evaluate_expression(query) is True


@pytest.mark.parametrize("room", ["train", "central", "room_1_1", ""])
def test_crafting_condition_rejects_other_facilities(condition_data, room):
    with pytest.raises(ValueError, match="加工站位置"):
        condition_data.facility_has_crafting_plan(room)
