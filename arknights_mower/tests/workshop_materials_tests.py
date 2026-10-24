"""Workshop materials regressions."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from arknights_mower.tests.workshop_fixtures import (
    SPECIALISTS,
    owned,
)
from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.utils import workshop_recommendation as workshop


def test_defaults_generate_low_tier_specialties_without_giving_them_to_generalists(
    game,
):
    from arknights_mower.tests.workshop_fixtures import allocate_sample_recipes

    meta, ids = game
    names = [row[0] for row in SPECIALISTS]
    roster = owned(ids, *names, "年", "空爆", "九色鹿")
    defaults = workshop.recommend_workshop_operators(roster, meta)["defaults"]
    flattened = [name for group in defaults.values() for name in group]
    assert set(names) <= set(flattened)
    assert all(flattened.count(name) == 1 for name in names if name != "特克诺")
    assert flattened.count("特克诺") == 2
    with patch.object(
        workshop,
        "available_operators",
        return_value=workshop.available_operators(roster, meta),
    ):
        result = allocate_sample_recipes(**defaults)
    materials = {
        entry["operator"]: {n for task in entry["items"] for n in task["item_names"]}
        for entry in result
    }
    assert materials["折桠"] == {"异铁组"}
    assert materials["维荻"] == {"酮凝集", "酮凝集组", "酮阵列"}
    assert materials["休谟斯"] == {
        "全新装置",
        "酮凝集组",
        "异铁组",
        "聚酸酯组",
        "糖组",
        "固源岩组",
    }
    assert materials["特克诺"] == {"晶体电子单元", "晶体电路"}
    assert "异铁组" not in materials["九色鹿"] | materials["空爆"]


@pytest.mark.parametrize("reason", ["unowned", "locked", "scheduled", "missing_box"])
def test_supplemental_low_tier_tasks_require_an_available_unlocked_specialist(
    game, reason
):
    from arknights_mower.tests.workshop_fixtures import allocate_sample_recipes

    meta, ids = game
    roster = (
        []
        if reason == "unowned"
        else owned(ids, "休谟斯", elite=0 if reason == "locked" else 1)
    )
    with (
        patch.object(
            workshop,
            "available_operators",
            return_value=workshop.available_operators(roster, meta),
            side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
            if reason == "missing_box"
            else None,
        ),
        patch.object(
            workshop,
            "scheduled_operators",
            return_value={"休谟斯": ["train"]} if reason == "scheduled" else {},
        ),
    ):
        result = allocate_sample_recipes(["休谟斯"], [], [])
    assert any(entry["items"] for entry in result) is (reason == "scheduled")


@pytest.mark.parametrize("recipe_source", ["game", "legacy_composite"])
def test_plan_specialties_include_direct_and_indirect_t3_with_counts_and_stock(
    game, recipe_source
):
    from collections import Counter

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils.growth_workshop import next_recipe
    from arknights_mower.utils.workshop_limits import batch_delta

    data = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())
    if recipe_source == "game":
        data["composite"] = {}
    ids = {v["name"]: key for key, v in data["items"].items()}
    stock = Counter(
        {key: 300 for key, item in data["items"].items() if item.get("rarity") == 2}
    )
    stock[ids["异铁块"]] = 1
    entries = [
        (
            "project",
            [{"id": ids["异铁块"], "count": 4}, {"id": ids["异铁组"], "count": 3}],
        )
    ]
    crafted = Counter()
    for _ in range(12):
        focus, settings = next_recipe(entries, data, stock, workshop_formula)
        if focus is None:
            break
        assert settings
        setting = settings[0]
        name = setting["item_names"][0]
        output = workshop_formula[name]["output_count"]
        batches = (setting["self_upper_limit"] - stock[ids[name]]) // output
        for material, count in batch_delta(
            name, workshop_formula[name], batches
        ).items():
            if material in ids:
                stock[ids[material]] += count
        crafted[name] += batches
    assert focus is None
    assert crafted == {"异铁组": 9, "全新装置": 3, "聚酸酯组": 3, "异铁块": 3}
    assert stock[ids["异铁块"]] == 4 and stock[ids["异铁组"]] == 3
