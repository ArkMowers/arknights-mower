"""MuMu Pro discovery and selected-instance preflight through HTTP."""

import json
import subprocess
import unittest
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
from arknights_mower.utils.device.session_io import ProductionSimulator

MUMU_PRESET = "macos.mumu_pro"
OLD_SERIAL = "127.0.0.1:16384"
MANUAL_SERIAL = "127.0.0.1:16416"


class MuMuProRouteTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        config.conf = config.Conf(
            device={
                "preset_id": MUMU_PRESET,
                "instance_id": "0",
                "instance_name": "Previously saved instance",
                "last_serial": OLD_SERIAL,
            }
        )
        config.save_conf()
        # A valid Air installation makes accidental product fallback observable.
        air = self.path.parent / "BlueStacks.app"
        (air / "Contents/MacOS").mkdir(parents=True)
        (air / "Contents/Info.plist").write_text("", encoding="utf-8")
        self.io = PreflightIO()
        self.io.host = "macos"
        self.io.installed.add(str(air))
        self.io.targets = [(OLD_SERIAL, "device")]
        self.sources = DiscoveryIO()
        self.control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                self.sources,
                air=BlueStacksAirDiscovery(application_paths=[air]),
            ),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)

    def post_device(self, route, device=None):
        response = self.client.post(
            route,
            headers=self.headers,
            json={} if device is None else {"device": device},
        )
        self.assertEqual(response.status_code, 200)
        return response.json

    def assert_manual_required(self, result):
        self.assertFalse(result["ok"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "mumu_pro_manual_required")
        self.assertEqual(result["error"]["action"], "manual")

    def test_explicit_mumu_discovery_requires_manual_without_air_or_save(self):
        before = self.path.read_bytes()
        result = self.post_device("/device/discover", {"preset_id": MUMU_PRESET})
        self.assert_manual_required(result)
        self.assertEqual(result["kind"], "discovery")
        self.assertIsNone(result["selected_key"])
        self.assertNotIn("profile_patch", result)
        loaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(loaded["device"]["preset_id"], MUMU_PRESET)
        self.assertEqual(loaded["device"]["last_serial"], OLD_SERIAL)
        self.assertEqual(self.path.read_bytes(), before)

    def test_discovered_multi_instance_selection_rechecks_same_instance(self):
        manager = self.path.parent / "MuMuPlayer.app/Contents/MacOS/mumutool"
        manager.parent.mkdir(parents=True)
        manager.write_bytes(b"stub")
        manager.chmod(0o755)
        rows = [
            {
                "index": index,
                "name": f"VM {index}",
                "bundle_path": str(self.path.parent / f"vms/{index}"),
                "state": "running",
                "adb_port": port,
            }
            for index, port in ((0, 16384), (1, 16416))
        ]

        def run(argv, **_kwargs):
            selected = argv[-1] != "all"
            chosen = next((row for row in rows if str(row["index"]) == argv[-1]), None)
            payload = chosen if selected else {"count": len(rows), "results": rows}
            response = {"errcode": 0, "message": "", "return": payload}
            return subprocess.CompletedProcess(argv, 0, json.dumps(response).encode(), b"")

        simulator = ProductionSimulator(run=run)
        self.control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(self.sources, simulator),
        )
        self.main.device_control = self.control
        self.addCleanup(self.control.close)
        self.io.targets = [(OLD_SERIAL, "device"), (MANUAL_SERIAL, "device")]
        before = self.path.read_bytes()
        discovered = self.post_device("/device/discover", {"manager_path": str(manager)})
        self.assertTrue(discovered["ok"], discovered["error"])
        self.assertEqual(discovered["status"], "selection_required")
        self.assertEqual(len(discovered["candidates"]), 2)
        self.assertIsNone(discovered["selected_key"])
        selected = next(
            candidate for candidate in discovered["candidates"] if candidate["instance_id"] == "1"
        )
        checked = self.post_device("/device/preflight", selected["binding"])
        self.assertTrue(checked["ok"], checked["error"])
        self.assertEqual(checked["serial"], MANUAL_SERIAL)
        self.assertEqual(self.path.read_bytes(), before)

        rows[1]["bundle_path"] = str(self.path.parent / "recreated/1")
        original_devices = self.io.devices
        with patch.object(self.io, "devices", side_effect=original_devices) as devices:
            rejected = self.post_device("/device/preflight", selected["binding"])
            self.assertFalse(rejected["ok"])
            self.assertEqual(rejected["error"]["code"], "mumu_pro_binding_changed")
            devices.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)

    def test_preflight_checks_saved_and_draft_serial_without_persisting(self):
        before = self.path.read_bytes()
        original_devices = self.io.devices
        with patch.object(self.io, "devices", side_effect=original_devices) as devices:
            checked = self.post_device("/device/preflight")
            self.assertTrue(checked["ok"], checked["error"])
            self.assertEqual(checked["serial"], OLD_SERIAL)
            devices.assert_called_once_with("product-adb", OLD_SERIAL)
            self.io.targets = [(MANUAL_SERIAL, "device"), ("USB-123", "device")]
            drafted = self.post_device(
                "/device/preflight", {"last_serial": MANUAL_SERIAL}
            )
            self.assertTrue(drafted["ok"], drafted["error"])
            self.assertEqual(drafted["serial"], MANUAL_SERIAL)
            self.assertEqual(
                devices.call_args_list[-1].args, ("product-adb", MANUAL_SERIAL)
            )
        self.assertEqual(config.conf.device.last_serial, OLD_SERIAL)
        self.assertEqual(self.path.read_bytes(), before)

    def test_settings_reads_and_unauthorized_actions_do_not_discover_or_probe(self):
        before = self.path.read_bytes()
        with patch.object(
            self.io, "devices", side_effect=AssertionError("settings ADB probe")
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

    def test_verified_serial_saves_without_changing_mumu_pro_preset(self):
        self.io.targets = [(MANUAL_SERIAL, "device"), ("USB-123", "device")]
        checked = self.post_device("/device/preflight", {"last_serial": MANUAL_SERIAL})
        self.assertTrue(checked["ok"], checked["error"])
        saved = self.client.patch(
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
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["preset_id"], MUMU_PRESET)
        self.assertEqual(saved.json["device"]["last_serial"], MANUAL_SERIAL)
        config.load_conf()
        self.assertTrue(self.post_device("/device/preflight")["ok"])

    def test_explicit_manual_fallback_clears_binding_and_saves_verified_target(self):
        fallback = self.client.patch(
            "/conf",
            headers=self.headers,
            json={
                "device": {
                    "preset_id": "manual.other",
                    "installation_path": "",
                    "manager_path": "",
                    "instance_id": "",
                    "instance_name": "",
                    "last_serial": "",
                    "game_package_confirmed": False,
                }
            },
        )
        self.assertEqual(fallback.status_code, 200)
        for field in (
            "installation_path",
            "manager_path",
            "instance_id",
            "last_serial",
        ):
            self.assertEqual(fallback.json["device"][field], "")
        self.assertEqual(fallback.json["device"]["preset_id"], "manual.other")
        self.assertEqual(fallback.json["adb"], "")
        self.io.targets = [(MANUAL_SERIAL, "device")]
        missing = self.post_device("/device/preflight")
        self.assertFalse(missing["ok"])
        self.assertEqual(missing["error"]["code"], "target_required")
        before = self.path.read_bytes()
        checked = self.post_device("/device/preflight", {"last_serial": MANUAL_SERIAL})
        self.assertTrue(checked["ok"], checked["error"])
        self.assertEqual(checked["serial"], MANUAL_SERIAL)
        self.assertEqual(checked["observations"]["effective"], [1920, 1080])
        self.assertEqual(checked["observations"]["frame"], [1920, 1080])
        self.assertEqual(self.path.read_bytes(), before)
        saved = self.client.patch(
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
        self.assertEqual(saved.status_code, 200)
        config.load_conf()
        loaded = self.client.get("/conf", headers=self.headers).json
        self.assertEqual(loaded["device"]["preset_id"], "manual.other")
        self.assertEqual(loaded["device"]["instance_id"], "")
        self.assertEqual(loaded["device"]["last_serial"], MANUAL_SERIAL)
        self.assertTrue(loaded["device"]["game_package_confirmed"])
        self.assertTrue(self.post_device("/device/preflight")["ok"])

    def test_manual_draft_can_reselect_same_serial_before_saving_new_binding(self):
        # The UI edits a draft, then preflights it before persisting anything.
        draft = {
            "preset_id": "manual.other",
            "installation_path": "",
            "manager_path": "",
            "instance_id": "",
            "instance_name": "",
            "last_serial": OLD_SERIAL,
            "game_package_confirmed": False,
        }
        before = self.path.read_bytes()
        checked = self.post_device("/device/preflight", draft)
        self.assertTrue(checked["ok"], checked["error"])
        self.assertEqual(checked["serial"], OLD_SERIAL)
        self.assertEqual(checked["observations"]["frame"], [1920, 1080])
        self.assertEqual(config.conf.device.preset_id, MUMU_PRESET)
        self.assertEqual(self.path.read_bytes(), before)
        # Only the action can use the explicit choice; changing the persisted
        # binding still clears it until the verified endpoint is saved next.
        saved = self.client.patch("/conf", headers=self.headers, json={"device": draft})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json["device"]["last_serial"], "")
        endpoint = self.client.patch(
            "/conf",
            headers=self.headers,
            json={"device": {"last_serial": checked["serial"]}},
        )
        self.assertEqual(endpoint.status_code, 200)
        self.assertEqual(endpoint.json["device"]["last_serial"], OLD_SERIAL)


if __name__ == "__main__":
    unittest.main()
