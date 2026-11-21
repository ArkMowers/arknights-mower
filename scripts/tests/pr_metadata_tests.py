import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALID = {
    "title": "fix(report): 修复灰色订单数漏读",
    "body": "## Summary（改动与方案）\n\n**订单数：** 扩展灰字色相范围。\n\n"
    "## Evidence（验证与评审）\n\n**订单数：** 给定离线样本读出 37，实机未验证。\n\n"
    "## Merge Danger（影响与回退）\n\n**恢复：** 回退代码，历史 CSV 另行核对。\n",
}


class PRMetadataTests(unittest.TestCase):
    def run_cli(self, directory, payload, *, governance=False, action=None):
        directory = Path(directory)
        context = directory / "CONTEXT.md"
        context.write_text(
            "### Field\n- **_Avoid_**: `ForbiddenTerm`\n", encoding="utf-8"
        )
        (directory / ".agents/notes").mkdir(parents=True, exist_ok=True)
        (directory / "CODING_STANDARDS.md").write_text(
            "### Offline Checking\nChecks report their verified scope.\n",
            encoding="utf-8",
        )
        draft = directory / "draft.json"
        draft.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        if governance:
            command = [
                sys.executable,
                str(ROOT / "scripts/verify_governance.py"),
                "--repo-root",
                str(directory),
            ]
            if action:
                if not (directory / ".git").exists():
                    subprocess.run(
                        ["git", "init", "-q"],
                        cwd=directory,
                        check=True,
                        capture_output=True,
                    )
                    subprocess.run(
                        [
                            "git",
                            "-c",
                            "user.name=Test",
                            "-c",
                            "user.email=test@example.invalid",
                            "-c",
                            "core.hooksPath=",
                            "-c",
                            "commit.gpgsign=false",
                            "commit",
                            "--allow-empty",
                            "-qm",
                            "fixture",
                        ],
                        cwd=directory,
                        check=True,
                        capture_output=True,
                    )
                sha = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=directory, text=True
                ).strip()
                event = directory / "event.json"
                event.write_text(
                    json.dumps(
                        {
                            "action": action,
                            "pull_request": {"base": {"sha": sha}, **payload},
                        }
                    ),
                    encoding="utf-8",
                )
                environment = {
                    **os.environ,
                    "GITHUB_EVENT_NAME": "pull_request",
                    "GITHUB_EVENT_PATH": str(event),
                    "PYTHONIOENCODING": "utf-8",
                }
                command += ["--ci"]
            else:
                environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
                command += ["--pr-json", str(draft)]
        else:
            command = [
                sys.executable,
                str(ROOT / "scripts/verify_pr_metadata.py"),
                "--context-file",
                str(context),
                "--pr-json",
                str(draft),
            ]
            environment = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        return subprocess.run(
            command,
            cwd=directory,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=30,
        )

    def test_publishable_small_change_passes_local_and_governance_entry(self):
        for governance in (False, True):
            with (
                self.subTest(governance=governance),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = self.run_cli(directory, VALID, governance=governance)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_format_and_placeholder_fail_at_publication_entry(self):
        cases = [
            ({"title": "修改", "body": ""}, "type(scope)"),
            ({**VALID, "title": "fix(报告): 修复订单数漏读"}, "English"),
            ({**VALID, "title": "fix(report): 修复订单数漏读。"}, "final period"),
            (
                {
                    **VALID,
                    "body": VALID["body"].replace(
                        "给定离线样本读出 37，实机未验证。", "〈结果〉"
                    ),
                },
                "placeholder",
            ),
            ({**VALID, "body": "修复订单数，离线验证通过。"}, "Summary, Evidence"),
            (
                {
                    **VALID,
                    "body": VALID["body"].replace(
                        "## Evidence（验证与评审）", "## Summary"
                    ),
                },
                "once",
            ),
            (
                {
                    **VALID,
                    "body": VALID["body"].replace(
                        "**订单数：** 给定离线样本读出 37，实机未验证。",
                        "<!-- 尚未填写 -->",
                    ),
                },
                "explanatory text",
            ),
            ({**VALID, "body": VALID["body"] + "\n## Evidence\n重复结果。"}, "once"),
            ({**VALID, "title": "fix(report): Correct order counts"}, "Chinese"),
        ]
        for payload, diagnostic in cases:
            with (
                self.subTest(payload=payload),
                tempfile.TemporaryDirectory() as directory,
            ):
                result = self.run_cli(directory, payload)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn(diagnostic, result.stdout)

    def test_scope_remains_optional_for_a_valid_title(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_cli(directory, {**VALID, "title": "fix: 修复订单数漏读"})
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_example_headings_do_not_replace_real_sections(self):
        for opening, closing in (("```text", "```"), ("~~~~", "~~~~"), ("<!--", "-->")):
            with (
                self.subTest(opening=opening),
                tempfile.TemporaryDirectory() as directory,
            ):
                payload = {
                    **VALID,
                    "body": opening + "\n" + VALID["body"] + closing + "\n",
                }
                result = self.run_cli(directory, payload)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("Summary, Evidence", result.stdout)

    def test_examples_inside_valid_sections_and_comment_hints_are_allowed(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = {
                **VALID,
                "body": "<!-- 说明 -->\n"
                + VALID["body"].replace(
                    "扩展灰字色相范围。",
                    "扩展灰字色相范围。\n```text\n## Evidence\n〈示例内容〉\n```\n",
                ),
            }
            result = self.run_cli(directory, payload)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_edited_event_rejects_bad_metadata_and_accepts_corrected_same_head(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = self.run_cli(
                directory, {**VALID, "body": ""}, governance=True, action="edited"
            )
            self.assertEqual(invalid.returncode, 1, invalid.stdout + invalid.stderr)
            self.assertIn("Summary, Evidence", invalid.stdout)
            corrected = self.run_cli(directory, VALID, governance=True, action="edited")
            self.assertEqual(
                corrected.returncode, 0, corrected.stdout + corrected.stderr
            )

    def test_body_is_data_and_terminology_is_checked_inside_examples(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel = Path(directory) / "must-not-exist"
            body = (
                VALID["body"] + f"\n$(touch {sentinel})\n```text\nForbiddenTerm\n```\n"
            )
            result = self.run_cli(directory, {**VALID, "body": body})
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("ForbiddenTerm", result.stdout)
            self.assertFalse(sentinel.exists())


if __name__ == "__main__":
    unittest.main()
