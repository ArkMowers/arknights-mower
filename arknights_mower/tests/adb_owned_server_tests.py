from contextlib import nullcontext
from io import StringIO
from subprocess import CompletedProcess, TimeoutExpired
from threading import Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.owned import OwnedADBServer
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    adb_command,
    adb_server_scope,
    run_adb,
)


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(config, "stop_mower", Event())
    clock = Clock()
    children = []

    def spawn(argv, **options):
        process = Mock()
        process.pid = 9000 + len(children)
        process.poll.return_value = None
        process.wait.side_effect = lambda **kwargs: setattr(
            process.poll, "return_value", 0
        )
        process.argv, process.options = argv, options
        children.append(process)
        return process

    probe = Mock(return_value=41)
    listener = Mock(return_value=True)
    runner = Mock(
        return_value=CompletedProcess(
            [], 0, b"Android Debug Bridge version 1.0.41\n", b""
        )
    )
    owner = OwnedADBServer(
        spawn=spawn,
        probe=probe,
        listener=listener,
        reserve=Mock(side_effect=[45001, 45002, 45003]),
        run=runner,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return SimpleNamespace(
        owner=owner,
        clock=clock,
        children=children,
        probe=probe,
        listener=listener,
        runner=runner,
    )


def test_start_owns_foreground_child_and_disables_unselected_transports(service):
    assert service.owner.recover("adb", timeout=10)
    child = service.children[0]
    assert child.argv == ["adb", "-L", "tcp:127.0.0.1:45001", "nodaemon", "server"]
    assert child.options["env"]["ADB_USB"] == "0"
    assert child.options["env"]["ADB_EMU"] == "0"
    assert child.options["env"]["ADB_MDNS"] == "0"
    assert child.options["env"]["ADB_MDNS_AUTO_CONNECT"] == "0"
    service.listener.assert_called_once()
    assert service.owner.address == ("127.0.0.1", 45001)
    service.owner.close()
    child.terminate.assert_called_once()


def test_healthy_service_never_restarts_for_offline_instances(service):
    service.owner.recover("adb", timeout=10)
    for _ in range(5):
        service.clock.now += 60
        assert not service.owner.recover("adb", timeout=10)
    assert len(service.children) == 1
    service.children[0].terminate.assert_not_called()


def test_sustained_failed_probes_rebuild_only_owned_child_on_new_port(service):
    service.owner.recover("adb", timeout=10)
    service.probe.side_effect = SharedADBError("stalled service")
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    service.clock.now += 29
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    service.clock.now += 1
    service.probe.side_effect = [SharedADBError("stalled service"), 41]
    action = Mock(side_effect=lambda operation: operation())
    assert service.owner.recover("adb", timeout=10, action=action)
    action.assert_called_once()
    service.children[0].terminate.assert_called_once()
    assert service.children[1].argv[2] == "tcp:127.0.0.1:45002"
    assert all("kill-server" not in child.argv for child in service.children)


def test_foreign_listener_is_never_adopted_or_terminated(service):
    service.listener.return_value = False
    with pytest.raises(SharedADBError, match="监听"):
        service.owner.recover("adb", timeout=2)
    assert len(service.children) == 1
    service.children[0].terminate.assert_called_once()
    with pytest.raises(SharedADBError):
        _ = service.owner.address


def test_cancellation_does_not_spawn_or_replace_a_server(service):
    config.stop_mower.set()
    with pytest.raises(MowerExit):
        service.owner.recover("adb", timeout=10)
    assert service.children == []


def test_real_cleanup_failure_prevents_replacement(service):
    service.owner.recover("adb", timeout=10)
    child = service.children[0]
    child.wait.side_effect = TimeoutExpired("adb", 1)
    with pytest.raises(SharedADBError) as failure:
        service.owner.close()
    assert failure.value.cleanup_failed
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    assert len(service.children) == 1


def test_process_owner_mismatch_never_terminates_a_child(service):
    service.owner.recover("adb", timeout=10)
    service.owner.owner_pid = -1
    service.owner.close()
    service.children[0].terminate.assert_not_called()


def test_owned_commands_use_port_without_mutating_global_environment(
    service, monkeypatch
):
    import os

    monkeypatch.delenv("ADB_SERVER_SOCKET", raising=False)
    service.owner.recover("adb", timeout=10)
    runner = Mock(return_value=CompletedProcess([], 0, b"", b""))
    with adb_server_scope(service.owner):
        run_adb(["adb", "devices"], timeout=5, run=runner)
        assert adb_command(["adb", "-s", "chosen", "shell"]) == [
            "adb",
            "-H",
            "127.0.0.1",
            "-P",
            "45001",
            "-s",
            "chosen",
            "shell",
        ]
    assert "ADB_SERVER_SOCKET" not in os.environ
    assert runner.call_args.args[0] == [
        "adb",
        "-H",
        "127.0.0.1",
        "-P",
        "45001",
        "devices",
    ]
    assert runner.call_args.kwargs["env"]["ADB_SERVER_SOCKET"] == "tcp:127.0.0.1:45001"


@pytest.mark.parametrize("scope", [nullcontext, lambda: adb_server_scope(None)])
def test_shared_service_commands_remain_forbidden(scope):
    runner = Mock()
    with scope(), pytest.raises(SharedADBError):
        run_adb(["adb", "kill-server"], timeout=5, run=runner)
    runner.assert_not_called()


@pytest.fixture
def application(service):
    from arknights_mower.tests.device_session_tests import (
        ADB,
        Adapter,
        Preflight,
        Simulator,
    )
    from arknights_mower.utils.config.conf import Conf
    from arknights_mower.utils.device.application import DeviceControl
    from arknights_mower.utils.device.session import DeviceSession

    serial = "127.0.0.1:16384"
    conf = Conf(
        device={
            "preset_id": "windows.mumu12",
            "instance_id": "0",
            "last_serial": serial,
            "screenshot_backend": "adb_gzip",
        }
    )
    adb, simulator = ADB(), Simulator()
    adb.rows, adb.boot = [(serial, "device")], "1"
    simulator.state, simulator.serial = "running", serial
    adapter = Adapter()
    adapter.rebind = Mock(wraps=adapter.rebind)
    session = DeviceSession(adb, simulator, clock=service.clock)
    control = DeviceControl(
        lambda: conf,
        adapter,
        session=session,
        preflight=Preflight(),
        adb_server=service.owner,
    )
    return SimpleNamespace(
        control=control,
        session=session,
        adapter=adapter,
        conf=conf,
        adb=adb,
        simulator=simulator,
    )


def test_application_rebuilds_helpers_after_verified_owned_server_recovery(
    service, application
):
    before = application.conf.model_dump()
    with application.control.run():
        device = application.control.start().unwrap()
        assert application.session.actions == 1
        service.probe.side_effect = SharedADBError("stalled service")
        assert not application.control.recover().ok
        application.adapter.rebind.assert_not_called()
        service.clock.now += 30
        service.probe.side_effect = [SharedADBError("stalled service"), 41]
        assert application.control.recover().unwrap() is device
        application.adapter.rebind.assert_called_once()
        assert application.session.actions == 1
        assert application.control.serial == before["device"]["last_serial"]
        assert application.conf.model_dump() == before
        assert application.simulator.actions == []
    assert all(child.terminate.call_count == 1 for child in service.children)


def test_run_exit_releases_helpers_before_the_owned_server(service, application):
    order = []
    close = service.owner.close
    service.owner.close = Mock(
        side_effect=lambda **kwargs: (order.append("server"), close(**kwargs))[-1]
    )
    with application.control.run():
        device = application.control.start().unwrap()
        device.close = lambda: order.append("helpers")
    assert order == ["helpers", "server"]


def test_zero_attempt_budget_never_starts_an_owned_service(service, application):
    application.conf.device.recovery_attempts = 0
    with application.control.run():
        assert not application.control.start().ok
        assert service.children == []


def test_physical_device_run_never_uses_owned_server(service, application):
    application.conf.device.preset_id = "manual.physical"
    with application.control.run():
        assert application.control.start().ok
    assert service.children == []


def test_owned_server_recovery_preserves_unknown_input_pause(service, application):
    from arknights_mower.utils.device.touch_backend import TouchFailure

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
        service.probe.side_effect = SharedADBError("stalled service")
        assert not application.control.recover().ok
        service.clock.now += 30
        service.probe.side_effect = [SharedADBError("stalled service"), 41]
        assert application.control.recover().ok
        operation = Mock()
        assert not application.control.execute(operation).ok
        operation.assert_not_called()


def test_listener_ownership_change_does_not_dispatch_to_foreign_service(service):
    service.owner.recover("adb", timeout=10)
    service.listener.return_value = False
    runner = Mock()
    with adb_server_scope(service.owner), pytest.raises(SharedADBError, match="监听"):
        run_adb(
            ["adb", "-s", "chosen", "shell", "input", "tap", "1", "2"],
            timeout=5,
            run=runner,
        )
    runner.assert_not_called()


def test_probe_failure_is_not_enough_without_elapsed_threshold(service):
    service.owner.recover("adb", timeout=10)
    service.probe.side_effect = SharedADBError("timeout")
    for _ in range(4):
        with pytest.raises(SharedADBError):
            service.owner.recover("adb", timeout=10)
    assert len(service.children) == 1


def test_a_verified_healthy_probe_resets_the_service_failure_window(service):
    service.owner.recover("adb", timeout=10)
    service.probe.side_effect = SharedADBError("timeout")
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    service.clock.now += 60
    service.probe.side_effect = None
    service.owner.recover("adb", timeout=10)
    service.probe.side_effect = SharedADBError("new incident")
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    assert len(service.children) == 1


def test_owned_service_attempt_and_elapsed_time_share_the_session_budget(
    service, application
):
    from arknights_mower.utils.device.session import SessionFailure

    application.conf.device.recovery_attempts = 1
    application.adb.rows = []
    with application.control.run():
        result = application.control.start()
        assert not result.ok
        assert isinstance(result.error.cause, SessionFailure)
        assert len(service.children) == 1
        assert application.session.actions == 1
        assert application.simulator.actions == []
        assert application.adb.actions == []


def test_changed_instance_is_rejected_after_service_rebuild(service, application):
    serial = application.conf.device.last_serial
    with application.control.run():
        application.control.start().unwrap()
        service.probe.side_effect = SharedADBError("stalled")
        assert not application.control.recover().ok
        service.clock.now += 30
        service.probe.side_effect = [SharedADBError("stalled"), 41]
        application.adb.rows = [("127.0.0.1:19999", "device")]
        application.simulator.state = "unknown"
        result = application.control.recover()
        assert not result.ok
        application.adapter.rebind.assert_not_called()
        assert application.conf.device.last_serial == serial
        assert application.control.serial == serial


def test_shutdown_defers_server_release_until_device_cleanup(service, application):
    with application.control.run():
        device = application.control.start().unwrap()
        application.control.begin_shutdown()
    assert not device.closed
    assert service.owner.process is service.children[0]
    assert application.control.close().ok
    assert device.closed
    assert service.owner.process is None


@pytest.mark.parametrize("release", ["close", "final_release"])
def test_exit_releases_owned_server_while_run_is_still_active(
    service, application, release
):
    order = []
    close_server = service.owner.close
    service.owner.close = Mock(
        side_effect=lambda **options: (order.append("server"), close_server(**options))[
            -1
        ]
    )
    with application.control.run():
        device = application.control.start().unwrap()
        close_device = device.close
        device.close = lambda: (order.append("helpers"), close_device())[-1]
        application.control.begin_shutdown()
        assert application.control._run_active
        assert getattr(application.control, release)().ok
        assert device.closed
        assert service.owner.process is None
        assert order == ["helpers", "server"]
        assert application.control.close().ok
        assert application.control.final_release().ok
    assert order == ["helpers", "server"]
    service.children[0].terminate.assert_called_once_with()


def test_idle_helper_cleanup_retains_server_until_whole_run_exit(service, application):
    with application.control.run():
        device = application.control.start().unwrap()
        assert application.control.close().ok
        assert device.closed
        assert service.owner.process is service.children[0]
        service.children[0].terminate.assert_not_called()
    assert service.owner.process is None
    service.children[0].terminate.assert_called_once_with()


def test_deferred_shutdown_releases_server_after_live_helper_operation_returns(
    service, application, monkeypatch
):
    entered, release = Event(), Event()
    order = []
    close_server = service.owner.close
    service.owner.close = Mock(
        side_effect=lambda **options: (order.append("server"), close_server(**options))[
            -1
        ]
    )
    monkeypatch.setattr(
        application.control,
        "_acquire_for_final_release",
        lambda: application.control.configuration_lock.acquire(timeout=0.01),
    )
    with application.control.run():
        device = application.control.start().unwrap()
        close_device = device.close
        device.close = lambda: (order.append("helpers"), close_device())[-1]

        def operation(handle):
            entered.set()
            assert release.wait(2)

        worker = Thread(target=lambda: application.control.execute(operation))
        worker.start()
        try:
            assert entered.wait(1)
            application.control.begin_shutdown()
            assert application.control.close(timeout=0.01).error.code == "close_timeout"
            assert application.control.final_release().error.code == "close_timeout"
            assert not device.closed
            assert service.owner.process is service.children[0]
            assert order == []
        finally:
            release.set()
            worker.join(2)
        assert not worker.is_alive()
        assert device.closed
        assert service.owner.process is None
        assert order == ["helpers", "server"]
        assert application.control.close().ok
        assert application.control.final_release().ok
    service.children[0].terminate.assert_called_once_with()


def test_invalid_adb_configuration_keeps_service_failure_classified(
    service, application
):
    application.adb.resolve_adb = Mock(side_effect=RuntimeError("invalid binary"))
    fatal = Mock()
    application.control._on_fatal = fatal
    with application.control.run():
        result = application.control.start()
        assert not result.ok
        assert result.error.code == "missing_adb"
        fatal.assert_not_called()
    assert service.children == []


def test_foreground_exit_is_reaped_before_starting_another_port(service):
    service.owner.recover("adb", timeout=10)
    service.children[0].poll.return_value = 1
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    service.clock.now += 30
    assert service.owner.recover("adb", timeout=10)
    assert len(service.children) == 2
    service.children[0].terminate.assert_not_called()


@pytest.mark.parametrize(
    "output", [b"unverified binary", b"Android Debug Bridge version 1.0.40\n"]
)
def test_unsupported_binary_never_starts_server_or_claims_usb(service, output):
    service.runner.return_value.stdout = output
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=10)
    assert service.children == []


@pytest.mark.parametrize(
    "argv", [["adb", "-P", "5037", "devices"], ["adb", "kill-server"]]
)
def test_owned_helper_cannot_redirect_or_manage_a_server(service, argv):
    service.owner.recover("adb", timeout=10)
    with adb_server_scope(service.owner), pytest.raises(SharedADBError):
        adb_command(argv)


def test_cancellation_while_waiting_for_listener_releases_only_spawned_child(service):
    service.listener.return_value = False

    def cancel(seconds):
        config.stop_mower.set()
        raise MowerExit()

    service.owner._sleep = cancel
    with pytest.raises(MowerExit):
        service.owner.recover("adb", timeout=10)
    service.children[0].terminate.assert_called_once()
    assert service.owner.process is None


def test_inactive_settings_restore_shared_server_context_after_run(
    service, application
):
    from arknights_mower.utils.device.adb_client.server import current_adb_server

    with application.control.run():
        assert application.control.start().ok
    with application.control._configuration(settings=True):
        assert current_adb_server() is None
    assert service.owner.process is None


def test_exit_during_termination_does_not_create_false_cleanup_failure(service):
    service.owner.recover("adb", timeout=10)
    child = service.children[0]

    def exited():
        child.poll.return_value = 0
        raise ProcessLookupError("already exited")

    child.terminate.side_effect = exited
    service.owner.close()
    assert service.owner.process is None
    assert service.owner.recover("adb", timeout=10)


@pytest.mark.parametrize(
    "name, expected_state", [("mower_api_35", "running"), ("other_avd", "stopped")]
)
def test_avd_registers_only_saved_emulator_alias_then_verifies_name(
    service, tmp_path, name, expected_state
):
    from arknights_mower.tests.device_avd_io_tests import SDKFixture

    sdk = SDKFixture(tmp_path)
    profile = sdk.profile()
    profile.last_serial = "emulator-5554"
    commands = []

    def run(argv, **options):
        commands.append(argv)
        assert argv[1:5] == ["-H", "127.0.0.1", "-P", "45001"]
        args = argv[5:]
        if args == ["connect", "emu:5554,5555"]:
            sdk.online(name=name)
            return CompletedProcess(
                argv, 0, b"Connected to emulator on ports 5554,5555", b""
            )
        return sdk.run([argv[0], *args], **options)

    controller = sdk.controller()
    controller.run = run
    service.owner.recover("adb", timeout=10)
    with adb_server_scope(service.owner):
        observation = controller.inspect(profile, 3)
    assert observation.state == expected_state
    assert commands[0][5:] == ["connect", "emu:5554,5555"]
    assert any(
        command[5:] == ["-s", "emulator-5554", "emu", "avd", "name"]
        for command in commands
    )
    assert profile.last_serial == "emulator-5554"
    assert sdk.launches == []


def test_actual_listener_probe_uses_only_owned_pid_and_loopback_port(monkeypatch):
    from arknights_mower.utils.device.adb_client import owned

    monkeypatch.setattr(owned.sys, "platform", "darwin")
    run = Mock(return_value=CompletedProcess([], 0, b"p123\nn127.0.0.1:45001\n", b""))
    monkeypatch.setattr(owned, "run_manager_command", run)
    assert owned._owns_listener(123, 45001, 1)
    command = run.call_args.args[0]
    assert command[command.index("-p") + 1] == "123"
    assert "-iTCP:45001" in command
    run.return_value.stdout = b"p123\nn*:45001\n"
    assert not owned._owns_listener(123, 45001, 1)


def test_windows_listener_probe_requires_exact_pid_endpoint_and_listen_state(
    monkeypatch,
):
    from arknights_mower.utils.device.adb_client import owned

    monkeypatch.setattr(owned, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(owned.sys, "platform", "win32")
    monkeypatch.setattr(owned.subprocess, "CREATE_NO_WINDOW", 8, raising=False)
    run = Mock(
        return_value=CompletedProcess(
            [], 0, b"TCP 127.0.0.1:45001 0.0.0.0:0 LISTENING 123\n", b""
        )
    )
    monkeypatch.setattr(owned, "run_manager_command", run)
    assert owned._owns_listener(123, 45001, 1)
    run.return_value.stdout = b"TCP 0.0.0.0:45001 0.0.0.0:0 LISTENING 123\nTCP 127.0.0.1:45001 0.0.0.0:0 LISTENING 456\n"
    assert not owned._owns_listener(123, 45001, 1)


def test_linux_listener_probe_matches_process_socket_inode(monkeypatch):
    from arknights_mower.utils.device.adb_client import owned

    descriptor = "/proc/123/fd/3"
    readlink = Mock(return_value="socket:[100]")

    def path(location):
        if location == "/proc/123/net/tcp":
            return SimpleNamespace(
                open=lambda: StringIO(
                    "0: 0100007F:AFC9 00000000:0000 0A 0 0 0 0 0 100\n"
                )
            )
        assert location == "/proc/123/fd"
        return SimpleNamespace(iterdir=lambda: iter([descriptor]))

    monkeypatch.setattr(owned.sys, "platform", "linux")
    monkeypatch.setattr(owned, "os", SimpleNamespace(name="posix", readlink=readlink))
    monkeypatch.setattr(owned, "Path", path)
    external = Mock(
        side_effect=AssertionError("Linux listener tests cannot execute host commands")
    )
    monkeypatch.setattr(owned, "run_manager_command", external)
    assert owned._owns_listener(123, 45001, 1)
    readlink.assert_called_once_with(descriptor)
    readlink.return_value = "socket:[200]"
    assert not owned._owns_listener(123, 45001, 1)
    external.assert_not_called()


def test_owned_probes_never_contact_the_shared_service(service):
    service.owner.recover("adb", timeout=10)
    service.owner.check("adb", timeout=10)
    assert all(
        call.kwargs["address"] == ("127.0.0.1", 45001)
        for call in service.probe.call_args_list
    )


def test_listener_verification_does_not_extend_startup_deadline(service):
    def late_listener(*args):
        service.clock.now += 10
        return True

    service.listener.side_effect = late_listener
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=5)
    service.probe.assert_not_called()
    service.children[0].terminate.assert_called_once()


def test_owned_cleanup_error_retains_its_identity_at_the_application_boundary(
    service, application
):
    with application.control.run():
        application.control.start().unwrap()
        service.probe.side_effect = SharedADBError("stalled")
        assert not application.control.recover().ok
        service.clock.now += 30
        service.children[0].wait.side_effect = TimeoutExpired("adb", 1)
        result = application.control.recover()
        assert not result.ok
        assert result.error.cause.cleanup_failed
        assert not application.control.shutdown_requested
        assert len(service.children) == 1
        application.adapter.rebind.assert_not_called()
    assert len(service.children) == 1


@pytest.mark.parametrize("stage", ["host", "listener"])
def test_exhausted_budget_does_not_count_as_failed_service_observation(service, stage):
    service.owner.recover("adb", timeout=10)

    def delayed_success(*args, **kwargs):
        service.clock.now += 5
        return 41 if stage == "host" else True

    observation = service.probe if stage == "host" else service.listener
    observation.side_effect = delayed_success
    for _ in range(2):
        with pytest.raises(SharedADBError, match="预算"):
            service.owner.recover("adb", timeout=5)
        service.clock.now += 30
    observation.side_effect = None
    service.probe.side_effect = SharedADBError("first actual failure")
    with pytest.raises(SharedADBError):
        service.owner.recover("adb", timeout=5)
    assert service.owner._failed_probes == 1
    assert len(service.children) == 1
    service.children[0].terminate.assert_not_called()


def test_non_probe_failure_never_authorizes_rebuild_from_previous_probe_window(service):
    service.owner.recover("adb", timeout=10)
    service.probe.side_effect = SharedADBError("stalled")
    for _ in range(2):
        with pytest.raises(SharedADBError):
            service.owner.recover("adb", timeout=10)
    service.clock.now += 30
    service.runner.return_value.stdout = b"Android Debug Bridge version 1.0.42\n"
    with pytest.raises(SharedADBError, match="协议不一致"):
        service.owner.recover("different-adb", timeout=10)
    assert len(service.children) == 1
    service.children[0].terminate.assert_not_called()


def test_generation_change_survives_a_failed_recovery_cycle(service, application):
    with application.control.run():
        device = application.control.start().unwrap()
        service.probe.side_effect = SharedADBError("stalled")
        assert not application.control.recover().ok
        service.clock.now += 30
        service.probe.side_effect = [SharedADBError("stalled"), 41]
        application.adb.frame = None
        assert not application.control.recover().ok
        assert service.owner.generation == 2
        assert application.control._bound_adb_generation == 1
        application.adapter.rebind.assert_not_called()
        service.probe.side_effect = None
        application.adb.frame = (1920, 1080)
        assert application.control.recover().unwrap() is device
        application.adapter.rebind.assert_called_once()
        assert application.control._bound_adb_generation == 2
        assert application.session.actions == 0
