"""Automatic recovery retries preserve saved intent and honor cancellation."""

import copy
import sqlite3
import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

from arknights_mower.tests.process_crash_recovery_tests import (  # noqa: F401
    notice as _notice,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    observed_scheduler as _observed_scheduler,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    offline as _offline,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    pending_tasks,
)
from arknights_mower.utils import config, crash_recovery, instance_supervisor
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.touch_backend import TouchFailure
from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

notice = _notice
offline = _offline
observed_scheduler = _observed_scheduler


def test_due_adjusted_dynamic_run_order_replans_without_repeating_acceleration(
    offline, observed_scheduler
):
    solver = observed_scheduler
    due = SchedulerTask(
        datetime.now() - timedelta(minutes=1),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
        adjusted=True,
    )
    future = SchedulerTask(
        datetime.now() + timedelta(hours=2),
        {"room_1_1": ["但书"]},
        TaskTypes.RUN_ORDER,
        "room_1_1",
        adjusted=True,
    )
    solver.tasks = [due, future]
    crash_recovery.replan_dynamic_tasks(solver)
    recheck = solver.tasks[0]
    assert recheck.type == TaskTypes.REFRESH_TIME and recheck.plan == {}
    assert recheck.meta_data == "room_1_1"
    assert due.type == TaskTypes.RUN_ORDER and due.plan == {"room_1_1": ["但书"]}
    assert solver.tasks[1] is future and future.adjusted


def test_due_dynamic_run_order_keeps_saved_original_roster_compensation(
    offline, observed_scheduler
):
    solver = observed_scheduler
    due, future = pending_tasks()
    solver.tasks = [due, future]
    crash_recovery.replan_dynamic_tasks(solver)
    restore = solver.tasks[0]
    assert restore.type == TaskTypes.RUN_ORDER and restore.run_order_restore_pending
    assert restore.plan == due.run_order_original_roster and restore.meta_data == ""
    assert solver.tasks[1] is future


def test_fia_old_charging_phase_uses_fresh_mood_and_preserves_return_and_future(
    offline, observed_scheduler
):
    solver = observed_scheduler
    fia = SimpleNamespace(current_mood=lambda: 0)
    target = SimpleNamespace(current_mood=lambda: 24)
    solver.op_data.operators.update({"菲亚梅塔": fia, "夕": target})
    solver.op_data.get_dorm_by_name = Mock(
        return_value=(0, SimpleNamespace(time=datetime.now() + timedelta(hours=4)))
    )
    charging = SchedulerTask(
        datetime.now() - timedelta(minutes=1),
        {"dormitory_1": ["夕", "菲亚梅塔"]},
        TaskTypes.FIAMMETTA,
        "夕",
    )
    returning = SchedulerTask(
        datetime.now() - timedelta(seconds=1),
        {"central": ["夕"]},
        TaskTypes.FIAMMETTA,
        "",
    )
    future = SchedulerTask(
        datetime.now() + timedelta(hours=5), charging.plan, TaskTypes.FIAMMETTA, "夕"
    )
    solver.tasks = [charging, returning, future]
    crash_recovery.replan_dynamic_tasks(solver)
    planned = solver.tasks[0]
    assert (
        planned.type == TaskTypes.FIAMMETTA
        and planned.plan == {}
        and planned.meta_data == ""
    )
    assert planned.time > datetime.now()
    assert solver.tasks[1] is returning and solver.tasks[2] is future


def test_automatic_retry_keeps_saved_queue_after_transient_snapshot_error(
    offline, notice, monkeypatch
):
    original, future = pending_tasks()
    saved = {"tasks": [original, future]}
    monkeypatch.setattr(
        offline.server,
        "load_state",
        Mock(side_effect=[sqlite3.OperationalError("temporarily locked"), saved]),
    )
    received = []
    completed = threading.Event()

    def start(mode, *, recovery_state):
        received.append(recovery_state)
        crash_recovery._update(active=False, phase="resolved")
        completed.set()
        return True

    monkeypatch.setattr(offline.server, "_start_mower", start)
    runner = crash_recovery.AutomaticRecovery(
        offline.server._retry_after_process_crash,
        running=lambda: False,
        closing=lambda: False,
        delays=(0.01, 0.02),
    )
    runner.start()
    assert completed.wait(2)
    runner.close()
    assert not runner.is_alive()
    assert len(received) == 1
    assert received[0]["tasks"] == [original, future]
    assert received[0]["tasks"][0] is original and received[0]["tasks"][1] is future
    assert received[0]["_process_crash_recovery"]
    assert not crash_recovery.status()["active"]
    offline.io.assert_not_called()


def test_fia_empty_due_plan_waits_for_observed_ready_time(offline, observed_scheduler):
    solver = observed_scheduler
    solver.op_data.operators["菲亚梅塔"] = SimpleNamespace(current_mood=lambda: 0)
    ready = datetime.now() + timedelta(hours=4)
    solver.op_data.get_dorm_by_name = Mock(
        return_value=(0, SimpleNamespace(time=ready))
    )
    due = SchedulerTask(
        datetime.now() - timedelta(minutes=1), task_type=TaskTypes.FIAMMETTA
    )
    solver.tasks = [due]
    crash_recovery.replan_dynamic_tasks(solver)
    assert solver.tasks[0].time == ready and solver.tasks[0].plan == {}


def test_recovery_preserves_failed_and_reopened_tasks(offline, observed_scheduler):
    from arknights_mower.utils.dorm_candidates import retained_task_reservations
    from arknights_mower.utils.scheduler_task import find_next_task

    solver = observed_scheduler
    for kind in (TaskTypes.RUN_ORDER, TaskTypes.FIAMMETTA):
        for reopened in (False, True):
            task = SchedulerTask(
                datetime.now() - timedelta(hours=1),
                {"central": ["夕"]},
                kind,
                "room_1_1" if kind == TaskTypes.RUN_ORDER else "夕",
            )
            task.run_order_original_roster = {"central": ["夕"]}
            solver.tasks = [task]
            solver._retain_failed_task(task, "读取未核实", ["central"])
            if reopened:
                solver.op_data.room_observations["central"] = (
                    solver.op_data.room_observations.get("central", 0) + 1
                )
                solver._resume_failed_tasks()
                assert task.execution_retained
            original = copy.deepcopy(task.__dict__)
            reservations = retained_task_reservations(solver.op_data, solver.tasks)
            crash_recovery.replan_dynamic_tasks(solver)
            assert solver.tasks == [task] and solver.tasks[0] is task
            assert task.__dict__ == original
            assert (
                retained_task_reservations(solver.op_data, solver.tasks) == reservations
            )
            assert find_next_task(solver.tasks) is (task if reopened else None)
    offline.io.assert_not_called()


def test_fia_unknown_ready_time_keeps_original_roster_restoration_dispatchable(
    offline, observed_scheduler
):
    from arknights_mower.utils.scheduler_task import find_next_task

    solver = observed_scheduler
    fia = solver.op_data.operators["夕"]
    fia.mood = 0
    fia.current_room = "dormitory_1"
    solver.op_data.operators["菲亚梅塔"] = fia
    solver.op_data.get_dorm_by_name = Mock(return_value=(None, None))
    due = SchedulerTask(
        datetime.now() - timedelta(minutes=1),
        {"dormitory_1": ["夕", "菲亚梅塔"]},
        TaskTypes.FIAMMETTA,
        "夕",
    )
    due.emergency_original_roster = {"central": ["夕"]}
    solver.tasks = [due]
    crash_recovery.replan_dynamic_tasks(solver)
    returning, charging = solver.tasks
    assert returning.plan == due.emergency_original_roster
    assert returning.meta_data == "" and find_next_task(solver.tasks) is returning
    assert charging.plan == {} and charging.time == due.time
    assert charging.execution_failure
    assert not config.stop_mower.is_set()
    offline.io.assert_not_called()


def test_fia_unknown_ready_time_retains_task_until_related_observation(
    offline, observed_scheduler
):
    from arknights_mower.utils.scheduler_task import find_next_task

    solver = observed_scheduler
    fia = solver.op_data.operators["夕"]
    fia.mood = 0
    fia.current_room = "dormitory_1"
    solver.op_data.operators["菲亚梅塔"] = fia
    solver.op_data.get_dorm_by_name = Mock(return_value=(None, None))
    due = SchedulerTask(
        datetime.now() - timedelta(minutes=1), task_type=TaskTypes.FIAMMETTA
    )
    independent = SchedulerTask(datetime.now(), task_type=TaskTypes.DEPOT)
    solver.tasks = [due, independent]
    original_time = due.time
    for _ in range(3):
        crash_recovery.replan_dynamic_tasks(solver)
        solver._resume_failed_tasks()
        assert solver.tasks == [due, independent] and solver.tasks[0] is due
        assert due.time == original_time and due.plan == {}
        assert find_next_task(solver.tasks) is independent
    solver.op_data.room_observations["contact"] = 1
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is independent
    solver.op_data.room_observations["dormitory_1"] = 1
    solver.op_data.get_dorm_by_name.return_value = (
        0,
        SimpleNamespace(time=datetime.now() + timedelta(hours=4)),
    )
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is independent
    assert due.time == original_time and due.execution_failure
    fia.current_mood = Mock(return_value=24)
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is independent
    fia.mood = 24
    fia.time_stamp = None
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is independent
    fia.time_stamp = datetime.now()
    fia.mood_is_prediction = True
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is independent
    fia.mood_is_prediction = False
    solver._resume_failed_tasks()
    assert find_next_task(solver.tasks) is due
    assert not hasattr(due, "process_recovery_fia_wait")
    target = solver.op_data.operators["絮雨"]
    target.mood = 0
    solver.check_fia = Mock(return_value=(["絮雨"], "dormitory_1"))
    solver._refresh_fia_candidate_moods = Mock()
    solver._emergency_fia_fallback = Mock(return_value=None)
    solver.task = due
    solver.plan_fia()
    assert solver.tasks[-1].plan == {"dormitory_1": ["絮雨", "菲亚梅塔"]}
    assert not config.stop_mower.is_set()
    offline.io.assert_not_called()


def test_fia_saved_return_roster_is_immediate_before_next_charge(
    offline, observed_scheduler
):
    solver = observed_scheduler
    solver.op_data.operators.update(
        {
            "菲亚梅塔": SimpleNamespace(current_mood=lambda: 0),
            "夕": SimpleNamespace(current_mood=lambda: 24),
        }
    )
    ready = datetime.now() + timedelta(hours=4)
    solver.op_data.get_dorm_by_name = Mock(
        return_value=(0, SimpleNamespace(time=ready))
    )
    charging = SchedulerTask(
        datetime.now() - timedelta(minutes=1),
        {"dormitory_1": ["夕", "菲亚梅塔"]},
        TaskTypes.FIAMMETTA,
        "夕",
    )
    charging.emergency_original_roster = {"central": ["夕"]}
    solver.tasks = [charging]
    crash_recovery.replan_dynamic_tasks(solver)
    returning, next_charge = solver.tasks
    assert (
        returning.meta_data == ""
        and returning.plan == charging.emergency_original_roster
        and returning.time <= datetime.now()
    )
    assert (
        next_charge.time == ready
        and next_charge.plan == {}
        and next_charge.meta_data == ""
    )


def test_normal_python_worker_exception_activates_already_running_recovery(
    offline, notice, monkeypatch
):
    from arknights_mower.utils import update_runtime as runtime

    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    called = threading.Event()

    def recover():
        called.set()
        crash_recovery._update(active=False, phase="resolved")

    runner = crash_recovery.AutomaticRecovery(
        recover, running=lambda: False, closing=lambda: False, delays=(0.01,)
    )
    runner.start()
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("initial OCR failed"))
    )
    try:
        offline.server._run_mower_worker({})
        assert called.wait(2)
    finally:
        runner.close()
    assert not crash_recovery.status()["active"]
    offline.io.assert_not_called()


def test_new_failure_after_resolution_starts_without_previous_cooldown(
    offline, notice, monkeypatch
):
    first_resolved, inactive_seen, second_attempt = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    real_status = crash_recovery.status
    calls = []

    def observed_status():
        current = real_status()
        if first_resolved.is_set() and not current["active"]:
            inactive_seen.set()
        return current

    def attempt():
        calls.append(1)
        if len(calls) == 1:
            crash_recovery._update(active=False, phase="resolved")
            first_resolved.set()
        else:
            second_attempt.set()
            crash_recovery._update(active=False, phase="resolved")

    monkeypatch.setattr(crash_recovery, "status", observed_status)
    runner = crash_recovery.AutomaticRecovery(
        attempt, running=lambda: False, closing=lambda: False, delays=(2.0,)
    )
    runner.start()
    try:
        assert inactive_seen.wait(2)
        crash_recovery.activate("later independent failure")
        assert second_attempt.wait(1)
    finally:
        runner.close()
    assert calls == [1, 1]


def test_new_worker_failure_before_next_poll_starts_without_previous_cooldown(
    offline, notice, monkeypatch
):
    second_attempt = threading.Event()
    calls = []
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("later worker failure"))
    )

    def attempt():
        calls.append(1)
        crash_recovery.complete()
        if len(calls) == 1:
            offline.server._run_mower_worker({})
            assert crash_recovery.status()["automatic"]
        else:
            second_attempt.set()

    runner = crash_recovery.AutomaticRecovery(
        attempt, running=lambda: False, closing=lambda: False, delays=(2.0,)
    )
    runner.start()
    try:
        assert second_attempt.wait(1)
    finally:
        runner.close()
    assert calls == [1, 1]
    offline.io.assert_not_called()


def test_completed_episode_interrupts_its_cooldown_for_new_worker_failure(
    offline, notice, monkeypatch
):
    backoff, second_attempt = threading.Event(), threading.Event()
    real_failed = crash_recovery.failed
    calls = []
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("later worker failure"))
    )

    def failed(*args, **kwargs):
        real_failed(*args, **kwargs)
        if kwargs.get("attempt") == 1:
            backoff.set()

    def attempt():
        calls.append(1)
        if len(calls) == 1:
            return
        crash_recovery.complete()
        second_attempt.set()

    monkeypatch.setattr(crash_recovery, "failed", failed)
    runner = crash_recovery.AutomaticRecovery(
        attempt, running=lambda: False, closing=lambda: False, delays=(2.0,)
    )
    runner.start()
    try:
        assert backoff.wait(1)
        crash_recovery.complete()
        offline.server._run_mower_worker({})
        assert second_attempt.wait(1)
    finally:
        runner.close()
    assert calls == [1, 1]
    offline.io.assert_not_called()


def test_repeated_worker_failure_in_same_episode_keeps_retry_sequence(
    offline, notice, monkeypatch
):
    recovered = threading.Event()
    real_failed = crash_recovery.failed
    calls, backoff_attempts = [], []
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("same worker failure"))
    )

    def failed(*args, **kwargs):
        if "attempt" in kwargs:
            backoff_attempts.append(kwargs["attempt"])
        real_failed(*args, **kwargs)

    def attempt():
        calls.append(1)
        if len(calls) < 3:
            offline.server._run_mower_worker({})
        else:
            crash_recovery.complete()
            recovered.set()

    monkeypatch.setattr(crash_recovery, "failed", failed)
    runner = crash_recovery.AutomaticRecovery(
        attempt, running=lambda: False, closing=lambda: False, delays=(0.01, 0.02)
    )
    runner.start()
    try:
        assert recovered.wait(2)
    finally:
        runner.close()
    assert calls == [1, 1, 1]
    assert backoff_attempts == [1, 2]
    offline.io.assert_not_called()


def test_explicit_start_after_stop_reenables_later_worker_recovery(
    offline, notice, monkeypatch, tmp_path
):
    from arknights_mower.utils import update_runtime as runtime

    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    assert offline.server._stop_mower()
    worker = Mock()
    worker.is_alive.return_value = False
    monkeypatch.setattr(offline.server, "Thread", Mock(return_value=worker))
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    monkeypatch.setattr(instance_supervisor, "task_intent", Mock())
    assert offline.server._start_mower("2")
    assert not crash_recovery.cancelled()
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RuntimeError("new worker failure"))
    )
    offline.server._run_mower_worker({})
    assert crash_recovery.status()["automatic"]
    offline.io.assert_not_called()


def test_internal_fatal_shutdown_preserves_intent_but_user_stop_cancels(
    offline, notice, monkeypatch
):
    resources = {}
    lifecycle = SimpleNamespace(
        reason="device_recovery_failed",
        own=lambda name, close, phase: resources.update({name: close}),
        watch=lambda: None,
    )
    intent = Mock()
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)
    offline.server.register_shutdown(lifecycle)
    resources["mower worker"]()
    intent.assert_not_called()
    assert crash_recovery.status()["automatic"]
    assert offline.server._stop_mower()
    assert not crash_recovery.status()["automatic"]


def test_internal_update_resume_cannot_override_prior_stop(
    offline, notice, monkeypatch
):
    assert offline.server._stop_mower()
    thread = Mock()
    intent = Mock()
    monkeypatch.setattr(offline.server, "Thread", thread)
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)
    assert not offline.server._start_mower("0", automatic=True)
    thread.assert_not_called()
    intent.assert_not_called()
    assert config.stop_mower.is_set()


def test_stop_cancels_automatic_retry_even_without_scheduler(offline, notice):
    attempted = threading.Event()
    calls = []

    def fail():
        calls.append(1)
        attempted.set()
        raise RuntimeError("OCR unavailable")

    runner = crash_recovery.AutomaticRecovery(
        fail, running=lambda: False, closing=lambda: False, delays=(0.05,)
    )
    runner.start()
    try:
        assert attempted.wait(1)
        assert offline.server._stop_mower()
        assert not crash_recovery.status()["automatic"]
        assert crash_recovery.status()["phase"] == "stopped"
        threading.Event().wait(0.12)
        assert calls == [1]
    finally:
        runner.close()
    offline.io.assert_not_called()


def test_corrupt_recovery_record_retries_without_overwriting_original(offline, notice):
    notice.write_text("{broken", encoding="utf-8")
    original = notice.read_bytes()
    attempts = threading.Event()

    def attempt():
        attempts.set()
        crash_recovery.begin()

    runner = crash_recovery.AutomaticRecovery(
        attempt, running=lambda: False, closing=lambda: False, delays=(0.02,)
    )
    runner.start()
    try:
        assert attempts.wait(1)
        threading.Event().wait(0.08)
        assert notice.read_bytes() == original
        assert crash_recovery.status()["automatic"]
        assert crash_recovery.status()["phase"] == "waiting"
    finally:
        runner.close()


def test_stop_between_run_intent_and_thread_start_keeps_final_false(
    offline, notice, monkeypatch, tmp_path
):
    entered, released, cancelled = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    intents, errors = [], []
    worker = Mock()
    worker.is_alive.return_value = False
    monkeypatch.setattr(offline.server, "Thread", Mock(return_value=worker))
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    original_cancel = crash_recovery.cancel

    def cancel():
        original_cancel()
        cancelled.set()

    monkeypatch.setattr(crash_recovery, "cancel", cancel)

    def intent(running, **kwargs):
        intents.append(running)
        if running:
            entered.set()
            assert released.wait(2)

    monkeypatch.setattr(instance_supervisor, "task_intent", intent)

    def start():
        try:
            offline.server._start_mower(
                "0", recovery_state={"_process_crash_recovery": True}
            )
        except RuntimeError as exc:
            errors.append(exc)

    starter = threading.Thread(target=start)
    stopper = threading.Thread(target=offline.server._stop_mower)
    starter.start()
    assert entered.wait(1)
    stopper.start()
    try:
        assert cancelled.wait(1)
    finally:
        released.set()
        starter.join(2)
        stopper.join(2)
    assert not starter.is_alive() and not stopper.is_alive()
    worker.start.assert_not_called()
    assert intents[-1] is False and not crash_recovery.status()["automatic"]
    assert config.stop_mower.is_set() and errors


def test_failed_automatic_thread_start_retains_requested_intent(
    offline, notice, monkeypatch, tmp_path
):
    worker = Mock()
    worker.start.side_effect = OSError("temporary thread limit")
    monkeypatch.setattr(offline.server, "Thread", Mock(return_value=worker))
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)
    intent = Mock()
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)
    import pytest

    with pytest.raises(OSError):
        offline.server._start_mower(
            "0", recovery_state={"_process_crash_recovery": True}
        )
    assert all(call.args[0] is True for call in intent.call_args_list)
    assert crash_recovery.status()["automatic"] and offline.server.mower_thread is None


def test_uncertain_touch_rebuilds_owned_session_and_observes_before_reentry(
    offline, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    original, future = pending_tasks()
    solver.tasks = [original, future]
    solver._process_recovery_occurred_at = (
        datetime.now() - timedelta(hours=2)
    ).isoformat()
    current_failure = datetime.now()
    device = Mock()
    result = SimpleNamespace(unwrap=lambda: device)
    events = []

    def close():
        events.append("close")
        if events.count("close") == 1:
            raise DeviceRecoveryError("temporary cleanup failure")
        return result

    control = SimpleNamespace(
        shutdown_requested=False,
        close=Mock(side_effect=close),
        recover=Mock(side_effect=lambda: (events.append("recover"), result)[1]),
    )
    monkeypatch.setattr(offline.main, "device_control", control)
    monkeypatch.setattr(offline.main, "csleep", lambda seconds: None)
    from arknights_mower.utils.device import recovery

    monkeypatch.setattr(recovery, "csleep", lambda seconds: None)

    def observe(current):
        events.append("observe")
        assert current is solver and events[-2] == "recover"
        assert current.tasks == [original, future]
        crash_recovery.replan_dynamic_tasks(current)

    monkeypatch.setattr(crash_recovery, "observe_scheduler", observe)
    failure = TouchFailure(
        config.conf.device, "windows", OSError("uncertain"), delivery_unknown=True
    )
    assert offline.main._resume_device_dispatch(solver, failure) is device
    assert events == ["close", "close", "recover", "observe"]
    assert (
        datetime.fromisoformat(solver._process_recovery_occurred_at) >= current_failure
    )
    assert solver.tasks[0].run_order_restore_pending
    assert solver.tasks[0].plan == original.run_order_original_roster
    assert solver.tasks[1] is future
    solver.recog.reset_after_external_control.assert_called_once()
    offline.io.assert_not_called()


def test_unknown_workshop_stock_waits_for_observation_without_polling_tasks(
    offline, observed_scheduler
):
    from arknights_mower.data import workshop_formula
    from arknights_mower.utils import workshop_limits
    from arknights_mower.utils.config.conf import RIICPart, WorkShopItem

    config.conf.workshop_settings = [
        RIICPart.WorkShopSetting(
            operator="夕",
            items=[WorkShopItem(item_names=["碳素"], self_upper_limit=100)],
        )
    ]
    names = crash_recovery.workshop_inventory_names()
    assert names == {"碳", "碳素"}
    old = {"碳": 100, "碳素": 5}
    offline.record.save_inventory_counts(old)
    solver = observed_scheduler
    original, future = pending_tasks()
    solver.tasks = [original, future]
    solver.仓库扫描 = Mock(return_value=False)
    crash_recovery.refresh_workshop_inventory(solver)
    assert offline.record.get_inventory_counts() == {}
    assert solver.tasks[:2] == [original, future]
    assert solver.tasks == [original, future]
    solver.仓库扫描.assert_called_once()
    setting = config.conf.workshop_settings[0].items[0]
    assert (
        workshop_limits.batch_limit("碳素", workshop_formula["碳素"], setting, {}) == 0
    )
    # Only a later actual inventory source can restore known values. No task
    # completion or unknown material count is invented by process recovery.
    offline.record.save_inventory_counts(
        old, scanned_counts=old, scanned_at=10_000_000_000
    )
    assert solver.tasks == [original, future]
    assert (
        workshop_limits.batch_limit(
            "碳素",
            workshop_formula["碳素"],
            setting,
            offline.record.get_inventory_counts(),
        )
        > 0
    )
    offline.io.assert_not_called()
