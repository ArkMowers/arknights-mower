"""Workshop allocation regressions."""

from unittest.mock import patch

import pytest

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.tests.workshop_fixtures import (
    item,
    owned,
)
from arknights_mower.utils import config
from arknights_mower.utils import workshop_recommendation as workshop


def test_allocator_matches_specific_recipes_and_merges_same_operator(game):
    meta, ids = game
    available = workshop.available_operators(owned(ids, "号角", "空爆"), meta)
    result = workshop.allocate_workshop_items(
        [
            (
                "fodder_operators",
                ["空爆", "号角"],
                [item("炽合金块"), item("聚酸酯块")],
            ),
            ("t5_operators", ["空爆"], [item("双极纳米片")]),
            ("book_operators", ["空爆"], [item("技巧概要·卷3")]),
        ],
        available=available,
    )
    assert len(result) == 2
    mapping = {entry["operator"]: entry["items"] for entry in result}
    assert mapping["号角"] == [item("炽合金块")]
    assert mapping["空爆"] == [
        item("聚酸酯块"),
        item("双极纳米片"),
        item("技巧概要·卷3"),
    ]


def test_fodder_is_only_added_to_deer_and_other_best_operators_remain(game):
    meta, ids = game
    result = workshop.allocate_workshop_items(
        [
            ("fodder_operators", ["九色鹿", "年"], [item("炽合金块")]),
            ("t5_operators", ["年"], [item("双极纳米片")]),
        ],
        fodder_items=[item("碳素")],
        available=workshop.available_operators(owned(ids, "九色鹿", "年"), meta),
    )
    mapping = {entry["operator"]: entry["items"] for entry in result}
    assert mapping["九色鹿"] == [item("碳素"), item("炽合金块")]
    assert mapping["年"] == [item("双极纳米片")]


@pytest.mark.parametrize("missing_rules", [False, True])
def test_old_lists_reserve_nian_for_t5_in_generated_config(game, missing_rules):
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.mastery_recommendation import (
        compute_default_workshop_config,
    )

    meta, ids = game
    available = workshop.available_operators(owned(ids, "年", "空爆", "赫拉格"), meta)
    with patch.object(
        workshop,
        "available_operators",
        return_value=available,
        side_effect=workshop.WorkshopRecommendationError("旧资源")
        if missing_rules
        else None,
    ):
        config = compute_default_workshop_config(
            ["年", "空爆"], ["年"], ["年", "赫拉格"]
        )
    materials = {
        entry["operator"]: {
            name for item in entry["items"] for name in item["item_names"]
        }
        for entry in config
    }
    assert "双极纳米片" in materials["年"]
    assert all(workshop_formula[name]["apCost"] >= 8 for name in materials["年"])
    assert "炽合金块" in materials["空爆"]
    assert "技巧概要·卷3" in materials["赫拉格"]


def test_default_config_merges_duplicate_operator_even_without_new_resources():
    from arknights_mower.utils.mastery_recommendation import (
        compute_default_workshop_config,
    )

    with patch.object(
        workshop,
        "available_operators",
        side_effect=workshop.WorkshopRecommendationError("旧资源"),
    ):
        result = compute_default_workshop_config(["凯尔希"], ["凯尔希"], ["凯尔希"])
    assert len(result) == 1
    materials = {name for entry in result[0]["items"] for name in entry["item_names"]}
    assert {"炽合金块", "双极纳米片", "技巧概要·卷3"} <= materials


@pytest.mark.parametrize("minimum", [50, 80])
def test_full_roster_config_orders_every_shared_recipe_by_bonus(game, minimum):
    from collections import defaultdict

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.mastery_recommendation import (
        compute_default_workshop_config,
    )

    meta, ids = game
    roster = owned(ids, *ids)
    available = workshop.available_operators(roster, meta)
    defaults = workshop.recommend_workshop_operators(roster, meta, min_bonus=minimum)[
        "defaults"
    ]
    with (
        patch.object(workshop, "available_operators", return_value=available),
        patch.object(config.conf, "workshop_min_bonus", minimum),
    ):
        result = compute_default_workshop_config(**defaults)
    recipe_bonuses = defaultdict(list)
    for entry in result:
        if entry["operator"] in {"九色鹿", "蚀清"}:
            continue  # Explicit T4 preferences override probability ordering.
        for task in entry["items"]:
            for material in task["item_names"]:
                recipe_bonuses[material].append(
                    workshop.recipe_bonus(
                        available[entry["operator"]],
                        material,
                        workshop_formula[material],
                    )
                )
    assert all(
        bonuses == sorted(bonuses, reverse=True) for bonuses in recipe_bonuses.values()
    )
