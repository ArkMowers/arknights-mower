"""Android application packaging and independent host release reuse."""

import io
import json
import lzma
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.check_android_package import check
from scripts.package_android import REQUIRED, package
from scripts.sync_android_release import REPO, append_download_link


def runtime_fixture(root):
    """Minimal structural fixture; CI separately builds/imports the actual ARM64 image."""
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr(
            "usr/local/bin/python3.12", b"\x7fELF\x02\x01" + b"\0" * 12 + b"\xb7\0"
        )
        archive.writestr("usr/lib/os-release", "ID=debian")
        archive.writestr("etc/ssl/certs/ca-certificates.crt", "certificate")
        archive.writestr(
            ".symlinks.json", json.dumps({"usr/local/bin/python": "python3.12"})
        )
    output = root / "out/python-runtime.zip.xz"
    output.parent.mkdir(exist_ok=True)
    output.write_bytes(lzma.compress(payload.getvalue()))
    return output


class AndroidPackageTests(unittest.TestCase):
    def test_nightly_version_can_be_packaged_and_checked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            version = "4.1.6-alpha.9.g40ac54e4"
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("payload")
            (root / "arknights_mower/__init__.py").write_text(
                f'__version__ = "{version}"\n'
            )
            runtime_fixture(root)
            archive = package(root, root / "out", version, "a" * 40)
            check(archive, version, "a" * 40)

    def test_package_keeps_host_and_user_data_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in (
                *REQUIRED,
                "arknights_mower/models/model.bin",
                "ui/src/pages/basement_skill/skill.json",
                "ui/src/pages/basement_skill/buffer.json",
                "mower_android/maa.py",
                "config/conf.yml",
                "arknights_mower/tests/example.py",
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("payload")
            (root / "arknights_mower/__init__.py").write_text('__version__ = "4.2.0"\n')
            runtime_fixture(root)
            result = package(root, root / "out", "4.2.0", "a" * 40)
            with zipfile.ZipFile(result) as z:
                meta = json.loads(z.read("mower-android.json"))
                self.assertEqual(meta["runtime_api"], 1)
                self.assertEqual(meta["format"], 2)
                self.assertEqual(meta["min_apk"], 29)
                self.assertGreater(meta["runtime"]["unpacked_size"], 0)
                self.assertIn("python-runtime.zip.xz", z.namelist())
                self.assertEqual(meta["version"], "4.2.0")
                self.assertIn("mower/ui/dist/index.html", z.namelist())
                self.assertFalse(
                    any(name.startswith("mower/ui/src/") for name in z.namelist())
                )
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

    def test_missing_runtime_cannot_silently_publish_a_thin_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in REQUIRED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("payload")
            (root / "arknights_mower/__init__.py").write_text('__version__ = "4.2.0"\n')
            with self.assertRaisesRegex(ValueError, "missing Python runtime"):
                package(root, root / "out", "4.2.0", "a" * 40)
            self.assertFalse((root / "out").exists())

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


class AndroidDownloadLinkTests(unittest.TestCase):
    def test_release_links_to_android_repository_without_creating_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            body = root / "body.md"
            body.write_text("本期修复内容\n", encoding="utf-8")
            append_download_link(body)
            text = body.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("本期修复内容\n"))
            self.assertIn(f"https://github.com/{REPO}/releases", text)
            self.assertIn("Mower 热更新包", text)
            self.assertIn("无需等待新 APK", text)
            self.assertEqual(list(root.iterdir()), [body])
            append_download_link(body)
            self.assertEqual(body.read_text(encoding="utf-8"), text)


if __name__ == "__main__":
    unittest.main()


class AndroidArchiveValidationTests(unittest.TestCase):
    def fixture(self, root, changes=None):
        for name in REQUIRED:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("payload")
        (root / "arknights_mower/__init__.py").write_text('__version__ = "4.2.0"\n')
        runtime_fixture(root)
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
            {"python-runtime.zip.xz": "corrupt"},
            {"mower/server.py": "def invalid("},
            {"mower/arknights_mower/utils/git_revision": "b" * 40},
            {"mower/arknights_mower/__init__.py": '__version__ = "4.2.1"'},
            {"mower/mower_android/host.py": "payload"},
            {"mower/ui/src/pages/basement_skill/skill.json": "{}"},
            {"../outside": "payload"},
            {"mower-android.json": "{}"},
        ]
        for changes in cases:
            with (
                self.subTest(changes=list(changes)),
                tempfile.TemporaryDirectory() as temp,
            ):
                archive = self.fixture(Path(temp), changes)
                with self.assertRaises((ValueError, SyntaxError, lzma.LZMAError)):
                    check(archive, "4.2.0", "a" * 40)
