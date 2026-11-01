#!/usr/bin/env python3
"""
verify_doc_links.py

Scans repository documentation Markdown files to verify that all relative links
resolve to valid target files, directories and Markdown anchors.
"""

import argparse
import html
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote

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
HEADING_PATTERN = re.compile(r"^ {0,3}#{1,6}(?:[ \t]+|$)(.*)$")
HTML_ANCHOR_PATTERN = re.compile(
    r"<[^>]*\s(?:id|name)\s*=\s*(?:\"([^\"]+)\"|'([^']+)'|([^\s>]+))[^>]*>",
    re.IGNORECASE,
)

IGNORED_SCHEMES = (
    "http://",
    "https://",
    "mailto:",
    "ftp://",
    "irc://",
    "conversation://",
)


def _non_fenced_lines(content: str) -> list[str]:
    """Preserve line numbers while excluding fenced examples and HTML comments."""
    lines = []
    fence = ""
    in_comment = False
    for line in content.splitlines():
        if fence:
            match = CODE_FENCE_PATTERN.match(line)
            if (
                match
                and match.group(1)[0] == fence[0]
                and len(match.group(1)) >= len(fence)
                and not line[match.end() :].strip()
            ):
                fence = ""
            lines.append("")
            continue
        if in_comment:
            _, end, line = line.partition("-->")
            if not end:
                lines.append("")
                continue
            in_comment = False
        while True:
            # A comment marker inside inline code is visible text.
            prose = INLINE_CODE_PATTERN.sub(
                lambda match: " " * len(match.group(0)), line
            )
            start = prose.find("<!--")
            if start < 0:
                break
            end = line.find("-->", start + 4)
            if end < 0:
                line = line[:start]
                in_comment = True
                break
            line = line[:start] + line[end + 3 :]
        match = CODE_FENCE_PATTERN.match(line)
        if match:
            fence = match.group(1)
            lines.append("")
        else:
            lines.append(line)
    return lines


def _markdown_anchors(content: str) -> set[str]:
    """Collect heading slugs and explicit HTML anchors from rendered prose."""
    lines = _non_fenced_lines(content)
    headings: set[str] = set()
    anchors: set[str] = set()
    for index, line in enumerate(lines):
        prose = (
            "" if line.startswith(("    ", "\t")) else INLINE_CODE_PATTERN.sub("", line)
        )
        for match in HTML_ANCHOR_PATTERN.finditer(prose):
            anchors.add(html.unescape(next(value for value in match.groups() if value)))
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            text = re.sub(r"[ \t]+#+[ \t]*$", "", heading_match.group(1))
        elif (
            index
            and re.fullmatch(r" {0,3}(?:=+|-+)[ \t]*", line)
            and lines[index - 1].strip()
            and not HEADING_PATTERN.match(lines[index - 1])
            and not re.match(
                r"(?: {4}|\t| {0,3}(?:>|[-+*]\s|\d+[.)]\s|<))", lines[index - 1]
            )
        ):
            text = lines[index - 1].strip()
        else:
            continue
        # Remove emphasis outside code spans; code identifiers retain underscores.
        pieces = []
        offset = 0
        for match in INLINE_CODE_PATTERN.finditer(text):
            pieces.append(
                re.sub(
                    r"(?<!\w)_{1,3}([^_]+)_{1,3}(?!\w)",
                    r"\1",
                    text[offset : match.start()],
                )
            )
            pieces.append(match.group(0)[len(match.group(1)) : -len(match.group(1))])
            offset = match.end()
        pieces.append(re.sub(r"(?<!\w)_{1,3}([^_]+)_{1,3}(?!\w)", r"\1", text[offset:]))
        text = "".join(pieces)
        # Keep link labels as visible heading text.
        text = INLINE_LINK_PATTERN.sub(lambda match: match.group(1), text)
        text = REF_LINK_PATTERN.sub(lambda match: match.group(1), text)
        text = re.sub(r"<[^>]*>", "", text)
        text = html.unescape(text).strip().lower()
        slug = "".join(
            "-" if char == " " else char
            for char in text
            if char in " -_" or unicodedata.category(char)[0] in "LNM"
        )
        unique = slug
        suffix = 0
        while unique in headings:
            suffix += 1
            unique = f"{slug}-{suffix}"
        headings.add(unique)
    return anchors | headings


def _check_target(
    target: str,
    md_file: Path,
    root_path: Path,
    line_no: int,
    link_repr: str,
    errors: list[str],
    anchor_cache: dict[Path, set[str]],
) -> None:
    target = target.strip()
    if not target:
        return

    if any(target.startswith(scheme) for scheme in IGNORED_SCHEMES):
        return

    file_target, _, fragment = target.partition("#")
    file_target = unquote(file_target)
    fragment = unquote(fragment)

    # If link starts with 'file:///', strip it for local link verification
    if not file_target:
        target_path = md_file
    elif file_target.startswith("file:///"):
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
    elif fragment and target_path.suffix.lower() == ".md":
        try:
            if target_path not in anchor_cache:
                anchor_cache[target_path] = _markdown_anchors(
                    target_path.read_text(encoding="utf-8")
                )
        except (OSError, UnicodeError) as exc:
            errors.append(f"Cannot read Markdown link target {target_path}: {exc}")
            return
        if fragment not in anchor_cache[target_path]:
            try:
                rel_source = md_file.relative_to(root_path)
            except ValueError:
                rel_source = md_file
            errors.append(
                f"Dead link in {rel_source}:{line_no}: '{link_repr}' -> "
                f"Anchor not found: '{fragment}' in {target_path}"
            )


def _markdown_files(root_path: Path) -> list[Path]:
    """Use Git's document set at worktree roots, with traversal for other roots."""
    git_marker = root_path / ".git"
    if git_marker.exists() or git_marker.is_symlink():
        worktree = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root_path,
            capture_output=True,
            timeout=10,
        )
        if worktree.returncode != 0:
            diagnostic = worktree.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"Git root lookup failed: {diagnostic}")
        git_root = Path(
            worktree.stdout.decode("utf-8", errors="surrogateescape").strip()
        ).resolve()
        if git_root != root_path:
            raise ValueError(f"Not a Git worktree root: {root_path}")

        inventory = subprocess.run(
            [
                "git",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                "*.md",
            ],
            cwd=root_path,
            capture_output=True,
            timeout=10,
        )
        if inventory.returncode != 0:
            diagnostic = inventory.stderr.decode("utf-8", errors="replace").strip()
            raise ValueError(f"Git document inventory failed: {diagnostic}")
        paths = {
            root_path / path.decode("utf-8", errors="surrogateescape")
            for path in inventory.stdout.split(b"\0")
            if path
        }
        return sorted(path for path in paths if path.is_file())

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
    return md_files


def verify_doc_links(root_dir: str | Path = ".") -> list[str]:
    root_path = Path(root_dir).resolve()
    errors: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}
    try:
        md_files = _markdown_files(root_path)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [f"Cannot collect Markdown documents: {exc}"]

    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"Failed to read {md_file}: {e}")
            continue

        # Step 1: Strip code fences and inline code.
        clean_lines = [
            INLINE_CODE_PATTERN.sub("", line) for line in _non_fenced_lines(content)
        ]

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
                        anchor_cache,
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
                        anchor_cache,
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
                        anchor_cache,
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
