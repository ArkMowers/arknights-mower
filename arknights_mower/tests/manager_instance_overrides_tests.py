from unittest.mock import Mock

import pytest
import yaml

from arknights_mower.tests.manager_connection_sharing_tests import (
    add_instance,
    edit_common,
    editor,
)
from arknights_mower.utils import manager_common as common
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.config.conf import Conf


@pytest.fixture
def manager(tmp_path, monkeypatch):
    from arknights_mower.utils.manager_instances import InstanceController

    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    return InstanceController(tmp_path / "instances.json")


def save_override(
    manager, state, target, *, changes=None, local_keys=None, manager_values=None
):
    return manager.update_device_settings(
        0,
        changes or {},
        target,
        state["values"],
        {
            "independent_configuration": state["independent_configuration"],
            "original_policy": state["original_policy"],
            "instance_override": {
                "local_keys": local_keys or [],
                "manager_values": manager_values or {},
            },
        },
    )


def test_instance_conf_overrides_win_at_launch_and_common_edits_keep_local_values(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(
        manager,
        tmp_path,
        "one",
        {"maa_path": "/local/maa", "screenshot": 7, "screenshot_archive_limit_mb": 123},
    )
    edit_common(
        manager, maa_path="/common/maa", screenshot=2, screenshot_archive_limit_mb=900
    )
    target, state = editor(manager)
    assert state["values"]["maa_path"] == "/common/maa"
    save_override(
        manager,
        state,
        target,
        changes={
            "maa_path": "/instance/maa",
            "screenshot": 8,
            "screenshot_archive_limit_mb": 456,
        },
        local_keys=["maa_path", "screenshot", "screenshot_archive_limit_mb"],
    )
    document = common.read_document(manager._common_path)
    assert document["version"] == 2
    assert document["instance_overrides"][common.policy_key(target["path"])] == {
        "local_keys": ["maa_path", "screenshot", "screenshot_archive_limit_mb"],
        "manager_values": {},
    }
    edit_common(manager, maa_path="/new/common", screenshot=3)
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    monkeypatch.setattr(common, "get_path", lambda path: tmp_path / "one")
    saved = Conf(**yaml.safe_load(path.read_text()))
    launched = common.for_launch(saved, managed=True)
    assert (
        launched.maa_path,
        launched.screenshot,
        launched.screenshot_archive_limit_mb,
    ) == ("/instance/maa", 8, 456)
    assert manager.get_maa_installations()["groups"][0]["target"] == "/instance/maa"
    target, state = editor(manager)
    save_override(manager, state, target)
    launched = common.for_launch(Conf(**yaml.safe_load(path.read_text())), managed=True)
    assert (launched.maa_path, launched.screenshot) == ("/new/common", 3)
    assert yaml.safe_load(path.read_text())["maa_path"] == "/instance/maa"


def test_manager_only_overrides_never_enter_conf_and_survive_global_save(
    manager, tmp_path
):
    _, path = add_instance(manager, tmp_path, "one", {})
    target, state = editor(manager)
    save_override(
        manager,
        state,
        target,
        manager_values={"startup_mode": "background", "instance_page_mode": "webview"},
    )
    raw = yaml.safe_load(path.read_text())
    assert not common.MANAGER_ONLY_KEYS & raw.keys()
    edit_common(manager, startup_mode="window", instance_page_mode="browser")
    document = common.read_document(manager._common_path)
    effective = common.instance_values(document, target["path"])
    assert effective["startup_mode"] == "background"
    assert effective["instance_page_mode"] == "webview"
    assert editor(manager)[1]["values"]["startup_mode"] == "background"


@pytest.mark.parametrize("change", ["global", "policy", "local", "running"])
def test_stale_or_running_editor_cannot_write_overrides(
    manager, tmp_path, monkeypatch, change
):
    _, path = add_instance(manager, tmp_path, "one", {})
    target, state = editor(manager)
    if change == "global":
        edit_common(manager, screenshot=3)
    elif change == "policy":
        save_override(manager, state, target, local_keys=["screenshot"])
    elif change == "local":
        raw = yaml.safe_load(path.read_text())
        raw["screenshot"] = 4
        path.write_text(yaml.safe_dump(raw))
    else:
        monkeypatch.setattr(
            manager, "_records", lambda: [dict(kind="instance", space=target["path"])]
        )
    before = (path.read_bytes(), manager._common_path.read_bytes())
    with pytest.raises(ValueError):
        save_override(manager, state, target, local_keys=["maa_path"])
    assert (path.read_bytes(), manager._common_path.read_bytes()) == before


def test_failed_common_save_restores_both_files_after_replace(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(manager, tmp_path, "one", {})
    target, state = editor(manager)
    before = (path.read_bytes(), manager._common_path.read_bytes())
    write = runtime.write_json

    def failed(destination, data, **kwargs):
        write(destination, data, **kwargs)
        raise OSError("after replacement")

    monkeypatch.setattr(runtime, "write_json", failed)
    with pytest.raises(OSError, match="after replacement"):
        save_override(
            manager, state, target, changes={"screenshot": 5}, local_keys=["screenshot"]
        )
    assert (path.read_bytes(), manager._common_path.read_bytes()) == before


@pytest.mark.parametrize(
    "override",
    [
        {"local_keys": ["startup_mode"], "manager_values": {}},
        {"local_keys": ["screenshot", "screenshot"], "manager_values": {}},
        {"local_keys": [], "manager_values": {"maa_path": "/other"}},
        {"local_keys": [], "manager_values": {"startup_mode": "bad"}},
        {"local_keys": [], "manager_values": {}, "unknown": True},
    ],
)
def test_invalid_version_two_override_is_rejected_without_writing(
    manager, tmp_path, override
):
    add_instance(manager, tmp_path, "one", {})
    values = manager.get_common_settings()["values"]
    data = dict(
        version=2,
        values=values,
        independent_instances={},
        instance_overrides={str(tmp_path / "one"): override},
    )
    runtime.write_json(manager._common_path, data)
    before = manager._common_path.read_bytes()
    with pytest.raises(ValueError):
        manager.get_common_settings()
    assert manager._common_path.read_bytes() == before


def test_manager_start_uses_local_background_mode(manager, tmp_path, monkeypatch):
    from arknights_mower.utils import manager_instances as controls

    add_instance(manager, tmp_path, "one", {})
    edit_common(manager, startup_mode="window")
    target, state = editor(manager)
    save_override(manager, state, target, manager_values={"startup_mode": "background"})
    spawned = Mock(return_value=Mock(pid=1234))
    monkeypatch.setattr(controls.subprocess, "Popen", spawned)
    monkeypatch.setattr(controls.threading, "Thread", Mock())
    assert manager.start(0, target)["ok"]
    assert spawned.call_args.kwargs["env"]["MOWER_BACKGROUND"] == "1"


def test_maintenance_admission_and_preview_use_local_maa_path(manager, tmp_path):
    add_instance(manager, tmp_path, "one", {"maa_path": "/instance/maa"})
    edit_common(manager, maa_path="/common/maa", screenshot=2)
    target, state = editor(manager)
    save_override(manager, state, target, local_keys=["maa_path", "screenshot"])
    manager._maintenance_job = dict(
        status="running", action="update", target="/instance/maa"
    )
    result = manager.start(0, target)
    assert not result["ok"] and "MAA 正在更新" in result["message"]
    values = manager.get_common_settings()["values"]
    result = manager.preview_common_settings(
        {**values, "maa_path": "/other", "screenshot": 3}, manager.instances.copy()
    )
    labels = {field["label"] for field in result["rows"][0]["fields"]}
    assert "MAA 安装目录" not in labels
    assert "截图保存时间（小时）" not in labels


def test_import_projection_does_not_modify_override_document(
    manager, tmp_path, monkeypatch
):
    from arknights_mower.utils import managed_device

    _, path = add_instance(manager, tmp_path, "one", {"screenshot": 7})
    edit_common(manager, screenshot=2)
    target, state = editor(manager)
    save_override(
        manager,
        state,
        target,
        local_keys=["screenshot"],
        manager_values={"startup_mode": "background"},
    )
    before = manager._common_path.read_bytes()
    document = common.read_document(manager._common_path)
    current = common.apply_settings(
        Conf(**yaml.safe_load(path.read_text())),
        common.instance_values(document, target["path"]),
    )
    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    imported = managed_device.preserve(
        {"screenshot": 99, "maa_path": "/unrelated"}, current
    )
    assert imported["screenshot"] == 7
    assert not common.MANAGER_ONLY_KEYS & imported.keys()
    assert manager._common_path.read_bytes() == before
