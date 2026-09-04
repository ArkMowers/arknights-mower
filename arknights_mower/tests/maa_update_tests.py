import io
import os
import stat
import sys
import tarfile
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import ANY, patch
from zipfile import ZipFile, ZipInfo

from arknights_mower.utils import maa_update as mu


def _asset(name: str, size: int = 100) -> dict:
    return {
        "name": name,
        "size": size,
        "browser_download_url": f"https://example.test/{name}",
    }


class TestReleaseParsing(unittest.TestCase):
    def test_selects_runtime_and_arm64_python_source(self):
        release = mu.parse_release(
            {
                "tag_name": "v6.17.0",
                "assets": [
                    _asset("MAA-v6.17.0-win-x64.zip"),
                    _asset("MAA-v6.17.0-win-arm64.zip", 300),
                    _asset("MAA-v6.17.0-macos-runtime-universal.zip", 200),
                    _asset("MAAComponent-DebugSymbol-v6.17.0-win-arm64.zip", 50),
                ],
            }
        )
        self.assertEqual(release.tag, "v6.17.0")
        self.assertEqual(
            release.runtime.name, "MAA-v6.17.0-macos-runtime-universal.zip"
        )
        self.assertEqual(release.python_source.name, "MAA-v6.17.0-win-arm64.zip")

    def test_missing_required_asset_raises(self):
        with self.assertRaises(mu.MaaUpdateError):
            mu.parse_release({"tag_name": "v1", "assets": []})

    def test_selects_linux_package_for_current_architecture(self):
        payload = {
            "tag_name": "v6.17.0",
            "assets": [
                _asset("MAA-v6.17.0-linux-aarch64.tar.gz", 201),
                _asset("MAA-v6.17.0-linux-x86_64.tar.gz", 202),
                _asset("MAA-v6.17.0-linux-x86_64.AppImage", 203),
            ],
        }

        x64 = mu.parse_release(payload, system="linux", machine="amd64")
        arm64 = mu.parse_release(payload, system="linux", machine="arm64")

        self.assertEqual(x64.runtime.name, "MAA-v6.17.0-linux-x86_64.tar.gz")
        self.assertEqual(arm64.runtime.name, "MAA-v6.17.0-linux-aarch64.tar.gz")
        self.assertIsNone(x64.python_source)

    def test_unsupported_linux_architecture_raises(self):
        with self.assertRaisesRegex(mu.MaaUpdateError, "riscv64"):
            mu.normalize_linux_arch("riscv64")

    def test_selects_windows_package_for_current_architecture(self):
        payload = {
            "tag_name": "v6.17.0",
            "assets": [
                _asset("MAA-v6.17.0-win-x64.zip", 201),
                _asset("MAA-v6.17.0-win-arm64.zip", 202),
            ],
        }

        x64 = mu.parse_release(payload, system="windows", machine="amd64")
        arm64 = mu.parse_release(payload, system="windows", machine="aarch64")

        self.assertEqual(x64.runtime.name, "MAA-v6.17.0-win-x64.zip")
        self.assertEqual(arm64.runtime.name, "MAA-v6.17.0-win-arm64.zip")
        self.assertIsNone(x64.python_source)

    def test_unsupported_windows_architecture_raises(self):
        with self.assertRaisesRegex(mu.MaaUpdateError, "x86"):
            mu.normalize_windows_arch("x86")

    def test_github_beta_channel_uses_maa_version_api(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "version": "v6.18.0-beta.1",
                    "details": {
                        "tag_name": "v6.18.0-beta.1",
                        "assets": [
                            _asset("MAA-v6.18.0-beta.1-win-x64.zip", 321),
                        ],
                    },
                }

        class Session:
            def __init__(self):
                self.urls = []

            def get(self, url, timeout):
                self.urls.append(url)
                return Response()

        session = Session()
        release = mu.get_latest_release(
            session=session,
            system="windows",
            machine="amd64",
            channel="beta",
        )

        self.assertEqual(release.tag, "v6.18.0-beta.1")
        self.assertEqual(release.channel, "beta")
        self.assertEqual(release.runtime.name, "MAA-v6.18.0-beta.1-win-x64.zip")
        self.assertEqual(
            session.urls,
            ["https://api.maa.plus/MaaAssistantArknights/api/version/beta.json"],
        )

    def test_unknown_update_channel_is_rejected(self):
        with self.assertRaisesRegex(mu.MaaUpdateError, "nightly"):
            mu.normalize_update_channel("nightly")

    def test_mirrorchyan_resolves_both_full_packages(self):
        class Response:
            status_code = 200

            def __init__(self, os_name):
                self.os_name = os_name

            def raise_for_status(self):
                return None

            def json(self):
                version = "v6.17.0"
                return {
                    "code": 0,
                    "data": {
                        "version_name": version,
                        "url": f"https://mirror.example/{self.os_name}",
                        "filesize": 123,
                        "sha256": "a" * 64,
                        "update_type": "full",
                    },
                }

        class Session:
            def __init__(self):
                self.params = []

            def get(self, url, params, timeout):
                self.params.append(params)
                return Response(params["os"])

        session = Session()
        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            release = mu.get_mirrorchyan_release("secret-token", session=session)

        self.assertEqual(release.source, "mirrorchyan")
        self.assertEqual(release.tag, "v6.17.0")
        self.assertEqual(release.runtime.name, "MAA-v6.17.0-macos-arm64.zip")
        self.assertEqual(release.python_source.name, "MAA-v6.17.0-win-arm64.zip")
        self.assertEqual([item["os"] for item in session.params], ["macos", "win"])

    def test_mirrorchyan_network_error_does_not_echo_token(self):
        class Session:
            def get(self, *args, **kwargs):
                raise mu.requests.RequestException("url?cdk=secret-token")

        with self.assertRaises(mu.MaaUpdateError) as caught:
            mu.get_mirrorchyan_release("secret-token", session=Session())
        self.assertNotIn("secret-token", str(caught.exception))

    def test_mirrorchyan_cdk_status_contains_expiration(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 0,
                    "data": {"cdk_expired_time": 2_000_000_000},
                }

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            status = mu.get_mirrorchyan_cdk_status(
                "secret-token",
                session=Session(),
                now=1_900_000_000,
            )

        self.assertTrue(status.valid)
        self.assertFalse(status.expired)
        self.assertEqual(status.expires_at, 2_000_000_000)

    def test_mirrorchyan_cdk_expired_error(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 7001,
                    "data": {"cdk_expired_time": 1_800_000_000},
                }

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            status = mu.get_mirrorchyan_cdk_status(
                "secret-token",
                session=Session(),
                now=1_900_000_000,
            )

        self.assertFalse(status.valid)
        self.assertTrue(status.expired)
        self.assertEqual(status.code, 7001)
        self.assertIn("已过期", status.message)

    def test_mirrorchyan_cdk_expired_timestamp_is_rejected(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 0,
                    "data": {"cdk_expired_time": 1_800_000_000},
                }

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            status = mu.get_mirrorchyan_cdk_status(
                "secret-token",
                session=Session(),
                now=1_900_000_000,
            )

        self.assertFalse(status.valid)
        self.assertTrue(status.expired)
        self.assertEqual(status.code, 7001)

    def test_mirrorchyan_cdk_invalid_error_does_not_echo_token(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"code": 7002, "data": None}

        class Session:
            def get(self, *args, **kwargs):
                return Response()

        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            status = mu.get_mirrorchyan_cdk_status(
                "secret-token",
                session=Session(),
            )

        self.assertFalse(status.valid)
        self.assertFalse(status.expired)
        self.assertEqual(status.code, 7002)
        self.assertIn("无效", status.message)
        self.assertNotIn("secret-token", status.message)

    def test_mirrorchyan_linux_resolves_one_full_package(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 0,
                    "data": {
                        "version_name": "v6.17.0",
                        "url": "https://mirror.example/linux",
                        "filesize": 456,
                        "sha256": "b" * 64,
                        "update_type": "full",
                    },
                }

        class Session:
            def __init__(self):
                self.params = []

            def get(self, url, params, timeout):
                self.params.append(params)
                return Response()

        session = Session()
        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            release = mu.get_mirrorchyan_release(
                "secret-token",
                session=session,
                system="linux",
                machine="x86_64",
            )

        self.assertEqual(release.runtime.name, "MAA-v6.17.0-linux-x86_64.tar.gz")
        self.assertIsNone(release.python_source)
        self.assertEqual(len(session.params), 1)
        self.assertEqual(session.params[0]["os"], "linux")
        self.assertEqual(session.params[0]["arch"], "x86_64")

    def test_mirrorchyan_windows_resolves_one_full_package(self):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "code": 0,
                    "data": {
                        "version_name": "v6.17.0",
                        "url": "https://mirror.example/windows",
                        "filesize": 456,
                        "sha256": "b" * 64,
                        "update_type": "full",
                    },
                }

        class Session:
            def __init__(self):
                self.params = []

            def get(self, url, params, timeout):
                self.params.append(params)
                return Response()

        session = Session()
        with patch.object(mu, "mirrorchyan_sp_id", return_value="spid"):
            release = mu.get_mirrorchyan_release(
                "secret-token",
                session=session,
                system="windows",
                machine="arm64",
                channel="beta",
            )

        self.assertEqual(release.runtime.name, "MAA-v6.17.0-win-arm64.zip")
        self.assertIsNone(release.python_source)
        self.assertEqual(release.channel, "beta")
        self.assertEqual(len(session.params), 1)
        self.assertEqual(session.params[0]["os"], "win")
        self.assertEqual(session.params[0]["arch"], "arm64")
        self.assertEqual(session.params[0]["channel"], "beta")


class TestArchiveExtraction(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_runtime_root_is_removed_and_symlink_is_preserved(self):
        archive_path = self.root / "runtime.zip"
        link_info = ZipInfo("MAA-v1-macos-runtime-universal/libCurrent.dylib")
        link_info.create_system = 3
        link_info.external_attr = (stat.S_IFLNK | 0o755) << 16
        with ZipFile(archive_path, "w") as archive:
            archive.writestr(
                "MAA-v1-macos-runtime-universal/resource/config.json", "{}"
            )
            archive.writestr(link_info, "libVersioned.dylib")

        destination = self.root / "new"
        mu.extract_runtime(archive_path, destination)

        self.assertEqual(
            (destination / "resource/config.json").read_text(encoding="utf-8"),
            "{}",
        )
        self.assertTrue((destination / "libCurrent.dylib").is_symlink())
        self.assertEqual(
            os.readlink(destination / "libCurrent.dylib"), "libVersioned.dylib"
        )

    def test_python_extraction_only_writes_python_folder(self):
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr("Python/asst/__init__.py", "VALUE = 1")
            archive.writestr("resource/large.dat", b"not selected")
        data.seek(0)

        class MemoryRangeReader(io.BytesIO):
            def __init__(self, *args, **kwargs):
                super().__init__(data.getvalue())

        destination = self.root / "new"
        with patch.object(mu, "HTTPRangeReader", MemoryRangeReader):
            downloaded = mu.extract_python_folder(
                mu.ReleaseAsset("MAA-win-arm64.zip", "https://example.test/a.zip", 999),
                destination,
            )

        self.assertEqual(downloaded, 0)
        self.assertEqual(
            (destination / "Python/asst/__init__.py").read_text(encoding="utf-8"),
            "VALUE = 1",
        )
        self.assertFalse((destination / "resource").exists())

    def test_python_path_traversal_is_rejected(self):
        data = io.BytesIO()
        with ZipFile(data, "w") as archive:
            archive.writestr("Python/../../outside.py", "bad")
        data.seek(0)

        class MemoryRangeReader(io.BytesIO):
            def __init__(self, *args, **kwargs):
                super().__init__(data.getvalue())

        with (
            patch.object(mu, "HTTPRangeReader", MemoryRangeReader),
            self.assertRaises(mu.MaaUpdateError),
        ):
            mu.extract_python_folder(
                mu.ReleaseAsset("MAA-win-arm64.zip", "https://example.test/a.zip", 1),
                self.root / "new",
            )
        self.assertFalse((self.root / "outside.py").exists())

    def test_windows_full_package_is_extracted(self):
        archive_path = self.root / "windows.zip"
        with ZipFile(archive_path, "w") as archive:
            archive.writestr("MaaCore.dll", b"core")
            archive.writestr("MAA.exe", b"main")
            archive.writestr("MAA.Updater.exe", b"updater")
            archive.writestr("resource/config.json", b"{}")
            archive.writestr("Python/asst/__init__.py", b"VALUE = 1")

        destination = self.root / "new"
        mu.extract_windows_package(archive_path, destination)

        self.assertTrue((destination / "MaaCore.dll").is_file())
        self.assertTrue((destination / "MAA.exe").is_file())
        self.assertTrue((destination / "MAA.Updater.exe").is_file())
        self.assertTrue((destination / "resource/config.json").is_file())
        self.assertTrue((destination / "Python/asst/__init__.py").is_file())

    def test_windows_full_package_supports_single_root(self):
        archive_path = self.root / "windows-root.zip"
        with ZipFile(archive_path, "w") as archive:
            root = "MAA-v6.17.0-win-x64"
            archive.writestr(f"{root}/MaaCore.dll", b"core")
            archive.writestr(f"{root}/MAA.exe", b"main")
            archive.writestr(f"{root}/MAA.Updater.exe", b"updater")
            archive.writestr(f"{root}/resource/config.json", b"{}")
            archive.writestr(f"{root}/Python/asst/__init__.py", b"VALUE = 1")

        destination = self.root / "new"
        mu.extract_windows_package(archive_path, destination)

        self.assertTrue((destination / "MaaCore.dll").is_file())
        self.assertFalse((destination / "MAA-v6.17.0-win-x64").exists())

    def test_windows_full_package_path_traversal_is_rejected(self):
        archive_path = self.root / "windows-bad.zip"
        with ZipFile(archive_path, "w") as archive:
            archive.writestr("../outside.dll", b"bad")

        with self.assertRaises(mu.MaaUpdateError):
            mu.extract_windows_package(archive_path, self.root / "new")
        self.assertFalse((self.root / "outside.dll").exists())

    @staticmethod
    def _add_tar_file(archive, name, content=b"fixture", mode=0o644):
        info = tarfile.TarInfo(name)
        info.size = len(content)
        info.mode = mode
        archive.addfile(info, io.BytesIO(content))

    def test_linux_package_extracts_single_root_and_preserves_symlink(self):
        archive_path = self.root / "linux.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            self._add_tar_file(
                archive,
                "MAA-v1-linux-x86_64/libMaaCore.so",
                mode=0o755,
            )
            self._add_tar_file(
                archive,
                "MAA-v1-linux-x86_64/resource/config.json",
                b"{}",
            )
            self._add_tar_file(
                archive,
                "MAA-v1-linux-x86_64/Python/asst/__init__.py",
                b"VALUE = 1",
            )
            link = tarfile.TarInfo("MAA-v1-linux-x86_64/libCurrent.so")
            link.type = tarfile.SYMTYPE
            link.linkname = "libMaaCore.so"
            archive.addfile(link)

        destination = self.root / "new"
        mu.extract_linux_package(archive_path, destination)

        self.assertTrue((destination / "libMaaCore.so").is_file())
        self.assertTrue((destination / "resource/config.json").is_file())
        self.assertTrue((destination / "Python/asst/__init__.py").is_file())
        self.assertEqual(os.readlink(destination / "libCurrent.so"), "libMaaCore.so")

    def test_linux_tar_path_traversal_is_rejected(self):
        archive_path = self.root / "bad.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            self._add_tar_file(archive, "../outside")

        with self.assertRaises(mu.MaaUpdateError):
            mu.extract_linux_package(archive_path, self.root / "new")
        self.assertFalse((self.root / "outside").exists())

    def test_linux_tar_dangerous_symlink_is_rejected(self):
        archive_path = self.root / "bad-link.tar.gz"
        with tarfile.open(archive_path, "w:gz") as archive:
            link = tarfile.TarInfo("libMaaCore.so")
            link.type = tarfile.SYMTYPE
            link.linkname = "../../outside"
            archive.addfile(link)
            self._add_tar_file(archive, "resource/config.json", b"{}")
            self._add_tar_file(archive, "Python/asst/__init__.py")

        with self.assertRaises(mu.MaaUpdateError):
            mu.extract_linux_package(archive_path, self.root / "new")


class TestInstalledVersion(unittest.TestCase):
    def test_reads_version_from_maa_core(self):
        class GetVersion:
            argtypes = None
            restype = None

            def __call__(self):
                return b"v6.17.0"

        class Library:
            _handle = 123
            AsstGetVersion = GetVersion()

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "libMaaCore.dylib").write_bytes(b"fixture")
            with (
                patch.object(mu.ctypes, "CDLL", return_value=Library()),
                patch.object(mu, "_close_dynamic_library") as close,
            ):
                version = mu.read_installed_version(root)

        self.assertEqual(version, "v6.17.0")
        close.assert_called_once_with(123)

    def test_missing_maa_core_has_no_installed_version(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(mu.read_installed_version(temp), "")


class TestInstallAndBackup(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = self.root / "maa"
        self.backup = self.root / "maa.old"
        self.release = mu.MaaRelease(
            tag="v6.17.0",
            runtime=mu.ReleaseAsset("runtime.zip", "https://example.test/runtime", 200),
            python_source=mu.ReleaseAsset(
                "win-arm64.zip", "https://example.test/windows", 300
            ),
        )

    def _install(self, callback=None):
        def fake_download(asset, destination, **kwargs):
            destination.write_bytes(b"zip")
            return asset.size

        def fake_runtime(archive_path, destination, **kwargs):
            (destination / "resource").mkdir()
            (destination / "resource/new.txt").write_text("new", encoding="utf-8")
            (destination / "libMaaCore.dylib").write_bytes(b"core")

        def fake_python(asset, destination, **kwargs):
            (destination / "Python").mkdir()
            (destination / "Python/api.py").write_text("api", encoding="utf-8")
            return 1234

        with (
            patch.object(mu, "get_latest_release", return_value=self.release),
            patch.object(mu, "download_asset", side_effect=fake_download),
            patch.object(mu, "extract_runtime", side_effect=fake_runtime),
            patch.object(mu, "extract_python_folder", side_effect=fake_python),
        ):
            return mu.install_latest_maa(self.target, callback=callback)

    def test_progress_descriptions_distinguish_download_and_update(self):
        download_messages = []
        download_result = self._install(
            callback=lambda _phase, _current, _total, message: download_messages.append(
                message
            )
        )
        update_messages = []
        update_result = self._install(
            callback=lambda _phase, _current, _total, message: update_messages.append(
                message
            )
        )

        self.assertEqual(download_result["operation"], "download")
        self.assertEqual(update_result["operation"], "update")
        self.assertTrue(any("下载信息" in message for message in download_messages))
        self.assertTrue(any("更新信息" in message for message in update_messages))

    def test_empty_target_is_rejected_before_download(self):
        with (
            patch.object(
                mu,
                "get_latest_release",
                side_effect=AssertionError("未设置目录时不应请求更新信息"),
            ),
            self.assertRaisesRegex(mu.MaaUpdateError, "Maa 目录无效"),
        ):
            mu.install_latest_maa("")

    def test_original_becomes_old_and_previous_old_is_cleared(self):
        self.target.mkdir()
        (self.target / "original.txt").write_text("original", encoding="utf-8")
        (self.target / "cache").mkdir()
        (self.target / "cache/state.json").write_text("cache", encoding="utf-8")
        (self.target / "config").mkdir()
        (self.target / "config/user.json").write_text("config", encoding="utf-8")
        self.backup.mkdir()
        (self.backup / "older.txt").write_text("older", encoding="utf-8")

        result = self._install()

        self.assertEqual((self.target / "resource/new.txt").read_text(), "new")
        self.assertEqual((self.target / "Python/api.py").read_text(), "api")
        self.assertFalse((self.target / ".maa-version").exists())
        self.assertEqual((self.target / "cache/state.json").read_text(), "cache")
        self.assertEqual((self.target / "config/user.json").read_text(), "config")
        self.assertEqual((self.backup / "original.txt").read_text(), "original")
        self.assertFalse((self.backup / "older.txt").exists())
        self.assertEqual(result["python_downloaded"], 1234)

    def test_failure_before_swap_keeps_target_and_old(self):
        self.target.mkdir()
        (self.target / "original.txt").write_text("original", encoding="utf-8")
        self.backup.mkdir()
        (self.backup / "older.txt").write_text("older", encoding="utf-8")

        with (
            patch.object(mu, "get_latest_release", return_value=self.release),
            patch.object(mu, "download_asset", side_effect=mu.MaaUpdateError("boom")),
            self.assertRaises(mu.MaaUpdateError),
        ):
            mu.install_latest_maa(self.target)

        self.assertEqual((self.target / "original.txt").read_text(), "original")
        self.assertEqual((self.backup / "older.txt").read_text(), "older")

    def test_mirror_install_downloads_both_full_packages(self):
        def fake_download(asset, destination, **kwargs):
            destination.write_bytes(b"zip")
            return asset.size

        def fake_macos(archive_path, destination, work_dir, **kwargs):
            (destination / "resource").mkdir()
            (destination / "libMaaCore.dylib").write_bytes(b"core")

        def fake_python(archive_path, destination, **kwargs):
            (destination / "Python").mkdir()
            (destination / "Python/api.py").write_text("api", encoding="utf-8")

        mirror_release = mu.MaaRelease(
            tag="v6.17.0",
            runtime=mu.ReleaseAsset("mac.zip", "https://mirror.test/mac", 200),
            python_source=mu.ReleaseAsset("win.zip", "https://mirror.test/win", 300),
            source="mirrorchyan",
        )
        with (
            patch.object(mu, "get_mirrorchyan_release", return_value=mirror_release),
            patch.object(mu, "download_asset", side_effect=fake_download) as download,
            patch.object(mu, "extract_mirror_macos_package", side_effect=fake_macos),
            patch.object(mu, "extract_python_archive", side_effect=fake_python),
            patch.object(
                mu,
                "extract_python_folder",
                side_effect=AssertionError("Mirror酱不应使用远程 Range 提取"),
            ),
        ):
            result = mu.install_latest_maa(
                self.target,
                source="mirrorchyan",
                mirror_token="secret-token",
            )

        self.assertEqual(download.call_count, 2)
        self.assertEqual(result["source"], "mirrorchyan")
        self.assertEqual(result["python_downloaded"], 300)
        self.assertTrue((self.target / "Python/api.py").is_file())

    def test_linux_install_downloads_and_extracts_one_package(self):
        linux_release = mu.MaaRelease(
            tag="v6.17.0",
            runtime=mu.ReleaseAsset(
                "MAA-v6.17.0-linux-x86_64.tar.gz",
                "https://example.test/linux",
                400,
            ),
        )

        def fake_download(asset, destination, **kwargs):
            destination.write_bytes(b"tar")
            return asset.size

        def fake_extract(archive_path, destination, **kwargs):
            (destination / "resource").mkdir()
            (destination / "Python").mkdir()
            (destination / "libMaaCore.so").write_bytes(b"core")

        with (
            patch.object(mu, "get_latest_release", return_value=linux_release),
            patch.object(mu, "download_asset", side_effect=fake_download) as download,
            patch.object(mu, "extract_linux_package", side_effect=fake_extract),
            patch.object(
                mu,
                "extract_python_folder",
                side_effect=AssertionError("Linux 不应再下载 Python 包"),
            ),
        ):
            result = mu.install_latest_maa(
                self.target,
                system="linux",
                machine="amd64",
            )

        download.assert_called_once()
        self.assertEqual(result["platform"], "linux")
        self.assertEqual(result["arch"], "x86_64")
        self.assertEqual(result["runtime_downloaded"], 400)
        self.assertEqual(result["python_downloaded"], 0)
        self.assertTrue((self.target / "Python").is_dir())

    def test_windows_initial_download_installs_one_full_package(self):
        windows_release = mu.MaaRelease(
            tag="v6.17.0",
            runtime=mu.ReleaseAsset(
                "MAA-v6.17.0-win-x64.zip",
                "https://example.test/windows",
                500,
            ),
            channel="beta",
        )

        def fake_download(asset, destination, **kwargs):
            destination.write_bytes(b"zip")
            return asset.size

        def fake_extract(archive_path, destination, **kwargs):
            (destination / "MaaCore.dll").write_bytes(b"core")
            (destination / "MAA.exe").write_bytes(b"main")
            (destination / "MAA.Updater.exe").write_bytes(b"updater")
            (destination / "resource").mkdir()
            (destination / "Python").mkdir()

        self.target.mkdir()
        (self.target / "config.json").write_text("{}", encoding="utf-8")
        with (
            patch.object(
                mu, "get_latest_release", return_value=windows_release
            ) as latest,
            patch.object(mu, "download_asset", side_effect=fake_download) as download,
            patch.object(mu, "extract_windows_package", side_effect=fake_extract),
        ):
            result = mu.install_latest_maa(
                self.target,
                system="windows",
                machine="amd64",
                channel="beta",
            )

        latest.assert_called_once_with(
            ANY,
            system="windows",
            machine="amd64",
            channel="beta",
        )
        download.assert_called_once()
        self.assertEqual(result["platform"], "windows")
        self.assertEqual(result["arch"], "x64")
        self.assertEqual(result["runtime_downloaded"], 500)
        self.assertEqual(result["python_downloaded"], 0)
        self.assertEqual(result["channel"], "beta")
        self.assertEqual(result["operation"], "download")
        self.assertTrue((self.target / "MAA.exe").is_file())
        self.assertTrue((self.target / "config.json").is_file())

    def test_windows_existing_install_is_not_replaced(self):
        self.target.mkdir()
        (self.target / "MaaCore.dll").write_bytes(b"existing")
        with (
            patch.object(
                mu,
                "get_latest_release",
                side_effect=AssertionError("已安装 Maa 时不应请求下载信息"),
            ),
            self.assertRaisesRegex(mu.MaaUpdateError, "手动打开 Maa 进行更新"),
        ):
            mu.install_latest_maa(
                self.target,
                system="windows",
                machine="amd64",
            )

        self.assertEqual((self.target / "MaaCore.dll").read_bytes(), b"existing")

    def test_swap_failure_restores_target_and_previous_old(self):
        self.target.mkdir()
        (self.target / "original.txt").write_text("original", encoding="utf-8")
        self.backup.mkdir()
        (self.backup / "older.txt").write_text("older", encoding="utf-8")
        work_dir = self.root / "work"
        work_dir.mkdir()
        staged = work_dir / "new"
        staged.mkdir()
        (staged / "new.txt").write_text("new", encoding="utf-8")
        real_replace = os.replace

        def fail_new_install(source, destination):
            if Path(source) == staged and Path(destination) == self.target:
                raise OSError("swap failed")
            return real_replace(source, destination)

        with (
            patch.object(mu.os, "replace", side_effect=fail_new_install),
            self.assertRaises(OSError),
        ):
            mu.replace_with_backup(staged, self.target, work_dir)

        self.assertEqual((self.target / "original.txt").read_text(), "original")
        self.assertEqual((self.backup / "older.txt").read_text(), "older")


class TestLoadedMaaCache(unittest.TestCase):
    def test_loaded_maa_cache_is_released(self):
        target = Path("/tmp/test-maa-cache")
        python_path = str(target / "Python")
        main_module = types.ModuleType("arknights_mower.__main__")
        main_module.base_scheduler = types.SimpleNamespace(MAA=object())
        base_module = types.ModuleType("arknights_mower.solvers.base_schedule")
        base_module.Message = object()
        asst_module = types.ModuleType("asst")
        asst_child = types.ModuleType("asst.asst")

        class Asst:
            _Asst__lib = types.SimpleNamespace(_handle=123)

        asst_child.Asst = Asst
        old_path = list(sys.path)
        sys.path.append(python_path)
        try:
            with (
                patch.dict(
                    sys.modules,
                    {
                        "arknights_mower.__main__": main_module,
                        "arknights_mower.solvers.base_schedule": base_module,
                        "asst": asst_module,
                        "asst.asst": asst_child,
                    },
                ),
                patch.object(mu, "_close_dynamic_library") as close,
            ):
                mu.clear_loaded_maa_cache(target)
                self.assertNotIn("asst", sys.modules)
                self.assertNotIn("asst.asst", sys.modules)
                close.assert_called_once_with(123)
            self.assertIsNone(main_module.base_scheduler.MAA)
            self.assertIsNone(base_module.Message)
            self.assertIsNone(Asst._Asst__lib)
            self.assertNotIn(python_path, sys.path)
        finally:
            sys.path[:] = old_path


if __name__ == "__main__":
    unittest.main()
