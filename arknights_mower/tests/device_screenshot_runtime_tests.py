"""Runtime DroidCast readiness keeps the application's one-rebuild budget."""

import unittest

import requests

from arknights_mower.tests import device_droidcast_tests


class RuntimeCaptureTests(unittest.TestCase):
    setUp = device_droidcast_tests.DroidCastTests.setUp

    def test_rebuilt_helper_can_begin_listening_before_the_only_retry(self):
        self.assertTrue(self.control.capture().ok)
        get = self.http.get
        attempts = 0

        def delayed(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise requests.ConnectionError("not listening yet")
            return get(*args, **kwargs)

        self.http.get = delayed
        result = self.control.capture()
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.shape, (1080, 1920, 3))
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(self.android.processes[0].terminated, 1)
        self.assertEqual(self.android.processes[1].terminated, 0)
        self.assertEqual(self.simulator.actions, [])
        self.assertGreater(self.clock.now, 0)

    def test_rebuilt_helper_never_listening_stops_within_one_deadline(self):
        self.assertTrue(self.control.capture().ok)
        self.http.failure = requests.ConnectionError("not listening")
        result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertIn("限定时间", result.error.message)
        self.assertLessEqual(self.clock.now, 10.1)
        self.assertEqual(len(self.android.processes), 2)
        self.assertFalse(self.control.capture().ok)
        self.assertEqual(len(self.android.processes), 2)
        self.assertEqual(self.simulator.actions, [])

    def test_helper_exit_is_reported_without_repeated_relaunch(self):
        spawn = self.android.spawn

        def exited(*args, **kwargs):
            process = spawn(*args, **kwargs)
            process.exited = True
            return process

        from unittest.mock import patch

        with patch("arknights_mower.utils.device.droidcast.subprocess.Popen", exited):
            result = self.control.capture()
        self.assertFalse(result.ok)
        self.assertIn("提前退出", result.error.message)
        self.assertEqual(len(self.android.processes), 2)
        self.assertFalse(self.control.capture().ok)
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
