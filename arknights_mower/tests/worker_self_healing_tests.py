"""工作线程故障复用任务恢复，用户停止始终优先。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.process_crash_recovery_tests import (
    configure_simulate,
    pending_tasks,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    notice as _notice,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    observed_scheduler as _observed_scheduler,
)
from arknights_mower.tests.process_crash_recovery_tests import (
    offline as _offline,
)
from arknights_mower.utils import config, crash_recovery, instance_supervisor
from arknights_mower.utils import email as mail
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.screenshot_backend import ScreenshotFailure
from arknights_mower.utils.device.touch_backend import TouchFailure
from arknights_mower.utils.recognize import RecognizeError

notice = _notice
offline = _offline
observed_scheduler = _observed_scheduler


def test_game_failure_resumes_saved_queue_with_restart_before_fresh_observation(
    offline, notice, observed_scheduler, monkeypatch, tmp_path
):
    original, future = pending_tasks()
    observed_scheduler.tasks = [original, future]
    assert offline.record.save_current_state()
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    crash_recovery.request_resume("0")
    run = Mock(side_effect=RecognizeError("startup scene unavailable"))
    monkeypatch.setattr(offline.main, "main", run)
    intent = Mock()
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)

    offline.server._run_mower_worker({})

    assert crash_recovery.status()["automatic"]
    worker = Mock()
    worker.is_alive.return_value = False
    create = Mock(return_value=worker)
    monkeypatch.setattr(offline.server, "Thread", create)
    monkeypatch.setattr(offline.server, "get_path", lambda value: tmp_path)
    monkeypatch.setattr(offline.server.resource_update, "running", lambda: False)

    assert offline.server._retry_after_process_crash()

    saved = create.call_args.kwargs["args"][0]
    assert saved["_process_crash_recovery"]
    assert saved["_restart_game"]
    assert saved["tasks"][0].run_order_original_roster == {"room_1_1": ["鸿雪"]}
    assert saved["tasks"][1].time == future.time
    assert not any(call.args[0] is False for call in intent.call_args_list)
    worker.start.assert_called_once()
    offline.io.assert_not_called()


@pytest.mark.parametrize("cancelled_by", ["stop_event", "stop_request"])
def test_user_stop_during_worker_failure_cannot_restart_or_notify(
    offline, notice, monkeypatch, cancelled_by
):
    request_exit, notify, recover = Mock(), Mock(), Mock()
    monkeypatch.setattr(
        offline.server, "shutdown", SimpleNamespace(closing=False, request=request_exit)
    )
    monkeypatch.setattr(mail, "send_message", notify)
    monkeypatch.setattr(crash_recovery, "worker_failed", recover, raising=False)

    def stopped_run(saved):
        if cancelled_by == "stop_event":
            config.stop_mower.set()
        else:
            offline.server._stop_mower()
        raise MemoryError("fault after stopping")

    monkeypatch.setattr(offline.main, "main", stopped_run)

    offline.server._run_mower_worker({})

    recover.assert_not_called()
    request_exit.assert_not_called()
    notify.assert_not_called()
    assert config.stop_mower.is_set()
    assert not crash_recovery.status()["automatic"]
    offline.io.assert_not_called()


def test_exhausted_same_failure_pauses_without_changing_user_run_intent(
    offline, notice, monkeypatch
):
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    crash_recovery.request_resume("0")
    monkeypatch.setattr(
        offline.main, "main", Mock(side_effect=RecognizeError("same scene failure"))
    )
    intent, notify, request_exit = Mock(), Mock(), Mock()
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)
    monkeypatch.setattr(mail, "send_message", notify)
    monkeypatch.setattr(
        offline.server, "shutdown", SimpleNamespace(closing=False, request=request_exit)
    )
    for _ in range(3):
        offline.server._run_mower_worker({})
        assert crash_recovery.status()["automatic"]
        crash_recovery.complete()

    offline.server._run_mower_worker({"_process_crash_recovery": True})

    current = crash_recovery.status()
    assert current["active"]
    assert not current["automatic"]
    assert current["phase"] == "failed"
    assert config.stop_mower.is_set()
    assert not crash_recovery.cancelled()
    assert not any(call.args[0] is False for call in intent.call_args_list)
    notify.assert_called_once()
    assert notify.call_args.kwargs["level"] == "ERROR"
    request_exit.assert_not_called()
    offline.io.assert_not_called()


@pytest.mark.parametrize("has_recovery_record", [False, True])
def test_memory_fault_without_supervised_child_does_not_close_http_service(
    offline, notice, monkeypatch, has_recovery_record
):
    monkeypatch.delenv("MOWER_SUPERVISOR_CHILD_REPORT", raising=False)
    monkeypatch.delenv("MOWER_SUPERVISOR_GENERATION", raising=False)
    if has_recovery_record:
        runtime.write_json(notice, {"active": False, "phase": "resolved"})
        crash_recovery.request_resume("0")
    else:
        monkeypatch.setattr(crash_recovery, "notice_path", lambda: None)
    request_exit, notify, intent = Mock(), Mock(), Mock()
    monkeypatch.setattr(
        offline.server, "shutdown", SimpleNamespace(closing=False, request=request_exit)
    )
    monkeypatch.setattr(mail, "send_message", notify)
    monkeypatch.setattr(instance_supervisor, "task_intent", intent)
    monkeypatch.setattr(offline.main, "main", Mock(side_effect=MemoryError("full")))

    offline.server._run_mower_worker({})

    request_exit.assert_not_called()
    assert config.stop_mower.is_set()
    assert not any(call.args[0] is False for call in intent.call_args_list)
    notify.assert_called_once()
    assert notify.call_args.kwargs["level"] == "ERROR"
    if has_recovery_record:
        assert not crash_recovery.status()["automatic"]
        assert crash_recovery.status()["phase"] == "failed"
    offline.io.assert_not_called()


def test_game_restart_precedes_observation_checkpoint_and_task_dispatch(
    offline, notice, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    runtime.write_json(notice, {"active": False, "phase": "resolved"})
    crash_recovery.request_resume("0")
    assert (
        crash_recovery.worker_failed(RecognizeError("scene unavailable"))
        == "restart_game"
    )
    prepared = crash_recovery.prepare_resume(offline.record.current_state())
    configure_simulate(offline, monkeypatch, solver)
    events = []
    solver.restart_game = Mock(side_effect=lambda: events.append("restart"))
    solver._read_room_mood = Mock(
        side_effect=lambda *args, **kwargs: events.append("observe")
    )
    save = offline.record.save_current_state

    def checkpoint():
        events.append("checkpoint")
        return save()

    def dispatch():
        events.append("dispatch")
        assert not crash_recovery.status()["active"]
        raise MowerExit

    monkeypatch.setattr(offline.record, "save_current_state", checkpoint)
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", dispatch)
    crash_recovery.begin()

    offline.main.simulate(prepared)

    assert events == [
        "restart",
        *["observe"] * len(solver.op_data.plan),
        "checkpoint",
        "dispatch",
    ]
    solver.restart_game.assert_called_once_with()
    offline.io.assert_not_called()


@pytest.mark.parametrize("failure_at", ["restore", "dispatch"])
def test_simulate_memory_failure_escapes_to_worker_recovery(
    offline, observed_scheduler, monkeypatch, failure_at
):
    solver = observed_scheduler
    saved = offline.record.current_state()
    configure_simulate(offline, monkeypatch, solver)
    if failure_at == "restore":

        class FailedOperators(dict):
            def items(self):
                raise MemoryError("restore allocation")

        saved["operators"] = FailedOperators()
        boundary = Mock(side_effect=MowerExit)
    else:
        boundary = Mock(side_effect=[MemoryError("dispatch allocation"), MowerExit])
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", boundary)
    refresh = solver.recog.update

    with pytest.raises(MemoryError, match="allocation"):
        offline.main.simulate(saved)

    refresh.assert_not_called()
    assert boundary.call_count == (0 if failure_at == "restore" else 1)
    offline.io.assert_not_called()


def test_uncertain_input_observation_memory_failure_escapes_to_worker_recovery(
    offline, observed_scheduler, monkeypatch
):
    solver = observed_scheduler
    device = object()
    result = SimpleNamespace(unwrap=lambda: device)
    control = SimpleNamespace(
        shutdown_requested=False,
        close=Mock(return_value=result),
        recover=Mock(return_value=result),
    )
    monkeypatch.setattr(offline.main, "device_control", control)
    monkeypatch.setattr(offline.main, "csleep", Mock())
    observation = Mock(side_effect=[MemoryError("observation allocation"), MowerExit])
    monkeypatch.setattr(crash_recovery, "observe_scheduler", observation)
    failure = TouchFailure(
        config.conf.device, "windows", OSError("uncertain"), delivery_unknown=True
    )

    with pytest.raises(MemoryError, match="observation allocation"):
        offline.main._resume_device_dispatch(solver, failure)

    observation.assert_called_once_with(solver)
    control.recover.assert_called_once_with()
    offline.io.assert_not_called()


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, AttributeError])
def test_consecutive_task_errors_recover_locally_once_then_escape_to_game_recovery(
    offline, observed_scheduler, monkeypatch, error_type
):
    solver = observed_scheduler
    configure_simulate(offline, monkeypatch, solver)
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", Mock())
    recover = Mock()
    monkeypatch.setattr(offline.main, "_resume_device_dispatch", recover)
    first_error = error_type("same task failure")
    solver.run = Mock(
        side_effect=[
            first_error,
            error_type("same task failure"),
            MowerExit,
        ]
    )

    with pytest.raises(error_type, match="same task failure"):
        offline.main.simulate({})

    assert solver.run.call_count == 2
    if error_type is ValueError:
        solver.recog.update.assert_called_once_with()
        recover.assert_not_called()
    else:
        solver.recog.update.assert_not_called()
        recover.assert_called_once_with(solver, first_error)
    offline.io.assert_not_called()


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError, AttributeError])
def test_successful_task_dispatch_resets_consecutive_error_count(
    offline, observed_scheduler, monkeypatch, error_type
):
    solver = observed_scheduler
    configure_simulate(offline, monkeypatch, solver)
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", Mock())
    recover = Mock()
    monkeypatch.setattr(offline.main, "_resume_device_dispatch", recover)
    solver.run = Mock(
        side_effect=[
            error_type("task failed"),
            None,
            error_type("task failed"),
            None,
            MowerExit,
        ]
    )

    offline.main.simulate({})

    assert solver.run.call_count == 5
    assert solver.recog.update.call_count == (2 if error_type is ValueError else 0)
    assert recover.call_count == (0 if error_type is ValueError else 2)
    offline.io.assert_not_called()


@pytest.mark.parametrize("failure_at", ["initialize", "dispatch"])
@pytest.mark.parametrize("wrapper", ["screenshot", "screenshot_fallback", "touch"])
def test_device_wrapped_memory_failure_never_starts_device_reconnection(
    offline, observed_scheduler, monkeypatch, failure_at, wrapper
):
    solver = observed_scheduler
    configure_simulate(offline, monkeypatch, solver)
    allocation = MemoryError("wrapped allocation failure")
    if wrapper == "touch":
        failure = TouchFailure(
            config.conf.device, "windows", allocation, delivery_unknown=True
        )
        failure.__cause__ = allocation
    else:
        failure = ScreenshotFailure(
            config.conf.device,
            "windows",
            allocation if wrapper == "screenshot" else OSError("helper failed"),
            fallback=allocation if wrapper == "screenshot_fallback" else None,
        )
    result = SimpleNamespace(unwrap=lambda: object())
    control = SimpleNamespace(
        shutdown_requested=False,
        recover=Mock(return_value=result),
        close=Mock(return_value=result),
    )
    monkeypatch.setattr(offline.main, "device_control", control)
    monkeypatch.setattr(offline.main, "csleep", Mock())
    monkeypatch.setattr(offline.main, "refresh_resource_at_boundary", Mock())
    observe = Mock()
    monkeypatch.setattr(crash_recovery, "observe_scheduler", observe)
    if failure_at == "initialize":
        monkeypatch.setattr(
            offline.main, "initialize", Mock(side_effect=[failure, solver])
        )
        solver.run = Mock(side_effect=MowerExit)
    else:
        solver.run = Mock(side_effect=[failure, MowerExit])

    with pytest.raises(type(failure)) as raised:
        offline.main.simulate({})

    assert raised.value is failure
    control.recover.assert_not_called()
    control.close.assert_not_called()
    observe.assert_not_called()
    offline.main.csleep.assert_not_called()
    offline.io.assert_not_called()
