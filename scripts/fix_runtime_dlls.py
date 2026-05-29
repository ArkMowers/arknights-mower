"""
Usage:
    Run this after `pyinstaller webui_zip.spec` on Windows.
    python scripts/fix_runtime_dlls.py
"""

import ctypes
import shutil
from ctypes import wintypes
from pathlib import Path

ROOT_DLL = Path("dist/mower/_internal/msvcp140.dll")
SKLEARN_DLL = Path("dist/mower/_internal/sklearn/.libs/msvcp140.dll")


class VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def file_version(path: Path) -> tuple[int, int, int, int]:
    size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
    buffer = ctypes.create_string_buffer(size)
    ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer)

    value = wintypes.LPVOID()
    value_len = wintypes.UINT()
    ctypes.windll.version.VerQueryValueW(
        buffer, "\\", ctypes.byref(value), ctypes.byref(value_len)
    )
    info = ctypes.cast(value, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    return (
        info.dwFileVersionMS >> 16,
        info.dwFileVersionMS & 0xFFFF,
        info.dwFileVersionLS >> 16,
        info.dwFileVersionLS & 0xFFFF,
    )


def version_text(version: tuple[int, int, int, int]) -> str:
    return ".".join(map(str, version))


def main() -> None:
    if not ROOT_DLL.is_file() or not SKLEARN_DLL.is_file():
        raise SystemExit(f"Missing DLL: {ROOT_DLL} or {SKLEARN_DLL}")

    root_version = file_version(ROOT_DLL)
    sklearn_version = file_version(SKLEARN_DLL)

    if root_version >= sklearn_version:
        source, target = ROOT_DLL, SKLEARN_DLL
        source_version, target_version = root_version, sklearn_version
    else:
        source, target = SKLEARN_DLL, ROOT_DLL
        source_version, target_version = sklearn_version, root_version

    if (
        source_version == target_version
        and source.stat().st_size == target.stat().st_size
    ):
        print(f"Already synced: {version_text(source_version)}")
        return

    shutil.copy2(source, target)
    print(
        f"Synced {target} from {source}: "
        f"{version_text(target_version)} -> {version_text(source_version)}"
    )


if __name__ == "__main__":
    main()
