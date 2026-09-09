"""Workshop recommendation regressions."""

import json
from unittest.mock import patch

import pytest
from flask import Flask

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.tests.workshop_fixtures import (
    owned,
    recipe,
)
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.views.mastery import mastery_bp


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
    assert result["recommendations"] == workshop.workshop_reference(meta)


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


@pytest.mark.parametrize(
    "minimum,expected",
    [
        (80, {"年", "号角", "空爆", "凯尔希·思衡托", "缇缇", "休谟斯"}),
        (90, {"年", "号角", "休谟斯", "凯尔希·思衡托"}),
        (100, {"年", "号角", "凯尔希·思衡托"}),
        (101, {"凯尔希·思衡托"}),
    ],
)
def test_one_click_threshold_keeps_all_qualifying_operators(game, minimum, expected):
    meta, ids = game
    roster = owned(ids, "年", "号角", "空爆", "凯尔希·思衡托", "缇缇", "休谟斯")
    result = workshop.recommend_workshop_operators(roster, meta, min_bonus=minimum)
    assert set().union(*map(set, result["defaults"].values())) == expected
    assert result["min_bonus"] == minimum
    if minimum > 80:
        assert result["defaults"]["book_operators"] == ["凯尔希·思衡托"]
        assert all(
            "凯尔希·思衡托" not in result["defaults"][category]
            for category in ("fodder_operators", "t5_operators")
        )
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
