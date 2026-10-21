import subprocess
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock
from xml.etree import ElementTree as ET

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.adb_client.core import Client
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import device_io_budget, io_timeout
from arknights_mower.utils.device.mumu_popup import (
    UI_DUMP_COMMAND,
    is_mumu_launcher,
    startup_ad_close_point,
)
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.touch_backend import TouchFailure

LAUNCHER = "app.lawnchair/app.lawnchair.LawnchairLauncher"
DUMP_COMMAND = UI_DUMP_COMMAND
CLOSE_COMMAND = "input tap 1655 162"
ICON_COMMAND = "input tap 800 500"
DESKTOP_XML = (
    b'<hierarchy rotation="1"><node class="android.view.ViewGroup" '
    b'package="app.lawnchair" bounds="[0,0][1920,1080]">'
    b'<node text="Arknights" resource-id="app.lawnchair:id/icon" '
    b'class="android.widget.TextView" package="app.lawnchair" '
    b'clickable="true" enabled="true" bounds="[700,400][900,600]" />'
    b"</node></hierarchy>"
)


@pytest.fixture
def popup_xml():
    return (Path(__file__).parent / "fixtures" / "mumu_startup_ad.xml").read_bytes()


def popup_tree(data):
    return ET.fromstring(data[: data.index(b"</hierarchy>") + len(b"</hierarchy>")])


def node_by_id(tree, suffix):
    return next(
        node
        for node in tree.iter("node")
        if node.get("resource-id") == f"app.lawnchair:id/{suffix}"
    )


@pytest.mark.parametrize(
    "focus",
    [LAUNCHER, "app.lawnchair/.LawnchairLauncher"],
)
def test_launcher_accepts_only_confirmed_activity_names(focus):
    assert is_mumu_launcher(focus)


@pytest.mark.parametrize(
    "focus",
    [
        "app.lawnchair/app.lawnchair.OtherActivity",
        "app.lawnchair.other/app.lawnchair.LawnchairLauncher",
        LAUNCHER + ".other",
        "com.mumu.launcher/com.mumu.launcher.Launcher",
        "Application Not Responding: app.lawnchair",
        "",
    ],
)
def test_other_windows_are_not_confirmed_mumu_launcher(focus):
    assert not is_mumu_launcher(focus)


def test_real_popup_output_identifies_close_center_not_membership(popup_xml):
    assert startup_ad_close_point(popup_xml) == (1655, 162)


def test_normal_desktop_has_no_startup_ad():
    assert startup_ad_close_point(DESKTOP_XML) is None


def test_other_application_controls_do_not_produce_a_close_point(popup_xml):
    data = popup_xml.replace(b"app.lawnchair", b"com.example.other")
    assert startup_ad_close_point(data) is None


@pytest.mark.parametrize("data", [b"", b"not xml", b"<hierarchy><node>"])
def test_malformed_hierarchy_is_not_treated_as_ad_absence(data):
    with pytest.raises(ValueError):
        startup_ad_close_point(data)


def test_oversized_hierarchy_is_rejected_before_detection():
    with pytest.raises(ValueError):
        startup_ad_close_point(b" " * (1024 * 1024 + 1) + DESKTOP_XML)


@pytest.mark.parametrize("missing", ["pic", "member", "memberText", "close"])
def test_partial_known_popup_is_not_treated_as_ad_absence(popup_xml, missing):
    tree = popup_tree(popup_xml)
    target = node_by_id(tree, missing)
    parent = next(parent for parent in tree.iter() if target in list(parent))
    parent.remove(target)
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


@pytest.mark.parametrize(
    "bounds",
    [
        "",
        "[1634,141][1634,183]",
        "[1676,183][1634,141]",
        "[-1,141][20,183]",
        "[1900,141][1921,183]",
        "[1634,1070][1676,1081]",
        "[a,141][1676,183]",
    ],
)
def test_close_bounds_must_fit_the_observed_parent_bounds(popup_xml, bounds):
    tree = popup_tree(popup_xml)
    node_by_id(tree, "close").set("bounds", bounds)
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


@pytest.mark.parametrize("part", ["pic", "close"])
@pytest.mark.parametrize("attribute", ["clickable", "enabled"])
def test_popup_image_and_close_must_be_interactive(popup_xml, part, attribute):
    tree = popup_tree(popup_xml)
    node_by_id(tree, part).set(attribute, "false")
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


@pytest.mark.parametrize("part", ["pic", "member", "memberText", "close"])
def test_known_popup_rejects_mixed_package_nodes(popup_xml, part):
    tree = popup_tree(popup_xml)
    node_by_id(tree, part).set("package", "com.example.other")
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


def test_membership_text_must_confirm_the_known_ad_structure(popup_xml):
    tree = popup_tree(popup_xml)
    node_by_id(tree, "memberText").set("text", "Other action")
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


def test_picture_must_be_an_image_view(popup_xml):
    tree = popup_tree(popup_xml)
    node_by_id(tree, "pic").set("class", "android.widget.TextView")
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


def test_ad_controls_require_a_view_group_parent(popup_xml):
    tree = popup_tree(popup_xml)
    close = node_by_id(tree, "close")
    parent = next(parent for parent in tree.iter() if close in list(parent))
    parent.set("class", "android.widget.FrameLayout")
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


def test_close_must_be_a_direct_sibling_of_picture_and_membership(popup_xml):
    tree = popup_tree(popup_xml)
    close = node_by_id(tree, "close")
    parent = next(parent for parent in tree.iter() if close in list(parent))
    parent.remove(close)
    wrapper = ET.SubElement(parent, "node", {"class": "android.view.ViewGroup"})
    wrapper.append(close)
    with pytest.raises(ValueError):
        startup_ad_close_point(ET.tostring(tree))


class AndroidResponses:
    def __init__(self, popup_xml, device):
        self.popup_xml = popup_xml
        self.device = device
        self.focus = LAUNCHER
        self.visible = True
        self.running = None
        self.close_works = True
        self.start_works = True
        self.close_error = None
        self.dump_error = None
        self.verification_error = None
        self.dump_override = None
        self.commands = []

    @property
    def game_focus(self):
        return f"{self.device.game_package}/{config.APP_ACTIVITY_NAME}"

    @property
    def start_command(self):
        return f"am start -n {self.game_focus}"

    @property
    def custom_command(self):
        return f"echo custom; {self.start_command}"

    def run(self, command):
        self.commands.append(command)
        if command == "dumpsys window | grep mCurrentFocus":
            return f"mCurrentFocus=Window{{123 u0 {self.focus}}}\n".encode()
        if command == DUMP_COMMAND:
            if self.dump_error is not None:
                raise self.dump_error
            if not self.visible and self.verification_error is not None:
                raise self.verification_error
            if self.dump_override is not None:
                return self.dump_override
            return self.popup_xml if self.visible else DESKTOP_XML
        if command == CLOSE_COMMAND:
            if self.close_error is not None:
                raise self.close_error
            if self.close_works:
                self.visible = False
            return b""
        if command == f"ps -A | grep {self.device.game_package} | grep -v grep":
            if self.running is None:
                return b""
            suffix = ":pushcore" if self.running == "pushcore" else ""
            return f"u0_a39 2000 1000 S {self.device.game_package}{suffix}\n".encode()
        if command in (ICON_COMMAND, self.start_command, self.custom_command):
            if self.start_works:
                self.focus = self.game_focus
                self.running = "main"
            return b""
        raise AssertionError(f"Unexpected Android command: {command}")


@pytest.fixture
def android(monkeypatch, popup_xml):
    conf = config.conf.model_copy(deep=True)
    conf.tap_to_launch_game.mode = "tap"
    conf.tap_to_launch_game.x = 800
    conf.tap_to_launch_game.y = 500
    conf.tap_to_launch_game.command = "echo custom; am start -n {package}/{activity}"
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(config, "stop_mower", Event())
    monkeypatch.setattr("arknights_mower.utils.device.device.csleep", lambda _: None)
    clock = [0.0]
    monkeypatch.setattr(
        "arknights_mower.utils.device.device.time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )

    def budget_sleep(seconds):
        clock[0] += seconds
        io_timeout(0)

    monkeypatch.setattr(
        "arknights_mower.utils.device.device.budget_sleep", budget_sleep
    )
    device = object.__new__(Device)
    device._profile = conf.device.model_copy(
        update={"game_package": "com.hypergryph.arknights", "recovery_timeout": 5}
    )
    device.control = MagicMock()
    device._connect_once = MagicMock(
        side_effect=AssertionError("Offline popup tests must not reconnect a device")
    )
    responses = AndroidResponses(popup_xml, device)
    responses.clock = clock
    device.client = MagicMock()
    device.client.run.side_effect = responses.run
    device.client.cmd.side_effect = lambda args: device.client.run.side_effect(args[1])
    return device, responses, conf


@pytest.fixture
def ui_cli(android, monkeypatch):
    from arknights_mower.utils.device.adb_client import utils

    device, responses, _ = android
    client = object.__new__(Client)
    client.adb_bin, client.device_id = "offline-adb", "offline-device"
    client._check_open = MagicMock()
    client.run = MagicMock(side_effect=responses.run)
    device.client = client
    device.session_control = SimpleNamespace(executing=True)
    calls = []

    def guard(adb, *, timeout, run):
        calls.append(("guard", adb, timeout))
        responses.clock[0] += 0.25
        return timeout - 0.25

    def run(argv, **kwargs):
        calls.append(("command", argv, kwargs))
        if kwargs["timeout"] < 5.25:
            responses.clock[0] += kwargs["timeout"]
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
        responses.clock[0] += 5.25
        return SimpleNamespace(stdout=responses.run(DUMP_COMMAND))

    monkeypatch.setattr(utils, "guard_adb", guard)
    monkeypatch.setattr(utils, "run_command", run)
    return device, responses, calls


def test_ui_hierarchy_uses_guarded_cli_past_five_second_socket_limit(ui_cli):
    device, responses, calls = ui_cli
    responses.visible = False

    device.launch()

    assert responses.clock[0] == pytest.approx(5.5)
    assert calls[0] == ("guard", "offline-adb", 10)
    assert calls[1][1] == [
        "offline-adb",
        "-s",
        "offline-device",
        "shell",
        DUMP_COMMAND,
    ]
    assert calls[1][2]["timeout"] == pytest.approx(9.75)
    assert calls[1][2]["check"] is True
    assert DUMP_COMMAND not in [
        call.args[0] for call in device.client.run.call_args_list
    ]
    assert responses.commands.count(ICON_COMMAND) == 1


def test_ui_cli_timeout_obeys_parent_budget_and_prevents_game_input(ui_cli):
    device, responses, calls = ui_cli
    responses.visible = False

    def remaining():
        seconds = 3 - responses.clock[0]
        if seconds <= 0:
            raise DeviceRecoveryError("parent budget exhausted")
        return seconds

    with pytest.raises(DeviceRecoveryError):
        with device_io_budget(remaining):
            device.launch()

    assert responses.clock[0] == pytest.approx(3)
    assert calls[0] == ("guard", "offline-adb", 3)
    assert calls[1][2]["timeout"] == pytest.approx(2.75)
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands


def test_ui_cli_preserves_xml_bytes_for_existing_parsers(ui_cli):
    device, responses, _ = ui_cli
    data = DESKTOP_XML.replace(b"Arknights", "明日方舟".encode("utf8"))
    responses.dump_override = data

    result = device._read_ui_hierarchy()

    assert isinstance(result, bytes)
    assert result == data


def test_ui_cli_second_read_shares_ten_second_ad_deadline(ui_cli):
    device, responses, calls = ui_cli

    with pytest.raises(DeviceRecoveryError):
        device.launch()

    assert responses.clock[0] == pytest.approx(10)
    assert [call[2] for call in calls if call[0] == "guard"] == pytest.approx([10, 4.5])
    assert responses.commands.count(CLOSE_COMMAND) == 1
    assert ICON_COMMAND not in responses.commands


def test_tap_launch_closes_real_popup_then_rechecks_before_icon_tap(android):
    device, responses, _ = android
    device.launch()
    commands = responses.commands
    assert commands[0] == "dumpsys window | grep mCurrentFocus"
    assert commands.count(CLOSE_COMMAND) == 1
    assert commands.count(ICON_COMMAND) == 1
    close_index = commands.index(CLOSE_COMMAND)
    icon_index = commands.index(ICON_COMMAND)
    assert DUMP_COMMAND in commands[:close_index]
    assert DUMP_COMMAND in commands[close_index + 1 : icon_index]
    assert not responses.visible
    assert responses.focus == responses.game_focus
    assert not any("force-stop" in command for command in commands)


def test_normal_mumu_desktop_only_taps_the_configured_icon(android):
    device, responses, _ = android
    responses.visible = False
    device.launch()
    assert CLOSE_COMMAND not in responses.commands
    assert responses.commands.count(ICON_COMMAND) == 1


@pytest.mark.parametrize("new_focus", ["game", "other"])
def test_no_ad_observation_rechecks_focus_before_tapping_icon(android, new_focus):
    device, responses, _ = android
    responses.visible = False

    def run(command):
        result = responses.run(command)
        if command == DUMP_COMMAND:
            responses.focus = (
                responses.game_focus
                if new_focus == "game"
                else "com.example.other/.Activity"
            )
        return result

    device.client.run.side_effect = run
    if new_focus == "game":
        device.launch()
    else:
        with pytest.raises(DeviceRecoveryError):
            device.launch()
    assert ICON_COMMAND not in responses.commands
    assert CLOSE_COMMAND not in responses.commands
    device._connect_once.assert_not_called()


def test_other_launcher_does_not_inspect_or_close_mumu_popup(android):
    device, responses, _ = android
    responses.focus = "com.example.home/.Launcher"
    device.launch()
    assert DUMP_COMMAND not in responses.commands
    assert CLOSE_COMMAND not in responses.commands
    assert responses.commands.count(ICON_COMMAND) == 1


@pytest.mark.parametrize("mode", ["adb", "custom"])
def test_direct_launch_preserves_the_selected_non_tap_command(android, mode):
    device, responses, conf = android
    conf.tap_to_launch_game.mode = mode
    device.launch()
    expected = responses.start_command if mode == "adb" else responses.custom_command
    assert responses.commands == [expected]


@pytest.mark.parametrize("mode", ["tap", "adb", "custom"])
@pytest.mark.parametrize("running", ["main", "pushcore"])
@pytest.mark.parametrize(
    "data",
    [b"", b" " * (1024 * 1024 + 1)],
    ids=["empty", "oversized"],
)
def test_home_wakeup_restores_running_game_without_reading_launcher_ui(
    android, mode, running, data
):
    device, responses, conf = android
    conf.tap_to_launch_game.mode = mode
    responses.focus = responses.game_focus
    responses.running = running
    responses.dump_override = data
    bound_client = device.client
    original_profile = device.profile.model_copy(deep=True)

    def run(command):
        if command == "input keyevent 3":
            responses.commands.append(command)
            responses.focus = LAUNCHER
            return b""
        return responses.run(command)

    device.client.run.side_effect = run
    device.return_home()
    assert responses.focus == LAUNCHER

    assert device.check_current_focus() is True
    assert responses.focus == responses.game_focus
    assert device.check_current_focus() is False

    assert responses.commands == [
        "input keyevent 3",
        "dumpsys window | grep mCurrentFocus",
        f"ps -A | grep {device.game_package} | grep -v grep",
        responses.start_command,
        "dumpsys window | grep mCurrentFocus",
        "dumpsys window | grep mCurrentFocus",
    ]
    assert device.client is bound_client
    assert device.profile == original_profile
    device.client.cmd.assert_not_called()
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("mode", ["adb", "custom"])
@pytest.mark.parametrize(
    "data",
    [b"", b" " * (1024 * 1024 + 1)],
    ids=["empty", "oversized"],
)
def test_stopped_game_direct_recovery_does_not_require_launcher_ui(android, mode, data):
    device, responses, conf = android
    conf.tap_to_launch_game.mode = mode
    responses.dump_override = data

    assert device.check_current_focus() is True
    assert responses.focus == responses.game_focus

    expected = responses.start_command if mode == "adb" else responses.custom_command
    assert responses.commands == [
        "dumpsys window | grep mCurrentFocus",
        f"ps -A | grep {device.game_package} | grep -v grep",
        expected,
        "dumpsys window | grep mCurrentFocus",
    ]
    device.client.cmd.assert_not_called()
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("entry", ["launch", "check_current_focus"])
def test_empty_launcher_ui_still_blocks_tap_launch(android, entry):
    device, responses, _ = android
    responses.dump_override = b""

    with pytest.raises(DeviceRecoveryError):
        getattr(device, entry)()

    assert responses.commands.count(DUMP_COMMAND) == 1
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    assert responses.custom_command not in responses.commands
    device._connect_once.assert_not_called()


def test_failed_direct_foreground_restore_prevents_recognizer_capture(android):
    from arknights_mower.utils.recognize import Recognizer

    device, responses, _ = android
    responses.running = "main"
    responses.start_works = False
    responses.dump_override = b""
    device.screencap = MagicMock()
    device.check_ui_responsive = MagicMock()
    recog = Recognizer(device)

    with pytest.raises(DeviceRecoveryError):
        recog.start()

    assert responses.commands.count(responses.start_command) == 1
    assert DUMP_COMMAND not in responses.commands
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands
    device.screencap.assert_not_called()
    device.check_ui_responsive.assert_not_called()
    device._connect_once.assert_not_called()
    assert recog._img is None


def test_cancelled_home_wakeup_does_not_restore_or_capture(android):
    from arknights_mower.utils.recognize import Recognizer

    device, responses, _ = android
    responses.running = "main"
    responses.dump_override = b""
    device.screencap = MagicMock()
    device.check_ui_responsive = MagicMock()
    recog = Recognizer(device)
    config.stop_mower.set()

    with pytest.raises(MowerExit):
        recog.start()

    assert responses.commands == []
    device.client.cmd.assert_not_called()
    device.screencap.assert_not_called()
    device.check_ui_responsive.assert_not_called()
    device._connect_once.assert_not_called()
    assert recog._img is None


def test_recognizer_continues_with_new_frames_after_direct_foreground_restore(android):
    import numpy as np

    from arknights_mower.utils.recognize import Recognizer

    device, responses, _ = android
    responses.running = "main"
    responses.dump_override = b""
    device.check_ui_responsive = MagicMock()
    images = [np.full((1080, 1920, 3), value, dtype=np.uint8) for value in (37, 89)]
    frames = [
        (b"first frame", images[0], images[0][:, :, 0]),
        (b"second frame", images[1], images[1][:, :, 0]),
    ]
    pending_frames = iter(frames)
    recog = Recognizer(device)

    def capture():
        assert responses.focus == responses.game_focus
        assert recog._img is None
        assert recog._screencap is None
        return next(pending_frames)

    device.screencap = MagicMock(side_effect=capture)
    recog.start()
    assert recog.img is images[0]
    assert recog.screencap == b"first frame"
    assert device.screencap.call_count == 1

    recog.update()
    recog.start()
    assert recog.img is images[1]
    assert recog.screencap == b"second frame"
    assert device.screencap.call_count == 2
    device.check_ui_responsive.assert_called_once_with()
    assert responses.commands == [
        "dumpsys window | grep mCurrentFocus",
        f"ps -A | grep {device.game_package} | grep -v grep",
        responses.start_command,
        "dumpsys window | grep mCurrentFocus",
        "dumpsys window | grep mCurrentFocus",
    ]
    device.client.cmd.assert_not_called()
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("mode", ["tap", "adb", "custom"])
@pytest.mark.parametrize("running", ["main", "pushcore"])
def test_running_game_popup_recovery_keeps_game_and_uses_foreground_restore(
    android, mode, running
):
    device, responses, conf = android
    conf.tap_to_launch_game.mode = mode
    responses.running = running
    assert device.check_current_focus() is True
    assert CLOSE_COMMAND not in responses.commands
    assert DUMP_COMMAND not in responses.commands
    assert responses.commands.count(responses.start_command) == 1
    assert ICON_COMMAND not in responses.commands
    assert responses.custom_command not in responses.commands
    assert not any("force-stop" in command for command in responses.commands)
    assert responses.focus == responses.game_focus
    assert device.check_current_focus() is False
    assert responses.commands.count(responses.start_command) == 1
    device.client.cmd.assert_not_called()
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("mode", ["tap", "adb", "custom"])
def test_stopped_game_popup_recovery_uses_the_saved_launch_mode(android, mode):
    device, responses, conf = android
    conf.tap_to_launch_game.mode = mode
    assert device.check_current_focus() is True
    expected = {
        "tap": ICON_COMMAND,
        "adb": responses.start_command,
        "custom": responses.custom_command,
    }[mode]
    assert responses.commands.count(CLOSE_COMMAND) == int(mode == "tap")
    assert responses.commands.count(expected) == 1
    if mode == "tap":
        assert responses.commands.index(CLOSE_COMMAND) < responses.commands.index(
            expected
        )
    else:
        assert DUMP_COMMAND not in responses.commands
        device.client.cmd.assert_not_called()
    assert responses.focus == responses.game_focus
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("entry", ["launch", "check_current_focus"])
def test_close_that_leaves_popup_visible_does_not_tap_icon_or_repeat_close(
    android, entry
):
    device, responses, _ = android
    responses.close_works = False
    with pytest.raises(DeviceRecoveryError):
        getattr(device, entry)()
    assert responses.commands.count(CLOSE_COMMAND) == 1
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("entry", ["launch", "check_current_focus"])
@pytest.mark.parametrize(
    "data",
    [b"broken hierarchy", b" " * (1024 * 1024 + 1)],
    ids=["malformed", "oversized"],
)
def test_unreadable_popup_state_blocks_further_game_input(android, entry, data):
    device, responses, _ = android
    responses.dump_override = data
    with pytest.raises(DeviceRecoveryError):
        getattr(device, entry)()
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("entry", ["launch", "check_current_focus"])
def test_cancelled_popup_read_does_not_close_or_launch(android, entry):
    device, responses, _ = android
    responses.dump_error = MowerExit()
    with pytest.raises(MowerExit):
        getattr(device, entry)()
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands
    device._connect_once.assert_not_called()


def test_cancellation_after_observation_does_not_send_close_click(android):
    device, responses, _ = android

    def run(command):
        result = responses.run(command)
        if command == DUMP_COMMAND:
            config.stop_mower.set()
        return result

    device.client.run.side_effect = run
    with pytest.raises(MowerExit):
        device.launch()
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("entry", ["launch", "check_current_focus"])
def test_cancelled_close_verification_does_not_tap_game_icon(android, entry):
    device, responses, _ = android
    responses.verification_error = MowerExit()
    with pytest.raises(MowerExit):
        getattr(device, entry)()
    assert responses.commands.count(CLOSE_COMMAND) == 1
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("entry", ["launch", "check_current_focus"])
def test_uncertain_close_input_is_not_replayed_or_followed_by_icon_tap(android, entry):
    device, responses, _ = android
    responses.close_error = ConnectionError("close input acknowledgement lost")
    with pytest.raises((TouchFailure, DeviceRecoveryError)):
        getattr(device, entry)()
    assert responses.commands.count(CLOSE_COMMAND) == 1
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    device._connect_once.assert_not_called()
    with pytest.raises((TouchFailure, DeviceRecoveryError)):
        getattr(device, entry)()
    assert responses.commands.count(CLOSE_COMMAND) == 1
    assert ICON_COMMAND not in responses.commands


def test_direct_foreground_restore_must_confirm_game_focus(android):
    device, responses, _ = android
    responses.running = "main"
    responses.start_works = False
    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()
    assert CLOSE_COMMAND not in responses.commands
    assert DUMP_COMMAND not in responses.commands
    assert responses.commands.count(responses.start_command) == 1
    assert ICON_COMMAND not in responses.commands
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("remaining", ["pic", "member", "close"])
def test_single_remaining_ad_control_blocks_icon_tap(android, remaining):
    device, responses, _ = android
    tree = popup_tree(responses.popup_xml)
    picture = node_by_id(tree, "pic")
    parent = next(parent for parent in tree.iter() if picture in list(parent))
    for child in list(parent):
        if child.get("resource-id") != f"app.lawnchair:id/{remaining}":
            parent.remove(child)
    responses.dump_override = ET.tostring(tree)
    with pytest.raises(DeviceRecoveryError):
        device.launch()
    assert CLOSE_COMMAND not in responses.commands
    assert ICON_COMMAND not in responses.commands
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("ad_visible", [True, False], ids=["closed-ad", "no-ad"])
def test_focus_race_to_another_application_blocks_tap_foreground_recovery(
    android, ad_visible
):
    device, responses, _ = android
    responses.visible = ad_visible

    def run(command):
        result = responses.run(command)
        if command == (CLOSE_COMMAND if ad_visible else DUMP_COMMAND):
            responses.focus = "com.example.other/.Activity"
        return result

    device.client.run.side_effect = run
    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()
    assert responses.commands.count(CLOSE_COMMAND) == int(ad_visible)
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    assert responses.custom_command not in responses.commands
    device._connect_once.assert_not_called()


def test_failed_post_close_focus_read_does_not_replay_close_or_reconnect(android):
    device, responses, _ = android
    responses.close_works = False
    device._connect_once.side_effect = None
    device._connect_once.return_value = None
    close_sent = False
    failure_sent = False

    def run(command):
        nonlocal close_sent, failure_sent
        if (
            close_sent
            and not failure_sent
            and command == "dumpsys window | grep mCurrentFocus"
        ):
            failure_sent = True
            responses.commands.append(command)
            raise ConnectionError("post-close focus acknowledgement lost")
        result = responses.run(command)
        if command == CLOSE_COMMAND:
            close_sent = True
        return result

    device.client.run.side_effect = run
    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()
    assert failure_sent
    assert responses.commands.count(CLOSE_COMMAND) == 1
    assert ICON_COMMAND not in responses.commands
    assert responses.start_command not in responses.commands
    device._connect_once.assert_not_called()
