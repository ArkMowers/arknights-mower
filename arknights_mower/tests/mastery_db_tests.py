import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from arknights_mower.utils.mastery_db import (
    add_plan_checked,
    delete_plan,
    get_active_plan,
    get_all_plans,
    get_all_routes,
    get_failed_plans,
    get_next_idle_plan,
    get_plan_by_id,
    get_reconcile_plans,
    get_route,
    get_route_settings,
    insert_plan,
    is_operator_busy,
    save_route,
    save_route_settings,
    should_notify,
    update_plan_priority,
    update_plan_status,
)
from arknights_mower.utils.mastery_recommendation import get_current_mastery_level


class TestMasteryDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_insert_and_get(self):
        pid = insert_plan("char_001", 0, 1, skill_name="技能1", path=self.db_path)
        self.assertGreater(pid, 0)
        plan = get_plan_by_id(pid, path=self.db_path)
        self.assertEqual(plan["char_id"], "char_001")
        self.assertEqual(plan["skill_index"], 0)
        self.assertEqual(plan["target_level"], 1)
        self.assertEqual(plan["status"], "idle")
        self.assertEqual(plan["swap_frozen"], 0)

    def test_get_all_plans_excludes_completed(self):
        p1 = insert_plan("char_001", 0, 1, path=self.db_path)
        p2 = insert_plan("char_002", 1, 2, path=self.db_path)
        update_plan_status(p1, "completed", path=self.db_path)
        plans = get_all_plans(path=self.db_path)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["id"], p2)

    def test_priority_ordering(self):
        insert_plan("char_a", 0, 1, priority=10, path=self.db_path)
        insert_plan("char_b", 0, 1, priority=1, path=self.db_path)
        insert_plan("char_c", 0, 1, priority=5, path=self.db_path)
        plans = get_all_plans(path=self.db_path)
        priorities = [p["priority"] for p in plans]
        self.assertEqual(priorities, [1, 5, 10])

    def test_get_active_plan(self):
        p1 = insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertIsNone(get_active_plan(path=self.db_path))
        update_plan_status(p1, "training", path=self.db_path)
        active = get_active_plan(path=self.db_path)
        self.assertEqual(active["id"], p1)

    def test_get_next_idle_plan(self):
        insert_plan("char_a", 0, 1, priority=5, path=self.db_path)
        insert_plan("char_b", 0, 1, priority=1, path=self.db_path)
        nxt = get_next_idle_plan(path=self.db_path)
        self.assertEqual(nxt["char_id"], "char_b")

    def test_get_failed_plans(self):
        # #69：failed 计划带失败原因单独可查（前端展示用），active 计划不混入
        p1 = insert_plan("char_001", 0, 1, path=self.db_path)
        p2 = insert_plan("char_002", 1, 2, path=self.db_path)
        update_plan_status(p2, "failed", failed_reason="材料不足", path=self.db_path)
        update_plan_status(p1, "training", path=self.db_path)
        failed = get_failed_plans(path=self.db_path)
        self.assertEqual([f["id"] for f in failed], [p2])
        self.assertEqual(failed[0]["failed_reason"], "材料不足")

    def test_get_reconcile_plans_merge_and_sort(self):
        # #98：reconcile 计划集 = 非终态 + failed（completed 仍排除），跨两组合并后
        # 按 (priority, id) 排序——重复计划（同干员技能）时优先高优先级一条。
        p_fail_hi = insert_plan("char_fail", 0, 1, priority=10, path=self.db_path)
        p_idle_lo = insert_plan("char_idle", 0, 1, priority=1, path=self.db_path)
        p_train = insert_plan("char_train", 1, 2, path=self.db_path)  # priority 0
        p_done = insert_plan("char_done", 0, 1, priority=3, path=self.db_path)
        update_plan_status(p_fail_hi, "failed", failed_reason="材料不足", path=self.db_path)
        update_plan_status(p_train, "training", path=self.db_path)
        update_plan_status(p_done, "completed", path=self.db_path)
        plans = get_reconcile_plans(path=self.db_path)
        ids = [p["id"] for p in plans]
        self.assertIn(p_fail_hi, ids, "failed 应纳入 reconcile 计划集（#98）")
        self.assertIn(p_idle_lo, ids)
        self.assertIn(p_train, ids)
        self.assertNotIn(p_done, ids, "completed 仍排除（真正终态，不恢复）")
        self.assertEqual(
            [p["priority"] for p in plans],
            [0, 1, 10],
            "跨 get_all_plans/get_failed_plans 合并后按 priority 排序",
        )

    def test_update_status(self):
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertTrue(update_plan_status(pid, "arranging", path=self.db_path))
        plan = get_plan_by_id(pid, path=self.db_path)
        self.assertEqual(plan["status"], "arranging")

    def test_update_status_invalid(self):
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertFalse(update_plan_status(pid, "bogus", path=self.db_path))

    def test_update_status_with_extras(self):
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        update_plan_status(
            pid,
            "training",
            expires_at="2026-01-01 12:00:00",
            swap_frozen=1,
            path=self.db_path,
        )
        plan = get_plan_by_id(pid, path=self.db_path)
        self.assertEqual(plan["expires_at"], "2026-01-01 12:00:00")
        self.assertEqual(plan["swap_frozen"], 1)

    def test_update_priority(self):
        pid = insert_plan("char_001", 0, 1, priority=5, path=self.db_path)
        update_plan_priority(pid, 1, path=self.db_path)
        plan = get_plan_by_id(pid, path=self.db_path)
        self.assertEqual(plan["priority"], 1)

    def test_delete_plan(self):
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertTrue(delete_plan(pid, path=self.db_path))
        self.assertIsNone(get_plan_by_id(pid, path=self.db_path))

    def test_delete_plan_cleans_notify_dedup(self):
        # #97：删计划顺带清通知去重（②③⑥⑦⑧ 用 str(plan_id) 作 dedup_key），
        # 避免孤儿 dedup 残留
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertTrue(should_notify("fake_reset", str(pid), path=self.db_path))
        self.assertFalse(should_notify("fake_reset", str(pid), path=self.db_path), "首轮已去重")
        delete_plan(pid, path=self.db_path)
        self.assertTrue(
            should_notify("fake_reset", str(pid), path=self.db_path),
            "删除后该计划通知可重发（去重行已清）",
        )

    def test_ensure_tables_once_per_path(self):
        # #82：同一库路径进程内只建表一次（_tables_created 记录已建库路径）
        from arknights_mower.utils import mastery_db

        mastery_db._tables_created.discard(self.db_path)
        self.assertNotIn(self.db_path, mastery_db._tables_created)
        insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertIn(
            self.db_path, mastery_db._tables_created, "首次连接后应记录该库已建表"
        )

    def test_ensure_tables_recreates_when_db_truncated(self):
        # #82 沿用 #86 守卫：库文件被清空（0 字节=新库）→ 重置标记，下次连接重建表
        # 首次插入触发建表；清空后重建表，第二次插入必须成功
        insert_plan("char_001", 0, 1, path=self.db_path)
        with open(self.db_path, "wb"):
            pass  # 清空文件（模拟运行中库被重置）
        pid2 = insert_plan("char_002", 1, 2, path=self.db_path)  # 应重建表成功
        self.assertGreater(pid2, 0)
        plan = get_plan_by_id(pid2, path=self.db_path)
        self.assertEqual(plan["char_id"], "char_002")

    def test_is_operator_busy(self):
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        self.assertFalse(is_operator_busy("char_001", path=self.db_path))
        update_plan_status(pid, "training", path=self.db_path)
        self.assertTrue(is_operator_busy("char_001", path=self.db_path))
        self.assertFalse(is_operator_busy("char_002", path=self.db_path))

    def test_is_operator_busy_waits_collect(self):
        # #59：waiting_collect（练完没收）也算 busy，不能把训练中干员当空闲挪走
        pid = insert_plan("char_001", 0, 1, path=self.db_path)
        update_plan_status(pid, "waiting_collect", path=self.db_path)
        self.assertTrue(is_operator_busy("char_001", path=self.db_path))

    def test_is_operator_busy_resolves_null_char_name(self):
        # #59：存量计划 char_name 为 NULL 时按名匹配也能命中（回退查表）
        pid = insert_plan("char_103_angel", 0, 1, char_name=None, path=self.db_path)
        update_plan_status(pid, "training", path=self.db_path)
        self.assertTrue(is_operator_busy("能天使", path=self.db_path))

    def test_insert_plan_canonicalizes_skill_name(self):
        # #63：计划 skill_name 存规范格式 `{序数}技能·真名`（真名并入 skill_data.json）
        pid = insert_plan("char_103_angel", 1, 3, path=self.db_path)
        plan = get_plan_by_id(pid, path=self.db_path)
        self.assertEqual(plan["skill_name"], "二技能·扫射模式")

    def test_lazy_fill_legacy_plan(self):
        # #63：存量占位 skill_name（技能N）/ NULL char_name 在读取时懒填充
        import sqlite3

        get_all_plans(path=self.db_path)  # 触发建表
        conn = sqlite3.connect(self.db_path)
        try:
            cur = conn.execute(
                "INSERT INTO mastery_plan "
                "(char_id, char_name, skill_index, skill_name, target_level, priority) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("char_103_angel", None, 0, "技能1", 2, 0),
            )
            pid = cur.lastrowid
            conn.commit()
        finally:
            conn.close()
        plan = get_plan_by_id(pid, path=self.db_path)
        self.assertEqual(plan["skill_name"], "一技能·冲锋模式")
        self.assertEqual(plan["char_name"], "能天使")

    def test_should_notify_once(self):
        # #61：通知仅三类各一次（同 dedup_key 只发一次）
        self.assertTrue(
            should_notify("blocked", "2026-08-01 14:00:00", path=self.db_path)
        )
        self.assertFalse(
            should_notify("blocked", "2026-08-01 14:00:00", path=self.db_path)
        )
        self.assertTrue(
            should_notify("blocked", "2026-08-01 15:00:00", path=self.db_path)
        )
        self.assertTrue(should_notify("fake_reset", "5", path=self.db_path))
        # m3_collect 类型：同 dedup_key 首次 True、再次 False；换 key 重新 True
        self.assertTrue(should_notify("m3_collect", "7", path=self.db_path))
        self.assertFalse(should_notify("m3_collect", "7", path=self.db_path))
        self.assertTrue(should_notify("m3_collect", "8", path=self.db_path))

    def test_route_crud(self):
        save_route("近卫", '{"level_1": {"operator": "赤冬"}}', path=self.db_path)
        route = get_route("近卫", path=self.db_path)
        self.assertIsNotNone(route)
        self.assertIn("赤冬", route["supports"])

    def test_route_fallback_to_default(self):
        save_route(
            "近卫",
            '{"level_1": {"operator": "default"}}',
            is_default=1,
            path=self.db_path,
        )
        route = get_route("近卫", path=self.db_path)
        self.assertIn("default", route["supports"])
        save_route(
            "近卫",
            '{"level_1": {"operator": "custom"}}',
            is_default=0,
            path=self.db_path,
        )
        route = get_route("近卫", path=self.db_path)
        self.assertIn("custom", route["supports"])

    def test_route_settings_round_trip(self):
        save_route(
            "近卫",
            "[]",
            optimal=True,
            half_off=False,
            path=self.db_path,
        )

        route = get_route("近卫", path=self.db_path)

        self.assertEqual(route["supports"], "[]")
        self.assertEqual(route["optimal"], 1)
        self.assertEqual(route["half_off"], 0)

    def test_route_settings_defaults(self):
        # #91 修订：无设置行 → 中枢加成默认 0（不是 5）、缓冲默认 10
        self.assertEqual(
            get_route_settings(path=self.db_path),
            {"central_bonus": 0, "mastery_swap_buffer": 10},
        )

    def test_route_settings_save_and_read(self):
        save_route_settings(central_bonus=5, mastery_swap_buffer=15, path=self.db_path)
        self.assertEqual(
            get_route_settings(path=self.db_path),
            {"central_bonus": 5, "mastery_swap_buffer": 15},
        )
        # 再存回 0 也生效
        save_route_settings(central_bonus=0, mastery_swap_buffer=10, path=self.db_path)
        self.assertEqual(
            get_route_settings(path=self.db_path),
            {"central_bonus": 0, "mastery_swap_buffer": 10},
        )

    def test_get_all_routes_excludes_settings_row(self):
        # 设置行（__mastery_settings__）是全局配置，不该出现在职业路线列表里
        save_route("近卫", '{"level_1": {"operator": "赤冬"}}', path=self.db_path)
        save_route_settings(central_bonus=5, mastery_swap_buffer=15, path=self.db_path)
        routes = get_all_routes(path=self.db_path)
        self.assertEqual([r["profession"] for r in routes], ["近卫"])
        self.assertEqual(
            get_route("近卫", path=self.db_path)["supports"],
            '{"level_1": {"operator": "赤冬"}}',
        )

    def test_route_schema_migrates_existing_database(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "CREATE TABLE mastery_route ("
                "profession TEXT NOT NULL,"
                "supports TEXT NOT NULL DEFAULT '{}',"
                "is_default INTEGER DEFAULT 0,"
                "created_at TEXT DEFAULT (datetime('now','localtime')) ,"
                "UNIQUE(profession, is_default)"
                ")"
            )
            conn.execute(
                "INSERT INTO mastery_route (profession, supports, is_default) VALUES (?, ?, ?)",
                ("近卫", "[]", 0),
            )
            conn.commit()
        finally:
            conn.close()

        route = get_route("近卫", path=self.db_path)

        self.assertEqual(route["optimal"], 0)
        self.assertEqual(route["half_off"], 1)
        conn = sqlite3.connect(self.db_path)
        try:
            columns = {
                row[1] for row in conn.execute("PRAGMA table_info(mastery_route)")
            }
        finally:
            conn.close()
        self.assertIn("optimal", columns)
        self.assertIn("half_off", columns)

    # --- #65/B7 统一计划创建校验 ---

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_add_plan_checked_rejects_already_at_target(self, get_level, insert):
        # 干员已到目标档位 → 拒绝并给清晰文案，不落库
        get_level.return_value = 2
        plan_id, reason = add_plan_checked(
            "char_001", 0, target_level=2, path=self.db_path
        )
        self.assertLessEqual(plan_id, 0)
        self.assertIn("无需再练", reason)
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    def test_add_plan_checked_rejects_invalid_target(self, insert):
        # target_level 越界/非整数/布尔（True==1，不得静默当专一）拒绝，不落库
        for bad in (0, 4, -1, "3", True):
            plan_id, reason = add_plan_checked(
                "char_001", 0, target_level=bad, path=self.db_path
            )
            self.assertLessEqual(plan_id, 0)
            self.assertIn("无效", reason)
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_add_plan_checked_defaults_target_to_three(self, get_level, insert):
        # target_level 缺省 = 专三（与推荐一致）
        get_level.return_value = 1
        insert.return_value = 9
        plan_id, reason = add_plan_checked("char_001", 0, path=self.db_path)
        self.assertEqual(plan_id, 9)
        self.assertIsNone(reason)
        self.assertEqual(insert.call_args.kwargs["target_level"], 3)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_add_plan_checked_skips_check_when_level_unknown(self, get_level, insert):
        # cultivate.json 读不到当前等级（None）→ 跳过等级校验仍落库
        get_level.return_value = None
        insert.return_value = 10
        plan_id, reason = add_plan_checked(
            "char_001", 0, target_level=3, path=self.db_path
        )
        self.assertEqual(plan_id, 10)
        self.assertIsNone(reason)
        self.assertEqual(insert.call_args.kwargs["target_level"], 3)

    @patch("arknights_mower.utils.mastery_recommendation.get_path")
    def test_get_current_mastery_level_reads_cultivate(self, get_path_mock):
        # 从 cultivate.json 读干员技能当前专精等级
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "data": {
                        "characters": [
                            {"id": "char_001", "skills": [{"level": 0}, {"level": 2}]}
                        ]
                    }
                },
                f,
            )
            path = f.name
        get_path_mock.return_value = path
        try:
            self.assertEqual(get_current_mastery_level("char_001", 0), 0)
            self.assertEqual(get_current_mastery_level("char_001", 1), 2)
            self.assertIsNone(get_current_mastery_level("char_999", 0))
        finally:
            os.unlink(path)

    @patch("arknights_mower.utils.mastery_recommendation.get_path")
    def test_get_current_mastery_level_missing_or_bad_file(self, get_path_mock):
        # cultivate.json 缺失 / 非 JSON → None（跳过等级校验）
        get_path_mock.return_value = os.path.join(
            self.db_path + "_nope", "cultivate.json"
        )
        self.assertIsNone(get_current_mastery_level("char_001", 0))
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write("not json")
            path = f.name
        get_path_mock.return_value = path
        try:
            self.assertIsNone(get_current_mastery_level("char_001", 0))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
