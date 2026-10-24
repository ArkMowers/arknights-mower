"""Android-owned settings remain authoritative through configuration boundaries."""

import copy
import sys
from io import BytesIO
from types import ModuleType
from unittest.mock import Mock
from zipfile import ZipFile

import pytest
import yaml
from yamlcore import CoreLoader

from arknights_mower.utils import config, config_backup
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.config.device_profile import DeviceProfile


@pytest.fixture
def android_settings(monkeypatch):
    owned = {
        "adb": "Android",
        "maa_adb_path": "Android",
        "maa_path": "/mower-data/maa",
        "maa_conn_preset": "Android",
        "maa_touch_option": "Android",
        "touch_method": "scrcpy",
        "simulator": {
            "name": "",
            "simulator_folder": "",
            "index": "0",
            "wait_time": 0,
            "hotkey": "",
        },
        "tap_to_launch_game": {
            "enable": False,
            "mode": "adb",
            "x": 0,
            "y": 0,
            "command": "",
        },
        "droidcast": {"enable": False, "rotate": False},
        "mumu12IPC": False,
        "custom_screenshot": {"enable": False, "command": ""},
        "close_simulator_when_idle": False,
        "fix_mumu12_adb_disconnect": False,
        "screenshot": 0.25,
        "theme": "dark",
    }

    def normalize(data):
        normalized = {**data, **copy.deepcopy(owned)}
        normalized["webview"] = {
            **data.get("webview", {}),
            "port": 12345,
            "token": "android-session-token",
        }
        return normalized

    package = ModuleType("mower_android")
    managed = ModuleType("mower_android.managed")
    managed.normalize = Mock(side_effect=normalize)
    package.managed = managed
    monkeypatch.setitem(sys.modules, "mower_android", package)
    monkeypatch.setitem(sys.modules, "mower_android.managed", managed)
    monkeypatch.setenv("MOWER_ANDROID", "1")
    return managed.normalize


@pytest.fixture
def desktop_settings():
    return {
        "device": {
            "preset_id": "windows.mumu12",
            "installation_path": "C:/MuMu",
            "manager_path": "C:/MuMu/MuMuManager.exe",
            "config_path": "C:/MuMu/instance.json",
            "adb_path": "C:/MuMu/adb.exe",
            "instance_id": "7",
            "instance_name": "desktop-instance",
            "instance_uuid": "desktop-uuid",
            "topology_fingerprint": "desktop-topology",
            "last_serial": "127.0.0.1:16384",
            "game_package_confirmed": True,
            "screenshot_backend": "mumu_ipc",
            "touch_backend": "mumu_ipc",
            "recovery_timeout": 999,
            "recovery_attempts": 99,
            "recovery_local_wait": 999,
            "recovery_shutdown_wait": 999,
            "manager_query_timeout": 999,
            "simulator_hotkey": "ctrl+f12",
            "simulator_hotkey_delay": 999,
        },
        "adb": "127.0.0.1:5555",
        "maa_adb_path": "C:/adb.exe",
        "maa_path": "C:/MAA",
        "maa_conn_preset": "MuMuEmulator12",
        "maa_touch_option": "MaaTouch",
        "touch_method": "maatouch",
        "simulator": {
            "name": "MuMu12",
            "simulator_folder": "C:/MuMu",
            "index": "7",
            "wait_time": 90,
            "hotkey": "ctrl+f12",
            "hotkey_delay": 999,
        },
        "tap_to_launch_game": {
            "enable": True,
            "mode": "custom",
            "x": 50,
            "y": 60,
            "command": "desktop-launch-command",
        },
        "droidcast": {"enable": True, "rotate": True},
        "mumu12IPC": True,
        "custom_screenshot": {"enable": True, "command": "desktop-capture"},
        "close_simulator_when_idle": True,
        "fix_mumu12_adb_disconnect": True,
        "screenshot": 72,
        "theme": "light",
        "webview": {"port": 58000, "token": "desktop-token", "scale": 1.5},
        "performance_mode": "xhigh",
        "low_frame_rate_mode": False,
    }


def assert_android_owned(conf):
    expected = DeviceProfile(
        preset_id="manual.other",
        adb_path="Android",
        last_serial="Android",
        instance_id="0",
        game_package=conf.APPNAME,
        screenshot_backend="adb_gzip",
        touch_backend="scrcpy",
    )
    assert conf.device == expected
    assert conf.adb == conf.maa_adb_path == "Android"
    assert conf.maa_path == "/mower-data/maa"
    assert conf.maa_conn_preset == conf.maa_touch_option == "Android"
    assert conf.touch_method == "scrcpy"
    assert conf.simulator.name == conf.simulator.simulator_folder == ""
    assert conf.simulator.index == "0"
    assert conf.simulator.wait_time == 0
    assert conf.simulator.hotkey == ""
    assert conf.simulator.hotkey_delay == 3
    assert not conf.tap_to_launch_game.enable
    assert conf.tap_to_launch_game.mode == "adb"
    assert conf.tap_to_launch_game.x == conf.tap_to_launch_game.y == 0
    assert "desktop" not in conf.tap_to_launch_game.command
    assert not conf.droidcast.enable and not conf.droidcast.rotate
    assert not conf.mumu12IPC and not conf.custom_screenshot.enable
    assert conf.custom_screenshot.command == ""
    assert not conf.close_simulator_when_idle
    assert not conf.fix_mumu12_adb_disconnect
    assert conf.screenshot == 0.25 and conf.theme == "dark"
    assert conf.webview.port == 12345
    assert conf.webview.token == "android-session-token"


@pytest.mark.parametrize("mode", ["auto", "xhigh", "high", "medium", "low"])
def test_desktop_profile_cannot_override_android_settings_but_preserves_performance(
    android_settings, desktop_settings, mode
):
    desktop_settings.update(
        performance_mode=mode, selection_poll_interval=0.8, run_order_delay=7.5
    )
    original = copy.deepcopy(desktop_settings)
    conf = Conf(**desktop_settings)
    assert_android_owned(conf)
    assert conf.performance_mode == mode
    assert conf.low_frame_rate_mode is (mode in ("medium", "low"))
    assert conf.selection_poll_interval == 0.8
    assert conf.run_order_delay == 7.5
    assert conf.webview.scale == 1.5
    assert desktop_settings == original
    android_settings.assert_called_once()


@pytest.mark.parametrize("profile", [None, "desktop", [], {"unknown": True}])
def test_desktop_profile_schema_does_not_block_android_load(android_settings, profile):
    assert_android_owned(Conf(device=profile))


def test_android_partial_updates_reuse_the_managed_boundary(
    android_settings, desktop_settings
):
    conf = Conf(package_type=2, mail_subject="android-title")
    original = conf.model_dump()
    updated = conf.updated(desktop_settings)
    assert_android_owned(updated)
    assert updated.package_type == 2
    assert updated.mail_subject == "android-title"
    assert conf.model_dump() == original
    edited = updated.updated({"mail_subject": "new-title"})
    assert edited.mail_subject == "new-title"
    assert_android_owned(edited)


@pytest.mark.parametrize(
    "profile",
    [None, "desktop", {"unknown": True}, {"screenshot_backend": "unsupported"}],
)
def test_android_partial_updates_ignore_desktop_profile_validation(
    android_settings, profile
):
    assert_android_owned(Conf().updated({"device": profile, "mail_subject": "new"}))


@pytest.mark.parametrize(
    "field", ["simulator", "droidcast", "custom_screenshot", "tap_to_launch_game"]
)
def test_android_ignores_malformed_legacy_device_settings(android_settings, field):
    assert_android_owned(Conf(**{field: None}))
    assert_android_owned(Conf().updated({field: None}))


def test_android_backup_validation_uses_the_managed_boundary(
    android_settings, desktop_settings
):
    files = {
        "conf.yml": yaml.safe_dump(desktop_settings).encode("utf-8"),
        "plan.json": config.PlanModel().model_dump_json().encode("utf-8"),
    }
    imported = config_backup._validate_configuration(files)[1]
    assert_android_owned(imported)


def test_android_backup_import_and_export_persist_native_settings(
    android_settings, desktop_settings, monkeypatch, tmp_path
):
    desktop_settings["future_general_setting"] = {"value": "keep"}
    desktop_settings["mail_subject"] = "schedule-report"
    desktop_settings["maa_weekly_plan"] = [{"weekday": "周一", "stage": ["1-7"]}]
    plan = config.PlanModel(
        plan1={"central": {"plans": [{"agent": "阿米娅", "replacement": ["杜宾"]}]}},
        conf={"rest_in_full": "阿米娅"},
        backup_plans=[
            {
                "name": "备用排班",
                "plan": {"central": {"plans": [{"agent": "杜宾"}]}},
                "conf": {"rest_in_full": "杜宾"},
                "task": {"central": ["杜宾"]},
                "trigger": {"left": "True", "operator": "==", "right": "True"},
            }
        ],
    )
    weekly = {
        "plans": {"日常": [{"weekday": "周一", "stage": ["1-7"]}]},
        "activity_fallbacks": {"活动": "日常"},
    }

    def get_path(name, space=None):
        return tmp_path / name.removeprefix("@app/")

    monkeypatch.setattr(config_backup, "get_path", get_path)
    monkeypatch.setattr(config, "conf_path", tmp_path / "config/conf.yml")
    monkeypatch.setattr(config, "plan_path", tmp_path / "config/plan.json")
    monkeypatch.setattr(
        config, "weekly_plans_path", tmp_path / "config/weekly_plans.yml"
    )
    monkeypatch.setattr(config, "conf", Conf(package_type=2))
    monkeypatch.setattr(config, "plan", config.PlanModel())
    config.conf_path.parent.mkdir()
    config.save_conf()
    config.save_plan()
    stream = BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("config/conf.yml", yaml.safe_dump(desktop_settings))
        archive.writestr("config/plan.json", plan.model_dump_json())
        archive.writestr("config/weekly_plans.yml", yaml.safe_dump(weekly))
    config_backup.import_configuration(stream.getvalue())
    assert_android_owned(config.conf)
    saved = yaml.load(config.conf_path.read_text(encoding="utf-8"), Loader=CoreLoader)
    exported_archive = config_backup.export_archive()
    exported_files = config_backup.read_archive(exported_archive)
    exported = yaml.load(exported_files["conf.yml"], Loader=CoreLoader)
    assert saved == exported
    assert exported["device"]["last_serial"] == "Android"
    assert exported["adb"] == exported["maa_adb_path"] == "Android"
    assert exported["maa_path"] == "/mower-data/maa"
    assert exported["simulator"]["name"] == ""
    assert not exported["mumu12IPC"]
    assert exported["webview"]["token"] == "android-session-token"
    assert exported["future_general_setting"] == {"value": "keep"}
    assert exported["mail_subject"] == "schedule-report"
    assert exported["maa_weekly_plan"][0]["stage"] == ["1-7"]
    assert config.plan == plan
    assert exported_files["plan.json"] == plan.model_dump_json().encode("utf-8")
    assert yaml.safe_load(exported_files["weekly_plans.yml"]) == weekly
    monkeypatch.setattr(config, "plan", config.PlanModel())
    config.save_plan()
    config.conf = config.conf.updated({"mail_subject": "changed"})
    config.save_conf()
    config.weekly_plans_path.write_text("plans: {}\n", encoding="utf-8")
    config_backup.import_configuration(exported_archive)
    config.load_conf()
    config.load_plan()
    assert_android_owned(config.conf)
    assert config.conf.mail_subject == "schedule-report"
    assert config.conf.maa_weekly_plan[0].stage == ["1-7"]
    assert config.plan == plan
    assert yaml.safe_load(config.weekly_plans_path.read_bytes()) == weekly


def test_android_general_settings_remain_editable(android_settings):
    conf = Conf().updated(
        {
            "mail_subject": "schedule-report",
            "screenshot_interval": 750,
            "maa_weekly_plan": [{"weekday": "周二", "stage": ["CE-6"]}],
        }
    )
    assert conf.mail_subject == "schedule-report"
    assert conf.screenshot_interval == 750
    assert conf.maa_weekly_plan[0].weekday == "周二"
    assert conf.maa_weekly_plan[0].stage == ["CE-6"]
    assert_android_owned(conf)


def test_android_save_and_reload_keep_native_settings(
    android_settings, desktop_settings, monkeypatch, tmp_path
):
    conf = Conf(**desktop_settings)
    monkeypatch.setattr(config, "conf", conf)
    monkeypatch.setattr(config, "conf_path", tmp_path / "conf.yml")
    config.save_conf()
    saved = yaml.load(config.conf_path.read_text(encoding="utf-8"), Loader=CoreLoader)
    assert_android_owned(Conf(**saved))
    assert saved["device"]["last_serial"] == "Android"
    assert saved["simulator"]["name"] == ""
    assert saved["maa_path"] == "/mower-data/maa"


@pytest.mark.parametrize("package_type", [1, 2, "1", "2"])
def test_android_server_selection_remains_editable(android_settings, package_type):
    conf = Conf().updated({"package_type": package_type})
    assert conf.package_type == int(package_type)
    assert_android_owned(conf)
    restored = Conf(**conf.model_dump())
    assert restored.package_type == int(package_type)
    assert_android_owned(restored)


def test_profile_only_backup_preserves_bilibili_selection(android_settings):
    conf = Conf(device={"game_package": "com.hypergryph.arknights.bilibili"})
    assert conf.package_type == 2
    assert_android_owned(conf)


def test_android_server_field_wins_over_a_conflicting_desktop_profile(android_settings):
    conf = Conf(
        package_type=1,
        device={"game_package": "com.hypergryph.arknights.bilibili"},
    )
    assert conf.package_type == 1
    assert_android_owned(conf)


def test_android_keeps_general_settings(android_settings, desktop_settings):
    desktop_settings.update(
        package_type=2,
        mail_subject="task-report",
        screenshot_interval=750,
        exit_game_when_idle=True,
        return_home_when_idle=True,
        maa_weekly_plan=[{"weekday": "周一", "stage": ["1-7"]}],
    )
    conf = Conf(**desktop_settings)
    assert conf.package_type == 2
    assert conf.mail_subject == "task-report"
    assert conf.screenshot_interval == 750
    assert conf.exit_game_when_idle and conf.return_home_when_idle
    assert conf.maa_weekly_plan[0].stage == ["1-7"]
    assert_android_owned(conf)


def test_desktop_profile_behavior_remains_unchanged(monkeypatch, desktop_settings):
    monkeypatch.delenv("MOWER_ANDROID", raising=False)
    conf = Conf(**desktop_settings)
    assert conf.device.preset_id == "windows.mumu12"
    assert conf.adb == "127.0.0.1:16384"
    assert conf.maa_adb_path == "C:/MuMu/adb.exe"
    assert conf.mumu12IPC
    assert conf.device.touch_backend == "mumu_ipc"
