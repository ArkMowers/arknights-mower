"""Workshop rules regressions."""

import pytest

from arknights_mower.tests.workshop_fixtures import (
    buff,
    item,
    recipe,
)
from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.utils.workshop_rules import (
    compile_workshop_buff,
    compile_workshop_data,
)


@pytest.mark.parametrize(
    "scope,match,miss",
    [
        ("装置类材料", "改量装置", "异铁块"),
        ("酮凝集类材料", "酮阵列", "改量装置"),
        ("源岩类材料", "提纯源岩", "聚酸酯块"),
        ("晶体类材料", "晶体电子单元", "双极纳米片"),
        ("异铁组材料", "异铁组", "异铁块"),
        ("炽合金块材料", "炽合金块", "炽合金"),
    ],
)
def test_material_scope_is_not_applied_to_whole_category(scope, match, miss):
    effects = compile_workshop_buff(
        buff(f"进驻加工站加工{scope}时，副产品的产出概率提升90%")
    )
    assert workshop.recipe_bonus(effects, match, recipe()) == 90
    assert workshop.recipe_bonus(effects, miss, recipe()) == 0


def test_original_cost_condition_and_dynamic_extra_are_not_assumed():
    effects = compile_workshop_buff(
        buff("进驻加工站加工原始心情消耗为8的任意类材料时，副产品的产出概率提升50%")
    )
    assert workshop.recipe_bonus(effects, "T5", recipe(8)) == 50
    assert workshop.recipe_bonus(effects, "T4", recipe(4)) == 0
    effects = compile_workshop_buff(
        buff(
            "进驻加工站加工任意类材料时，副产品的产出概率提升50%；如果白铁进驻在宿舍，则额外提升10%"
        )
    )
    assert workshop.recipe_bonus(effects, "T4", recipe()) == 50
    assert (
        compile_workshop_buff(
            buff(
                "进驻加工站加工精英材料时，宿舍内每有1名心情12以下的干员，副产品的产出概率提升5%"
            )
        )
        == []
    )


def test_empty_upgrade_replaces_previous_skill_and_level_gate_is_exact():
    chars = {"char_test": {"name": "测试"}}
    building = {
        "buffs": {
            "old": buff("进驻加工站加工任意类材料时，副产品的产出概率提升40%"),
            "new": {"roomType": "CONTROL", "description": "其他技能"},
        },
        "chars": {
            "char_test": {
                "buffChar": [
                    {
                        "buffData": [
                            {
                                "buffId": "old",
                                "cond": {"phase": "PHASE_0", "level": 30},
                            },
                            {"buffId": "new", "cond": {"phase": "PHASE_1", "level": 1}},
                        ]
                    }
                ]
            }
        },
    }
    meta = compile_workshop_data(chars, building)["operators"]
    for elite, level, expected in [(0, 29, []), (0, 30, ["测试"]), (1, 1, [])]:
        result = workshop.recommend_workshop_operators(
            [{"id": "char_test", "evolvePhase": elite, "level": level}],
            meta,
            {"T4": recipe()},
            min_bonus=40,
        )
        assert result["defaults"]["fodder_operators"] == expected


def test_resource_compiler_keeps_actual_ingredient_counts_for_elite_materials():
    building = {
        "buffs": {},
        "workshopFormulas": {
            "iron": {
                "formulaType": "F_EVOLVE",
                "itemId": "30044",
                "count": 1,
                "costs": [
                    {"id": "30043", "count": 2},
                    {"id": "30063", "count": 1},
                    {"id": "30033", "count": 1},
                ],
            },
            "furniture": {
                "formulaType": "F_FURNITURE",
                "itemId": "3401",
                "count": 12,
                "costs": [],
            },
        },
    }
    result = compile_workshop_data({}, building)
    assert result["recipe_ingredients"] == {
        "30044": {"30043": 2, "30063": 1, "30033": 1}
    }


def test_dorm_metadata_tracks_unlocks_without_adding_dorm_only_operators():
    def group(buff_id, elite=0, level=1):
        return {
            "buffData": [
                {"buffId": buff_id, "cond": {"phase": f"PHASE_{elite}", "level": level}}
            ]
        }

    chars = {
        "char_a": {"name": "A"},
        "char_z": {"name": "Z"},
        "char_dorm": {"name": "宿舍专员"},
    }
    building = {
        "buffs": {
            "workshop": buff("进驻加工站加工技巧概要时，副产品的产出概率提升80%"),
            "dorm": {"roomType": "DORMITORY", "description": "宿舍技能"},
        },
        "chars": {
            "char_a": {"buffChar": [group("workshop")]},
            "char_z": {"buffChar": [group("workshop"), group("dorm", 1, 30)]},
            "char_dorm": {"buffChar": [group("dorm")]},
        },
    }
    meta = compile_workshop_data(chars, building)["operators"]
    assert set(meta) == {"char_a", "char_z"}
    for elite, level, expected in [
        (0, 50, ["A", "Z"]),
        (1, 29, ["A", "Z"]),
        (1, 30, ["Z", "A"]),
        (2, 1, ["Z", "A"]),
    ]:
        roster = [{"id": cid, "evolvePhase": elite, "level": level} for cid in chars]
        result = workshop.recommend_workshop_operators(roster, meta)
        assert result["defaults"]["book_operators"] == expected
        assert [
            entry["name"] for entry in result["recommendations"]["book_operators"]
        ] == ["Z", "A"]  # Cultivation references use fully unlocked skills.
        configs = [
            {"operator": name, "items": [item("技巧概要·卷3")]} for name in ["A", "Z"]
        ]
        assert [
            entry["operator"]
            for entry in workshop.prioritize_workshop_settings(
                configs, available=workshop.available_operators(roster, meta)
            )
        ] == expected
