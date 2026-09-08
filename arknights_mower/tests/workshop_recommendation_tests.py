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
    assert scopes["空爆"] == ["聚酸酯块"]
    assert result["defaults"]["t5_operators"] == ["年"]
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
                "t5_operators": {"年"},
                "book_operators": {"凯尔希"},
                "fodder_operators": {"空爆", "号角"},
            },
        ),
        (
            ["凯尔希", "空爆", "号角"],
            {
                "t5_operators": {"空爆"},
                "book_operators": {"凯尔希"},
                "fodder_operators": {"号角"},
            },
        ),
        (
            ["凯尔希"],
            {
                "t5_operators": {"凯尔希"},
                "book_operators": set(),
                "fodder_operators": set(),
            },
        ),
    ],
)
def test_automatic_categories_are_exclusive_and_use_remaining_operators(
    game, names, expected
):
    meta, ids = game
    result = workshop.recommend_workshop_operators(owned(ids, *names), meta)
    assert {key: set(value) for key, value in result["defaults"].items()} == expected
    flattened = [name for names in result["defaults"].values() for name in names]
    assert len(flattened) == len(set(flattened))
    for key, operators in result["recommendations"].items():
        assert {entry["name"] for entry in operators} == expected[key]


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
    assert set(result["defaults"]["fodder_operators"]) == {"九色鹿", "号角"}
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
    assert result[0]["items"] == [item("碳素"), item("炽合金块")]
    assert result[1]["items"] == [item("双极纳米片")]


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
