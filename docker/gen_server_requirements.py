#!/usr/bin/env python3
"""Filter desktop-only packages from the direct runtime dependencies.

Usage:
    python gen_server_requirements.py requirements.in requirements-server.txt
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable, Tuple

EXCLUDE = {"pywebview", "pystray", "pyautogui"}


def split_req(line: str) -> Tuple[str, str]:
    """Split a requirement into (name, rest).

    "rest" contains version specifiers / extras and leading whitespace is preserved.
    """

    # Remove inline comments for name parsing only
    trimmed = line.split("#", 1)[0].strip()
    if not trimmed:
        return "", line

    # Identify name part up to version/extras separators
    separators = ["==", ">=", "<=", "!=", "~=", "<", ">", "[", " "]
    idx = len(trimmed)
    for sep in separators:
        pos = trimmed.find(sep)
        if pos != -1:
            idx = min(idx, pos)
    name = trimmed[:idx]
    return name.lower(), line


def transform_lines(lines: Iterable[str]) -> Iterable[str]:
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            yield raw
            continue

        name, original = split_req(raw)
        if not name:
            yield raw
            continue

        if name in EXCLUDE:
            continue

        yield original


def main() -> int:
    if len(sys.argv) != 3:
        print(
            "Usage: python gen_server_requirements.py <input_requirements.txt> <output_requirements.txt>",
            file=sys.stderr,
        )
        return 1

    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])

    if not src.exists():
        print(f"Input requirements file not found: {src}", file=sys.stderr)
        return 1

    lines = src.read_text(encoding="utf-8-sig").splitlines(keepends=True)
    transformed = list(transform_lines(lines))
    dst.write_text("".join(transformed), encoding="utf-8")
    print(f"Generated server requirements: {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
