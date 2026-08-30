import json
import sys
import types
import unittest
from datetime import datetime
from unittest.mock import MagicMock, call, patch

from flask import Flask

# base_schedule 导入链（cultivate_depot→skland）在 skland 模块加载时调用
# SecuritySm.get_d_id() 发网络请求（§14 环境性 flake，与测试无关）。与
# base_scheduler_tests 同款 stub。refresh 测试的 lazy import 在 os.path.exists
# 被 patch 的窗口内触发 skland 加载，不 stub 会误伤 requests 的 CA bundle 检查。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.views.mastery import mastery_bp  # noqa: E402


class TestMasteryRouteView(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(mastery_bp)
        self.client = app.test_client()

    @patch("arknights_mower.views.mastery.save_route")
    def test_route_post_forwards_all_persisted_settings(self, save_route_mock):
        response = self.client.post(
            "/mastery-route",
            json={
                "profession": "近卫",
                "supports": [],
                "optimal": True,
                "half_off": False,
            },
        )

        self.assertEqual(response.status_code, 200)
        save_route_mock.assert_called_once_with(
            "近卫",
            "[]",
            is_default=0,
            optimal=True,
            half_off=False,
        )

    @patch("arknights_mower.views.mastery.save_route")
    def test_route_post_rejects_invalid_json(self, save_route_mock):
        # #114：supports 不是合法 JSON → 400 拒绝保存（坏数据不得进库，读取端无守卫）
        for bad in ("not json", "{", "", '"broken'):
            r = self.client.post(
                "/mastery-route", json={"profession": "近卫", "supports": bad}
            )
            self.assertEqual(r.status_code, 400, f"supports={bad!r} 应 400")
            self.assertIn("合法 JSON", r.get_json()["error"])
        save_route_mock.assert_not_called()

    @patch("arknights_mower.views.mastery.save_route")
    def test_route_post_rejects_wrong_shape(self, save_route_mock):
        # #114：合法 JSON 但形态不是数组/包装对象/旧字典 → 400
        # （读取端 _route_entry_from_supports 返回 None 静默回退默认路线）；
        # level_N 值非 dict（如字符串）能过 json.loads 却在读取端 dict() 抛 ValueError
        # 被 _get_plan_route 吞掉静默回退 → 同样拒绝
        for bad in (
            "42",
            '"hello"',
            "null",
            '{"foo": 1}',
            "true",
            '{"level_1": "garbage"}',
            '{"level_1": 42}',
        ):
            r = self.client.post(
                "/mastery-route", json={"profession": "近卫", "supports": bad}
            )
            self.assertEqual(r.status_code, 400, f"supports={bad!r} 应 400")
        save_route_mock.assert_not_called()

    @patch("arknights_mower.views.mastery.save_route")
    def test_route_post_accepts_valid_shapes(self, save_route_mock):
        # #114：三种合法形态（数组/包装对象/旧字典）都放行保存
        valid = (
            '[{"name": "银灰", "skill_level": 1}]',
            '{"supports": [{"name": "银灰", "skill_level": 1}]}',
            '{"level_1": {"operator": "赤冬"}}',
        )
        for good in valid:
            r = self.client.post(
                "/mastery-route", json={"profession": "近卫", "supports": good}
            )
            self.assertEqual(r.status_code, 200, f"supports={good!r} 应 200")
        self.assertEqual(save_route_mock.call_count, len(valid))

    @patch("arknights_mower.views.mastery.get_route_settings")
    @patch("arknights_mower.views.mastery.get_all_routes")
    def test_route_get_includes_settings(self, routes_mock, settings_mock):
        # #91 修订：GET /mastery-route 带全局设置（中枢加成 + 换人缓冲），前端一个开关读它
        routes_mock.return_value = []
        settings_mock.return_value = {"central_bonus": 5, "mastery_swap_buffer": 15}
        response = self.client.get("/mastery-route")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(
            data["settings"], {"central_bonus": 5, "mastery_swap_buffer": 15}
        )
        self.assertEqual(data["routes"], [])

    @patch("arknights_mower.views.mastery.save_route_settings")
    def test_route_settings_post_forwards_values(self, save_mock):
        response = self.client.post(
            "/mastery-route/settings",
            json={"central_bonus": 5, "mastery_swap_buffer": 15},
        )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_called_once_with(central_bonus=5, mastery_swap_buffer=15)

    @patch("arknights_mower.views.mastery.save_route_settings")
    def test_route_settings_post_keeps_zero_buffer(self, save_mock):
        # review 修复：显式 buffer=0 合法（UI min=0），不得被 or 10 吞成 10
        response = self.client.post(
            "/mastery-route/settings",
            json={"central_bonus": 0, "mastery_swap_buffer": 0},
        )
        self.assertEqual(response.status_code, 200)
        save_mock.assert_called_once_with(central_bonus=0, mastery_swap_buffer=0)


class TestMasteryPlanView(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(mastery_bp)
        self.client = app.test_client()

    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.views.mastery.get_all_history")
    @patch("arknights_mower.views.mastery.get_failed_plans")
    @patch("arknights_mower.views.mastery.get_all_plans")
    def test_plan_get_includes_failed_plans(
        self, get_all, get_failed, get_history, get_skill
    ):
        # #69：failed 计划要带给前端（含 failed_reason），不能"凭空消失"
        get_all.return_value = [
            {
                "id": 1,
                "char_id": "char_001",
                "char_name": "测试干员",
                "skill_index": 0,
                "skill_name": "一技能",
                "target_level": 1,
                "status": "idle",
                "priority": 0,
                "expires_at": None,
                "failed_reason": None,
            }
        ]
        get_failed.return_value = [
            {
                "id": 2,
                "char_id": "char_002",
                "char_name": "失败干员",
                "skill_index": 1,
                "skill_name": "二技能",
                "target_level": 2,
                "status": "failed",
                "priority": 0,
                "expires_at": None,
                "failed_reason": "材料不足",
            }
        ]
        get_history.return_value = []
        get_skill.return_value = {"characters": {}}

        response = self.client.get("/mastery-plan")
        self.assertEqual(response.status_code, 200)
        plans = response.get_json()["plans"]
        self.assertEqual([p["status"] for p in plans], ["idle", "failed"])
        failed = next(p for p in plans if p["status"] == "failed")
        self.assertEqual(failed["failed_reason"], "材料不足")
        self.assertEqual(failed["name"], "失败干员")

    def _char_table(self):
        return {
            "characters": {
                "char_001": {
                    "name": "阿米娅",
                    "skills": [
                        {"name": "一技能"},
                        {"name": "二技能"},
                        {"name": "三技能"},
                    ],
                }
            }
        }

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_bulk_rejects_out_of_range_target(self, get_skill, insert):
        # #65/B7：bulk 路径 target_level 越界（0/4/布尔 true）拒绝，不落库
        get_skill.return_value = self._char_table()
        for bad in (0, 4, True):
            r = self.client.post(
                "/mastery-plan",
                json={
                    "items": [{"name": "阿米娅", "skill_index": 0, "target_level": bad}]
                },
            )
            res = r.get_json()["results"][0]
            self.assertEqual(res["status"], "error")
            self.assertIn("无效", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_bulk_rejects_non_int_target(self, get_skill, insert):
        # #65/B7：target_level 非整数（如字符串 "3"）拒绝
        get_skill.return_value = self._char_table()
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 0, "target_level": "3"}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "error")
        self.assertIn("无效", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_bulk_defaults_target_to_three(self, get_level, get_skill, insert):
        # #65/B7：bulk 未传 target_level 默认专三（与推荐一致），不再硬编码专一
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 5
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 0}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "added")
        self.assertEqual(res["id"], 5)
        self.assertEqual(insert.call_args.kwargs["target_level"], 3)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_bulk_honors_explicit_target(self, get_level, get_skill, insert):
        # #65/B7：bulk 显式 target_level 被采纳（在范围内且低于当前等级）
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 8
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 1, "target_level": 2}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "added")
        self.assertEqual(insert.call_args.kwargs["target_level"], 2)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_bulk_rejects_operator_already_at_target(
        self, get_level, get_skill, insert
    ):
        # #65/B7：干员已到目标档位 → 拒绝并给清晰文案，不落库
        get_skill.return_value = self._char_table()
        get_level.return_value = 2
        r = self.client.post(
            "/mastery-plan",
            json={"items": [{"name": "阿米娅", "skill_index": 0, "target_level": 2}]},
        )
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "error")
        self.assertIn("无需再练", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_flat_defaults_target_to_three(self, get_level, get_skill, insert):
        # #65/B7：扁平路径不传 target_level，默认专三（不再硬编码专一）
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 7
        r = self.client.post("/mastery-plan", json={"阿米娅": 0})
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "added")
        self.assertEqual(res["id"], 7)
        self.assertEqual(insert.call_args.kwargs["target_level"], 3)

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_flat_rejects_operator_already_at_target(
        self, get_level, get_skill, insert
    ):
        # #65/B7：干员已专三（≥ 默认目标）→ 扁平路径也拒绝
        get_skill.return_value = self._char_table()
        get_level.return_value = 3
        r = self.client.post("/mastery-plan", json={"阿米娅": 0})
        res = r.get_json()["results"][0]
        self.assertEqual(res["status"], "error")
        self.assertIn("已专", res["reason"])
        insert.assert_not_called()

    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_flat_rejects_bool_skill_index(self, get_skill, insert):
        # #112：bool 是 int 子类（True in (0,1,2) 为真）——JSON true 必须被拒绝为
        # invalid skill_index，不得静默当成二技能建错计划
        get_skill.return_value = self._char_table()
        for bad in (True, False):
            r = self.client.post("/mastery-plan", json={"阿米娅": bad})
            res = r.get_json()["results"][0]
            self.assertEqual(res["status"], "error")
            self.assertEqual(res["reason"], "invalid skill_index")
        insert.assert_not_called()

    # --- #97 删除清理 ---

    @patch("arknights_mower.views.mastery._purge_plan_tasks")
    @patch("arknights_mower.views.mastery.delete_plan")
    def test_delete_purges_queued_tasks(self, delete_mock, purge_mock):
        # #97：删除计划后清残留队列任务（该 plan_key 的 SKILL_UPGRADE/SWAP/fill）
        delete_mock.return_value = True
        r = self.client.delete("/mastery-plan", json={"id": 3})
        self.assertEqual(r.status_code, 200)
        delete_mock.assert_called_once_with(3)
        purge_mock.assert_called_once_with(3)

    @patch("arknights_mower.views.mastery.delete_plan")
    def test_delete_requires_id(self, delete_mock):
        # 存量：无 id → 400
        r = self.client.delete("/mastery-plan", json={})
        self.assertEqual(r.status_code, 400)
        delete_mock.assert_not_called()

    @patch("arknights_mower.views.mastery.delete_plan")
    def test_delete_rejects_non_numeric_id(self, delete_mock):
        # #113：非数字 id 不再 int() ValueError → 500，应 400（对齐 #97 retry）
        for bad in ("abc", True, 1.5):
            r = self.client.delete("/mastery-plan", json={"id": bad})
            self.assertEqual(r.status_code, 400, f"id={bad!r} 应 400")
            self.assertIn("invalid id", r.get_json()["error"])
        delete_mock.assert_not_called()

    @patch("arknights_mower.views.mastery.update_plan_priority")
    def test_order_rejects_non_numeric_id(self, update_mock):
        # #113：PATCH order 非数字 id → 400（不再 int() ValueError → 500）
        r = self.client.patch(
            "/mastery-plan/order", json=[{"id": "abc", "priority": 1}]
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid id", r.get_json()["error"])
        update_mock.assert_not_called()

    @patch("arknights_mower.views.mastery.update_plan_priority")
    def test_order_rejects_non_numeric_priority(self, update_mock):
        # #113：PATCH order 非数字 priority → 400（与 id 同型）
        r = self.client.patch(
            "/mastery-plan/order", json=[{"id": 3, "priority": "abc"}]
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("invalid priority", r.get_json()["error"])
        update_mock.assert_not_called()

    def test_purge_plan_tasks_removes_plan_key_tasks(self):
        # #97：_purge_plan_tasks 清掉该计划 plan_key 的队列任务（SKILL_UPGRADE/SWAP，
        # #101 补位不再有独立 fill-{id} 键），保留其它
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
        from arknights_mower.views.mastery import _purge_plan_tasks

        fake = types.ModuleType("arknights_mower.__main__")
        sched = types.SimpleNamespace()
        t1 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t1.plan_key = "5"
        t2 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SWAP_SUPPORT)
        t2.plan_key = "5"
        t3 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t3.plan_key = "9"
        sched.tasks = [t1, t2, t3]
        fake.base_scheduler = sched
        with patch.dict(sys.modules, {"arknights_mower.__main__": fake}):
            _purge_plan_tasks(5)
        remaining = [getattr(t, "plan_key", None) for t in sched.tasks]
        self.assertEqual(remaining, ["9"], "plan_key=5 应清掉，plan_key=9 保留")

    def test_purge_plan_tasks_keeps_current_dispatch(self):
        # #97 review 修复：当前派发任务（base_scheduler.task）不删——主循环 dispatch 完
        # 按 `del self.tasks[0]` 删除它，若移走会误删下一个排队任务
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
        from arknights_mower.views.mastery import _purge_plan_tasks

        fake = types.ModuleType("arknights_mower.__main__")
        sched = types.SimpleNamespace()
        t1 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t1.plan_key = "5"
        t2 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SWAP_SUPPORT)
        t2.plan_key = "5"
        t3 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t3.plan_key = "9"
        sched.tasks = [t1, t2, t3]
        sched.task = t1  # t1（计划5 的任务）正在派发
        fake.base_scheduler = sched
        with patch.dict(sys.modules, {"arknights_mower.__main__": fake}):
            _purge_plan_tasks(5)
        remaining = [getattr(t, "plan_key", None) for t in sched.tasks]
        self.assertEqual(
            remaining,
            ["5", "9"],
            "当前派发任务(plan_key=5)保留（del self.tasks[0] 会删它），另一条 plan_key=5 清掉",
        )

    def test_purge_plan_tasks_guards_no_scheduler(self):
        # #97：base_scheduler 未运行（None）→ 防御不崩
        from arknights_mower.views.mastery import _purge_plan_tasks

        fake = types.ModuleType("arknights_mower.__main__")
        fake.base_scheduler = None
        with patch.dict(sys.modules, {"arknights_mower.__main__": fake}):
            _purge_plan_tasks(5)  # 不应抛异常

    def test_purge_plan_tasks_snapshot_excludes_current_deleted_plan(self):
        # #147 边界：被删计划的任务当前正被派发（base_scheduler.task）→ live 队列保留
        # （del self.tasks[0] 占位），但持久化快照必须剔除它——否则重启 load_state 复活
        from arknights_mower.utils.scheduler_task import SchedulerTask, TaskTypes
        from arknights_mower.views.mastery import _purge_plan_tasks

        fake = types.ModuleType("arknights_mower.__main__")
        sched = types.SimpleNamespace()
        t1 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t1.plan_key = "5"
        t2 = SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        t2.plan_key = "9"
        sched.tasks = [t1, t2]
        sched.task = t1  # 计划5 的任务正在派发
        fake.base_scheduler = sched
        saved = {}
        with patch.dict(sys.modules, {"arknights_mower.__main__": fake}):
            with (
                patch(
                    "arknights_mower.solvers.record.current_state",
                    return_value={"tasks": list(sched.tasks)},
                ) as cs,
                patch(
                    "arknights_mower.solvers.record.save_state_to_db",
                    side_effect=lambda st: saved.update(st) or True,
                ),
            ):
                _purge_plan_tasks(5)
        cs.assert_called_once()
        persisted = [getattr(t, "plan_key", None) for t in saved["tasks"]]
        self.assertEqual(persisted, ["9"], "快照应剔除被删计划的当前派发任务")
        live = [getattr(t, "plan_key", None) for t in sched.tasks]
        self.assertEqual(
            live, ["5", "9"], "live 队列仍保留 current（del tasks[0] 占位）"
        )

    # --- 一键专精立即派发 ---

    @patch("arknights_mower.views.mastery._dispatch_new_plans_immediately")
    @patch("arknights_mower.utils.mastery_db.insert_plan")
    @patch("arknights_mower.views.mastery.get_skill_data")
    @patch("arknights_mower.utils.mastery_recommendation.get_current_mastery_level")
    def test_post_added_dispatches_immediately(
        self, get_level, get_skill, insert, dispatch
    ):
        # 一键专精建计划成功后立即派发，不再等下次仓库扫描
        get_skill.return_value = self._char_table()
        get_level.return_value = 1
        insert.return_value = 5
        r = self.client.post(
            "/mastery-plan", json={"items": [{"name": "阿米娅", "skill_index": 0}]}
        )
        self.assertEqual(r.get_json()["results"][0]["status"], "added")
        dispatch.assert_called_once()

    @patch("arknights_mower.views.mastery._dispatch_new_plans_immediately")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_post_no_add_no_dispatch(self, get_skill, dispatch):
        # 全部 error（无新计划落库）→ 不派发
        get_skill.return_value = self._char_table()
        r = self.client.post(
            "/mastery-plan", json={"items": [{"name": "不存在", "skill_index": 0}]}
        )
        self.assertEqual(r.get_json()["results"][0]["status"], "error")
        dispatch.assert_not_called()

    @patch("arknights_mower.views.mastery._dispatch_new_plans_immediately")
    @patch("arknights_mower.views.mastery.get_skill_data")
    def test_post_batch_all_errors_no_dispatch(self, get_skill, dispatch):
        # batch 多计划全部 error（无 added）→ 不派发
        get_skill.return_value = self._char_table()
        r = self.client.post(
            "/mastery-plan",
            json={
                "items": [
                    {"name": "不存在1", "skill_index": 0},
                    {"name": "不存在2", "skill_index": 1},
                ]
            },
        )
        statuses = [x["status"] for x in r.get_json()["results"]]
        self.assertEqual(statuses, ["error", "error"])
        dispatch.assert_not_called()

    def test_dispatch_new_plans_immediately_calls_dispatch(self):
        # 材料核算后把 scheduled 交给 _dispatch_scan_start_tasks（复用扫描派发逻辑）
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        sched = MagicMock()
        fake.base_scheduler = sched
        scheduled = [{"char_id": "char_a", "skill_index": 1}]
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={"scheduled": scheduled, "skipped": []},
            ),
            patch("arknights_mower.views.mastery._refresh_cultivate_if_stale"),
            patch("arknights_mower.utils.config.wake_scheduler", MagicMock()),
        ):
            _dispatch_new_plans_immediately()
        sched._dispatch_scan_start_tasks.assert_called_once_with(scheduled)

    def test_dispatch_new_plans_immediately_noop_when_nothing_scheduled(self):
        # 材料不足（scheduled 空）→ dispatch 拿空列表（_dispatch_scan_start_tasks 空返回
        # no-op，不产生开始任务）——钉死「材料不足不派发」行为
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        sched = MagicMock()
        fake.base_scheduler = sched
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={
                    "scheduled": [],
                    "skipped": [{"char_id": "char_a", "skill_index": 1}],
                },
            ),
            patch("arknights_mower.views.mastery._refresh_cultivate_if_stale"),
            patch("arknights_mower.utils.config.wake_scheduler", MagicMock()),
        ):
            _dispatch_new_plans_immediately()
        sched._dispatch_scan_start_tasks.assert_called_once_with([])

    def test_dispatch_refreshes_stale_cultivate_and_wakes(self):
        # #141 方案 A：派发前刷新 stale cultivate.json；scheduled 非空 → 唤醒调度休眠
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        sched = MagicMock()
        fake.base_scheduler = sched
        scheduled = [{"char_id": "char_a", "skill_index": 1}]
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={"scheduled": scheduled, "skipped": []},
            ),
            patch(
                "arknights_mower.views.mastery._refresh_cultivate_if_stale"
            ) as refresh,
            patch("arknights_mower.utils.config.wake_scheduler", MagicMock()) as wake,
        ):
            _dispatch_new_plans_immediately()
        refresh.assert_called_once()
        sched._dispatch_scan_start_tasks.assert_called_once_with(scheduled)
        wake.set.assert_called_once()

    def test_dispatch_no_wake_when_nothing_scheduled(self):
        # 材料不足（scheduled 空）→ 派发空列表、不唤醒（无任务可执行，唤醒无意义）
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        fake.base_scheduler = MagicMock()
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={"scheduled": [], "skipped": [{"char_id": "a"}]},
            ),
            patch("arknights_mower.views.mastery._refresh_cultivate_if_stale"),
            patch("arknights_mower.utils.config.wake_scheduler", MagicMock()) as wake,
        ):
            _dispatch_new_plans_immediately()
        wake.set.assert_not_called()

    def test_refresh_cultivate_skips_when_fresh(self):
        # cultivate.json mtime < maa_gap → 不拉取（尊重间隔铁律，不绕过间隔打森空岛）
        from arknights_mower.views.mastery import _refresh_cultivate_if_stale

        with (
            patch(
                "arknights_mower.views.mastery.get_path",
                return_value="C:/fake/cultivate.json",
            ),
            patch("os.path.exists", return_value=True),
            patch("os.path.getmtime", return_value=datetime.now().timestamp()),
            patch("arknights_mower.solvers.cultivate_depot.cultivate.start") as start,
        ):
            _refresh_cultivate_if_stale()
        start.assert_not_called()

    def test_refresh_cultivate_when_stale_or_missing(self):
        # 缺失（exists=False）/ 过期（mtime > maa_gap）→ 拉取刷新（森空岛）
        from arknights_mower.views.mastery import _refresh_cultivate_if_stale

        with (
            patch(
                "arknights_mower.views.mastery.get_path",
                return_value="C:/fake/cultivate.json",
            ),
            patch("os.path.exists", return_value=False),
            patch("arknights_mower.solvers.cultivate_depot.cultivate.start") as start,
        ):
            _refresh_cultivate_if_stale()
        start.assert_called_once()

    def test_chars_missing_from_cultivate(self):
        # #141 review 跟进：新干员不在本地 cultivate.json characters → 缺失；在数据里
        # （含被推荐过滤的非精二）不算缺失
        from arknights_mower.views.mastery import _chars_missing_from_cultivate

        fake_path = "C:/fake/cultivate.json"
        with (
            patch("arknights_mower.views.mastery.get_path", return_value=fake_path),
            patch("os.path.exists", return_value=True),
            patch(
                "builtins.open",
                unittest.mock.mock_open(
                    read_data=json.dumps(
                        {
                            "data": {
                                "characters": [
                                    {"id": "char_old", "name": "旧干员"},
                                    {"id": "char_new", "name": "新干员"},
                                ]
                            }
                        }
                    )
                ),
            ),
        ):
            self.assertEqual(
                _chars_missing_from_cultivate(["char_old", "char_new"]), set()
            )
            self.assertEqual(
                _chars_missing_from_cultivate(["char_ghost"]), {"char_ghost"}
            )

    def test_chars_missing_no_file_returns_all(self):
        from arknights_mower.views.mastery import _chars_missing_from_cultivate

        with (
            patch(
                "arknights_mower.views.mastery.get_path",
                return_value="C:/fake/cultivate.json",
            ),
            patch("os.path.exists", return_value=False),
        ):
            self.assertEqual(_chars_missing_from_cultivate(["char_a"]), {"char_a"})

    def test_dispatch_forces_refresh_when_new_char_missing(self):
        # #141 review 跟进：新增干员不在本地 cultivate 数据（新获得）→ 强制拉一次再重算
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        sched = MagicMock()
        fake.base_scheduler = sched
        scheduled = [{"char_id": "char_new", "skill_index": 1}]
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={"scheduled": scheduled, "skipped": []},
            ),
            patch(
                "arknights_mower.views.mastery._chars_missing_from_cultivate",
                return_value={"char_new"},
            ),
            patch(
                "arknights_mower.views.mastery._refresh_cultivate_if_stale"
            ) as refresh,
            patch("arknights_mower.utils.config.wake_scheduler", MagicMock()),
        ):
            _dispatch_new_plans_immediately(chars=["char_new"])
        # 第一次 stale 刷新 + 新干员缺失强制刷新，各一次
        self.assertEqual(refresh.call_count, 2)
        self.assertEqual(refresh.call_args_list[1], call(force=True))

    def test_dispatch_no_force_when_char_in_data(self):
        # 干员已在本地数据（非精二等被过滤的不算缺失）→ 不强制刷新
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        fake.base_scheduler = MagicMock()
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={"scheduled": [], "skipped": []},
            ),
            patch(
                "arknights_mower.views.mastery._chars_missing_from_cultivate",
                return_value=set(),
            ),
            patch(
                "arknights_mower.views.mastery._refresh_cultivate_if_stale"
            ) as refresh,
            patch("arknights_mower.utils.config.wake_scheduler", MagicMock()),
        ):
            _dispatch_new_plans_immediately(chars=["char_old"])
        refresh.assert_called_once()  # 只有 stale 刷新，无强制刷新

    def test_dispatch_new_plans_immediately_gated_off(self):
        # enable_mastery=OFF 不派发（与扫描派发一致，铁律10「留」半边）
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        fake.base_scheduler = MagicMock()
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", False),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks"
            ) as mock_auto,
        ):
            _dispatch_new_plans_immediately()
        mock_auto.assert_not_called()
        fake.base_scheduler._dispatch_scan_start_tasks.assert_not_called()

    def test_dispatch_new_plans_immediately_guards_no_scheduler(self):
        # base_scheduler 未运行（None）→ 防御不崩
        from arknights_mower.views.mastery import _dispatch_new_plans_immediately

        fake = types.ModuleType("arknights_mower.__main__")
        fake.base_scheduler = None
        with (
            patch.dict(sys.modules, {"arknights_mower.__main__": fake}),
            patch("arknights_mower.views.mastery.config.conf.enable_mastery", True),
        ):
            _dispatch_new_plans_immediately()  # 不应抛异常


if __name__ == "__main__":
    unittest.main()
