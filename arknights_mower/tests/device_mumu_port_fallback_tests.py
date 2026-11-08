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
from arknights_mower.tests.device_session_tests import ADB, Clock, Simulator
from arknights_mower.utils import config
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.mumu_discovery import MuMuDiscoveryIO
from arknights_mower.utils.device.mumu_info import MuMuEndpointUnavailable
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.preflight_io import ProductionPreflightIO
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.session import (
    DeviceSession,
    RecoveryPolicy,
    SessionFailure,
)
from arknights_mower.utils.device.session_io import ProductionSimulator


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
    assert instances == []
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
        subprocess.TimeoutExpired("MuMuManager", 1),
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
    assert instances == []
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
