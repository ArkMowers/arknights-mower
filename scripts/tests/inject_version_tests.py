"""Tests for the shared release-version injection helper."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import inject_version  # noqa: E402


class InjectVersionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
