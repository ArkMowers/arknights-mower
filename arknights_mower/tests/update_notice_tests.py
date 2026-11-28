import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower.utils import update_notice


class UpdateNoticeTests(unittest.TestCase):
    def setUp(self):
        temporary_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_dir.cleanup)
        self.changelog_path = Path(temporary_dir.name) / "CHANGELOG.md"
        self.patch_value("CHANGELOG_FILE", self.changelog_path)
        self.state = {
            update_notice.LAST_SEEN_VERSION_KEY: "4.1.6-alpha.1",
            update_notice.LAST_ACKNOWLEDGED_VERSION_KEY: "4.1.6-alpha.1",
        }
        self.patch_value("read_app_state", lambda: self.state.copy())
        self.patch_value("write_app_state", self.state.update)
        self.manager = update_notice.UpdateNoticeManager()
        self.manager.current_version = "4.1.6-alpha.2"

    def patch_value(self, name, value):
        patcher = patch.object(update_notice, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_changelog(self, text):
        self.changelog_path.write_text(text, encoding="utf-8")

    def test_release_headers_with_and_without_dates(self):
        for version in ("4.1.6-alpha.2", "4.1.6", "4.1.5.8"):
            for prefix in ("", "v"):
                for suffix in ("", " - 2026-09-01"):
                    with self.subTest(version=version, prefix=prefix, suffix=suffix):
                        self.manager.current_version = version
                        self.write_changelog(
                            f"# CHANGELOG\n\n## {prefix}{version}{suffix}\n\n"
                            "### Bug Fixes\n\n- 修复更新日志\n"
                        )
                        self.assertEqual(
                            self.manager._resolve_changelog(),
                            "### Bug Fixes\n\n- 修复更新日志",
                        )

    def test_alpha_upgrade_shows_only_current_release_until_acknowledged(self):
        self.write_changelog(
            "# CHANGELOG\n\n"
            "## 4.1.6-alpha.20 - 2026-09-09\n\n- 后续版本\n\n"
            "## 4.1.6-alpha.2 - 2026-09-01\n\n"
            "### Bug Fixes\n\n- 修复更新日志\n\n"
            "## v4.1.6-alpha.1 - 2026-08-31\n\n- 上一测试版\n\n"
            "## v4.1.5\n\n- 正式版\n"
        )

        notice = self.manager.get_notice()
        self.assertTrue(notice["should_show"])
        self.assertEqual(notice["previous_version"], "4.1.6-alpha.1")
        self.assertEqual(notice["changelog"], "### Bug Fixes\n\n- 修复更新日志")
        self.assertEqual(self.manager.get_notice(), notice)

        self.manager.acknowledge("4.1.6-alpha.2")
        self.assertFalse(self.manager.get_notice()["should_show"])

    def test_source_version_falls_back_to_release_without_build_metadata(self):
        self.manager.current_version = "4.1.6-alpha.2+abcdef0"
        self.write_changelog("## 4.1.6-alpha.2 - 2026-09-01\n\n- 发布日志\n")
        self.assertEqual(self.manager.get_notice()["changelog"], "- 发布日志")

    def test_exact_build_version_takes_priority(self):
        self.manager.current_version = "4.1.6-alpha.2+abcdef0"
        self.write_changelog(
            "## 4.1.6-alpha.2+abcdef0 - 2026-09-01\n\n- 构建日志\n\n"
            "## 4.1.6-alpha.2 - 2026-09-01\n\n- 发布日志\n"
        )
        self.assertEqual(self.manager.get_notice()["changelog"], "- 构建日志")

    def test_first_run_still_shows_full_changelog(self):
        self.state.clear()
        text = (
            "# CHANGELOG\n\n"
            "## 4.1.6-alpha.2 - 2026-09-01\n\n- 当前版本\n\n"
            "## 4.1.6-alpha.1 - 2026-08-31\n\n- 上一版本\n"
        )
        self.write_changelog(text)
        notice = self.manager.get_notice()
        self.assertTrue(notice["should_show"])
        self.assertEqual(notice["changelog"], text.strip())

    def test_missing_or_empty_release_keeps_version_fallback(self):
        for content in (
            None,
            "",
            "## 4.1.6-alpha.2 - 2026-09-01\n",
            "## v4.1.5\n- 旧版",
        ):
            with self.subTest(content=content):
                if content is not None:
                    self.write_changelog(content)
                self.assertEqual(
                    self.manager._resolve_changelog(), "已更新到 4.1.6-alpha.2"
                )


if __name__ == "__main__":
    unittest.main()
