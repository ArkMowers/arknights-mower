"""Verify the structure of a PyInstaller macOS .app bundle.

Checks, on the macOS build runner:

* the main executable matches the expected architecture (``file``/``lipo``)
* every Mach-O binary and dylib inside the bundle matches that architecture
* ``codesign --verify --deep --strict`` passes (ad-hoc signature is accepted)
* ``otool -L`` finds no missing or wrong absolute dynamic-library paths

The parsing helpers take captured command output so they can be unit-tested
without a macOS host.

Usage:
    python scripts/check_macos_app.py dist/mower/mower.app --arch x64
    python scripts/check_macos_app.py dist/mower/mower.app --arch arm64
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

SYSTEM_LIB_PREFIXES = ("/usr/lib/", "/System/Library/")
RELATIVE_PREFIXES = ("@rpath/", "@loader_path/", "@executable_path/")


def parse_file_arch(output: str) -> str | None:
    """Return 'x86_64' or 'arm64' from ``file`` output, else None."""
    if "universal" in output or ("x86_64" in output and "arm64" in output):
        return "universal2"
    if "x86_64" in output:
        return "x86_64"
    if "arm64" in output:
        return "arm64"
    return None


def is_system_dependency(dependency: str) -> bool:
    return dependency.startswith(SYSTEM_LIB_PREFIXES) or dependency.startswith(
        RELATIVE_PREFIXES
    )


def extract_otool_dependencies(output: str) -> list[str]:
    """Return the dependency paths from ``otool -L`` output (skipping the id line)."""
    dependencies = []
    for line in output.splitlines():
        if not line.startswith("\t") or not line.rstrip().endswith(")"):
            continue
        path = line.strip().split(" (", 1)[0]
        dependencies.append(path)
    return dependencies


def run_command(tool: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [tool, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def check_binary_arch(binary: Path, expected: str, runner=run_command) -> list[str]:
    """Return errors; empty means the binary matches the expected arch."""
    file_result = runner("file", str(binary))
    lipo_result = runner("lipo", "-info", str(binary))
    file_output = file_result.stdout + file_result.stderr
    lipo_output = lipo_result.stdout + lipo_result.stderr
    if file_result.returncode != 0 or not file_output.strip():
        return [f"{binary}: `file` failed to describe the binary"]
    arch = parse_file_arch(file_output)
    if arch == "universal2":
        return [f"{binary}: universal2 binary is not a single-arch build"]
    if arch != expected:
        return [f"{binary}: expected {expected} but `file` reports {arch or 'unknown'}"]
    if expected not in lipo_output:
        return [f"{binary}: `lipo -info` does not list {expected}"]
    return []


def check_bundle(app_dir: Path, expected: str, runner=run_command) -> list[str]:
    """Return all structural errors; empty means the bundle is valid."""
    if not app_dir.is_dir():
        return [f"{app_dir}: .app bundle not found"]
    macos_dir = app_dir / "Contents" / "MacOS"
    if not macos_dir.is_dir():
        return [f"{app_dir}: missing Contents/MacOS"]

    errors = []
    macho_files: list[Path] = []

    for binary in sorted(macos_dir.iterdir()):
        if binary.is_file():
            macho_files.append(binary)
            errors.extend(check_binary_arch(binary, expected, runner))

    for path in sorted(app_dir.rglob("*")):
        if not path.is_file() or path.suffix not in {".dylib", ".so"}:
            continue
        file_result = runner("file", str(path))
        file_output = file_result.stdout + file_result.stderr
        if "Mach-O" not in file_output:
            continue
        macho_files.append(path)
        arch = parse_file_arch(file_output)
        if arch != expected:
            errors.append(f"{path}: expected {expected} but `file` reports {arch}")

    codesign = runner("codesign", "--verify", "--deep", "--strict", str(app_dir))
    if codesign.returncode != 0:
        errors.append(
            f"codesign --verify failed for {app_dir}:\n{codesign.stdout + codesign.stderr}"
        )

    for binary in macho_files:
        otool = runner("otool", "-L", str(binary))
        if otool.returncode != 0:
            errors.append(f"otool -L failed for {binary}: {otool.stderr}")
            continue
        for dependency in extract_otool_dependencies(otool.stdout):
            if not is_system_dependency(dependency):
                errors.append(f"{binary}: unexpected dependency {dependency}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app_dir", type=Path, help="path to the .app bundle")
    parser.add_argument(
        "--arch",
        choices=("x86_64", "arm64"),
        required=True,
        help="expected architecture of the build",
    )
    args = parser.parse_args()

    missing = [
        tool for tool in ("file", "lipo", "codesign", "otool") if not shutil.which(tool)
    ]
    if missing:
        print(f"::error::required tools not found: {', '.join(missing)}")
        return 2

    errors = check_bundle(args.app_dir, args.arch)
    if errors:
        for error in errors:
            print(f"::error::{error}")
        print(f"macOS bundle check failed: {len(errors)} problem(s)")
        return 1
    print(f"macOS bundle check passed: {args.app_dir} is a valid {args.arch} app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
