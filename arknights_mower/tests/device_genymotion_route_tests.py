"""Genymotion selection and immediate launch consent through authenticated HTTP."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_genymotion_tests import (
    OTHER_ID,
    VM_ID,
    GenymotionFixture,
)
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import ProductionSimulator

TARGET_SERIAL = "127.0.0.1:6555"


class GenymotionRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.gm = GenymotionFixture(root)
        self.io, self.adb = PreflightIO(), ADB()
        self.io.installed.update({str(root), str(self.gm.manager)})
        self.io.paths.add("verified-adb")
        self.adb.rows = [("USB-123", "device"), (TARGET_SERIAL, "device")]
        self.adb.boot = "1"
        self.io.targets = self.adb.rows
        config.conf = config.Conf(
            device={
                "preset_id": "linux.genymotion",
                "instance_id": VM_ID,
                "instance_name": "Mower Linux VM",
                "installation_path": str(root),
                "manager_path": str(self.gm.manager),
                "last_serial": "USB-123",
            }
        )
        config.save_conf()
        simulator = ProductionSimulator(genymotion=self.gm.controller)
        self.control = DeviceControl(
            lambda: config.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), simulator, genymotion=self.gm.controller
            ),
            genymotion=self.gm.controller,
            session=DeviceSession(
                self.adb,
                simulator,
                clock=self.gm.clock,
                policy=RecoveryPolicy(timeout=5, poll_interval=1),
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def launch(self, **kwargs):
        return self.client.post(
            "/device/genymotion/start",
            headers=self.headers,
            json={"confirmed_instance": VM_ID, **kwargs},
        )

    def test_authentication_and_invalid_consent_never_contact_the_manager(self):
        before = self.path.read_bytes()
        missing_token = self.client.post(
            "/device/genymotion/start", json={"confirmed_instance": VM_ID}
        )
        self.assertEqual(missing_token.status_code, 403)
        for payload in (
            {},
            [],
            None,
            {"confirmed_instance": True},
            {"confirmed_instance": " "},
            {"confirmed_instance": VM_ID, "remember": True},
        ):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/device/genymotion/start", headers=self.headers, json=payload
                )
                self.assertEqual(response.status_code, 400)
        wrong = self.launch(confirmed_instance=OTHER_ID)
        self.assertEqual(wrong.status_code, 200)
        self.assertFalse(wrong.json["ok"])
        self.assertEqual(wrong.json["error"]["code"], "start_confirmation_required")
        self.assertEqual(self.gm.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_active_worker_or_run_rejects_launch_before_manager_io(self):
        worker = MagicMock()
        worker.is_alive.return_value = True
        with patch.object(self.server, "mower_thread", worker):
            self.assertEqual(self.launch().status_code, 409)
        with self.control.run():
            rejected = self.launch()
            self.assertEqual(rejected.json["error"]["code"], "device_session_active")
        self.assertEqual(self.gm.calls, [])

    def test_confirmed_launch_starts_once_then_checks_uuid_adb_and_frame(self):
        self.gm.details = self.gm.fixtures["stopped_details"]
        before = self.path.read_bytes()
        stopped = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertFalse(stopped.json["ok"])
        self.assertEqual(stopped.json["error"]["code"], "start_confirmation_required")
        self.assertFalse(any("start" in argv for argv, _ in self.gm.calls))

        def started():
            self.gm.details = self.gm.fixtures["details"]

        self.gm.on_start = started
        ready = self.launch()
        self.assertEqual(ready.status_code, 200)
        self.assertTrue(ready.json["ok"], ready.json["error"])
        self.assertEqual(ready.json["serial"], TARGET_SERIAL)
        self.assertEqual(ready.json["observations"]["effective"], [1920, 1080])
        self.assertEqual(ready.json["observations"]["frame"], [1920, 1080])
        starts = [argv for argv, _ in self.gm.calls if "start" in argv]
        self.assertEqual(
            starts, [[str(self.gm.manager.resolve()), "admin", "start", VM_ID]]
        )
        self.assertFalse(any("list" in argv for argv, _ in self.gm.calls))
        self.assertEqual(self.path.read_bytes(), before)

    def test_manager_contract_failure_keeps_manual_repair_and_never_launches(self):
        self.gm.version = "Version : 99.0.0\n"
        before = self.path.read_bytes()
        rejected = self.launch()
        self.assertFalse(rejected.json["ok"])
        self.assertEqual(
            rejected.json["error"]["code"], "genymotion_version_unsupported"
        )
        self.assertEqual(rejected.json["error"]["action"], "manual")
        self.assertFalse(any("start" in argv for argv, _ in self.gm.calls))
        self.assertEqual(self.path.read_bytes(), before)

    def test_unavailable_current_adb_target_never_switches_or_reuses_launch_consent(
        self,
    ):
        self.gm.details = self.gm.fixtures["stopped_details"]
        self.adb.rows = [("USB-123", "device")]
        before = self.path.read_bytes()

        def started():
            self.gm.details = self.gm.fixtures["details"]

        self.gm.on_start = started
        failed = self.launch()
        self.assertFalse(failed.json["ok"])
        self.assertEqual(self.gm.clock.now, 5)
        self.assertEqual(self.adb.actions, [TARGET_SERIAL])
        self.gm.details = self.gm.fixtures["stopped_details"]
        retry = self.control.start()
        self.assertFalse(retry.ok)
        self.assertEqual(retry.error.code, "start_confirmation_required")
        self.assertEqual(sum("start" in argv for argv, _ in self.gm.calls), 1)
        self.assertFalse(any("list" in argv for argv, _ in self.gm.calls))
        self.assertEqual(self.path.read_bytes(), before)

    def test_discovery_is_read_only_and_selected_binding_clears_the_old_endpoint(self):
        before = self.path.read_bytes()
        found = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertTrue(found.json["ok"], found.json["error"])
        candidate = found.json["candidates"][0]
        self.assertEqual(found.json["selected_key"], candidate["key"])
        self.assertEqual(candidate["instance_id"], VM_ID)
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(self.path.read_bytes(), before)
        saved = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["instance_id"], VM_ID)
        self.assertEqual(saved.json["device"]["last_serial"], "")
        self.assertFalse(saved.json["device"]["game_package_confirmed"])
        self.assertFalse(any("start" in argv for argv, _ in self.gm.calls))

    def test_preflight_refreshes_only_selected_uuid_and_validates_the_actual_frame(
        self,
    ):
        before = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], TARGET_SERIAL)
        self.assertEqual(checked.json["observations"]["frame"], [1920, 1080])
        self.assertTrue(
            any(argv[-2:] == ["details", VM_ID] for argv, _ in self.gm.calls)
        )
        self.io.frame = self.io.frame[:720, :1280]
        invalid = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertFalse(invalid.json["ok"])
        self.assertEqual(invalid.json["error"]["code"], "frame_size_mismatch")
        self.assertFalse(
            any("start" in argv or "list" in argv for argv, _ in self.gm.calls)
        )
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
