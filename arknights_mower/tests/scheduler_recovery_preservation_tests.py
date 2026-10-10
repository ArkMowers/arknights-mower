import importlib
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import config, scheduler_task
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device import recovery
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

CRITICAL_TYPES = {
    TaskTypes.SKILL_UPGRADE,
    TaskTypes.SWAP_SUPPORT,
    TaskTypes.REFRESH_TIME,
    TaskTypes.SWITCH_PRODUCT,
    TaskTypes.FIAMMETTA,
}
FUTURE_TYPES = {
    TaskTypes.RUN_ORDER,
    TaskTypes.FURNITURE,
    TaskTypes.DEPOT,
    TaskTypes.CLUE,
    TaskTypes.WORKSHOP,
}
MANUAL_TYPES = (
    TaskTypes.FURNITURE,
    TaskTypes.DEPOT,
    TaskTypes.CLUE,
    TaskTypes.WORKSHOP,
)


@pytest.fixture
def scheduler(monkeypatch):
    forbidden_io = Mock(side_effect=AssertionError("external I/O is forbidden"))
    monkeypatch.setattr(socket.socket, "connect", forbidden_io)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden_io)
    monkeypatch.setattr(subprocess, "Popen", forbidden_io)
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    base_schedule = importlib.import_module("arknights_mower.solvers.base_schedule")
    main = importlib.import_module("arknights_mower.__main__")

    class Clock(datetime):
        current = datetime(2026, 10, 1, 10)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else cls.current.replace(tzinfo=tz)

    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.tasks = []
    solver.emergency_state = None
    solver.error = False
    solver.op_data = SimpleNamespace(
        plan={},
        operators={},
        dorm=[],
        correct_dorm=Mock(),
        validate_backup_plans=Mock(return_value={"success": True}),
    )
    solver.device = Mock()
    solver.recog = Mock()
    solver.party_time = solver.free_clue = solver.credit_fight = None
    solver.scene = Mock(return_value=base_schedule.Scene.INFRA_MAIN)
    solver.find = Mock(return_value=True)
    solver.check_current_focus = Mock()
    solver.backup_plan_solver = Mock(return_value=False)
    solver.queue_product_switches = Mock()
    solver._sync_run_order_tasks = Mock()
    solver._refresh_deferred_product_reservations = Mock()
    solver.agent_get_mood = Mock(return_value=None)
    solver.run_order_solver = Mock()
    solver.plan_solver = Mock(side_effect=solver.skip)
    solver.initialize_operators = Mock(return_value=None)
    solver.defer_backup_plan_until_mood_read = False
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    monkeypatch.setattr(config.conf, "enable_mastery", False)
    monkeypatch.setattr(base_schedule, "datetime", Clock)
    monkeypatch.setattr(scheduler_task, "datetime", Clock)
    monkeypatch.setattr(base_schedule, "save_log", Mock())
    monkeypatch.setattr(
        scheduler_task.NewsChecker, "get_update_time", Mock(return_value=(None, None))
    )
    monkeypatch.setattr(main, "base_scheduler", solver)
    return SimpleNamespace(
        solver=solver, clock=Clock, module=base_schedule, main=main, io=forbidden_io
    )


@pytest.mark.parametrize("task_type", list(TaskTypes))
@pytest.mark.parametrize(
    "offset",
    [
        timedelta(minutes=-20),
        timedelta(minutes=-15),
        timedelta(seconds=-1),
        timedelta(0),
        timedelta(microseconds=1),
        timedelta(hours=1),
    ],
)
def test_stale_cleanup_preserves_only_critical_or_future_explicit_tasks(
    scheduler, task_type, offset
):
    now = scheduler.clock.now()
    stale = SchedulerTask(now - timedelta(minutes=20), task_type=TaskTypes.SHIFT_OFF)
    pending = SchedulerTask(
        now + offset,
        {"room_1_1": ["Current", "但书"]},
        task_type,
        meta_data="pending intent",
        adjusted=True,
    )
    pending.workshop_generation = 7
    pending.workshop_recipe = {"name": "固源岩", "count": 2}
    scheduler.solver.tasks = [stale, pending]

    scheduler.solver.handle_error(True)

    retained = any(task is pending for task in scheduler.solver.tasks)
    assert retained == (
        task_type in CRITICAL_TYPES
        or (task_type in FUTURE_TYPES and offset > timedelta(0))
    )
    assert all(task is not stale for task in scheduler.solver.tasks)
    correction = scheduler.solver.tasks[-1]
    assert correction.type == TaskTypes.NOT_SPECIFIC
    assert correction.time == now
    assert correction.plan == {}
    assert len(scheduler.solver.tasks) == 1 + retained
    assert pending.time == now + offset
    assert pending.plan == {"room_1_1": ["Current", "但书"]}
    assert pending.meta_data == "pending intent"
    assert pending.adjusted is True
    assert pending.workshop_generation == 7
    assert pending.workshop_recipe == {"name": "固源岩", "count": 2}
    scheduler.io.assert_not_called()


def test_depot_mastery_dispatch_keeps_source_release_available(
    scheduler, monkeypatch, tmp_path
):
    solver, main = scheduler.solver, scheduler.main
    now = scheduler.clock.now()
    monkeypatch.setattr(config, "conf", config.Conf())
    config.conf.maa_depot_enable = True
    monkeypatch.setattr(main, "datetime", scheduler.clock)
    monkeypatch.setattr(main, "get_server_time", scheduler.clock.now)
    monkeypatch.setattr(main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    depot = tmp_path / "depotresult.csv"
    depot.touch()
    monkeypatch.setattr(main, "get_path", lambda value: depot)
    monkeypatch.setattr(
        main, "_read_depot_scan_timestamp", lambda value: int(now.timestamp()) - 86400
    )
    for daily in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, daily, now.date())
    solver.recruit_plan_solver = Mock()
    solver.mower_plan_solver = Mock()
    solver.has_maa_tasks = Mock(return_value=False)
    solver.rest_until_next_task = Mock(side_effect=MowerExit)
    solver.tasks = [SchedulerTask(now + timedelta(hours=1))]
    upgrade = SchedulerTask(now, task_type=TaskTypes.SKILL_UPGRADE)
    restore = SchedulerTask(
        now + timedelta(minutes=1),
        {"room_1_1": ["陈"]},
        TaskTypes.RUN_ORDER,
    )
    restore.run_order_original_roster = {"room_1_1": ["陈"]}
    restore.run_order_restore_pending = True
    release = SchedulerTask(now, {"room_1_2": ["银灰"]}, TaskTypes.SELF_CORRECTION)
    solver.op_data.operators = {
        "陈": SimpleNamespace(current_room="room_1_2", is_working=lambda: True)
    }

    def scan():
        solver.tasks.append(upgrade)

    solver.仓库扫描 = Mock(side_effect=scan)
    solver.find_next_task = lambda task_type: next(
        (task for task in solver.tasks if task.type == task_type), None
    )
    dispatched = []

    def run():
        if not dispatched:
            dispatched.append(upgrade)
            solver.tasks.remove(upgrade)
            solver.tasks.extend([restore, release])
            return
        dispatched.append(solver.tasks[0])
        raise MowerExit

    solver.run = Mock(side_effect=run)

    main.simulate(None)

    assert dispatched == [upgrade, release]
    assert release.time == now
    assert restore.time == now + timedelta(minutes=1)
    assert restore.run_order_original_roster == {"room_1_1": ["陈"]}
    assert restore.run_order_restore_pending
    solver.rest_until_next_task.assert_not_called()
    scheduler.io.assert_not_called()


def test_exact_fifteen_minute_boundary_does_not_rebuild_ordinary_queue(scheduler):
    now = scheduler.clock.now()
    tasks = [
        SchedulerTask(now - timedelta(minutes=15), task_type=TaskTypes.SHIFT_OFF),
        SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.SHIFT_ON),
    ]
    scheduler.solver.tasks = tasks

    scheduler.solver.handle_error(True)

    assert scheduler.solver.tasks is tasks
    assert len(tasks) == 2


def test_critical_overdue_task_does_not_trigger_ordinary_rebuild(scheduler):
    now = scheduler.clock.now()
    tasks = [
        SchedulerTask(now - timedelta(minutes=20), task_type=TaskTypes.SWAP_SUPPORT),
        SchedulerTask(now + timedelta(hours=1), task_type=TaskTypes.SHIFT_ON),
    ]
    scheduler.solver.tasks = tasks

    scheduler.solver.handle_error(True)

    assert scheduler.solver.tasks is tasks
    assert len(tasks) == 2


@pytest.mark.parametrize("manual_type", MANUAL_TYPES)
def test_real_run_preserves_manual_task_until_its_own_dispatch_time(
    scheduler, monkeypatch, manual_type
):
    now = scheduler.clock.now()
    manual = SchedulerTask(
        now + timedelta(hours=1), task_type=manual_type, meta_data="蜜莓"
    )
    gate = SchedulerTask(now + timedelta(hours=2), task_type=TaskTypes.SKILL_UPGRADE)
    stale = SchedulerTask(now - timedelta(minutes=20), task_type=TaskTypes.SHIFT_ON)
    scheduler.solver.tasks = [stale, manual, gate]
    furniture = importlib.import_module("arknights_mower.solvers.furniture")
    dispatch = Mock()
    if manual_type == TaskTypes.FURNITURE:
        monkeypatch.setattr(furniture.FurnitureDismantler, "run", dispatch)
    else:
        method = {
            TaskTypes.DEPOT: "仓库扫描",
            TaskTypes.CLUE: "_run_clue_flow",
            TaskTypes.WORKSHOP: "craft_material",
        }[manual_type]
        monkeypatch.setattr(scheduler.solver, method, dispatch)

    scheduler.solver.run()

    assert [id(task) for task in scheduler.solver.tasks] == [id(manual), id(gate)]
    scheduler.solver.agent_get_mood.assert_called_once_with(skip_dorm=True)
    scheduler.solver.run_order_solver.assert_called_once_with()
    scheduler.solver.plan_solver.assert_called_once_with()
    assert scheduler.solver.task is None
    dispatch.assert_not_called()

    scheduler.clock.current = manual.time
    scheduler.solver.run()

    dispatch.assert_called_once_with()
    assert all(task is not manual for task in scheduler.solver.tasks)
    assert any(task is gate for task in scheduler.solver.tasks)
    scheduler.io.assert_not_called()


@pytest.mark.parametrize("manual_type", MANUAL_TYPES)
@pytest.mark.parametrize("stale_type", [TaskTypes.RUN_ORDER, TaskTypes.SHIFT_OFF])
def test_real_worker_resumes_same_scheduler_and_replans_after_capture_refresh(
    scheduler, monkeypatch, manual_type, stale_type
):
    solver = scheduler.solver
    main = scheduler.main
    now = scheduler.clock.now()
    stale = SchedulerTask(now, task_type=stale_type)
    future_shift = SchedulerTask(
        now + timedelta(minutes=90), task_type=TaskTypes.SHIFT_ON
    )
    manual = SchedulerTask(
        now + timedelta(hours=1), task_type=manual_type, meta_data="蜜莓"
    )
    gate = SchedulerTask(now + timedelta(hours=2), task_type=TaskTypes.SKILL_UPGRADE)
    solver.tasks = [stale, manual, future_shift, gate]
    events = []
    ready_device = Mock()
    result = SimpleNamespace(unwrap=lambda: ready_device)

    def recover():
        if control.recover.call_count == 1:
            assert any(task is stale for task in solver.tasks)
            assert any(task is manual for task in solver.tasks)
            scheduler.clock.current += timedelta(minutes=20)
            raise recovery.DeviceRecoveryError("budget")
        return result

    control = SimpleNamespace(
        shutdown_requested=False, recover=Mock(side_effect=recover)
    )

    def scene():
        events.append("scene")
        if len(events) == 1:
            raise recovery.DeviceRecoveryError("runtime")
        assert "capture" in events
        return scheduler.module.Scene.INFRA_MAIN

    def sleep(seconds):
        scheduler.clock.current += timedelta(seconds=seconds)

    def stop_after_replanning():
        solver.skip()
        raise MowerExit

    def initialize(tasks, *, connection_retries):
        assert tasks == []
        assert connection_retries == 1
        solver.defer_backup_plan_until_mood_read = False
        return solver

    solver.scene = Mock(side_effect=scene)
    solver.recog.update = Mock(side_effect=lambda: events.append("capture"))
    solver.plan_solver = Mock(side_effect=stop_after_replanning)
    initialize_mock = Mock(side_effect=initialize)
    monkeypatch.setattr(main, "initialize", initialize_mock)
    monkeypatch.setattr(main, "device_control", control)
    monkeypatch.setattr(main, "csleep", sleep)
    monkeypatch.setattr(recovery, "csleep", sleep)
    monkeypatch.setattr(scheduler.module, "csleep", sleep)
    monkeypatch.setattr(main, "datetime", scheduler.clock)
    monkeypatch.setattr(main, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(main.NewsChecker, "get_maintenance", Mock(return_value=None))
    monkeypatch.setattr(main, "_apply_version_update_resting_threshold", Mock())
    solver._read_agent_mood = Mock()
    solver._read_initial_card_mood = Mock()
    main.simulate(None)

    initialize_mock.assert_called_once_with([], connection_retries=1)
    assert main.base_scheduler is solver
    assert solver.device is ready_device
    assert solver.recog.device is ready_device
    assert control.recover.call_count == 2
    assert events[:3] == ["scene", "capture", "scene"]
    assert any(task is manual for task in solver.tasks)
    assert any(task is gate for task in solver.tasks)
    assert all(task is not stale for task in solver.tasks)
    assert all(task is not future_shift for task in solver.tasks)
    solver.run_order_solver.assert_called_once_with()
    solver.plan_solver.assert_called_once_with()
    solver._read_initial_card_mood.assert_called_once_with()
    scheduler.io.assert_not_called()
