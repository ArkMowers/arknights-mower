import copy
import json
from unittest.mock import Mock

import pytest
import yaml

from arknights_mower.utils import managed_device
from arknights_mower.utils import manager_common as common
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.manager_instances import InstanceController


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.setattr(runtime, "state_dir", lambda: tmp_path / "runtime")
    monkeypatch.setattr(runtime, "instances", lambda **kwargs: [])
    monkeypatch.setattr(runtime, "active_job", lambda: False)
    return InstanceController(tmp_path / "instances.json")


def add_instance(manager, root, name, raw):
    directory = root / name
    path = directory / "config/conf.yml"
    path.parent.mkdir(parents=True)
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    manager.add(name, str(directory))
    return len(manager.instances) - 1, path


def edit_common(manager, **changes):
    original = manager.get_common_settings()["values"]
    manager.update_all_settings(
        [],
        manager.instances.copy(),
        {"values": {**original, **changes}, "original": original},
    )


def editor(manager, idx=0):
    target = manager.instances[idx].copy()
    return target, manager.get_device_settings(idx, target)


def editor_values(configuration):
    return {
        **managed_device.snapshot(configuration),
        "screenshot": configuration.screenshot,
        "screenshot_archive_limit_mb": configuration.screenshot_archive_limit_mb,
        "startup_mode": "window",
        "instance_page_mode": "browser",
    }


def set_independent(manager, enabled, idx=0, changes=None):
    target, state = editor(manager, idx)
    return manager.update_device_settings(
        idx,
        changes or {},
        target,
        state["values"],
        {
            "independent_configuration": enabled,
            "original_policy": state["original_policy"],
        },
    )


def test_common_schema_excludes_instance_binding_and_includes_connection_commands(
    manager,
):
    schema = manager.get_common_settings()
    fields = {field["key"]: field for field in schema["fields"]}
    for key in (
        "device.instance_id",
        "device.instance_name",
        "device.instance_uuid",
        "device.topology_fingerprint",
        "device.last_serial",
        "device.game_package",
    ):
        assert key not in fields
        assert key not in common.SHARED_CONNECTION_KEYS
    for key in (
        "device.preset_id",
        "device.installation_path",
        "device.manager_path",
        "device.config_path",
        "custom_screenshot.command",
        "tap_to_launch_game.command",
        "device.recovery_timeout",
        "performance_mode",
        "simulator.wait_time",
    ):
        assert fields[key]["shared_connection"] is True
        assert key in schema["values"]


def test_migration_uses_one_coherent_baseline_and_retains_explicit_conflicting_instances(
    manager, tmp_path
):
    first, first_path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "instance_id": "7",
                "last_serial": "127.0.0.1:17007",
                "screenshot_backend": "mumu_ipc",
                "touch_backend": "mumu_ipc",
            },
            "close_simulator_when_idle": True,
        },
    )
    second, second_path = add_instance(
        manager,
        tmp_path,
        "second",
        {
            "device": {
                "preset_id": "windows.ldplayer9",
                "instance_id": "8",
                "last_serial": "127.0.0.1:17008",
                "screenshot_backend": "adb_gzip",
            },
            "exit_game_when_idle": True,
            "custom_screenshot": {"command": "different capture"},
        },
    )
    before = [path.read_bytes() for path in (first_path, second_path)]
    expected_second = editor_values(Conf(**yaml.safe_load(second_path.read_text())))
    baseline = manager.get_common_settings()["values"]
    assert (
        baseline["device.screenshot_backend"]
        == baseline["device.touch_backend"]
        == "mumu_ipc"
    )
    assert baseline["close_simulator_when_idle"] is True
    assert baseline["exit_game_when_idle"] is False
    assert editor(manager, first)[1]["independent_configuration"] is False
    second_state = editor(manager, second)[1]
    assert second_state["independent_configuration"] is True
    assert second_state["values"] == expected_second
    assert [path.read_bytes() for path in (first_path, second_path)] == before
    reopened = InstanceController(manager._storage_path)
    assert editor(reopened, second)[1]["values"] == expected_second


def test_legacy_flat_common_values_materialize_the_effective_binding(manager, tmp_path):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "installation_path": "C:/own",
                "manager_path": "C:/own/manager.exe",
                "config_path": "C:/own/config",
                "instance_id": "3",
                "instance_uuid": "vm-three",
                "topology_fingerprint": "topology-three",
                "last_serial": "127.0.0.1:17003",
                "game_package": "com.hypergryph.arknights.bilibili",
            },
            "performance_mode": "high",
            "account": "personal sender",
            "pass_code": "personal secret",
            "custom_smtp_server": {
                "enable": True,
                "server": "smtp.personal.example.com",
            },
        },
    )
    manager._common_path.parent.mkdir(parents=True)
    manager._common_path.write_text(
        json.dumps(
            {
                "device.installation_path": "C:/foreign",
                "device.manager_path": "C:/foreign/manager.exe",
                "performance_mode": "low",
                "account": "shared sender",
                "startup_mode": "background",
                "instance_page_mode": "webview",
            }
        )
    )
    original = Conf(**yaml.safe_load(path.read_text()))
    expected = original.updated(
        {
            "device": {
                "installation_path": "C:/foreign",
                "manager_path": "C:/foreign/manager.exe",
            },
            "performance_mode": "low",
        }
    )
    target, state = editor(manager)
    assert state["independent_configuration"] is True
    assert state["values"]["device"] == expected.device.model_dump()
    assert state["values"]["performance_mode"] == "high"
    changed = common.apply_settings(
        Conf(**yaml.safe_load(path.read_text())),
        manager.get_common_settings()["values"],
        independent=True,
    )
    assert changed.device.model_dump() == expected.device.model_dump()
    assert changed.account == original.account
    assert changed.pass_code == original.pass_code
    assert changed.custom_smtp_server == original.custom_smtp_server
    persisted = yaml.safe_load(path.read_text())
    assert persisted["account"] == "personal sender"
    assert persisted["pass_code"] == "personal secret"
    assert persisted["custom_smtp_server"]["server"] == "smtp.personal.example.com"
    assert "startup_mode" not in yaml.safe_load(path.read_text())
    assert "instance_page_mode" not in yaml.safe_load(path.read_text())
    assert (
        manager.get_common_settings()["values"]["device.installation_path"]
        == "C:/foreign"
    )
    assert (
        manager.get_common_settings()["values"]["device.manager_path"]
        == "C:/foreign/manager.exe"
    )
    assert target == {"name": "first", "path": str(path.parent.parent)}


@pytest.mark.parametrize("independent", [False, True])
def test_versioned_sender_removal_preserves_instance_mail_and_connection_policy(
    manager, tmp_path, monkeypatch, independent
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "account": "personal@example.com",
            "pass_code": "personal-secret",
            "custom_smtp_server": {
                "enable": True,
                "server": "smtp.personal.example.com",
                "encryption": "tls",
                "ssl_port": 465,
            },
            "recipient": ["owner@example.com"],
            "mail_enable": 0,
            "performance_mode": "high",
        },
    )
    manager.get_common_settings()
    document = json.loads(manager._common_path.read_text())
    policy_key = common.policy_key(path.parent.parent)
    document["independent_instances"][policy_key] = independent
    document["values"].update(
        {
            "performance_mode": "low",
            "account": "shared@example.com",
            "pass_code": "shared-secret",
            "custom_smtp_server.enable": False,
            "custom_smtp_server.server": "smtp.shared.example.com",
            "custom_smtp_server.encryption": "starttls",
            "custom_smtp_server.ssl_port": 587,
        }
    )
    manager._common_path.write_text(json.dumps(document), encoding="utf-8")
    before = path.read_bytes()
    original = Conf(**yaml.safe_load(before))
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    monkeypatch.setattr(common, "get_path", lambda *args: path.parent.parent)
    launched = common.for_launch(original, managed=True)
    assert launched.account == original.account
    assert launched.pass_code == original.pass_code
    assert launched.custom_smtp_server == original.custom_smtp_server
    assert launched.recipient == original.recipient
    assert launched.mail_enable == original.mail_enable
    assert launched.performance_mode == ("high" if independent else "low")
    schema = manager.get_common_settings()
    assert "account" not in schema["values"]
    assert "pass_code" not in schema["values"]
    assert not any(key.startswith("custom_smtp_server.") for key in schema["values"])
    assert editor(manager)[1]["independent_configuration"] is independent
    edit_common(manager, screenshot=7)
    persisted = json.loads(manager._common_path.read_text())
    assert persisted["independent_instances"] == {policy_key: independent}
    assert persisted["values"] == {**schema["values"], "screenshot": 7}
    assert path.read_bytes() == before


def test_legacy_flat_paths_remain_shared_without_instance_or_preview_writes(
    manager, tmp_path
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "instance_id": "3",
                "last_serial": "127.0.0.1:17003",
            },
            "private_extension": {"keep": True},
        },
    )
    manager._common_path.parent.mkdir(parents=True)
    legacy = {
        "device.installation_path": "C:/MuMuPlayer-12.0",
        "device.manager_path": "C:/MuMuPlayer-12.0/shell/MuMuManager.exe",
    }
    manager._common_path.write_text(json.dumps(legacy))
    before = path.read_bytes(), manager._common_path.read_bytes()
    original = Conf(**yaml.safe_load(path.read_text()))
    expected = original.updated(
        {"device": {key.split(".")[1]: value for key, value in legacy.items()}}
    )
    manager.preview_common_settings(legacy, manager.instances.copy())
    assert (path.read_bytes(), manager._common_path.read_bytes()) == before
    manager.get_common_settings()
    stored = yaml.safe_load(path.read_text())
    assert path.read_bytes() == before[0]
    assert editor(manager)[1]["values"]["device"] == expected.device.model_dump()
    assert editor(manager)[1]["independent_configuration"] is False
    assert stored["private_extension"] == {"keep": True}
    assert original.device.installation_path == ""
    assert original.device.last_serial == "127.0.0.1:17003"
    after = path.read_bytes(), manager._common_path.read_bytes()
    manager.get_common_settings()
    assert (path.read_bytes(), manager._common_path.read_bytes()) == after


@pytest.mark.parametrize(
    "failure", ["second_instance", "global_before", "global_after"]
)
def test_legacy_path_migration_rolls_back_all_original_bytes(
    manager, tmp_path, monkeypatch, failure
):
    paths = []
    for name in ("first", "second"):
        _, path = add_instance(
            manager,
            tmp_path,
            name,
            {
                "device": {"preset_id": "windows.mumu12", "instance_id": name},
                "private_extension": {"keep": name},
                "performance_mode": "high",
            },
        )
        path.write_text("# preserve this comment\n" + path.read_text())
        paths.append(path)
    manager._common_path.parent.mkdir(parents=True)
    manager._common_path.write_text(
        '{\n  "device.installation_path": "C:/shared", "performance_mode": "low"\n}\n'
    )
    originals = [path.read_bytes() for path in (*paths, manager._common_path)]
    write_config = manager._write_config
    write_json = runtime.write_json
    if failure == "second_instance":

        def fail_second(path, raw):
            write_config(path, raw)
            if path == paths[1]:
                raise OSError("migration failed")

        monkeypatch.setattr(manager, "_write_config", fail_second)
    else:

        def fail_global(path, raw, **kwargs):
            if failure == "global_after":
                write_json(path, raw, **kwargs)
            raise OSError("migration failed")

        monkeypatch.setattr(runtime, "write_json", fail_global)
    with pytest.raises(OSError, match="migration failed"):
        manager.get_common_settings()
    assert [path.read_bytes() for path in (*paths, manager._common_path)] == originals


def test_failed_legacy_path_migration_removes_new_config_and_preserves_legacy_source(
    manager, tmp_path, monkeypatch
):
    directory = tmp_path / "legacy-instance"
    directory.mkdir()
    legacy = directory / "conf.yml"
    legacy.write_text(
        "# legacy source\nperformance_mode: high\ndevice:\n  preset_id: windows.mumu12\n"
    )
    manager.add("legacy", str(directory))
    manager._common_path.parent.mkdir(parents=True)
    manager._common_path.write_text(
        '{"device.installation_path": "C:/shared", "performance_mode": "low"}'
    )
    originals = legacy.read_bytes(), manager._common_path.read_bytes()
    monkeypatch.setattr(runtime, "write_json", Mock(side_effect=OSError("failed")))
    with pytest.raises(OSError, match="failed"):
        manager.get_common_settings()
    assert (legacy.read_bytes(), manager._common_path.read_bytes()) == originals
    assert not (directory / "config/conf.yml").exists()


@pytest.mark.parametrize(
    "raw", [{"device": {"recovery_timeout": 900}}, {"screenshot_interval": 120000}]
)
@pytest.mark.parametrize("compatible_baseline", [False, True])
def test_unrepresentable_legacy_values_remain_independent_without_blocking_migration(
    manager, tmp_path, monkeypatch, raw, compatible_baseline
):
    idx, path = add_instance(manager, tmp_path, "unrepresentable", raw)
    if compatible_baseline:
        add_instance(manager, tmp_path, "baseline", {"performance_mode": "low"})
    before = path.read_bytes()
    original = Conf(**yaml.safe_load(path.read_text()))
    values = manager.get_common_settings()["values"]
    assert common.validate_settings(values) == values
    expected = Conf(performance_mode="low") if compatible_baseline else Conf()
    assert values["performance_mode"] == expected.performance_mode
    state = editor(manager, idx)[1]
    assert state["independent_configuration"] is True
    assert state["values"] == editor_values(original)
    assert path.read_bytes() == before
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    monkeypatch.setattr(common, "get_path", lambda *args, **kwargs: path.parent.parent)
    assert (
        common.for_launch(original, managed=True).model_dump() == original.model_dump()
    )
    monkeypatch.setattr(
        "arknights_mower.utils.manager_instances.subprocess.Popen",
        Mock(return_value=Mock(pid=987654)),
    )
    assert manager.start(idx, manager.instances[idx].copy()) == {"ok": True}
    assert path.read_bytes() == before


def test_invalid_explicit_legacy_common_value_is_not_replaced_by_valid_baseline(
    manager,
):
    manager._common_path.parent.mkdir(parents=True)
    manager._common_path.write_text('{"device.recovery_timeout": 900}')
    before = manager._common_path.read_bytes()
    with pytest.raises(ValueError):
        manager.get_common_settings()
    assert manager._common_path.read_bytes() == before


def test_shared_changes_are_launch_snapshots_and_never_write_instance_files(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "manual.other",
                "last_serial": "host:18001",
                "game_package": "com.hypergryph.arknights.bilibili",
            }
        },
    )
    _, state = editor(manager)
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    monkeypatch.setattr(common, "get_path", lambda *args, **kwargs: path.parent.parent)
    before = path.read_bytes()
    original = Conf(**yaml.safe_load(path.read_text()))
    running = common.for_launch(original, managed=True)
    edit_common(
        manager,
        performance_mode="low",
        **{
            "device.recovery_timeout": 245,
            "custom_screenshot.command": "shared capture",
        },
    )
    later = common.for_launch(original, managed=True)
    assert running.performance_mode == state["values"]["performance_mode"]
    assert later.performance_mode == "low"
    assert later.device.recovery_timeout == 245
    assert later.custom_screenshot.command == "shared capture"
    assert later.device.last_serial == "host:18001"
    assert later.device.game_package == "com.hypergryph.arknights.bilibili"
    assert common.for_launch(original, managed=False) is original
    assert path.read_bytes() == before


def test_independent_toggle_captures_inherited_values_and_return_to_shared_follows_global(
    manager, tmp_path
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {"preset_id": "manual.other", "last_serial": "private:18002"},
            "private_extension": {"keep": True},
        },
    )
    edit_common(manager, performance_mode="low")
    assert editor(manager)[1]["values"]["performance_mode"] == "low"
    assert set_independent(manager, True) == {"ok": True}
    edit_common(manager, performance_mode="high")
    independent = editor(manager)[1]
    assert independent["independent_configuration"] is True
    assert independent["values"]["performance_mode"] == "low"
    assert yaml.safe_load(path.read_text())["private_extension"] == {"keep": True}
    set_independent(manager, False)
    shared = editor(manager)[1]
    assert shared["independent_configuration"] is False
    assert shared["values"]["performance_mode"] == "high"
    assert shared["values"]["device"]["last_serial"] == "private:18002"


def test_shared_mode_rejects_local_shared_changes_and_four_argument_saves_never_toggle(
    manager, tmp_path
):
    _, path = add_instance(manager, tmp_path, "first", {})
    target, state = editor(manager)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="共享连接参数"):
        manager.update_device_settings(
            0, {"performance_mode": "low"}, target, state["values"]
        )
    assert path.read_bytes() == before
    manager.update_device_settings(
        0, {"device.instance_name": "chosen instance"}, target, state["values"]
    )
    assert editor(manager)[1]["independent_configuration"] is False


def test_new_directories_are_classified_before_shared_values_change(manager, tmp_path):
    add_instance(manager, tmp_path, "first", {"performance_mode": "high"})
    original = manager.get_common_settings()["values"]
    added, path = add_instance(manager, tmp_path, "added", {"performance_mode": "high"})
    different, different_path = add_instance(
        manager, tmp_path, "different", {"performance_mode": "low"}
    )
    empty, _ = add_instance(manager, tmp_path, "empty", {})
    before = path.read_bytes(), different_path.read_bytes()
    manager.update_all_settings(
        [],
        manager.instances.copy(),
        {"values": {**original, "performance_mode": "medium"}, "original": original},
    )
    assert editor(manager, added)[1]["independent_configuration"] is False
    assert editor(manager, added)[1]["values"]["performance_mode"] == "medium"
    assert editor(manager, different)[1]["independent_configuration"] is True
    assert editor(manager, different)[1]["values"]["performance_mode"] == "low"
    assert editor(manager, empty)[1]["independent_configuration"] is False
    assert (path.read_bytes(), different_path.read_bytes()) == before


def test_connection_policy_follows_directory_and_resolves_aliases(manager, tmp_path):
    idx, original_path = add_instance(
        manager, tmp_path, "first", {"performance_mode": "high"}
    )
    editor(manager)
    set_independent(manager, True)
    alias = original_path.parent.parent / "config/.."
    manager.add("alias", str(alias))
    assert editor(manager, 1)[1]["independent_configuration"] is True
    moved_path = tmp_path / "replacement"
    manager.set_path(idx, str(moved_path), manager.instances[idx].copy())
    state = editor(manager, idx)[1]
    assert state["independent_configuration"] is False
    document = common.read_document(manager._common_path)
    assert document["independent_instances"][common.policy_key(moved_path)] is False
    assert document["independent_instances"][common.policy_key(alias)] is True


def test_shared_binding_save_validates_inherited_backend_and_retains_local_values(
    manager, tmp_path
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "screenshot_backend": "mumu_ipc",
                "touch_backend": "mumu_ipc",
                "last_serial": "old:17001",
            },
            "performance_mode": "high",
        },
    )
    editor(manager)
    edit_common(
        manager,
        performance_mode="low",
        **{"device.screenshot_backend": "droidcast", "device.touch_backend": "scrcpy"},
    )
    target, state = editor(manager)
    manager.update_device_settings(
        0, {"device.instance_id": "8"}, target, state["values"]
    )
    state = editor(manager)[1]
    assert state["values"]["device"]["preset_id"] == "windows.mumu12"
    assert state["values"]["device"]["instance_id"] == "8"
    assert state["values"]["device"]["last_serial"] == ""
    assert state["values"]["device"]["screenshot_backend"] == "droidcast"
    stored = yaml.safe_load(path.read_text())
    assert stored["performance_mode"] == "high"
    assert stored["device"]["screenshot_backend"] == "mumu_ipc"
    assert stored["mumu12IPC"] is True
    set_independent(manager, True)
    assert (
        yaml.safe_load(path.read_text())["device"]["screenshot_backend"] == "droidcast"
    )


def test_disabling_independent_configuration_validates_shared_backend(
    manager, tmp_path
):
    add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "screenshot_backend": "mumu_ipc",
                "touch_backend": "mumu_ipc",
            }
        },
    )
    editor(manager)
    set_independent(manager, True)
    edit_common(
        manager,
        **{"device.screenshot_backend": "droidcast", "device.touch_backend": "scrcpy"},
    )
    set_independent(manager, False)
    state = editor(manager)[1]
    assert state["independent_configuration"] is False
    assert state["values"]["device"]["screenshot_backend"] == "droidcast"


@pytest.mark.parametrize("stale", ["policy", "common", "running"])
def test_stale_policy_common_snapshot_or_running_instance_reject_before_changes(
    manager, tmp_path, monkeypatch, stale
):
    _, path = add_instance(manager, tmp_path, "first", {})
    target, state = editor(manager)
    if stale == "policy":
        set_independent(manager, True)
    elif stale == "common":
        edit_common(manager, performance_mode="low")
    else:
        monkeypatch.setattr(
            runtime,
            "instances",
            lambda **kwargs: [{"kind": "instance", "space": target["path"]}],
        )
    before = path.read_bytes(), manager._common_path.read_bytes()
    with pytest.raises(ValueError):
        manager.update_device_settings(
            0,
            {"device.last_serial": "wrong"},
            target,
            state["values"],
            {
                "independent_configuration": True,
                "original_policy": state["original_policy"],
            },
        )
    assert (path.read_bytes(), manager._common_path.read_bytes()) == before


def test_failed_policy_commit_restores_exact_instance_bytes(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(manager, tmp_path, "first", {"private_extension": 9})
    editor(manager)
    before = path.read_bytes(), manager._common_path.read_bytes()
    monkeypatch.setattr(
        runtime, "write_json", Mock(side_effect=OSError("policy write failed"))
    )
    with pytest.raises(OSError, match="policy write failed"):
        set_independent(manager, True, changes={"performance_mode": "low"})
    assert (path.read_bytes(), manager._common_path.read_bytes()) == before


def test_corrupt_policy_file_is_not_replaced_with_defaults(manager):
    manager._common_path.parent.mkdir(parents=True)
    bad = '{"version":1,"values":{},"independent_instances":{}}'
    manager._common_path.write_text(bad)
    with pytest.raises(ValueError, match="缺少共享参数"):
        manager.get_common_settings()
    assert manager._common_path.read_text() == bad


def test_shared_values_and_policy_survive_instance_configuration_import_projection(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {"preset_id": "manual.other", "last_serial": "chosen:18003"},
            "updates_enabled": False,
        },
    )
    edit_common(manager, performance_mode="low")
    current = Conf(
        **copy.deepcopy(editor(manager)[1]["values"]),
        account="personal sender",
        updates_enabled=False,
    )
    monkeypatch.setenv("MOWER_MANAGED", "1")
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    document = json.loads(manager._common_path.read_text())
    document["values"]["account"] = "retired shared sender"
    manager._common_path.write_text(json.dumps(document), encoding="utf-8")
    before = manager._common_path.read_bytes()
    imported = {
        "device": {"last_serial": "foreign"},
        "performance_mode": "high",
        "updates_enabled": True,
        "account": "foreign sender",
    }
    managed_device.preserve(imported, current)
    assert imported["device"]["last_serial"] == "chosen:18003"
    assert imported["performance_mode"] == "low"
    assert imported["account"] == "foreign sender"
    assert imported["extra_settings_visible"] is False
    assert "updates_enabled" not in imported
    assert manager._common_path.read_bytes() == before
    assert path.exists()


@pytest.mark.parametrize(
    "changes",
    [
        {"device.preset_id": "windows.mumu12"},
        {"device.installation_path": "C:/other"},
        {"device.manager_path": "C:/manager.exe"},
        {"device.config_path": "C:/config"},
        {"device.last_serial": "other:12345"},
        {"device.last_serial": ""},
    ],
)
def test_shared_template_and_endpoint_reject_local_save_and_discovery(
    manager, tmp_path, monkeypatch, changes
):
    _, path = add_instance(manager, tmp_path, "first", {})
    target, state = editor(manager)
    before = path.read_bytes(), manager._common_path.read_bytes()
    discover = Mock()
    monkeypatch.setattr(managed_device, "discover", discover)
    with pytest.raises(ValueError, match="共享连接参数"):
        manager.update_device_settings(0, changes, target, state["values"])
    with pytest.raises(ValueError, match="共享连接参数"):
        manager.discover_device_settings(0, changes, target, state["values"])
    discover.assert_not_called()
    assert (path.read_bytes(), manager._common_path.read_bytes()) == before


def test_shared_template_launch_snapshot_and_binding_endpoint_isolation(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "instance_id": "2",
                "instance_name": "first",
                "last_serial": "old:17002",
            }
        },
    )
    _, second = add_instance(
        manager,
        tmp_path,
        "second",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "instance_id": "3",
                "last_serial": "old:17003",
            }
        },
    )
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    monkeypatch.setattr(common, "get_path", lambda *args, **kwargs: path.parent.parent)
    manager.get_common_settings()
    original = Conf(**yaml.safe_load(path.read_text()))
    running = common.for_launch(original, managed=True)
    before = path.read_bytes(), second.read_bytes()
    edit_common(
        manager,
        **{
            "device.installation_path": "C:/shared",
            "device.manager_path": "",
            "device.config_path": "",
        },
    )
    later = common.for_launch(original, managed=True)
    assert running.device.installation_path == ""
    assert running.device.last_serial == "old:17002"
    assert later.device.installation_path == "C:/shared"
    assert later.device.last_serial == ""
    assert later.device.instance_id == "2"
    assert later.device.instance_name == "first"
    assert (path.read_bytes(), second.read_bytes()) == before
    target, state = editor(manager)
    manager.update_device_settings(
        0,
        {
            "device.instance_id": "4",
            "device.instance_name": "four",
            "device.game_package": "com.hypergryph.arknights.bilibili",
        },
        target,
        state["values"],
    )
    current = editor(manager)[1]["values"]["device"]
    assert current["instance_id"] == "4" and current["instance_name"] == "four"
    assert current["installation_path"] == "C:/shared" and current["last_serial"] == ""
    assert yaml.safe_load(second.read_text())["device"]["last_serial"] == "old:17003"


@pytest.mark.parametrize("change", ["id", "name"])
def test_shared_binding_change_clears_cached_endpoint_and_derived_identity(
    manager, tmp_path, change
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "instance_id": "2",
                "instance_name": "two",
                "last_serial": "old:17002",
                "instance_uuid": "uuid-two",
                "topology_fingerprint": "fingerprint-two",
            }
        },
    )
    target, state = editor(manager)
    assert state["values"]["device"]["last_serial"] == "old:17002"
    manager.update_device_settings(
        0,
        {"device.instance_id" if change == "id" else "device.instance_name": "new"},
        target,
        state["values"],
    )
    stored = yaml.safe_load(path.read_text())["device"]
    assert (
        stored["last_serial"]
        == stored["instance_uuid"]
        == stored["topology_fingerprint"]
        == ""
    )


def test_old_version_one_template_upgrade_preserves_effective_shared_values_and_policies(
    manager, tmp_path
):
    first, first_path = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "installation_path": "C:/one",
                "last_serial": "one:17001",
            },
            "performance_mode": "high",
        },
    )
    second, second_path = add_instance(
        manager,
        tmp_path,
        "second",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "installation_path": "C:/two",
                "last_serial": "two:17002",
            },
            "performance_mode": "high",
            "private_extension": {"keep": True},
        },
    )
    third, third_path = add_instance(
        manager,
        tmp_path,
        "third",
        {
            "device": {"preset_id": "windows.nox", "installation_path": "C:/three"},
            "performance_mode": "medium",
        },
    )
    old_values = {
        key: value
        for key, value in manager.get_common_settings()["values"].items()
        if key not in common.TEMPLATE_KEYS
    }
    old_values["performance_mode"] = "low"
    policies = {
        common.policy_key(path.parent.parent): idx == third
        for idx, path in enumerate((first_path, second_path, third_path))
    }
    runtime.write_json(
        manager._common_path,
        dict(version=1, values=old_values, independent_instances=policies),
        sync=True,
    )
    before = first_path.read_bytes(), third_path.read_bytes()
    expected_second = common.apply_settings(
        Conf(**yaml.safe_load(second_path.read_text())), old_values
    )
    values = manager.get_common_settings()["values"]
    assert common.TEMPLATE_KEYS <= values.keys()
    assert values["device.installation_path"] == "C:/one"
    assert editor(manager, first)[1]["independent_configuration"] is False
    assert editor(manager, first)[1]["values"]["performance_mode"] == "low"
    assert editor(manager, second)[1]["independent_configuration"] is True
    assert editor(manager, second)[1]["values"] == editor_values(expected_second)
    assert editor(manager, third)[1]["independent_configuration"] is True
    assert editor(manager, third)[1]["values"]["performance_mode"] == "medium"
    assert (first_path.read_bytes(), third_path.read_bytes()) == before
    assert yaml.safe_load(second_path.read_text())["private_extension"] == {
        "keep": True
    }
    after = second_path.read_bytes(), manager._common_path.read_bytes()
    manager.get_common_settings()
    assert (second_path.read_bytes(), manager._common_path.read_bytes()) == after


def test_old_version_one_without_instances_adds_template_defaults(manager):
    values = {
        key: value
        for key, value in manager.get_common_settings()["values"].items()
        if key not in common.TEMPLATE_KEYS
    }
    runtime.write_json(
        manager._common_path,
        dict(version=1, values=values, independent_instances={}),
        sync=True,
    )
    result = manager.get_common_settings()["values"]
    assert result["device.preset_id"] == "manual.other"
    assert (
        result["device.installation_path"]
        == result["device.manager_path"]
        == result["device.config_path"]
        == ""
    )
    assert common.read_document(manager._common_path)["values"] == result


def test_switch_to_shared_discovery_uses_template_and_rejects_stale_common_snapshot(
    manager, tmp_path, monkeypatch
):
    add_instance(
        manager, tmp_path, "first", {"device": {"preset_id": "windows.mumu12"}}
    )
    editor(manager)
    set_independent(
        manager,
        True,
        changes={
            "device.preset_id": "windows.nox",
            "device.installation_path": "C:/private",
        },
    )
    target, state = editor(manager)
    policy = {
        "independent_configuration": False,
        "original_policy": state["original_policy"],
    }
    discover = Mock(return_value={"candidates": []})
    monkeypatch.setattr(managed_device, "discover", discover)
    manager.discover_device_settings(0, {}, target, state["values"], policy)
    assert discover.call_args.args[0].device.preset_id == "windows.mumu12"
    assert discover.call_args.args[0].device.installation_path == ""
    edit_common(manager, **{"device.installation_path": "C:/new"})
    with pytest.raises(ValueError, match="独立连接配置已变化"):
        manager.discover_device_settings(0, {}, target, state["values"], policy)
    assert discover.call_count == 1


@pytest.mark.parametrize("foreign", [False, True])
def test_shared_discovery_projects_automatic_paths_but_rejects_foreign_template(
    manager, tmp_path, monkeypatch, foreign
):
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {"device": {"preset_id": "windows.nox", "installation_path": "C:/Nox"}},
    )
    target, state = editor(manager)
    binding = {
        "preset_id": "windows.nox",
        "installation_path": "C:\\foreign" if foreign else "c:\\nox\\",
        "manager_path": "C:/Nox/bin/NoxConsole.exe",
        "config_path": "C:/Nox/config",
        "instance_id": "3",
        "instance_name": "third",
        "instance_uuid": "uuid-three",
        "topology_fingerprint": "fingerprint-three",
        "last_serial": "detected:17003",
    }
    monkeypatch.setattr(
        managed_device,
        "discover",
        Mock(return_value={"candidates": [{"binding": binding}]}),
    )
    result = manager.discover_device_settings(0, {}, target, state["values"])
    candidate = result["candidates"][0]
    assert candidate["shared_template_matches"] is not foreign
    changes = {
        f"device.{key}": binding[key]
        for key in (
            "instance_id",
            "instance_name",
            "instance_uuid",
            "topology_fingerprint",
        )
    }
    if foreign:
        before = path.read_bytes()
        with pytest.raises(ValueError, match="识别信息由检测结果维护"):
            manager.update_device_settings(0, changes, target, state["values"])
        assert path.read_bytes() == before
    else:
        assert candidate["binding"]["installation_path"] == "C:/Nox"
        assert (
            candidate["binding"]["manager_path"]
            == candidate["binding"]["config_path"]
            == ""
        )
        manager.update_device_settings(0, changes, target, state["values"])
        stored = yaml.safe_load(path.read_text())["device"]
        assert stored["installation_path"] == "C:/Nox"
        assert stored["manager_path"] == stored["config_path"] == ""
        assert stored["instance_uuid"] == "uuid-three" and stored["last_serial"] == ""
        assert editor(manager)[1]["values"]["device"]["instance_uuid"] == "uuid-three"


@pytest.mark.parametrize("failure", ["last_instance", "global_before", "global_after"])
def test_old_version_one_template_upgrade_restores_exact_files_on_failure(
    manager, tmp_path, monkeypatch, failure
):
    paths = []
    for index in range(3):
        _, path = add_instance(
            manager,
            tmp_path,
            str(index),
            {
                "device": {
                    "preset_id": "windows.nox",
                    "installation_path": f"C:/Nox-{index}",
                },
                "performance_mode": "high",
                "private_extension": index,
            },
        )
        path.write_text("# retain original comment\n" + path.read_text())
        paths.append(path)
    values = {
        key: value
        for key, value in manager.get_common_settings()["values"].items()
        if key not in common.TEMPLATE_KEYS
    }
    values["performance_mode"] = "low"
    policies = {common.policy_key(path.parent.parent): False for path in paths}
    runtime.write_json(
        manager._common_path,
        dict(version=1, values=values, independent_instances=policies),
        sync=True,
    )
    originals = [path.read_bytes() for path in (*paths, manager._common_path)]
    write_config, write_json = manager._write_config, runtime.write_json
    if failure == "last_instance":

        def fail(path, raw):
            write_config(path, raw)
            if path == paths[-1]:
                raise OSError("upgrade failed")

        monkeypatch.setattr(manager, "_write_config", fail)
    else:

        def fail(path, raw, **kwargs):
            if failure == "global_after":
                write_json(path, raw, **kwargs)
            raise OSError("upgrade failed")

        monkeypatch.setattr(runtime, "write_json", fail)
    with pytest.raises(OSError, match="upgrade failed"):
        manager.get_common_settings()
    assert [path.read_bytes() for path in (*paths, manager._common_path)] == originals


def test_shared_derived_identity_rejects_incomplete_detection_template(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(manager, tmp_path, "first", {})
    target, state = editor(manager)
    monkeypatch.setattr(
        managed_device,
        "discover",
        Mock(
            return_value={
                "candidates": [
                    {"binding": {"instance_id": "3", "instance_uuid": "uuid-three"}}
                ]
            }
        ),
    )
    before = path.read_bytes()
    with pytest.raises(ValueError, match="识别信息由检测结果维护"):
        manager.update_device_settings(
            0,
            {"device.instance_id": "3", "device.instance_uuid": "uuid-three"},
            target,
            state["values"],
        )
    assert path.read_bytes() == before


@pytest.mark.parametrize("legacy_version", [0, 1])
def test_template_upgrade_preserves_implicit_auto_paths_in_existing_bindings(
    manager, tmp_path, legacy_version
):
    first, _ = add_instance(
        manager,
        tmp_path,
        "first",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "installation_path": "C:/one",
                "instance_id": "1",
            },
            "performance_mode": "high",
        },
    )
    second, second_path = add_instance(
        manager,
        tmp_path,
        "second",
        {
            "device": {
                "preset_id": "windows.mumu12",
                "instance_id": "1",
                "last_serial": "second:17001",
            },
            "performance_mode": "high",
        },
    )
    original = Conf(**yaml.safe_load(second_path.read_text()))
    if legacy_version == 1:
        values = {
            key: value
            for key, value in manager.get_common_settings()["values"].items()
            if key not in common.TEMPLATE_KEYS
        }
        values["performance_mode"] = "low"
        policies = {
            common.policy_key(instance["path"]): False for instance in manager.instances
        }
        runtime.write_json(
            manager._common_path,
            dict(version=1, values=values, independent_instances=policies),
            sync=True,
        )
        expected = common.apply_settings(original, values)
    else:
        expected = original
    manager.get_common_settings()
    assert editor(manager, first)[1]["independent_configuration"] is False
    state = editor(manager, second)[1]
    assert state["independent_configuration"] is True
    assert state["values"] == editor_values(expected)
    assert state["values"]["device"]["installation_path"] == ""
    assert state["values"]["device"]["last_serial"] == "second:17001"


@pytest.mark.parametrize(
    "preset,relative_manager",
    [
        ("windows.nox", "bin/NoxConsole.exe"),
        ("windows.mumu12", "shell/MuMuManager.exe"),
    ],
)
def test_shared_candidates_reuse_real_vendor_manager_location_semantics(
    manager, tmp_path, monkeypatch, preset, relative_manager
):
    root = (tmp_path / "emulator").resolve()
    executable = root / relative_manager
    executable.parent.mkdir(parents=True)
    executable.touch()
    if preset == "windows.nox":
        from arknights_mower.utils.device.nox_discovery import locate_nox_manager

        locator = locate_nox_manager
    else:
        from arknights_mower.utils.device.mumu_discovery import MuMuDiscoveryIO

        locator = MuMuDiscoveryIO._manager_candidate
    detected_manager, detected_root = locator(root)
    assert detected_manager == executable
    _, path = add_instance(
        manager,
        tmp_path,
        "first",
        {"device": {"preset_id": preset, "installation_path": str(root)}},
    )
    target, state = editor(manager)
    binding = {
        "preset_id": preset,
        "installation_path": str(detected_root),
        "manager_path": str(detected_manager),
        "instance_id": "1",
        "instance_uuid": "uuid-one",
        "topology_fingerprint": "fingerprint-one",
    }
    monkeypatch.setattr(
        managed_device,
        "discover",
        Mock(return_value={"candidates": [{"binding": binding}]}),
    )
    result = manager.discover_device_settings(0, {}, target, state["values"])
    assert result["candidates"][0]["shared_template_matches"] is True
    assert result["candidates"][0]["binding"]["installation_path"] == str(root)
    manager.update_device_settings(
        0,
        {
            "device.instance_id": "1",
            "device.instance_uuid": "uuid-one",
            "device.topology_fingerprint": "fingerprint-one",
        },
        target,
        state["values"],
    )
    stored = yaml.safe_load(path.read_text())["device"]
    assert stored["installation_path"] == str(root)
    assert stored["manager_path"] == "" and stored["instance_uuid"] == "uuid-one"


def test_shared_template_path_aliases_use_existing_config_resolver(
    monkeypatch, tmp_path
):
    from arknights_mower.utils import path as config_path

    root = (tmp_path / "data").resolve()
    monkeypatch.setattr(
        config_path, "get_path", lambda value, **kwargs: root / value.split("/", 1)[1]
    )
    values = {
        "device.preset_id": "linux.avd",
        "device.installation_path": "@app/sdk",
        "device.manager_path": "",
        "device.config_path": "@app/avd/config.ini",
    }
    binding = {
        "preset_id": "linux.avd",
        "installation_path": str(root / "sdk"),
        "manager_path": str(root / "sdk/emulator"),
        "config_path": str(root / "avd/config.ini"),
        "instance_name": "first",
    }
    projected = managed_device.project_shared_candidates(
        {"candidates": [{"binding": binding}]}, values
    )["candidates"][0]
    assert projected["shared_template_matches"] is True
    assert projected["binding"]["installation_path"] == "@app/sdk"
    assert projected["binding"]["config_path"] == "@app/avd/config.ini"


def waiting_values(**changes):
    return {**Conf().waiting_scene.model_dump(mode="json"), **changes}


def test_waiting_scene_schema_uses_configuration_defaults_and_shared_editor_metadata(
    manager,
):
    schema = manager.get_common_settings()
    field = next(item for item in schema["fields"] if item["key"] == "waiting_scene")
    assert field["kind"] == "waiting_scene"
    assert field["shared_connection"] is True
    assert field["default"] == schema["values"]["waiting_scene"] == waiting_values()
    assert {scene for scene, _ in field["scenes"]} == set(waiting_values())
    state = editor_after_add(manager)
    device_field = next(
        item for item in state["fields"] if item["key"] == "waiting_scene"
    )
    assert device_field["kind"] == "waiting_scene"
    assert device_field["scenes"] == field["scenes"]
    assert "waiting_scene" in state["shared_keys"]


def editor_after_add(manager):
    manager.add("first", str(manager._storage_path.parent / "first"))
    return editor(manager)[1]


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        {},
        {
            key: value
            for key, value in Conf().waiting_scene.model_dump(mode="json").items()
            if key != "UNKNOWN"
        },
        {**Conf().waiting_scene.model_dump(mode="json"), "EXTRA": [1, 10]},
        {**Conf().waiting_scene.model_dump(mode="json"), "UNKNOWN": [1]},
        {**Conf().waiting_scene.model_dump(mode="json"), "UNKNOWN": [1, 2, 3]},
        {**Conf().waiting_scene.model_dump(mode="json"), "UNKNOWN": [True, 10]},
        {**Conf().waiting_scene.model_dump(mode="json"), "UNKNOWN": [1, False]},
        {**Conf().waiting_scene.model_dump(mode="json"), "UNKNOWN": ["1", 10]},
        {**Conf().waiting_scene.model_dump(mode="json"), "UNKNOWN": [1, 10.0]},
    ],
)
def test_waiting_scene_rejects_incomplete_or_non_integer_values_before_writes(
    manager, invalid
):
    original = manager.get_common_settings()["values"]
    before = manager._common_path.read_bytes()
    with pytest.raises(ValueError, match="页面等待参数"):
        manager.update_all_settings(
            [],
            [],
            {"values": {**original, "waiting_scene": invalid}, "original": original},
        )
    assert manager._common_path.read_bytes() == before
    with pytest.raises(ValueError, match="页面等待参数"):
        managed_device.validate_patch({"waiting_scene": invalid})


def test_waiting_scene_validation_keeps_existing_conf_integer_semantics():
    values = waiting_values(UNKNOWN=[-1, 0], CONNECTING=[100000, 100000])
    assert common.validate_settings({"waiting_scene": values}) == {
        "waiting_scene": values
    }
    assert managed_device.validate_patch({"waiting_scene": values}) == {
        "waiting_scene": values
    }
    assert Conf(waiting_scene=values).waiting_scene.model_dump(mode="json") == values


def test_old_shared_document_adds_waiting_scene_without_losing_effective_values(
    manager, tmp_path
):
    first, first_path = add_instance(
        manager,
        tmp_path,
        "first",
        {"performance_mode": "high", "waiting_scene": waiting_values(UNKNOWN=[5, 11])},
    )
    second, second_path = add_instance(
        manager, tmp_path, "second", {"performance_mode": "high"}
    )
    third, third_path = add_instance(
        manager,
        tmp_path,
        "third",
        {
            "performance_mode": "medium",
            "waiting_scene": waiting_values(UNKNOWN=[7, 13]),
        },
    )
    values = manager.get_common_settings()["values"]
    values.pop("waiting_scene")
    values["performance_mode"] = "low"
    policies = {
        common.policy_key(path.parent.parent): index == third
        for index, path in enumerate((first_path, second_path, third_path))
    }
    runtime.write_json(
        manager._common_path,
        dict(version=1, values=values, independent_instances=policies),
        sync=True,
    )
    before = first_path.read_bytes(), third_path.read_bytes()
    expected_second = common.apply_settings(
        Conf(**yaml.safe_load(second_path.read_text())), values
    )
    upgraded = manager.get_common_settings()["values"]
    assert upgraded["waiting_scene"] == waiting_values(UNKNOWN=[5, 11])
    assert editor(manager, first)[1]["independent_configuration"] is False
    assert editor(manager, first)[1]["values"]["performance_mode"] == "low"
    assert editor(manager, second)[1]["independent_configuration"] is True
    assert editor(manager, second)[1]["values"] == editor_values(expected_second)
    assert editor(manager, third)[1]["independent_configuration"] is True
    assert editor(manager, third)[1]["values"]["waiting_scene"] == waiting_values(
        UNKNOWN=[7, 13]
    )
    assert (first_path.read_bytes(), third_path.read_bytes()) == before
    after = second_path.read_bytes(), manager._common_path.read_bytes()
    manager.get_common_settings()
    assert (second_path.read_bytes(), manager._common_path.read_bytes()) == after


def test_empty_old_shared_document_adds_waiting_defaults_without_changing_policies(
    manager,
):
    values = manager.get_common_settings()["values"]
    values.pop("waiting_scene")
    runtime.write_json(
        manager._common_path,
        dict(version=1, values=values, independent_instances={}),
        sync=True,
    )
    assert manager.get_common_settings()["values"]["waiting_scene"] == waiting_values()
    assert common.read_document(manager._common_path)["independent_instances"] == {}


@pytest.mark.parametrize("failure", ["instance_after", "global_after"])
def test_waiting_scene_upgrade_failure_restores_original_instance_and_common_bytes(
    manager, tmp_path, monkeypatch, failure
):
    paths = []
    for name, raw in (
        ("first", {"waiting_scene": waiting_values(UNKNOWN=[5, 11])}),
        ("second", {}),
    ):
        _, path = add_instance(
            manager, tmp_path, name, {"performance_mode": "high", **raw}
        )
        path.write_text("# preserve this comment\n" + path.read_text())
        paths.append(path)
    values = manager.get_common_settings()["values"]
    values.pop("waiting_scene")
    values["performance_mode"] = "low"
    runtime.write_json(
        manager._common_path,
        dict(
            version=1,
            values=values,
            independent_instances={
                common.policy_key(path.parent.parent): False for path in paths
            },
        ),
        sync=True,
    )
    originals = [path.read_bytes() for path in (*paths, manager._common_path)]
    write_config = manager._write_config
    write_json = runtime.write_json
    if failure == "instance_after":

        def fail_instance(path, raw):
            write_config(path, raw)
            raise OSError("waiting upgrade failed")

        monkeypatch.setattr(manager, "_write_config", fail_instance)
    else:

        def fail_global(path, raw, **kwargs):
            write_json(path, raw, **kwargs)
            raise OSError("waiting upgrade failed")

        monkeypatch.setattr(runtime, "write_json", fail_global)
    with pytest.raises(OSError, match="waiting upgrade failed"):
        manager.get_common_settings()
    assert [path.read_bytes() for path in (*paths, manager._common_path)] == originals


def test_waiting_scene_shared_launch_snapshot_and_independent_json_bridge_edits(
    manager, tmp_path, monkeypatch
):
    _, path = add_instance(
        manager, tmp_path, "first", {"waiting_scene": waiting_values(UNKNOWN=[5, 11])}
    )
    manager.get_common_settings()
    original_bytes = path.read_bytes()
    edit_common(manager, waiting_scene=waiting_values(UNKNOWN=[7, 13]))
    assert path.read_bytes() == original_bytes
    monkeypatch.setattr(common, "settings_path", lambda: manager._common_path)
    monkeypatch.setattr(common, "get_path", lambda *args, **kwargs: path.parent.parent)
    local = Conf(**yaml.safe_load(path.read_text()))
    running = common.for_launch(local, managed=True)
    assert running.waiting_scene.UNKNOWN == (7, 13)
    target, state = editor(manager)
    state = json.loads(json.dumps(state))
    independent_table = waiting_values(UNKNOWN=[9, 17])
    manager.update_device_settings(
        0,
        {"waiting_scene": independent_table},
        target,
        state["values"],
        {
            "independent_configuration": True,
            "original_policy": state["original_policy"],
        },
    )
    assert editor(manager)[1]["values"]["waiting_scene"] == independent_table
    edit_common(manager, waiting_scene=waiting_values(UNKNOWN=[11, 19]))
    assert running.waiting_scene.UNKNOWN == (7, 13)
    assert common.for_launch(
        Conf(**yaml.safe_load(path.read_text())), managed=True
    ).waiting_scene.UNKNOWN == (9, 17)
    set_independent(manager, False)
    assert editor(manager)[1]["values"]["waiting_scene"] == waiting_values(
        UNKNOWN=[11, 19]
    )
    local = Conf(**yaml.safe_load(path.read_text()))
    assert common.for_launch(local, managed=False) is local
    assert local.waiting_scene.UNKNOWN == (9, 17)
