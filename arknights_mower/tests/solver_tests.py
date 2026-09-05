import unittest
from unittest.mock import MagicMock, call, patch

from arknights_mower.utils import config
from arknights_mower.utils.solver import BaseSolver


class TestSolverStartupLaunch(unittest.TestCase):
    """启动时目标设备未注册到 adb=模拟器未启动，直接启动模拟器而不是重连（修复点）。"""

    def setUp(self):
        self.enterContext(patch.object(config.conf, "close_simulator_when_idle", True))
        self.enterContext(patch.object(config.conf, "adb", "127.0.0.1:16384"))
        self.enterContext(patch("arknights_mower.utils.solver.Scrcpy"))
        self.device_patch = patch("arknights_mower.utils.solver.Device")
        self.device_mock = self.device_patch.start()
        self.device_mock.side_effect = RuntimeError("Device connection failure")
        self.session_patch = patch("arknights_mower.utils.solver.Session")
        self.session_mock = self.session_patch.start()
        self.session_mock.return_value.devices_list.return_value = []
        self.restart_patch = patch("arknights_mower.utils.solver.restart_simulator")
        self.restart_mock = self.restart_patch.start()
        self.restart_mock.return_value = True
        self.addCleanup(self.device_patch.stop)
        self.addCleanup(self.session_patch.stop)
        self.addCleanup(self.restart_patch.stop)

    def test_first_task_starts_closed_simulator_then_connects(self):
        device = MagicMock()
        self.device_mock.side_effect = [
            RuntimeError("Device connection failure"),
            device,
        ]
        actions = MagicMock()
        actions.attach_mock(self.device_mock, "device")
        actions.attach_mock(self.restart_mock, "start")
        with patch("arknights_mower.utils.solver.Recognizer") as recog:
            solver = BaseSolver()
        self.assertIs(solver.device, device)
        self.assertEqual(
            actions.mock_calls,
            [call.device(), call.start(stop=False, start=True), call.device()],
        )
        recog.assert_called_once_with(device)

    def test_unchecked_option_does_not_start_missing_simulator(self):
        with patch.object(config.conf, "close_simulator_when_idle", False):
            with self.assertRaises(ConnectionError):
                BaseSolver()
        self.restart_mock.assert_not_called()

    def test_running_device_does_not_need_start(self):
        self.device_mock.side_effect = None
        with patch("arknights_mower.utils.solver.Recognizer"):
            BaseSolver()
        self.restart_mock.assert_not_called()

    def test_failed_start_does_not_continue_device_initialization(self):
        self.restart_mock.return_value = False
        with self.assertRaisesRegex(ConnectionError, "首次任务启动模拟器失败"):
            BaseSolver()
        self.device_mock.assert_called_once_with()

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


class TestTapElement(unittest.TestCase):
    """tap_element：find 返回空时不 tap、不抛错、返回 False；找到时 tap 中心、返回 True。"""

    def setUp(self):
        self.solver = BaseSolver.__new__(BaseSolver)
        self.find_patch = patch.object(BaseSolver, "find")
        self.tap_patch = patch.object(BaseSolver, "tap")
        self.find_mock = self.find_patch.start()
        self.tap_mock = self.tap_patch.start()
        self.addCleanup(self.find_patch.stop)
        self.addCleanup(self.tap_patch.stop)

    def test_missing_element_no_tap_returns_false(self):
        self.find_mock.return_value = None
        result = self.solver.tap_element("confirm_blue")
        self.assertFalse(result)
        self.tap_mock.assert_not_called()

    def test_found_element_taps_center_returns_true(self):
        self.find_mock.return_value = [[100, 200], [300, 400]]
        result = self.solver.tap_element("confirm_blue")
        self.assertTrue(result)
        self.tap_mock.assert_called_once_with([[100, 200], [300, 400]], 0.5, 0.5, 1)


if __name__ == "__main__":
    unittest.main()
