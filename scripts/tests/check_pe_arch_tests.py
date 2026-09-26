"""Tests for the portable PE machine-type checker."""

import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_pe_arch  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]


def fake_pe(machine: int) -> bytes:
    """Build a minimal PE image header with the given IMAGE_FILE_MACHINE value."""
    e_lfanew = 0x40
    header = bytearray(b"\x00" * 0x100)
    header[0:2] = b"MZ"
    header[0x3C:0x40] = struct.pack("<I", e_lfanew)
    header[e_lfanew : e_lfanew + 4] = b"PE\x00\x00"
    header[e_lfanew + 4 : e_lfanew + 6] = struct.pack("<H", machine)
    return bytes(header)


class PeMachineTests(unittest.TestCase):
    def test_machine_type_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mower.exe"
            path.write_bytes(fake_pe(0x8664))
            self.assertEqual(check_pe_arch.pe_machine(path), 0x8664)

    def test_arm64_machine_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mower.exe"
            path.write_bytes(fake_pe(0xAA64))
            self.assertEqual(check_pe_arch.pe_machine(path), 0xAA64)

    def test_rejects_non_pe_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "not_a_pe.dll"
            path.write_bytes(b"not a PE file at all")
            with self.assertRaises(ValueError):
                check_pe_arch.pe_machine(path)

    def test_check_directory_rejects_mismatched_arch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.dll").write_bytes(fake_pe(0x8664))
            (root / "bad.dll").write_bytes(fake_pe(0xAA64))
            errors, _ = check_pe_arch.check_directory(root, "x64")
            self.assertEqual(len(errors), 1)
            self.assertIn("bad.dll", errors[0])

    def test_check_directory_passes_when_all_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.dll").write_bytes(fake_pe(0xAA64))
            (root / "b.pyd").write_bytes(fake_pe(0xAA64))
            errors, checked = check_pe_arch.check_directory(root, "arm64")
            self.assertEqual(errors, [])
            self.assertEqual(len(checked), 2)

    def test_check_directory_fails_without_pe_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readme.txt").write_text("hello", encoding="utf-8")
            errors, _ = check_pe_arch.check_directory(root, "x64")
            self.assertEqual(len(errors), 1)
            self.assertIn("no PE files", errors[0])

    def test_multi_arch_runtime_dirs_are_exempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # 多架构运行时载荷：即使 arch 不匹配也不该报错
            nested = root / "_internal/webview/lib/runtimes/win-arm64/native"
            nested.mkdir(parents=True)
            (nested / "WebView2Loader.dll").write_bytes(fake_pe(0xAA64))
            (root / "_internal/clr_loader/ffi/dlls/x86").mkdir(parents=True)
            (root / "_internal/clr_loader/ffi/dlls/x86/ClrLoader.dll").write_bytes(
                fake_pe(0x014C)
            )
            # 真实原生栈：x64 构建里的 arm64 扩展必须被抓住
            (root / "_internal/cv2").mkdir(parents=True)
            (root / "_internal/cv2/arm64.pyd").write_bytes(fake_pe(0xAA64))
            errors, checked = check_pe_arch.check_directory(root, "x64")
            self.assertEqual(len(errors), 1)
            self.assertIn("arm64.pyd", errors[0])
            self.assertEqual(len(checked), 1)

    def test_multi_arch_exception_helper(self):
        self.assertTrue(
            check_pe_arch.is_multi_arch_exception(
                "_internal/webview/lib/runtimes/win-arm64/native/WebView2Loader.dll"
            )
        )
        self.assertTrue(
            check_pe_arch.is_multi_arch_exception(
                "_internal/clr_loader/ffi/dlls/x86/ClrLoader.dll"
            )
        )
        self.assertTrue(
            check_pe_arch.is_multi_arch_exception(
                "_internal/pythonnet/runtime/Python.Runtime.dll"
            )
        )
        self.assertFalse(
            check_pe_arch.is_multi_arch_exception("_internal/cv2/arm64.pyd")
        )

    def test_real_x64_build_is_detected_as_x64(self):
        real_binary = REPO_ROOT / "dist/mower/mower.exe"
        if not real_binary.is_file():
            self.skipTest("no local x64 build available")
        self.assertEqual(check_pe_arch.pe_machine(real_binary), 0x8664)


if __name__ == "__main__":
    unittest.main()
