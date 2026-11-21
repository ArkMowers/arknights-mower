"""Offline MuMu lifecycle checks with an explicitly entered ADB address."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Clock
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.endpoint_identity import InstanceBindingError
from arknights_mower.utils.device.mumu_discovery import MuMuDiscoveryIO
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import (
    DeviceSession,
    RecoveryPolicy,
    SessionFailure,
)
from arknights_mower.utils.device.session_io import ProductionSimulator

ADDRESS = "127.0.0.1:16384"


class MuMuManager:
    def __init__(
        self,
        *,
        running=True,
        name="主号",
        query=b"",
        other=None,
        port=0,
        created=None,
        android=None,
    ):
        self.running = running
        self.name = name
        self.query = query
        self.other = other
        self.port = port
        self.created = created
        self.android = android
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(argv[1:])
        if argv[1] == "api":
            assert argv[2:4] == ["-v", "0"]
            self.running = argv[-1] == "launch_player"
            output = b'{"code":0}'
        elif argv[1] == "adb":
            assert argv[2:] == ["-v", "0"]
            output = self.query
        else:
            assert argv[1:3] == ["info", "-v"]
            entry = {
                "index": "0",
                "name": self.name,
                "is_process_started": self.running,
                "is_android_started": self.running
                if self.android is None
                else self.android,
                "adb_port": self.port,
            }
            if self.created is not None:
                entry["created_timestamp"] = self.created
            data = {"0": entry}
            if self.other and argv[-1] == "all":
                data["1"] = {
                    "index": "1",
                    "name": "其他实例",
                    "is_process_started": True,
                    "is_android_started": True,
                    "adb_port": self.other,
                }
            output = json.dumps(data).encode()
        return subprocess.CompletedProcess(argv, 0, output, b"")


@pytest.fixture
def manager_file(tmp_path):
    manager = tmp_path / "MuMuManager.exe"
    manager.touch()
    return manager


def bound(manager, *, manual=ADDRESS, **kwargs):
    return DeviceProfile(
        preset_id="windows.mumu12",
        manager_path=str(manager),
        instance_id="0",
        instance_name="主号",
        last_serial="127.0.0.1:9999",
        mumu_manual_serial=manual,
        **kwargs,
    )


def test_manual_address_supports_automatic_start_and_stop(manager_file):
    vendor, clock, adb = MuMuManager(running=False), Clock(), ADB()
    adb.rows, adb.boot = [(ADDRESS, "device")], "1"
    simulator = ProductionSimulator(run=vendor, monotonic=clock.monotonic)
    session = DeviceSession(
        adb,
        simulator,
        clock=clock,
        policy=RecoveryPolicy(attempts=3, timeout=10, local_wait=0, poll_interval=0.1),
    )
    profile = bound(manager_file)
    session.bind(profile)
    ready = session.ensure_ready()
    assert (ready.state, ready.serial) == ("ready", ADDRESS)
    assert [call for call in vendor.calls if call[0] == "api"] == [
        ["api", "-v", "0", "launch_player"]
    ]
    assert simulator.stop(profile, 3)
    assert vendor.calls[-1] == ["api", "-v", "0", "shutdown_player"]
    assert not vendor.running


def test_auto_start_connects_the_explicit_manual_address(manager_file):
    vendor, clock, adb = MuMuManager(running=False), Clock(), ADB()
    adb.boot = "1"
    adb.on_recover = lambda: setattr(adb, "rows", [(ADDRESS, "device")])
    session = DeviceSession(
        adb,
        ProductionSimulator(run=vendor, monotonic=clock.monotonic),
        clock=clock,
        policy=RecoveryPolicy(attempts=3, timeout=10, local_wait=0, poll_interval=0.1),
    )
    session.bind(bound(manager_file))
    ready = session.ensure_ready()
    assert ready.serial == ADDRESS
    assert adb.actions == [ADDRESS]
    assert [call for call in vendor.calls if call[0] == "api"] == [
        ["api", "-v", "0", "launch_player"]
    ]


def test_stop_checks_instance_identity_without_requiring_an_adb_port(manager_file):
    vendor = MuMuManager()
    assert ProductionSimulator(run=vendor).stop(bound(manager_file, manual=""), 3)
    assert vendor.calls == [
        ["info", "-v", "0"],
        ["api", "-v", "0", "shutdown_player"],
    ]


def test_invalid_manual_address_does_not_start_a_stopped_instance(manager_file):
    vendor, clock, adb = MuMuManager(running=False), Clock(), ADB()
    session = DeviceSession(
        adb,
        ProductionSimulator(run=vendor, monotonic=clock.monotonic),
        clock=clock,
    )
    session.bind(bound(manager_file, manual="invalid-address"))
    with pytest.raises(SessionFailure) as failure:
        session.ensure_ready()
    assert failure.value.observation.code == "mumu_endpoint_unavailable"
    assert all(call[0] != "api" for call in vendor.calls)


def test_stop_rejects_replaced_instance_without_sending_shutdown(manager_file):
    vendor = MuMuManager(name="另一个实例")
    with pytest.raises(InstanceBindingError):
        ProductionSimulator(run=vendor).stop(bound(manager_file), 3)
    assert vendor.calls == [["info", "-v", "0"]]


def test_manual_address_cannot_override_another_instance_reported_port(manager_file):
    vendor = MuMuManager(other=16384)
    with pytest.raises(InstanceBindingError) as failure:
        ProductionSimulator(run=vendor).inspect(bound(manager_file), 3)
    assert failure.value.code == "mumu_endpoint_unavailable"
    assert all(call[0] != "api" for call in vendor.calls)


def test_manual_address_cannot_override_a_different_manager_address(manager_file):
    vendor = MuMuManager(query=b"127.0.0.1:16448")
    with pytest.raises(InstanceBindingError) as failure:
        ProductionSimulator(run=vendor).inspect(bound(manager_file), 3)
    assert failure.value.code == "mumu_endpoint_unavailable"


def test_manual_address_rechecks_other_instances_even_when_info_reports_the_port(
    manager_file,
):
    vendor = MuMuManager(port=16384, other=16384)
    with pytest.raises(InstanceBindingError) as failure:
        ProductionSimulator(run=vendor).inspect(bound(manager_file), 3)
    assert failure.value.code == "mumu_endpoint_unavailable"
    assert vendor.calls == [["info", "-v", "0"], ["info", "-v", "all"]]


def test_selected_unresolved_instance_rechecks_a_later_reported_port(manager_file):
    vendor = MuMuManager(port=16384, other=16384, created=111)
    selected = bound(manager_file, manual="", mumu_created_timestamp="111")
    with pytest.raises(InstanceBindingError) as failure:
        ProductionSimulator(run=vendor).inspect(selected, 3)
    assert failure.value.code == "mumu_endpoint_unavailable"


def test_starting_instance_waits_for_android_before_checking_manual_address(
    manager_file,
):
    vendor = MuMuManager(running=True, android=False, port=16384)
    observed = ProductionSimulator(run=vendor).inspect(bound(manager_file), 3)
    assert observed.state == "starting"
    assert observed.serial is None
    assert vendor.calls == [["info", "-v", "0"]]


def test_manual_preflight_records_creation_time_and_rejects_a_replaced_instance(
    manager_file,
):
    vendor = MuMuManager(created=111)
    simulator = ProductionSimulator(run=vendor)
    io = PreflightIO()
    io.host, io.boot = "windows", "1"
    io.installed.add(str(manager_file))
    io.targets = [(ADDRESS, "device")]
    io.installed_packages = ["com.hypergryph.arknights"]
    selected = bound(manager_file, adb_path="manual-adb")
    result = DiscoveryService(MuMuDiscoveryIO(run=vendor), simulator).check_binding(
        selected, PreflightService(io)
    )
    assert result.ok
    assert result.profile_patch["mumu_created_timestamp"] == "111"

    saved = selected.model_copy(update=result.profile_patch)
    vendor.created = 222
    vendor.calls.clear()
    with pytest.raises(InstanceBindingError) as failure:
        simulator.inspect(saved, 3)
    assert failure.value.code == "binding_changed"
    with pytest.raises(InstanceBindingError):
        simulator.stop(saved, 3)
    vendor.created = None
    with pytest.raises(InstanceBindingError):
        simulator.inspect(saved, 3)
    assert all(call[0] != "api" for call in vendor.calls)


def test_manager_verification_rejects_a_reported_port_conflict(manager_file):
    from arknights_mower.utils import managed_device

    vendor = MuMuManager(port=16384, other=16384)
    with (
        patch(
            "arknights_mower.utils.device.session_io.ProductionSimulator",
            return_value=ProductionSimulator(run=vendor),
        ),
        pytest.raises(InstanceBindingError) as failure,
    ):
        managed_device.inspect_mumu_identity(bound(manager_file))
    assert failure.value.code == "mumu_endpoint_unavailable"


def test_missing_port_instance_remains_explicitly_selectable(manager_file):
    vendor = MuMuManager(created=111)
    io = MuMuDiscoveryIO(
        run=vendor,
        platform="windows",
        registry_paths=lambda: [],
        fixed_paths=lambda: [],
        process_paths=lambda: [],
    )
    probe = PreflightIO()
    probe.host = "windows"
    result = DiscoveryService(io).discover(
        DeviceProfile(manager_path=str(manager_file)),
        "windows",
        PreflightService(probe),
    )
    assert result.selected_key is None
    assert result.error.code == "mumu_endpoint_unavailable"
    assert len(result.candidates) == 1
    assert result.candidates[0]["binding"]["instance_id"] == "0"
    assert result.candidates[0]["binding"]["mumu_created_timestamp"] == "111"
    assert result.candidates[0]["serial"] == ""

    selected = Conf().updated({"device": result.candidates[0]["binding"]})
    assert selected.device.mumu_created_timestamp == "111"
    assert (
        config.persistent_conf(selected.model_dump())["device"][
            "mumu_created_timestamp"
        ]
        == "111"
    )
    vendor.created = 222
    with pytest.raises(InstanceBindingError) as failure:
        ProductionSimulator(run=vendor).inspect(selected.device, 3)
    assert failure.value.code == "binding_changed"


def test_missing_port_error_keeps_the_observed_creation_time(manager_file):
    vendor = MuMuManager(created=111)
    io = PreflightIO()
    io.host = "windows"
    result = DiscoveryService(
        MuMuDiscoveryIO(run=vendor), ProductionSimulator(run=vendor)
    ).check_binding(
        bound(manager_file, manual="", adb_path="manual-adb"), PreflightService(io)
    )
    assert result.error.code == "mumu_endpoint_unavailable"
    assert result.error.mumu_created_timestamp == "111"


def test_creation_time_without_manual_address_is_saved_for_the_selected_instance(
    manager_file,
):
    profile = bound(manager_file, manual="", mumu_created_timestamp="111")
    saved = config.persistent_conf(Conf(device=profile.model_dump()).model_dump())
    assert saved["device"]["mumu_created_timestamp"] == "111"


def test_identity_changes_clear_the_manually_entered_address(manager_file):
    original = Conf(
        device=bound(manager_file, mumu_created_timestamp="111").model_dump()
    )
    for field, value in (
        ("instance_id", "1"),
        ("instance_name", "其他实例"),
        ("manager_path", str(Path(manager_file).parent / "other.exe")),
        ("preset_id", "manual.other"),
    ):
        updated = original.updated({"device": {field: value}})
        assert updated.device.mumu_manual_serial == ""
        assert updated.device.mumu_created_timestamp == (
            "" if field == "preset_id" else "111"
        )
    cleared = original.updated({"device": {"mumu_manual_serial": ""}})
    assert cleared.device.mumu_created_timestamp == "111"


def test_same_creation_time_is_retained_when_selecting_a_different_instance(
    manager_file,
):
    original = Conf(
        device=bound(manager_file, mumu_created_timestamp="111").model_dump()
    )
    selected = original.updated(
        {
            "device": {
                "instance_id": "1",
                "instance_name": "小号",
                "mumu_manual_serial": "",
            }
        }
    )
    assert selected.device.mumu_manual_serial == ""
    assert selected.device.mumu_created_timestamp == "111"


def test_discovery_keeps_creation_time_even_when_a_port_is_initially_reported(
    manager_file,
):
    vendor = MuMuManager(created=111, port=16384)
    io = MuMuDiscoveryIO(
        run=vendor,
        platform="windows",
        registry_paths=lambda: [],
        fixed_paths=lambda: [],
        process_paths=lambda: [],
    )
    probe = PreflightIO()
    probe.host = "windows"
    result = DiscoveryService(io).discover(
        DeviceProfile(manager_path=str(manager_file)),
        "windows",
        PreflightService(probe),
    )
    candidate = result.candidates[0]
    assert candidate["serial"] == ADDRESS
    assert candidate["binding"]["mumu_created_timestamp"] == "111"
    selected = Conf().updated({"device": candidate["binding"]})
    vendor.created = 222
    vendor.port = 0
    with pytest.raises(InstanceBindingError) as failure:
        ProductionSimulator(run=vendor).inspect(selected.device, 3)
    assert failure.value.code == "binding_changed"


def test_changing_manual_address_cannot_erase_the_saved_instance_creation_time(
    manager_file,
):
    original = Conf(
        device=bound(manager_file, mumu_created_timestamp="111").model_dump()
    )
    updated = original.updated(
        {
            "device": {
                "mumu_manual_serial": "127.0.0.1:16448",
                "mumu_created_timestamp": "",
            }
        }
    )
    assert updated.device.mumu_created_timestamp == "111"


def test_empty_manual_address_is_not_written_into_existing_device_configuration():
    current = Conf().updated({"theme": "dark"}).model_dump(exclude_unset=True)
    before = dict(current["device"])
    saved = config.persistent_conf(current)
    assert "mumu_manual_serial" not in saved["device"]
    assert "mumu_created_timestamp" not in saved["device"]
    assert current["device"] == before


def test_manual_address_is_preserved_when_explicitly_configured(manager_file):
    current = Conf(device=bound(manager_file).model_dump()).model_dump(
        exclude_unset=True
    )
    assert config.persistent_conf(current)["device"]["mumu_manual_serial"] == ADDRESS


def test_manual_address_is_not_allowed_with_mumu_ipc(manager_file):
    with pytest.raises(ValidationError):
        bound(manager_file, screenshot_backend="mumu_ipc", touch_backend="mumu_ipc")


class MuMuManualRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        folder = self.enterContext(tempfile.TemporaryDirectory())
        manager = Path(folder) / "MuMuManager.exe"
        manager.touch()
        self.vendor = MuMuManager(created=111)
        self.clock = Clock()
        adb = ADB()
        adb.rows, adb.boot = [(ADDRESS, "device")], "1"
        simulator = ProductionSimulator(run=self.vendor, monotonic=self.clock.monotonic)
        session = DeviceSession(adb, simulator, clock=self.clock)
        io = PreflightIO()
        io.host = "windows"
        io.installed.update({folder, str(manager)})
        io.targets = [(ADDRESS, "device")]
        io.boot = "1"
        io.installed_packages = ["com.hypergryph.arknights"]
        discovery = MuMuDiscoveryIO(
            run=self.vendor,
            platform="windows",
            registry_paths=lambda: [],
            fixed_paths=lambda: [],
            process_paths=lambda: [],
        )
        self.control = DeviceControl(
            lambda: config.conf,
            Mock(),
            preflight=PreflightService(io),
            discovery=DiscoveryService(discovery, simulator),
            session=session,
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)
        config.conf = Conf(
            device=bound(
                manager, manual="", installation_path=folder, adb_path="manual-adb"
            ).model_dump()
        )
        config.save_conf()

    def test_manual_address_preflight_save_and_automatic_start(self):
        before = self.path.read_bytes()
        for route in ("/device/preflight", "/device/start"):
            for headers in ({}, {"token": "wrong"}):
                self.assertEqual(
                    self.client.post(route, headers=headers, json={}).status_code, 403
                )
        self.assertEqual(self.vendor.calls, [])
        response = self.client.post(
            "/device/preflight",
            headers=self.headers,
            json={"device": {"mumu_manual_serial": ADDRESS, "last_serial": ""}},
        )
        self.assertTrue(response.json["ok"], response.json)
        self.assertEqual(response.json["serial"], ADDRESS)
        self.assertEqual(
            response.json["profile_patch"]["mumu_created_timestamp"], "111"
        )
        self.assertEqual(self.path.read_bytes(), before)
        saved = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "mumu_manual_serial": ADDRESS,
                    "mumu_created_timestamp": "111",
                    "last_serial": "",
                }
            },
        )
        self.assertEqual(saved.status_code, 200, saved.json)
        saved = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": ADDRESS,
                    "game_package": response.json["game_package"],
                }
            },
        )
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(config.conf.device.preset_id, "windows.mumu12")
        self.assertEqual(config.conf.device.mumu_manual_serial, ADDRESS)
        self.assertEqual(config.conf.device.mumu_created_timestamp, "111")
        self.vendor.running = False
        self.vendor.calls.clear()
        started = self.client.post("/device/start", headers=self.headers, json={})
        self.assertTrue(started.json["ok"], started.json)
        self.assertEqual(started.json["serial"], ADDRESS)
        self.assertEqual(started.json["profile_patch"]["mumu_created_timestamp"], "111")
        self.assertIn(["api", "-v", "0", "launch_player"], self.vendor.calls)

    def test_starting_a_stopped_manual_draft_returns_the_creation_time(self):
        self.vendor.running = False
        before = self.path.read_bytes()
        started = self.client.post(
            "/device/start",
            headers=self.headers,
            json={"device": {"mumu_manual_serial": ADDRESS}},
        )
        self.assertTrue(started.json["ok"], started.json)
        self.assertEqual(started.json["profile_patch"]["mumu_created_timestamp"], "111")
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_start_reports_the_observed_creation_time(self):
        result = self.client.post("/device/start", headers=self.headers, json={})
        self.assertFalse(result.json["ok"])
        self.assertEqual(result.json["error"]["code"], "mumu_endpoint_unavailable")
        self.assertEqual(result.json["error"]["mumu_created_timestamp"], "111")
        self.assertFalse(any(call[0] == "api" for call in self.vendor.calls))
