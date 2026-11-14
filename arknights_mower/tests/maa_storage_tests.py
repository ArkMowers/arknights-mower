"""Offline filesystem and native lock checks; no device or live MAA required."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from arknights_mower.utils import maa_process, maa_storage, path
from arknights_mower.utils.maa_update import MaaUpdateError


def test_android_load_preserves_host_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("MOWER_ANDROID", "1")
    target = tmp_path / "MAA"
    assert maa_storage.load_options(target) == {
        "path": target,
        "incremental_path": target / "cache",
    }
    assert list(tmp_path.iterdir()) == []


def test_runtime_paths_follow_data_root_and_preserve_legacy_cache(
    tmp_path, monkeypatch
):
    target = tmp_path / "MAA"
    legacy = target / "cache/resource/tasks.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"old": {}}')
    data = tmp_path / "mower-data"
    monkeypatch.setattr(path, "_data_dir", data)
    monkeypatch.setattr(path, "global_space", "instance-a")
    first = maa_storage.load_options(target)
    monkeypatch.setattr(path, "global_space", "instance-b")
    second = maa_storage.load_options(target)
    assert first == second
    assert first["user_dir"].is_relative_to(data)
    cached = first["incremental_path"] / "resource/tasks.json"
    assert json.loads(cached.read_text()) == {"old": {}}
    cached.write_text('{"new": {}}')
    maa_storage.load_options(target)
    assert json.loads(cached.read_text()) == {"new": {}}
    assert json.loads(legacy.read_text()) == {"old": {}}


@pytest.mark.parametrize("nested_data", ["resource/mower-data", "."])
def test_cache_migration_excludes_storage_within_legacy_cache(
    tmp_path, monkeypatch, nested_data
):
    target = tmp_path / "MAA"
    legacy = target / "cache"
    tasks = legacy / "resource/tasks.json"
    tasks.parent.mkdir(parents=True)
    tasks.write_text('{"old": {}}')
    data = legacy / nested_data
    (data / "config").mkdir(parents=True)
    settings = data / "config/conf.yml"
    settings.write_text("keep: true")
    monkeypatch.setattr(path, "_data_dir", data)
    other_runtime = maa_storage.storage_root(tmp_path / "another-maa")
    other_runtime.mkdir(parents=True)
    (other_runtime / "marker").write_text("other installation")

    cache = maa_storage.prepare_cache(target)

    assert (cache / "resource/tasks.json").read_text() == tasks.read_text()
    assert not (cache / "resource/mower-data").exists()
    assert not (cache / maa_storage.storage_root(target).relative_to(data)).exists()
    assert not (cache / other_runtime.relative_to(data)).exists()
    assert (other_runtime / "marker").read_text() == "other installation"
    assert settings.read_text() == "keep: true"


def test_cache_migration_skips_alias_to_mower_data(tmp_path, monkeypatch):
    target = tmp_path / "MAA"
    legacy = target / "cache"
    tasks = legacy / "resource/tasks.json"
    tasks.parent.mkdir(parents=True)
    tasks.write_text("{}")
    data = tmp_path / "mower-data"
    data.mkdir()
    alias = legacy / "linked-data"
    if os.name == "nt":
        from _winapi import CreateJunction

        CreateJunction(str(data), str(alias))
    else:
        alias.symlink_to(data, target_is_directory=True)
    monkeypatch.setattr(path, "_data_dir", data)

    cache = maa_storage.prepare_cache(target)

    assert (cache / "resource/tasks.json").read_text() == tasks.read_text()
    assert not (cache / alias.name).exists()
    assert alias.resolve() == data.resolve()


def test_different_data_roots_still_exclude_update_and_recover_after_crash(
    tmp_path, monkeypatch
):
    target = tmp_path / "MAA"
    target.mkdir()
    monkeypatch.setattr(path, "_data_dir", tmp_path / "second-mower")
    script = (
        "import sys; from arknights_mower.utils.maa_process import installation_lease; "
        "lease=installation_lease(sys.argv[1]); print('ready', flush=True); sys.stdin.read()"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(target)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "MOWER_DATA_DIR": str(tmp_path / "first-mower")},
    )
    try:
        assert child.stdout.readline().strip() == b"ready"
        with maa_process.installation_lease(target):
            with pytest.raises(MaaUpdateError, match="其他实例"):
                maa_process.installation_lease(target, exclusive=True)
        child.kill()
        child.wait(5)
        with maa_process.installation_lease(target, exclusive=True):
            pass
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(5)
        for stream in (child.stdin, child.stdout, child.stderr):
            stream.close()
    assert list(target.iterdir()) == []
    assert not list(tmp_path.glob(".*.mower-maa.lock"))


def test_lease_can_be_closed_by_cleanup_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(path, "_data_dir", tmp_path / "data")
    lease = maa_process.installation_lease(tmp_path)
    closer = threading.Thread(target=lease.close)
    closer.start()
    closer.join(6)
    assert not closer.is_alive()
    with maa_process.installation_lease(tmp_path, exclusive=True):
        pass


def test_existing_legacy_lease_still_blocks_new_installer(tmp_path, monkeypatch):
    monkeypatch.setattr(path, "_data_dir", tmp_path / "data")
    legacy = tmp_path.parent / f".{tmp_path.name}.mower-maa.lock"
    try:
        with maa_process._file_lease(legacy, exclusive=False):
            with pytest.raises(MaaUpdateError, match="其他实例"):
                maa_process.installation_lease(tmp_path, exclusive=True)
    finally:
        legacy.unlink(missing_ok=True)


def test_permission_failure_names_file_and_does_not_claim_contention(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(path, "_data_dir", tmp_path / "data")
    real_open = Path.open

    def denied(file, *args, **kwargs):
        if file.name == "installation.lock":
            raise PermissionError(13, "denied", str(file))
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(MaaUpdateError, match="文件访问被拒绝.*installation.lock"):
        maa_process.installation_lease(tmp_path)


def test_windows_permission_repair_preview_and_links(tmp_path, monkeypatch):
    from arknights_mower.utils import windows_permissions as permissions

    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setattr(permissions, "_lookup_sid_type", lambda sid: 1)
    folder = tmp_path / "Mower"
    folder.mkdir()
    file = folder / "config.json"
    file.write_text('{"keep": true}')
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(permissions.subprocess, "run", run)
    sid = "S-1-5-21-1-2-3-1001"
    assert permissions.repair_permissions([folder], sid) == 2
    run.assert_not_called()

    assert permissions.repair_permissions([folder], sid, apply=True) == 2
    assert all(f"*{sid}:" in call.args[0][3] for call in run.call_args_list)
    assert all("/T" not in call.args[0] for call in run.call_args_list)
    assert file.read_text() == '{"keep": true}'
    link = folder / "link"
    try:
        link.symlink_to(tmp_path / "outside", target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    run.reset_mock()
    with pytest.raises(ValueError, match="链接"):
        permissions.repair_permissions([folder], sid, apply=True)
    run.assert_not_called()


def test_permission_repair_rejects_parent_links_and_normalizes_scope(
    tmp_path, monkeypatch
):
    from arknights_mower.utils import windows_permissions as permissions

    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setattr(permissions, "_lookup_sid_type", lambda sid: 1)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    sid = "S-1-5-21-1-2-3-1001"
    with pytest.raises(ValueError, match="整个磁盘或用户目录"):
        permissions.repair_permissions([tmp_path / "Mower/.."], sid)
    target = tmp_path / "real/Mower"
    target.mkdir(parents=True)
    link = tmp_path / "linked"
    try:
        link.symlink_to(target.parent, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="链接"):
        permissions.repair_permissions([link / "Mower"], sid)


@pytest.mark.parametrize(
    ("sid", "sid_type"),
    [
        ("S-1-1-0", 5),  # Everyone
        ("S-1-5-32-545", 4),  # Built-in Users
        ("S-1-5-21-1-2-3-1002", OSError("account not mapped")),
    ],
)
@pytest.mark.parametrize("apply", [False, True])
def test_permission_repair_requires_one_user_account(
    tmp_path, monkeypatch, sid, sid_type, apply
):
    from arknights_mower.utils import windows_permissions as permissions

    outcome = (
        {"side_effect": sid_type}
        if isinstance(sid_type, OSError)
        else {"return_value": sid_type}
    )
    lookup = Mock(**outcome)
    run = Mock()
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setattr(permissions, "_lookup_sid_type", lookup)
    monkeypatch.setattr(permissions.subprocess, "run", run)

    with pytest.raises(ValueError, match="Windows 用户账户的 SID"):
        permissions.repair_permissions([tmp_path], sid, apply=apply)

    lookup.assert_called_once_with(sid)
    run.assert_not_called()


def test_unreadable_saved_json_never_becomes_default(tmp_path, monkeypatch):
    from arknights_mower.utils import update_runtime

    saved = tmp_path / "network.json"
    saved.write_text('{"token": "preserved"}')
    real_read = Path.read_text

    def denied(file, *args, **kwargs):
        if file == saved:
            raise PermissionError(13, "denied", str(file))
        return real_read(file, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    with pytest.raises(PermissionError, match="network.json"):
        update_runtime.read_json(saved, {})
    assert saved.read_bytes() == b'{"token": "preserved"}'


@pytest.mark.parametrize("kind", ["conf", "plan"])
def test_unreadable_configuration_is_not_replaced(tmp_path, monkeypatch, kind):
    from arknights_mower.utils import config

    saved = tmp_path / f"{kind}.json"
    saved.write_bytes(b'{"preserved": true}')
    monkeypatch.setattr(config, f"{kind}_path", saved)
    for name in (
        "conf",
        "plan",
        "_legacy_dorm_order",
        "_retired_dorm_conf",
        "operation_feedback_avg",
        "operation_feedback_count",
        "operation_feedback_mode",
        "operation_feedback_cap",
        "operation_failure_streak",
        "operation_recovery_successes",
    ):
        monkeypatch.setattr(config, name, getattr(config, name))
    write = Mock()
    monkeypatch.setattr(config, f"save_{kind}", write)
    real_open, real_is_file = Path.open, Path.is_file

    def denied(file, *args, **kwargs):
        if file == saved:
            raise PermissionError(13, "denied", str(file))
        return real_open(file, *args, **kwargs)

    # Python 3.14 returns False for stat errors; only a missing read may default.
    monkeypatch.setattr(
        Path, "is_file", lambda file: False if file == saved else real_is_file(file)
    )
    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(PermissionError, match=kind):
        getattr(config, f"load_{kind}")()
    write.assert_not_called()
    with real_open(saved, "rb") as stream:
        assert stream.read() == b'{"preserved": true}'


def test_failed_rollback_retains_workspace_and_original_files(tmp_path, monkeypatch):
    from arknights_mower.utils import maa_update as update

    target = tmp_path / "MAA"
    target.mkdir()
    (target / "original.txt").write_text("original")
    monkeypatch.setattr(path, "_data_dir", tmp_path / "data")
    real_replace = os.replace

    def denied_restore(source, destination):
        if Path(source) == target / ".old/original.txt":
            raise PermissionError("restore denied")
        return real_replace(source, destination)

    def broken_copy(source, destination):
        destination.write_text("partial new file")
        raise PermissionError("install denied")

    monkeypatch.setattr(os, "replace", denied_restore)
    monkeypatch.setattr(update, "_copy_install_entry", broken_copy)
    with pytest.raises(update.MaaRollbackError, match="更新现场保留"):
        with update.update_workspace(target, "core-") as work:
            staged = work / "new"
            staged.mkdir()
            (staged / "new.txt").write_text("new")
            update.replace_with_backup(staged, target, work)
    assert work.is_dir()
    assert (work / "new/new.txt").read_text() == "new"
    assert (target / ".old/original.txt").read_text() == "original"
    assert not (target / "new.txt").exists()


@pytest.mark.parametrize("entry", ["webview_ui.py", "manager.py"])
def test_permission_repair_entry_precedes_configuration_loading(tmp_path, entry):
    invalid_data = tmp_path / "not-a-directory"
    invalid_data.write_text("unusable data root")
    result = subprocess.run(
        [sys.executable, entry, "--repair-permissions", "--help"],
        env={**os.environ, "MOWER_DATA_DIR": str(invalid_data)},
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert b"--user-sid" in result.stdout
    assert invalid_data.read_text() == "unusable data root"


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL APIs")
@pytest.mark.parametrize("sid", ["S-1-1-0", "S-1-5-32-545"])
def test_native_windows_repair_rejects_group_sids(tmp_path, monkeypatch, sid):
    from arknights_mower.utils import windows_permissions as permissions

    run = Mock()
    monkeypatch.setattr(permissions.subprocess, "run", run)

    with pytest.raises(ValueError, match="请指定单个 Windows 用户账户的 SID"):
        permissions.repair_permissions([tmp_path], sid, apply=True)

    run.assert_not_called()


@pytest.mark.skipif(os.name != "nt", reason="Windows ACL APIs")
def test_native_windows_repair_grants_current_account_without_changing_content(
    tmp_path,
):
    from arknights_mower.utils.windows_permissions import (
        current_user_sid,
        repair_permissions,
    )

    file = tmp_path / "state.json"
    file.write_text("preserved")
    sid = current_user_sid()
    tool = str(Path(os.environ["SystemRoot"]) / "System32/icacls.exe")
    subprocess.run(
        [tool, str(file), "/inheritance:r", "/grant:r", f"*{sid}:R"],
        check=True,
        timeout=10,
        capture_output=True,
    )
    repair_permissions([tmp_path], sid, apply=True)
    assert file.read_text() == "preserved"
    file.write_text("saved again")
    assert file.read_text() == "saved again"
