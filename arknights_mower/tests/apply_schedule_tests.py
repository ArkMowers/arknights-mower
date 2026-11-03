"""Offline task restart through the authenticated plan application route."""

from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import arknights_mower.__main__ as mower_main
import server
from arknights_mower.solvers import record
from arknights_mower.utils import config, crash_recovery, instance_supervisor
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
from arknights_mower.views import task as task_view


@pytest.fixture
def application(monkeypatch, tmp_path):
    monkeypatch.setattr(server.app, "token", "apply-test", raising=False)
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(instance_supervisor, "task_intent", Mock())
    shutdown = Mock(side_effect=AssertionError("process shutdown"))
    monkeypatch.setattr(
        server, "shutdown", SimpleNamespace(closing=False, request=shutdown)
    )
    launch = Mock(side_effect=AssertionError("process launch"))
    monkeypatch.setattr(server.subprocess, "Popen", launch)
    monkeypatch.setattr(server, "active_job", lambda: None)
    monkeypatch.setattr(server, "_job_running", lambda _: False)
    monkeypatch.setattr(server.resource_update, "running", lambda: False)
    monkeypatch.setattr(server, "_performance_test_status", lambda: {"status": "idle"})
    monkeypatch.setattr(server, "get_path", lambda _: tmp_path / "tmp")
    monkeypatch.setattr(
        record,
        "get_path",
        lambda name: tmp_path / "state.db" if name.endswith("data.db") else tmp_path,
    )
    monkeypatch.setattr(record, "_tables_created", False)
    saved = {
        "operators": {"阿米娅": SimpleNamespace(mood=13, current_room="central")},
        "dorm": [{"name": "能天使", "position": ("dormitory_1", 2)}],
        "tasks": [SchedulerTask(task_type=TaskTypes.SHIFT_OFF)],
        "task_count": 7,
    }
    snapshot = Mock(return_value=saved)
    monkeypatch.setattr(record, "current_state", snapshot)
    monkeypatch.setattr(mower_main, "base_scheduler", SimpleNamespace())
    monkeypatch.setattr(task_view, "mower_thread", None)
    events = []
    alive = True

    def join(timeout):
        nonlocal alive
        assert config.stop_mower.is_set()
        assert timeout >= 0
        events.append("cleanup")
        alive = False
        mower_main.base_scheduler = None

    old_worker = SimpleNamespace(is_alive=lambda: alive, join=join)
    monkeypatch.setattr(server, "mower_thread", old_worker)
    new_worker = Mock()
    new_worker.start.side_effect = lambda: events.append("start")
    thread_factory = Mock(return_value=new_worker)
    monkeypatch.setattr(server, "Thread", thread_factory)
    return SimpleNamespace(
        client=server.app.test_client(),
        saved=saved,
        events=events,
        old_worker=old_worker,
        new_worker=new_worker,
        thread_factory=thread_factory,
        launch=launch,
        shutdown=shutdown,
        snapshot=snapshot,
    )


def apply(application, token="apply-test"):
    headers = {"token": token} if token else {}
    return application.client.post("/plan/apply", headers=headers)


def test_application_stops_worker_then_starts_mode_one_without_process_restart(
    application,
):
    response = apply(application)

    assert response.status_code == 200
    assert response.json["ok"]
    assert application.events == ["cleanup", "start"]
    assert server.mower_thread is application.new_worker
    assert task_view.mower_thread is application.new_worker
    resumed = application.thread_factory.call_args.kwargs["args"][0]
    assert resumed["tasks"] == []
    assert resumed["operators"] == application.saved["operators"]
    assert resumed["dorm"] == application.saved["dorm"]
    assert resumed["task_count"] == 7
    assert record.load_state()["tasks"][0].type == TaskTypes.SHIFT_OFF
    assert not config.stop_mower.is_set()
    application.launch.assert_not_called()
    application.shutdown.assert_not_called()


@pytest.mark.parametrize("token", [None, "wrong"])
def test_application_requires_token_before_stopping_or_starting(application, token):
    response = apply(application, token)

    assert response.status_code == 403
    assert application.events == []
    application.snapshot.assert_not_called()
    application.thread_factory.assert_not_called()
    assert not config.stop_mower.is_set()


def test_old_process_action_cannot_restart_the_service_to_apply_a_plan(application):
    response = application.client.post(
        "/process-control/action",
        headers={"token": "apply-test", "X-Mower-Control": "1"},
        json={"action": "apply_schedule"},
    )

    assert not response.json["ok"]
    assert application.events == []
    application.launch.assert_not_called()


@pytest.mark.parametrize(
    "blocker", ["stopped", "stopping", "update", "shutdown", "test"]
)
def test_application_rejects_unavailable_task_without_stopping_it(
    application, monkeypatch, blocker
):
    if blocker == "stopped":
        monkeypatch.setattr(server, "mower_thread", None)
    elif blocker == "stopping":
        config.stop_mower.set()
    elif blocker == "update":
        monkeypatch.setattr(server, "active_job", lambda: {"id": "update"})
    elif blocker == "shutdown":
        monkeypatch.setattr(server.shutdown, "closing", True)
    else:
        monkeypatch.setattr(
            server, "_performance_test_status", lambda: {"status": "running"}
        )
    response = apply(application)

    assert response.status_code == 409
    assert not response.json["ok"]
    assert application.events == []
    application.thread_factory.assert_not_called()


def test_application_does_not_start_another_worker_when_stop_times_out(application):
    application.old_worker.join = lambda _: application.events.append("still stopping")

    response = apply(application)

    assert response.status_code == 409
    assert not response.json["ok"]
    assert application.events == ["still stopping"]
    assert server.mower_thread is application.old_worker
    application.thread_factory.assert_not_called()
    assert config.stop_mower.is_set()


def test_application_reports_start_rejection_after_successful_stop(
    application, monkeypatch
):
    monkeypatch.setattr(server.resource_update, "running", lambda: True)

    response = apply(application)

    assert response.status_code == 409
    assert not response.json["ok"]
    assert application.events == ["cleanup"]
    assert server.mower_thread is None
    application.thread_factory.assert_not_called()
    assert config.stop_mower.is_set()


def test_application_does_not_start_when_state_cannot_be_saved(
    application, monkeypatch
):
    monkeypatch.setattr(record, "save_state_to_db", lambda _: False)

    response = apply(application)

    assert response.status_code == 500
    assert "保存失败" in response.json["message"]
    assert application.events == ["cleanup"]
    application.thread_factory.assert_not_called()


def test_application_reports_worker_start_failure_without_restarting_process(
    application,
):
    application.new_worker.start.side_effect = RuntimeError("cannot create task thread")

    response = apply(application)

    assert response.status_code == 500
    assert "启动失败" in response.json["message"]
    assert server.mower_thread is None
    assert config.stop_mower.is_set()
    application.launch.assert_not_called()
    application.shutdown.assert_not_called()
