"""Owned workshop defaults, recipe-specific bonuses and merged configurations."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Flask

from arknights_mower.utils import config
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.utils.config.plan import PlanModel
from arknights_mower.utils.workshop_rules import (
    compile_workshop_buff,
    compile_workshop_data,
)
from arknights_mower.views.mastery import mastery_bp


@pytest.fixture(autouse=True)
def empty_schedule(monkeypatch):
    monkeypatch.setattr(config, "plan", PlanModel(), raising=False)


def buff(text):
    return {"roomType": "WORKSHOP", "description": text}


@pytest.fixture
def game():
    meta = json.loads((Path(__file__).parents[1] / "data/skill_data.json").read_text())[
        "workshop"
    ]["operators"]
    return meta, {entry["name"]: cid for cid, entry in meta.items()}


def owned(ids, *names, elite=2, level=90):
    return [{"id": ids[name], "evolvePhase": elite, "level": level} for name in names]


def recipe(cost=4, tab="精英材料"):
    return {"apCost": cost, "tab": tab}


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


def test_owned_unlocked_pool_keeps_all_ties_and_material_specialists(game):
    meta, ids = game
    roster = owned(ids, "年", "空爆", "苏苏洛", "号角", "赫拉格")
    result = workshop.recommend_workshop_operators(
        roster,
        meta,
        {
            "炽合金块": recipe(),
            "聚酸酯块": recipe(),
            "双极纳米片": recipe(8),
            "技巧概要·卷3": recipe(2, "技巧概要"),
        },
    )
    assert set(result["defaults"]["fodder_operators"]) == {"号角", "空爆", "苏苏洛"}
    scopes = {
        entry["name"]: entry["materials"]
        for entry in result["recommendations"]["fodder_operators"]
    }
    assert scopes["号角"] == ["炽合金块"]
    assert (
        "空爆" not in scopes
    )  # 80% remains selectable but is not a material recommendation.
    assert set(result["defaults"]["t5_operators"]) == {"年", "空爆", "苏苏洛"}
    assert result["defaults"]["book_operators"] == ["赫拉格"]
    assert result["nine_colored_deer"]["owned"] is False
    locked = workshop.recommend_workshop_operators(
        owned(ids, "空爆", "苏苏洛", "号角", elite=0), meta
    )
    assert all(not names for names in locked["defaults"].values())


def test_deer_keeps_fodder_priority_and_manual_reference_when_unowned(game):
    meta, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, "九色鹿", "年", elite=0), meta
    )
    assert result["defaults"]["fodder_operators"] == ["九色鹿"]
    assert result["defaults"]["t5_operators"] == ["年"]
    assert result["nine_colored_deer"] == {
        "name": "九色鹿",
        "owned": True,
    }
    missing = workshop.recommend_workshop_operators(owned(ids, "年"), meta)
    assert missing["defaults"]["fodder_operators"] == []
    assert missing["defaults"]["t5_operators"] == ["年"]
    assert missing["nine_colored_deer"] == {
        "name": "九色鹿",
        "owned": False,
    }


@pytest.mark.parametrize(
    "names,expected",
    [
        (
            ["年", "凯尔希", "空爆", "号角"],
            {
                "t5_operators": {"年", "空爆"},
                "book_operators": set(),
                "fodder_operators": {"空爆", "号角"},
            },
        ),
        (
            ["凯尔希", "空爆", "号角"],
            {
                "t5_operators": {"空爆"},
                "book_operators": set(),
                "fodder_operators": {"号角", "空爆"},
            },
        ),
        (
            ["凯尔希"],
            {
                "t5_operators": set(),
                "book_operators": set(),
                "fodder_operators": set(),
            },
        ),
    ],
)
def test_ordinary_80_percent_operators_can_fill_multiple_categories(
    game, names, expected
):
    meta, ids = game
    result = workshop.recommend_workshop_operators(owned(ids, *names), meta)
    assert {key: set(value) for key, value in result["defaults"].items()} == expected
    for key, operators in result["recommendations"].items():
        assert {entry["name"] for entry in operators} == expected[key] - {"空爆"}


def test_nian_is_not_used_for_non_t5_when_no_t5_recipe_is_requested(game):
    meta, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, "年"), meta, {"炽合金块": recipe()}
    )
    assert all(not names for names in result["defaults"].values())


def test_book_upgrade_does_not_stack_or_select_locked_trainer(game):
    meta, ids = game
    result = workshop.recommend_workshop_operators(
        owned(ids, "炎客", "司霆惊蛰", "赫拉格", elite=0), meta
    )
    assert result["defaults"]["book_operators"] == ["赫拉格"]
    result = workshop.recommend_workshop_operators(
        owned(ids, "炎客", "司霆惊蛰", "赫拉格"), meta
    )
    assert set(result["defaults"]["book_operators"]) == {"炎客", "司霆惊蛰", "赫拉格"}
    assert all(
        set(entry["bonuses"].values()) == {80}
        for entry in result["recommendations"]["book_operators"]
    )


def item(name):
    return {"item_names": [name], "children_lower_limit": 7, "self_upper_limit": 12}


def facility(name, replacement=()):
    return {"plans": [{"agent": name, "replacement": list(replacement)}]}


@pytest.mark.parametrize("backup", [False, True])
@pytest.mark.parametrize("replacement", [False, True])
@pytest.mark.parametrize(
    "room",
    ["central", "meeting", "contact", "train", "gaming_1", "room_1_1", "room_2_2"],
)
def test_all_other_facilities_block_primary_and_replacement_staff(
    backup, replacement, room
):
    slot = facility("Free", ["年"]) if replacement else facility("年", ["Current"])
    plan = (
        {"backup_plans": [{"plan": {room: slot}}]}
        if backup
        else {"plan1": {room: slot}}
    )
    assert workshop.scheduled_operators(PlanModel.model_validate(plan)) == {
        "年": [room]
    }


@pytest.mark.parametrize(
    "room", ["factory", "dormitory_1", "dormitory_2", "dormitory_3", "dormitory_4"]
)
def test_dorms_and_workshop_are_allowed_in_both_plans(room):
    plan = {
        "plan1": {room: facility("年", ["号角"])},
        "backup_plans": [{"plan": {room: facility("九色鹿", ["空爆"])}}],
    }
    assert workshop.scheduled_operators(PlanModel.model_validate(plan)) == {}
    plan["backup_plans"].append({"plan": {"central": facility("年")}})
    assert workshop.scheduled_operators(plan) == {"年": ["central"]}


def test_recommendation_uses_best_unscheduled_operator_and_deer_only_needs_ownership(
    game,
):
    meta, ids = game
    roster = owned(ids, "九色鹿", elite=0, level=1) + owned(ids, "年", "空爆", "号角")
    # Ownership is enough even when no unlocked probability rule is listed for deer.
    meta[ids["九色鹿"]]["groups"] = []
    plan = {
        "plan1": {"dormitory_1": facility("年", ["九色鹿"])},
        "backup_plans": [{"plan": {"central": facility("Free", ["年"])}}],
    }
    result = workshop.recommend_workshop_operators(roster, meta, plan=plan)
    assert set(result["defaults"]["fodder_operators"]) == {"九色鹿", "号角", "空爆"}
    assert result["defaults"]["t5_operators"] == ["空爆"]
    plan["backup_plans"][0]["plan"]["train"] = facility("九色鹿")
    result = workshop.recommend_workshop_operators(roster, meta, plan=plan)
    assert "九色鹿" not in result["defaults"]["fodder_operators"]
    assert result["nine_colored_deer"]["owned"] is True


def test_auto_config_rechecks_schedule_and_applies_filter_without_box(
    game, monkeypatch
):
    meta, ids = game
    available = workshop.available_operators(owned(ids, "号角", "空爆"), meta)
    groups = [("fodder_operators", ["号角", "空爆"], [item("炽合金块")])]
    before = workshop.allocate_workshop_items(groups, available=available)
    assert before[0]["items"] == [item("炽合金块")]
    monkeypatch.setattr(
        config,
        "plan",
        PlanModel.model_validate(
            {"backup_plans": [{"plan": {"meeting": facility("号角")}}]}
        ),
    )
    after = workshop.allocate_workshop_items(groups, available=available)
    assert after == [{"operator": "空爆", "enabled": True, "items": [item("炽合金块")]}]
    with patch.object(
        workshop,
        "available_operators",
        side_effect=workshop.WorkshopRecommendationError("缺少 BOX"),
    ):
        assert workshop.allocate_workshop_items(groups) == after


def test_blocked_deer_receives_no_material_or_fodder():
    result = workshop.allocate_workshop_items(
        [("fodder_operators", ["九色鹿"], [item("炽合金块")])],
        available={},
        fodder_items=[item("碳素")],
        plan={"plan1": {"train": facility("九色鹿")}},
    )
    assert result == []


def test_box_cache_reads_updates_and_reports_missing_data(tmp_path):
    path = tmp_path / "cultivate.json"
    with patch("arknights_mower.utils.path.get_path", return_value=path):
        with pytest.raises(workshop.WorkshopRecommendationError, match="同步干员数据"):
            workshop.owned_roster()
        path.write_text(json.dumps({"data": {"characters": [{"id": "first"}]}}))
        assert workshop.owned_roster() == [{"id": "first"}]
        assert workshop.owned_roster() == [{"id": "first"}]
        path.write_text(
            json.dumps({"data": {"characters": [{"id": "updated-operator"}]}})
        )
        assert workshop.owned_roster() == [{"id": "updated-operator"}]
        path.write_text("invalid json")
        with pytest.raises(workshop.WorkshopRecommendationError, match="同步干员数据"):
            workshop.owned_roster()


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


def test_endpoint_is_read_only_and_reports_missing_box_or_resource():
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    app.token = "test"
    client = app.test_client()
    assert client.get("/workshop-operators/recommendations").status_code == 403
    with patch.object(
        workshop,
        "recommend_workshop_operators",
        side_effect=workshop.WorkshopRecommendationError("请同步干员数据"),
    ):
        response = client.get(
            "/workshop-operators/recommendations", headers={"token": "test"}
        )
    assert response.status_code == 400
    assert response.json == {"error": "请同步干员数据"}
    with patch.object(workshop, "available_operators", return_value={}):
        response = client.get(
            "/workshop-operators/recommendations", headers={"token": "test"}
        )
    assert response.status_code == 200
    assert response.json["defaults"] == {key: [] for key in workshop.CATEGORIES}


SPECIALISTS = [
    ("贾维", 2, "改量装置", 4, 90),
    ("奥斯塔", 2, "聚酸酯块", 4, 90),
    ("泥岩", 2, "提纯源岩", 4, 90),
    ("熔泉", 2, "异铁块", 4, 90),
    ("号角", 2, "炽合金块", 4, 100),
    ("维荻", 1, "酮阵列", 4, 80),
    ("特克诺", 2, "晶体电子单元", 8, 80),
    ("折桠", 2, "异铁组", 2, 90),
    ("谬因", 2, "提纯源岩", 4, 90),
    ("休谟斯", 1, "糖组", 2, 90),
    ("缇缇", 2, "双极纳米片", 8, 80),
]


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
        entries = result["recommendations"][category]
        assert result["defaults"][category] == ([name] if phase == elite else [])
        if phase < elite:
            assert entries == []
        elif bonus < 90:
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
    assert set(result["recommendations"]["fodder_operators"][0]["materials"]) == {
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
    assert not any(entry["items"] for entry in result)


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
    path.write_text(json.dumps({"data": {"items": [{"id": iron_id, "count": 1}]}}))
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


@pytest.mark.parametrize(
    "minimum,expected",
    [
        (80, {"年", "号角", "空爆", "凯尔希·思衡托", "缇缇", "休谟斯"}),
        (90, {"年", "号角", "休谟斯"}),
        (100, {"年", "号角"}),
        (101, set()),
    ],
)
def test_one_click_threshold_keeps_all_qualifying_operators(game, minimum, expected):
    meta, ids = game
    roster = owned(ids, "年", "号角", "空爆", "凯尔希·思衡托", "缇缇", "休谟斯")
    result = workshop.recommend_workshop_operators(roster, meta, min_bonus=minimum)
    assert set().union(*map(set, result["defaults"].values())) == expected
    assert result["min_bonus"] == minimum
    if minimum == 80:
        assert all("凯尔希·思衡托" in names for names in result["defaults"].values())
        assert "缇缇" in result["defaults"]["t5_operators"]
        assert "缇缇" not in result["defaults"]["fodder_operators"]
        effects = workshop.available_operators(roster, meta)["缇缇"]
        assert workshop.recipe_bonus(effects, "双极纳米片", recipe(8)) == 80
        assert {
            "kind": "cost_reduction",
            "categories": ["material"],
            "original_cost": 8,
            "reduction": 4,
        } in effects


def test_threshold_is_saved_with_config_and_validated_by_endpoint(game):
    from pydantic import ValidationError

    from arknights_mower.utils.config.conf import RIICPart

    assert RIICPart().workshop_min_bonus == 80
    stored = RIICPart(workshop_min_bonus=90).model_dump_json()
    assert RIICPart.model_validate_json(stored).workshop_min_bonus == 90
    with pytest.raises(ValidationError):
        RIICPart(workshop_min_bonus=-1)
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    client = app.test_client()
    with patch.object(workshop, "available_operators", return_value={}):
        for value in ["-1", "1001", "nan", "80.5", "abc"]:
            assert (
                client.get(
                    f"/workshop-operators/recommendations?min_bonus={value}"
                ).status_code
                == 400
            )
        response = client.get("/workshop-operators/recommendations?min_bonus=90")
    assert response.status_code == 200
    assert response.json["min_bonus"] == 90


def test_highest_bonus_precedes_honeyberry_then_titi_in_t5(game):
    meta, ids = game
    roster = owned(ids, "空爆", "缇缇", "蜜莓", "年", "号角")
    recommendations = workshop.recommend_workshop_operators(roster, meta)
    assert recommendations["defaults"]["t5_operators"] == ["年", "蜜莓", "缇缇", "空爆"]
    assert recommendations["defaults"]["fodder_operators"] == ["号角", "蜜莓", "空爆"]
    result = workshop.allocate_workshop_items(
        [("t5_operators", ["空爆", "缇缇", "蜜莓", "年"], [item("双极纳米片")])],
        available=workshop.available_operators(roster, meta),
    )
    assert [entry["operator"] for entry in result] == ["年", "蜜莓", "缇缇", "空爆"]
    # Titi's mood savings do not make ordinary T5 recipes exclusive to her.
    assert all(entry["items"] == [item("双极纳米片")] for entry in result)


def test_unlocked_80_percent_is_required_for_honeyberry_preference(game):
    meta, ids = game
    roster = owned(ids, "蜜莓", elite=0) + owned(ids, "空爆", "缇缇")
    result = workshop.allocate_workshop_items(
        [("t5_operators", ["蜜莓", "空爆", "缇缇"], [item("双极纳米片")])],
        available=workshop.available_operators(roster, meta),
        min_bonus=75,
    )
    assert [entry["operator"] for entry in result] == ["缇缇", "空爆", "蜜莓"]


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


@pytest.mark.parametrize("nian_mood", [24, 20])
def test_scheduler_prioritizes_existing_configs_and_respects_existing_mood_gate(
    game, nian_mood
):
    from types import SimpleNamespace

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import scheduler_task
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    meta, ids = game
    names = ["空爆", "缇缇", "蜜莓", "年"]
    settings = [
        RIICPart.WorkShopSetting(
            operator=name, items=[WorkShopItem(**item("双极纳米片"))]
        )
        for name in names
    ]
    available = workshop.available_operators(owned(ids, *names), meta)
    operators = {
        name: SimpleNamespace(mood=nian_mood if name == "年" else 24) for name in names
    }
    inventory = {
        "双极纳米片": 0,
        **{name: 100 for name in workshop_formula["双极纳米片"]["items"]},
    }
    tasks = []
    with (
        patch.object(config.conf, "workshop_settings", settings),
        patch.object(scheduler_task, "get_inventory_counts", return_value=inventory),
        patch.object(workshop, "available_operators", return_value=available),
    ):
        scheduler_task.try_workshop_tasks(SimpleNamespace(operators=operators), tasks)
    assert [task.meta_data for task in tasks] == (["年"] if nian_mood > 22 else []) + [
        "蜜莓",
        "缇缇",
        "空爆",
    ]
    assert [entry.operator for entry in settings] == names
    assert all(
        (later.time - earlier.time).total_seconds() >= 2
        for earlier, later in zip(tasks, tasks[1:])
    )


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
        ] == expected
        configs = [
            {"operator": name, "items": [item("技巧概要·卷3")]} for name in ["A", "Z"]
        ]
        assert [
            entry["operator"]
            for entry in workshop.prioritize_workshop_settings(
                configs, available=workshop.available_operators(roster, meta)
            )
        ] == expected


def test_all_unlocked_dorm_skills_win_ties_but_not_larger_bonuses(game):
    meta, ids = game
    names = ["司霆惊蛰", "炎客", "子月", "赫拉格", "蜜莓", "空爆", "年"]
    available = workshop.available_operators(owned(ids, *names), meta)
    result = workshop.recommend_workshop_operators(owned(ids, *names), meta)
    assert set(result["defaults"]["book_operators"][:2]) == {"子月", "赫拉格"}
    assert result["defaults"]["t5_operators"] == ["年", "蜜莓", "空爆"]
    assert all(
        {"kind": "dormitory"} in available[name] for name in ["子月", "赫拉格", "蜜莓"]
    )
    assert {"kind": "dormitory"} not in workshop.available_operators(
        owned(ids, "蜜莓", elite=1), meta
    )["蜜莓"]


@pytest.mark.parametrize("minimum", [50, 80, 95])
def test_curated_recommendations_have_independent_material_and_book_floors(
    game, minimum
):
    meta, ids = game
    names = [
        "九色鹿",
        "蚀清",
        "莱伊",
        "空爆",
        "蜜莓",
        "缇缇",
        "年",
        "号角",
        "熔泉",
        "休谟斯",
        "维荻",
        "特克诺",
        "子月",
        "赫拉格",
    ]
    result = workshop.recommend_workshop_operators(
        owned(ids, *names), meta, min_bonus=minimum
    )
    recommended = {
        key: [entry["name"] for entry in entries]
        for key, entries in result["recommendations"].items()
    }
    assert recommended["fodder_operators"] == [
        "九色鹿",
        "蚀清",
        "号角",
        "休谟斯",
        "熔泉",
    ]
    assert recommended["t5_operators"] == ["年"]
    assert set(recommended["book_operators"]) == {"子月", "赫拉格"}
    sesa = result["recommendations"]["fodder_operators"][1]
    assert sesa["material_scope"] == "t4"
    assert set(sesa["bonuses"].values()) == {80}
    for category, entries in result["recommendations"].items():
        for entry in entries:
            if entry["name"] not in {"九色鹿", "蚀清"}:
                assert min(entry["bonuses"].values()) >= (
                    80 if category == "book_operators" else 90
                )
    if minimum <= 80:
        assert "莱伊" in result["defaults"]["t5_operators"]
        assert "蜜莓" in result["defaults"]["fodder_operators"]
    else:
        assert (
            "蚀清" not in result["defaults"]["fodder_operators"]
        )  # One-click honors its configured floor.


def test_curated_exceptions_still_require_ownership_unlock_and_schedule(game):
    meta, ids = game
    locked = workshop.recommend_workshop_operators(owned(ids, "蚀清", elite=1), meta)
    assert locked["recommendations"]["fodder_operators"] == []
    blocked = workshop.recommend_workshop_operators(
        owned(ids, "九色鹿", "蚀清"),
        meta,
        plan={"backup_plans": [{"plan": {"central": facility("蚀清", ["九色鹿"])}}]},
    )
    assert all(not entries for entries in blocked["recommendations"].values())
    assert all(not entries for entries in blocked["defaults"].values())


@pytest.mark.parametrize("missing_box", [False, True])
def test_t4_scopes_apply_to_old_category_lists_and_keep_deer_building_fodder(
    game, missing_box
):
    meta, ids = game
    names = ["莱伊", "蚀清", "九色鹿"]
    formulas = {
        "糖组": recipe(2),
        "糖聚块": recipe(),
        "双极纳米片": recipe(8),
        "技巧概要·卷3": recipe(2, "技巧概要"),
        "碳素": recipe(2, "基建材料"),
    }
    groups = [
        ("fodder_operators", names, [item("糖组"), item("糖聚块")]),
        ("t5_operators", names, [item("双极纳米片")]),
        ("book_operators", names, [item("技巧概要·卷3")]),
    ]
    with patch.object(
        workshop,
        "available_operators",
        return_value=workshop.available_operators(owned(ids, *names), meta),
        side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
        if missing_box
        else None,
    ):
        result = workshop.allocate_workshop_items(
            groups, formulas=formulas, fodder_items=[item("碳素")]
        )
    assert [entry["operator"] for entry in result] == ["九色鹿", "蚀清", "莱伊"]
    scopes = {
        entry["operator"]: {
            material for task in entry["items"] for material in task["item_names"]
        }
        for entry in result
    }
    assert scopes == {
        "九色鹿": {"糖聚块", "碳素"},
        "蚀清": {"糖聚块"},
        "莱伊": {"糖组", "双极纳米片", "技巧概要·卷3"},
    }


def test_t4_preferences_precede_specialists_without_broadening_other_generalists(game):
    meta, ids = game
    names = ["蜜莓", "号角", "蚀清", "九色鹿"]
    result = workshop.recommend_workshop_operators(
        owned(ids, *names), meta, {"炽合金块": recipe()}
    )
    assert result["defaults"]["fodder_operators"] == ["九色鹿", "蚀清", "号角"]
    allocated = workshop.allocate_workshop_items(
        [("fodder_operators", names, [item("炽合金块")])],
        available=workshop.available_operators(owned(ids, *names), meta),
        min_bonus=90,
    )
    assert [entry["operator"] for entry in allocated if entry["items"]] == [
        "九色鹿",
        "蚀清",
        "号角",
    ]


@pytest.mark.parametrize("missing_box", [False, True])
def test_saved_runtime_configs_are_scoped_before_dispatch_without_mutating_them(
    game, missing_box
):
    from types import SimpleNamespace

    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import scheduler_task
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    meta, ids = game
    # Stock makes only a forbidden recipe available for each operator.
    names = ["莱伊", "蚀清", "九色鹿"]
    settings = [
        RIICPart.WorkShopSetting(
            operator=name,
            items=[WorkShopItem(**item("糖聚块" if name == "莱伊" else "双极纳米片"))],
        )
        for name in names
    ]
    snapshot = [entry.model_dump() for entry in settings]
    inventory = {
        name: 100 for recipe in workshop_formula.values() for name in recipe["items"]
    }
    inventory.update({"糖聚块": 0, "双极纳米片": 0})
    tasks = []
    with (
        patch.object(config.conf, "workshop_settings", settings),
        patch.object(scheduler_task, "get_inventory_counts", return_value=inventory),
        patch.object(
            workshop,
            "available_operators",
            return_value=workshop.available_operators(owned(ids, *names), meta),
            side_effect=workshop.WorkshopRecommendationError("缺少 BOX")
            if missing_box
            else None,
        ),
    ):
        scheduler_task.try_workshop_tasks(
            SimpleNamespace(
                operators={name: SimpleNamespace(mood=24) for name in names}
            ),
            tasks,
        )
    assert tasks == []
    assert [entry.model_dump() for entry in settings] == snapshot


def test_mixed_saved_recipe_rows_keep_limits_and_only_remove_forbidden_materials():
    original = [{**item("糖聚块"), "item_names": ["糖聚块", "糖组", "双极纳米片"]}]
    result = workshop.scope_workshop_items("蚀清", original)
    assert result == [item("糖聚块")]
    assert original[0]["item_names"] == ["糖聚块", "糖组", "双极纳米片"]
