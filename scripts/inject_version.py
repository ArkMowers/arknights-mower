#!/usr/bin/env python3
"""Inject a stable or alpha release version into arknights_mower/__init__.py."""

import argparse
import re
from pathlib import Path

VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(-alpha\.[0-9]+)?$")
ASSIGNMENT_PATTERN = re.compile(r'^__version__ = "[^"]*"$', re.MULTILINE)
DEFAULT_VERSION_FILE = Path("arknights_mower/__init__.py")


def inject_version(path: Path, version: str) -> None:
    if VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"invalid release version: {version}")

    source = path.read_text(encoding="utf-8")
    new_source, count = ASSIGNMENT_PATTERN.subn(f'__version__ = "{version}"', source)
    if count != 1:
        raise ValueError(
            f"expected one __version__ assignment in {path}, found {count}"
        )
    path.write_text(new_source, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="stable or alpha version without the leading v")
    parser.add_argument(
        "--path",
        type=Path,
        default=DEFAULT_VERSION_FILE,
        help="version file to update",
    )
    args = parser.parse_args()

    inject_version(args.path, args.version)
    print(f"injected {args.version} into {args.path}")


if __name__ == "__main__":
    main()
