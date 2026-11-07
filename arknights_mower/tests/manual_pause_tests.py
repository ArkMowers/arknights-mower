"""明确取消手动闪断只结束该窗口，普通任务唤醒不能提前登录。"""

from datetime import timedelta
from threading import Event
from unittest.mock import Mock

import pytest

from arknights_mower import __main__ as main
from arknights_mower.solvers import base_schedule as base
from arknights_mower.tests import idle_scene_watchdog_tests as idle_tests
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

idle_scheduler = idle_tests.idle_scheduler


@pytest.fixture
def pause_env(idle_scheduler, monkeypatch):
    import server

    monkeypatch.setattr(main, "_manual_pause", None)
    monkeypatch.setattr(main, "datetime", idle_scheduler.clock)
    monkeypatch.setattr(server.app, "token", "pause-token", raising=False)
    monkeypatch.setattr(server, "mower_thread", Mock(is_alive=Mock(return_value=True)))
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "wake_scheduler", Event())
    idle_scheduler.solver.op_data = None
    return idle_scheduler, server.app.test_client()


@pytest.mark.parametrize(
    "path,method",
    [("/status", "GET"), ("/status", "HEAD"), ("/maintenance-pause", "DELETE")],
)
@pytest.mark.parametrize("token", [None, "incorrect"])
def test_pause_routes_reject_unauthorized_state_access(
    pause_env, monkeypatch, path, method, token
):
    denied = Mock(side_effect=AssertionError("unauthorized pause access"))
    monkeypatch.setattr(main, "get_manual_pause", denied)
    monkeypatch.setattr(main, "cancel_manual_pause", denied)
    response = pause_env[1].open(
        path,
        method=method,
        json={"id": "old"},
        headers={} if token is None else {"token": token},
    )
    assert response.status_code == 403
    denied.assert_not_called()


@pytest.mark.parametrize("startup", [False, True])
def test_cancel_pause_wakes_only_current_window_and_preserves_other_tasks(
    pause_env, monkeypatch, startup
):
    env, client = pause_env
    solver, clock = env.solver, env.clock
    update = SchedulerTask(clock.now(), task_type=TaskTypes.FLASH_UPDATE)
    update.duration_minutes = 10
    update.maintenance_mode = "pause"
    unrelated = SchedulerTask(clock.now(), task_type=TaskTypes.MAIL)
    next_window = SchedulerTask(
        clock.now() + timedelta(minutes=30), task_type=TaskTypes.FLASH_UPDATE
    )
    solver.tasks = [update, unrelated, next_window]
    monkeypatch.setattr(main, "base_scheduler", None if startup else solver)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", solver.tasks)
    solver.handle_idle_action = Mock()
    checks = []

    def advance(seconds):
        clock.current += timedelta(seconds=1 if startup else seconds)
        checks.append(main.get_manual_pause())
        snapshot = client.get("/status", headers={"token": "pause-token"}).json
        assert (
            snapshot["maintenance_pause"]["id"]
            == update.maintenance_info.announcement_id
        )
        # 页面过期、无凭证及错误请求都不能结束当前等待。
        assert (
            client.delete(
                "/maintenance-pause",
                json={"id": "old"},
                headers={"token": "pause-token"},
            ).status_code
            == 409
        )
        assert (
            client.delete(
                "/maintenance-pause", json={"id": snapshot["maintenance_pause"]["id"]}
            ).status_code
            == 403
        )
        if len(checks) == 1 and not startup:
            config.wake_scheduler.set()
            return
        response = client.delete(
            "/maintenance-pause",
            json={"id": snapshot["maintenance_pause"]["id"]},
            headers={"token": "pause-token"},
        )
        assert response.status_code == 200
        assert main.get_manual_pause() is None
        if startup:
            raise MowerExit

    monkeypatch.setattr(main if startup else base, "csleep", advance)
    start = clock.now()
    assert (
        main._handle_maintenance(update.maintenance_info, None if startup else solver)
        is False
    )
    assert len(checks) == (1 if startup else 2)
    if not startup:
        assert clock.now() - start == timedelta(seconds=2)
        assert not solver.sleeping
    else:
        assert clock.now() - start == timedelta(seconds=1)
    assert solver.tasks == [unrelated, next_window]
    assert main.get_manual_pause() is None
    assert not config.stop_mower.is_set()


def test_cancel_validation_and_stale_id_do_not_affect_next_pause(pause_env):
    env, client = pause_env
    update = SchedulerTask(env.clock.now(), task_type=TaskTypes.FLASH_UPDATE)
    current = (update.maintenance_info, Event())
    main._manual_pause = current
    for payload in (None, {}, {"id": True}, {"id": ""}):
        assert (
            client.delete(
                "/maintenance-pause", json=payload, headers={"token": "pause-token"}
            ).status_code
            == 400
        )
    assert not main.cancel_manual_pause("old")
    assert not current[1].is_set()
    assert main.cancel_manual_pause(update.maintenance_info.announcement_id)
    assert current[1].is_set()
    next_window = SchedulerTask(
        env.clock.now() + timedelta(minutes=20), task_type=TaskTypes.FLASH_UPDATE
    )
    next_pause = (next_window.maintenance_info, Event())
    main._manual_pause = next_pause
    assert not main.cancel_manual_pause(update.maintenance_info.announcement_id)
    assert not next_pause[1].is_set()


def test_wait_failure_clears_pause_without_consuming_task(pause_env, monkeypatch):
    env, _ = pause_env
    update = SchedulerTask(env.clock.now(), task_type=TaskTypes.FLASH_UPDATE)
    update.maintenance_mode = "pause"
    env.solver.tasks = [update]
    env.solver.handle_idle_action = Mock(side_effect=RuntimeError("device failure"))
    with pytest.raises(RuntimeError, match="device failure"):
        main._handle_maintenance(update.maintenance_info, env.solver)
    assert main.get_manual_pause() is None
    assert env.solver.tasks == [update]
