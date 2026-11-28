"""Waydroid fixtures exercised through the device application boundary."""

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_avd_tests import AVDIO
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import ProductionSimulator
from arknights_mower.utils.device.waydroid import WaydroidController


class WaydroidTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.manager = root / "waydroid"
        self.manager.touch()
        self.manager.chmod(0o755)
        self.busctl = root / "busctl"
        self.busctl.touch()
        self.busctl.chmod(0o755)
        self.fixtures = json.loads(
            (Path(__file__).parent / "fixtures/waydroid.json").read_text(
                encoding="utf-8"
            )
        )
        self.metadata = self.fixtures["running"]["session"].copy()
        self.output = self.fixtures["running"]["status"]
        self.commands = []
        self.launches = []
        self.exit_code = None
        self.clock = Clock()
        self.on_spawn = lambda: None

        def run(argv, **kwargs):
            self.commands.append(argv)
            if argv[1:] == ["session", "stop"]:
                self.output = self.fixtures["stopped"]["status"]
                self.metadata = {}
                return subprocess.CompletedProcess(argv, 0, b"", b"")
            output = (
                json.dumps({"type": "a{ss}", "data": [self.metadata]})
                if argv[0] == str(self.busctl)
                else self.output
            )
            return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

        def spawn(argv, **kwargs):
            self.launches.append(argv)
            self.on_spawn()
            return SimpleNamespace(poll=lambda: self.exit_code)

        self.waydroid = WaydroidController(
            run=run,
            which=lambda name: str(root / name),
            uid=lambda: 1000,
            host="linux",
            data_path="/home/alice/.local/share/waydroid/data",
            spawn=spawn,
            monotonic=self.clock.monotonic,
        )
        self.io = PreflightIO()
        self.io.paths.add("verified-adb")
        self.io.installed.update({str(root), str(self.manager)})
        self.conf = Conf(device={"preset_id": "linux.waydroid"})
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.waydroid, waydroid=self.waydroid
            ),
        )

    def test_official_running_environment_is_discovered_without_adb_guess_or_save(self):
        before = self.conf.model_dump()
        result = self.control.discover()
        self.assertTrue(result.ok, result.error)
        candidate = result.candidates[0]
        self.assertEqual(result.selected_key, candidate["key"])
        self.assertEqual(candidate["state"], "running")
        self.assertEqual(candidate["serial"], "192.168.240.112:5555")
        self.assertEqual(candidate["binding"]["instance_id"], "waydroid:1000")
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(self.conf.model_dump(), before)

    def test_missing_uninitialized_stopped_and_unresolved_are_distinct(self):
        for output, code in (
            (self.fixtures["uninitialized"]["status"], "waydroid_uninitialized"),
            (self.fixtures["missing_endpoint"]["status"], "endpoint_unresolved"),
            ("unexpected output", "manager_output_invalid"),
        ):
            with self.subTest(code=code):
                self.output = output
                result = self.control.discover()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertTrue(result.error.message)
        self.output = self.fixtures["stopped"]["status"]
        self.metadata = {}
        result = self.control.discover()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.candidates[0]["state"], "stopped")
        self.assertEqual(result.candidates[0]["serial"], "")
        self.manager.unlink()
        result = self.control.discover()
        self.assertEqual(result.error.code, "missing_installation")
        self.assertEqual(result.error.fields, ["manager_path"])

    def test_bound_preflight_uses_current_official_endpoint_and_checks_data_identity(
        self,
    ):
        result = self.control.discover()
        self.conf = self.conf.updated({"device": result.candidates[0]["binding"]})
        self.conf.device.last_serial = "USB-123"
        self.io.targets = self.fixtures["multiple_targets"]["devices"]
        checked = self.control.preflight()
        self.assertTrue(checked.ok, checked.error)
        self.assertEqual(checked.serial, "192.168.240.112:5555")
        self.assertEqual(self.conf.device.config_path, self.metadata["waydroid_data"])
        self.metadata["waydroid_data"] = "/home/alice/different-account/waydroid/data"
        rejected = self.control.preflight()
        self.assertFalse(rejected.ok)
        self.assertEqual(rejected.error.code, "waydroid_binding_changed")
        self.assertEqual(rejected.serial, "")

    def test_new_session_refreshes_same_environment_and_rejects_another_user(self):
        result = self.control.discover()
        self.conf = self.conf.updated({"device": result.candidates[0]["binding"]})
        self.conf.device.last_serial = "USB-123"
        adb = ADB()
        adb.rows = [("USB-123", "device"), ("192.168.240.113:5555", "device")]
        adb.boot = "1"
        self.io.targets = adb.rows
        self.output = self.output.replace("192.168.240.112", "192.168.240.113")
        simulator = ProductionSimulator(waydroid=self.waydroid)
        control = DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=DeviceSession(
                adb, simulator, clock=Clock(), policy=RecoveryPolicy(timeout=5)
            ),
        )
        before = self.conf.model_dump()
        opened = control.start()
        self.assertTrue(opened.ok, opened.error)
        self.assertEqual(opened.serial, "192.168.240.113:5555")
        self.assertEqual(
            control.settings_status()["preflight"]["adb_path"], "verified-adb"
        )
        control.close()
        before = self.conf.model_dump()
        self.metadata["user_id"] = "1001"
        self.output = self.output.replace("alice(1000)", "bob(1001)")
        rejected = control.start()
        self.assertFalse(rejected.ok)
        self.assertEqual(rejected.error.code, "waydroid_binding_changed")
        self.assertEqual(adb.actions, [])
        self.assertEqual(self.conf.model_dump(), before)

    def test_fresh_linux_offers_waydroid_and_avd_without_preferring_either(self):
        self.conf = Conf(device={})
        control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.waydroid, waydroid=self.waydroid, avd=AVDIO()
            ),
        )
        result = control.discover()
        self.assertEqual(
            {c["preset_id"] for c in result.candidates}, {"linux.waydroid", "linux.avd"}
        )
        self.assertIsNone(result.selected_key)
        self.assertEqual(result.status, "selection_required")

    def session_control(self):
        self.adb = ADB()
        self.adb.boot = "1"
        self.adb.rows = self.fixtures["multiple_targets"]["devices"]
        self.io.targets = self.adb.rows
        self.session = DeviceSession(
            self.adb,
            ProductionSimulator(waydroid=self.waydroid),
            clock=self.clock,
            policy=RecoveryPolicy(timeout=5, local_wait=1),
        )
        return DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=self.session,
        )

    def mark_running(self):
        self.output = self.fixtures["running"]["status"]
        self.metadata = self.fixtures["running"]["session"].copy()

    def test_stopped_environment_starts_once_and_close_leaves_it_running(self):
        self.output = self.fixtures["stopped"]["status"]
        self.metadata = {}
        found = self.control.discover()
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        check = self.control.preflight()
        self.assertEqual(check.error.code, "instance_stopped")
        self.assertEqual(check.error.action, "start")
        self.assertEqual(self.launches, [])
        self.on_spawn = self.mark_running
        control = self.session_control()
        opened = control.start()
        self.assertTrue(opened.ok, opened.error)
        self.assertEqual(opened.serial, "192.168.240.112:5555")
        control.close()
        control.close()
        self.assertEqual(len(self.launches), 1)
        self.assertFalse(any("stop" in argv for argv in self.commands))
        self.assertEqual(self.session.actions, 1)

    def test_unrecoverable_transport_has_one_restart_and_a_finite_budget(self):
        found = self.control.discover()
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        self.on_spawn = self.mark_running
        control = self.session_control()
        self.adb.rows = [("USB-123", "device")]
        failed = control.start()
        self.assertFalse(failed.ok)
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(sum("stop" in argv for argv in self.commands), 1)
        self.assertEqual(set(self.adb.actions), {"192.168.240.112:5555"})
        self.assertLessEqual(self.session.actions, 3)
        self.assertLessEqual(self.clock.now, 5)

    def test_launch_exit_and_deadline_fail_without_retrying_another_target(self):
        self.output = self.fixtures["stopped"]["status"]
        self.metadata = {}
        found = self.control.discover()
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        self.exit_code = 1
        control = self.session_control()
        self.assertFalse(control.start().ok)
        self.assertEqual(len(self.launches), 1)
        self.assertEqual(self.adb.actions, [])
        self.exit_code = None
        self.on_spawn = lambda: self.clock.sleep(5)
        control = self.session_control()
        self.assertFalse(control.start().ok)
        self.assertEqual(len(self.launches), 2)
        self.assertEqual(self.adb.actions, [])

    def test_running_environment_is_not_launched_and_different_user_cannot_stop_it(
        self,
    ):
        found = self.control.discover()
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        self.assertFalse(self.waydroid.start(self.conf.device, 5))
        self.assertEqual(self.launches, [])
        self.waydroid.uid = lambda: 1001
        with self.assertRaisesRegex(ValueError, "当前用户会话"):
            self.waydroid.stop(self.conf.device, 5)
        self.assertFalse(any("stop" in argv for argv in self.commands))

    def test_ambiguous_and_missing_ip_never_fall_back_to_any_online_device(self):
        found = self.control.discover()
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        self.io.targets = self.fixtures["multiple_targets"]["devices"]
        self.output = self.fixtures["ambiguous_endpoint"]["status"]
        result = self.control.preflight()
        self.assertEqual(result.error.code, "endpoint_ambiguous")
        self.assertEqual(result.error.action, "select")
        self.assertEqual(result.error.fields, ["last_serial"])
        self.conf.device.last_serial = "192.168.240.112:5555"
        self.assertTrue(self.control.preflight().ok)
        self.output = self.fixtures["missing_endpoint"]["status"]
        rejected = self.control.preflight()
        self.assertFalse(rejected.ok)
        self.assertEqual(rejected.error.code, "endpoint_unresolved")
        self.assertEqual(rejected.serial, "")

    def test_starting_container_waits_without_using_stale_endpoint_or_restarting(self):
        found = self.control.discover()
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        self.output = self.output.replace("Container:\tRUNNING", "Container:\tSTOPPED")
        self.metadata["state"] = "STOPPED"
        self.assertEqual(self.control.preflight().status, "booting")
        control = self.session_control()
        original_sleep = self.clock.sleep

        def sleep(seconds):
            original_sleep(seconds)
            if self.clock.now >= 1:
                self.mark_running()

        self.clock.sleep = sleep
        ready = control.start()
        self.assertTrue(ready.ok, ready.error)
        self.assertEqual(ready.serial, "192.168.240.112:5555")
        self.assertEqual(self.launches, [])
        self.assertEqual(self.adb.actions, [])
        self.assertFalse(any("stop" in argv for argv in self.commands))

    def test_launched_environment_waits_for_its_official_ip_within_startup_deadline(
        self,
    ):
        for obtains_ip in (True, False):
            with self.subTest(obtains_ip=obtains_ip):
                self.output = self.fixtures["stopped"]["status"]
                self.metadata = {}
                self.clock.now = 0
                self.launches.clear()
                found = self.control.discover()
                self.conf = self.conf.updated(
                    {"device": found.candidates[0]["binding"]}
                )
                self.conf.device.last_serial = "USB-123"

                def launching():
                    self.mark_running()
                    self.output = self.fixtures["missing_endpoint"]["status"]

                def sleep(seconds):
                    self.clock.now += seconds
                    if obtains_ip and self.clock.now >= 1:
                        self.mark_running()

                self.on_spawn = launching
                self.clock.sleep = sleep
                control = self.session_control()
                result = control.start()
                self.assertEqual(result.ok, obtains_ip, result.error)
                self.assertEqual(self.clock.now, 1 if obtains_ip else 5)
                self.assertEqual(len(self.launches), 1)
                self.assertEqual(self.adb.actions, [])
                self.assertFalse(any("stop" in argv for argv in self.commands))
                if obtains_ip:
                    self.assertEqual(result.serial, "192.168.240.112:5555")
                else:
                    self.assertEqual(result.error.code, "recovery_exhausted")
                    self.assertEqual(result.readiness.serial, "")
                control.close()


if __name__ == "__main__":
    unittest.main()
