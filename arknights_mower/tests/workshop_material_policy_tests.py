"""The T2 preservation switch applies to plans, saved tasks and batch execution."""

import copy

import pytest

from arknights_mower.data import workshop_formula
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import RIICPart, WorkShopItem
from arknights_mower.utils.mastery_materials import MaterialBudget
from arknights_mower.utils.workshop_limits import batch_limit
from arknights_mower.utils.workshop_material_policy import (
    PROTECTED_T2_MATERIALS,
    protected_workshop_materials,
)
from arknights_mower.utils.workshop_recommendation import (
    allocate_workshop_items,
    prioritize_workshop_settings,
)


def test_switch_defaults_off_and_round_trips():
    assert not RIICPart().workshop_protect_t2_device_rock
    enabled = RIICPart(workshop_protect_t2_device_rock=True)
    assert RIICPart(**enabled.model_dump()).workshop_protect_t2_device_rock


@pytest.mark.parametrize("enabled", [False, True])
def test_only_exact_t2_ingredients_are_blocked_at_execution(monkeypatch, enabled):
    monkeypatch.setattr(config.conf, "workshop_protect_t2_device_rock", enabled)
    setting = WorkShopItem(self_upper_limit=1, children_lower_limit=0)
    for name in (
        "固源岩组",
        "全新装置",
        "提纯源岩",
        "改量装置",
        "固源岩",
        "装置",
        "技巧概要·卷3",
    ):
        recipe = workshop_formula[name]
        inventory = {ingredient: 99 for ingredient in recipe["items"]}
        inventory[recipe["output_name"]] = 0
        protected = bool(PROTECTED_T2_MATERIALS.intersection(recipe["items"]))
        assert batch_limit(name, recipe, setting, inventory) == (
            0 if enabled and protected else 1
        ), name


def test_saved_and_generated_tasks_preserve_other_materials_and_user_settings(
    monkeypatch,
):
    monkeypatch.setattr(config.conf, "workshop_protect_t2_device_rock", True)
    items = [
        {
            "item_names": ["固源岩组", "全新装置", "提纯源岩"],
            "self_upper_limit": 5,
            "children_lower_limit": 0,
        }
    ]
    settings = [{"operator": "测试干员", "enabled": True, "items": items}]
    before = copy.deepcopy(settings)
    scoped = prioritize_workshop_settings(settings, available={})
    assert scoped[0]["items"][0]["item_names"] == ["提纯源岩"]
    assert settings == before
    generated = allocate_workshop_items(
        [("fodder_operators", ["测试干员"], items)], available={}
    )
    assert [
        name
        for entry in generated
        for item in entry["items"]
        for name in item["item_names"]
    ] == ["提纯源岩"]
    monkeypatch.setattr(config.conf, "workshop_protect_t2_device_rock", False)
    assert prioritize_workshop_settings(settings, available={}) == before


@pytest.mark.parametrize("name", ["固源岩", "装置"])
@pytest.mark.parametrize("enabled", [False, True])
def test_budget_excludes_protected_t2_and_t1_routes_but_uses_t3_stock(
    monkeypatch, name, enabled
):
    monkeypatch.setattr(config.conf, "workshop_protect_t2_device_rock", enabled)
    data = {
        "items": {
            "t1": {"name": "低阶原料", "rarity": 1},
            "t2": {"name": name, "rarity": 2},
            "t3": {"name": "蓝材料", "rarity": 3},
            "t4": {"name": "紫材料", "rarity": 4},
        },
        "composite": {
            "t2": {"pathway": [{"id": "t1", "count": 3}]},
            "t3": {"pathway": [{"id": "t2", "count": 5}]},
            "t4": {"pathway": [{"id": "t3", "count": 3}]},
        },
    }
    calculator = MaterialBudget(
        data,
        {"t1": 300, "t2": 100, "t3": 1},
        blocked_materials=protected_workshop_materials(),
    )
    result = calculator.calculate_plan([("skill", [{"id": "t4", "count": 1}])])
    assert result["craftable"] is not enabled
    if enabled:
        assert [(row["id"], row["count"]) for row in result["missing"]] == [("t3", 2)]
        assert all(row["id"] not in {"t1", "t2"} for row in result["crafting"])
        assert result["missing_skills"] == ["skill"]
    else:
        assert result["missing"] == []
