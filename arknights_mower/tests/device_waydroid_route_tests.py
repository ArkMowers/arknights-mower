"""Waydroid discovery, explicit binding and read-only preflight through HTTP."""

import json
import subprocess
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
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.waydroid import WaydroidController

TARGET_SERIAL = "192.168.240.112:5555"
DATA_PATH = "/home/alice/.local/share/waydroid/data"


class WaydroidRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = directory / "waydroid"
        manager.touch()
        manager.chmod(0o755)
        busctl = directory / "busctl"
        busctl.touch()
        busctl.chmod(0o755)
        self.commands = []
        self.metadata = {
            "state": "RUNNING",
            "user_id": "1000",
            "waydroid_data": DATA_PATH,
        }
        self.output = (
            "Session:\tRUNNING\nContainer:\tRUNNING\nVendor type:\tMAINLINE\n"
            "IP address:\t192.168.240.112\nSession user:\talice(1000)\n"
            "Wayland display:\twayland-0\n"
        )

        def run(argv, **kwargs):
            self.commands.append(argv)
            output = (
                json.dumps({"type": "a{ss}", "data": [self.metadata]})
                if argv[0] == str(busctl)
                else self.output
            )
            return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

        self.waydroid = WaydroidController(
            run=run,
            which=lambda name: str(directory / name),
            uid=lambda: 1000,
            host="linux",
            data_path=DATA_PATH,
        )
        self.io = PreflightIO()
        self.io.installed.update({str(directory), str(manager)})
        self.io.targets = [("USB-other", "device"), (TARGET_SERIAL, "device")]
        self.control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.waydroid, waydroid=self.waydroid
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def discover(self):
        response = self.client.post(
            "/device/discover",
            headers=self.headers,
            json={"device": {"preset_id": "linux.waydroid", "last_serial": ""}},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def bind(self):
        discovered = self.discover()
        self.assertTrue(discovered["ok"], discovered["error"])
        candidate = discovered["candidates"][0]
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def check(self):
        response = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_discovery_uses_official_environment_without_saving_other_online_device(
        self,
    ):
        before = self.path.read_bytes()
        result = self.discover()
        self.assertTrue(result["ok"], result["error"])
        candidate = result["candidates"][0]
        self.assertEqual(result["selected_key"], candidate["key"])
        self.assertEqual(candidate["serial"], TARGET_SERIAL)
        self.assertEqual(candidate["binding"]["instance_id"], "waydroid:1000")
        self.assertEqual(candidate["binding"]["config_path"], DATA_PATH)
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(config.conf.device.last_serial, "USB-123")
        self.assertEqual(self.path.read_bytes(), before)

    def test_settings_reads_and_unauthorized_requests_never_scan(self):
        before = self.path.read_bytes()
        with patch.object(self.io, "devices", side_effect=AssertionError("ADB scan")):
            for route in ("/conf", "/device/status"):
                self.assertEqual(
                    self.client.get(route, headers=self.headers).status_code, 200
                )
            for route in ("/device/discover", "/device/preflight"):
                response = self.client.post(
                    route, json={"device": {"preset_id": "linux.waydroid"}}
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_binding_and_verified_endpoint_save_survive_reload_and_ip_change(self):
        saved = self.bind()
        self.assertEqual(saved["device"]["last_serial"], "")
        self.assertEqual(saved["adb"], "")
        before = self.path.read_bytes()
        checked = self.check()
        self.assertTrue(checked["ok"], checked["error"])
        self.assertEqual(checked["serial"], TARGET_SERIAL)
        self.assertEqual(checked["observations"]["effective"], [1920, 1080])
        self.assertEqual(checked["observations"]["frame"], [1920, 1080])
        self.assertEqual(checked["game_package"], "com.hypergryph.arknights.bilibili")
        self.assertEqual(self.path.read_bytes(), before)
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": checked["serial"],
                    "adb_path": checked["adb_path"],
                    "game_package": checked["game_package"],
                    "game_package_confirmed": True,
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        config.load_conf()
        reloaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(reloaded["device"]["instance_id"], "waydroid:1000")
        self.assertEqual(reloaded["device"]["config_path"], DATA_PATH)
        self.assertEqual(reloaded["device"]["last_serial"], TARGET_SERIAL)
        self.assertEqual(reloaded["device"]["game_package"], checked["game_package"])
        self.output = self.output.replace("192.168.240.112", "192.168.240.120")
        self.io.targets.append(("192.168.240.120:5555", "device"))
        before = self.path.read_bytes()
        refreshed = self.check()
        self.assertTrue(refreshed["ok"], refreshed["error"])
        self.assertEqual(refreshed["serial"], "192.168.240.120:5555")
        self.assertEqual(config.conf.device.last_serial, TARGET_SERIAL)
        self.assertEqual(self.path.read_bytes(), before)

    def test_changed_data_environment_requires_reselection_without_adb_fallback(self):
        self.bind()
        before = self.path.read_bytes()
        self.metadata["waydroid_data"] = "/home/alice/another-waydroid/data"
        with patch.object(
            self.io, "devices", side_effect=AssertionError("ADB fallback")
        ):
            checked = self.check()
        self.assertFalse(checked["ok"])
        self.assertEqual(checked["error"]["code"], "waydroid_binding_changed")
        self.assertEqual(checked["error"]["action"], "select")
        self.assertEqual(checked["serial"], "")
        self.assertEqual(config.conf.device.config_path, DATA_PATH)
        self.assertEqual(self.path.read_bytes(), before)

    def test_preflight_rejects_transport_boot_frame_and_package_failures(self):
        self.bind()
        before = self.path.read_bytes()
        for name, value, code in (
            ("targets", [("USB-other", "device")], "target_absent"),
            ("boot", "0", "boot_incomplete"),
            # A parsed size is diagnostic; only an unreadable one still stops.
            ("size", "Physical size: not-a-size", "invalid_size"),
            ("frame", None, "frame_failed"),
            ("installed_packages", [], "package_missing"),
            (
                "installed_packages",
                ["com.hypergryph.arknights", "com.hypergryph.arknights.bilibili"],
                "package_ambiguous",
            ),
        ):
            with self.subTest(code=code):
                previous = getattr(self.io, name)
                setattr(self.io, name, value)
                try:
                    checked = self.check()
                    self.assertFalse(checked["ok"])
                    self.assertEqual(checked["error"]["code"], code)
                    self.assertEqual(checked["serial"], TARGET_SERIAL)
                    self.assertTrue(checked["error"]["message"])
                    self.assertEqual(self.path.read_bytes(), before)
                finally:
                    setattr(self.io, name, previous)

    def test_multiple_official_addresses_require_explicit_matching_endpoint(self):
        before = self.path.read_bytes()
        self.output += "IP address:\t192.168.240.120\n"
        ambiguous = self.discover()
        self.assertFalse(ambiguous["ok"])
        self.assertIsNone(ambiguous["selected_key"])
        self.assertEqual(ambiguous["error"]["code"], "endpoint_ambiguous")
        self.assertEqual(ambiguous["error"]["action"], "select")
        self.assertEqual(ambiguous["error"]["fields"], ["last_serial"])
        response = self.client.post(
            "/device/discover",
            headers=self.headers,
            json={
                "device": {
                    "preset_id": "linux.waydroid",
                    "last_serial": TARGET_SERIAL,
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"], response.json["error"])
        self.assertEqual(response.json["candidates"][0]["serial"], TARGET_SERIAL)
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
