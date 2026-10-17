"""Check the Windows client's resource admission, repair and mutex protocol."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock
from zipfile import ZipFile

import pytest

from arknights_mower.utils import maa_process as processes
from arknights_mower.utils import maa_update as update
from arknights_mower.utils.maa_backup import BackupCheckpoint


def installation(path):
    path.mkdir(exist_ok=True)
    for name in ("MaaCore.dll", "MAA.exe", "MAA.Updater.exe"):
        (path / name).write_bytes(b"old")
    (path / "Python").mkdir(exist_ok=True)
    resource = path / "resource/Arknights-Tile-Pos/stage.json"
    resource.parent.mkdir(parents=True, exist_ok=True)
    resource.write_text("{}")
    (path / "filelist.txt").write_text("resource/Arknights-Tile-Pos/stage.json\n")
    return resource


def test_incomplete_full_package_is_rejected_before_installation(tmp_path):
    archive = tmp_path / "full.zip"
    with ZipFile(archive, "w") as package:
        for name in (
            "MaaCore.dll",
            "MAA.exe",
            "MAA.Updater.exe",
            "Python/asst/asst.py",
        ):
            package.writestr(name, "fixture")
        package.writestr("resource/config.json", "{}")
        package.writestr("filelist.txt", "resource/Arknights-Tile-Pos/missing.json\n")
    with pytest.raises(update.MaaUpdateError, match="missing.json"):
        update.extract_windows_package(archive, tmp_path / "staged")


@pytest.mark.parametrize(
    "problem", ["missing_resource", "failed_update", "missing_core", "bad_manifest"]
)
@pytest.mark.parametrize("source", ["github", "mirrorchyan"])
def test_damaged_installation_requests_full_package_and_repairs_same_version(
    tmp_path, monkeypatch, problem, source
):
    target = tmp_path / "MAA"
    resource = installation(target)
    (target / "config.json").write_text("user data")
    if problem == "missing_resource":
        resource.unlink()
    elif problem == "failed_update":
        (target / "pending-update-failure.txt").write_text("interrupted update")
    elif problem == "bad_manifest":
        (target / "filelist.txt").write_bytes(b"\xff")
    else:
        (target / "MaaCore.dll").unlink()
    monkeypatch.setenv("MOWER_ANDROID", "0")
    monkeypatch.setattr(update, "read_installed_version", lambda *a, **kw: "v6.20.0")
    release = update.MaaRelease(
        tag="v6.20.0",
        runtime=update.ReleaseAsset("full.zip", "https://example.test/full", 0),
        source=source,
    )
    fetch = Mock(return_value=release)
    monkeypatch.setattr(
        update,
        "get_latest_release" if source == "github" else "get_mirrorchyan_release",
        fetch,
    )

    def download(asset, destination, **kwargs):
        with ZipFile(destination, "w") as package:
            for name in (
                "MaaCore.dll",
                "MAA.exe",
                "MAA.Updater.exe",
                "Python/asst/asst.py",
            ):
                package.writestr(name, "new")
            package.writestr("resource/Arknights-Tile-Pos/stage.json", "{}")
            package.writestr("filelist.txt", "resource/Arknights-Tile-Pos/stage.json\n")
        return destination.stat().st_size

    monkeypatch.setattr(update, "download_asset", download)
    result = update.install_latest_maa(
        target, system="windows", machine="amd64", source=source, mirror_token="fixture"
    )
    assert fetch.call_args.kwargs["installed_version"] == ""
    assert result["updated"] and result["package_type"] == "full"
    assert result["backup"] == str(target / ".old")
    assert (target / ".old/config.json").read_text() == "user data"
    assert (target / "config.json").read_text() == "user data"
    assert not (target / "pending-update-failure.txt").exists()
    assert not target.with_name("MAA.old").exists()
    assert resource.exists()


def test_client_mutex_name_matches_the_documented_windows_protocol():
    expected = "MAA_E2BC746FE6E78680923E827CDB53ABC99A78C623C18243077605112096105D50"
    assert processes.maa_client_mutex_name("c:\\Maa\\") == expected


def test_incomplete_ota_result_cannot_hide_missing_unchanged_resources(tmp_path):
    target = tmp_path / "staged"
    resource = installation(target)
    archive = tmp_path / "ota.zip"
    with ZipFile(archive, "w") as package:
        package.writestr("removelist.txt", "resource/Arknights-Tile-Pos/stage.json\n")
        package.writestr("MaaCore.dll", "new core")
    with pytest.raises(update.MaaUpdateError, match="stage.json"):
        update.apply_windows_ota_package(archive, target)
    assert not resource.exists()


def test_damaged_installation_rejects_source_returning_an_ota(tmp_path, monkeypatch):
    target = tmp_path / "MAA"
    installation(target).unlink()
    monkeypatch.setattr(update, "read_installed_version", lambda *a, **kw: "v6.20.0")
    monkeypatch.setattr(
        update,
        "get_latest_release",
        lambda *a, **kw: update.MaaRelease(
            tag="v6.20.0",
            runtime=update.ReleaseAsset("ota.zip", "https://example.test/ota", 0),
            package_type="ota",
        ),
    )
    download = Mock()
    monkeypatch.setattr(update, "download_asset", download)
    with pytest.raises(update.MaaUpdateError, match="不能使用 OTA 修复"):
        update.install_latest_maa(target, system="windows", machine="amd64")
    download.assert_not_called()
    assert (target / "MaaCore.dll").read_bytes() == b"old"


@pytest.mark.parametrize("status", [0, 0x80])
def test_official_mutex_releases_normal_and_abandoned_ownership(monkeypatch, status):
    kernel = Mock()
    kernel.CreateMutexW.return_value = 17
    kernel.WaitForSingleObject.return_value = status
    monkeypatch.setattr(processes, "_windows_mutex_api", lambda: kernel)
    with processes._maa_client_mutex("MAA_fixture"):
        kernel.ReleaseMutex.assert_not_called()
    kernel.WaitForSingleObject.assert_called_once_with(17, 0)
    kernel.ReleaseMutex.assert_called_once_with(17)
    kernel.CloseHandle.assert_called_once_with(17)


def test_busy_official_mutex_preserves_entire_backup_before_deleting_any_file(
    tmp_path, monkeypatch
):
    target = tmp_path / "MAA"
    installation(target)
    saved = target / ".old/resource"
    saved.mkdir(parents=True)
    (saved / "stage.json").write_text("keep resource")
    checkpoint = BackupCheckpoint(target)
    kernel = Mock()
    kernel.CreateMutexW.return_value = 17
    kernel.WaitForSingleObject.return_value = 0x102
    monkeypatch.setattr(processes, "_windows_mutex_api", lambda: kernel)
    from contextlib import contextmanager

    @contextmanager
    def guard(path):
        with processes._maa_client_mutex("MAA_fixture"):
            yield

    monkeypatch.setattr(processes, "maa_client_guard", guard)
    assert not checkpoint.retire()
    assert (saved / "stage.json").read_text() == "keep resource"
    kernel.ReleaseMutex.assert_not_called()
    kernel.CloseHandle.assert_called_once_with(17)


def test_failed_final_backup_move_restores_installation_and_previous_backup(
    tmp_path, monkeypatch
):
    target = tmp_path / "MAA"
    installation(target)
    old = target / ".old"
    old.mkdir()
    (old / "older.txt").write_text("prior backup")
    work = tmp_path / "work"
    work.mkdir()
    staged = work / "new"
    installation(staged)
    original = update.os.replace

    def replace(source, destination):
        if Path(source) == work / "current.old" and Path(destination) == old:
            raise PermissionError("backup destination locked")
        return original(source, destination)

    monkeypatch.setattr(update.os, "replace", replace)
    with pytest.raises(PermissionError):
        update.replace_with_backup(staged, target, work)
    assert (target / "MaaCore.dll").read_bytes() == b"old"
    assert (old / "older.txt").read_text() == "prior backup"
    assert staged.exists()


@pytest.mark.parametrize("failure", ["mapping", "scan_failed", "unavailable"])
@pytest.mark.skipif(os.name == "nt", reason="macOS mapping checks use POSIX paths")
def test_macos_client_scan_preserves_backup_before_deletion(
    tmp_path, monkeypatch, failure
):
    target = tmp_path / "maa"
    target.mkdir()
    (target / "libMaaCore.dylib").write_bytes(b"fixture")
    saved = target / ".old/resource/stage.json"
    saved.parent.mkdir(parents=True)
    saved.write_text("keep resource")
    checkpoint = BackupCheckpoint(target)
    monkeypatch.setenv("MOWER_ANDROID", "0")
    monkeypatch.setattr(sys, "platform", "darwin")
    from arknights_mower.utils.device import manager_io

    scan = Mock()
    if failure == "unavailable":
        scan.side_effect = FileNotFoundError("lsof missing")
    else:
        scan.return_value = subprocess.CompletedProcess(
            [],
            0 if failure == "mapping" else 2,
            stdout=b"p123\nn/path/libMaaCore.dylib\n" if failure == "mapping" else b"",
            stderr=b"" if failure == "mapping" else b"scan failed",
        )
    monkeypatch.setattr(manager_io, "run_command", scan)
    assert not checkpoint.retire()
    assert saved.read_text() == "keep resource"
