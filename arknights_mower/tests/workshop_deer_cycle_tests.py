"""Real crafting dispatch alternates demanded fodder, configured fodder and one T4."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from arknights_mower.data import workshop_formula
from arknights_mower.tests.workshop_limits_tests import game as game
from arknights_mower.tests.workshop_limits_tests import inventory as inventory
from arknights_mower.utils import config, workshop_automation
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.workshop_limits import deer_recipe_ready


@pytest.fixture
def deer(game, inventory, monkeypatch):
    solver, state, base = game
    config.conf.enable_mastery = True
    config.conf.workshop_auto_active = True
    config.conf.workshop_settings = [
        RIICPart.WorkShopSetting(
            operator="九色鹿",
            source="mastery",
            items=[
                WorkShopItem(
                    item_names=["固源岩组"], children_lower_limit=0, self_upper_limit=1
                ),
                WorkShopItem(
                    item_names=["家具零件_碳素组"],
                    children_lower_limit=0,
                    self_upper_limit=12,
                ),
                WorkShopItem(
                    item_names=["异铁块"], children_lower_limit=0, self_upper_limit=1
                ),
            ],
        )
    ]
    inventory.save_inventory_counts(
        {
            "固源岩组": 0,
            "固源岩": 109,
            "家具零件": 0,
            "碳素组": 3,
            "异铁块": 0,
            "异铁组": 10,
            "全新装置": 10,
            "聚酸酯组": 10,
            "龙门币": 10000,
        }
    )
    solver.op_data.operators["九色鹿"] = SimpleNamespace(mood=24)
    state.causality = 30
    solver.digit_reader = SimpleNamespace(get_deer_causality=lambda _: state.causality)
    furniture_pos = ((200, 10), (220, 20))
    old_items, old_tap = solver.item_list, solver.tap
    # Furniture appears first on screen, while the demand quota comes first in settings.
    solver.item_list = lambda: [("家具零件_碳素组", furniture_pos, True), *old_items()]

    def tap(pos, **kwargs):
        if pos == (210, 15):
            state.selected, state.count = "家具零件_碳素组", 1
            state.scene = base.Scene.FACTORY_DASHBOARD
            return
        if pos == (1920 * 0.88, 1080 * 0.88):
            state.causality = (
                0
                if state.selected == "异铁块"
                else state.causality
                + state.count * workshop_formula[state.selected]["apCost"]
            )
        old_tap(pos, **kwargs)

    solver.tap = tap
    solver._dispatch_scan_start_tasks = MagicMock()
    from arknights_mower.utils import mastery_recommendation

    schedule = MagicMock(return_value={"scheduled": []})
    monkeypatch.setattr(mastery_recommendation, "auto_schedule_mastery_tasks", schedule)

    def recalculate():
        assert state.crafts[-1] == ("异铁块", 1)
        config.conf.workshop_generation += 1

    update = MagicMock(side_effect=recalculate)
    monkeypatch.setattr(workshop_automation, "restore_if_no_plans", lambda: None)
    monkeypatch.setattr(
        workshop_automation, "refresh_workshop_after_inventory_change", lambda: True
    )
    monkeypatch.setattr(workshop_automation, "update_workshop_config", update)
    return solver, state, base, update, schedule


def test_demand_then_furniture_fodder_then_one_t4_with_real_inventory(deer, inventory):
    solver, state, base, update, schedule = deer
    solver.generate_product("九色鹿")
    base.save_exception.assert_not_called()
    assert state.crafts == [("固源岩组", 1), ("家具零件_碳素组", 1), ("异铁块", 1)]
    assert state.causality == 0
    assert inventory.get_inventory_counts()["家具零件"] == 12
    assert inventory.get_inventory_counts()["碳素组"] == 2
    assert solver.op_data.operators["九色鹿"].mood == 14
    update.assert_called_once()
    schedule.assert_called_once()


def test_completed_fodder_requires_t4_before_more_fodder(deer):
    solver, state, base, update, _ = deer
    state.causality = 36
    solver.generate_product("九色鹿")
    base.save_exception.assert_not_called()
    assert state.crafts == [("异铁块", 1)]
    update.assert_called_once()


def test_no_usable_t4_stops_without_more_fodder(deer, inventory):
    solver, state, base, update, _ = deer
    state.causality = 36
    inventory.save_inventory_counts({"异铁块": 1})
    for _ in range(2):
        solver.generate_product("九色鹿")
    assert state.crafts == []
    update.assert_not_called()
    base.save_exception.assert_not_called()


def test_rejected_first_fodder_uses_configured_fallback_in_the_same_visit(deer):
    from arknights_mower.utils.workshop_ui import FORMULA_TABS

    solver, state, base, update, _ = deer
    config.conf.workshop_settings[0].items[1].self_upper_limit = 24
    original = solver.item_list
    original_tap = solver.tap
    state.scrolled = False
    chip = FORMULA_TABS["芯片"]

    def tap(pos, **kwargs):
        if pos == (chip[0] * 1920, chip[1] * 1080):
            state.scrolled = False
        original_tap(pos, **kwargs)

    solver.tap = tap
    solver.swipe_noinertia = lambda *a, **kw: setattr(state, "scrolled", True)

    def items():
        if state.scrolled:
            return []
        return [
            (name, pos, False if name == "固源岩组" else valid)
            for name, pos, valid in original()
        ]

    solver.item_list = items
    solver.generate_product("九色鹿")
    base.save_exception.assert_not_called()
    assert state.crafts == [("家具零件_碳素组", 2), ("异铁块", 1)]
    update.assert_called_once()


def test_random_byproduct_does_not_advance_causality_or_change_inventory(
    deer, inventory, monkeypatch
):
    solver, state, base, update, _ = deer
    config.conf.workshop_settings[0].items[1].self_upper_limit = 24
    inventory.save_inventory_counts({"异铁": 100})
    original = solver.tap

    def tap(pos, **kwargs):
        before = state.causality
        original(pos, **kwargs)
        if pos == (1920 * 0.88, 1080 * 0.88) and state.selected == "固源岩组":
            state.causality = before

    solver.tap = tap
    solver.generate_product("九色鹿")
    base.save_exception.assert_not_called()
    assert state.crafts == [("固源岩组", 1), ("家具零件_碳素组", 2), ("异铁块", 1)]
    assert inventory.get_inventory_counts()["异铁"] == 100
    assert solver.op_data.operators["九色鹿"].mood == 10
    update.assert_called_once()


@pytest.mark.parametrize("gap", [0, 1, 4, 5, 8, 40])
def test_phase_checks_distinguish_four_mood_furniture_from_t4(gap):
    assert deer_recipe_ready(workshop_formula["家具零件_碳素组"], gap) is (gap >= 5)
    assert deer_recipe_ready(workshop_formula["糖组"], gap) is (gap >= 5)
    assert deer_recipe_ready(workshop_formula["技巧概要·卷3"], gap) is (gap >= 5)
    assert deer_recipe_ready(workshop_formula["异铁块"], gap) is (gap <= 4)
