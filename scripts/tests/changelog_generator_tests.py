"""changelog_generator.prepend_changelog 幂等性测试（不联网）。

覆盖：首次插入版本块、相同版本重复执行不重复插入、已有其他版本时新版本仍
插入到正确位置、前缀版本不误判、插入不删除其他版本内容。
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import changelog_generator  # noqa: E402

BLOCK = (
    "## 4.1.6-alpha.2 - 2026-08-31\n"
    "\n"
    "### New\n"
    "\n"
    "- 新增多平台构建\n"
    "\n"
    "**Full Changelog**: https://github.com/ArkMowers/arknights-mower/compare/x...y\n"
)


def _write(tmp: str, content: str) -> Path:
    path = Path(tmp) / "CHANGELOG.md"
    path.write_text(content, encoding="utf-8")
    return path


def _fake_git(tags: dict[str, int | None], creation_order: list[str] | None = None):
    """模拟 changelog_generator.git()：tag 值=HEAD 到该 tag 的提交距离，None=不可达。"""

    def fake_git(*args):
        if args == ("tag", "-l"):
            return "\n".join(tags) + "\n"
        if args == ("tag", "--sort=-creatordate"):
            return "\n".join(creation_order or list(tags)) + "\n"
        if args[0] == "rev-list" and args[1] == "--count":
            name = args[2].removesuffix("..HEAD")
            distance = tags.get(name)
            return str(distance if distance is not None else 0)
        raise AssertionError(f"unexpected git call: {args}")

    return fake_git


def _fake_run(tags: dict[str, int | None]):
    """模拟 merge-base --is-ancestor 的可达性判断（returncode 0=可达）。"""

    def fake_run(cmd, capture_output=True, text=True, encoding="utf-8"):
        name = cmd[-1]
        return subprocess.CompletedProcess(cmd, 0 if tags.get(name) is not None else 1)

    return fake_run


class PrependChangelogTests(unittest.TestCase):
    def test_first_insert_places_block_after_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "# CHANGELOG\n\n## 4.1.5 - 2026-08-01\n\n- 旧内容\n")
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertTrue(inserted)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(
                text.startswith("# CHANGELOG\n\n## 4.1.6-alpha.2 - 2026-08-31\n")
            )

    def test_same_version_not_inserted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "# CHANGELOG\n\n" + BLOCK + "\n## 4.1.5 - 2026-08-01\n")
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertFalse(inserted)
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("## 4.1.6-alpha.2 - 2026-08-31"), 1)

    def test_new_version_inserted_above_existing_versions(self):
        older = "# CHANGELOG\n\n## 4.1.6-alpha.1 - 2026-08-01\n\n- 旧版本内容\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, older)
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertTrue(inserted)
            text = path.read_text(encoding="utf-8")
            self.assertLess(
                text.index("## 4.1.6-alpha.2 - 2026-08-31"),
                text.index("## 4.1.6-alpha.1 - 2026-08-01"),
            )
            self.assertIn("- 旧版本内容", text)

    def test_prefix_version_not_matched(self):
        other = "# CHANGELOG\n\n## 4.1.6-alpha.20 - 2026-08-31\n\n- 更高版本\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, other)
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertTrue(inserted)
            text = path.read_text(encoding="utf-8")
            self.assertLess(
                text.index("## 4.1.6-alpha.2 - 2026-08-31"),
                text.index("## 4.1.6-alpha.20 - 2026-08-31"),
            )

    def test_no_heading_file_gets_block_on_top(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "## 4.1.5 - 2026-08-01\n\n- 旧内容\n")
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertTrue(inserted)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("## 4.1.6-alpha.2 - 2026-08-31\n"))
            self.assertIn("- 旧内容", text)

    def test_crlf_repeat_not_inserted_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = "# CHANGELOG\r\n\r\n" + BLOCK.replace("\n", "\r\n") + "\r\n"
            path = _write(tmp, content)
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertFalse(inserted)
            self.assertEqual(
                path.read_text(encoding="utf-8").count("## 4.1.6-alpha.2"), 1
            )

    def test_date_less_heading_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write(tmp, "# CHANGELOG\n\n## 4.1.6-alpha.2\n\n- 旧内容\n")
            inserted = changelog_generator.prepend_changelog(path, BLOCK)
            self.assertFalse(inserted)


class ContributorLoginTests(unittest.TestCase):
    def setUp(self):
        changelog_generator._login_cache.clear()

    def test_same_display_name_with_different_emails_does_not_share_login(self):
        records = (
            f"aaa{changelog_generator.SEP}同名作者{changelog_generator.SEP}"
            f"first@example.com{changelog_generator.SEP}fix: 第一个提交"
            f"{changelog_generator.SEP}{changelog_generator.REC}"
            f"bbb{changelog_generator.SEP}同名作者{changelog_generator.SEP}"
            f"second@example.com{changelog_generator.SEP}fix: 第二个提交"
            f"{changelog_generator.SEP}{changelog_generator.REC}"
        )

        def api_response(url):
            login = "first-login" if url.endswith("/aaa") else "second-login"
            return {"author": {"login": login}}

        with (
            mock.patch.object(changelog_generator, "git", return_value=records),
            mock.patch.object(
                changelog_generator, "github_api_get", side_effect=api_response
            ),
        ):
            commits = changelog_generator.collect_commits("")
            logins = [
                changelog_generator.resolve_logins(
                    "owner/repo", commit["hash"], commit["authors"]
                )
                for commit in commits
            ]

        self.assertEqual(logins, [["first-login"], ["second-login"]])

    def test_primary_author_login_is_cached_by_normalized_email(self):
        with mock.patch.object(
            changelog_generator,
            "github_api_get",
            return_value={"author": {"login": "stable-login"}},
        ) as api_get:
            first = changelog_generator.resolve_logins(
                "owner/repo", "aaa", [("First Name", "Stable@Example.com")]
            )
            second = changelog_generator.resolve_logins(
                "owner/repo", "bbb", [("Renamed Author", "stable@example.com")]
            )

        self.assertEqual(first, ["stable-login"])
        self.assertEqual(second, ["stable-login"])
        api_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/commits/aaa"
        )

    def test_noreply_coauthor_is_resolved_without_network_lookup(self):
        with mock.patch.object(
            changelog_generator,
            "github_api_get",
            return_value={"author": {"login": "primary"}},
        ):
            logins = changelog_generator.resolve_logins(
                "owner/repo",
                "aaa",
                [
                    ("Primary", "primary@example.com"),
                    ("Contributor", "123456+co-author@users.noreply.github.com"),
                ],
            )

        self.assertEqual(logins, ["primary", "co-author"])

    def test_unrecognized_authors_are_skipped_instead_of_guessed(self):
        with mock.patch.object(
            changelog_generator, "github_api_get", return_value=None
        ):
            logins = changelog_generator.resolve_logins(
                "owner/repo",
                "aaa",
                [
                    ("Display Name", "person@example.com"),
                    ("Another Person", "other@example.com"),
                ],
            )

        self.assertEqual(logins, [])

    def test_logins_are_deduplicated_case_insensitively(self):
        with mock.patch.object(
            changelog_generator,
            "github_api_get",
            return_value={"author": {"login": "Alice"}},
        ):
            logins = changelog_generator.resolve_logins(
                "owner/repo",
                "aaa",
                [
                    ("Primary", "primary@example.com"),
                    ("Same Account", "alice@users.noreply.github.com"),
                    ("Other Account", "Bob@users.noreply.github.com"),
                ],
            )

        self.assertEqual(logins, ["Alice", "Bob"])

    def test_release_body_uses_bare_mentions_without_manual_thanks_section(self):
        commits = [
            {
                "category": "fix",
                "hash": "aaa",
                "authors": [("Alice", "alice@example.com")],
                "desc": "修复发布流程",
                "number": 42,
            }
        ]
        with (
            mock.patch.object(
                changelog_generator, "release_date", return_value="2026-09-01"
            ),
            mock.patch.object(
                changelog_generator,
                "resolve_logins",
                return_value=["Alice", "Bob"],
            ),
        ):
            body = changelog_generator.render_release_body(
                "v4.1.6-alpha.2", "owner/repo", "v4.1.6-alpha.1", commits
            )

        self.assertIn(
            "- 修复发布流程 [(#42)](https://github.com/owner/repo/pull/42) @Alice @Bob",
            body,
        )
        self.assertNotIn("[@Alice]", body)
        self.assertNotIn("## Thanks to", body)

    def test_collect_commits_preserves_primary_and_coauthor_emails(self):
        record = (
            f"aaa{changelog_generator.SEP}Primary Name{changelog_generator.SEP}"
            f"primary@example.com{changelog_generator.SEP}fix: 修复贡献者"
            f"{changelog_generator.SEP}"
            "Co-authored-by: Shared Name <shared@example.com>\n"
            f"{changelog_generator.REC}"
        )
        with mock.patch.object(changelog_generator, "git", return_value=record):
            commits = changelog_generator.collect_commits("")

        self.assertEqual(
            commits[0]["authors"],
            [
                ("Primary Name", "primary@example.com"),
                ("Shared Name", "shared@example.com"),
            ],
        )


class FindBaseTagTests(unittest.TestCase):
    def test_stable_tag_skips_nearer_alpha_and_uses_previous_stable(self):
        tags = {"v4.1.6-alpha.1": 1, "v4.1.5": 86, "v4.1.2": 300}
        with (
            mock.patch.object(changelog_generator, "git", side_effect=_fake_git(tags)),
            mock.patch.object(
                changelog_generator.subprocess, "run", side_effect=_fake_run(tags)
            ),
        ):
            self.assertEqual(changelog_generator.find_base_tag("v4.1.6"), "v4.1.5")

    def test_alpha_tag_uses_previous_alpha(self):
        tags = {"v4.1.6-alpha.1": 5, "v4.1.5": 100}
        with (
            mock.patch.object(changelog_generator, "git", side_effect=_fake_git(tags)),
            mock.patch.object(
                changelog_generator.subprocess, "run", side_effect=_fake_run(tags)
            ),
        ):
            self.assertEqual(
                changelog_generator.find_base_tag("v4.1.6-alpha.2"), "v4.1.6-alpha.1"
            )

    def test_alpha_tag_without_previous_alpha_falls_back_to_stable(self):
        tags = {"v4.1.5": 100}
        with (
            mock.patch.object(changelog_generator, "git", side_effect=_fake_git(tags)),
            mock.patch.object(
                changelog_generator.subprocess, "run", side_effect=_fake_run(tags)
            ),
        ):
            self.assertEqual(
                changelog_generator.find_base_tag("v4.1.6-alpha.1"), "v4.1.5"
            )

    def test_stable_tag_falls_back_to_latest_stable_by_creation_when_none_reachable(
        self,
    ):
        tags = {"v4.1.5": None, "v4.1.2": None}
        with (
            mock.patch.object(changelog_generator, "git", side_effect=_fake_git(tags)),
            mock.patch.object(
                changelog_generator.subprocess, "run", side_effect=_fake_run(tags)
            ),
        ):
            self.assertEqual(changelog_generator.find_base_tag("v4.1.6"), "v4.1.5")

    def test_non_version_tags_are_ignored(self):
        tags = {"backup/pre-split-abc": 1, "v4.1.5": 50}
        with (
            mock.patch.object(changelog_generator, "git", side_effect=_fake_git(tags)),
            mock.patch.object(
                changelog_generator.subprocess, "run", side_effect=_fake_run(tags)
            ),
        ):
            self.assertEqual(changelog_generator.find_base_tag("v4.1.6"), "v4.1.5")


class ParseCategoryTests(unittest.TestCase):
    def test_dependency_upgrade_keyword_maps_to_deps(self):
        self.assertEqual(
            changelog_generator.parse_category(
                "build(ui): 前端依赖整体升级 + 图表修复"
            ),
            "deps",
        )

    def test_deps_scope_maps_to_deps(self):
        self.assertEqual(
            changelog_generator.parse_category("build(deps): bump vite"), "deps"
        )

    def test_dependency_update_keyword_maps_to_deps(self):
        self.assertEqual(
            changelog_generator.parse_category("chore(ui): 更新依赖"), "deps"
        )

    def test_build_release_prepare_is_still_skipped(self):
        self.assertIsNone(
            changelog_generator.parse_category("build(release): prepare release v4.1.6")
        )

    def test_ci_prefix_is_still_skipped(self):
        self.assertIsNone(changelog_generator.parse_category("ci: fix build"))

    def test_release_body_includes_dependencies_heading(self):
        commits = [
            {
                "category": "deps",
                "hash": "aaa",
                "authors": [("Alice", "alice@example.com")],
                "desc": "前端依赖整体升级",
                "number": 154,
            }
        ]
        with (
            mock.patch.object(
                changelog_generator, "release_date", return_value="2026-09-01"
            ),
            mock.patch.object(
                changelog_generator, "resolve_logins", return_value=["Alice"]
            ),
        ):
            body = changelog_generator.render_release_body(
                "v4.1.6-alpha.2", "owner/repo", "v4.1.6-alpha.1", commits
            )
        self.assertIn("### Dependencies", body)
        self.assertIn(
            "- 前端依赖整体升级 "
            "[(#154)](https://github.com/owner/repo/pull/154) @Alice",
            body,
        )


if __name__ == "__main__":
    unittest.main()
