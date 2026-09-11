import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from arknights_mower.utils.maa_update import (
    MaaUpdateError,
    extract_linux_package,
    parse_release,
)


class AndroidUpdateTests(unittest.TestCase):
    def payload(self, names):
        return {
            "tag_name": "v6.17.5",
            "assets": [
                {
                    "name": name,
                    "browser_download_url": "https://example.invalid/" + name,
                    "size": 10,
                    "digest": "sha256:" + "a" * 64,
                }
                for name in names
            ],
        }

    def test_only_official_android_component_selected(self):
        release = parse_release(
            self.payload(
                [
                    "MAA-v6.17.5-linux-aarch64.tar.gz",
                    "MAA-v6.17.5-win-arm64.zip",
                    "MAAComponent-v6.17.5-android-arm64.tar.gz",
                ]
            ),
            system="android",
            machine="aarch64",
        )
        self.assertEqual(
            release.runtime.name, "MAAComponent-v6.17.5-android-arm64.tar.gz"
        )
        self.assertIsNone(release.python_source)
        self.assertEqual(release.runtime.sha256, "a" * 64)

    def test_missing_android_asset_never_falls_back_to_linux(self):
        with self.assertRaises(MaaUpdateError):
            parse_release(
                self.payload(["MAA-v6.17.5-linux-aarch64.tar.gz"]),
                system="android",
                machine="arm64",
            )

    def test_android_archive_requires_android_controller(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "wrong.tar.gz"
            dest = Path(directory) / "out"
            dest.mkdir()
            with tarfile.open(package, "w:gz") as tar:
                for name in ("libMaaCore.so", "resource/config.json", "Python/asst.py"):
                    info = tarfile.TarInfo(name)
                    info.size = 2
                    tar.addfile(info, io.BytesIO(b"{}"))
            with self.assertRaisesRegex(MaaUpdateError, "Android"):
                extract_linux_package(package, dest, android=True)
