import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device


def _device() -> Device:
    device = object.__new__(Device)
    device.client = MagicMock()
    return device


class TestIsAppRunningInBackground(unittest.TestCase):
    """#159：is_app_running_in_background 走同一条持久 adb 会话 ps/stopped 双查，
    无法判定时按「运行中」处理，避免误判重新拉起游戏（Bug 2 的 pidof 假阴性根因）。
    """

    def test_ps_found_process_returns_true(self):
        device = _device()
        device.client.run.return_value = (
            f"u0_a123  456  789  1234  5678  ...  {config.conf.APPNAME}\n".encode()
        )
        self.assertTrue(device.is_app_running_in_background())
        device.client.run.assert_called_once_with(
            f"ps -A | grep {config.conf.APPNAME} | grep -v grep"
        )

    def test_ps_empty_force_stopped_returns_false(self):
        device = _device()
        device.client.run.side_effect = [b"", b"Packages:\n  stopped=true\n"]
        self.assertFalse(device.is_app_running_in_background())

    def test_ps_empty_not_force_stopped_returns_true(self):
        device = _device()
        device.client.run.side_effect = [b"", b"Packages:\n  stopped=false\n"]
        self.assertTrue(device.is_app_running_in_background())

    def test_ps_empty_no_stopped_field_returns_true(self):
        device = _device()
        device.client.run.side_effect = [b"", b"Packages:\n  userId=10104\n"]
        self.assertTrue(device.is_app_running_in_background())

    def test_query_error_returns_true(self):
        device = _device()
        device.client.run.side_effect = RuntimeError("adb server is not working")
        self.assertTrue(device.is_app_running_in_background())

    def test_ps_empty_dumpsys_error_returns_true(self):
        device = _device()
        device.client.run.side_effect = [
            b"",
            RuntimeError("adb server is not working"),
        ]
        self.assertTrue(device.is_app_running_in_background())

    def test_bring_to_foreground_uses_persistent_session(self):
        device = _device()
        device.bring_to_foreground()
        device.client.run.assert_called_once_with(
            f"am start -n {config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}"
        )


class TestCheckCurrentFocus(unittest.TestCase):
    """#160：check_current_focus 四态 + 瞬时错误不重启、设备无法连接才自动重启模拟器。

    前台→无动作；后台/无法判定→bring_to_foreground；进程停止→launch；
    瞬时错误→重连重试；设备无法连接→自动重启模拟器（重启有上限）。
    """

    GAME_FOCUS = f"{config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}"
    LAUNCHER_FOCUS = "com.mumu.launcher/com.mumu.launcher.Launcher"

    def setUp(self):
        self.device = _device()
        self.device.control = MagicMock()
        self.device.is_app_running_in_background = MagicMock(return_value=True)
        self.device.bring_to_foreground = MagicMock()
        self.device.launch = MagicMock()
        self.device.start_droidcast = MagicMock()
        self.restart_mock = patch(
            "arknights_mower.utils.device.device.restart_simulator"
        ).start()
        self.addCleanup(self.restart_mock.stop)

    def _patchers(self) -> ExitStack:
        stack = ExitStack()
        stack.enter_context(patch("arknights_mower.utils.device.device.Session"))
        stack.enter_context(patch("arknights_mower.utils.device.device.Scrcpy"))
        stack.enter_context(patch("arknights_mower.utils.device.device.csleep"))
        stack.enter_context(
            patch("arknights_mower.utils.device.device.logger.exception")
        )
        return stack

    def test_focus_is_game_no_update(self):
        self.device.current_focus = MagicMock(return_value=self.GAME_FOCUS)
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertFalse(result)
        self.device.bring_to_foreground.assert_not_called()
        self.device.launch.assert_not_called()

    def test_focus_other_game_in_background_brings_to_foreground(self):
        self.device.current_focus = MagicMock(return_value=self.LAUNCHER_FOCUS)
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.device.bring_to_foreground.assert_called_once_with()
        self.device.launch.assert_not_called()

    def test_focus_other_game_not_running_launches(self):
        self.device.current_focus = MagicMock(return_value=self.LAUNCHER_FOCUS)
        self.device.is_app_running_in_background = MagicMock(return_value=False)
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.device.launch.assert_called_once_with()
        self.device.bring_to_foreground.assert_not_called()

    def test_transient_error_recovers_and_retries(self):
        self.device.current_focus = MagicMock(
            side_effect=[ConnectionError(b"closed"), self.LAUNCHER_FOCUS]
        )
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.assertEqual(self.device.current_focus.call_count, 2)
        self.device.client.check_server_alive.assert_called_once_with()
        self.device.bring_to_foreground.assert_called_once_with()

    def test_confirmed_dead_auto_restarts_then_raises(self):
        self.device.current_focus = MagicMock(side_effect=ConnectionError(b"closed"))
        with self._patchers():
            with self.assertRaisesRegex(ConnectionError, "重启模拟器"):
                self.device.check_current_focus()
        # retries=3 × restarts=3：9 次重试，判定设备无法连接自动重启 3 次后才放弃
        self.assertEqual(self.device.current_focus.call_count, 9)
        self.assertEqual(self.restart_mock.call_count, 3)
        self.device.launch.assert_not_called()

    def test_confirmed_dead_restarts_and_recovers(self):
        # 3 次瞬时失败判定设备无法连接 → 自动重启模拟器 → 重启后恢复
        self.device.current_focus = MagicMock(
            side_effect=[ConnectionError(b"closed")] * 3 + [self.LAUNCHER_FOCUS]
        )
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.restart_mock.assert_called_once_with()
        self.device.bring_to_foreground.assert_called_once_with()

    def test_mower_exit_propagates_immediately(self):
        self.device.current_focus = MagicMock(side_effect=MowerExit())
        with self._patchers():
            with self.assertRaises(MowerExit):
                self.device.check_current_focus()
        self.assertEqual(self.device.current_focus.call_count, 1)

    def test_reconnect_failure_does_not_escape_recover(self):
        # recover 里 reconnect 抛错不再穿出：计入重试，最终仍走自动重启（修复点）
        self.device.current_focus = MagicMock(side_effect=ConnectionError(b"closed"))
        self.device.reconnect = MagicMock(side_effect=RuntimeError("adb server 挂了"))
        with self._patchers():
            with self.assertRaisesRegex(ConnectionError, "重启模拟器"):
                self.device.check_current_focus()
        self.assertEqual(self.device.current_focus.call_count, 9)
        self.assertEqual(self.restart_mock.call_count, 3)
        self.device.launch.assert_not_called()


class TestStartDroidcast(unittest.TestCase):
    """install 失败（如设备瞬时离线）返回 False 而不抛错，不让重连崩（修复点）。"""

    def test_install_failure_returns_false(self):
        device = _device()
        device.get_droidcast_classpath = MagicMock(return_value=None)
        device.client.cmd = MagicMock(side_effect=RuntimeError("device offline"))
        self.assertFalse(device.start_droidcast())


if __name__ == "__main__":
    unittest.main()
