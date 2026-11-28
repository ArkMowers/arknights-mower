"""Cultivation references are independent of BOX, schedules and task allocation."""

from unittest.mock import patch

import pytest
from flask import Flask

from arknights_mower.tests.workshop_fixtures import recipe
from arknights_mower.utils import workshop_recommendation as workshop
from arknights_mower.views.mastery import mastery_bp


@pytest.mark.parametrize("box", [None, "{}", '{"data":{"characters":[]}}'])
def test_reference_endpoint_works_without_valid_box_and_never_supplies_defaults(
    tmp_path, box
):
    path = tmp_path / "cultivate.json"
    if box is not None:
        path.write_text(box)
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    app.token = "test"
    client = app.test_client()
    assert client.get("/workshop-operators/reference").status_code == 403
    with patch("arknights_mower.utils.path.get_path", return_value=path):
        response = client.get(
            "/workshop-operators/reference", headers={"token": "test"}
        )
    assert response.status_code == 200
    assert set(response.json) == {"recommendations"}
    assert response.json["recommendations"]["fodder_operators"][0]["name"] == "九色鹿"
    assert path.read_text() == box if box is not None else not path.exists()


def test_reference_endpoint_reports_missing_rules():
    app = Flask(__name__)
    app.register_blueprint(mastery_bp)
    with patch.object(
        workshop,
        "workshop_reference",
        side_effect=workshop.WorkshopRecommendationError("请更新资源包"),
    ):
        response = app.test_client().get("/workshop-operators/reference")
    assert response.status_code == 400
    assert response.json == {"error": "请更新资源包"}


def reference_operator(name, bonus, *, family=None):
    effect = {"kind": "byproduct", "categories": ["material", "book"], "bonus": bonus}
    if family:
        effect["family"] = family
    return {"name": name, "groups": [[{"elite": 2, "level": 1, "effects": [effect]}]]}


def test_reference_does_not_hide_operators_by_category_assignment_or_specialists():
    meta = {
        "char_general": reference_operator("泛用干员", 90),
        "char_special": reference_operator("糖类干员", 100, family="糖"),
    }
    formulas = {
        "糖聚块": recipe(),
        "聚合剂": recipe(8),
        "技巧概要·卷3": recipe(2, "技巧概要"),
    }
    result = workshop.workshop_reference(meta, formulas)
    assert all("泛用干员" in {e["name"] for e in rows} for rows in result.values())
    assert {e["name"] for e in result["fodder_operators"]} == {"糖类干员", "泛用干员"}
    assert all(e["materials"] == ["糖聚块"] for e in result["fodder_operators"])
