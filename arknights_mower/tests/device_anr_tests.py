from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device


@pytest.mark.parametrize("game_process", ["main", "pushcore", "absent"])
def test_mumu_acceleration_anr_does_not_block_foreground_recovery(game_process):
    device = object.__new__(Device)
    device.client = MagicMock()
    game_focus = f"{device.game_package}/{config.APP_ACTIVITY_NAME}"
    focus = "Application Not Responding: com.mumu.acc"

    def run(command):
        nonlocal focus
        if command == "dumpsys window | grep mCurrentFocus":
            return f"  mCurrentFocus=Window{{13b999 u0 {focus}}}\n".encode()
        if command == f"ps -A | grep {device.game_package} | grep -v grep":
            if game_process == "absent":
                return b""
            suffix = ":pushcore" if game_process == "pushcore" else ""
            return f"u0_a39 31745 1137 S {device.game_package}{suffix}\n".encode()
        if command == "am force-stop com.mumu.acc":
            focus = "com.mumu.launcher/com.mumu.launcher.Launcher"
            return b""
        if command == f"am start -n {game_focus}":
            if not focus.startswith("Application Not Responding:"):
                focus = game_focus
            return b"Starting: Intent\n"
        raise AssertionError(f"Unexpected device command: {command}")

    device.client.run.side_effect = run
    with (
        patch.object(Device, "recover", lambda self, operation: operation()),
        patch("arknights_mower.utils.device.device.csleep"),
        patch.object(config.conf.tap_to_launch_game, "mode", "adb"),
    ):
        assert device.check_current_focus() is True
        assert device.current_focus() == game_focus
        assert device.check_current_focus() is False

    commands = [entry.args[0] for entry in device.client.run.call_args_list]
    assert commands.count("am force-stop com.mumu.acc") == 1
    assert f"am force-stop {device.game_package}" not in commands


@pytest.mark.parametrize(
    "window_title",
    [
        "Application Not Responding: com.mumu.acc",
        "Application Not Responding: com.example.other",
        f"{config.conf.APPNAME}/{config.APP_ACTIVITY_NAME}",
    ],
)
def test_current_focus_preserves_anr_title_and_normal_activity(window_title):
    device = object.__new__(Device)
    device.client = MagicMock()
    device.client.run.return_value = (
        f"  mCurrentFocus=Window{{13b999 u0 {window_title}}}\n".encode()
    )
    with patch.object(Device, "recover", lambda self, operation: operation()):
        assert device.current_focus() == window_title


@pytest.mark.parametrize(
    "window_title",
    [
        "com.mumu.acc/.MainActivity",
        "Application Not Responding: com.example.other",
        "Application Not Responding: com.mumu.acc.other",
    ],
)
def test_other_windows_do_not_stop_mumu_acceleration_service(window_title):
    device = object.__new__(Device)
    device.client = MagicMock()
    game_focus = f"{device.game_package}/{config.APP_ACTIVITY_NAME}"
    device.client.run.side_effect = [
        f"  mCurrentFocus=Window{{13b999 u0 {window_title}}}\n".encode(),
        f"  mCurrentFocus=Window{{13b999 u0 {game_focus}}}\n".encode(),
    ]
    device.is_app_running_in_background = MagicMock(return_value=True)
    device.bring_to_foreground = MagicMock()
    with (
        patch.object(Device, "recover", lambda self, operation: operation()),
        patch("arknights_mower.utils.device.device.csleep"),
    ):
        assert device.check_current_focus() is True

    assert [call.args[0] for call in device.client.run.call_args_list] == [
        "dumpsys window | grep mCurrentFocus",
        "dumpsys window | grep mCurrentFocus",
    ]
    device.bring_to_foreground.assert_called_once_with()


@pytest.mark.parametrize("error", [MowerExit(), ConnectionError("offline")])
def test_failed_anr_service_stop_does_not_continue_foreground_recovery(error):
    device = object.__new__(Device)
    device.client = MagicMock()
    device.client.run.side_effect = [
        b"  mCurrentFocus=Window{13b999 u0 Application Not Responding: com.mumu.acc}\n",
        error,
    ]
    device.is_app_running_in_background = MagicMock()
    device.bring_to_foreground = MagicMock()
    device.launch = MagicMock()
    with patch.object(Device, "recover", lambda self, operation: operation()):
        with pytest.raises(type(error)) as raised:
            device.check_current_focus()

    assert raised.value is error
    assert [entry.args[0] for entry in device.client.run.call_args_list] == [
        "dumpsys window | grep mCurrentFocus",
        "am force-stop com.mumu.acc",
    ]
    device.is_app_running_in_background.assert_not_called()
    device.bring_to_foreground.assert_not_called()
    device.launch.assert_not_called()
