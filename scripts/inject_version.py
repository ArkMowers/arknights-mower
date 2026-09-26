#!/usr/bin/env python3
"""Inject release metadata into arknights_mower/__init__.py."""

import argparse
import re
from pathlib import Path

VERSION_PATTERN = re.compile(
    r"^[0-9]+\.[0-9]+\.[0-9]+(?:-alpha\.[0-9]+(?:\.g[0-9a-f]{8})?)?$"
)
DEFAULT_VERSION_FILE = Path("arknights_mower/__init__.py")
ARCHIVE_FORMATS = {"windows": "zip", "linux": "tar.gz", "macos": "dmg"}


def _replace_assignment(source: str, name: str, value: str, path: Path) -> str:
    pattern = re.compile(rf'^{re.escape(name)} = "[^"]*"$', re.MULTILINE)
    updated, count = pattern.subn(f'{name} = "{value}"', source)
    if count != 1:
        raise ValueError(f"expected one {name} assignment in {path}, found {count}")
    return updated


def inject_release(
    path: Path,
    version: str,
    system: str | None = None,
    arch: str | None = None,
) -> None:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"invalid release version: {version}")
    if (system is None) != (arch is None):
        raise ValueError("release system and architecture must be provided together")
    if system is not None and system not in ARCHIVE_FORMATS:
        raise ValueError(f"unsupported release system: {system}")
    if arch is not None and arch not in ("x64", "arm64"):
        raise ValueError(f"unsupported release architecture: {arch}")

    source = path.read_text(encoding="utf-8")
    source = _replace_assignment(source, "__version__", version, path)
    if system is not None:
        source = _replace_assignment(source, "__release_system__", system, path)
        source = _replace_assignment(source, "__release_arch__", arch, path)
        source = _replace_assignment(
            source, "__release_archive__", ARCHIVE_FORMATS[system], path
        )
    path.write_text(source, encoding="utf-8")


def inject_version(path: Path, version: str) -> None:
    inject_release(path, version)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="stable or alpha version without the leading v")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_VERSION_FILE,
        help="version file to update",
    )
    parser.add_argument("--system", choices=tuple(ARCHIVE_FORMATS))
    parser.add_argument("--arch", choices=("x64", "arm64"))
    args = parser.parse_args()

    inject_release(args.path, args.version, args.system, args.arch)
    print(f"injected {args.version} into {args.path}")


if __name__ == "__main__":
    main()
