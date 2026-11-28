import unittest
from contextlib import ExitStack
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.recovery import DeviceRecoveryError

FOCUS_COMMAND = "dumpsys window | grep mCurrentFocus"


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
        self.device.current_focus = MagicMock(
            side_effect=[self.LAUNCHER_FOCUS, self.GAME_FOCUS]
        )
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
        self.device.current_focus = MagicMock(
            side_effect=[self.LAUNCHER_FOCUS, self.GAME_FOCUS]
        )
        self.device.is_app_running_in_background = MagicMock(return_value=False)
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.device.launch.assert_called_once_with()
        self.device.bring_to_foreground.assert_not_called()

    def test_transient_error_recovers_and_retries(self):
        self.device.current_focus = MagicMock(
            side_effect=[
                ConnectionError(b"closed"),
                self.LAUNCHER_FOCUS,
                self.GAME_FOCUS,
            ]
        )
        with self._patchers():
            result = self.device.check_current_focus()
        self.assertTrue(result)
        self.assertEqual(self.device.current_focus.call_count, 3)
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
            side_effect=[ConnectionError(b"closed")] * 3
            + [self.LAUNCHER_FOCUS, self.GAME_FOCUS]
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


@pytest.fixture
def foreground_device(monkeypatch):
    device = _device()
    device._profile = config.conf.device.model_copy(
        update={"game_package": "com.hypergryph.arknights.bilibili"}
    )
    device._connect_once = MagicMock(side_effect=AssertionError("Unexpected reconnect"))
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr(config.conf.tap_to_launch_game, "mode", "adb")
    clock = [0.0]

    def sleep(seconds):
        if config.stop_mower.is_set():
            raise MowerExit
        clock[0] += seconds

    monkeypatch.setattr(
        "arknights_mower.utils.device.device.time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )
    monkeypatch.setattr("arknights_mower.utils.device.device.csleep", sleep)
    monkeypatch.setattr("arknights_mower.utils.device.io_budget.csleep", sleep)
    return device, clock


def test_waits_for_launcher_before_starting_after_bilibili_login(foreground_device):
    device, clock = foreground_device
    app = device.game_package
    game_focus = f"{app}/{config.APP_ACTIVITY_NAME}"
    start_times = []
    launcher_at = 4.2

    def run(command):
        if command == FOCUS_COMMAND:
            if clock[0] < launcher_at:
                return b"  mCurrentFocus=null\n"
            if start_times and launcher_at <= start_times[-1] <= clock[0] - 14:
                return f"  mCurrentFocus=Window{{123 u0 {game_focus}}}\n".encode()
            return b"  mCurrentFocus=Window{123 u0 com.mumu.launcher/.Launcher}\n"
        if command == f"ps -A | grep {app} | grep -v grep":
            if clock[0] < launcher_at:
                return f"u0_a34 27881 1087 0 0 0 0 S {app}\n".encode()
            return b""
        if command == f"am start -n {game_focus}":
            start_times.append(clock[0])
            if clock[0] < launcher_at:
                return (
                    b"Warning: Activity not started, intent has been delivered "
                    b"to currently running top-most instance.\n"
                )
            return b"Starting: Intent\n"
        raise AssertionError(f"Unexpected Android command: {command}")

    device.client.run.side_effect = run

    assert device.check_current_focus() is True
    assert start_times == [pytest.approx(launcher_at, abs=0.2)]
    assert start_times[0] >= launcher_at
    assert clock[0] >= start_times[0] + 14
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("missing_focus", [b"  mCurrentFocus=null\n", b""])
def test_window_returning_on_its_own_needs_only_focus_reads(
    foreground_device, missing_focus
):
    device, clock = foreground_device
    game_focus = f"{device.game_package}/{config.APP_ACTIVITY_NAME}"

    def run(command):
        if command != FOCUS_COMMAND:
            return b""
        if clock[0] < 1:
            return missing_focus
        return f"  mCurrentFocus=Window{{123 u0 {game_focus}}}\n".encode()

    device.client.run.side_effect = run

    assert device.check_current_focus() is True
    assert clock[0] >= 1
    assert {entry.args[0] for entry in device.client.run.call_args_list} == {
        FOCUS_COMMAND
    }
    device._connect_once.assert_not_called()


def test_unresolved_window_times_out_without_starting(foreground_device):
    device, clock = foreground_device
    device.client.run.return_value = b"  mCurrentFocus=null\n"

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert clock[0] == pytest.approx(30)
    assert {entry.args[0] for entry in device.client.run.call_args_list} == {
        FOCUS_COMMAND
    }
    device._connect_once.assert_not_called()


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
