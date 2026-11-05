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


@pytest.mark.parametrize("room", ["train", "central", "room_1_1", ""])
def test_crafting_condition_rejects_other_facilities(condition_data, room):
    with pytest.raises(ValueError, match="加工站位置"):
        condition_data.facility_has_crafting_plan(room)
