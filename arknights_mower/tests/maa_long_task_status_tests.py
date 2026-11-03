from unittest.mock import MagicMock

import pytest

from arknights_mower.solvers import record
from arknights_mower.tests import maa_copilot_tests as helpers
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.maa_copilot import queue_key
from arknights_mower.utils.maa_long_task import blackflow_start_run_key

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


@pytest.mark.parametrize("kind", ["copilot", "paradox", "sss", "blackflow"])
def test_status_follows_current_saved_round_and_does_not_write_progress(status, kind):
    server, read = status
    assert all(not item["completed"] for item in read().values())
    if kind == "blackflow":
        settings = server.config.conf.rogue
        record.save_maa_blackflow_progress(
            {"key": blackflow_start_run_key(settings), "completed": True}
        )
        load = record.load_maa_blackflow_progress
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
    else:
        settings.run_id = "new-round"
    assert read()[kind]["completed"] is False
    assert load() == before


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


def test_status_read_failure_is_not_reported_as_pending(client, monkeypatch):
    monkeypatch.setattr(
        "arknights_mower.utils.maa_long_task.completion_status",
        MagicMock(side_effect=OSError("offline test")),
    )
    response = client.get(
        "/maa-long-task-status", headers={"token": "copilot-test-token"}
    )
    assert response.status_code == 500
    assert response.get_json() == {"message": "读取大型任务状态失败"}
