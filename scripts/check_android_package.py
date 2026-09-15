"""Validate the application update archive before publishing it to Android hosts."""

import argparse
import json
import sys
import zipfile
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.package_android import REQUIRED, RUNTIME_API  # noqa: E402


def check(package: Path, version: str, revision: str) -> None:
    with zipfile.ZipFile(package) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError("duplicate entries or damaged Android archive")
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise ValueError(f"unsafe archive path: {name}")
            if name != "mower-android.json" and not name.startswith("mower/"):
                raise ValueError(f"unexpected archive root: {name}")
            if any(p in ("mower_android", "__pycache__", "tests") for p in path.parts):
                raise ValueError(f"host or development files in update: {name}")
        meta = json.loads(archive.read("mower-android.json"))
        expected = {
            "kind": "mower-android",
            "format": 1,
            "version": version,
            "revision": revision,
            "runtime_api": RUNTIME_API,
            "python": "3.12",
            "platform": "android",
            "arch": "arm64",
        }
        if meta != expected:
            raise ValueError("Android update manifest differs from expected release")
        for name in REQUIRED:
            if not archive.read("mower/" + name).strip():
                raise ValueError(f"empty required file: {name}")
        if (
            archive.read("mower/arknights_mower/utils/git_revision").decode()
            != revision
        ):
            raise ValueError("embedded revision differs from release")
        source = archive.read("mower/arknights_mower/__init__.py").decode()
        if f'__version__ = "{version}"' not in source:
            raise ValueError("embedded version differs from release")
        for name in names:
            if name.endswith(".py"):
                compile(archive.read(name), name, "exec")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    check(args.package, args.version, args.revision)
    print("Android update manifest, payload and Python syntax verified")


if __name__ == "__main__":
    main()
