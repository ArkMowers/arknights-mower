import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import install_windows_openssl as openssl  # noqa: E402

FILES = {
    "libcrypto-3.dll": b"new crypto",
    "libssl-3.dll": b"new ssl",
    "LICENSE.txt": b"new license",
}


class WindowsOpenSSLTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()

    def venv(self):
        venv = self.root / "venv"
        site = venv / "Lib" / "site-packages"
        site.mkdir(parents=True)
        (venv / "pyvenv.cfg").touch()
        self.enterContext(patch.object(sys, "prefix", str(venv)))
        self.enterContext(patch.object(sys, "base_prefix", str(self.root / "python")))
        return venv, site

    def test_changed_source_license_rejects_entire_install(self):
        venv, site = self.venv()
        source = self.root / "source"
        source.mkdir()
        for name, data in FILES.items():
            (source / name).write_bytes(data)
        hashes = {
            name: hashlib.sha256(data).hexdigest() for name, data in FILES.items()
        }
        (source / "LICENSE.txt").write_bytes(b"wrong license")
        self.enterContext(patch.object(openssl, "HASHES", hashes))
        self.enterContext(patch.object(sys, "platform", "win32"))
        self.enterContext(patch.object(sys, "version_info", (3, 12, 10)))
        self.enterContext(
            patch.object(openssl.sysconfig, "get_platform", return_value="win-amd64")
        )
        self.enterContext(
            patch.object(
                sys, "argv", ["install", "--source", str(source), "--venv", str(venv)]
            )
        )
        with (
            redirect_stderr(io.StringIO()) as err,
            self.assertRaises(SystemExit) as failure,
        ):
            openssl.main()
        self.assertNotEqual(failure.exception.code, 0)
        self.assertIn("SHA256 for LICENSE.txt", err.getvalue())
        self.assertEqual(list(site.iterdir()), [])

    def test_venv_install_is_repeatable_and_hook_can_be_removed(self):
        venv, site = self.venv()
        base_dlls = Path(sys.base_prefix) / "DLLs"
        base_dlls.mkdir(parents=True)
        for name in ("libcrypto-3.dll", "libssl-3.dll"):
            (base_dlls / name).write_bytes(b"base copy")
        openssl.install_venv(venv, FILES)
        hook = site / openssl.HOOK
        private = site / openssl.PRIVATE_DIR
        self.assertIn(f"{private.name}/bootstrap.py", hook.read_text("ascii"))
        self.assertTrue((private / "bootstrap.py").is_file())
        installed = [hook, *private.iterdir()]
        before = {p: p.stat().st_mtime_ns for p in installed}
        openssl.install_venv(venv, FILES)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in installed})
        for name, data in FILES.items():
            self.assertEqual((private / name).read_bytes(), data)
        hook.unlink()
        self.assertEqual(list(site.glob("*.pth")), [])
        for name in ("libcrypto-3.dll", "libssl-3.dll"):
            self.assertEqual((base_dlls / name).read_bytes(), b"base copy")

    def bundle_with_originals(self):
        bundle = self.root / "mower"
        internal = bundle / "_internal"
        (internal / "arknights_mower").mkdir(parents=True)
        for marker in ("base_library.zip", "_ssl.pyd", "arknights_mower/__init__.py"):
            (internal / marker).touch()
        for exe in ("mower.exe", "多开管理器.exe"):
            (bundle / exe).touch()
        self.enterContext(patch.object(openssl, "pe_machine", return_value=0x8664))
        original = {
            "libcrypto-3.dll": b"old crypto",
            "libssl-3.dll": b"old ssl",
            "OpenSSL-LICENSE.txt": b"old license",
        }
        for name, data in original.items():
            (internal / name).write_bytes(data)

        return bundle, original

    def test_bundle_rolls_back_failed_or_interrupted_second_replacement(self):
        bundle, original = self.bundle_with_originals()
        internal = bundle / "_internal"
        replace = Path.replace
        for failure in (PermissionError, KeyboardInterrupt):
            with self.subTest(failure=failure.__name__):

                def fail_second(staged, target):
                    if (
                        staged.name == "libssl-3.dll"
                        and staged.read_bytes() == FILES["libssl-3.dll"]
                    ):
                        self.assertEqual(
                            (target.parent / "libcrypto-3.dll").read_bytes(),
                            FILES["libcrypto-3.dll"],
                        )
                        if failure is KeyboardInterrupt:
                            replace(staged, target)
                        raise failure("injected test failure")
                    return replace(staged, target)

                with (
                    patch.object(Path, "replace", fail_second),
                    self.assertRaises(failure),
                ):
                    openssl.install_bundle(bundle, FILES)
                self.assertFalse((bundle / "_internal.mower-openssl-pending").exists())
                for name, data in original.items():
                    self.assertEqual((internal / name).read_bytes(), data)

    def test_orphaned_pending_directory_requires_rebuild(self):
        bundle, original = self.bundle_with_originals()
        internal = bundle / "_internal"
        pending = bundle / "_internal.mower-openssl-pending"
        internal.rename(pending)
        with self.assertRaisesRegex(ValueError, "(?i)rebuild"):
            openssl.install_bundle(bundle, FILES)
        self.assertFalse(internal.exists())
        for name, data in original.items():
            self.assertEqual((pending / name).read_bytes(), data)
