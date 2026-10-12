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
    monkeypatch.setattr(survey, "get_path", lambda _, space=None: path)
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
        {"skill1": {"10": 81}},
        {"skill1": {"256": 80}},
        {"skill1": {"01": 80}},
        {"skill1": {"10": True}},
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


def test_mixed_skill_scales_preserve_other_public_metrics(public_survey):
    """Reduced public response observed on 2026-10-12, without player data."""
    path, session, response, _ = public_survey
    response.json.return_value = {
        "code": 200,
        "data": [
            {
                "charId": "char_002_amiya",
                "own": 119052,
                "sampleSize": 119052,
                "elite": {"0": 941, "1": 2446, "2": 115665},
                "skill1": {
                    "0": 114135,
                    "1": 1458,
                    "2": 840,
                    "3": 2612,
                    "7": 6,
                    "10": 1,
                },
                "modY": {"0": 99460, "1": 7274, "2": 2634, "3": 9684},
            }
        ],
    }
    result = survey.get_statistics()
    assert result["error"] is None and not result["stale"]
    operator = result["operators"][0]
    assert "skill1" not in operator  # Mixed scales cannot supply a known mastery rate.
    assert operator["elite"]["2"] == 115665
    assert operator["modY"]["3"] == 9684
    assert json.loads(path.read_text())["operators"] == [operator]
    assert survey.get_statistics() == result
    session.get.assert_called_once()


def test_failure_cooldown_survives_repeated_reads_and_allows_later_recovery(
    public_survey, monkeypatch
):
    path, session, _, rows = public_survey
    path.write_text(json.dumps({"operators": rows, "fetched_at": 1}))
    session.get.side_effect = requests.Timeout("must not expose remote details")
    first = survey.get_statistics()
    assert "超时" in first["error"]
    assert first["retry_after"] == 1_000_300
    assert survey.get_statistics() == first
    session.get.assert_called_once()
    monkeypatch.setattr(survey, "time", lambda: 1_000_299)
    assert survey.get_statistics()["retry_after"] == first["retry_after"]
    session.get.assert_called_once()
    session.get.side_effect = None
    monkeypatch.setattr(survey, "time", lambda: 1_000_300)
    recovered = survey.get_statistics()
    assert recovered["error"] is None and not recovered["stale"]
    assert session.get.call_count == 2


def test_rate_limit_is_distinct_and_does_not_expose_response_body(public_survey):
    _, session, _, _ = public_survey
    session.get.side_effect = requests.HTTPError(
        "remote secret body", response=MagicMock(status_code=429)
    )
    result = survey.get_statistics()
    assert "限流" in result["error"]
    assert "remote secret" not in result["error"]
    assert survey.get_statistics() == result
    session.get.assert_called_once()


@pytest.mark.parametrize("shared_timestamp", [None, 1])
def test_valid_instance_cache_is_promoted_without_remote_fetch(
    public_survey, tmp_path, monkeypatch, shared_timestamp
):
    _, session, _, rows = public_survey
    shared = tmp_path / "shared.json"
    legacy = tmp_path / "instance.json"
    legacy.write_text(json.dumps({"operators": rows, "fetched_at": 999_999}))
    if shared_timestamp:
        shared.write_text(
            json.dumps({"operators": rows, "fetched_at": shared_timestamp})
        )
    monkeypatch.setattr(
        survey, "get_path", lambda _, space=None: shared if space == "" else legacy
    )
    result = survey.get_statistics()
    assert result["fetched_at"] == 999_999 and not result["stale"]
    assert json.loads(shared.read_text())["fetched_at"] == 999_999
    assert legacy.exists()
    session.get.assert_not_called()


def test_shared_cache_is_reused_by_distinct_configuration_spaces(
    public_survey, tmp_path, monkeypatch
):
    shared, session, _, _ = public_survey
    for instance in ("one", "two"):
        legacy = tmp_path / instance / "yituliu_statistics.json"
        monkeypatch.setattr(
            survey, "get_path", lambda _, space=None: shared if space == "" else legacy
        )
        result = survey.get_statistics()
        assert not result["stale"]
    session.get.assert_called_once()


def test_lock_contention_has_finite_wait_and_preserves_stale_cache(
    public_survey, monkeypatch
):
    path, session, _, rows = public_survey
    path.write_text(json.dumps({"operators": rows, "fetched_at": 1}))
    ticks = iter([0, 1, survey.LOCK_WAIT_TIMEOUT])
    monkeypatch.setattr(survey, "monotonic", lambda: next(ticks))
    wait = MagicMock()
    monkeypatch.setattr(survey, "sleep", wait)
    monkeypatch.setattr(
        survey, "submission_lock", MagicMock(side_effect=survey.LockBusyError("busy"))
    )
    result = survey.get_statistics()
    assert "其他实例" in result["error"]
    assert result["operators"] == rows and result["stale"]
    wait.assert_called_once_with(0.1)
    session.get.assert_not_called()


def test_coordination_failure_never_starts_unlocked_remote_request(
    public_survey, monkeypatch
):
    _, session, _, _ = public_survey
    monkeypatch.setattr(
        survey, "submission_lock", MagicMock(side_effect=PermissionError())
    )
    result = survey.get_statistics()
    assert "权限" in result["error"]
    session.get.assert_not_called()


def test_invalid_cooldown_record_cannot_break_loading(public_survey):
    path, session, _, _ = public_survey
    directory = path.parent / "yituliu_statistics"
    directory.mkdir()
    (directory / "retry.json").write_text(
        json.dumps({"retry_after": 1_000_001, "reason": []})
    )
    assert survey.get_statistics()["error"] is None
    session.get.assert_called_once()


def _statistics_process(root, instance, counter, ready, release, output, fail):
    """Use real process/file locks while keeping all provider traffic mocked."""
    from pathlib import Path

    survey.get_path = lambda _, space=None: (
        Path(root) / ("shared" if space == "" else instance) / "yituliu_statistics.json"
    )
    survey.time = lambda: 1_000_000
    session = MagicMock()
    session.__enter__.return_value = session
    response = MagicMock(status_code=200, content=b"public data")
    response.__enter__.return_value = response
    response.json.return_value = {
        "code": 200,
        "data": [{"charId": "char_test", "own": 1, "sampleSize": 1}],
    }

    def fetch(*args, **kwargs):
        with counter.get_lock():
            counter.value += 1
        if not release.wait(10):
            raise RuntimeError("test release timed out")
        if fail:
            raise requests.Timeout("offline")
        return response

    session.get.side_effect = fetch
    survey.requests.Session = lambda: session
    ready.wait(timeout=10)
    output.put(survey.get_statistics())


@pytest.mark.parametrize("fail", [False, True])
def test_separate_processes_share_one_refresh_or_failure_cooldown(tmp_path, fail):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    counter = context.Value("i", 0)
    ready = context.Barrier(3)
    release = context.Event()
    output = context.Queue()
    processes = [
        context.Process(
            target=_statistics_process,
            args=(str(tmp_path), name, counter, ready, release, output, fail),
        )
        for name in ("instance_one", "instance_two")
    ]
    try:
        for process in processes:
            process.start()
        ready.wait(timeout=10)
        release.set()
        results = [output.get(timeout=15) for _ in processes]
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0
        assert counter.value == 1
        assert results[0] == results[1]
        if fail:
            assert results[0]["retry_after"] == 1_000_300
            assert "超时" in results[0]["error"]
        else:
            assert results[0]["operators"][0]["charId"] == "char_test"
            assert not results[0]["stale"]
    finally:
        release.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        output.close()
