"""手动维护复用公告维护的避让、副表和等待流程，不访问设备或网络。"""

import pickle
from datetime import timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import ANY, Mock

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
    find_next_task,
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


@pytest.mark.parametrize(
    "kind,duration",
    [(kind, duration) for kind in MAINTENANCE_TASK_TYPES for duration in (None, 25)]
    + [(TaskTypes.SERVER_UPDATE, 0)],
)
@pytest.mark.parametrize("legacy_name", [False, True])
def test_authenticated_route_creates_window_without_roster_and_wakes(
    maintenance, monkeypatch, kind, duration, legacy_name
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
            "task_type": ("闪断更新" if kind == TaskTypes.FLASH_UPDATE else "停服更新")
            if legacy_name
            else kind.display_value,
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
    expected_duration = 10 if duration is None else duration
    assert task.duration_minutes == expected_duration
    assert task.maintenance_mode == "prepare"
    assert maintenance.module.config.wake_scheduler.is_set()
    assert maintenance.module.config.maintenance_recheck.is_set()
    result = client.get("/task", headers={"token": "test-token"}).json[0]
    assert str(expected_duration) in result["display_name"]
    assert result["display_name"].startswith(kind.display_value)
    assert result["duration_minutes"] == expected_duration
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


@pytest.mark.parametrize("elapsed", [0, 4, 5, 9, 10])
def test_manual_flash_waits_to_exact_end_without_probe_or_stopping(
    maintenance, monkeypatch, elapsed
):
    update = update_task(maintenance, minutes=0)
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
            (10 - elapsed) * 60, allow_wakeup=False, cancelled=ANY
        )
    else:
        solver._idle_sleep.assert_not_called()
    assert not maintenance.main._flash_probe_ids
    stop.assert_not_called()
    assert not maintenance.module.config.stop_mower.is_set()


@pytest.mark.parametrize("kind", [TaskTypes.FLASH_UPDATE, TaskTypes.SERVER_UPDATE])
@pytest.mark.parametrize("immediate", [False, True])
def test_prepared_update_finishes_advanced_work_before_pausing(
    maintenance, kind, immediate
):
    solver = maintenance.solver
    update = update_task(maintenance, kind=kind, minutes=0 if immediate else 60)
    order = SchedulerTask(
        update.time + timedelta(minutes=4),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
    )
    swap = SchedulerTask(
        update.time + timedelta(minutes=6), task_type=TaskTypes.SWAP_SUPPORT
    )
    solver.tasks.extend([order, swap])
    if not immediate:
        scheduling(solver.tasks, time_now=maintenance.clock.now())
    maintenance.clock.current = update.time
    solver._idle_sleep = Mock()
    solver.handle_idle_action = Mock()
    original_start = update.time

    assert (
        maintenance.main._handle_maintenance(update.maintenance_info, solver) is False
    )
    solver._idle_sleep.assert_not_called()
    assert not maintenance.module.config.stop_mower.is_set()
    assert update.maintenance_preparation_pending
    assert order.time < original_start
    assert swap.time <= original_start

    # 失败保留原任务；暂停任务不占派发位置，无关工作仍可执行。
    order.execution_failure = {"reason": "controlled device failure"}
    solver.tasks.remove(swap)
    unrelated = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    solver.tasks.append(unrelated)
    snapshot = [(id(task), task.time) for task in solver.tasks]
    for _ in range(3):
        assert (
            maintenance.main._handle_maintenance(update.maintenance_info, solver)
            is False
        )
        assert find_next_task(solver.tasks, op_data=solver.op_data) is unrelated
        assert [(id(task), task.time) for task in solver.tasks] == snapshot
    solver._idle_sleep.assert_not_called()

    # 原班恢复也是同一次跑单的剩余工作，完成后才交接暂停。
    order.run_order_restore_pending = True
    order.run_order_original_roster = {"room_1_1": ["鸿雪"]}
    del order.execution_failure
    assert (
        maintenance.main._handle_maintenance(update.maintenance_info, solver) is False
    )
    solver._idle_sleep.assert_not_called()
    solver.tasks.remove(order)
    result = maintenance.main._handle_maintenance(update.maintenance_info, solver)
    assert not update.maintenance_preparation_pending
    assert update.time == original_start
    if kind == TaskTypes.FLASH_UPDATE:
        assert result is False
        solver._idle_sleep.assert_called_once_with(
            600, allow_wakeup=False, cancelled=ANY
        )
    else:
        assert isinstance(result, MaintenanceInfo)
        assert maintenance.module.config.stop_mower.is_set()


def test_direct_pause_does_not_wait_for_advanced_work(maintenance):
    update = update_task(maintenance, mode="pause", minutes=0)
    order = SchedulerTask(update.time, task_type=TaskTypes.RUN_ORDER)
    order.maintenance_start = update.time
    maintenance.solver.tasks.append(order)
    maintenance.solver._idle_sleep = Mock()
    maintenance.solver.handle_idle_action = Mock()
    maintenance.main._handle_maintenance(update.maintenance_info, maintenance.solver)
    maintenance.solver._idle_sleep.assert_called_once_with(
        600, allow_wakeup=False, cancelled=ANY
    )
    assert order in maintenance.solver.tasks


@pytest.mark.parametrize("kind", [TaskTypes.FLASH_UPDATE, TaskTypes.SERVER_UPDATE])
def test_prepared_update_waits_for_support_handoff_without_orders(maintenance, kind):
    update = update_task(maintenance, kind=kind)
    swap = SchedulerTask(
        update.time + timedelta(minutes=5), task_type=TaskTypes.SWAP_SUPPORT
    )
    solver = maintenance.solver
    solver.tasks.append(swap)
    scheduling(solver.tasks, time_now=maintenance.clock.now())
    maintenance.clock.current = update.time
    solver._idle_sleep = Mock()
    solver.handle_idle_action = Mock()
    assert (
        maintenance.main._handle_maintenance(update.maintenance_info, solver) is False
    )
    assert update.maintenance_preparation_pending
    assert find_next_task(solver.tasks, op_data=solver.op_data) is swap
    solver._idle_sleep.assert_not_called()
    assert not maintenance.module.config.stop_mower.is_set()
    solver.tasks.remove(swap)
    result = maintenance.main._handle_maintenance(update.maintenance_info, solver)
    if kind == TaskTypes.FLASH_UPDATE:
        solver._idle_sleep.assert_called_once_with(
            600, allow_wakeup=False, cancelled=ANY
        )
    else:
        assert isinstance(result, MaintenanceInfo)


def test_overdue_flash_keeps_preparation_until_completion_without_new_pause(
    maintenance,
):
    update = update_task(maintenance, minutes=60)
    order = SchedulerTask(
        update.time + timedelta(minutes=4),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
    )
    solver = maintenance.solver
    solver.tasks.append(order)
    scheduling(solver.tasks, time_now=maintenance.clock.now())
    solver._idle_sleep = Mock()
    solver.handle_idle_action = Mock()
    maintenance.clock.current = update.time
    assert (
        maintenance.main._handle_maintenance(update.maintenance_info, solver) is False
    )
    maintenance.clock.current += timedelta(minutes=20)
    (restored,) = pickle.loads(pickle.dumps([update]))
    assert restored.maintenance_info.active_at(maintenance.clock.now())
    assert update.maintenance_info in NewsChecker.get_manual_maintenances()
    assert (
        maintenance.main._handle_maintenance(update.maintenance_info, solver) is False
    )
    assert update.time == restored.time
    solver.tasks.remove(order)
    assert (
        maintenance.main._handle_maintenance(update.maintenance_info, solver) is False
    )
    solver._idle_sleep.assert_not_called()


@pytest.mark.parametrize("elapsed", [0, 4, 9])
def test_manual_server_stops_and_returns_exact_restart_time(
    maintenance, monkeypatch, elapsed
):
    from arknights_mower.solvers import record

    update = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=0)
    maintenance.clock.current += timedelta(minutes=elapsed)
    save = Mock(return_value=True)
    monkeypatch.setattr(record, "save_current_state", save)
    maintenance.solver._idle_sleep = Mock()
    maintenance.solver.handle_idle_action = Mock()
    info = maintenance.main._handle_maintenance(
        update.maintenance_info, maintenance.solver
    )
    assert info == update.maintenance_info
    assert info.end == update.time + timedelta(minutes=10)
    save.assert_not_called()
    assert maintenance.module.config.stop_mower.is_set()
    maintenance.solver._idle_sleep.assert_not_called()
    maintenance.solver.handle_idle_action.assert_not_called()
    maintenance.io.assert_not_called()


def test_startup_server_update_returns_restart_before_device_initialization(
    maintenance, monkeypatch
):
    update = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=-4)
    main = maintenance.main
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", ())
    monkeypatch.setattr(main, "_arm_maintenance_timer", Mock())
    monkeypatch.setattr(main.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(main, "simulate", Mock())
    monkeypatch.setattr(
        main, "csleep", Mock(side_effect=AssertionError("server downtime must stop"))
    )
    result = main._main({"tasks": [update]})
    assert result == update.maintenance_info
    assert maintenance.module.config.stop_mower.is_set()
    main.rapidocr.initialize_ocr.assert_not_called()
    main.simulate.assert_not_called()
    main.csleep.assert_not_called()


@pytest.mark.parametrize("server_minutes", [0, 5])
def test_overlapping_flash_hands_control_to_server_stop_at_its_start(
    maintenance, monkeypatch, server_minutes
):
    flash = update_task(maintenance, minutes=-1)
    server = update_task(
        maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=server_minutes
    )
    main = maintenance.main
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", ())
    monkeypatch.setattr(main, "_arm_maintenance_timer", Mock())
    monkeypatch.setattr(main.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(main, "simulate", Mock())
    sleep = Mock(
        side_effect=lambda seconds: setattr(
            maintenance.clock,
            "current",
            maintenance.clock.now() + timedelta(seconds=seconds),
        )
    )
    monkeypatch.setattr(main, "csleep", sleep)
    result = main._main({"tasks": [flash, server]})
    assert result == server.maintenance_info
    assert maintenance.clock.now() == server.time
    assert maintenance.module.config.stop_mower.is_set()
    main.rapidocr.initialize_ocr.assert_not_called()
    main.simulate.assert_not_called()
    assert sleep.call_count == (1 if server_minutes else 0)


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
    assert Operators.major_maintenance_remaining_hours(data) == 0.0


@pytest.mark.parametrize(
    "kind,duration",
    [(kind, 35) for kind in MAINTENANCE_TASK_TYPES] + [(TaskTypes.SERVER_UPDATE, 0)],
)
def test_restored_update_preserves_duration_mode_and_original_timestamp(
    maintenance, kind, duration
):
    task = update_task(maintenance, kind=kind)
    task.duration_minutes = duration
    (restored,) = pickle.loads(pickle.dumps([task]))
    maintenance.solver.tasks = [restored]
    assert restored.time == task.time
    assert restored.type is kind
    assert restored.type.value == (
        "flash_update" if kind == TaskTypes.FLASH_UPDATE else "server_update"
    )
    assert (
        restored.maintenance_info.announcement_id
        == task.maintenance_info.announcement_id
    )
    assert restored.duration_minutes == duration
    assert restored.maintenance_info.restart_after_update == (duration > 0)
    assert restored.maintenance_mode == "prepare"
    assert restored.maintenance_info in NewsChecker.get_manual_maintenances()
    assert replan_update_tasks({"tasks": [restored]})["tasks"][0] is restored


@pytest.mark.parametrize("elapsed", [0, 4])
def test_zero_duration_startup_consumes_only_shutdown_task_and_saves_before_exit(
    maintenance, monkeypatch, elapsed
):
    from arknights_mower.solvers import record

    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=-elapsed)
    task.duration_minutes = 0
    pending = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    saved = {"tasks": [task, pending], "other_state": "preserved"}
    main = maintenance.main
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", ())
    monkeypatch.setattr(main, "_arm_maintenance_timer", Mock())
    monkeypatch.setattr(main.rapidocr, "initialize_ocr", Mock())
    monkeypatch.setattr(main, "simulate", Mock())
    write = Mock(return_value=True)
    monkeypatch.setattr(record, "save_state_to_db", write)
    result = main._main(saved)
    assert result == task.maintenance_info
    assert not result.restart_after_update
    main._save_manual_update_state(result, saved)
    write.assert_called_once_with({"tasks": [pending], "other_state": "preserved"})
    main.rapidocr.initialize_ocr.assert_not_called()
    main.simulate.assert_not_called()
    assert maintenance.module.config.stop_mower.is_set()


def test_managed_instance_rejects_zero_duration_without_process_permission(
    maintenance, monkeypatch
):
    from arknights_mower.utils import managed_device
    from arknights_mower.views import task as route

    app = Flask(__name__)
    app.token = "test-token"
    app.register_blueprint(route.task_bp)
    monkeypatch.setattr(route, "mower_thread", Mock(is_alive=Mock(return_value=True)))
    monkeypatch.setattr(managed_device, "extra_settings_allowed", lambda _: False)
    result = app.test_client().post(
        "/task",
        json={
            "task": {
                "time": "2026-10-01T03:00:00.000Z",
                "plan": {},
                "task_type": "停服更新",
                "meta_data": "",
                "duration_minutes": 0,
            }
        },
        headers={"token": "test-token"},
    )
    assert "多开管理器" in result.text
    assert maintenance.solver.tasks == []
    assert not maintenance.module.config.wake_scheduler.is_set()


def test_zero_duration_failed_snapshot_keeps_shutdown_task_for_manual_recovery(
    maintenance, monkeypatch
):
    from arknights_mower.solvers import record

    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=0)
    task.duration_minutes = 0
    pending = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    saved = {"tasks": [task, pending]}
    monkeypatch.setattr(maintenance.main, "base_scheduler", None)
    monkeypatch.setattr(record, "save_state_to_db", Mock(return_value=False))
    with pytest.raises(RuntimeError, match="保存任务状态失败"):
        maintenance.main._save_manual_update_state(task.maintenance_info, saved)
    assert saved["tasks"] == [task, pending]


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
    assert not maintenance.module.config.stop_mower.is_set()
    assert maintenance.module.config.maintenance_recheck.is_set()


@pytest.mark.parametrize("duration", [0, 10])
def test_manual_server_update_activates_and_exits_the_existing_backup(
    maintenance, backup_solver, monkeypatch, duration
):
    from arknights_mower.utils import operators

    monkeypatch.setattr(operators, "datetime", maintenance.clock)
    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=20)
    task.duration_minutes = duration
    backup_solver.backup_plan_solver()
    assert backup_solver.op_data.plan_condition == [True]
    assert backup_solver.op_data.run_order_paused
    maintenance.clock.current = task.maintenance_info.end
    if duration == 0:
        maintenance.solver.tasks.remove(task)
    backup_solver.backup_plan_solver()
    assert backup_solver.op_data.plan_condition == [False]
    assert not backup_solver.op_data.run_order_paused


@pytest.mark.parametrize("duration", [0, 10])
def test_due_server_update_waits_for_actual_backup_shift_before_stopping(
    maintenance, backup_solver, monkeypatch, duration
):
    from arknights_mower.utils import operators

    monkeypatch.setattr(operators, "datetime", maintenance.clock)
    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=0)
    task.duration_minutes = duration
    backup_solver.tasks = [task]
    monkeypatch.setattr(maintenance.main, "base_scheduler", backup_solver)
    # 没有跑单替班时，直接经过原有的维护副表换班流程。
    for op in backup_solver.op_data.operators.values():
        op.replacement = []
    assert (
        maintenance.main._handle_maintenance(task.maintenance_info, backup_solver)
        is False
    )
    assert backup_solver.op_data.plan_condition == [True]
    shifts = [
        pending
        for pending in backup_solver.tasks
        if pending.meta_data == "副表内存收敛"
    ]
    assert shifts
    assert task.maintenance_preparation_pending
    assert (
        find_next_task(backup_solver.tasks, op_data=backup_solver.op_data) is not task
    )
    snapshot = [(id(pending), pending.time) for pending in backup_solver.tasks]
    for _ in range(3):
        assert (
            maintenance.main._handle_maintenance(task.maintenance_info, backup_solver)
            is False
        )
        assert [
            (id(pending), pending.time) for pending in backup_solver.tasks
        ] == snapshot
        assert not maintenance.module.config.stop_mower.is_set()

    # 切表任务失败时保留原停止任务，并让无关的可执行任务继续调度。
    for shift in shifts:
        shift.execution_failure = {"reason": "controlled device failure"}
    # 消费切表流程附带的普通规划唤醒，再检查无关任务的调度。
    backup_solver.tasks[:] = [task, *shifts]
    unrelated = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    backup_solver.tasks.append(unrelated)
    assert (
        maintenance.main._handle_maintenance(task.maintenance_info, backup_solver)
        is False
    )
    assert (
        find_next_task(backup_solver.tasks, op_data=backup_solver.op_data) is unrelated
    )
    assert task.time == maintenance.clock.now()

    # 模拟设备边界确认已完成换班并移除任务，下一次检查才允许停止。
    backup_solver.tasks[:] = [task, unrelated]
    backup_solver.maintenance_entry_pending = False
    result = maintenance.main._handle_maintenance(task.maintenance_info, backup_solver)
    assert isinstance(result, MaintenanceInfo)
    assert not task.maintenance_preparation_pending
    assert maintenance.module.config.stop_mower.is_set()
    assert unrelated in backup_solver.tasks


def test_pending_server_preparation_survives_overdue_cleanup_and_snapshot(maintenance):
    task = update_task(maintenance, kind=TaskTypes.SERVER_UPDATE, minutes=-20)
    task.maintenance_preparation_pending = True
    stale = SchedulerTask(task.time, task_type=TaskTypes.SHIFT_OFF)
    unrelated = SchedulerTask(maintenance.clock.now(), task_type=TaskTypes.MAIL)
    maintenance.solver.tasks.extend([stale, unrelated])
    maintenance.solver.handle_error(True)
    assert task in maintenance.solver.tasks
    assert task.maintenance_info in NewsChecker.get_manual_maintenances()
    (restored,) = pickle.loads(pickle.dumps([task]))
    assert restored.time == task.time
    assert restored.maintenance_preparation_pending
    assert restored.maintenance_info.active_at(maintenance.clock.now())
    assert find_next_task([task, unrelated]) is unrelated


@pytest.mark.parametrize("kind", [TaskTypes.FLASH_UPDATE, TaskTypes.SERVER_UPDATE])
def test_overdue_preparation_survives_cleanup_until_actual_completion(
    maintenance, kind
):
    env = maintenance
    update = update_task(env, kind=kind)
    order = SchedulerTask(
        update.time + timedelta(minutes=4),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
    )
    env.solver.tasks.append(order)
    scheduling(env.solver.tasks, time_now=env.clock.now())
    env.clock.current = update.time + timedelta(minutes=6)
    env.solver._idle_sleep = Mock()
    env.solver.handle_idle_action = Mock()
    original_time, original_plan = order.time, dict(order.plan)
    assert env.main._handle_maintenance(update.maintenance_info, env.solver) is False
    stale = SchedulerTask(env.clock.now() - timedelta(minutes=20))
    unrelated = SchedulerTask(
        env.clock.now() + timedelta(minutes=1), task_type=TaskTypes.MAIL
    )
    env.solver.tasks.extend([stale, unrelated])
    assert order.time < env.clock.now() - timedelta(minutes=15)
    for _ in range(3):
        assert (
            env.main._handle_maintenance(update.maintenance_info, env.solver) is False
        )
        env.solver.handle_error(True)
        assert sum(task is order for task in env.solver.tasks) == 1
        assert order.time == original_time and order.plan == original_plan
        assert order.maintenance_start == update.time
        assert update.maintenance_preparation_pending
        assert unrelated in env.solver.tasks and stale not in env.solver.tasks
        assert find_next_task(env.solver.tasks) is order
        env.solver._idle_sleep.assert_not_called()
        assert not env.module.config.stop_mower.is_set()
    order.execution_failure = {"reason": "unchanged observation"}
    assert find_next_task(env.solver.tasks) is unrelated
    assert env.main._handle_maintenance(update.maintenance_info, env.solver) is False
    del order.execution_failure
    assert find_next_task(env.solver.tasks) is order
    env.solver.tasks.remove(order)
    info = update.maintenance_info
    result = env.main._handle_maintenance(info, env.solver)
    assert not update.maintenance_preparation_pending
    if kind == TaskTypes.SERVER_UPDATE:
        assert result is info
        assert env.module.config.stop_mower.is_set()
    else:
        assert result is False
        env.solver._idle_sleep.assert_called_once_with(
            240, allow_wakeup=False, cancelled=ANY
        )
    assert unrelated in env.solver.tasks
    env.io.assert_not_called()


@pytest.mark.parametrize("startup", [False, True])
def test_manual_flash_hands_control_to_official_major_at_its_start(
    maintenance, monkeypatch, startup
):
    env, main = maintenance, maintenance.main
    flash = update_task(env, mode="pause", minutes=0)
    announced = MaintenanceInfo(
        flash.time + timedelta(minutes=5),
        flash.time + timedelta(hours=6),
        "major",
        "版本更新停机维护公告",
        "",
        "official-major",
    )
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: announced)
    monkeypatch.setattr(main, "Timer", Mock())
    monkeypatch.setattr(main, "_maintenance_timer", None)
    monkeypatch.setattr(main, "_maintenance_timer_key", None)
    stop = Mock(side_effect=lambda info: env.module.config.stop_mower.set())
    monkeypatch.setattr(main, "_stop_for_major_update", stop)

    def sleep(seconds, **kwargs):
        env.clock.current += timedelta(seconds=seconds)

    monkeypatch.setattr(main, "csleep", sleep)
    env.solver.handle_idle_action = Mock()
    env.solver._idle_sleep = Mock(side_effect=sleep)
    if startup:
        monkeypatch.setattr(main, "base_scheduler", None)
        monkeypatch.setattr(main.rapidocr, "initialize_ocr", Mock())
        monkeypatch.setattr(main, "simulate", Mock())
        assert main._main({"tasks": [flash]}) is True
        main.rapidocr.initialize_ocr.assert_not_called()
        main.simulate.assert_not_called()
    else:
        assert main._handle_maintenance(flash.maintenance_info, env.solver) is True
        assert flash in env.solver.tasks
    assert env.clock.now() == announced.start
    stop.assert_called_once_with(announced)
    assert env.module.config.stop_mower.is_set()
    assert main.get_manual_pause() is None
    env.io.assert_not_called()


def test_started_official_major_preempts_pending_manual_preparation(
    maintenance, monkeypatch
):
    env = maintenance
    flash = update_task(env, minutes=0)
    announced = MaintenanceInfo(
        flash.time,
        flash.time + timedelta(hours=6),
        "major",
        "版本更新停机维护公告",
        "",
        "official-major",
    )
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: announced)
    stop = Mock()
    monkeypatch.setattr(env.main, "_stop_for_major_update", stop)
    env.solver._prepare_manual_maintenance = Mock(return_value=False)
    assert env.main._handle_maintenance(flash.maintenance_info, env.solver) is True
    stop.assert_called_once_with(announced)
    env.solver._prepare_manual_maintenance.assert_not_called()
    assert flash in env.solver.tasks
    env.io.assert_not_called()


def test_pending_manual_server_timer_keeps_later_official_stop(
    maintenance, monkeypatch
):
    env, main = maintenance, maintenance.main
    task = update_task(env, kind=TaskTypes.SERVER_UPDATE, minutes=1)
    announced = MaintenanceInfo(
        task.time + timedelta(minutes=5),
        task.time + timedelta(hours=6),
        "major",
        "版本更新停机维护公告",
        "",
        "official-major",
    )
    monkeypatch.setattr(main, "Timer", Mock(side_effect=lambda *args: Mock()))
    monkeypatch.setattr(main, "_maintenance_timer", None)
    monkeypatch.setattr(main, "_maintenance_timer_key", None)
    stop = Mock()
    monkeypatch.setattr(main, "_stop_for_major_update", stop)
    main._arm_maintenance_timer(
        task.maintenance_info,
        major_info=task.maintenance_info,
        announced_info=announced,
    )
    assert main.Timer.call_args.args[0] == 60
    env.clock.current = task.time
    main.Timer.call_args.args[1]()
    assert main.Timer.call_args.args[0] == 300
    env.clock.current = announced.start
    main.Timer.call_args.args[1]()
    stop.assert_called_once_with(announced)
    env.io.assert_not_called()


@pytest.mark.parametrize("threshold_during_flash", [False, True])
def test_flash_timer_and_cancellation_preserve_official_stop(
    maintenance, monkeypatch, threshold_during_flash
):
    from arknights_mower.utils.csleep import MowerExit

    env, main = maintenance, maintenance.main
    flash = update_task(env, mode="pause", minutes=1)
    announced = MaintenanceInfo(
        flash.time + timedelta(minutes=5),
        flash.time + timedelta(hours=6),
        "major",
        "版本更新停机维护公告",
        "",
        "official-major",
    )
    monkeypatch.setattr(NewsChecker, "get_maintenance", lambda: announced)
    monkeypatch.setattr(
        env.module.config.conf,
        "version_update_threshold_advance_hours",
        3 / 60 if threshold_during_flash else 1,
    )
    timer = Mock(side_effect=lambda *args: Mock())
    monkeypatch.setattr(main, "Timer", timer)
    monkeypatch.setattr(main, "_maintenance_timer", None)
    monkeypatch.setattr(main, "_maintenance_timer_key", None)
    stop = Mock(side_effect=lambda info: env.module.config.stop_mower.set())
    monkeypatch.setattr(main, "_stop_for_major_update", stop)
    main._arm_maintenance_timer(announced)
    original_timer = main._maintenance_timer
    main._arm_maintenance_timer(flash.maintenance_info, major_info=announced)
    original_timer.cancel.assert_called_once()
    assert timer.call_args.args[0] == 60
    flash_callback = timer.call_args.args[1]
    env.clock.current = flash.time
    flash_callback()
    assert timer.call_args.args[0] == (120 if threshold_during_flash else 300)
    calls = timer.call_count
    flash_callback()
    assert timer.call_count == calls

    def cancel(seconds):
        assert main.cancel_manual_pause(flash.maintenance_info.announcement_id)
        raise MowerExit

    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "_startup_maintenance_tasks", env.solver.tasks)
    monkeypatch.setattr(main, "csleep", cancel)
    assert main._handle_maintenance(flash.maintenance_info, None) is False
    assert flash not in env.solver.tasks
    if threshold_during_flash:
        env.clock.current = announced.start - timedelta(minutes=3)
        timer.call_args.args[1]()
        assert timer.call_args.args[0] == 180
    env.clock.current = announced.start
    timer.call_args.args[1]()
    stop.assert_called_once_with(announced)
    assert env.module.config.stop_mower.is_set()
    env.io.assert_not_called()


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


@pytest.mark.parametrize("preparation_pending", [False, True])
def test_startup_waits_through_overlapping_manual_windows_before_initializing(
    maintenance, monkeypatch, preparation_pending
):
    main = maintenance.main
    first = update_task(maintenance, minutes=0)
    second = update_task(maintenance, minutes=5)
    first.maintenance_preparation_pending = preparation_pending
    second.maintenance_preparation_pending = preparation_pending
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
    assert first.maintenance_preparation_pending is preparation_pending
    assert second.maintenance_preparation_pending is preparation_pending


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


@pytest.mark.parametrize("kind", [TaskTypes.FLASH_UPDATE, TaskTypes.SERVER_UPDATE])
def test_main_dispatches_preparation_before_due_manual_pause(
    maintenance, monkeypatch, kind
):
    from arknights_mower.utils.csleep import MowerExit

    task = update_task(maintenance, kind=kind, minutes=0)
    task.duration_minutes = 0 if kind == TaskTypes.SERVER_UPDATE else 10
    task.maintenance_preparation_pending = True
    shift = SchedulerTask(
        maintenance.clock.now(), {"room_1_1": ["但书"]}, TaskTypes.SELF_CORRECTION
    )
    solver = Mock()
    solver.tasks = [task, shift]
    solver.initialize_operators.return_value = None
    solver.op_data.validate_backup_plans.return_value = {"success": True}
    solver._initial_mood_refresh_rooms = set()
    solver._prepare_manual_maintenance.return_value = False
    solver.run.side_effect = MowerExit
    main = maintenance.main
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    main.simulate(None)
    solver._prepare_manual_maintenance.assert_called_once_with(task.maintenance_info)
    solver.run.assert_called_once()
    assert task in solver.tasks
    assert not maintenance.module.config.stop_mower.is_set()


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
