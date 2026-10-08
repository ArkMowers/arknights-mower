#!/usr/bin/env python3
"""
verify_governance.py

Unified execution gate for Arknights Mower repository governance checks:
1. Note format, triplet integrity, and sidecar schemas (verify_agent_note_format.py)
2. Relative Markdown documentation links validity (verify_doc_links.py)
3. Glossary alignment against CONTEXT.md Avoid terms (verify_glossary_alignment.py)

Concept meaning, document placement, and glossary approval require manual review.
"""

import sys

try:
    from verify_agent_note_format import verify_agent_notes
    from verify_doc_links import verify_doc_links
    from verify_glossary_alignment import verify_glossary_alignment
except ImportError:
    from scripts.verify_agent_note_format import verify_agent_notes
    from scripts.verify_doc_links import verify_doc_links
    from scripts.verify_glossary_alignment import verify_glossary_alignment


def run_all_checks() -> int:
    print("=" * 60)
    print("Arknights Mower Repository Governance Gate Checks")
    print("=" * 60)

    total_errors = 0

    # 1. Agent Notes Triplet & Format Check
    print("\n[Gate 1/3] Verifying agent note format and triplet integrity...")
    note_errors = verify_agent_notes()
    if note_errors:
        print(f"  FAILED: {len(note_errors)} error(s)")
        for err in note_errors:
            print(f"    - {err}")
        total_errors += len(note_errors)
    else:
        print("  PASSED: All decision note triplets, naming, and schemas are valid.")

    # 2. Markdown Relative Links Check
    print("\n[Gate 2/3] Verifying Markdown relative links...")
    link_errors = verify_doc_links()
    if link_errors:
        print(f"  FAILED: {len(link_errors)} dead link(s)")
        for err in link_errors:
            print(f"    - {err}")
        total_errors += len(link_errors)
    else:
        print("  PASSED: All Markdown relative documentation links are valid.")

    # 3. Avoid-Term Check
    print("\n[Gate 3/3] Verifying Avoid terms from the domain glossary...")
    glossary_errors = verify_glossary_alignment()
    if glossary_errors:
        print(f"  FAILED: {len(glossary_errors)} Avoid-term check error(s)")
        for err in glossary_errors:
            print(f"    - {err}")
        total_errors += len(glossary_errors)
    else:
        print(
            "  PASSED: Zero Avoid terms detected across notes, docs, and code comments."
        )

    print("\n" + "=" * 60)
    print(
        "Scope: note formats, relative Markdown links and Avoid terms in scanned text."
    )
    print(
        "Manual review remains required for concept changes, document placement and "
        "glossary approval."
    )
    if total_errors > 0:
        print(f"FAILED: Found {total_errors} error(s) in the automated checks.")
        return 1

    print("AUTOMATED CHECKS PASSED: All three checks completed without errors.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(run_all_checks())
