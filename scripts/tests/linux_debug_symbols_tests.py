import ctypes
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.split_linux_debug_symbols import split_linux_debug_symbols


@unittest.skipUnless(
    sys.platform.startswith("linux"), "requires native Linux ELF tools"
)
class LinuxDebugSymbolsTests(unittest.TestCase):
    def test_bundle_loads_shared_library_and_gdb_finds_separate_symbols(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "mower"
            internal = bundle / "_internal"
            library = internal / "example" / "libexample.so.1"
            library.parent.mkdir(parents=True)
            source = root / "example.c"
            source.write_text("int answer(void) { return 42; }\n")
            subprocess.run(
                ["cc", "-g", "-shared", "-fPIC", "-o", library, source], check=True
            )
            alias = internal / "libexample.so"
            alias.symlink_to(library.relative_to(internal))
            notice = internal / "LICENSE"
            notice.write_bytes(b"example notice")
            launcher = bundle / "mower"
            launcher_bytes = library.read_bytes() + b"PyInstaller archive"
            launcher.write_bytes(launcher_bytes)
            stripped_input = internal / "plain.so"
            subprocess.run(
                ["objcopy", "--strip-debug", library, stripped_input], check=True
            )
            plain_bytes = stripped_input.read_bytes()
            mode = library.stat().st_mode

            split_linux_debug_symbols(bundle)

            self.assertEqual(launcher.read_bytes(), launcher_bytes)
            self.assertEqual(notice.read_bytes(), b"example notice")
            self.assertEqual(stripped_input.read_bytes(), plain_bytes)
            self.assertTrue(alias.is_symlink())
            self.assertEqual(library.stat().st_mode, mode)
            self.assertEqual(ctypes.CDLL(str(alias)).answer(), 42)
            sections = subprocess.check_output(["readelf", "-SW", library])
            self.assertNotIn(b".debug_info", sections)
            self.assertIn(b".gnu_debuglink", sections)
            self.assertFalse(list(bundle.rglob("*.debug")))
            stripped_bytes = library.read_bytes()
            split_linux_debug_symbols(bundle)
            self.assertEqual(library.read_bytes(), stripped_bytes)
            with tarfile.open(root / "mower-linux-debug.tar.gz") as symbols:
                self.assertEqual(
                    symbols.getnames(),
                    ["mower/_internal/example/.debug/libexample.so.1.debug"],
                )
                symbols.extractall(root, filter="data")
            with self.subTest(check="GDB source lookup"):
                if shutil.which("gdb") is None:
                    self.skipTest("GDB is unavailable for source lookup")
                source_line = subprocess.check_output(
                    ["gdb", "--batch", "-nx", library, "-ex", "info line answer"],
                    text=True,
                )
                self.assertIn("example.c", source_line)
            (library.parent / ".debug/libexample.so.1.debug").unlink()
            stripped_input.replace(library)
            split_linux_debug_symbols(bundle)
            with tarfile.open(root / "mower-linux-debug.tar.gz") as symbols:
                self.assertEqual(symbols.getnames(), [])
