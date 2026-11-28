#!/usr/bin/env python3
"""
verify_agent_note_format.py

Mechanically verifies bilingual decisions and historical triplet metadata. With a
repository root, it checks historical identifiers and test-file references under
the compatibility policy. It does not execute tests or production modules.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

try:
    from governance_baseline import policy_comparison_base
except ImportError:
    from scripts.governance_baseline import policy_comparison_base

try:
    from verify_doc_links import (
        CODE_FENCE_PATTERN,
        INLINE_CODE_PATTERN,
        INLINE_LINK_PATTERN,
        REF_DEF_PATTERN,
    )
except ImportError:
    from scripts.verify_doc_links import (
        CODE_FENCE_PATTERN,
        INLINE_CODE_PATTERN,
        INLINE_LINK_PATTERN,
        REF_DEF_PATTERN,
    )

VALID_LIFECYCLES = {"proposed", "implemented", "archived", "rejected"}
VALID_CATEGORIES = {
    "feature",
    "bug-fix",
    "simplification",
    "architecture",
    "process",
    "testing",
}
DIRECTORY_GUIDES = {"AGENTS.md", "README.md", "README.zh.md"}

FILENAME_DATE_SLUG_PATTERN = re.compile(
    r"^(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)$"
)
INVARIANT_PATTERN = re.compile(r"^\[INV-(?:[A-Z]+-)?\d{2}\]$")
ISSUE_REF_PATTERN = re.compile(r"(?<![A-Za-z0-9_&#])#(\d{1,6})\b")
INVARIANT_DECLARATION_PATTERN = re.compile(
    r"^-\s+\*\*(\[INV-(?:[A-Z]+-)?\d{2}\])\s+[^*]+\*\*:"
)


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


def changed_note_paths(
    repo_root: Path, comparison_base: str | None = None
) -> set[str] | None:
    """Collect working-tree and requested committed changes; None means no baseline."""
    worktree = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_root,
        capture_output=True,
        timeout=10,
    )
    if worktree.returncode != 0 or (
        Path(
            worktree.stdout.decode("utf-8", errors="surrogateescape").strip()
        ).resolve()
        != repo_root
    ):
        if comparison_base is not None:
            raise ValueError("Comparison reference root is not a Git worktree root")
        return None
    paths = set()
    commands = [
        ("diff", "--name-only", "-z"),
        ("diff", "--cached", "--name-only", "-z"),
        ("ls-files", "--others", "--exclude-standard", "-z"),
    ]
    if comparison_base is not None:
        base = subprocess.run(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{comparison_base}^{{commit}}",
            ],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        if base.returncode != 0:
            raise ValueError(f"Invalid comparison base: {comparison_base}")
        commands.append(
            ("diff", "--name-only", "-z", base.stdout.decode().strip(), "HEAD")
        )
    for arguments in commands:
        result = subprocess.run(
            ["git", *arguments, "--", ".agents/notes"],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            if comparison_base is not None:
                raise ValueError("Cannot inspect notes against the comparison base")
            return None
        paths.update(
            path.decode("utf-8", errors="surrogateescape")
            for path in result.stdout.split(b"\0")
            if path
        )
    return paths


def invariant_declarations(content: str) -> set[str]:
    """Read historical declarations outside Markdown code fences."""
    declarations = set()
    fence = None
    for line in content.splitlines():
        stripped = line.lstrip()
        marker = re.match(r"(`{3,}|~{3,})", stripped)
        if marker:
            delimiter = marker.group(1)
            if fence is None:
                fence = delimiter
            elif delimiter[0] == fence[0] and len(delimiter) >= len(fence):
                fence = None
            continue
        if fence is None:
            match = INVARIANT_DECLARATION_PATTERN.match(line)
            if match:
                declarations.add(match.group(1))
    return declarations


def parse_legacy_ids(content: str, source: str | Path) -> set[str]:
    identifiers = json.loads(content)
    if not isinstance(identifiers, list) or any(
        not isinstance(identifier, str) or not INVARIANT_PATTERN.fullmatch(identifier)
        for identifier in identifiers
    ):
        raise ValueError(
            f"Frozen legacy identifiers must be a JSON list of invariant identifiers in {source}"
        )
    return set(identifiers)


def declared_invariants(registry: Path) -> set[str]:
    """Resolve legacy metadata from old declarations and the frozen identifier set."""
    declarations = invariant_declarations(registry.read_text(encoding="utf-8"))
    legacy_path = registry.parent / "scripts/legacy_invariant_ids.json"
    if legacy_path.exists():
        declarations.update(
            parse_legacy_ids(legacy_path.read_text(encoding="utf-8"), legacy_path)
        )
    return declarations


def historical_invariants(repo_root: Path, reference: str) -> set[str]:
    """Allow the initial frozen-set migration only from IDs present at the baseline."""
    commit = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{reference}^{{commit}}"],
        cwd=repo_root,
        capture_output=True,
        timeout=10,
    )
    if commit.returncode != 0:
        if reference == "HEAD":
            return set()
        raise ValueError(f"Invalid comparison base: {reference}")
    reference = commit.stdout.decode().strip()
    paths = ("CODING_STANDARDS.md", "scripts/legacy_invariant_ids.json")
    result = subprocess.run(
        ["git", "ls-tree", "--name-only", "-z", reference, "--", *paths],
        cwd=repo_root,
        capture_output=True,
        timeout=10,
    )
    if result.returncode != 0:
        raise ValueError(f"Cannot inspect historical identifiers at {reference}")
    identifiers = set()
    for path in result.stdout.split(b"\0"):
        if not path:
            continue
        relative = path.decode("utf-8", errors="surrogateescape")
        content = subprocess.run(
            ["git", "show", "--end-of-options", f"{reference}:{relative}"],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        if content.returncode != 0:
            raise ValueError(
                f"Cannot read historical identifiers from {reference}:{relative}"
            )
        text = content.stdout.decode("utf-8")
        identifiers.update(
            invariant_declarations(text)
            if relative == "CODING_STANDARDS.md"
            else parse_legacy_ids(text, f"{reference}:{relative}")
        )
    return identifiers


def legacy_note_keys(
    repo_root: Path, comparison_base: str | None, *, include_head: bool = True
) -> set[tuple[str, str]]:
    """Read historical identities across lifecycle moves; unborn Git has none."""
    keys = set()
    references = [comparison_base or "HEAD"]
    if include_head and comparison_base is not None:
        references.append("HEAD")
    for reference in references:
        commit = subprocess.run(
            [
                "git",
                "rev-parse",
                "--verify",
                "--end-of-options",
                f"{reference}^{{commit}}",
            ],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        if commit.returncode != 0:
            # An initialized fixture or checkout can have no first commit yet.
            if reference == "HEAD":
                continue
            raise ValueError(f"Invalid comparison base: {reference}")
        result = subprocess.run(
            [
                "git",
                "ls-tree",
                "-r",
                "--name-only",
                "-z",
                commit.stdout.decode().strip(),
                "--",
                ".agents/notes",
            ],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            raise ValueError(f"Cannot inspect legacy note format at {reference}")
        for path in result.stdout.split(b"\0"):
            note_path = Path(path.decode("utf-8", errors="surrogateescape"))
            if note_path.name.endswith(".sidecar.json"):
                keys.add((note_path.parent.name, note_path.name[:-13]))
    return keys


def verify_decision_source_links(path: Path, repository: Path) -> list[str]:
    """Validate local source links in a new decision without importing targets."""
    errors = []
    fence = None
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        marker = CODE_FENCE_PATTERN.match(line)
        if marker:
            delimiter = marker.group(1)
            if fence is None:
                fence = delimiter
            elif delimiter[0] == fence[0] and len(delimiter) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        clean = INLINE_CODE_PATTERN.sub("", line)
        targets = [
            match.group(2) or match.group(3)
            for match in INLINE_LINK_PATTERN.finditer(clean)
        ]
        definition = REF_DEF_PATTERN.match(clean)
        if definition:
            targets.append(definition.group(2) or definition.group(3))
        for target in targets:
            normalized = unquote(target.split("#", 1)[0]).replace("\\", "/")
            if not normalized.endswith((".py", ".js", ".ts", ".vue")):
                continue
            scheme = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", normalized)
            drive = re.match(r"^[A-Za-z]:", normalized)
            if scheme and scheme.group(0).lower() != "file:" and not drive:
                continue
            if scheme or normalized.startswith("/"):
                errors.append(
                    f"Invalid source link '{target}' in {path}:{line_number}: local source links must be relative"
                )
                continue
            source = (path.parent / normalized).resolve()
            if not source.is_relative_to(repository) or not source.is_file():
                errors.append(
                    f"Missing or outside-repository source link '{target}' in {path}:{line_number}"
                )
    return errors


def verify_decision_body(content: str, lifecycle: str, language: str) -> list[str]:
    """Check lifecycle sections; rationale and evidence still require review."""
    lines = content.splitlines()
    if lines and lines[0].strip() == "---":
        for index, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                lines = lines[index + 1 :]
                break
    visible = []
    fence = None
    in_comment = False
    for line in lines:
        if fence is None:
            if not in_comment and line.startswith(("    ", "\t")):
                visible.append(line)
                continue
            fragments = []
            while line:
                if in_comment:
                    end = line.find("-->")
                    if end == -1:
                        break
                    line = line[end + 3 :]
                    in_comment = False
                else:
                    comment = re.search(r"(?<!\\)(?:\\\\)*<!--", line)
                    start = comment.end() - 4 if comment else -1
                    inline = (
                        None
                        if CODE_FENCE_PATTERN.match(line)
                        else INLINE_CODE_PATTERN.search(line)
                    )
                    if inline and (start == -1 or inline.start() < start):
                        fragments.append(line[: inline.start()] + "code")
                        line = line[inline.end() :]
                        continue
                    if comment is None:
                        fragments.append(line)
                        break
                    fragments.append(line[:start])
                    line = line[start + 4 :]
                    in_comment = True
            line = "".join(fragments)
        marker = CODE_FENCE_PATTERN.match(line)
        if marker:
            delimiter = marker.group(1)
            if fence is None:
                fence = delimiter
            elif (
                delimiter[0] == fence[0]
                and len(delimiter) >= len(fence)
                and not line[marker.end() :].strip()
            ):
                fence = None
            visible.append("")
            continue
        # Code can supply evidence, but its example headings are not sections.
        visible.append("    " + line if fence is not None else line)
    text = "\n".join(visible)
    headings = list(re.finditer(r"^##[ \t]+(.+?)[ \t]*#*[ \t]*$", text, re.MULTILINE))
    names = [heading.group(1).strip() for heading in headings]
    chinese = language == "zh"
    problem = "问题" if chinese else "Problem"
    proposal = "提案" if chinese else "Proposal"
    decision = "决策" if chinese else "Decision"
    alternatives = "考虑过的替代方案" if chinese else "Alternatives considered"
    acceptance = "验收条件" if chinese else "Acceptance criteria"
    risks = "风险" if chinese else "Risks"
    consequences = "后果" if chinese else "Consequences"
    rejection = "拒绝理由" if chinese else "Rejection"
    required = [problem, alternatives]
    if lifecycle == "proposed":
        required += [proposal, acceptance, risks]
    elif lifecycle == "rejected":
        required += [proposal, rejection]
    else:
        required += [decision, consequences]
    errors = []
    if not names or names[0] != problem:
        errors.append(f"Decision body opens with '## {problem}'")
    for name in required:
        matches = [index for index, actual in enumerate(names) if actual == name]
        if len(matches) != 1:
            errors.append(f"Decision body requires one '## {name}' section")
            continue
        index = matches[0]
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        if not text[headings[index].end() : end].strip():
            errors.append(f"Decision section '## {name}' requires recorded content")
    if lifecycle in {"implemented", "archived"}:
        forbidden = {
            "Proposal",
            "Plan",
            "Migration plan",
            "Acceptance criteria",
            "提案",
            "计划",
            "迁移计划",
            "验收条件",
        }
        for name in names:
            if name in forbidden:
                errors.append(
                    f"'{lifecycle}' decision retains proposal section '## {name}'"
                )
    return errors


def verify_agent_notes(
    notes_dir: str | Path = ".agents/notes",
    *,
    repo_root: str | Path | None = None,
    warnings: list[str] | None = None,
    all_active: bool = False,
    comparison_base: str | None = None,
) -> list[str]:
    """Validate structure; an explicit repository root also enables reference checks."""
    errors = []
    notes_path = Path(notes_dir).resolve()

    if not notes_path.exists():
        return [f"Notes directory not found: {notes_path}"]

    repository = Path(repo_root).resolve() if repo_root is not None else None
    if repository is not None and not notes_path.is_relative_to(repository):
        return [
            f"Notes directory is outside the repository reference root: {notes_path}"
        ]
    compatibility_warnings = warnings if warnings is not None else []
    changed = None
    declarations = set()
    legacy_keys = set()
    baseline_legacy_keys = None
    if repository is not None:
        try:
            changed = changed_note_paths(repository, comparison_base)
            declarations = declared_invariants(repository / "CODING_STANDARDS.md")
            if changed is not None:
                legacy_base = policy_comparison_base(
                    repository, comparison_base, "legacy_format"
                )
                legacy_keys = legacy_note_keys(repository, legacy_base) or set()
                baseline_legacy_keys = legacy_note_keys(
                    repository, legacy_base, include_head=False
                )
                if baseline_legacy_keys is not None:
                    historical_ids = historical_invariants(
                        repository, legacy_base or "HEAD"
                    )
                    for identifier in sorted(declarations - historical_ids):
                        errors.append(
                            f"New legacy identifier '{identifier}'; new rules use behavior names and contract links"
                        )
                    for identifier in sorted(historical_ids - declarations):
                        errors.append(
                            f"Missing frozen legacy identifier '{identifier}'; retain historical identifiers for existing metadata"
                        )
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            return [f"Cannot establish note-reference baseline: {exc}"]

    # Collect all decision files by (lifecycle, category, slug_base).
    triplets: dict[tuple[str, str, str], dict[str, Path]] = {}

    for root, dirs, files in os.walk(notes_path):
        rel_root = Path(root).relative_to(notes_path)
        parts = rel_root.parts

        if not parts:
            # Directory guides are navigation/policy, not dated decisions.
            for f in files:
                if f not in DIRECTORY_GUIDES and not f.startswith("."):
                    errors.append(f"Unexpected file at root of notes directory: {f}")
            continue

        lifecycle = parts[0]
        if lifecycle not in VALID_LIFECYCLES:
            errors.append(f"Invalid lifecycle directory '{lifecycle}' in {rel_root}")
            continue

        if len(parts) == 1:
            for f in files:
                if f not in DIRECTORY_GUIDES and f != ".gitkeep":
                    errors.append(
                        f"Unexpected file directly under lifecycle directory: {rel_root}/{f}"
                    )
            continue

        category = parts[1]
        if category not in VALID_CATEGORIES:
            errors.append(f"Invalid category directory '{category}' in {rel_root}")
            continue

        if len(parts) > 2:
            errors.append(f"Unexpected nested note directory: {rel_root}")
            dirs.clear()
            continue

        for f in files:
            if f in DIRECTORY_GUIDES or f == ".gitkeep":
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

    # Verify shared frontmatter, format-specific completeness and legacy metadata.
    for (lifecycle, category, stem), roles in triplets.items():
        expected_date = stem[:10]
        formats = {}
        # 1. Markdown frontmatter validation applies to both formats.
        for md_role in ("en", "zh"):
            if md_role in roles:
                path = roles[md_role]
                content = path.read_text(encoding="utf-8")
                fm = parse_yaml_frontmatter(content)
                if fm is None:
                    errors.append(f"Missing or malformed YAML frontmatter in {path}")
                    continue

                formats[md_role] = fm.get("format")
                if "format" in fm and fm["format"] != "decision":
                    errors.append(f"Unsupported note format '{fm['format']}' in {path}")

                if fm.get("format") == "decision":
                    errors.extend(
                        f"{error} in {path}"
                        for error in verify_decision_body(content, lifecycle, md_role)
                    )

                for req_key in ("title", "status", "category", "date"):
                    if req_key not in fm:
                        errors.append(
                            f"Frontmatter in {path} missing required key '{req_key}'"
                        )
                    elif not fm[req_key].strip():
                        errors.append(
                            f"Frontmatter '{req_key}' must be nonempty in {path}"
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

        # 2. Only an explicitly marked new decision can omit the sidecar.
        decision_format = "decision" in formats.values()
        if decision_format and any(value != "decision" for value in formats.values()):
            errors.append(
                f"Bilingual note format must agree for '{stem}' in {lifecycle}/{category}"
            )
        legacy_triplet = "sidecar" in roles or (category, stem) in legacy_keys
        if (
            legacy_triplet
            and baseline_legacy_keys is not None
            and (category, stem) not in baseline_legacy_keys
        ):
            errors.append(
                f"New legacy triplet '{stem}' in {lifecycle}/{category}; new records require format: decision and a bilingual Markdown pair"
            )
        if decision_format and legacy_triplet:
            errors.append(
                f"Cannot change legacy triplet '{stem}' to format: decision; preserve its sidecar and historical format"
            )
        required_roles = (
            ("en", "zh")
            if decision_format and not legacy_triplet
            else ("en", "zh", "sidecar")
        )
        structure = "decision" if decision_format and not legacy_triplet else "triplet"
        for req_role in required_roles:
            if req_role not in roles:
                errors.append(
                    f"Incomplete {structure} for '{stem}' in {lifecycle}/{category}: missing '{req_role}' file"
                )

        if decision_format and not legacy_triplet and repository is not None:
            relative_dir = next(iter(roles.values())).parent.relative_to(repository)
            relative_stem = (relative_dir / stem).as_posix()
            strict = lifecycle in {"proposed", "implemented"} and (
                all_active
                or changed is None
                or any(path.startswith(relative_stem + ".") for path in changed)
            )
            reference_errors = errors if strict else compatibility_warnings
            for role in ("en", "zh"):
                if role in roles:
                    reference_errors.extend(
                        verify_decision_source_links(roles[role], repository)
                    )

        # 3. Sidecar JSON validation
        if "sidecar" in roles:
            sidecar_path = roles["sidecar"]
            try:
                data = json.loads(sidecar_path.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(f"Malformed JSON in {sidecar_path}: {e}")
                continue

            if not isinstance(data, dict):
                errors.append(f"Sidecar must be a JSON object in {sidecar_path}")
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
                    if not isinstance(inv, str) or not INVARIANT_PATTERN.fullmatch(inv):
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
                elif any(not isinstance(item, str) or not item.strip() for item in val):
                    errors.append(
                        f"Sidecar '{list_key}' entries must be nonempty strings in {sidecar_path}"
                    )

            if repository is not None:
                relative_stem = sidecar_path.relative_to(repository).as_posix()[:-13]
                strict = lifecycle in {"proposed", "implemented"} and (
                    all_active
                    or changed is None
                    or any(path.startswith(relative_stem + ".") for path in changed)
                )
                reference_errors = errors if strict else compatibility_warnings
                if isinstance(invariants, list):
                    for invariant in invariants:
                        if isinstance(invariant, str) and invariant not in declarations:
                            reference_errors.append(
                                f"Undeclared invariant '{invariant}' in {sidecar_path}"
                            )
                suites = data.get("test_suites")
                if isinstance(suites, list):
                    for suite in suites:
                        if not isinstance(suite, str) or not suite.strip():
                            continue
                        normalized = suite.replace("\\", "/")
                        target = (repository / normalized).resolve()
                        if (
                            re.match(r"^[A-Za-z]:", normalized)
                            or Path(normalized).is_absolute()
                            or not target.is_relative_to(repository)
                            or not target.is_file()
                        ):
                            reference_errors.append(
                                f"Missing or outside-repository test suite '{suite}' in {sidecar_path}"
                            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify bilingual decision notes and historical triplet integrity."
    )
    parser.add_argument(
        "--notes-dir",
        default=".agents/notes",
        help="Path to .agents/notes directory (default: .agents/notes)",
    )
    parser.add_argument("--repo-root", default=".", help="Repository reference root")
    parser.add_argument(
        "--base", help="Also check active notes changed from this commit/ref to HEAD"
    )
    parser.add_argument(
        "--all-active", action="store_true", help="Strictly audit all active references"
    )
    args = parser.parse_args()

    warnings = []
    errors = verify_agent_notes(
        args.notes_dir,
        repo_root=args.repo_root,
        warnings=warnings,
        all_active=args.all_active,
        comparison_base=args.base,
    )
    for warning in warnings:
        print(f"COMPATIBILITY WARNING: {warning}")
    if errors:
        print(f"FAILED: Found {len(errors)} error(s) in agent notes:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print(
        "SUCCESS: Note structures and required active references pass; "
        "behavior, record ownership and implementation status require separate review."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
