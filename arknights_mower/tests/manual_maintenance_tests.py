"""手动维护复用公告维护的避让、副表和等待流程，不访问设备或网络。"""

import pickle
from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from flask import Flask

from arknights_mower.tests import maintenance_run_order_tests as backup_tests
from arknights_mower.tests import scheduler_recovery_preservation_tests as recovery
from arknights_mower.utils import news_checker
from arknights_mower.utils.news_checker import MaintenanceInfo, NewsChecker
from arknights_mower.utils.operators import Operators
from arknights_mower.utils.scheduler_task import (
    MAINTENANCE_TASK_TYPES,
    SchedulerTask,
    TaskTypes,
    protect_priority_tasks,
    replan_update_tasks,
    scheduling,
)

scheduler = recovery.scheduler
backup_solver = backup_tests.solver


@pytest.fixture
def maintenance(scheduler, monkeypatch):
    monkeypatch.setattr(news_checker, "datetime", scheduler.clock)
    monkeypatch.setattr(scheduler.main, "datetime", scheduler.clock)
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(scheduler.module.config, "wake_scheduler", Event())
    monkeypatch.setattr(scheduler.module.config.conf, "enable_mastery", True)
    monkeypatch.setattr(scheduler.main, "_flash_probe_ids", set())
    return scheduler


def update_task(maintenance, kind=TaskTypes.FLASH_UPDATE, mode="prepare", minutes=60):
    task = SchedulerTask(
        maintenance.clock.now() + timedelta(minutes=minutes), task_type=kind
    )
    task.duration_minutes = 10
    task.maintenance_mode = mode
    maintenance.solver.tasks.append(task)
    return task


@pytest.mark.parametrize("kind", list(MAINTENANCE_TASK_TYPES))
@pytest.mark.parametrize("duration", [None, 25])
def test_authenticated_route_creates_window_without_roster_and_wakes(
    maintenance, monkeypatch, kind, duration
):
    from arknights_mower.views import task as route

    app = Flask(__name__)
    app.token = "test-token"
    app.register_blueprint(route.task_bp)
    monkeypatch.setattr(route, "mower_thread", Mock(is_alive=Mock(return_value=True)))
    body = {
        "task": {
            "time": "2026-10-01T03:00:00.000Z",
            "plan": {"train": ["陈"]},
            "task_type": kind.display_value,
            "meta_data": "stale",
        }
    }
    if duration is not None:
        body["task"]["duration_minutes"] = duration
    client = app.test_client()
    for token in (None, "wrong"):
        headers = {"token": token} if token else {}
        assert client.post("/task", json=body, headers=headers).status_code == 403
        assert client.get("/task", headers=headers).status_code == 403
        assert maintenance.solver.tasks == []
        assert not maintenance.module.config.wake_scheduler.is_set()
    assert (
        client.post("/task", json=body, headers={"token": "test-token"}).text
        == "添加任务成功！"
    )
    (task,) = maintenance.solver.tasks
    assert task.type == kind
    assert task.plan == {} and task.meta_data == ""
    assert task.duration_minutes == (duration or 10)
    assert task.maintenance_mode == "prepare"
    assert maintenance.module.config.wake_scheduler.is_set()
    assert maintenance.module.config.maintenance_recheck.is_set()
    result = client.get("/task", headers={"token": "test-token"}).json[0]
    assert str(duration or 10) in result["display_name"]
    assert result["duration_minutes"] == (duration or 10)
    maintenance.io.assert_not_called()


@pytest.mark.parametrize(
    "field,value",
    [
        ("duration_minutes", 0),
        ("duration_minutes", -1),
        ("duration_minutes", 1.5),
        ("duration_minutes", True),
        ("duration_minutes", "10"),
        ("duration_minutes", 10081),
        ("maintenance_mode", "unknown"),
    ],
)
def test_route_rejects_invalid_window_without_queue_mutation(
    maintenance, monkeypatch, field, value
):
    from arknights_mower.views import task as route

    app = Flask(__name__)
    app.token = "test-token"
    app.register_blueprint(route.task_bp)
    monkeypatch.setattr(route, "mower_thread", Mock(is_alive=Mock(return_value=True)))
    task = {
        "time": "2026-10-01T03:00:00.000Z",
        "plan": {},
        "task_type": "闪断更新",
        "meta_data": "",
        field: value,
    }
    result = app.test_client().post(
        "/task", json={"task": task}, headers={"token": "test-token"}
    )
    assert result.text != "添加任务成功！"
    assert maintenance.solver.tasks == []
    assert not maintenance.module.config.wake_scheduler.is_set()


@pytest.mark.parametrize("entry", [scheduling, protect_priority_tasks])
@pytest.mark.parametrize("mode", ["prepare", "pause"])
def test_flash_update_reuses_order_and_support_advance_only_in_prepare_mode(
    maintenance, entry, mode
):
    update = update_task(maintenance, mode=mode)
    update.duration_minutes = 30
    order = SchedulerTask(
        update.time + timedelta(minutes=4),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
    )
    swap = SchedulerTask(
        update.time + timedelta(minutes=25), task_type=TaskTypes.SWAP_SUPPORT
    )
    maintenance.solver.tasks.extend([order, swap])
    original_order, original_swap = order.time, swap.time
    entry(maintenance.solver.tasks, time_now=maintenance.clock.now())
    if mode == "prepare":
        # protect_priority_tasks 只保护换人；跑单提前由 scheduling 的原入口负责。
        if entry is scheduling:
            assert order.time < update.time - timedelta(minutes=10)
            assert order.adjusted
        assert swap.time < update.time - timedelta(minutes=10)
        assert swap.advance_support_swap
    else:
        assert order.time == original_order
        assert swap.time == original_swap
        assert not order.adjusted
        assert not getattr(swap, "advance_support_swap", False)
    snapshot = [(id(task), task.time) for task in maintenance.solver.tasks]
    for _ in range(3):
        entry(maintenance.solver.tasks, time_now=maintenance.clock.now())
    assert [(id(task), task.time) for task in maintenance.solver.tasks] == snapshot


@pytest.mark.parametrize("kind", list(MAINTENANCE_TASK_TYPES))
@pytest.mark.parametrize("elapsed", [0, 4, 5, 9, 10])
def test_manual_window_waits_to_exact_end_without_probe_or_stopping(
    maintenance, monkeypatch, kind, elapsed
):
    update = update_task(maintenance, kind=kind, minutes=0)
    info = update.maintenance_info
    maintenance.clock.current += timedelta(minutes=elapsed)
    solver = maintenance.solver
    solver._idle_sleep = Mock()
    solver.handle_idle_action = Mock()
    solver.tasks.append(SchedulerTask(maintenance.clock.now()))
    stop = Mock()
    monkeypatch.setattr(maintenance.main, "_stop_for_major_update", stop)
    assert info.resume_at == info.end
    assert not info.allows_early_login
    assert maintenance.main._handle_maintenance(info, solver) is False
    if elapsed < 10:
        solver._idle_sleep.assert_called_once_with(
            (10 - elapsed) * 60, allow_wakeup=False
        )
    else:
        solver._idle_sleep.assert_not_called()
    assert not maintenance.main._flash_probe_ids
    stop.assert_not_called()
    assert not maintenance.module.config.stop_mower.is_set()


def test_active_window_yields_before_scheduler_device_work_and_preserves_queue(
    maintenance,
):
    update = update_task(maintenance, minutes=0)
    pending = SchedulerTask(maintenance.clock.now(), {"train": ["陈"]})
    maintenance.solver.tasks.append(pending)
    maintenance.solver.handle_error = Mock()
    maintenance.solver.run()
    maintenance.solver.handle_error.assert_not_called()
    assert maintenance.module.config.maintenance_recheck.is_set()
    assert maintenance.solver.tasks == [update, pending]
    maintenance.io.assert_not_called()


def test_server_update_supplies_existing_backup_threshold_without_flash_activation(
    maintenance, monkeypatch
):
    from arknights_mower.utils import operators

    monkeypatch.setattr(operators, "datetime", maintenance.clock)
    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=20)
    data = SimpleNamespace(
        backup_plans=[SimpleNamespace(major_maintenance_thresholds=[0.5, 0.25])],
        backup_groups=[],
    )
    assert Operators.major_maintenance_remaining_hours(data) == pytest.approx(1 / 3)
    assert Operators.next_major_maintenance_check(data) == task.time - timedelta(
        minutes=15
    )
    task.type = TaskTypes.FLASH_UPDATE
    assert Operators.major_maintenance_remaining_hours(data) == float("inf")
    assert Operators.next_major_maintenance_check(data) is None
    task.type = TaskTypes.SERVER_UPDATE
    maintenance.clock.current = task.time
    assert Operators.major_maintenance_remaining_hours(data) == float("inf")


@pytest.mark.parametrize("kind", list(MAINTENANCE_TASK_TYPES))
def test_restored_update_preserves_duration_mode_and_original_timestamp(
    maintenance, kind
):
    task = update_task(maintenance, kind=kind)
    task.duration_minutes = 35
    (restored,) = pickle.loads(pickle.dumps([task]))
    maintenance.solver.tasks = [restored]
    assert restored.time == task.time
    assert restored.duration_minutes == 35
    assert restored.maintenance_mode == "prepare"
    assert restored.maintenance_info in NewsChecker.get_manual_maintenances()
    assert replan_update_tasks({"tasks": [restored]})["tasks"][0] is restored


def test_manual_pause_takes_precedence_over_announced_flash_probe(
    maintenance, monkeypatch
):
    task = update_task(maintenance, mode="pause", minutes=0)
    announced = MaintenanceInfo(
        task.time - timedelta(minutes=2),
        task.time + timedelta(minutes=15),
        "hot",
        "闪断更新",
        "",
        "announced",
    )
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: announced)
    assert NewsChecker.get_effective_maintenance() == task.maintenance_info
    maintenance.clock.current += timedelta(minutes=10)
    assert NewsChecker.get_effective_maintenance() == announced


def test_manual_server_timer_wakes_without_requesting_client_update(
    maintenance, monkeypatch
):
    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=20)
    stop = Mock()
    timer = Mock()
    monkeypatch.setattr(maintenance.main, "Timer", timer)
    monkeypatch.setattr(maintenance.main, "_maintenance_timer", None)
    monkeypatch.setattr(maintenance.main, "_maintenance_timer_key", None)
    monkeypatch.setattr(maintenance.main, "_stop_for_major_update", stop)
    maintenance.main._arm_maintenance_timer(task.maintenance_info)
    timer.call_args.args[1]()
    stop.assert_not_called()
    assert maintenance.module.config.wake_scheduler.is_set()
    assert maintenance.module.config.maintenance_recheck.is_set()


def test_manual_server_update_activates_and_exits_the_existing_backup(
    maintenance, backup_solver, monkeypatch
):
    from arknights_mower.utils import operators

    monkeypatch.setattr(operators, "datetime", maintenance.clock)
    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=20)
    backup_solver.backup_plan_solver()
    assert backup_solver.op_data.plan_condition == [True]
    assert backup_solver.op_data.run_order_paused
    maintenance.clock.current = task.maintenance_info.end
    backup_solver.backup_plan_solver()
    assert backup_solver.op_data.plan_condition == [False]
    assert not backup_solver.op_data.run_order_paused


def test_update_start_is_fixed_even_when_an_order_needs_the_same_operation_window(
    maintenance,
):
    task = update_task(maintenance, mode="pause", minutes=3)
    start = task.time
    order = SchedulerTask(start + timedelta(seconds=1), task_type=TaskTypes.RUN_ORDER)
    maintenance.solver.tasks.append(order)
    for _ in range(3):
        scheduling(maintenance.solver.tasks, time_now=maintenance.clock.now())
        assert task.time == start
        assert task.maintenance_info.end == start + timedelta(minutes=10)


def test_startup_waits_through_overlapping_manual_windows_before_initializing(
    maintenance, monkeypatch
):
    main = maintenance.main
    first = update_task(maintenance, minutes=0)
    second = update_task(maintenance, minutes=5)
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", ())
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        maintenance.clock.current += timedelta(seconds=seconds)

    monkeypatch.setattr(main, "csleep", sleep)
    monkeypatch.setattr(main, "_arm_maintenance_timer", Mock())
    initialized_at = []
    initialize = Mock(
        side_effect=lambda: initialized_at.append(maintenance.clock.now())
    )
    monkeypatch.setattr(main.rapidocr, "initialize_ocr", initialize)
    simulate = Mock()
    monkeypatch.setattr(main, "simulate", simulate)
    saved = {"tasks": [first, second]}
    main._main(saved)
    assert sleeps == [600, 300]
    assert initialized_at == [second.maintenance_info.end]
    assert maintenance.clock.now() == second.maintenance_info.end
    initialize.assert_called_once()
    simulate.assert_called_once_with(saved)


def test_short_idle_wait_yields_at_manual_start_without_waiting_for_timer(
    maintenance, monkeypatch
):
    task = update_task(maintenance, minutes=1)
    solver = maintenance.solver
    monkeypatch.setattr(maintenance.module, "sync_replacement_checks", Mock())
    for name in (
        "_refresh_observed_recovery_tasks",
        "_resume_failed_tasks",
        "handle_error",
        "_emergency_filter_tasks",
        "_schedule_maintenance_backup_check",
        "_resume_waiting_group_shifts",
        "_fill_empty_dorms",
    ):
        monkeypatch.setattr(solver, name, Mock())
    solver._idle_sleep = Mock(
        side_effect=lambda seconds: setattr(
            maintenance.clock,
            "current",
            maintenance.clock.now() + timedelta(seconds=seconds),
        )
    )
    solver.run()
    solver._idle_sleep.assert_called_once_with(60)
    assert maintenance.module.config.maintenance_recheck.is_set()
    assert solver.tasks == [task]
    solver.check_current_focus.assert_not_called()


def test_main_removes_only_expired_manual_windows_before_dispatch(
    maintenance, monkeypatch
):
    from arknights_mower.utils.csleep import MowerExit

    expired = update_task(maintenance, minutes=-20)
    pending = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    solver = Mock()
    solver.tasks = [expired, pending]
    solver.initialize_operators.return_value = None
    solver.op_data.validate_backup_plans.return_value = {"success": True}
    solver._initial_mood_refresh_rooms = set()
    solver.run.side_effect = MowerExit
    main = maintenance.main
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    main.simulate(None)
    assert len(solver.tasks) == 1
    assert solver.tasks[0] is pending
    solver.run.assert_called_once()


@pytest.mark.parametrize(
    "major_hours,delay_hours,threshold", [(11, 3, 0.8), (13, 1, 0.65)]
)
def test_manual_flash_preserves_official_major_threshold_and_its_wakeup(
    maintenance, monkeypatch, major_hours, delay_hours, threshold
):
    from arknights_mower.utils.csleep import MowerExit

    flash = update_task(maintenance, minutes=180)
    announced = MaintenanceInfo(
        maintenance.clock.now() + timedelta(hours=major_hours),
        maintenance.clock.now() + timedelta(hours=major_hours + 6),
        "major",
        "版本更新停机维护公告",
        "",
        "announced-major",
    )
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: announced)
    monkeypatch.setattr(maintenance.module.config.conf, "resting_threshold", 0.65)
    monkeypatch.setattr(
        maintenance.module.config.conf, "version_update_resting_threshold", 0.8
    )
    monkeypatch.setattr(
        maintenance.module.config.conf, "version_update_threshold_advance_hours", 12
    )
    solver = Mock()
    pending = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    solver.tasks = [pending, flash]
    solver.initialize_operators.return_value = None
    solver.op_data.validate_backup_plans.return_value = {"success": True}
    solver.op_data.config = SimpleNamespace(resting_threshold=0.65)
    solver._initial_mood_refresh_rooms = set()
    solver.run.side_effect = MowerExit
    solver.recog.update.side_effect = AssertionError("unexpected main-loop failure")
    main = maintenance.main
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    timer = Mock()
    monkeypatch.setattr(main, "Timer", timer)
    monkeypatch.setattr(main, "_maintenance_timer", None)
    monkeypatch.setattr(main, "_maintenance_timer_key", None)
    main.simulate(None)
    assert solver.op_data.config.resting_threshold == threshold
    assert timer.call_args.args[0] == delay_hours * 3600
    solver.run.assert_called_once()
    assert solver.tasks == [pending, flash]
