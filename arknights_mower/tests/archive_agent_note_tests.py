"""Offline transition checks for bilingual decisions and historical triplets."""

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".agents/skills/mower-archive-agent-notes/scripts/archive_note.py"
)
SPEC = importlib.util.spec_from_file_location("archive_agent_note", SCRIPT)
archive_note = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(archive_note)


class ArchiveAgentNoteTests(unittest.TestCase):
    slug = "2026-10-11-transition-example"

    def make_record(self, root, *, decision=True):
        directory = Path(root) / ".agents/notes/proposed/feature"
        directory.mkdir(parents=True)
        marker = "format: decision\n" if decision else ""
        for extension, title in ((".md", "Example"), (".zh.md", "示例")):
            (directory / f"{self.slug}{extension}").write_text(
                f"---\n{marker}title: {title}\nstatus: 'proposed'\n"
                "category: feature\ndate: 2026-10-11\n---\n\n"
                "Body keeps its example:\n```yaml\nstatus: proposed\n```\n",
                encoding="utf-8",
            )
        if not decision:
            (directory / f"{self.slug}.sidecar.json").write_text(
                json.dumps(
                    {
                        "title": "Example",
                        "status": "proposed",
                        "category": "feature",
                        "date": "2026-10-11",
                        "authors": ["Tester"],
                        "invariants": [],
                        "code_symbols": [],
                        "test_suites": [],
                    }
                ),
                encoding="utf-8",
            )
        return directory

    def assert_rejected_without_moves(self, source, target, error):
        before = {path.name: path.read_bytes() for path in source.iterdir()}
        with self.assertRaises(error):
            archive_note.transition_triplet(source / self.slug, target)
        self.assertEqual(
            before, {path.name: path.read_bytes() for path in source.iterdir()}
        )

    def test_cli_transitions_pair_and_preserves_body_in_both_languages(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_record(temporary)
            result = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(SCRIPT),
                    str(source / f"{self.slug}.zh.md"),
                    "--to",
                    "implemented",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            target = source.parent.parent / "implemented/feature"
            self.assertEqual(
                sorted(path.name for path in target.iterdir()),
                [f"{self.slug}.md", f"{self.slug}.zh.md"],
            )
            for extension in (".md", ".zh.md"):
                content = (target / f"{self.slug}{extension}").read_text(
                    encoding="utf-8"
                )
                self.assertIn("status: implemented", content.split("---", 2)[1])
                self.assertIn("```yaml\nstatus: proposed\n```", content)
                self.assertFalse((source / f"{self.slug}{extension}").exists())

    def test_pair_can_transition_to_archived_or_rejected(self):
        for lifecycle in ("archived", "rejected"):
            with (
                self.subTest(lifecycle=lifecycle),
                tempfile.TemporaryDirectory() as temporary,
            ):
                source = self.make_record(temporary)
                archive_note.transition_triplet(source / self.slug, lifecycle)
                target = source.parent.parent / lifecycle / "feature"
                for extension in (".md", ".zh.md"):
                    fields = archive_note.note_frontmatter(
                        target / f"{self.slug}{extension}"
                    )
                    self.assertEqual(fields["status"], lifecycle)

    def test_legacy_transition_keeps_sidecar_and_updates_its_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_record(temporary, decision=False)
            archive_note.transition_triplet(
                source / f"{self.slug}.sidecar.json", "implemented"
            )
            target = source.parent.parent / "implemented/feature"
            self.assertEqual(len(list(target.iterdir())), 3)
            sidecar = json.loads(
                (target / f"{self.slug}.sidecar.json").read_text(encoding="utf-8")
            )
            self.assertEqual(sidecar["status"], "implemented")
            self.assertEqual(sidecar["authors"], ["Tester"])

    def test_decision_marker_rejects_legacy_sidecar_even_when_it_is_malformed(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_record(temporary)
            (source / f"{self.slug}.sidecar.json").write_text(
                "broken", encoding="utf-8"
            )
            self.assert_rejected_without_moves(source, "implemented", ValueError)

    def test_pair_requires_matching_markers_and_valid_source_frontmatter(self):
        mutations = (
            ("format: decision\n", ""),
            ("format: decision", "format: other"),
            ("title: 示例", "title:"),
            ("status: 'proposed'", "status: implemented"),
            ("category: feature", "category: process"),
            ("date: 2026-10-11", "date: 2026-10-10"),
        )
        for original, replacement in mutations:
            with (
                self.subTest(original=original),
                tempfile.TemporaryDirectory() as temporary,
            ):
                source = self.make_record(temporary)
                chinese = source / f"{self.slug}.zh.md"
                chinese.write_text(
                    chinese.read_text(encoding="utf-8").replace(original, replacement),
                    encoding="utf-8",
                )
                self.assert_rejected_without_moves(source, "implemented", ValueError)

    def test_missing_pair_language_or_legacy_sidecar_does_not_downgrade_format(self):
        for decision, extension in ((True, ".zh.md"), (False, ".sidecar.json")):
            with (
                self.subTest(decision=decision),
                tempfile.TemporaryDirectory() as temporary,
            ):
                source = self.make_record(temporary, decision=decision)
                (source / f"{self.slug}{extension}").unlink()
                self.assert_rejected_without_moves(
                    source, "implemented", FileNotFoundError
                )

    def test_pair_checks_all_target_artifacts_before_moving(self):
        for extension in (".md", ".zh.md", ".sidecar.json"):
            with (
                self.subTest(extension=extension),
                tempfile.TemporaryDirectory() as temporary,
            ):
                source = self.make_record(temporary)
                target = source.parent.parent / "implemented/feature"
                target.mkdir(parents=True)
                existing = target / f"{self.slug}{extension}"
                existing.write_text("existing", encoding="utf-8")
                self.assert_rejected_without_moves(
                    source, "implemented", FileExistsError
                )
                self.assertEqual(existing.read_text(encoding="utf-8"), "existing")

    def test_same_state_preserves_files_and_remains_a_no_op(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_record(temporary)
            before = {path.name: path.read_bytes() for path in source.iterdir()}
            archive_note.transition_triplet(source / self.slug, "proposed")
            self.assertEqual(
                before, {path.name: path.read_bytes() for path in source.iterdir()}
            )
            archive_note.transition_triplet(source / "2026-10-11-missing", "proposed")

    def test_paths_outside_note_layout_are_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = self.make_record(temporary)
            for path in (
                Path(temporary) / "proposed/feature" / self.slug,
                source.parent / "unknown" / self.slug,
                source / "unexpected-name",
            ):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    archive_note.transition_triplet(path, "implemented")
            self.assertEqual(len(list(source.iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
