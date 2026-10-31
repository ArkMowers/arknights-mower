"""Tests for the macOS .app bundle structural check (no macOS tools required)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_macos_app  # noqa: E402


class FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def runner_with(script):
    """Build a fake runner: script maps (tool, last_arg) -> FakeResult."""

    def run(tool, *args):
        key = (tool, args[-1]) if args else (tool, None)
        return script.get(key, FakeResult(stderr=f"{tool}: not found", returncode=1))

    return run


class ParseHelpersTests(unittest.TestCase):
    def test_parse_file_arch(self):
        self.assertEqual(
            check_macos_app.parse_file_arch("Mach-O 64-bit x86_64"), "x86_64"
        )
        self.assertEqual(
            check_macos_app.parse_file_arch("Mach-O 64-bit arm64"), "arm64"
        )
        self.assertEqual(
            check_macos_app.parse_file_arch("Mach-O universal binary"), "universal2"
        )
        self.assertIsNone(check_macos_app.parse_file_arch("ASCII text"))

    def test_is_system_dependency(self):
        self.assertTrue(
            check_macos_app.is_system_dependency("/usr/lib/libSystem.B.dylib")
        )
        self.assertTrue(
            check_macos_app.is_system_dependency(
                "/System/Library/Frameworks/Cocoa.framework/..."
            )
        )
        self.assertTrue(
            check_macos_app.is_system_dependency("@rpath/libonnxruntime.dylib")
        )
        self.assertTrue(
            check_macos_app.is_system_dependency("@loader_path/libzbar.dylib")
        )
        self.assertFalse(
            check_macos_app.is_system_dependency("/opt/homebrew/lib/libzbar.dylib")
        )
        self.assertFalse(
            check_macos_app.is_system_dependency("/usr/local/lib/libiconv.dylib")
        )

    def test_extract_otool_dependencies(self):
        output = (
            "/app/Contents/MacOS/mower:\n"
            "\t/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n"
            "\t@rpath/libfoo.dylib (compatibility version 0.0.0)\n"
            "\t/opt/homebrew/lib/libzbar.dylib (compatibility version 6.0.0)\n"
        )
        deps = check_macos_app.extract_otool_dependencies(output)
        self.assertEqual(
            deps,
            [
                "/usr/lib/libSystem.B.dylib",
                "@rpath/libfoo.dylib",
                "/opt/homebrew/lib/libzbar.dylib",
            ],
        )

    def test_check_binary_arch_accepts_expected(self):
        binary = Path("mower")
        script = {
            ("file", "mower"): FakeResult("Mach-O 64-bit arm64"),
            ("lipo", "mower"): FakeResult("Non-fat file: arm64"),
        }
        self.assertEqual(
            check_macos_app.check_binary_arch(binary, "arm64", runner_with(script)), []
        )

    def test_check_binary_arch_rejects_wrong_arch_and_universal2(self):
        binary = Path("mower")
        wrong = runner_with(
            {
                ("file", "mower"): FakeResult("Mach-O 64-bit x86_64"),
                ("lipo", "mower"): FakeResult("Non-fat file: x86_64"),
            }
        )
        self.assertEqual(
            len(check_macos_app.check_binary_arch(binary, "arm64", wrong)), 1
        )

        universal = runner_with(
            {
                ("file", "mower"): FakeResult(
                    "Mach-O universal binary with 2 architectures"
                ),
                ("lipo", "mower"): FakeResult(
                    "Architectures in the fat file: x86_64 arm64"
                ),
            }
        )
        self.assertEqual(
            len(check_macos_app.check_binary_arch(binary, "arm64", universal)), 1
        )

    def test_check_bundle_reports_codesign_and_otool_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "mower.app"
            (app / "Contents" / "MacOS").mkdir(parents=True)
            (app / "Contents" / "MacOS" / "mower").write_bytes(b"\xcf\xfa\xed\xfe")
            script = {
                ("file", str(app / "Contents/MacOS/mower")): FakeResult(
                    "Mach-O 64-bit x86_64"
                ),
                ("lipo", str(app / "Contents/MacOS/mower")): FakeResult(
                    "Non-fat file: x86_64"
                ),
                (
                    "codesign",
                    str(app),
                ): FakeResult("code object is not signed at all", returncode=1),
                ("otool", str(app / "Contents/MacOS/mower")): FakeResult(
                    "/usr/lib/libSystem.B.dylib (compatibility version 1.0.0)\n"
                ),
            }
            errors = check_macos_app.check_bundle(app, "x86_64", runner_with(script))
            self.assertTrue(
                any("codesign --verify failed" in error for error in errors), errors
            )

    def test_check_bundle_flags_absolute_homebrew_dependency(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "mower.app"
            (app / "Contents" / "MacOS").mkdir(parents=True)
            (app / "Contents" / "MacOS" / "mower").write_bytes(b"\xcf\xfa\xed\xfe")
            script = {
                ("file", str(app / "Contents/MacOS/mower")): FakeResult(
                    "Mach-O 64-bit arm64"
                ),
                ("lipo", str(app / "Contents/MacOS/mower")): FakeResult(
                    "Non-fat file: arm64"
                ),
                ("codesign", str(app)): FakeResult(
                    "satisfies its Designated Requirement"
                ),
                ("otool", str(app / "Contents/MacOS/mower")): FakeResult(
                    "\t/opt/homebrew/lib/libzbar.dylib (compatibility version 6.0.0)\n"
                ),
            }
            errors = check_macos_app.check_bundle(app, "arm64", runner_with(script))
            self.assertTrue(
                any("unexpected dependency" in error for error in errors), errors
            )


if __name__ == "__main__":
    unittest.main()
