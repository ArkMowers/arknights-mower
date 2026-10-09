"""Homebound keeps her T5 specialty without displacing higher-bonus workers."""

from copy import deepcopy
from unittest.mock import patch

import pytest

from arknights_mower.data import workshop_formula
from arknights_mower.tests.workshop_fixtures import (
    buff,
    item,
    owned,
)
from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.utils.workshop_allocation import scope_setting
from arknights_mower.utils.workshop_rules import (
    compile_workshop_buff,
    compile_workshop_data,
)

TRAVELER = "旅骨"
T4 = "手性屈光体"
T5 = "重相位对映体"
SKILL = (
    "进驻加工站加工<@cc.kw>手性屈光体</>或<@cc.kw>重相位对映体</>时，"
    "副产物的产出概率提升<@cc.vup>90%</>"
)


@pytest.fixture
def traveler_game(game):
    meta, ids = game
    cid = "char_4232_hbound"
    metadata = compile_workshop_data(
        {cid: {"name": TRAVELER}},
        {
            "buffs": {"workshop_formula_device[080]": buff(SKILL)},
            "chars": {
                cid: {
                    "buffChar": [
                        {
                            "buffData": [
                                {
                                    "buffId": "workshop_formula_device[080]",
                                    "cond": {"phase": "PHASE_2", "level": 1},
                                }
                            ]
                        }
                    ]
                }
            },
        },
    )
    return {**meta, **metadata["operators"]}, {**ids, TRAVELER: cid}


@pytest.mark.parametrize("word", ["副产物", "副产品"])
def test_game_description_compiles_two_exact_material_rules(word):
    effects = compile_workshop_buff(buff(SKILL.replace("副产物", word)))
    assert effects == [
        {"kind": "byproduct", "categories": ["material"], "bonus": 90, "item": name}
        for name in (T4, T5)
    ]
    assert workshop.recipe_bonus(effects, T4, workshop_formula[T4]) == 90
    assert workshop.recipe_bonus(effects, T5, workshop_formula[T5]) == 90
    assert (
        workshop.recipe_bonus(effects, "双极纳米片", workshop_formula["双极纳米片"])
        == 0
    )


def test_legacy_combined_item_rule_matches_each_material():
    effects = [
        {
            "kind": "byproduct",
            "categories": ["material"],
            "bonus": 90,
            "item": f"{T4}或{T5}",
        }
    ]
    assert workshop.recipe_bonus(effects, T5, workshop_formula[T5]) == 90
    assert (
        workshop.recipe_bonus(effects, "双极纳米片", workshop_formula["双极纳米片"])
        == 0
    )


@pytest.mark.parametrize("elite", [0, 1, 2])
def test_resource_traveler_requires_elite_two_and_is_only_recommended_for_t5(
    traveler_game, elite
):
    meta, ids = traveler_game
    assert ids[TRAVELER] == "char_4232_hbound"
    result = workshop.recommend_workshop_operators(
        owned(ids, TRAVELER, elite=elite, level=1), meta
    )
    assert result["defaults"] == {
        "fodder_operators": [],
        "t5_operators": [TRAVELER] if elite == 2 else [],
        "book_operators": [],
    }
    assert not any(
        entry["name"] == TRAVELER
        for entry in result["recommendations"]["fodder_operators"]
    )
    entry = next(
        entry
        for entry in result["recommendations"]["t5_operators"]
        if entry["name"] == TRAVELER
    )
    assert entry["materials"] == [T5]
    assert entry["bonuses"] == {T5: 90}


@pytest.mark.parametrize("with_nian", [False, True])
def test_nian_keeps_higher_bonus_priority_and_traveler_keeps_t5_scope(
    traveler_game, with_nian
):
    meta, ids = traveler_game
    names = [TRAVELER, "蜜莓"] + (["年"] if with_nian else [])
    available = workshop.available_operators(owned(ids, *names), meta)
    formulas = {name: workshop_formula[name] for name in (T4, T5, "双极纳米片")}
    recommended = workshop.recommend_workshop_operators(
        owned(ids, *names), meta, formulas
    )
    assert recommended["defaults"]["t5_operators"] == (
        ["年", TRAVELER, "蜜莓"] if with_nian else [TRAVELER, "蜜莓"]
    )
    result = workshop.allocate_workshop_items(
        [("t5_operators", names, [item(name) for name in formulas])],
        available=available,
        formulas=formulas,
    )
    mapping = {
        entry["operator"]: {
            name for task in entry["items"] for name in task["item_names"]
        }
        for entry in result
    }
    assert mapping[TRAVELER] == {T5}
    assert (T5 in mapping["蜜莓"]) is with_nian
    if with_nian:
        assert result[0]["operator"] == "年"
        assert T5 in mapping["年"]
        assert workshop.recipe_bonus(available["年"], T5, formulas[T5]) > 90
    else:
        assert result[0]["operator"] == TRAVELER


@pytest.mark.parametrize("missing_box", [False, True])
def test_missing_box_allocation_preserves_traveler_specialty(
    traveler_game, missing_box
):
    meta, ids = traveler_game
    available = workshop.available_operators(owned(ids, TRAVELER), meta)
    with patch.object(
        workshop,
        "available_operators",
        return_value=available,
        side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
        if missing_box
        else None,
    ):
        result = workshop.allocate_workshop_items(
            [("t5_operators", [TRAVELER], [item(T4), item(T5), item("双极纳米片")])]
        )
    assert result[0]["items"] == [item(T5)]


@pytest.mark.parametrize("model", [False, True])
def test_saved_manual_items_drop_t4_without_mutating_original(model):
    from arknights_mower.utils.config.conf import RIICPart

    original = {"operator": TRAVELER, "items": [item(T4), item(T5)]}
    if model:
        original = RIICPart.WorkShopSetting(**original)
    before = deepcopy(original)
    scoped = scope_setting(original, workshop_formula)
    ordered = workshop.prioritize_workshop_settings([original], available={})[0]
    for result in (scoped, ordered):
        data = result.model_dump() if model else result
        assert [entry["item_names"] for entry in data["items"]] == [[T5]]
    assert original == before
