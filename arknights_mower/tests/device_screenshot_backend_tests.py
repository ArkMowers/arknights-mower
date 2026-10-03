"""Selected capture recovery through the device-control application boundary."""

import unittest
from unittest.mock import patch

import numpy as np

from arknights_mower.tests.device_preflight_tests import PreflightIO
from arknights_mower.tests.device_session_tests import (
    ADB,
    Clock,
    Preflight,
    Simulator,
)
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.device.application import DeviceControl
from arknights_mower.utils.device.preflight import PreflightService
from arknights_mower.utils.device.session import DeviceSession


class CaptureHandle:
    device_id = "USB-A"

    def __init__(self):
        self.frames = [RuntimeError("capture native code=7")]
        self.captures = 0
        self.rebuilds = 0
        self.standard_frames = [np.zeros((1080, 1920, 3), dtype=np.uint8)]
        self.standard_captures = 0

    def capture_frame(self):
        self.captures += 1
        frame = self.frames[min(self.captures - 1, len(self.frames) - 1)]
        if isinstance(frame, Exception):
            raise frame
        return frame

    def standard_frame(self):
        self.standard_captures += 1
        frame = self.standard_frames[
            min(self.standard_captures - 1, len(self.standard_frames) - 1)
        ]
        if isinstance(frame, Exception):
            raise frame
        return frame

    def rebuild_screenshot(self):
        self.rebuilds += 1

    def close(self):
        pass


class CaptureAdapter:
    def __init__(self, handle):
        self.handle = handle

    def open_verified(self, configuration, result):
        return self.handle

    def rebind(self, device, result):
        device.rebuild_screenshot()
        device.device_id = result.serial


class ScreenshotBackendTests(unittest.TestCase):
    def setUp(self):
        self.conf = Conf(
            device={"last_serial": "USB-A", "screenshot_backend": "adb_gzip"}
        )
        self.adb, self.simulator = ADB(), Simulator()
        self.adb.rows, self.adb.boot = [("USB-A", "device")], "1"
        self.handle = CaptureHandle()
        self.session = DeviceSession(self.adb, self.simulator, clock=Clock())
        self.control = DeviceControl(
            lambda: self.conf,
            CaptureAdapter(self.handle),
            preflight=Preflight(),
            session=self.session,
        )
        self.assertTrue(self.control.start().ok)

    def test_ready_capture_failure_rebuilds_once_and_stays_failed_without_switch(self):
        before = self.conf.model_dump()
        result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "screenshot_failed")
        self.assertIn("native code=7", result.error.message)
        self.assertEqual(self.handle.captures, 2)
        self.assertEqual(self.handle.rebuilds, 1)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])
        self.assertEqual(self.conf.model_dump(), before)
        error = self.control.settings_status()["error"]
        self.assertEqual(error["backend"], "adb_gzip")
        self.assertEqual(
            {item["backend"] for item in error["alternatives"]},
            {"droidcast", "custom"},
        )
        self.assertFalse(self.control.capture().ok)
        self.assertFalse(self.control.execute(lambda device: device.capture_frame()).ok)
        self.assertEqual(self.handle.captures, 2)
        self.assertEqual(self.handle.rebuilds, 1)

    def test_each_capture_incident_rebuilds_once_without_renewing_its_deadline(self):
        black = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.handle.frames = [
            ValueError("first truncated frame"),
            black,
            ValueError("second truncated frame"),
            black,
        ]

        def rebuild():
            self.handle.rebuilds += 1
            self.session.clock.sleep(self.session.policy.timeout - 1)

        self.handle.rebuild_screenshot = rebuild
        before = self.conf.model_dump()
        with patch.object(
            self.session, "begin_budget", wraps=self.session.begin_budget
        ) as begin:
            for incident in (1, 2):
                result = self.control.capture()
                self.assertTrue(result.ok, result.error)
                self.assertIs(result.value, black)
                self.assertEqual(self.handle.rebuilds, incident)
                self.assertEqual(self.session.remaining(), 1)
                self.assertEqual(begin.call_count, incident)
        self.assertEqual(self.handle.captures, 4)
        self.assertEqual(self.handle.standard_captures, 0)
        self.assertEqual(self.conf.model_dump(), before)

    def test_repeated_valid_black_frames_do_not_trigger_recovery(self):
        self.handle.frames = [np.zeros((1080, 1920, 3), dtype=np.uint8)]
        for _ in range(3):
            self.assertTrue(self.control.capture().ok)
        self.assertEqual(self.handle.rebuilds, 0)
        self.assertEqual(self.simulator.actions, [])

    def test_backend_rebuild_failure_does_not_retry_or_restart(self):
        def broken_rebuild():
            self.handle.rebuilds += 1
            raise RuntimeError("helper init failed")

        self.handle.rebuild_screenshot = broken_rebuild
        result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertIn("helper init failed", result.error.message)
        self.assertFalse(self.control.capture().ok)
        self.assertEqual(self.handle.captures, 1)
        self.assertEqual(self.handle.rebuilds, 1)
        self.assertEqual(self.simulator.actions, [])

    def test_wrong_shape_is_terminal_without_retry_rebuild_or_degradation(self):
        self.handle.frames = [np.zeros((720, 1280, 3), dtype=np.uint8)]
        result = self.control.capture()
        self.assertEqual(result.error.code, "frame_size_mismatch")
        self.assertIn("1280×720", result.error.message)
        self.assertIn("1920×1080", result.error.message)
        self.assertEqual(self.handle.rebuilds, 0)
        self.assertEqual(self.handle.captures, 1)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])
        error = self.control.settings_status()["error"]
        self.assertEqual(error["action"], "fix_size")
        self.assertEqual(error["fields"], ["screenshot_backend"])
        self.assertFalse(
            self.control.settings_status()["screenshot_backend"]["degraded"]
        )
        self.assertFalse(self.control.capture().ok)
        self.assertEqual(self.handle.captures, 1)

    def test_rebuild_failure_degrades_to_standard_adb_and_records_it(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.handle.frames = [RuntimeError("helper init failed")]
        for _ in range(2):
            self.assertTrue(self.control.capture().ok)
        self.assertEqual(self.handle.captures, 2)
        self.assertEqual(self.handle.rebuilds, 1)
        self.assertEqual(self.handle.standard_captures, 2)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])
        backend = self.control.settings_status()["screenshot_backend"]
        self.assertEqual(backend["selected"], "droidcast")
        self.assertEqual(backend["effective"], "adb_gzip")
        self.assertTrue(backend["degraded"])

    def test_degraded_capture_starts_a_fresh_budget_after_previous_recovery(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.assertTrue(self.control.capture().ok)
        self.session.clock.now += self.session.policy.timeout + 1
        result = self.control.capture()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(self.handle.standard_captures, 2)
        self.assertEqual(self.handle.rebuilds, 1)

    def test_droidcast_recovery_and_degradation_do_not_probe_the_failed_helper(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.adb.standard_frame_size = lambda *args: (1920, 1080)

        def failed_helper(*args):
            raise AssertionError(
                "DroidCast readiness probe must not restart the helper"
            )

        self.adb.frame_size = failed_helper
        first = self.control.capture()
        self.assertTrue(first.ok, first.error)
        second = self.control.capture()
        self.assertTrue(second.ok, second.error)
        self.assertEqual(self.handle.standard_captures, 2)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.adb.actions, [])

    def test_degraded_capture_rejects_a_different_verified_endpoint(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.assertTrue(self.control.capture().ok)
        self.simulator.state, self.simulator.serial = "running", "OTHER"
        self.adb.rows = [("OTHER", "device")]
        self.assertFalse(self.control.capture().ok)
        self.assertEqual(self.handle.standard_captures, 1)

    def test_fallback_probes_keep_only_the_budget_left_after_rebuild(self):
        self.conf.device.screenshot_backend = "droidcast"
        timeouts = []
        devices = self.adb.devices

        def observe_devices(adb_path, timeout):
            timeouts.append(timeout)
            return devices(adb_path, timeout)

        self.adb.devices = observe_devices
        self.handle.rebuild_screenshot = lambda: self.session.clock.sleep(
            self.session.policy.timeout - 1
        )
        result = self.control.capture()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(timeouts[-1], 1)
        self.assertEqual(self.handle.standard_captures, 1)

    def test_exhausted_rebuild_never_renews_budget_for_fallback(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.handle.rebuild_screenshot = lambda: self.session.clock.sleep(
            self.session.policy.timeout
        )
        with patch.object(
            self.session, "begin_budget", wraps=self.session.begin_budget
        ) as begin:
            result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertEqual(begin.call_count, 1)
        self.assertEqual(self.handle.standard_captures, 0)

    def test_standard_adb_failure_still_latches_with_the_recorded_degradation(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.handle.frames = [RuntimeError("helper init failed")]
        self.handle.standard_frames = [ValueError("standard ADB capture failed")]
        result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, "screenshot_failed")
        self.assertIn("helper init failed", result.error.message)
        self.assertIn("standard ADB capture failed", result.error.message)
        self.assertEqual(self.handle.captures, 2)
        self.assertEqual(self.handle.rebuilds, 1)
        self.assertEqual(self.handle.standard_captures, 1)
        self.assertEqual(self.simulator.actions, [])
        self.assertFalse(self.control.capture().ok)
        self.assertEqual(self.handle.standard_captures, 1)

    def test_not_ready_target_is_never_switched_to_standard_adb(self):
        self.conf.device.screenshot_backend = "droidcast"
        self.handle.frames = [RuntimeError("helper init failed")]
        control = DeviceControl(
            lambda: self.conf,
            CaptureAdapter(self.handle),
            preflight=Preflight(),
            session=self.session,
        )
        self.assertTrue(control.start().ok)
        self.adb.rows = [("USB-A", "offline")]
        result = control.capture()
        self.assertFalse(result.ok)
        self.assertEqual(self.handle.standard_captures, 0)
        self.assertEqual(self.handle.rebuilds, 0)
        self.assertEqual(self.simulator.actions, [])
        backend = control.settings_status()["screenshot_backend"]
        self.assertFalse(backend["degraded"])
        self.assertEqual(backend["effective"], "droidcast")

    def test_transport_recovery_rebind_counts_as_the_backend_rebuild(self):
        self.handle.frames = [
            RuntimeError("offline"),
            np.zeros((1080, 1920, 3), dtype=np.uint8),
        ]
        self.adb.rows = [("USB-A", "offline")]
        self.adb.on_recover = lambda: setattr(self.adb, "rows", [("USB-A", "device")])
        self.assertTrue(self.control.capture().ok)
        self.assertEqual(self.handle.rebuilds, 1)
        self.assertEqual(self.adb.actions, ["USB-A"])
        self.assertEqual(self.simulator.actions, [])

    def test_runtime_uses_the_selected_mumu_backend_and_exposes_native_error(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from arknights_mower.tests.device_mumu_frame_tests import (
            NativeRenderer,
            connected_ipc,
        )
        from arknights_mower.utils import config
        from arknights_mower.utils.device.device import Device

        self.conf = Conf(
            device={
                "preset_id": "windows.mumu12",
                "last_serial": "USB-A",
                "screenshot_backend": "mumu_ipc",
                "touch_backend": "mumu_ipc",
            }
        )
        renderer = NativeRenderer(code=-5, width=1280, height=720)
        ipc = connected_ipc(renderer)
        # Reconnection stays within this native backend, without manager I/O.
        ipc._emu_state = lambda: "running"
        device = object.__new__(Device)
        device.device_id = "USB-A"
        device.control = SimpleNamespace(mumu12IPC=ipc)
        control = DeviceControl(
            lambda: self.conf,
            CaptureAdapter(device),
            preflight=Preflight(),
            session=self.session,
        )
        capture_session = SimpleNamespace(
            capture_frame=ipc.capture_display, close=ipc.disconnect
        )
        with (
            patch.object(config, "conf", self.conf),
            patch("arknights_mower.utils.device.device.__system__", "windows"),
            patch(
                "arknights_mower.utils.device.device.MuMuCaptureSession",
                return_value=capture_session,
            ),
        ):
            self.assertTrue(control.start().ok)
            result = control.capture()
        self.assertFalse(result.ok)
        self.assertIn("-5", result.error.message)
        self.assertIn("1280×720", result.error.message)
        self.assertEqual(renderer.disconnected, [7])
        self.assertEqual(renderer.connect_calls, 1)
        self.assertEqual(self.simulator.actions, [])
        self.assertEqual(self.conf.device.screenshot_backend, "mumu_ipc")

    def test_readonly_preflight_preserves_capture_error_and_peer_alternatives(self):
        class BrokenCapture(PreflightIO):
            def capture_frame(self, adb_path, serial, profile):
                raise RuntimeError("MuMu IPC native code=8, actual=1280x720")

        control = DeviceControl(
            lambda: self.conf,
            CaptureAdapter(self.handle),
            preflight=PreflightService(BrokenCapture()),
        )
        self.conf.device.last_serial = "USB-123"
        before = self.conf.model_dump()
        result = control.preflight().to_dict()
        self.assertFalse(result["ok"])
        self.assertIn("native code=8", result["error"]["message"])
        self.assertIn("1280x720", result["error"]["message"])
        self.assertEqual(result["error"]["backend"], "adb_gzip")
        self.assertEqual(len(result["error"]["alternatives"]), 2)
        self.assertEqual(self.conf.model_dump(), before)


if __name__ == "__main__":
    unittest.main()
