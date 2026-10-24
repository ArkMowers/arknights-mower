"""Desktop Release inspection reads only the embedded version file."""

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from arknights_mower.utils.software_update_package import (
    VERSION_FILE_PATH,
    inspect_package,
)


def version_source(version="4.2.0", system="windows", arch="x64", **changes):
    values = {
        "__version__": version,
        "__release_system__": system,
        "__release_arch__": arch,
        "__release_archive__": {
            "windows": "zip",
            "linux": "tar.gz",
            "macos": "dmg",
        }[system],
    }
    values.update(changes)
    assignments = "\n".join(f'{name} = "{value}"' for name, value in values.items())
    return (assignments + "\nraise RuntimeError('must not execute')\n").encode()


def make_release_package(
    version="4.2.0", system="windows", arch="x64", *, content=None
):
    content = content or version_source(version, system, arch)
    output = io.BytesIO()
    if system == "windows":
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr(str(VERSION_FILE_PATH), content)
            archive.writestr("mower/任意其他文件.exe", b"not inspected")
    else:
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            info = tarfile.TarInfo(str(VERSION_FILE_PATH))
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
            ignored = b"not inspected"
            info = tarfile.TarInfo("mower/任意其他文件")
            info.size = len(ignored)
            archive.addfile(info, io.BytesIO(ignored))
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

    def test_version_platform_and_arch_come_from_version_file_not_filename(self):
        for system, archive in (("windows", "zip"), ("linux", "tar.gz")):
            for arch in ("x64", "arm64"):
                with self.subTest(system=system, arch=arch):
                    result = self.inspect(
                        make_release_package("4.1.6-alpha.7", system, arch),
                        system,
                        arch,
                    )
                    self.assertEqual(
                        result, {"version": "4.1.6-alpha.7", "format": archive}
                    )

    def test_no_payload_file_list_is_validated(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr(str(VERSION_FILE_PATH), version_source())
        self.assertEqual(self.inspect(data.getvalue())["version"], "4.2.0")

    def test_version_file_must_match_current_platform_and_arch(self):
        for source in (
            version_source(system="linux", arch="x64"),
            version_source(system="windows", arch="arm64"),
        ):
            with (
                self.subTest(source=source),
                self.assertRaisesRegex(ValueError, "系统或架构"),
            ):
                self.inspect(make_release_package(content=source))

    def test_missing_duplicate_or_invalid_version_file_is_rejected(self):
        cases = []
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w") as archive:
            archive.writestr("mower/file", b"fixture")
        cases.append(empty.getvalue())
        duplicate = io.BytesIO()
        with zipfile.ZipFile(duplicate, "w") as archive:
            archive.writestr(str(VERSION_FILE_PATH), version_source())
            archive.writestr(str(VERSION_FILE_PATH), version_source())
        cases.append(duplicate.getvalue())
        cases.extend(
            make_release_package(content=content)
            for content in (
                b"not python(",
                version_source(version="invalid"),
                version_source(__release_system__="linux"),
                version_source(__release_archive__="tar.gz"),
                version_source(__release_arch__=""),
            )
        )
        for data in cases:
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                self.inspect(data)

    def test_unknown_or_damaged_archives_are_rejected(self):
        for data in (b"", b"not an archive", make_release_package()[:30]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.inspect(data)


if __name__ == "__main__":
    unittest.main()
