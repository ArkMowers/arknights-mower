#!/usr/bin/env python3
"""
verify_glossary_alignment.py

Parses CONTEXT.md dynamically to extract prohibited terms ('Avoid' lists), then scans
agent notes, documentation, and source code comments/docstrings for violations.
The glossary supplies Avoid terms; its definitions, document placement, and edit
approval are outside this check's scope.
"""

import argparse
import ast
import hashlib
import io
import json
import os
import re
import subprocess
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
}

DEFAULT_SCAN_ROOTS = (
    ".agents/notes",
    ".agents/skills",
    "docs",
    "arknights_mower",
    "ui/src",
    "AGENTS.md",
    ".agents/AGENTS.md",
    "CODING_STANDARDS.md",
    "scripts/README.md",
)
PROSE_SUFFIXES = {".md", ".json", ".diff", ".txt", ".yaml", ".yml"}

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
    *,
    comparison_base: str | None = None,
    warnings: list[str] | None = None,
) -> list[str]:
    """Return Avoid-term scan errors; concept definitions require separate review."""
    context_path = Path(context_file).resolve()
    if not context_path.exists():
        return [f"CONTEXT.md not found at {context_path}"]

    avoid_terms = extract_avoid_terms(context_path)
    if not avoid_terms:
        return [f"No avoid terms extracted from {context_path}"]

    repository = context_path.parent
    roots = (
        scan_roots
        if scan_roots is not None
        else [repository / p for p in DEFAULT_SCAN_ROOTS]
    )
    preserved, errors = load_preserved_sources(repository)
    changed, scope_errors = added_line_scope(repository, comparison_base)
    errors.extend(scope_errors)
    development = development_terms(context_path)
    inherited = []
    seen = set()
    for scan_root in roots:
        root = Path(scan_root).resolve()
        paths = [root] if root.is_file() else walk_files(root)
        for path in paths:
            if path in seen or path.name in SELF_EXCLUDED_FILES:
                continue
            seen.add(path)
            if path.suffix.lower() not in PROSE_SUFFIXES | {
                ".py",
                ".js",
                ".ts",
                ".vue",
            }:
                continue
            try:
                relative = path.relative_to(repository).as_posix()
            except ValueError:
                relative = str(path)
            try:
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as error:
                errors.append(f"Failed to read {relative}: {error}")
                continue
            lines = (
                list(enumerate(content.splitlines(), 1))
                if path.suffix.lower() in PROSE_SUFFIXES
                else extract_comments_and_docstrings(path)
            )
            for number, line in lines:
                if number in preserved.get(relative, set()):
                    identifier = preserved[relative][number]
                    if identifier is None:
                        continue
                    line = line.replace(f"`{identifier}`", "")
                for term in check_text_for_avoid_terms(line, avoid_terms):
                    diagnostic = f"Glossary violation in {relative}:{number}: Found prohibited term '{term}'"
                    if (
                        term in development
                        and changed is not None
                        and number not in changed.get(relative, set())
                    ):
                        inherited.append(diagnostic)
                    else:
                        errors.append(diagnostic)
    if warnings is not None:
        warnings.extend(inherited)
    return errors


def walk_files(root: Path) -> list[Path]:
    """Include skill resources and hidden instruction directories without cache trees."""
    result = []
    for directory, names, files in os.walk(root):
        names[:] = [name for name in names if name not in IGNORED_DIRS]
        result.extend(Path(directory) / name for name in files)
    return result


def development_terms(context: Path) -> set[str]:
    """Only the approved development section has a newly-written-prose scope."""
    result = set()
    for path in (context, context.parent / "CONTEXT.zh.md"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        sections = re.split(r"(?m)^## ", text)
        for section in sections:
            if not section.startswith(
                ("3. Development & Documentation Language", "3. 开发与文档用语")
            ):
                continue
            for line in section.splitlines():
                match = AVOID_LINE_PATTERN.search(line)
                if match:
                    result.update(re.findall(r"`([^`]+)`", match.group(1)))
    return result


def added_line_scope(
    repository: Path, base: str | None
) -> tuple[dict[str, set[int]] | None, list[str]]:
    """Compare branch and working-tree prose from the shared comparison ancestor."""
    try:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        if top.returncode or Path(top.stdout.strip()).resolve() != repository:
            if base is not None:
                return None, ["Cannot determine prose scope: not a Git worktree root"]
            return None, []
        revision = base or "HEAD"
        resolved = subprocess.run(
            ["git", "rev-parse", "--verify", revision + "^{commit}"],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        if resolved.returncode:
            return None, [f"Cannot determine prose comparison commit: {revision}"]
        revision = resolved.stdout.strip()
        ancestor = subprocess.run(
            ["git", "merge-base", revision, "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=True,
        )
        revision = ancestor.stdout.strip()
        diff = subprocess.run(
            [
                "git",
                "-c",
                "core.quotePath=false",
                "diff",
                "--no-ext-diff",
                "--unified=0",
                revision,
                "--",
            ],
            cwd=repository,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        changed: dict[str, set[int]] = {}
        path = None
        for line in diff.stdout.splitlines():
            if line.startswith("+++ "):
                name = line[4:].rstrip("\t")
                if name.startswith('"'):
                    name = ast.literal_eval(name)
                path = name[2:] if name.startswith("b/") else None
            elif path is not None and line.startswith("@@"):
                match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
                if match:
                    start, count = int(match[1]), int(match[2] or 1)
                    changed.setdefault(path, set()).update(range(start, start + count))
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=repository,
            capture_output=True,
            timeout=15,
            check=True,
        )
        for name in untracked.stdout.decode("utf-8").split("\0"):
            path_object = repository / name
            if (
                name
                and path_object.is_file()
                and path_object.suffix.lower()
                in PROSE_SUFFIXES | {".py", ".js", ".ts", ".vue"}
            ):
                changed[name] = set(
                    range(
                        1, len(path_object.read_text(encoding="utf-8").splitlines()) + 1
                    )
                )
        return changed, []
    except (OSError, ValueError, SyntaxError, subprocess.SubprocessError) as error:
        return None, [f"Cannot determine prose comparison scope: {error}"]


def validate_source_span(
    record: dict, lines: list[str], repository: Path, label: str
) -> tuple[set[int], str | None]:
    """Validate one labelled source span without importing the cited code."""
    if record.get("kind") not in {
        "historical-quotation",
        "test-counterexample",
        "code-identifier",
    }:
        raise ValueError("source record needs a supported kind")
    source = record["source"]
    if not isinstance(source, str) or not re.fullmatch(
        r"https://github\.com/[^/]+/[^/]+/blob/[0-9a-f]{40}/[^\s]+", source
    ):
        raise ValueError("preserved source needs an immutable source-file URL")
    start, end = record["start_line"], record["end_line"]
    if (
        type(start) is not int
        or type(end) is not int
        or not 1 <= start <= end <= len(lines)
    ):
        raise ValueError("preserved source line range is invalid")
    content = "".join(lines[start - 1 : end])
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != record["sha256"]:
        raise ValueError(f"preserved source content changed: {label}")
    if not isinstance(record.get("label"), str) or not record["label"].strip():
        raise ValueError("preserved source needs a descriptive label")
    identifier = None
    if record["kind"] == "code-identifier":
        identifier = record.get("identifier")
        source_path = (repository / record["source_path"]).resolve()
        if (
            not isinstance(identifier, str)
            or not identifier.isidentifier()
            or not source_path.is_relative_to(repository)
        ):
            raise ValueError("code identifier needs an in-repository Python definition")
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        declarations = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        declarations.update(
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        )
        if identifier not in declarations:
            raise ValueError("code identifier is not declared in the source file")
        if f"`{identifier}`" not in content:
            raise ValueError("code identifier must be an exact inline-code reference")
    return set(range(start, end + 1)), identifier


def load_preserved_sources(
    repository: Path,
) -> tuple[dict[str, dict[int, str | None]], list[str]]:
    """Check explicit quotation/counterexample spans; surrounding prose stays scanned."""
    manifest = repository / "scripts/prose_sources.json"
    if not manifest.exists():
        return {}, []
    spans: dict[str, dict[int, str | None]] = {}
    try:
        records = json.loads(manifest.read_text(encoding="utf-8"))
        if not isinstance(records, list):
            raise ValueError("source records must be a list")
        for record in records:
            if not isinstance(record, dict) or record.get("kind") not in {
                "historical-quotation",
                "test-counterexample",
                "code-identifier",
            }:
                raise ValueError("source record needs a supported kind")
            name = record["path"]
            path = (repository / name).resolve()
            if not path.is_relative_to(repository) or Path(name).is_absolute():
                raise ValueError("preserved source path must stay in the repository")
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            numbers, identifier = validate_source_span(record, lines, repository, name)
            selected = spans.setdefault(path.relative_to(repository).as_posix(), {})
            if selected.keys() & numbers:
                raise ValueError("preserved source spans must not overlap")
            selected.update({number: identifier for number in numbers})
        return spans, []
    except (KeyError, TypeError, OSError, ValueError, SyntaxError) as error:
        return {}, [f"Invalid preserved prose source: {error}"]


def pr_source_spans(
    body: str, repository: Path
) -> tuple[dict[int, str | None], list[str]]:
    """Recognize bounded source markers in PR bodies using the file-source validator."""
    lines = body.replace("\r\n", "\n").replace("\r", "\n").splitlines(keepends=True)
    spans: dict[int, str | None] = {}
    start = None
    record = None
    try:
        for number, line in enumerate(lines, 1):
            marker = re.fullmatch(r"<!-- mower-prose-source (.+) -->", line.strip())
            if marker:
                if start is not None:
                    raise ValueError("source markers must not nest")
                record = json.loads(marker[1])
                if not isinstance(record, dict):
                    raise ValueError("source marker must contain a JSON object")
                start = number + 1
            elif line.strip() == "<!-- /mower-prose-source -->":
                if start is None or record is None:
                    raise ValueError("source marker has no opening")
                numbers, identifier = validate_source_span(
                    {**record, "start_line": start, "end_line": number - 1},
                    lines,
                    repository,
                    "PR body",
                )
                spans.update({index: identifier for index in numbers})
                start = None
                record = None
            elif line.strip().startswith(
                ("<!-- mower-prose-source", "<!-- /mower-prose-source")
            ):
                raise ValueError("malformed source marker")
        if start is not None:
            raise ValueError("source marker has no closing")
        return spans, []
    except (KeyError, TypeError, OSError, ValueError, SyntaxError) as error:
        return {}, [f"Invalid PR preserved source: {error}"]


def verify_pr_text(payload: object, context_file: str | Path) -> list[str]:
    """Scan complete title/body text; only validated, explicit body source spans differ."""
    if not isinstance(payload, dict) or not all(
        isinstance(payload.get(key), str) for key in ("title", "body")
    ):
        return ["PR text must be an object with string title and body"]
    context = Path(context_file).resolve()
    terms = extract_avoid_terms(context)
    preserved, errors = pr_source_spans(payload["body"], context.parent)
    if not terms:
        return ["No Avoid terms found for PR text checking"]
    for key in ("title", "body"):
        for number, line in enumerate(payload[key].splitlines(), 1):
            if key == "body" and number in preserved:
                identifier = preserved[number]
                if identifier is None:
                    continue
                line = line.replace(f"`{identifier}`", "")
            for term in check_text_for_avoid_terms(line, terms):
                errors.append(
                    f"Glossary violation in PR {key}:{number}: Found prohibited term '{term}'"
                )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan notes, docs and code comments for glossary Avoid terms."
    )
    parser.add_argument(
        "--context-file",
        default="CONTEXT.md",
        help="Path to CONTEXT.md (default: CONTEXT.md)",
    )
    parser.add_argument(
        "--base", help="Comparison commit for newly written development prose"
    )
    parser.add_argument(
        "--pr-json", help="Scan title/body JSON from a file, or - for stdin"
    )
    args = parser.parse_args()
    warnings: list[str] = []
    if args.pr_json:
        try:
            payload = json.loads(
                sys.stdin.read()
                if args.pr_json == "-"
                else Path(args.pr_json).read_text(encoding="utf-8-sig")
            )
            errors = verify_pr_text(payload, args.context_file)
        except (OSError, ValueError) as error:
            errors = [f"Cannot read PR text: {error}"]
    else:
        errors = verify_glossary_alignment(
            args.context_file, comparison_base=args.base, warnings=warnings
        )
    if warnings:
        print(
            f"UNCHANGED DEVELOPMENT PROSE: {len(warnings)} listed-term occurrence(s) predate the comparison; not labelled as quotations."
        )
    if errors:
        print(f"FAILED: Found {len(errors)} Avoid-term check error(s):")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        "SUCCESS: Checked formal text, preserved-source markers and listed terms in scope. Meaning and source relevance require review."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
