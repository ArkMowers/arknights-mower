import inspect
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml
from yamlcore import CoreLoader

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


def test_bridge_does_not_expose_filesystem_objects(manager):
    assert not any(
        isinstance(value, Path)
        for name, value in inspect.getmembers(manager)
        if not name.startswith("_")
    )


def test_separate_api_objects_cannot_admit_concurrent_operations(manager):
    other = Api(manager._storage_path)
    with manager._operation():
        assert not other.start(0)["ok"]
    controls.subprocess.Popen.assert_not_called()
    assert other.start(0)["ok"]


def test_failed_reservation_write_closes_only_the_child_just_created(
    manager, monkeypatch
):
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
