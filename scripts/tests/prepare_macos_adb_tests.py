import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import prepare_macos_adb as adb


class PrepareMacosAdbTests(unittest.TestCase):
    def test_verified_archive_stages_only_adb_and_its_notices(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "tools.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("platform-tools/adb", b"test executable")
                package.writestr("platform-tools/NOTICE.txt", b"license notice")
                package.writestr("platform-tools/source.properties", b"Pkg.Revision=36")
                package.writestr("platform-tools/fastboot", b"not needed")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with patch.object(adb, "SHA256", digest):
                destination = adb.prepare_macos_adb(root / "staged", archive)
                before = (destination / "adb").stat().st_mtime_ns
                adb.prepare_macos_adb(destination, archive)
            self.assertEqual((destination / "adb").read_bytes(), b"test executable")
            self.assertEqual((destination / "adb").stat().st_mtime_ns, before)
            self.assertTrue((destination / "adb").stat().st_mode & 0o111)
            self.assertEqual(
                {path.name for path in destination.iterdir()},
                {"adb", "NOTICE.txt", "source.properties"},
            )

    def test_checksum_failure_preserves_existing_binary(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "adb").write_bytes(b"original")
            archive = root / "bad.zip"
            archive.write_bytes(b"incomplete download")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                adb.prepare_macos_adb(root, archive)
            self.assertEqual((root / "adb").read_bytes(), b"original")
