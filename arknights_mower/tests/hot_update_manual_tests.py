import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from arknights_mower.utils import hot_update as hu
from arknights_mower.utils.zip_safe import is_unsafe_zip_member


def _zip_bytes(entries=None) -> bytes:
    buf = io.BytesIO()
    with ZipFile(buf, "w") as z:
        for name, content in (entries or {}).items():
            z.writestr(name, content)
    return buf.getvalue()


class TestHasHotupdateMarker(unittest.TestCase):
    """zip 内容校验：至少要带一个热更标记文件，否则不是热更包。"""

    def test_data_marker_root_present(self):
        self.assertTrue(hu._has_hotupdate_marker(["nav_steps.json"]))
        self.assertTrue(hu._has_hotupdate_marker(["stage_data.json"]))
        self.assertTrue(hu._has_hotupdate_marker(["stage_data.json", "version.json"]))

    def test_version_json_alone_not_a_marker(self):
        self.assertFalse(hu._has_hotupdate_marker(["version.json"]))
        self.assertFalse(hu._has_hotupdate_marker(["version.json", "readme.txt"]))

    def test_nested_marker_not_root_rejected(self):
        self.assertFalse(hu._has_hotupdate_marker(["sub/nav_steps.json"]))

    def test_no_marker_absent(self):
        self.assertFalse(hu._has_hotupdate_marker([]))
        self.assertFalse(hu._has_hotupdate_marker(["readme.txt", "data.bin"]))


class TestUnsafeMember(unittest.TestCase):
    """zip-slip 防护：拒绝绝对路径 / 穿越 / Windows 盘符路径。"""

    def test_traversal_rejected(self):
        self.assertTrue(is_unsafe_zip_member("../../etc/passwd"))
        self.assertTrue(is_unsafe_zip_member("a/../../b"))
        self.assertTrue(is_unsafe_zip_member("/abs/path"))

    def test_windows_drive_rejected(self):
        self.assertTrue(is_unsafe_zip_member("C:/evil"))
        self.assertTrue(is_unsafe_zip_member("c:evil"))

    def test_normal_ok(self):
        self.assertFalse(is_unsafe_zip_member("nav_steps.json"))
        self.assertFalse(is_unsafe_zip_member("a/b/nav_steps.json"))


class TestVersionTagFromZip(unittest.TestCase):
    """手动包的版本号尽力从 version.json 读取；缺省/损坏/取不到返回 None。"""

    def test_reads_version(self):
        data = _zip_bytes({"version.json": json.dumps({"version": "v1.2.3"})})
        self.assertEqual(hu._version_tag_from_zip(data), "v1.2.3")

    def test_absent_returns_none(self):
        data = _zip_bytes({"nav_steps.json": "{}"})
        self.assertIsNone(hu._version_tag_from_zip(data))

    def test_malformed_returns_none(self):
        data = _zip_bytes({"version.json": "{bad"})
        self.assertIsNone(hu._version_tag_from_zip(data))

    def test_missing_version_field_returns_none(self):
        data = _zip_bytes({"version.json": json.dumps({"foo": 1})})
        self.assertIsNone(hu._version_tag_from_zip(data))


class TestExtractZip(unittest.TestCase):
    """核心应用路径：清空热更目录 -> 校验标记 + zip-slip -> 解压。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.extract = self.dir / "hot_update"
        self.extract_p = patch.object(hu, "extract_path", self.extract)

    def test_extracts_marked_zip_and_clears_old(self):
        with self.extract_p:
            self.extract.mkdir(parents=True)
            (self.extract / "old.txt").write_text("x", encoding="utf-8")
            ok = hu._extract_zip(
                _zip_bytes({"nav_steps.json": json.dumps({"version": 1})})
            )
            self.assertTrue(ok)
            self.assertTrue((self.extract / "nav_steps.json").exists())
            self.assertFalse((self.extract / "old.txt").exists())

    def test_zip_without_marker_rejected(self):
        with self.extract_p:
            self.assertFalse(hu._extract_zip(_zip_bytes({"readme.txt": "x"})))

    def test_version_json_only_rejected(self):
        # 只有清单文件、没有任何数据文件 -> 应用了也没东西可加载，不通过校验
        with self.extract_p:
            self.assertFalse(
                hu._extract_zip(
                    _zip_bytes({"version.json": json.dumps({"version": "v1"})})
                )
            )

    def test_zip_slip_rejected(self):
        with self.extract_p:
            self.assertFalse(
                hu._extract_zip(
                    _zip_bytes({"../evil.txt": "x", "nav_steps.json": "{}"})
                )
            )

    def test_not_a_zip_rejected(self):
        with self.extract_p:
            self.assertFalse(hu._extract_zip(b"not a zip"))


class TestApplyManualZip(unittest.TestCase):
    """手动应用编排：校验+解压 -> 记录版本（尽力）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.extract = self.dir / "hot_update"
        self.version = self.dir / "hot_update_version.json"
        self.extract_p = patch.object(hu, "extract_path", self.extract)
        self.version_p = patch.object(hu, "version_state", self.version)

    def test_applies_and_records_version(self):
        data = _zip_bytes(
            {
                "nav_steps.json": json.dumps({"version": 1}),
                "version.json": json.dumps({"version": "v9.9.9"}),
            }
        )
        with self.extract_p, self.version_p:
            self.assertTrue(hu.apply_manual_zip(data))
            self.assertEqual(self.version.read_text(encoding="utf-8"), "v9.9.9")

    def test_applies_without_version_preserves_tag(self):
        data = _zip_bytes({"nav_steps.json": json.dumps({"version": 1})})
        self.version.write_text("v8.8.8", encoding="utf-8")
        with self.extract_p, self.version_p:
            self.assertTrue(hu.apply_manual_zip(data))
            self.assertEqual(self.version.read_text(encoding="utf-8"), "v8.8.8")

    def test_older_version_preserves_tag(self):
        # 只升不降：拖入更旧包 -> 不覆盖已应用的更新版本（内容仍应用）
        data = _zip_bytes(
            {
                "nav_steps.json": json.dumps({"version": 1}),
                "version.json": json.dumps({"version": "v2026.08.21-aaaaaa"}),
            }
        )
        self.version.write_text("v2026.08.23-bbbbbb", encoding="utf-8")
        with self.extract_p, self.version_p:
            self.assertTrue(hu.apply_manual_zip(data))
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.23-bbbbbb"
            )

    def test_newer_version_updates_tag(self):
        data = _zip_bytes(
            {
                "nav_steps.json": json.dumps({"version": 1}),
                "version.json": json.dumps({"version": "v2026.08.23-bbbbbb"}),
            }
        )
        self.version.write_text("v2026.08.21-aaaaaa", encoding="utf-8")
        with self.extract_p, self.version_p:
            self.assertTrue(hu.apply_manual_zip(data))
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.23-bbbbbb"
            )

    def test_same_version_preserves_tag(self):
        data = _zip_bytes(
            {
                "nav_steps.json": json.dumps({"version": 1}),
                "version.json": json.dumps({"version": "v2026.08.22-aaaaaa"}),
            }
        )
        self.version.write_text("v2026.08.22-aaaaaa", encoding="utf-8")
        with self.extract_p, self.version_p:
            self.assertTrue(hu.apply_manual_zip(data))
            self.assertEqual(
                self.version.read_text(encoding="utf-8"), "v2026.08.22-aaaaaa"
            )

    def test_invalid_rejected(self):
        with self.extract_p, self.version_p:
            self.assertFalse(hu.apply_manual_zip(_zip_bytes({"x.txt": "a"})))


if __name__ == "__main__":
    unittest.main()
