"""#83：auto_schedule_mastery_tasks / compute_workshop_config 直接读 DB 计划。

matery_plan.json 是全仓库无写入者的孤儿文件（@app/tmp 上的 stale key），UI/API/agent
新增计划不在里面，扫描自动开始会漏。两函数改为读 get_all_plans()（非终态计划）。
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from arknights_mower.utils import mastery_recommendation as rec


def _recommendations(op_id, skill_index, materials, current_level=0):
    """get_mastery_recommendations 返回值：单干员单技能（空链=材料充足）。"""
    return {
        "has_data": True,
        "operators": [
            {
                "char_id": op_id,
                "name": op_id,
                "profession": "CASTER",
                "recommendations": [
                    {
                        "skill_index": skill_index,
                        "skill_name": f"技能{skill_index + 1}",
                        "current_level": current_level,
                        "chain_needed_materials": materials,
                    }
                ],
            }
        ],
    }


def _plan(**overrides):
    plan = {
        "id": 1,
        "char_id": "char_A",
        "char_name": "A",
        "skill_index": 1,
        "skill_name": "技能2",
        "target_level": 3,
        "status": "idle",
    }
    plan.update(overrides)
    return plan


class TestAutoScheduleReadsDb(unittest.TestCase):
    """#83：auto_schedule_mastery_tasks 的计划集来自 DB，不读孤儿文件。"""

    def setUp(self):
        # 隔离 cultivate.json / skill_data.json：指向不存在的路径（读到走空分支）
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(
            rec,
            "get_path",
            return_value=os.path.join(self.tmp.name, "missing.json"),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_db_plan_scheduled_when_materials_sufficient(self):
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_A", 1, []),
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual([e["char_id"] for e in result["scheduled"]], ["char_A"])
        self.assertEqual(result["skipped"], [])

    def test_db_plan_skipped_when_materials_insufficient(self):
        mats = [{"name": "技巧概要·卷3", "count": 99}]
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_A", 1, mats),
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual(result["scheduled"], [])
        self.assertEqual([e["char_id"] for e in result["skipped"]], ["char_A"])

    def test_plan_not_in_db_not_scheduled(self):
        # 推荐有 (char_B, 2) 但 DB 无此计划 → 不安排（旧行为：文件 stale key 会漏/误排）
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_B", 2, []),
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual(result, {"scheduled": [], "skipped": []})

    def test_empty_db_returns_empty(self):
        with (
            patch("arknights_mower.utils.mastery_db.get_all_plans", return_value=[]),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_A", 1, []),
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual(result, {"scheduled": [], "skipped": []})


class TestComputeWorkshopConfigReadsDb(unittest.TestCase):
    """#83：compute_workshop_config 按 DB 计划核算材料需求。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        skill_path = os.path.join(self.tmp.name, "skill_data.json")
        with open(skill_path, "w", encoding="utf-8") as f:
            json.dump({"items": {}}, f)
        patcher = patch.object(rec, "_find_skill_data", return_value=skill_path)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_db_plan_drives_book_demand(self):
        # DB 计划 (char_A, 1) → 推荐链材料 技巧概要·卷3×5 → 合成配置 book 上限=5
        mats = [{"name": "技巧概要·卷3", "count": 5}]
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_A", 1, mats),
            ),
            patch.object(
                rec,
                "get_path",
                return_value=os.path.join(self.tmp.name, "no_cultivate.json"),
            ),
        ):
            config = rec.compute_workshop_config()
        self.assertIsNotNone(config)
        book = [c for c in config if c["operator"] == "司霆惊蛰"]
        self.assertEqual(len(book), 1)
        self.assertEqual(
            book[0]["items"],
            [
                {
                    "item_names": ["技巧概要·卷3"],
                    "children_lower_limit": 0,
                    "self_upper_limit": 5,
                }
            ],
        )

    def test_plan_not_in_db_no_demand(self):
        # 推荐链材料属于无 DB 计划的 (char_B, 2) → 不计入需求（book 空）
        mats = [{"name": "技巧概要·卷3", "count": 5}]
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_B", 2, mats),
            ),
            patch.object(
                rec,
                "get_path",
                return_value=os.path.join(self.tmp.name, "no_cultivate.json"),
            ),
        ):
            config = rec.compute_workshop_config()
        self.assertIsNotNone(config)
        book = [c for c in config if c["operator"] == "司霆惊蛰"]
        self.assertEqual(book[0]["items"], [])

    def test_no_db_plans_returns_none(self):
        # 无 DB 计划 → 无需求 → None（调用方保留默认合成配置）
        with (
            patch("arknights_mower.utils.mastery_db.get_all_plans", return_value=[]),
            patch.object(
                rec,
                "get_path",
                return_value=os.path.join(self.tmp.name, "no_cultivate.json"),
            ),
        ):
            config = rec.compute_workshop_config()
        self.assertIsNone(config)


if __name__ == "__main__":
    unittest.main()
