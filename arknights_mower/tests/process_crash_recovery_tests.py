"""Offline HTTP, observation and SQLite boundaries for native process exits."""

import importlib
import pickle
import socket
import subprocess
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from threading import Event, RLock, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from arknights_mower.utils import config, crash_recovery
from arknights_mower.utils import instance_supervisor as supervisor
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes


@pytest.fixture
def offline(monkeypatch, tmp_path):
    forbidden = Mock(side_effect=AssertionError("live device/network/process I/O"))
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    main = importlib.import_module("arknights_mower.__main__")
    server = importlib.import_module("server")
    record = importlib.import_module("arknights_mower.solvers.record")
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    monkeypatch.setattr(config, "conf", config.Conf())
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config, "maintenance_recheck", Event())
    monkeypatch.setattr(config, "save_conf", lambda: None)
    monkeypatch.setattr(server.app, "token", "crash-test", raising=False)
    monkeypatch.setattr(server, "mower_thread", None)
    monkeypatch.setattr(server, "active_job", lambda: None)
    monkeypatch.setattr(server, "shutdown", SimpleNamespace(closing=False))
    monkeypatch.setattr(main, "base_scheduler", None)
    monkeypatch.setattr(record, "_tables_created", False)
    monkeypatch.setattr(
        record,
        "get_path",
        lambda value: tmp_path / ("data.db" if value.endswith("data.db") else ""),
    )
    inventory_changed = record.workshop_inventory_changed
    was_changed = inventory_changed.is_set()
    inventory_changed.clear()
    try:
        yield SimpleNamespace(main=main, server=server, record=record, io=forbidden)
    finally:
        if was_changed:
            inventory_changed.set()
        else:
            inventory_changed.clear()


@pytest.fixture
def notice(monkeypatch, tmp_path):
    monkeypatch.setattr(crash_recovery, "_cancelled", False)
    monkeypatch.setattr(crash_recovery, "_progress", {})
    monkeypatch.setenv("MOWER_SUPERVISOR_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("MOWER_RECOVERY_RUN", "1")
    path = tmp_path / "recovery.json"
    runtime.write_json(
        path,
        {
            "active": True,
            "phase": "waiting",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "message": "主实例意外退出，等待核实",
            "exit_code": 23,
        },
    )
    return path


def pending_tasks():
    now = datetime.now()
    original = SchedulerTask(
        now - timedelta(minutes=1),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
    )
    original.run_order_original_roster = {"room_1_1": ["鸿雪"]}
    future = SchedulerTask(
        now + timedelta(hours=2),
        {"central": ["夕"]},
        TaskTypes.WORKSHOP,
        "explicit appointment",
    )
    return original, future


def test_automatic_prepare_preserves_all_saved_tasks_without_dispositions(notice):
    original, future = pending_tasks()
    original.run_order_restore_pending = True
    saved = {"tasks": [original, future]}
    prepared = crash_recovery.prepare_resume(saved)
    assert prepared["tasks"] == [original, future]
    assert prepared["tasks"][0] is original and prepared["tasks"][1] is future
    assert original.run_order_restore_pending
    assert original.run_order_original_roster == {"room_1_1": ["鸿雪"]}
    assert prepared["_process_crash_recovery"]
    assert not prepared["_process_crash_no_snapshot"]
    assert crash_recovery.status()["automatic"]


def test_ordinary_start_after_stop_checks_pending_state_without_clearing_tasks(
    offline, notice, observed_scheduler, monkeypatch, tmp_path
):
    original, future = pending_tasks()
    observed_scheduler.tasks = [original, future]
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        snapshot = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    assert offline.server._stop_mower()
    assert crash_recovery.status()["active"]
    assert not crash_recovery.status()["automatic"]
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    assert offline.server._start_mower("0")
    resumed = create.call_args.kwargs["args"][0]
    assert resumed["_process_crash_recovery"]
    assert resumed["tasks"][0].run_order_original_roster == {"room_1_1": ["鸿雪"]}
    assert resumed["tasks"][1].time == future.time
    assert crash_recovery.status()["startup"] is True
    assert crash_recovery.status()["automatic"]
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == snapshot
        )
    offline.io.assert_not_called()


def test_corrupt_notice_never_overwrites_original(notice):
    notice.write_text("{broken", encoding="utf-8")
    original = notice.read_bytes()
    crash_recovery.failed()
    crash_recovery.snapshot_failed()
    assert notice.read_bytes() == original
    assert crash_recovery.status()["active"] and crash_recovery.status()["automatic"]
    with pytest.raises(RuntimeError):
        crash_recovery.begin()
    assert notice.read_bytes() == original


def test_http_recovery_status_is_read_only_and_has_no_manual_resume(
    offline, notice, monkeypatch
):
    read = Mock()
    monkeypatch.setattr(offline.server, "load_state", read)
    client = offline.server.app.test_client()
    assert client.get("/crash-recovery/status").status_code == 403
    response = client.get("/crash-recovery/status", headers={"token": "crash-test"})
    assert response.status_code == 200 and response.json["automatic"]
    assert client.post(
        "/crash-recovery/resume", headers={"token": "crash-test"}, json={}
    ).status_code in (404, 405)
    assert (
        "resume_allowed" not in response.json and "uncertain_tasks" not in response.json
    )
    read.assert_not_called()


def test_stop_keeps_automatic_retry_cancelled_despite_report_failure(
    offline, notice, monkeypatch
):
    monkeypatch.setattr(
        supervisor, "task_intent", Mock(side_effect=OSError("disk full"))
    )
    assert offline.server._stop_mower()
    assert config.stop_mower.is_set() and crash_recovery.status()["active"]
    assert not crash_recovery.status()["automatic"]
    assert not offline.server._retry_after_process_crash()
    offline.io.assert_not_called()


def test_stop_cancels_resume_published_by_start_already_holding_lock(
    offline, notice, monkeypatch, tmp_path
):
    monkeypatch.delenv("MOWER_SUPERVISOR_INTENT", raising=False)
    monkeypatch.setattr(offline.server, "maa_maintenance_lock", RLock())
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(offline.server, "load_state", Mock(return_value={}))
    monkeypatch.setattr(offline.server, "_cancel_scheduled_start", Mock())
    worker = Mock()
    worker.is_alive.return_value = False
    monkeypatch.setattr(offline.server, "Thread", Mock(return_value=worker))
    observed, proceed, stop_cancelled = Event(), Event(), Event()
    original_status, original_cancel = crash_recovery.status, crash_recovery.cancel
    starts, stops, errors = [], [], []

    def status():
        value = original_status()
        if not observed.is_set():
            observed.set()
            assert proceed.wait(5), "Start must resume after Stop cancels recovery"
        return value

    def cancel():
        original_cancel()
        stop_cancelled.set()

    monkeypatch.setattr(crash_recovery, "status", status)
    monkeypatch.setattr(crash_recovery, "cancel", cancel)

    def start():
        try:
            starts.append(offline.server._start_mower("0"))
        except BaseException as error:
            errors.append(error)

    def stop():
        try:
            stops.append(offline.server._stop_mower(timeout=5))
        except BaseException as error:
            errors.append(error)

    starter, stopper = Thread(target=start), Thread(target=stop)
    starter.start()
    try:
        assert observed.wait(5), (
            "Start must read the active notice while holding the lock"
        )
        stopper.start()
        assert stop_cancelled.wait(5), (
            "Stop must cancel before waiting for Start's lock"
        )
    finally:
        proceed.set()
        starter.join(5)
        if stopper.ident is not None:
            stopper.join(5)
    assert not starter.is_alive() and not stopper.is_alive() and not errors
    assert starts == [True] and stops == [True]
    assert config.stop_mower.is_set()
    assert crash_recovery.cancelled()
    assert runtime.read_json(notice)["resume_requested"] is False
    assert not crash_recovery.status()["automatic"]
    assert not offline.server._retry_after_process_crash()
    worker.start.assert_called_once()
    offline.io.assert_not_called()


def test_start_report_failure_rolls_back_unstarted_worker(
    offline, monkeypatch, tmp_path
):
    monkeypatch.delenv("MOWER_SUPERVISOR_DIRECTORY", raising=False)
    monkeypatch.setattr(offline.server, "active_job", lambda: None)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(
        supervisor, "task_intent", Mock(side_effect=OSError("disk full"))
    )
    thread = Mock()
    monkeypatch.setattr(offline.server, "Thread", Mock(return_value=thread))
    with pytest.raises(OSError):
        offline.server._start_mower("2")
    thread.start.assert_not_called()
    assert offline.server.mower_thread is None
    assert config.stop_mower.is_set()
    assert offline.server._stop_mower()


@pytest.fixture
def observed_scheduler(offline, monkeypatch):
    base = importlib.import_module("arknights_mower.solvers.base_schedule")
    from arknights_mower.utils.plan import Plan, PlanConfig, Room

    solver = object.__new__(base.BaseSchedulerSolver)
    solver.global_plan = {
        "default_plan": Plan(
            {
                "central": [Room("夕", "感知", ["诗怀雅"])],
                "contact": [Room("絮雨", "感知", ["斥罪"])],
                "dormitory_1": [
                    Room("塑心", "感知", ["隐德来希"]),
                    *[Room("Free", "", []) for _ in range(4)],
                ],
            },
            PlanConfig("", "", "", resting_threshold=0.65),
        ),
        "backup_plans": [],
    }
    assert solver.initialize_operators() is None
    solver.tasks, solver.task = [], None
    solver.recog = Mock(gray=np.zeros((1080, 1920), dtype=np.uint8))
    solver.back_to_infrastructure = Mock()
    solver.enter_room, solver.back = Mock(), Mock()
    solver.emergency_state = None
    solver.party_time = None
    solver.task_count = 7
    today = datetime.now().date()
    for daily in ("daily_visit_friend", "daily_report", "daily_skland", "daily_mail"):
        setattr(solver, daily, today)
    solver.defer_backup_plan_until_mood_read = False
    solver._initial_mood_refresh_rooms = set()
    monkeypatch.setattr(offline.main, "base_scheduler", solver)
    return solver


def test_actual_checkpoint_roundtrip_keeps_receipts_appointments_and_compensation(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    original, future = pending_tasks()
    original.plan = {"central": ["夕"]}
    original.run_order_original_roster = {"central": ["夕"]}
    original.run_order_restore_pending = True
    prepared = crash_recovery.prepare_resume({"tasks": [original, future]})
    solver.tasks = prepared["tasks"]
    readings = []

    def read(room, **kwargs):
        assert kwargs == {"force_mood": True, "strict_observation": True}
        assert crash_recovery.status()["active"]
        readings.append(room)
        for index, planned in enumerate(solver.op_data.plan[room]):
            if planned.agent in solver.op_data.operators:
                op = solver.op_data.operators[planned.agent]
                op.current_room, op.current_index = room, index
                op.time_stamp, op.mood = datetime.now(), 20

    solver._read_room_mood = read
    crash_recovery.begin()
    crash_recovery.reconcile_scheduler(solver)
    loaded = offline.record.load_state(strict=True)
    assert not crash_recovery.status()["active"]
    assert set(readings) == set(solver.op_data.plan)
    assert loaded["tasks"][0].run_order_restore_pending
    assert loaded["tasks"][1].time == future.time
    assert loaded["operators"]["夕"].current_room == "central"
    assert loaded["operators"]["夕"].mood == 20
    offline.io.assert_not_called()


@pytest.mark.parametrize("start", ["reset", "recovery"])
def test_zero_working_mood_does_not_interrupt_observation_checkpoint(
    offline, notice, observed_scheduler, start
):
    solver = observed_scheduler
    solver.op_data.plan = {
        room: solver.op_data.plan[room] for room in ("central", "contact")
    }
    pending = SchedulerTask(datetime.now() + timedelta(hours=1), {}, TaskTypes.DEPOT)
    solver.tasks = [pending]
    target = solver.op_data.operators["夕"]
    offline.record.save_agent_action(
        target.name,
        "central",
        "central",
        True,
        target.group,
        1,
        current_time=datetime.now() - timedelta(hours=1),
    )
    current_room = None

    def enter(room):
        nonlocal current_room
        current_room = room

    solver.enter_room = Mock(side_effect=enter)
    solver.leifeng_mode = True
    solver.turn_on_room_detail = Mock()
    solver.refresh_facility_state = Mock()
    solver.detect_product_complete = Mock(return_value=None)
    solver.find = Mock(return_value=None)
    solver.read_screen = Mock(
        side_effect=lambda *a, **kw: "夕" if current_room == "central" else "絮雨"
    )
    solver.read_accurate_mood = Mock(
        side_effect=lambda *a, **kw: 0 if current_room == "central" else 20
    )
    solver.read_time = Mock(return_value=3009)
    if start == "reset":
        crash_recovery.checkpoint_reset(solver)
    else:
        crash_recovery.reconcile_scheduler(solver)
        assert not crash_recovery.status()["active"]
    assert [call.args[0] for call in solver.enter_room.call_args_list] == [
        "central",
        "contact",
    ]
    assert solver.tasks == [pending]
    assert solver.tasks[0] is pending
    loaded = offline.record.load_state(strict=True)
    assert loaded["tasks"][0].time == pending.time
    assert loaded["operators"]["夕"].current_room == "central"
    assert loaded["operators"]["夕"].mood == 0
    assert loaded["operators"]["絮雨"].mood == 20
    assert offline.record._fetchall(
        "SELECT mood FROM agent_action WHERE name = ?", "夕"
    ) == [(1,), (0,)]
    solver.read_time.assert_called_once()
    offline.io.assert_not_called()


@pytest.mark.parametrize("mode", ["0", "1", "2"])
def test_explicit_recovery_start_preserves_the_selected_mode(
    offline, notice, observed_scheduler, monkeypatch, tmp_path, mode
):
    observed_scheduler.tasks = list(pending_tasks())
    observed_scheduler.op_data.operators["夕"].mood = 17
    assert offline.record.save_current_state()
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    client = offline.server.app.test_client()
    response = client.get(f"/start/{mode}", headers={"token": "crash-test"})
    assert response.status_code == 200 and response.data == b"true"
    saved = create.call_args.kwargs["args"][0]
    assert saved["_process_crash_recovery"]
    assert len(saved["tasks"]) == (2 if mode == "0" else 0)
    assert saved["_process_crash_no_snapshot"] == (mode == "2")
    if mode != "2":
        assert saved["operators"]["夕"].mood == 17
    else:
        assert "operators" not in saved
    worker.start.assert_called_once()
    offline.io.assert_not_called()


def test_explicit_reset_bypasses_corrupt_snapshot_and_retains_mode_after_failure(
    offline, notice, monkeypatch, tmp_path
):
    with offline.record._conn() as connection:
        connection.execute("INSERT INTO saved_state VALUES ('now', ?)", (b"corrupt",))
        connection.commit()
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    client = offline.server.app.test_client()
    response = client.get("/start/2", headers={"token": "crash-test"})
    assert response.status_code == 200 and response.data == b"true"
    saved = create.call_args.kwargs["args"][0]
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("observation unavailable"))
    )
    offline.server._run_mower_worker(saved)
    assert offline.server._retry_after_process_crash()
    retried = create.call_args.kwargs["args"][0]
    assert retried["_process_crash_no_snapshot"] and retried["tasks"] == []
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == b"corrupt"
        )
    offline.io.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["observation", "checkpoint", "cancel", "unknown_room"]
)
def test_failed_reconciliation_never_clears_pause_or_pending_intent(
    offline, notice, observed_scheduler, monkeypatch, failure
):
    solver = observed_scheduler
    future = SchedulerTask(
        datetime.now() + timedelta(hours=2), {"central": ["夕"]}, TaskTypes.WORKSHOP
    )
    solver.tasks = [future]

    def read(*args, **kwargs):
        if failure == "observation":
            raise RuntimeError("OCR failed")
        if failure == "cancel":
            config.stop_mower.set()

    solver._read_room_mood = read
    if failure == "checkpoint":
        monkeypatch.setattr(offline.record, "save_current_state", lambda: False)
    if failure == "unknown_room":
        future.run_order_original_roster = {"room_1_1": ["鸿雪"]}
    crash_recovery.begin()
    with pytest.raises((RuntimeError, MowerExit)):
        crash_recovery.reconcile_scheduler(solver)
    crash_recovery.failed()
    assert (
        crash_recovery.status()["active"]
        and crash_recovery.status()["phase"] == "waiting"
    )
    assert solver.tasks == [future]
    offline.io.assert_not_called()


def test_strict_sqlite_load_distinguishes_absent_corrupt_and_invalid_snapshot(offline):
    assert offline.record.load_state(strict=True) is None
    for blob in (
        b"unpicklable",
        pickle.dumps(["not a state"]),
        pickle.dumps({}),
        pickle.dumps({"tasks": []}),
    ):
        with offline.record._conn() as connection:
            connection.execute("DELETE FROM saved_state")
            connection.execute("INSERT INTO saved_state VALUES ('now', ?)", (blob,))
            connection.commit()
        with pytest.raises((ValueError, pickle.UnpicklingError)):
            offline.record.load_state(strict=True)
    offline.io.assert_not_called()


@pytest.mark.parametrize(
    "blob",
    [
        b"broken",
        pickle.dumps({}),
        pickle.dumps({"tasks": []}),
        pickle.dumps(["wrong type"]),
    ],
)
def test_actual_sqlite_bad_snapshot_exposes_pause_and_preserves_original_blob(
    offline, notice, monkeypatch, blob
):
    with offline.record._conn() as connection:
        connection.execute("INSERT INTO saved_state VALUES ('now', ?)", (blob,))
        connection.commit()
    launch = Mock()
    monkeypatch.setattr(offline.server, "_start_mower", launch)
    client = offline.server.app.test_client()
    headers = {"token": "crash-test"}
    with pytest.raises((ValueError, pickle.UnpicklingError)):
        offline.server._retry_after_process_crash()
    status = client.get("/crash-recovery/status", headers=headers)
    assert status.status_code == 200
    assert status.json["active"] and status.json["automatic"]
    assert "暂时无法完整读取" in status.json["message"]
    launch.assert_not_called()
    with offline.record._conn() as connection:
        assert connection.execute("SELECT state FROM saved_state").fetchone()[0] == blob


def test_actual_sqlite_no_row_allows_only_explicit_observation_path(
    offline, notice, monkeypatch
):
    assert offline.record.load_state(strict=True) is None
    launch = Mock(return_value=True)
    monkeypatch.setattr(offline.server, "_start_mower", launch)
    assert offline.server._retry_after_process_crash()
    saved = launch.call_args.kwargs["recovery_state"]
    assert saved["_process_crash_no_snapshot"] and saved["_process_crash_recovery"]
    assert saved["tasks"] == []
    assert (
        crash_recovery.status()["active"]
        and crash_recovery.status()["phase"] == "observing"
    )


def configure_simulate(offline, monkeypatch, solver):
    solver._state_restore_complete = False
    monkeypatch.setattr(offline.main, "initialize", Mock(return_value=solver))
    monkeypatch.setattr(offline.main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(
        offline.main, "_apply_version_update_resting_threshold", lambda *args: None
    )
    solver.initialize_operators = Mock(return_value=None)
    solver.op_data.validate_backup_plans = Mock(return_value={"success": True})


@pytest.mark.parametrize("checkpoint_failure", [False, True])
def test_queue_reset_start_keeps_mode_until_its_first_checkpoint(
    offline, notice, observed_scheduler, monkeypatch, tmp_path, checkpoint_failure
):
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    observed_scheduler.tasks = list(pending_tasks())
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    assert offline.server._start_mower("1")
    saved = create.call_args.kwargs["args"][0]
    assert saved["tasks"] == []
    assert crash_recovery.pending_start_type() == "1"
    configure_simulate(offline, monkeypatch, observed_scheduler)
    if checkpoint_failure:
        monkeypatch.setattr(offline.record, "save_current_state", lambda: False)
        with pytest.raises(RuntimeError, match="清空任务后的状态暂未保存"):
            offline.main.simulate(saved)
        assert crash_recovery.pending_start_type() == "1"
        with offline.record._conn() as connection:
            assert (
                connection.execute("SELECT state FROM saved_state").fetchone()[0]
                == original
            )
    else:

        def dispatch():
            assert crash_recovery.pending_start_type() is None
            assert offline.record.load_state(strict=True)["tasks"] == []
            raise MowerExit

        monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", dispatch)
        offline.main.simulate(saved)
        crash_recovery.activate("later independent failure")
        assert not crash_recovery.status()["active"]
        assert crash_recovery.pending_start_type() is None
    offline.io.assert_not_called()


@pytest.mark.parametrize("replacement", ["restart_resume", "apply_schedule", "update"])
@pytest.mark.parametrize("user_requested", [False, True])
def test_user_stop_after_job_admission_overrides_captured_running_state(
    offline, monkeypatch, tmp_path, replacement, user_requested
):
    import os

    from arknights_mower.utils import process_control, software_update_worker

    state = tmp_path / "state"
    job_id = "accepted-replacement"
    record = {
        "id": "owned",
        "kind": "instance",
        "pid": os.getpid(),
        "running": True,
        "space": "owned-space",
        "name": "owned-instance",
        "port": 59998,
        "executable": "owned-python",
        "argv": ["owned-desktop.py"],
        "cwd": str(tmp_path),
    }
    runtime.write_json(state / "active/owner.json", {"id": job_id, "pid": os.getpid()})
    runtime.write_json(state / "instances/owned.json", record)
    monkeypatch.setattr(runtime, "state_dir", lambda: state)
    if user_requested:
        response = offline.server.app.test_client().get(
            "/stop", headers={"token": "crash-test"}
        )
        assert response.data == b"true"
    else:
        with offline.server.app.test_request_context(headers={"token": "crash-test"}):
            assert offline.server.stop(user_requested=False) == "true"
    assert runtime.task_stop_requested(record, job_id, state) is user_requested
    create = Mock(return_value=Mock(poll=lambda: None))
    monkeypatch.setattr(software_update_worker.subprocess, "Popen", create)
    if replacement == "update":
        worker = object.__new__(software_update_worker.Worker)
        worker.state, worker.work = state, tmp_path / "work"
        worker.work.mkdir()
        worker.root = tmp_path
        worker.job = {"id": job_id, "background": False, "deployment": "release"}
        worker.report = Mock()
        worker.restart([record], verify=False)
    else:
        job_path = tmp_path / "control/job.json"
        runtime.write_json(
            job_path,
            {
                "id": job_id,
                "action": replacement,
                "record": record,
                "state_dir": str(state),
                "frozen": False,
            },
        )
        monkeypatch.setattr(runtime, "process_alive", lambda pid: False)
        monkeypatch.setattr(
            runtime,
            "instances",
            lambda *args, **kwargs: [
                {
                    **record,
                    "ready": True,
                    "restart_job": job_id,
                }
            ],
        )
        process_control.execute(job_path)
        assert (
            runtime.read_json(job_path.parent / "status.json")["status"] == "succeeded"
        )
    environment = create.call_args.kwargs["env"]
    assert environment["MOWER_RESUME_RUN"] == ("0" if user_requested else "1")
    if user_requested:
        assert environment.get("MOWER_RESUME_MODE") not in ("0", "1")
    assert record["running"] is True
    offline.io.assert_not_called()


def test_process_control_stop_waits_for_guardian_release(
    offline, monkeypatch, tmp_path
):
    from arknights_mower.utils import process_control

    state = tmp_path / "update-state"
    job_path = tmp_path / "control/job.json"
    record = {
        "id": "owned",
        "pid": 1,
        "supervision_directory": str(tmp_path / "guardian"),
    }
    runtime.write_json(
        job_path,
        {
            "id": "stop-owned",
            "action": "stop",
            "record": record,
            "state_dir": str(state),
        },
    )
    monkeypatch.setattr(runtime, "process_alive", lambda pid: False)
    released = []

    def wait(recorded, deadline):
        assert recorded == record
        assert (state / "shutdown/owned.json").exists()
        released.append(recorded)

    monkeypatch.setattr(runtime, "wait_for_supervisor_release", wait)
    process_control.execute(job_path)
    assert released == [record]
    assert runtime.read_json(job_path.parent / "status.json")["status"] == "succeeded"
    offline.io.assert_not_called()


def test_updater_waits_for_each_owned_guardian_before_installation(
    offline, monkeypatch, tmp_path
):
    from arknights_mower.utils import software_update_worker as update

    worker = object.__new__(update.Worker)
    worker.state, worker.work, worker.job = (
        tmp_path / "state",
        tmp_path / "work",
        {"id": "update"},
    )
    worker.report = Mock()
    records = [
        {"kind": "instance", "id": "a", "pid": 1},
        {"kind": "instance", "id": "b", "pid": 2},
    ]
    monkeypatch.setattr(update, "instances", lambda state: records)
    monkeypatch.setattr(update, "process_alive", lambda pid: False)
    released = []

    def wait(recorded, deadline):
        assert worker.stopped == records
        assert all(
            (worker.state / "shutdown" / f"{item['id']}.json").exists()
            for item in records
        )
        released.append(recorded)

    monkeypatch.setattr(update, "wait_for_supervisor_release", wait)
    worker.stop_instances()
    assert released == records
    offline.io.assert_not_called()


def test_production_simulate_observes_and_checkpoints_before_dispatch(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    future = SchedulerTask(
        datetime.now() + timedelta(hours=2), {"central": ["夕"]}, TaskTypes.WORKSHOP
    )
    solver.tasks = [future]
    saved = offline.record.current_state()
    prepared = crash_recovery.prepare_resume(saved)
    configure_simulate(offline, monkeypatch, solver)
    solver._read_room_mood = Mock()
    after_boundary = Mock()

    def dispatch_boundary():
        after_boundary()
        assert not crash_recovery.status()["active"]
        loaded = offline.record.load_state(strict=True)
        assert any(
            task.time == future.time and task.type == future.type
            for task in loaded["tasks"]
        )
        assert solver._read_room_mood.call_count == len(solver.op_data.plan)
        raise MowerExit

    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", dispatch_boundary)
    crash_recovery.begin()
    offline.main.simulate(prepared)
    after_boundary.assert_called_once()
    offline.io.assert_not_called()


@pytest.mark.parametrize("failure_at", ["navigation", "room"])
def test_observation_device_failure_recovers_same_scheduler_before_dispatch(
    offline, notice, observed_scheduler, monkeypatch, failure_at
):
    solver = observed_scheduler
    future = pending_tasks()[1]
    solver.tasks = [future]
    saved = offline.record.current_state()
    assert offline.record.save_state_to_db(saved)
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    prepared = crash_recovery.prepare_resume(saved)
    retained = []
    configure_simulate(offline, monkeypatch, solver)
    fault = DeviceRecoveryError("设备连接暂时中断")
    calls = []

    def fail_once(*args, **kwargs):
        calls.append(args)
        if len(calls) == 1:
            raise fault

    solver._read_room_mood = Mock()
    if failure_at == "navigation":
        solver.back_to_infrastructure = Mock(side_effect=fail_once)
    else:
        solver._read_room_mood.side_effect = fail_once

    def recover(scheduler, error):
        assert scheduler is solver and error is fault
        retained.append(solver.tasks[0])
        assert retained[0].time == future.time
        assert not solver._state_restore_complete
        assert crash_recovery.status()["active"]
        with offline.record._conn() as connection:
            assert (
                connection.execute("SELECT state FROM saved_state").fetchone()[0]
                == original
            )

    recovery = Mock(side_effect=recover)
    monkeypatch.setattr(offline.main, "_resume_device_dispatch", recovery)

    def dispatch():
        assert not crash_recovery.status()["active"]
        assert solver._state_restore_complete
        assert solver.tasks[0] is retained[0] and retained[0].time == future.time
        loaded = offline.record.load_state(strict=True)
        assert loaded["tasks"][0].time == future.time
        assert solver._read_room_mood.call_count >= len(solver.op_data.plan)
        raise MowerExit

    boundary = Mock(side_effect=dispatch)
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", boundary)
    crash_recovery.begin()

    offline.main.simulate(prepared)

    recovery.assert_called_once_with(solver, fault)
    offline.main.initialize.assert_called_once()
    boundary.assert_called_once()
    offline.io.assert_not_called()


def test_stop_during_observation_device_recovery_keeps_checkpoint_and_pending_tasks(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    solver.tasks = list(pending_tasks())
    saved = offline.record.current_state()
    assert offline.record.save_state_to_db(saved)
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    prepared = crash_recovery.prepare_resume(saved)
    configure_simulate(offline, monkeypatch, solver)
    fault = DeviceRecoveryError("设备连接暂时中断")
    solver.back_to_infrastructure = Mock(side_effect=fault)
    solver._read_room_mood = Mock()

    def stop(*args):
        config.stop_mower.set()
        crash_recovery.cancel()
        raise MowerExit

    recovery = Mock(side_effect=stop)
    monkeypatch.setattr(offline.main, "_resume_device_dispatch", recovery)
    boundary = Mock()
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", boundary)
    crash_recovery.begin()

    offline.main.simulate(prepared)

    recovery.assert_called_once_with(solver, fault)
    boundary.assert_not_called()
    solver._read_room_mood.assert_not_called()
    assert solver.tasks == prepared["tasks"] and not solver._state_restore_complete
    assert crash_recovery.status()["active"]
    assert not crash_recovery.status()["automatic"]
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == original
        )
    offline.io.assert_not_called()


def test_production_simulate_partial_restore_keeps_pause_before_observation(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    saved = offline.record.current_state()
    saved["operators"] = {"夕": SimpleNamespace(group="", mood=20)}
    prepared = crash_recovery.prepare_resume(saved)
    configure_simulate(offline, monkeypatch, solver)
    observed = Mock()
    monkeypatch.setattr(crash_recovery, "reconcile_scheduler", observed)
    crash_recovery.begin()
    with pytest.raises(AttributeError):
        offline.main.simulate(prepared)
    observed.assert_not_called()
    crash_recovery.failed()
    assert crash_recovery.status()["active"]
    offline.io.assert_not_called()


@pytest.mark.parametrize(
    "name,mood", [("", 20), ("夕", -1), ("夕", float("nan")), ("夕", 25)]
)
def test_strict_actual_room_reader_rejects_ambiguous_slot_or_invalid_mood(
    offline, observed_scheduler, monkeypatch, name, mood
):
    solver = observed_scheduler
    solver.turn_on_room_detail = Mock()
    solver.detect_product_complete = Mock(return_value=None)
    solver.find = Mock(return_value=None)
    solver.read_screen = Mock(return_value=name)
    solver.read_accurate_mood = Mock(return_value=mood)
    solver.sleep = Mock()
    from arknights_mower.utils.recognize import RecognizeError

    with pytest.raises(RecognizeError):
        solver.get_agent_from_room("central", force_mood=True, strict_observation=True)
    if name == "":
        assert solver.read_screen.call_count == 3
    offline.io.assert_not_called()


def test_stop_during_restore_preserves_the_only_saved_queue(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    solver.tasks = list(pending_tasks())
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    prepared = crash_recovery.prepare_resume(offline.record.load_state(strict=True))
    solver.tasks = []
    configure_simulate(offline, monkeypatch, solver)

    def stop_before_restore():
        client = offline.server.app.test_client()
        response = client.get("/stop", headers={"token": "crash-test"})
        assert response.status_code == 200 and response.data == b"true"
        raise MowerExit

    solver.initialize_operators.side_effect = stop_before_restore
    with pytest.raises(MowerExit):
        offline.main.simulate(prepared)
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == original
        )
    assert not crash_recovery.status()["automatic"]
    offline.io.assert_not_called()


def isolate_main_run(offline, monkeypatch):
    monkeypatch.setattr(
        offline.main,
        "device_control",
        SimpleNamespace(run=lambda **kwargs: nullcontext()),
    )
    monkeypatch.setattr(offline.main, "resource_task_session", nullcontext)
    monkeypatch.setattr(offline.main, "_close_device_session", Mock())
    monkeypatch.setattr(offline.main, "_cancel_maintenance_timer", Mock())


def test_later_worker_failure_saves_compensation_after_successful_recovery(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    prepared = crash_recovery.prepare_resume(offline.record.current_state())
    configure_simulate(offline, monkeypatch, solver)
    isolate_main_run(offline, monkeypatch)
    monkeypatch.setattr(offline.main, "_main", offline.main.simulate)
    solver._read_room_mood = Mock()
    compensation, future = pending_tasks()

    def later_failure():
        assert not crash_recovery.status()["active"]
        solver.tasks.extend([compensation, future])
        raise RuntimeError("later task failure")

    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", later_failure)
    monkeypatch.setattr(
        offline.main,
        "_resume_device_dispatch",
        Mock(side_effect=RuntimeError("later task failure")),
    )
    crash_recovery.begin()
    with pytest.raises(RuntimeError, match="later task failure"):
        offline.main.main(prepared)
    loaded = offline.record.load_state(strict=True)
    assert len(loaded["tasks"]) == 2
    assert (
        loaded["tasks"][0].run_order_original_roster
        == compensation.run_order_original_roster
    )
    assert loaded["tasks"][1].time == future.time
    offline.io.assert_not_called()


def test_failed_in_process_observation_does_not_save_unverified_positions(
    offline, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    solver._state_restore_complete = True
    operator = solver.op_data.operators["夕"]
    operator.current_room, operator.current_index = "central", 0
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    isolate_main_run(offline, monkeypatch)
    solver._read_room_mood = Mock(side_effect=RuntimeError("observation failed"))
    monkeypatch.setattr(
        offline.main, "_main", lambda saved: crash_recovery.observe_scheduler(solver)
    )
    with pytest.raises(RuntimeError, match="observation failed"):
        offline.main.main({})
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == original
        )
    offline.io.assert_not_called()


@pytest.mark.parametrize(
    "rejection", ["worker_still_running", "resource_update_running"]
)
def test_rejected_recovery_start_preserves_stop_and_selected_mode(
    offline, notice, monkeypatch, rejection
):
    crash_recovery.cancel()
    original = notice.read_bytes()
    intent = Mock()
    monkeypatch.setattr(supervisor, "task_intent", intent)
    worker = Mock()
    worker.is_alive.return_value = rejection == "worker_still_running"
    monkeypatch.setattr(offline.server, "mower_thread", worker)
    monkeypatch.setattr(
        offline.server.resource_update,
        "running",
        lambda: rejection == "resource_update_running",
    )
    client = offline.server.app.test_client()
    response = client.get("/start/2", headers={"token": "crash-test"})
    assert response.status_code == 200 and response.data == b"false"
    assert crash_recovery.cancelled()
    assert notice.read_bytes() == original
    intent.assert_not_called()
    worker.start.assert_not_called()
    offline.io.assert_not_called()


def test_update_started_while_start_waits_for_lock_preserves_stop_and_mode(
    offline, notice, monkeypatch
):
    crash_recovery.cancel()
    original = notice.read_bytes()
    intent = Mock()
    monkeypatch.setattr(supervisor, "task_intent", intent)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    maintenance_lock = RLock()
    monkeypatch.setattr(offline.server, "maa_maintenance_lock", maintenance_lock)
    initial_check, update_started = Event(), Event()
    responses, errors = [], []

    def active_job():
        if not update_started.is_set():
            initial_check.set()
            return None
        return {"id": "active-replacement"}

    monkeypatch.setattr(offline.server, "active_job", active_job)

    def start():
        try:
            responses.append(
                offline.server.app.test_client().get(
                    "/start/2", headers={"token": "crash-test"}
                )
            )
        except BaseException as error:
            errors.append(error)

    starter = Thread(target=start)
    with maintenance_lock:
        starter.start()
        assert initial_check.wait(2)
        update_started.set()
    starter.join(2)
    assert not starter.is_alive() and not errors
    assert len(responses) == 1
    assert responses[0].status_code == 200 and responses[0].data == b"false"
    assert crash_recovery.cancelled()
    assert notice.read_bytes() == original
    intent.assert_not_called()
    assert offline.server.mower_thread is None
    offline.io.assert_not_called()


def test_stop_snapshot_captured_before_observation_cannot_save_partial_mutations(
    offline, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    solver._state_restore_complete = True
    operator = solver.op_data.operators["夕"]
    operator.current_room, operator.current_index = "central", 0
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    stop = offline.server._stop_mower

    def cancel_observation(*args, **kwargs):
        assert stop()
        raise MowerExit

    solver._read_room_mood = cancel_observation

    def interleaved_stop():
        with pytest.raises(MowerExit):
            crash_recovery.observe_scheduler(solver)
        return True

    monkeypatch.setattr(offline.server, "_stop_mower", interleaved_stop)
    response = offline.server.app.test_client().get(
        "/stop", headers={"token": "crash-test"}
    )
    assert response.status_code == 200 and response.data == b"true"
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == original
        )
    offline.io.assert_not_called()


def test_initial_reset_failure_cannot_reload_previous_urgent_handoff(
    offline, notice, observed_scheduler, monkeypatch, tmp_path
):
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    handoff = SchedulerTask(datetime.now(), {}, TaskTypes.EXHAUST_OFF)
    handoff.urgent_recovery_request_names = ["夕"]
    handoff.urgent_recovery_support_names = ["絮雨"]
    handoff.urgent_recovery_reserved_names = ["斥罪"]
    handoff.urgent_recovery_reserved_slots = [("dormitory_1", 1)]
    observed_scheduler.tasks = [handoff]
    observed_scheduler.waiting_group_shifts = [handoff]
    observed_scheduler.op_data.urgent_recovery_supporters = {"夕": ["絮雨"]}
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    response = offline.server.app.test_client().get(
        "/start/2", headers={"token": "crash-test"}
    )
    assert response.data == b"true"
    saved = create.call_args.kwargs["args"][0]
    assert saved == {}
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("observation unavailable"))
    )
    offline.server._run_mower_worker(saved)
    assert not offline.server._retry_after_process_crash()
    assert crash_recovery.pending_start_type() == "2"
    assert offline.server._start_mower("0")
    retried = create.call_args.kwargs["args"][0]
    assert retried == {}
    assert "urgent_recovery_supporters" not in retried
    assert "waiting_group_shifts" not in retried
    with offline.record._conn() as connection:
        assert (
            connection.execute("SELECT state FROM saved_state").fetchone()[0]
            == original
        )
    offline.io.assert_not_called()


@pytest.mark.parametrize(
    "mode,failure",
    [("0", None), ("2", None), ("2", "observation"), ("2", "checkpoint")],
)
def test_start_entry_resets_or_restores_urgent_handoff_and_protection(
    offline, notice, observed_scheduler, monkeypatch, tmp_path, mode, failure
):
    import copy

    from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
    from arknights_mower.utils.urgent_recovery import pending_urgent_reservations

    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    old = observed_scheduler
    handoff = SchedulerTask(datetime.now(), {}, TaskTypes.EXHAUST_OFF)
    handoff.urgent_recovery_request_names = ["夕"]
    handoff.urgent_recovery_support_names = ["絮雨"]
    handoff.urgent_recovery_reserved_names = ["斥罪"]
    handoff.urgent_recovery_reserved_slots = [("dormitory_1", 1)]
    old.tasks = [handoff]
    old.waiting_group_shifts = [handoff]
    old.op_data.urgent_recovery_supporters = {"夕": ["絮雨"]}
    assert offline.record.save_current_state()
    with offline.record._conn() as connection:
        original = connection.execute("SELECT state FROM saved_state").fetchone()[0]
    fresh = object.__new__(BaseSchedulerSolver)
    fresh.__dict__.update(old.__dict__)
    fresh.global_plan = copy.deepcopy(old.global_plan)
    fresh.tasks, fresh.task, fresh.waiting_group_shifts = [], None, []
    fresh.op_data = None
    monkeypatch.setattr(offline.main, "initialize", lambda *a, **kw: fresh)
    monkeypatch.setattr(offline.main.NewsChecker, "get_maintenance", lambda: None)
    monkeypatch.setattr(
        offline.main, "_apply_version_update_resting_threshold", lambda *a: None
    )
    monkeypatch.setattr(
        offline.main, "refresh_resource_at_boundary", Mock(side_effect=MowerExit)
    )
    reads = []

    def read(room, **kwargs):
        reads.append(room)
        for index, planned in enumerate(fresh.op_data.plan[room]):
            if planned.agent in fresh.op_data.operators:
                op = fresh.op_data.operators[planned.agent]
                op.current_room, op.current_index = room, index
                op.time_stamp, op.mood = datetime.now(), 17

    fresh._read_room_mood = (
        Mock(side_effect=RuntimeError("observation failed"))
        if failure == "observation"
        else read
    )
    if failure == "checkpoint":
        monkeypatch.setattr(offline.record, "save_current_state", lambda: False)
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    response = offline.server.app.test_client().get(
        f"/start/{mode}", headers={"token": "crash-test"}
    )
    assert response.data == b"true"
    saved = create.call_args.kwargs["args"][0]
    if failure:
        with pytest.raises(RuntimeError):
            offline.main.simulate(saved)
        assert crash_recovery.reset_observation_pending()
        assert not fresh._state_restore_complete
        with offline.record._conn() as connection:
            assert (
                connection.execute("SELECT state FROM saved_state").fetchone()[0]
                == original
            )
        crash_recovery.activate("initial reset failure")
        assert not crash_recovery.status()["active"]
        assert crash_recovery.pending_start_type() == "2"
        offline.io.assert_not_called()
        return
    offline.main.simulate(saved)
    assert fresh.op_data is not old.op_data
    assert {
        room: [(slot.agent, slot.group, slot.replacement) for slot in slots]
        for room, slots in fresh.op_data.plan.items()
    } == {
        room: [(slot.agent, slot.group, slot.replacement) for slot in slots]
        for room, slots in old.op_data.plan.items()
    }
    if mode == "2":
        assert fresh.op_data.urgent_recovery_supporters == {}
        assert fresh.waiting_group_shifts == []
        assert pending_urgent_reservations(fresh.tasks) == (set(), set())
        assert set(reads) == set(fresh.op_data.plan)
        assert fresh.op_data.operators["夕"].mood == 17
        assert not crash_recovery.reset_observation_pending()
        checkpoint = offline.record.load_state(strict=True)
        assert checkpoint["urgent_recovery_supporters"] == {}
        assert checkpoint["waiting_group_shifts"] == []
        crash_recovery.activate("later unrelated worker failure")
        assert not crash_recovery.status()["active"]
        assert crash_recovery.pending_start_type() is None
    else:
        assert fresh.op_data.urgent_recovery_supporters == {"夕": ["絮雨"]}
        assert len(fresh.waiting_group_shifts) == 1
        assert pending_urgent_reservations(fresh.tasks) == (
            {"斥罪"},
            {("dormitory_1", 1)},
        )
        assert not reads
    offline.io.assert_not_called()


@pytest.mark.parametrize("failed_before_stop", [False, True])
def test_stopped_reset_still_skips_old_snapshot_on_ordinary_start(
    offline, notice, monkeypatch, tmp_path, failed_before_stop
):
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(supervisor, "task_intent", Mock())
    read = Mock(side_effect=AssertionError("pre-reset snapshot must stay unused"))
    monkeypatch.setattr(offline.server, "load_state", read)
    client = offline.server.app.test_client()
    assert client.get("/start/2", headers={"token": "crash-test"}).data == b"true"
    if failed_before_stop:
        monkeypatch.setattr(
            offline.main, "main", Mock(side_effect=RuntimeError("observation failed"))
        )
        offline.server._run_mower_worker(create.call_args.kwargs["args"][0])
    assert offline.server._stop_mower()
    assert crash_recovery.reset_observation_pending()
    assert client.get("/start/0", headers={"token": "crash-test"}).data == b"true"
    read.assert_not_called()
    assert crash_recovery.reset_observation_pending()
    saved = create.call_args.kwargs["args"][0]
    assert not saved.get("tasks")
    assert saved == {}
    offline.io.assert_not_called()
