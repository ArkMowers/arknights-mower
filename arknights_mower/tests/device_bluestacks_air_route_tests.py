"""Air discovery, repair and explicit endpoint selection through HTTP."""

import plistlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.bluestacks_air import BlueStacksAirDiscovery
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService

AIR_PRESET = "macos.bluestacks_air"
AIR_SERIAL = "127.0.0.1:5555"
GAME_PACKAGE = "com.hypergryph.arknights.bilibili"


class BlueStacksAirRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.app = root / "BlueStacks.app"
        (self.app / "Contents/MacOS").mkdir(parents=True)
        (self.app / "Contents/Info.plist").write_bytes(
            plistlib.dumps(
                {
                    "CFBundleName": "BlueStacks",
                    "CFBundleExecutable": "BlueStacks",
                    "CFBundleShortVersionString": "5.21.782",
                }
            )
        )
        self.io = PreflightIO()
        self.io.host = "macos"
        self.io.installed.add(str(self.app))
        self.io.targets = [(AIR_SERIAL, "device")]
        self.sources = DiscoveryIO()
        self.control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                self.sources,
                air=BlueStacksAirDiscovery(application_paths=[self.app]),
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def discover(self, device=None):
        response = self.client.post(
            "/device/discover",
            headers=self.headers,
            json={} if device is None else {"device": device},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def preflight(self, device=None):
        response = self.client.post(
            "/device/preflight",
            headers=self.headers,
            json={} if device is None else {"device": device},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def assert_ready(self, result, serial=AIR_SERIAL):
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["kind"], "preflight")
        self.assertEqual(result["preset_id"], AIR_PRESET)
        self.assertEqual(result["host_platform"], "macos")
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["serial"], serial)
        self.assertEqual(result["observations"]["effective"], [1920, 1080])
        self.assertEqual(result["observations"]["frame"], [1920, 1080])
        self.assertEqual(result["game_package"], GAME_PACKAGE)

    def test_settings_reads_and_unauthorized_actions_do_not_scan_or_connect(self):
        before = self.path.read_bytes()
        original_is_file = Path.is_file

        def read_file(path):
            if path == self.app / "Contents/Info.plist":
                raise AssertionError("settings reads must not inspect an application")
            return original_is_file(path)

        with (
            patch.object(Path, "is_file", read_file),
            patch.object(self.io, "devices", side_effect=AssertionError("ADB scan")),
        ):
            for route in ("/conf", "/device/status"):
                self.assertEqual(
                    self.client.get(route, headers=self.headers).status_code, 200
                )
                self.assertEqual(self.client.get(route).status_code, 403)
            for route in ("/device/discover", "/device/preflight"):
                self.assertEqual(self.client.post(route, json={}).status_code, 403)
        self.assertEqual(self.sources.calls, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_default_detection_finds_air_and_validates_without_saving(self):
        self.assertEqual(config.conf.device.preset_id, "manual.other")
        before = self.path.read_bytes()
        with patch.object(
            self.io, "boot_completed", wraps=self.io.boot_completed
        ) as boot:
            detected = self.discover()
        self.assert_ready(detected)
        boot.assert_called_once_with("product-adb", AIR_SERIAL)
        self.assertEqual(detected["profile_patch"]["installation_path"], str(self.app))
        self.assertEqual(detected["profile_patch"]["instance_id"], "")
        self.assertEqual(detected["profile_patch"]["manager_path"], "")
        self.assertIn("不提供多实例", detected["guidance"])
        self.assertEqual(config.conf.device.preset_id, "manual.other")
        self.assertEqual(config.conf.device.last_serial, "USB-123")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.sources.calls, 0)

    def test_first_macos_configuration_has_no_inherited_emulator_endpoint(self):
        self.path.unlink()
        with patch("arknights_mower.utils.config.__system__", "darwin", create=True):
            config.load_conf()
        loaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(loaded["device"]["preset_id"], "manual.other")
        self.assertEqual(loaded["device"]["last_serial"], "")
        self.assert_ready(self.discover())

    def test_existing_macos_manual_configuration_keeps_its_endpoint(self):
        config.conf.device.last_serial = "127.0.0.1:16384"
        config.save_conf()
        before = self.path.read_bytes()
        with patch("arknights_mower.utils.config.__system__", "darwin", create=True):
            config.load_conf()
        loaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(loaded["device"]["preset_id"], "manual.other")
        self.assertEqual(loaded["device"]["last_serial"], "127.0.0.1:16384")
        self.assertEqual(self.path.read_bytes(), before)

    def test_adb_off_returns_settings_serial_repair_and_retry_then_succeeds(self):
        self.io.targets = []
        before = self.path.read_bytes()
        rejected = self.discover()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "air_adb_unavailable")
        self.assertEqual(rejected["error"]["fields"], ["last_serial"])
        self.assertEqual(rejected["error"]["action"], "retry")
        for instruction in ("Settings", "Advanced", "ADB", "保存", "重试"):
            self.assertIn(instruction, rejected["error"]["message"])
        self.assertEqual(rejected["profile_patch"], {})
        self.io.targets = [(AIR_SERIAL, "device")]
        self.assert_ready(self.discover())
        self.assertEqual(self.path.read_bytes(), before)

    def test_binding_then_endpoint_save_survives_reload_and_reinspection(self):
        detected = self.discover()
        self.assert_ready(detected)
        saved = self.client.patch(
            "/conf", headers=self.headers, json={"device": detected["profile_patch"]}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["preset_id"], AIR_PRESET)
        self.assertEqual(saved.json["device"]["last_serial"], "")
        accepted = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": detected["serial"],
                    "adb_path": detected["adb_path"],
                    "game_package": detected["game_package"],
                    "game_package_confirmed": True,
                }
            },
        )
        self.assertEqual(accepted.status_code, 200)
        config.load_conf()
        reloaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(reloaded["device"]["preset_id"], AIR_PRESET)
        self.assertEqual(reloaded["device"]["installation_path"], str(self.app))
        self.assertEqual(reloaded["device"]["last_serial"], AIR_SERIAL)
        self.assertEqual(reloaded["device"]["game_package"], GAME_PACKAGE)
        self.assertEqual(reloaded["device"]["instance_id"], "")
        before = self.path.read_bytes()
        self.assert_ready(self.preflight())
        self.assertEqual(self.path.read_bytes(), before)

    def test_multiple_devices_require_explicit_serial_and_never_select_first(self):
        self.io.targets = [("USB-other", "device"), (AIR_SERIAL, "device")]
        before = self.path.read_bytes()
        with patch.object(
            self.io, "boot_completed", wraps=self.io.boot_completed
        ) as boot:
            rejected = self.discover()
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["status"], "selection_required")
            self.assertEqual(rejected["serial"], "")
            self.assertEqual(rejected["error"]["code"], "multiple_devices")
            self.assertEqual(rejected["error"]["fields"], ["last_serial"])
            self.assertEqual(
                [target["serial"] for target in rejected["candidates"]],
                ["USB-other", AIR_SERIAL],
            )
            boot.assert_not_called()
            checked = self.preflight(
                {
                    "preset_id": AIR_PRESET,
                    "installation_path": str(self.app),
                    "last_serial": AIR_SERIAL,
                }
            )
            self.assert_ready(checked)
            boot.assert_called_once_with("product-adb", AIR_SERIAL)
        self.assertEqual(self.path.read_bytes(), before)

    def test_air_draft_preserves_explicit_serial_equal_to_previous_manual_target(self):
        self.io.targets = [("USB-other", "device"), (AIR_SERIAL, "device")]
        config.conf = config.conf.updated({"device": {"last_serial": AIR_SERIAL}})
        config.save_conf()
        before = self.path.read_bytes()
        checked = self.preflight(
            {
                "preset_id": AIR_PRESET,
                "installation_path": str(self.app),
                "last_serial": AIR_SERIAL,
            }
        )
        self.assert_ready(checked)
        self.assertEqual(config.conf.device.preset_id, "manual.other")
        self.assertEqual(self.path.read_bytes(), before)

    def test_non_macos_air_preflight_returns_platform_repair_without_adb(self):
        for host in ("windows", "linux"):
            with self.subTest(host=host):
                self.io.host = host
                with patch.object(
                    self.io, "devices", side_effect=AssertionError("ADB scan")
                ):
                    rejected = self.preflight(
                        {
                            "preset_id": AIR_PRESET,
                            "installation_path": str(self.app),
                            "last_serial": AIR_SERIAL,
                        }
                    )
                self.assertFalse(rejected["ok"])
                self.assertEqual(rejected["error"]["code"], "unsupported_host")
                self.assertEqual(rejected["error"]["fields"], ["preset_id"])
                self.assertIn("macOS", rejected["error"]["message"])


if __name__ == "__main__":
    unittest.main()
