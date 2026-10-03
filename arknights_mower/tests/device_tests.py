import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, call, patch

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device


def _device() -> Device:
    device = object.__new__(Device)
    device.client = MagicMock()
    return device


class TestIsAppRunningInBackground(unittest.TestCase):
    """is_app_running_in_background 走持久 adb 会话检查进程存活。"""

    def setUp(self):
        self.enterContext(patch.object(Device, "recover", lambda self, func: func()))

    def test_ps_found_process_returns_true(self):
        device = _device()
        device.client.run.return_value = (
            f"u0_a123  456  789  1234  5678  ...  {config.conf.APPNAME}\n".encode()
        )
        self.assertTrue(device.is_app_running_in_background())
        device.client.run.assert_called_once_with(
            f"ps -A | grep {config.conf.APPNAME} | grep -v grep"
        )

    def test_ps_empty_returns_false(self):
        device = _device()
        device.client.run.return_value = b""
        self.assertFalse(device.is_app_running_in_background())

    def test_query_error_returns_false(self):
        device = _device()
        device.client.run.side_effect = RuntimeError("adb server is not working")
        self.assertFalse(device.is_app_running_in_background())

    def test_bring_to_foreground_uses_persistent_session(self):
        device = _device()
        device.bring_to_foreground()
        device.client.run.assert_called_once_with(
            f"am start -n {config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}"
        )


class TestCheckCurrentFocus(unittest.TestCase):
    """check_current_focus 状态与重连重试。

    前台→无动作；后台→bring_to_foreground；进程停止→launch；
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
        self.restart_mock = self.enterContext(
            patch(
                "arknights_mower.utils.simulator.restart_simulator",
                return_value=True,
            )
        )

        self.reconnect_once = self.enterContext(
            patch.object(self.device, "_connect_once")
        )
        self.enterContext(patch("arknights_mower.utils.device.recovery.csleep"))

    def _patchers(self) -> ExitStack:
        stack = ExitStack()
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
            with self.assertLogs("arknights_mower.utils.log", level="INFO") as logs:
                result = self.device.check_current_focus()
        self.assertTrue(result)
        self.device.bring_to_foreground.assert_called_once_with()
        self.device.launch.assert_not_called()
        self.assertIn("游戏不在前台，正在把游戏调到前台", "\n".join(logs.output))

    def test_launch_reports_the_game_start(self):
        device = _device()
        with self._patchers():
            with self.assertLogs("arknights_mower.utils.log", level="INFO") as logs:
                device.launch()
        self.assertIn("明日方舟，启动！", "\n".join(logs.output))

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
        self.reconnect_once.assert_called_once_with(wait_for_device=True)
        self.device.bring_to_foreground.assert_called_once_with()

    def test_confirmed_dead_exhausts_local_budget(self):
        self.device.current_focus = MagicMock(side_effect=ConnectionError(b"closed"))
        with self._patchers():
            with self.assertRaisesRegex(ConnectionError, "局部连接预算耗尽"):
                self.device.check_current_focus()
        self.assertEqual(self.device.current_focus.call_count, 4)
        self.restart_mock.assert_not_called()
        self.device.launch.assert_not_called()

    def test_last_local_attempt_can_recover(self):
        self.device.current_focus = MagicMock(
            side_effect=[ConnectionError(b"closed")] * 3 + [self.LAUNCHER_FOCUS]
        )
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.restart_mock.assert_not_called()
        self.device.bring_to_foreground.assert_called_once_with()

    def test_mower_exit_propagates_immediately(self):
        self.device.current_focus = MagicMock(side_effect=MowerExit())
        with self._patchers():
            with self.assertRaises(MowerExit):
                self.device.check_current_focus()
        self.assertEqual(self.device.current_focus.call_count, 1)

    def test_reconnect_failure_does_not_escape_recover(self):
        # A failed reconnect consumes the same local budget.
        self.device.current_focus = MagicMock(side_effect=ConnectionError(b"closed"))
        self.reconnect_once.side_effect = RuntimeError("adb server 挂了")
        with self._patchers():
            with self.assertRaisesRegex(ConnectionError, "局部连接预算耗尽"):
                self.device.check_current_focus()
        self.assertEqual(self.device.current_focus.call_count, 1)
        self.assertEqual(self.reconnect_once.call_count, 3)
        self.restart_mock.assert_not_called()
        self.device.launch.assert_not_called()

    def test_runtime_local_recovery_is_independent_of_idle_option(self):
        for close_when_idle in (False, True):
            with (
                self.subTest(close_when_idle=close_when_idle),
                patch.object(config.conf, "close_simulator_when_idle", close_when_idle),
            ):
                operation = MagicMock(
                    side_effect=[ConnectionError("offline"), "connected"]
                )
                self.reconnect_once.side_effect = [ConnectionError("offline")] * 2 + [
                    None
                ]
                actions = MagicMock()
                actions.attach_mock(operation, "operation")
                actions.attach_mock(self.reconnect_once, "reconnect")
                actions.attach_mock(self.restart_mock, "restart")
                self.assertEqual(self.device.recover(operation), "connected")
                self.assertEqual(
                    actions.mock_calls,
                    [call.operation()]
                    + [call.reconnect(wait_for_device=True)] * 2
                    + [
                        call.reconnect(wait_for_device=True),
                        call.operation(),
                    ],
                )


class TestDroidCastConnectionOrdering(unittest.TestCase):
    def test_reconnect_failure_does_not_start_touch_service(self):
        self.device = _device()
        self.device.control = None
        self.device.start_droidcast = MagicMock(return_value=False)
        with (
            patch.object(config.conf.droidcast, "enable", True),
            patch.object(config.conf, "touch_method", "scrcpy"),
            patch.object(self.device, "check_resolution", return_value=True),
            patch("arknights_mower.utils.device.device.Scrcpy") as scrcpy,
        ):
            with self.assertRaisesRegex(ConnectionError, "DroidCast启动失败"):
                self.device._connect_once()
        scrcpy.assert_not_called()


if __name__ == "__main__":
    unittest.main()
