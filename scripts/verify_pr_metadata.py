#!/usr/bin/env python3
"""Check publishable PR format and terminology without executing body text."""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from verify_glossary_alignment import verify_pr_text
except ImportError:
    from scripts.verify_glossary_alignment import verify_pr_text


TITLE = re.compile(
    r"(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[A-Za-z][A-Za-z0-9_./-]*)\))?!?: (?P<description>[^\r\n]+)"
)
SECTIONS = ("Summary", "Evidence", "Merge Danger")
PLACEHOLDER = re.compile(r"〈[^〉\n]*〉|<(?i:type|scope|description)>")


def verify_title(title: str) -> list[str]:
    match = TITLE.fullmatch(title)
    if match is None:
        return [
            "PR title must use type(scope): description; an optional scope must be English"
        ]
    errors = []
    description = match["description"]
    if description != description.strip() or description.endswith(("。", ".")):
        errors.append("PR title description must be trimmed and have no final period")
    if not re.search(r"[\u3400-\u9fff]", description):
        errors.append("PR title description must contain Chinese text")
    if PLACEHOLDER.search(title):
        errors.append("PR title contains a template placeholder")
    return errors


def visible_lines(body: str) -> list[str]:
    """Remove comments and fenced examples from the structural view only."""
    lines = re.sub(r"<!--.*?(?:-->|$)", "", body, flags=re.DOTALL).splitlines()
    visible = []
    fence = None
    for line in lines:
        delimiter = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if (
                delimiter
                and delimiter[1][0] == fence[0]
                and len(delimiter[1]) >= len(fence)
                and not delimiter[2].strip()
            ):
                fence = None
            continue
        if delimiter:
            fence = delimiter[1]
            continue
        visible.append(line)
    return visible


def verify_pr_format(payload: object) -> list[str]:
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(key), str) for key in ("title", "body")
    ):
        return ["PR text must be an object with string title and body"]
    errors = verify_title(payload["title"])
    lines = visible_lines(payload["body"])
    headings = []
    for i, line in enumerate(lines):
        match = re.fullmatch(r" {0,3}##\s+(.+?)\s*", line)
        if match:
            name = re.sub(r"（[^）]*）$", "", match[1]).rstrip()
            headings.append((i, name))
    if tuple(name for _, name in headings) != SECTIONS:
        errors.append(
            "PR body must contain Summary, Evidence and Merge Danger once, in that order"
        )
    else:
        for index, (start, name) in enumerate(headings):
            end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
            content = lines[start + 1 : end]
            if not any(re.search(r"[\w\u3400-\u9fff]", line) for line in content):
                errors.append(f"PR body section {name} must contain explanatory text")
    if PLACEHOLDER.search("\n".join(lines)):
        errors.append("PR body contains a template placeholder")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pr-json", required=True, help="Title/body JSON file, or - for stdin"
    )
    parser.add_argument("--context-file", default="CONTEXT.md")
    args = parser.parse_args()
    try:
        source = (
            sys.stdin.read()
            if args.pr_json == "-"
            else Path(args.pr_json).read_text(encoding="utf-8-sig")
        )
        payload = json.loads(source)
        errors = verify_pr_format(payload)
        errors.extend(verify_pr_text(payload, args.context_file))
    except (OSError, ValueError) as error:
        errors = [f"Cannot read PR text: {error}"]
    if errors:
        print("FAILED: PR publication checks")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "PASSED: PR title, sections, placeholders and terminology. Fact coverage requires review."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
