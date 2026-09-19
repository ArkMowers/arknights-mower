"""Verify the machine type of every PE file (exe/dll/pyd) under a directory.

Usage:
    python scripts/check_pe_arch.py dist/mower --arch arm64
    python scripts/check_pe_arch.py dist/mower --arch x64

Exits non-zero if any PE file does not match the expected architecture, or if
no PE file is found. This runs on the build runner to prove an ARM64 build is
genuinely ARM64 instead of an x64 binary renamed to look like one.
"""

import argparse
import struct
import sys
from pathlib import Path

# IMAGE_FILE_MACHINE_* values from the PE/COFF specification.
MACHINE_TYPES = {
    0x014C: "x86",
    0x01C4: "arm",
    0x8664: "x64",
    0xAA64: "arm64",
}
EXPECTED_MACHINE = {
    "x86": 0x014C,
    "arm": 0x01C4,
    "x64": 0x8664,
    "arm64": 0xAA64,
}
PE_SUFFIXES = (".exe", ".dll", ".pyd")

# PyInstaller 6 one-folder 布局把全部依赖放进 dist/mower/_internal。以下子路径
# 天然含多架构载荷，架构与主程序无关，豁免强校验：
#   - webview/lib/          pywebview 的 .NET AnyCPU 程序集（PE machine 恒为 x86）
#   - webview/lib/runtimes/ WebView2 为各架构分发的原生 loader
#   - clr_loader/ffi/       pythonnet 的 x86/x64 .NET host
#   - pythonnet/runtime/    pythonnet 的 AnyCPU 程序集
EXCEPTION_SUBSTRINGS = (
    "webview/lib/",
    "clr_loader/ffi/",
    "pythonnet/runtime/",
)


def is_multi_arch_exception(relative_posix: str) -> bool:
    return any(segment in relative_posix for segment in EXCEPTION_SUBSTRINGS)


def pe_machine(path: Path) -> int:
    """Return the IMAGE_FILE_MACHINE value of a PE file."""
    with open(path, "rb") as handle:
        header = handle.read(0x1000)
    if header[:2] != b"MZ":
        raise ValueError(f"{path}: not a PE file (missing MZ header)")
    (e_lfanew,) = struct.unpack_from("<I", header, 0x3C)
    if header[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError(f"{path}: missing PE signature")
    (machine,) = struct.unpack_from("<H", header, e_lfanew + 4)
    return machine


def machine_label(machine: int) -> str:
    return MACHINE_TYPES.get(machine, f"0x{machine:04X}")


def collect_pe_files(directory: Path) -> list[Path]:
    return sorted(
        path for path in directory.rglob("*") if path.suffix.lower() in PE_SUFFIXES
    )


def check_directory(directory: Path, expected: str) -> tuple[list[str], list[Path]]:
    """Return (errors, checked_files); empty errors means the check passed."""
    expected_machine = EXPECTED_MACHINE[expected]
    files = collect_pe_files(directory)
    if not files:
        return [f"{directory}: no PE files found under the given path"], []
    errors = []
    checked = []
    for path in files:
        relative = path.relative_to(directory).as_posix()
        if is_multi_arch_exception(relative):
            continue
        checked.append(path)
        try:
            machine = pe_machine(path)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
            continue
        if machine != expected_machine:
            errors.append(
                f"{path}: expected {expected} (0x{expected_machine:04X}) "
                f"but got {machine_label(machine)} (0x{machine:04X})"
            )
    return errors, checked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory to scan for PE files")
    parser.add_argument(
        "--arch",
        choices=sorted(EXPECTED_MACHINE),
        required=True,
        help="expected architecture of every PE file",
    )
    args = parser.parse_args()

    if not args.directory.is_dir():
        print(f"::error::{args.directory} is not a directory")
        return 2

    errors, checked = check_directory(args.directory, args.arch)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        print(f"PE architecture check failed: {len(errors)} problem(s)")
        return 1

    print(
        f"PE architecture check passed: {len(checked)} file(s) checked, all {args.arch}"
    )
    for path in checked:
        machine = pe_machine(path)
        print(f"  {machine_label(machine)}  {path.relative_to(args.directory)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
