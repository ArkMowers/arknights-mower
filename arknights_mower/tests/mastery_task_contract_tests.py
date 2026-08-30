"""#71 一键专精流接入 DB 计划架构——/task 契约 + 前端流契约测试。

- 服务端 `/task`：原始「技能专精」任务被明确拒绝并指引 POST /mastery-plan，不再死路；
  `upgrade_support` 载荷不再被消费。空任务 / 加工材料等其它类型仍照常入队。
- 前端流：一键专精（MasteryRecommendation.vue）与手动对话框（TaskDialog.vue）都调用
  POST /mastery-plan，不再提交原始「技能专精」/task（前端无测试框架，用源码契约守卫）。
- 派发链路（AC2）：计划创建 API 落库的计划必须被扫描派发 `_dispatch_scan_start_tasks`
  找到并入队开始任务，否则前端建了计划也不会开始训练。
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytz
from flask import Flask

import arknights_mower.views.task as task_module
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.mastery_db import add_plan_checked, get_all_plans
from arknights_mower.utils.scheduler_task import TaskTypes
from arknights_mower.views.task import task_bp

# base_schedule 导入链（cultivate_depot→skland）在 skland 模块加载时调用
# SecuritySm.get_d_id() 发网络请求（§14 环境性 flake，与测试无关），与
# base_scheduler_tests 同款 stub。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeThread:
    def __init__(self, alive=True):
        self._alive = alive

    def is_alive(self):
        return self._alive


class _FakeScheduler:
    def __init__(self):
        self.tasks = []

    def find_next_task(self, compare_time=None, compare_type="<", **kwargs):
        return None


def _task_payload(task_type, meta_data="", plan_key=None, upgrade_support=None):
    time_str = (datetime.now(pytz.utc) + timedelta(minutes=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f%z"
    )
    body = {
        "task": {
            "time": time_str,
            "plan": {},
            "task_type": task_type,
            "meta_data": meta_data,
        }
    }
    if plan_key is not None:
        body["task"]["plan_key"] = plan_key
    if upgrade_support is not None:
        body["upgrade_support"] = upgrade_support
    return body


class TestTaskEndpointContract(unittest.TestCase):
    def setUp(self):
        self.fake_scheduler = _FakeScheduler()
        fake_main = ModuleType("arknights_mower.__main__")
        fake_main.base_scheduler = self.fake_scheduler
        self._saved_main = sys.modules.get("arknights_mower.__main__")
        sys.modules["arknights_mower.__main__"] = fake_main

        self._saved_thread = task_module.mower_thread
        task_module.mower_thread = _FakeThread(alive=True)

        app = Flask(__name__)
        app.register_blueprint(task_bp)
        self.client = app.test_client()

    def tearDown(self):
        task_module.mower_thread = self._saved_thread
        if self._saved_main is None:
            sys.modules.pop("arknights_mower.__main__", None)
        else:
            sys.modules["arknights_mower.__main__"] = self._saved_main

    def test_skill_upgrade_rejected_with_plan_api_pointer(self):
        # #71：前端不再发原始「技能专精」/task；若收到则明确拒绝并指引计划 API，不再死路。
        r = self.client.post("/task", json=_task_payload("技能专精", meta_data="1"))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("添加任务成功！", r.data.decode("utf-8"))
        self.assertIn("mastery-plan", r.data.decode("utf-8"))
        self.assertEqual(self.fake_scheduler.tasks, [])

    def test_skill_upgrade_rejected_even_with_plan_key(self):
        # 旧流的 plan_key（char_id_level 形态）也不再被接受——专精训练统一走计划 API。
        r = self.client.post(
            "/task",
            json=_task_payload("技能专精", meta_data="1", plan_key="char_001_1"),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("mastery-plan", r.data.decode("utf-8"))
        self.assertEqual(self.fake_scheduler.tasks, [])

    def test_upgrade_support_payload_no_longer_consumed(self):
        # upgrade_support 载荷后端无消费者（#71 验收：移除或接入路线配置），不再被静默收下。
        r = self.client.post(
            "/task",
            json=_task_payload(
                "技能专精",
                meta_data="1",
                upgrade_support=[{"name": "阿", "skill_level": 1}],
            ),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("mastery-plan", r.data.decode("utf-8"))
        self.assertEqual(self.fake_scheduler.tasks, [])

    def test_empty_task_still_added(self):
        r = self.client.post("/task", json=_task_payload("空任务"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data.decode("utf-8"), "添加任务成功！")
        self.assertEqual(len(self.fake_scheduler.tasks), 1)

    def test_duplicate_time_rejected(self):
        self.fake_scheduler.find_next_task = lambda *a, **kw: object()
        r = self.client.post("/task", json=_task_payload("空任务"))
        self.assertEqual(r.status_code, 200)
        self.assertIn("找到同时间任务请勿重复添加", r.data.decode("utf-8"))
        self.assertEqual(self.fake_scheduler.tasks, [])

    def test_mower_not_running_rejected(self):
        saved = task_module.mower_thread
        task_module.mower_thread = None
        try:
            r = self.client.post("/task", json=_task_payload("空任务"))
        finally:
            task_module.mower_thread = saved
        self.assertEqual(r.status_code, 200)
        self.assertIn("请确保Mower正在运行", r.data.decode("utf-8"))


class TestFrontendFlowContract(unittest.TestCase):
    def _read(self, rel_path):
        path = REPO_ROOT / rel_path
        self.assertTrue(path.exists(), f"前端源文件缺失: {path}")
        return path.read_text(encoding="utf-8")

    def test_one_click_flow_uses_plan_api(self):
        # 一键专精不再发原始「技能专精」/task，改走计划创建 API。
        src = self._read("ui/src/pages/MasteryRecommendation.vue")
        self.assertIn("VITE_HTTP_URL}/mastery-plan", src)
        self.assertNotIn("task_type: '技能专精'", src)
        self.assertNotIn("upgrade_support", src)

    def test_manual_dialog_uses_plan_api_and_keeps_target_level(self):
        # 手动对话框（运行日志页）同样走计划 API，保留用户选的目标等级（可能非专三）。
        src = self._read("ui/src/components/TaskDialog.vue")
        self.assertIn("VITE_HTTP_URL}/mastery-plan", src)
        self.assertIn("target_level: mastery_target_level.value", src)
        # 原始「技能专精」/task 的载荷标记已移除（meta_data=skill_level 字符串 + upgrade_support 载荷）
        self.assertNotIn("task.meta_data = skill_level.value + ''", src)
        self.assertNotIn("upgrade_support.value", src)


class TestPlanApiDispatchLink(unittest.TestCase):
    """AC2 链路：计划创建 API（前端一键/手动对话框入口）落库的计划，扫描派发能找到并入队。

    单独测两端都有既有用例（add_plan_checked 落库 / `_dispatch_scan_start_tasks` 入队）；
    这里合起来验证「API 建的计划 = dispatch 找的计划」这条胶水——status 必须是 idle 才会
    被 dispatch 拉起，否则前端建了计划也永不开始训练。
    """

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()
        self._level = patch(
            "arknights_mower.utils.mastery_recommendation.get_current_mastery_level",
            return_value=1,
        )
        self._level.start()

    def tearDown(self):
        self._level.stop()
        os.unlink(self.db_path)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_plan_created_via_api_is_dispatched_by_scan(self):
        plan_id, err = add_plan_checked(
            "char_001", 0, target_level=3, char_name="阿米娅", path=self.db_path
        )
        self.assertGreater(plan_id, 0, err)
        self.assertEqual(
            [p["status"] for p in get_all_plans(path=self.db_path)], ["idle"]
        )

        # dispatch 内部调用 get_all_plans()（默认库路径）；把它指向临时库，验证
        # 「API 建的计划」正是 dispatch 找到的那条。
        real_get_all_plans = get_all_plans
        with patch(
            "arknights_mower.utils.mastery_db.get_all_plans",
            side_effect=lambda **k: real_get_all_plans(path=self.db_path, **k),
        ):
            solver = BaseSchedulerSolver()
            solver.task = None
            solver.tasks = []
            BaseSchedulerSolver._dispatch_scan_start_tasks(
                solver, [{"char_id": "char_001", "skill_index": 0}]
            )
        self.assertEqual(len(solver.tasks), 1)
        task = solver.tasks[0]
        self.assertEqual(task.type, TaskTypes.SKILL_UPGRADE)
        self.assertEqual(task.plan_key, str(plan_id))


if __name__ == "__main__":
    unittest.main()
