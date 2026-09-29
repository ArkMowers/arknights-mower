"""Discovery and binding outcomes at the device-control application seam."""

import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

import numpy as np

from arknights_mower.tests.device_application_tests import ManualAdapter
from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import ADB, Adapter, Clock, Simulator
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.discovery import DiscoveryService
from arknights_mower.utils.device.preflight import PreflightError, PreflightService
from arknights_mower.utils.device.session import DeviceSession, RecoveryPolicy
from arknights_mower.utils.device.session_io import ProductionSimulator
from arknights_mower.utils.device.windows_discovery import WindowsDiscoveryIO


class DiscoveryIO:
    def __init__(self):
        self.installations = []
        self.errors = []
        self.calls = 0

    def discover(self, profile):
        self.calls += 1
        return {"installations": self.installations, "errors": self.errors}


class VendorIsolationTests(unittest.TestCase):
    """One vendor's unexpected error never fails the whole detection request."""

    def test_a_raising_vendor_is_reported_and_the_others_still_return(self):
        class Broken:
            product = "雷电模拟器 9"

            def discover(self, profile):
                raise AttributeError("'RegistryValues' object has no attribute 'key'")

        class Working:
            product = "MuMu 12"

            def discover(self, profile):
                return {
                    "installations": [{"installation_path": "C:/MuMu12"}],
                    "errors": [],
                }

        result = WindowsDiscoveryIO((Broken(), Working())).discover(object())
        self.assertEqual(len(result["installations"]), 1)
        self.assertEqual(len(result["errors"]), 1)
        error = result["errors"][0]
        self.assertEqual(error.code, "discovery_failed")
        self.assertIn("雷电模拟器 9", error.message)
        self.assertEqual(error.fields, ["manager_path"])


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.configuration = Conf()
        self.io = DiscoveryIO()
        self.preflight_io = PreflightIO()
        self.preflight_io.host = "windows"
        self.simulator = Simulator()
        self.control = DeviceControl(
            lambda: self.configuration,
            ManualAdapter(),
            preflight=PreflightService(self.preflight_io),
            discovery=DiscoveryService(self.io, self.simulator),
        )

    def test_no_installation_returns_only_the_missing_installation_repair(self):
        before = self.configuration.model_dump()
        self.control.settings_status()
        self.assertEqual(self.io.calls, 0)
        result = self.control.discover().to_dict()
        self.assertFalse(result["ok"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["error"]["code"], "missing_installation")
        self.assertEqual(result["error"]["fields"], ["installation_path"])
        self.assertEqual(self.configuration.model_dump(), before)

    def test_single_stopped_instance_can_bind_without_inventing_an_endpoint(self):
        self.io.installations = [
            {
                "installation_path": "C:/MuMu12",
                "manager_path": "C:/MuMu12/shell/MuMuManager.exe",
                "instances": [
                    {
                        "instance_id": "3",
                        "instance_name": "日常号",
                        "state": "stopped",
                        "serial": "",
                    }
                ],
            }
        ]
        self.configuration = Conf(adb="old-online-target")
        result = self.control.discover().to_dict()
        candidate = result["candidates"][0]
        self.assertTrue(result["ok"])
        self.assertEqual(result["selected_key"], candidate["key"])
        self.assertEqual(candidate["instance_name"], "日常号")
        self.assertEqual(candidate["serial"], "")
        self.assertIsNone(candidate["preflight"])
        self.assertEqual(self.configuration.adb, "old-online-target")
        self.configuration = self.configuration.updated(
            {"device": candidate["binding"]}
        )
        self.assertEqual(self.configuration.device.instance_id, "3")
        self.assertEqual(self.configuration.device.instance_name, "日常号")
        self.assertEqual(self.configuration.device.last_serial, "")
        self.assertEqual(self.configuration.adb, "")

    def test_multiple_installations_require_selection_even_with_the_same_index(self):
        installation = {
            "installation_path": "C:/MuMu12",
            "manager_path": "C:/MuMu12/shell/MuMuManager.exe",
            "instances": [
                {
                    "instance_id": "0",
                    "instance_name": "主号",
                    "state": "running",
                    "serial": "127.0.0.1:16512",
                },
                {
                    "instance_id": "2",
                    "instance_name": "副号",
                    "state": "stopped",
                    "serial": "",
                },
            ],
        }
        second = deepcopy(installation)
        second["installation_path"] = "D:/MuMu12"
        second["manager_path"] = "D:/MuMu12/shell/MuMuManager.exe"
        self.io.installations = [installation, second]
        result = self.control.discover().to_dict()
        self.assertIsNone(result["selected_key"])
        self.assertEqual(result["status"], "selection_required")
        self.assertEqual(len({item["key"] for item in result["candidates"]}), 4)
        self.io.installations.reverse()
        reordered = self.control.discover().to_dict()
        self.assertEqual(
            {item["key"] for item in reordered["candidates"]},
            {item["key"] for item in result["candidates"]},
        )

    def test_partial_discovery_retains_good_instances_and_does_not_auto_choose(self):
        self.io.installations = [
            {
                "installation_path": "C:/MuMu12",
                "manager_path": "C:/MuMu12/shell/MuMuManager.exe",
                "instances": [
                    {
                        "instance_id": "3",
                        "instance_name": "日常号",
                        "state": "stopped",
                        "serial": "",
                    }
                ],
            }
        ]
        for code, fields in (
            ("manager_timeout", ["manager_path"]),
            ("manager_parse_failed", ["manager_path"]),
            ("discovery_permission_denied", ["installation_path"]),
        ):
            with self.subTest(code=code):
                self.io.errors = [
                    PreflightError(code, "请修复来源后重试", fields=fields)
                ]
                result = self.control.discover().to_dict()
                self.assertEqual(len(result["candidates"]), 1)
                self.assertIsNone(result["selected_key"])
                self.assertEqual(result["error"]["code"], code)
                self.assertEqual(result["errors"][0]["fields"], fields)

    def test_non_windows_and_active_sessions_never_search_installations(self):
        self.preflight_io.host = "linux"
        self.assertEqual(self.control.discover().error.code, "discovery_unavailable")
        self.assertEqual(self.io.calls, 0)
        self.control = DeviceControl(
            lambda: self.configuration,
            ManualAdapter(),
            discovery=DiscoveryService(self.io),
        )
        self.control.start()
        self.addCleanup(self.control.close)
        self.assertEqual(self.control.discover().error.code, "device_session_active")
        self.assertEqual(self.io.calls, 0)

    def test_bound_preflight_refreshes_only_its_instance_and_does_not_persist(self):
        self.configuration = Conf(
            device={
                "preset_id": "windows.mumu12",
                "instance_id": "3",
                "last_serial": "old-online",
            }
        )
        self.simulator.state = "running"
        self.simulator.serial = "127.0.0.1:16888"
        self.preflight_io.targets = [
            ("old-online", "device"),
            ("127.0.0.1:16888", "device"),
        ]
        result = self.control.preflight()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.serial, "127.0.0.1:16888")
        self.assertEqual(result.observations["frame"], [1920, 1080])
        self.assertEqual(self.simulator.bindings, [("windows.mumu12", "3")])
        self.assertEqual(self.configuration.device.last_serial, "old-online")
        self.assertEqual(self.io.calls, 0)

    def test_stopped_binding_never_checks_the_old_online_serial(self):
        self.configuration = Conf(
            device={
                "preset_id": "windows.mumu12",
                "instance_id": "3",
                "last_serial": "USB-123",
            }
        )
        self.simulator.state = "stopped"
        result = self.control.preflight()
        self.assertFalse(result.ok)
        self.assertEqual(result.serial, "")
        self.assertEqual(result.error.code, "instance_stopped")
        self.assertEqual(result.error.fields, [])
        self.assertEqual(self.simulator.actions, [])


class BoundMuMuSessionTests(unittest.TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        manager = folder / "MuMuManager.exe"
        manager.touch()
        self.configuration = Conf(
            device={
                "preset_id": "windows.mumu12",
                "installation_path": str(folder),
                "manager_path": str(manager),
                "instance_id": "3",
                "last_serial": "old-online",
            }
        )
        self.running = True
        self.port = 16888
        self.manager_targets = []
        self.lifecycle = []
        self.adb = ADB()
        self.adb.boot = "1"
        self.io = PreflightIO()
        self.io.host = "windows"
        self.io.paths.add("verified-adb")
        self.io.installed.update([str(folder), str(manager)])
        self.online()
        self.simulator = ProductionSimulator(run=self.run_manager)
        self.control = DeviceControl(
            lambda: self.configuration,
            Adapter(),
            preflight=PreflightService(self.io),
            session=DeviceSession(
                self.adb,
                self.simulator,
                clock=Clock(),
                policy=RecoveryPolicy(timeout=12, local_wait=1),
            ),
        )
        self.addCleanup(self.control.close)

    def online(self):
        self.io.targets = self.adb.rows = [
            ("old-online", "device"),
            (f"127.0.0.1:{self.port}", "device"),
        ]

    def run_manager(self, argv, **kwargs):
        if argv[1] == "info":
            self.manager_targets.append(argv[-1])
            output = json.dumps(
                {
                    "index": 3,
                    "name": "日常号",
                    "is_process_started": self.running,
                    "is_android_started": self.running,
                    "adb_port": self.port,
                }
            )
        else:
            self.lifecycle.append((argv[3], argv[-1]))
            self.running = argv[-1] == "launch_player"
            output = "{}"
        return subprocess.CompletedProcess(argv, 0, output.encode(), b"")

    def test_new_sessions_follow_the_bound_instances_changed_port(self):
        for port in (16888, 17777):
            self.port = port
            self.online()
            result = self.control.start()
            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.serial, f"127.0.0.1:{port}")
            self.assertEqual(
                self.control.settings_status()["preflight"]["observations"]["frame"],
                [1920, 1080],
            )
            self.control.close()
        self.assertEqual(set(self.manager_targets), {"3"})
        self.assertEqual(self.lifecycle, [])

    def test_stopped_instance_starts_once_then_validates_its_endpoint(self):
        self.running = False
        self.assertTrue(self.control.start().ok)
        self.assertEqual(self.lifecycle, [("3", "launch_player")])
        self.assertEqual(set(self.manager_targets), {"3"})

    def test_wrong_first_frame_rejects_the_refreshed_instance(self):
        for size, frame, code in (
            (
                # A portrait report is diagnostic; the frame below is the reason
                # this case is rejected.
                "Physical size: 1280x720",
                np.zeros((720, 1280, 3), dtype=np.uint8),
                "frame_size_mismatch",
            ),
            (
                "Physical size: 1920x1080",
                np.zeros((720, 1280, 3), dtype=np.uint8),
                "frame_size_mismatch",
            ),
        ):
            with self.subTest(code=code):
                self.io.size, self.io.frame = size, frame
                result = self.control.start()
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertEqual(self.lifecycle, [])
                self.control.close()

    def test_a_good_frame_accepts_a_portrait_reported_size(self):
        # Measured on the user's machine: screencap reports 1920x1080 while
        # wm size reports Physical size: 1080x1920.
        self.io.size = "Physical size: 1080x1920"
        self.io.frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        result = self.control.start()
        self.assertTrue(result.ok, result.error)
        self.control.close()


if __name__ == "__main__":
    unittest.main()
