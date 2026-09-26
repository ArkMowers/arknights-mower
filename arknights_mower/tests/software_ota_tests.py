"""Portable OTA reconstruction from a verified release asset."""

import base64
import bz2
import hashlib
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from werkzeug.datastructures import FileStorage

from arknights_mower.utils import software_update
from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.software_update_worker import (
    Worker,
    apply_bsdiff,
    apply_ota_archive,
)


class SoftwareOtaTests(unittest.TestCase):
    BSDIFF_FIXTURE = base64.b64decode(
        "QlNESUZGNDAvAAAAAAAAADIAAAAAAAAALAEAAAAAAABCWmg5MUFZJlNZzSEkTQAABlBAcBQABEAAIAAhkwQhgIkDeF28XckU4UJDNISRNEJaaDkxQVkmU1muwWlpAABP4ADAQAgAACCgADDNAFKJppMCeJxOJ8XckU4UJCuwWlpAQlpoORdyRThQkAAAAAA="
    )

    def test_bsdiff_accepts_seek_only_control_block(self):
        def number(value):
            return abs(value).to_bytes(8, "little")[:-1] + bytes(
                [0x80 if value < 0 else 0]
            )

        control = b"".join(number(value) for value in (0, 0, 3, 3, 0, 0))
        compressed_control = bz2.compress(control)
        compressed_diff = bz2.compress(b"\0" * 3)
        patch = (
            b"BSDIFF40"
            + number(len(compressed_control))
            + number(len(compressed_diff))
            + number(3)
            + compressed_control
            + compressed_diff
            + bz2.compress(b"")
        )
        self.assertEqual(apply_bsdiff(b"abcdef", patch, 3), b"def")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.installed = self.root / "installed"
        self.installed.mkdir()
        (self.installed / "keep").write_bytes(b"keep")
        (self.installed / "replace").write_bytes(b"old")
        (self.installed / "delete").write_bytes(b"gone")

    def package(self, *, keep_hash=None, file_name="mower/added"):
        def file(value):
            return {
                "type": "file",
                "mode": 0o644,
                "sha256": hashlib.sha256(value).hexdigest(),
            }

        manifest = {
            "kind": "mower-ota",
            "format": 1,
            "from": "4.1.6-alpha.7",
            "to": "4.1.6-alpha.8",
            "platform": "windows",
            "arch": "x64",
            "files": {
                "mower/keep": file(b"keep"),
                "mower/replace": file(b"new"),
                file_name: file(b"added"),
            },
            "changed": ["mower/replace", file_name],
        }
        if keep_hash:
            manifest["files"]["mower/keep"]["sha256"] = keep_hash
        package = self.root / "ota.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("ota.json", json.dumps(manifest))
            archive.writestr("payload/mower/replace", b"new")
            archive.writestr("payload/" + file_name, b"added")
        return package

    def apply(self, package):
        apply_ota_archive(
            package,
            self.installed,
            self.root / "stage",
            from_version="4.1.6-alpha.7",
            to_version="v4.1.6-alpha.8",
            platform="windows",
            arch="x64",
        )

    def test_rebuilds_complete_target_and_deletes_absent_files(self):
        self.apply(self.package())
        self.assertEqual((self.root / "stage/mower/keep").read_bytes(), b"keep")
        self.assertEqual((self.root / "stage/mower/replace").read_bytes(), b"new")
        self.assertEqual((self.root / "stage/mower/added").read_bytes(), b"added")
        self.assertFalse((self.root / "stage/mower/delete").exists())

    def test_rejects_modified_base_and_escaping_path(self):
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.apply(self.package(keep_hash="0" * 64))
        with self.assertRaisesRegex(ValueError, "非法路径"):
            self.apply(self.package(file_name="mower/../outside"))
        self.assertFalse((self.root / "outside").exists())

    def test_rebuilds_bsdiff_executable_and_checks_its_base(self):
        old, new = b"old binary data" * 20, b"new binary data" * 20
        (self.installed / "binary").write_bytes(old)
        manifest = {
            "kind": "mower-ota",
            "format": 2,
            "from": "4.1.6-alpha.7",
            "to": "4.1.6-alpha.8",
            "platform": "windows",
            "arch": "x64",
            "files": {
                "mower/binary": {
                    "type": "file",
                    "mode": 0o755,
                    "sha256": hashlib.sha256(new).hexdigest(),
                }
            },
            "changed": ["mower/binary"],
            "patches": {
                "mower/binary": {
                    "type": "bsdiff",
                    "base_sha256": hashlib.sha256(old).hexdigest(),
                    "sha256": hashlib.sha256(self.BSDIFF_FIXTURE).hexdigest(),
                    "size": len(new),
                }
            },
        }
        package = self.root / "binary-ota.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("ota.json", json.dumps(manifest))
            archive.writestr("patch/mower/binary", self.BSDIFF_FIXTURE)
        self.apply(package)
        self.assertEqual((self.root / "stage/mower/binary").read_bytes(), new)
        (self.installed / "binary").write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "补丁起点"):
            self.apply(package)

    def test_manual_upload_accepts_matching_ota_without_network(self):
        archive = self.package()
        with (
            patch.object(runtime, "frozen", return_value=True),
            patch.object(runtime, "state_dir", return_value=self.root / "state"),
            patch.object(
                software_update, "platform_asset", return_value=("windows", "x64")
            ),
            patch.object(software_update, "__version__", "4.1.6-alpha.7"),
            patch.dict(software_update._checks, {}, clear=True),
            patch.object(
                software_update, "github", side_effect=AssertionError("offline")
            ),
        ):
            result = software_update.inspect_upload(
                FileStorage(
                    stream=io.BytesIO(archive.read_bytes()), filename="renamed.bin"
                )
            )
            self.assertEqual(result["package_kind"], "ota")
            self.assertEqual(result["version"], "v4.1.6-alpha.8")
            plan = software_update._checks[result["check_id"]]
            self.assertEqual(plan["current_version"], "4.1.6-alpha.7")
            self.assertEqual(plan["ota_asset"]["name"], "package.zip")
            self.assertEqual(
                plan["ota_asset"]["sha256"],
                hashlib.sha256(archive.read_bytes()).hexdigest(),
            )
            software_update.discard_upload(result["check_id"])
            with (
                patch.object(software_update, "__version__", "4.1.6-alpha.6"),
                self.assertRaisesRegex(ValueError, "需要从 4.1.6-alpha.7 更新"),
            ):
                software_update.inspect_upload(
                    FileStorage(
                        stream=io.BytesIO(archive.read_bytes()), filename="ota.zip"
                    )
                )
            self.assertEqual(list((self.root / "state/uploads").iterdir()), [])

    def test_manual_ota_rebuilds_locally_and_never_falls_back_to_network(self):
        executable = self.installed / "mower.exe"
        executable.write_bytes(b"old executable")
        update_runtime = (
            self.installed / "_internal/arknights_mower/utils/update_runtime.py"
        )
        update_runtime.parent.mkdir(parents=True)
        update_runtime.write_bytes(b"runtime")
        version_file = self.installed / "_internal/arknights_mower/__init__.py"
        version_file.write_bytes(b"old version")

        def record(data):
            return {
                "type": "file",
                "mode": 0o644,
                "sha256": hashlib.sha256(data).hexdigest(),
            }

        manifest = {
            "kind": "mower-ota",
            "format": 1,
            "from": "4.1.6-alpha.7",
            "to": "4.1.6-alpha.8",
            "platform": "windows",
            "arch": "x64",
            "files": {
                "mower/mower.exe": record(executable.read_bytes()),
                "mower/_internal/arknights_mower/utils/update_runtime.py": record(
                    update_runtime.read_bytes()
                ),
                "mower/_internal/arknights_mower/__init__.py": record(b"new version"),
            },
            "changed": ["mower/_internal/arknights_mower/__init__.py"],
        }
        archive = self.root / "local-ota.zip"
        with zipfile.ZipFile(archive, "w") as package:
            package.writestr("ota.json", json.dumps(manifest))
            package.writestr(
                "payload/mower/_internal/arknights_mower/__init__.py", b"new version"
            )
        work = self.root / "work"
        work.mkdir()
        staged = work / "package.zip"
        shutil.copy2(archive, staged)
        worker = object.__new__(Worker)
        worker.job = {
            "id": "manual",
            "manual": True,
            "version": "v4.1.6-alpha.8",
            "current_version": "4.1.6-alpha.7",
            "asset": {"name": staged.name},
            "ota_asset": {
                "name": staged.name,
                "size": staged.stat().st_size,
                "sha256": hashlib.sha256(staged.read_bytes()).hexdigest(),
                "platform": "windows",
                "arch": "x64",
            },
        }
        worker.root = self.installed
        worker.work = work
        worker.status = {}
        worker.report = Mock()
        worker.check_cancelled = Mock()
        worker.copy_package_file = shutil.copy2
        worker.prepare_full_package = Mock(
            side_effect=AssertionError("offline full fallback")
        )
        with (
            patch.object(sys, "platform", "win32"),
            patch(
                "arknights_mower.utils.software_update_worker.request_download",
                side_effect=AssertionError("manual OTA must stay offline"),
            ),
        ):
            worker.prepare_package()
        self.assertEqual(
            (worker.prepared / "_internal/arknights_mower/__init__.py").read_bytes(),
            b"new version",
        )
        self.assertEqual(executable.read_bytes(), b"old executable")
        worker.prepare_full_package.assert_not_called()
        executable.write_bytes(b"modified base")
        with (
            patch.object(sys, "platform", "win32"),
            patch(
                "arknights_mower.utils.software_update_worker.request_download",
                side_effect=AssertionError("manual OTA must stay offline"),
            ),
            self.assertRaisesRegex(ValueError, "SHA-256"),
        ):
            worker.prepare_package()
        worker.prepare_full_package.assert_not_called()

    def test_selects_exact_source_and_target_asset(self):
        name = "arknights-mower-ota_4.1.6-alpha.7_to_4.1.6-alpha.8_windows_x64.zip"
        release = {
            "tag_name": "v4.1.6-alpha.8",
            "draft": False,
            "assets": [
                {
                    "name": name,
                    "size": 123,
                    "digest": "sha256:" + "a" * 64,
                    "browser_download_url": f"https://github.com/{software_update.OTA_REPO}/releases/download/v4.1.6-alpha.8/{name}",
                }
            ],
        }
        with (
            patch.object(
                software_update, "platform_asset", return_value=("windows", "x64")
            ),
            patch.object(software_update, "github", return_value=release),
        ):
            selected = software_update.choose_ota_asset(
                "v4.1.6-alpha.8", "4.1.6-alpha.7"
            )
            self.assertEqual(selected["name"], name)
            self.assertIsNone(
                software_update.choose_ota_asset("v4.1.6-alpha.8", "4.1.6-alpha.6")
            )

    def test_bad_ota_falls_back_to_full_package_before_install(self):
        worker = object.__new__(Worker)
        worker.job = {
            "id": "test",
            "asset": {"name": "full.zip"},
            "ota_asset": {"name": "ota.zip"},
        }
        worker.work = self.root / "work"
        worker.work.mkdir()
        worker.root = self.root / "install"
        worker.root.mkdir()
        worker.report = Mock()
        worker.prepare_ota = Mock(side_effect=ValueError("base mismatch"))

        def prepare_full(payload):
            runtime = payload / "mower/_internal/arknights_mower/utils"
            runtime.mkdir(parents=True)
            (runtime / "update_runtime.py").write_text("ready")
            (payload / "mower/mower").write_text("binary")

        worker.prepare_full_package = Mock(side_effect=prepare_full)
        worker.copy_package_file = shutil.copy2
        worker.prepare_package()
        worker.prepare_full_package.assert_called_once()
        self.assertTrue((worker.prepared / "mower").is_file())


if __name__ == "__main__":
    unittest.main()
