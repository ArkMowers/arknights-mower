#!/usr/bin/env python3
"""
verify_governance.py

Unified execution gate for Arknights Mower repository governance checks:
1. Note structures and required references (verify_agent_note_format.py)
2. Relative Markdown documentation links validity (verify_doc_links.py)
3. Avoid terms in scanned text (verify_glossary_alignment.py)

These checks do not establish behavior, semantic consistency or glossary approval.
"""

import argparse
import sys
from pathlib import Path

try:
    from verify_agent_note_format import verify_agent_notes
    from verify_doc_links import verify_doc_links
    from verify_glossary_alignment import verify_glossary_alignment
except ImportError:
    from scripts.verify_agent_note_format import verify_agent_notes
    from scripts.verify_doc_links import verify_doc_links
    from scripts.verify_glossary_alignment import verify_glossary_alignment


def run_all_checks(
    repo_root: str | Path = ".", *, comparison_base: str | None = None
) -> int:
    repository = Path(repo_root).resolve()
    print("=" * 60)
    print("Arknights Mower Repository Governance Gate Checks")
    print("=" * 60)

    total_errors = 0

    # 1. Agent Notes Triplet & Format Check
    print("\n[Gate 1/3] Verifying agent note format and triplet integrity...")
    note_warnings = []
    note_errors = verify_agent_notes(
        repository / ".agents/notes",
        repo_root=repository,
        warnings=note_warnings,
        comparison_base=comparison_base,
    )
    if note_warnings:
        print(f"  COMPATIBILITY WARNINGS: {len(note_warnings)} historical reference(s)")
        for warning in note_warnings[:10]:
            print(f"    - {warning}")
        if len(note_warnings) > 10:
            print("    Remaining warnings: run scripts/verify_agent_note_format.py.")
    if note_errors:
        print(f"  FAILED: {len(note_errors)} error(s)")
        for err in note_errors:
            print(f"    - {err}")
        total_errors += len(note_errors)
    else:
        print("  PASSED: Note structures and required active references are valid.")

    # 2. Markdown Relative Links Check
    print("\n[Gate 2/3] Verifying Markdown relative links...")
    link_errors = verify_doc_links(repository)
    if link_errors:
        print(f"  FAILED: {len(link_errors)} dead link(s)")
        for err in link_errors:
            print(f"    - {err}")
        total_errors += len(link_errors)
    else:
        print(
            "  PASSED: Enforced relative document links exist; source links are excluded."
        )

    # 3. Avoid-Term Check
    print("\n[Gate 3/3] Verifying glossary Avoid terms in scanned text...")
    glossary_errors = verify_glossary_alignment(
        repository / "CONTEXT.md",
        scan_roots=[
            repository / path
            for path in (".agents/notes", "docs", "arknights_mower", "ui/src")
        ],
    )
    if glossary_errors:
        print(f"  FAILED: {len(glossary_errors)} glossary violation(s)")
        for err in glossary_errors:
            print(f"    - {err}")
        total_errors += len(glossary_errors)
    else:
        print(
            "  PASSED: Zero Avoid terms detected across notes, docs, and code comments."
        )

    print("\n" + "=" * 60)
    print("Scope: note structures/references, relative Markdown links and Avoid terms.")
    print(
        "Not evaluated: behavior tests, record independence, contract consistency, "
        "concept meaning, glossary approval or implementation status."
    )
    print(
        "Reference policy: changed active notes are strict; historical warnings remain."
    )
    if comparison_base is not None:
        print(f"Committed note changes are also checked against: {comparison_base}")
    print("Code-symbol resolution is not checked; review those references statically.")
    if total_errors > 0:
        print(f"FAILED: Found {total_errors} structural error(s).")
        return 1

    print("STRUCTURAL CHECKS PASSED: All three automated checks completed.")
    print("=" * 60)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run scoped structural governance checks"
    )
    parser.add_argument("--repo-root", default=".", help="Repository reference root")
    parser.add_argument(
        "--base", help="Also check active notes changed from this commit/ref to HEAD"
    )
    args = parser.parse_args()
    return run_all_checks(args.repo_root, comparison_base=args.base)


if __name__ == "__main__":
    sys.exit(main())
