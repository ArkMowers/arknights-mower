"""Mastery assistant api regressions."""

import json
from unittest.mock import patch

import pytest
from flask import Flask

from arknights_mower.tests.mastery_support_fixtures import (
    context_game as context_game,
)
from arknights_mower.tests.mastery_support_fixtures import (
    database as database,
)
from arknights_mower.tests.mastery_support_fixtures import (
    game as game,
)
from arknights_mower.utils import mastery_db as db
from arknights_mower.utils import mastery_support as support
from arknights_mower.utils import mastery_support_data as support_data
from arknights_mower.views.mastery import mastery_bp


def test_route_api_personal_defaults_and_unowned_manual_choice(database, context_game):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    with patch("arknights_mower.views.mastery.config.conf") as conf:
        conf.webview.token = ""
        client = app.test_client()
        data = client.get("/mastery-route").json
        assert data["best_trainers"]["近卫"]["1"]["name"] == "赤冬"
        assert data["best_trainers"]["近卫"]["1"]["owned"] is False
        allowed = {"假日威龙陈", "艾丽妮", "逻各斯"}
        assert all(
            s["name"] in allowed and (not s["swap"] or s["swap_name"] in allowed)
            for route in data["defaults"].values()
            for s in route["supports"]
        )
        personal = data["defaults"]["狙击"]
        assert (
            client.post(
                "/mastery-route", json={"profession": "狙击", **personal}
            ).status_code
            == 200
        )
        saved = client.get("/mastery-route").json["routes"]
        assert json.loads(saved[0]["supports"]) == personal["supports"]
        manual = [{"name": "赤冬", "skill_level": 1, "efficiency": 75}]
        assert (
            client.post(
                "/mastery-route", json={"profession": "近卫", "supports": manual}
            ).status_code
            == 200
        )
        saved = client.get("/mastery-route").json["routes"]
        warrior = next(r for r in saved if r["profession"] == "近卫")
        assert json.loads(warrior["supports"]) == manual


def test_route_api_keeps_reference_without_roster(database, context_game):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support_data,
            "owned_roster",
            side_effect=support.RosterUnavailableError("请同步练度"),
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().get("/mastery-route")
    assert response.status_code == 200
    from arknights_mower.solvers.mastery import DEFAULT_ROUTES

    assert (
        response.json["defaults"]
        == support.legacy_profession_routes(DEFAULT_ROUTES)["defaults"]
    )
    assert len(response.json["defaults"]) == 8
    for profession, route in response.json["defaults"].items():
        assert [s["skill_level"] for s in route["supports"]] == [1, 2, 3]
        for row in route["supports"]:
            original = DEFAULT_ROUTES[profession][f"level_{row['skill_level']}"]
            assert row["name"] == original["operator"]
            assert row["efficiency"] == original["efficiency"]
            assert row["swap_name"] == (original["swap_target"] or "")
            assert row["match"] == original["job_match"]
    assert "原默认最佳路线" in response.json["defaults_error"]
    assert response.json["best_trainers"]["近卫"]["1"]["owned"] is None


def test_api_creates_atomic_plan_and_allows_unskilled_manual_choice(
    database, context_game
):
    _, ids = context_game
    with patch(
        "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
        return_value=0,
    ):
        pid, error = db.add_plan_checked(ids["能天使"], 0, 3, char_name="能天使")
    assert error is None
    plan = db.get_plan_by_id(pid)
    assert support.decode_supports(plan)["stages"]
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    stages = [
        {"level": s["level"], "operator": "芬", "swap_target": None}
        for s in support.decode_supports(plan)["stages"]
    ]
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support_data, "schedule_context", return_value=({"能天使": {"room_1_1"}}, 0)
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().patch(
            "/mastery-plan/supports", json={"id": pid, "stages": stages}
        )
    assert response.status_code == 200, response.json
    assert response.json["support_plan"]["stages"][0]["efficiency"] == 0
    with patch.object(
        support_data, "schedule_context", return_value=({"芬": {"dormitory_1"}}, 5)
    ):
        with pytest.raises(support.SupportPlanError, match="非训练室排班"):
            support.edit_supports(plan, stages)


def test_route_api_does_not_use_unowned_defaults_for_missing_rules(
    database, context_game
):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support, "training_data", side_effect=support.SupportPlanError("缺少规则")
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().get("/mastery-route")
    assert response.json["defaults"] == {}
    assert response.json["defaults_error"] == "缺少规则"
