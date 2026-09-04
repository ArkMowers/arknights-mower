import json
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from zipfile import ZipFile, ZipInfo

import requests

from arknights_mower.utils import maa_resource_update as mru


def _version_payload(version: str, activity: str = "测试活动") -> dict:
    return {
        "activity": {"name": activity, "time": 0},
        "last_updated": version,
    }


def _write_resource_zip(
    path: Path,
    version: str,
    prefix: str = "MaaResource-main/resource",
    files: dict[str, bytes] | None = None,
) -> None:
    with ZipFile(path, "w") as archive:
        for name, data in (files or {}).items():
            archive.writestr(f"{prefix}/{name}", data)
        archive.writestr(
            f"{prefix}/version.json",
            json.dumps(_version_payload(version), ensure_ascii=False),
        )


class _JsonResponse:
    def __init__(self, payload, status_error: Exception | None = None):
        self.payload = payload
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error:
            raise self.status_error

    def json(self):
        return self.payload


class TestMaaResourceVersion(unittest.TestCase):
    def test_reads_local_resource_version(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            version_file = target / "resource" / "version.json"
            version_file.parent.mkdir()
            version_file.write_text(
                json.dumps(_version_payload("2026-09-04 01:07:54.000", "月行水上")),
                encoding="utf-8",
            )

            info = mru.read_maa_resource_info(target)

        self.assertEqual(info["version"], "2026-09-04 01:07:54.000")
        self.assertEqual(info["release_note"], "月行水上")

    def test_invalid_local_version_is_treated_as_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            version_file = target / "resource" / "version.json"
            version_file.parent.mkdir()
            version_file.write_text('{"last_updated":"bad"}', encoding="utf-8")

            info = mru.read_maa_resource_info(target)

        self.assertEqual(info, {"version": "", "release_note": ""})

    def test_github_release_uses_resource_version(self):
        session = Mock()
        session.get.return_value = _JsonResponse(
            _version_payload("2026-09-04 01:07:54.000", "月行水上")
        )

        release = mru.get_github_resource_release(session)

        self.assertEqual(release.version, "2026-09-04 01:07:54.000")
        self.assertEqual(release.release_note, "月行水上")
        self.assertEqual(release.source, "github")

    def test_github_check_marks_same_version_as_current(self):
        release = mru.MaaResourceRelease(
            version="2026-09-04 01:07:54.000",
            source="github",
        )
        with patch.object(mru, "get_github_resource_release", return_value=release):
            checked = mru.get_maa_resource_release(
                "github",
                current_version="2026-09-04 01:07:54.000",
            )

        self.assertFalse(checked.available)

    def test_github_check_marks_newer_version_available(self):
        release = mru.MaaResourceRelease(
            version="2026-09-04 01:07:54.000",
            source="github",
        )
        with patch.object(mru, "get_github_resource_release", return_value=release):
            checked = mru.get_maa_resource_release(
                "github",
                current_version="2026-09-03 01:00:00.000",
            )

        self.assertTrue(checked.available)

    def test_mirrorchyan_release_request_does_not_use_app_channel(self):
        session = Mock()
        session.get.return_value = _JsonResponse(
            {
                "code": 0,
                "data": {
                    "version_name": "2026-09-04 01:07:54.000",
                    "release_note": "月行水上",
                    "url": "https://example.test/resource.zip",
                    "filesize": 123,
                    "sha256": "abc",
                },
            }
        )

        release = mru.get_mirrorchyan_resource_release(
            "fixture-token",
            current_version="2026-09-03 01:00:00.000",
            session=session,
        )

        params = session.get.call_args.kwargs["params"]
        self.assertNotIn("channel", params)
        self.assertNotIn("os", params)
        self.assertEqual(params["current_version"], "2026-09-03 01:00:00.000")
        self.assertTrue(release.available)
        self.assertEqual(release.size, 123)

    def test_mirrorchyan_error_does_not_echo_token(self):
        token = "fixture-sensitive-token"
        session = Mock()
        session.get.side_effect = requests.RequestException(
            f"https://example.test/?cdk={token}"
        )

        with self.assertRaises(mru.MaaUpdateError) as context:
            mru.get_mirrorchyan_resource_release(token, session=session)

        self.assertNotIn(token, str(context.exception))

    def test_mirrorchyan_expired_timestamp_is_rejected(self):
        session = Mock()
        session.get.return_value = _JsonResponse(
            {
                "code": 0,
                "data": {
                    "version_name": "2026-09-04 01:07:54.000",
                    "url": "https://example.test/resource.zip",
                    "cdk_expired_time": 1,
                },
            }
        )

        with self.assertRaisesRegex(mru.MaaUpdateError, "已过期"):
            mru.get_mirrorchyan_resource_release(
                "fixture-token",
                current_version="2026-09-03 01:00:00.000",
                session=session,
            )


class TestMaaResourceArchive(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.current = self.root / "current"
        self.current.mkdir()
        (self.current / "version.json").write_text(
            json.dumps(_version_payload("2026-09-03 01:00:00.000")),
            encoding="utf-8",
        )
        (self.current / "keep.json").write_text("old", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_github_archive_is_merged_without_deleting_old_files(self):
        archive = self.root / "github.zip"
        _write_resource_zip(
            archive,
            "2026-09-04 01:07:54.000",
            files={"tasks.json": b"new"},
        )
        staged = self.root / "staged"

        version = mru.merge_resource_archive(archive, self.current, staged)

        self.assertEqual(version, "2026-09-04 01:07:54.000")
        self.assertEqual((staged / "keep.json").read_text(), "old")
        self.assertEqual((staged / "tasks.json").read_bytes(), b"new")

    def test_mirrorchyan_root_resource_archive_is_supported(self):
        archive = self.root / "mirror.zip"
        _write_resource_zip(
            archive,
            "2026-09-04 01:07:54.000",
            prefix="resource",
            files={"template/item.png": b"image"},
        )
        staged = self.root / "staged"

        mru.merge_resource_archive(archive, self.current, staged)

        self.assertEqual((staged / "template" / "item.png").read_bytes(), b"image")

    def test_path_traversal_is_rejected(self):
        archive = self.root / "unsafe.zip"
        with ZipFile(archive, "w") as z:
            z.writestr("MaaResource-main/resource/../../escaped", b"bad")
            z.writestr(
                "MaaResource-main/resource/version.json",
                json.dumps(_version_payload("2026-09-04 01:07:54.000")),
            )

        with self.assertRaisesRegex(mru.MaaUpdateError, "非法路径"):
            mru.merge_resource_archive(archive, self.current, self.root / "staged")

    def test_symlink_is_rejected(self):
        archive = self.root / "symlink.zip"
        with ZipFile(archive, "w") as z:
            link = ZipInfo("MaaResource-main/resource/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(link, "target")
            z.writestr(
                "MaaResource-main/resource/version.json",
                json.dumps(_version_payload("2026-09-04 01:07:54.000")),
            )

        with self.assertRaisesRegex(mru.MaaUpdateError, "符号链接"):
            mru.merge_resource_archive(archive, self.current, self.root / "staged")

    def test_existing_resource_symlink_is_rejected(self):
        archive = self.root / "safe.zip"
        _write_resource_zip(archive, "2026-09-04 01:07:54.000")
        (self.current / "redirect").symlink_to(self.root)

        with self.assertRaisesRegex(mru.MaaUpdateError, "符号链接"):
            mru.merge_resource_archive(archive, self.current, self.root / "staged")


class TestInstallMaaResource(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / "MAA"
        self.resource = self.target / "resource"
        self.resource.mkdir(parents=True)
        (self.target / "libMaaCore.dylib").write_bytes(b"core")
        (self.resource / "version.json").write_text(
            json.dumps(_version_payload("2026-09-03 01:00:00.000")),
            encoding="utf-8",
        )
        (self.resource / "old.txt").write_text("current", encoding="utf-8")
        self.package = self.target.parent / "resource.zip"
        _write_resource_zip(
            self.package,
            "2026-09-04 01:07:54.000",
            files={"new.txt": b"new"},
        )

    def tearDown(self):
        self.temp.cleanup()

    def _install(self):
        release = mru.MaaResourceRelease(
            version="2026-09-04 01:07:54.000",
            source="github",
            url="https://example.test/resource.zip",
            release_note="月行水上",
        )

        def fake_download(release, destination, **kwargs):
            destination.write_bytes(self.package.read_bytes())
            return destination.stat().st_size

        with (
            patch.object(mru, "get_github_resource_release", return_value=release),
            patch.object(mru, "download_resource_archive", side_effect=fake_download),
        ):
            return mru.install_maa_resource_update(self.target, system="darwin")

    def test_update_keeps_incremental_files_and_creates_backup(self):
        old_backup = self.target / "resource.old"
        old_backup.mkdir()
        (old_backup / "older.txt").write_text("older", encoding="utf-8")

        result = self._install()

        self.assertTrue(result["updated"])
        self.assertEqual(result["version"], "2026-09-04 01:07:54.000")
        self.assertEqual((self.resource / "old.txt").read_text(), "current")
        self.assertEqual((self.resource / "new.txt").read_text(), "new")
        self.assertEqual((old_backup / "old.txt").read_text(), "current")
        self.assertFalse((old_backup / "older.txt").exists())

    def test_archive_version_mismatch_keeps_current_resource(self):
        release = mru.MaaResourceRelease(
            version="2026-09-05 01:07:54.000",
            source="github",
            url="https://example.test/resource.zip",
        )

        def fake_download(release, destination, **kwargs):
            destination.write_bytes(self.package.read_bytes())
            return destination.stat().st_size

        with (
            patch.object(mru, "get_github_resource_release", return_value=release),
            patch.object(mru, "download_resource_archive", side_effect=fake_download),
            self.assertRaisesRegex(mru.MaaUpdateError, "版本信息不一致"),
        ):
            mru.install_maa_resource_update(self.target, system="darwin")

        self.assertEqual((self.resource / "old.txt").read_text(), "current")
        self.assertEqual(
            mru.read_maa_resource_info(self.target)["version"],
            "2026-09-03 01:00:00.000",
        )

    def test_post_swap_validation_failure_restores_resource_and_previous_backup(self):
        old_backup = self.target / "resource.old"
        old_backup.mkdir()
        (old_backup / "older.txt").write_text("older", encoding="utf-8")
        release = mru.MaaResourceRelease(
            version="2026-09-04 01:07:54.000",
            source="github",
            url="https://example.test/resource.zip",
        )

        def fake_download(release, destination, **kwargs):
            destination.write_bytes(self.package.read_bytes())
            return destination.stat().st_size

        with (
            patch.object(mru, "get_github_resource_release", return_value=release),
            patch.object(mru, "download_resource_archive", side_effect=fake_download),
            patch.object(
                mru,
                "read_maa_resource_info",
                side_effect=[
                    {
                        "version": "2026-09-03 01:00:00.000",
                        "release_note": "",
                    },
                    {"version": "", "release_note": ""},
                ],
            ),
            self.assertRaisesRegex(mru.MaaUpdateError, "已回滚"),
        ):
            mru.install_maa_resource_update(self.target, system="darwin")

        self.assertEqual((self.resource / "old.txt").read_text(), "current")
        self.assertEqual((old_backup / "older.txt").read_text(), "older")
        self.assertFalse((self.resource / "new.txt").exists())

    def test_windows_keeps_resource_update_in_maa(self):
        with self.assertRaisesRegex(mru.MaaUpdateError, "Maa 主程序"):
            mru.install_maa_resource_update(self.target, system="windows")
