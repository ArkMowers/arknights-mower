"""Public survey data stays separate from player credentials and growth plans."""

import json
import sys
from unittest.mock import MagicMock

import pytest
import requests

from arknights_mower.utils import yituliu_statistics as survey


@pytest.fixture
def public_survey(tmp_path, monkeypatch):
    path = tmp_path / "yituliu_statistics.json"
    monkeypatch.setattr(survey, "get_path", lambda _: path)
    monkeypatch.setattr(survey, "time", lambda: 1_000_000)
    session = MagicMock()
    session.__enter__.return_value = session
    response = MagicMock(status_code=200, content=b"public data")
    response.__enter__.return_value = response
    session.get.return_value = response
    monkeypatch.setattr(survey.requests, "Session", lambda: session)
    rows = [
        {
            "charId": "char_example",
            "own": 80,
            "sampleSize": 100,
            "elite": {"0": 10, "1": 20, "2": 50},
            "skill1": {"0": 20, "1": 10, "2": 20, "3": 30},
            "modX": {"0": 60, "3": 20},
        }
    ]
    response.json.return_value = {"code": 200, "data": rows}
    return path, session, response, rows


def test_public_fetch_has_no_identity_and_cache_strips_unknown_fields(public_survey):
    path, session, response, rows = public_survey
    rows[0]["unexpected"] = {"token": "untrusted response value"}
    result = survey.get_statistics()
    session.get.assert_called_once_with(
        survey.SOURCE_URL, timeout=(3, 8), allow_redirects=False
    )
    assert session.trust_env is False
    assert result["fetched_at"] == 1_000_000
    assert result["stale"] is False and result["error"] is None
    assert "unexpected" not in result["operators"][0]
    assert json.loads(path.read_text())["operators"] == result["operators"]
    assert survey.get_statistics() == result
    assert session.get.call_count == 1


def test_expired_cache_is_replaced_only_by_valid_fresh_aggregates(public_survey):
    path, session, response, rows = public_survey
    path.write_text(
        json.dumps({"operators": rows, "fetched_at": 1_000_000 - survey.CACHE_TTL})
    )
    response.json.return_value["data"] = [{**rows[0], "sampleSize": 120}]
    result = survey.get_statistics()
    assert result["operators"][0]["sampleSize"] == 120
    assert result["stale"] is False
    assert json.loads(path.read_text())["fetched_at"] == 1_000_000


def test_timeout_preserves_old_disk_cache_and_reports_staleness(public_survey):
    path, session, response, rows = public_survey
    old = json.dumps({"operators": rows, "fetched_at": 1})
    path.write_text(old)
    session.get.side_effect = requests.Timeout("timeout")
    result = survey.get_statistics()
    assert result["operators"] == rows
    assert result["fetched_at"] == 1 and result["stale"] is True
    assert result["error"]
    assert path.read_text() == old


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"code": 500},
        {"code": 200, "data": []},
        {"code": 200, "data": [{"charId": "invalid"}]},
    ],
)
def test_invalid_public_data_cannot_replace_valid_cache(public_survey, bad):
    path, session, response, rows = public_survey
    old = json.dumps({"operators": rows, "fetched_at": 1})
    path.write_text(old)
    response.json.return_value = bad
    result = survey.get_statistics()
    assert result["stale"] is True and result["error"]
    assert result["operators"] == rows
    assert path.read_text() == old


@pytest.mark.parametrize(
    "change",
    [
        {"own": True},
        {"own": 101},
        {"sampleSize": 0},
        {"skill1": {"3": 81}},
        {"elite": {"3": 10}},
        {"modX": {"1": -1}},
    ],
)
def test_invalid_counts_do_not_become_survey_rates(public_survey, change):
    _, _, _, rows = public_survey
    rows[0].update(change)
    result = survey.get_statistics()
    assert result["operators"] == []
    assert result["fetched_at"] is None and result["stale"] is True
    assert result["error"]


def test_corrupt_cache_and_unavailable_source_return_no_invented_statistics(
    public_survey,
):
    path, session, _, _ = public_survey
    path.write_text("broken json")
    session.get.side_effect = requests.ConnectionError("offline")
    result = survey.get_statistics()
    assert result["operators"] == [] and result["error"]
    assert path.read_text() == "broken json"


def test_cache_write_failure_keeps_valid_response_and_reports_error(
    public_survey, monkeypatch
):
    _, _, _, rows = public_survey
    monkeypatch.setattr(
        survey, "atomic_write", MagicMock(side_effect=OSError("read only"))
    )
    result = survey.get_statistics()
    assert result["operators"] == rows and result["stale"] is False
    assert "缓存保存失败" in result["error"]


def test_survey_route_uses_local_auth_without_forwarding_local_request(
    public_survey, monkeypatch
):
    sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())
    import server

    monkeypatch.setattr(server.app, "token", "local-only", raising=False)
    fetch = MagicMock(return_value={"operators": [], "stale": True})
    monkeypatch.setattr(survey, "get_statistics", fetch)
    client = server.app.test_client()
    assert client.get("/growth-survey").status_code == 403
    fetch.assert_not_called()
    response = client.get(
        "/growth-survey?uid=must-not-forward", headers={"token": "local-only"}
    )
    assert response.status_code == 200 and response.json == fetch.return_value
    fetch.assert_called_once_with()
    assert (
        client.post("/growth-survey", headers={"token": "local-only"}).status_code
        == 405
    )


def test_zero_sample_operator_is_returned_without_fabricated_distribution(
    public_survey,
):
    _, _, response, _ = public_survey
    response.json.return_value = {
        "code": 200,
        "data": [{"charId": "char_new", "own": 0, "sampleSize": 0, "elite": {"0": 0}}],
    }
    result = survey.get_statistics()
    assert result["stale"] is False
    assert result["operators"][0]["sampleSize"] == 0
