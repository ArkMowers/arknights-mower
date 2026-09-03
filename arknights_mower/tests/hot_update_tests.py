import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from arknights_mower.utils import config
from arknights_mower.utils import hot_update as hu
from arknights_mower.utils.res_version import parse_version, version_newer


def _fake_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as z:
        z.writestr("stage_data.json", json.dumps({"x": 1}))
        z.writestr(
            "nav_steps.json", json.dumps({"version": 1, "stages": {}, "patterns": {}})
        )
    return buf.getvalue()


class TestHotUpdateBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.extract = self.dir / "hot_update"
        self.version = self.dir / "hot_update_version.json"

        self.enable = patch.object(config.conf.hot_update, "enable", True)
        self.extract_p = patch.object(hu, "extract_path", self.extract)
        self.version_p = patch.object(hu, "version_state", self.version)
        # 模块全局 last_update 跨用例残留会触发 30 分钟节流，逐用例重置
        self._old_last_update = hu.last_update
        hu.last_update = None
        self.addCleanup(setattr, hu, "last_update", self._old_last_update)


class TestLatestReleaseTag(TestHotUpdateBase):
    def test_returns_tag(self):
        with self.enable, patch.object(hu.requests, "get") as get:
            get.return_value.status_code = 200
            get.return_value.json = lambda: {"tag_name": "v1.0.1"}
            self.assertEqual(hu._latest_release_tag(), "v1.0.1")

    def test_http_error_returns_none(self):
        with self.enable, patch.object(hu.requests, "get") as get:
            get.return_value.status_code = 404
            self.assertIsNone(hu._latest_release_tag())

    def test_exception_returns_none(self):
        with self.enable, patch.object(hu.requests, "get", side_effect=OSError("boom")):
            self.assertIsNone(hu._latest_release_tag())


class TestDownloadAndExtract(TestHotUpdateBase):
    def test_downloads_and_extracts(self):
        with self.enable, self.extract_p, patch.object(hu.requests, "get") as get:
            get.return_value.status_code = 200
            get.return_value.content = _fake_zip_bytes()
            self.extract.mkdir(parents=True)
            (self.extract / "old.txt").write_text("x", encoding="utf-8")
            self.assertTrue(hu._download_and_extract())
            self.assertTrue((self.extract / "stage_data.json").exists())
            self.assertFalse((self.extract / "old.txt").exists())  # extract 前已清空

    def test_http_error_returns_false(self):
        with self.enable, self.extract_p, patch.object(hu.requests, "get") as get:
            get.return_value.status_code = 500
            self.assertFalse(hu._download_and_extract())


class TestUpdateOrchestration(TestHotUpdateBase):
    """update() 编排：config 门、版本比对、不重复下载、记录已应用版本。"""

    def test_disabled_by_config_noop(self):
        with (
            patch.object(config.conf.hot_update, "enable", False),
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value="v1") as latest,
        ):
            hu.update()
            latest.assert_not_called()  # 未开启 -> 根本不去查

    def test_applied_equal_latest_no_download(self):
        self.version.write_text("v2026.08.22-aaaaaa", encoding="utf-8")
        with (
            self.enable,
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value="v2026.08.22-aaaaaa"),
            patch.object(hu, "_download_and_extract") as dl,
        ):
            hu.update()
            dl.assert_not_called()

    def test_remote_older_than_local_no_download(self):
        # 手滑发旧版：本地已是 08.23，remote 是 08.22 -> 不降级、不下
        self.version.write_text("v2026.08.23-aaaaaa", encoding="utf-8")
        with (
            self.enable,
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value="v2026.08.22-bbbbbb"),
            patch.object(hu, "_download_and_extract") as dl,
        ):
            hu.update()
            dl.assert_not_called()

    def test_new_version_downloads_and_records(self):
        self.version.write_text("v2026.08.21-aaaaaa", encoding="utf-8")
        with (
            self.enable,
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value="v2026.08.22-bbbbbb"),
            patch.object(hu, "_download_and_extract", return_value=True),
        ):
            hu.update()
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.22-bbbbbb"
            )

    def test_same_day_new_hash_downloads(self):
        # 同日两个 release：哈希不同即视为更新，无需计数后缀
        self.version.write_text("v2026.08.22-aaaaaa", encoding="utf-8")
        with (
            self.enable,
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value="v2026.08.22-bbbbbb"),
            patch.object(hu, "_download_and_extract", return_value=True),
        ):
            hu.update()
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.22-bbbbbb"
            )

    def test_download_failure_does_not_record(self):
        self.version.write_text("v2026.08.21-aaaaaa", encoding="utf-8")
        with (
            self.enable,
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value="v2026.08.22-bbbbbb"),
            patch.object(hu, "_download_and_extract", return_value=False),
        ):
            hu.update()
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.21-aaaaaa"
            )  # 未记录

    def test_api_error_graceful(self):
        self.version.write_text("v2026.08.21-aaaaaa", encoding="utf-8")
        with (
            self.enable,
            self.extract_p,
            self.version_p,
            patch.object(hu, "_latest_release_tag", return_value=None),
            patch.object(hu, "_download_and_extract") as dl,
        ):
            hu.update()  # 不应抛异常
            dl.assert_not_called()
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.21-aaaaaa"
            )


class TestTagCompare(unittest.TestCase):
    """「日期 + 哈希」tag 解析与「只升级不降级」守卫。"""

    def test_parse_valid(self):
        self.assertEqual(
            parse_version("v2026.08.22-9f3c8a2", require_v=True),
            (2026, 8, 22, "9f3c8a2"),
        )
        self.assertEqual(
            parse_version("v2026.08.22-9f3c8a2d4b1c", require_v=True),
            (2026, 8, 22, "9f3c8a2d4b1c"),
        )

    def test_parse_invalid_returns_none(self):
        self.assertIsNone(parse_version("v2026.08.22", require_v=True))  # 缺哈希
        self.assertIsNone(parse_version("v1", require_v=True))
        self.assertIsNone(parse_version("", require_v=True))
        self.assertIsNone(parse_version("abc", require_v=True))

    def test_is_newer_same_false(self):
        self.assertFalse(
            version_newer("v2026.08.22-aaaaaa", "v2026.08.22-aaaaaa", require_v=True)
        )

    def test_is_newer_remote_older_false(self):
        # remote 更旧 -> 不降级
        self.assertFalse(
            version_newer("v2026.08.22-aaaaaa", "v2026.08.23-bbbbbb", require_v=True)
        )

    def test_is_newer_date_true(self):
        self.assertTrue(
            version_newer("v2026.08.22-aaaaaa", "v2026.08.21-bbbbbb", require_v=True)
        )

    def test_is_newer_same_day_different_hash_true(self):
        # 同日两个 release：哈希不同即视为更新（内容变了）
        self.assertTrue(
            version_newer("v2026.08.22-bbbbbb", "v2026.08.22-aaaaaa", require_v=True)
        )

    def test_is_newer_unparsable_falls_back_to_different(self):
        self.assertTrue(version_newer("v2", "v1", require_v=True))
        self.assertFalse(version_newer("v1", "v1", require_v=True))

    def test_is_newer_empty_local(self):
        self.assertTrue(version_newer("v2026.08.22-aaaaaa", "", require_v=True))


if __name__ == "__main__":
    unittest.main()
