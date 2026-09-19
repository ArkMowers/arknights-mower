import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arknights_mower import data as data_module


class TestStageDataMergeView(unittest.TestCase):
    """关卡信息合并视图：内置全量基线（启动固定） + 热更活动层（运行时按 id 覆盖/新增）。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.overlay_file = self.dir / "stage_data.json"

    def _write_overlay(self, payload):
        self.overlay_file.write_text(json.dumps(payload), encoding="utf-8")

    def _fake_base(self):
        return [
            {"id": "0-1", "name": "0-1", "stageType": "MAIN", "apCost": 12},
            {
                "id": "AP-1",
                "name": "AP-1",
                "stageType": "ACTIVITY",
                "endTs": 100,
                "apCost": 18,
            },
        ]

    def _patch_base_and_overlay(self, base):
        patchers = [
            patch.object(data_module, "_stage_data_base", base),
            patch.object(
                data_module, "stage_data_overlay_path", lambda: self.overlay_file
            ),
        ]
        for p in patchers:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in patchers])

    def test_overlay_path_points_to_hot_update_dir(self):
        path = data_module.stage_data_overlay_path()
        self.assertEqual(path.parts[-3:], ("tmp", "hot_update", "stage_data.json"))

    def test_builtin_base_loaded_at_import(self):
        # 全量基线启动时读进内存，非空（自带那份）
        self.assertIsInstance(data_module._stage_data_base, list)
        self.assertTrue(len(data_module._stage_data_base) > 0)

    def test_no_overlay_uses_base(self):
        base = self._fake_base()
        self._patch_base_and_overlay(base)
        self.assertFalse(self.overlay_file.exists())
        self.assertEqual(list(data_module.stage_data_full), base)

    def test_overlay_replaces_and_adds_permanent_untouched(self):
        base = self._fake_base()
        self._write_overlay(
            [
                {
                    "id": "AP-1",
                    "name": "AP-1",
                    "stageType": "ACTIVITY",
                    "endTs": 200,
                    "apCost": 20,
                },
                {
                    "id": "AP-5",
                    "name": "AP-5",
                    "stageType": "ACTIVITY",
                    "endTs": 300,
                    "apCost": 21,
                },
            ]
        )
        self._patch_base_and_overlay(base)
        merged = list(data_module.stage_data_full)
        by_id = {item["id"]: item for item in merged}
        self.assertEqual(by_id["0-1"]["apCost"], 12)  # 常驻不动
        self.assertEqual(by_id["0-1"]["stageType"], "MAIN")
        self.assertEqual(by_id["AP-1"]["endTs"], 200)  # 被热更覆盖
        self.assertEqual(by_id["AP-1"]["apCost"], 20)
        self.assertEqual(by_id["AP-5"]["endTs"], 300)  # 新增
        self.assertEqual(len(merged), 3)

    def test_corrupt_overlay_falls_back_to_base(self):
        base = self._fake_base()
        self.overlay_file.write_text("{not valid json", encoding="utf-8")
        self._patch_base_and_overlay(base)
        self.assertEqual(list(data_module.stage_data_full), base)

    def test_non_list_overlay_falls_back_to_base(self):
        base = self._fake_base()
        self.overlay_file.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        self._patch_base_and_overlay(base)
        self.assertEqual(list(data_module.stage_data_full), base)

    def test_malformed_overlay_members_fall_back_to_base(self):
        # 合法 JSON 但元素非对象（[null, 1, "x"]）也算损坏 → 回退基线、不抛
        base = self._fake_base()
        self.overlay_file.write_text(
            json.dumps([None, 1, "x", {"id": "AP-9"}]), encoding="utf-8"
        )
        self._patch_base_and_overlay(base)
        self.assertEqual(list(data_module.stage_data_full), base)
        self.assertFalse(
            any(item["id"] == "AP-9" for item in data_module.stage_data_full)
        )

    def test_consumer_lookup_finds_new_activity(self):
        # 调用方现状 `for item in stage_data_full if item.get("id")==name or item.get("name")==name`
        base = self._fake_base()
        self._write_overlay(
            [{"id": "AP-5", "name": "AP-5", "stageType": "ACTIVITY", "endTs": 300}]
        )
        self._patch_base_and_overlay(base)
        got = next(
            (item for item in data_module.stage_data_full if item.get("id") == "AP-5"),
            None,
        )
        self.assertEqual(got["endTs"], 300)

    def test_removed_overlay_falls_back_to_base(self):
        # 热更层删除后回退基线
        base = self._fake_base()
        self._write_overlay([{"id": "AP-5", "name": "AP-5", "stageType": "ACTIVITY"}])
        self._patch_base_and_overlay(base)
        self.assertTrue(
            any(item["id"] == "AP-5" for item in data_module.stage_data_full)
        )
        self.overlay_file.unlink()
        self.assertFalse(
            any(item["id"] == "AP-5" for item in data_module.stage_data_full)
        )
        self.assertEqual(len(list(data_module.stage_data_full)), 2)


if __name__ == "__main__":
    unittest.main()
