"""发布说明的聚焦回归：虚拟 Git/API 数据，不联网或创建 Git 提交。"""

import contextlib
import copy
import io
import json
import os
import re
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


def associated_response(sha, pulls=(), *, has_next=False, total=None):
    nodes = [
        {
            "number": item["number"],
            "title": item["title"],
            "body": item["body"],
            "mergedAt": item["merged_at"],
            "mergeCommit": {"oid": item["merge_commit_sha"]},
            "changedFiles": item.get("changed_files", 1),
            "baseRepository": {"nameWithOwner": item["base"]["repo"]["full_name"]},
        }
        for item in pulls
    ]
    return {
        "data": {
            "repository": {
                "object": {
                    "oid": sha,
                    "associatedPullRequests": {
                        "totalCount": len(nodes) if total is None else total,
                        "nodes": nodes,
                        "pageInfo": {"hasNextPage": has_next},
                    },
                }
            }
        }
    }


class RebaseCollectionTests(unittest.TestCase):
    """真实临时 Git 历史经 collect_commits 进入 API 关联与撤销路径。"""

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.previous = Path.cwd()
        os.chdir(self.scratch.name)
        self.addCleanup(os.chdir, self.previous)
        self.run_git("init", "--quiet")
        self.run_git("config", "user.name", "Author")
        self.run_git("config", "user.email", "author@users.noreply.github.com")
        self.run_git("config", "commit.gpgsign", "false")
        self.base = self.add_commit("chore: 初始版本", "base", "base\n")
        self.responses = {}
        self.pr_files = {}
        self.pr_diffs = {}
        self.api_calls = []

    def run_git(self, *args):
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        ).stdout.strip()

    def add_commit(self, subject, filename=None, content="", body="", author="author"):
        if filename is not None:
            Path(filename).write_text(content, encoding="utf-8")
            self.run_git("add", filename)
        self.run_git(
            "-c",
            f"user.name={author}",
            "-c",
            f"user.email={author}@users.noreply.github.com",
            "commit",
            "--quiet",
            "--allow-empty",
            "-m",
            subject,
            "-m",
            body,
        )
        return self.run_git("rev-parse", "HEAD")

    def associate(
        self, commits, *, body="Changelog: 支持批量导出。", title="feat: 支持批量导出"
    ):
        pr = pull(commits[-1], body, title)
        # 原 PR 的提交数和 SHA 不参与实际主线的成员确认。
        pr["commits"] = 91
        pr["head"] = {"sha": "f" * 40}
        before = self.run_git("rev-parse", commits[0] + "^")
        files = []
        for filename in self.run_git(
            "diff", "--name-only", before, commits[-1]
        ).splitlines():
            patch = self.run_git(
                "diff",
                "--no-renames",
                "--unified=3",
                before,
                commits[-1],
                "--",
                filename,
            )
            start = patch.find("\n@@ ")
            additions, deletions, _ = self.run_git(
                "diff", "--numstat", before, commits[-1], "--", filename
            ).split("\t", 2)
            files.append(
                {
                    "filename": filename,
                    "status": "added"
                    if not self.run_git("ls-tree", before, "--", filename)
                    else "modified",
                    "sha": self.run_git("rev-parse", commits[-1] + ":" + filename),
                    "patch": patch[start + 1 :] if start >= 0 else None,
                    "additions": int(additions),
                    "deletions": int(deletions),
                }
            )
        pr["changed_files"] = len(files)
        self.pr_files[pr["number"]] = files
        self.pr_diffs[pr["number"]] = self.run_git(
            "diff", "--no-renames", "--unified=3", before, commits[-1]
        )
        for sha in commits:
            self.responses[sha] = associated_response(sha, [pr])
        return pr

    def query(self, query, variables):
        self.api_calls.append(variables["sha"])
        return copy.deepcopy(
            self.responses.get(variables["sha"], associated_response(variables["sha"]))
        )

    def collect(self, base=None):
        with (
            mock.patch.object(
                generator, "github_graphql", side_effect=self.query, create=True
            ),
            mock.patch.object(generator, "github_api_get", side_effect=self.rest),
        ):
            return generator.collect_commits(base or self.base, "owner/repo")

    def rest(self, url, **kwargs):
        if kwargs.get("as_text"):
            number = int(url.rsplit("/", 1)[1])
            return self.pr_diffs.get(number)
        if "/files?" in url:
            number = int(url.split("/pulls/")[1].split("/")[0])
            return copy.deepcopy(self.pr_files.get(number, []))
        if "/commits/" in url and "/pulls?" in url:
            sha = url.split("/commits/", 1)[1].split("/", 1)[0]
            response = self.responses.get(sha)
            if not isinstance(response, dict):
                return None
            nodes = response["data"]["repository"]["object"]["associatedPullRequests"][
                "nodes"
            ]
            return [
                pull(
                    item["mergeCommit"]["oid"],
                    item["body"],
                    item["title"],
                    item["number"],
                )
                for item in nodes
            ]
        return []

    def make_pair(self, *, tail="fix: 修复导出文件名"):
        first = self.add_commit(
            "feat: 新增导出入口", "first", "entry\n", author="first"
        )
        second = self.add_commit(tail, "second", "names\n", author="second")
        self.associate([first, second])
        return first, second

    def test_direct_commits_use_body_then_title_without_pr(self):
        self.add_commit(
            "fix: 修复目录", "first", "directory\n", "Changelog: 修复导出目录。"
        )
        self.add_commit("feat: 新增导出入口", "second", "entry\n")
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["新增导出入口", "修复导出目录。"],
        )

    def test_single_rebase_or_squash_uses_pr_summary_and_checks_predecessor(self):
        sha = self.add_commit(
            "feat: 中间版本", "first", "entry\n", "Changelog: 中间说明。"
        )
        self.associate([sha])
        self.assertEqual([item["desc"] for item in self.collect()], ["支持批量导出。"])
        self.assertIn(self.base, self.api_calls)

    def test_multiple_rebased_commits_emit_once_and_keep_all_authors(self):
        first, second = self.make_pair()
        entries = self.collect()
        self.assertEqual([item["desc"] for item in entries], ["支持批量导出。"])
        self.assertEqual(
            {item["hash"] for item in entries[0]["contributor_commits"]},
            {first, second},
        )
        with mock.patch.object(generator, "github_api_get", return_value=None):
            rendered = generator.render_release_body(
                "v1.0.0", "owner/repo", self.base, entries
            )
        self.assertIn("@first", rendered)
        self.assertIn("@second", rendered)

    def test_ci_tail_is_grouped_before_commit_filtering(self):
        self.make_pair(tail="ci: 调整导出测试")
        self.assertEqual([item["desc"] for item in self.collect()], ["支持批量导出。"])

    def test_actual_parent_chain_ignores_original_commit_count_and_dropped_empty_commit(
        self,
    ):
        first, second = self.make_pair()
        self.assertNotEqual(
            self.responses[first]["data"]["repository"]["object"]["oid"], "f" * 40
        )
        self.assertEqual([item["hash"] for item in self.collect()], [second])

    def test_missing_middle_association_does_not_apply_tail_summary(self):
        first = self.add_commit("feat: 新增导出入口", "first", "entry\n")
        middle = self.add_commit("fix: 修复导出目录", "middle", "directory\n")
        last = self.add_commit("fix: 修复导出文件名", "last", "names\n")
        self.associate([first, middle, last])
        self.responses[middle] = None
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["修复导出文件名", "修复导出目录", "新增导出入口"],
        )

    def test_missing_first_association_for_same_file_cannot_prove_complete_group(self):
        Path("shared").write_text(
            "one\ntwo\nthree\nfour\nfive\nsix\n", encoding="utf-8"
        )
        self.run_git("add", "shared")
        self.run_git("commit", "--quiet", "-m", "chore: 保存初始文件")
        self.base = self.run_git("rev-parse", "HEAD")
        first = self.add_commit(
            "feat: 修改首行", "shared", "first\ntwo\nthree\nfour\nfive\nsix\n"
        )
        second = self.add_commit(
            "fix: 修改末行", "shared", "first\ntwo\nthree\nfour\nfive\nlast\n"
        )
        self.associate([first, second])
        for response in (associated_response(first), None):
            with self.subTest(response=response):
                self.responses[first] = response
                self.assertEqual(
                    [item["desc"] for item in self.collect()], ["修改末行", "修改首行"]
                )

    def test_empty_middle_association_and_non_contiguous_same_pr_use_commits(self):
        first = self.add_commit("feat: 新增入口", "first", "entry\n")
        middle = self.add_commit("fix: 修复目录", "middle", "directory\n")
        last = self.add_commit("fix: 修复文件名", "last", "name\n")
        self.associate([first, middle, last])
        self.responses[middle] = associated_response(middle)
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["修复文件名", "修复目录", "新增入口"],
        )

    def test_truncated_first_hunk_and_missing_first_association_fail_line_counts(self):
        lines = [f"line {index}\n" for index in range(100)]
        self.base = self.add_commit("chore: 保存初始文件", "shared", "".join(lines))
        lines[90] = "changed tail\n"
        first = self.add_commit("feat: 修改文件末尾", "shared", "".join(lines))
        lines[5] = "changed head\n"
        last = self.add_commit("fix: 修改文件开头", "shared", "".join(lines))
        self.associate([first, last])
        self.responses[first] = associated_response(first)
        file = self.pr_files[17][0]
        self.assertEqual((file["additions"], file["deletions"]), (2, 2))
        file["patch"] = file["patch"].split("\n@@ ", 1)[0]
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["修改文件开头", "修改文件末尾"],
        )

    def test_ambiguous_or_incomplete_api_response_uses_each_commit(self):
        first, second = self.make_pair()
        original = copy.deepcopy(self.responses[first])
        cases = [
            None,
            {"errors": [{"message": "denied"}], **original},
            associated_response(
                first, [pull(second, "Changelog: 支持导出。")], has_next=True
            ),
            associated_response(
                first, [pull(second, "Changelog: 支持导出。")], total=2
            ),
            associated_response(
                first,
                [
                    pull(second, "Changelog: 支持导出。"),
                    pull(second, "Changelog: 其他。", number=18),
                ],
            ),
        ]
        for response in cases:
            with self.subTest(response=response):
                self.responses[first] = response
                self.assertEqual(
                    [item["desc"] for item in self.collect()],
                    ["修复导出文件名", "新增导出入口"],
                )

    def test_wrong_repository_open_pr_and_wrong_terminal_sha_use_git(self):
        first, second = self.make_pair()
        for field in ("repository", "open", "anchor"):
            with self.subTest(field=field):
                pr = pull(second, "Changelog: 支持批量导出。")
                if field == "repository":
                    pr["base"]["repo"]["full_name"] = "other/repo"
                elif field == "open":
                    pr["merged_at"] = None
                else:
                    pr["merge_commit_sha"] = "f" * 40
                for sha in (first, second):
                    self.responses[sha] = associated_response(sha, [pr])
                self.assertEqual(
                    [item["desc"] for item in self.collect()],
                    ["修复导出文件名", "新增导出入口"],
                )

    def test_base_cutting_pr_and_head_before_terminal_sha_use_commits(self):
        first, second = self.make_pair()
        self.assertEqual(
            [item["desc"] for item in self.collect(first)], ["修复导出文件名"]
        )
        self.run_git("checkout", "--quiet", "--detach", first)
        self.assertEqual([item["desc"] for item in self.collect()], ["新增导出入口"])

    def test_unavailable_predecessor_prevents_partial_group_summary(self):
        self.make_pair()
        self.responses[self.base] = None
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["修复导出文件名", "新增导出入口"],
        )

    def test_missing_truncated_or_inconsistent_pr_file_evidence_uses_commits(self):
        self.make_pair()
        original = copy.deepcopy(self.pr_files[17])
        cases = []
        for field, value in (
            ("patch", None),
            ("patch", "@@ -0,0 +1 @@\n+incomplete"),
            ("sha", "f" * 40),
            ("status", "renamed"),
        ):
            files = copy.deepcopy(original)
            files[0][field] = value
            cases.append(files)
        cases.extend((original[:1], [original[0], original[0]]))
        for files in cases:
            with self.subTest(files=files):
                self.pr_files[17] = files
                self.assertEqual(
                    [item["desc"] for item in self.collect()],
                    ["修复导出文件名", "新增导出入口"],
                )

    def test_file_pagination_failure_and_api_limit_do_not_claim_complete_pr(self):
        first, second = self.make_pair()
        for sha in (first, second):
            self.responses[sha]["data"]["repository"]["object"][
                "associatedPullRequests"
            ]["nodes"][0]["changedFiles"] = 101
        called = []

        def paged(url, **kwargs):
            called.append(url)
            if url.endswith("page=1"):
                return [copy.deepcopy(self.pr_files[17][0]) for _ in range(100)]
            return None

        with mock.patch.object(self, "rest", side_effect=paged):
            self.assertEqual(len(self.collect()), 2)
        self.assertEqual(len(called), 2)
        self.assertTrue(called[-1].endswith("page=2"))
        for sha in (first, second):
            self.responses[sha]["data"]["repository"]["object"][
                "associatedPullRequests"
            ]["nodes"][0]["changedFiles"] = 3000
        with mock.patch.object(self, "rest") as rest:
            self.assertEqual(len(self.collect()), 2)
        rest.assert_not_called()

    def test_missing_mode_only_prefix_does_not_pass_as_complete_text_change(self):
        self.add_commit("chore: 保存脚本", "script", "old\n")
        self.run_git("update-index", "--chmod=+x", "script")
        self.base = self.add_commit("chore: 设置脚本权限")
        self.run_git("update-index", "--chmod=-x", "script")
        first = self.add_commit("chore: 移除脚本执行权限")
        last = self.add_commit("fix: 修复脚本内容", "script", "new\n")
        self.associate([first, last])
        self.responses[first] = associated_response(first)
        self.assertIn("old mode 100755", self.pr_diffs[17])
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["修复脚本内容", "移除脚本执行权限"],
        )

    def test_hunk_display_labels_can_differ_but_ranges_and_content_must_match(self):
        self.make_pair()
        for file in self.pr_files[17]:
            file["patch"] = re.sub(
                r"^(@@.*?@@).*$",
                r"\1 API function label",
                file["patch"],
                flags=re.MULTILINE,
            )
        self.pr_diffs[17] = re.sub(
            r"^(@@.*?@@).*$",
            r"\1 API function label",
            self.pr_diffs[17],
            flags=re.MULTILINE,
        )
        self.assertEqual([item["desc"] for item in self.collect()], ["支持批量导出。"])
        original = self.pr_files[17][0]["patch"]
        self.pr_files[17][0]["patch"] = original.replace("+1 @@", "+2 @@")
        self.assertEqual(len(self.collect()), 2)
        self.pr_files[17][0]["patch"] = original.replace("+entry", "+other")
        self.assertEqual(len(self.collect()), 2)

    def test_missing_or_partial_complete_diff_uses_individual_commits(self):
        self.make_pair()
        original = self.pr_diffs[17]
        for diff in (
            None,
            "",
            original.split("diff --git ", 2)[0]
            + "diff --git "
            + original.split("diff --git ", 2)[1],
        ):
            with self.subTest(diff=diff):
                self.pr_diffs[17] = diff
                self.assertEqual(len(self.collect()), 2)

    def test_no_valid_summary_keeps_individual_commit_notes_and_skip_rules(self):
        first, second = self.make_pair(tail="ci: 调整导出测试")
        for body in ("", "Changelog:", "Changelog: 一。\n\nChangelog: 二。"):
            with self.subTest(body=body):
                self.associate([first, second], body=body)
                self.assertEqual(
                    [item["desc"] for item in self.collect()], ["新增导出入口"]
                )

    def test_group_skip_marker_and_category_are_taken_from_pr(self):
        first, second = self.make_pair(tail="build: 准备导出产物")
        self.associate([first, second], title="build(deps): 更新导出依赖")
        self.assertEqual([item["category"] for item in self.collect()], ["deps"])
        self.associate(
            [first, second], body="Changelog: 支持导出。\n\n[skip changelog]"
        )
        self.assertEqual(self.collect(), [])

    def test_partial_revert_uses_remaining_commit_instead_of_whole_pr_summary(self):
        first, second = self.make_pair()
        self.run_git("revert", "--no-edit", second)
        self.assertEqual([item["desc"] for item in self.collect()], ["新增导出入口"])
        self.assertNotEqual(first, second)

    def test_complete_individual_reverts_cancel_entire_group(self):
        first, second = self.make_pair()
        self.run_git("revert", "--no-edit", second)
        self.run_git("revert", "--no-edit", first)
        self.assertEqual(self.collect(), [])

    def test_one_complete_inverse_change_cancels_whole_group(self):
        first, second = self.make_pair()
        self.run_git("revert", "--no-commit", second)
        self.run_git("revert", "--no-commit", first)
        self.add_commit("revert: 撤销导出入口", body=f"This reverts commit {second}.")
        self.assertEqual(self.collect(), [])

    def test_unconfirmed_partial_revert_cannot_keep_original_whole_summary(self):
        first, second = self.make_pair()
        self.add_commit(
            "revert: 部分撤销导出",
            "first",
            "partial\n",
            f"This reverts commit {first}.",
        )
        self.assertEqual(
            [item["desc"] for item in self.collect()],
            ["部分撤销导出", "修复导出文件名", "新增导出入口"],
        )

    def test_revert_of_revert_restores_whole_pr_and_cross_base_revert_remains(self):
        first, second = self.make_pair()
        self.run_git("revert", "--no-edit", second)
        undo = self.run_git("rev-parse", "HEAD")
        self.assertEqual(len(self.collect(second)), 1)
        self.run_git("revert", "--no-edit", undo)
        self.assertEqual([item["desc"] for item in self.collect()], ["支持批量导出。"])

    def test_graphql_transport_uses_actual_sha_and_reports_http_failure(self):
        first, second = self.make_pair()
        calls = []
        accepts = []

        def respond(request, timeout):
            if request.full_url == "https://api.github.com/graphql":
                self.assertEqual(request.get_method(), "POST")
                data = json.loads(request.data)
                self.assertIn("associatedPullRequests", data["query"])
                self.assertIn("pageInfo", data["query"])
                calls.append(data["variables"]["sha"])
                body = json.dumps(self.query(data["query"], data["variables"]))
            else:
                self.assertEqual(request.get_method(), "GET")
                accept = request.get_header("Accept")
                accepts.append(accept)
                as_text = accept == "application/vnd.github.diff"
                result = self.rest(request.full_url, as_text=as_text)
                body = result if as_text else json.dumps(result)
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = body.encode("utf-8")
            return response

        with mock.patch.object(
            generator.urllib.request, "urlopen", side_effect=respond
        ):
            self.assertEqual(
                [
                    item["desc"]
                    for item in generator.collect_commits(self.base, "owner/repo")
                ],
                ["支持批量导出。"],
            )
        self.assertEqual(set(calls), {first, second, self.base})
        self.assertEqual(
            accepts, ["application/vnd.github+json", "application/vnd.github.diff"]
        )
        stderr = io.StringIO()
        with (
            mock.patch.object(
                generator.urllib.request, "urlopen", side_effect=OSError("offline")
            ),
            mock.patch.object(generator, "github_api_get", return_value=[]),
            contextlib.redirect_stderr(stderr),
        ):
            self.assertEqual(len(generator.collect_commits(self.base, "owner/repo")), 2)
        self.assertIn("unavailable", stderr.getvalue())


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
                generator,
                "github_graphql",
                side_effect=lambda query, variables: (
                    None
                    if api is None
                    else associated_response(
                        variables["sha"],
                        [
                            item
                            for item in (api if isinstance(api, list) else [api])
                            if isinstance(item, dict)
                            and item.get("merge_commit_sha") == variables["sha"]
                        ],
                    )
                ),
            ),
            mock.patch.object(generator, "pr_changes_match", return_value=True),
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
        self.assertTrue(
            any("/pulls/17/files" in call.args[0] for call in api.call_args_list)
        )

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
                    [item],
                    api=[
                        pull(
                            item["hash"], "Changelog: 无需发布。", title=item["subject"]
                        )
                    ],
                )
                self.assertEqual(result, [])
                if "[skip changelog]" in item["body"]:
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
                mock.patch.object(
                    generator,
                    "github_graphql",
                    side_effect=lambda query, variables: associated_response(
                        variables["sha"],
                        [pr] if variables["sha"] == squashed["hash"] else [],
                    ),
                ),
                mock.patch.object(generator, "pr_changes_match", return_value=True),
                mock.patch.object(generator, "resolve_logins", return_value=[]),
                mock.patch.object(generator, "release_date", return_value="2026-10-14"),
            ):
                generator.main()
            generated = out.read_text(encoding="utf-8")
            self.assertIn(final, generated)
            self.assertNotIn("中间版本说明", generated)
            self.assertNotIn("原因和方案", generated)
            self.assertIn(previous, saved.read_text(encoding="utf-8"))
            self.assertTrue(
                any(
                    call.args[0]
                    == "https://api.github.com/repos/owner/repo/pulls/17/files?per_page=100&page=1"
                    for call in api.call_args_list
                )
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
