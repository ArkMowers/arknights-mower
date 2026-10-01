"""Device and IPC operations preserve the application's recovery ownership."""

import subprocess
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config
from arknights_mower.utils.device.adb_client.server import SharedADBError
from arknights_mower.utils.device.device import Device


class SessionControl:
    def __init__(self, device):
        self.device = device
        self.executing = False
        self.operations = 0
        self.recoveries = 0
        self.stops = 0

    def execute(self, operation):
        self.operations += 1
        self.executing = True
        try:
            value = operation(self.device)
        finally:
            self.executing = False
        return SimpleNamespace(unwrap=lambda: value)

    def capture(self):
        return self.execute(lambda device: device.capture_frame())

    def recover(self):
        self.recoveries += 1
        return SimpleNamespace(unwrap=lambda: None)

    def stop_bound_simulator(self):
        self.stops += 1
        return True


class DeviceSessionCallerTests(unittest.TestCase):
    def setUp(self):
        self.device = object.__new__(Device)
        self.device.control = MagicMock()
        self.device.client = MagicMock()
        self.session = SessionControl(self.device)
        self.device.session_control = self.session

    def incompatible_server(self):
        self.enterContext(
            patch(
                "arknights_mower.utils.device.adb_client.server.probe_adb_server",
                return_value=40,
            )
        )
        return self.enterContext(
            patch(
                "subprocess.run",
                return_value=subprocess.CompletedProcess(
                    [], 0, b"Android Debug Bridge version 1.0.41\n", b""
                ),
            )
        )

    def test_custom_adb_capture_does_not_execute_with_incompatible_server(self):
        run = self.incompatible_server()
        self.device.strict_target = True
        self.device.device_id = "USB-A"
        self.device.client.adb_bin = "chosen-adb"
        self.device.control.mumu12IPC = None
        with (
            patch.object(config.conf.device, "screenshot_backend", "custom"),
            patch.object(config.conf.custom_screenshot, "enable", True),
            patch.object(
                config.conf.custom_screenshot, "command", "adb shell screencap -p"
            ),
            patch.object(config, "screenshot_time", datetime.min),
            patch("subprocess.check_output") as capture,
            self.assertRaises(SharedADBError),
        ):
            self.device.screencap()
        self.assertEqual(run.call_args.args[0], ["chosen-adb", "version"])
        capture.assert_not_called()

    def test_maatouch_does_not_spawn_with_incompatible_server(self):
        from arknights_mower.utils.device.maatouch.session import Session

        run = self.incompatible_server()
        self.device.client.adb_bin = "chosen-adb"
        with patch("subprocess.Popen") as spawn, self.assertRaises(SharedADBError):
            Session(self.device.client)
        self.assertEqual(run.call_args.args[0], ["chosen-adb", "version"])
        spawn.assert_not_called()

    def test_idle_transport_cleanup_preserves_incompatible_shared_server(self):
        from arknights_mower.utils.simulator import restart_simulator

        run = self.incompatible_server()
        self.device.client.device_id = "127.0.0.1:16416"
        self.device.client.adb_bin = "chosen-adb"
        with (
            patch.dict(
                sys.modules,
                {
                    "arknights_mower.__main__": SimpleNamespace(
                        device_control=self.session
                    )
                },
            ),
            patch.object(config.conf.device, "preset_id", "windows.mumu12"),
            patch.object(config.conf.simulator, "name", "MuMu12"),
            patch.object(config.conf.simulator, "index", "0"),
            patch.object(config.conf, "adb", "127.0.0.1:16384"),
            patch.object(config.conf, "maa_adb_path", "saved-adb"),
            patch.object(config.conf, "fix_mumu12_adb_disconnect", True),
            patch(
                "arknights_mower.utils.simulator.run_command", return_value=True
            ) as legacy_stop,
        ):
            self.assertTrue(restart_simulator(start=False))
        self.assertEqual(run.call_count, 1)
        self.assertEqual(run.call_args.args[0], ["chosen-adb", "version"])
        legacy_stop.assert_not_called()
        self.assertEqual(self.session.stops, 1)
        self.assertEqual(self.session.operations, 1)
        self.assertEqual(self.session.recoveries, 0)

    def test_uncertain_input_is_sent_once_through_application(self):
        touch = self.device.control
        touch.tap.side_effect = ConnectionError("delivery unknown")
        with self.assertRaisesRegex(ConnectionError, "delivery unknown"):
            self.device.tap((50, 60))
        touch.tap.assert_called_once_with((50, 60))
        touch.close.assert_called_once_with()
        self.assertIsNone(self.device.control)
        self.assertEqual(self.session.operations, 1)
        self.assertEqual(self.session.recoveries, 0)

    def test_nested_device_operation_uses_one_application_execution(self):
        self.device.client.run.return_value = b"frame"
        self.assertEqual(
            self.device.recover(lambda: self.device.run("screencap")), b"frame"
        )
        self.assertEqual(self.session.operations, 1)
        self.device.client.run.assert_called_once_with("screencap")

    def test_reconnect_uses_application_budget_even_with_legacy_arguments(self):
        self.device.reconnect(retries=100, restarts=100)
        self.assertEqual(self.session.recoveries, 1)
        self.device.client.reconnect.assert_not_called()

    def test_ipc_capture_failure_never_requests_device_restart(self):
        from arknights_mower.tests.device_mumu_frame_tests import (
            NativeRenderer,
            connected_ipc,
        )

        backend = connected_ipc(NativeRenderer(code=-5))
        with self.assertRaisesRegex(RuntimeError, "-5"):
            backend.capture_display()
        self.assertEqual(self.session.recoveries, 0)


if __name__ == "__main__":
    unittest.main()
