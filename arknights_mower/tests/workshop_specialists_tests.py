"""Workshop specialists regressions."""

from unittest.mock import patch

import pytest

from arknights_mower.tests.workshop_fixtures import (
    SPECIALISTS,
    item,
    owned,
    recipe,
)
from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.utils.workshop_selection import WorkshopSelection


@pytest.mark.parametrize(
    "name,elite,bonus,cost", [("缇缇", 1, 75, 8), ("休谟斯", 0, 50, 2)]
)
def test_material_scope_does_not_require_future_bonus_or_specialty(
    game, name, elite, bonus, cost
):
    from arknights_mower.data import workshop_formula

    meta, ids = game
    available = workshop.available_operators(owned(ids, name, elite=elite), meta)
    selection = WorkshopSelection(available, workshop_formula, min_bonus=bonus)
    entries = [entry for rows in selection.select().values() for entry in rows]
    assert len(entries) == 1
    entry = entries[0]
    assert set(entry["materials"]) == {
        material
        for material, formula in workshop_formula.items()
        if formula.get("tab") == "精英材料" and formula.get("apCost") == cost
    }
    assert set(entry["bonuses"].values()) == {bonus}
    assert not entry.get("specialist")


@pytest.mark.parametrize("name,elite,material,cost,bonus", SPECIALISTS)
def test_all_specialists_require_their_unlock_and_keep_matching_recipes(
    game, name, elite, material, cost, bonus
):
    meta, ids = game
    formulas = {material: recipe(cost), "无关材料": recipe(cost)}
    category = workshop.recipe_category(recipe(cost))
    for phase in [elite - 1, elite]:
        result = workshop.recommend_workshop_operators(
            owned(ids, name, elite=phase, level=1), meta, formulas
        )
        entries = [
            entry
            for entry in result["recommendations"][category]
            if entry["name"] == name
        ]
        assert result["defaults"][category] == ([name] if phase == elite else [])
        if bonus < 90:
            assert entries == []  # Special materials use the same curated 90% floor.
        else:
            assert entries == [
                {
                    "name": name,
                    # Humus matches original cost 2, regardless of material family.
                    "materials": sorted(formulas)
                    if name in {"休谟斯", "缇缇"}
                    else [material],
                    "bonuses": {n: bonus for n in formulas}
                    if name in {"休谟斯", "缇缇"}
                    else {material: bonus},
                    "causality": False,
                    "specialist": True,
                }
            ]


def test_humus_90_percent_requires_original_cost_two_elite_materials(game):
    meta, ids = game
    effects = workshop.available_operators(owned(ids, "休谟斯", elite=1), meta)[
        "休谟斯"
    ]
    assert workshop.recipe_bonus(effects, "糖", recipe(1)) == 50
    assert workshop.recipe_bonus(effects, "糖组", recipe(2)) == 90
    assert workshop.recipe_bonus(effects, "糖聚块", recipe(4)) == 50
    assert workshop.recipe_bonus(effects, "技巧概要·卷3", recipe(2, "技巧概要")) == 50
    assert workshop.recipe_bonus(effects, "碳素", recipe(2, "基建材料")) == 0
    result = workshop.recommend_workshop_operators(owned(ids, "休谟斯", elite=1), meta)
    assert result["defaults"]["t5_operators"] == []
    assert result["defaults"]["book_operators"] == []
    humus = next(
        entry
        for entry in result["recommendations"]["fodder_operators"]
        if entry["name"] == "休谟斯"
    )
    assert set(humus["materials"]) == {
        "全新装置",
        "酮凝集组",
        "异铁组",
        "聚酸酯组",
        "糖组",
        "固源岩组",
    }


def test_80_percent_specialist_is_added_in_all_matching_categories(
    game,
):
    meta, ids = game
    result = workshop.recommend_workshop_operators(owned(ids, "特克诺", "年"), meta)
    assert set(result["defaults"]["t5_operators"]) == {"年", "特克诺"}
    assert result["defaults"]["fodder_operators"] == ["特克诺"]
    available = workshop.available_operators(owned(ids, "特克诺", "年"), meta)
    result = workshop.allocate_workshop_items(
        [
            (
                "t5_operators",
                ["年", "特克诺"],
                [item("晶体电子单元"), item("双极纳米片")],
            )
        ],
        available=available,
    )
    assert result[1]["items"] == [item("晶体电子单元")]
    assert result[0]["items"] == [item("晶体电子单元"), item("双极纳米片")]


@pytest.mark.parametrize("missing_box", [False, True])
@pytest.mark.parametrize("name,elite,material,cost,bonus", SPECIALISTS)
def test_specialist_alone_never_gets_unrelated_materials_even_without_box(
    game, missing_box, name, elite, material, cost, bonus
):
    meta, ids = game
    available = workshop.available_operators(owned(ids, name), meta)
    category = workshop.recipe_category(recipe(cost))
    with patch.object(
        workshop,
        "available_operators",
        return_value=available,
        side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
        if missing_box
        else None,
    ):
        result = workshop.allocate_workshop_items(
            [(category, [name], [item(material), item("糖"), item("技巧概要·卷3")])]
        )
    assert result[0]["items"] == [item(material)]


def test_best_specialists_exclude_generalists_but_keep_same_material_specialists(game):
    meta, ids = game
    names = ["蜜莓", "熔泉", "折桠", "休谟斯", "维荻", "九色鹿"]
    result = workshop.allocate_workshop_items(
        [
            (
                "fodder_operators",
                names,
                [item("异铁组"), item("酮凝集组"), item("糖聚块")],
            )
        ],
        available=workshop.available_operators(owned(ids, *names), meta),
    )
    mapping = {
        entry["operator"]: {n for task in entry["items"] for n in task["item_names"]}
        for entry in result
    }
    assert {name for name, materials in mapping.items() if "异铁组" in materials} == {
        "熔泉",
        "折桠",
        "休谟斯",
    }
    assert {name for name, materials in mapping.items() if "酮凝集组" in materials} == {
        "休谟斯",
        "维荻",
    }
    assert mapping["蜜莓"] == {"糖聚块"}
    assert mapping["九色鹿"] == {"糖聚块"}
    assert [entry["operator"] for entry in result].index("休谟斯") < [
        entry["operator"] for entry in result
    ].index("维荻")


@pytest.mark.parametrize("with_nian", [True, False])
def test_specialist_reservation_never_overrides_a_higher_generic_bonus(game, with_nian):
    meta, ids = game
    names = ["蜜莓", "特克诺"] + (["年"] if with_nian else [])
    roster = owned(ids, *names)
    result = workshop.allocate_workshop_items(
        [("t5_operators", names, [item("晶体电子单元")])],
        available=workshop.available_operators(roster, meta),
    )
    if with_nian:
        assert result[0]["operator"] == "年"
        assert result[0]["items"] == [item("晶体电子单元")]
    else:
        assert [entry["operator"] for entry in result if entry["items"]] == ["特克诺"]
    recommended = workshop.recommend_workshop_operators(
        roster, meta, {"晶体电子单元": recipe(8), "糖聚块": recipe()}
    )
    assert "蜜莓" in recommended["defaults"]["fodder_operators"]
    if not with_nian:
        assert recommended["defaults"]["t5_operators"] == ["特克诺"]
