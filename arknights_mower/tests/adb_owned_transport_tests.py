"""ADB consumers retain shared defaults and route owned transports explicitly."""

import io
import os
import shlex
import socket
import subprocess
import sys
from contextlib import nullcontext
from datetime import datetime, timedelta
from functools import partial
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, call

import pytest
import requests

from arknights_mower.utils import config
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device import (
    device,
    droidcast,
    endpoint_identity,
    nox_endpoint,
    screenshot,
)
from arknights_mower.utils.device.adb_client import core, server, session, utils
from arknights_mower.utils.device.adb_client import socket as adb_socket
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.ldplayer_endpoint import LDPlayerEndpointResolver
from arknights_mower.utils.device.maatouch import session as maatouch
from arknights_mower.utils.device.session_io import ProductionSessionADB
from arknights_mower.utils.device.touch_backend import TouchFailure

ADB = "/chosen adb/adb"
SERIAL = "127.0.0.1:5559"
BOOT_ID = b"42e9de7c-0aa1-4a25-aec5-81d7e8a1acef"


@pytest.fixture(autouse=True)
def hermetic_io(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External process or network I/O is not mocked")

    for name in ("run", "Popen", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    environment = {
        name: value
        for name, value in os.environ.items()
        if name != "PYTEST_CURRENT_TEST"
    }
    yield
    assert {
        name: value
        for name, value in os.environ.items()
        if name != "PYTEST_CURRENT_TEST"
    } == environment


@pytest.fixture(params=[False, True], ids=["shared", "owned"])
def transport(request, monkeypatch):
    owned = request.param
    port = 52137 if owned else 5037
    owner = (
        SimpleNamespace(
            port=port,
            address=("127.0.0.1", port),
            generation=1,
            adb_path=ADB,
            check=Mock(),
        )
        if owned
        else None
    )
    monkeypatch.setattr(server, "probe_adb_server", Mock(return_value=None))
    with server.adb_server_scope(owner):
        yield SimpleNamespace(
            owned=owned,
            address=server.adb_server_address,
            command=server.adb_command,
            options=server.adb_subprocess_options,
            owner=owner,
        )


def assert_child_options(options, transport):
    expected = transport.options()
    if transport.owned:
        assert options["env"] == expected["env"]
        assert options["env"] is not os.environ
        assert options["env"]["ADB_SERVER_SOCKET"] == "tcp:127.0.0.1:52137"
        assert options["env"]["ANDROID_ADB_SERVER_ADDRESS"] == "127.0.0.1"
        for name in ("ANDROID_ADB_SERVER_PORT", "ADB_SERVER_PORT"):
            assert options["env"][name] == "52137"
    else:
        assert "env" not in options
    assert not options.get("shell")


def test_socket_session_keeps_its_original_endpoint_during_retry(
    transport, monkeypatch
):
    first, replacement = Mock(), Mock()
    first.send.side_effect = socket.timeout("read-only query")
    factory = Mock(side_effect=[first, replacement])
    monkeypatch.setattr(session, "Socket", factory)
    connection = session.Session()
    try:
        monkeypatch.setattr(session, "adb_server_address", lambda: ("127.0.0.1", 52138))
        connection.request("host:version")
        assert connection.server == transport.address()
        assert factory.call_args_list == [
            call(transport.address(), 5),
            call(transport.address(), 10),
        ]
        first.close.assert_called_once_with()
    finally:
        connection.close()
    replacement.close.assert_called_once_with()


def test_raw_capture_socket_uses_selected_server_and_target(transport, monkeypatch):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.recv.side_effect = [b"OKAY", b"OKAY", b"frame", b""]
    connect = Mock(return_value=connection)
    monkeypatch.setattr(socket, "create_connection", connect)
    assert screenshot._adb_output(SERIAL, "screencap", 64, lambda: 2) == b"frame"
    connect.assert_called_once_with(transport.address(), timeout=2)
    services = [f"host:transport:{SERIAL}", "exec:screencap"]
    assert connection.sendall.call_args_list == [
        call(f"{len(service):04x}".encode() + service.encode()) for service in services
    ]
    connection.__exit__.assert_called_once()


def test_capture_guard_precedes_both_raw_socket_requests(transport, monkeypatch):
    connections = [Mock(), Mock()]
    for connection, output in zip(connections, [b"30\n", b"gzip frame"]):
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        connection.recv.side_effect = [b"OKAY", b"OKAY", output, b""]
    connect = Mock(side_effect=connections)
    guard = Mock()
    order = Mock()
    order.attach_mock(guard, "guard")
    order.attach_mock(connect, "connect")
    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setattr(screenshot, "guard_adb", guard)
    decoded = object()
    decoder = Mock(return_value=decoded)
    monkeypatch.setattr(screenshot, "decode_adb_frame", decoder)
    assert screenshot.capture_adb_frame(ADB, SERIAL) is decoded
    assert [entry[0] for entry in order.mock_calls] == ["guard", "connect", "connect"]
    for arguments in connect.call_args_list:
        assert arguments.args == (transport.address(),)
        assert 0 < arguments.kwargs["timeout"] <= screenshot.CAPTURE_TIMEOUT
    decoder.assert_called_once_with(b"gzip frame", header_size=16)


def test_check_output_routes_only_after_guard(transport, monkeypatch):
    order = Mock()
    guard = Mock(return_value=3)
    output = Mock(return_value=b"ok")
    order.attach_mock(guard, "guard")
    order.attach_mock(output, "output")
    monkeypatch.setattr(utils, "guard_adb", guard)
    monkeypatch.setattr(subprocess, "check_output", output)
    argv = [ADB, "-s", SERIAL, "shell", "getprop"]
    assert utils.run_cmd(argv, decode=True) == "ok"
    assert argv == [ADB, "-s", SERIAL, "shell", "getprop"]
    assert [entry[0] for entry in order.mock_calls] == ["guard", "output"]
    guard.assert_called_once_with(ADB, timeout=10, run=subprocess.run)
    assert output.call_args.args == (transport.command(argv),)
    assert output.call_args.kwargs["timeout"] == 3
    assert_child_options(output.call_args.kwargs, transport)


def test_client_helper_process_routes_after_guard(transport, monkeypatch):
    order = Mock()
    guard, spawn = Mock(), Mock()
    order.attach_mock(guard, "guard")
    order.attach_mock(spawn, "spawn")
    monkeypatch.setattr(core, "guard_adb", guard)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    client = object.__new__(core.Client)
    client.adb_bin, client.device_id = ADB, SERIAL
    assert client.process("helper", ["--input"]) is spawn.return_value
    assert [entry[0] for entry in order.mock_calls] == ["guard", "spawn"]
    assert spawn.call_args.args == (
        transport.command([ADB, "-s", SERIAL, "shell", "helper", "--input"]),
    )
    assert_child_options(spawn.call_args.kwargs, transport)


def test_maatouch_handshake_process_routes_after_guard(transport, monkeypatch):
    process = Mock(
        stdout=io.StringIO("^ 10 1920 1080 255\n$ 123\n"),
        stdin=io.StringIO(),
        returncode=0,
    )
    process.poll.return_value = None
    guard, spawn, order = Mock(), Mock(return_value=process), Mock()
    order.attach_mock(guard, "guard")
    order.attach_mock(spawn, "spawn")
    monkeypatch.setattr(maatouch, "guard_adb", guard)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    client = SimpleNamespace(adb_bin=ADB, device_id=SERIAL)
    helper = maatouch.Session(client, defer_start=True)
    monkeypatch.setattr(helper, "_io", lambda operation, timeout: operation())
    try:
        helper.start()
        assert helper.pid == "123"
        assert [entry[0] for entry in order.mock_calls] == ["guard", "spawn"]
        assert spawn.call_args.args == (
            transport.command(
                [
                    ADB,
                    "-s",
                    SERIAL,
                    "shell",
                    "CLASSPATH=/data/local/tmp/maatouch",
                    "app_process",
                    "/",
                    "com.shxyke.MaaTouch.App",
                ]
            ),
        )
        assert_child_options(spawn.call_args.kwargs, transport)
    finally:
        process.poll.return_value = 0
        helper.close()


def test_droidcast_helper_process_routes_after_guard(transport, monkeypatch):
    helper = droidcast.DroidCastSession(ADB, SERIAL)
    monkeypatch.setattr(helper, "close", Mock())
    monkeypatch.setattr(helper, "ensure_version", Mock(return_value="/chosen app.apk"))
    monkeypatch.setattr(helper, "_create_forward", Mock())
    monkeypatch.setattr(droidcast, "get_new_port", lambda: 52345)
    monkeypatch.setattr(requests, "Session", Mock())
    order, guard, spawn = Mock(), Mock(), Mock()
    order.attach_mock(guard, "guard")
    order.attach_mock(spawn, "spawn")
    monkeypatch.setattr(droidcast, "guard_adb", guard)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    helper.start()
    assert [entry[0] for entry in order.mock_calls] == ["guard", "spawn"]
    assert spawn.call_args.args == (
        transport.command(
            [
                ADB,
                "-s",
                SERIAL,
                "shell",
                "CLASSPATH='/chosen app.apk'",
                "app_process",
                "/",
                f"--nice-name={helper.name}",
                f"{droidcast.PACKAGE}.Main",
                "--port=52345",
            ]
        ),
    )
    assert_child_options(spawn.call_args.kwargs, transport)
    assert helper.http.trust_env is False


def test_forward_claim_survives_routed_command_deadline_failure(transport, monkeypatch):
    helper = droidcast.DroidCastSession(ADB, SERIAL)
    execute = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
    monkeypatch.setattr(subprocess, "run", execute)

    def expired_after_success(args, *, stage, runner):
        argv = transport.command([ADB, "-s", SERIAL, *args])
        runner(argv, timeout=1, **transport.options())
        raise TimeoutError("after successful forward")

    monkeypatch.setattr(helper, "_adb", expired_after_success)
    with pytest.raises(TimeoutError, match="successful forward"):
        helper._create_forward(52345)
    assert helper.port == 52345
    assert_child_options(execute.call_args.kwargs, transport)


@pytest.mark.parametrize("args", [["forward", "--list"], ["shell", "pidof", "helper"]])
def test_droidcast_commands_keep_central_guarded_routing(args, transport, monkeypatch):
    guarded = Mock(return_value=SimpleNamespace(stdout=b"ok"))
    monkeypatch.setattr(droidcast, "run_adb", guarded)
    helper = droidcast.DroidCastSession(ADB, SERIAL)
    assert helper._adb(args, stage="cleanup", cleanup=True) == b"ok"
    selector = [] if args == ["forward", "--list"] else ["-s", SERIAL]
    assert guarded.call_args.args == ([ADB, *selector, *args],)
    assert guarded.call_args.kwargs["timeout"] == droidcast.COMMAND_TIMEOUT


@pytest.mark.parametrize(
    "args",
    [
        ["forward", "--list"],
        ["forward", "--remove", "tcp:52345"],
        ["shell", "kill", "123"],
    ],
)
def test_droidcast_cleanup_uses_routed_argv_and_child_environment(
    args, transport, monkeypatch
):
    execute = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
    monkeypatch.setattr(subprocess, "run", execute)
    helper = droidcast.DroidCastSession(ADB, SERIAL)
    assert helper._adb(args, stage="cleanup", cleanup=True) == b""
    selector = [] if args == ["forward", "--list"] else ["-s", SERIAL]
    assert execute.call_args.args == (transport.command([ADB, *selector, *args]),)
    assert_child_options(execute.call_args.kwargs, transport)


@pytest.mark.parametrize("adb_capture", [False, True], ids=["external", "adb"])
def test_custom_capture_routes_only_adb_commands(adb_capture, transport, monkeypatch):
    command = "adb exec-out screencap -p" if adb_capture else "capture --png"
    configuration = SimpleNamespace(custom_screenshot=SimpleNamespace(command=command))
    monkeypatch.setattr(config, "conf", configuration)
    target = object.__new__(device.Device)
    target._profile = DeviceProfile(screenshot_backend="custom")
    target.client = SimpleNamespace(adb_bin=ADB)
    target.device_id = SERIAL
    frame = object()
    monkeypatch.setattr(device, "bytes2img", Mock(return_value=frame))
    order, guard, output = Mock(), Mock(return_value=3), Mock(return_value=b"png")
    order.attach_mock(guard, "guard")
    order.attach_mock(output, "output")
    monkeypatch.setattr(device, "guard_adb", guard)
    monkeypatch.setattr(subprocess, "check_output", output)
    assert target.capture_frame() is frame
    if adb_capture:
        assert [entry[0] for entry in order.mock_calls] == ["guard", "output"]
        expected = transport.command([ADB, "-s", SERIAL, "exec-out", "screencap", "-p"])
        assert output.call_args.kwargs["timeout"] == 3
        assert_child_options(output.call_args.kwargs, transport)
    else:
        guard.assert_not_called()
        expected = ["capture", "--png"]
        assert "env" not in output.call_args.kwargs
    assert output.call_args.args == (expected,)


@pytest.mark.parametrize(
    "consumer", ["check_output", "client", "maatouch", "custom", "raw", "droidcast"]
)
def test_guard_failure_prevents_any_process(consumer, transport, monkeypatch):
    rejected = Mock(side_effect=SharedADBError("refused"))
    spawn, output = Mock(), Mock()
    monkeypatch.setattr(subprocess, "Popen", spawn)
    monkeypatch.setattr(subprocess, "check_output", output)
    client = object.__new__(core.Client)
    client.adb_bin, client.device_id = ADB, SERIAL
    expected_error = SharedADBError
    if consumer == "check_output":
        monkeypatch.setattr(utils, "guard_adb", rejected)
        operation = partial(utils.run_cmd, [ADB, "devices"])
    elif consumer == "client":
        monkeypatch.setattr(core, "guard_adb", rejected)
        operation = partial(client.process, "helper")
    elif consumer == "maatouch":
        monkeypatch.setattr(maatouch, "guard_adb", rejected)
        operation = maatouch.Session(client, defer_start=True).start
    elif consumer == "raw":
        monkeypatch.setattr(screenshot, "guard_adb", rejected)
        operation = partial(screenshot.capture_adb_frame, ADB, SERIAL)
    elif consumer == "droidcast":
        monkeypatch.setattr(droidcast, "guard_adb", rejected)
        helper = droidcast.DroidCastSession(ADB, SERIAL)
        monkeypatch.setattr(helper, "close", Mock())
        monkeypatch.setattr(helper, "ensure_version", Mock(return_value="/helper.apk"))
        monkeypatch.setattr(helper, "_create_forward", Mock())
        monkeypatch.setattr(droidcast, "get_new_port", lambda: 52345)
        operation = helper.start
        expected_error = droidcast.DroidCastError
    else:
        monkeypatch.setattr(device, "guard_adb", rejected)
        monkeypatch.setattr(
            config,
            "conf",
            SimpleNamespace(
                custom_screenshot=SimpleNamespace(command="adb exec-out screencap -p")
            ),
        )
        target = object.__new__(device.Device)
        target._profile = DeviceProfile(screenshot_backend="custom")
        target.client, target.device_id = client, SERIAL
        operation = target.capture_frame
    with pytest.raises(expected_error, match="refused"):
        operation()
    spawn.assert_not_called()
    output.assert_not_called()


@pytest.mark.parametrize("command", ["list2", "launch", "quit", "powershell"])
def test_non_adb_vendor_commands_keep_default_environment(
    command, transport, monkeypatch
):
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, b"ok", b""))
    argv = ["manager", command]
    assert (
        endpoint_identity.run_endpoint_command(
            argv, timeout=3, run=runner, probe=None, monotonic=lambda: 0
        )
        == b"ok"
    )
    assert runner.call_args.args == (argv,)
    assert "env" not in runner.call_args.kwargs


def test_ldplayer_delegation_matches_direct_adb_without_affecting_vendor_commands(
    transport, monkeypatch, tmp_path
):
    manager = tmp_path / "ldconsole.exe"
    (tmp_path / "adb.exe").touch()
    calls = []
    profile = DeviceProfile(
        preset_id="windows.ldplayer9",
        instance_id="2",
        instance_name="chosen",
        last_serial=SERIAL,
        adb_path=ADB,
    )

    def runner(argv, **options):
        calls.append((argv, options))
        if argv[0] == str(manager):
            if argv[1] == "list2":
                output = b"2,chosen,0,0,1,223,224\n"
            else:
                assert argv[1:] == [
                    "adb",
                    "--index",
                    "2",
                    "--command",
                    endpoint_identity.BOOT_ID_COMMAND,
                ]
                output = BOOT_ID
        elif "devices" in argv:
            output = f"List of devices attached\n{SERIAL}\tdevice\n".encode()
        else:
            output = BOOT_ID
        return subprocess.CompletedProcess(argv, 0, output, b"")

    guard = Mock()
    monkeypatch.setattr(
        "arknights_mower.utils.device.ldplayer_endpoint.guard_adb", guard
    )
    resolver = LDPlayerEndpointResolver(
        run=runner, probe=lambda timeout: None, listener_ports=lambda pid, timeout: []
    )
    observation = resolver.inspect(profile, manager, 3)
    assert observation.serial == SERIAL
    guard.assert_called_once()
    assert guard.call_args.args == (str(tmp_path / "adb.exe"),)
    for argv, options in calls:
        if argv[:2] == [str(manager), "list2"]:
            assert "env" not in options
        else:
            assert_child_options(options, transport)
        if argv[0] == ADB and transport.owned:
            assert argv[:5] == [ADB, "-H", "127.0.0.1", "-P", "52137"]


@pytest.mark.parametrize("platform", ["nt", "posix"])
@pytest.mark.parametrize("selected_adb", [False, True], ids=["fallback", "selected"])
@pytest.mark.parametrize(
    "failure",
    ["none", "guard", "adblite", "missing-adblite", "kill", "missing-kill"],
)
def test_maa_connect_receives_platform_quoted_owned_prefix(
    platform, selected_adb, failure, transport, monkeypatch, tmp_path
):
    from arknights_mower.solvers import base_schedule

    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(base_schedule, "Message", int, raising=False)
    adb_path = (
        'C:\\Program Files\\chosen "adb"\\adb.exe'
        if platform == "nt"
        else "/chosen adb's directory/adb"
    )
    assistant = Mock()
    asst = ModuleType("asst.asst")
    asst.Asst = Mock(return_value=assistant)
    asst_utils = ModuleType("asst.utils")
    asst_utils.InstanceOptionType = SimpleNamespace(
        touch_type="touch", adblite_enabled=4, kill_on_adb_exit=5
    )
    asst_utils.Message = int
    monkeypatch.setitem(sys.modules, "asst", ModuleType("asst"))
    monkeypatch.setitem(sys.modules, "asst.asst", asst)
    monkeypatch.setitem(sys.modules, "asst.utils", asst_utils)
    configuration = SimpleNamespace(
        maa_path=str(tmp_path),
        maa_adb_path="fallback-adb",
        maa_touch_option="maatouch",
        maa_conn_preset="General",
    )
    monkeypatch.setattr(config, "conf", configuration)
    monkeypatch.setattr(
        base_schedule,
        "resolve_config_path",
        lambda path: str(tmp_path) if path == configuration.maa_path else adb_path,
    )
    monkeypatch.setattr(
        base_schedule,
        "os",
        SimpleNamespace(name=platform, path=os.path, environ=os.environ),
    )
    monkeypatch.setattr(base_schedule, "current_adb_server", lambda: transport.owner)
    monkeypatch.setattr(base_schedule, "adb_command", transport.command)
    guard = Mock(wraps=server.guard_adb)
    if failure == "guard":
        guard.side_effect = SharedADBError("guard refused")
    elif failure in {"adblite", "kill"}:
        rejected_option = 4 if failure == "adblite" else 5
        assistant.set_instance_option.side_effect = lambda option, value: (
            option != rejected_option
        )
    elif failure.startswith("missing-"):
        name = "adblite_enabled" if failure == "missing-adblite" else "kill_on_adb_exit"
        delattr(asst_utils.InstanceOptionType, name)
    monkeypatch.setattr(base_schedule, "guard_adb", guard)
    order = Mock()
    order.attach_mock(guard, "guard")
    order.attach_mock(assistant.connect, "connect")
    response = Mock(content=b"{}")
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(requests, "get", Mock(return_value=response))
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    solver.device = SimpleNamespace(
        client=SimpleNamespace(
            adb_bin=adb_path if selected_adb else None, device_id=SERIAL
        )
    )
    try:
        if transport.owned and failure != "none":
            with pytest.raises(SharedADBError):
                solver.initialize_maa()
            assistant.connect.assert_not_called()
            if failure == "guard":
                guard.assert_called_once_with(adb_path, timeout=10)
            else:
                guard.assert_not_called()
            return
        solver.initialize_maa()
        expected = adb_path
        if transport.owned:
            argv = transport.command([adb_path])
            expected = (
                subprocess.list2cmdline(argv) if platform == "nt" else shlex.join(argv)
            )
            if platform == "posix":
                assert shlex.split(expected) == argv
            assistant.set_instance_option.assert_has_calls([call(4, "0"), call(5, "0")])
            guard.assert_called_once_with(adb_path, timeout=10)
            assert [entry[0] for entry in order.mock_calls] == ["guard", "connect"]
        else:
            guard.assert_not_called()
        assistant.connect.assert_called_once_with(expected, SERIAL, "General")
        assert configuration.maa_adb_path == "fallback-adb"
        assert solver.device.client.adb_bin == (adb_path if selected_adb else None)
    finally:
        if hasattr(solver, "MAA"):
            solver.MAA.stop()


@pytest.mark.parametrize(
    "response,accepted",
    [
        ("Connected to emulator on ports 5558,5559", True),
        ("Emulator already registered on port 5559", True),
        ("Connected to emulator on ports 5554,5555", False),
        ("Emulator already registered on port 5555", False),
        ("connected to 127.0.0.1:5559", False),
    ],
)
def test_selected_emulator_alias_recovery_registers_only_owned_transport(
    response, accepted, transport
):
    reply = response if transport.owned else "reconnecting emulator-5558 [device]"
    runner = Mock(return_value=subprocess.CompletedProcess([], 0, reply.encode(), b""))
    adb = ProductionSessionADB(run=runner, probe=lambda timeout: None)
    assert adb.recover(ADB, "emulator-5558", 5) == (
        accepted if transport.owned else True
    )
    argv = (
        [ADB, "connect", "emu:5558,5559"]
        if transport.owned
        else [ADB, "-s", "emulator-5558", "reconnect"]
    )
    assert runner.call_count == 1
    assert runner.call_args.args == (transport.command(argv),)
    assert_child_options(runner.call_args.kwargs, transport)
    assert 0 < runner.call_args.kwargs["timeout"] <= 5


@pytest.mark.parametrize("kind", ["tcp", "emulator"])
@pytest.mark.parametrize("changed", [False, True], ids=["stable", "restarted"])
def test_ldplayer_empty_owned_inventory_connects_only_instance_candidates(
    kind, changed, monkeypatch, tmp_path
):
    manager = tmp_path / "ldconsole.exe"
    (tmp_path / "adb.exe").touch()
    serial = "127.0.0.1:18701" if kind == "tcp" else "emulator-5558"
    profile = DeviceProfile(
        preset_id="windows.ldplayer9",
        instance_id="2",
        instance_name="chosen",
        last_serial=serial if kind == "emulator" else "",
        adb_path=ADB,
    )
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    rows, calls = {}, []
    manager_reads = 0

    def runner(argv, **options):
        nonlocal manager_reads
        calls.append((argv, options))
        if argv[0] == str(manager):
            if argv[1] == "list2":
                manager_reads += 1
                process = 225 if changed and manager_reads == 2 else 224
                output = f"2,chosen,0,0,1,223,{process}\n".encode()
                assert "env" not in options
            else:
                assert rows.get(serial) == "device"
                assert options["env"]["ADB_SERVER_SOCKET"] == "tcp:127.0.0.1:52137"
                output = BOOT_ID
        else:
            assert argv[:5] == [ADB, "-H", "127.0.0.1", "-P", "52137"]
            args = argv[5:]
            if args[:1] == ["devices"]:
                output = (
                    "List of devices attached\n"
                    + "\n".join(f"{target}\t{state}" for target, state in rows.items())
                ).encode()
            elif args[:1] == ["connect"]:
                expected = serial if kind == "tcp" else "emu:5558,5559"
                if args[1] != expected:
                    raise subprocess.CalledProcessError(1, argv, stderr=b"refused")
                rows[serial] = "device"
                rows["127.0.0.1:19001"] = "device"
                output = b"connected"
            else:
                assert args[:2] == ["-s", serial]
                output = BOOT_ID
        return subprocess.CompletedProcess(argv, 0, output, b"")

    listeners = Mock(return_value=[serial] if kind == "tcp" else [])
    resolver = LDPlayerEndpointResolver(
        run=runner, probe=lambda timeout: None, listener_ports=listeners
    )
    with server.adb_server_scope(owner):
        if changed:
            with pytest.raises(endpoint_identity.InstanceBindingError) as error:
                resolver.inspect(profile, manager, 5)
            assert error.value.code == "binding_changed"
        else:
            assert resolver.inspect(profile, manager, 5).serial == serial
    assert manager_reads == 2
    assert listeners.call_args.args[0] == 224
    adb_commands = [argv[5:] for argv, _ in calls if argv[0] == ADB]
    assert adb_commands[0] == ["devices", "-l"]
    assert all("127.0.0.1:19001" not in argv for argv in adb_commands)
    if kind == "tcp":
        assert next(argv for argv in adb_commands if argv[0] == "connect") == [
            "connect",
            serial,
        ]
    else:
        assert ["connect", "emu:5558,5559"] in adb_commands
    assert profile.last_serial == (serial if kind == "emulator" else "")


@pytest.mark.parametrize(
    "scenario",
    ["success", "wrong-boot", "restart", "offline", "unauthorized", "refused"],
)
def test_nox_empty_owned_inventory_registers_only_vm_config_endpoint(
    scenario, monkeypatch, tmp_path
):
    from arknights_mower.tests.device_nox_session_tests import OTHER_BOOT, NoxTransport

    fixture = NoxTransport(tmp_path)
    fixture.states = {}
    if scenario == "wrong-boot":
        fixture.manager_boot = OTHER_BOOT
    if scenario == "restart":
        fixture.after_shell = lambda: setattr(
            fixture, "listing", fixture.listing.replace(b"1200", b"1201")
        )
    calls = []

    def runner(argv, **options):
        calls.append((argv, options))
        if argv[0] == str(fixture.manager):
            if argv[1] == "list":
                assert "env" not in options
            else:
                assert fixture.states.get("127.0.0.1:62125") == "device"
                assert options["env"]["ADB_SERVER_SOCKET"] == "tcp:127.0.0.1:52137"
            return fixture.run(argv, **options)
        assert argv[1:5] == ["-H", "127.0.0.1", "-P", "52137"]
        raw = [argv[0], *argv[5:]]
        if raw[1] == "connect":
            assert raw[2] == "127.0.0.1:62125"
            if scenario == "refused":
                raise subprocess.CalledProcessError(1, argv, stderr=b"refused")
            fixture.states[raw[2]] = (
                scenario if scenario in {"offline", "unauthorized"} else "device"
            )
            fixture.states["127.0.0.1:62001"] = "device"
            return subprocess.CompletedProcess(argv, 0, b"connected", b"")
        return fixture.run(raw, **options)

    profile = fixture.configuration.device
    original = profile.model_dump()
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    reader = nox_endpoint.NoxBindingReader(run=runner, probe=lambda timeout: None)
    with server.adb_server_scope(owner):
        if scenario == "success":
            assert (
                reader.inspect(profile, fixture.manager, 5).serial == "127.0.0.1:62125"
            )
        else:
            with pytest.raises(endpoint_identity.InstanceBindingError) as error:
                reader.inspect(profile, fixture.manager, 5)
            codes = {
                "wrong-boot": "endpoint_unresolved",
                "restart": "binding_changed",
                "offline": "device_offline",
                "unauthorized": "device_unauthorized",
                "refused": "endpoint_unresolved",
            }
            assert error.value.code == codes[scenario]
    assert profile.model_dump() == original
    adb_commands = [argv[5:] for argv, _ in calls if argv[0] != str(fixture.manager)]
    assert adb_commands[:2] == [["devices", "-l"], ["devices", "-l"]]
    assert ["connect", "127.0.0.1:62125"] in adb_commands
    assert all("127.0.0.1:62001" not in argv for argv in adb_commands)


@pytest.mark.parametrize("path", ["session", "socket", "capture"])
def test_owned_listener_failure_prevents_raw_socket_connection(path, monkeypatch):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137),
        generation=1,
        adb_path=ADB,
        check=Mock(side_effect=SharedADBError("foreign listener")),
    )
    connect = Mock()
    monkeypatch.setattr(socket, "create_connection", connect)
    with server.adb_server_scope(owner), pytest.raises(SharedADBError, match="foreign"):
        if path == "session":
            session.Session()
        elif path == "socket":
            adb_socket.Socket(owner.address, 5)
        else:
            screenshot._adb_output(SERIAL, "screencap", 64, lambda: 3)
    connect.assert_not_called()
    owner.check.assert_called_once()


@pytest.mark.parametrize("operation", ["send", "recv", "recv_into", "request"])
@pytest.mark.parametrize("changed", ["generation", "listener"])
def test_owned_connections_reject_stale_generation_before_io(
    operation, changed, monkeypatch
):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    connection = Mock()
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    with server.adb_server_scope(owner):
        handle = (
            session.Session()
            if operation == "request"
            else adb_socket.Socket(owner.address, 5)
        )
    owner.check.reset_mock()
    if changed == "generation":
        owner.generation += 1
    else:
        owner.address = ("127.0.0.1", 52138)
    try:
        with pytest.raises(ConnectionError, match="旧连接") as error:
            if operation == "request":
                handle.request("host:version")
            elif operation == "send":
                handle.sendall(b"000chost:version")
            elif operation == "recv":
                handle.recv(4)
            else:
                handle.recv_into(bytearray(4), 4)
        assert bool(getattr(error.value, "input_not_sent", False)) == (
            operation in {"send", "request"}
        )
        connection.sendall.assert_not_called()
        connection.recv.assert_not_called()
        connection.recv_into.assert_not_called()
    finally:
        handle.close()
    connection.close.assert_called_once()


@pytest.mark.parametrize("path", ["session", "socket", "capture"])
def test_captured_owner_is_checked_before_each_new_command(path, monkeypatch):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.recv.side_effect = [b"OKAY", b"0004", b"0029"]
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    with server.adb_server_scope(owner):
        if path == "capture":
            owner.check.side_effect = [None, None, SharedADBError("listener replaced")]
            with pytest.raises(SharedADBError, match="listener replaced"):
                screenshot._adb_output(SERIAL, "screencap", 64, lambda: 3)
            assert connection.sendall.call_count == 1
            connection.__exit__.assert_called_once()
            return
        handle = (
            session.Session()
            if path == "session"
            else adb_socket.Socket(owner.address, 5)
        )
    owner.check.side_effect = SharedADBError("listener replaced")
    try:
        with pytest.raises(SharedADBError, match="listener replaced") as error:
            if path == "session":
                handle.request("host:version")
            else:
                handle.sendall(b"000chost:version")
        assert error.value.input_not_sent is True
        connection.sendall.assert_not_called()
    finally:
        handle.close()


def test_capture_rejects_generation_change_during_decode(monkeypatch):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    monkeypatch.setattr(screenshot, "guard_adb", Mock())
    monkeypatch.setattr(screenshot, "_adb_output", Mock(side_effect=[b"30\n", b"gzip"]))

    def changed_generation(*args, **kwargs):
        owner.generation += 1
        return object()

    monkeypatch.setattr(screenshot, "decode_adb_frame", changed_generation)
    with server.adb_server_scope(owner), pytest.raises(ConnectionError, match="旧连接"):
        screenshot.capture_adb_frame(ADB, SERIAL)


def test_maa_guard_failure_returns_to_device_recovery_without_discarding_tasks(
    monkeypatch,
):
    from arknights_mower.solvers import base_schedule
    from arknights_mower.utils.config.conf import Conf

    configuration = Conf()
    monkeypatch.setattr(config, "conf", configuration)
    solver = object.__new__(base_schedule.BaseSchedulerSolver)
    task = SimpleNamespace(time=datetime.now() + timedelta(hours=1))
    solver.tasks = [task]
    solver.last_execution = {"maa": None}
    solver.MAA = Mock()
    solver.back_to_index = Mock()
    solver.initialize_maa = Mock(side_effect=SharedADBError("guard refused"))
    solver.maa_stop = Mock()
    idle = Mock()
    solver._idle_sleep = idle
    notify = Mock()
    monkeypatch.setattr(base_schedule, "send_message", notify)
    with pytest.raises(SharedADBError, match="guard refused"):
        solver.maa_plan_solver(tasks=["StartUp"], one_time=True)
    assert solver.tasks == [task]
    solver.maa_stop.assert_called_once_with()
    idle.assert_not_called()
    assert all(
        arguments.args[0] != "guard refused" for arguments in notify.call_args_list
    )


@pytest.mark.parametrize("path", ["session", "socket"])
def test_real_socket_send_failure_never_claims_input_not_sent(path, monkeypatch):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    connection = Mock()
    connection.sendall.side_effect = socket.timeout("delivery uncertain")
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    with server.adb_server_scope(owner):
        handle = (
            session.Session()
            if path == "session"
            else adb_socket.Socket(owner.address, 5)
        )
    try:
        with pytest.raises(socket.timeout, match="uncertain") as error:
            if path == "session":
                handle.request("exec:input tap 100 100")
            else:
                handle.sendall(b"input")
        assert not getattr(error.value, "input_not_sent", False)
        assert connection.sendall.call_count == 1
    finally:
        handle.close()


def test_generation_change_after_socket_send_remains_uncertain(monkeypatch):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    connection = Mock()
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    with server.adb_server_scope(owner):
        handle = adb_socket.Socket(owner.address, 5)
    connection.sendall.side_effect = lambda payload: setattr(owner, "generation", 2)
    try:
        with pytest.raises(ConnectionError, match="旧连接") as error:
            handle.sendall(b"input")
        assert not getattr(error.value, "input_not_sent", False)
        connection.sendall.assert_called_once_with(b"input")
    finally:
        handle.close()


def test_session_retry_retains_captured_owner_outside_its_context(monkeypatch):
    owner = SimpleNamespace(
        address=("127.0.0.1", 52137), generation=1, adb_path=ADB, check=Mock()
    )
    first, replacement = Mock(), Mock()
    first.sendall.side_effect = socket.timeout("read-only query")

    def receive_okay(buffer, nbytes):
        buffer[:4] = b"OKAY"
        return 4

    replacement.recv_into.side_effect = receive_okay
    connect = Mock(side_effect=[first, replacement])
    monkeypatch.setattr(socket, "create_connection", connect)
    with server.adb_server_scope(owner):
        handle = session.Session()
    try:
        handle.request("host:version")
        assert handle.sock.server_owner is owner
        assert handle.sock.server_generation == 1
        assert all(
            arguments.args == (owner.address,) for arguments in connect.call_args_list
        )
    finally:
        handle.close()


def test_socket_timeout_setup_failure_is_known_unsent_without_owner_attributes():
    handle = object.__new__(adb_socket.Socket)
    handle.timeout = 5
    handle.sock = Mock()
    handle.sock.settimeout.side_effect = OSError("closed before send")
    with pytest.raises(OSError, match="closed before send") as error:
        handle.sendall(b"input")
    assert error.value.input_not_sent is True
    handle.sock.sendall.assert_not_called()


@pytest.mark.parametrize("failure_type", [ConnectionError, SharedADBError])
def test_client_run_session_failure_marks_input_unsent(failure_type):
    client = object.__new__(core.Client)
    client.session = Mock(side_effect=failure_type("session refused"))
    with pytest.raises(failure_type, match="session refused") as error:
        client.run("input tap 100 100")
    assert error.value.input_not_sent is True
    client.session.assert_called_once_with()


@pytest.mark.parametrize("delivery_unknown", [None, False, True])
def test_input_boundary_prefers_explicit_delivery_verdict_over_unsent_marker(
    delivery_unknown, monkeypatch
):
    target = object.__new__(device.Device)
    target._profile = DeviceProfile()
    target._recovery_scope = nullcontext
    target._input_budget = nullcontext
    target._stop_control = Mock()
    monkeypatch.setattr(config, "conf", SimpleNamespace(device=target.profile))
    error = ConnectionError("guard refused before input")
    error.input_not_sent = True
    if delivery_unknown is not None:
        error.delivery_unknown = delivery_unknown
    operation = Mock(side_effect=error)
    with pytest.raises(TouchFailure) as raised:
        target._input_once(operation, transport="adb")
    assert raised.value.delivery_unknown is (delivery_unknown is True)
    assert raised.value.retryable is (delivery_unknown is not True)
    assert target._stop_control.call_count == int(delivery_unknown is True)
    operation.assert_called_once_with()
