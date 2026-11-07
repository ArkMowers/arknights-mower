"""AVD discovery, one-shot launch consent and persistence through HTTP."""

import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_avd_tests import AVDIO
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy

AVD_NAME = "Mower_API_35"
TARGET_SERIAL = "emulator-5580"
GAME_PACKAGE = "com.hypergryph.arknights.bilibili"


class AVDRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        self.io, self.avd = PreflightIO(), AVDIO()
        self.clock, self.adb = Clock(), ADB()
        self.io.installed.update({"/sdk", "/sdk/emulator/emulator"})
        self.io.paths.add("verified-adb")
        self.adb.rows = [("emulator-5554", "device"), (TARGET_SERIAL, "device")]
        self.adb.boot = "1"
        self.io.targets = self.adb.rows
        self.avd.on_start = self.mark_started
        self.control = DeviceControl(
            lambda: config.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(DiscoveryIO(), self.avd, avd=self.avd),
            avd=self.avd,
            session=DeviceSession(
                self.adb,
                self.avd,
                clock=self.clock,
                policy=RecoveryPolicy(timeout=5, poll_interval=1),
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def mark_started(self):
        self.avd.state = "running"
        self.avd.serial = TARGET_SERIAL

    def discover(self, host="linux"):
        self.io.host = host
        response = self.client.post(
            "/device/discover",
            headers=self.headers,
            json={"device": {"preset_id": f"{host}.avd", "last_serial": ""}},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def bind(self, host="linux"):
        candidate = self.discover(host)["candidates"][0]
        response = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["device"]["last_serial"], "")
        return response.json

    def launch(self, **kwargs):
        response = self.client.post(
            "/device/avd/start",
            headers=self.headers,
            json={"confirmed_instance": AVD_NAME, **kwargs},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def test_settings_reads_and_token_failures_never_launch_or_scan(self):
        before = self.path.read_bytes()
        with (
            patch.object(self.avd, "discover", side_effect=AssertionError("AVD scan")),
            patch.object(self.io, "devices", side_effect=AssertionError("ADB scan")),
        ):
            for route in ("/conf", "/device/status"):
                self.assertEqual(
                    self.client.get(route, headers=self.headers).status_code, 200
                )
            response = self.client.post(
                "/device/avd/start", json={"confirmed_instance": AVD_NAME}
            )
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.avd.launches, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_discovery_selects_one_or_requires_selection_without_launch_or_save(self):
        before = self.path.read_bytes()
        for host in ("linux", "macos"):
            with self.subTest(host=host):
                single = self.discover(host)
                self.assertEqual(single["kind"], "discovery")
                self.assertEqual(single["status"], "discovered")
                candidate = single["candidates"][0]
                self.assertEqual(candidate["key"], single["selected_key"])
                self.assertEqual(candidate["binding"]["preset_id"], f"{host}.avd")
                self.assertEqual(candidate["binding"]["last_serial"], "")
                self.avd.names.append("Personal_API_35")
                multiple = self.discover(host)
                self.assertEqual(multiple["status"], "selection_required")
                self.assertIsNone(multiple["selected_key"])
                self.assertEqual(len(multiple["candidates"]), 2)
                self.avd.names.pop()
        self.assertEqual(self.avd.launches, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_first_linux_configuration_discovers_avd_without_legacy_endpoint(self):
        self.path.unlink()
        with patch("arknights_mower.utils.config.__system__", "linux", create=True):
            config.load_conf()
        loaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(loaded["device"]["preset_id"], "manual.other")
        self.assertEqual(loaded["device"]["last_serial"], "")
        detected = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(detected.status_code, 200)
        self.assertTrue(detected.json["ok"], detected.json["error"])
        self.assertEqual(detected.json["candidates"][0]["preset_id"], "linux.avd")
        self.assertEqual(self.avd.launches, [])

    def test_invalid_payload_or_missing_consent_never_launches(self):
        self.bind()
        before = self.path.read_bytes()
        for payload in (
            [],
            None,
            {},
            {"confirmed_instance": ""},
            {"confirmed_instance": " "},
            {"confirmed_instance": True},
            {"confirmed_instance": 35},
            {"confirmed_instance": AVD_NAME, "remember": True},
            {"confirmed_instance": AVD_NAME, "device": []},
            {"confirmed_instance": AVD_NAME, "confirmed_package": "not-a-game"},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/device/avd/start", headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.avd.launches, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_wrong_instance_and_read_only_preflight_never_launch(self):
        self.bind()
        before = self.path.read_bytes()
        wrong = self.launch(confirmed_instance="Personal_API_35")
        self.assertFalse(wrong["ok"])
        self.assertEqual(wrong["error"]["code"], "start_confirmation_required")
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(checked.status_code, 200)
        self.assertFalse(checked.json["ok"])
        self.assertEqual(checked.json["error"]["code"], "start_confirmation_required")
        self.assertEqual(self.avd.launches, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_confirmed_launch_uses_dynamic_target_and_never_persists_draft(self):
        candidate = self.discover()["candidates"][0]
        before = self.path.read_bytes()
        self.io.installed_packages.append("com.hypergryph.arknights")
        ready = self.launch(device=candidate["binding"], confirmed_package=GAME_PACKAGE)
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(ready["status"], "ready")
        self.assertEqual(ready["serial"], TARGET_SERIAL)
        self.assertEqual(ready["adb_path"], "product-adb")
        self.assertEqual(ready["observations"]["effective"], [1920, 1080])
        self.assertEqual(ready["observations"]["frame"], [1920, 1080])
        self.assertEqual(ready["game_package"], GAME_PACKAGE)
        self.assertEqual(self.avd.launches, [AVD_NAME])
        self.assertEqual(config.conf.device.preset_id, "manual.other")
        self.assertEqual(config.conf.device.last_serial, "USB-123")
        self.assertEqual(self.path.read_bytes(), before)

    def test_confirmed_launch_reports_preflight_failure_without_saving(self):
        self.bind()
        before = self.path.read_bytes()
        # Only an unreadable or ambiguous size stops the read-only check; the
        # decoded frame is what a parsed size is judged against.
        self.io.size = "Physical size: not-a-size"
        rejected = self.launch()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["serial"], TARGET_SERIAL)
        self.assertEqual(rejected["error"]["code"], "invalid_size")
        self.assertEqual(self.avd.launches, [AVD_NAME])
        self.assertEqual(self.path.read_bytes(), before)

    def test_binding_then_verified_endpoint_save_survives_reload(self):
        saved = self.bind()
        self.assertEqual(saved["device"]["instance_id"], AVD_NAME)
        self.assertEqual(saved["adb"], "")
        before = self.path.read_bytes()
        ready = self.launch()
        self.assertTrue(ready["ok"], ready["error"])
        self.assertEqual(self.path.read_bytes(), before)
        response = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": ready["serial"],
                    "adb_path": ready["adb_path"],
                    "game_package": ready["game_package"],
                    "game_package_confirmed": True,
                }
            },
        )
        self.assertEqual(response.status_code, 200)
        config.load_conf()
        reloaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(reloaded["device"]["preset_id"], "linux.avd")
        self.assertEqual(reloaded["device"]["instance_id"], AVD_NAME)
        self.assertEqual(reloaded["device"]["last_serial"], TARGET_SERIAL)
        self.assertNotIn("confirmed_instance", reloaded["device"])
        self.avd.serial = "emulator-5590"
        self.io.targets.append(("emulator-5590", "device"))
        before = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], "emulator-5590")
        self.assertEqual(self.avd.launches, [AVD_NAME])
        self.assertEqual(self.path.read_bytes(), before)

    def test_active_device_and_worker_reject_launch_before_adapter_io(self):
        self.bind()
        self.mark_started()
        started = self.control.start()
        self.assertTrue(started.ok, started.error)
        before = self.path.read_bytes()
        rejected = self.launch()
        self.assertFalse(rejected["ok"])
        self.assertEqual(rejected["error"]["code"], "device_session_active")
        self.control.close()
        worker = MagicMock()
        worker.is_alive.return_value = True
        with patch.object(self.server, "mower_thread", worker):
            rejected = self.client.post(
                "/device/avd/start",
                headers=self.headers,
                json={"confirmed_instance": AVD_NAME},
            )
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(rejected.json["error"]["code"], "device_session_active")
        with self.control.run():
            rejected = self.launch()
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["code"], "device_session_active")
        self.assertEqual(self.avd.launches, [])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
