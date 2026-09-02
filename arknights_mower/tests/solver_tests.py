import unittest
from unittest.mock import patch

from arknights_mower.utils import config
from arknights_mower.utils.solver import BaseSolver


class TestSolverStartupLaunch(unittest.TestCase):
    """启动时目标设备未注册到 adb=模拟器未启动，直接启动模拟器而不是重连（修复点）。"""

    def setUp(self):
        self.device_patch = patch("arknights_mower.utils.solver.Device")
        self.device_mock = self.device_patch.start()
        self.device_mock.side_effect = RuntimeError("Device connection failure")
        self.session_patch = patch("arknights_mower.utils.solver.Session")
        self.session_mock = self.session_patch.start()
        self.session_mock.return_value.devices_list.return_value = []
        self.restart_patch = patch("arknights_mower.utils.solver.restart_simulator")
        self.restart_mock = self.restart_patch.start()
        self.addCleanup(self.device_patch.stop)
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.restart_patch.stop)

    def test_no_device_launches_simulator(self):
        old_adb = config.conf.adb
        config.conf.adb = "127.0.0.1:16384"
        try:
            with self.assertRaises(ConnectionError):
                BaseSolver()
        finally:
            config.conf.adb = old_adb
        self.restart_mock.assert_called_with(stop=False, start=True)
        self.assertEqual(self.restart_mock.call_count, 3)

    def test_no_configured_adb_does_not_launch(self):
        old_adb = config.conf.adb
        config.conf.adb = ""
        try:
            with self.assertRaises(ConnectionError):
                BaseSolver()
        finally:
            config.conf.adb = old_adb
        self.restart_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
