from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from arknights_mower.utils import config
from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.device.device import Device
from arknights_mower.utils.device.io_budget import device_io_budget, io_timeout
from arknights_mower.utils.device.mumu_popup import UI_DUMP_COMMAND
from arknights_mower.utils.device.recovery import DeviceRecoveryError
from arknights_mower.utils.device.touch_backend import TouchFailure

CLOSE_SYSTEM_DIALOGS = "am broadcast -a android.intent.action.CLOSE_SYSTEM_DIALOGS"
CLOSE_SYSTEM_UI = "input tap 959 565"
SYSTEM_UI_ANR = "Application Not Responding: com.android.systemui"
LAUNCHER = "com.mumu.launcher/com.mumu.launcher.Launcher"
SDK_COMMAND = "getprop ro.build.version.sdk"
USER_COMMAND = "am get-current-user"
GLOBAL_CONFIG_COMMAND = "dumpsys activity activities 2>/dev/null | grep mGlobalConfig"
THEME_COMMAND = "dumpsys activity service com.android.systemui/.SystemUIService ThemeOverlayController"


def error_dialog(*, anr=True, enabled=True):
    wait = (
        '<node resource-id="android:id/aerr_wait" package="android" '
        'class="android.widget.Button" enabled="true" clickable="true" '
        'bounds="[500,607][1418,689]" />'
        if anr
        else ""
    )
    return (
        '<hierarchy rotation="0"><node package="android" '
        'class="android.widget.FrameLayout" bounds="[460,417][1459,730]">'
        '<node resource-id="android:id/alertTitle" package="android" '
        'class="android.widget.TextView" bounds="[503,450][1418,500]" />'
        '<node resource-id="android:id/aerr_close" package="android" '
        f'class="android.widget.Button" enabled="{str(enabled).lower()}" '
        'clickable="true" bounds="[500,524][1418,606]" />'
        f"{wait}</node></hierarchy>"
    ).encode()


class SystemUiRecoveryResponses:
    def __init__(self, device, clock):
        self.device = device
        self.clock = clock
        self.sdk = b"30\n"
        self.monet_enabled = True
        self.assets_seq = 7
        self.theme_states = [(False, False, "ColorScheme{ready}", 8)]
        self.theme_observations = []
        self.theme_output_override = None
        self.current_user = b"0\n"
        self.system_colors = ["{0=[WallpaperColors: ff000000 h: 0]}"]
        self.fabricated_overlays = False
        self.overlay_settings = b"null\n"
        self.global_config_override = None
        self.global_config_states = None
        self.theme_output_states = None
        self.include_color_scheme = True
        self.ui_states = None
        self.focus_before_click = None
        self.cancel_after_dump = False
        self.dump_error = None
        self.focus = SYSTEM_UI_ANR
        self.old_pid = b"1492\n"
        self.poll_states = [(b"4031\n", LAUNCHER)]
        self.observations = []
        self.close_sent = False
        self.close_error = None
        self.poll_error = None
        self.cancel_after_close = False
        self.restore_works = True
        self.game_running = True
        self.after_launch_ready_at = None
        self.after_launch_focus = None
        self.cancel_game_wait_at = None
        self.game_wait_error = None
        self.launch_started = False
        self.commands = []

    @property
    def game_focus(self):
        return f"{self.device.game_package}/{config.APP_ACTIVITY_NAME}"

    def run(self, command):
        io_timeout(30)
        self.commands.append(command)
        if command == SDK_COMMAND:
            return self.sdk
        if command == USER_COMMAND:
            return self.current_user
        if command.startswith("settings --user "):
            return self.overlay_settings
        if command == GLOBAL_CONFIG_COMMAND:
            if self.global_config_states:
                output = self.global_config_states[0]
                if len(self.global_config_states) > 1:
                    self.global_config_states.pop(0)
                return output
            if self.global_config_override is not None:
                return self.global_config_override
            if self.assets_seq == 0:
                return b"mGlobalConfiguration={land}\n"
            return f"mGlobalConfiguration={{land as.{self.assets_seq}}}\n".encode()
        if command == THEME_COMMAND:
            if self.theme_output_states:
                result = self.theme_output_states[0]
                if len(self.theme_output_states) > 1:
                    self.theme_output_states.pop(0)
                return result
            if self.theme_output_override is not None:
                return self.theme_output_override
            if not self.monet_enabled:
                return b"mIsMonetEnabled=false\n"
            needs, deferred, scheme, self.assets_seq = self.theme_states[0]
            if len(self.theme_states) > 1:
                self.theme_states.pop(0)
            self.theme_observations.append((needs, deferred, scheme, self.assets_seq))
            colors = self.system_colors[0]
            if len(self.system_colors) > 1:
                self.system_colors.pop(0)
            return (
                "ThemeOverlayController:\n"
                "  mIsMonetEnabled=true\n"
                f"  mSystemColors={colors}\n"
                f"  mNeedsOverlayCreation={str(needs).lower()}\n"
                f"  mDeferredThemeEvaluation={str(deferred).lower()}\n"
                + (
                    "  mSecondaryOverlay=android.content.om.FabricatedOverlay@47c9560\n"
                    "  mNeutralOverlay=android.content.om.FabricatedOverlay@7bd2b41\n"
                    if self.fabricated_overlays
                    else ""
                )
                + (
                    f"  mColorScheme={scheme or 'null'}\n"
                    if self.include_color_scheme
                    else ""
                )
            ).encode()
        if command == UI_DUMP_COMMAND:
            if self.dump_error is not None:
                raise self.dump_error
            if self.ui_states is not None:
                data = self.ui_states[0]
                if len(self.ui_states) > 1:
                    self.ui_states.pop(0)
            else:
                data = error_dialog(anr=self.focus == SYSTEM_UI_ANR)
            if self.focus_before_click is not None:
                self.focus = self.focus_before_click
            if self.cancel_after_dump:
                config.stop_mower.set()
            return data
        if command == "dumpsys window | grep mCurrentFocus":
            if self.launch_started and self.game_wait_error is not None:
                raise self.game_wait_error
            if (
                self.launch_started
                and self.cancel_game_wait_at is not None
                and self.clock[0] >= self.cancel_game_wait_at
            ):
                config.stop_mower.set()
            if (
                self.launch_started
                and self.after_launch_ready_at is not None
                and self.clock[0] >= self.after_launch_ready_at
            ):
                self.focus = self.game_focus
            return f"mCurrentFocus=Window{{123 u0 {self.focus}}}\n".encode()
        if command == "pidof com.android.systemui":
            if not self.close_sent:
                return self.old_pid
            if self.poll_error is not None:
                raise self.poll_error
            pid, self.focus = self.poll_states[0]
            if len(self.poll_states) > 1:
                self.poll_states.pop(0)
            self.observations.append((pid, self.focus))
            return pid
        if command == CLOSE_SYSTEM_UI:
            self.close_sent = True
            if self.close_error is not None:
                raise self.close_error
            if self.cancel_after_close:
                config.stop_mower.set()
            return b""
        if command == f"ps -A | grep {self.device.game_package} | grep -v grep":
            if not self.game_running:
                return b""
            return f"u0_a39 31745 1137 S {self.device.game_package}\n".encode()
        if command == f"am start -n {self.game_focus}":
            self.launch_started = True
            if self.after_launch_focus is not None:
                self.focus = self.after_launch_focus
            elif self.after_launch_ready_at is not None:
                self.focus = "null"
            elif self.restore_works:
                self.focus = self.game_focus
            return b"Starting: Intent\n"
        raise AssertionError(f"Unexpected device command: {command}")


@pytest.fixture
def system_ui_recovery(monkeypatch):
    conf = config.conf.model_copy(deep=True)
    conf.tap_to_launch_game.mode = "adb"
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(config, "stop_mower", Event())
    clock = [0.0]
    monkeypatch.setattr(
        "arknights_mower.utils.device.device.time",
        SimpleNamespace(monotonic=lambda: clock[0]),
    )

    def sleep(seconds):
        if config.stop_mower.is_set():
            raise MowerExit
        clock[0] += seconds

    def budget_sleep(seconds):
        sleep(0)
        clock[0] += io_timeout(seconds)
        io_timeout(0)

    monkeypatch.setattr("arknights_mower.utils.device.device.csleep", sleep)
    monkeypatch.setattr(
        "arknights_mower.utils.device.device.budget_sleep", budget_sleep
    )
    device = object.__new__(Device)
    device._profile = conf.device.model_copy(
        update={"game_package": "com.hypergryph.arknights"}
    )
    device._connect_once = MagicMock(
        side_effect=AssertionError("Offline ANR tests must not reconnect a device")
    )
    responses = SystemUiRecoveryResponses(device, clock)
    device.client = MagicMock()
    device.client.run.side_effect = responses.run
    device.client.cmd.side_effect = lambda args: responses.run(args[1])
    return device, responses, clock


def test_system_ui_close_clicks_only_verified_error_dialog(system_ui_recovery):
    device, responses, _ = system_ui_recovery

    assert device.check_current_focus() is True

    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert CLOSE_SYSTEM_DIALOGS not in responses.commands
    assert responses.commands.index(UI_DUMP_COMMAND) < responses.commands.index(
        CLOSE_SYSTEM_UI
    )
    device.client.cmd.assert_called_once_with(["shell", UI_DUMP_COMMAND])
    assert UI_DUMP_COMMAND not in [
        call.args[0] for call in device.client.run.call_args_list
    ]


def test_system_ui_close_waits_for_initially_disabled_button(system_ui_recovery):
    device, responses, clock = system_ui_recovery
    responses.ui_states = [error_dialog(enabled=False), error_dialog()]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.2)
    assert responses.commands.count(UI_DUMP_COMMAND) == 2
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize(("parent_timeout", "expected_elapsed"), [(30, 15), (1, 1)])
def test_disabled_error_button_shares_local_and_parent_deadlines(
    system_ui_recovery, parent_timeout, expected_elapsed
):
    device, responses, clock = system_ui_recovery
    responses.ui_states = [error_dialog(enabled=False)]

    def remaining():
        seconds = parent_timeout - clock[0]
        if seconds <= 0:
            raise TimeoutError("Parent device deadline expired")
        return seconds

    with pytest.raises(DeviceRecoveryError):
        with device_io_budget(remaining):
            device.check_current_focus()

    assert clock[0] == pytest.approx(expected_elapsed)
    assert CLOSE_SYSTEM_UI not in responses.commands
    assert not any(command.startswith("am start") for command in responses.commands)


@pytest.mark.parametrize(
    "window_title",
    [
        LAUNCHER,
        "Application Error: com.example.other",
        "Application Error: com.android.systemui",
    ],
)
def test_changed_error_focus_prevents_close_click(system_ui_recovery, window_title):
    device, responses, _ = system_ui_recovery
    responses.focus_before_click = window_title

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert CLOSE_SYSTEM_UI not in responses.commands
    assert not any(command.startswith("am start") for command in responses.commands)


@pytest.mark.parametrize("data", [b"", b"<hierarchy/>", b"not XML"])
def test_unconfirmed_error_hierarchy_prevents_close_click(system_ui_recovery, data):
    device, responses, _ = system_ui_recovery
    responses.ui_states = [data]

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert CLOSE_SYSTEM_UI not in responses.commands
    device._connect_once.assert_not_called()


def test_cancel_after_error_dump_prevents_close_click(system_ui_recovery):
    device, responses, _ = system_ui_recovery
    responses.cancel_after_dump = True

    with pytest.raises(MowerExit):
        device.check_current_focus()

    assert CLOSE_SYSTEM_UI not in responses.commands


def test_system_ui_recovery_observes_game_foreground_without_relaunch(
    system_ui_recovery,
):
    device, responses, _ = system_ui_recovery
    responses.poll_states = [(b"4031\n", responses.game_focus)]

    assert device.check_current_focus() is True

    assert not any(command.startswith("am start") for command in responses.commands)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize(
    "window_title",
    ["Application Error: com.example.other", SYSTEM_UI_ANR],
)
def test_new_error_after_restart_confirmation_prevents_game_restore(
    system_ui_recovery, window_title
):
    device, responses, _ = system_ui_recovery

    def recovered():
        responses.focus = window_title

    device._close_system_ui_error = MagicMock(side_effect=recovered)

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert not any(command.startswith("am start") for command in responses.commands)


def test_system_ui_recovery_checks_advertisement_on_fresh_launcher_focus(
    system_ui_recovery,
):
    device, responses, _ = system_ui_recovery
    launcher = "app.lawnchair/app.lawnchair.LawnchairLauncher"
    responses.poll_states = [(b"4031\n", launcher)]

    def close_ad(focus):
        assert focus == launcher
        responses.focus = responses.game_focus
        return True

    device._dismiss_mumu_startup_ad = MagicMock(side_effect=close_ad)

    assert device.check_current_focus() is True

    device._dismiss_mumu_startup_ad.assert_called_once_with(launcher)
    assert not any(command.startswith("am start") for command in responses.commands)


def test_system_ui_recovery_waits_for_observed_theme_work(
    system_ui_recovery,
):
    device, responses, _ = system_ui_recovery
    responses.sdk = b"32\n"
    expected = [
        (True, True, None, 7),
        (False, False, "ColorScheme{ready}", 7),
    ]
    responses.theme_states = expected.copy()

    assert device.check_current_focus() is True

    assert responses.theme_observations == expected
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(GLOBAL_CONFIG_COMMAND) == 1
    assert responses.commands.index(f"am start -n {responses.game_focus}") > max(
        index
        for index, command in enumerate(responses.commands)
        if command == THEME_COMMAND
    )
    device._connect_once.assert_not_called()


def test_default_monet_waits_for_colors_then_applied_fabricated_resources(
    system_ui_recovery,
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.assets_seq = 15
    responses.fabricated_overlays = True
    responses.system_colors = ["{}", "{0=[WallpaperColors: ff000000 h: 0]}"]
    responses.theme_states = [
        (False, False, None, 15),
        (False, False, "ColorScheme{ready}", 15),
        (False, False, "ColorScheme{ready}", 16),
    ]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.4)
    assert len(responses.theme_observations) == 3
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.index(GLOBAL_CONFIG_COMMAND) < responses.commands.index(
        CLOSE_SYSTEM_UI
    )
    start = responses.commands.index(f"am start -n {responses.game_focus}")
    assert start > max(
        i
        for i, command in enumerate(responses.commands)
        if command == GLOBAL_CONFIG_COMMAND
    )


def test_default_monet_accepts_zero_assets_baseline_without_as_token(
    system_ui_recovery,
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.assets_seq = 0
    responses.fabricated_overlays = True
    responses.theme_states = [
        (False, False, "ColorScheme{ready}", 0),
        (False, False, "ColorScheme{ready}", 1),
    ]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.2)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize("field", ["mGlobalConfig", "mGlobalConfiguration"])
@pytest.mark.parametrize("baseline", [0, 15])
def test_default_monet_accepts_complete_global_configuration_with_nested_window_config(
    system_ui_recovery, baseline, field
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.fabricated_overlays = True

    def configuration(sequence):
        assets = f"as.{sequence} " if sequence else ""
        return (
            f"          {field}={{1.0 ?mcc?mnc [zh_CN_#Hans] ldltr sw617dp "
            "w1097dp h593dp 295dpi lrg long land night finger -keyb/v/v dpad/v "
            "winConfig={ mBounds=Rect(0, 0 - 1920, 1080) "
            "mAppBounds=Rect(0, 0 - 1920, 1080) "
            "mMaxBounds=Rect(0, 0 - 1920, 1080) mWindowingMode=fullscreen "
            "mDisplayWindowingMode=fullscreen mActivityType=undefined "
            "mAlwaysOnTop=undefined mRotation=ROTATION_90} "
            f"{assets}s.205 fontWeightAdjustment=0}}\n"
        ).encode()

    responses.global_config_states = [
        configuration(baseline),
        configuration(baseline),
        configuration(baseline + 1),
    ]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.2)
    assert responses.commands.count(GLOBAL_CONFIG_COMMAND) == 3
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1


@pytest.mark.parametrize(
    "custom_palette",
    [
        b'{"android.theme.customization.system_palette":"com.theme.static"}',
        b'{"android.theme.customization.accent_color":"ff0000"}',
    ],
)
def test_custom_palettes_do_not_require_generated_resource_sequence_advance(
    system_ui_recovery, custom_palette
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.overlay_settings = custom_palette
    responses.fabricated_overlays = True
    responses.theme_states = [(False, False, "ColorScheme{ready}", 7)]

    assert device.check_current_focus() is True

    assert clock[0] == 0
    assert responses.commands.count(GLOBAL_CONFIG_COMMAND) == 1


@pytest.mark.parametrize("colors", ["{0=null}", "{0=[WallpaperColors: ff000000 h: 0]}"])
def test_absent_wallpaper_or_no_fabricated_overlay_does_not_require_assets_advance(
    system_ui_recovery, colors
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.system_colors = [colors]
    scheme = None if colors == "{0=null}" else "ColorScheme{ready}"
    responses.theme_states = [(False, False, scheme, 7)]

    assert device.check_current_focus() is True

    assert clock[0] == 0
    assert responses.commands.count(GLOBAL_CONFIG_COMMAND) == 1


def test_wallpaper_color_fetch_waits_for_current_user_and_accepts_explicit_null(
    system_ui_recovery,
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.current_user = b"10\n"
    responses.system_colors = [
        "{0=[WallpaperColors: ff000000 h: 0]}",
        "{0=[WallpaperColors: ff000000 h: 0], 10=null}",
    ]
    responses.theme_states = [(False, False, None, 7)]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.2)
    assert responses.commands.count(THEME_COMMAND) == 2
    assert (
        "settings --user 10 get secure theme_customization_overlay_packages"
        in responses.commands
    )


def test_unrecognized_wallpaper_dump_does_not_clear_observed_unread_colors(
    system_ui_recovery,
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.system_colors = ["{}", "unsupported", "{0=null}"]
    responses.theme_states = [(False, False, None, 7)]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.4)
    assert responses.commands.count(THEME_COMMAND) == 3


@pytest.mark.parametrize(("parent_timeout", "expected_elapsed"), [(30, 15), (1, 1)])
def test_pending_fabricated_resources_share_system_ui_and_parent_deadlines(
    system_ui_recovery, parent_timeout, expected_elapsed
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.fabricated_overlays = True
    responses.theme_states = [(False, False, "ColorScheme{ready}", 7)]

    def remaining():
        seconds = parent_timeout - clock[0]
        if seconds <= 0:
            raise TimeoutError("Parent device deadline expired")
        return seconds

    with pytest.raises(DeviceRecoveryError):
        with device_io_budget(remaining):
            device.check_current_focus()

    assert clock[0] == pytest.approx(expected_elapsed)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert not any(command.startswith("am start") for command in responses.commands)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"permission denied\n",
        b"as.7\n",
        b"mGlobalConfig={land winConfig={mRotation=ROTATION_90}\n",
        b"mGlobalConfig={land winConfig={mRotation=ROTATION_90}}}\n",
        b"mGlobalConfig={land} winConfig={mRotation=ROTATION_90}\n",
        b"mGlobalConfig={land winConfig={mRotation=ROTATION_90}} trailing\n",
        b"mGlobalConfig={}\n",
        b"mGlobalConfig={land as.7 as.8}\n",
        b"mGlobalConfig={land as.invalid}\n",
        b"mGlobalConfig={land as.7}\nmGlobalConfig={land winConfig={\n",
    ],
)
def test_unknown_global_configuration_is_not_treated_as_zero_for_fabricated_resources(
    system_ui_recovery, data
):
    device, responses, _ = system_ui_recovery
    responses.sdk = b"32\n"
    responses.fabricated_overlays = True
    responses.global_config_override = data

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert not any(command.startswith("am start") for command in responses.commands)


def test_assets_sequence_uses_top_level_configuration_field(system_ui_recovery):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.fabricated_overlays = True
    responses.global_config_states = [
        b"mGlobalConfig={land winConfig={as.99} as.15 s.205}\n",
        b"mGlobalConfig={land winConfig={as.100} as.15 s.206}\n",
        b"mGlobalConfig={land winConfig={as.100} as.16 s.213}\n",
    ]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.2)
    assert responses.commands.count(GLOBAL_CONFIG_COMMAND) == 3
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1


@pytest.mark.parametrize("sdk", [29, 30])
def test_pre_monet_system_ui_recovery_skips_private_theme_dump(system_ui_recovery, sdk):
    device, responses, _ = system_ui_recovery
    responses.sdk = f"{sdk}\n".encode()

    assert device.check_current_focus() is True

    assert THEME_COMMAND not in responses.commands
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


def test_disabled_monet_does_not_require_assets_sequence_change(system_ui_recovery):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.monet_enabled = False

    assert device.check_current_focus() is True

    assert responses.assets_seq == 7
    assert clock[0] == 0
    assert responses.commands.count(THEME_COMMAND) == 1
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize(
    "pending",
    [
        (True, False, "ColorScheme{ready}", 8),
        (False, True, "ColorScheme{ready}", 8),
        (False, False, None, 8),
    ],
)
def test_monet_recovery_requires_completed_flags_and_color_scheme(
    system_ui_recovery, pending
):
    device, responses, _ = system_ui_recovery
    responses.sdk = b"32\n"
    ready = (False, False, "ColorScheme{ready}", 8)
    responses.theme_states = [pending, ready]

    assert device.check_current_focus() is True

    assert responses.theme_observations == [pending, ready]
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize(("parent_timeout", "expected_elapsed"), [(60, 15), (1, 1)])
def test_pending_theme_work_shares_system_ui_and_parent_deadlines(
    system_ui_recovery, parent_timeout, expected_elapsed
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    responses.theme_states = [(True, False, "ColorScheme{ready}", 7)]

    def remaining():
        seconds = parent_timeout - clock[0]
        if seconds <= 0:
            raise TimeoutError("Parent device deadline expired")
        return seconds

    with pytest.raises(DeviceRecoveryError):
        with device_io_budget(remaining):
            device.check_current_focus()

    assert clock[0] == pytest.approx(expected_elapsed)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert not any(command.startswith("am start") for command in responses.commands)
    device._connect_once.assert_not_called()


@pytest.mark.parametrize(
    "data", [b"", b"Can't find service\n", b"mIsMonetEnabled=unknown\n"]
)
def test_unsupported_private_theme_dump_does_not_prevent_recovery(
    system_ui_recovery, data
):
    device, responses, _ = system_ui_recovery
    responses.sdk = b"32\n"
    responses.theme_output_override = data

    assert device.check_current_focus() is True

    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


def test_android_twelve_theme_without_color_scheme_or_assets_sequence_is_supported(
    system_ui_recovery,
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"31\n"
    responses.system_colors = ["null"]
    responses.assets_seq = 0
    responses.include_color_scheme = False
    responses.theme_states = [(False, False, None, 0)]

    assert device.check_current_focus() is True

    assert clock[0] == 0
    assert GLOBAL_CONFIG_COMMAND not in responses.commands
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize("pending_field", ["mNeedsOverlayCreation", "mColorScheme"])
def test_missing_theme_fields_do_not_erase_observed_pending_work(
    system_ui_recovery, pending_field
):
    device, responses, clock = system_ui_recovery
    responses.sdk = b"32\n"
    pending = "null" if pending_field == "mColorScheme" else "true"
    ready = "ColorScheme{ready}" if pending_field == "mColorScheme" else "false"
    responses.theme_output_states = [
        (
            "mIsMonetEnabled=true\nmSystemColors={0=[WallpaperColors: ff000000 h: 0]}\n"
            f"{pending_field}={pending}\n"
        ).encode(),
        b"Can't find service\n",
        f"mIsMonetEnabled=true\n{pending_field}={ready}\n".encode(),
    ]

    assert device.check_current_focus() is True

    assert clock[0] == pytest.approx(0.4)
    assert responses.commands.count(THEME_COMMAND) == 3
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1


@pytest.mark.parametrize("game_running", [True, False])
def test_system_ui_recovery_accepts_game_foreground_after_fourteen_seconds(
    system_ui_recovery, game_running
):
    device, responses, clock = system_ui_recovery
    responses.game_running = game_running
    responses.after_launch_ready_at = 14

    assert device.check_current_focus() is True

    assert responses.focus == responses.game_focus
    assert 14 <= clock[0] <= 14.21
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    assert not any(
        command.startswith("am force-stop") for command in responses.commands
    )
    device._connect_once.assert_not_called()


@pytest.mark.parametrize(("parent_timeout", "expected_elapsed"), [(60, 30), (1, 1)])
def test_system_ui_game_wait_preserves_local_and_parent_deadlines(
    system_ui_recovery, parent_timeout, expected_elapsed
):
    device, responses, clock = system_ui_recovery
    responses.after_launch_ready_at = 40

    def remaining():
        seconds = parent_timeout - clock[0]
        if seconds <= 0:
            raise TimeoutError("Parent device deadline expired")
        return seconds

    with pytest.raises(DeviceRecoveryError):
        with device_io_budget(remaining):
            device.check_current_focus()

    assert clock[0] == pytest.approx(expected_elapsed)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


def test_cancel_during_system_ui_game_wait_does_not_replay_launch(system_ui_recovery):
    device, responses, clock = system_ui_recovery
    responses.after_launch_ready_at = 14
    responses.cancel_game_wait_at = 0.4

    with pytest.raises(MowerExit):
        device.check_current_focus()

    assert clock[0] <= 0.61
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


@pytest.mark.parametrize(
    "window_title",
    [
        "Application Error: com.hypergryph.arknights",
        "Application Not Responding: com.example.other",
        "Application Error: com.android.systemui",
    ],
)
def test_new_error_during_system_ui_game_wait_prevents_repeated_launch(
    system_ui_recovery, window_title
):
    device, responses, clock = system_ui_recovery
    responses.after_launch_focus = window_title

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert clock[0] == 0
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("error", [MowerExit(), ConnectionError("offline")])
def test_failed_system_ui_game_observation_does_not_replay_launch(
    system_ui_recovery, error
):
    device, responses, _ = system_ui_recovery
    responses.game_wait_error = error
    expected = MowerExit if isinstance(error, MowerExit) else DeviceRecoveryError

    with pytest.raises(expected) as caught:
        device.check_current_focus()

    if isinstance(error, MowerExit):
        assert caught.value is error
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("game_running", [True, False])
@pytest.mark.parametrize("ready_after", [0, 14])
def test_ordinary_game_foreground_restore_waits_for_actual_window(
    system_ui_recovery, game_running, ready_after
):
    device, responses, clock = system_ui_recovery
    responses.focus = LAUNCHER
    responses.game_running = game_running
    responses.after_launch_ready_at = ready_after

    assert device.check_current_focus() is True

    assert ready_after <= clock[0] <= ready_after + 0.21
    assert CLOSE_SYSTEM_UI not in responses.commands
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("game_running", [True, False])
def test_ordinary_game_window_timeout_does_not_replay_start(
    system_ui_recovery, game_running
):
    device, responses, clock = system_ui_recovery
    responses.focus = LAUNCHER
    responses.game_running = game_running
    responses.after_launch_ready_at = 40

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert clock[0] == pytest.approx(30)
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("game_process", ["main", "pushcore", "absent"])
@pytest.mark.parametrize(
    ("error_title", "recovery_command"),
    [
        pytest.param(
            "Application Not Responding: com.mumu.acc",
            "am force-stop com.mumu.acc",
            id="mumu",
        ),
        pytest.param(
            "Application Not Responding: com.android.systemui",
            CLOSE_SYSTEM_UI,
            id="systemui_anr",
        ),
        pytest.param(
            "Application Error: com.android.systemui",
            CLOSE_SYSTEM_UI,
            id="systemui_error",
        ),
    ],
)
def test_known_anr_does_not_block_foreground_recovery(
    game_process, error_title, recovery_command
):
    device = object.__new__(Device)
    device.client = MagicMock()
    game_focus = f"{device.game_package}/{config.APP_ACTIVITY_NAME}"
    focus = error_title
    closed = False

    def run(command):
        nonlocal focus, closed
        if command == SDK_COMMAND:
            return b"30\n"
        if command == GLOBAL_CONFIG_COMMAND:
            return b"mGlobalConfiguration={land as.7}\n"
        if command == UI_DUMP_COMMAND:
            return error_dialog(anr=error_title == SYSTEM_UI_ANR)
        if command == "dumpsys window | grep mCurrentFocus":
            return f"  mCurrentFocus=Window{{13b999 u0 {focus}}}\n".encode()
        if command == f"ps -A | grep {device.game_package} | grep -v grep":
            if game_process == "absent":
                return b""
            suffix = ":pushcore" if game_process == "pushcore" else ""
            return f"u0_a39 31745 1137 S {device.game_package}{suffix}\n".encode()
        if command == "pidof com.android.systemui":
            return b"4031\n" if closed else b"1492\n"
        if command == recovery_command:
            closed = True
            focus = "com.mumu.launcher/com.mumu.launcher.Launcher"
            return b""
        if command == f"am start -n {game_focus}":
            if not focus.startswith(
                ("Application Not Responding:", "Application Error:")
            ):
                focus = game_focus
            return b"Starting: Intent\n"
        raise AssertionError(f"Unexpected device command: {command}")

    device.client.run.side_effect = run
    device.client.cmd.side_effect = lambda args: run(args[1])
    with (
        patch.object(Device, "recover", lambda self, operation: operation()),
        patch("arknights_mower.utils.device.device.csleep"),
        patch.object(config.conf.tap_to_launch_game, "mode", "adb"),
    ):
        assert device.check_current_focus() is True
        assert device.current_focus() == game_focus
        assert device.check_current_focus() is False

    commands = [entry.args[0] for entry in device.client.run.call_args_list]
    assert commands.count(recovery_command) == 1
    assert commands.count(f"am start -n {game_focus}") == 1
    assert f"am force-stop {device.game_package}" not in commands
    assert f"am crash {device.game_package}" not in commands


@pytest.mark.parametrize(
    "window_title",
    [
        "Application Not Responding: com.mumu.acc",
        "Application Not Responding: com.android.systemui",
        "Application Error: com.android.systemui",
        "Application Error: com.example.other",
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
        "com.android.systemui/.MainActivity",
        "Application Not Responding: com.example.other",
        "Application Not Responding: com.mumu.acc.other",
        "Application Not Responding: com.android.systemui.other",
        "Application Error: com.android.systemui.other",
        "Application Error: com.example.other",
        "Application Error: com.mumu.acc",
    ],
)
def test_other_windows_do_not_run_anr_recovery_commands(window_title):
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
def test_failed_mumu_anr_command_does_not_continue_foreground_recovery(error):
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


def test_system_ui_restart_waits_for_new_process_and_activity(system_ui_recovery):
    device, responses, clock = system_ui_recovery
    expected = [
        (b"1492\n", SYSTEM_UI_ANR),
        (b"", "null"),
        (b"4031\n", "null"),
        (b"4031\n", LAUNCHER),
    ]
    responses.poll_states = expected.copy()

    assert device.check_current_focus() is True

    assert responses.observations == expected
    assert clock[0] == pytest.approx(0.6)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    start_command = f"am start -n {responses.game_focus}"
    assert responses.commands.count(start_command) == 1
    assert responses.commands.index(start_command) > max(
        index
        for index, command in enumerate(responses.commands)
        if command == "pidof com.android.systemui"
    )
    device._connect_once.assert_not_called()


@pytest.mark.parametrize(("parent_timeout", "expected_elapsed"), [(30, 15), (1, 1)])
def test_system_ui_restart_preserves_local_and_parent_deadlines(
    system_ui_recovery, parent_timeout, expected_elapsed
):
    device, responses, clock = system_ui_recovery
    responses.poll_states = [(b"1492\n", SYSTEM_UI_ANR)]

    def remaining():
        seconds = parent_timeout - clock[0]
        if seconds <= 0:
            raise TimeoutError("Parent device deadline expired")
        return seconds

    with pytest.raises(DeviceRecoveryError):
        with device_io_budget(remaining):
            device.check_current_focus()

    assert clock[0] == pytest.approx(expected_elapsed)
    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert not any(command.startswith("am start") for command in responses.commands)
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("stage", ["dump_error", "close_error", "poll_error"])
@pytest.mark.parametrize("error", [MowerExit(), ConnectionError("offline")])
def test_system_ui_failure_does_not_replay_close_click(
    system_ui_recovery, stage, error
):
    device, responses, _ = system_ui_recovery
    setattr(responses, stage, error)
    expected = MowerExit if isinstance(error, MowerExit) else DeviceRecoveryError

    with pytest.raises(expected) as caught:
        device.check_current_focus()

    if isinstance(error, MowerExit):
        assert caught.value is error
    elif stage == "close_error":
        assert isinstance(caught.value, TouchFailure)
        assert caught.value.delivery_unknown is True
        assert caught.value.transport == "adb"
    assert responses.commands.count(CLOSE_SYSTEM_UI) == (stage != "dump_error")
    assert not any(command.startswith("am start") for command in responses.commands)
    device._connect_once.assert_not_called()


def test_cancel_after_system_ui_close_prevents_game_restore(system_ui_recovery):
    device, responses, _ = system_ui_recovery
    responses.cancel_after_close = True

    with pytest.raises(MowerExit):
        device.check_current_focus()

    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert not any(command.startswith("am start") for command in responses.commands)
    device._connect_once.assert_not_called()


def test_system_ui_restart_still_requires_confirmed_game_foreground(system_ui_recovery):
    device, responses, _ = system_ui_recovery
    responses.restore_works = False

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert responses.commands.count(f"am start -n {responses.game_focus}") == 1
    device._connect_once.assert_not_called()


@pytest.mark.parametrize("old_pid", [b"", b"pidof: unavailable\n"])
def test_unconfirmed_system_ui_process_prevents_close_click(
    system_ui_recovery, old_pid
):
    device, responses, _ = system_ui_recovery
    responses.old_pid = old_pid

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert CLOSE_SYSTEM_UI not in responses.commands
    assert not any(command.startswith("am start") for command in responses.commands)
    device._connect_once.assert_not_called()


@pytest.mark.parametrize(
    "window_title",
    [
        "Application Error: com.example.other",
        "Application Not Responding: com.example.other",
    ],
)
def test_other_error_after_system_ui_restart_prevents_game_restore(
    system_ui_recovery, window_title
):
    device, responses, _ = system_ui_recovery
    responses.poll_states = [(b"4031\n", window_title)]

    with pytest.raises(DeviceRecoveryError):
        device.check_current_focus()

    assert responses.commands.count(CLOSE_SYSTEM_UI) == 1
    assert not any(command.startswith("am start") for command in responses.commands)
    device._connect_once.assert_not_called()
