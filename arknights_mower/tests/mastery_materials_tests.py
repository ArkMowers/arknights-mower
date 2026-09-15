"""Inventory is shared across all requirements, including intermediate crafts."""

import copy
import json

import pytest

from arknights_mower.utils.mastery_materials import (
    MaterialBudget,
    plan_material_summary,
)


def resources():
    return {
        "items": {
            "t5": {"name": "金材料", "rarity": 5},
            "t4": {"name": "紫材料", "rarity": 4},
            "t3": {"name": "蓝材料", "rarity": 3},
            "t2": {"name": "绿材料", "rarity": 2},
            "t1": {"name": "白材料", "rarity": 1},
            "3303": {"name": "技巧概要·卷3", "rarity": 4},
            "3302": {"name": "技巧概要·卷2", "rarity": 3},
        },
        "composite": {
            "t5": {"pathway": [{"id": "t4", "count": 2}]},
            "t4": {"pathway": [{"id": "t3", "count": 3}]},
        },
    }


def lower_recipes():
    return {
        "蓝材料": {"costs": {"绿材料": 5}},
        "绿材料": {"costs": {"白材料": 3}},
        "技巧概要·卷3": {"costs": {"技巧概要·卷2": 3}},
    }


def budget(demand, stock):
    return MaterialBudget(resources(), stock, lower_recipes()).calculate(
        [{"id": key, "count": value} for key, value in demand.items()]
    )


def test_intermediate_stock_is_used_before_decomposition():
    result = budget({"t5": 1}, {"t4": 1, "t3": 3})
    assert not result["available"]
    assert result["craftable"]
    assert [(r["id"], r["required"]) for r in result["crafting"]] == [
        ("t4", 2),
        ("t3", 3),
    ]
    assert result["missing"] == []


def test_direct_and_indirect_needs_share_inventory_once():
    result = budget({"t5": 1, "t4": 1, "t3": 2}, {"t4": 1, "t3": 4})
    assert [(r["id"], r["count"]) for r in result["missing"]] == [("t3", 4)]
    assert result["missing"][0]["required"] == 8


def test_multiple_skills_do_not_each_spend_the_same_stock():
    result = MaterialBudget(resources(), {"t3": 5}).calculate(
        [{"id": "t3", "count": 4}, {"id": "t3", "count": 4}]
    )
    assert result["missing"][0]["count"] == 3


def test_lower_stock_makes_whole_blue_materials_only():
    result = budget({"t3": 3}, {"t2": 9, "t1": 3})
    assert result["missing"][0]["count"] == 1
    assert result["missing"][0]["blue"]
    assert result["missing"][0]["craftable_count"] == 2
    result = budget({"t3": 1}, {"t2": 4})
    assert result["missing"][0]["count"] == 1


def test_books_are_craftable_but_missing_books_are_not_blue_elite_materials():
    assert budget({"3303": 2}, {"3302": 6})["craftable"]
    result = budget({"3303": 2}, {"3302": 5})
    assert result["missing"][0]["count"] == 1
    assert not result["missing"][0]["blue"]


def test_owned_high_materials_do_not_consume_lower_stock():
    result = budget({"t5": 1, "t3": 2}, {"t5": 1, "t3": 2})
    assert result["available"] and result["craftable"]
    assert not result["crafting"]


def test_missing_recipe_does_not_silently_mark_materials_craftable():
    result = budget({"unknown": 1}, {})
    assert not result["craftable"]
    assert result["missing"][0]["count"] == 1


def test_inputs_are_not_mutated_and_repeated_calculations_are_independent():
    data, stock = resources(), {"t3": 3}
    saved = copy.deepcopy((data, stock))
    calculator = MaterialBudget(data, stock)
    assert calculator.calculate([{"id": "t4", "count": 1}]) == calculator.calculate(
        [{"id": "t4", "count": 1}]
    )
    assert (data, stock) == saved


def test_recipe_cycles_are_rejected():
    data = resources()
    data["composite"]["t3"] = {"pathway": [{"id": "t5", "count": 1}]}
    with pytest.raises(ValueError, match="循环"):
        MaterialBudget(data, {})


@pytest.mark.parametrize(
    "status,target,current,runtime_level,expected",
    [
        ("idle", 2, 0, None, 3),
        ("training", 3, 0, 1, 6),
        ("waiting_collect", 3, 1, 1, 6),
        ("idle", 3, 2, None, 4),
    ],
)
def test_plan_summary_uses_remaining_target_levels_and_excludes_paid_training(
    tmp_path, monkeypatch, status, target, current, runtime_level, expected
):
    from arknights_mower.utils import mastery_db, mastery_recommendation, path

    data = resources()
    data["characters"] = {
        "char_test": {
            "skills": [
                {
                    "levels": [
                        {"materials": [{"id": "t3", "count": count}]}
                        for count in (1, 2, 4)
                    ]
                }
            ]
        }
    }
    box = tmp_path / "box.json"
    box.write_text(
        json.dumps(
            {
                "data": {
                    "characters": [{"id": "char_test", "skills": [{"level": current}]}],
                    "items": [],
                }
            }
        )
    )
    monkeypatch.setattr(path, "get_path", lambda _: box)
    monkeypatch.setattr(mastery_recommendation, "get_skill_data", lambda: data)
    monkeypatch.setattr(
        mastery_db,
        "get_all_plans",
        lambda: [
            {
                "char_id": "char_test",
                "skill_index": 0,
                "target_level": target,
                "status": status,
                "support_runtime": json.dumps({"level": runtime_level}),
            }
        ],
    )
    monkeypatch.setattr(mastery_db, "get_failed_plans", lambda: [])
    result = plan_material_summary(["char_test_0", "char_test_0"])
    assert result["materials"][0]["required"] == expected


def test_low_materials_reserved_for_direct_needs_are_not_spent_twice():
    result = budget({"t3": 1, "t2": 5}, {"t2": 5})
    assert [(row["id"], row["count"]) for row in result["missing"]] == [("t3", 1)]


def test_lower_tiers_are_shown_when_they_can_complete_crafting():
    result = budget({"t3": 1}, {"t2": 4, "t1": 3})
    assert result["craftable"]
    assert [(r["id"], r["required"]) for r in result["crafting"]] == [
        ("t2", 4),
        ("t1", 3),
    ]


def test_chip_conversion_recipes_do_not_break_mastery_budgeting():
    recipes = lower_recipes()
    recipes["金材料"] = {"tab": "芯片", "costs": {"紫材料": 1}}
    recipes["紫材料"] = {"tab": "芯片", "costs": {"金材料": 1}}
    calculator = MaterialBudget(resources(), {"t3": 6}, recipes)
    assert calculator.calculate([{"id": "t5", "count": 1}])["craftable"]


def test_empty_plan_does_not_require_box_data():
    assert plan_material_summary([])["materials"] == []


def test_missing_skills_follow_plan_order_and_share_inventory():
    calculator = MaterialBudget(resources(), {"t3": 5, "t5": 1})
    entries = [
        ("first", [{"id": "t3", "count": 4}]),
        ("second", [{"id": "t3", "count": 4}]),
        ("stocked", [{"id": "t5", "count": 1}]),
    ]
    result = calculator.calculate_plan(entries)
    assert result["missing_skills"] == ["second"]
    assert result["missing"][0]["count"] == 3
    assert {row["id"] for row in result["materials"]} == {"t3", "t5"}
    assert calculator.calculate_plan([entries[1], entries[0], entries[2]])[
        "missing_skills"
    ] == ["first"]


def test_book_shortages_are_displayed_without_listing_skills():
    result = MaterialBudget(resources(), {}).calculate_plan(
        [("books_only", [{"id": "3303", "count": 2}])]
    )
    assert result["missing_skills"] == []
    assert not result["craftable"]
    assert [(row["id"], row["count"]) for row in result["missing"]] == [("3303", 2)]


def test_mixed_shortages_only_list_skills_lacking_elite_materials():
    result = MaterialBudget(resources(), {"t3": 3}).calculate_plan(
        [
            ("craftable", [{"id": "t4", "count": 1}]),
            ("books_only", [{"id": "3303", "count": 2}]),
            ("elite_missing", [{"id": "t4", "count": 1}]),
        ]
    )
    assert result["missing_skills"] == ["elite_missing"]
    assert {row["id"]: row["count"] for row in result["missing"]} == {
        "3303": 2,
        "t3": 3,
    }


@pytest.mark.parametrize(
    "stock,expected_missing,expected_spent",
    [
        ({"t2": 4, "t1": 3}, 2, {"t2": 4, "t1": 3}),
        ({"t2": 8, "t1": 3}, 2, {"t2": 5}),
        ({"t2": 10, "t1": 0}, 1, {"t2": 10}),
        ({"t2": 4, "t1": 2}, 3, {}),
    ],
)
def test_lower_tier_consumption_is_capped_and_remaining_shortage_stays_blue(
    stock, expected_missing, expected_spent
):
    result = budget({"t3": 3}, stock)
    assert [(row["id"], row["count"]) for row in result["missing"]] == [
        ("t3", expected_missing)
    ]
    spent = {row["id"]: row["required"] for row in result["crafting"]}
    assert spent == expected_spent
    assert all(count <= stock.get(item, 0) for item, count in spent.items())


def test_lower_tier_direct_and_crafting_consumption_are_both_displayed():
    result = budget({"t3": 1, "t2": 2}, {"t2": 7})
    assert result["craftable"]
    assert [(row["id"], row["required"]) for row in result["crafting"]] == [("t2", 7)]


def test_craftable_materials_are_distinguished_from_unrelated_missing_materials():
    result = budget({"t4": 1, "3303": 2}, {"t3": 3, "3302": 3})
    assert not result["craftable"]
    assert {row["id"]: row["craftable"] for row in result["materials"]} == {
        "t4": True,
        "3303": False,
    }


def test_lower_tier_crafting_marks_blue_and_high_materials_craftable():
    result = budget({"t5": 1}, {"t4": 1, "t3": 2, "t2": 5})
    assert result["craftable"]
    assert all(row["craftable"] for row in result["materials"] + result["crafting"])
    result = budget({"t5": 1}, {"t4": 1, "t3": 2, "t2": 4})
    assert not result["materials"][0]["craftable"]
    assert {row["id"]: row["craftable"] for row in result["crafting"]} == {
        "t4": False,
        "t3": False,
    }


def test_shared_ingredient_shortage_is_not_claimed_as_craftable_by_each_parent():
    data = resources()
    data["items"]["other_t4"] = {"name": "另一紫材料", "rarity": 4}
    data["composite"]["other_t4"] = {"pathway": [{"id": "t3", "count": 3}]}
    result = MaterialBudget(data, {"t3": 3}).calculate(
        [
            {"id": "t4", "count": 1},
            {"id": "other_t4", "count": 1},
        ]
    )
    assert all(not row["craftable"] for row in result["materials"])
    assert result["missing"][0]["count"] == 3
