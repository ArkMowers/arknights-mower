"""Shared ADB consumers preserve guards, target selection and delivery verdicts."""

import io
import os
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
SHARED_ADDRESS = ("127.0.0.1", 5037)


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


@pytest.fixture(autouse=True)
def shared_probe(monkeypatch):
    monkeypatch.setattr(server, "probe_adb_server", Mock(return_value=None))


def assert_child_options(options):
    assert "env" not in options
    assert not options.get("shell")


def test_socket_session_retry_uses_fixed_shared_endpoint(monkeypatch):
    first, replacement = Mock(), Mock()
    first.send.side_effect = socket.timeout("read-only query")
    factory = Mock(side_effect=[first, replacement])
    monkeypatch.setattr(session, "Socket", factory)
    connection = session.Session()
    try:
        connection.request("host:version")
        assert connection.server == SHARED_ADDRESS
        assert factory.call_args_list == [
            call(SHARED_ADDRESS, 5),
            call(SHARED_ADDRESS, 10),
        ]
        first.close.assert_called_once_with()
    finally:
        connection.close()
    replacement.close.assert_called_once_with()


def test_raw_capture_socket_uses_shared_server_and_pinned_target(monkeypatch):
    connection = Mock()
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    connection.recv.side_effect = [b"OKAY", b"OKAY", b"frame", b""]
    connect = Mock(return_value=connection)
    monkeypatch.setattr(socket, "create_connection", connect)
    assert screenshot._adb_output(SERIAL, "screencap", 64, lambda: 2) == b"frame"
    connect.assert_called_once_with(SHARED_ADDRESS, timeout=2)
    services = [f"host:transport:{SERIAL}", "exec:screencap"]
    assert connection.sendall.call_args_list == [
        call(f"{len(service):04x}".encode() + service.encode()) for service in services
    ]
    connection.__exit__.assert_called_once()


@pytest.mark.parametrize("clock_start", [0.0, 510.2])
def test_capture_guard_precedes_both_raw_socket_requests(monkeypatch, clock_start):
    # 510.2 + 10 - 510.2 略大于 10，固定时钟复现 Windows 的舍入边界。
    monkeypatch.setattr(screenshot.time, "monotonic", lambda: clock_start)
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
        assert arguments.args == (SHARED_ADDRESS,)
        assert 0 < arguments.kwargs["timeout"] <= screenshot.CAPTURE_TIMEOUT
    decoder.assert_called_once_with(b"gzip frame", header_size=16)


def test_command_output_runs_only_after_guard(monkeypatch):
    order = Mock()
    guard = Mock(return_value=3)
    output = Mock(return_value=subprocess.CompletedProcess([], 0, b"ok", None))
    order.attach_mock(guard, "guard")
    order.attach_mock(output, "output")
    monkeypatch.setattr(utils, "guard_adb", guard)
    monkeypatch.setattr(utils, "run_command", output)
    argv = [ADB, "-s", SERIAL, "shell", "getprop"]
    assert utils.run_cmd(argv, decode=True) == "ok"
    assert argv == [ADB, "-s", SERIAL, "shell", "getprop"]
    assert [entry[0] for entry in order.mock_calls] == ["guard", "output"]
    guard.assert_called_once_with(ADB, timeout=10, run=output)
    assert output.call_args.args == (argv,)
    assert output.call_args.kwargs["timeout"] == 3
    assert_child_options(output.call_args.kwargs)


def test_client_helper_process_starts_after_guard(monkeypatch):
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
    assert spawn.call_args.args == ([ADB, "-s", SERIAL, "shell", "helper", "--input"],)
    assert_child_options(spawn.call_args.kwargs)


def test_maatouch_handshake_process_starts_after_guard(monkeypatch):
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
            [
                ADB,
                "-s",
                SERIAL,
                "shell",
                "CLASSPATH=/data/local/tmp/maatouch",
                "app_process",
                "/",
                "com.shxyke.MaaTouch.App",
            ],
        )
        assert_child_options(spawn.call_args.kwargs)
    finally:
        process.poll.return_value = 0
        helper.close()


def test_droidcast_helper_process_starts_after_guard(monkeypatch):
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
        ],
    )
    assert_child_options(spawn.call_args.kwargs)
    assert helper.http.trust_env is False


def test_forward_claim_survives_command_deadline_failure(monkeypatch):
    helper = droidcast.DroidCastSession(ADB, SERIAL)
    execute = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
    monkeypatch.setattr(droidcast, "run_command", execute)

    def expired_after_success(args, *, stage, runner):
        argv = [ADB, "-s", SERIAL, *args]
        runner(argv, timeout=1)
        raise TimeoutError("after successful forward")

    monkeypatch.setattr(helper, "_adb", expired_after_success)
    with pytest.raises(TimeoutError, match="successful forward"):
        helper._create_forward(52345)
    assert helper.port == 52345
    assert_child_options(execute.call_args.kwargs)


@pytest.mark.parametrize("args", [["forward", "--list"], ["shell", "pidof", "helper"]])
def test_droidcast_commands_keep_shared_guard(args, monkeypatch):
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
def test_droidcast_cleanup_preserves_argv_and_environment(args, monkeypatch):
    execute = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
    monkeypatch.setattr(droidcast, "run_command", execute)
    helper = droidcast.DroidCastSession(ADB, SERIAL)
    assert helper._adb(args, stage="cleanup", cleanup=True) == b""
    selector = [] if args == ["forward", "--list"] else ["-s", SERIAL]
    assert execute.call_args.args == ([ADB, *selector, *args],)
    assert_child_options(execute.call_args.kwargs)


@pytest.mark.parametrize("adb_capture", [False, True], ids=["external", "adb"])
def test_custom_capture_guards_only_adb_commands(adb_capture, monkeypatch):
    command = "adb exec-out screencap -p" if adb_capture else "capture --png"
    configuration = SimpleNamespace(custom_screenshot=SimpleNamespace(command=command))
    monkeypatch.setattr(config, "conf", configuration)
    target = object.__new__(device.Device)
    target._profile = DeviceProfile(screenshot_backend="custom")
    target.client = SimpleNamespace(adb_bin=ADB)
    target.device_id = SERIAL
    frame = object()
    monkeypatch.setattr(device, "bytes2img", Mock(return_value=frame))
    order, guard, output = (
        Mock(),
        Mock(return_value=3),
        Mock(return_value=subprocess.CompletedProcess([], 0, b"png", None)),
    )
    order.attach_mock(guard, "guard")
    order.attach_mock(output, "output")
    monkeypatch.setattr(device, "guard_adb", guard)
    monkeypatch.setattr(device, "run_command", output)
    assert target.capture_frame() is frame
    if adb_capture:
        assert [entry[0] for entry in order.mock_calls] == ["guard", "output"]
        expected = [ADB, "-s", SERIAL, "exec-out", "screencap", "-p"]
        assert output.call_args.kwargs["timeout"] == 3
        assert_child_options(output.call_args.kwargs)
    else:
        guard.assert_not_called()
        expected = ["capture", "--png"]
        assert "env" not in output.call_args.kwargs
    assert output.call_args.args == (expected,)


@pytest.mark.parametrize(
    "consumer", ["check_output", "client", "maatouch", "custom", "raw", "droidcast"]
)
def test_guard_failure_prevents_any_process(consumer, monkeypatch):
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
def test_non_adb_vendor_commands_keep_default_environment(command, monkeypatch):
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
    monkeypatch, tmp_path
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
            assert_child_options(options)
        if argv[0] == ADB:
            assert argv[1:3] in (["devices", "-l"], ["-s", SERIAL])


@pytest.mark.parametrize("platform", ["nt", "posix"])
@pytest.mark.parametrize("selected_adb", [False, True], ids=["fallback", "selected"])
@pytest.mark.parametrize(
    "failure",
    [
        "none",
        "guard",
        "adblite",
        "missing-adblite",
        "kill",
        "missing-kill",
        "missing-both",
    ],
)
def test_maa_connect_preserves_shared_compatibility(
    platform, selected_adb, failure, monkeypatch, tmp_path
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
    guard = Mock(wraps=server.guard_adb)
    if failure == "guard":
        guard.side_effect = SharedADBError("guard refused")
    elif failure in {"adblite", "kill"}:
        rejected_option = 4 if failure == "adblite" else 5
        assistant.set_instance_option.side_effect = lambda option, value: (
            option != rejected_option
        )
    elif failure.startswith("missing-"):
        if failure in {"missing-adblite", "missing-both"}:
            delattr(asst_utils.InstanceOptionType, "adblite_enabled")
        if failure in {"missing-kill", "missing-both"}:
            delattr(asst_utils.InstanceOptionType, "kill_on_adb_exit")
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
        if failure == "guard":
            with pytest.raises(SharedADBError):
                solver.initialize_maa()
            assistant.connect.assert_not_called()
            guard.assert_called_once_with(adb_path, timeout=10)
            return
        solver.initialize_maa()
        expected_options = [call("touch", "maatouch")]
        if failure not in {"missing-adblite", "missing-both"}:
            expected_options.append(call(4, "0"))
        if failure not in {"missing-kill", "missing-both"}:
            expected_options.append(call(5, "0"))
        assert assistant.set_instance_option.call_args_list == expected_options
        guard.assert_called_once_with(adb_path, timeout=10)
        assert [entry[0] for entry in order.mock_calls] == ["guard", "connect"]
        assistant.connect.assert_called_once_with(adb_path, SERIAL, "General")
        assert configuration.maa_adb_path == "fallback-adb"
        assert solver.device.client.adb_bin == (adb_path if selected_adb else None)
    finally:
        if hasattr(solver, "MAA"):
            solver.MAA.stop()


@pytest.mark.parametrize(
    "response,accepted",
    [
        ("Connected to emulator on ports 5558,5559", True),
        ("Connected to emulator on ports 5554,5555", False),
        ("Emulator already registered on port 5555", False),
        ("connected to 127.0.0.1:5559", False),
    ],
)
@pytest.mark.parametrize("clock_start", [0.0, 510.2])
def test_selected_emulator_alias_recovery_connects_only_pinned_ports(
    response, accepted, clock_start
):
    runner = Mock(
        return_value=subprocess.CompletedProcess([], 0, response.encode(), b"")
    )
    adb = ProductionSessionADB(
        run=runner, probe=lambda timeout: None, monotonic=lambda: clock_start
    )
    assert adb.recover(ADB, "emulator-5558", 5) is accepted
    runner.assert_called_once()
    assert runner.call_args.args == ([ADB, "connect", "emu:5558,5559"],)
    assert_child_options(runner.call_args.kwargs)
    assert 0 < runner.call_args.kwargs["timeout"] <= 5


@pytest.mark.parametrize(
    "reconnect_response,accepted",
    [
        ("reconnecting emulator-5558 [offline]", True),
        ("reconnecting emulator-5554 [offline]", False),
        ("reconnecting emulator-5558 failed", False),
    ],
)
def test_registered_offline_emulator_alias_requires_targeted_reconnect(
    reconnect_response, accepted
):
    state = ["offline"]

    def run(argv, **kwargs):
        if argv == [ADB, "connect", "emu:5558,5559"]:
            output = "Emulator already registered on port 5559"
        elif argv == [ADB, "-s", "emulator-5558", "reconnect"]:
            output = reconnect_response
            if accepted:
                state[0] = "device"
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    runner = Mock(side_effect=run)
    adb = ProductionSessionADB(run=runner, probe=lambda timeout: None)
    assert adb.recover(ADB, "emulator-5558", 5) is accepted
    assert state[0] == ("device" if accepted else "offline")
    assert [entry.args[0] for entry in runner.call_args_list] == [
        [ADB, "connect", "emu:5558,5559"],
        [ADB, "-s", "emulator-5558", "reconnect"],
    ]


def test_registered_emulator_reconnect_shares_the_connect_deadline():
    now = [0]

    def run(argv, **kwargs):
        now[0] = 5
        return subprocess.CompletedProcess(
            argv, 0, b"Emulator already registered on port 5559", b""
        )

    runner = Mock(side_effect=run)
    with pytest.raises(SharedADBError):
        ProductionSessionADB(
            run=runner, probe=lambda timeout: None, monotonic=lambda: now[0]
        ).recover(ADB, "emulator-5558", 5)
    assert runner.call_count == 1


def test_registered_emulator_reconnect_uses_only_remaining_time():
    now = [0]

    def run(argv, **kwargs):
        if argv[1] == "connect":
            now[0] = 2
            output = "Emulator already registered on port 5559"
        else:
            output = "reconnecting emulator-5558 [offline]"
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    runner = Mock(side_effect=run)
    assert ProductionSessionADB(
        run=runner, probe=lambda timeout: None, monotonic=lambda: now[0]
    ).recover(ADB, "emulator-5558", 5)
    assert [entry.kwargs["timeout"] for entry in runner.call_args_list] == [5, 3]


def test_registered_emulator_cancellation_never_sends_targeted_reconnect():
    from arknights_mower.tests.device_session_tests import Clock
    from arknights_mower.utils.csleep import MowerExit
    from arknights_mower.utils.device.session import DeviceSession

    def run(argv, **kwargs):
        bound.begin_shutdown()
        return subprocess.CompletedProcess(
            argv, 0, b"Emulator already registered on port 5559", b""
        )

    runner = Mock(side_effect=run)
    adb = ProductionSessionADB(run=runner, probe=lambda timeout: None)
    bound = DeviceSession(adb, Mock(), clock=Clock())
    deadline = bound.begin_budget()
    with pytest.raises(MowerExit):
        bound._action(
            lambda timeout: adb.recover(ADB, "emulator-5558", timeout), deadline
        )
    runner.assert_called_once()
    assert runner.call_args.args[0] == [ADB, "connect", "emu:5558,5559"]


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
    connection = Mock()
    connection.sendall.side_effect = socket.timeout("delivery uncertain")
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    handle = (
        session.Session() if path == "session" else adb_socket.Socket(SHARED_ADDRESS, 5)
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


def test_session_retry_reopens_only_the_shared_socket(monkeypatch):
    first, replacement = Mock(), Mock()
    first.sendall.side_effect = socket.timeout("read-only query")

    def receive_okay(buffer, nbytes):
        buffer[:4] = b"OKAY"
        return 4

    replacement.recv_into.side_effect = receive_okay
    connect = Mock(side_effect=[first, replacement])
    monkeypatch.setattr(socket, "create_connection", connect)
    handle = session.Session()
    try:
        handle.request("host:version")
        assert connect.call_args_list == [
            call(SHARED_ADDRESS, timeout=5),
            call(SHARED_ADDRESS, timeout=10),
        ]
        first.close.assert_called_once_with()
    finally:
        handle.close()
    replacement.close.assert_called_once_with()


def test_capture_decode_remains_within_its_deadline(monkeypatch):
    now = [0]
    monkeypatch.setattr(screenshot.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(screenshot, "guard_adb", Mock())
    monkeypatch.setattr(screenshot, "_adb_output", Mock(side_effect=[b"30\n", b"gzip"]))

    def expired_decode(*args, **kwargs):
        now[0] = screenshot.CAPTURE_TIMEOUT + 1
        return object()

    monkeypatch.setattr(screenshot, "decode_adb_frame", expired_decode)
    with pytest.raises(TimeoutError):
        screenshot.capture_adb_frame(ADB, SERIAL)


def test_socket_deadline_failure_after_send_never_claims_input_unsent(monkeypatch):
    connection = Mock()
    monkeypatch.setattr(socket, "create_connection", Mock(return_value=connection))
    handle = adb_socket.Socket(SHARED_ADDRESS, 5)
    monkeypatch.setattr(
        adb_socket, "io_timeout", Mock(side_effect=[5, TimeoutError("after send")])
    )
    try:
        with pytest.raises(TimeoutError, match="after send") as error:
            handle.sendall(b"input")
        assert not getattr(error.value, "input_not_sent", False)
        connection.sendall.assert_called_once_with(b"input")
    finally:
        handle.close()


@pytest.mark.parametrize(
    "serial,endpoint",
    [
        ("emulator-1024", "emu:1024,1025"),
        ("emulator-5558", "emu:5558,5559"),
        ("emulator-65534", "emu:65534,65535"),
        ("emulator-5559", None),
        ("emulator-1022", None),
        ("emulator-65536", None),
        ("emulator-5558 other", None),
        ("127.0.0.1:5559", None),
        ("USB_123", None),
        ("", None),
    ],
)
def test_emulator_connect_target_accepts_only_valid_pinned_console_ports(
    serial, endpoint
):
    assert endpoint_identity.emulator_connect_target(serial) == endpoint


def test_socket_timeout_setup_failure_is_known_unsent():
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
