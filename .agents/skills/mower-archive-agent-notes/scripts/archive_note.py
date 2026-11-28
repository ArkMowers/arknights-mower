#!/usr/bin/env python3
"""
archive_note.py

Helper script for mower-archive-agent-notes skill.
Transitions bilingual decision records or legacy note triplets between lifecycles
and synchronizes their frontmatter and any legacy sidecar status.
It does not verify implementation, behavior tests or review conclusions.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

VALID_LIFECYCLES = {"proposed", "implemented", "archived", "rejected"}
VALID_CATEGORIES = {
    "architecture",
    "feature",
    "bug-fix",
    "simplification",
    "process",
    "testing",
}
SLUG_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$")


def note_frontmatter(file_path: Path) -> dict[str, str]:
    """Read the opening scalar fields used to select and validate a record format."""
    lines = file_path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if ":" in line:
            key, value = line.split(":", 1)
            fields[key.strip()] = value.strip().strip("\"'")
    return {}


def record_extensions(
    source_dir: Path, stem: str, lifecycle: str, category: str
) -> list[str]:
    """Select an explicit bilingual decision or retain the legacy triplet format."""
    markdown = [source_dir / f"{stem}{ext}" for ext in (".md", ".zh.md")]
    fields = [note_frontmatter(path) if path.is_file() else {} for path in markdown]
    formats = [frontmatter.get("format") for frontmatter in fields]
    if not any("format" in frontmatter for frontmatter in fields):
        return [".md", ".zh.md", ".sidecar.json"]
    if any(value not in (None, "decision") for value in formats):
        raise ValueError(f"Unsupported note format in '{stem}': {formats}")
    if (source_dir / f"{stem}.sidecar.json").exists():
        raise ValueError(f"Decision marker cannot hide a legacy sidecar for '{stem}'")
    for path, frontmatter in zip(markdown, fields):
        if not path.is_file():
            raise FileNotFoundError(
                f"Cannot transition incomplete decision: missing {path}"
            )
        if frontmatter.get("format") != "decision":
            raise ValueError(f"Both languages require 'format: decision': {path}")
        expected = {"status": lifecycle, "category": category, "date": stem[:10]}
        if not frontmatter.get("title"):
            raise ValueError(f"Decision frontmatter requires a title: {path}")
        for key, value in expected.items():
            if frontmatter.get(key) != value:
                raise ValueError(
                    f"Decision frontmatter '{key}' must be '{value}': {path}"
                )
    return [".md", ".zh.md"]


def update_markdown_status(file_path: Path, new_status: str) -> None:
    content = file_path.read_text(encoding="utf-8")
    # Only update status in the opening YAML frontmatter (between first and second '---')
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            # parts[0] is empty, parts[1] is frontmatter, parts[2] is markdown body
            frontmatter = re.sub(
                r'^(status:\s*)["\']?[a-z\-]+["\']?',
                rf"\g<1>{new_status}",
                parts[1],
                flags=re.MULTILINE,
            )
            updated = f"---{frontmatter}---{parts[2]}"
            file_path.write_text(updated, encoding="utf-8")
            return

    # Fallback if no frontmatter delimiters were found
    updated = re.sub(
        r'^(status:\s*)["\']?[a-z\-]+["\']?',
        rf"\g<1>{new_status}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    file_path.write_text(updated, encoding="utf-8")


def update_sidecar_status(file_path: Path, new_status: str) -> None:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    data["status"] = new_status
    file_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def transition_triplet(slug_path: str | Path, target_lifecycle: str) -> None:
    if target_lifecycle not in VALID_LIFECYCLES:
        raise ValueError(
            f"Invalid target lifecycle: {target_lifecycle}. Must be one of {VALID_LIFECYCLES}"
        )

    path = Path(slug_path).absolute()
    # Determine base directory and parts
    # Expected path: .agents/notes/{lifecycle}/{category}/{slug}
    # Can also be passed as .agents/notes/{lifecycle}/{category}/{slug}.md
    if path.name.endswith(".sidecar.json"):
        stem = path.name[:-13]
    elif path.name.endswith(".zh.md"):
        stem = path.name[:-6]
    elif path.suffix == ".md":
        stem = path.name[:-3]
    else:
        stem = path.name
    category = path.parent.name
    source_lifecycle = path.parent.parent.name
    notes_root = path.parent.parent.parent

    if (
        notes_root.name != "notes"
        or notes_root.parent.name != ".agents"
        or source_lifecycle not in VALID_LIFECYCLES
        or category not in VALID_CATEGORIES
        or not SLUG_PATTERN.fullmatch(stem)
    ):
        raise ValueError(
            "Expected .agents/notes/{lifecycle}/{category}/YYYY-MM-DD-slug"
        )

    if source_lifecycle == target_lifecycle:
        print(
            f"Note '{stem}' is already in lifecycle '{target_lifecycle}'. Nothing to do."
        )
        return

    source_dir = notes_root / source_lifecycle / category
    target_dir = notes_root / target_lifecycle / category
    resolved_root = notes_root.resolve()
    for directory in (source_dir, target_dir):
        if not directory.resolve().is_relative_to(resolved_root):
            raise ValueError(
                f"Note directory resolves outside the notes root: {directory}"
            )
    for directory in (source_dir, target_dir):
        for ext in (".md", ".zh.md", ".sidecar.json"):
            if not (directory / f"{stem}{ext}").resolve().is_relative_to(resolved_root):
                raise ValueError(
                    f"Note file resolves outside the notes root: {directory}"
                )
    extensions = record_extensions(source_dir, stem, source_lifecycle, category)

    # 1. Pre-flight Validation: Check all source files exist and are complete
    missing_sources = []
    for ext in extensions:
        src = source_dir / f"{stem}{ext}"
        if not src.is_file():
            missing_sources.append(src)

    if missing_sources:
        raise FileNotFoundError(
            f"Cannot transition incomplete note '{stem}': missing {missing_sources}"
        )

    # 2. Validate sidecar JSON is readable
    if ".sidecar.json" in extensions:
        sidecar_path = source_dir / f"{stem}.sidecar.json"
        try:
            data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Sidecar must be a JSON object")
        except Exception as e:
            raise ValueError(f"Invalid sidecar JSON in {sidecar_path}: {e}") from e

    # 3. Collision Prevention: Ensure no target file already exists in target_dir
    existing_targets = []
    for ext in (".md", ".zh.md", ".sidecar.json"):
        dst = target_dir / f"{stem}{ext}"
        if dst.exists():
            existing_targets.append(dst)

    if existing_targets:
        raise FileExistsError(
            f"Target note files already exist in {target_lifecycle}/{category}: {existing_targets}. "
            "Aborting transition to prevent accidental data overwrite."
        )

    # 4. Move and update status sequentially; this is not a transactional move.
    target_dir.mkdir(parents=True, exist_ok=True)
    print(f"Transitioning '{stem}' from {source_lifecycle} to {target_lifecycle}...")

    for ext in extensions:
        src = source_dir / f"{stem}{ext}"
        dst = target_dir / f"{stem}{ext}"

        shutil.move(str(src), str(dst))

        if ext in (".md", ".zh.md"):
            update_markdown_status(dst, target_lifecycle)
        elif ext == ".sidecar.json":
            update_sidecar_status(dst, target_lifecycle)

        print(f"  Moved & updated: {dst.relative_to(notes_root.parent)}")

    print(f"Successfully transitioned '{stem}' to {target_lifecycle}.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Transition bilingual decisions or legacy note triplets between lifecycles."
    )
    parser.add_argument(
        "note_path",
        help="Path to note or note stem (e.g., .agents/notes/proposed/feature/2026-09-28-my-feature)",
    )
    parser.add_argument(
        "--to", required=True, choices=list(VALID_LIFECYCLES), help="Target lifecycle"
    )
    args = parser.parse_args()

    try:
        transition_triplet(args.note_path, args.to)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
