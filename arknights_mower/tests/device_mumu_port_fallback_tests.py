"""Offline checks for the MuMu manager's per-instance ADB address query."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_preflight_io_tests import configure_mumu_capture
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.endpoint_identity import (
    InstanceBindingError,
    ManagerQueryTimeout,
)
from arknights_mower.utils.device.mumu_discovery import MuMuDiscoveryIO
from arknights_mower.utils.device.mumu_info import (
    MuMuEndpointUnavailable,
    mumu_endpoint_with_fallback,
)
from arknights_mower.utils.device.preflight import (
    PreflightError,
    PreflightResult,
    PreflightService,
)
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO
from arknights_mower.utils.device.recovery import (
    DeviceRecoveryError,
    UIUnresponsiveError,
)
from arknights_mower.utils.device.session import (
    DeviceSession,
    ReadinessResult,
    RecoveryPolicy,
    SessionFailure,
)
from arknights_mower.utils.device.session_io import (
    ProductionSessionADB,
    ProductionSimulator,
)


def entry(**changes):
    return {
        "index": "0",
        "name": "主号",
        "is_process_started": True,
        "is_android_started": True,
        **changes,
    }


def vendor(initial, *, address=b"127.0.0.1:16384\r\n", fresh=None):
    calls = []
    info_count = 0

    def run(argv, **kwargs):
        nonlocal info_count
        calls.append((argv, kwargs["timeout"]))
        if argv[1] == "info":
            info_count += 1
            data = initial if info_count == 1 or fresh is None else fresh
            return subprocess.CompletedProcess(argv, 0, json.dumps(data).encode(), b"")
        assert argv[1:] == ["adb", "-v", "0"]
        if isinstance(address, Exception):
            raise address
        return subprocess.CompletedProcess(argv, 0, address, b"")

    return run, calls


def profile(manager):
    return DeviceProfile(
        preset_id="windows.mumu12",
        manager_path=str(manager),
        instance_id="0",
        instance_name="主号",
        last_serial="127.0.0.1:9999",
    )


@pytest.mark.parametrize("missing_port", [{}, {"adb_port": 0}, {"adb_port": ""}])
def test_discovery_and_session_query_the_selected_instance(missing_port):
    information = {"0": entry(**missing_port)}
    run, calls = vendor(information)
    discovery = MuMuDiscoveryIO(run=run, platform="windows")
    instances, errors = discovery._instances(Path("MuMuManager.exe"), 3)
    assert not errors
    assert instances[0]["serial"] == "127.0.0.1:16384"
    assert [call[0][1:] for call in calls] == [
        ["info", "-v", "all"],
        ["adb", "-v", "0"],
        ["info", "-v", "all"],
    ]
    assert all(0 < timeout <= 3 for _, timeout in calls)

    with tempfile.TemporaryDirectory() as folder:
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        run, calls = vendor(information)
        observed = ProductionSimulator(run=run).inspect(profile(manager), 5)
        assert (observed.state, observed.serial) == ("running", "127.0.0.1:16384")
        assert [call[0][1:] for call in calls] == [
            ["info", "-v", "0"],
            ["adb", "-v", "0"],
            ["info", "-v", "all"],
        ]
        assert all(0 < timeout <= 5 for _, timeout in calls)


def test_valid_info_port_does_not_need_the_fallback():
    run, calls = vendor({"0": entry(adb_port=16448)})
    instances, errors = MuMuDiscoveryIO(run=run, platform="windows")._instances(
        Path("MuMuManager.exe"), 3
    )
    assert not errors
    assert instances[0]["serial"] == "127.0.0.1:16448"
    assert len(calls) == 1


def test_session_uses_the_fallback_address_instead_of_the_old_saved_serial():
    with tempfile.TemporaryDirectory() as folder:
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        run, calls = vendor({"0": entry()})
        adb = ADB()
        adb.rows, adb.boot = [("127.0.0.1:16384", "device")], "1"
        session = DeviceSession(adb, ProductionSimulator(run=run), clock=Clock())
        session.bind(profile(manager))
        ready = session.ensure_ready()
    assert ready.state == "ready"
    assert ready.serial == "127.0.0.1:16384"
    assert adb.actions == []
    assert all(call[0][1] != "api" for call in calls)


@pytest.mark.parametrize("port", [True, 65536, "not-a-port"])
def test_invalid_info_port_reports_configuration_without_fallback(port):
    run, calls = vendor({"0": entry(adb_port=port)})
    instances, errors = MuMuDiscoveryIO(run=run, platform="windows")._instances(
        Path("MuMuManager.exe"), 3
    )
    assert len(instances) == 1
    assert instances[0]["instance_id"] == "0"
    assert instances[0]["serial"] == ""
    assert errors[0].code == "mumu_endpoint_unavailable"
    assert "检查" in errors[0].message
    assert len(calls) == 1


def test_stopped_or_unconfirmed_instance_does_not_query_a_port():
    for data in (entry(is_process_started=False), entry(is_android_started=False)):
        run, calls = vendor({"0": data})
        instances, errors = MuMuDiscoveryIO(run=run, platform="windows")._instances(
            Path("MuMuManager.exe"), 3
        )
        assert not errors
        assert instances[0]["state"] in {"stopped", "starting"}
        assert instances[0]["serial"] == ""
        assert len(calls) == 1
    with tempfile.TemporaryDirectory() as folder:
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        run, calls = vendor({"0": entry(name="已替换")})
        with pytest.raises(InstanceBindingError):
            ProductionSimulator(run=run).inspect(profile(manager), 5)
        assert len(calls) == 1


def test_fallback_commands_share_the_original_discovery_deadline():
    now = [0.0]
    base_run, calls = vendor({"0": entry()})

    def timed_run(argv, **kwargs):
        result = base_run(argv, **kwargs)
        now[0] += 0.75
        return result

    io = MuMuDiscoveryIO(run=timed_run, platform="windows", monotonic=lambda: now[0])
    instances, errors = io._instances(Path("MuMuManager.exe"), 3)
    assert not errors
    assert instances[0]["serial"] == "127.0.0.1:16384"
    assert [timeout for _, timeout in calls] == [3, 2.25, 1.5]


class TimedMuMuManager:
    """Spend a query window on a transient timeout without launching a device."""

    def __init__(self, clock, timeout_phase, failures, timeout_cost=None):
        self.clock = clock
        self.timeout_phase = timeout_phase
        self.failures = failures
        self.timeout_cost = timeout_cost
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((argv[1:], self.clock.now, kwargs["timeout"]))
        phase = (
            "adb" if argv[1] == "adb" else "recheck" if argv[-1] == "all" else "info"
        )
        assert argv[1] in {"info", "adb"}
        if phase == self.timeout_phase and self.failures:
            self.failures -= 1
            elapsed = min(kwargs["timeout"], self.timeout_cost or kwargs["timeout"])
            self.clock.now += elapsed
            raise subprocess.TimeoutExpired(argv, elapsed)
        output = (
            b"127.0.0.1:16384"
            if phase == "adb"
            else json.dumps({"0": entry()}).encode("utf-8")
        )
        return subprocess.CompletedProcess(argv, 0, output, b"")


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
@pytest.mark.parametrize("manual_serial", ["", "127.0.0.1:16384"])
def test_manager_fallback_timeout_retries_same_instance_within_recovery_budget(
    tmp_path, timeout_phase, manual_serial
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock = Clock()
    run = TimedMuMuManager(clock, timeout_phase, failures=1)
    adb = ADB()
    adb.rows, adb.boot = [("127.0.0.1:16384", "device")], "1"
    session = DeviceSession(
        adb,
        ProductionSimulator(run=run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    selected = profile(manager).model_copy(update={"mumu_manual_serial": manual_serial})
    before = selected.model_dump()
    session.bind(selected)
    with patch.object(
        session, "_report_observation", wraps=session._report_observation
    ) as report:
        ready = session.ensure_ready()

    assert report.call_args_list[0].args[0].code == "manager_timeout"
    assert report.call_args_list[0].args[0].serial == ""
    assert ready.serial == "127.0.0.1:16384"
    assert 10 <= clock.now < 60
    assert sum(call == ["info", "-v", "0"] for call, _, _ in run.calls) >= 2
    assert session.actions == 0
    assert adb.actions == []
    assert selected.model_dump() == before


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
@pytest.mark.parametrize("manual_serial", ["", "127.0.0.1:16384"])
def test_repeated_fallback_timeouts_consume_only_the_original_time_budget(
    tmp_path, timeout_phase, manual_serial
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock = Clock()
    run = TimedMuMuManager(clock, timeout_phase, failures=20)
    adb = ADB()
    session = DeviceSession(
        adb,
        ProductionSimulator(run=run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    selected = profile(manager).model_copy(update={"mumu_manual_serial": manual_serial})
    before = selected.model_dump()
    session.bind(selected)
    with pytest.raises(SessionFailure) as failure:
        session.ensure_ready()

    assert failure.value.observation.code == "manager_timeout"
    assert clock.now == 60
    assert sum(call == ["info", "-v", "0"] for call, _, _ in run.calls) > 1
    assert all(0 < timeout <= 10 for _, _, timeout in run.calls)
    assert session.actions == 0
    assert adb.actions == []
    assert selected.model_dump() == before


def test_short_fallback_timeout_does_not_immediately_use_the_manual_address(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    run = TimedMuMuManager(clock, "adb", failures=1, timeout_cost=0.1)
    adb.rows, adb.boot = [("127.0.0.1:16384", "device")], "1"
    session = DeviceSession(
        adb,
        ProductionSimulator(run=run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, poll_interval=1),
    )
    session.bind(
        profile(manager).model_copy(update={"mumu_manual_serial": "127.0.0.1:16384"})
    )
    with patch.object(
        session, "_report_observation", wraps=session._report_observation
    ) as report:
        ready = session.ensure_ready()
    assert report.call_args_list[0].args[0].code == "manager_timeout"
    assert [call for call, _, _ in run.calls][:3] == [
        ["info", "-v", "0"],
        ["adb", "-v", "0"],
        ["info", "-v", "0"],
    ]
    assert ready.serial == "127.0.0.1:16384"
    assert session.actions == 0
    assert adb.actions == []


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
def test_fallback_timeout_after_reconnect_keeps_waiting_without_another_action(
    tmp_path, timeout_phase
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    run = TimedMuMuManager(clock, timeout_phase, failures=0)
    serial = "127.0.0.1:16384"
    adb.rows = [(serial, "offline")]
    adb.boot = "1"

    def reconnect():
        adb.rows = [(serial, "device")]
        run.failures = 1

    adb.on_recover = reconnect
    session = DeviceSession(
        adb,
        ProductionSimulator(run=run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    session.bind(profile(manager))
    with patch.object(
        session, "_report_observation", wraps=session._report_observation
    ) as report:
        ready = session.ensure_ready()

    assert ready.serial == serial
    assert "manager_timeout" in [call.args[0].code for call in report.call_args_list]
    assert 10 <= clock.now < 60
    assert session.actions == 1
    assert adb.actions == [serial]


class RestartingMuMuManager(TimedMuMuManager):
    def __init__(self, clock, failures):
        super().__init__(clock, "adb", failures)
        self.running = True

    def __call__(self, argv, **kwargs):
        if argv[1] == "api":
            self.calls.append((argv[1:], self.clock.now, kwargs["timeout"]))
            self.running = argv[-1] == "launch_player"
            return subprocess.CompletedProcess(argv, 0, b'{"code":0}', b"")
        if argv[1] == "info" and not self.running:
            self.calls.append((argv[1:], self.clock.now, kwargs["timeout"]))
            stopped = {"0": entry(is_process_started=False, is_android_started=False)}
            return subprocess.CompletedProcess(
                argv, 0, json.dumps(stopped).encode(), b""
            )
        return super().__call__(argv, **kwargs)


@pytest.mark.parametrize("failures", [1, 20])
def test_ui_recovery_retries_manager_timeout_before_any_restart_action(
    tmp_path, failures
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    run = RestartingMuMuManager(clock, failures)
    serial = "127.0.0.1:16384"
    adb.rows, adb.boot = [(serial, "device")], "1"
    session = DeviceSession(
        adb,
        ProductionSimulator(run=run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    session.bind(profile(manager), resolved_adb="verified-adb")
    failure = UIUnresponsiveError()
    session.record_ui_failure(failure)
    deadline = session.begin_budget()
    if failures == 1:
        ready = session.restart(failure, deadline=deadline)
        assert ready.serial == serial
        assert [call[-1] for call, _, _ in run.calls if call[0] == "api"] == [
            "shutdown_player",
            "launch_player",
        ]
        assert session.actions == 1
        assert 10 <= clock.now < 60
    else:
        with pytest.raises(SessionFailure) as rejected:
            session.restart(failure, deadline=deadline)
        assert rejected.value.observation.code == "manager_timeout"
        assert clock.now == 60
        assert not any(call[0] == "api" for call, _, _ in run.calls)
        assert not failure.stop_requested
        assert not failure.start_requested
        assert session.actions == 0
    assert adb.actions == []


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
def test_mumu_frame_probe_retries_manager_timeout_without_reconnecting(
    tmp_path, timeout_phase
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    run = TimedMuMuManager(clock, timeout_phase, failures=1)
    simulator.state, simulator.serial = "running", "127.0.0.1:16384"
    adb.rows, adb.boot = [(simulator.serial, "device")], "1"
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    session.bind(
        profile(manager).model_copy(
            update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
        )
    )

    def frame_probe(adb_path, serial, timeout):
        endpoint = mumu_endpoint_with_fallback(
            entry(),
            "0",
            str(manager),
            lambda argv: run(argv, timeout=min(10, timeout)).stdout,
        )
        assert endpoint == serial
        return (1920, 1080)

    with patch.object(
        session, "_report_observation", wraps=session._report_observation
    ) as report:
        ready = session.ensure_ready(frame_probe=frame_probe)

    assert report.call_args_list[0].args[0].code == "manager_timeout"
    assert report.call_args_list[0].args[0].serial == ""
    assert ready.serial == "127.0.0.1:16384"
    assert session.actions == 0
    assert adb.actions == []
    assert simulator.actions == []


def test_production_mumu_frame_query_uses_the_configured_short_window(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    run = TimedMuMuManager(clock, "adb", failures=1)
    serial = "127.0.0.1:16384"
    simulator.state, simulator.serial = "running", serial
    adb.rows, adb.boot = [(serial, "device")], "1"
    selected = profile(manager).model_copy(
        update={
            "manager_query_timeout": 10,
            "screenshot_backend": "mumu_ipc",
            "touch_backend": "mumu_ipc",
        }
    )
    capture_adb = ProductionSessionADB(run=run, monotonic=clock.monotonic)
    capture_adb.bind(selected)
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    session.bind(selected)
    with (
        patch.object(ProductionPreflightIO, "host_platform", return_value="windows"),
        patch(
            "arknights_mower.utils.device.preflight_io.resolve_mumu_paths",
            return_value=("root", str(manager)),
        ),
        patch(
            "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
        ) as context,
    ):
        configure_mumu_capture(context.return_value)
        ready = session.ensure_ready(frame_probe=capture_adb.frame_size)
    assert ready.serial == serial
    assert 10 <= clock.now < 60
    assert sum(call == ["adb", "-v", "0"] for call, _, _ in run.calls) >= 2
    assert all(timeout <= 10 for _, _, timeout in run.calls)
    assert session.actions == 0
    assert adb.actions == []
    assert simulator.actions == []


def test_mumu_custom_capture_keeps_its_existing_command_window(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b"image", b""))
    adapter = ProductionSessionADB(run=run)
    adapter.bind(profile(manager).model_copy(update={"screenshot_backend": "custom"}))
    assert adapter._preflight_io(60, frame=True)._run(["custom-capture"]) == b"image"
    assert run.call_args.kwargs["timeout"] > 10


def test_actual_mumu_frame_timeout_stays_a_frame_failure(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    simulator.state, simulator.serial = "running", "127.0.0.1:16384"
    adb.rows, adb.boot = [(simulator.serial, "device")], "1"
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    session.bind(
        profile(manager).model_copy(
            update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
        )
    )
    frame_probe = Mock(side_effect=[TimeoutError("MuMu IPC 首帧超时"), (1920, 1080)])
    with patch.object(
        session, "_report_observation", wraps=session._report_observation
    ) as report:
        ready = session.ensure_ready(frame_probe=frame_probe)
    assert report.call_args_list[0].args[0].code == "frame_failed"
    assert ready.serial == simulator.serial


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
def test_read_only_mumu_capture_reports_manager_timeout_without_retrying_capture(
    tmp_path, timeout_phase
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock = Clock()
    run = TimedMuMuManager(clock, timeout_phase, failures=20)
    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.targets = [("127.0.0.1:16384", "device")]
    io.installed_packages = ["com.hypergryph.arknights"]

    def capture(adb_path, serial, selected):
        return mumu_endpoint_with_fallback(
            entry(), "0", str(manager), lambda argv: run(argv, timeout=3).stdout
        )

    io.capture_frame = Mock(side_effect=capture)
    selected = profile(manager).model_copy(
        update={
            "manager_path": "",
            "adb_path": "manual-adb",
            "last_serial": "127.0.0.1:16384",
            "screenshot_backend": "mumu_ipc",
            "touch_backend": "mumu_ipc",
        }
    )
    result = PreflightService(io).check(selected)
    assert not result.ok
    assert result.error.code == "manager_timeout"
    assert result.error.action == "retry"
    assert result.serial == ""
    io.capture_frame.assert_called_once()


@pytest.mark.parametrize("operation", ["start", "start_bound", "recover"])
def test_runtime_mumu_preflight_retries_query_timeout_within_existing_budget(
    tmp_path, operation
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    serial = "127.0.0.1:16384"
    simulator.state, simulator.serial = "running", serial
    adb.rows, adb.boot = [(serial, "device")], "1"
    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager))
    io.paths.add("verified-adb")
    io.targets = [(serial, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]
    failing = {"remaining": 0 if operation == "recover" else 1}

    def capture(adb_path, target, selected):
        if failing["remaining"]:
            failing["remaining"] -= 1
            clock.now += 10
            raise ManagerQueryTimeout("MuMu 管理程序查询超时")
        return io.frame

    io.capture_frame = Mock(side_effect=capture)
    selected = profile(manager).model_copy(
        update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
    )
    conf = Conf(device=selected.model_dump())
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=PreflightService(io)
    )
    if operation == "recover":
        assert control.start().ok
        adb.rows = [(serial, "offline")]
        adb.on_recover = lambda: setattr(adb, "rows", [(serial, "device")])
        failing["remaining"] = 1
        result = control.recover()
        assert adb.actions == [serial]
        assert session.actions == 1
    elif operation == "start_bound":
        result = control.start_bound(conf)
        assert adb.actions == []
        assert session.actions == 0
    else:
        result = control.start()
        assert adb.actions == []
        assert session.actions == 0
    assert result.ok, result.error
    assert 10 <= clock.now < 60
    assert simulator.actions == []


@pytest.mark.parametrize("operation", ["start", "start_bound"])
def test_runtime_mumu_preflight_timeout_exhausts_time_without_extra_actions(
    tmp_path, operation
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    serial = "127.0.0.1:16384"
    simulator.state, simulator.serial = "running", serial
    adb.rows, adb.boot = [(serial, "device")], "1"
    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager))
    io.paths.add("verified-adb")
    io.targets = [(serial, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]

    def capture(adb_path, target, selected):
        clock.now += min(10, session.remaining())
        raise ManagerQueryTimeout("MuMu 管理程序查询超时")

    io.capture_frame = Mock(side_effect=capture)
    selected = profile(manager).model_copy(
        update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
    )
    conf = Conf(device=selected.model_dump())
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(timeout=60, attempts=3, local_wait=2, poll_interval=1),
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=PreflightService(io)
    )
    result = (
        control.start_bound(conf) if operation == "start_bound" else control.start()
    )
    assert not result.ok
    assert result.error.code == "manager_timeout"
    assert clock.now == 60
    assert io.capture_frame.call_count > 1
    assert session.actions == 0
    assert adb.actions == []
    assert simulator.actions == []


def test_runtime_preflight_stops_if_timeout_is_followed_by_a_binding_error(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    serial = "127.0.0.1:16384"
    simulator.state, simulator.serial = "running", serial
    adb.rows, adb.boot = [(serial, "device")], "1"
    preflight = Mock()
    preflight.host_platform.return_value = "windows"
    preflight.check.side_effect = [
        PreflightResult(
            False,
            "windows",
            "failed",
            "",
            error=PreflightError("manager_timeout", "超时"),
        ),
        PreflightResult(
            False,
            "windows",
            "failed",
            "",
            error=PreflightError("binding_changed", "实例已变化"),
        ),
    ]
    conf = Conf(device=profile(manager).model_dump())
    session = DeviceSession(
        adb, simulator, clock=clock, policy=RecoveryPolicy(timeout=60)
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=preflight
    )
    result = control.start()
    assert not result.ok
    assert result.error.code == "binding_changed"
    assert preflight.check.call_count == 2
    assert session.actions == 0
    assert adb.actions == []
    assert simulator.actions == []


def test_runtime_preflight_keeps_a_terminal_session_error_after_timeout(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    serial = "127.0.0.1:16384"
    simulator.state, simulator.serial = "running", serial
    adb.rows, adb.boot = [(serial, "device")], "1"
    preflight = Mock()
    preflight.host_platform.return_value = "windows"
    changed = ReadinessResult(
        "offline", "", code="binding_changed", message="实例已变化"
    )
    preflight.check.side_effect = [
        PreflightResult(
            False,
            "windows",
            "failed",
            "",
            error=PreflightError("manager_timeout", "超时"),
        ),
        SessionFailure(changed, "实例已变化"),
    ]
    conf = Conf(device=profile(manager).model_dump())
    session = DeviceSession(
        adb, simulator, clock=clock, policy=RecoveryPolicy(timeout=60)
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=preflight
    )
    result = control.start()
    assert not result.ok
    assert result.error.code == "binding_changed"
    assert preflight.check.call_count == 2
    assert session.actions == 0
    assert adb.actions == []


def test_runtime_preflight_rejects_replaced_mumu_instance_after_timeout(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb, simulator = Clock(), ADB(), Simulator()
    serial = "127.0.0.1:16384"
    simulator.state, simulator.serial = "running", serial
    adb.rows, adb.boot = [(serial, "device")], "1"
    io, capture_io = PreflightIO(), ProductionPreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager))
    io.paths.add("verified-adb")
    io.targets = [(serial, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]
    selected = profile(manager).model_copy(
        update={
            "mumu_created_timestamp": "111",
            "screenshot_backend": "mumu_ipc",
            "touch_backend": "mumu_ipc",
        }
    )
    calls = 0

    def capture(adb_path, target, current):
        nonlocal calls
        calls += 1
        if calls == 1:
            clock.now += 10
            raise ManagerQueryTimeout("MuMu 管理程序查询超时")
        return capture_io._capture_mumu(current, target)

    io.capture_frame = Mock(side_effect=capture)
    conf = Conf(device=selected.model_dump())
    session = DeviceSession(
        adb, simulator, clock=clock, policy=RecoveryPolicy(timeout=60, poll_interval=1)
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=PreflightService(io)
    )
    replacement = json.dumps(
        {"0": entry(adb_port=16384, created_timestamp=222)}
    ).encode()
    with (
        patch(
            "arknights_mower.utils.device.preflight_io.resolve_mumu_paths",
            return_value=("root", str(manager)),
        ),
        patch.object(capture_io, "_run", return_value=replacement),
        patch(
            "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
        ) as context,
    ):
        configure_mumu_capture(context.return_value)
        result = control.start()
    assert not result.ok
    assert result.error.code == "binding_changed"
    assert calls == 2
    assert session.actions == 0
    assert adb.actions == []
    assert simulator.actions == []
    context.return_value.Process.assert_not_called()


def test_runtime_preflight_revalidates_instance_before_retrying_capture(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    serial = "127.0.0.1:16384"
    adb.rows, adb.boot = [(serial, "device")], "1"
    state = {"created": 111}
    manager_calls = []

    def manager_run(argv, **kwargs):
        manager_calls.append(argv[1:])
        assert argv[1] == "info"
        output = json.dumps(
            {"0": entry(adb_port=16384, created_timestamp=state["created"])}
        ).encode()
        return subprocess.CompletedProcess(argv, 0, output, b"")

    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager))
    io.paths.add("verified-adb")
    io.targets = [(serial, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]

    def capture(adb_path, target, selected):
        state["created"] = 222
        clock.now += 10
        raise ManagerQueryTimeout("MuMu 管理程序查询超时")

    io.capture_frame = Mock(side_effect=capture)
    selected = profile(manager).model_copy(
        update={
            "mumu_created_timestamp": "111",
            "screenshot_backend": "mumu_ipc",
            "touch_backend": "mumu_ipc",
        }
    )
    session = DeviceSession(
        adb,
        ProductionSimulator(run=manager_run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, poll_interval=1),
    )
    control = DeviceControl(
        lambda: Conf(device=selected.model_dump()),
        Adapter(),
        session=session,
        preflight=PreflightService(io),
    )
    result = control.start()
    assert not result.ok
    assert result.error.code == "binding_changed"
    io.capture_frame.assert_called_once()
    assert session.actions == 0
    assert adb.actions == []
    assert all(call[0] != "api" for call in manager_calls)


@pytest.mark.parametrize("operation", ["start", "start_bound"])
def test_runtime_preflight_pins_observed_creation_time_without_persisting_it(
    tmp_path, operation
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    serial = "127.0.0.1:16384"
    adb.rows, adb.boot = [(serial, "device")], "1"
    state = {"created": 111}
    manager_calls = []

    def manager_run(argv, **kwargs):
        manager_calls.append(argv[1:])
        assert argv[1] == "info"
        output = json.dumps(
            {"0": entry(adb_port=16384, created_timestamp=state["created"])}
        ).encode()
        return subprocess.CompletedProcess(argv, 0, output, b"")

    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager))
    io.paths.add("verified-adb")
    io.targets = [(serial, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]

    def capture(adb_path, target, selected):
        state["created"] = 222
        clock.now += 10
        raise ManagerQueryTimeout("MuMu 管理程序查询超时")

    io.capture_frame = Mock(side_effect=capture)
    selected = profile(manager).model_copy(
        update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
    )
    conf = Conf(device=selected.model_dump())
    before = conf.model_dump()
    session = DeviceSession(
        adb,
        ProductionSimulator(run=manager_run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, poll_interval=1),
    )
    control = DeviceControl(
        lambda: conf, Adapter(), session=session, preflight=PreflightService(io)
    )
    result = (
        control.start_bound(conf) if operation == "start_bound" else control.start()
    )
    assert not result.ok
    assert result.error.code == "binding_changed"
    assert conf.model_dump() == before
    assert conf.device.mumu_created_timestamp == ""
    io.capture_frame.assert_called_once()
    assert session.actions == 0
    assert adb.actions == []
    assert all(call[0] != "api" for call in manager_calls)


def test_first_mumu_frame_timeout_keeps_the_observed_instance_identity(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    serial = "127.0.0.1:16384"
    adb.rows, adb.boot = [(serial, "device")], "1"
    state = {"created": 111}

    def manager_run(argv, **kwargs):
        assert argv[1] == "info"
        output = json.dumps(
            {"0": entry(adb_port=16384, created_timestamp=state["created"])}
        ).encode()
        return subprocess.CompletedProcess(argv, 0, output, b"")

    selected = profile(manager).model_copy(
        update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
    )
    before = selected.model_dump()
    session = DeviceSession(
        adb,
        ProductionSimulator(run=manager_run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, poll_interval=1),
    )
    session.bind(selected)

    def frame_probe(adb_path, target, timeout):
        assert session.profile.mumu_created_timestamp == "111"
        state["created"] = 222
        clock.now += 10
        raise ManagerQueryTimeout("MuMu 管理程序查询超时")

    with pytest.raises(SessionFailure) as failure:
        session.ensure_ready(frame_probe=frame_probe)
    assert failure.value.observation.code == "binding_changed"
    assert session.actions == 0
    assert adb.actions == []
    assert selected.model_dump() == before


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
def test_runtime_preflight_retries_a_timeout_during_binding_revalidation(
    tmp_path, timeout_phase
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock, adb = Clock(), ADB()
    serial = "127.0.0.1:16384"
    adb.rows, adb.boot = [(serial, "device")], "1"
    run = TimedMuMuManager(clock, timeout_phase, failures=0)
    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager))
    io.paths.add("verified-adb")
    io.targets = [(serial, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]
    captures = 0

    def capture(adb_path, target, selected):
        nonlocal captures
        captures += 1
        if captures == 1:
            run.failures = 1
            clock.now += 10
            raise ManagerQueryTimeout("MuMu 管理程序查询超时")
        return io.frame

    io.capture_frame = Mock(side_effect=capture)
    selected = profile(manager).model_copy(
        update={"screenshot_backend": "mumu_ipc", "touch_backend": "mumu_ipc"}
    )
    session = DeviceSession(
        adb,
        ProductionSimulator(run=run, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(timeout=60, poll_interval=1),
    )
    control = DeviceControl(
        lambda: Conf(device=selected.model_dump()),
        Adapter(),
        session=session,
        preflight=PreflightService(io),
    )
    result = control.start()
    assert result.ok, result.error
    assert captures == 2
    assert 20 <= clock.now < 60
    assert sum(call == ["info", "-v", "0"] for call, _, _ in run.calls) >= 3
    assert session.actions == 0
    assert adb.actions == []


def test_mumu_initial_capture_manager_timeout_remains_a_query_timeout():
    io = ProductionPreflightIO()
    selected = profile("manager")
    with (
        patch(
            "arknights_mower.utils.device.preflight_io.resolve_mumu_paths",
            return_value=("root", "manager"),
        ),
        patch.object(
            io,
            "_run",
            side_effect=subprocess.TimeoutExpired(["manager", "info"], 3),
        ),
        pytest.raises(TimeoutError),
    ):
        io._capture_mumu(selected, "127.0.0.1:16384")


@pytest.mark.parametrize("timeout_phase", ["adb", "recheck"])
def test_one_shot_binding_check_reports_a_retryable_manager_timeout(
    tmp_path, timeout_phase
):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    clock = Clock()
    run = TimedMuMuManager(clock, timeout_phase, failures=1)
    io = PreflightIO()
    io.host = "windows"
    service = DiscoveryService(
        MuMuDiscoveryIO(run=run, platform="windows"),
        ProductionSimulator(run=run, monotonic=clock.monotonic),
    )
    result = service.check_binding(profile(manager), PreflightService(io))
    assert not result.ok
    assert result.error.code == "manager_timeout"
    assert result.error.action == "retry"
    assert result.serial == ""


def test_rejected_adb_query_can_still_use_an_explicit_manual_address(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    rejected = subprocess.CalledProcessError(1, [str(manager), "adb", "-v", "0"])
    run, calls = vendor({"0": entry()}, address=rejected)
    selected = profile(manager).model_copy(
        update={"mumu_manual_serial": "127.0.0.1:16384"}
    )
    observed = ProductionSimulator(run=run).inspect(selected, 5)
    assert observed.serial == "127.0.0.1:16384"
    assert [call[0][1] for call in calls] == ["info", "adb", "info"]


@pytest.mark.parametrize("cancelled", [MowerExit(), DeviceRecoveryError("cancelled")])
def test_cancellation_is_not_converted_to_a_port_failure(cancelled):
    run, _ = vendor({"0": entry()}, address=cancelled)
    with pytest.raises(type(cancelled)):
        MuMuDiscoveryIO(run=run, platform="windows")._instances(
            Path("MuMuManager.exe"), 3
        )


@pytest.mark.parametrize(
    "address",
    [
        b"",
        b"127.0.0.1:0",
        b"127.0.0.1:16384\n127.0.0.1:16448",
        b"unknown",
    ],
)
def test_unavailable_address_has_port_guidance_without_reusing_saved_address(address):
    with tempfile.TemporaryDirectory() as folder:
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        run, calls = vendor({"0": entry()}, address=address)
        with pytest.raises(InstanceBindingError) as rejected:
            ProductionSimulator(run=run).inspect(profile(manager), 5)
        assert rejected.value.code == "mumu_endpoint_unavailable"
        assert "端口" in str(rejected.value)
        assert "检查" in str(rejected.value)
        assert all(call[0][1] != "api" for call in calls)

    run, _ = vendor({"0": entry()}, address=address)
    instances, errors = MuMuDiscoveryIO(run=run, platform="windows")._instances(
        Path("MuMuManager.exe"), 3
    )
    assert len(instances) == 1
    assert instances[0]["instance_id"] == "0"
    assert instances[0]["serial"] == ""
    assert errors[0].code == "mumu_endpoint_unavailable"


@pytest.mark.parametrize(
    ("fresh", "code"),
    [
        ({"0": entry(name="其他实例")}, "binding_changed"),
        ({"0": entry(is_process_started=False)}, "binding_changed"),
        ({"0": entry(adb_port=16448)}, "mumu_endpoint_unavailable"),
        ({"0": entry(adb_port=65536)}, "mumu_endpoint_unavailable"),
        (
            {"0": entry(), "1": entry(index="1", name="其他实例", adb_port=16384)},
            "mumu_endpoint_unavailable",
        ),
    ],
)
def test_recheck_rejects_changed_identity_or_conflicting_endpoint(fresh, code):
    with tempfile.TemporaryDirectory() as folder:
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        run, calls = vendor({"0": entry()}, fresh=fresh)
        with pytest.raises(InstanceBindingError) as rejected:
            ProductionSimulator(run=run).inspect(profile(manager), 5)
        assert rejected.value.code == code
        if code == "mumu_endpoint_unavailable":
            assert "端口" in str(rejected.value)
            assert "检查" in str(rejected.value)
        assert all(call[0][1] != "api" for call in calls)


def test_native_capture_accepts_only_the_verified_fallback_address():
    run, calls = vendor({"0": entry()})
    with (
        patch(
            "arknights_mower.utils.device.preflight_io.resolve_mumu_paths",
            return_value=("root", "manager"),
        ),
        patch(
            "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
        ) as context,
        patch.object(
            ProductionPreflightIO,
            "_run",
            side_effect=lambda argv: run(argv, timeout=5).stdout,
        ),
    ):
        configure_mumu_capture(context.return_value)
        result = ProductionPreflightIO()._capture_mumu(
            profile("manager"), "127.0.0.1:16384"
        )
    assert result.shape == (1080, 1920, 3)
    assert [call[0][1] for call in calls] == ["info", "adb", "info"]


def test_native_capture_does_not_use_an_outdated_serial():
    run, _ = vendor({"0": entry()})
    with (
        patch(
            "arknights_mower.utils.device.preflight_io.resolve_mumu_paths",
            return_value=("root", "manager"),
        ),
        patch(
            "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
        ) as context,
        patch.object(
            ProductionPreflightIO,
            "_run",
            side_effect=lambda argv: run(argv, timeout=5).stdout,
        ),
        pytest.raises(MuMuEndpointUnavailable, match="不一致"),
    ):
        ProductionPreflightIO()._capture_mumu(profile("manager"), "127.0.0.1:9999")
    context.assert_not_called()


def test_native_capture_reports_changed_instance_identity():
    run, _ = vendor({"0": entry(name="已替换", adb_port=16384)})
    with (
        patch(
            "arknights_mower.utils.device.preflight_io.resolve_mumu_paths",
            return_value=("root", "manager"),
        ),
        patch(
            "arknights_mower.utils.device.preflight_io.multiprocessing.get_context"
        ) as context,
        patch.object(
            ProductionPreflightIO,
            "_run",
            side_effect=lambda argv: run(argv, timeout=5).stdout,
        ),
        pytest.raises(InstanceBindingError) as failure,
    ):
        ProductionPreflightIO()._capture_mumu(profile("manager"), "127.0.0.1:16384")
    assert failure.value.code == "binding_changed"
    context.assert_not_called()


def test_port_failure_during_frame_probe_does_not_trigger_reconnect_or_restart():
    adb, simulator = ADB(), Simulator()
    serial = "127.0.0.1:16384"
    adb.rows, adb.boot = [(serial, "device")], "1"
    adb.frame_size = Mock(side_effect=MuMuEndpointUnavailable("0"))
    simulator.state, simulator.serial = "running", serial
    session = DeviceSession(
        adb,
        simulator,
        clock=Clock(),
        policy=RecoveryPolicy(attempts=2, timeout=1, local_wait=0, poll_interval=0.1),
    )
    session.bind(profile("manager"))
    with pytest.raises(SessionFailure) as failure:
        session.ensure_ready()
    assert failure.value.observation.code == "mumu_endpoint_unavailable"
    assert failure.value.observation.serial == ""
    assert adb.actions == []
    assert simulator.actions == []


def test_port_failure_during_read_only_capture_retains_port_guidance():
    io = PreflightIO()
    io.boot = "1"
    io.capture_frame = Mock(side_effect=MuMuEndpointUnavailable("0"))
    result = PreflightService(io).check(
        DeviceProfile(last_serial="USB-123", adb_path="manual-adb")
    )
    assert not result.ok
    assert result.error.code == "mumu_endpoint_unavailable"
    assert "检查" in result.error.message
    io.capture_frame.assert_called_once()


class MuMuFallbackRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        folder = self.enterContext(tempfile.TemporaryDirectory())
        manager = Path(folder) / "shell" / "MuMuManager.exe"
        manager.parent.mkdir()
        manager.touch()
        chosen = profile(manager)
        chosen.installation_path = folder
        chosen.adb_path = "manual-adb"
        config.conf.device = chosen
        config.save_conf()
        run, self.calls = vendor({"0": entry()}, address=b"")
        io = PreflightIO()
        io.host = "windows"
        discovery = MuMuDiscoveryIO(
            run=run,
            registry_paths=lambda: [],
            fixed_paths=lambda: [],
            process_paths=lambda: [],
            platform="windows",
        )
        self.control = DeviceControl(
            lambda: config.conf,
            Mock(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(discovery, ProductionSimulator(run=run)),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def test_auth_and_explicit_port_failure_through_settings_routes(self):
        before = self.path.read_bytes()
        for route in ("/device/discover", "/device/preflight"):
            for headers in ({}, {"token": "wrong"}):
                self.assertEqual(
                    self.client.post(route, headers=headers, json={}).status_code, 403
                )
            self.assertEqual(self.calls, [])
            result = self.client.post(route, headers=self.headers, json={})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json["error"]["code"], "mumu_endpoint_unavailable")
            self.assertIn("检查", result.json["error"]["message"])
            self.assertEqual(self.path.read_bytes(), before)
            self.calls.clear()

    def test_preflight_timeout_is_retryable_and_requires_the_instance_token(self):
        clock = Clock()
        run = TimedMuMuManager(clock, "adb", failures=1)
        self.control._discovery._simulator = ProductionSimulator(
            run=run, monotonic=clock.monotonic
        )
        before = self.path.read_bytes()
        for headers in ({}, {"token": "wrong"}):
            self.assertEqual(
                self.client.post(
                    "/device/preflight", headers=headers, json={}
                ).status_code,
                403,
            )
        self.assertEqual(run.calls, [])
        response = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["error"]["code"], "manager_timeout")
        self.assertEqual(response.json["error"]["action"], "retry")
        self.assertEqual(self.path.read_bytes(), before)
