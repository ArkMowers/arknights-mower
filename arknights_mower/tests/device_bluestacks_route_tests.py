"""BlueStacks selection, endpoint refresh and repair behavior through HTTP."""

import tempfile
import unittest
from unittest.mock import patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_bluestacks_session_tests import (
    ANDROID_ID,
    OTHER,
    SERIAL,
    BlueStacksTransport,
)
from arknights_mower.utils import config
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService


class BlueStacksDeviceRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        root = self.enterContext(tempfile.TemporaryDirectory())
        self.fixture = BlueStacksTransport(root)
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

    def choose_instance(self):
        before = self.path.read_bytes()
        response = self.client.post("/device/discover", headers=self.headers, json={})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["ok"], response.json["error"])
        self.assertEqual(response.json["status"], "selection_required")
        self.assertIsNone(response.json["selected_key"])
        candidates = response.json["candidates"]
        self.assertEqual(
            {item["instance_id"] for item in candidates}, {"Nougat32", "Pie64_2"}
        )
        self.assertEqual(self.path.read_bytes(), before)
        candidate = next(
            item for item in candidates if item["instance_id"] == "Pie64_2"
        )
        self.assertEqual(candidate["serial"], "")
        self.assertEqual(candidate["binding"]["last_serial"], "")
        selected = self.client.patch(
            "/conf", headers=self.headers, json={"device": candidate["binding"]}
        )
        self.assertEqual(selected.status_code, 200)
        return candidate

    def save_verified_endpoint(self):
        before = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], SERIAL)
        self.assertEqual(checked.json["adb_path"], str(self.fixture.adb))
        self.assertEqual(checked.json["observations"]["frame"], [1920, 1080])
        self.assertEqual(self.path.read_bytes(), before)
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

    def assert_other_instances_untouched(self):
        self.assertFalse(any(OTHER in argv for argv, _ in self.fixture.calls))
        self.assertFalse(
            any("127.0.0.1:5565" in argv for argv, _ in self.fixture.calls)
        )

    def test_settings_reads_and_unauthorized_actions_do_not_discover_or_connect(self):
        before = self.path.read_bytes()
        with patch.object(
            self.fixture.discovery,
            "discover",
            wraps=self.fixture.discovery.discover,
        ) as discovery:
            for route in ("/conf", "/device/status"):
                self.assertEqual(
                    self.client.get(route, headers=self.headers).status_code, 200
                )
                self.assertEqual(self.client.get(route).status_code, 403)
            self.assertGreaterEqual(
                self.client.get("/device/discover", headers=self.headers).status_code,
                400,
            )
            for route in ("/device/discover", "/device/preflight"):
                self.assertEqual(self.client.post(route, json={}).status_code, 403)
            self.assertEqual(
                self.client.patch(
                    "/conf", json={"device": {"instance_id": "Nougat32"}}
                ).status_code,
                403,
            )
            discovery.assert_not_called()
        self.assertEqual(self.fixture.calls, [])
        self.assertEqual(self.path.read_bytes(), before)

    def test_explicit_selection_persists_keyword_and_config_before_endpoint(self):
        self.choose_instance()
        config.load_conf()
        saved = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(saved["device"]["preset_id"], "windows.bluestacks5")
        self.assertEqual(saved["device"]["instance_id"], "Pie64_2")
        self.assertEqual(saved["device"]["instance_name"], "日常号")
        self.assertEqual(saved["device"]["config_path"], str(self.fixture.config_path))
        self.assertEqual(saved["device"]["last_serial"], "")
        self.assertEqual(saved["simulator"]["index"], "Pie64_2")
        self.save_verified_endpoint()
        config.load_conf()
        saved = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(saved["device"]["last_serial"], SERIAL)
        self.assertEqual(saved["device"]["instance_id"], "Pie64_2")
        self.assertTrue(saved["device"]["game_package_confirmed"])
        self.assert_other_instances_untouched()
        self.fixture.adapter.open_verified.assert_not_called()

    def test_preflight_refreshes_saved_instance_after_its_dynamic_port_changes(self):
        self.choose_instance()
        self.save_verified_endpoint()
        current_serial = "127.0.0.1:62518"
        self.fixture.config_path.write_text(
            self.fixture.config_path.read_text(encoding="utf-8").replace(
                'status.adb_port="61342"', 'status.adb_port="62518"'
            ),
            encoding="utf-8",
        )
        # The old port and a different instance remain online. Neither is a fallback.
        self.fixture.states[current_serial] = "device"
        self.fixture.ids[current_serial] = ANDROID_ID
        self.fixture.io.targets = list(self.fixture.states.items())
        self.fixture.calls.clear()
        before = self.path.read_bytes()
        checked = self.client.post("/device/preflight", headers=self.headers, json={})
        self.assertEqual(checked.status_code, 200)
        self.assertTrue(checked.json["ok"], checked.json["error"])
        self.assertEqual(checked.json["serial"], current_serial)
        self.assertEqual(checked.json["observations"]["frame"], [1920, 1080])
        self.assertEqual(self.path.read_bytes(), before)
        config.load_conf()
        self.assertEqual(config.conf.device.instance_id, "Pie64_2")
        self.assertEqual(config.conf.device.config_path, str(self.fixture.config_path))
        self.assertEqual(config.conf.device.last_serial, SERIAL)
        self.assertFalse(any(SERIAL in argv for argv, _ in self.fixture.calls))
        self.assert_other_instances_untouched()

    def test_missing_config_requires_config_path_repair_without_changing_binding(self):
        self.choose_instance()
        self.save_verified_endpoint()
        self.fixture.config_path.unlink()
        self.fixture.calls.clear()
        before = self.path.read_bytes()
        for route in ("/device/discover", "/device/preflight"):
            with self.subTest(route=route):
                rejected = self.client.post(route, headers=self.headers, json={})
                self.assertEqual(rejected.status_code, 200)
                self.assertFalse(rejected.json["ok"])
                self.assertEqual(rejected.json["error"]["code"], "missing_config")
                self.assertEqual(rejected.json["error"]["fields"], ["config_path"])
                self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(config.conf.device.instance_id, "Pie64_2")
        self.assertEqual(config.conf.device.last_serial, SERIAL)
        self.assertEqual(self.fixture.calls, [])

    def test_absent_or_disabled_adb_switch_explains_enable_and_retry(self):
        self.choose_instance()
        self.save_verified_endpoint()
        original = self.fixture.config_path.read_text(encoding="utf-8")
        before = self.path.read_bytes()
        for replacement in ('bst.enable_adb_access="0"', ""):
            with self.subTest(switch=replacement):
                self.fixture.config_path.write_text(
                    original.replace('bst.enable_adb_access="1"', replacement),
                    encoding="utf-8",
                )
                self.fixture.calls.clear()
                rejected = self.client.post(
                    "/device/preflight", headers=self.headers, json={}
                )
                self.assertEqual(rejected.status_code, 200)
                self.assertFalse(rejected.json["ok"])
                self.assertEqual(rejected.json["error"]["code"], "adb_disabled")
                self.assertEqual(rejected.json["error"]["fields"], [])
                self.assertIn("设置", rejected.json["error"]["message"])
                self.assertIn("高级", rejected.json["error"]["message"])
                self.assertIn("重试", rejected.json["error"]["message"])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.fixture.calls, [])

    def test_stale_endpoint_rejects_mismatch_or_unreachable_without_fallback(self):
        self.choose_instance()
        self.save_verified_endpoint()
        before = self.path.read_bytes()
        for reachable, expected_code in (
            (True, "endpoint_mismatch"),
            (False, "endpoint_unreachable"),
        ):
            with self.subTest(reachable=reachable):
                self.fixture.ids[SERIAL] = "2222222222222222"
                if not reachable:
                    del self.fixture.states[SERIAL]
                self.fixture.io.targets = list(self.fixture.states.items())
                self.fixture.calls.clear()
                rejected = self.client.post(
                    "/device/preflight", headers=self.headers, json={}
                )
                self.assertEqual(rejected.status_code, 200)
                self.assertFalse(rejected.json["ok"])
                self.assertEqual(rejected.json["error"]["code"], expected_code)
                self.assertEqual(rejected.json["serial"], "")
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(config.conf.device.instance_id, "Pie64_2")
                self.assertEqual(config.conf.device.last_serial, SERIAL)
                self.assert_other_instances_untouched()
                self.fixture.adapter.open_verified.assert_not_called()


if __name__ == "__main__":
    unittest.main()
