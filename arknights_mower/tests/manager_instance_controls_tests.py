import inspect
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from yamlcore import CoreLoader

from arknights_mower.utils import manager_common
from arknights_mower.utils import manager_instances as controls
from arknights_mower.utils import update_runtime as runtime
from manager import Api
from webview_ui import desktop_port


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    monkeypatch.setattr(runtime, "process_alive", lambda pid: pid == 12345)
    child = Mock(pid=12345)
    monkeypatch.setattr(controls.subprocess, "Popen", Mock(return_value=child))
    monkeypatch.setattr(controls.threading, "Thread", Mock())
    api = Api(tmp_path / "instances.json")
    api.add("first", str(tmp_path / "first"))
    return api


def record(manager, **changes):
    return dict(
        id="registered",
        pid=12345,
        kind="instance",
        space=manager.instances[0]["path"],
        managed=True,
        ready=True,
        running=False,
        **changes,
    )


def read_conf(manager):
    path = Path(manager.instances[0]["path"]) / "config/conf.yml"
    return yaml.load(path.read_text(encoding="utf-8"), Loader=CoreLoader)


def batch_changes(manager, settings):
    return [
        {"idx": idx, "settings": dict(settings)}
        for idx in range(len(manager.instances))
    ]


def test_unset_permissions_allow_updates_and_disable_ai_without_writing(manager):
    item = manager.get_instances()[0]
    assert item["updates_enabled"] is True
    assert item["ai_assistant_enabled"] is False
    assert not (Path(item["path"]) / "config/conf.yml").exists()
    manager.update_settings(0, {"token": "keep", "port": 58001})
    reopened = Api(manager._storage_path)
    item = reopened.get_instances()[0]
    assert item["updates_enabled"] is True
    assert item["ai_assistant_enabled"] is False
    saved = read_conf(reopened)
    assert "updates_enabled" not in saved
    assert "ai_assistant_enabled" not in saved


@pytest.mark.parametrize("enabled", [False, True])
def test_update_permission_is_persisted_without_changing_other_settings(
    manager, enabled
):
    assert manager.get_instances()[0]["updates_enabled"] is True
    manager.update_settings(
        0, {"token": "keep", "port": 58001, "ai_assistant_enabled": True}
    )
    manager.update_all_settings(
        batch_changes(manager, {"updates_enabled": enabled}), manager.instances.copy()
    )
    reopened = Api(manager._storage_path)
    assert reopened.get_instances()[0]["updates_enabled"] is enabled
    saved = read_conf(reopened)
    assert saved["updates_enabled"] is enabled
    assert saved["ai_assistant_enabled"] is True
    assert saved["webview"] == {"token": "keep", "port": 58001}


@pytest.mark.parametrize("enabled", [None, 0, 1, "true", "false"])
def test_manager_rejects_invalid_update_permission_without_writing(manager, enabled):
    with pytest.raises(ValueError, match="布尔值"):
        manager.update_settings(
            0, {"token": "", "port": None, "updates_enabled": enabled}
        )
    assert not (Path(manager.instances[0]["path"]) / "config/conf.yml").exists()


def test_manager_skips_live_update_permission_edits(manager, monkeypatch):
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [record(manager)])
    with pytest.raises(ValueError):
        manager.update_settings(0, {"token": "", "port": None, "updates_enabled": True})
    result = manager.update_all_settings(
        batch_changes(manager, {"updates_enabled": True}), manager.instances.copy()
    )
    assert result["results"][0]["status"] == "skipped"
    assert not (Path(manager.instances[0]["path"]) / "config/conf.yml").exists()


@pytest.mark.parametrize("change", ["renamed", "moved", "removed", "replaced"])
def test_single_settings_reject_changed_target_without_touching_either_config(
    manager, change
):
    manager.update_settings(0, {"token": "first", "port": 58001})
    first = Path(manager.instances[0]["path"]) / "config/conf.yml"
    target = dict(manager.instances[0])
    manager.add("second", str(first.parent.parent.parent / "second"))
    manager.update_settings(1, {"token": "second", "port": 58002})
    second = Path(manager.instances[1]["path"]) / "config/conf.yml"
    before = {path: path.read_bytes() for path in (first, second)}
    other = Api(manager._storage_path)
    if change == "renamed":
        other.rename(0, "renamed")
    elif change == "moved":
        other._update(0, {"path": other.instances[1]["path"]})
    elif change == "removed":
        other.remove(1)
        other.remove(0)
    else:
        other.remove(0)
    assert manager.instances[0] == target
    with pytest.raises(ValueError, match="实例已变化"):
        manager.update_settings(
            0,
            {"token": "stale", "port": None, "ai_assistant_enabled": True},
            target,
        )
    assert {path: path.read_bytes() for path in (first, second)} == before


def test_single_settings_accept_matching_target_after_an_unrelated_list_change(manager):
    target = dict(manager.instances[0])
    manager.add("unrelated", str(Path(target["path"]).parent / "other"))
    manager.update_settings(
        0, {"token": "new", "port": None, "ai_assistant_enabled": True}, target
    )
    assert read_conf(manager)["webview"] == {"token": "new", "port": 0}
    assert read_conf(manager)["ai_assistant_enabled"] is True


def test_single_settings_matching_target_still_rejects_running_process(
    manager, monkeypatch
):
    target = dict(manager.instances[0])
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [record(manager)])
    with pytest.raises(ValueError, match="实例进程运行期间"):
        manager.update_settings(
            0, {"token": "new", "port": None, "ai_assistant_enabled": True}, target
        )
    assert not Path(target["path"]).exists()


@pytest.mark.parametrize("action", ["remove", "rename", "start", "stop", "select_path"])
@pytest.mark.parametrize("changed", [False, True])
def test_row_actions_validate_captured_target_before_side_effects(
    manager, monkeypatch, action, changed
):
    target = dict(manager.instances[0])
    manager.update_settings(0, {"token": "first", "port": None})
    manager.add("second", str(manager._storage_path.parent / "second"))
    manager.update_settings(1, {"token": "second", "port": None})
    files = [Path(item["path"]) / "config/conf.yml" for item in manager.instances]
    before_configs = {path: path.read_bytes() for path in files}
    other = Api(manager._storage_path)
    if changed:
        other.remove(0)
    else:
        other.add("unrelated", "")
    before_list = manager._storage_path.read_bytes()
    current = other.instances[0]
    if action == "stop":
        live = dict(record(manager), space=current["path"])
        monkeypatch.setattr(runtime, "instances", lambda **kwargs: [live])
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    choose = Mock(return_value=str(manager._storage_path.parent / "selected"))
    monkeypatch.setattr("manager.choose_instance_directory", choose)
    monkeypatch.setattr("manager.webview.active_window", lambda: None)

    def apply():
        if action == "rename":
            return manager.rename(0, "renamed", target)
        return getattr(manager, action)(0, target)

    if changed:
        if action in ("start", "stop"):
            result = apply()
            assert result["ok"] is False
            assert "实例已变化" in result["message"]
        else:
            with pytest.raises(ValueError, match="实例已变化"):
                apply()
        controls.subprocess.Popen.assert_not_called()
        send.assert_not_called()
        choose.assert_not_called()
        assert manager._storage_path.read_bytes() == before_list
    else:
        result = apply()
        if action == "start":
            assert result["ok"] is True
            controls.subprocess.Popen.assert_called_once()
        elif action == "stop":
            assert result["ok"] is True
            send.assert_called_once_with(live, "exit")
        elif action == "remove":
            assert all(item["path"] != target["path"] for item in manager.instances)
        elif action == "rename":
            assert manager.instances[0]["name"] == "renamed"
        else:
            choose.assert_called_once_with(None, target["path"])
            assert manager.instances[0]["path"] == result
    assert {path: path.read_bytes() for path in files} == before_configs


def test_folder_dialog_rejects_target_replaced_while_choosing(manager, monkeypatch):
    target = dict(manager.instances[0])
    manager.add("second", str(manager._storage_path.parent / "second"))
    other = Api(manager._storage_path)
    saved = []

    def choose(*args):
        other.remove(0)
        saved.append(manager._storage_path.read_bytes())
        return str(manager._storage_path.parent / "selected")

    monkeypatch.setattr("manager.choose_instance_directory", choose)
    monkeypatch.setattr("manager.webview.active_window", lambda: None)
    with pytest.raises(ValueError, match="实例已变化"):
        manager.select_path(0, target)
    assert manager._storage_path.read_bytes() == saved[0]
    assert manager.instances[0] == other.instances[0]


def test_duplicate_launch_is_blocked_before_registration_and_after_window_reopen(
    manager,
):
    assert manager.start(0) == {"ok": True}
    reopened = Api(manager._storage_path)
    assert not reopened.start(0)["ok"]
    controls.subprocess.Popen.assert_called_once()
    state = reopened.get_instances()[0]
    assert state["state"] == "starting"
    assert not state["editable"] and not state["can_start"] and state["can_stop"]


@pytest.mark.parametrize(
    "values,background",
    [
        ({}, "0"),
        ({"startup_mode": "window"}, "0"),
        ({"startup_mode": "background"}, "1"),
    ],
)
@pytest.mark.parametrize("bulk", [False, True])
def test_manager_launch_honors_saved_common_startup_mode(
    manager, monkeypatch, values, background, bulk
):
    monkeypatch.setenv("MOWER_BACKGROUND", "1")
    manager.update_all_settings(
        [], manager.instances.copy(), {"values": values, "original": {}}
    )
    assert (manager.start_all() if bulk else manager.start(0))["ok"]
    controls.subprocess.Popen.assert_called_once()
    env = controls.subprocess.Popen.call_args.kwargs["env"]
    assert env["MOWER_BACKGROUND"] == background
    assert env["MOWER_MANAGED"] == "1"
    assert {
        key: value
        for key, value in manager_common.read_settings(manager._common_path).items()
        if key not in manager_common.SHARED_CONNECTION_KEYS
    } == values
    assert not Path(manager.instances[0]["path"]).exists()


def test_invalid_common_startup_mode_blocks_launch_before_creating_a_process(manager):
    runtime.write_json(manager._common_path, {"startup_mode": "invalid"})
    assert not manager.start(0)["ok"]
    controls.subprocess.Popen.assert_not_called()


def test_browser_action_addresses_ready_registration_without_starting_another_instance(
    manager, monkeypatch
):
    manager.update_settings(0, {"token": "saved-token", "port": 58001})
    registered = record(manager, port=59002)
    pending = {**registered, "ready": False}
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [pending, registered])
    assert manager.get_instances()[0]["can_open_browser"]
    assert manager.open_browser(0, dict(manager.instances[0])) == {"ok": True}
    commands = list((runtime.state_dir() / "commands/registered").glob("*.json"))
    assert len(commands) == 1
    assert json.loads(commands[0].read_text()) == {"action": "browser"}
    controls.subprocess.Popen.assert_not_called()


@pytest.mark.parametrize("state", ["stopped", "starting", "stopping", "unmanaged"])
def test_browser_action_rechecks_instance_readiness_before_dispatch(
    manager, monkeypatch, state
):
    registered = record(manager)
    registered["ready"] = state != "starting"
    registered["managed"] = state != "unmanaged"
    monkeypatch.setattr(
        runtime,
        "instances",
        lambda **kwargs: [] if state == "stopped" else [registered],
    )
    if state == "stopping":
        runtime.send_instance_command(registered, "exit")
    assert not manager.get_instances()[0]["can_open_browser"]
    assert not manager.open_browser(0, dict(manager.instances[0]))["ok"]
    assert not (runtime.state_dir() / "commands").exists()
    controls.subprocess.Popen.assert_not_called()


def test_browser_action_rejects_stale_target_and_unreadable_state(manager, monkeypatch):
    target = dict(manager.instances[0])
    manager.rename(0, "renamed")
    assert not manager.open_browser(0, target)["ok"]
    assert not manager.open_browser(-1, dict(manager.instances[0]))["ok"]
    assert not manager.open_browser(True, dict(manager.instances[0]))["ok"]
    monkeypatch.setattr(runtime, "instances", Mock(side_effect=OSError("scan failed")))
    assert manager.open_browser(0, dict(manager.instances[0])) == {
        "ok": False,
        "message": "scan failed",
    }
    assert not (runtime.state_dir() / "commands").exists()


def test_bridge_does_not_expose_filesystem_objects(manager):
    assert not any(
        isinstance(value, Path)
        for name, value in inspect.getmembers(manager)
        if not name.startswith("_")
    )


def test_manager_keeps_folder_dialog_on_its_own_window(manager, monkeypatch):
    import manager as manager_module

    window = Mock()
    other_window = Mock()
    monkeypatch.setattr(manager_module.webview, "active_window", other_window)
    choose = Mock(return_value=(str(manager._storage_path.parent / "selected"),))
    monkeypatch.setattr(manager_module, "choose_instance_directory", choose)
    controller = Api(manager._storage_path, window=window)
    original = manager.instances[0]["path"]
    selected = controller.select_path(0)
    choose.assert_called_once_with(window, original)
    other_window.assert_not_called()
    assert manager.get_instances()[0]["path"] == selected


def test_manager_launch_does_not_inherit_parent_instance_recovery(manager, monkeypatch):
    monkeypatch.delenv("http_proxy", raising=False)
    inherited = {
        "MOWER_SUPERVISOR_DIRECTORY": "parent-supervision",
        "MOWER_SUPERVISOR_CHILD_REPORT": "parent-report",
        "MOWER_SUPERVISOR_GENERATION": "parent-generation",
        "MOWER_SUPERVISOR_INTENT": "parent-intent",
        "MOWER_RECOVERY_RUN": "1",
        "MOWER_RESUME_MODE": "1",
        "MOWER_RESTART_JOB": "parent-update",
        "MOWER_RESTART_PORT": "58011",
        "MOWER_RESUME_RUN": "1",
        "MOWER_LAUNCH_ID": "parent-launch",
        "MOWER_MANAGER_PORT": "58012",
        "MOWER_BACKGROUND": "1",
        "MOWER_DATA_DIR": str(manager._storage_path.parent / "shared-data"),
        "HTTP_PROXY": "http://proxy.invalid:8080",
    }
    for name, value in inherited.items():
        monkeypatch.setenv(name, value)

    assert manager.start(0) == {"ok": True}
    environment = controls.subprocess.Popen.call_args.kwargs["env"]
    assert not any(name.startswith("MOWER_SUPERVISOR_") for name in environment)
    assert "MOWER_RECOVERY_RUN" not in environment
    assert "MOWER_RESUME_MODE" not in environment
    assert environment["MOWER_RESTART_JOB"] == ""
    assert environment["MOWER_RESTART_PORT"] == ""
    assert environment["MOWER_RESUME_RUN"] == "0"
    assert environment["MOWER_LAUNCH_ID"] != "parent-launch"
    assert len(environment["MOWER_LAUNCH_ID"]) == 32
    assert environment["MOWER_MANAGER_PORT"] == "0"
    assert environment["MOWER_BACKGROUND"] == "0"
    assert environment["MOWER_MANAGED"] == "1"
    assert environment["MOWER_DATA_DIR"] == inherited["MOWER_DATA_DIR"]
    assert environment["http_proxy"] == inherited["HTTP_PROXY"]
    assert {name: controls.os.environ[name] for name in inherited} == inherited


def test_manager_saves_device_and_performance_without_replacing_private_fields(manager):
    manager.update_settings(0, {"token": "private", "port": None})
    destination = Path(manager.instances[0]["path"]) / "config/conf.yml"
    raw = read_conf(manager)
    raw.update(
        theme="dark",
        private_extension={"keep": True},
        custom_screenshot={"command": "old", "private": 7},
    )
    destination.write_text(yaml.safe_dump(raw), encoding="utf-8")
    target = manager.instances[0].copy()
    settings = manager.get_device_settings(0, target)
    original = settings["values"]
    assert manager.update_device_settings(
        0,
        {
            "custom_screenshot.command": "capture-new",
            "device.last_serial": "chosen-device",
            "performance_mode": "low",
            "screenshot_interval": 750,
        },
        target,
        original,
        {
            "independent_configuration": True,
            "original_policy": settings["original_policy"],
        },
    ) == {"ok": True}
    saved = read_conf(manager)
    assert saved["custom_screenshot"] == {
        "command": "capture-new",
        "enable": False,
        "private": 7,
    }
    assert saved["device"]["last_serial"] == saved["adb"] == "chosen-device"
    assert saved["performance_mode"] == "low"
    assert saved["screenshot_interval"] == 750
    assert saved["webview"]["token"] == "private"
    assert saved["private_extension"] == {"keep": True}
    assert saved["theme"] == "dark"


@pytest.mark.parametrize("blocked", ["running", "target", "stale", "job", "invalid"])
def test_manager_rejects_device_edits_without_writes(manager, monkeypatch, blocked):
    manager.update_settings(0, {"token": "private", "port": None})
    destination = Path(manager.instances[0]["path"]) / "config/conf.yml"
    target = manager.instances[0].copy()
    original = manager.get_device_settings(0, target)["values"]
    changes = {"custom_screenshot.command": "replacement"}
    if blocked == "running":
        monkeypatch.setattr(runtime, "instances", lambda **kwargs: [record(manager)])
    elif blocked == "target":
        target["name"] = "stale"
    elif blocked == "stale":
        original["performance_mode"] = "stale"
    elif blocked == "job":
        monkeypatch.setattr(runtime, "active_job", lambda: True)
    else:
        changes = {"webview.token": "unauthorized"}
    before = destination.read_bytes()
    with pytest.raises(ValueError):
        manager.update_device_settings(0, changes, target, original)
    assert destination.read_bytes() == before


@pytest.mark.parametrize("field", ["instance_uuid", "topology_fingerprint"])
def test_manager_identity_metadata_requires_detected_binding(
    manager, monkeypatch, field
):
    from arknights_mower.utils import managed_device

    manager.update_settings(0, {"token": "keep", "port": None})
    target = manager.instances[0].copy()
    settings = manager.get_device_settings(0, target)
    assert next(
        item for item in settings["fields"] if item["key"] == f"device.{field}"
    )["read_only"]
    destination = Path(target["path"]) / "config/conf.yml"
    before = destination.read_bytes()
    monkeypatch.setattr(
        managed_device, "discover", Mock(return_value={"candidates": []})
    )
    changes = {f"device.{field}": "forged"}
    with pytest.raises(ValueError, match="识别信息由检测结果维护"):
        manager.update_device_settings(0, changes, target, settings["values"])
    assert destination.read_bytes() == before
    binding = {
        "preset_id": "windows.nox",
        "instance_id": "0",
        "instance_uuid": "uuid",
        "topology_fingerprint": "fingerprint",
    }
    managed_device.discover.return_value = {
        "candidates": [{"binding": {**binding, "game_package_confirmed": False}}]
    }
    changes = {f"device.{key}": value for key, value in binding.items()}
    changes["device.game_package"] = "com.hypergryph.arknights.bilibili"
    assert manager.update_device_settings(
        0,
        changes,
        target,
        settings["values"],
        {
            "independent_configuration": True,
            "original_policy": settings["original_policy"],
        },
    ) == {"ok": True}
    assert read_conf(manager)["device"][field] == binding[field]


def test_manager_discovery_uses_a_validated_draft_without_persisting_it(
    manager, monkeypatch
):
    from arknights_mower.utils import managed_device

    target = manager.instances[0].copy()
    settings = manager.get_device_settings(0, target)
    original = settings["values"]
    discover = Mock(return_value={"candidates": [{"key": "chosen"}]})
    monkeypatch.setattr(managed_device, "discover", discover)
    result = manager.discover_device_settings(
        0,
        {"device.adb_path": "chosen-adb"},
        target,
        original,
        {
            "independent_configuration": True,
            "original_policy": settings["original_policy"],
        },
    )
    assert result == {"candidates": [{"key": "chosen"}]}
    assert discover.call_args.args[0].device.adb_path == "chosen-adb"
    assert not (Path(target["path"]) / "config/conf.yml").exists()


def test_separate_api_objects_cannot_admit_concurrent_operations(manager):
    other = Api(manager._storage_path)
    with manager._operation():
        assert not other.start(0)["ok"]
    controls.subprocess.Popen.assert_not_called()
    assert other.start(0)["ok"]


def test_failed_reservation_write_closes_only_the_child_just_created(
    manager, monkeypatch
):
    manager.get_common_settings()
    child = controls.subprocess.Popen.return_value
    child.wait.side_effect = [subprocess.TimeoutExpired("fixture", 5), None]
    monkeypatch.setattr(
        runtime, "write_json", Mock(side_effect=OSError("reservation failed"))
    )
    assert manager.start(0) == {"ok": False, "message": "reservation failed"}
    child.terminate.assert_called_once()
    child.kill.assert_called_once()
    assert child.wait.call_count == 2
    assert manager.get_instances()[0]["can_start"]


def test_alias_paths_share_process_identity(manager):
    manager.add("alias", str(Path(manager.instances[0]["path"]) / ".." / "first"))
    assert manager.start(0)["ok"]
    assert not manager.start(1)["ok"]
    with pytest.raises(ValueError, match="进程运行"):
        manager.rename(1, "changed")
    controls.subprocess.Popen.assert_called_once()


def test_stop_during_startup_reaches_child_launch_identity_and_waits_for_exit(
    manager, monkeypatch
):
    assert manager.start(0)["ok"]
    launch_id = controls.subprocess.Popen.call_args.kwargs["env"]["MOWER_LAUNCH_ID"]
    assert manager.stop(0)["ok"]
    request = runtime.state_dir() / "shutdown" / f"{launch_id}.json"
    assert json.loads(request.read_text()) == {"manager": True}
    item = manager.get_instances()[0]
    assert item["state"] == "stopping" and not item["can_stop"] and not item["editable"]
    controls.subprocess.Popen.return_value.terminate.assert_not_called()
    monkeypatch.setattr(runtime, "process_alive", lambda pid: False)
    item = manager.get_instances()[0]
    assert item["state"] == "stopped" and item["editable"] and item["can_start"]
    assert not request.exists()


def test_automation_stopped_does_not_make_process_editable(manager, monkeypatch):
    live = record(manager)
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [live])
    before = manager._storage_path.read_bytes()
    for action in [
        lambda: manager.rename(0, "changed"),
        lambda: manager.remove(0),
        lambda: manager.update_settings(0, {"token": "secret", "port": 58001}),
        lambda: manager.select_path(0),
    ]:
        with pytest.raises(ValueError, match="进程运行"):
            action()
        assert manager._storage_path.read_bytes() == before
    state = manager.get_instances()[0]
    assert state["state"] == "running" and not state["editable"] and state["can_stop"]
    assert manager.stop(0)["ok"]
    assert (runtime.state_dir() / "shutdown/registered.json").exists()


def test_folder_dialog_rechecks_process_after_selection(manager, monkeypatch):
    from manager import webview

    monkeypatch.setattr(webview, "active_window", lambda: None)

    def choose(*args):
        assert manager.start(0)["ok"]
        return str(Path(manager.instances[0]["path"]).parent / "other")

    monkeypatch.setattr("manager.choose_instance_directory", choose)
    before = manager._storage_path.read_bytes()
    with pytest.raises(ValueError, match="进程运行"):
        manager.select_path(0)
    assert manager._storage_path.read_bytes() == before


def test_running_destination_cannot_be_selected(manager, monkeypatch):
    monkeypatch.setattr("manager.webview.active_window", lambda: None)
    destination = str(Path(manager.instances[0]["path"]).parent / "other")
    monkeypatch.setattr("manager.choose_instance_directory", lambda *args: destination)
    monkeypatch.setattr(
        runtime,
        "instances",
        lambda **kwargs: [dict(record(manager), space=destination)],
    )
    before = manager._storage_path.read_bytes()
    with pytest.raises(ValueError, match="进程运行"):
        manager.select_path(0)
    assert manager._storage_path.read_bytes() == before


def test_settings_preserve_legacy_and_unknown_configuration(manager):
    root = Path(manager.instances[0]["path"])
    root.mkdir()
    legacy = root / "conf.yml"
    legacy.write_text(
        "private_payload: encrypted-text\ncustom: {flag: true}\nwebview: {scale: 1.25, token: old}\n",
        encoding="utf-8",
    )
    manager.update_settings(0, {"token": "new-secret", "port": 58001})
    raw = read_conf(manager)
    assert raw == {
        "private_payload": "encrypted-text",
        "custom": {"flag": True},
        "webview": {"scale": 1.25, "token": "new-secret", "port": 58001},
    }
    assert legacy.read_text(encoding="utf-8").startswith("private_payload:")
    manager.update_settings(0, {"token": "", "port": None})
    assert read_conf(manager)["webview"]["port"] == 0
    assert manager.get_instances()[0]["port"] is None


def test_assistant_defaults_off_and_saved_choices_survive_manager_recreation(manager):
    assert manager.get_instances()[0]["ai_assistant_enabled"] is False
    for enabled in (True, False):
        manager.update_settings(
            0, {"token": "", "port": None, "ai_assistant_enabled": enabled}
        )
        reopened = Api(manager._storage_path)
        assert reopened.get_instances()[0]["ai_assistant_enabled"] is enabled
        assert read_conf(reopened)["ai_assistant_enabled"] is enabled
        reopened.update_settings(0, {"token": "changed", "port": None})
        assert read_conf(reopened)["ai_assistant_enabled"] is enabled


def test_running_process_cannot_change_assistant_and_failed_write_preserves_choice(
    manager, monkeypatch
):
    settings = {"token": "", "port": None, "ai_assistant_enabled": True}
    manager.update_settings(0, settings)
    target = Path(manager.instances[0]["path"]) / "config/conf.yml"
    before = target.read_bytes()
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [record(manager)])
    with pytest.raises(ValueError, match="进程运行"):
        manager.update_settings(0, {**settings, "ai_assistant_enabled": False})
    assert target.read_bytes() == before
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(
        runtime, "replace_with_retry", Mock(side_effect=PermissionError("locked"))
    )
    with pytest.raises(PermissionError):
        manager.update_settings(0, {**settings, "ai_assistant_enabled": False})
    assert target.read_bytes() == before


def test_assistant_choices_are_per_instance_and_preserve_unknown_yaml_fields(manager):
    root = Path(manager.instances[0]["path"])
    root.mkdir()
    (root / "conf.yml").write_text(
        "private_payload: encrypted-text\ncustom: {flag: true}\n", encoding="utf-8"
    )
    manager.add("second", str(root.parent / "second"))
    manager.update_settings(
        0, {"token": "", "port": None, "ai_assistant_enabled": True}
    )
    assert read_conf(manager)["private_payload"] == "encrypted-text"
    assert read_conf(manager)["custom"] == {"flag": True}
    assert [
        row["ai_assistant_enabled"]
        for row in Api(manager._storage_path).get_instances()
    ] == [True, False]


@pytest.mark.parametrize("enabled", [1, 0, "true", "false", None])
def test_invalid_assistant_choice_never_writes(manager, enabled):
    with pytest.raises(ValueError):
        manager.update_settings(
            0, {"token": "", "port": None, "ai_assistant_enabled": enabled}
        )
    assert not Path(manager.instances[0]["path"]).exists()


def test_batch_ai_only_preserves_each_connection_and_private_configuration(manager):
    first = Path(manager.instances[0]["path"])
    first.mkdir()
    (first / "conf.yml").write_text(
        "webview: {token: first-secret, port: 58001}\nprivate_payload: encrypted\n",
        encoding="utf-8",
    )
    manager.add("second", str(first.parent / "second"))
    manager.update_settings(1, {"token": "second-secret", "port": 58002})
    targets = manager.instances.copy()
    result = manager.update_all_settings(
        batch_changes(manager, {"ai_assistant_enabled": True}), targets
    )
    assert [item["status"] for item in result["results"]] == ["updated", "updated"]
    for idx, token, port in ((0, "first-secret", 58001), (1, "second-secret", 58002)):
        _, raw = controls.read_instance_config(manager.instances[idx]["path"])
        assert raw["ai_assistant_enabled"] is True
        assert raw["webview"] == {"token": token, "port": port}
    assert read_conf(manager)["private_payload"] == "encrypted"
    result = manager.update_all_settings(
        batch_changes(manager, {"ai_assistant_enabled": False}), targets
    )
    assert all(item["status"] == "updated" for item in result["results"])
    assert all(
        not row["ai_assistant_enabled"]
        for row in Api(manager._storage_path).get_instances()
    )


def test_batch_table_saves_different_cells_and_leaves_unedited_rows_untouched(manager):
    root = Path(manager.instances[0]["path"])
    manager.update_settings(0, {"token": "first", "port": 58000})
    manager.add("second", str(root.parent / "second"))
    manager.update_settings(1, {"token": "second", "port": 58001})
    manager.add("third", str(root.parent / "third"))
    result = manager.update_all_settings(
        [
            {"idx": 0, "settings": {"ai_assistant_enabled": True}},
            {"idx": 1, "settings": {"token": "new-second", "port": 59002}},
        ],
        manager.instances.copy(),
    )
    assert [row["idx"] for row in result["results"]] == [0, 1]
    assert read_conf(manager)["webview"] == {"token": "first", "port": 58000}
    assert read_conf(manager)["ai_assistant_enabled"] is True
    _, second = controls.read_instance_config(manager.instances[1]["path"])
    assert second["webview"] == {"token": "new-second", "port": 59002}
    assert "ai_assistant_enabled" not in second
    assert not Path(manager.instances[2]["path"]).exists()


def test_batch_settings_skip_live_missing_and_alias_directories(manager, monkeypatch):
    root = Path(manager.instances[0]["path"])
    manager.update_settings(0, {"token": "keep", "port": 59000})
    manager.add("second", str(root.parent / "second"))
    manager.add("missing", "")
    manager.add("alias", str(root.parent / "second" / ".." / "second"))
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [record(manager)])
    before = read_conf(manager)
    result = manager.update_all_settings(
        batch_changes(manager, {"token": "shared", "port": 58001}),
        manager.instances.copy(),
    )
    assert [item["status"] for item in result["results"]] == [
        "skipped",
        "updated",
        "skipped",
        "skipped",
    ]
    assert read_conf(manager) == before
    _, second = controls.read_instance_config(manager.instances[1]["path"])
    assert second["webview"] == {"token": "shared", "port": 58001}
    assert "ai_assistant_enabled" not in second


def test_batch_random_ports_clear_token_only_when_selected(manager):
    manager.update_settings(
        0, {"token": "keep", "port": 58001, "ai_assistant_enabled": True}
    )
    targets = manager.instances.copy()
    manager.update_all_settings(batch_changes(manager, {"port": None}), targets)
    assert read_conf(manager)["webview"] == {"token": "keep", "port": 0}
    assert read_conf(manager)["ai_assistant_enabled"] is True
    manager.update_all_settings(batch_changes(manager, {"token": ""}), targets)
    assert read_conf(manager)["webview"] == {"token": "", "port": 0}


@pytest.mark.parametrize(
    "changes",
    [
        {},
        [],
        [{"idx": 0, "settings": {}}],
        [{"idx": True, "settings": {"token": "new"}}],
        [{"idx": -1, "settings": {"token": "new"}}],
        [{"idx": 2, "settings": {"token": "new"}}],
        [{"idx": 0}],
        [{"idx": 0, "settings": {"name": "same"}}],
        [{"idx": 0, "settings": {"token": 1}}],
        [{"idx": 0, "settings": {"ai_assistant_enabled": 1}}],
        [{"idx": 0, "settings": {"port": True}}],
        [{"idx": 0, "settings": {"port": 65536}}],
        [
            {"idx": 0, "settings": {"token": "a"}},
            {"idx": 0, "settings": {"token": "b"}},
        ],
        [
            {"idx": 0, "settings": {"token": "new"}},
            {"idx": 1, "settings": {"port": 65536}},
        ],
    ],
)
def test_invalid_batch_payloads_do_not_write_any_instance(manager, changes):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    with pytest.raises(ValueError):
        manager.update_all_settings(changes, manager.instances.copy())
    assert all(not Path(row["path"]).exists() for row in manager.instances)


def test_batch_rejects_changed_target_list_before_writing(manager):
    targets = manager.instances.copy()
    manager.rename(0, "changed")
    with pytest.raises(ValueError, match="实例列表已变化"):
        manager.update_all_settings(
            batch_changes(manager, {"ai_assistant_enabled": True}), targets
        )
    assert not Path(manager.instances[0]["path"]).exists()


def test_batch_failed_file_retains_previous_bytes_and_other_files_can_succeed(
    manager, monkeypatch
):
    manager.update_settings(0, {"token": "old", "port": None})
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    first = Path(manager.instances[0]["path"]) / "config/conf.yml"
    before = first.read_bytes()
    replace = runtime.replace_with_retry

    def fail_first(source, destination):
        if Path(destination) == first:
            raise PermissionError("locked")
        return replace(source, destination)

    monkeypatch.setattr(runtime, "replace_with_retry", fail_first)
    result = manager.update_all_settings(
        batch_changes(manager, {"token": "new"}), manager.instances.copy()
    )
    assert [item["status"] for item in result["results"]] == ["failed", "updated"]
    assert result["results"][0]["message"] == "locked"
    assert first.read_bytes() == before
    assert list(first.parent.iterdir()) == [first]
    _, second = controls.read_instance_config(manager.instances[1]["path"])
    assert second["webview"]["token"] == "new"


def test_batch_does_not_replace_unreadable_yaml_and_still_updates_other_instances(
    manager,
):
    root = Path(manager.instances[0]["path"])
    root.mkdir()
    broken = root / "conf.yml"
    broken.write_text("[invalid", encoding="utf-8")
    manager.add("second", str(root.parent / "second"))
    result = manager.update_all_settings(
        batch_changes(manager, {"ai_assistant_enabled": True}), manager.instances.copy()
    )
    assert [item["status"] for item in result["results"]] == ["failed", "updated"]
    assert broken.read_text(encoding="utf-8") == "[invalid"


def test_batch_rechecks_process_state_before_each_write(manager, monkeypatch):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    records = [[], [record(manager)]]
    records[1][0]["space"] = manager.instances[1]["path"]
    monkeypatch.setattr(runtime, "instances", Mock(side_effect=records))
    result = manager.update_all_settings(
        batch_changes(manager, {"ai_assistant_enabled": True}), manager.instances.copy()
    )
    assert [item["status"] for item in result["results"]] == ["updated", "skipped"]
    assert not Path(manager.instances[1]["path"]).exists()


@pytest.mark.parametrize("late", [False, True])
def test_batch_scan_failure_stops_unverified_writes(manager, monkeypatch, late):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    failure = runtime.InstanceScanError("unreadable")
    monkeypatch.setattr(
        runtime, "instances", Mock(side_effect=[[], failure] if late else failure)
    )
    if late:
        result = manager.update_all_settings(
            batch_changes(manager, {"ai_assistant_enabled": True}),
            manager.instances.copy(),
        )
        assert [item["status"] for item in result["results"]] == ["updated", "failed"]
    else:
        with pytest.raises(runtime.InstanceScanError):
            manager.update_all_settings(
                batch_changes(manager, {"ai_assistant_enabled": True}),
                manager.instances.copy(),
            )
        assert not Path(manager.instances[0]["path"]).exists()
    assert not Path(manager.instances[1]["path"]).exists()


def test_batch_stops_before_next_file_when_time_budget_expires(manager, monkeypatch):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    monkeypatch.setattr(controls, "monotonic", Mock(side_effect=[0, 0, 0, 11]))
    result = manager.update_all_settings(
        batch_changes(manager, {"ai_assistant_enabled": True}), manager.instances.copy()
    )
    assert [item["status"] for item in result["results"]] == ["updated", "failed"]
    assert "时间上限" in result["results"][1]["message"]
    assert not Path(manager.instances[1]["path"]).exists()


def test_batch_retry_skips_rewriting_completed_files_and_can_reach_remaining_work(
    manager, monkeypatch
):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    clock = [0]
    replace = runtime.replace_with_retry

    def slow_replace(source, destination):
        replace(source, destination)
        clock[0] += 11

    writer = Mock(side_effect=slow_replace)
    monkeypatch.setattr(runtime, "replace_with_retry", writer)
    monkeypatch.setattr(controls, "monotonic", lambda: clock[0])
    changes = batch_changes(manager, {"ai_assistant_enabled": True})
    targets = manager.instances.copy()
    first = manager.update_all_settings(changes, targets)
    assert [row["status"] for row in first["results"]] == ["updated", "failed"]
    second = manager.update_all_settings(changes, targets)
    assert [row["status"] for row in second["results"]] == ["updated", "updated"]
    assert second["results"][0]["message"] == "已符合设置"
    assert writer.call_count == 2


def test_batch_update_guard_skips_every_instance_during_software_operations(
    manager, monkeypatch
):
    monkeypatch.setattr(runtime, "active_job", lambda: True)
    result = manager.update_all_settings(
        batch_changes(manager, {"ai_assistant_enabled": True}), manager.instances.copy()
    )
    assert result["results"][0]["status"] == "skipped"
    assert "软件更新" in result["results"][0]["message"]
    assert not Path(manager.instances[0]["path"]).exists()


def test_settings_can_repair_invalid_connection_values_without_losing_other_fields(
    manager,
):
    root = Path(manager.instances[0]["path"])
    root.mkdir()
    (root / "conf.yml").write_text(
        "other: retained\nwebview: {port: invalid, token: 123}\n", encoding="utf-8"
    )
    assert not manager.get_instances()[0]["can_start"]
    manager.update_settings(0, {"token": "fixed", "port": None})
    assert read_conf(manager) == {
        "other": "retained",
        "webview": {"token": "fixed", "port": 0},
    }


def test_launch_registration_receives_stop_requested_before_it_exists(
    manager, monkeypatch
):
    assert manager.start(0)["ok"]
    env = controls.subprocess.Popen.call_args.kwargs["env"]
    assert manager.stop(0)["ok"]
    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setenv("MOWER_LAUNCH_ID", env["MOWER_LAUNCH_ID"])
    registration = runtime.RuntimeRegistration(
        "instance", space=manager.instances[0]["path"]
    )
    try:
        assert registration.id == env["MOWER_LAUNCH_ID"]
        assert registration.shutdown_requested()
        assert registration.record["managed"]
        assert "MOWER_LAUNCH_ID" not in controls.os.environ
    finally:
        runtime.atexit.unregister(registration.close)
        registration.close()


@pytest.mark.parametrize("value", ["../escape", "x" * 32, ""])
def test_invalid_launch_identity_never_selects_registration_path(
    manager, monkeypatch, value
):
    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setenv("MOWER_LAUNCH_ID", value)
    registration = runtime.RuntimeRegistration("instance")
    try:
        assert len(registration.id) == 32
        assert all(c in "0123456789abcdef" for c in registration.id)
        assert registration.path.parent == runtime.state_dir() / "instances"
    finally:
        runtime.atexit.unregister(registration.close)
        registration.close()


@pytest.mark.parametrize("port", [-1, 65536, 1.5, True, "58001"])
def test_invalid_port_does_not_write_configuration(manager, port):
    with pytest.raises(ValueError):
        manager.update_settings(0, {"token": "", "port": port})
    assert not Path(manager.instances[0]["path"]).exists()


def test_failed_write_preserves_config_and_instance_list(manager, monkeypatch):
    manager.update_settings(0, {"token": "old", "port": None})
    target = Path(manager.instances[0]["path"]) / "config/conf.yml"
    original = target.read_bytes()
    monkeypatch.setattr(
        runtime, "replace_with_retry", Mock(side_effect=PermissionError("locked"))
    )
    with pytest.raises(PermissionError):
        manager.update_settings(0, {"token": "new", "port": 58001})
    assert target.read_bytes() == original
    before = manager._storage_path.read_bytes()
    with pytest.raises(PermissionError):
        manager.rename(0, "changed")
    assert manager._storage_path.read_bytes() == before
    assert manager.instances[0]["name"] == "first"


def test_unreadable_registration_blocks_start_and_edit_without_overwrite(
    manager, monkeypatch
):
    monkeypatch.setattr(
        runtime, "instances", Mock(side_effect=runtime.InstanceScanError("unreadable"))
    )
    before = manager._storage_path.read_bytes()
    assert manager.start(0) == {"ok": False, "message": "unreadable"}
    with pytest.raises(runtime.InstanceScanError):
        manager.remove(0)
    controls.subprocess.Popen.assert_not_called()
    assert manager._storage_path.read_bytes() == before


def test_corrupt_files_are_not_reset(manager):
    root = Path(manager.instances[0]["path"])
    root.mkdir()
    config = root / "conf.yml"
    config.write_text("[invalid", encoding="utf-8")
    assert not manager.start(0)["ok"]
    with pytest.raises(yaml.YAMLError):
        manager.update_settings(0, {"token": "", "port": None})
    assert config.read_text() == "[invalid"
    manager._storage_path.write_text("[invalid", encoding="utf-8")
    with pytest.raises(ValueError):
        Api(manager._storage_path)
    assert manager._storage_path.read_text() == "[invalid"


def test_bulk_start_obeys_each_individual_start_guard(manager, monkeypatch):
    manager.add("unconfigured", "")
    manager.add("running", str(Path(manager.instances[0]["path"]).parent / "running"))
    live = dict(record(manager), space=manager.instances[2]["path"])
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [live])
    result = manager.start_all()
    assert result == {"ok": True, "message": ""}
    controls.subprocess.Popen.assert_called_once()
    assert controls.subprocess.Popen.call_args.args[0][-1] == "first"


def test_busy_update_blocks_bulk_start_and_all_config_changes(manager, monkeypatch):
    monkeypatch.setattr(runtime, "active_job", lambda: True)
    assert not manager.get_instances()[0]["can_start"]
    assert manager.start_all() == {"ok": True, "message": ""}
    with pytest.raises(ValueError, match="软件更新"):
        manager.rename(0, "changed")
    controls.subprocess.Popen.assert_not_called()


def test_busy_port_blocks_individual_and_bulk_start(manager, monkeypatch):
    manager.update_settings(0, {"token": "", "port": 58001})
    probe = Mock()
    probe.__enter__ = Mock(return_value=probe)
    probe.__exit__ = Mock(return_value=False)
    probe.bind.side_effect = OSError("busy")
    monkeypatch.setattr(controls.socket, "socket", Mock(return_value=probe))
    item = manager.get_instances()[0]
    assert not item["can_start"] and item["editable"]
    assert not manager.start(0)["ok"]
    assert manager.start_all() == {"ok": True, "message": ""}
    controls.subprocess.Popen.assert_not_called()


def test_bulk_start_keeps_spawn_errors_and_continues(manager):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    controls.subprocess.Popen.side_effect = [OSError("spawn failed"), Mock(pid=12345)]
    assert manager.start_all() == {"ok": False, "message": "spawn failed"}
    assert controls.subprocess.Popen.call_count == 2
    assert manager.get_instances()[1]["state"] == "starting"


def test_bulk_start_silently_skips_port_reserved_earlier_in_batch(manager, monkeypatch):
    probe = Mock()
    probe.__enter__ = Mock(return_value=probe)
    probe.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(controls.socket, "socket", Mock(return_value=probe))
    manager.update_settings(0, {"token": "", "port": 58001})
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    manager.update_settings(1, {"token": "", "port": 58001})
    assert manager.start_all() == {"ok": True, "message": ""}
    controls.subprocess.Popen.assert_called_once()


def test_fixed_port_is_reserved_before_http_server_is_ready(manager, monkeypatch):
    probe = Mock()
    probe.__enter__ = Mock(return_value=probe)
    probe.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(controls.socket, "socket", Mock(return_value=probe))
    manager.update_settings(0, {"token": "", "port": 58001})
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    manager.update_settings(1, {"token": "", "port": 58001})
    assert manager.start(0)["ok"]
    assert not manager.start(1)["ok"]
    assert (
        controls.subprocess.Popen.call_args.kwargs["env"]["MOWER_MANAGER_PORT"]
        == "58001"
    )
    controls.subprocess.Popen.assert_called_once()


def test_failed_spawn_releases_startability(manager, monkeypatch):
    monkeypatch.setattr(
        controls.subprocess, "Popen", Mock(side_effect=OSError("spawn failed"))
    )
    assert manager.start(0) == {"ok": False, "message": "spawn failed"}
    assert manager.get_instances()[0]["can_start"]


def test_bulk_stop_only_targets_configured_managed_instances(manager, monkeypatch):
    manager.add("second", str(Path(manager.instances[0]["path"]).parent / "second"))
    live = record(manager)
    other = dict(live, id="other", space="other-directory")
    second = dict(live, id="second", space=manager.instances[1]["path"])
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [live, other, second])
    send = Mock()
    monkeypatch.setattr(runtime, "send_instance_command", send)
    assert manager.stop_all()["ok"]
    assert {call.args[0]["id"] for call in send.call_args_list} == {
        "registered",
        "second",
    }
    assert all(call.args[1] == "exit" for call in send.call_args_list)


@pytest.mark.parametrize("token", ["", "secret"])
def test_managed_port_setting_is_independent_of_remote_token(token, monkeypatch):
    monkeypatch.setattr("arknights_mower.utils.network.get_new_port", lambda: 32100)
    conf = SimpleNamespace(token=token, port=58000)
    assert desktop_port(conf, True, manager_port="58001") == 58001
    assert desktop_port(conf, True, manager_port="0") == 32100
    assert desktop_port(conf, True, restart_port="58002", manager_port="0") == 58002
    assert desktop_port(conf, False) == (58000 if token else 32100)
    conf.port = 0
    assert desktop_port(conf, False) == 32100


def test_extra_settings_visibility_defaults_hidden_without_rewriting_old_config(
    manager,
):
    from arknights_mower.utils.config.conf import Conf

    assert Conf().extra_settings_visible is False
    assert manager.get_instances()[0]["extra_settings_visible"] is False
    manager.update_settings(0, {"token": "keep", "port": None})
    before = (Path(manager.instances[0]["path"]) / "config/conf.yml").read_bytes()
    assert manager.get_instances()[0]["extra_settings_visible"] is False
    assert (
        Path(manager.instances[0]["path"]) / "config/conf.yml"
    ).read_bytes() == before
    assert "extra_settings_visible" not in read_conf(manager)


@pytest.mark.parametrize("assistant", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_extra_settings_visibility_persists_without_changing_authorization(
    manager, enabled, assistant
):
    manager.update_settings(
        0,
        {
            "token": "keep",
            "port": None,
            "updates_enabled": False,
            "ai_assistant_enabled": assistant,
        },
    )
    manager.update_all_settings(
        batch_changes(manager, {"extra_settings_visible": enabled}),
        manager.instances.copy(),
    )
    reopened = Api(manager._storage_path)
    assert reopened.get_instances()[0]["extra_settings_visible"] is enabled
    saved = read_conf(reopened)
    assert saved["extra_settings_visible"] is enabled
    assert saved["updates_enabled"] is False
    assert saved["ai_assistant_enabled"] is assistant
    assert saved["webview"] == {"token": "keep", "port": 0}
    reopened.update_settings(
        0, {"token": "keep", "port": None, "extra_settings_visible": not enabled}
    )
    assert reopened.get_instances()[0]["extra_settings_visible"] is not enabled
    assert read_conf(reopened)["updates_enabled"] is False
    assert read_conf(reopened)["ai_assistant_enabled"] is assistant


@pytest.mark.parametrize("value", [None, 0, 1, "true", "false"])
def test_extra_settings_visibility_rejects_non_bool(manager, value):
    from pydantic import ValidationError

    from arknights_mower.utils.config.conf import Conf

    with pytest.raises(ValidationError):
        Conf(extra_settings_visible=value)
    with pytest.raises(ValueError, match="布尔值"):
        manager.update_settings(
            0, {"token": "", "port": None, "extra_settings_visible": value}
        )
    with pytest.raises(ValueError, match="布尔值"):
        manager.update_all_settings(
            batch_changes(manager, {"extra_settings_visible": value}),
            manager.instances.copy(),
        )
    assert not (Path(manager.instances[0]["path"]) / "config/conf.yml").exists()


def test_live_instance_cannot_change_extra_settings_visibility(manager, monkeypatch):
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [record(manager)])
    with pytest.raises(ValueError):
        manager.update_settings(
            0, {"token": "", "port": None, "extra_settings_visible": True}
        )
    result = manager.update_all_settings(
        batch_changes(manager, {"extra_settings_visible": True}),
        manager.instances.copy(),
    )
    assert result["results"][0]["status"] == "skipped"
    assert not (Path(manager.instances[0]["path"]) / "config/conf.yml").exists()
