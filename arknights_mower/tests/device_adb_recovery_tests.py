from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.tests.device_session_tests import (
    ADB,
    Adapter,
    Clock,
    Preflight,
    Simulator,
)
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.session import DeviceSession
from arknights_mower.utils.device.touch_backend import TouchFailure


@pytest.fixture
def application():
    serial = "127.0.0.1:19001"
    conf = Conf(
        device={
            "preset_id": "windows.mumu12",
            "instance_id": "0",
            "last_serial": serial,
            "screenshot_backend": "adb_gzip",
        }
    )
    adb, simulator, clock = ADB(), Simulator(), Clock()
    adb.rows, adb.boot = [(serial, "device")], "1"
    simulator.state, simulator.serial = "running", serial
    adapter = Adapter()
    adapter.rebind = Mock(wraps=adapter.rebind)
    recovery = SimpleNamespace(generation=0, recover=Mock(return_value=False))
    session = DeviceSession(adb, simulator, clock=clock)
    control = DeviceControl(
        lambda: conf,
        adapter,
        session=session,
        preflight=Preflight(),
        adb_recovery=recovery,
    )
    yield SimpleNamespace(
        control=control,
        session=session,
        adapter=adapter,
        conf=conf,
        adb=adb,
        simulator=simulator,
        recovery=recovery,
    )
    control.close()


def test_healthy_shared_server_never_consumes_restart_action(application):
    before = application.conf.model_dump()
    with application.control.run():
        device = application.control.start().unwrap()
        assert application.session.actions == 0
        assert application.control.recover().unwrap() is device
        application.adapter.rebind.assert_not_called()
        assert application.conf.model_dump() == before
        assert application.simulator.actions == []


def test_shared_restart_requires_verified_target_before_helper_rebuild(application):
    with application.control.run():
        device = application.control.start().unwrap()
        application.recovery.generation += 1
        assert application.control.recover().unwrap() is device
        application.adapter.rebind.assert_called_once()
        assert application.control._bound_adb_generation == 1


def test_peer_restart_generation_survives_failed_verification(application):
    with application.control.run():
        device = application.control.start().unwrap()
        application.recovery.generation += 1
        application.adb.frame = None
        assert not application.control.recover().ok
        application.adapter.rebind.assert_not_called()
        assert application.control._bound_adb_generation == 0
        application.adb.frame = (1920, 1080)
        assert application.control.recover().unwrap() is device
        application.adapter.rebind.assert_called_once()
        assert application.control._bound_adb_generation == 1


def test_host_failure_retains_target_and_does_not_close_shared_service(application):
    before = application.conf.model_dump()
    with application.control.run():
        application.control.start().unwrap()
        application.recovery.recover.side_effect = SharedADBError("host stalled")
        assert not application.control.recover().ok
        assert application.conf.model_dump() == before
        application.adapter.rebind.assert_not_called()
        assert not application.control.shutdown_requested
    assert not hasattr(application.recovery, "close")


def test_unknown_input_is_not_replayed_after_shared_restart(application):
    with application.control.run():
        application.control.start().unwrap()
        failure = TouchFailure(
            application.conf.device,
            "windows",
            BrokenPipeError("unknown"),
            delivery_unknown=True,
        )

        def fail(device):
            raise failure

        assert not application.control.execute(fail).ok
        application.recovery.generation += 1
        assert application.control.recover().ok
        operation = Mock()
        assert not application.control.execute(operation).ok
        operation.assert_not_called()


def test_changed_binding_after_shared_restart_never_rebinds_other_device(application):
    serial = application.conf.device.last_serial
    with application.control.run():
        application.control.start().unwrap()
        application.recovery.generation += 1
        application.adb.rows = [("127.0.0.1:19999", "device")]
        application.simulator.state = "unknown"
        assert not application.control.recover().ok
        application.adapter.rebind.assert_not_called()
        assert application.conf.device.last_serial == serial


def test_idle_cleanup_and_run_exit_release_only_device_helpers(application):
    with application.control.run():
        device = application.control.start().unwrap()
        assert application.control.close().ok
        assert device.closed
        assert application.control.start().ok
    assert not application.control.active
    assert not hasattr(application.recovery, "close")


def test_shared_restart_callback_uses_existing_session_action_budget(application):
    def restart(adb_path, *, timeout, cancelled, action):
        assert not cancelled()
        return action(lambda: True)

    application.recovery.recover.side_effect = restart
    application.conf.device.recovery_attempts = 0
    with application.control.run():
        assert not application.control.start().ok
        assert application.session.actions == 0


def test_host_recovers_before_restart_action_without_failing_startup(application):
    def recovered(adb_path, *, timeout, cancelled, action):
        return action(lambda: False)

    application.recovery.recover.side_effect = recovered
    with application.control.run():
        assert application.control.start().ok
        assert application.control.recover().ok
        assert application.control._bound_adb_generation == 0
        application.adapter.rebind.assert_called_once()


def test_shared_recovery_cancellation_checks_worker_and_device_shutdown(application):
    with application.control.run():
        assert application.control.start().ok
        callback = application.recovery.recover.call_args.kwargs["cancelled"]
        assert not callback()
        application.control._pending_close.set()
        assert callback()
        application.control._pending_close.clear()
        application.session.clock.sleep = Mock(side_effect=MowerExit("cancelled"))
        with pytest.raises(MowerExit):
            callback()
        application.session.clock.sleep = Mock()
