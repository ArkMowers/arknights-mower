"""Local package inspection never imports package code or fetches metadata."""

import io
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from arknights_mower.utils.software_update_package import (
    executable_platform,
    inspect_package,
    package_version,
)


def package_files(version="4.2.0", system="windows", arch="x64"):
    header = bytearray(128)
    if system == "windows":
        header[:2] = b"MZ"
        struct.pack_into("<I", header, 60, 64)
        header[64:68] = b"PE\0\0"
        struct.pack_into("<H", header, 68, 0x8664 if arch == "x64" else 0xAA64)
    else:
        header[:6] = b"\x7fELF\x02\x01"
        struct.pack_into("<H", header, 18, 62 if arch == "x64" else 183)
    library = io.BytesIO()
    with zipfile.ZipFile(library, "w") as archive:
        archive.writestr("fixture.pyc", b"fixture")
    root = "mower/_internal/"
    return {
        "mower/" + ("mower.exe" if system == "windows" else "mower"): bytes(header),
        "mower/" + ("manager.exe" if system == "windows" else "manager"): bytes(header),
        root
        + "arknights_mower/__init__.py": f'__version__ = "{version}"\nraise RuntimeError("must not execute")\n'.encode(),
        root + "arknights_mower/utils/update_runtime.py": b"# fixture",
        root + "arknights_mower/utils/software_update_worker.py": b"# fixture",
        root + "ui/dist/index.html": b"fixture",
        root + "ui/dist/manager/index.html": b"fixture",
        root + "base_library.zip": library.getvalue(),
        root
        + (
            "python312.dll" if system == "windows" else "libpython3.12.so.1.0"
        ): b"fixture runtime",
    }


def make_release_package(version="4.2.0", system="windows", arch="x64", *, files=None):
    files = package_files(version, system, arch) if files is None else files
    output = io.BytesIO()
    if system == "windows":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            for name, data in files.items():
                archive.writestr(name, data)
    else:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for name, data in files.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
    return output.getvalue()


class PackageInspectionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def inspect(self, data, system="windows", arch="x64", name="任意改名 (1).bin"):
        package = self.root / name
        package.write_bytes(data)
        return inspect_package(package, system, arch)

    def test_version_comes_from_contents_even_when_filename_claims_a_newer_version(
        self,
    ):
        for system in ("windows", "linux"):
            for arch in ("x64", "arm64"):
                with self.subTest(system=system, arch=arch):
                    result = self.inspect(
                        make_release_package("4.1.5", system, arch),
                        system,
                        arch,
                        "arknights-mower_99.0.0_macos_arm64 (1).dmg",
                    )
                    self.assertEqual(result["version"], "4.1.5")
                    self.assertEqual(
                        result["format"], "zip" if system == "windows" else "tar.gz"
                    )

    def test_required_files_and_python_library_are_checked(self):
        for missing in package_files():
            files = package_files()
            files.pop(missing)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.inspect(make_release_package(files=files))
        files = package_files()
        files["mower/_internal/base_library.zip"] = b"broken library"
        with self.assertRaisesRegex(ValueError, "标准库损坏"):
            self.inspect(make_release_package(files=files))

    def test_wrong_platform_architecture_and_source_zip_are_rejected(self):
        for data in (
            make_release_package(arch="arm64"),
            make_release_package(system="linux"),
            make_release_package(
                files={"arknights_mower/__init__.py": b'__version__ = "4.2.0"'}
            ),
        ):
            with self.assertRaises(ValueError):
                self.inspect(data)

    def test_corrupted_zip_and_gzip_footer_are_rejected(self):
        data = make_release_package()
        # Alter stored bytes without updating the ZIP CRC.
        with self.assertRaises(zipfile.BadZipFile):
            self.inspect(data.replace(b"must not execute", b"must not executX"))
        data = bytearray(make_release_package(system="linux"))
        data[-8] ^= 0xFF
        with self.assertRaises(OSError):
            self.inspect(bytes(data), "linux")
        for data in (b"", b"not an archive", make_release_package()[:100]):
            with self.assertRaises(ValueError):
                self.inspect(data)

    def test_version_is_a_single_literal_never_executed(self):
        path = self.root / "__init__.py"
        for source in (
            b'__version__ = str("4.2.0")',
            b'__version__ = "4.2.0"\n__version__ = "4.3.0"',
            b'def value():\n    __version__ = "4.2.0"',
            b'__version__ = "invalid"',
            b"broken(",
        ):
            path.write_bytes(source)
            with self.subTest(source=source), self.assertRaises(ValueError):
                package_version(path)
        path.write_text('__version__: str = "4.2.0-alpha.1"\nraise RuntimeError()\n')
        self.assertEqual(package_version(path), "4.2.0-alpha.1")

    def test_macho_architecture_is_read_without_running_the_executable(self):
        path = self.root / "mower"
        for cpu, arch in ((0x1000007, "x64"), (0x100000C, "arm64")):
            path.write_bytes(b"\xcf\xfa\xed\xfe" + struct.pack("<I", cpu) + bytes(24))
            self.assertEqual(executable_platform(path), ("macos", {arch}))

    @unittest.skipUnless(
        sys.platform == "darwin", "requires macOS hdiutil and codesign"
    )
    def test_real_renamed_dmg_inspects_signed_fixture_bundle(self):
        app = self.root / "image/mower.app"
        for name, data in package_files().items():
            if name.startswith("mower/_internal/"):
                target = (
                    app / "Contents/Resources" / name.removeprefix("mower/_internal/")
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        for name in ("MacOS/mower", "MacOS/manager", "Frameworks/Python"):
            target = app / "Contents" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile("/usr/bin/true", target)
            target.chmod(0o755)
        (app / "Contents/Info.plist").write_text(
            '<?xml version="1.0"?><plist version="1.0"><dict>'
            "<key>CFBundleExecutable</key><string>mower</string>"
            "<key>CFBundleIdentifier</key><string>mower.test.offline</string>"
            "</dict></plist>"
        )
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(app)],
            check=True,
            capture_output=True,
        )
        image = self.root / "fixture.dmg"
        subprocess.run(
            [
                "hdiutil",
                "create",
                "-srcfolder",
                str(app.parent),
                "-format",
                "UDZO",
                str(image),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        renamed = image.with_name("任意改名 (1).bin")
        image.rename(renamed)
        _, arches = executable_platform(app / "Contents/MacOS/mower")
        result = inspect_package(renamed, "macos", next(iter(arches)))
        self.assertEqual(result, {"version": "4.2.0", "format": "dmg"})
