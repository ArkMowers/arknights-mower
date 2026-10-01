"""Finite device recovery cycles preserve run intent and input boundaries."""

import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, call

import numpy as np
import pytest

from arknights_mower.tests.device_screenshot_backend_tests import (
    CaptureAdapter,
    CaptureHandle,
)
from arknights_mower.tests.device_session_tests import (
    ADB,
    Adapter,
    Clock,
    Preflight,
    Simulator,
)
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device import application, recovery
from arknights_mower.utils.device.adb_client import core as adb_core
from arknights_mower.utils.device.adb_client.socket import Socket
from arknights_mower.utils.device.application import (
    DeviceControl,
    LegacyDeviceAdapter,
    PreflightRejected,
)
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.maatouch.session import MaaTouchCleanupError
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.scrcpy.core import ScrcpyCleanupError
from arknights_mower.utils.device.screenshot_backend import ScreenshotFailure
from arknights_mower.utils.device.session import DeviceSession
from arknights_mower.utils.device.touch_backend import TouchFailure


@pytest.fixture
def cancellation(monkeypatch):
    stop = Event()
    monkeypatch.setattr(config, "stop_mower", stop)
    return stop


@pytest.fixture
def task_main(monkeypatch, cancellation):
    monkeypatch.setitem(sys.modules, "arknights_mower.utils.skland", Mock())
    from arknights_mower import __main__ as mower

    monkeypatch.setattr(mower, "base_scheduler", None)
    monkeypatch.setattr(mower, "csleep", Mock())
    monkeypatch.setattr(recovery, "csleep", Mock())
    monkeypatch.setattr(mower, "refresh_resource_at_boundary", Mock())
    monkeypatch.setattr(mower.NewsChecker, "get_maintenance", Mock(return_value=None))
    return mower


def test_recovery_cycles_wait_before_a_new_finite_attempt(monkeypatch, cancellation):
    recover = Mock(
        side_effect=[
            DeviceRecoveryError("first cycle"),
            DeviceRecoveryError("second cycle"),
            "ready",
        ]
    )
    sleep = Mock()
    monkeypatch.setattr(recovery, "csleep", sleep)

    assert (
        recovery.wait_for_recovery(
            recover, retry_errors=(DeviceRecoveryError,), cooldown=30
        )
        == "ready"
    )
    assert recover.call_count == 3
    assert sleep.call_args_list == [call(30), call(30)]


def test_cancellation_during_cooldown_never_opens_another_budget(
    monkeypatch, cancellation
):
    recover = Mock(side_effect=DeviceRecoveryError("exhausted"))

    def stop(seconds):
        cancellation.set()
        raise MowerExit

    monkeypatch.setattr(recovery, "csleep", stop)
    with pytest.raises(MowerExit):
        recovery.wait_for_recovery(recover, retry_errors=(DeviceRecoveryError,))
    recover.assert_called_once_with()


def test_recovery_supervision_does_not_hide_internal_faults(monkeypatch, cancellation):
    sleep = Mock()
    monkeypatch.setattr(recovery, "csleep", sleep)
    with pytest.raises(ValueError, match="internal fault"):
        recovery.wait_for_recovery(
            Mock(side_effect=ValueError("internal fault")),
            retry_errors=(DeviceRecoveryError,),
        )
    sleep.assert_not_called()


def test_cancelled_success_never_resumes_dispatch(cancellation):
    def late_success():
        cancellation.set()
        return "late ready"

    with pytest.raises(MowerExit):
        recovery.wait_for_recovery(late_success, retry_errors=(DeviceRecoveryError,))


def test_runtime_recovery_preserves_scheduler_and_refreshes_capture(
    task_main, monkeypatch
):
    device = object()
    result = SimpleNamespace(unwrap=lambda: device)
    control = SimpleNamespace(
        shutdown_requested=False,
        recover=Mock(side_effect=[DeviceRecoveryError("budget"), result]),
    )
    pending = [object()]
    scheduler = SimpleNamespace(
        device=object(), tasks=pending, recog=SimpleNamespace(update=Mock())
    )
    monkeypatch.setattr(task_main, "device_control", control)

    assert task_main._resume_device_dispatch(scheduler) is device
    assert scheduler.tasks is pending
    assert scheduler.device is device
    assert scheduler.recog.device is device
    scheduler.recog.update.assert_called_once_with()
    assert control.recover.call_count == 2
    task_main.csleep.assert_called_once_with(30)
    recovery.csleep.assert_called_once_with(30)


def test_unknown_side_effect_keeps_task_and_worker_until_cancel(
    task_main, monkeypatch, cancellation
):
    failure = TouchFailure(
        Conf().device, "windows", OSError("unknown"), delivery_unknown=True
    )
    device = object()
    control = SimpleNamespace(
        shutdown_requested=False,
        recover=Mock(return_value=SimpleNamespace(unwrap=lambda: device)),
        pause_dispatch=Mock(),
    )
    pending = [object()]
    scheduler = SimpleNamespace(
        device=device, tasks=pending, recog=SimpleNamespace(update=Mock())
    )
    monkeypatch.setattr(task_main, "device_control", control)
    sleeps = []

    def stop_after_paused(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            cancellation.set()
            raise MowerExit

    monkeypatch.setattr(task_main, "csleep", stop_after_paused)
    with pytest.raises(MowerExit):
        task_main._resume_device_dispatch(scheduler, failure)
    assert scheduler.tasks is pending
    assert control.pause_dispatch.call_count == 2
    assert control.recover.call_count == 2
    assert scheduler.recog.update.call_count == 2


def test_dispatch_returns_to_same_scheduler_after_budget_exhaustion(
    task_main, monkeypatch
):
    scheduler = Mock()
    scheduler.initialize_operators.return_value = None
    scheduler.op_data.validate_backup_plans.return_value = {"success": True}
    scheduler.tasks = []
    scheduler.run.side_effect = [DeviceRecoveryError("runtime"), MowerExit()]
    initialize = Mock(return_value=scheduler)
    resume = Mock()
    monkeypatch.setattr(task_main, "initialize", initialize)
    monkeypatch.setattr(task_main, "_resume_device_dispatch", resume)

    task_main.simulate(None)

    initialize.assert_called_once_with([], connection_retries=1)
    assert scheduler.run.call_count == 2
    assert resume.call_args.args[0] is scheduler
    assert task_main.base_scheduler is scheduler


@pytest.mark.parametrize(
    "failure",
    [
        DeviceRecoveryError("startup"),
        PreflightRejected("configuration", "invalid_size"),
        OSError("transport"),
    ],
)
def test_startup_failure_retains_run_intent(task_main, monkeypatch, failure):
    scheduler = Mock()
    scheduler.initialize_operators.return_value = "validation complete"
    initialize = Mock(side_effect=[failure, scheduler])
    resume = Mock()
    monkeypatch.setattr(task_main, "initialize", initialize)
    monkeypatch.setattr(task_main, "_resume_device_dispatch", resume)

    task_main.simulate({"tasks": ["saved task"]})

    assert initialize.call_count == 2
    resume.assert_called_once_with(failure=failure)


def test_capture_failure_retains_handle_and_can_recover(cancellation):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    control = DeviceControl(
        lambda: conf,
        Adapter(),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    device = control.start().unwrap()
    failure = ScreenshotFailure(conf.device, "windows", TimeoutError("capture"))

    def fail_capture(target):
        raise failure

    assert not control.execute(fail_capture).ok
    assert not device.closed
    assert control.recover().unwrap() is device
    assert control.execute(lambda target: target.device_id).unwrap() == "USB-A"
    assert simulator.actions == []
    assert control.close().ok


def test_external_startup_error_never_requests_application_shutdown(cancellation):
    error = OSError("temporary transport failure")
    shutdown = Mock()
    adapter = SimpleNamespace(open=Mock(side_effect=error))
    control = DeviceControl(
        lambda: SimpleNamespace(adb="USB-A"), adapter, on_fatal=shutdown
    )

    result = control.start()

    assert result.error.cause is error
    assert not control.shutdown_requested
    shutdown.assert_not_called()


def test_input_only_repair_preserves_preparation_capture_and_adb(cancellation):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    preflight = Preflight()
    check = preflight.check
    preflight.check = lambda profile, **options: check(profile)
    adapter = Adapter()
    adapter.rebind = Mock(side_effect=AssertionError("must preserve healthy resources"))
    control = DeviceControl(
        lambda: conf,
        adapter,
        preflight=preflight,
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    device = control.start().unwrap()
    device.input_alive = Mock(side_effect=[False, True])
    device.rebuild_input = Mock(return_value=True)
    preparation = SimpleNamespace(prepared_size=(1920, 1080), close=Mock())
    control._preparation = preparation
    capture, client = object(), object()
    device.capture, device.client = capture, client

    assert control.recover().unwrap() is device
    device.rebuild_input.assert_called_once_with()
    adapter.rebind.assert_not_called()
    preparation.close.assert_not_called()
    assert device.capture is capture
    assert device.client is client
    assert not device.closed
    assert simulator.actions == []
    assert control._session.actions == 1
    assert control.close().ok


def test_unknown_task_input_can_repair_without_reopening_input(cancellation):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    control = DeviceControl(
        lambda: conf,
        Adapter(),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    device = control.start().unwrap()
    device.capture_frame = lambda: np.zeros((1080, 1920, 3), dtype=np.uint8)
    failure = TouchFailure(
        conf.device, "windows", OSError("unknown input"), delivery_unknown=True
    )

    def uncertain_input(target):
        raise failure

    assert not control.execute(uncertain_input).ok
    assert control.recover().unwrap() is device
    assert control.status().status == "paused"
    operation = Mock()
    assert control.execute(operation).error.cause is failure
    operation.assert_not_called()
    assert control.capture().ok
    assert control.settings_status()["error"]["delivery_unknown"]
    assert control.close().ok


def test_native_recovery_keeps_android_adapter_ownership(monkeypatch, cancellation):
    monkeypatch.setattr(application, "is_android_runtime", lambda: True)
    device = SimpleNamespace(device_id="Android", reconnect=Mock(), close=Mock())
    control = DeviceControl(
        lambda: SimpleNamespace(adb="Android"),
        SimpleNamespace(open=Mock(return_value=device)),
    )
    control.start().unwrap()

    assert control.recover().unwrap() is device
    device.reconnect.assert_called_once_with()
    device.close.assert_not_called()
    assert control.close().ok


def test_missing_adapter_pauses_instead_of_ending_supervision(cancellation):
    control = DeviceControl(
        lambda: SimpleNamespace(adb="USB-A"),
        SimpleNamespace(
            open=Mock(return_value=SimpleNamespace(device_id="USB-A", close=Mock()))
        ),
    )
    control.start().unwrap()
    assert isinstance(control.recover().error.cause, DeviceRecoveryError)
    assert control.close().ok


def test_compensation_and_helper_reopen_cannot_clear_unknown_input(cancellation):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    control = DeviceControl(
        lambda: conf,
        Adapter(),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    original = control.start().unwrap()
    failure = TouchFailure(
        conf.device, "windows", OSError("unknown input"), delivery_unknown=True
    )
    control.pause_dispatch(failure)

    control._close_failure(
        PreflightRejected("temporary preflight failure"), "recovery_failed"
    )

    assert original.closed
    replacement = control.recover().unwrap()
    assert replacement is not original
    assert control.status().status == "paused"
    operation = Mock()
    assert control.execute(operation).error.cause is failure
    operation.assert_not_called()
    assert control.close().ok


def test_native_recovery_never_adopts_changed_identity(monkeypatch, cancellation):
    monkeypatch.setattr(application, "is_android_runtime", lambda: True)
    device = SimpleNamespace(device_id="Android", close=Mock())

    def change_target():
        device.device_id = "other target"

    device.reconnect = Mock(side_effect=change_target)
    control = DeviceControl(
        lambda: SimpleNamespace(adb="Android"),
        SimpleNamespace(open=Mock(return_value=device)),
    )
    control.start().unwrap()

    assert not control.recover().ok
    assert not control.recover().ok
    device.reconnect.assert_called_once_with()
    assert control._serial == "Android"
    assert control.close().ok


def test_pinned_adb_disconnect_after_preflight_never_requests_shutdown(
    monkeypatch, cancellation
):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    monkeypatch.setattr(config, "conf", conf)
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    transport = Mock()
    transport.devices_list.return_value = [("OTHER", "device")]
    monkeypatch.setattr(adb_core, "Session", Mock(return_value=transport))
    helper = Mock()
    monkeypatch.setattr(Device, "Control", helper)
    shutdown = Mock()
    control = DeviceControl(
        lambda: conf,
        LegacyDeviceAdapter(),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
        on_fatal=shutdown,
    )

    result = control.start()

    assert isinstance(result.error.cause, ConnectionError)
    assert "pinned target not ready" in result.error.message
    assert not control.shutdown_requested
    shutdown.assert_not_called()
    helper.assert_not_called()
    assert conf.device.last_serial == "USB-A"
    assert simulator.actions == []
    assert control.close().ok


def test_capture_incident_after_verified_endpoint_shift_uses_current_binding(
    cancellation,
):
    conf = Conf(
        device={
            "preset_id": "windows.mumu12",
            "instance_id": "0",
            "last_serial": "USB-A",
            "screenshot_backend": "adb_gzip",
        }
    )
    before = conf.model_dump()
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    simulator.state, simulator.serial = "running", "USB-A"
    handle = CaptureHandle()
    control = DeviceControl(
        lambda: conf,
        CaptureAdapter(handle),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    control.start().unwrap()
    simulator.serial = "USB-B"
    adb.rows = [("USB-B", "device")]
    assert control.recover().unwrap() is handle
    assert control.serial == "USB-B"
    assert control._serial == "USB-A"
    handle.frames = [
        RuntimeError("new endpoint helper failure"),
        np.zeros((1080, 1920, 3), dtype=np.uint8),
    ]

    assert control.capture().ok

    assert conf.model_dump() == before
    assert set(simulator.bindings) == {("windows.mumu12", "0")}
    assert simulator.actions == []
    assert control.close().ok


def test_failed_helper_construction_uses_remaining_attempts(cancellation):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    control = DeviceControl(
        lambda: conf,
        Adapter(),
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    device = control.start().unwrap()
    failure = TouchFailure(conf.device, "windows", TimeoutError("first helper startup"))
    device.rebuild_input = Mock(side_effect=[failure, True])
    device.input_alive = Mock(side_effect=[False, True])

    assert control.recover().unwrap() is device

    assert device.rebuild_input.call_count == 2
    assert control._session.actions == 2
    assert not device.closed
    assert simulator.actions == []
    assert control.close().ok


def test_missing_adb_resource_requires_verified_full_rebind(cancellation):
    conf = Conf(device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"})
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [("USB-A", "device")], "1"
    adapter = Adapter()
    control = DeviceControl(
        lambda: conf,
        adapter,
        preflight=Preflight(),
        session=DeviceSession(adb, simulator, clock=Clock()),
    )
    device = control.start().unwrap()
    device.client = None
    device.input_alive = Mock(side_effect=[False, True])
    device.rebuild_input = Mock(
        side_effect=AssertionError("cannot repair input without ADB")
    )
    adapter.rebind = Mock()

    assert control.recover().unwrap() is device

    adapter.rebind.assert_called_once()
    device.rebuild_input.assert_not_called()
    assert simulator.actions == []
    assert control.close().ok


@pytest.mark.parametrize(
    "failure",
    [
        ScrcpyCleanupError("scrcpy cleanup failed"),
        MaaTouchCleanupError("MaaTouch cleanup failed"),
    ],
)
def test_cleanup_failure_keeps_supervision_without_replacing_resources(
    cancellation, failure
):
    shutdown = Mock()
    adapter = SimpleNamespace(open=Mock(side_effect=failure))
    control = DeviceControl(
        lambda: SimpleNamespace(adb="USB-A"), adapter, on_fatal=shutdown
    )

    result = control.start()

    assert not control.shutdown_requested
    shutdown.assert_not_called()
    assert result.error.code == "close_failed"
    assert isinstance(result.error.cause, DeviceRecoveryError)
    assert result.error.cause.__cause__ is failure
    assert control._helper_cleanup_error is failure
    for _ in range(2):
        repeated = control.recover()
        assert isinstance(repeated.error.cause, DeviceRecoveryError)
        assert repeated.error.cause.__cause__ is failure
    adapter.open.assert_called_once()


def test_adb_eof_is_a_recoverable_connection_failure(monkeypatch):
    connection = Mock()
    connection.recv_into.return_value = 0
    monkeypatch.setattr(
        adb_core.socket, "create_connection", Mock(return_value=connection)
    )
    channel = Socket(("127.0.0.1", 5037), 1)

    with pytest.raises(ConnectionError, match="recv_exactly"):
        channel.recv_exactly(4)

    channel.close()
