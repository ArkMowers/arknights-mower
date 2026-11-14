"""Nox discovery, binding persistence and topology repair through HTTP."""

import tempfile
import unittest

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_nox_session_tests import NoxTransport
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService

VM_UUID = "5e1aaadc-7991-419d-a2b6-f030b497b282"
REPLACEMENT_UUID = "591bde10-1227-4d43-aeb2-c97247c5b1c3"
SERIAL = "127.0.0.1:62125"


class NoxDeviceRouteTests(unittest.TestCase):
    def setUp(self):
        # Reuse the HTTP environment without inheriting unrelated test cases.
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.fixture = NoxTransport(root)
        self.addCleanup(self.fixture.control.close)
        self.control = DeviceControl(
            lambda: config.conf,
            self.fixture.adapter,
            preflight=PreflightService(self.fixture.io),
            discovery=self.fixture.discovery,
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)
        config.conf = config.conf.updated(
            {"device": {"adb_path": str(self.fixture.adb)}}
        )
        config.save_conf()

    def choose_discovered_vm(self):
        response = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"], response.json["error"])
        self.assertEqual(len(response.json["candidates"]), 1)
        candidate = response.json["candidates"][0]
        selected = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(selected.status_code, 200)
        return candidate

    def test_settings_reads_and_unauthorized_actions_never_probe_nox(self):
        before = self.path.read_bytes()
        for route in ("/conf", "/device/status"):
            self.assertEqual(
                self.client.get(route, headers=self.headers).status_code, 200
            )
        self.assertGreaterEqual(
            self.client.get("/device/discover", headers=self.headers).status_code,
            400,
        )
        for route in ("/device/discover", "/device/preflight"):
            self.assertEqual(self.client.post(route, json={}).status_code, 403)
        self.assertEqual(self.fixture.calls, [])
        self.assertEqual(self.path.read_bytes(), before)
        response = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"], response.json["error"])
        self.assertTrue(self.fixture.calls)
        self.assertEqual(self.path.read_bytes(), before)

    def test_chosen_vm_persists_identity_then_saves_only_its_verified_endpoint(self):
        candidate = self.choose_discovered_vm()
        config.load_conf()
        saved = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(saved["device"]["preset_id"], "windows.nox")
        self.assertEqual(saved["device"]["instance_id"], "Nox_2")
        self.assertEqual(saved["device"]["instance_name"], "日常号")
        self.assertEqual(saved["device"]["instance_uuid"], VM_UUID)
        self.assertEqual(
            saved["device"]["topology_fingerprint"],
            candidate["binding"]["topology_fingerprint"],
        )
        self.assertEqual(len(saved["device"]["topology_fingerprint"]), 64)
        self.assertEqual(saved["device"]["last_serial"], "")
        self.assertEqual(saved["simulator"]["index"], "Nox_2")
        binding_saved = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], SERIAL)
        self.assertEqual(checked.json["adb_path"], str(self.fixture.adb))
        self.assertEqual(checked.json["observations"]["frame"], [1920, 1080])
        self.assertEqual(self.path.read_bytes(), binding_saved)
        self.assertEqual(config.conf.device.last_serial, "")
        self.assertEqual(self.fixture.lifecycle, [])
        accepted = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": checked.json["serial"],
                    "adb_path": checked.json["adb_path"],
                    "game_package": checked.json["game_package"],
                    "game_package_confirmed": True,
                }
            },
        )
        self.assertEqual(accepted.status_code, 200)
        config.load_conf()
        reloaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(reloaded["device"]["last_serial"], SERIAL)
        self.assertEqual(reloaded["device"]["instance_uuid"], VM_UUID)
        self.assertTrue(reloaded["device"]["game_package_confirmed"])
        self.assertFalse(
            any("127.0.0.1:62001" in argv for argv, _ in self.fixture.calls)
        )

    def test_recreated_vm_rejects_old_endpoint_and_requires_explicit_reselection(self):
        chosen = self.choose_discovered_vm()
        accepted = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "last_serial": SERIAL,
                    "game_package": "com.hypergryph.arknights.bilibili",
                    "game_package_confirmed": True,
                }
            },
        )
        self.assertEqual(accepted.status_code, 200)
        before = self.path.read_bytes()
        self.fixture.vm.write_text(
            self.fixture.vm.read_text(encoding="utf-8").replace(
                VM_UUID, REPLACEMENT_UUID
            ),
            encoding="utf-8",
        )
        self.fixture.calls.clear()
        rejected = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(rejected.status_code, 200)
        self.assertFalse(rejected.json["ok"])
        self.assertEqual(rejected.json["error"]["code"], "topology_changed")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(config.conf.device.instance_uuid, VM_UUID)
        self.assertEqual(config.conf.device.last_serial, SERIAL)
        self.assertFalse(any(SERIAL in argv for argv, _ in self.fixture.calls))
        self.assertFalse(
            any("127.0.0.1:62001" in argv for argv, _ in self.fixture.calls)
        )
        self.assertEqual(self.fixture.lifecycle, [])

        discovered = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(discovered.status_code, 200)
        self.assertEqual(len(discovered.json["candidates"]), 1)
        self.assertIsNone(discovered.json["selected_key"])
        self.assertEqual(discovered.json["status"], "selection_required")
        self.assertEqual(discovered.json["error"]["code"], "topology_changed")
        self.assertEqual(discovered.json["error"]["action"], "select")
        self.assertEqual(self.path.read_bytes(), before)
        replacement = discovered.json["candidates"][0]
        self.assertEqual(replacement["instance_id"], "Nox_2")
        self.assertEqual(replacement["instance_uuid"], REPLACEMENT_UUID)
        self.assertNotEqual(
            replacement["topology_fingerprint"], chosen["topology_fingerprint"]
        )
        selected = self.client.patch(
            "/conf", headers=self.headers, json={"device": replacement["binding"]}
        )
        self.assertEqual(selected.status_code, 200)
        config.load_conf()
        self.assertEqual(config.conf.device.instance_uuid, REPLACEMENT_UUID)
        self.assertEqual(config.conf.device.last_serial, "")
        self.assertFalse(config.conf.device.game_package_confirmed)


if __name__ == "__main__":
    unittest.main()
