#!/usr/bin/env python3
"""
archive_note.py

Helper script for mower-archive-agent-notes skill.
Automates transitioning note triplets between lifecycles (proposed -> implemented -> archived / rejected)
and synchronizes frontmatter and sidecar JSON status.
It does not verify implementation, behavior tests or review conclusions.
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

VALID_LIFECYCLES = {"proposed", "implemented", "archived", "rejected"}


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

    path = Path(slug_path)
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

    if source_lifecycle == target_lifecycle:
        print(
            f"Note '{stem}' is already in lifecycle '{target_lifecycle}'. Nothing to do."
        )
        return

    source_dir = notes_root / source_lifecycle / category
    target_dir = notes_root / target_lifecycle / category
    extensions = [".md", ".zh.md", ".sidecar.json"]

    # 1. Pre-flight Validation: Check all source files exist and are complete
    missing_sources = []
    for ext in extensions:
        src = source_dir / f"{stem}{ext}"
        if not src.exists():
            missing_sources.append(src)

    if missing_sources:
        raise FileNotFoundError(
            f"Cannot transition incomplete note triplet '{stem}': missing {missing_sources}"
        )

    # 2. Validate sidecar JSON is readable
    sidecar_path = source_dir / f"{stem}.sidecar.json"
    try:
        json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise ValueError(f"Invalid sidecar JSON in {sidecar_path}: {e}") from e

    # 3. Collision Prevention: Ensure no target file already exists in target_dir
    existing_targets = []
    for ext in extensions:
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
        description="Transition agent note triplets between lifecycles."
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
