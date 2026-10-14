"""发布说明的聚焦回归：虚拟 Git/API 数据，不联网或创建 Git 提交。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import changelog_generator as generator  # noqa: E402


def commit(name, subject, body="", parents=("0" * 40,), author="Author"):
    return {
        "hash": name * 40,
        "subject": subject,
        "body": body,
        "parents": list(parents),
        "author": author,
    }


def serialize(commits):
    return "".join(
        generator.SEP.join(
            [
                item["hash"],
                item["author"],
                f"{item['author']}@example.com",
                item["subject"],
                item["body"],
                " ".join(item["parents"]),
            ]
        )
        + generator.REC
        for item in commits
    )


def pull(sha, body, title="feat: 新增导出入口", number=17):
    return {
        "number": number,
        "title": title,
        "body": body,
        "merged_at": "2026-10-14T01:00:00Z",
        "merge_commit_sha": sha,
        "base": {"repo": {"full_name": "owner/repo"}},
    }


class ReleaseCollectionTests(unittest.TestCase):
    def collect(
        self, commits, *, branches=None, api=None, inverse=False, repo="owner/repo"
    ):
        branches = branches or {}

        def fake_git(*args):
            self.assertEqual(args[0], "log")
            self.assertIn("--topo-order", args)
            if "--first-parent" in args:
                self.assertEqual(args[-1], "base..HEAD")
                return serialize(commits)
            return serialize(branches[args[-1]])

        with (
            mock.patch.object(generator, "git", side_effect=fake_git),
            mock.patch.object(generator, "github_api_get", return_value=api) as api_get,
            mock.patch.object(
                generator, "inverse_changes_match", return_value=inverse
            ) as match,
        ):
            result = generator.collect_commits("base", repo)
        return result, api_get, match

    def test_squash_uses_final_pr_summary_instead_of_embedded_commit_notes(self):
        squashed = commit("a", "feat: 新增导出入口", "Changelog: 中间版本说明。")
        final = "支持批量导出。"
        body = "## Summary\n\nChangelog: " + final + "\n\n" + "详细审阅材料。\n" * 1000
        result, api, _ = self.collect([squashed], api=[pull(squashed["hash"], body)])
        self.assertEqual(
            [(item["desc"], item["category"]) for item in result], [(final, "feat")]
        )
        self.assertEqual(result[0]["number"], 17)
        self.assertIn("/commits/" + squashed["hash"] + "/pulls", api.call_args.args[0])

    def test_merge_summary_replaces_branch_entries_and_preserves_contributors(self):
        first = commit("a", "feat: 新增入口", author="First")
        second = commit("b", "fix: 修复入口", parents=(first["hash"],), author="Second")
        merged = commit(
            "c",
            f"Merge pull request {chr(35)}17 from branch",
            parents=("0" * 40, second["hash"]),
        )
        result, api, _ = self.collect(
            [merged],
            branches={
                merged["hash"] + "^1.." + merged["hash"]: [merged, second, first]
            },
            api=pull(merged["hash"], "Changelog: 支持批量导出。"),
        )
        self.assertEqual([item["desc"] for item in result], ["支持批量导出。"])
        self.assertTrue(api.call_args.args[0].endswith("/pulls/17"))
        with (
            mock.patch.object(generator, "release_date", return_value="2026-10-14"),
            mock.patch.object(
                generator,
                "resolve_logins",
                side_effect=[["second"], ["first", "SECOND"]],
            ),
        ):
            rendered = generator.render_release_body(
                "v1.0.0", "owner/repo", "base", result
            )
        self.assertEqual(rendered.count("- 支持批量导出。"), 1)
        self.assertIn("@second @first", rendered)
        self.assertNotIn("@SECOND", rendered)

    def test_old_merge_without_summary_keeps_legacy_branch_titles(self):
        first = commit("a", "feat: 新增入口")
        second = commit("b", "fix: 修复入口", parents=(first["hash"],))
        merged = commit("c", "Merge branch", parents=("0" * 40, second["hash"]))
        result, _, _ = self.collect(
            [merged],
            branches={
                merged["hash"] + "^1.." + merged["hash"]: [merged, second, first]
            },
            api=[],
        )
        self.assertEqual([item["desc"] for item in result], ["修复入口", "新增入口"])

    def test_marked_merge_can_fall_back_to_its_git_body(self):
        first = commit("a", "feat: 中间版本")
        merged = commit(
            "c",
            "feat: 新增入口",
            "Changelog: 新增导出入口。",
            ("0" * 40, first["hash"]),
        )
        result, _, _ = self.collect(
            [merged],
            branches={merged["hash"] + "^1.." + merged["hash"]: [merged, first]},
            api=None,
        )
        self.assertEqual([item["desc"] for item in result], ["新增导出入口。"])

    def test_api_failure_and_invalid_prs_keep_git_fallback(self):
        item = commit("a", "fix: 修复入口", "Changelog: 修复导出入口。")
        wrong_sha = pull("b" * 40, "Changelog: 不属于本提交。")
        wrong_repo = pull(item["hash"], "Changelog: 不属于本仓库。")
        wrong_repo["base"]["repo"]["full_name"] = "other/repo"
        open_pr = pull(item["hash"], "Changelog: 尚未合并。")
        open_pr["merged_at"] = None
        for api in (
            None,
            [wrong_sha],
            [wrong_repo],
            [open_pr],
            [pull(item["hash"], "")],
        ):
            with self.subTest(api=api):
                result, _, _ = self.collect([item], api=api)
                self.assertEqual(
                    [entry["desc"] for entry in result], ["修复导出入口。"]
                )

    def test_duplicate_pr_summaries_and_ambiguous_association_use_title(self):
        item = commit("a", "fix: 修复入口")
        for api in (
            [pull(item["hash"], "Changelog: 第一段。\n\nChangelog: 第二段。")],
            [
                pull(item["hash"], "Changelog: 第一段。"),
                pull(item["hash"], "Changelog: 第二段。", number=18),
            ],
        ):
            with self.subTest(api=api):
                result, _, _ = self.collect([item], api=api)
                self.assertEqual([entry["desc"] for entry in result], ["修复入口"])

    def test_skip_rules_remain_effective_with_pr_summaries(self):
        for item in (
            commit("a", "build: 更新构建"),
            commit("a", "fix: 修复入口", "[skip changelog]"),
        ):
            with self.subTest(item=item):
                result, api, _ = self.collect(
                    [item], api=[pull(item["hash"], "Changelog: 无需发布。")]
                )
                self.assertEqual(result, [])
                api.assert_not_called()

    def test_complete_revert_in_range_cancels_both_entries(self):
        original = commit("a", "feat: 新增入口")
        undo = commit(
            "b",
            "revert: 撤销入口",
            f"This reverts commit {original['hash']}.",
            (original["hash"],),
        )
        result, api, match = self.collect([undo, original], inverse=True)
        self.assertEqual(result, [])
        api.assert_not_called()
        self.assertEqual(match.call_args.args[0]["hash"], original["hash"])

    def test_revert_of_revert_restores_original_entry(self):
        original = commit("a", "feat: 新增入口")
        undo = commit(
            "b",
            "revert: 撤销入口",
            f"This reverts commit {original['hash']}.",
            (original["hash"],),
        )
        restored = commit(
            "c",
            "revert: 恢复入口",
            f"This reverts commit {undo['hash']}.",
            (undo["hash"],),
        )
        result, _, _ = self.collect([restored, undo, original], inverse=True, repo="")
        self.assertEqual([item["desc"] for item in result], ["新增入口"])

    def test_revert_of_published_change_is_retained(self):
        undo = commit("b", "revert: 移除旧入口", f"This reverts commit {'a' * 40}.")
        result, _, match = self.collect([undo], repo="")
        self.assertEqual([item["desc"] for item in result], ["移除旧入口"])
        match.assert_not_called()

    def test_standard_git_revert_is_other_even_when_target_title_contains_feature(self):
        undo = commit(
            "b", 'Revert "feat: 新增入口"', f"This reverts commit {'a' * 40}."
        )
        result, _, _ = self.collect([undo], repo="")
        self.assertEqual(result[0]["category"], "other")
        self.assertEqual(result[0]["desc"], undo["subject"])

    def test_unconfirmed_or_partial_revert_is_not_silently_removed(self):
        original = commit("a", "feat: 新增入口")
        undo = commit(
            "b",
            "revert: 部分撤销入口",
            f"This reverts commit {original['hash']}.",
            (original["hash"],),
        )
        result, _, _ = self.collect([undo, original], inverse=False, repo="")
        self.assertEqual(
            [item["desc"] for item in result], ["部分撤销入口", "新增入口"]
        )

    def test_reverting_merge_removes_its_imported_branch_entries(self):
        first = commit("a", "feat: 新增入口")
        merged = commit("c", "Merge branch", parents=("0" * 40, first["hash"]))
        undo = commit(
            "d",
            "revert: 撤销合并",
            f"This reverts commit {merged['hash']}.",
            (merged["hash"],),
        )
        result, _, _ = self.collect(
            [undo, merged],
            branches={merged["hash"] + "^1.." + merged["hash"]: [merged, first]},
            inverse=True,
        )
        self.assertEqual(result, [])

    def test_reverts_merged_through_another_pr_cancel_the_two_mainline_changes(self):
        first = commit("a", "feat: 新增入口")
        merged = commit("c", "Merge branch", parents=("0" * 40, first["hash"]))
        undo = commit(
            "b",
            "revert: 撤销入口",
            f"This reverts commit {first['hash']}.",
            (merged["hash"],),
        )
        undo_merge = commit("d", "Merge branch", parents=(merged["hash"], undo["hash"]))
        result, _, match = self.collect(
            [undo_merge, merged],
            inverse=True,
            branches={
                merged["hash"] + "^1.." + merged["hash"]: [merged, first],
                undo_merge["hash"] + "^1.." + undo_merge["hash"]: [undo_merge, undo],
            },
        )
        self.assertEqual(result, [])
        self.assertEqual(
            [item["hash"] for item in match.call_args.args],
            [merged["hash"], undo_merge["hash"]],
        )


class DescriptionAndPersistenceTests(unittest.TestCase):
    def test_pr_summary_ignores_examples_and_stops_at_next_heading(self):
        body = "<!-- Changelog: 注释 -->\nChangelog: 新增入口。\n## Summary\n详细解释\n```text\nChangelog: 示例\n```"
        self.assertEqual(generator.extract_pr_changelog(body), "新增入口。")
        self.assertIsNone(
            generator.extract_pr_changelog("```text\nChangelog: 示例\n```")
        )
        self.assertIsNone(
            generator.extract_pr_changelog("Changelog:\n\n## Summary\n解释")
        )
        self.assertEqual(
            generator.extract_changelog_entry(
                "Changelog: 新增入口。\n  ## 验证\n检查记录"
            ),
            "新增入口。",
        )

    def test_inverse_comparison_preserves_patch_position_whitespace_and_binary_content(
        self,
    ):
        original = {"hash": "a" * 40, "parents": ["0" * 40]}
        undo = {"hash": "b" * 40, "parents": [original["hash"]]}
        patch = b"diff --git a/file b/file\nindex 111..222\n--- a/file\n+++ b/file\n@@ -2 +2 @@\n-new\n+old\n"
        same = patch.replace(b"111..222", b"333..444")
        for actual, expected in (
            (same, True),
            (same.replace(b"+old", b"+ old"), False),
            (same.replace(b"-2 +2", b"-3 +3"), False),
            (same + b"GIT binary patch\nliteral 1\nA\n", False),
        ):
            with self.subTest(expected=expected, actual=actual):
                responses = [
                    subprocess.CompletedProcess([], 0, stdout=patch),
                    subprocess.CompletedProcess([], 0, stdout=actual),
                ]
                with mock.patch.object(
                    generator.subprocess, "run", side_effect=responses
                ) as run:
                    self.assertEqual(
                        generator.inverse_changes_match(original, undo), expected
                    )
                self.assertEqual(
                    run.call_args_list[0].args[0][-2:], [original["hash"], "0" * 40]
                )
                self.assertEqual(
                    run.call_args_list[1].args[0][-2:], [original["hash"], undo["hash"]]
                )

    def test_main_reads_summary_then_freezes_saved_release_body(self):
        squashed = commit("a", "feat: 新增导出入口", "Changelog: 中间版本说明。")
        final = "支持批量导出。"
        pr = pull(
            squashed["hash"], "## Summary\n\nChangelog: " + final + "\n\n原因和方案。"
        )
        with tempfile.TemporaryDirectory() as scratch:
            saved = Path(scratch) / "CHANGELOG.md"
            previous = "## 0.9.0\n\n- 旧版本\n"
            saved.write_text("# CHANGELOG\n\n" + previous, encoding="utf-8")
            out = Path(scratch) / "body.md"
            argv = [
                "generator",
                "--tag",
                "v1.0.0",
                "--repo",
                "owner/repo",
                "--out",
                str(out),
                "--prepend-to",
                str(saved),
            ]
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(generator, "find_base_tag", return_value="v0.9.0"),
                mock.patch.object(generator, "git", return_value=serialize([squashed])),
                mock.patch.object(
                    generator, "github_api_get", return_value=[pr]
                ) as api,
                mock.patch.object(generator, "resolve_logins", return_value=[]),
                mock.patch.object(generator, "release_date", return_value="2026-10-14"),
            ):
                generator.main()
            generated = out.read_text(encoding="utf-8")
            self.assertIn(final, generated)
            self.assertNotIn("中间版本说明", generated)
            self.assertNotIn("原因和方案", generated)
            self.assertIn(previous, saved.read_text(encoding="utf-8"))
            self.assertEqual(
                api.call_args.args[0],
                f"https://api.github.com/repos/owner/repo/commits/{squashed['hash']}/pulls?per_page=100",
            )
            before = saved.read_bytes()
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    generator, "git", side_effect=AssertionError("Git read")
                ),
                mock.patch.object(
                    generator, "github_api_get", side_effect=AssertionError("PR read")
                ),
            ):
                generator.main()
            self.assertEqual(out.read_text(encoding="utf-8"), generated)
            self.assertEqual(saved.read_bytes(), before)

    def test_main_reuses_saved_version_without_git_or_pr_reads(self):
        with tempfile.TemporaryDirectory() as scratch:
            saved = Path(scratch) / "CHANGELOG.md"
            block = "## 1.0.0 - 2026-10-14\n\n- 已确认的发布内容\n"
            saved.write_text(
                "# CHANGELOG\n\n" + block + "\n## 0.9.0\n\n- 旧版本\n", encoding="utf-8"
            )
            out = Path(scratch) / "body.md"
            argv = [
                "generator",
                "--tag",
                "v1.0.0",
                "--repo",
                "owner/repo",
                "--out",
                str(out),
                "--prepend-to",
                str(saved),
            ]
            before = saved.read_bytes()
            with (
                mock.patch.object(sys, "argv", argv),
                mock.patch.object(
                    generator, "git", side_effect=AssertionError("unexpected Git read")
                ),
                mock.patch.object(
                    generator,
                    "github_api_get",
                    side_effect=AssertionError("unexpected PR read"),
                ),
            ):
                generator.main()
            self.assertEqual(out.read_text(encoding="utf-8"), block)
            self.assertEqual(saved.read_bytes(), before)

    def test_version_prefix_does_not_reuse_another_release(self):
        with tempfile.TemporaryDirectory() as scratch:
            saved = Path(scratch) / "CHANGELOG.md"
            saved.write_text(
                "# CHANGELOG\n\n## 1.0.0-alpha.20\n\n- 其他版本\n", encoding="utf-8"
            )
            self.assertIsNone(generator.existing_release_block(saved, "v1.0.0-alpha.2"))
