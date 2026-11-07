"""Intermediate reserves and their fees must be supplied before growth crafting."""

from collections import Counter

import pytest

from arknights_mower.data import workshop_formula
from arknights_mower.tests.growth_crafting_order_tests import order_case as order_case
from arknights_mower.tests.growth_planning_tests import growth_case as growth_case
from arknights_mower.utils.config.conf import WorkShopItem
from arknights_mower.utils.growth_workshop import (
    crafting_gold_cost,
    growth_workshop_config,
    next_recipe,
)
from arknights_mower.utils.mastery_materials import MaterialBudget
from arknights_mower.utils.workshop_limits import batch_delta, batch_limit


@pytest.fixture
def sugar_case(order_case):
    case = order_case
    case.plans = [case.plans[0]]
    case.goals = []
    case.skills["items"].update(
        {
            "raw": {"name": "代糖", "rarity": 1},
            "sugar": {"name": "糖", "rarity": 2},
            "t3": {"name": "糖组", "rarity": 3},
            "4001": {"name": "龙门币", "rarity": 0},
        }
    )
    case.formulas = {name: workshop_formula[name] for name in ("糖", "糖组")}
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = [
        {"id": "t3", "count": 1}
    ]
    case.stock = Counter({"raw": 112, "sugar": 0, "t3": 0, "4001": 20000})
    return case


def generate(case):
    return growth_workshop_config(
        case.box,
        case.skills,
        case.plans,
        case.goals,
        case.stock,
        case.formulas,
        case.operators,
    )


def test_low_raw_stock_cannot_admit_a_chain_that_would_spend_the_new_intermediate(
    sugar_case,
):
    case = sugar_case
    budget = MaterialBudget(case.skills, case.stock, case.formulas)
    assert budget.calculate([{"id": "t3", "count": 1}])["craftable"] is False
    assert generate(case).settings == []
    assert case.stock["raw"] == 112 and case.stock["sugar"] == 0


def test_reserve_deficit_is_included_in_the_first_intermediate_quota(sugar_case):
    case = sugar_case
    case.stock["raw"] = 412
    settings = generate(case).settings
    assert settings[0]["items"] == [
        {"item_names": ["糖"], "children_lower_limit": 0, "self_upper_limit": 104}
    ]


@pytest.mark.parametrize("gold,admitted", [(200, False), (599, False), (600, True)])
def test_fee_includes_four_extra_intermediates_needed_above_the_reserve(
    sugar_case, gold, admitted
):
    case = sugar_case
    case.stock["sugar"] = 100
    case.stock["4001"] = gold
    budget = MaterialBudget(case.skills, case.stock, case.formulas)
    assert crafting_gold_cost(budget, [{"id": "t3", "count": 1}], case.formulas) == 600
    assert bool(generate(case).settings) is admitted


def test_admitted_chain_finishes_at_exact_gold_and_material_reserves(sugar_case):
    case = sugar_case
    case.stock["sugar"] = 100
    case.stock["4001"] = 600
    names = {"代糖": "raw", "糖": "sugar", "糖组": "t3", "龙门币": "4001"}
    for expected_name, expected_batches in [("糖", 4), ("糖组", 1)]:
        item = generate(case).settings[0]["items"][0]
        assert item["item_names"] == [expected_name]
        inventory = {name: case.stock[iid] for name, iid in names.items()}
        assert (
            batch_limit(
                expected_name,
                case.formulas[expected_name],
                WorkShopItem(**item),
                inventory,
            )
            == expected_batches
        )
        for name, amount in batch_delta(
            expected_name, case.formulas[expected_name], expected_batches
        ).items():
            case.stock[names[name]] += amount
    assert case.stock == Counter({"raw": 100, "sugar": 100, "t3": 1, "4001": 0})
    assert generate(case).settings == []


def test_direct_t2_goal_does_not_require_building_an_unused_reserve(sugar_case):
    case = sugar_case
    case.stock["raw"] = 103
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = [
        {"id": "sugar", "count": 1}
    ]
    assert generate(case).settings[0]["items"][0]["self_upper_limit"] == 1


def test_direct_t2_goal_can_share_the_stock_held_above_ingredient_consumption(
    sugar_case,
):
    case = sugar_case
    case.stock["sugar"] = 100
    case.stock["4001"] = 600
    materials = [{"id": "sugar", "count": 3}, {"id": "t3", "count": 1}]
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = (
        materials
    )
    budget = MaterialBudget(case.skills, case.stock, case.formulas)
    assert crafting_gold_cost(budget, materials, case.formulas) == 600
    assert generate(case).settings[0]["items"][0] == {
        "item_names": ["糖"],
        "children_lower_limit": 0,
        "self_upper_limit": 104,
    }


def test_earlier_prepared_entry_keeps_its_physical_stock_in_the_ingredient_floor(
    sugar_case,
):
    case = sugar_case
    case.stock["sugar"] = 100
    entries = [
        ("before", [{"id": "sugar", "count": 3}]),
        ("after", [{"id": "t3", "count": 1}]),
    ]
    _, items = next_recipe(entries, case.skills, case.stock, case.formulas)
    assert items == [
        {"item_names": ["糖"], "children_lower_limit": 0, "self_upper_limit": 104}
    ]
    case.stock["sugar"] = 104
    case.stock["raw"] = 100
    _, items = next_recipe(entries, case.skills, case.stock, case.formulas)
    assert items == [
        {"item_names": ["糖组"], "children_lower_limit": 0, "self_upper_limit": 1}
    ]


@pytest.mark.parametrize("direct_sugar", [3, 100, 105])
@pytest.mark.parametrize("owned_sugar", [0, 2])
def test_new_intermediate_stock_also_satisfies_the_direct_goal(
    sugar_case, direct_sugar, owned_sugar
):
    case = sugar_case
    materials = [{"id": "sugar", "count": direct_sugar}, {"id": "t3", "count": 1}]
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = (
        materials
    )
    final_sugar = max(100, direct_sugar)
    sugar_batches = final_sugar + 4 - owned_sugar
    case.stock["raw"] = 100 + 3 * sugar_batches
    case.stock["sugar"] = owned_sugar
    case.stock["4001"] = 100 * sugar_batches + 200
    budget = MaterialBudget(case.skills, case.stock, case.formulas)
    summary = budget.calculate(materials)
    assert summary["missing"] == []
    assert summary["craftable"] is True
    assert crafting_gold_cost(budget, materials, case.formulas) == case.stock["4001"]

    names = {"代糖": "raw", "糖": "sugar", "糖组": "t3", "龙门币": "4001"}
    for expected_name, expected_batches in [
        ("糖", 99),
        ("糖", sugar_batches - 99),
        ("糖组", 1),
    ]:
        item = generate(case).settings[0]["items"][0]
        assert item["item_names"] == [expected_name]
        inventory = {name: case.stock[iid] for name, iid in names.items()}
        assert (
            batch_limit(
                expected_name,
                case.formulas[expected_name],
                WorkShopItem(**item),
                inventory,
            )
            == expected_batches
        )
        for name, amount in batch_delta(
            expected_name, case.formulas[expected_name], expected_batches
        ).items():
            case.stock[names[name]] += amount
    assert case.stock == Counter({"raw": 100, "sugar": final_sugar, "t3": 1, "4001": 0})
    assert generate(case).settings == []


@pytest.mark.parametrize("direct_sugar", [3, 100, 105])
def test_next_recipe_does_not_add_the_direct_goal_to_the_intermediate_floor(
    sugar_case, direct_sugar
):
    case = sugar_case
    case.stock["raw"] = 1000
    entries = [
        ("target", [{"id": "sugar", "count": direct_sugar}, {"id": "t3", "count": 1}])
    ]
    _, items = next_recipe(entries, case.skills, case.stock, case.formulas)
    assert items == [
        {
            "item_names": ["糖"],
            "children_lower_limit": 0,
            "self_upper_limit": max(100, direct_sugar) + 4,
        }
    ]


@pytest.mark.parametrize("short_resource", ["raw", "4001"])
def test_shared_direct_goal_still_rejects_a_material_or_fee_deficit(
    sugar_case, short_resource
):
    case = sugar_case
    case.stock["raw"] = 412
    case.stock["4001"] = 10600
    case.stock[short_resource] -= 1
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = [
        {"id": "sugar", "count": 3},
        {"id": "t3", "count": 1},
    ]
    assert generate(case).settings == []


def test_direct_goal_uses_owned_stock_below_the_ingredient_floor(sugar_case):
    case = sugar_case
    materials = [{"id": "sugar", "count": 3}]
    case.skills["characters"]["char_test"]["skills"][0]["levels"][0]["materials"] = (
        materials
    )
    case.stock = Counter({"sugar": 3})
    budget = MaterialBudget(case.skills, case.stock, case.formulas)
    summary = budget.calculate(materials)
    assert summary["available"] is True
    assert summary["craftable"] is True
    assert summary["missing"] == []
    assert crafting_gold_cost(budget, materials, case.formulas) == 0
    assert generate(case).settings == []
