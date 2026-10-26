"""本轮结束停止复用正常收尾和保存状态，不把其他等待当作完成。"""

from contextlib import contextmanager, nullcontext
from datetime import date, datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower import __main__ as main
from arknights_mower.solvers import base_schedule as base
from arknights_mower.solvers import record
from arknights_mower.tests import idle_scene_watchdog_tests as idle_tests
from arknights_mower.utils import (
    config,
    crash_recovery,
    instance_supervisor,
    round_stop,
    update_runtime,
)
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.news_checker import MaintenanceInfo
from arknights_mower.utils.operators import Operator

REAL_SAVE_CURRENT_STATE = record.save_current_state
idle_scheduler = idle_tests.idle_scheduler
production_idle_scheduler = idle_tests.production_idle_scheduler


@pytest.fixture(autouse=True)
def stop_state(monkeypatch):
    monkeypatch.setattr(round_stop, "_requested", False)
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    save = Mock(return_value=True)
    intent = Mock()
    replacement = Mock()
    monkeypatch.setattr(record, "save_current_state", save)
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)
    monkeypatch.setattr(update_runtime, "record_task_stop", replacement)
    return SimpleNamespace(save=save, intent=intent, replacement=replacement)


@pytest.fixture
def route_server(monkeypatch):
    import server

    monkeypatch.setattr(server.app, "token", "round-stop-token", raising=False)
    monkeypatch.setattr(server, "mower_thread", Mock(is_alive=Mock(return_value=True)))
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(server, "active_job", lambda: False)
    monkeypatch.setattr(server, "performance_test_job", {"status": "idle"})
    monkeypatch.setattr(main, "base_scheduler", None)
    return server


HEADERS = {"token": "round-stop-token"}


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("token", [None, "incorrect"])
def test_route_rejects_missing_or_invalid_token_before_state_access(
    route_server, monkeypatch, method, token
):
    denied = Mock(side_effect=AssertionError("未授权请求不得读写停止请求"))
    for name in ("request_stop", "cancel", "pending"):
        monkeypatch.setattr(round_stop, name, denied)
    response = route_server.app.test_client().open(
        "/stop-after-round",
        method=method,
        headers={} if token is None else {"token": token},
    )
    assert response.status_code == 403
    denied.assert_not_called()


def test_request_cancel_and_status_do_not_stop_running_work(route_server, stop_state):
    client = route_server.app.test_client()
    for _ in range(2):
        response = client.put("/stop-after-round", headers=HEADERS)
        assert response.json == {"stop_after_round": True}
        assert client.get("/status", headers=HEADERS).json["stop_after_round"]
        assert not config.stop_mower.is_set()
    response = client.delete("/stop-after-round", headers=HEADERS)
    assert response.json == {"stop_after_round": False}
    assert not client.get("/status", headers=HEADERS).json["stop_after_round"]
    stop_state.save.assert_not_called()
    stop_state.intent.assert_not_called()
    stop_state.replacement.assert_not_called()
    assert not crash_recovery.cancelled()


@pytest.mark.parametrize(
    "condition", ["absent", "finished", "stopping", "shutdown", "update", "test"]
)
def test_request_requires_an_active_automation_worker(
    route_server, monkeypatch, condition
):
    if condition == "absent":
        route_server.mower_thread = None
    elif condition == "finished":
        route_server.mower_thread.is_alive.return_value = False
    elif condition == "stopping":
        config.stop_mower.set()
    elif condition == "shutdown":
        route_server.shutdown.closing = True
    elif condition == "update":
        monkeypatch.setattr(route_server, "active_job", lambda: True)
    else:
        route_server.performance_test_job["status"] = "running"
    response = route_server.app.test_client().put("/stop-after-round", headers=HEADERS)
    assert response.status_code == 409
    assert not round_stop.pending()


def test_cancel_is_idempotent_after_worker_exit(route_server):
    round_stop.request_stop()
    route_server.mower_thread.is_alive.return_value = False
    client = route_server.app.test_client()
    assert not client.get("/status", headers=HEADERS).json["stop_after_round"]
    assert client.delete("/stop-after-round", headers=HEADERS).json == {
        "stop_after_round": False
    }


def test_normal_round_saves_then_stops_without_a_future_start_notice(
    production_idle_scheduler, stop_state
):
    solver = production_idle_scheduler.solver
    tasks = [(task, task.time, dict(task.plan)) for task in solver.tasks]
    round_stop.request_stop()

    def saved():
        assert not config.stop_mower.is_set()
        assert not crash_recovery.cancelled()
        stop_state.intent.assert_not_called()
        return True

    stop_state.save.side_effect = saved
    with pytest.raises(MowerExit):
        solver.rest_until_next_task()

    stop_state.save.assert_called_once_with()
    stop_state.intent.assert_called_once_with(False)
    stop_state.replacement.assert_called_once_with()
    assert crash_recovery.cancelled()
    assert config.stop_mower.is_set()
    assert not round_stop.pending()
    assert [(task, task.time, dict(task.plan)) for task in solver.tasks] == tasks
    assert solver.task_count == 1
    assert base.send_message.call_args.args[1] == "本轮任务结束，已按要求停止"
    assert base.send_message.call_count == 1
    solver.device.reconnect.assert_not_called()
    solver.device.check_current_focus.assert_not_called()


def test_request_during_normal_rest_stops_before_device_wakeup(
    production_idle_scheduler, monkeypatch, stop_state
):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    started = clock.now()
    config.conf.close_simulator_when_idle = True
    restart = Mock(return_value=True)
    monkeypatch.setattr(base, "restart_simulator", restart)

    def sleep(seconds):
        clock.current += timedelta(seconds=seconds)
        round_stop.request_stop()

    monkeypatch.setattr(base, "csleep", sleep)
    with pytest.raises(MowerExit):
        solver.rest_until_next_task()
    assert clock.now() - started == timedelta(seconds=1)
    assert not solver.sleeping
    restart.assert_called_once_with(start=False)
    stop_state.save.assert_called_once_with()
    assert base.send_message.call_args.args[1] == "本轮任务结束，已按要求停止"


@pytest.mark.parametrize("allow_wakeup", [True, False])
def test_other_idle_waits_do_not_fulfill_round_stop(
    production_idle_scheduler, stop_state, allow_wakeup
):
    solver = production_idle_scheduler.solver
    round_stop.request_stop()
    solver._idle_sleep(2, allow_wakeup=allow_wakeup)
    assert round_stop.pending()
    assert not config.stop_mower.is_set()
    stop_state.save.assert_not_called()
    stop_state.intent.assert_not_called()


def test_due_work_must_finish_before_round_stop(production_idle_scheduler, stop_state):
    solver, clock = production_idle_scheduler.solver, production_idle_scheduler.clock
    solver.tasks[0].time = clock.now()
    round_stop.request_stop()
    solver.rest_until_next_task()
    assert round_stop.pending()
    stop_state.save.assert_not_called()
    assert not config.stop_mower.is_set()


def test_cancelled_request_preserves_normal_rest(production_idle_scheduler, stop_state):
    solver = production_idle_scheduler.solver
    round_stop.request_stop()
    round_stop.cancel()
    solver.rest_until_next_task()
    assert not config.stop_mower.is_set()
    stop_state.save.assert_not_called()
    assert "开始工作" in base.send_message.call_args.args[1]


def test_empty_queue_is_also_a_round_end(production_idle_scheduler, stop_state):
    solver = production_idle_scheduler.solver
    solver.tasks = []
    round_stop.request_stop()
    with pytest.raises(MowerExit):
        solver.rest_until_next_task()
    stop_state.save.assert_called_once_with()


def test_save_failure_keeps_request_and_run_intent(
    production_idle_scheduler, stop_state
):
    stop_state.save.return_value = False
    round_stop.request_stop()
    with pytest.raises(RuntimeError, match="保存运行状态失败"):
        production_idle_scheduler.solver.rest_until_next_task()
    assert round_stop.pending()
    assert not config.stop_mower.is_set()
    assert not crash_recovery.cancelled()
    stop_state.intent.assert_not_called()
    base.send_message.assert_not_called()


def test_notification_failure_does_not_restart_work(production_idle_scheduler):
    base.send_message.side_effect = RuntimeError("邮件不可用")
    round_stop.request_stop()
    with pytest.raises(MowerExit):
        production_idle_scheduler.solver.rest_until_next_task()
    assert config.stop_mower.is_set()
    assert crash_recovery.cancelled()


@pytest.mark.parametrize("report", ["intent", "replacement"])
def test_report_failure_does_not_prevent_stop(
    production_idle_scheduler, stop_state, report
):
    getattr(stop_state, report).side_effect = OSError("报告暂时无法写入")
    round_stop.request_stop()
    with pytest.raises(MowerExit):
        production_idle_scheduler.solver.rest_until_next_task()
    assert config.stop_mower.is_set()
    assert crash_recovery.cancelled()


def test_round_end_leaves_the_worker_through_device_cleanup(
    route_server, production_idle_scheduler, monkeypatch, stop_state
):
    solver = production_idle_scheduler.solver
    monkeypatch.setattr(main, "base_scheduler", solver)
    events = []

    @contextmanager
    def device_run(**kwargs):
        events.append("enter")
        try:
            yield
        finally:
            assert config.stop_mower.is_set()
            stop_state.save.assert_called_once_with()
            events.append("leave")

    close = Mock(return_value=SimpleNamespace(ok=True))
    control = SimpleNamespace(run=device_run, shutdown_requested=False, close=close)
    monkeypatch.setattr(main, "device_control", control)
    monkeypatch.setattr(main, "resource_task_session", nullcontext)
    monkeypatch.setattr(main, "_main", lambda _: solver.rest_until_next_task())
    activate = Mock()
    monkeypatch.setattr(crash_recovery, "activate", activate)
    round_stop.request_stop()
    route_server._run_mower_worker({})
    assert events == ["enter", "leave"]
    close.assert_called_once_with()
    activate.assert_not_called()
    assert main.base_scheduler is None
    assert not round_stop.pending()


def test_immediate_stop_clears_the_pending_request(route_server, stop_state):
    round_stop.request_stop()
    route_server.mower_thread.is_alive.return_value = False
    assert route_server._stop_mower()
    assert not round_stop.pending()
    assert config.stop_mower.is_set()
    assert crash_recovery.cancelled()


@pytest.mark.parametrize("failure", [None, MowerExit(), RuntimeError("worker failed")])
def test_worker_exit_clears_request(route_server, monkeypatch, failure):
    round_stop.request_stop()
    monkeypatch.setattr(main, "main", Mock(side_effect=failure))
    monkeypatch.setattr(crash_recovery, "activate", Mock())
    route_server._run_mower_worker({})
    assert not round_stop.pending()


def test_new_start_clears_old_request(route_server, monkeypatch, tmp_path):
    round_stop.request_stop()
    route_server.mower_thread = None
    monkeypatch.setattr(route_server, "get_path", lambda _: tmp_path)
    monkeypatch.setattr(route_server, "_job_running", lambda _: False)
    monkeypatch.setattr(route_server.resource_update, "running", lambda: False)
    monkeypatch.setattr(route_server, "Thread", Mock())
    monkeypatch.setattr(crash_recovery, "status", lambda: {"active": False})
    monkeypatch.setattr(crash_recovery, "request_resume", Mock())
    assert route_server._start_mower("2")
    assert not round_stop.pending()
    assert not config.stop_mower.is_set()


def test_manual_downtime_keeps_its_restart_when_round_stop_is_pending(
    route_server, monkeypatch, stop_state
):
    now = datetime.now()
    maintenance = MaintenanceInfo(
        now,
        now + timedelta(minutes=10),
        "major",
        "停服更新",
        "",
        "manual-round-stop-test",
        manual=True,
    )
    monkeypatch.setattr(main, "main", Mock(return_value=maintenance))
    schedule = Mock(return_value=maintenance.end)
    monkeypatch.setattr(route_server, "_schedule_start", schedule)
    round_stop.request_stop()
    route_server._run_mower_worker({})
    schedule.assert_called_once()
    assert schedule.call_args.kwargs == {"start_type": "0"}
    assert 590 < schedule.call_args.args[0] <= 600
    assert not round_stop.pending()
    assert config.stop_mower.is_set()
    stop_state.save.assert_not_called()


def test_round_stop_persists_queue_positions_and_mood(
    production_idle_scheduler, income_db, monkeypatch
):
    solver = production_idle_scheduler.solver
    monkeypatch.setattr(main, "base_scheduler", solver)
    data = solver.op_data
    data.all_dorms = lambda: []
    data.party_time = None
    data.backup_plans = []
    operator = Operator("阿米娅", "room_1_1")
    operator.mood, operator.current_room, operator.current_index = 13.5, "room_1_1", 1
    data.operators = {"阿米娅": operator}
    for name in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, name, date.min)
    # 使用真实的状态采集和 SQLite 写入，覆盖停止后载入的内容。
    monkeypatch.setattr(record, "save_current_state", REAL_SAVE_CURRENT_STATE)
    pending = [(task.time, dict(task.plan), task.type) for task in solver.tasks]
    round_stop.request_stop()
    with pytest.raises(MowerExit):
        solver.rest_until_next_task()
    saved = record.load_state(strict=True)
    assert [(task.time, task.plan, task.type) for task in saved["tasks"]] == pending
    restored = saved["operators"]["阿米娅"]
    assert (restored.mood, restored.current_room, restored.current_index) == (
        13.5,
        "room_1_1",
        1,
    )
    assert saved["task_count"] == 1
