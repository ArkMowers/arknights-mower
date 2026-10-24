"""Growth overview omits material graphs; selected details preserve full costs."""

import json

import pytest

from arknights_mower.utils import growth
from arknights_mower.utils import mastery_recommendation as mr


@pytest.fixture
def roster(tmp_path, monkeypatch, income_db):
    from pathlib import Path

    skills = json.loads(
        (Path(mr.__file__).parents[1] / "data/skill_data.json").read_text("utf-8")
    )
    chars = [
        {
            "id": cid,
            "evolvePhase": 0,
            "level": 1,
            "mainSkillLevel": 1,
            "skills": [],
            "equips": [],
        }
        for cid in skills["growth"]["characters"]
    ]
    path = tmp_path / "cultivate.json"
    path.write_text(json.dumps({"data": {"characters": chars, "items": []}}))
    monkeypatch.setattr(mr, "get_path", lambda _: path)
    monkeypatch.setattr(mr, "get_skill_data", lambda: skills)
    monkeypatch.setattr(growth, "load_goals", lambda: [])
    monkeypatch.setattr(growth, "statistics_history", lambda: [])
    return chars


def test_overview_has_all_operators_without_calculating_material_graphs(
    roster, monkeypatch
):
    def forbidden(*_):
        pytest.fail("overview calculates material graph")

    monkeypatch.setattr(growth, "calculate_growth_materials", forbidden)
    result = mr.get_mastery_recommendations(include_materials=False)
    assert result["has_data"]
    assert len(result["operators"]) >= 400
    assert len(json.dumps(result, ensure_ascii=False).encode()) < 1024 * 1024
    operator = next(op for op in result["operators"] if op["name"] == "能天使")
    assert [rec["skill_index"] for rec in operator["recommendations"]] == [0, 1, 2]
    assert all(rec["current_level"] == 0 for rec in operator["recommendations"])
    assert operator["modules"]
    assert "materials" not in operator["modules"][0]
    assert operator["max_phase"] == 2
    assert result["personal_statistics"]


def test_selected_details_match_legacy_full_response_and_preserve_manual_costs(roster):
    legacy = mr.get_mastery_recommendations()
    assert {"goals", "statistics", "personal_statistics", "history"} <= legacy.keys()
    expected = next(op for op in legacy["operators"] if op["name"] == "能天使")
    detail = mr.get_mastery_recommendations(char_id=expected["char_id"])
    assert detail["operators"] == [expected]
    assert expected["recommendations"][0]["targets"]["3"]["material_summary"][
        "materials"
    ]
    assert expected["level_goals"][0]["summary"]["materials"]
    assert expected["modules"][0]["targets"]["1"]["opening_summary"]["materials"]
    assert mr.get_mastery_recommendations(char_id="missing")["operators"] == []


@pytest.mark.parametrize("include_materials", [False, True])
def test_selected_details_skip_account_statistics_and_history(
    roster, monkeypatch, include_materials
):
    from arknights_mower.utils import growth_value, operator_statistics

    def forbidden(*_):
        pytest.fail("operator details load account statistics or history")

    for module, name in (
        (growth, "load_goals"),
        (growth, "statistics"),
        (growth, "statistics_history"),
        (growth_value, "price_catalog"),
        (operator_statistics, "personal_statistics"),
    ):
        monkeypatch.setattr(module, name, forbidden)
    char_id = roster[0]["id"]
    result = mr.get_mastery_recommendations(
        char_id=char_id, include_materials=include_materials
    )
    assert result.keys() == {"operators", "has_data", "error"}
    assert result["has_data"] and result["error"] is None
    assert [op["char_id"] for op in result["operators"]] == [char_id]


def test_http_overview_and_detail_keep_json_routing(roster, monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "growth-session", raising=False)
    client = server.app.test_client()
    headers = {"token": "growth-session"}
    overview = client.get(
        "/mastery-recommendation?materials=0", headers=headers
    ).get_json()
    assert {"goals", "statistics", "personal_statistics", "history"} <= overview.keys()
    op = overview["operators"][0]
    assert "targets" not in op["recommendations"][0]
    detail = client.get(
        "/mastery-recommendation",
        query_string={"char_id": op["char_id"]},
        headers=headers,
    ).get_json()
    assert len(detail["operators"]) == 1
    assert detail["operators"][0]["recommendations"][0]["targets"]["3"][
        "material_summary"
    ]


@pytest.mark.parametrize("method", ["get", "head"])
@pytest.mark.parametrize("token", [None, "invalid", "growth-session"])
@pytest.mark.parametrize("query", [{}, {"materials": "0"}, {"char_id": "operator"}])
def test_http_recommendation_token_precedes_account_reads(
    monkeypatch, method, token, query
):
    import server

    calls = []

    def recommendations(**kwargs):
        calls.append(kwargs)
        return {"operators": [], "has_data": True, "error": None}

    monkeypatch.setattr(server.app, "token", "growth-session", raising=False)
    monkeypatch.setattr(mr, "get_mastery_recommendations", recommendations)
    headers = {"Accept": "application/json, text/plain, */*"}
    if token is not None:
        headers["token"] = token
    response = getattr(server.app.test_client(), method)(
        "/mastery-recommendation", query_string=query, headers=headers
    )
    if token == "growth-session":
        assert response.status_code == 200
        assert calls == [
            {
                "include_materials": query.get("materials") != "0",
                "char_id": query.get("char_id"),
            }
        ]
    else:
        assert response.status_code == 403
        assert calls == []


@pytest.mark.parametrize("method", ["get", "head"])
def test_http_recommendation_page_navigation_remains_public(
    monkeypatch, tmp_path, method
):
    import server

    def forbidden(**_):
        pytest.fail("page navigation reads account data")

    html = "<html><body>Growth page</body></html>"
    (tmp_path / "index.html").write_text(html, encoding="utf-8")
    monkeypatch.setattr(server.app, "static_folder", str(tmp_path))
    monkeypatch.setattr(server.app, "token", "growth-session", raising=False)
    monkeypatch.setattr(mr, "get_mastery_recommendations", forbidden)
    response = getattr(server.app.test_client(), method)(
        "/mastery-recommendation",
        headers={"Accept": "text/html", "Sec-Fetch-Dest": "document"},
    )
    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert response.data == (html.encode() if method == "get" else b"")
    assert {"Accept", "Sec-Fetch-Dest"} <= set(response.vary)
    response.close()


def test_parallel_detail_reads_preserve_operator_identity_and_resource_data(
    roster, monkeypatch
):
    from concurrent.futures import ThreadPoolExecutor

    import server

    monkeypatch.setattr(server.app, "token", "growth-session", raising=False)
    skills = mr.get_skill_data()
    before = json.dumps(skills, sort_keys=True)
    ids = [row["id"] for row in roster[:4]]

    def read(cid):
        with server.app.test_client() as client:
            return client.get(
                "/mastery-recommendation",
                query_string={"char_id": cid},
                headers={"token": "growth-session"},
            ).get_json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, ids))
    for cid, result in zip(ids, results):
        assert [op["char_id"] for op in result["operators"]] == [cid]
    assert json.dumps(skills, sort_keys=True) == before
