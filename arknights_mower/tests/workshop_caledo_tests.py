"""Caledo joins T4 automatic crafting immediately after Corroserum."""

import pytest

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    facility,
    item,
    owned,
    recipe,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.utils import workshop_recommendation as workshop


@pytest.mark.parametrize("minimum", [80, 95, 1000])
def test_caledo_defaults_and_references_follow_corroserum(game, minimum):
    meta, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, "镜匠", "蚀清", "九色鹿", "号角"),
        meta,
        {"炽合金块": recipe(), "糖组": recipe(2), "双极纳米片": recipe(8)},
        min_bonus=minimum,
    )
    assert result["defaults"]["fodder_operators"][:3] == ["九色鹿", "蚀清", "镜匠"]
    assert "镜匠" not in result["defaults"]["t5_operators"]
    mirror = next(
        op
        for op in result["recommendations"]["fodder_operators"]
        if op["name"] == "镜匠"
    )
    assert mirror["material_scope"] == "t4"
    assert mirror["materials"] == ["炽合金块"]
    assert mirror["bonuses"] == {"炽合金块": 80}
    if minimum <= 80:
        assert result["defaults"]["fodder_operators"] == [
            "九色鹿",
            "蚀清",
            "镜匠",
            "号角",
        ]


def test_caledo_requires_owned_unlocked_and_unscheduled_skills(game):
    meta, ids = game
    for roster, plan in [
        ([], {}),
        (owned(ids, "镜匠", elite=1), {}),
        (owned(ids, "镜匠"), {"plan1": {"central": facility("镜匠")}}),
    ]:
        result = workshop.recommend_workshop_operators(
            roster, meta, min_bonus=80, plan=plan
        )
        assert "镜匠" not in result["defaults"]["fodder_operators"]
    effects = workshop.available_operators(owned(ids, "镜匠", elite=1), meta)["镜匠"]
    assert workshop.recipe_bonus(effects, "炽合金块", recipe()) == 75


def test_caledo_execution_copies_keep_priority_and_t4_scope(game):
    meta, ids = game
    names = ["号角", "镜匠", "蚀清", "九色鹿"]
    available = workshop.available_operators(owned(ids, *names), meta)
    settings = [
        {
            "operator": name,
            "items": [item("炽合金块"), item("双极纳米片"), item("糖组")],
        }
        for name in names
    ]
    result = workshop.prioritize_workshop_settings(
        settings,
        available=available,
        formulas={"炽合金块": recipe(), "双极纳米片": recipe(8), "糖组": recipe(2)},
    )
    assert [entry["operator"] for entry in result] == ["九色鹿", "蚀清", "镜匠", "号角"]
    assert result[2]["items"] == [item("炽合金块")]
    assert settings[1]["items"] == [item("炽合金块"), item("双极纳米片"), item("糖组")]
    allocated = workshop.allocate_workshop_items(
        [("fodder_operators", names, [item("炽合金块")])],
        available=available,
        formulas={"炽合金块": recipe()},
        min_bonus=90,
    )
    assert [entry["operator"] for entry in allocated] == [
        "九色鹿",
        "蚀清",
        "镜匠",
        "号角",
    ]
