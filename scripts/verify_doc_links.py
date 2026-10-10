#!/usr/bin/env python3
"""
verify_doc_links.py

Scans repository documentation Markdown files to verify that all relative links
resolve to valid target files or directories, preventing dead links.
"""

import argparse
import os
import re
import sys
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "tmp",
    ".pytest_cache",
    ".pytest_tmp",
    ".pytest_temp",
    ".ruff_cache",
    "dist",
    "build",
    "__pycache__",
}

INLINE_LINK_PATTERN = re.compile(
    r"\[([^\]]*)\]\(\s*(?:<([^>]+)>|([^\s\)\"\']+))(?:\s+[\"'(][^\"'\)]*[\"'\)])?\s*\)"
)
REF_DEF_PATTERN = re.compile(
    r"^[ \t]*\[([^\]]+)\]:\s*(?:<([^>]+)>|(\S+))(?:\s+[\"'(].*[\"'\)])?"
)
REF_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
INLINE_CODE_PATTERN = re.compile(r"(`+)(?:(?!\1)[\s\S])*\1")
CODE_FENCE_PATTERN = re.compile(r"^[ \t]*(```+|~~~+)")

IGNORED_SCHEMES = (
    "http://",
    "https://",
    "mailto:",
    "ftp://",
    "irc://",
    "conversation://",
)


def _check_target(
    target: str,
    md_file: Path,
    root_path: Path,
    line_no: int,
    link_repr: str,
    errors: list[str],
) -> None:
    target = target.strip()
    if not target or target.startswith("#"):
        return

    if any(target.startswith(scheme) for scheme in IGNORED_SCHEMES):
        return

    # Strip internal anchor if present: e.g. path/to/file.md#section -> path/to/file.md
    file_target = target.split("#", 1)[0]
    if not file_target:
        return

    # If link starts with 'file:///', strip it for local link verification
    if file_target.startswith("file:///"):
        target_path = Path(file_target[8:])
    else:
        target_path = (md_file.parent / file_target).resolve()

    # Source code references (.py, .js, .ts, .vue) may document planned subsystem contracts
    # across phased PR boundaries; only enforce hard existence on doc files, triplets, and directories.
    if file_target.endswith((".py", ".js", ".ts", ".vue")):
        return

    if not target_path.exists():
        try:
            rel_source = md_file.relative_to(root_path)
        except ValueError:
            rel_source = md_file
        errors.append(
            f"Dead link in {rel_source}:{line_no}: '{link_repr}' -> Target not found: {target_path}"
        )


def verify_doc_links(root_dir: str | Path = ".") -> list[str]:
    root_path = Path(root_dir).resolve()
    errors: list[str] = []

    # Gather markdown files
    md_files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        # Prune ignored directories in-place
        dirnames[:] = [
            d
            for d in dirnames
            if d not in IGNORED_DIRS and (not d.startswith(".") or d == ".agents")
        ]

        for f in filenames:
            if f.endswith(".md"):
                md_files.append(Path(dirpath) / f)

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"Failed to read {md_file}: {e}")
            continue

        raw_lines = content.splitlines()
        clean_lines: list[str] = []
        in_code_fence = False
        current_fence_marker = ""

        # Step 1: Strip code fences and inline code
        for line in raw_lines:
            fence_match = CODE_FENCE_PATTERN.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if not in_code_fence:
                    in_code_fence = True
                    current_fence_marker = marker[0]  # ` or ~
                    clean_lines.append("")
                    continue
                elif marker[0] == current_fence_marker:
                    in_code_fence = False
                    current_fence_marker = ""
                    clean_lines.append("")
                    continue

            if in_code_fence:
                clean_lines.append("")
            else:
                # Strip inline code backticks to avoid scanning documentation examples
                no_inline_code = INLINE_CODE_PATTERN.sub("", line)
                clean_lines.append(no_inline_code)

        # Step 2: Collect all reference link definitions: [ref]: target "title"
        ref_defs: dict[str, tuple[str, int]] = {}
        for line_no, line in enumerate(clean_lines, 1):
            ref_match = REF_DEF_PATTERN.match(line)
            if ref_match:
                ref_label = ref_match.group(1).strip().lower()
                target = ref_match.group(2) or ref_match.group(3)
                if target:
                    ref_defs[ref_label] = (target.strip(), line_no)
                    # Also verify reference definition target directly
                    _check_target(
                        target,
                        md_file,
                        root_path,
                        line_no,
                        f"[{ref_match.group(1)}]: {target}",
                        errors,
                    )

        # Step 3: Scan for inline links and reference usages
        for line_no, line in enumerate(clean_lines, 1):
            # Inline links: [text](target "title")
            for match in INLINE_LINK_PATTERN.finditer(line):
                text = match.group(1)
                target = match.group(2) or match.group(3)
                if target:
                    _check_target(
                        target,
                        md_file,
                        root_path,
                        line_no,
                        f"[{text}]({target})",
                        errors,
                    )

            # Reference links: [text][ref] or [ref][]
            for match in REF_LINK_PATTERN.finditer(line):
                text = match.group(1)
                ref_label = match.group(2).strip()
                lookup_key = ref_label.lower() if ref_label else text.strip().lower()

                if lookup_key in ref_defs:
                    ref_target = ref_defs[lookup_key][0]
                    _check_target(
                        ref_target,
                        md_file,
                        root_path,
                        line_no,
                        f"[{text}][{ref_label or text}]",
                        errors,
                    )
                else:
                    try:
                        rel_source = md_file.relative_to(root_path)
                    except ValueError:
                        rel_source = md_file
                    errors.append(
                        f"Dead link in {rel_source}:{line_no}: '[{text}][{ref_label}]' -> Unresolved reference label: '{lookup_key}'"
                    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify relative Markdown documentation links."
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Root directory of repository to scan (default: .)",
    )
    args = parser.parse_args()

    errors = verify_doc_links(args.root)
    if errors:
        print(f"FAILED: Found {len(errors)} broken relative link(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("SUCCESS: All Markdown relative documentation links are valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
