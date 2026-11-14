"""Local Docker fixtures through the device-control application boundary."""

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_avd_tests import AVDIO
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.redroid import RedroidController
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import ProductionSimulator


class DockerFixture:
    def __init__(self, root):
        self.manager = root / "docker"
        self.manager.touch()
        self.manager.chmod(0o755)
        self.fixtures = json.loads(
            (Path(__file__).parent / "fixtures/redroid.json").read_text(
                encoding="utf-8"
            )
        )
        self.rows = [deepcopy(self.fixtures["running"])]
        self.server = self.fixtures["server"]
        self.calls = []
        self.inspect_output = None
        self.failure = None
        self.on_start = lambda: None
        self.clock = Clock()
        self.controller = RedroidController(
            run=self.run,
            which=lambda name: str(self.manager),
            host="linux",
            monotonic=self.clock.monotonic,
        )

    def run(self, argv, **options):
        self.calls.append((argv, options))
        if self.failure:
            raise self.failure
        if "version" in argv:
            output = json.dumps(self.server)
        elif "ls" in argv:
            output = "\n".join(row["Id"] for row in self.rows)
        elif "inspect" in argv:
            requested = argv[argv.index("inspect") + 1 :]
            output = (
                self.inspect_output
                if self.inspect_output is not None
                else json.dumps([row for row in self.rows if row["Id"] in requested])
            )
        elif "start" in argv:
            self.on_start()
            output = argv[-1]
        else:
            raise AssertionError(f"Unexpected Docker operation: {argv}")
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")


class RedroidTests(unittest.TestCase):
    def setUp(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.docker = DockerFixture(root)
        self.io = PreflightIO()
        self.io.installed.update({str(root), str(self.docker.manager)})
        self.io.paths.add("verified-adb")
        self.io.targets = [("USB-123", "device"), ("127.0.0.1:15555", "device")]
        self.conf = Conf(device={"preset_id": "linux.redroid"})
        self.control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(), self.docker.controller, redroid=self.docker.controller
            ),
        )

    def test_missing_docker_returns_only_manager_repair_without_saving(self):
        self.docker.manager.unlink()
        before = self.conf.model_dump()
        result = self.control.discover()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "missing_installation")
        self.assertEqual(result.error.fields, ["manager_path"])
        self.assertEqual(result.candidates, [])
        self.assertEqual(self.docker.calls, [])
        self.assertEqual(self.conf.model_dump(), before)

    def test_official_images_only_one_auto_binding_uses_id_not_endpoint(self):
        self.docker.rows.append(deepcopy(self.docker.fixtures["custom"]))
        before = self.conf.model_dump()
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.assertEqual(len(found.candidates), 1)
        candidate = found.candidates[0]
        self.assertEqual(found.selected_key, candidate["key"])
        self.assertEqual(candidate["instance_id"], "a" * 64)
        self.assertEqual(candidate["instance_name"], "redroid-main")
        self.assertEqual(candidate["serial"], "127.0.0.1:15555")
        self.assertEqual(
            candidate["binding"]["config_path"], "unix:///var/run/docker.sock"
        )
        self.assertEqual(candidate["binding"]["last_serial"], "")
        self.assertEqual(self.conf.model_dump(), before)

    def bind(self):
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.conf = self.conf.updated({"device": found.candidates[0]["binding"]})
        return found.candidates[0]

    def test_selected_container_refreshes_port_and_ignores_old_online_target(self):
        self.bind()
        self.conf.device.last_serial = "USB-123"
        self.docker.rows[0]["NetworkSettings"]["Ports"]["5555/tcp"] = (
            self.docker.fixtures["changed_port"]
        )
        self.io.targets.append(("127.0.0.1:25555", "device"))
        self.docker.calls.clear()
        before = self.conf.model_dump()
        checked = self.control.preflight()
        self.assertTrue(checked.ok, checked.error)
        self.assertEqual(checked.serial, "127.0.0.1:25555")
        self.assertEqual(checked.observations["frame"], [1920, 1080])
        self.assertEqual(self.conf.model_dump(), before)
        self.assertFalse(any("ls" in argv for argv, _ in self.docker.calls))
        self.assertTrue(
            all(
                argv[-1] == "a" * 64
                for argv, _ in self.docker.calls
                if "inspect" in argv
            )
        )

    def test_stopped_candidate_has_no_endpoint_and_requires_confirmation(self):
        stopped = deepcopy(self.docker.fixtures["stopped"])
        stopped["NetworkSettings"] = deepcopy(self.docker.rows[0]["NetworkSettings"])
        self.docker.rows = [stopped]
        candidate = self.bind()
        self.assertEqual(candidate["state"], "stopped")
        self.assertEqual(candidate["serial"], "")
        checked = self.control.preflight()
        self.assertEqual(checked.error.code, "start_confirmation_required")
        self.assertEqual(checked.error.action, "confirm")
        self.assertFalse(any("start" in argv for argv, _ in self.docker.calls))

    def test_multiple_candidates_require_selection_and_empty_list_offers_manual(self):
        self.docker.rows.append(deepcopy(self.docker.fixtures["stopped"]))
        found = self.control.discover()
        self.assertTrue(found.ok, found.error)
        self.assertIsNone(found.selected_key)
        self.assertEqual(found.status, "selection_required")
        self.assertEqual(len(found.candidates), 2)
        for rows in ([], [self.docker.fixtures["custom"]]):
            self.docker.rows = rows
            result = self.control.discover()
            self.assertEqual(result.error.code, "no_redroid")
            self.assertEqual(result.error.action, "manual")
            self.assertEqual(result.candidates, [])

    def test_unusable_sibling_reports_repair_without_hiding_valid_container(self):
        for override in (
            {"NetworkSettings": {"Ports": {}}},
            {"HostConfig": {"NetworkMode": "host"}},
        ):
            with self.subTest(override=override):
                sibling = {
                    **deepcopy(self.docker.fixtures["running"]),
                    "Id": "b" * 64,
                    "Name": "/redroid-needs-manual",
                    **override,
                }
                self.docker.rows = [deepcopy(self.docker.fixtures["running"]), sibling]
                self.conf = Conf(device={"preset_id": "linux.redroid"})
                found = self.control.discover()
                self.assertEqual(len(found.candidates), 1)
                self.assertEqual(found.candidates[0]["instance_id"], "a" * 64)
                self.assertIsNone(found.selected_key)
                self.assertEqual(found.status, "selection_required")
                self.assertEqual(found.error.action, "manual")
                self.conf = self.conf.updated(
                    {"device": found.candidates[0]["binding"]}
                )
                self.assertTrue(self.control.preflight().ok)

    def test_first_linux_discovery_offers_redroid_alongside_other_products(self):
        self.conf = Conf(device={})
        control = DeviceControl(
            lambda: self.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(
                DiscoveryIO(),
                self.docker.controller,
                avd=AVDIO(),
                redroid=self.docker.controller,
            ),
        )
        found = control.discover()
        self.assertTrue(found.ok, found.error)
        self.assertEqual(
            {candidate["preset_id"] for candidate in found.candidates},
            {"linux.avd", "linux.redroid"},
        )
        self.assertEqual(found.status, "selection_required")
        self.assertIsNone(found.selected_key)

    def test_name_change_keeps_id_binding_but_replacement_cannot_take_over(self):
        self.bind()
        self.docker.rows[0]["Name"] = "/renamed-game"
        self.assertTrue(self.control.preflight().ok)
        self.docker.rows = [self.docker.fixtures["stopped"]]
        self.docker.rows[0]["Name"] = "/redroid-main"
        rejected = self.control.preflight()
        self.assertFalse(rejected.ok)
        self.assertEqual(rejected.serial, "")
        self.assertFalse(any("start" in argv for argv, _ in self.docker.calls))

    def session_control(self):
        self.adb = ADB()
        self.adb.boot = "1"
        self.adb.rows = self.io.targets
        self.session = DeviceSession(
            self.adb,
            ProductionSimulator(redroid=self.docker.controller),
            clock=self.docker.clock,
            policy=RecoveryPolicy(timeout=5, local_wait=1),
        )
        return DeviceControl(
            lambda: self.conf,
            Adapter(),
            preflight=PreflightService(self.io),
            session=self.session,
            redroid=self.docker.controller,
        )

    def mark_started(self):
        self.docker.rows[0]["State"] = deepcopy(
            self.docker.fixtures["running"]["State"]
        )
        self.docker.rows[0]["NetworkSettings"] = deepcopy(
            self.docker.fixtures["running"]["NetworkSettings"]
        )

    def test_stopped_session_does_not_launch_until_same_id_explicitly_confirmed(self):
        self.docker.rows = [deepcopy(self.docker.fixtures["stopped"])]
        self.bind()
        control = self.session_control()
        self.assertEqual(control.start().error.code, "start_confirmation_required")
        self.assertEqual(
            control.start_redroid(confirmed_instance="a" * 64).error.code,
            "start_confirmation_required",
        )
        self.assertFalse(any("start" in argv for argv, _ in self.docker.calls))
        self.docker.on_start = self.mark_started
        result = control.start_redroid(confirmed_instance="b" * 64)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:15555")
        control.close()
        control.close()
        actions = [argv for argv, _ in self.docker.calls if "start" in argv]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0][-1], "b" * 64)
        self.assertFalse(any("stop" in argv for argv, _ in self.docker.calls))
        self.docker.rows = [deepcopy(self.docker.fixtures["stopped"])]
        rejected = control.start()
        self.assertEqual(rejected.error.code, "start_confirmation_required")

    def test_confirmed_launch_waits_for_same_container_current_mapping_only(self):
        self.docker.rows = [deepcopy(self.docker.fixtures["stopped"])]
        self.bind()
        self.conf.device.last_serial = "USB-123"
        control = self.session_control()

        def launch_without_mapping():
            self.mark_started()
            self.docker.rows[0]["NetworkSettings"]["Ports"] = {}

        self.docker.on_start = launch_without_mapping

        def sleep(seconds):
            self.docker.clock.now += seconds
            if self.docker.clock.now >= 1:
                self.docker.rows[0]["NetworkSettings"]["Ports"] = {
                    "5555/tcp": self.docker.fixtures["changed_port"]
                }
                self.adb.rows = [("USB-123", "device"), ("127.0.0.1:25555", "device")]
                self.io.targets = self.adb.rows

        self.docker.clock.sleep = sleep
        result = control.start_redroid(confirmed_instance="b" * 64)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:25555")
        self.assertEqual(self.docker.clock.now, 1)
        self.assertNotIn("USB-123", self.adb.actions)
        self.assertEqual(sum("start" in argv for argv, _ in self.docker.calls), 1)

    def test_launch_without_mapping_exhausts_one_deadline_without_restarting(self):
        self.docker.rows = [deepcopy(self.docker.fixtures["stopped"])]
        self.bind()
        control = self.session_control()

        def launch_without_mapping():
            self.mark_started()
            self.docker.rows[0]["NetworkSettings"]["Ports"] = {}

        self.docker.on_start = launch_without_mapping
        failed = control.start_redroid(confirmed_instance="b" * 64)
        self.assertFalse(failed.ok)
        self.assertEqual(self.docker.clock.now, 5)
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(sum("start" in argv for argv, _ in self.docker.calls), 1)
        self.assertFalse(any("stop" in argv for argv, _ in self.docker.calls))

    def test_preflight_validates_adb_boot_frame_and_package(self):
        self.bind()
        for key, value, code in (
            ("targets", [("USB-123", "device")], "target_absent"),
            ("targets", [("127.0.0.1:15555", "offline")], "device_offline"),
            ("targets", [("127.0.0.1:15555", "unauthorized")], "device_unauthorized"),
            ("boot", "0", "boot_incomplete"),
            ("size", "Physical size: not-a-size", "invalid_size"),
            ("frame", None, "frame_failed"),
            ("installed_packages", [], "package_missing"),
        ):
            with self.subTest(code=code):
                previous = getattr(self.io, key)
                setattr(self.io, key, value)
                result = self.control.preflight()
                setattr(self.io, key, previous)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertEqual(result.serial, "127.0.0.1:15555")


if __name__ == "__main__":
    unittest.main()
