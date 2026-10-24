import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock
from wsgiref.util import setup_testing_defaults

import pytest
import yaml

from arknights_mower.utils import manager_common as common
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.manager_instances import InstanceController
from manager import Api, manager_app


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    return InstanceController(tmp_path / "instances.json")


def save(manager, values, original=None, changes=None):
    return manager.update_all_settings(
        changes or [],
        manager.instances.copy(),
        {"values": values, "original": original or {}},
    )


def test_common_editor_defaults_match_existing_configuration():
    conf = Conf()
    for field in common.FIELDS:
        if field["kind"] in {"directory", "file"} or field["key"] == "startup_mode":
            continue
        actual = conf
        for name in field["key"].split("."):
            actual = getattr(actual, name)
        assert field["default"] == actual, field["key"]


def test_common_settings_persist_without_any_instances(manager):
    assert manager.get_common_settings()["values"] == {}
    values = {"maa_path": "C:/共享/MAA", "account": "sender@example.com"}
    assert save(manager, values) == {"ok": True, "results": [], "common_saved": True}
    reopened = InstanceController(manager._storage_path)
    assert reopened.get_common_settings()["values"] == values
    assert manager.instances == []
    assert not manager._storage_path.exists()
    save(manager, {}, values)
    assert reopened.get_common_settings()["values"] == {}


@pytest.mark.parametrize("key", ["maa_path", "device.adb_path"])
def test_common_native_selection_is_a_draft_and_cancel_does_not_write(
    manager, monkeypatch, key
):
    window = Mock()
    monkeypatch.setattr("manager.webview.active_window", lambda: window)
    choose = Mock(side_effect=[None, ("C:/chosen",)])
    monkeypatch.setattr("manager.choose_directory", choose)
    window.create_file_dialog = choose
    api = Api(manager._storage_path)
    assert api.select_common_path(key) is None
    assert api.select_common_path(key) == "C:/chosen"
    assert not api._common_path.exists()
    with pytest.raises(ValueError, match="不支持"):
        api.select_common_path("pass_code")
    assert choose.call_count == 2


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize(
    "route",
    [
        "/get_common_settings",
        "/update_all_settings",
        "/select_common_path",
        "/open_browser",
        "/config/manager-common.json",
    ],
)
def test_common_bridge_operations_are_not_http_routes(
    tmp_path, monkeypatch, method, route
):
    static_root = tmp_path / "dist"
    static_root.mkdir()
    monkeypatch.setattr("manager.get_path", lambda *args, **kwargs: static_root)
    env = {}
    setup_testing_defaults(env)
    env.update(REQUEST_METHOD=method, PATH_INFO=route)
    statuses = []
    response = manager_app()(
        env, lambda status, headers, exc_info=None: statuses.append(status)
    )
    try:
        b"".join(response)
    finally:
        if hasattr(response, "close"):
            response.close()
    assert statuses[0].startswith("404" if method == "GET" else "405")


def test_common_save_leaves_running_and_stopped_instance_files_untouched(
    manager, tmp_path, monkeypatch
):
    manager.add("running", str(tmp_path / "running"))
    manager.add("stopped", str(tmp_path / "stopped"))
    paths = []
    for instance in manager.instances:
        path = Path(instance["path"]) / "config/conf.yml"
        path.parent.mkdir(parents=True)
        path.write_text("private_field: keep\naccount: personal\n", encoding="utf-8")
        paths.append(path)
    before = [path.read_bytes() for path in paths]
    monkeypatch.setattr(
        runtime,
        "instances",
        lambda **kwargs: [
            {"kind": "instance", "space": str(tmp_path / "running"), "managed": True}
        ],
    )
    result = save(
        manager,
        {"account": "shared"},
        changes=[{"idx": 0, "settings": {"token": "blocked"}}],
    )
    assert result["common_saved"] is True
    assert result["results"][0]["status"] == "skipped"
    assert [path.read_bytes() for path in paths] == before


@pytest.mark.parametrize(
    "values",
    [
        {"recipient": ["wrong@example.com"]},
        {"device.instance_id": "0"},
        {"updates_enabled": True},
        {"webview.token": "secret"},
        {"screenshot_interval": True},
        {"screenshot_interval": -1},
        {"screenshot_interval": 1.5},
        {"device.recovery_timeout": float("inf")},
        {"device.recovery_attempts": 0},
        {"selection_poll_interval": 0.01},
        {"device.adb_path": ""},
        {"maa_path": None},
        {"account": 42},
        {"low_frame_rate_mode": "false"},
        {"performance_mode": "invalid"},
        {"startup_mode": "invalid"},
        {"startup_mode": True},
        {"custom_smtp_server.ssl_port": 65536},
        {"custom_smtp_server.encryption": "none"},
        {"device.screenshot_backend": "droidcast"},
        {"device.screenshot_backend": "mumu_ipc", "device.touch_backend": "scrcpy"},
    ],
)
def test_invalid_common_fields_reject_before_any_write(manager, tmp_path, values):
    manager.add("one", str(tmp_path / "one"))
    with pytest.raises(ValueError):
        save(manager, values, changes=[{"idx": 0, "settings": {"token": "new"}}])
    assert not manager._common_path.exists()
    assert not (tmp_path / "one").exists()


def test_stale_common_snapshot_blocks_row_changes_and_retains_newer_save(
    manager, tmp_path
):
    manager.add("one", str(tmp_path / "one"))
    save(manager, {"screenshot": 2})
    with pytest.raises(ValueError, match="公共配置已变化"):
        save(
            manager,
            {"screenshot": 3},
            changes=[{"idx": 0, "settings": {"token": "new"}}],
        )
    assert common.read_settings(manager._common_path) == {"screenshot": 2}
    assert not (tmp_path / "one").exists()


def test_stale_list_and_failed_initial_scan_do_not_save_common(
    manager, tmp_path, monkeypatch
):
    manager.add("one", str(tmp_path / "one"))
    with pytest.raises(ValueError, match="实例列表已变化"):
        manager.update_all_settings(
            [], [], {"values": {"screenshot": 3}, "original": {}}
        )
    monkeypatch.setattr(runtime, "instances", Mock(side_effect=OSError("scan failed")))
    with pytest.raises(OSError, match="scan failed"):
        save(manager, {"screenshot": 3})
    assert not manager._common_path.exists()


def test_failed_common_replace_preserves_previous_data(manager, monkeypatch):
    save(manager, {"screenshot": 1})
    before = manager._common_path.read_bytes()
    monkeypatch.setattr(
        runtime, "replace_with_retry", Mock(side_effect=OSError("write failed"))
    )
    with pytest.raises(OSError, match="write failed"):
        save(manager, {"screenshot": 2}, {"screenshot": 1})
    assert manager._common_path.read_bytes() == before


def test_malformed_common_file_is_not_replaced_by_defaults(manager):
    manager._common_path.parent.mkdir(parents=True)
    manager._common_path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        manager.get_common_settings()
    with pytest.raises(ValueError):
        save(manager, {})
    assert manager._common_path.read_text() == "not json"


def test_common_application_preserves_recipients_permissions_and_device_identity():
    original = Conf(
        device={
            "preset_id": "windows.mumu12",
            "instance_id": "7",
            "last_serial": "127.0.0.1:17000",
            "instance_uuid": "vm-seven",
        },
        recipient=["personal@example.com"],
        mail_subject="personal",
        mail_enable=0,
        webview={"port": 58001, "token": "instance-token"},
        ai_assistant_enabled=False,
        updates_enabled=False,
    )
    before = original.model_dump()
    changed = common.apply_settings(
        original,
        {
            "startup_mode": "background",
            "device.adb_path": "C:/adb.exe",
            "maa_path": "C:/MAA",
            "account": "sender@example.com",
            "pass_code": "sender-secret",
            "custom_smtp_server.server": "smtp.example.com",
            "device.recovery_timeout": 240,
            "performance_mode": "low",
            "screenshot": 6,
            "screenshot_archive_limit_mb": 1024,
        },
    )
    assert changed.account == "sender@example.com"
    assert changed.pass_code == "sender-secret"
    assert changed.recipient == ["personal@example.com"]
    assert changed.mail_subject == "personal" and changed.mail_enable == 0
    assert changed.webview.port == 58001 and changed.webview.token == "instance-token"
    assert not changed.ai_assistant_enabled and not changed.updates_enabled
    assert changed.device.instance_id == "7"
    assert changed.device.instance_uuid == "vm-seven"
    assert changed.device.last_serial == "127.0.0.1:17000"
    assert changed.device.adb_path == changed.maa_adb_path == "C:/adb.exe"
    assert changed.device.recovery_timeout == 240
    assert changed.performance_mode == "low" and changed.screenshot == 6
    assert changed.screenshot_archive_limit_mb == 1024
    assert original.model_dump() == before


def test_startup_mode_stays_manager_owned_and_does_not_patch_instance_configuration():
    original = Conf(start_automatically=False)
    assert common.apply_settings(original, {"startup_mode": "background"}) is original


def test_common_path_change_uses_existing_rebinding_rules_and_legacy_mapping():
    original = Conf(
        simulator={"name": "MuMu12", "index": "4", "simulator_folder": "C:/old"},
        adb="127.0.0.1:16416",
    )
    changed = common.apply_settings(original, {"device.installation_path": "C:/new"})
    assert changed.device.preset_id == "windows.mumu12"
    assert changed.device.instance_id == "4"
    assert (
        changed.device.installation_path
        == changed.simulator.simulator_folder
        == "C:/new"
    )
    assert changed.device.last_serial == changed.adb == ""
    assert not changed.device.game_package_confirmed
    assert original.device.last_serial == "127.0.0.1:16416"


def test_native_capture_cannot_change_an_incompatible_instance_target():
    original = Conf(device={"preset_id": "windows.ldplayer9", "instance_id": "2"})
    with pytest.raises(ValueError, match="MuMu"):
        common.apply_settings(
            original,
            {
                "device.screenshot_backend": "mumu_ipc",
                "device.touch_backend": "mumu_ipc",
            },
        )
    assert original.device.preset_id == "windows.ldplayer9"
    assert original.device.instance_id == "2"


def test_common_file_changes_do_not_change_existing_launch_snapshot(
    manager, monkeypatch
):
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    save(manager, {"screenshot": 2})
    running = common.for_launch(Conf(), managed=True)
    save(manager, {"screenshot": 3}, {"screenshot": 2})
    assert running.screenshot == 2
    assert common.for_launch(Conf(), managed=True).screenshot == 3
    monkeypatch.setattr(
        common,
        "read_settings",
        Mock(side_effect=AssertionError("standalone must not read")),
    )
    assert common.for_launch(Conf(screenshot=7), managed=False).screenshot == 7


@pytest.mark.parametrize("managed,fresh", [(True, True), (True, False), (False, False)])
def test_real_configuration_startup_reads_common_only_for_managed_launch(
    tmp_path, managed, fresh
):
    root = tmp_path / "data"
    common_path = root / "config/manager-common.json"
    common_path.parent.mkdir(parents=True)
    common_path.write_text(
        json.dumps(
            {
                "maa_path": "C:/shared-maa",
                "account": "shared-sender",
                "startup_mode": "background",
            }
        ),
        encoding="utf-8",
    )
    conf_path = root / "instance/config/conf.yml"
    conf_path.parent.mkdir(parents=True)
    raw = {
        "maa_path": "C:/private-maa",
        "account": "personal",
        "recipient": ["owner@example.com"],
        "private": "untouched",
    }
    if not fresh:
        conf_path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        before = conf_path.read_bytes()
    code = (
        "import json; from arknights_mower.utils import path; path.global_space='instance'; "
        "from arknights_mower.utils import config; "
        "print(json.dumps([config.conf.maa_path, config.conf.account, config.conf.recipient]))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[2],
        env={
            **os.environ,
            "MOWER_DATA_DIR": str(root),
            "MOWER_MANAGED": "1" if managed else "0",
            "MOWER_ANDROID": "0",
        },
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=30,
        check=True,
    )
    expected = (
        ["C:/shared-maa", "shared-sender"]
        if managed
        else ["C:/private-maa", "personal"]
    )
    assert json.loads(result.stdout.strip().splitlines()[-1]) == [
        *expected,
        [] if fresh else ["owner@example.com"],
    ]
    if not fresh:
        assert conf_path.read_bytes() == before
