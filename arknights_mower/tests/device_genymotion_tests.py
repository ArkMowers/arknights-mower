"""Official gmtool protocol fixtures at the device-control application seam."""

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_avd_tests import AVDIO
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.genymotion import GenymotionController
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import ProductionSimulator

VM_ID = "b54fe1d2-0e30-42e6-b62b-94b3596088b9"
OTHER_ID = "cae763ad-620a-4692-b959-84bbe4974534"


class GenymotionFixture:
    def __init__(self, root):
        self.manager = root / "gmtool"
        self.manager.touch()
        self.manager.chmod(0o755)
        self.fixtures = json.loads(
            (Path(__file__).parent / "fixtures/genymotion.json").read_text(
                encoding="utf-8"
            )
        )
        self.listing = deepcopy(self.fixtures["list"])
        self.details = self.fixtures["details"]
        self.version = self.fixtures["version"]
        self.responses = {}
        self.calls = []
        self.on_start = lambda: None
        self.clock = Clock()
        self.controller = GenymotionController(
            run=self.run,
            which=lambda name: str(self.manager),
            host="linux",
            monotonic=self.clock.monotonic,
        )

    def run(self, argv, **options):
        self.calls.append((argv, options))
        stage = next(
            name for name in ("version", "list", "details", "start") if name in argv
        )
        response = self.responses.get(stage)
        if isinstance(response, BaseException):
            raise response
        if response is not None:
            return response
        if stage == "start":
            self.on_start()
            output = ""
        else:
            output = {
                "version": self.version,
                "list": json.dumps(self.listing),
                "details": self.details,
            }[stage]
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")


class GenymotionTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.gm = GenymotionFixture(root)
        self.io = PreflightIO()
        self.io.paths.add("verified-adb")
        self.io.installed.update({str(root), str(self.gm.manager)})
        self.io.targets = [("USB-123", "device"), ("127.0.0.1:6555", "device")]
        self.conf = Conf(device={"preset_id": "linux.genymotion"})
        self.simulator = ProductionSimulator(genymotion=self.gm.controller)
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.simulator, genymotion=self.gm.controller
            ),
        )

    def bind(self):
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        return found.candidates[0]

    def test_one_official_vm_selects_uuid_without_saving_endpoint_or_launching(self):
        before = self.conf.model_dump()
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        candidate = found.candidates[0]
        self.assertEqual(found.selected_key, candidate["key"])
        self.assertEqual(candidate["instance_id"], VM_ID)
        self.assertEqual(candidate["instance_name"], "Mower Linux VM")
        self.assertEqual(candidate["serial"], "127.0.0.1:6555")
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(self.conf.model_dump(), before)
        self.assertFalse(any("start" in argv for argv, _ in self.gm.calls))

    def test_preflight_refreshes_selected_uuid_only_and_checks_current_frame(self):
        self.bind()
        self.conf.device.last_serial = "USB-123"
        self.gm.details = self.gm.details.replace(":6555", ":7555")
        self.io.targets.append(("127.0.0.1:7555", "device"))
        self.gm.calls.clear()
        before = self.conf.model_dump()
        result = self.control.preflight()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:7555")
        self.assertEqual(result.observations["frame"], [1920, 1080])
        self.assertEqual(result.observations["effective"], [1920, 1080])
        self.assertEqual(self.conf.model_dump(), before)
        self.assertFalse(any("list" in argv for argv, _ in self.gm.calls))
        self.assertTrue(
            any(argv[-2:] == ["details", VM_ID] for argv, _ in self.gm.calls)
        )
        # The reported size is diagnostic; only the decoded frame is gated.
        self.io.size = "Physical size: 1280x720"
        self.assertEqual(self.control.preflight().error, None)
        self.io.frame = np.zeros((720, 1280, 3), np.uint8)
        self.assertEqual(self.control.preflight().error.code, "frame_size_mismatch")

    def test_launch_is_confirmed_once_and_verified_against_the_same_vm(self):
        self.bind()
        self.gm.details = self.gm.fixtures["stopped_details"]
        adb = ADB()
        adb.rows, adb.boot = self.io.targets, "1"
        control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=DeviceSession(
                adb,
                self.simulator,
                clock=self.gm.clock,
                policy=RecoveryPolicy(timeout=5, poll_interval=1),
            ),
            genymotion=self.gm.controller,
        )
        self.addCleanup(control.close)
        rejected = control.start()
        self.assertEqual(rejected.error.code, "start_confirmation_required")
        self.assertFalse(any("start" in argv for argv, _ in self.gm.calls))
        self.gm.on_start = lambda: setattr(
            self.gm, "details", self.gm.fixtures["details"]
        )
        before = self.conf.model_dump()
        launched = control.start_genymotion(confirmed_instance=VM_ID)
        self.assertTrue(launched.ok, launched.error)
        self.assertEqual(launched.serial, "127.0.0.1:6555")
        self.assertEqual(launched.observations["frame"], [1920, 1080])
        self.assertEqual(
            [argv[-1] for argv, _ in self.gm.calls if "start" in argv], [VM_ID]
        )
        self.assertEqual(self.conf.model_dump(), before)
        self.gm.details = self.gm.fixtures["stopped_details"]
        self.assertEqual(control.start().error.code, "start_confirmation_required")
        self.assertEqual(sum("start" in argv for argv, _ in self.gm.calls), 1)

    def test_multiple_vms_require_selection_even_with_the_same_display_name(self):
        self.gm.listing["instances"].append(
            {**self.gm.listing["instances"][0], "uuid": OTHER_ID, "state": "off"}
        )
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.assertEqual(found.status, "selection_required")
        self.assertIsNone(found.selected_key)
        self.assertEqual(len({item["key"] for item in found.candidates}), 2)
        stopped = found.candidates[1]
        self.assertEqual(stopped["serial"], "")
        self.assertEqual(stopped["state"], "stopped")

    def test_fresh_linux_discovery_combines_genymotion_and_primary_products(self):
        self.conf = Conf(device={})
        control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(),
                self.simulator,
                avd=AVDIO(),
                genymotion=self.gm.controller,
            ),
        )
        result = control.discover()
        self.assertTrue(result.ok, result.error)
        self.assertIsNone(result.selected_key)
        self.assertEqual(
            {row["preset_id"] for row in result.candidates},
            {"linux.avd", "linux.genymotion"},
        )

    def session_control(self, adb):
        control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=DeviceSession(
                adb,
                self.simulator,
                clock=self.gm.clock,
                policy=RecoveryPolicy(timeout=5, poll_interval=1),
            ),
            genymotion=self.gm.controller,
        )
        self.addCleanup(control.close)
        return control

    def test_new_session_refreshes_uuid_and_never_adopts_old_or_other_online_vm(self):
        self.bind()
        self.conf.device.last_serial = "USB-123"
        self.gm.details = self.gm.details.replace(":6555", ":7555")
        self.io.targets.append(("127.0.0.1:7555", "device"))
        adb = ADB()
        adb.rows, adb.boot = self.io.targets, "1"
        self.gm.calls.clear()
        ready = self.session_control(adb).start()
        self.assertTrue(ready.ok, ready.error)
        self.assertEqual(ready.value.device_id, "127.0.0.1:7555")
        self.assertFalse(any("list" in argv for argv, _ in self.gm.calls))
        # Even an online saved endpoint does not authorize a replacement VM.
        self.gm.details = self.gm.details.replace(VM_ID, OTHER_ID)
        failed = self.session_control(adb).start()
        self.assertFalse(failed.ok)
        self.assertEqual(failed.error.code, "genymotion_binding_changed")
        self.assertEqual(failed.readiness.serial, "")
        self.assertEqual(adb.actions, [])

    def test_absent_selected_adb_has_finite_wait_without_restart_or_other_target(self):
        self.bind()
        adb = ADB()
        adb.rows, adb.boot = [("USB-123", "device")], "1"
        before = self.conf.model_dump()
        failed = self.session_control(adb).start()
        self.assertFalse(failed.ok)
        self.assertEqual(self.gm.clock.now, 5)
        self.assertEqual(adb.actions, ["127.0.0.1:6555"])
        self.assertFalse(
            any(set(argv) & {"start", "stop", "restart"} for argv, _ in self.gm.calls)
        )
        self.assertEqual(self.conf.model_dump(), before)

    def test_running_vm_still_requires_boot_actual_frame_and_package_preflight(self):
        self.bind()
        for value, expected in (("0", "boot_incomplete"), ("1", None)):
            self.io.boot = value
            result = self.control.preflight()
            self.assertEqual(result.error.code if result.error else None, expected)
        self.io.frame = self.io.frame[:720, :1280]
        self.assertEqual(self.control.preflight().error.code, "frame_size_mismatch")


if __name__ == "__main__":
    unittest.main()
