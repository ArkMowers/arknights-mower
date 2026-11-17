"""Exercise MAA updates with paths exceeding the legacy Windows limit."""

import builtins
import io
import json
import os
import tempfile
from pathlib import Path, PureWindowsPath
from zipfile import ZipFile

import pytest

from arknights_mower.utils import maa_resource_update as resources
from arknights_mower.utils import maa_storage, maa_update, path


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        (r"D:\Mower\tmp\maa\updates", r"\\?\D:\Mower\tmp\maa\updates"),
        (r"D:/Mower/tmp/../资源", r"\\?\D:\Mower\资源"),
        (r"\\server\share\Mower\tmp", r"\\?\UNC\server\share\Mower\tmp"),
        (r"\\?\D:\Mower\tmp", r"\\?\D:\Mower\tmp"),
        (r"\\?\UNC\server\share\tmp", r"\\?\UNC\server\share\tmp"),
    ],
)
def test_windows_workspace_path_forms(original, expected):
    assert maa_update._windows_extended_path(PureWindowsPath(original)) == expected


@pytest.mark.parametrize("prefix", ["core-", "resource-"])
def test_update_workspace_keeps_storage_identity_and_cleans_long_files(
    tmp_path, monkeypatch, prefix
):
    monkeypatch.setattr(path, "_data_dir", tmp_path / "data")
    target = tmp_path / "MAA"
    expected = maa_storage.storage_root(target) / "updates"
    with maa_update.update_workspace(target, prefix) as work:
        assert work.parent.samefile(expected)
        if os.name == "nt":
            assert str(work).startswith("\\\\?\\")
        else:
            assert work.parent == expected
        nested = work.joinpath(*(["long-resource-directory"] * 10), "资源.json")
        nested.parent.mkdir(parents=True)
        nested.write_bytes(b"preserved")
        assert nested.read_bytes() == b"preserved"
    assert not work.exists()
    assert list(expected.iterdir()) == []


@pytest.mark.skipif(os.name != "nt", reason="Native Windows filesystem paths")
@pytest.mark.parametrize("outcome", ["success", "merge_failure", "rollback"])
def test_windows_resource_install_with_legacy_path_limit(monkeypatch, outcome):
    import _winapi

    # Keep the installed filename short enough; only Mower's staging makes it long.
    with tempfile.TemporaryDirectory(prefix="maa-path-") as temporary:
        root = Path(temporary)
        target = root / "MAA"
        resource = target / "resource"
        relative = Path(
            "copilot/old/塔山农业实验平台_Tower_Mountains_Agricultural_Experimental_Platform/"
            "SSS_TowerMountains_SkalterEyjalterGoldenglowSilverash+Exusiai.json"
        )
        original = resource / relative
        assert len(str(original)) < 260
        original.parent.mkdir(parents=True)
        original.write_bytes(b"old copilot")
        (target / "MaaCore.dll").write_bytes(b"unchanged core")
        old_version = "2026-11-15 20:39:15.000"
        new_version = "2026-11-16 20:39:15.000"
        version = resource / "version.json"
        version.write_text(json.dumps({"last_updated": old_version}))
        (target / "filelist.txt").write_text(
            f"resource/{relative.as_posix()}\nresource/version.json\n",
            encoding="utf-8",
        )
        prior_backup = target / ".old/resource/prior.txt"
        prior_backup.parent.mkdir(parents=True)
        prior_backup.write_bytes(b"prior backup")
        monkeypatch.setattr(path, "_data_dir", root / "mower-data")
        monkeypatch.setenv("MOWER_ANDROID", "0")
        release = resources.MaaResourceRelease(
            new_version, "github", "https://example.test/resource.zip"
        )
        monkeypatch.setattr(
            resources, "get_maa_resource_release", lambda *a, **kw: release
        )
        workspaces = []

        def download(release, destination, **kwargs):
            workspaces.append(destination.parent)
            assert len(str(destination.parent / "resource" / relative)) > 260
            with ZipFile(destination, "w") as archive:
                archive.writestr(f"resource/{relative.as_posix()}", b"new copilot")
                archive.writestr(
                    "resource/version.json",
                    json.dumps(
                        {
                            "last_updated": old_version
                            if outcome == "merge_failure"
                            else new_version
                        }
                    ),
                )
            return destination.stat().st_size

        monkeypatch.setattr(resources, "download_resource_archive", download)
        real_info = resources.read_maa_resource_info
        calls = 0

        def read_info(target):
            nonlocal calls
            calls += 1
            if outcome == "rollback" and calls == 2:
                return {"version": "", "release_note": ""}
            return real_info(target)

        monkeypatch.setattr(resources, "read_maa_resource_info", read_info)

        def check_legacy_path(file):
            if isinstance(file, (str, os.PathLike)):
                value = os.fspath(file)
                if len(value) >= 260 and not value.startswith("\\\\?\\"):
                    raise OSError(2, "legacy Windows path limit", value, 3)

        def legacy_open(open_file):
            def guarded(file, *args, **kwargs):
                check_legacy_path(file)
                return open_file(file, *args, **kwargs)

            return guarded

        # Enforce the old limit even when CI's Python manifest enables long paths.
        with monkeypatch.context() as boundary:
            boundary.setattr(builtins, "open", legacy_open(builtins.open))
            boundary.setattr(io, "open", legacy_open(io.open))
            if hasattr(_winapi, "CopyFile2"):
                native_copy = _winapi.CopyFile2

                def legacy_copy(source, destination, *args, **kwargs):
                    check_legacy_path(source)
                    check_legacy_path(destination)
                    return native_copy(source, destination, *args, **kwargs)

                boundary.setattr(_winapi, "CopyFile2", legacy_copy)
            if outcome == "success":
                with monkeypatch.context() as previous:
                    previous.setattr(maa_update, "_windows_extended_path", str)
                    with pytest.raises(
                        resources.MaaUpdateError, match="复制现有 MAA 资源失败"
                    ):
                        resources.install_maa_resource_update(target, system="windows")
                assert original.read_bytes() == b"old copilot"
                assert prior_backup.read_bytes() == b"prior backup"
                result = resources.install_maa_resource_update(target, system="windows")
                assert result["updated"]
            else:
                message = "版本信息不一致" if outcome == "merge_failure" else "已回滚"
                with pytest.raises(resources.MaaUpdateError, match=message):
                    resources.install_maa_resource_update(target, system="windows")

        assert (target / "MaaCore.dll").read_bytes() == b"unchanged core"
        assert all(not work.exists() for work in workspaces)
        assert list((maa_storage.storage_root(target) / "updates").iterdir()) == []
        if outcome == "success":
            assert original.read_bytes() == b"new copilot"
            assert (target / ".old/resource" / relative).read_bytes() == b"old copilot"
            assert real_info(target)["version"] == new_version
        else:
            assert original.read_bytes() == b"old copilot"
            assert prior_backup.read_bytes() == b"prior backup"
            assert real_info(target)["version"] == old_version
