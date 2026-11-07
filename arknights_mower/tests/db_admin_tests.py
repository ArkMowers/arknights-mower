"""数据库管理接口（db_admin）测试。

- `/db-admin/stats`：返回每类可删数据的行数 + 专精计划 active 数。
- `/db-admin/delete`：按白名单类删行（DELETE FROM），**绝不 DROP TABLE**（#82 建表守卫
  进程内只跑一次，被 DROP 的表不会重建，下次读写即 no-such-table）；未知键整体拒绝。
"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from flask import Flask

from arknights_mower.solvers import record
from arknights_mower.utils import mastery_db
from arknights_mower.views.db_admin import CATEGORY_TABLES, db_admin_bp

ALL_TABLES = list(CATEGORY_TABLES.values())


def _seed_db(path):
    """建一个带全部白名单表 + 若干行的临时库。"""
    # 重置建表守卫标记（#82 进程内只跑一次）——每个临时库都是新库，要重建表
    record._tables_created = False
    mastery_db._tables_created.discard(path)
    conn = sqlite3.connect(path)
    record._ensure_tables(conn)
    mastery_db._ensure_tables(conn, path)
    conn.executescript(
        """
        INSERT INTO mastery_plan (char_id, skill_index, target_level, status)
            VALUES ('char_a', 0, 3, 'idle');
        INSERT INTO mastery_plan (char_id, skill_index, target_level, status)
            VALUES ('char_b', 1, 3, 'training');
        INSERT INTO mastery_route (profession, supports, is_default) VALUES ('近卫', '[]', 1);
        INSERT INTO mastery_route (profession, supports, is_default) VALUES ('术师', '[]', 0);
        INSERT INTO mastery_notify (notify_type, dedup_key) VALUES ('blocked', 'k1');
        INSERT INTO log (time, task, level, message) VALUES (1, 'x', 'INFO', 'm');
        INSERT INTO agent_action (name) VALUES ('能天使');
        INSERT INTO operation_history (stage_id) VALUES ('stage_a');
        INSERT INTO trading_history (time, server_date, type, price)
            VALUES (1, '2026-01-01', 'buy', 100);
        INSERT INTO inventory (item_name, count) VALUES ('碳素', 5);
        INSERT INTO saved_state (time, state) VALUES ('2026-01-01', X'00');
        """
    )
    conn.commit()
    conn.close()


def _make_app():
    app = Flask(__name__)
    app.register_blueprint(db_admin_bp)
    return app


@contextmanager
def _patch_conn(path):
    """把 record._conn 指向临时库（隔离真实 data.db）。

    **不设 row_factory**——与生产 record._conn 一致（返回元组），保证接口用位置索引，
    防止「测试里设了 row_factory、生产没有」的伪绿（stats 曾因此全 0/500）。
    """

    @contextmanager
    def _conn():
        conn = sqlite3.connect(path)
        try:
            yield conn
        finally:
            conn.close()

    with patch.object(record, "_conn", _conn):
        yield


class TestDbAdminStats(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        _seed_db(self.db_path)
        self.client = _make_app().test_client()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_stats_returns_counts(self):
        with _patch_conn(self.db_path):
            resp = self.client.get("/db-admin/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["mastery_plan"], 2)
        self.assertEqual(data["mastery_route"], 2)
        self.assertEqual(data["mastery_notify"], 1)
        self.assertEqual(data["log"], 1)
        self.assertEqual(data["agent_action"], 1)
        self.assertEqual(data["operation_history"], 1)
        self.assertEqual(data["trading_history"], 1)
        self.assertEqual(data["inventory"], 1)
        self.assertEqual(data["saved_state"], 1)
        self.assertEqual(data["mastery_plan_active"], 1, "training 计划计入 active")

    def test_token_required(self):
        app = _make_app()
        app.token = "secret"
        client = app.test_client()
        with _patch_conn(self.db_path):
            resp = client.get("/db-admin/stats")
        self.assertEqual(resp.status_code, 403)

    def test_stats_fresh_install_mastery_tables_missing(self):
        # 全新安装：mastery 表从未创建（record._ensure_tables 只管 record 表）→
        # stats 不 500，专精各类按 0，运行数据表照常统计
        fresh = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        fresh_path = fresh.name
        fresh.close()
        try:
            conn = sqlite3.connect(fresh_path)
            record._tables_created = False
            record._ensure_tables(conn)  # 只建 record 表，不建 mastery 表
            conn.execute(
                "INSERT INTO log (time, task, level, message) VALUES (1, 'x', 'I', 'm')"
            )
            conn.commit()
            conn.close()

            @contextmanager
            def _c():
                c = sqlite3.connect(fresh_path)
                try:
                    yield c
                finally:
                    c.close()

            with patch.object(record, "_conn", _c):
                resp = self.client.get("/db-admin/stats")
            self.assertEqual(resp.status_code, 200)
            data = resp.get_json()
            self.assertEqual(data["mastery_plan"], 0, "未建表按 0，不 500")
            self.assertEqual(data["mastery_plan_active"], 0)
            self.assertEqual(data["log"], 1, "record 表照常统计")
        finally:
            os.unlink(fresh_path)


class TestDbAdminDelete(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        _seed_db(self.db_path)
        self.client = _make_app().test_client()

    def tearDown(self):
        os.unlink(self.db_path)

    def test_delete_rows(self):
        with _patch_conn(self.db_path):
            resp = self.client.post(
                "/db-admin/delete", json={"categories": ["mastery_plan", "log"]}
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["deleted"]["mastery_plan"], 2)
        self.assertEqual(data["deleted"]["log"], 1)
        # 未选的类不受影响
        with _patch_conn(self.db_path):
            resp2 = self.client.get("/db-admin/stats")
        counts = resp2.get_json()
        self.assertEqual(counts["mastery_plan"], 0)
        self.assertEqual(counts["log"], 0)
        self.assertEqual(counts["agent_action"], 1)

    def test_delete_does_not_drop_table(self):
        # 删完全部类后表结构必须仍在（可继续插入）——防 #82 守卫误判 no-such-table
        with _patch_conn(self.db_path):
            resp = self.client.post("/db-admin/delete", json={"categories": ALL_TABLES})
        self.assertEqual(resp.status_code, 200)
        conn = sqlite3.connect(self.db_path)
        try:
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            conn.execute(
                "INSERT INTO mastery_plan (char_id, skill_index, target_level)"
                " VALUES ('char_x', 2, 3)"
            )
            conn.commit()
        finally:
            conn.close()
        for t in ALL_TABLES:
            self.assertIn(t, names, f"{t} 不能被 DROP（#82 守卫不重建被删的表）")

    def test_unknown_category_rejected(self):
        with _patch_conn(self.db_path):
            resp = self.client.post(
                "/db-admin/delete",
                json={"categories": ["mastery_plan", "secret_table"]},
            )
        self.assertEqual(resp.status_code, 400)
        # 白名单外不可触碰：整体拒绝，mastery_plan 未被删
        with _patch_conn(self.db_path):
            resp2 = self.client.get("/db-admin/stats")
        self.assertEqual(resp2.get_json()["mastery_plan"], 2)

    def test_empty_categories_rejected(self):
        with _patch_conn(self.db_path):
            resp = self.client.post("/db-admin/delete", json={"categories": []})
        self.assertEqual(resp.status_code, 400)

    def test_delete_saved_state_then_reinsert_works(self):
        # 运行缓存删除后：表仍在、可再插入（程序下次保存会重建）
        with _patch_conn(self.db_path):
            resp = self.client.post(
                "/db-admin/delete", json={"categories": ["saved_state"]}
            )
        self.assertEqual(resp.status_code, 200)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO saved_state (time, state) VALUES ('2026-01-01', X'00')"
            )
            conn.commit()
        finally:
            conn.close()

    def test_delete_mastery_plan_purges_queued_tasks(self):
        # #118：批量删计划后清 #97 队列残留任务（plan_key=旧id 的 SKILL_UPGRADE/SWAP
        # 照常派发到已删计划），与 DELETE /mastery-plan 的清理对齐
        import sys
        import types
        from datetime import datetime

        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        fake = types.ModuleType("arknights_mower.__main__")
        sched = types.SimpleNamespace()
        t1 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t1.plan_key = "1"
        t2 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SWAP_SUPPORT)
        t2.plan_key = "2"
        t3 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t3.plan_key = "9"
        sched.tasks = [t1, t2, t3]
        fake.base_scheduler = sched
        with _patch_conn(self.db_path):
            with patch.dict(sys.modules, {"arknights_mower.__main__": fake}):
                resp = self.client.post(
                    "/db-admin/delete", json={"categories": ["mastery_plan"]}
                )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["deleted"]["mastery_plan"], 2)
        remaining = [getattr(t, "plan_key", None) for t in sched.tasks]
        self.assertEqual(
            remaining, ["9"], "plan_key=种子库计划id(1/2) 应清掉，plan_key=9 保留"
        )

    def test_delete_other_tables_keeps_queued_tasks(self):
        # #118：删非 mastery_plan 类别不触发队列清理（只清计划类）
        import sys
        import types
        from datetime import datetime

        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes

        fake = types.ModuleType("arknights_mower.__main__")
        sched = types.SimpleNamespace()
        t1 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t1.plan_key = "1"
        sched.tasks = [t1]
        fake.base_scheduler = sched
        with _patch_conn(self.db_path):
            with patch.dict(sys.modules, {"arknights_mower.__main__": fake}):
                resp = self.client.post(
                    "/db-admin/delete", json={"categories": ["log"]}
                )
        self.assertEqual(resp.status_code, 200)
        remaining = [getattr(t, "plan_key", None) for t in sched.tasks]
        self.assertEqual(remaining, ["1"], "删 log 不应清计划队列任务")


if __name__ == "__main__":
    unittest.main()
