import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

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
            _, sidecar, metadata = self.make_reference_repo(
                tmpdir, slug="2026-10-08-new-decision"
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


if __name__ == "__main__":
    unittest.main()
