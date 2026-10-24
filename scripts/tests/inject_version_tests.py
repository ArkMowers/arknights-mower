"""Tests for the shared release-version injection helper."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inject_version  # noqa: E402


class InjectVersionTests(unittest.TestCase):
    def test_injects_desktop_release_metadata_into_version_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text(
                '__version__ = "4.1.5.8"\n'
                '__release_system__ = ""\n'
                '__release_arch__ = ""\n'
                '__release_archive__ = ""\n',
                encoding="utf-8",
            )

            inject_version.inject_release(path, "4.1.6-alpha.1", "linux", "arm64")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '__version__ = "4.1.6-alpha.1"\n'
                '__release_system__ = "linux"\n'
                '__release_arch__ = "arm64"\n'
                '__release_archive__ = "tar.gz"\n',
            )

    def test_injects_valid_alpha_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text(
                'before = True\n__version__ = "4.1.5.8"\nafter = True\n',
                encoding="utf-8",
            )

            inject_version.inject_version(path, "4.1.6-alpha.1")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                'before = True\n__version__ = "4.1.6-alpha.1"\nafter = True\n',
            )

    def test_injects_nightly_alpha_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text('__version__ = "4.1.6-alpha.9"\n', encoding="utf-8")
            inject_version.inject_version(path, "4.1.6-alpha.9.g12345678")
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '__version__ = "4.1.6-alpha.9.g12345678"\n',
            )

    def test_injects_valid_stable_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            path.write_text('__version__ = "4.1.5.8"\n', encoding="utf-8")

            inject_version.inject_version(path, "4.1.6")

            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '__version__ = "4.1.6"\n',
            )

    def test_rejects_invalid_release_version_without_writing(self):
        cases = (
            "4.1.6-alpha",
            "4.1.6-alpha.1.2",
            "4.1.6-dev.1234abc",
            "4.1",
            "v4.1.6-alpha.1",  # 不能带 v
        )
        for version in cases:
            with self.subTest(version=version):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "__init__.py"
                    original = '__version__ = "4.1.5.8"\n'
                    path.write_text(original, encoding="utf-8")

                    with self.assertRaisesRegex(ValueError, "invalid release version"):
                        inject_version.inject_version(path, version)

                    self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_requires_exactly_one_assignment_without_writing(self):
        cases = (
            "value = 'missing'\n",
            '__version__ = "one"\n__version__ = "two"\n',
        )
        for original in cases:
            with self.subTest(original=original):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "__init__.py"
                    path.write_text(original, encoding="utf-8")

                    with self.assertRaisesRegex(ValueError, "expected one"):
                        inject_version.inject_version(path, "4.1.6-alpha.1")

                    self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_invalid_release_metadata_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "__init__.py"
            original = (
                '__version__ = "4.1.5.8"\n'
                '__release_system__ = ""\n'
                '__release_arch__ = ""\n'
                '__release_archive__ = ""\n'
            )
            path.write_text(original, encoding="utf-8")
            for system, arch in (
                ("windows", None),
                ("android", "arm64"),
                ("windows", "x86"),
            ):
                with (
                    self.subTest(system=system, arch=arch),
                    self.assertRaises(ValueError),
                ):
                    inject_version.inject_release(path, "4.1.6", system, arch)
                self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
