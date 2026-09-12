"""Mastery assistant creation regressions."""

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


def test_adding_scheduled_trainee_keeps_assistant_exclusions(database, context_game):
    _, ids = context_game
    with (
        patch.object(
            support_data,
            "schedule_context",
            return_value=(
                {"能天使": {"dormitory_1"}, "假日威龙陈": {"room_1_1"}},
                0,
            ),
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=0,
        ),
    ):
        pid, error = db.add_plan_checked(ids["能天使"], 0, 3, char_name="能天使")
    assert pid > 0 and error is None
    plan = db.get_plan_by_id(pid)
    assert plan["status"] == "idle"
    stages = support.decode_supports(plan)["stages"]
    assert len(stages) == 3
    assert all(s["operator"] not in {"能天使", "假日威龙陈"} for s in stages)


@pytest.mark.parametrize("legacy_payload", [False, True])
def test_plan_api_allows_scheduled_trainee(database, context_game, legacy_payload):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    payload = (
        {"能天使": 0}
        if legacy_payload
        else {"items": [{"name": "能天使", "skill_index": 0}]}
    )
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support_data, "schedule_context", return_value=({"能天使": {"room_1_1"}}, 0)
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=0,
        ),
    ):
        conf.webview.token = ""
        response = app.test_client().post("/mastery-plan", json=payload)
    assert response.status_code == 200
    result = response.json["results"][0]
    assert result["status"] == "added"
    assert support.decode_supports(db.get_plan_by_id(result["id"]))["stages"]


@pytest.mark.parametrize("legacy_payload", [False, True])
def test_no_box_plan_api_falls_back_to_route(database, legacy_payload):
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    payload = (
        {"能天使": 0}
        if legacy_payload
        else {"items": [{"name": "能天使", "skill_index": 0}]}
    )
    with (
        patch("arknights_mower.views.mastery.config.conf") as conf,
        patch.object(
            support_data,
            "owned_roster",
            side_effect=support.RosterUnavailableError("未同步"),
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=None,
        ),
        patch("arknights_mower.views.mastery._dispatch_new_plans_immediately"),
    ):
        conf.webview.token = ""
        response = app.test_client().post("/mastery-plan", json=payload)
    assert response.status_code == 200, response.json
    added = response.json["results"][0]
    assert added["support_mode"] == "route"
    assert "职业路线" in added["warning"]
    assert db.get_plan_by_id(added["id"])["support_plan"] is None


def test_explicit_manual_route_needs_no_training_resources(database):
    with (
        patch.object(support, "plan_supports") as calculate,
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=None,
        ),
    ):
        pid, error = db.add_plan_checked("char_103_angel", 0, support_mode="route")
    assert pid > 0 and error is None
    calculate.assert_not_called()
    assert db.get_plan_by_id(pid)["support_plan"] is None


def test_auto_validation_errors_are_not_downgraded_to_route(database):
    with (
        patch.object(
            support, "plan_supports", side_effect=support.SupportPlanError("排班冲突")
        ),
        patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=None,
        ),
    ):
        pid, error = db.add_plan_checked("char_103_angel", 0)
    assert pid == -1 and error == "排班冲突"
    assert db.get_all_plans() == []
    assert db.add_plan_checked("char_103_angel", 0, support_mode="invalid")[0] == -1
