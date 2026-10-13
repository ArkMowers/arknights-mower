"""Mastery dispatch reads persisted plans and confirmed finished inventory."""

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


def _write_inventory_files(tmp_dir, item_id, owned):
    """写 cultivate.json（库存）+ skill_data.json（材料名→id）到临时目录。

    auto_schedule_mastery_tasks 直接读这两文件（R-06 链路级递减）；
    返回两路径供测试覆盖 get_path / _find_skill_data 指向。
    """
    cultivate_path = os.path.join(tmp_dir, "cultivate.json")
    skill_path = os.path.join(tmp_dir, "skill_data.json")
    with open(cultivate_path, "w", encoding="utf-8") as f:
        json.dump({"data": {"items": [{"id": item_id, "count": owned}]}}, f)
    with open(skill_path, "w", encoding="utf-8") as f:
        json.dump({"items": {item_id: {"name": "技巧概要·卷3"}}}, f)
    return cultivate_path, skill_path


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
        # #111：带真实材料链跑正分支——库存 owned == count（ID 解析命中）→ scheduled。
        # 原空链时循环不执行、all_materials_sufficient 恒 True，库存 ID 解析/计数
        # 回归（owned 恒 0）逃逸测试。
        cultivate_path, skill_path = _write_inventory_files(
            self.tmp.name, "item_T3", 50
        )
        mats = [{"name": "技巧概要·卷3", "count": 50}]
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(rec, "get_path", return_value=cultivate_path),
            patch.object(rec, "_find_skill_data", return_value=skill_path),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_A", 1, mats),
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual([e["char_id"] for e in result["scheduled"]], ["char_A"])
        self.assertEqual(result["skipped"], [])

    def test_db_plan_skipped_when_inventory_short(self):
        # #111 对照：同材料链库存 owned < count → skipped（确保正分支不是恒 True）
        cultivate_path, skill_path = _write_inventory_files(self.tmp.name, "item_T3", 5)
        mats = [{"name": "技巧概要·卷3", "count": 50}]
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[_plan(char_id="char_A", skill_index=1)],
            ),
            patch.object(rec, "get_path", return_value=cultivate_path),
            patch.object(rec, "_find_skill_data", return_value=skill_path),
            patch.object(
                rec,
                "get_mastery_recommendations",
                return_value=_recommendations("char_A", 1, mats),
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual(result["scheduled"], [])
        self.assertEqual([e["char_id"] for e in result["skipped"]], ["char_A"])

    def test_db_plan_skipped_when_trainee_is_in_nontraining_schedule(self):
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
            patch(
                "arknights_mower.utils.mastery_support_data.trainee_schedule_conflict",
                return_value="char_A 出现在非训练室排班（room_1_1），不能进行专精训练",
            ),
        ):
            result = rec.auto_schedule_mastery_tasks()
        self.assertEqual(result["scheduled"], [])
        self.assertEqual(result["skipped"][0]["achievable"], False)
        self.assertIn("room_1_1", result["skipped"][0]["reason"])

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


if __name__ == "__main__":
    unittest.main()
