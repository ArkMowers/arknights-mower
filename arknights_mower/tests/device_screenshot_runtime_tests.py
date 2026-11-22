"""Runtime DroidCast incidents retain one rebuild and verified ADB degradation."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import requests

from arknights_mower.tests import device_droidcast_tests
from arknights_mower.utils import config
from arknights_mower.utils.device import capture_time


class RuntimeCaptureTests(unittest.TestCase):
    setUp = device_droidcast_tests.DroidCastTests.setUp
    assert_adb_degraded = device_droidcast_tests.DroidCastTests.assert_adb_degraded

    def wall_time(self):
        return datetime(2026, 10, 18, 9, 0) + timedelta(seconds=self.clock.now)

    def prepare_timed_capture(self):
        self.device.session_control = self.control
        self.enterContext(
            patch.multiple(
                config,
                screenshot_time=datetime.min,
                screenshot_count=0,
                screenshot_avg=None,
            )
        )
        self.enterContext(
            patch("arknights_mower.utils.device.device.save_screenshot_frame")
        )
        self.enterContext(
            patch.object(capture_time, "datetime")
        ).now.side_effect = self.wall_time

    def test_rebuilt_helper_can_begin_listening_before_the_only_retry(self):
        self.assertTrue(self.control.capture().ok)
        self.prepare_timed_capture()
        get = self.http.get
        requests_at = []

        def delayed(*args, **kwargs):
            requests_at.append(self.wall_time())
            self.clock.sleep(0.25)
            if len(requests_at) < 3:
                raise requests.ConnectionError("not listening yet")
            return get(*args, **kwargs)

        self.http.get = delayed
        frame = self.device.screencap()
        self.assertEqual(frame[1].shape, (1080, 1920, 3))
        self.assertEqual(len(requests_at), 3)
        self.assertEqual(frame.requested_at, requests_at[-1])
        self.assertLess(requests_at[0], frame.requested_at)
        self.assertLess(frame.requested_at, self.wall_time())
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.android.processes[1].terminated, 0)
        self.assertEqual(self.simulator.actions, [])
        self.assertGreater(self.clock.now, 0)

    def test_degraded_frame_keeps_the_standard_adb_request_time(self):
        self.prepare_timed_capture()
        http_times = []
        adb_times = []

        def unavailable(*args, **kwargs):
            http_times.append(self.wall_time())
            self.clock.sleep(0.25)
            raise requests.ReadTimeout("read stalled")

        def standard_output(serial, command, limit, remaining, *, on_request=None):
            if command.startswith("screencap"):
                adb_times.append(self.wall_time())
            data = self.standard.output(
                serial, command, limit, remaining, on_request=on_request
            )
            self.clock.sleep(0.25)
            return data

        self.http.get = unavailable
        with patch(
            f"{device_droidcast_tests.SCREENSHOT_MODULE}._adb_output", standard_output
        ):
            frame = self.device.screencap()

        self.assertTrue(np.array_equal(frame[1], self.standard.frame))
        self.assertEqual(len(http_times), 2)
        self.assertEqual(adb_times, [frame.requested_at])
        self.assertLess(http_times[-1], frame.requested_at)
        self.assertLess(frame.requested_at, self.wall_time())

    def test_rebuilt_helper_never_listening_degrades_within_one_deadline(self):
        self.assertTrue(self.control.capture().ok)
        self.http.failure = requests.ConnectionError("not listening")
        result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_start_timeout", "限定时间")
        self.assertLessEqual(self.clock.now, 10.1)
        self.assertEqual(len(self.android.processes), 2)
        calls = len(self.http.calls)
        self.assert_adb_degraded(
            self.control.capture(), "droidcast_start_timeout", "限定时间"
        )
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(len(self.http.calls), calls)
        self.assertEqual(self.simulator.actions, [])

    def test_helper_exit_is_reported_without_repeated_relaunch(self):
        spawn = self.android.spawn

        def exited(*args, **kwargs):
            process = spawn(*args, **kwargs)
            process.exited = True
            return process

        with patch("arknights_mower.utils.device.droidcast.subprocess.Popen", exited):
            result = self.control.capture()
        self.assert_adb_degraded(result, "droidcast_start_failed", "提前退出")
        self.assertEqual(len(self.android.processes), 2)
        self.assert_adb_degraded(
            self.control.capture(), "droidcast_start_failed", "提前退出"
        )
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(self.http.calls, [])

    def test_late_first_capture_uses_healthy_helper_without_rebuilding(self):
        self.assertTrue(self.device.start_droidcast())
        self.clock.sleep(30)
        result = self.control.capture()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(self.android.processes), 1)
        self.assertEqual(self.android.processes[0].terminated, 0)


if __name__ == "__main__":
    unittest.main()
