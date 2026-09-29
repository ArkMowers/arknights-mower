#!/usr/bin/env python3
"""
verify_agent_note_format.py

Mechanically verifies the formatting, triplet completeness, and frontmatter/sidecar schemas
of all technical decision notes under .agents/notes/.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

VALID_LIFECYCLES = {"proposed", "implemented", "archived", "rejected"}
VALID_CATEGORIES = {
    "feature",
    "bug-fix",
    "simplification",
    "architecture",
    "process",
    "testing",
}

FILENAME_DATE_SLUG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)$"
)
INVARIANT_PATTERN = re.compile(r"^\[INV-(?:[A-Z]+-)?\d{2}\]$")
ISSUE_REF_PATTERN = re.compile(r"(?<![A-Za-z0-9_&#])#(\d{1,6})\b")


def parse_yaml_frontmatter(content: str) -> dict | None:
    """Parses simple key-value YAML frontmatter between leading --- delimiters."""
    lines = content.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    data = {}
    for i in range(1, len(lines)):
        line = lines[i].strip()
        if line == "---":
            return data
        if ":" in line:
            key, val = line.split(":", 1)
            data[key.strip()] = val.strip().strip("\"'")
    return None


def verify_agent_notes(notes_dir: str | Path = ".agents/notes") -> list[str]:
    errors = []
    notes_path = Path(notes_dir).resolve()

    if not notes_path.exists():
        return [f"Notes directory not found: {notes_path}"]

    # Collect all triplets by (lifecycle, category, slug_base)
    triplets: dict[tuple[str, str, str], dict[str, Path]] = {}

    for root, dirs, files in os.walk(notes_path):
        rel_root = Path(root).relative_to(notes_path)
        parts = rel_root.parts

        if not parts:
            # Top-level .agents/notes/ - allow AGENTS.md and hidden files
            for f in files:
                if f != "AGENTS.md" and not f.startswith("."):
                    errors.append(f"Unexpected file at root of notes directory: {f}")
            continue

        lifecycle = parts[0]
        if lifecycle not in VALID_LIFECYCLES:
            errors.append(f"Invalid lifecycle directory '{lifecycle}' in {rel_root}")
            continue

        if len(parts) == 1:
            for f in files:
                if f != ".gitkeep":
                    errors.append(
                        f"Unexpected file directly under lifecycle directory: {rel_root}/{f}"
                    )
            continue

        category = parts[1]
        if category not in VALID_CATEGORIES:
            errors.append(f"Invalid category directory '{category}' in {rel_root}")
            continue

        for f in files:
            if f == ".gitkeep":
                continue

            file_path = Path(root) / f

            # Check for issue tracker numbers in content
            try:
                content = file_path.read_text(encoding="utf-8")
                issue_matches = ISSUE_REF_PATTERN.findall(content)
                if issue_matches:
                    errors.append(
                        f"Prohibited issue tracker reference(s) #{','.join(issue_matches)} found in {file_path}"
                    )
            except Exception as e:
                errors.append(f"Failed to read file {file_path}: {e}")
                continue

            # Determine triplet role
            if f.endswith(".sidecar.json"):
                stem = f[:-13]
                role = "sidecar"
            elif f.endswith(".zh.md"):
                stem = f[:-6]
                role = "zh"
            elif f.endswith(".md"):
                stem = f[:-3]
                role = "en"
            else:
                errors.append(f"Unrecognized file naming convention: {file_path}")
                continue

            slug_match = FILENAME_DATE_SLUG_PATTERN.match(stem)
            if not slug_match:
                errors.append(
                    f"Filename does not match 'YYYY-MM-DD-slug' convention: {f} in {rel_root}"
                )
                continue

            key = (lifecycle, category, stem)
            if key not in triplets:
                triplets[key] = {}
            triplets[key][role] = file_path

    # Verify triplet completeness and metadata contents
    for (lifecycle, category, stem), roles in triplets.items():
        expected_date = stem[:10]

        # 1. Completeness
        for req_role in ("en", "zh", "sidecar"):
            if req_role not in roles:
                errors.append(
                    f"Incomplete triplet for '{stem}' in {lifecycle}/{category}: missing '{req_role}' file"
                )

        # 2. Markdown frontmatter validation
        for md_role in ("en", "zh"):
            if md_role in roles:
                path = roles[md_role]
                content = path.read_text(encoding="utf-8")
                fm = parse_yaml_frontmatter(content)
                if fm is None:
                    errors.append(f"Missing or malformed YAML frontmatter in {path}")
                    continue

                for req_key in ("title", "status", "category", "date"):
                    if req_key not in fm:
                        errors.append(
                            f"Frontmatter in {path} missing required key '{req_key}'"
                        )

                if fm.get("status") != lifecycle:
                    errors.append(
                        f"Frontmatter 'status' ({fm.get('status')}) does not match lifecycle directory ({lifecycle}) in {path}"
                    )
                if fm.get("category") != category:
                    errors.append(
                        f"Frontmatter 'category' ({fm.get('category')}) does not match category directory ({category}) in {path}"
                    )
                if fm.get("date") != expected_date:
                    errors.append(
                        f"Frontmatter 'date' ({fm.get('date')}) does not match filename date ({expected_date}) in {path}"
                    )

        # 3. Sidecar JSON validation
        if "sidecar" in roles:
            sidecar_path = roles["sidecar"]
            try:
                data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(f"Malformed JSON in {sidecar_path}: {e}")
                continue

            for req_key in (
                "title",
                "status",
                "category",
                "date",
                "authors",
                "invariants",
                "code_symbols",
                "test_suites",
            ):
                if req_key not in data:
                    errors.append(
                        f"Sidecar {sidecar_path} missing required key '{req_key}'"
                    )

            if data.get("status") != lifecycle:
                errors.append(
                    f"Sidecar 'status' ({data.get('status')}) does not match lifecycle ({lifecycle}) in {sidecar_path}"
                )
            if data.get("category") != category:
                errors.append(
                    f"Sidecar 'category' ({data.get('category')}) does not match category ({category}) in {sidecar_path}"
                )
            if data.get("date") != expected_date:
                errors.append(
                    f"Sidecar 'date' ({data.get('date')}) does not match filename date ({expected_date}) in {sidecar_path}"
                )

            invariants = data.get("invariants", [])
            if not isinstance(invariants, list):
                errors.append(f"Sidecar 'invariants' must be a list in {sidecar_path}")
            else:
                for inv in invariants:
                    if not INVARIANT_PATTERN.match(inv):
                        errors.append(
                            f"Invalid invariant format '{inv}' in {sidecar_path} "
                            "(must match [INV-XX] or [INV-SUBSYSTEM-XX])"
                        )

            for list_key in ("authors", "code_symbols", "test_suites"):
                val = data.get(list_key)
                if not isinstance(val, list):
                    errors.append(
                        f"Sidecar '{list_key}' must be a list in {sidecar_path}"
                    )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify agent note format and triplet integrity."
    )
    parser.add_argument(
        "--notes-dir",
        default=".agents/notes",
        help="Path to .agents/notes directory (default: .agents/notes)",
    )
    args = parser.parse_args()

    errors = verify_agent_notes(args.notes_dir)
    if errors:
        print(f"FAILED: Found {len(errors)} error(s) in agent notes:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        "SUCCESS: All agent notes strictly conform to triplet, naming, and schema standards."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
