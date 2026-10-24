import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from arknights_mower.utils import manager_tools as tools
from arknights_mower.utils import network_settings as network
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.manager_instances import InstanceController


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    controller = InstanceController(tmp_path / "instances.json")
    controller.add("one", str(tmp_path / "one"))
    controller.add("two", str(tmp_path / "two"))
    return controller


def write_conf(manager, index, values):
    path = Path(manager.instances[index]["path"]) / "config/conf.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(values), encoding="utf-8")
    return path


def test_batch_automatic_start_only_changes_selected_rows_and_preserves_permissions(
    manager,
):
    path = write_conf(
        manager,
        0,
        {
            "private": "keep",
            "updates_enabled": False,
            "ai_assistant_enabled": False,
            "webview": {"token": "secret", "port": 58001},
        },
    )
    result = manager.update_all_settings(
        [{"idx": 0, "settings": {"start_automatically": True}}],
        manager.instances.copy(),
    )
    assert result["results"][0]["status"] == "updated"
    assert yaml.safe_load(path.read_text()) == {
        "private": "keep",
        "updates_enabled": False,
        "ai_assistant_enabled": False,
        "start_automatically": True,
        "webview": {"token": "secret", "port": 58001},
    }
    assert manager.get_instances()[0]["start_automatically"] is True
    assert not (Path(manager.instances[1]["path"]) / "config/conf.yml").exists()
    with pytest.raises(ValueError):
        manager.update_all_settings(
            [{"idx": 0, "settings": {"start_automatically": 1}}],
            manager.instances.copy(),
        )


def test_common_preview_is_read_only_redacts_both_secrets_and_reports_native_mismatch(
    manager,
):
    path = write_conf(
        manager,
        0,
        {"device": {"preset_id": "windows.ldplayer9"}, "pass_code": "old-secret"},
    )
    before = path.read_bytes()
    result = manager.preview_common_settings(
        {
            "pass_code": "new-secret",
            "device.screenshot_backend": "mumu_ipc",
            "device.touch_backend": "mumu_ipc",
        },
        manager.instances.copy(),
    )
    assert "MuMu" in result["rows"][0]["warnings"][0]
    assert result["future_instances"] is True
    serialized = json.dumps(result)
    assert "old-secret" not in serialized and "new-secret" not in serialized
    assert result["rows"][0]["fields"][2]["after"] == "已设置"
    assert path.read_bytes() == before
    assert not manager._common_path.exists()
    with pytest.raises(ValueError, match="实例列表"):
        manager.preview_common_settings({}, [])


def test_proxy_entry_reuses_shared_file_and_rejects_stale_and_corrupt_data(
    manager, tmp_path, monkeypatch
):
    path = tmp_path / "network.json"
    monkeypatch.setattr(network, "settings_path", lambda: path)
    monkeypatch.setattr(network, "apply_http_proxy", Mock())
    original = manager.get_network_settings()
    changed = {
        "http_proxy": "http://127.0.0.1:7890",
        "github_proxy": "https://proxy.example/",
    }
    assert manager.save_network_settings(changed, original) == changed
    assert json.loads(path.read_text()) == changed
    with pytest.raises(ValueError, match="已变化"):
        manager.save_network_settings(original, original)
    path.write_text("not json")
    with pytest.raises(ValueError):
        manager.get_network_settings()
    with pytest.raises(ValueError):
        manager.save_network_settings(original, original)
    assert path.read_text() == "not json"


def test_storage_reports_aliases_without_double_counting_and_does_not_follow_links(
    manager, tmp_path
):
    root = Path(manager.instances[0]["path"])
    (root / "log").mkdir(parents=True)
    (root / "log/runtime.log").write_bytes(b"abc")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep").write_bytes(b"x" * 100)
    (root / "screenshot").symlink_to(outside, target_is_directory=True)
    manager.add("alias", str(root / ".." / "one"))
    result = manager.get_storage_usage()["rows"]
    assert result[0]["log"] == 3 and result[0]["screenshot"] == 0
    assert "符号链接" in result[0]["warning"]
    assert result[2]["log"] == 0 and "不重复计数" in result[2]["warning"]


def test_cleanup_age_scope_target_and_stopped_process_checks(manager, monkeypatch):
    root = Path(manager.instances[0]["path"])
    (root / "log").mkdir(parents=True)
    old = root / "log/old.log"
    new = root / "log/runtime.log"
    old.write_bytes(b"old")
    new.write_bytes(b"new")
    os.utime(old, (1, 1))
    config = write_conf(manager, 0, {"private": "keep"})
    target = manager.instances[0].copy()
    result = manager.clean_instance_storage(0, target, ["log"], 7)
    assert result == {"ok": True, "deleted": 1, "freed": 3, "errors": []}
    assert not old.exists() and new.exists() and config.exists()
    monkeypatch.setattr(
        runtime,
        "instances",
        lambda **kwargs: [{"kind": "instance", "space": str(root), "managed": True}],
    )
    with pytest.raises(ValueError, match="运行期间"):
        manager.clean_instance_storage(0, target, ["log"], 0)
    assert new.exists()
    with pytest.raises(ValueError, match="已变化"):
        manager.clean_instance_storage(
            0, {"name": "wrong", "path": str(root)}, ["log"], 0
        )
    with pytest.raises(ValueError, match="范围"):
        manager.clean_instance_storage(0, target, ["config"], 0)


def test_cleanup_leaves_symlink_targets_and_private_data_untouched(manager, tmp_path):
    root = Path(manager.instances[0]["path"])
    (root / "log").mkdir(parents=True)
    outside = tmp_path / "keep"
    outside.write_text("private")
    (root / "log/link").symlink_to(outside)
    (root / "database.db").write_text("database")
    manager.clean_instance_storage(0, manager.instances[0].copy(), ["log"], 0)
    assert outside.read_text() == "private"
    assert (root / "database.db").read_text() == "database"


def test_maa_groups_effective_paths_aliases_channels_and_permissions(manager, tmp_path):
    shared = tmp_path / "maa"
    write_conf(manager, 0, {"maa_path": str(shared), "maa_update_channel": "beta"})
    write_conf(
        manager, 1, {"maa_path": str(shared / ".." / "maa"), "updates_enabled": False}
    )
    groups = manager.get_maa_installations()["groups"]
    assert len(groups) == 1
    assert groups[0]["instances"] == ["one", "two"]
    assert groups[0]["channels"] == ["beta", "stable"]
    assert groups[0]["updates_enabled"] is False
    with pytest.raises(ValueError, match="允许更新"):
        manager.start_maa_maintenance(str(shared), "stable", "core", "check")


def test_maa_update_requires_fresh_matching_check_and_stopped_instances(
    manager, tmp_path, monkeypatch
):
    shared = tmp_path / "maa"
    for idx in range(2):
        write_conf(manager, idx, {"maa_path": str(shared)})
    with pytest.raises(ValueError, match="先检查"):
        manager.start_maa_maintenance(str(shared), "stable", "core", "update")
    manager._maa_check = dict(
        target=str(shared),
        channel="stable",
        component="core",
        available=True,
        time=tools.monotonic(),
    )
    monkeypatch.setattr(
        runtime,
        "instances",
        lambda **kwargs: [{"kind": "instance", "space": manager.instances[0]["path"]}],
    )
    with pytest.raises(ValueError, match="先停止"):
        manager.start_maa_maintenance(str(shared), "stable", "core", "update")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    thread = Mock()
    monkeypatch.setattr(tools.threading, "Thread", Mock(return_value=thread))
    assert manager.start_maa_maintenance(str(shared), "stable", "core", "update")["ok"]
    assert not manager.request_close()
    with pytest.raises(ValueError, match="正在更新"):
        manager._start_settings(manager.instances[0], [])
    assert manager._maa_check == {}
    thread.start.assert_called_once()


def test_maa_check_uses_existing_release_client_and_update_retains_backup_installer(
    manager, tmp_path, monkeypatch
):
    from arknights_mower.utils import maa_resource_update, maa_update

    shared = str(tmp_path / "maa")
    monkeypatch.setattr(
        maa_update, "read_installed_version", lambda *args, **kwargs: "v1.0.0"
    )
    monkeypatch.setattr(maa_update, "has_maa_installation", lambda *args: True)
    monkeypatch.setattr(
        maa_update, "get_latest_release", lambda **kwargs: SimpleNamespace(tag="v2.0.0")
    )
    install = Mock(return_value={"updated": True, "version": "v2.0.0"})
    monkeypatch.setattr(maa_update, "install_latest_maa", install)
    manager._maa_worker(shared, "stable", "core", "check", {})
    snapshot = manager.get_maintenance_status()
    assert snapshot["status"] == "completed" and snapshot["result"]["available"]
    check = manager._maa_check.copy()
    manager._maa_worker(shared, "stable", "core", "update", check)
    assert manager.get_maintenance_status()["result"]["updated"]
    install.assert_called_once()
    monkeypatch.setattr(
        maa_update, "read_installed_version", lambda *args, **kwargs: "v1.5.0"
    )
    manager._maa_worker(shared, "stable", "core", "update", check)
    assert manager.get_maintenance_status()["status"] == "failed"
    install.assert_called_once()
    monkeypatch.setattr(
        maa_resource_update,
        "read_maa_resource_info",
        lambda target: {"version": "2026-10-01"},
    )
    monkeypatch.setattr(
        maa_resource_update,
        "get_maa_resource_release",
        lambda *args, **kwargs: SimpleNamespace(available=False, version="2026-10-01"),
    )
    manager._maa_worker(shared, "stable", "resource", "check", {})
    assert manager.get_maintenance_status()["result"]["available"] is False


def test_maintenance_failure_is_reported_and_allows_closing(manager, monkeypatch):
    monkeypatch.setattr(
        manager, "_run_maa_worker", Mock(side_effect=RuntimeError("failed"))
    )
    manager._maa_worker("target", "stable", "core", "check", {})
    assert manager.get_maintenance_status()["status"] == "failed"
    assert manager.request_close()


def test_native_manager_close_hides_active_maintenance_and_tray_exit_is_rejected(
    manager, monkeypatch
):
    import manager as desktop
    from arknights_mower.utils import desktop_process

    handlers = {}

    class Event:
        def __init__(self, name):
            self.name = name

        def __iadd__(self, callback):
            handlers[self.name] = callback
            return self

    window = Mock()
    window.events = SimpleNamespace(closing=Event("closing"), closed=Event("closed"))
    monkeypatch.setattr(desktop_process, "watch_parent", Mock())
    monkeypatch.setattr(desktop, "Api", lambda **kwargs: manager)
    monkeypatch.setattr(desktop.webview, "create_window", Mock(return_value=window))
    monkeypatch.setattr(desktop.webview, "start", Mock())
    thread = Mock()
    factory = Mock(return_value=thread)
    monkeypatch.setattr(tools.threading, "Thread", factory)
    connection = Mock()
    desktop.manager_window(connection, Mock(), Mock())
    manager._maintenance_job = {"status": "running"}
    assert handlers["closing"]() is False
    window.hide.assert_called_once()
    connection.recv.side_effect = ["request_exit", EOFError()]
    factory.call_args.kwargs["target"]()
    connection.send.assert_called_with(False)
    window.destroy.assert_not_called()
    manager._maintenance_job["status"] = "completed"
    connection.recv.side_effect = ["request_exit"]
    factory.call_args.kwargs["target"]()
    connection.send.assert_called_with(True)
    window.destroy.assert_called_once()


def test_manager_mower_update_bridge_delegates_without_changing_web_update_api(
    manager, monkeypatch
):
    from arknights_mower.utils import software_update as updater

    details = {"ok": True, "version": "current", "blockers": []}
    monkeypatch.setattr(updater, "info", Mock(return_value=details))
    monkeypatch.setattr(updater, "check", Mock(return_value={"check_id": "receipt"}))
    monkeypatch.setattr(updater, "submit", Mock(return_value={"ok": True, "id": "job"}))
    monkeypatch.setattr(updater, "status", Mock(return_value={"status": "running"}))
    monkeypatch.setattr(updater, "cancel", Mock(return_value={"ok": True}))
    assert manager.get_mower_update_info() == details
    assert manager.check_mower_update("beta") == {"check_id": "receipt"}
    updater.check.assert_called_once_with("beta")
    assert manager.start_mower_update("receipt", True)["id"] == "job"
    updater.submit.assert_called_once_with("receipt", True)
    assert manager.get_mower_update_status()["status"] == "running"
    assert manager.cancel_mower_update("job")["ok"]
    updater.cancel.assert_called_once_with("job")
    with pytest.raises(ValueError, match="请求无效"):
        manager.start_mower_update("receipt", 1)
    manager._maintenance_job = {"status": "running"}
    with pytest.raises(ValueError, match="MAA 维护"):
        manager.start_mower_update("receipt", True)
    assert updater.submit.call_count == 1


@pytest.mark.parametrize(
    "pid,kind,allowed",
    [
        (111, "instance", True),
        (222, "manager", True),
        (333, "manager", False),
        (222, "instance", False),
    ],
)
def test_software_update_accepts_registered_manager_parent_and_retains_desktop_boundary(
    tmp_path, monkeypatch, pid, kind, allowed
):
    from arknights_mower.utils import software_update as updater

    monkeypatch.setattr(updater.os, "getpid", lambda: 111)
    monkeypatch.setattr(updater.os, "getppid", lambda: 222)
    monkeypatch.setattr(runtime, "installation_root", lambda: tmp_path)
    monkeypatch.setattr(runtime, "frozen", lambda: True)
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "updates")
    monkeypatch.setattr(
        runtime,
        "instances",
        lambda: [{"pid": pid, "kind": kind, "name": "test", "running": True}],
    )
    monkeypatch.setattr(updater, "get_settings", lambda: {})
    monkeypatch.setattr(
        updater.network_settings, "get_effective_settings", lambda: {"http_proxy": ""}
    )
    result = updater.info()
    assert bool(result["blockers"]) is not allowed
    assert result["ok"]


def test_cleanup_reports_completed_deletions_when_later_category_is_a_link(
    manager, tmp_path
):
    root = Path(manager.instances[0]["path"])
    (root / "log").mkdir(parents=True)
    (root / "log/old.log").write_bytes(b"old")
    outside = tmp_path / "archive"
    outside.mkdir()
    (outside / "keep").write_text("keep")
    (root / "screenshot").symlink_to(outside, target_is_directory=True)
    result = manager.clean_instance_storage(
        0, manager.instances[0].copy(), ["log", "screenshot"], 0
    )
    assert result["deleted"] == 1 and result["freed"] == 3
    assert "符号链接" in result["errors"][0]
    assert (outside / "keep").read_text() == "keep"
