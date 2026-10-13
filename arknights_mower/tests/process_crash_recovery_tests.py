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
    return SimpleNamespace(main=main, server=server, record=record, io=forbidden)


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
    assert client.post("/crash-recovery/resume", json={}).status_code in (404, 405)
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
