#!/usr/bin/env python3
"""
verify_glossary_alignment.py

Parses CONTEXT.md dynamically to extract prohibited terms ('Avoid' lists), then scans
agent notes, documentation, and source code comments/docstrings for violations.
"""

import argparse
import ast
import io
import os
import re
import sys
import tokenize
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

SELF_EXCLUDED_FILES = {
    "CONTEXT.md",
    "CONTEXT.zh.md",
    "verify_glossary_alignment.py",
    "verify_governance.py",
    "verify_governance_tests.py",
}

AVOID_LINE_PATTERN = re.compile(
    r"-\s*\*\*_(?:Avoid|禁止使用)_\*\*:\s*(.+)", re.IGNORECASE
)
TERM_PAIR_PATTERN = re.compile(r"([^\(`]+)(?:\(`([^`\)]+)`\))?")


def extract_avoid_terms(context_path: Path) -> list[tuple[str, str]]:
    """Extracts (term, language_type) pairs from CONTEXT.md and CONTEXT.zh.md Avoid lines."""
    files_to_read = [context_path]
    zh_path = context_path.parent / "CONTEXT.zh.md"
    if zh_path.exists() and zh_path not in files_to_read:
        files_to_read.append(zh_path)

    avoid_terms = []
    seen = set()

    for cp in files_to_read:
        if not cp.exists():
            continue
        content = cp.read_text(encoding="utf-8")
        for line in content.splitlines():
            match = AVOID_LINE_PATTERN.search(line)
            if match:
                raw_terms = match.group(1).split(",")
                for raw_term in raw_terms:
                    raw_term = raw_term.strip()
                    if not raw_term:
                        continue
                    # Handle raw backtick items like `Runtime state`
                    clean_term = raw_term.strip("` \t")
                    pair_match = TERM_PAIR_PATTERN.search(raw_term)
                    if pair_match:
                        cn_part = pair_match.group(1).strip("` \t")
                        en_part = (
                            pair_match.group(2).strip("` \t")
                            if pair_match.group(2)
                            else ""
                        )
                        for part, lang in (
                            (cn_part, "cn" if not cn_part.isascii() else "en"),
                            (en_part, "en"),
                        ):
                            if part and part not in seen:
                                seen.add(part)
                                avoid_terms.append((part, lang))
                    elif clean_term and clean_term not in seen:
                        seen.add(clean_term)
                        avoid_terms.append(
                            (clean_term, "en" if clean_term.isascii() else "cn")
                        )

    return avoid_terms


def extract_js_ts_vue_comments(content: str) -> list[tuple[int, str]]:
    """Extracts comments (//, /* */, <!-- -->) from JS/TS/Vue content with 1-indexed line numbers."""
    results: list[tuple[int, str]] = []
    i = 0
    n = len(content)
    line_no = 1

    state = (
        "CODE"  # CODE, STR_S, STR_D, STR_B, COMMENT_LINE, COMMENT_BLOCK, COMMENT_HTML
    )
    comment_start_line = 1
    comment_chars: list[str] = []

    while i < n:
        c = content[i]

        if state == "CODE":
            if c == "\n":
                line_no += 1
                i += 1
            elif c == "'" and content[i : i + 3] != "'''":
                state = "STR_S"
                i += 1
            elif c == '"':
                state = "STR_D"
                i += 1
            elif c == "`":
                state = "STR_B"
                i += 1
            elif c == "/" and i + 1 < n and content[i + 1] == "/":
                state = "COMMENT_LINE"
                comment_start_line = line_no
                comment_chars = ["/", "/"]
                i += 2
            elif c == "/" and i + 1 < n and content[i + 1] == "*":
                state = "COMMENT_BLOCK"
                comment_start_line = line_no
                comment_chars = ["/", "*"]
                i += 2
            elif c == "<" and i + 3 < n and content[i : i + 4] == "<!--":
                state = "COMMENT_HTML"
                comment_start_line = line_no
                comment_chars = ["<", "!", "-", "-"]
                i += 4
            else:
                i += 1
        elif state == "STR_S":
            if c == "\n":
                line_no += 1
            if c == "\\" and i + 1 < n:
                i += 2
            elif c == "'":
                state = "CODE"
                i += 1
            else:
                i += 1
        elif state == "STR_D":
            if c == "\n":
                line_no += 1
            if c == "\\" and i + 1 < n:
                i += 2
            elif c == '"':
                state = "CODE"
                i += 1
            else:
                i += 1
        elif state == "STR_B":
            if c == "\n":
                line_no += 1
            if c == "\\" and i + 1 < n:
                i += 2
            elif c == "`":
                state = "CODE"
                i += 1
            else:
                i += 1
        elif state == "COMMENT_LINE":
            if c == "\n":
                comment_text = "".join(comment_chars)
                results.append((comment_start_line, comment_text))
                comment_chars = []
                state = "CODE"
                line_no += 1
                i += 1
            else:
                comment_chars.append(c)
                i += 1
        elif state == "COMMENT_BLOCK":
            if c == "\n":
                line_no += 1
            comment_chars.append(c)
            if c == "*" and i + 1 < n and content[i + 1] == "/":
                comment_chars.append("/")
                i += 2
                comment_text = "".join(comment_chars)
                for offset, c_line in enumerate(comment_text.splitlines()):
                    results.append((comment_start_line + offset, c_line))
                comment_chars = []
                state = "CODE"
            else:
                i += 1
        elif state == "COMMENT_HTML":
            if c == "\n":
                line_no += 1
            comment_chars.append(c)
            if c == "-" and i + 2 < n and content[i : i + 3] == "-->":
                comment_chars.append("-")
                comment_chars.append(">")
                i += 3
                comment_text = "".join(comment_chars)
                for offset, c_line in enumerate(comment_text.splitlines()):
                    results.append((comment_start_line + offset, c_line))
                comment_chars = []
                state = "CODE"
            else:
                i += 1

    if state == "COMMENT_LINE":
        results.append((comment_start_line, "".join(comment_chars)))
    elif state in ("COMMENT_BLOCK", "COMMENT_HTML"):
        comment_text = "".join(comment_chars)
        for offset, c_line in enumerate(comment_text.splitlines()):
            results.append((comment_start_line + offset, c_line))

    return results


def extract_comments_and_docstrings(file_path: Path) -> list[tuple[int, str]]:
    """Extracts line-numbered comment and docstring texts from Python or JS/TS/Vue files."""
    results: list[tuple[int, str]] = []
    suffix = file_path.suffix.lower()

    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    if suffix == ".py":
        # 1. Extract comments via tokenize
        try:
            content_bytes = content.encode("utf-8")
            tokens = tokenize.tokenize(io.BytesIO(content_bytes).readline)
            for tok in tokens:
                if tok.type == tokenize.COMMENT:
                    results.append((tok.start[0], tok.string))
        except Exception:
            for idx, line in enumerate(content.splitlines(), 1):
                if "#" in line:
                    results.append((idx, line[line.index("#") :]))

        # 2. Extract docstrings via AST
        try:
            tree = ast.parse(content)
            # Module docstring
            if (
                tree.body
                and isinstance(tree.body[0], ast.Expr)
                and isinstance(tree.body[0].value, ast.Constant)
                and isinstance(tree.body[0].value.value, str)
            ):
                doc_str = tree.body[0].value.value
                start_line = tree.body[0].lineno
                for offset, line_text in enumerate(doc_str.splitlines()):
                    results.append((start_line + offset, line_text))

            # Class and function docstrings
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    if (
                        node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)
                    ):
                        doc_str = node.body[0].value.value
                        start_line = node.body[0].lineno
                        for offset, line_text in enumerate(doc_str.splitlines()):
                            results.append((start_line + offset, line_text))
        except Exception:
            pass

    elif suffix in (".js", ".ts", ".vue"):
        results.extend(extract_js_ts_vue_comments(content))

    return results


def check_text_for_avoid_terms(
    text: str, avoid_terms: list[tuple[str, str]]
) -> list[str]:
    """Returns matching avoid terms found in text."""
    hits = []
    for term, lang in avoid_terms:
        if lang == "en":
            # Word boundary check for ASCII English terms
            pattern = r"\b" + re.escape(term) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                hits.append(term)
        else:
            # Substring check for Chinese terms
            if term in text:
                hits.append(term)
    return hits


def verify_glossary_alignment(
    context_file: str | Path = "CONTEXT.md",
    scan_roots: list[str | Path] | None = None,
) -> list[str]:
    context_path = Path(context_file).resolve()
    if not context_path.exists():
        return [f"CONTEXT.md not found at {context_path}"]

    avoid_terms = extract_avoid_terms(context_path)
    if not avoid_terms:
        return [f"No avoid terms extracted from {context_path}"]

    if scan_roots is None:
        scan_roots = [".agents/notes", "docs", "arknights_mower", "ui/src"]

    errors = []
    root_base = Path(".").resolve()

    for scan_root in scan_roots:
        root_dir = Path(scan_root).resolve()
        if not root_dir.exists():
            continue

        for dirpath, dirnames, filenames in os.walk(root_dir):
            dirnames[:] = [
                d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")
            ]

            for f in filenames:
                if f in SELF_EXCLUDED_FILES:
                    continue

                file_path = Path(dirpath) / f
                try:
                    rel_path = file_path.relative_to(root_base)
                except ValueError:
                    rel_path = file_path

                if f.endswith(".md"):
                    # Scan full Markdown documentation
                    try:
                        content = file_path.read_text(encoding="utf-8")
                    except Exception as e:
                        errors.append(f"Failed to read {rel_path}: {e}")
                        continue

                    for line_no, line in enumerate(content.splitlines(), 1):
                        hits = check_text_for_avoid_terms(line, avoid_terms)
                        for hit in hits:
                            errors.append(
                                f"Glossary violation in {rel_path}:{line_no}: Found prohibited term '{hit}'"
                            )

                elif f.endswith((".py", ".js", ".ts", ".vue")):
                    # Scan code comments and docstrings only
                    comment_lines = extract_comments_and_docstrings(file_path)
                    for line_no, line_text in comment_lines:
                        hits = check_text_for_avoid_terms(line_text, avoid_terms)
                        for hit in hits:
                            errors.append(
                                f"Glossary violation in code comment {rel_path}:{line_no}: Found prohibited term '{hit}'"
                            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify alignment against CONTEXT.md Avoid glossary."
    )
    parser.add_argument(
        "--context-file",
        default="CONTEXT.md",
        help="Path to CONTEXT.md (default: CONTEXT.md)",
    )
    args = parser.parse_args()

    errors = verify_glossary_alignment(args.context_file)
    if errors:
        print(f"FAILED: Found {len(errors)} glossary alignment violation(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        "SUCCESS: Zero Avoid terms detected across notes, documentation, and code comments."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
