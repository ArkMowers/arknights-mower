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
    expected = next(op for op in legacy["operators"] if op["name"] == "能天使")
    detail = mr.get_mastery_recommendations(char_id=expected["char_id"])
    assert detail["operators"] == [expected]
    assert expected["recommendations"][0]["targets"]["3"]["material_summary"][
        "materials"
    ]
    assert expected["level_goals"][0]["summary"]["materials"]
    assert expected["modules"][0]["targets"]["1"]["opening_summary"]["materials"]
    assert mr.get_mastery_recommendations(char_id="missing")["operators"] == []


def test_http_overview_and_detail_keep_json_routing(roster):
    import server

    client = server.app.test_client()
    overview = client.get("/mastery-recommendation?materials=0").get_json()
    op = overview["operators"][0]
    assert "targets" not in op["recommendations"][0]
    detail = client.get(
        "/mastery-recommendation", query_string={"char_id": op["char_id"]}
    ).get_json()
    assert len(detail["operators"]) == 1
    assert detail["operators"][0]["recommendations"][0]["targets"]["3"][
        "material_summary"
    ]


def test_parallel_detail_reads_preserve_operator_identity_and_resource_data(roster):
    from concurrent.futures import ThreadPoolExecutor

    import server

    skills = mr.get_skill_data()
    before = json.dumps(skills, sort_keys=True)
    ids = [row["id"] for row in roster[:4]]

    def read(cid):
        with server.app.test_client() as client:
            return client.get(
                "/mastery-recommendation", query_string={"char_id": cid}
            ).get_json()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(read, ids))
    for cid, result in zip(ids, results):
        assert [op["char_id"] for op in result["operators"]] == [cid]
    assert json.dumps(skills, sort_keys=True) == before
