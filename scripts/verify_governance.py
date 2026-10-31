#!/usr/bin/env python3
"""
verify_governance.py

Unified execution gate for Arknights Mower repository governance checks:
1. Note structures and required references (verify_agent_note_format.py)
2. Relative Markdown documentation links validity (verify_doc_links.py)
3. Avoid terms in scanned text (verify_glossary_alignment.py)
   Supplied PR metadata also checks publication format (verify_pr_metadata.py).

These checks do not establish behavior, semantic consistency or glossary approval.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    from verify_agent_note_format import verify_agent_notes
    from verify_doc_links import verify_doc_links
    from verify_glossary_alignment import verify_glossary_alignment, verify_pr_text
    from verify_pr_metadata import verify_pr_format
except ImportError:
    from scripts.verify_agent_note_format import verify_agent_notes
    from scripts.verify_doc_links import verify_doc_links
    from scripts.verify_glossary_alignment import (
        verify_glossary_alignment,
        verify_pr_text,
    )
    from scripts.verify_pr_metadata import verify_pr_format


def run_all_checks(
    repo_root: str | Path = ".",
    *,
    comparison_base: str | None = None,
    all_active: bool = False,
    pr_text: object | None = None,
) -> int:
    repository = Path(repo_root).resolve()
    print("=" * 60)
    print("Arknights Mower Repository Governance Gate Checks")
    print("=" * 60)

    total_errors = 0

    # 1. Agent Notes Triplet & Format Check
    print("\n[Gate 1/3] Verifying bilingual decisions and legacy triplet integrity...")
    note_warnings = []
    note_errors = verify_agent_notes(
        repository / ".agents/notes",
        repo_root=repository,
        warnings=note_warnings,
        comparison_base=comparison_base,
        all_active=all_active,
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
            "  PASSED: Relative document targets and Markdown anchors resolve; source links are excluded."
        )

    # 3. Avoid-Term Check
    print("\n[Gate 3/3] Verifying glossary Avoid terms in scanned text...")
    prose_warnings: list[str] = []
    glossary_errors = verify_glossary_alignment(
        repository / "CONTEXT.md",
        comparison_base=comparison_base,
        warnings=prose_warnings,
    )
    if prose_warnings:
        print(
            f"  UNCHANGED DEVELOPMENT PROSE: {len(prose_warnings)} listed-term occurrence(s)."
        )
        print(
            "  Existing wording is reported separately, not treated as a historical quotation; new lines are checked."
        )
    if pr_text is not None:
        glossary_errors.extend(verify_pr_format(pr_text))
        glossary_errors.extend(verify_pr_text(pr_text, repository / "CONTEXT.md"))
    if glossary_errors:
        print(f"  FAILED: {len(glossary_errors)} formal-text error(s)")
        for err in glossary_errors:
            print(f"    - {err}")
        total_errors += len(glossary_errors)
    else:
        print(
            "  PASSED: Listed terms and preserved-source markers checked in formal text scope."
        )
        if pr_text is not None:
            print(
                "  PASSED: Supplied PR title and body passed publication format checks."
            )

    print("\n" + "=" * 60)
    print("Scope: note structures/references, relative Markdown links and Avoid terms.")
    if pr_text is not None:
        print("PR scope: supplied title/body publication format and terminology.")
    print(
        "Not evaluated: behavior tests, record independence, contract consistency, "
        "concept meaning, glossary approval or implementation status."
    )
    if all_active:
        print(
            "Reference policy: full active-reference audit; archived warnings remain."
        )
    else:
        print(
            "Reference policy: changed active notes are strict; historical warnings remain."
        )
    if comparison_base is not None:
        print(f"Committed note changes are also checked against: {comparison_base}")
    print("Code-symbol resolution is not checked; review those references statically.")
    print(
        "Text scope includes skills and templates; source hashes/labels do not establish historical meaning or title completeness."
    )
    if total_errors > 0:
        print(f"FAILED: Found {total_errors} structural error(s).")
        return 1

    print("STRUCTURAL CHECKS PASSED: All three automated checks completed.")
    print("=" * 60)
    return 0


def github_comparison_scope() -> tuple[str | None, bool]:
    """Select committed scope from GitHub's event payload without shell interpolation."""
    event_name = os.environ["GITHUB_EVENT_NAME"]
    event = json.loads(
        Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
    )
    if not isinstance(event, dict):
        raise ValueError("GitHub event must be an object")
    if event_name == "workflow_dispatch":
        inputs = event.get("inputs", {})
        if not isinstance(inputs, dict):
            raise ValueError("Manual-run inputs must be an object")
        base = inputs.get("comparison_base", "")
        if not isinstance(base, str):
            raise ValueError("Manual comparison base must be a string")
        base = base.strip()
        return base or None, not bool(base)
    if event_name == "pull_request":
        base = event["pull_request"]["base"]["sha"]
    elif event_name == "push":
        base = event["before"]
    else:
        raise ValueError(f"Unsupported GitHub event: {event_name}")
    if not isinstance(base, str) or not re.fullmatch(r"[0-9a-f]{40}", base):
        raise ValueError("GitHub comparison base must be a full commit SHA")
    if base == "0" * 40:
        if event_name == "push":
            return None, True
        raise ValueError("Pull-request comparison base is missing")
    return base, False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run scoped structural governance checks"
    )
    parser.add_argument("--repo-root", default=".", help="Repository reference root")
    parser.add_argument(
        "--pr-json", help="Title/body JSON file; CI uses pull_request event text"
    )
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument(
        "--base", help="Also check active notes changed from this commit/ref to HEAD"
    )
    scope.add_argument(
        "--all-active", action="store_true", help="Check every active note reference"
    )
    scope.add_argument(
        "--ci", action="store_true", help="Use GitHub event comparison scope"
    )
    args = parser.parse_args()
    base, all_active = args.base, args.all_active
    pr_text = None
    if args.ci:
        try:
            base, all_active = github_comparison_scope()
            if os.environ["GITHUB_EVENT_NAME"] == "pull_request":
                event = json.loads(
                    Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8")
                )
                pr_text = {
                    key: event["pull_request"].get(key) for key in ("title", "body")
                }
                if "body" in event["pull_request"] and pr_text["body"] is None:
                    pr_text["body"] = ""
        except (KeyError, TypeError, OSError, ValueError) as error:
            print(f"FAILED: Cannot determine CI comparison scope: {error}")
            return 1
    if args.pr_json:
        try:
            pr_text = json.loads(Path(args.pr_json).read_text(encoding="utf-8-sig"))
            if pr_text is None:
                raise ValueError("PR text must be an object with string title and body")
        except (OSError, ValueError) as error:
            print(f"FAILED: Cannot read PR text: {error}")
            return 1
    return run_all_checks(
        args.repo_root, comparison_base=base, all_active=all_active, pr_text=pr_text
    )


if __name__ == "__main__":
    sys.exit(main())
