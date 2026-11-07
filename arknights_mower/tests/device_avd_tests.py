"""AVD selection, consent and lifecycle at the device application seam."""

import tempfile
import unittest
from pathlib import Path

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_avd_io_tests import SDKFixture
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.bluestacks_air import BlueStacksAirDiscovery
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import (
    DeviceSession,
    InstanceObservation,
    RecoveryPolicy,
)


class AVDIO:
    def __init__(self):
        self.names = ["Mower_API_35"]
        self.state = "stopped"
        self.serial = ""
        self.launches = []
        self.stops = []
        self.on_start = lambda: None

    def inspect(self, profile, timeout):
        return InstanceObservation(self.state, self.serial or None)

    def start_confirmed(self, profile, timeout):
        self.launches.append(profile.instance_id)
        self.on_start()
        return True

    def stop_owned(self, profile, timeout):
        self.stops.append(profile.instance_id)
        return True

    def discover(self, profile, host):
        return {
            "installations": [
                {
                    "preset_id": f"{host}.avd",
                    "installation_path": "/sdk",
                    "manager_path": "/sdk/emulator/emulator",
                    "instances": [
                        {
                            "instance_id": name,
                            "instance_name": name,
                            "state": "unknown",
                            "serial": "",
                        }
                        for name in self.names
                    ],
                }
            ],
            "errors": [],
        }


class AVDTests(unittest.TestCase):
    def setUp(self):
        self.io = PreflightIO()
        self.avd = AVDIO()
        self.conf = Conf(device={"preset_id": "linux.avd", "last_serial": ""})
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(DiscoveryIO(), avd=self.avd),
        )

    def test_one_avd_is_selected_without_launching_or_persisting(self):
        before = self.conf.model_dump()
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["key"], result["selected_key"])
        self.assertEqual(candidate["binding"]["instance_id"], "Mower_API_35")
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(self.conf.model_dump(), before)

    def test_multiple_avds_require_selection_and_empty_list_explains_creation(self):
        self.avd.names.append("Personal_API_35")
        result = self.control.discover().to_dict()
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["status"], "selection_required")
        self.avd.names.clear()
        result = self.control.discover().to_dict()
        self.assertEqual(result["error"]["code"], "no_avd")

    def test_fresh_macos_discovers_avd_when_air_is_not_installed(self):
        self.io.host = "macos"
        self.conf.device.preset_id = "manual.other"
        result = self.control.discover().to_dict()
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["candidates"][0]["preset_id"], "macos.avd")

    def test_fresh_macos_missing_sdk_can_be_repaired_using_returned_fields(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        sdk = SDKFixture(root)
        self.io.host = "macos"
        self.conf = Conf(device={})
        control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(DiscoveryIO(), avd=sdk.controller()),
        )
        before = self.conf.model_dump()
        failed = control.discover()
        self.assertEqual(failed.error.code, "missing_sdk")
        for repair in (
            {"installation_path": str(sdk.manager.parent.parent)},
            {"manager_path": str(sdk.manager)},
        ):
            with self.subTest(repair=repair):
                result = control.discover(self.conf.updated({"device": repair}))
                self.assertTrue(result.ok, result.error)
                self.assertEqual(
                    result.candidates[0]["binding"]["manager_path"], str(sdk.manager)
                )
        self.assertEqual(self.conf.model_dump(), before)

    def test_air_and_avd_together_require_product_selection(self):
        self.io.host = "macos"
        self.conf.device.preset_id = "manual.other"
        app = Path(self.enterContext(tempfile.TemporaryDirectory())) / "BlueStacks.app"
        (app / "Contents/MacOS").mkdir(parents=True)
        (app / "Contents/Info.plist").write_bytes(b"fixture")
        self.io.installed.add(str(app))
        self.io.targets = [("127.0.0.1:5555", "device")]
        control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(),
                avd=self.avd,
                air=BlueStacksAirDiscovery(application_paths=[app]),
            ),
        )
        result = control.discover().to_dict()
        self.assertEqual(len(result["candidates"]), 2)
        self.assertIsNone(result["selected_key"])

    def test_unconfirmed_or_wrong_instance_never_launches(self):
        self.conf.device.instance_id = "Mower_API_35"
        for confirmation in (None, "", "Personal_API_35"):
            with self.subTest(confirmation=confirmation):
                result = self.control.start_avd(confirmed_instance=confirmation)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, "start_confirmation_required")
        self.assertEqual(self.avd.launches, [])

    def session_control(self):
        self.clock, self.adb = Clock(), ADB()
        self.adb.rows = [("emulator-5554", "device"), ("emulator-5580", "device")]
        self.adb.boot = "1"
        self.io.targets = self.adb.rows
        self.conf.device.instance_id = "Mower_API_35"
        self.conf.device.last_serial = "emulator-5554"
        self.control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            avd=self.avd,
            discovery=DiscoveryService(DiscoveryIO(), self.avd, avd=self.avd),
            session=DeviceSession(
                self.adb,
                self.avd,
                clock=self.clock,
                policy=RecoveryPolicy(timeout=5, poll_interval=1),
            ),
        )

    def test_detection_of_stopped_avd_requires_confirmation_without_launch(self):
        self.session_control()
        result = self.control.preflight()
        self.assertEqual(result.error.code, "start_confirmation_required")
        self.assertEqual(self.avd.launches, [])
        result = self.control.start()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "start_confirmation_required")
        self.assertEqual(self.avd.launches, [])

    def test_confirmed_launch_preflights_dynamic_target_and_close_leaves_it_running(
        self,
    ):
        self.session_control()

        def launched():
            self.avd.state = "running"
            self.avd.serial = "emulator-5580"

        self.avd.on_start = launched
        before = self.conf.model_dump()
        result = self.control.start_avd(confirmed_instance="Mower_API_35")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "emulator-5580")
        self.assertEqual(result.adb_path, "product-adb")
        self.assertEqual(result.observations["frame"], [1920, 1080])
        self.assertEqual(self.conf.model_dump(), before)
        self.control.close()
        self.control.close()
        self.assertEqual(self.avd.stops, [])
        self.assertFalse(self.control.stop_owned_avd())
        self.conf.close_simulator_when_idle = True
        self.assertTrue(self.control.stop_owned_avd())
        self.assertEqual(self.avd.stops, ["Mower_API_35"])

    def test_missing_adb_is_repairable_and_does_not_launch(self):
        self.session_control()
        self.io.paths.clear()
        result = self.control.start_avd(confirmed_instance="Mower_API_35")
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "missing_adb")
        self.assertEqual(result.error.fields, ["adb_path"])
        self.assertEqual(self.avd.launches, [])

    def test_startup_wait_expires_without_restarting_or_using_stale_serial(self):
        self.session_control()

        def launched():
            self.avd.state = "starting"

        self.avd.on_start = launched
        result = self.control.start_avd(confirmed_instance="Mower_API_35")
        self.assertFalse(result.ok)
        self.assertEqual(result.serial, "")
        self.assertEqual(self.clock.now, 5)
        self.assertEqual(self.avd.launches, ["Mower_API_35"])
        self.assertEqual(self.avd.stops, [])
        self.assertEqual(self.adb.actions, [])


if __name__ == "__main__":
    unittest.main()
