import hashlib
import importlib.util
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from scripts.verify_agent_note_format import verify_agent_notes
from scripts.verify_doc_links import verify_doc_links
from scripts.verify_glossary_alignment import verify_glossary_alignment
from scripts.verify_governance import run_all_checks

# Load archive_note module dynamically due to hyphenated path
ARCHIVE_NOTE_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / ".agents"
    / "skills"
    / "mower-archive-agent-notes"
    / "scripts"
    / "archive_note.py"
)
spec = importlib.util.spec_from_file_location("archive_note", ARCHIVE_NOTE_PATH)
archive_note = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive_note)


class VerifyGovernanceTests(unittest.TestCase):
    def make_reference_repo(self, directory, lifecycle="implemented", slug=None):
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        (root / "CODING_STANDARDS.md").write_text(
            "- **[INV-REC-07] Field Integrity**: Unread fields remain absent.\n",
            encoding="utf-8",
        )
        (root / "CONTEXT.md").write_text(
            "### Field\n- **Definition**: A report field.\n"
            "- **_Avoid_**: `ForbiddenTerm`\n",
            encoding="utf-8",
        )
        suite = root / "arknights_mower/tests/field_tests.py"
        suite.parent.mkdir(parents=True, exist_ok=True)
        suite.write_text(
            "raise RuntimeError('must not import this suite')\n", encoding="utf-8"
        )
        note_dir = root / ".agents/notes" / lifecycle / "bug-fix"
        note_dir.mkdir(parents=True, exist_ok=True)
        slug = slug or "2026-10-08-reference-check"
        for suffix in (".md", ".zh.md"):
            (note_dir / f"{slug}{suffix}").write_text(
                f"---\ntitle: Field Integrity\nstatus: {lifecycle}\ncategory: bug-fix\n"
                f"date: {slug[:10]}\n---\n\nCurrent contract.\n",
                encoding="utf-8",
            )
        metadata = {
            "title": "Field Integrity",
            "status": lifecycle,
            "category": "bug-fix",
            "date": slug[:10],
            "authors": ["Tester"],
            "invariants": ["[INV-REC-07]"],
            "code_symbols": ["production.symbol"],
            "test_suites": ["arknights_mower/tests/field_tests.py"],
        }
        sidecar = note_dir / f"{slug}.sidecar.json"
        sidecar.write_text(json.dumps(metadata), encoding="utf-8")
        return root, sidecar, metadata

    def run_reference_gate(self, root):
        output = io.StringIO()
        with redirect_stdout(output):
            result = run_all_checks(root)
        return result, output.getvalue()

    def commit_reference_fixture(self, root, message):
        for arguments in (
            ["add", "."],
            [
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "-c",
                "core.hooksPath=",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-qm",
                message,
            ],
        ):
            subprocess.run(
                ["git", *arguments],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )

    def make_decision_note(
        self, root, slug="2026-10-11-named-decision", *, lifecycle="proposed"
    ):
        directory = Path(root) / ".agents/notes" / lifecycle / "architecture"
        directory.mkdir(parents=True, exist_ok=True)
        paths = []
        for suffix in (".md", ".zh.md"):
            path = directory / f"{slug}{suffix}"
            path.write_text(
                f"---\nformat: decision\ntitle: Named Decision\nstatus: {lifecycle}\n"
                f"category: architecture\ndate: {slug[:10]}\n---\n\n"
                + self.decision_body(lifecycle, chinese=suffix == ".zh.md"),
                encoding="utf-8",
            )
            paths.append(path)
        return paths

    def decision_body(self, lifecycle, *, chinese=False):
        if chinese:
            sections = [
                ("问题", "重复提交会产生重复记录。"),
                (
                    "决策" if lifecycle in {"implemented", "archived"} else "提案",
                    "记录与确认凭据在同一事务中保存。",
                ),
                ("考虑过的替代方案", "保留 CSV 追加无法确认重试结果。"),
            ]
            if lifecycle == "proposed":
                sections += [
                    ("验收条件", "重复相同输入保留一行，并返回相同凭据。"),
                    ("风险", "既有读取方需要兼容迁移。"),
                ]
            elif lifecycle == "rejected":
                sections.append(("拒绝理由", "尚无跨进程写入方，暂时保留当前实现。"))
            else:
                sections.append(("后果", "接受维护凭据的成本，重试结果可确认。"))
        else:
            sections = [
                ("Problem", "Repeated submissions can create duplicate rows."),
                (
                    "Decision"
                    if lifecycle in {"implemented", "archived"}
                    else "Proposal",
                    "Store the row and its receipt in one transaction.",
                ),
                ("Alternatives considered", "CSV append cannot confirm retry results."),
            ]
            if lifecycle == "proposed":
                sections += [
                    (
                        "Acceptance criteria",
                        "Repeating input retains one row and receipt.",
                    ),
                    ("Risks", "Existing readers need a compatibility migration."),
                ]
            elif lifecycle == "rejected":
                sections.append(
                    ("Rejection", "No cross-process writer justifies this cost.")
                )
            else:
                sections.append(
                    ("Consequences", "Receipt maintenance enables confirmed retries.")
                )
        return (
            "# Named Decision\n\n"
            + "\n\n".join(f"## {heading}\n\n{body}" for heading, body in sections)
            + "\n"
        )

    def test_directory_guides_are_not_classified_as_decision_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            notes = root / ".agents/notes"
            for directory in (
                notes,
                notes / "implemented",
                notes / "implemented/bug-fix",
            ):
                for name in ("README.md", "README.zh.md", "AGENTS.md"):
                    (directory / name).write_text(
                        "# Directory responsibilities\n", encoding="utf-8"
                    )
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)
            (notes / "implemented/guide.md").write_text(
                "Unknown entry\n", encoding="utf-8"
            )
            self.assertTrue(verify_agent_notes(notes))

    def test_new_decision_requires_lifecycle_sections_in_both_languages(self):
        for lifecycle in ("proposed", "implemented", "archived", "rejected"):
            with (
                self.subTest(lifecycle=lifecycle),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                paths = self.make_decision_note(tmpdir, lifecycle=lifecycle)
                self.assertEqual(verify_agent_notes(Path(tmpdir) / ".agents/notes"), [])
                paths[1].write_text(
                    paths[1]
                    .read_text(encoding="utf-8")
                    .replace("## 考虑过的替代方案", "## 其他说明"),
                    encoding="utf-8",
                )
                errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
                self.assertTrue(
                    any("考虑过的替代方案" in error for error in errors), errors
                )

    def test_directory_guides_do_not_allow_an_extra_note_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self.make_decision_note(tmpdir, lifecycle="implemented")
            unexpected = paths[0].parent / "unrecognized"
            unexpected.mkdir()
            (unexpected / "README.md").write_text("# Guide\n", encoding="utf-8")
            errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
            self.assertTrue(any("directory" in error for error in errors), errors)

    def test_frontmatter_sections_do_not_satisfy_an_empty_decision_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self.make_decision_note(tmpdir)
            fields = paths[0].read_text(encoding="utf-8").split("---", 2)[1]
            paths[0].write_text(
                "---" + fields + self.decision_body("proposed") + "---\n",
                encoding="utf-8",
            )
            errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
            self.assertTrue(any("Problem" in error for error in errors), errors)

    def test_comment_and_code_fence_markers_do_not_hide_real_sections(self):
        for example in (
            "<!--\n```markdown\n## Problem\nSample only\n-->\n",
            "```html\n<!-- literal comment\n```\n",
            "The literal Markdown marker is `<!--`.\n",
            "The escaped Markdown marker is \\<!--.\n",
            "    <!-- indented code\n",
            "<!-- A code span cannot hide the comment end ` -->`\n",
        ):
            with self.subTest(example=example), tempfile.TemporaryDirectory() as tmpdir:
                paths = self.make_decision_note(tmpdir)
                header, fields, body = (
                    paths[0].read_text(encoding="utf-8").split("---", 2)
                )
                paths[0].write_text(
                    "---".join((header, fields, "\n" + example + body)),
                    encoding="utf-8",
                )
                self.assertEqual(verify_agent_notes(Path(tmpdir) / ".agents/notes"), [])

    def test_section_examples_in_code_fences_do_not_satisfy_decision_body(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self.make_decision_note(tmpdir)
            content = paths[0].read_text(encoding="utf-8")
            frontmatter = content.split("---", 2)[:2]
            paths[0].write_text(
                "---".join(frontmatter)
                + "---\n\n```markdown\n"
                + self.decision_body("proposed")
                + "```\n",
                encoding="utf-8",
            )
            errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
            self.assertTrue(any("Problem" in error for error in errors), errors)

    def test_status_change_alone_does_not_complete_a_proposal(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self.make_decision_note(tmpdir)
            archive_note.transition_triplet(paths[0], "implemented")
            errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
            self.assertTrue(any("Proposal" in error for error in errors), errors)
            for path in (Path(tmpdir) / ".agents/notes/implemented/architecture").glob(
                "*.md"
            ):
                content = path.read_text(encoding="utf-8").split("---", 2)
                path.write_text(
                    "---".join(content[:2])
                    + "---\n\n"
                    + self.decision_body(
                        "implemented", chinese=path.name.endswith(".zh.md")
                    ),
                    encoding="utf-8",
                )
            self.assertEqual(verify_agent_notes(Path(tmpdir) / ".agents/notes"), [])

    def test_empty_required_sections_do_not_establish_a_decision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            paths = self.make_decision_note(tmpdir)
            paths[0].write_text(
                paths[0]
                .read_text(encoding="utf-8")
                .replace(
                    "CSV append cannot confirm retry results.", "<!-- Not recorded -->"
                ),
                encoding="utf-8",
            )
            errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
            self.assertTrue(
                any("Alternatives considered" in error for error in errors), errors
            )

    def test_bilingual_decision_without_sidecar_passes_actual_governance_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            self.make_decision_note(root)
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)

    def test_decision_requires_both_languages_and_matching_format(self):
        for mutation, diagnostic in (
            ("missing_chinese", "missing 'zh' file"),
            ("missing_format", "format"),
            ("unknown_format", "format"),
        ):
            with (
                self.subTest(mutation=mutation),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                paths = self.make_decision_note(tmpdir)
                if mutation == "missing_chinese":
                    paths[1].unlink()
                else:
                    replacement = (
                        "" if mutation == "missing_format" else "format: other\n"
                    )
                    paths[1].write_text(
                        paths[1]
                        .read_text(encoding="utf-8")
                        .replace("format: decision\n", replacement),
                        encoding="utf-8",
                    )
                errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
                self.assertTrue(any(diagnostic in error for error in errors), errors)

    def test_decision_still_validates_required_frontmatter_and_path(self):
        for old, new, diagnostic in (
            ("title: Named Decision\n", "", "missing required key 'title'"),
            ("title: Named Decision", "title:", "must be nonempty"),
            ("status: proposed", "status: implemented", "lifecycle directory"),
            ("category: architecture", "category: feature", "category directory"),
            ("date: 2026-10-11", "date: 2026-10-10", "filename date"),
        ):
            with self.subTest(old=old), tempfile.TemporaryDirectory() as tmpdir:
                english, _ = self.make_decision_note(tmpdir)
                english.write_text(
                    english.read_text(encoding="utf-8").replace(old, new),
                    encoding="utf-8",
                )
                errors = verify_agent_notes(Path(tmpdir) / ".agents/notes")
                self.assertTrue(any(diagnostic in error for error in errors), errors)

    def test_decision_source_links_validate_actual_files_without_importing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            english, _ = self.make_decision_note(root)
            source = root / "production.py"
            source.write_text(
                "raise RuntimeError('must not import')\n", encoding="utf-8"
            )
            english.write_text(
                english.read_text(encoding="utf-8")
                + "[Production](../../../../production.py)\n"
                + "[Regression][regression]\n"
                + "[regression]: ../../../../arknights_mower/tests/field_tests.py\n"
                + "[External](https://example.invalid/planned.py)\n"
                + "`[Example](missing.py)`\n```markdown\n[Example](missing.py)\n```\n",
                encoding="utf-8",
            )
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)
            source.unlink()
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 1, output)
            self.assertIn("Missing or outside-repository source link", output)
            self.assertIn("production.py", output)

    def test_decision_missing_and_outside_source_links_fail(self):
        for target in (
            "../../../../arknights_mower/tests/missing_tests.py",
            "../../../../../outside.py",
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmpdir:
                root, _, _ = self.make_reference_repo(tmpdir)
                english, _ = self.make_decision_note(root)
                english.write_text(
                    english.read_text(encoding="utf-8") + f"[Verification]({target})\n",
                    encoding="utf-8",
                )
                result, output = self.run_reference_gate(root)
                self.assertEqual(result, 1, output)
                self.assertIn("Missing or outside-repository source link", output)

    def test_decision_rejects_absolute_local_source_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            english, _ = self.make_decision_note(root)
            original = english.read_text(encoding="utf-8")
            source = root / "production.py"
            source.write_text(
                "raise RuntimeError('must not import')\n", encoding="utf-8"
            )
            for target in (
                source.as_uri(),
                source.with_name("missing.py").as_uri(),
                source.as_posix(),
                "/production.py",
            ):
                with self.subTest(target=target):
                    english.write_text(
                        original + f"[Verification]({target})\n", encoding="utf-8"
                    )
                    result, output = self.run_reference_gate(root)
                    self.assertEqual(result, 1, output)
                    self.assertIn("local source links must be relative", output)

    def test_decision_marker_cannot_hide_present_legacy_sidecar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, _ = self.make_reference_repo(tmpdir)
            for suffix in (".md", ".zh.md"):
                path = sidecar.with_name(sidecar.name[:-13] + suffix)
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "---\n", "---\nformat: decision\n", 1
                    ),
                    encoding="utf-8",
                )
            sidecar.write_text("[]", encoding="utf-8")
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 1, output)
            self.assertIn("JSON object", output)
            self.assertIn("legacy triplet", output)

    def test_deleted_legacy_sidecar_cannot_be_downgraded_in_git_worktree_or_branch(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "legacy fixture")
            base = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                )
                .decode()
                .strip()
            )
            for suffix in (".md", ".zh.md"):
                path = sidecar.with_name(sidecar.name[:-13] + suffix)
                path.write_text(
                    path.read_text(encoding="utf-8").replace(
                        "---\n", "---\nformat: decision\n", 1
                    ),
                    encoding="utf-8",
                )
            sidecar.unlink()
            errors = verify_agent_notes(root / ".agents/notes", repo_root=root)
            self.assertTrue(any("legacy triplet" in error for error in errors), errors)
            self.commit_reference_fixture(root, "attempted format conversion")
            errors = verify_agent_notes(
                root / ".agents/notes", repo_root=root, comparison_base=base
            )
            self.assertTrue(any("legacy triplet" in error for error in errors), errors)

    def test_same_slug_in_another_category_can_be_a_new_decision(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "legacy category fixture")
            self.make_decision_note(root, slug=sidecar.name[:-13])
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)

    def test_legacy_same_category_cannot_downgrade_after_lifecycle_move(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "legacy lifecycle fixture")
            destination = root / ".agents/notes/proposed/bug-fix"
            destination.mkdir(parents=True)
            for suffix in (".md", ".zh.md"):
                path = sidecar.with_name(sidecar.name[:-13] + suffix)
                content = (
                    path.read_text(encoding="utf-8")
                    .replace("---\n", "---\nformat: decision\n", 1)
                    .replace("status: implemented", "status: proposed")
                )
                (destination / path.name).write_text(content, encoding="utf-8")
                path.unlink()
            sidecar.unlink()
            errors = verify_agent_notes(root / ".agents/notes", repo_root=root)
            self.assertTrue(any("legacy triplet" in error for error in errors), errors)

    def test_frozen_legacy_identifiers_keep_sidecar_references_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, metadata = self.make_reference_repo(tmpdir)
            (root / "CODING_STANDARDS.md").write_text(
                "## Core Isolation\nExplicit selections remain persisted.\n",
                encoding="utf-8",
            )
            metadata["invariants"] = ["[INV-01]", "[INV-REC-07]"]
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            frozen = root / "scripts/legacy_invariant_ids.json"
            frozen.parent.mkdir()
            frozen.write_text(
                json.dumps(["[INV-01]", "[INV-REC-07]"]), encoding="utf-8"
            )
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)

    def run_note_cli(self, root, comparison_base=None):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/verify_agent_note_format.py"
        )
        arguments = [
            sys.executable,
            "-X",
            "utf8",
            str(script),
            "--repo-root",
            str(root),
            "--notes-dir",
            str(root / ".agents/notes"),
        ]
        if comparison_base is not None:
            arguments += ["--base", comparison_base]
        return subprocess.run(
            arguments,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    def test_new_legacy_triplets_fail_at_note_cli(self):
        for lifecycle in ("implemented", "archived"):
            for mode in ("untracked", "staged", "committed"):
                with (
                    self.subTest(lifecycle=lifecycle, mode=mode),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    root, _, _ = self.make_reference_repo(tmpdir)
                    subprocess.run(
                        ["git", "init", "-q"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                        timeout=15,
                    )
                    self.commit_reference_fixture(root, "historical fixture")
                    base = (
                        subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                        )
                        .decode()
                        .strip()
                    )
                    self.make_reference_repo(
                        root, lifecycle, slug="2026-10-11-new-legacy"
                    )
                    if mode == "staged":
                        subprocess.run(
                            ["git", "add", "."],
                            cwd=root,
                            check=True,
                            capture_output=True,
                            timeout=15,
                        )
                    elif mode == "committed":
                        self.commit_reference_fixture(root, "new legacy fixture")
                    result = self.run_note_cli(
                        root, base if mode == "committed" else None
                    )
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn("New legacy triplet", result.stdout)

    def test_frozen_identifiers_migrate_history_and_reject_new_ids_at_note_cli(self):
        for frozen_exists in (False, True):
            for committed in (False, True):
                with (
                    self.subTest(frozen_exists=frozen_exists, committed=committed),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    root, sidecar, metadata = self.make_reference_repo(tmpdir)
                    frozen = root / "scripts/legacy_invariant_ids.json"
                    frozen.parent.mkdir()
                    if frozen_exists:
                        frozen.write_text(
                            json.dumps(["[INV-REC-07]"]), encoding="utf-8"
                        )
                    subprocess.run(
                        ["git", "init", "-q"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                        timeout=15,
                    )
                    self.commit_reference_fixture(root, "historical identifiers")
                    base = (
                        subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                        )
                        .decode()
                        .strip()
                    )
                    (root / "CODING_STANDARDS.md").write_text(
                        "## Core Isolation\nExplicit selections remain persisted.\n",
                        encoding="utf-8",
                    )
                    frozen.write_text(json.dumps(["[INV-REC-07]"]), encoding="utf-8")
                    migrated = self.run_note_cli(root)
                    self.assertEqual(
                        migrated.returncode, 0, migrated.stdout + migrated.stderr
                    )
                    frozen.write_text(
                        json.dumps(["[INV-REC-07]", "[INV-NEW-99]"]), encoding="utf-8"
                    )
                    metadata["invariants"] = ["[INV-NEW-99]"]
                    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
                    if committed:
                        self.commit_reference_fixture(root, "added identifier")
                    result = self.run_note_cli(root, base if committed else None)
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn("New legacy identifier '[INV-NEW-99]'", result.stdout)

    def test_frozen_identifiers_cannot_be_removed_at_note_cli(self):
        for committed in (False, True):
            for remove_file in (False, True):
                with (
                    self.subTest(committed=committed, remove_file=remove_file),
                    tempfile.TemporaryDirectory() as tmpdir,
                ):
                    root, _, _ = self.make_reference_repo(tmpdir, "archived")
                    (root / "CODING_STANDARDS.md").write_text(
                        "## Core Isolation\nExplicit selections remain persisted.\n",
                        encoding="utf-8",
                    )
                    frozen = root / "scripts/legacy_invariant_ids.json"
                    frozen.parent.mkdir()
                    frozen.write_text(json.dumps(["[INV-REC-07]"]), encoding="utf-8")
                    subprocess.run(
                        ["git", "init", "-q"],
                        cwd=root,
                        check=True,
                        capture_output=True,
                        timeout=15,
                    )
                    self.commit_reference_fixture(
                        root, "archived historical identifiers"
                    )
                    base = (
                        subprocess.check_output(
                            ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                        )
                        .decode()
                        .strip()
                    )
                    if remove_file:
                        frozen.unlink()
                    else:
                        frozen.write_text("[]", encoding="utf-8")
                    if committed:
                        self.commit_reference_fixture(
                            root, "removed historical identifier"
                        )
                    result = self.run_note_cli(root, base if committed else None)
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn(
                        "Missing frozen legacy identifier '[INV-REC-07]'", result.stdout
                    )

    def test_historical_triplet_edit_and_archive_remain_valid_at_note_cli(self):
        for committed in (False, True):
            with (
                self.subTest(committed=committed),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                root, sidecar, _ = self.make_reference_repo(tmpdir)
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                self.commit_reference_fixture(root, "historical triplet")
                base = (
                    subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                    )
                    .decode()
                    .strip()
                )
                english = sidecar.with_name(sidecar.name[:-13] + ".md")
                english.write_text(
                    english.read_text("utf-8") + "Updated evidence.\n", encoding="utf-8"
                )
                edited = self.run_note_cli(root)
                self.assertEqual(edited.returncode, 0, edited.stdout + edited.stderr)
                with redirect_stdout(io.StringIO()):
                    archive_note.transition_triplet(english, "archived")
                if committed:
                    self.commit_reference_fixture(root, "archived historical triplet")
                archived = self.run_note_cli(root, base if committed else None)
                self.assertEqual(
                    archived.returncode, 0, archived.stdout + archived.stderr
                )

    def test_unborn_git_requires_new_decisions_and_named_rules_at_note_cli(self):
        for kind, diagnostic in (
            ("legacy-triplet", "New legacy triplet"),
            ("new-identifier", "New legacy identifier '[INV-NEW-99]'"),
            ("decision", None),
        ):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmpdir:
                root, sidecar, metadata = self.make_reference_repo(tmpdir)
                (root / "CODING_STANDARDS.md").write_text(
                    "## Core Isolation\nExplicit selections remain persisted.\n",
                    encoding="utf-8",
                )
                if kind == "legacy-triplet":
                    metadata["invariants"] = []
                    sidecar.write_text(json.dumps(metadata), encoding="utf-8")
                else:
                    for suffix in (".md", ".zh.md", ".sidecar.json"):
                        sidecar.with_name(sidecar.name[:-13] + suffix).unlink()
                    self.make_decision_note(root)
                    if kind == "new-identifier":
                        frozen = root / "scripts/legacy_invariant_ids.json"
                        frozen.parent.mkdir()
                        frozen.write_text(
                            json.dumps(["[INV-NEW-99]"]), encoding="utf-8"
                        )
                without_git = self.run_note_cli(root)
                self.assertEqual(
                    without_git.returncode, 0, without_git.stdout + without_git.stderr
                )
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                unborn = self.run_note_cli(root)
                self.assertEqual(
                    unborn.returncode,
                    1 if diagnostic else 0,
                    unborn.stdout + unborn.stderr,
                )
                if diagnostic:
                    self.assertIn(diagnostic, unborn.stdout)

    def test_malformed_frozen_identifiers_fail_governance_entry(self):
        for content in ("{", "{}", "[null]", '["INV-REC-07"]'):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as tmpdir:
                root, _, _ = self.make_reference_repo(tmpdir)
                frozen = root / "scripts/legacy_invariant_ids.json"
                frozen.parent.mkdir()
                frozen.write_text(content, encoding="utf-8")
                result, output = self.run_reference_gate(root)
                self.assertEqual(result, 1, output)

    def test_all_existing_notes_pass_verification(self):
        errors = verify_agent_notes(".agents/notes")
        self.assertEqual(errors, [])

    def test_invalid_note_naming_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "implemented" / "architecture"
            target_dir.mkdir(parents=True)
            (target_dir / "bad_naming_convention.md").write_text(
                "---\ntitle: T\nstatus: implemented\ncategory: architecture\ndate: 2026-09-28\n---\n",
                encoding="utf-8",
            )
            errors = verify_agent_notes(tmpdir)
            self.assertTrue(
                any(
                    "YYYY-MM-DD-slug" in err or "Unrecognized file" in err
                    for err in errors
                )
            )

    def test_incomplete_triplet_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "implemented" / "feature"
            target_dir.mkdir(parents=True)
            slug = "2026-09-28-isolated-feature"
            (target_dir / f"{slug}.md").write_text(
                "---\ntitle: T\nstatus: implemented\ncategory: feature\ndate: 2026-09-28\n---\nContent",
                encoding="utf-8",
            )
            # Missing .zh.md and .sidecar.json
            errors = verify_agent_notes(tmpdir)
            self.assertTrue(any("missing 'zh' file" in err for err in errors))
            self.assertTrue(any("missing 'sidecar' file" in err for err in errors))

    def test_invalid_sidecar_schema_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "implemented" / "architecture"
            target_dir.mkdir(parents=True)
            slug = "2026-09-28-schema-check"
            (target_dir / f"{slug}.md").write_text(
                "---\ntitle: T\nstatus: implemented\ncategory: architecture\ndate: 2026-09-28\n---\n",
                encoding="utf-8",
            )
            (target_dir / f"{slug}.zh.md").write_text(
                "---\ntitle: T\nstatus: implemented\ncategory: architecture\ndate: 2026-09-28\n---\n",
                encoding="utf-8",
            )
            # Invariant missing brackets [INV-01]
            sidecar_data = {
                "title": "T",
                "status": "implemented",
                "category": "architecture",
                "date": "2026-09-28",
                "authors": ["Tester"],
                "invariants": ["INV-01"],
                "code_symbols": [],
                "test_suites": [],
            }
            (target_dir / f"{slug}.sidecar.json").write_text(
                json.dumps(sidecar_data), encoding="utf-8"
            )
            errors = verify_agent_notes(tmpdir)
            self.assertTrue(any("Invalid invariant format" in err for err in errors))

    def test_forbidden_issue_number_detected_in_note(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "implemented" / "feature"
            target_dir.mkdir(parents=True)
            slug = "2026-09-28-forbidden-issue"
            (target_dir / f"{slug}.md").write_text(
                "---\ntitle: T\nstatus: implemented\ncategory: feature\ndate: 2026-09-28\n---\nFixes issue #1234 here.",
                encoding="utf-8",
            )
            (target_dir / f"{slug}.zh.md").write_text(
                "---\ntitle: T\nstatus: implemented\ncategory: feature\ndate: 2026-09-28\n---\n修复",
                encoding="utf-8",
            )
            sidecar_data = {
                "title": "T",
                "status": "implemented",
                "category": "feature",
                "date": "2026-09-28",
                "authors": [],
                "invariants": [],
                "code_symbols": [],
                "test_suites": [],
            }
            (target_dir / f"{slug}.sidecar.json").write_text(
                json.dumps(sidecar_data), encoding="utf-8"
            )
            errors = verify_agent_notes(tmpdir)
            self.assertTrue(
                any("Prohibited issue tracker reference" in err for err in errors)
            )

    def test_subsystem_invariants_pass_and_malformed_identifiers_fail(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "proposed" / "bug-fix"
            target_dir.mkdir(parents=True)
            slug = "2026-09-28-subsystem-invariants"
            for suffix in (".md", ".zh.md"):
                (target_dir / f"{slug}{suffix}").write_text(
                    "---\ntitle: T\nstatus: proposed\ncategory: bug-fix\ndate: 2026-09-28\n---\n",
                    encoding="utf-8",
                )
            sidecar = {
                "title": "T",
                "status": "proposed",
                "category": "bug-fix",
                "date": "2026-09-28",
                "authors": ["Tester"],
                "invariants": ["[INV-01]", "[INV-DEV-01]", "[INV-SCHED-04]"],
                "code_symbols": [],
                "test_suites": [],
            }
            path = target_dir / f"{slug}.sidecar.json"
            path.write_text(json.dumps(sidecar), encoding="utf-8")
            self.assertEqual(verify_agent_notes(tmpdir), [])

            for invariant in ("[INV-dev-01]", "[INV-DEV-1]", "[INV--01]", "INV-DEV-01"):
                with self.subTest(invariant=invariant):
                    sidecar["invariants"] = [invariant]
                    path.write_text(json.dumps(sidecar), encoding="utf-8")
                    self.assertTrue(
                        any(
                            "Invalid invariant format" in error
                            for error in verify_agent_notes(tmpdir)
                        )
                    )

    def test_dead_markdown_link_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_doc.md"
            test_file.write_text(
                "See [Missing](non_existent_file.md)", encoding="utf-8"
            )
            errors = verify_doc_links(tmpdir)
            self.assertTrue(any("non_existent_file.md" in err for err in errors))

    def test_git_ignored_local_documents_do_not_block_governance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "historical fixture")
            (root / ".gitignore").write_text(
                "debug/\nlocal-diagnostic.md\n", encoding="utf-8"
            )
            for relative in ("debug/nested/diagnostic.md", "local-diagnostic.md"):
                document = root / relative
                document.parent.mkdir(parents=True, exist_ok=True)
                document.write_text("[Missing](retired.md)\n", encoding="utf-8")

            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)
            self.assertIn("STRUCTURAL CHECKS PASSED", output)

    def test_git_tracked_ignored_document_still_blocks_governance(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "historical fixture")
            (root / ".gitignore").write_text("debug/\n", encoding="utf-8")
            document = root / "debug/tracked.md"
            document.parent.mkdir()
            document.write_text("[Missing](retired.md)\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "-f", "--", "debug/tracked.md"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            (document.parent / "local.md").write_text(
                "[Missing](local-retired.md)\n", encoding="utf-8"
            )

            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 1, output)
            self.assertIn("tracked.md", output)
            self.assertNotIn("local-retired.md", output)
            self.assertNotIn("STRUCTURAL CHECKS PASSED", output)

    def test_git_untracked_documents_include_hidden_paths_and_utf8_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "historical fixture")
            for relative in ("docs/new.md", ".review/新说明.md"):
                document = root / relative
                document.parent.mkdir()
                document.write_text("[Missing](retired.md)\n", encoding="utf-8")

            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 1, output)
            self.assertIn("new.md", output)
            self.assertIn("新说明.md", output)
            self.assertNotIn("STRUCTURAL CHECKS PASSED", output)

    def test_non_git_document_root_keeps_traversal_inside_parent_repository(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=parent,
                check=True,
                capture_output=True,
                timeout=15,
            )
            root = parent / "nested"
            document = root / "debug/diagnostic.md"
            document.parent.mkdir(parents=True)
            document.write_text("[Missing](retired.md)\n", encoding="utf-8")
            (root / ".gitignore").write_text("debug/\n", encoding="utf-8")

            errors = verify_doc_links(root)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("diagnostic.md", errors[0])

    def test_git_document_inventory_failures_are_reported(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            actual_run = subprocess.run

            def fail_inventory(arguments, **kwargs):
                if arguments[1] == "ls-files":
                    return subprocess.CompletedProcess(
                        arguments, 1, b"", b"fatal: cannot read index"
                    )
                return actual_run(arguments, **kwargs)

            with patch("scripts.verify_doc_links.subprocess.run", fail_inventory):
                errors = verify_doc_links(root)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("Cannot collect Markdown documents", errors[0])
            self.assertIn("cannot read index", errors[0])

            for fault in (
                OSError("Git unavailable"),
                subprocess.TimeoutExpired("git", 10),
            ):
                with self.subTest(fault=fault):
                    with patch(
                        "scripts.verify_doc_links.subprocess.run", side_effect=fault
                    ):
                        errors = verify_doc_links(root)
                    self.assertEqual(len(errors), 1, errors)
                    self.assertIn("Cannot collect Markdown documents", errors[0])

    def test_broken_git_worktree_metadata_does_not_silently_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / ".git").write_text("gitdir: missing\n", encoding="utf-8")
            errors = verify_doc_links(root)
            self.assertEqual(len(errors), 1, errors)
            self.assertIn("Cannot collect Markdown documents", errors[0])

    def test_markdown_link_titles_angle_brackets_and_code_blocks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "valid.md").write_text("# Valid\n", encoding="utf-8")
            doc = root / "doc.md"
            doc_content = (
                'See [Valid](valid.md "Doc Title") and [Valid Angle](<valid.md>).\n'
                "Inline code sample: `[Missing](missing_inline.md)` should be ignored.\n"
                "```markdown\n"
                "# Fenced code block:\n"
                "[Missing Block](missing_block.md)\n"
                "```\n"
                "Real broken link: [Broken](<missing_real.md> 'Broken Title')\n"
            )
            doc.write_text(doc_content, encoding="utf-8")
            errors = verify_doc_links(root)
            self.assertEqual(len(errors), 1)
            self.assertTrue("missing_real.md" in errors[0])

    def test_markdown_reference_style_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "target.md").write_text("# Target\n", encoding="utf-8")
            doc = root / "doc.md"
            doc.write_text(
                "Full reference: [Text][ref1]\n"
                "Collapsed reference: [target.md][]\n"
                "Broken reference target: [Text2][ref-broken]\n"
                "Unresolved reference label: [Text3][unresolved]\n\n"
                '[ref1]: target.md "Title"\n'
                "[target.md]: <target.md>\n"
                "[ref-broken]: non_existent.md\n",
                encoding="utf-8",
            )
            errors = verify_doc_links(root)
            self.assertEqual(
                len(errors), 3
            )  # ref-broken definition, ref-broken usage, unresolved usage
            self.assertTrue(any("non_existent.md" in err for err in errors))
            self.assertTrue(any("unresolved" in err for err in errors))

    def test_markdown_anchor_cli_rejects_missing_and_example_only_fragments(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "target.md").write_text(
                "# Repeated\n\n# Repeated\n\n"
                "````markdown\n```\n# Fenced Only\n````\n"
                '`<a id="inline-only"></a>`\n'
                '<!--\n```\n# Comment Heading\n<a id="comment-id"></a>\n-->\n'
                "\n    Indented Example\n----------------\n"
                '\n    <a id="indented-code-only"></a>\n'
                "\n- List Example\n---------------\n",
                encoding="utf-8",
            )
            (root / "doc.md").write_text(
                "# Existing\n"
                "[Same page](#missing-same)\n"
                "[Other page](target.md#missing-cross)\n"
                "[Code heading](target.md#fenced-only)\n"
                "[Code anchor](target.md#inline-only)\n"
                "[Absent duplicate](target.md#repeated-2)\n"
                "[Hidden heading](target.md#comment-heading)\n"
                "[Hidden ID](target.md#comment-id)\n"
                "[Indented code](target.md#indented-example)\n"
                "[Indented HTML](target.md#indented-code-only)\n"
                "[List](target.md#list-example)\n"
                "`[Example](#ignored-inline)`\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(
                        Path(__file__).resolve().parents[2]
                        / "scripts/verify_doc_links.py"
                    ),
                    "--root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("Found 10 broken", result.stdout)
            for fragment in (
                "missing-same",
                "missing-cross",
                "fenced-only",
                "inline-only",
                "repeated-2",
                "comment-heading",
                "comment-id",
                "indented-example",
                "indented-code-only",
                "list-example",
            ):
                self.assertIn(fragment, result.stdout)
            self.assertNotIn("ignored-inline", result.stdout)

    def test_markdown_anchor_cli_accepts_rendered_headings_and_custom_anchors(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "target page.md").write_text(
                "# **Recovery** & _Policy_!\n"
                "## `__init__` API\n"
                "## 重连恢复\n"
                "## Repeated\n## Repeated-1\n## Repeated\n"
                "\nSetext `code_name`\n------------------\n"
                '<a id="Custom-ID"></a>\n<a name="custom-name"></a>\n',
                encoding="utf-8",
            )
            (root / "doc.md").write_text(
                "# Same Page\n[Same](#same-page)\n"
                "[Styled](target%20page.md#recovery--policy)\n"
                "[Code identifier](target%20page.md#__init__-api)\n"
                "[Encoded][cross]\n"
                "[Duplicate](target%20page.md#repeated-2)\n"
                "[Setext](target%20page.md#setext-code_name)\n"
                "[ID](target%20page.md#Custom-ID)\n"
                "[Named](target%20page.md#custom-name)\n"
                "[cross]: target%20page.md#%E9%87%8D%E8%BF%9E%E6%81%A2%E5%A4%8D\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(
                        Path(__file__).resolve().parents[2]
                        / "scripts/verify_doc_links.py"
                    ),
                    "--root",
                    str(root),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("SUCCESS", result.stdout)

    def test_glossary_avoid_term_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CONTEXT.md").write_text(
                "### Test Concept\n- **Definition**: D\n- **_Avoid_**: `ForbiddenTerm`\n",
                encoding="utf-8",
            )
            (root / "doc.md").write_text("We use ForbiddenTerm here.", encoding="utf-8")
            errors = verify_glossary_alignment(
                context_file=root / "CONTEXT.md", scan_roots=[root]
            )
            self.assertTrue(any("ForbiddenTerm" in err for err in errors))

    def test_glossary_clean_file_passes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CONTEXT.md").write_text(
                "### Test Concept\n- **Definition**: D\n- **_Avoid_**: `ForbiddenTerm`\n",
                encoding="utf-8",
            )
            (root / "doc.md").write_text(
                "We use ApprovedConcept here.", encoding="utf-8"
            )
            errors = verify_glossary_alignment(
                context_file=root / "CONTEXT.md", scan_roots=[root]
            )
            self.assertEqual(errors, [])

    def test_glossary_python_and_frontend_comments_vs_strings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "CONTEXT.md").write_text(
                "### Test Concept\n- **Definition**: D\n- **_Avoid_**: `ForbiddenTerm`\n",
                encoding="utf-8",
            )
            # Python file: string literal containing # ForbiddenTerm should NOT be flagged;
            # real comment and docstring SHOULD be flagged.
            py_file = root / "sample.py"
            py_file.write_text(
                'label = "# ForbiddenTerm in string"\n'
                "# Real comment with ForbiddenTerm\n"
                "def func():\n"
                '    """Docstring containing ForbiddenTerm."""\n'
                "    return True\n",
                encoding="utf-8",
            )
            errors = verify_glossary_alignment(
                context_file=root / "CONTEXT.md", scan_roots=[root]
            )
            self.assertEqual(len(errors), 2)
            self.assertTrue(any("sample.py:2" in err for err in errors))
            self.assertTrue(any("sample.py:4" in err for err in errors))

            # JS/Vue file: HTML comment and JS comment should be flagged; string literal should NOT.
            vue_file = root / "Component.vue"
            vue_file.write_text(
                "<template>\n"
                "  <!-- HTML comment with ForbiddenTerm -->\n"
                '  <div>{{ "http://url.com//ForbiddenTerm" }}</div>\n'
                "</template>\n"
                "<script>\n"
                "// JS comment with ForbiddenTerm\n"
                'const msg = "/* ForbiddenTerm in string */";\n'
                "</script>\n",
                encoding="utf-8",
            )
            errors_all = verify_glossary_alignment(
                context_file=root / "CONTEXT.md", scan_roots=[root]
            )
            self.assertEqual(len(errors_all), 4)  # 2 python + 2 vue

    def test_archive_note_transition_lifecycle_and_frontmatter_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            notes_root = Path(tmpdir) / ".agents" / "notes"
            proposed_dir = notes_root / "proposed" / "feature"
            proposed_dir.mkdir(parents=True)

            slug = "2026-09-28-test-transition"
            (proposed_dir / f"{slug}.md").write_text(
                '---\ntitle: Test Feature\nstatus: "proposed"\ncategory: feature\ndate: 2026-09-28\n---\n\n'
                "Body text mentioning status: proposed in code sample:\n```yaml\nstatus: proposed\n```\n",
                encoding="utf-8",
            )
            (proposed_dir / f"{slug}.zh.md").write_text(
                "---\ntitle: 测试功能\nstatus: proposed\ncategory: feature\ndate: 2026-09-28\n---\n\n正文",
                encoding="utf-8",
            )
            sidecar_data = {
                "title": "Test Feature",
                "status": "proposed",
                "category": "feature",
                "date": "2026-09-28",
                "authors": ["Tester"],
                "invariants": ["[INV-01]"],
                "code_symbols": [],
                "test_suites": [],
            }
            (proposed_dir / f"{slug}.sidecar.json").write_text(
                json.dumps(sidecar_data, indent=2), encoding="utf-8"
            )

            # 1. Successful transition to implemented
            archive_note.transition_triplet(
                proposed_dir / slug, target_lifecycle="implemented"
            )

            implemented_dir = notes_root / "implemented" / "feature"
            self.assertFalse((proposed_dir / f"{slug}.md").exists())
            self.assertTrue((implemented_dir / f"{slug}.md").exists())
            self.assertTrue((implemented_dir / f"{slug}.zh.md").exists())
            self.assertTrue((implemented_dir / f"{slug}.sidecar.json").exists())

            # Verify frontmatter updated to implemented, but body code sample preserved
            md_content = (implemented_dir / f"{slug}.md").read_text(encoding="utf-8")
            self.assertIn(
                "status: implemented", md_content[: md_content.find("---", 3)]
            )
            self.assertIn("status: proposed", md_content[md_content.find("---", 3) :])

            sidecar_loaded = json.loads(
                (implemented_dir / f"{slug}.sidecar.json").read_text(encoding="utf-8")
            )
            self.assertEqual(sidecar_loaded["status"], "implemented")

            # 2. Pre-flight collision guard
            # Recreate proposed files
            (proposed_dir / f"{slug}.md").write_text("---", encoding="utf-8")
            (proposed_dir / f"{slug}.zh.md").write_text("---", encoding="utf-8")
            (proposed_dir / f"{slug}.sidecar.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                archive_note.transition_triplet(
                    proposed_dir / slug, target_lifecycle="implemented"
                )

            # 3. Missing source file guard
            (proposed_dir / f"{slug}.zh.md").unlink()
            with self.assertRaises(FileNotFoundError):
                archive_note.transition_triplet(
                    proposed_dir / slug, target_lifecycle="archived"
                )

    def test_run_all_checks_passes(self):
        self.assertEqual(run_all_checks(), 0)

    def test_success_reports_automated_scope_and_remaining_manual_review(self):
        output = io.StringIO()
        with (
            patch("scripts.verify_governance.verify_agent_notes", return_value=[]),
            patch("scripts.verify_governance.verify_doc_links", return_value=[]),
            patch(
                "scripts.verify_governance.verify_glossary_alignment", return_value=[]
            ),
            redirect_stdout(output),
        ):
            result = run_all_checks()

        self.assertEqual(result, 0)
        report = output.getvalue()
        self.assertIn("STRUCTURAL CHECKS PASSED", report)
        self.assertIn(
            "note structures/references, relative Markdown links and Avoid terms",
            report,
        )
        self.assertIn("Not evaluated: behavior tests", report)
        self.assertIn(
            "concept meaning, glossary approval or implementation status", report
        )
        self.assertNotIn("fully compliant", report)

    def test_each_failed_gate_reports_failure_and_runs_remaining_checks(self):
        checks = (
            "verify_agent_notes",
            "verify_doc_links",
            "verify_glossary_alignment",
        )
        for failed_check in checks:
            with self.subTest(failed_check=failed_check), ExitStack() as stack:
                mocked_checks = [
                    stack.enter_context(
                        patch(
                            f"scripts.verify_governance.{check}",
                            return_value=["Sample violation"]
                            if check == failed_check
                            else [],
                        )
                    )
                    for check in checks
                ]
                output = io.StringIO()
                stack.enter_context(redirect_stdout(output))
                result = run_all_checks()

                self.assertEqual(result, 1)
                self.assertIn("Sample violation", output.getvalue())
                self.assertNotIn("STRUCTURAL CHECKS PASSED", output.getvalue())
                for mocked_check in mocked_checks:
                    mocked_check.assert_called_once()

    def test_reference_checks_reachable_from_actual_cli_without_importing_modules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            source = root / "production.py"
            marker = root / "imported.txt"
            source.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('side effect')\n",
                encoding="utf-8",
            )
            script = (
                Path(__file__).resolve().parents[2] / "scripts/verify_governance.py"
            )
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(script)],
                cwd=root,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("STRUCTURAL CHECKS PASSED", result.stdout)
            self.assertIn("Code-symbol resolution is not checked", result.stdout)
            self.assertIn("Not evaluated: behavior tests", result.stdout)
            self.assertIn("glossary approval or implementation status", result.stdout)
            self.assertNotIn("fully compliant", result.stdout)
            self.assertFalse(marker.exists())

    def test_missing_test_suite_and_undeclared_invariant_fail_at_governance_entry(self):
        for field, value, diagnostic in (
            ("test_suites", ["arknights_mower/tests/missing_tests.py"], "test suite"),
            ("invariants", ["[INV-REC-99]"], "Undeclared invariant"),
            ("test_suites", ["../outside_tests.py"], "outside-repository"),
            ("test_suites", ["C:/outside_tests.py"], "outside-repository"),
        ):
            with (
                self.subTest(field=field, value=value),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                root, sidecar, metadata = self.make_reference_repo(tmpdir)
                metadata[field] = value
                sidecar.write_text(json.dumps(metadata), encoding="utf-8")
                result, output = self.run_reference_gate(root)
                self.assertEqual(result, 1)
                self.assertIn(diagnostic, output)
                self.assertIn("[Gate 2/3]", output)
                self.assertIn("[Gate 3/3]", output)
                self.assertNotIn("STRUCTURAL CHECKS PASSED", output)

    def test_invariant_mentions_and_fenced_examples_are_not_declarations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            (root / "CODING_STANDARDS.md").write_text(
                "A review mentions [INV-REC-07].\n```markdown\n"
                "- **[INV-REC-07] Example**: This is an example.\n```\n",
                encoding="utf-8",
            )
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 1)
            self.assertIn("Undeclared invariant", output)

    def test_historical_references_warn_but_touched_triplet_is_strict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, metadata = self.make_reference_repo(tmpdir)
            metadata["test_suites"] = ["arknights_mower/tests/retired_tests.py"]
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            for arguments in (
                ["init", "-q"],
                ["add", "."],
                [
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "-c",
                    "core.hooksPath=",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-qm",
                    "reference fixture",
                ],
            ):
                subprocess.run(
                    ["git", *arguments],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    timeout=15,
                )

            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0)
            self.assertIn("COMPATIBILITY WARNINGS", output)
            self.assertIn("retired_tests.py", output)

            # A deliberate audit can make unchanged active references strict.
            script = (
                Path(__file__).resolve().parents[2]
                / "scripts/verify_agent_note_format.py"
            )
            audit = subprocess.run(
                [sys.executable, "-X", "utf8", str(script), "--all-active"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(audit.returncode, 1, audit.stdout + audit.stderr)
            self.assertIn("retired_tests.py", audit.stdout)

            english = sidecar.with_name("2026-10-08-reference-check.md")
            original = english.read_text(encoding="utf-8")
            english.write_text(original + "Reviewed behavior.\n", encoding="utf-8")
            self.assertEqual(self.run_reference_gate(root)[0], 1)

            english.write_text(original, encoding="utf-8")
            chinese = sidecar.with_name("2026-10-08-reference-check.zh.md")
            original_zh = chinese.read_text(encoding="utf-8")
            chinese.write_text(original_zh + "Reviewed behavior.\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "--", str(chinese)],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            chinese.write_text(original_zh, encoding="utf-8")
            self.assertEqual(self.run_reference_gate(root)[0], 1)

    def test_untracked_active_references_are_strict_and_archive_references_warn(self):
        for lifecycle, expected in (
            ("implemented", 1),
            ("proposed", 1),
            ("archived", 0),
            ("rejected", 0),
        ):
            with (
                self.subTest(lifecycle=lifecycle),
                tempfile.TemporaryDirectory() as tmpdir,
            ):
                root, sidecar, metadata = self.make_reference_repo(tmpdir, lifecycle)
                subprocess.run(
                    ["git", "init", "-q"],
                    cwd=root,
                    check=True,
                    capture_output=True,
                    timeout=15,
                )
                self.commit_reference_fixture(root, "historical reference fixture")
                metadata["test_suites"] = ["arknights_mower/tests/missing_tests.py"]
                sidecar.write_text(json.dumps(metadata), encoding="utf-8")
                result, output = self.run_reference_gate(root)
                self.assertEqual(result, expected, output)
                self.assertIn("missing_tests.py", output)

    def test_metadata_overlap_does_not_prove_duplicate_decisions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(
                tmpdir, slug="2026-10-07-first-decision"
            )
            self.make_reference_repo(tmpdir, slug="2026-10-08-second-decision")
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 0, output)

    def test_committed_note_changes_use_requested_base_at_actual_governance_cli(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(
                tmpdir, slug="2026-10-07-existing-decision"
            )
            _, sidecar, metadata = self.make_reference_repo(
                tmpdir, slug="2026-10-08-reviewed-decision"
            )
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "existing fixture")
            comparison_base = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                )
                .decode()
                .strip()
            )
            metadata["test_suites"] = ["arknights_mower/tests/missing_tests.py"]
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            self.commit_reference_fixture(root, "new fixture")
            self.assertEqual(self.run_reference_gate(root)[0], 0)

            script = (
                Path(__file__).resolve().parents[2] / "scripts/verify_governance.py"
            )
            for base, diagnostic in (
                (comparison_base, "missing_tests.py"),
                ("nonexistent-review-base", "Invalid comparison base"),
            ):
                with self.subTest(base=base):
                    result = subprocess.run(
                        [sys.executable, "-X", "utf8", str(script), "--base", base],
                        cwd=root,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=30,
                    )
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn(diagnostic, result.stdout)
                    self.assertNotIn("STRUCTURAL CHECKS PASSED", result.stdout)

            current = subprocess.run(
                [sys.executable, "-X", "utf8", str(script), "--base", "HEAD"],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
            self.assertIn("COMPATIBILITY WARNINGS", current.stdout)

    def run_governance_workflow(self, root, event_name, event):
        repository = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load(
            (repository / ".github/workflows/docs-consistency.yml").read_text("utf-8")
        )
        steps = workflow["jobs"]["verify"]["steps"]
        command = shlex.split(
            next(
                step["run"]
                for step in steps
                if "scripts/verify_governance.py" in step.get("run", "")
            )
        )
        event_path = root / "github-event.json"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        return subprocess.run(
            [sys.executable, "-X", "utf8", str(repository / command[1]), *command[2:]],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            env={
                **os.environ,
                "GITHUB_EVENT_NAME": event_name,
                "GITHUB_EVENT_PATH": str(event_path),
            },
        )

    def test_github_workflow_checks_committed_notes_and_preserves_historical_warnings(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, old_sidecar, old_metadata = self.make_reference_repo(
                tmpdir, slug="2026-10-07-existing-decision"
            )
            old_metadata["test_suites"] = ["arknights_mower/tests/retired_tests.py"]
            old_sidecar.write_text(json.dumps(old_metadata), encoding="utf-8")
            _, sidecar, metadata = self.make_reference_repo(
                tmpdir, slug="2026-10-08-reviewed-decision"
            )
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "existing fixture")
            base = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                )
                .decode()
                .strip()
            )
            metadata["test_suites"] = ["arknights_mower/tests/missing_tests.py"]
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            self.commit_reference_fixture(root, "new fixture")

            events = (
                (
                    "pull_request",
                    {
                        "pull_request": {
                            "base": {"sha": base},
                            "title": "docs: 更新文档",
                            "body": "已核实的变化。",
                        }
                    },
                ),
                ("push", {"before": base}),
                ("workflow_dispatch", {"inputs": {"comparison_base": base}}),
            )
            for event_name, event in events:
                with self.subTest(event_name=event_name):
                    result = self.run_governance_workflow(root, event_name, event)
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn("missing_tests.py", result.stdout)
                    self.assertNotIn("STRUCTURAL CHECKS PASSED", result.stdout)

            metadata["test_suites"] = ["arknights_mower/tests/field_tests.py"]
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            self.commit_reference_fixture(root, "repaired fixture")
            for event_name, event in events:
                with self.subTest(repaired=event_name):
                    result = self.run_governance_workflow(root, event_name, event)
                    self.assertEqual(
                        result.returncode, 0, result.stdout + result.stderr
                    )
                    self.assertIn("COMPATIBILITY WARNINGS", result.stdout)
                    self.assertIn("retired_tests.py", result.stdout)
                    self.assertIn(base, result.stdout)

            for event_name, event in (
                ("workflow_dispatch", {}),
                ("push", {"before": "0" * 40}),
            ):
                with self.subTest(full_audit=event_name):
                    result = self.run_governance_workflow(root, event_name, event)
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn("retired_tests.py", result.stdout)

    def test_github_workflow_rejects_missing_or_unavailable_comparison_scope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root, _, _ = self.make_reference_repo(tmpdir)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "fixture")
            for event_name, event in (
                ("pull_request", {}),
                ("pull_request", {"pull_request": None}),
                ("pull_request", []),
                ("push", {}),
                ("push", {"before": "a" * 40}),
                ("pull_request", {"pull_request": {"base": {"sha": "0" * 40}}}),
                ("pull_request", {"pull_request": {"base": {"sha": "HEAD"}}}),
                ("workflow_dispatch", {"inputs": None}),
                ("workflow_dispatch", {"inputs": {"comparison_base": "missing-base"}}),
                ("unknown-event", {}),
            ):
                with self.subTest(event_name=event_name, event=event):
                    result = self.run_governance_workflow(root, event_name, event)
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertNotIn("STRUCTURAL CHECKS PASSED", result.stdout)

        repository = Path(__file__).resolve().parents[2]
        workflow = yaml.safe_load(
            (repository / ".github/workflows/docs-consistency.yml").read_text("utf-8")
        )
        checkout = next(
            step
            for step in workflow["jobs"]["verify"]["steps"]
            if step.get("uses", "").startswith("actions/checkout@")
        )
        self.assertEqual(checkout.get("with", {}).get("fetch-depth"), 0)

    def test_malformed_metadata_returns_errors_instead_of_crashing_gate(self):
        for field, value in (
            ("invariants", [None]),
            ("authors", [7]),
            ("code_symbols", [""]),
            ("test_suites", [False]),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmpdir:
                root, sidecar, metadata = self.make_reference_repo(tmpdir)
                metadata[field] = value
                sidecar.write_text(json.dumps(metadata), encoding="utf-8")
                result, output = self.run_reference_gate(root)
                self.assertEqual(result, 1, output)

        with tempfile.TemporaryDirectory() as tmpdir:
            root, sidecar, _ = self.make_reference_repo(tmpdir)
            sidecar.write_text("[]", encoding="utf-8")
            result, output = self.run_reference_gate(root)
            self.assertEqual(result, 1)
            self.assertIn("JSON object", output)

    def test_nested_non_git_reference_root_does_not_inherit_parent_history(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parent = Path(tmpdir)
            root, sidecar, metadata = self.make_reference_repo(parent / "nested")
            metadata["test_suites"] = ["arknights_mower/tests/missing_tests.py"]
            sidecar.write_text(json.dumps(metadata), encoding="utf-8")
            subprocess.run(
                ["git", "init", "-q"],
                cwd=parent,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(parent, "parent fixture")
            script = (
                Path(__file__).resolve().parents[2] / "scripts/verify_governance.py"
            )
            result = subprocess.run(
                [sys.executable, "-X", "utf8", str(script), "--repo-root", str(root)],
                cwd=parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("missing_tests.py", result.stdout)
            self.assertNotIn("COMPATIBILITY WARNINGS", result.stdout)

            scoped = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(script),
                    "--repo-root",
                    str(root),
                    "--base",
                    "HEAD",
                ],
                cwd=parent,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(scoped.returncode, 1, scoped.stdout + scoped.stderr)
            self.assertIn("not a Git worktree root", scoped.stdout)


class VerifyFormalTextTests(unittest.TestCase):
    make_reference_repo = VerifyGovernanceTests.make_reference_repo
    commit_reference_fixture = VerifyGovernanceTests.commit_reference_fixture
    run_governance_workflow = VerifyGovernanceTests.run_governance_workflow

    def run_text_cli(self, root, *arguments):
        script = (
            Path(__file__).resolve().parents[2] / "scripts/verify_glossary_alignment.py"
        )
        return subprocess.run(
            [sys.executable, "-B", "-X", "utf8", str(script), *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    def test_skill_template_evaluation_and_fenced_prose_reach_default_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            for name, content in (
                (".agents/skills/example/SKILL.md", "# ForbiddenTerm\n"),
                (
                    ".agents/skills/example/assets/body.md",
                    "```text\n`ForbiddenTerm`\n```\n",
                ),
                (
                    ".agents/skills/example/evals/evals.json",
                    '{"expected_output":"ForbiddenTerm"}',
                ),
            ):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            result = self.run_text_cli(root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            for name in ("SKILL.md", "body.md", "evals.json"):
                self.assertIn(name, result.stdout)

    def test_development_new_lines_and_business_rules_have_separate_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            glossary = root / "CONTEXT.md"
            glossary.write_text(
                glossary.read_text(encoding="utf-8")
                + "\n## 3. Development & Documentation Language\n- **_Avoid_**: `OldWording`\n",
                encoding="utf-8",
            )
            document = root / "docs/guide.md"
            document.parent.mkdir()
            document.write_text("OldWording\n", encoding="utf-8")
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "initial prose")
            baseline = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                )
                .decode()
                .strip()
            )
            inherited = self.run_text_cli(root, "--base", baseline)
            self.assertEqual(
                inherited.returncode, 0, inherited.stdout + inherited.stderr
            )
            self.assertIn("UNCHANGED DEVELOPMENT PROSE", inherited.stdout)
            document.write_text("OldWording\nNew OldWording\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "docs/guide.md"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            (root / "docs/new.md").write_text("OldWording\n", encoding="utf-8")
            staged = self.run_text_cli(root, "--base", baseline)
            self.assertEqual(staged.returncode, 1, staged.stdout + staged.stderr)
            self.assertIn("guide.md:2", staged.stdout)
            self.assertIn("new.md:1", staged.stdout)
            self.commit_reference_fixture(root, "new prose")
            committed = self.run_text_cli(root, "--base", baseline)
            self.assertEqual(
                committed.returncode, 1, committed.stdout + committed.stderr
            )
            document.write_text("ForbiddenTerm\n", encoding="utf-8")
            self.commit_reference_fixture(root, "existing business violation")
            business = self.run_text_cli(root, "--base", "HEAD")
            self.assertEqual(business.returncode, 1, business.stdout + business.stderr)
            self.assertIn("ForbiddenTerm", business.stdout)

    def test_preserved_span_checks_hash_source_and_surrounding_current_prose(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            path = root / ".agents/skills/example/evals/input.md"
            path.parent.mkdir(parents=True)
            path.write_text(
                "Historical quotation follows.\nForbiddenTerm\nCurrent rule: ForbiddenTerm\n",
                encoding="utf-8",
            )
            record = {
                "path": path.relative_to(root).as_posix(),
                "kind": "historical-quotation",
                "label": "Original input for comparison, not a recommendation.",
                "source": "https://github.com/example/project/blob/"
                + "a" * 40
                + "/input.md",
                "start_line": 2,
                "end_line": 2,
                "sha256": hashlib.sha256(b"ForbiddenTerm\n").hexdigest(),
            }
            manifest = root / "scripts/prose_sources.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps([record]), encoding="utf-8")
            result = self.run_text_cli(root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertNotIn("input.md:2:", result.stdout)
            self.assertIn("input.md:3:", result.stdout)
            for field, value in (
                ("sha256", "0" * 64),
                ("source", "https://example.invalid/input"),
                ("path", "../outside.md"),
                ("label", ""),
            ):
                with self.subTest(field=field):
                    manifest.write_text(
                        json.dumps([{**record, field: value}]), encoding="utf-8"
                    )
                    invalid = self.run_text_cli(root)
                    self.assertEqual(
                        invalid.returncode, 1, invalid.stdout + invalid.stderr
                    )
                    self.assertIn("Invalid preserved prose source", invalid.stdout)

    def test_real_identifier_is_kept_but_surrounding_formal_prose_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            source = root / "source.py"
            source.write_text("class ForbiddenTerm:\n    pass\n", encoding="utf-8")
            document = root / "docs/api.md"
            document.parent.mkdir()
            text = "Use `ForbiddenTerm`; ForbiddenTerm is the recommended prose.\n"
            document.write_text(text, encoding="utf-8")
            record = {
                "path": "docs/api.md",
                "kind": "code-identifier",
                "label": "Existing Python class reference.",
                "source": "https://github.com/example/project/blob/"
                + "a" * 40
                + "/source.py",
                "source_path": "source.py",
                "identifier": "ForbiddenTerm",
                "start_line": 1,
                "end_line": 1,
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
            }
            manifest = root / "scripts/prose_sources.json"
            manifest.parent.mkdir()
            manifest.write_text(json.dumps([record]), encoding="utf-8")
            result = self.run_text_cli(root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("docs/api.md:1", result.stdout)
            document.write_text("Use `ForbiddenTerm`.\n", encoding="utf-8")
            record["sha256"] = hashlib.sha256(
                document.read_text(encoding="utf-8").encode("utf-8")
            ).hexdigest()
            manifest.write_text(json.dumps([record]), encoding="utf-8")
            clean = self.run_text_cli(root)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            source.write_text("class OtherName:\n    pass\n", encoding="utf-8")
            result = self.run_text_cli(root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("not declared", result.stdout)

    def test_complete_pr_metadata_reaches_local_and_ci_edited_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
                capture_output=True,
                timeout=15,
            )
            self.commit_reference_fixture(root, "fixture")
            base = (
                subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=root, timeout=15
                )
                .decode()
                .strip()
            )
            payload = {
                "title": "docs: ForbiddenTerm",
                "body": "```text\n`ForbiddenTerm`\n```\n",
            }
            draft = root / "draft.json"
            draft.write_text(json.dumps(payload), encoding="utf-8")
            local = self.run_text_cli(root, "--pr-json", str(draft))
            self.assertEqual(local.returncode, 1, local.stdout + local.stderr)
            self.assertIn("PR title:1", local.stdout)
            self.assertIn("PR body:2", local.stdout)
            event = {
                "action": "edited",
                "pull_request": {"base": {"sha": base}, **payload},
            }
            ci = self.run_governance_workflow(root, "pull_request", event)
            self.assertEqual(ci.returncode, 1, ci.stdout + ci.stderr)
            self.assertIn("PR title:1", ci.stdout)
            self.assertIn("PR body:2", ci.stdout)
            event["pull_request"].update(title="docs: 更新文档", body="核实后的事实。")
            clean = self.run_governance_workflow(root, "pull_request", event)
            self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
            workflow = yaml.safe_load(
                (
                    Path(__file__).resolve().parents[2]
                    / ".github/workflows/docs-consistency.yml"
                ).read_text(encoding="utf-8")
            )
            triggers = workflow.get("on", workflow.get(True))
            self.assertIn("edited", triggers["pull_request"]["types"])

    def test_pr_schema_errors_fail_with_specific_diagnostics(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            path = root / "draft.json"
            for payload in (
                [],
                {"title": "title"},
                {"title": 1, "body": "body"},
                {"title": "title", "body": None},
            ):
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    result = self.run_text_cli(root, "--pr-json", str(path))
                    self.assertEqual(
                        result.returncode, 1, result.stdout + result.stderr
                    )
                    self.assertIn("string title and body", result.stdout)

    def test_pr_preserved_quote_markers_do_not_exempt_current_body_or_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root, _, _ = self.make_reference_repo(directory)
            metadata = {
                "kind": "test-counterexample",
                "label": "Preserved counterexample for review.",
                "source": "https://github.com/example/project/blob/"
                + "a" * 40
                + "/input.md",
                "sha256": hashlib.sha256(b"ForbiddenTerm\n").hexdigest(),
            }
            quote = (
                "<!-- mower-prose-source "
                + json.dumps(metadata)
                + " -->\nForbiddenTerm\n<!-- /mower-prose-source -->\n"
            )
            draft = root / "draft.json"
            draft.write_text(
                json.dumps({"title": "docs: 更新文档", "body": quote}), encoding="utf-8"
            )
            valid = self.run_text_cli(root, "--pr-json", str(draft))
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            draft.write_text(
                json.dumps(
                    {
                        "title": "docs: ForbiddenTerm",
                        "body": quote + "Current rule: ForbiddenTerm\n",
                    }
                ),
                encoding="utf-8",
            )
            current = self.run_text_cli(root, "--pr-json", str(draft))
            self.assertEqual(current.returncode, 1, current.stdout + current.stderr)
            self.assertIn("PR title:1", current.stdout)
            self.assertIn("PR body:4", current.stdout)
            self.assertNotIn("PR body:2", current.stdout)
            for body in (
                quote.replace("ForbiddenTerm\n", "Changed ForbiddenTerm\n"),
                quote.replace("<!-- /mower-prose-source -->", ""),
            ):
                with self.subTest(body=body):
                    draft.write_text(
                        json.dumps({"title": "docs: 更新文档", "body": body}),
                        encoding="utf-8",
                    )
                    invalid = self.run_text_cli(root, "--pr-json", str(draft))
                    self.assertEqual(
                        invalid.returncode, 1, invalid.stdout + invalid.stderr
                    )
                    self.assertIn("Invalid PR preserved source", invalid.stdout)


if __name__ == "__main__":
    unittest.main()
