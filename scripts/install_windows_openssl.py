"""Install the pinned CPython Windows OpenSSL pair into one Mower environment."""

import argparse
import hashlib
import sys
import sysconfig
import tempfile
from http.client import HTTPException
from pathlib import Path
from urllib.request import urlopen

from check_pe_arch import EXPECTED_MACHINE, pe_machine

VERSION = "3.5.9"
SOURCE_URL = (
    "https://raw.githubusercontent.com/python/cpython-bin-deps/"
    "ddb46a415b4995440723183e644f8d2c346567a2/amd64/"
)
PRIVATE_DIR = "_mower_openssl_3_5_9"
HOOK = "00_mower_openssl.pth"
HASHES = {
    "libcrypto-3.dll": "75495fe0e079ab00d49be740d3c710a0b94e3f74f9648cb7cc9f768fc7f52319",
    "libssl-3.dll": "8957182a9c385bfd9f3f790921de2ddc614cf91f99edbed4e9e5446a46504e32",
    "LICENSE.txt": "ed72ce2b51ee58f117e5a021e2e04af158857f40269fbc03491f0b2a99dbcc96",
}

# Use the current venv as the anchor even when an application changes cwd or
# adds entries to sys.path. The DLL beside _ssl.pyd otherwise takes precedence.
STARTUP = (
    f"import runpy, sys; runpy.run_path(sys.prefix + "
    f'"/Lib/site-packages/{PRIVATE_DIR}/bootstrap.py")\n'
).encode("ascii")

BOOTSTRAP = b"""import ctypes
from pathlib import Path
import sys

root = Path(__file__).parent
kernel = ctypes.WinDLL("kernel32")
kernel.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
kernel.GetModuleHandleW.restype = ctypes.c_void_p
kernel.GetModuleFileNameW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint]
handles = []
try:
    for name in ("libcrypto-3.dll", "libssl-3.dll"):
        path = root / name
        handle = ctypes.WinDLL(str(path))
        loaded = ctypes.create_unicode_buffer(32768)
        if not kernel.GetModuleFileNameW(kernel.GetModuleHandleW(name), loaded, len(loaded)):
            raise ctypes.WinError()
        if not path.samefile(loaded.value):
            raise OSError(f"an earlier copy of {name} is already loaded")
        handles.append(handle)
except OSError as exc:
    raise SystemExit(f"Mower OpenSSL startup failed: {exc}. Remove 00_mower_openssl.pth to revert.")
sys._mower_openssl_handles = handles
"""


def verified_source(directory):
    files = {}
    for name, expected in HASHES.items():
        if directory is None:
            with urlopen(SOURCE_URL + name, timeout=30) as response:
                data = response.read()
        else:
            data = (directory / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError(f"Unexpected SHA256 for {name}")
        files[name] = data
    return files


def checked_path(path):
    # A junction or symlink inside the selected environment could redirect a
    # write into another application, even when the final filename looks safe.
    if path.resolve() != path:
        raise ValueError(f"Refusing redirected path: {path}")
    return path


def same_bytes(path, data):
    checked_path(path)
    return path.is_file() and path.read_bytes() == data


def install_venv(root, files):
    if sys.prefix == sys.base_prefix or root != Path(sys.prefix).resolve():
        raise ValueError("Run this script with the selected venv's Scripts/python.exe")
    site = checked_path(root / "Lib" / "site-packages")
    if not (root / "pyvenv.cfg").is_file() or not site.is_dir():
        raise ValueError(f"Not a Windows venv: {root}")
    private = checked_path(site / PRIVATE_DIR)
    hook = checked_path(site / HOOK)
    contents = {**files, "bootstrap.py": BOOTSTRAP}
    if hook.exists() and not same_bytes(hook, STARTUP):
        raise ValueError(f"Unrecognized startup hook: {hook}")
    if private.exists():
        if not all(same_bytes(private / name, data) for name, data in contents.items()):
            raise ValueError(
                f"Existing OpenSSL directory has different contents: {private}"
            )
    else:
        with tempfile.TemporaryDirectory(dir=site) as temp:
            staged = Path(temp) / PRIVATE_DIR
            staged.mkdir()
            for name, data in contents.items():
                (staged / name).write_bytes(data)
            staged.rename(private)
    if not same_bytes(hook, STARTUP):
        with tempfile.TemporaryDirectory(dir=site) as temp:
            staged_hook = Path(temp) / HOOK
            staged_hook.write_bytes(STARTUP)
            staged_hook.replace(hook)


def install_bundle(root, files):
    offline = root / "_internal.mower-openssl-pending"
    if offline.exists():
        raise ValueError(
            f"An interrupted build remains in {offline}. Rebuild the bundle."
        )
    internal = checked_path(root / "_internal")
    for name in ("mower.exe", "多开管理器.exe"):
        if pe_machine(checked_path(root / name)) != EXPECTED_MACHINE["x64"]:
            raise ValueError(f"Expected an x64 Mower bundle: {root}")
    for marker in ("base_library.zip", "arknights_mower/__init__.py", "_ssl.pyd"):
        if not checked_path(internal / marker).is_file():
            raise ValueError(f"Missing PyInstaller Mower bundle file: {marker}")
    contents = dict(files)
    contents["OpenSSL-LICENSE.txt"] = contents.pop("LICENSE.txt")
    for name in ("libcrypto-3.dll", "libssl-3.dll"):
        if not checked_path(internal / name).is_file():
            raise ValueError(f"Missing bundled OpenSSL dependency: {name}")
    changes = {
        name: data
        for name, data in contents.items()
        if not same_bytes(internal / name, data)
    }
    if not changes:
        return

    # Keep the build's dependency directory offline until the complete pair is
    # ready. A terminated build cannot be mistaken for a runnable release.
    with tempfile.TemporaryDirectory(dir=root) as temp:
        staged = Path(temp)
        for name, data in changes.items():
            (staged / name).write_bytes(data)
        internal.rename(offline)
        originals = {}
        try:
            for name in changes:
                dest = offline / name
                originals[name] = dest.read_bytes() if dest.exists() else None
                (staged / name).replace(dest)
        except BaseException:
            for name, prior in originals.items():
                dest = offline / name
                if prior is None:
                    dest.unlink(missing_ok=True)
                elif not same_bytes(dest, prior):
                    backup = staged / name
                    backup.write_bytes(prior)
                    backup.replace(dest)
            offline.rename(internal)
            raise
        offline.rename(internal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--download",
        action="store_true",
        help="fetch the pinned CPython binaries over HTTPS",
    )
    source.add_argument(
        "--source",
        type=Path,
        help="CPython bin-deps OpenSSL amd64 directory",
    )
    targets = parser.add_mutually_exclusive_group(required=True)
    targets.add_argument("--venv", type=Path, help="current Mower virtual environment")
    targets.add_argument(
        "--bundle", type=Path, help="completed Windows PyInstaller dist/mower directory"
    )
    args = parser.parse_args()
    if (
        sys.implementation.name != "cpython"
        or sys.version_info[:2] != (3, 12)
        or sys.platform != "win32"
        or sysconfig.get_platform() != "win-amd64"
    ):
        parser.exit(1, "Expected Windows x64 CPython 3.12.\n")
    try:
        files = verified_source(args.source)
        root = (args.venv or args.bundle).resolve(strict=True)
        if args.venv:
            install_venv(root, files)
        else:
            install_bundle(root, files)
    except (ValueError, OSError, HTTPException) as exc:
        parser.exit(1, f"OpenSSL installation failed: {exc}\n")
    print(f"Mower OpenSSL {VERSION} ready in {root}")


if __name__ == "__main__":
    main()
