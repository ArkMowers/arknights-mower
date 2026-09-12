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
    from arknights_mower.utils.mastery_recommendation import (
        compute_default_workshop_config,
    )

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
        result = compute_default_workshop_config(**defaults)
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
    from arknights_mower.utils.mastery_recommendation import (
        compute_default_workshop_config,
    )

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
        result = compute_default_workshop_config(["休谟斯"], [], [])
    assert any(entry["items"] for entry in result) is (reason == "scheduled")


@pytest.mark.parametrize("recipe_source", ["game", "legacy_composite"])
def test_plan_specialties_include_direct_and_indirect_t3_with_counts_and_stock(
    game, tmp_path, recipe_source
):
    from arknights_mower.utils import mastery_recommendation as rec

    meta, ids = game
    data = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())
    if recipe_source == "game":
        data["composite"] = {}
    else:
        data["workshop"].pop("recipe_ingredients")
        data["composite"] = {
            "30044": {
                "pathway": [
                    {"id": "30043", "count": 2},
                    {"id": "30063", "count": 1},
                    {"id": "30033", "count": 1},
                ]
            }
        }
    skill_path = tmp_path / "skill_data.json"
    skill_path.write_text(json.dumps(data))
    iron_id = next(i for i, v in data["items"].items() if v["name"] == "异铁块")
    path = tmp_path / "cultivate.json"
    stock = [{"id": iron_id, "count": 1}] + [
        {"id": key, "count": 300}
        for key, item in data["items"].items()
        if item.get("rarity") == 2
    ]
    path.write_text(json.dumps({"data": {"items": stock}}))
    recommendations = {
        "operators": [
            {
                "char_id": "char_test",
                "recommendations": [
                    {
                        "skill_index": 0,
                        "chain_needed_materials": [
                            {"name": "异铁块", "count": 4},
                            {"name": "异铁组", "count": 3},
                        ],
                    }
                ],
            }
        ]
    }
    with (
        patch(
            "arknights_mower.utils.mastery_db.get_all_plans",
            return_value=[{"char_id": "char_test", "skill_index": 0}],
        ),
        patch.object(rec, "get_path", return_value=path),
        patch.object(
            rec,
            "_find_skill_data",
            return_value=skill_path,
        ),
        patch.object(rec, "get_mastery_recommendations", return_value=recommendations),
        patch.object(
            workshop,
            "available_operators",
            return_value=workshop.available_operators(
                owned(ids, "折桠", "休谟斯"), meta
            ),
        ),
    ):
        result = rec.compute_workshop_config(["折桠", "休谟斯"], [], [])
    assert result[0]["items"] == [
        {"item_names": ["异铁组"], "children_lower_limit": 0, "self_upper_limit": 9}
    ]
    assert {
        task["item_names"][0]: task["self_upper_limit"] for task in result[1]["items"]
    } == {"异铁组": 9, "全新装置": 3, "聚酸酯组": 3}
