from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.maa_copilot import queue_key
from arknights_mower.utils.maa_long_task import (
    blackflow_boss_run_key,
    blackflow_start_run_key,
)

files = helpers.files
client = helpers.client


@pytest.mark.parametrize("method", ["GET", "HEAD"])
@pytest.mark.parametrize("token", [None, "invalid"])
def test_status_requires_token_before_reading_progress(
    client, monkeypatch, method, token
):
    read = MagicMock()
    monkeypatch.setattr("arknights_mower.utils.maa_long_task.completion_status", read)
    headers = {} if token is None else {"token": token}
    assert (
        client.open("/maa-long-task-status", method=method, headers=headers).status_code
        == 403
    )
    read.assert_not_called()


@pytest.fixture
def status(client, monkeypatch, tmp_path):
    import server

    monkeypatch.setattr(record, "get_path", lambda value: tmp_path / value[5:])
    monkeypatch.setattr(record, "_tables_created", False)

    def read():
        response = client.get(
            "/maa-long-task-status", headers={"token": "copilot-test-token"}
        )
        assert response.status_code == 200
        return response.get_json()

    return server, read


def test_status_reads_all_six_tasks_with_one_connection_and_query(status, monkeypatch):
    _, read = status
    with record._conn():
        pass
    statements = []
    connect = record.sqlite3.connect

    def traced_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connection.set_trace_callback(statements.append)
        return connection

    counted = MagicMock(side_effect=traced_connect)
    monkeypatch.setattr(record.sqlite3, "connect", counted)
    result = read()

    assert set(result) == {
        "copilot",
        "paradox",
        "sss",
        "blackflow",
        "blackflow_boss",
        "garrison",
    }
    assert all(not item["completed"] for item in result.values())
    counted.assert_called_once()
    assert (
        len([sql for sql in statements if sql.lstrip().upper().startswith("SELECT")])
        == 1
    )


@pytest.mark.parametrize(
    "kind", ["copilot", "paradox", "sss", "blackflow", "blackflow_boss"]
)
def test_status_follows_current_saved_round_and_does_not_write_progress(status, kind):
    server, read = status
    assert all(not item["completed"] for item in read().values())
    if kind in ("blackflow", "blackflow_boss"):
        boss = kind == "blackflow_boss"
        settings = server.config.conf.rogue
        record.save_maa_blackflow_progress(
            {
                "key": (blackflow_boss_run_key if boss else blackflow_start_run_key)(
                    settings
                ),
                "completed": True,
            },
            boss=boss,
        )

        def load():
            return record.load_maa_blackflow_progress(boss=boss)
    else:
        settings = getattr(server.config.conf, kind)
        settings.scripts = getattr(
            Conf(**{kind: {"scripts": [{"id": "a" * 64}]}}), kind
        ).scripts
        getattr(record, f"save_maa_{kind}_progress")(
            {"key": queue_key(settings), "next": 1, "failed": False}
        )
        load = getattr(record, f"load_maa_{kind}_progress")
    before = load()
    assert read()[kind]["completed"] is True
    assert load() == before
    if kind == "blackflow":
        settings.blackflow_start_run_id = "new-round"
    elif kind == "blackflow_boss":
        settings.blackflow_boss_run_id = "new-boss-round"
    else:
        settings.run_id = "new-round"
    assert read()[kind]["completed"] is False
    assert load() == before


def test_opening_and_boss_statuses_are_independent(status):
    server, read = status
    settings = server.config.conf.rogue
    record.save_maa_blackflow_progress(
        {"key": blackflow_start_run_key(settings), "completed": True}
    )
    record.save_maa_blackflow_progress(
        {"key": blackflow_boss_run_key(settings), "completed": True}, boss=True
    )
    assert read()["blackflow"]["completed"] is True
    assert read()["blackflow_boss"]["completed"] is True
    difficulty = settings.difficulty
    settings.difficulty = difficulty + 1
    changed = read()
    assert not changed["blackflow"]["completed"]
    assert not changed["blackflow_boss"]["completed"]
    settings.difficulty = difficulty
    settings.blackflow_start_run_id = "new-opening"
    assert read()["blackflow"]["completed"] is False
    assert read()["blackflow_boss"]["completed"] is True
    settings.blackflow_boss_run_id = "new-boss"
    assert read()["blackflow_boss"]["completed"] is False


def test_authorized_head_reads_status(client, monkeypatch):
    read = MagicMock(return_value={"blackflow_boss": {"completed": True}})
    monkeypatch.setattr("arknights_mower.utils.maa_long_task.completion_status", read)
    response = client.head(
        "/maa-long-task-status", headers={"token": "copilot-test-token"}
    )
    assert response.status_code == 200
    read.assert_called_once()


def test_partial_sss_repetitions_still_wait_for_execution(status):
    server, read = status
    server.config.conf.sss = Conf(sss={"scripts": [{"id": "a" * 64, "times": 2}]}).sss
    record.save_maa_sss_progress(
        {
            "key": queue_key(server.config.conf.sss),
            "next": 0,
            "completed": 1,
            "failed": False,
        }
    )
    assert read()["sss"]["completed"] is False


def test_status_read_failure_is_not_reported_as_pending(client, status):
    with record._conn() as connection:
        connection.execute("INSERT INTO maa_paradox_progress VALUES (1, 'invalid')")
        connection.commit()
    response = client.get(
        "/maa-long-task-status", headers={"token": "copilot-test-token"}
    )
    assert response.status_code == 500
    assert response.get_json() == {"message": "读取大型任务状态失败"}


def test_garrison_status_reads_observed_wins_without_advancing_match(status):
    from arknights_mower.solvers.garrison.model import catalogue, prepare_progress

    server, read = status
    p = prepare_progress(server.config.conf, {})
    p["wins"] = {s["id"]: 3 for s in catalogue()["strategies"]}
    p["match"] = {"stage": "act3autochess_m01", "round": 4}
    record.save_garrison_progress(p)
    assert read()["garrison"]["completed"]
    assert record.load_garrison_progress() == p
    server.config.conf.garrison.target_wins = 6
    assert not read()["garrison"]["completed"]
    assert record.load_garrison_progress() == p
