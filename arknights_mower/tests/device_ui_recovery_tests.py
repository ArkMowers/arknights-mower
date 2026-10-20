"""界面失活恢复的原实例权限、资源释放和不重放行为。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.device_session_tests import ADB, Clock, Preflight, Simulator
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.endpoint_identity import CONFIRMED_START_PRESETS
from arknights_mower.utils.device.io_budget import device_io_budget
from arknights_mower.utils.device.preflight import PreflightError, PreflightResult
from arknights_mower.utils.device.recovery import (
    DeviceRecoveryError,
    UIUnresponsiveError,
)
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.touch_backend import TouchFailure


@pytest.fixture
def ui_session():
    events = []
    conf = Conf(
        device={
            "preset_id": "windows.mumu12",
            "instance_id": "0",
            "last_serial": "USB-A",
        }
    )
    clock, adb, simulator = Clock(), ADB(), Simulator()
    simulator.state, simulator.serial = "running", "USB-A"
    adb.rows, adb.boot = [("USB-A", "device")], "1"

    class Handle:
        device_id = "USB-A"
        closed = False
        close_error = None
        probe_error = None

        def close(self):
            events.append("close")
            if self.close_error is not None:
                raise self.close_error
            self.closed = True

        def _probe_ui_responsive(self):
            events.append("probe")
            if self.probe_error is not None:
                raise self.probe_error

    handle = Handle()

    class Adapter:
        def open_verified(self, configuration, result):
            return handle

        def rebind(self, device, result):
            assert device is handle
            assert device.closed
            events.append("rebind")
            device.closed = False
            device.device_id = result.serial

    stop, start = simulator.stop, simulator.start

    def stopping(profile, timeout):
        assert handle.closed
        events.append("stop")
        return stop(profile, timeout)

    def starting(profile, timeout):
        assert simulator.state == "stopped"
        events.append("start")
        return start(profile, timeout)

    def ready():
        simulator.state, simulator.serial = "running", "USB-B"
        adb.rows = [("USB-B", "device")]

    simulator.stop, simulator.start, simulator.on_start = stopping, starting, ready
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(timeout=12, local_wait=1, shutdown_wait=3),
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=Preflight()
    )
    assert control.start().ok
    yield SimpleNamespace(
        control=control,
        session=session,
        simulator=simulator,
        handle=handle,
        events=events,
        clock=clock,
        conf=conf,
    )
    handle.close_error = None
    control.close()


def fail_ui(env):
    operation = Mock(side_effect=UIUnresponsiveError())
    result = env.control.execute(operation)
    assert not result.ok
    return operation


def test_restart_releases_handles_rebinds_same_device_and_preserves_input_pause(
    ui_session,
):
    env = ui_session
    operation = fail_ui(env)
    pause = TouchFailure(
        env.conf.device, "windows", TimeoutError("delivery"), delivery_unknown=True
    )
    env.control.pause_dispatch(pause)
    result = env.control.recover()
    assert result.ok, result.error
    assert result.value is env.handle
    assert result.serial == "USB-B"
    assert result.helpers_rebuilt
    assert result.status == "paused"
    assert env.events == ["close", "stop", "start", "rebind", "probe"]
    assert env.simulator.bindings and set(env.simulator.bindings) == {
        ("windows.mumu12", "0")
    }
    operation.assert_called_once_with(env.handle)
    blocked = env.control.execute(Mock())
    assert not blocked.ok and blocked.error.cause is pause
    assert env.conf.device.last_serial == "USB-A"


def test_dispatch_recovery_retries_preflight_without_restarting_again(
    ui_session, monkeypatch
):
    import sys
    from datetime import datetime
    from threading import Event

    from arknights_mower.utils import config
    from arknights_mower.utils.device import recovery

    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    from arknights_mower import __main__ as main

    env = ui_session
    operation = fail_ui(env)
    failure = env.control._ui_unresponsive_failure
    check = env.control._check_profile
    env.control._check_profile = Mock(
        return_value=PreflightResult(
            False,
            "windows",
            "failed",
            "USB-B",
            error=PreflightError("frame_failed", "暂未取得有效截图"),
        )
    )

    first = env.control.recover()

    assert not first.ok and first.error.code == "frame_failed"
    assert env.control._device is env.handle
    assert env.control._ui_unresponsive_failure is failure
    assert failure.stop_requested and failure.start_requested
    assert env.simulator.actions == ["stop", "start"]
    env.control._check_profile = check
    task = SimpleNamespace(time=datetime(2026, 10, 20, 12, 30))
    pending = [task]
    scheduler = SimpleNamespace(
        device=env.handle,
        tasks=pending,
        recog=SimpleNamespace(device=env.handle, update=Mock()),
    )
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(main, "device_control", env.control)
    monkeypatch.setattr(main, "csleep", Mock())
    monkeypatch.setattr(recovery, "csleep", Mock())

    assert main._resume_device_dispatch(scheduler, failure) is env.handle

    assert scheduler.tasks is pending and scheduler.tasks == [task]
    assert task.time == datetime(2026, 10, 20, 12, 30)
    scheduler.recog.update.assert_called_once_with()
    assert env.control._ui_unresponsive_failure is None
    assert env.events == ["close", "stop", "start", "close", "rebind", "probe"]
    assert env.simulator.actions == ["stop", "start"]
    operation.assert_called_once_with(env.handle)


def test_cancellation_during_restart_preflight_still_releases_owner(ui_session):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure
    env.control._check_profile = Mock(side_effect=MowerExit("cancelled"))

    result = env.control.recover()

    assert not result.ok and result.error.code == "cancelled"
    assert env.control._device is None
    assert env.control._ui_unresponsive_failure is failure
    assert env.simulator.actions == ["stop", "start"]
    assert env.events == ["close", "stop", "start", "close"]


@pytest.mark.parametrize(
    "preset",
    sorted(CONFIRMED_START_PRESETS)
    + ["manual.other", "manual.physical", "windows.bluestacks5", "macos.mumu_pro"],
)
def test_no_full_restart_authority_preserves_original_target(ui_session, preset):
    env = ui_session
    env.session.profile = env.session.profile.model_copy(update={"preset_id": preset})
    fail_ui(env)
    result = env.control.recover()
    assert not result.ok
    assert "stop" not in env.events and "start" not in env.events
    assert env.control._device is env.handle


def test_changed_binding_never_restarts_another_instance(ui_session):
    env = ui_session
    fail_ui(env)
    env.session.profile = env.session.profile.model_copy(update={"instance_id": "1"})
    assert not env.control.recover().ok
    assert env.simulator.actions == []


def test_unknown_manager_state_requires_a_new_confirmed_observation(ui_session):
    env = ui_session
    fail_ui(env)
    env.simulator.state = "unknown"
    assert not env.control.recover().ok
    assert env.simulator.actions == []
    env.simulator.state = "running"
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


def test_failed_handle_cleanup_blocks_stop_and_retains_owner_for_later_cleanup(
    ui_session,
):
    env = ui_session
    fail_ui(env)
    env.handle.close_error = RuntimeError("owned helper still running")
    first = env.control.recover()
    assert not first.ok
    assert first.error.code == "close_failed"
    assert env.control._device is env.handle
    assert env.simulator.actions == []
    env.handle.close_error = None
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


@pytest.mark.parametrize("target_change", ["binding", "unknown", "serial"])
def test_cleanup_reconnect_rejects_unconfirmed_original_target(
    ui_session, target_change
):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure
    env.handle.close_error = RuntimeError("owned helper needs original transport")
    env.session.adb.rows = [("USB-A", "offline")]
    if target_change == "binding":
        env.session.profile = env.session.profile.model_copy(
            update={"instance_id": "1"}
        )
    elif target_change == "unknown":
        env.simulator.state = "unknown"
    else:
        env.simulator.serial = "USB-B"

    assert not env.control.recover().ok

    assert env.session.adb.actions == []
    assert env.simulator.actions == []
    assert env.control._device is env.handle
    assert env.control._cleanup_device is env.handle
    assert env.control._ui_unresponsive_failure is failure
    assert not failure.stop_requested


def test_cleanup_retry_observes_transport_despite_rejected_reconnect_ack(ui_session):
    env = ui_session
    fail_ui(env)
    env.handle.close_error = RuntimeError("owned helper needs original transport")
    env.session.adb.rows = [("USB-A", "offline")]
    recover = env.session.adb.recover

    def reconnect(adb_path, serial, timeout):
        recover(adb_path, serial, timeout)
        env.session.adb.rows = [("USB-A", "device")]
        env.handle.close_error = None
        return False

    env.session.adb.recover = reconnect
    result = env.control.recover()

    assert result.ok, result.error
    assert result.value is env.handle
    assert env.session.adb.actions == ["USB-A"]
    assert env.simulator.actions == ["stop", "start"]


def test_parent_expiration_during_failed_cleanup_prevents_transport_reconnect(
    ui_session,
):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure

    def slow_close():
        env.clock.sleep(2)
        raise RuntimeError("owned helper needs original transport")

    env.handle.close = slow_close

    def parent_remaining():
        if env.clock.now >= 2:
            raise DeviceRecoveryError("parent budget exhausted")
        return 2 - env.clock.now

    with pytest.raises(DeviceRecoveryError, match="parent budget"):
        with device_io_budget(parent_remaining):
            assert not env.control.recover().ok

    assert env.session.adb.actions == []
    assert env.simulator.actions == []
    assert env.control._ui_unresponsive_failure is failure
    assert env.control._cleanup_device is env.handle


def test_lost_stop_acknowledgement_does_not_repeat_stop_across_recovery_budgets(
    ui_session,
):
    env = ui_session
    fail_ui(env)

    def uncertain_stop(profile, timeout):
        env.simulator.actions.append("stop")
        raise OSError("lost stop acknowledgement")

    env.simulator.stop = uncertain_stop
    assert not env.control.recover().ok
    assert not env.control.recover().ok
    assert env.simulator.actions == ["stop"]
    assert env.clock.now == 3
    env.simulator.state = "stopped"
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


def test_start_waits_for_confirmed_stop_and_does_not_reissue_stop(ui_session):
    env = ui_session
    fail_ui(env)

    def slow_stop(profile, timeout):
        env.simulator.actions.append("stop")
        env.simulator.state = "starting"
        return True

    env.simulator.stop = slow_stop
    assert not env.control.recover().ok
    assert env.clock.now == 3
    assert env.simulator.actions == ["stop"]
    env.simulator.state = "stopped"
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


def test_lost_start_acknowledgement_never_replays_start_or_stop(ui_session):
    env = ui_session
    fail_ui(env)
    start = env.simulator.start

    def uncertain_start(profile, timeout):
        start(profile, timeout)
        raise OSError("lost start acknowledgement")

    env.simulator.start = uncertain_start
    assert not env.control.recover().ok
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


def test_restart_marker_is_released_only_by_a_real_successful_ui_probe(ui_session):
    env = ui_session
    fail_ui(env)
    env.handle.probe_error = UIUnresponsiveError()
    assert not env.control.recover().ok
    assert not env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]
    env.handle.probe_error = None
    assert env.control.recover().ok
    fail_ui(env)
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start", "stop", "start"]


@pytest.mark.parametrize("changed_target", [False, True])
def test_independent_new_session_does_not_inherit_closed_owner_ui_failure(
    ui_session, changed_target
):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure
    assert env.control.close().ok
    assert env.control._ui_unresponsive_failure is failure
    if changed_target:
        env.conf.device.instance_id = "1"

    assert env.control.start().ok
    assert env.control.recover().ok

    assert env.simulator.actions == []
    assert env.control._ui_unresponsive_failure is None
    assert env.session.profile.instance_id == ("1" if changed_target else "0")


def test_failed_close_does_not_retire_original_ui_failure_or_allow_new_session(
    ui_session,
):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure
    env.handle.close_error = RuntimeError("owned helper still running")

    assert not env.control.close().ok
    assert not env.control.start().ok

    assert env.control._ui_unresponsive_failure is failure
    assert env.simulator.actions == []


def test_failed_independent_start_retains_original_ui_failure(ui_session):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure
    assert env.control.close().ok
    env.control._adapter.open_verified = Mock(
        side_effect=DeviceRecoveryError("new session failed")
    )

    assert not env.control.start().ok

    assert env.control._ui_unresponsive_failure is failure
    assert env.simulator.actions == []


def test_existing_session_start_does_not_retire_ui_failure(ui_session):
    env = ui_session
    fail_ui(env)
    failure = env.control._ui_unresponsive_failure

    assert not env.control.start().ok

    assert env.control._ui_unresponsive_failure is failure
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


def test_dead_rebuilt_input_cannot_report_recovery_or_authorize_another_restart(
    ui_session,
):
    env = ui_session
    fail_ui(env)
    env.handle.input_alive = Mock(return_value=False)
    assert not env.control.recover().ok
    assert "probe" not in env.events
    env.handle.input_alive.return_value = True
    assert env.control.recover().ok
    assert env.simulator.actions == ["stop", "start"]


def test_parent_budget_exhausted_during_cleanup_never_authorizes_stop(ui_session):
    env = ui_session
    fail_ui(env)
    close = env.handle.close

    def slow_close():
        close()
        env.clock.sleep(4)

    env.handle.close = slow_close

    def parent_remaining():
        if env.clock.now >= 3:
            raise DeviceRecoveryError("parent budget exhausted")
        return 3 - env.clock.now

    with pytest.raises(DeviceRecoveryError, match="parent budget"):
        with device_io_budget(parent_remaining):
            assert not env.control.recover().ok
    assert env.simulator.actions == []


def test_stop_confirmation_cannot_outlive_the_parent_budget(ui_session):
    env = ui_session
    fail_ui(env)

    def slow_stop(profile, timeout):
        env.simulator.actions.append("stop")
        env.simulator.state = "starting"
        return True

    def parent_remaining():
        if env.clock.now >= 2:
            raise DeviceRecoveryError("parent budget exhausted")
        return 2 - env.clock.now

    env.simulator.stop = slow_stop
    with pytest.raises(DeviceRecoveryError, match="parent budget"):
        with device_io_budget(parent_remaining):
            assert not env.control.recover().ok
    assert env.clock.now == 2
    assert env.simulator.actions == ["stop"]


def test_unreadable_manager_does_not_restart_or_escape_the_recovery_boundary(
    ui_session,
):
    env = ui_session
    fail_ui(env)
    env.simulator.inspect = Mock(side_effect=OSError("manager unavailable"))
    result = env.control.recover()
    assert not result.ok
    assert isinstance(result.error.cause, DeviceRecoveryError)
    assert env.simulator.actions == []


def test_cancellation_during_stop_confirmation_never_starts(ui_session):
    env = ui_session
    fail_ui(env)

    def slow_stop(profile, timeout):
        env.simulator.actions.append("stop")
        env.simulator.state = "starting"
        return True

    def cancelled_sleep(seconds):
        if seconds:
            raise MowerExit("cancelled")

    env.simulator.stop = slow_stop
    env.clock.sleep = cancelled_sleep
    result = env.control.recover()
    assert not result.ok and result.error.code == "cancelled"
    assert env.simulator.actions == ["stop"]


def test_healthy_transport_or_unchanged_image_does_not_authorize_restart(ui_session):
    env = ui_session
    assert env.control.execute(lambda device: b"same frame").ok
    assert env.control.recover().ok
    assert env.simulator.actions == []
