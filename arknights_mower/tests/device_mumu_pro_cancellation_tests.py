"""MuMu Pro manager preparation cancellation through real control and HTTP."""

import json
import subprocess
import unittest
from threading import Event
from unittest.mock import patch

from arknights_mower.tests import device_settings_route_tests as settings_routes
from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_discovery_tests import DiscoveryIO
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Clock
from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit, csleep
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession
from arknights_mower.utils.device.session_io import ProductionSimulator


class MuMuProCancellationTests(unittest.TestCase):
    def setUp(self):
        settings_routes.DeviceSettingsRouteTests.setUp(self)
        application = self.path.parent / "MuMuPlayer.app"
        manager = application / "Contents/MacOS/mumutool"
        manager.parent.mkdir(parents=True)
        manager.write_bytes(b"fixture manager")
        manager.chmod(0o755)
        (application / "Contents/Info.plist").touch()
        config.conf = config.Conf(
            device={
                "preset_id": "macos.mumu_pro",
                "manager_path": str(manager),
                "instance_id": "0",
                "instance_name": "Saved instance",
                "last_serial": "127.0.0.1:16384",
            }
        )
        config.save_conf()
        self.stop = Event()
        self.enterContext(patch.object(config, "stop_mower", self.stop))
        self.io = PreflightIO()
        self.io.host = "macos"
        self.rows = [
            {
                "index": 0,
                "name": "Saved instance",
                "bundle_path": str(self.path.parent.resolve() / "vms/0"),
                "state": "running",
                "adb_port": 16384,
            }
        ]
        self.phase = ""
        self.signal = "shutdown"
        self.empty_inventory = False

    def reset_control(self):
        self.commands = []
        self.clock = Clock()
        self.simulator = ProductionSimulator(
            run=self.run_command, monotonic=self.clock.monotonic
        )
        self.control = DeviceControl(
            lambda: config.conf,
            ManualAdapter(),
            preflight=PreflightService(self.io),
            discovery=DiscoveryService(DiscoveryIO(), self.simulator),
            session=DeviceSession(ADB(), self.simulator, clock=self.clock),
        )
        self.main.device_control = self.control

    def cancel(self):
        if self.signal == "shutdown":
            self.control.begin_shutdown()
        else:
            self.control._pending_close.set()

    def run_command(self, argv, **options):
        self.assertGreater(options["timeout"], 0)
        self.assertLessEqual(options["timeout"], 3)
        command = "open" if argv[0] == "/usr/bin/open" else argv[1]
        self.commands.append(command)
        if self.phase == command:
            self.cancel()
        if command == "port":
            raise subprocess.CalledProcessError(1, argv, stderr=b"Error: invalidPort")
        response = (
            json.dumps(
                {
                    "errcode": 0,
                    "return": {"count": len(self.rows), "results": self.rows},
                }
            ).encode()
            if command == "info" and not self.empty_inventory
            else b'{"errcode":0,"return":{"count":0,"results":[]}}'
        )
        return subprocess.CompletedProcess(argv, 0, response, b"")

    def assert_cancelled(self, route=None):
        before = config.conf.model_dump()
        saved = self.path.read_bytes()
        stopped = self.stop.is_set()
        if route is None:
            with self.assertRaises(MowerExit):
                self.control.prepare_mumu_pro_manager(config.conf)
        else:
            response = self.client.post(
                route, headers=self.headers, json={"start_manager": True}
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json["ok"])
            self.assertEqual(response.json["status"], "cancelled")
            self.assertEqual(
                response.json["error"]["code"], "device_operation_cancelled"
            )
        self.assertEqual(self.stop.is_set(), stopped)
        self.assertEqual(config.conf.model_dump(), before)
        self.assertEqual(self.path.read_bytes(), saved)

    def check_command_boundaries(self, route=None):
        for self.signal in ("shutdown", "close"):
            for stopped in (False, True):
                if stopped:
                    self.stop.set()
                else:
                    self.stop.clear()
                for self.phase, expected in (
                    ("port", ["port"]),
                    ("open", ["port", "open"]),
                    ("info", ["port", "open", "info"]),
                ):
                    with self.subTest(
                        signal=self.signal, stopped=stopped, phase=self.phase
                    ):
                        self.reset_control()
                        self.assert_cancelled(route)
                        self.assertEqual(self.commands, expected)

    def test_direct_preparation_cancels_at_each_command_boundary(self):
        self.check_command_boundaries()

    def test_discovery_http_returns_cancellation_at_each_command_boundary(self):
        self.check_command_boundaries("/device/discover")

    def test_preflight_http_returns_cancellation_at_each_command_boundary(self):
        self.check_command_boundaries("/device/preflight")

    def test_default_poll_wait_observes_shutdown_and_close(self):
        self.empty_inventory = True
        self.stop.set()
        for self.signal in ("shutdown", "close"):
            with self.subTest(signal=self.signal):
                self.reset_control()
                with patch(
                    "arknights_mower.utils.csleep.time.sleep",
                    side_effect=lambda interval: self.cancel(),
                ) as sleep:
                    self.assert_cancelled("/device/discover")
                sleep.assert_called_once()
                self.assertEqual(self.commands, ["port", "open", "info"])

    def test_completion_boundary_rechecks_cancellation(self):
        for self.signal in ("shutdown", "close"):
            with self.subTest(signal=self.signal):
                self.reset_control()
                with patch.object(
                    self.simulator,
                    "prepare_mumu_pro",
                    side_effect=lambda *args: self.cancel(),
                ):
                    self.assert_cancelled()
                self.assertEqual(self.commands, [])

    def test_empty_inventory_timeout_does_not_publish_success_after_cancellation(self):
        self.empty_inventory = True
        for self.signal in ("shutdown", "close"):
            with self.subTest(signal=self.signal):
                self.reset_control()

                def wait_until_deadline(interval):
                    self.clock.now = 6
                    self.cancel()

                self.simulator._mumu_pro._sleep = wait_until_deadline
                self.assert_cancelled("/device/discover")
                self.assertEqual(self.commands, ["port", "open", "info"])

    def test_stopped_task_does_not_cancel_preparation_and_restores_task_policy(self):
        self.stop.set()
        self.reset_control()
        prepared = self.control.prepare_mumu_pro_manager(config.conf)
        self.assertTrue(prepared.ok, prepared.error)
        self.assertEqual(self.commands, ["port", "open", "info"])
        self.assertTrue(self.stop.is_set())
        with self.assertRaises(MowerExit):
            csleep(0)


if __name__ == "__main__":
    unittest.main()
