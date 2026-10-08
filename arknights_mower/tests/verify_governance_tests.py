import importlib.util
import io
import json
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
        self.assertIn("AUTOMATED CHECKS PASSED", report)
        self.assertIn("note formats, relative Markdown links and Avoid terms", report)
        self.assertIn("Manual review", report)
        self.assertIn(
            "concept changes, document placement and glossary approval", report
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
                self.assertNotIn("AUTOMATED CHECKS PASSED", output.getvalue())
                for mocked_check in mocked_checks:
                    mocked_check.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
