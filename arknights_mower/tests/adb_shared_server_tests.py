import errno
import json
import multiprocessing
import os
import socket
import subprocess
import sys
import time
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client import shared
from arknights_mower.utils.device.adb_client.server import (
    SharedADBError,
    SharedADBHandshakeTimeout,
    SharedADBStopTimeout,
    probe_adb_server,
)
from arknights_mower.utils.device.adb_client.shared import SharedADBRecovery


class Clock:
    def __init__(self):
        self.now = 0
        self.wall = 1000

    def monotonic(self):
        return self.now

    def wall_clock(self):
        return self.wall

    def sleep(self, seconds):
        self.now += seconds
        self.wall += seconds


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(
        shared,
        "terminate_verified_adb",
        Mock(side_effect=SharedADBError("无法核验所选 ADB 进程")),
    )
    for name in (
        "ADB_SERVER_SOCKET",
        "ANDROID_ADB_SERVER_ADDRESS",
        "ANDROID_ADB_SERVER_PORT",
        "ADB_SERVER_PORT",
    ):
        monkeypatch.delenv(name, raising=False)
    clock = Clock()
    host = SimpleNamespace(
        version=41, mutations=[], clients={"selected-adb": (41, "35.0.2")}
    )

    def probe(timeout):
        if isinstance(host.version, Exception):
            raise host.version
        return host.version

    def kill(timeout):
        host.mutations.append("host:kill")
        host.version = None

    def run(argv, **kwargs):
        if argv[1] == "version":
            protocol, release = host.clients[argv[0]]
            return subprocess.CompletedProcess(
                argv,
                0,
                f"Android Debug Bridge version 1.0.{protocol}\nVersion {release}\n".encode(),
                b"",
            )
        assert argv[0] in host.clients and argv[1:] == ["start-server"]
        host.mutations.append("start-server")
        host.version = host.clients[argv[0]][0]
        return subprocess.CompletedProcess(argv, 0, b"", b"")

    runner, observer, killer = (
        Mock(side_effect=run),
        Mock(side_effect=probe),
        Mock(side_effect=kill),
    )
    options = dict(
        lock_path=tmp_path / "shared.lock",
        run=runner,
        probe=observer,
        kill=killer,
        monotonic=clock.monotonic,
        wall_clock=clock.wall_clock,
        sleep=clock.sleep,
    )
    return SimpleNamespace(
        recovery=SharedADBRecovery(**options),
        options=options,
        clock=clock,
        host=host,
        runner=runner,
        probe=observer,
        kill=killer,
    )


def establish_failure(service):
    service.host.version = SharedADBHandshakeTimeout("host handshake stalled")
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    service.clock.sleep(30)


def test_wedged_protocol_stop_terminates_verified_listener_before_start(
    service, monkeypatch
):
    from arknights_mower.utils.device.adb_client.server import kill_adb_server

    establish_failure(service)
    factory = MagicMock()
    factory.return_value.__enter__.return_value.connect.side_effect = socket.timeout(
        "shared listener never accepts"
    )
    service.recovery._kill = None
    monkeypatch.setattr(
        shared,
        "kill_adb_server",
        lambda timeout, **kwargs: kill_adb_server(
            timeout, socket_factory=factory, **kwargs
        ),
    )

    def terminate(adb_path, timeout, **kwargs):
        assert adb_path == "selected-adb"
        assert timeout > 0
        assert service.host.mutations == []
        service.host.mutations.append("verified process stop")
        service.host.version = None
        return True

    fallback = Mock(side_effect=terminate)
    monkeypatch.setattr(shared, "terminate_verified_adb", fallback, raising=False)

    assert service.recovery.recover("selected-adb", timeout=5)

    fallback.assert_called_once()
    assert service.host.mutations == ["verified process stop", "start-server"]
    assert service.recovery.generation == 1


def test_protocol_stop_fallback_skips_restart_when_service_recovers(
    service, monkeypatch
):
    establish_failure(service)
    service.kill.side_effect = SharedADBStopTimeout("protocol stop timed out")

    def recovered(*args, **kwargs):
        service.host.version = 41
        return False

    fallback = Mock(side_effect=recovered)
    monkeypatch.setattr(shared, "terminate_verified_adb", fallback)

    assert service.recovery.recover("selected-adb", timeout=5) is False

    fallback.assert_called_once()
    assert service.host.mutations == []
    assert service.recovery.generation == 1


def test_unverified_protocol_stop_retains_failure_and_attempt_without_start(
    service, monkeypatch
):
    establish_failure(service)
    service.kill.side_effect = SharedADBStopTimeout("protocol stop timed out")
    fallback = Mock(side_effect=SharedADBError("端口由其他程序占用"))
    monkeypatch.setattr(shared, "terminate_verified_adb", fallback)

    with pytest.raises(
        SharedADBError, match="protocol stop timed out；端口由其他程序占用"
    ):
        service.recovery.recover("selected-adb", timeout=5)

    state = json.loads(service.options["lock_path"].read_bytes()[1:])
    assert state["generation"] == 1
    assert state["last_attempt"] == service.clock.wall
    assert service.host.mutations == []
    fallback.assert_called_once()


def test_process_stop_without_confirmed_port_release_never_starts(service, monkeypatch):
    establish_failure(service)
    service.kill.side_effect = SharedADBStopTimeout("protocol stop timed out")
    fallback = Mock(return_value=True)
    monkeypatch.setattr(shared, "terminate_verified_adb", fallback)
    started = service.clock.now

    with pytest.raises(SharedADBError, match="时间预算已耗尽"):
        service.recovery.recover("selected-adb", timeout=5)

    assert service.clock.now - started == pytest.approx(5)
    assert service.host.mutations == []
    fallback.assert_called_once()


@pytest.fixture
def different_adb_clients(service):
    paths = []
    for name, release in (
        ("platform tools", "36.0.0"),
        ("vendor tools", "32.0.0-vendor"),
    ):
        binary = service.options["lock_path"].parent / name / "adb.exe"
        binary.parent.mkdir()
        binary.touch()
        paths.append(str(binary))
        service.host.clients[str(binary)] = (41, release)
    return tuple((SharedADBRecovery(**service.options), path) for path in paths)


def test_different_compatible_binaries_share_healthy_server_without_actions(
    service, different_adb_clients
):
    action = Mock()
    for recovery, binary in (*different_adb_clients, *different_adb_clients):
        assert recovery.recover(binary, timeout=5, action=action) is False
        assert recovery.adb_path == binary
        assert recovery.generation == 0
        assert recovery._lock_path == service.options["lock_path"]
    assert [entry.args[0] for entry in service.runner.call_args_list] == [
        [binary, "version"]
        for _, binary in (*different_adb_clients, *different_adb_clients)
    ]
    action.assert_not_called()
    assert service.host.mutations == []
    assert not service.options["lock_path"].exists()


@pytest.mark.parametrize("starter", [0, 1])
def test_different_binary_reuses_first_clients_started_server(
    service, different_adb_clients, starter
):
    recovery, binary = different_adb_clients[starter]
    peer, peer_binary = different_adb_clients[1 - starter]
    service.host.version = None
    assert recovery.recover(binary, timeout=5) is True
    assert peer.recover(peer_binary, timeout=5) is False
    assert recovery.adb_path == binary
    assert peer.adb_path == peer_binary
    assert recovery.generation == peer.generation == 1
    assert service.host.mutations == ["start-server"]
    assert [
        entry.args[0]
        for entry in service.runner.call_args_list
        if entry.args[0][1] == "start-server"
    ] == [[binary, "start-server"]]
    service.kill.assert_not_called()


@pytest.mark.parametrize("starter", [0, 1])
def test_incompatible_peer_never_replaces_first_started_server(
    service, different_adb_clients, starter
):
    recovery, binary = different_adb_clients[starter]
    peer, peer_binary = different_adb_clients[1 - starter]
    service.host.clients[binary] = (40, "older-vendor")
    service.host.version = None
    assert recovery.recover(binary, timeout=5) is True
    with pytest.raises(SharedADBError, match="版本不一致"):
        peer.recover(peer_binary, timeout=5)
    assert recovery.recover(binary, timeout=5) is False
    assert recovery.adb_path == binary
    assert peer.adb_path == peer_binary
    assert service.host.version == 40
    assert service.host.mutations == ["start-server"]
    service.kill.assert_not_called()


@pytest.mark.parametrize("protocol", [40, 42])
def test_different_incompatible_binary_never_interrupts_compatible_peer(
    service, different_adb_clients, protocol
):
    recovery, binary = different_adb_clients[0]
    peer, peer_binary = different_adb_clients[1]
    service.host.clients[peer_binary] = (protocol, "vendor-mismatch")
    action = Mock()
    with pytest.raises(SharedADBError, match="版本不一致"):
        peer.recover(peer_binary, timeout=5, action=action)
    assert recovery.recover(binary, timeout=5) is False
    assert recovery.adb_path == binary
    assert peer.adb_path == peer_binary
    assert recovery.generation == peer.generation == 0
    assert service.host.version == 41
    assert service.host.mutations == []
    action.assert_not_called()
    service.kill.assert_not_called()


@pytest.mark.parametrize("starter", [0, 1])
def test_different_binary_restart_updates_peer_generation_without_second_restart(
    service, different_adb_clients, starter
):
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for recovery, binary in different_adb_clients:
        with pytest.raises(SharedADBError, match="30 秒"):
            recovery.recover(binary, timeout=5)
    service.clock.sleep(30)
    recovery, binary = different_adb_clients[starter]
    peer, peer_binary = different_adb_clients[1 - starter]
    assert recovery.recover(binary, timeout=5) is True
    assert peer.recover(peer_binary, timeout=5) is False
    assert recovery.adb_path == binary
    assert peer.adb_path == peer_binary
    assert recovery.generation == peer.generation == 1
    assert service.host.mutations == ["host:kill", "start-server"]
    service.kill.assert_called_once()
    assert [
        entry.args[0]
        for entry in service.runner.call_args_list
        if entry.args[0][1] == "start-server"
    ] == [[binary, "start-server"]]


def test_failed_restart_cooldown_is_shared_across_different_binaries(
    service, different_adb_clients
):
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for recovery, binary in different_adb_clients:
        with pytest.raises(SharedADBError, match="30 秒"):
            recovery.recover(binary, timeout=5)
    service.clock.sleep(30)
    recovery, binary = different_adb_clients[0]
    peer, peer_binary = different_adb_clients[1]
    service.kill.side_effect = SharedADBError("host:kill rejected")
    with pytest.raises(SharedADBError, match="host:kill rejected"):
        recovery.recover(binary, timeout=5)
    with pytest.raises(SharedADBError, match="冷却"):
        peer.recover(peer_binary, timeout=5)
    assert recovery.generation == peer.generation == 1
    service.kill.assert_called_once()
    assert service.host.mutations == []


@pytest.fixture
def shared_applications(service, different_adb_clients):
    from arknights_mower.tests.device_session_tests import Adapter, Preflight, Simulator
    from arknights_mower.utils.config.conf import Conf
    from arknights_mower.utils.device.application import DeviceControl
    from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
    from arknights_mower.utils.device.session_io import ProductionSessionADB

    targets = {
        binary: f"127.0.0.1:{19001 + index}"
        for index, (_, binary) in enumerate(different_adb_clients)
    }
    states = {serial: "device" for serial in targets.values()}
    original_run = service.runner.side_effect

    def run(argv, **kwargs):
        if argv[1] in {"version", "start-server"}:
            result = original_run(argv, **kwargs)
            if argv[1] == "start-server":
                states.clear()
            return result
        if argv[1:] == ["devices"]:
            output = "List of devices attached\n" + "\n".join(
                f"{serial}\t{state}" for serial, state in states.items()
            )
        else:
            serial = argv[2]
            assert serial == targets[argv[0]]
            if argv[1] == "disconnect":
                state = states.pop(serial, None)
                output = (
                    f"disconnected {serial}"
                    if state is not None
                    else f"error: no such device '{serial}'"
                )
            elif argv[1] == "connect":
                states[serial] = "device"
                output = f"connected to {serial}"
            elif argv[1:] == ["-s", serial, "shell", "getprop", "sys.boot_completed"]:
                output = "1"
            elif argv[1:] == ["-s", serial, "shell", "wm", "size"]:
                output = "Physical size: 1920x1080"
            else:
                raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    def frame(binary, serial, timeout):
        assert timeout > 0
        assert serial == targets[binary]
        assert states.get(serial) == "device"
        return 1920, 1080

    service.runner.side_effect = run
    applications = []
    with ExitStack() as resources:
        for index, (recovery, binary) in enumerate(different_adb_clients):
            conf = Conf(
                device={
                    "preset_id": "windows.mumu12",
                    "instance_id": str(index),
                    "last_serial": targets[binary],
                    "adb_path": binary,
                    "screenshot_backend": "adb_gzip",
                }
            )
            simulator = Simulator()
            simulator.state, simulator.serial = "running", targets[binary]
            adapter = Adapter()
            adapter.rebind = Mock(wraps=adapter.rebind)
            adb = ProductionSessionADB(
                run=service.runner,
                probe=service.probe,
                monotonic=service.clock.monotonic,
                frame=frame,
            )
            session = DeviceSession(
                adb, simulator, clock=service.clock, policy=RecoveryPolicy(local_wait=1)
            )
            control = DeviceControl(
                lambda conf=conf: conf,
                adapter,
                session=session,
                preflight=Preflight(),
                adb_recovery=recovery,
            )
            resources.enter_context(control.run())
            applications.append(
                SimpleNamespace(
                    control=control,
                    session=session,
                    conf=conf,
                    adapter=adapter,
                    recovery=recovery,
                    simulator=simulator,
                    states=states,
                )
            )
        yield applications


@pytest.mark.parametrize("starter", [0, 1])
def test_different_adb_instances_restore_own_targets_and_helpers_after_shared_restart(
    service, shared_applications, starter
):
    snapshots = [application.conf.model_dump() for application in shared_applications]
    devices = [
        application.control.start().unwrap() for application in shared_applications
    ]
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for application in shared_applications:
        assert not application.control.recover().ok
        application.adapter.rebind.assert_not_called()
    service.clock.sleep(30)
    for index in (starter, 1 - starter):
        application = shared_applications[index]
        assert application.control.recover().unwrap() is devices[index]
        application.adapter.rebind.assert_called_once()
        result = application.adapter.rebind.call_args.args[1]
        assert result.serial == application.conf.device.last_serial
        assert result.adb_path == application.conf.device.adb_path
        assert application.session.adb_path == application.conf.device.adb_path
        assert application.recovery.generation == 1
        assert application.control._bound_adb_generation == 1
        assert application.simulator.actions == []
        assert application.conf.model_dump() == snapshots[index]
        assert application.control.recover().unwrap() is devices[index]
        application.adapter.rebind.assert_called_once()
    assert service.host.mutations == ["host:kill", "start-server"]
    service.kill.assert_called_once()
    assert [
        entry.args[0]
        for entry in service.runner.call_args_list
        if entry.args[0][1] == "start-server"
    ] == [[shared_applications[starter].conf.device.adb_path, "start-server"]]
    assert [
        entry.args[0]
        for entry in service.runner.call_args_list
        if entry.args[0][1] == "connect"
    ] == [
        [
            shared_applications[index].conf.device.adb_path,
            "connect",
            shared_applications[index].conf.device.last_serial,
        ]
        for index in (starter, 1 - starter)
    ]


@pytest.mark.parametrize("unverified", [0, 1])
def test_different_adb_peer_waits_for_valid_frame_before_generation_binding(
    service, shared_applications, unverified
):
    snapshots = [application.conf.model_dump() for application in shared_applications]
    devices = [
        application.control.start().unwrap() for application in shared_applications
    ]
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for application in shared_applications:
        assert not application.control.recover().ok
    service.clock.sleep(30)
    healthy = shared_applications[1 - unverified]
    affected = shared_applications[unverified]
    original_frame = affected.session.adb._frame
    frame_dimensions = [(1280, 720)]

    def sample_frame(binary, serial, timeout):
        original_frame(binary, serial, timeout)
        return frame_dimensions[0]

    affected.session.adb._frame = Mock(side_effect=sample_frame)
    assert healthy.control.recover().unwrap() is devices[1 - unverified]
    result = affected.control.recover()
    assert not result.ok
    assert result.error.code == "frame_failed"
    assert affected.recovery.generation == 1
    assert affected.control._bound_adb_generation == 0
    affected.adapter.rebind.assert_not_called()
    assert healthy.control.recover().unwrap() is devices[1 - unverified]
    healthy.adapter.rebind.assert_called_once()
    frame_dimensions[0] = (1920, 1080)
    assert affected.control.recover().unwrap() is devices[unverified]
    assert affected.control._bound_adb_generation == 1
    affected.adapter.rebind.assert_called_once()
    for index, application in enumerate(shared_applications):
        assert application.conf.model_dump() == snapshots[index]
        assert application.simulator.actions == []
    assert service.host.mutations == ["host:kill", "start-server"]
    service.kill.assert_called_once()


@pytest.mark.parametrize("incompatible", [0, 1])
@pytest.mark.parametrize("protocol", [40, 42])
def test_incompatible_instance_preserves_healthy_peer_and_both_configurations(
    service, shared_applications, incompatible, protocol
):
    snapshots = [application.conf.model_dump() for application in shared_applications]
    devices = [
        application.control.start().unwrap() for application in shared_applications
    ]
    affected = shared_applications[incompatible]
    healthy = shared_applications[1 - incompatible]
    service.host.clients[affected.conf.device.adb_path] = (protocol, "vendor-mismatch")
    service.runner.reset_mock()
    result = affected.control.recover()
    assert not result.ok
    assert result.error.code == "recovery_failed"
    assert "版本不一致" in result.error.message
    assert healthy.control.recover().unwrap() is devices[1 - incompatible]
    operation = Mock(return_value="healthy task")
    assert healthy.control.execute(operation).unwrap() == "healthy task"
    operation.assert_called_once_with(devices[1 - incompatible])
    for index, application in enumerate(shared_applications):
        assert application.conf.model_dump() == snapshots[index]
        assert not application.control.shutdown_requested
        assert application.recovery.generation == 0
        application.adapter.rebind.assert_not_called()
    assert all(
        entry.args[0][1] == "version"
        for entry in service.runner.call_args_list
        if entry.args[0][0] == affected.conf.device.adb_path
    )
    assert service.host.version == 41
    assert service.host.mutations == []
    service.kill.assert_not_called()
    service.host.clients[affected.conf.device.adb_path] = (41, "compatible-replacement")
    assert affected.control.recover().unwrap() is devices[incompatible]
    assert affected.conf.model_dump() == snapshots[incompatible]
    affected.adapter.rebind.assert_not_called()
    assert service.host.mutations == []


@pytest.mark.parametrize("offline", [(0,), (1,), (0, 1)])
def test_different_adb_offline_targets_reconnect_without_restarting_healthy_host(
    service, shared_applications, offline
):
    snapshots = [application.conf.model_dump() for application in shared_applications]
    devices = [
        application.control.start().unwrap() for application in shared_applications
    ]
    for index in offline:
        application = shared_applications[index]
        application.states[application.conf.device.last_serial] = "offline"
    service.runner.reset_mock()
    for index, application in enumerate(shared_applications):
        assert application.control.recover().unwrap() is devices[index]
        assert application.conf.model_dump() == snapshots[index]
        assert application.recovery.generation == 0
        assert application.simulator.actions == []
        if index in offline:
            application.adapter.rebind.assert_called_once()
        else:
            application.adapter.rebind.assert_not_called()
    assert [
        entry.args[0]
        for entry in service.runner.call_args_list
        if entry.args[0][1] == "connect"
    ] == [
        [
            shared_applications[index].conf.device.adb_path,
            "connect",
            shared_applications[index].conf.device.last_serial,
        ]
        for index in offline
    ]
    assert service.host.version == 41
    assert service.host.mutations == []
    service.kill.assert_not_called()


@pytest.mark.parametrize("closed", [0, 1])
def test_closing_different_adb_instance_preserves_healthy_peer_dispatch(
    service, shared_applications, closed
):
    devices = [
        application.control.start().unwrap() for application in shared_applications
    ]
    peer = shared_applications[1 - closed]
    original = peer.conf.model_dump()
    assert shared_applications[closed].control.close().ok
    assert devices[closed].closed
    assert peer.control.recover().unwrap() is devices[1 - closed]
    operation = Mock(return_value="healthy task")
    assert peer.control.execute(operation).unwrap() == "healthy task"
    operation.assert_called_once_with(devices[1 - closed])
    assert peer.conf.model_dump() == original
    peer.adapter.rebind.assert_not_called()
    assert service.host.version == 41
    assert service.host.mutations == []
    service.kill.assert_not_called()


def test_healthy_host_does_not_restart_or_consume_action_even_if_devices_offline(
    service,
):
    action = Mock()
    assert service.recovery.recover("selected-adb", timeout=5, action=action) is False
    assert service.recovery.adb_path == "selected-adb"
    assert service.recovery.generation == 0
    assert service.host.mutations == []
    assert all(
        call.args[0] == ["selected-adb", "version"]
        for call in service.runner.call_args_list
    )
    action.assert_not_called()


def test_absent_host_starts_selected_binary_without_kill(service):
    service.host.version = None
    action = Mock(side_effect=lambda operation: operation())
    assert service.recovery.recover("selected-adb", timeout=5, action=action) is True
    action.assert_called_once()
    assert service.host.mutations == ["start-server"]
    assert service.recovery.generation == 1


def test_restart_requires_two_cycles_and_thirty_monotonic_seconds(service):
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for advance in (0, 10, 19):
        service.clock.sleep(advance)
        with pytest.raises(SharedADBError, match="30 秒"):
            service.recovery.recover("selected-adb", timeout=5)
        assert service.host.mutations == []
        assert service.recovery.generation == 0
    service.clock.sleep(1)
    action = Mock(side_effect=lambda operation: operation())
    assert service.recovery.recover("selected-adb", timeout=5, action=action) is True
    action.assert_called_once()
    assert service.host.mutations == ["host:kill", "start-server"]
    assert service.recovery.generation == 1


def test_unanswered_connect_escalates_through_the_same_restart_window(service):
    """A connect timeout is an unanswered listener, not an unverifiable host.

    The observation reaches recovery as an unanswered handshake, so it counts
    towards the sustained-failure window and recovery reaches the restart
    decision. Classifying it as an unverifiable host instead aborts every cycle
    before that decision, so the stalled server is never replaced.
    """

    def wedged(timeout):
        """A loopback connect the host never completes, seen from the probe."""
        factory = MagicMock()
        factory.return_value.__enter__.return_value.connect.side_effect = (
            socket.timeout("connect stalled")
        )
        return probe_adb_server(timeout, socket_factory=factory)

    clock = Clock()
    # The client-version command is the only CLI call before the restart.
    run = Mock(
        return_value=subprocess.CompletedProcess(
            ["selected-adb", "version"],
            0,
            b"Android Debug Bridge version 1.0.41\nVersion 35.0.2\n",
            b"",
        )
    )
    kill = Mock()
    recovery = SharedADBRecovery(
        lock_path=service.options["lock_path"],
        run=run,
        probe=wedged,
        kill=kill,
        monotonic=clock.monotonic,
        wall_clock=clock.wall_clock,
        sleep=clock.sleep,
    )
    for advance in (0, 1):
        clock.sleep(advance)
        with pytest.raises(SharedADBError, match="30 秒"):
            recovery.recover("selected-adb", timeout=5)
        assert kill.call_count == 0
        assert recovery.generation == 0
    clock.sleep(30)
    with pytest.raises(SharedADBError):
        recovery.recover("selected-adb", timeout=5)
    assert kill.call_count == 1
    assert recovery.generation == 1
    assert run.call_args.args[0] == ["selected-adb", "version"]


def test_unverified_unanswered_connect_remains_bounded_without_start(service):
    """Unverified port ownership preserves the listener and recorded cooldown."""
    clock = Clock()
    run = Mock(
        return_value=subprocess.CompletedProcess(
            ["selected-adb", "version"],
            0,
            b"Android Debug Bridge version 1.0.41\nVersion 35.0.2\n",
            b"",
        )
    )
    recovery = SharedADBRecovery(
        lock_path=service.options["lock_path"],
        run=run,
        probe=Mock(
            side_effect=SharedADBHandshakeTimeout("共享 ADB server 未完成主机握手")
        ),
        kill=Mock(side_effect=SharedADBStopTimeout("无法显式停止共享 ADB server")),
        monotonic=clock.monotonic,
        wall_clock=clock.wall_clock,
        sleep=clock.sleep,
    )
    for _ in range(4):
        clock.sleep(30)
        with pytest.raises(SharedADBError):
            recovery.recover("selected-adb", timeout=5)
    assert run.call_args.args[0] == ["selected-adb", "version"]
    assert recovery.generation > 0


def test_wall_clock_jump_never_shortens_monotonic_failure_window(service):
    service.host.version = SharedADBHandshakeTimeout("stalled")
    with pytest.raises(SharedADBError):
        service.recovery.recover("selected-adb", timeout=5)
    service.clock.wall += 100000
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


@pytest.mark.parametrize(
    "response",
    [
        41,
        None,
        SharedADBError("EOF"),
        SharedADBError("malformed"),
        0,
        "0029",
        PermissionError(),
        OSError("reset"),
    ],
)
def test_non_timeout_observation_resets_failure_window(service, response):
    establish_failure(service)
    service.host.version = response
    if response in (41, None):
        service.recovery.recover("selected-adb", timeout=5)
    else:
        with pytest.raises(SharedADBError):
            service.recovery.recover("selected-adb", timeout=5)
    service.host.mutations.clear()
    service.host.version = SharedADBHandshakeTimeout("stalled again")
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery._failed_probes == 1
    assert service.host.mutations == []


def test_gap_longer_than_sixty_seconds_does_not_count_as_sustained_failure(service):
    establish_failure(service)
    service.clock.sleep(31)
    with pytest.raises(SharedADBError, match="30 秒"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


@pytest.mark.parametrize("locked_response", [41, 40, SharedADBError("malformed"), 0])
def test_locked_reprobe_prevents_restart_after_listener_recovers_or_changes(
    service, locked_response
):
    establish_failure(service)
    service.probe.side_effect = [SharedADBHandshakeTimeout("stalled"), locked_response]
    if locked_response == 41:
        assert service.recovery.recover("selected-adb", timeout=5) is False
    else:
        with pytest.raises(SharedADBError):
            service.recovery.recover("selected-adb", timeout=5)
    service.kill.assert_not_called()
    assert service.recovery._failed_probes == 0
    assert service.recovery.generation == 0


def test_initial_mismatch_never_authorizes_restart_from_old_timeout_window(service):
    establish_failure(service)
    service.host.version = 40
    with pytest.raises(SharedADBError, match="版本不一致"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_action_reprobes_immediately_before_mutating(service):
    establish_failure(service)

    def action(operation):
        service.host.version = 41
        assert operation() is True

    assert service.recovery.recover("selected-adb", timeout=5, action=action) is False
    assert service.host.mutations == []
    assert service.recovery.generation == 0


def test_action_budget_rejection_prevents_restart_and_generation_change(service):
    establish_failure(service)
    action = Mock(side_effect=RuntimeError("action budget exhausted"))
    with pytest.raises(RuntimeError, match="action budget"):
        service.recovery.recover("selected-adb", timeout=5, action=action)
    assert service.host.mutations == []
    assert service.recovery.generation == 0


@pytest.mark.parametrize("stage", ["initial", "probe", "action"])
def test_cancellation_never_authorizes_or_records_restart(service, stage):
    establish_failure(service)
    cancelled = [stage == "initial"]
    if stage == "probe":

        def observe(timeout):
            cancelled[0] = True
            raise SharedADBHandshakeTimeout("stalled")

        service.probe.side_effect = observe

    def action(operation):
        cancelled[0] = True
        return operation()

    with pytest.raises(MowerExit):
        service.recovery.recover(
            "selected-adb",
            timeout=5,
            cancelled=lambda: cancelled[0],
            action=action if stage == "action" else None,
        )
    assert service.recovery.generation == 0
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_cancellation_callable_can_raise_instead_of_returning_bool(service):
    cancelled = Mock(side_effect=MowerExit)
    with pytest.raises(MowerExit):
        service.recovery.recover("selected-adb", timeout=5, cancelled=cancelled)
    service.runner.assert_not_called()
    service.probe.assert_not_called()


def test_raising_cancellation_clears_previous_host_failure_window(service):
    establish_failure(service)
    with pytest.raises(MowerExit):
        service.recovery.recover(
            "selected-adb", timeout=5, cancelled=Mock(side_effect=MowerExit)
        )
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_total_probe_budget_exhaustion_is_not_a_host_failure(service):
    def observe(timeout):
        service.clock.sleep(5)
        raise SharedADBHandshakeTimeout("stalled")

    service.probe.side_effect = observe
    with pytest.raises(SharedADBError, match="时间预算"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery._failed_probes == 0
    assert service.host.mutations == []


def test_protocol_version_cannot_be_derived_from_unverified_binary(service):
    service.runner.return_value = subprocess.CompletedProcess(
        [], 0, b"unknown vendor", b""
    )
    service.runner.side_effect = None
    with pytest.raises(SharedADBError, match="协议版本"):
        service.recovery.recover("selected-adb", timeout=5)
    service.probe.assert_not_called()
    assert service.host.mutations == []


@pytest.mark.parametrize("locked_byte_unreadable", [False, True])
def test_failed_restart_persists_generation_before_kill_and_peer_observes_it(
    service, monkeypatch, locked_byte_unreadable
):
    establish_failure(service)
    if locked_byte_unreadable:
        monkeypatch.setattr(
            type(service.options["lock_path"]),
            "read_bytes",
            Mock(side_effect=PermissionError(errno.EACCES, "locked byte")),
        )

    def kill(timeout):
        assert service.recovery.generation == 1
        with service.options["lock_path"].open("rb") as handle:
            handle.seek(1)
            record = json.loads(handle.read(1024))
        assert record["generation"] == 1
        raise SharedADBError("host:kill failed")

    service.kill.side_effect = kill
    with pytest.raises(SharedADBError, match="host:kill"):
        service.recovery.recover("selected-adb", timeout=5)
    service.host.version = 41
    peer = SharedADBRecovery(**service.options)
    assert peer.recover("selected-adb", timeout=5) is False
    assert peer.generation == service.recovery.generation == 1


def test_missing_service_can_start_inside_failed_kill_cooldown(service):
    establish_failure(service)

    def kill(timeout):
        service.host.version = None
        raise SharedADBError("kill ACK lost")

    service.kill.side_effect = kill
    with pytest.raises(SharedADBError, match="ACK"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery.recover("selected-adb", timeout=5) is True
    assert service.recovery.generation == 2
    service.kill.assert_called_once()
    assert service.host.mutations == ["start-server"]


def test_rejected_kill_reports_promptly_without_waiting_or_starting(service):
    establish_failure(service)
    service.kill.side_effect = SharedADBError("停止请求（FAIL）")
    with pytest.raises(SharedADBError, match="FAIL"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.clock.now == 30
    assert service.recovery.generation == 1
    assert service.host.mutations == []


def test_failed_start_keeps_generation_and_missing_service_can_retry(service):
    service.host.version = None
    original = service.runner.side_effect

    def run(argv, **kwargs):
        if argv[1] == "start-server":
            raise subprocess.CalledProcessError(1, argv, stderr=b"cannot listen")
        return original(argv, **kwargs)

    service.runner.side_effect = run
    with pytest.raises(SharedADBError, match="恢复失败"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.recovery.generation == 1
    service.runner.side_effect = original
    assert service.recovery.recover("selected-adb", timeout=5) is True
    assert service.recovery.generation == 2


def test_peer_restart_cooldown_prevents_another_kill(service):
    peer = SharedADBRecovery(**service.options)
    service.host.version = SharedADBHandshakeTimeout("stalled")
    for recovery in (service.recovery, peer):
        with pytest.raises(SharedADBError, match="30 秒"):
            recovery.recover("selected-adb", timeout=5)
    service.clock.sleep(30)
    service.kill.side_effect = SharedADBError("host:kill stalled")
    with pytest.raises(SharedADBError, match="host:kill"):
        service.recovery.recover("selected-adb", timeout=5)
    with pytest.raises(SharedADBError, match="冷却"):
        peer.recover("selected-adb", timeout=5)
    assert peer.generation == 1
    service.kill.assert_called_once()
    service.clock.sleep(30)
    service.kill.side_effect = None
    service.kill.return_value = None
    service.probe.side_effect = [SharedADBHandshakeTimeout("stalled")] * 3 + [
        None,
        None,
        41,
    ]
    assert peer.recover("selected-adb", timeout=5) is True
    assert peer.generation == 2


def test_host_that_ignores_kill_is_not_force_killed_or_started(service):
    establish_failure(service)
    service.kill.side_effect = None
    with pytest.raises(SharedADBError, match="时间预算"):
        service.recovery.recover("selected-adb", timeout=0.5)
    assert service.recovery.generation == 1
    service.kill.assert_called_once()
    assert not any(
        call.args[0][1] == "start-server" for call in service.runner.call_args_list
    )
    assert service.clock.now == pytest.approx(30.5)


def test_server_appearing_between_stop_and_start_is_not_replaced(service):
    establish_failure(service)
    service.probe.side_effect = [SharedADBHandshakeTimeout("stalled")] * 3 + [None, 40]
    with pytest.raises(SharedADBError, match="版本不一致"):
        service.recovery.recover("selected-adb", timeout=5)
    service.kill.assert_called_once()
    assert service.recovery.generation == 1
    assert not any(
        call.args[0][1] == "start-server" for call in service.runner.call_args_list
    )


@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b"{}",
        b"x" * 1025,
        b'{"generation": -1, "last_attempt": 1}',
        b'{"generation": true, "last_attempt": 1}',
        b'{"generation": 1, "last_attempt": NaN}',
    ],
)
def test_invalid_coordination_state_fails_closed(service, content):
    service.options["lock_path"].write_bytes(b"\0" + content)
    service.host.version = SharedADBHandshakeTimeout("stalled")
    with pytest.raises(SharedADBError, match="恢复记录"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


def test_invalid_marker_prefix_never_authorizes_restart(service):
    service.options["lock_path"].write_bytes(b"x")
    service.host.version = SharedADBHandshakeTimeout("stalled")
    with pytest.raises(SharedADBError, match="恢复记录"):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


def hold_lock(path, acquired, release):
    recovery = SharedADBRecovery(lock_path=path)
    with recovery._locked(time.monotonic() + 10, None):
        acquired.set()
        if not release.wait(10):
            raise RuntimeError("test lock release timed out")


@pytest.mark.parametrize("client_index", [None, 0, 1])
def test_cross_process_lock_is_bounded_and_releases_without_unlinking(
    service, different_adb_clients, client_index
):
    recovery, binary = (
        (service.recovery, "selected-adb")
        if client_index is None
        else different_adb_clients[client_index]
    )
    context = multiprocessing.get_context("spawn")
    acquired, release = context.Event(), context.Event()
    process = context.Process(
        target=hold_lock, args=(service.options["lock_path"], acquired, release)
    )
    process.start()
    try:
        assert acquired.wait(5)
        assert recovery.recover(binary, timeout=5) is False
        assert service.clock.now == 0
        service.host.version = None
        with pytest.raises(SharedADBError, match="时间预算"):
            recovery.recover(binary, timeout=0.2)
        assert service.clock.now == pytest.approx(0.2)
        assert service.host.mutations == []
    finally:
        release.set()
        process.join(5)
        if process.is_alive():
            process.terminate()
            process.join(5)
    assert process.exitcode == 0
    assert service.options["lock_path"].exists()
    service.host.version = 41
    assert recovery.recover(binary, timeout=5) is False


def test_healthy_host_never_creates_coordination_marker(service):
    assert service.recovery.recover("selected-adb", timeout=5) is False
    assert not service.options["lock_path"].exists()
    assert service.recovery.generation == 0


def test_healthy_invalid_marker_warns_and_invalidates_helpers_once(
    service, monkeypatch
):
    service.options["lock_path"].write_bytes(b"\0partial-json")
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    for _ in range(3):
        assert service.recovery.recover("selected-adb", timeout=5) is False
    assert service.recovery.generation == 1
    assert service.clock.now == 0
    assert service.host.mutations == []
    assert service.options["lock_path"].read_bytes() == b"\0partial-json"
    log.warning.assert_called_once()
    assert "恢复协调记录不可读" in log.warning.call_args.args[0]
    assert "generation=" not in log.warning.call_args.args[0]


def test_healthy_unreadable_marker_continues_without_mutation(service, monkeypatch):
    service.options["lock_path"].mkdir()
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    assert service.recovery.recover("selected-adb", timeout=5) is False
    assert service.recovery.generation == 1
    assert service.host.mutations == []
    log.warning.assert_called_once()


def test_healthy_unwritable_marker_is_read_without_locking(service, monkeypatch):
    service.options["lock_path"].write_bytes(
        b'\0{"generation": 3, "last_attempt": 1000}'
    )
    monkeypatch.setattr(
        shared.os, "open", Mock(side_effect=PermissionError("read only"))
    )
    assert service.recovery.recover("selected-adb", timeout=5) is False
    assert service.recovery.generation == 3
    shared.os.open.assert_not_called()
    assert service.host.mutations == []


def test_unknown_generation_episode_then_restart_cannot_reuse_local_generation(service):
    marker = service.options["lock_path"]
    marker.write_bytes(b"\0partial-json")
    assert service.recovery.recover("selected-adb", timeout=5) is False
    helper_generation = service.recovery.generation
    marker.write_bytes(b'\0{"generation": 0, "last_attempt": 1000}')
    service.host.version = None
    assert service.recovery.recover("selected-adb", timeout=5) is True
    assert service.recovery.generation > helper_generation
    assert json.loads(marker.read_bytes()[1:])["generation"] == 1


@pytest.mark.parametrize("response", [None, 40, SharedADBHandshakeTimeout("stalled")])
def test_invalid_marker_never_authorizes_mutation_on_absent_mismatched_stalled_host(
    service, response
):
    service.options["lock_path"].write_bytes(b"\0partial-json")
    service.host.version = response
    with pytest.raises(SharedADBError):
        service.recovery.recover("selected-adb", timeout=5)
    assert service.host.mutations == []


def test_attempt_and_verified_outcome_log_generation_and_shared_blast_radius(
    service, monkeypatch
):
    establish_failure(service)
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    assert service.recovery.recover("selected-adb", timeout=5) is True
    log.warning.assert_called_once()
    log.info.assert_called_once()
    assert "其他主机工具的 ADB 连接可能断开" in log.warning.call_args.args[0]
    assert log.warning.call_args.args[1] == "重启"
    assert "共享 ADB 服务已%s" in log.info.call_args.args[0]
    assert log.info.call_args.args[1] == "重启"
    # One sentence per fact: no key=value diagnostics in operator-facing lines.
    for entry in (log.warning, log.info):
        assert "generation=" not in entry.call_args.args[0]
    assert service.recovery.generation == 1


def test_failed_attempt_logs_bounded_diagnostics_and_generation(service, monkeypatch):
    establish_failure(service)
    log = Mock()
    monkeypatch.setattr(shared, "logger", log)
    service.kill.side_effect = SharedADBError("x" * 2000)
    with pytest.raises(SharedADBError):
        service.recovery.recover("selected-adb", timeout=5)
    assert log.warning.call_count == 2
    assert "共享 ADB 服务%s未成功" in log.warning.call_args.args[0]
    assert log.warning.call_args.args[1] == "重启"
    assert len(log.warning.call_args.args[2]) == 1024
    log.info.assert_not_called()


def test_windows_empty_file_initializes_lock_byte_and_unlocks(service, monkeypatch):
    calls = []

    def locking(descriptor, mode, count):
        assert os.fstat(descriptor).st_size >= 1
        calls.append((mode, count))

    module = SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locking)
    monkeypatch.setitem(sys.modules, "msvcrt", module)
    with monkeypatch.context() as windows:
        windows.setattr(shared.os, "name", "nt")
        with pytest.raises(RuntimeError, match="test failure"):
            with service.recovery._locked(5, None):
                raise RuntimeError("test failure")
    assert calls == [(1, 1), (2, 1)]
    assert service.options["lock_path"].read_bytes() == b"\0"


def test_default_lock_path_is_shared_independent_of_binary(
    service, different_adb_clients, monkeypatch
):
    home = service.options["lock_path"].parent
    monkeypatch.setattr(shared.Path, "home", lambda: home)
    options = {
        name: value for name, value in service.options.items() if name != "lock_path"
    }
    clients = [
        (SharedADBRecovery(**options), binary) for _, binary in different_adb_clients
    ]
    expected = home / ".cache" / "arknights-mower" / "adb-5037.lock"
    for recovery, binary in clients:
        assert recovery._lock_path == expected
        assert recovery.recover(binary, timeout=5) is False
        assert recovery._lock_path == expected
        assert recovery.adb_path == binary
    assert not expected.exists()
    assert service.host.mutations == []
