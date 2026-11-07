"""Selected-instance endpoint refresh with injected external ADB observations."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.bluestacks_discovery import BlueStacksDiscoveryIO
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import (
    ProductionSessionADB,
    ProductionSimulator,
)

FIXTURES = Path(__file__).parent / "fixtures"
SERIAL = "127.0.0.1:61342"
OTHER = "127.0.0.1:5555"
ANDROID_ID = "0123456789abcdef"


class BlueStacksTransport:
    def __init__(self, root):
        self.root = Path(root)
        self.player = self.root / "program/HD-Player.exe"
        self.player.parent.mkdir()
        self.player.touch()
        self.adb = self.root / "program/HD-Adb.exe"
        self.adb.touch()
        self.config_path = self.root / "data/bluestacks.conf"
        self.config_path.parent.mkdir()
        self.config_path.write_bytes(
            (FIXTURES / "bluestacks5_multiple.conf").read_bytes()
        )
        self.states = {OTHER: "device", SERIAL: "device"}
        self.ids = {OTHER: "1111111111111111", SERIAL: ANDROID_ID}
        self.calls = []
        self.connect_output = None
        self.command_error = None
        self.after_identity = lambda: None
        self.io = PreflightIO()
        self.io.host = "windows"
        self.io.paths.add(str(self.adb))
        self.io.installed.update([str(self.player.parent), str(self.player)])
        self.simulator = ProductionSimulator(run=self.run, probe=lambda timeout: None)
        self.discovery = DiscoveryService(
            BlueStacksDiscoveryIO(
                registry_installations=lambda: [
                    (str(self.player), str(self.config_path))
                ],
                platform="windows",
            ),
            self.simulator,
        )
        self.configuration = Conf()
        self.adapter = Mock(wraps=Adapter())
        self.control = DeviceControl(
            lambda: self.configuration,
            self.adapter,
            preflight=PreflightService(self.io),
            discovery=self.discovery,
            session=DeviceSession(
                ProductionSessionADB(
                    run=self.run,
                    probe=lambda timeout: None,
                    # The frame probe belongs to the capture backends; this test
                    # owns binding and ADB-path decisions only.
                    frame=lambda adb_path, serial, timeout: (1920, 1080),
                ),
                self.simulator,
                clock=Clock(),
                policy=RecoveryPolicy(timeout=12, local_wait=1),
            ),
        )
        chosen = self.control.discover().candidates[1]
        self.configuration = self.configuration.updated(
            {"device": {**chosen["binding"], "adb_path": str(self.adb)}}
        )
        self.io.targets = list(self.states.items())

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if argv[0] != str(self.adb):
            raise AssertionError(f"Unexpected executable: {argv}")
        if argv[1] == "version":
            output = "Android Debug Bridge version 1.0.41"
        elif argv[1] == "devices":
            output = "List of devices attached\n" + "\n".join(
                f"{serial}\t{state}" for serial, state in self.states.items()
            )
        elif argv[1] == "connect":
            if self.command_error:
                raise self.command_error
            output = self.connect_output or f"connected to {argv[2]}"
        elif "wm" in argv:
            output = "Physical size: 1920x1080"
        elif argv[1] == "-s":
            if "settings" in argv:
                output = self.ids[argv[2]]
                self.after_identity()
            else:
                output = "1"
        else:
            raise AssertionError(argv)
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    def scenario(self, name):
        row = json.loads((FIXTURES / "bluestacks5_endpoints.json").read_text())[name]
        if row["state"] is None:
            self.states.pop(SERIAL, None)
        else:
            self.states[SERIAL] = row["state"]
        self.ids[SERIAL] = row["android_id"]
        self.io.targets = list(self.states.items())


class BlueStacksSessionTests(unittest.TestCase):
    def setUp(self):
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.fixture = BlueStacksTransport(root)
        self.addCleanup(self.fixture.control.close)

    def test_new_sessions_read_only_bound_keyword_and_its_current_dynamic_port(self):
        fixture = self.fixture
        for port in (61342, 62518):
            serial = f"127.0.0.1:{port}"
            fixture.config_path.write_text(
                (FIXTURES / "bluestacks5_multiple.conf")
                .read_text(encoding="utf-8")
                .replace('status.adb_port="61342"', f'status.adb_port="{port}"'),
                encoding="utf-8",
            )
            fixture.states[serial] = "device"
            fixture.ids[serial] = ANDROID_ID
            fixture.io.targets = list(fixture.states.items())
            result = fixture.control.start()
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.serial, serial)
            self.assertEqual(fixture.configuration.device.instance_id, "Pie64_2")
            fixture.control.close()
        self.assertFalse(any(OTHER in argv for argv, _ in fixture.calls))
        self.assertFalse(any("127.0.0.1:5565" in argv for argv, _ in fixture.calls))
        self.assertEqual(
            fixture.adapter.open_verified.call_args.args[1].observations["frame"],
            [1920, 1080],
        )

    def test_ordinary_mode_reads_bound_adb_port_when_no_status_field_exists(self):
        fixture = self.fixture
        fixture.config_path.write_text(
            fixture.config_path.read_text(encoding="utf-8").replace(
                'bst.instance.Pie64_2.status.adb_port="61342"\n', ""
            ),
            encoding="utf-8",
        )
        fixture.states["127.0.0.1:5565"] = "device"
        fixture.ids["127.0.0.1:5565"] = ANDROID_ID
        fixture.io.targets = list(fixture.states.items())
        result = fixture.control.preflight()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:5565")
        self.assertFalse(any(OTHER in argv for argv, _ in fixture.calls))

    def test_invalid_dynamic_port_never_uses_static_or_saved_online_endpoint(self):
        fixture = self.fixture
        original = fixture.config_path.read_text(encoding="utf-8")
        fixture.configuration.device.last_serial = OTHER
        for port in ("", "0", "65536", "banana", "-1"):
            with self.subTest(port=port):
                fixture.config_path.write_text(
                    original.replace(
                        'status.adb_port="61342"', f'status.adb_port="{port}"'
                    ),
                    encoding="utf-8",
                )
                result = fixture.control.preflight()
                self.assertEqual(result.error.code, "config_invalid")
                self.assertEqual(result.serial, "")
                self.assertEqual(fixture.configuration.device.instance_id, "Pie64_2")
        self.assertEqual(fixture.calls, [])

    def test_disabled_or_missing_adb_switch_gives_vendor_enable_instructions(self):
        fixture = self.fixture
        original = fixture.config_path.read_text(encoding="utf-8")
        for replacement in (
            'bst.enable_adb_access="0"',
            "",
            'bst.enable_adb_access="yes"',
        ):
            with self.subTest(replacement=replacement):
                fixture.config_path.write_text(
                    original.replace('bst.enable_adb_access="1"', replacement),
                    encoding="utf-8",
                )
                result = fixture.control.preflight()
                self.assertEqual(result.error.code, "adb_disabled")
                self.assertIn("高级", result.error.message)
                self.assertIn("Android debug bridge", result.error.message)
                self.assertEqual(result.error.fields, [])
        self.assertEqual(fixture.calls, [])

    def test_stopped_instance_stays_bound_without_starting_or_using_online_peer(self):
        fixture = self.fixture
        fixture.scenario("stopped")
        fixture.configuration.device.last_serial = OTHER
        result = fixture.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "endpoint_unreachable")
        self.assertIn("手动启动", result.error.message)
        self.assertEqual(fixture.configuration.device.instance_id, "Pie64_2")
        fixture.adapter.open_verified.assert_not_called()
        self.assertFalse(any(OTHER in argv for argv, _ in fixture.calls))
        self.assertFalse(
            any(argv[0] == str(fixture.player) for argv, _ in fixture.calls)
        )

    def test_stale_endpoint_now_owned_by_another_android_guest_is_rejected(self):
        fixture = self.fixture
        fixture.scenario("stale")
        result = fixture.control.start()
        self.assertEqual(result.error.code, "endpoint_mismatch")
        fixture.adapter.open_verified.assert_not_called()
        self.assertFalse(any(OTHER in argv for argv, _ in fixture.calls))

    def test_missing_selected_instance_or_file_does_not_reuse_saved_serial(self):
        fixture = self.fixture
        fixture.configuration.device.last_serial = OTHER
        fixture.config_path.write_bytes(
            (FIXTURES / "bluestacks5_single.conf").read_bytes()
        )
        self.assertEqual(fixture.control.preflight().error.code, "instance_missing")
        fixture.config_path.unlink()
        self.assertEqual(fixture.control.preflight().error.code, "missing_config")
        self.assertEqual(fixture.calls, [])

    def test_unreadable_bound_config_repairs_config_access_instead_of_player_path(self):
        fixture = self.fixture
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            checked = fixture.control.preflight()
            self.assertEqual(checked.error.code, "discovery_permission")
            self.assertEqual(checked.error.fields, ["config_path"])
            self.assertIn("配置", checked.error.message)
            started = fixture.control.start()
            self.assertEqual(started.error.code, "discovery_permission")
        fixture.adapter.open_verified.assert_not_called()

    def test_config_changes_during_validation_never_return_a_verified_endpoint(self):
        fixture = self.fixture

        def change():
            fixture.config_path.write_text(
                fixture.config_path.read_text(encoding="utf-8").replace(
                    "61342", "62001"
                ),
                encoding="utf-8",
            )

        fixture.after_identity = change
        result = fixture.control.start()
        self.assertEqual(result.error.code, "binding_changed")
        fixture.adapter.open_verified.assert_not_called()

    def test_duplicate_android_identity_or_endpoint_requires_manual_repair(self):
        fixture = self.fixture
        original = fixture.config_path.read_text(encoding="utf-8")
        for content, code in (
            (original.replace("1111111111111111", ANDROID_ID), "endpoint_ambiguous"),
            (
                original.replace('status.adb_port="5555"', 'status.adb_port="61342"'),
                "config_invalid",
            ),
            (original.replace(ANDROID_ID, "missing"), "config_invalid"),
        ):
            with self.subTest(code=code):
                fixture.config_path.write_text(content, encoding="utf-8")
                self.assertEqual(fixture.control.preflight().error.code, code)
        self.assertEqual(fixture.calls, [])

    def test_offline_unauthorized_or_ambiguous_selected_target_never_falls_back(self):
        fixture = self.fixture
        for state, code in (
            ("offline", "device_offline"),
            ("unauthorized", "device_unauthorized"),
        ):
            with self.subTest(state=state):
                fixture.scenario(state)
                result = fixture.control.preflight()
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.serial, "")
        self.assertFalse(any(OTHER in argv for argv, _ in fixture.calls))

    def test_unreachable_adb_command_has_endpoint_repair_instead_of_binding_fields(
        self,
    ):
        fixture = self.fixture
        fixture.scenario("stopped")
        for failure in (
            subprocess.CalledProcessError(1, "connect", stderr=b"cannot connect"),
            ValueError("cannot connect"),
            subprocess.TimeoutExpired("connect", 3),
        ):
            with self.subTest(failure=type(failure).__name__):
                fixture.command_error = failure
                result = fixture.control.preflight()
                self.assertEqual(result.error.code, "endpoint_unreachable")
                self.assertEqual(result.error.fields, [])
                self.assertIn("手动启动", result.error.message)
        fixture.command_error = None
        fixture.connect_output = "successful but not a connection"
        self.assertEqual(fixture.control.preflight().error.code, "endpoint_unreachable")


if __name__ == "__main__":
    unittest.main()
