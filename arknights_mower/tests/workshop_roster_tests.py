"""Exercise real cached BOX reads through the workshop recommendation endpoint."""

import json

import pytest
from flask import Flask

from arknights_mower.tests.workshop_fixtures import (
    empty_schedule as empty_schedule,
)
from arknights_mower.tests.workshop_fixtures import (
    game as game,
)
from arknights_mower.tests.workshop_fixtures import owned
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.views.mastery import mastery_bp


@pytest.fixture
def roster_endpoint(tmp_path, monkeypatch):
    path = tmp_path / "cultivate.json"
    monkeypatch.setattr("arknights_mower.utils.path.get_path", lambda _: path)
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    return path, app.test_client()


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        None,
        {"data": None},
        {"data": []},
        {"data": {}},
        {"data": {"characters": []}},
        {"data": {"characters": {}}},
        {"data": {"characters": [None]}},
        {"data": {"characters": [{}]}},
        {"data": {"characters": [{"id": ""}]}},
        {"data": {"characters": [{"id": "char_2014_nian", "evolvePhase": None}]}},
        {"data": {"characters": [{"id": "char_2014_nian", "level": "90"}]}},
        {"code": 1, "data": {"characters": [{"id": "char_2014_nian"}]}},
    ],
)
def test_invalid_box_returns_actionable_error_instead_of_empty_defaults(
    roster_endpoint, payload
):
    path, client = roster_endpoint
    path.write_text(json.dumps(payload))
    response = client.get("/workshop-operators/recommendations")
    assert response.status_code == 400
    assert "同步干员数据" in response.json["error"]
    assert "defaults" not in response.json


def test_valid_box_without_eligible_workshop_operators_is_success(roster_endpoint):
    path, client = roster_endpoint
    path.write_text(json.dumps({"data": {"characters": [{"id": "char_002_amiya"}]}}))
    response = client.get("/workshop-operators/recommendations")
    assert response.status_code == 200
    assert response.json["defaults"] == {key: [] for key in workshop.CATEGORIES}


def test_invalid_refresh_does_not_reuse_cached_valid_candidates(roster_endpoint):
    path, client = roster_endpoint
    path.write_text(json.dumps({"data": {"characters": [{"id": "char_002_amiya"}]}}))
    assert client.get("/workshop-operators/recommendations").status_code == 200
    path.write_text(json.dumps({"data": {"characters": []}}))
    assert client.get("/workshop-operators/recommendations").status_code == 400


@pytest.mark.parametrize(
    "name,elite,bonus,category",
    [
        ("缇缇", 0, 75, "t5_operators"),
        ("缇缇", 1, 75, "t5_operators"),
        ("休谟斯", 0, 50, "fodder_operators"),
    ],
)
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_lower_threshold_uses_current_skill_before_specialty_unlock(
    roster_endpoint, game, name, elite, bonus, category, offset
):
    _, ids = game
    path, client = roster_endpoint
    path.write_text(
        json.dumps({"data": {"characters": owned(ids, name, elite=elite, level=1)}})
    )
    response = client.get(
        f"/workshop-operators/recommendations?min_bonus={bonus + offset}"
    )
    assert response.status_code == 200
    expected = {key: [] for key in workshop.CATEGORIES}
    if offset <= 0:
        expected[category] = [name]
    assert response.json["defaults"] == expected
