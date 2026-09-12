"""Android application packaging and independent host release reuse."""

import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts.check_android_package import check
from scripts.package_android import REQUIRED, package
from scripts.sync_android_release import REPO, candidates, download, sync


class AndroidPackageTests(unittest.TestCase):
    def test_package_keeps_host_and_user_data_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                *REQUIRED,
                "arknights_mower/models/model.bin",
                "mower_android/maa.py",
                "config/conf.yml",
                "arknights_mower/tests/example.py",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("payload")
            (root / "arknights_mower/__init__.py").write_text('__version__ = "4.2.0"\n')
            result = package(root, root / "out", "4.2.0", "a" * 40)
            with zipfile.ZipFile(result) as z:
                meta = json.loads(z.read("mower-android.json"))
                self.assertEqual(meta["runtime_api"], 1)
                self.assertEqual(meta["version"], "4.2.0")
                self.assertIn("mower/ui/dist/index.html", z.namelist())
                self.assertEqual(z.read("mower/CHANGELOG.md"), b"payload")
                self.assertIn("mower/arknights_mower/models/model.bin", z.namelist())
                self.assertFalse(
                    any(
                        "mower_android" in name
                        or "/tests/" in name
                        or "/config/conf.yml" in name
                        for name in z.namelist()
                    )
                )
                self.assertEqual(
                    z.read("mower/arknights_mower/utils/git_revision"), b"a" * 40
                )
            with self.assertRaisesRegex(ValueError, "version does not match"):
                package(root, root / "out", "4.2.1", "a" * 40)
            (root / "ui/dist/index.html").unlink()
            with self.assertRaisesRegex(ValueError, "missing build input"):
                package(root, root / "out", "4.2.0", "a" * 40)

    def test_missing_or_empty_changelog_cannot_publish_an_update(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("payload")
            (root / "arknights_mower/__init__.py").write_text('__version__ = "4.2.0"\n')
            changelog = root / "CHANGELOG.md"
            changelog.unlink()
            with self.assertRaisesRegex(ValueError, "missing build input: CHANGELOG"):
                package(root, root / "out", "4.2.0", "a" * 40)
            changelog.write_text(" \n\t")
            with self.assertRaisesRegex(ValueError, "empty build input: CHANGELOG"):
                package(root, root / "out", "4.2.0", "a" * 40)
            self.assertFalse((root / "out").exists())


def release(tag, date, api=1, prerelease=False):
    meta = {
        "format": 1,
        "runtime_api": api,
        "apk": {"name": "mower-android-arm64.apk"},
        "maa_python": {"name": "mower-maa-python-1.0.0.zip"},
    }
    return {
        "tag_name": tag,
        "published_at": date,
        "prerelease": prerelease,
        "assets": [
            {"name": "android-release.json", "payload": json.dumps(meta).encode()},
            {"name": "mower-android-arm64.apk", "payload": b"existing signed apk"},
            {"name": "mower-maa-python-1.0.0.zip", "payload": b"existing adapter"},
            {
                "name": "MAAComponent-v1-android-arm64.tar.gz",
                "payload": b"not mirrored",
            },
        ],
    }


def fetch(asset, destination, limit):
    path = destination / asset["name"]
    path.write_bytes(asset["payload"])
    return path


class AndroidReleaseSyncTests(unittest.TestCase):
    def test_channels_and_newest_compatible_host_are_independent_of_mower_version(self):
        items = [
            release("v0.1.0", "1"),
            release("v0.2.0-alpha.1", "2", prerelease=True),
            release("v0.3.0", "3", api=2),
            release("v0.4.0-dev.1", "4", prerelease=True),
        ]
        self.assertEqual(
            [r["tag_name"] for r in candidates(items, "stable")], ["v0.3.0", "v0.1.0"]
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"
            names = sync(items, "beta", root / "out", body, fetch)
            self.assertEqual(len(names), 2)
            self.assertIn("v0.2.0-alpha.1", body.read_text())
            self.assertEqual(
                (root / "out/mower-android-arm64.apk").read_bytes(),
                b"existing signed apk",
            )
            self.assertEqual(set(p.name for p in (root / "out").iterdir()), set(names))

    def test_absent_compatible_host_does_not_block_mower_release(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(
                sync(
                    [release("v1.0.0", "1", api=2)],
                    "stable",
                    root / "out",
                    root / "body",
                    fetch,
                ),
                [],
            )
            self.assertIn("仅发布 Mower 热更新包", (root / "body").read_text())

    def test_incomplete_or_corrupt_release_is_not_partially_published(self):
        item = release("v1.0.0", "1")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            def fail_second(asset, destination, limit):
                if asset["name"].endswith(".zip"):
                    raise ValueError("corrupt")
                return fetch(asset, destination, limit)

            with self.assertRaisesRegex(ValueError, "corrupt"):
                sync([item], "stable", root / "out", root / "body", fail_second)
            self.assertEqual(list((root / "out").iterdir()), [])
            item["assets"] = item["assets"][:2]
            with self.assertRaisesRegex(ValueError, "missing declared"):
                sync([item], "stable", root / "out", root / "body", fetch)

    def test_download_verifies_github_digest_and_removes_failed_file(self):
        payload = b"signed bytes"
        asset = {
            "name": "mower-android-arm64.apk",
            "size": len(payload),
            "digest": "sha256:" + hashlib.sha256(payload).hexdigest(),
            "browser_download_url": f"https://github.com/{REPO}/releases/download/v1.0.0/mower-android-arm64.apk",
        }
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch(
                "scripts.sync_android_release.urlopen", return_value=io.BytesIO(payload)
            ):
                self.assertEqual(download(asset, root, 100).read_bytes(), payload)
            with patch(
                "scripts.sync_android_release.urlopen",
                return_value=io.BytesIO(b"corrupt"),
            ):
                with self.assertRaisesRegex(ValueError, "digest or size"):
                    download(asset, root, 100)
            self.assertEqual(list(root.iterdir()), [])
            asset["browser_download_url"] = "https://example.com/file.apk"
            with self.assertRaisesRegex(ValueError, "metadata"):
                download(asset, root, 100)


if __name__ == "__main__":
    unittest.main()


class AndroidArchiveValidationTests(unittest.TestCase):
    def fixture(self, root, changes=None):
        for name in REQUIRED:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("payload")
        (root / "arknights_mower/__init__.py").write_text('__version__ = "4.2.0"\n')
        original = package(root, root / "out", "4.2.0", "a" * 40)
        if not changes:
            return original
        edited = root / "edited.zip"
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(edited, "w") as dest:
            files = {name: source.read(name) for name in source.namelist()}
            files.update(changes)
            for name, contents in files.items():
                dest.writestr(name, contents)
        return edited

    def test_real_package_passes_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            check(self.fixture(Path(temp)), "4.2.0", "a" * 40)

    def test_bad_payload_cannot_be_published(self):
        cases = [
            {"mower/CHANGELOG.md": " "},
            {"mower/server.py": "def invalid("},
            {"mower/arknights_mower/utils/git_revision": "b" * 40},
            {"mower/arknights_mower/__init__.py": '__version__ = "4.2.1"'},
            {"mower/mower_android/host.py": "payload"},
            {"../outside": "payload"},
            {"mower-android.json": "{}"},
        ]
        for changes in cases:
            with (
                self.subTest(changes=list(changes)),
                tempfile.TemporaryDirectory() as temp,
            ):
                archive = self.fixture(Path(temp), changes)
                with self.assertRaises((ValueError, SyntaxError)):
                    check(archive, "4.2.0", "a" * 40)
