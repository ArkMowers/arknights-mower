import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

# base_schedule 导入链（cultivate_depot→skland）会在 skland 模块加载时调用
# SecuritySm.get_d_id() 发网络请求（§14 环境性 flake，与测试无关）。与
# mastery_choose_train_tests.py 同款 stub，避免单测依赖外网。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.solvers import mastery_reader  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.logic_expression import LogicExpression  # noqa: E402
from arknights_mower.utils.operators import Operator  # noqa: E402
from arknights_mower.utils.plan import Plan, PlanConfig, Room  # noqa: E402
from arknights_mower.utils.recognize import Scene  # noqa: E402
from arknights_mower.utils.scheduler_task import TaskTypes, find_next_task  # noqa: E402

with patch.dict("sys.modules", {"RecruitSolver": MagicMock()}):
    pass


class TestBaseScheduler(unittest.TestCase):
    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_run_order_solver_uses_current_time_for_expired_exhaust_task(self):
        solver = BaseSchedulerSolver()
        solver._training_sm = MagicMock()
        solver._training_sm.is_operator_protected.return_value = False
        solver.tasks = []
        solver.drone_room = None
        solver.op_data = MagicMock()
        solver.op_data.exhaust_agent = ["伊内丝"]
        solver.op_data.rest_in_full_group = set()
        solver.op_data.groups = {}
        solver.op_data.operators = {
            "伊内丝": Operator(
                "伊内丝",
                "meeting",
                group="",
                current_room="meeting",
                current_index=0,
                exhaust_require=True,
                mood=1,
                lower_limit=0,
                operator_type="high",
                depletion_rate=1,
            )
        }
        start_time = datetime(2026, 5, 2, 15, 19, 33)
        detected_exhaust_time = start_time + timedelta(minutes=10)

        class FixedDateTime(datetime):
            now_value = start_time

            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return cls.now_value.replace(tzinfo=tz)
                return cls.now_value

        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "plan_run_order"),
            patch.object(BaseSchedulerSolver, "check_fia", return_value=(None, None)),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                return_value=[{"time": detected_exhaust_time}],
            ),
            patch.object(BaseSchedulerSolver, "back"),
        ):
            solver.run_order_solver()

        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.EXHAUST_OFF)
        self.assertEqual(solver.tasks[0].time, start_time)
        self.assertIsNone(
            find_next_task(solver.tasks, start_time - timedelta(seconds=900))
        )

        solver.error = True
        FixedDateTime.now_value = start_time + timedelta(seconds=1)
        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "scene", return_value=Scene.INDEX),
        ):
            solver.handle_error(force=True)

        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.EXHAUST_OFF)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_backup_plan_solver_Caper(self):
        plan_config = {
            "meeting": [
                Room("伊内丝", "", ["见行者", "陈"]),
                Room("跃跃", "", ["见行者", "陈"]),
            ]
        }
        plan_config1 = {
            "meeting": [
                Room("伊内丝", "", ["陈", "红"]),
                Room("见行者", "", ["陈", "红"]),
            ]
        }
        agent_base_config = PlanConfig("稀音", "稀音", "伺夜")
        plan = {
            # 阶段 1
            "default_plan": Plan(plan_config, agent_base_config),
            "backup_plans": [
                Plan(
                    plan_config1,
                    agent_base_config,
                    trigger=LogicExpression(
                        "op_data.party_time is None", "and", " True "
                    ),
                    task={"meeting": ["Current", "见行者"]},
                )
            ],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        with patch.object(BaseSchedulerSolver, "agent_get_mood") as mock_agent_get_mood:
            mock_agent_get_mood.return_value = None
            solver.backup_plan_solver()
            self.assertEqual(len(solver.tasks), 1)
            solver.party_time = datetime.now()
            solver.backup_plan_solver()
            self.assertTrue(
                all(not condition for condition in solver.op_data.plan_condition)
            )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_backup_plan_solver_GreyytheLightningbearer(self):
        plan_config = {
            "room_2_3": [Room("雷蛇", "澄闪", ["炎狱炎熔", "格雷伊"])],
            "room_1_3": [Room("承曦格雷伊", "自动化", ["炎狱炎熔"])],
            "room_2_1": [
                Room("温蒂", "自动化", ["泡泡"]),
                Room("森蚺", "自动化", ["火神"]),
                Room("清流", "自动化", ["贝娜"]),
            ],
            "room_2_2": [Room("澄闪", "澄闪", ["炎狱炎熔", "格雷伊"])],
            "central": [
                Room("阿米娅", "", ["诗怀雅"]),
                Room("琴柳", "乌有", ["清道夫"]),
                Room("重岳", "乌有", ["杜宾"]),
                Room("夕", "乌有", ["玛恩纳"]),
                Room("令", "乌有", ["凯尔希"]),
            ],
            "contact": [Room("桑葚", "乌有", ["絮雨"])],
        }
        backup_plan1_config = {
            "central": [
                Room("阿米娅", "", ["诗怀雅"]),
                Room("清道夫", "", ["诗怀雅"]),
                Room("杜宾", "", ["泡泡"]),
                Room("玛恩纳", "", ["火神"]),
                Room("森蚺", "", ["诗怀雅"]),
            ],
            "room_2_1": [
                Room("温蒂", "", ["泡泡"]),
                Room("掠风", "", ["贝娜"]),
                Room("清流", "", ["火神"]),
            ],
            "room_1_3": [Room("Lancet-2", "", ["承曦格雷伊"])],
            "room_2_2": [Room("澄闪", "", ["承曦格雷伊", "格雷伊"])],
            "room_2_3": [Room("雷蛇", "", ["承曦格雷伊", "格雷伊"])],
            "contact": [Room("絮雨", "", ["桑葚"])],
        }
        agent_base_config0 = PlanConfig(
            "稀音,黑键,焰尾,伊内丝",
            "稀音,柏喙,伊内丝",
            "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云,掠风",
            ling_xi=2,
            resting_threshold=0.1,
        )
        agent_base_config = PlanConfig(
            "稀音,黑键,焰尾,伊内丝",
            "稀音,柏喙,伊内丝",
            "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云",
            ling_xi=2,
            free_blacklist="艾丽妮,但书,龙舌兰",
        )
        plan = {
            # 阶段 1
            "default_plan": Plan(plan_config, agent_base_config),
            "backup_plans": [
                Plan(
                    backup_plan1_config,
                    agent_base_config0,
                    trigger=LogicExpression(
                        "op_data.operators['令'].current_room.startswith('dorm')",
                        "and",
                        LogicExpression(
                            "op_data.operators['温蒂'].current_mood() - op_data.operators['承曦格雷伊'].current_mood()",
                            ">",
                            "4",
                        ),
                    ),
                    task={
                        "dormitory_2": [
                            "Current",
                            "Current",
                            "Current",
                            "Current",
                            "承曦格雷伊",
                        ]
                    },
                )
            ],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        with patch.object(BaseSchedulerSolver, "agent_get_mood") as mock_agent_get_mood:
            mock_agent_get_mood.return_value = None
            solver.op_data.operators["令"].current_room = "dorm"
            solver.op_data.operators["温蒂"].mood = 12
            solver.op_data.operators["承曦格雷伊"].mood = 7
            solver.backup_plan_solver()
            self.assertEqual(len(solver.tasks), 1)
            solver.op_data.operators["承曦格雷伊"].mood = 12
            solver.backup_plan_solver()
            self.assertTrue(
                all(not condition for condition in solver.op_data.plan_condition)
            )

    def _create_backup_refresh_solver(self):
        agent_base_config = PlanConfig("", "", "")
        default_plan = {"meeting": [Room("伊内丝", "", ["陈"])]}
        backup_plan = {"meeting": [Room("见行者", "", ["陈"])]}
        plan = {
            "default_plan": Plan(default_plan, agent_base_config),
            "backup_plans": [
                Plan(
                    backup_plan,
                    agent_base_config,
                    trigger=LogicExpression(
                        "op_data.operators['见行者'].current_room", "==", "meeting"
                    ),
                )
            ],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.op_data.add(Operator("见行者", ""))
        solver.tasks = []
        solver._training_sm = MagicMock()

        def read_meeting(room, read_time_index):
            if room == "train":
                return []
            op = solver.op_data.operators["见行者"]
            op.current_room = "meeting"
            op.current_index = 0
            op.mood = 5
            op.time_stamp = datetime.now()
            return [{"agent": "见行者", "mood": 5}]

        return solver, read_meeting

    def _create_no_train_plan_solver(self):
        agent_base_config = PlanConfig("", "", "")
        plan = {
            "default_plan": Plan(
                {"meeting": [Room("伊内丝", "", ["陈"])]},
                agent_base_config,
            ),
            "backup_plans": [],
        }

        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        solver._training_sm = MagicMock()
        return solver

    def _read_no_train_meeting(self, solver):
        def read_room(room, read_time_index):
            if room == "train":
                self.fail("训练室不应被读取")
            op = solver.op_data.operators["伊内丝"]
            op.current_room = "meeting"
            op.current_index = 0
            op.mood = 5
            op.time_stamp = datetime.now()
            return [{"agent": "伊内丝", "mood": 5}]

        return read_room

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_get_agent_from_room_uses_train_slots_without_train_plan(self):
        solver = self._create_no_train_plan_solver()

        with (
            patch.object(BaseSchedulerSolver, "turn_on_room_detail"),
            patch.object(
                BaseSchedulerSolver,
                "detect_product_complete",
                return_value=False,
            ),
            patch.object(BaseSchedulerSolver, "find", return_value=True),
        ):
            result = solver.get_agent_from_room("train")

        self.assertEqual(len(result), 2)
        self.assertEqual([item["agent"] for item in result], ["", ""])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_infra_main_requests_restart_after_mood_read(self):
        solver = BaseSchedulerSolver()
        solver.task = None
        solver.planned = False
        solver.tasks = []
        solver.restart_after_mood_read = True

        with (
            patch.object(BaseSchedulerSolver, "find", return_value=True),
            patch.object(BaseSchedulerSolver, "no_pending_task", return_value=True),
            patch.object(
                BaseSchedulerSolver,
                "agent_get_mood",
                return_value="self_correction",
            ) as mock_agent_get_mood,
            patch.object(BaseSchedulerSolver, "run_order_solver") as mock_run_order,
            patch.object(BaseSchedulerSolver, "plan_solver") as mock_plan,
        ):
            result = solver.infra_main()

        self.assertEqual(result, "restart_after_mood_read")
        self.assertFalse(solver.restart_after_mood_read)
        mock_agent_get_mood.assert_called_once_with(skip_dorm=True)
        mock_run_order.assert_not_called()
        mock_plan.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_keeps_self_correction_when_backup_refresh_disabled(self):
        solver, read_meeting = self._create_backup_refresh_solver()

        with (
            patch.object(
                base_schedule.config.conf, "refresh_backup_plan_after_mood", False
            ),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                side_effect=read_meeting,
            ),
            patch.object(BaseSchedulerSolver, "back"),
        ):
            result = solver.agent_get_mood(skip_dorm=True)

        self.assertEqual(result, "self_correction")
        self.assertEqual(solver.op_data.plan_condition, [False])
        self.assertEqual(solver.op_data.plan["meeting"][0].agent, "伊内丝")
        self.assertTrue(
            any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_does_not_refresh_backup_plan_by_default(self):
        solver, read_meeting = self._create_backup_refresh_solver()

        with (
            patch.object(
                base_schedule.config.conf, "refresh_backup_plan_after_mood", True
            ),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(
                BaseSchedulerSolver,
                "get_agent_from_room",
                side_effect=read_meeting,
            ),
            patch.object(BaseSchedulerSolver, "back"),
        ):
            result = solver.agent_get_mood(skip_dorm=True)

        self.assertEqual(result, "self_correction")
        self.assertEqual(solver.op_data.plan_condition, [False])
        self.assertEqual(solver.op_data.plan["meeting"][0].agent, "伊内丝")
        self.assertTrue(
            any(task.type == TaskTypes.SELF_CORRECTION for task in solver.tasks)
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_no_keepalive_enqueue_for_idle_plan(self):
        # #74 第3段：keepalive 完全删除——DB 有 idle 计划也不再每轮补 now-task
        # SKILL_UPGRADE（开始训练只由扫描派发；重启恢复靠 gate 顺路重读 + 扫描派发兜底）。
        solver = self._empty_infra_solver()
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(BaseSchedulerSolver, "find", return_value=True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan",
                return_value={"id": 1},
            ),
        ):
            solver.infra_main()
        self.assertEqual(
            len(solver.tasks), 0, "keepalive 已删：有 idle 计划也不再每轮补 now-task"
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_no_keepalive_enqueue_for_active_plan(self):
        # 同上：active 计划也不再触发 keepalive（重启恢复改由 gate 顺路重读收取任务）
        solver = self._empty_infra_solver()
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(BaseSchedulerSolver, "find", return_value=True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan",
                return_value={"id": 2, "status": "training"},
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan", return_value=None
            ),
        ):
            solver.infra_main()
        self.assertEqual(len(solver.tasks), 0)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_occupied_recheck_converges_one_future_task(self):
        # #66/B1 验收（keepalive 已删，#74 第3段）：占用训练 × 无 active × 不匹配 →
        # 读取器排未来重检（倒计时结束 + 缓冲），队列收敛为恰好一条未来 SKILL_UPGRADE，
        # 不再每 ~4s 进出训练室（keepalive 已删，队列空也不会每轮补 now-task）。
        from arknights_mower.solvers.mastery_reader import (
            ARRANGING_RETRY_BUFFER,
            _upsert_skill_upgrade_task,
        )
        from arknights_mower.utils.scheduler_task import SchedulerTask

        solver = self._empty_infra_solver()
        solver.task = None
        # 初始入队一条到期 SKILL_UPGRADE（模拟扫描/派发后的入口；keepalive 已删，
        # 没有「每轮补 now-task」来造首条）
        solver.tasks = [
            SchedulerTask(time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE)
        ]
        countdown_end = datetime.now() + timedelta(hours=2)

        def reader_occupied_blocked(s):
            # 模拟 #66 读取器占用路径：排一条未来重检（倒计时结束 + 缓冲）
            _upsert_skill_upgrade_task(s, countdown_end + ARRANGING_RETRY_BUFFER)

        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan",
                return_value={"id": 1},
            ),
            patch(
                "arknights_mower.solvers.mastery.run_mastery_task",
                side_effect=reader_occupied_blocked,
            ) as rmt,
        ):
            for _ in range(20):
                # 与 mower 主循环一致：先 dispatch 到期的 SKILL_UPGRADE；keepalive 已删，
                # 队列空也不会补 now-task，收敛只靠读取器排的未来重检。
                due = [
                    t
                    for t in solver.tasks
                    if t.type == TaskTypes.SKILL_UPGRADE
                    and t.time <= datetime.now() + timedelta(seconds=1)
                ]
                if due:
                    task = min(due, key=lambda t: t.time)
                    solver.task = task
                    rmt(solver)
                    solver.tasks.remove(task)
                    solver.task = None

        upgrades = [t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]
        self.assertEqual(len(upgrades), 1)
        self.assertEqual(upgrades[0].time, countdown_end + ARRANGING_RETRY_BUFFER)

    def _empty_infra_solver(self):
        """构造进入 infra_main 的 `elif not self.todo_task` 分支所需的空状态。

        __init__ 已由调用方 patch 掉；keepalive 已删（#74 第3段），该分支现在只做
        无人机/补货检查和 todo_task 置位。
        """
        solver = BaseSchedulerSolver()
        solver.task = None
        solver.tasks = []
        solver.planned = True
        solver.todo_task = False
        solver.collect_notification = True
        solver.enable_party = False
        solver.last_clue = None
        solver.drone_room = None
        solver.drone_time = None
        solver.reload_room = None
        solver.reload_time = None
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = []
        return solver


class TestTrainGateReadThenJudge(unittest.TestCase):
    """#74 phase 1：gate L0 先读再判（修 base_schedule.py:3257 DB 预判跳过死锁）。

    排班进训练室不再用「DB active 就跳过」的预判（DB 是意图缓存可能过期，跳过就
    永不读屏幕、永不修正 DB → 重启后训练室僵住）；一律先进房读屏幕 → enable_mastery
    时 reconcile_short 据截图修正 DB → 再按锁定/保护判定跳过/冻结，空闲×未保护正常安排。
    """

    @staticmethod
    def _make_solver(plan):
        """可跑 agent_arrange_room("train") 的 solver：当前房间=计划 → 排班直接收尾。"""
        solver = BaseSchedulerSolver()
        solver.task = None
        solver.tasks = []
        solver.waiting_scene = []
        solver.scene = MagicMock(return_value=Scene.INDEX)
        solver.op_data = MagicMock()
        solver.op_data.run_order_rooms = set()
        solver.op_data.operators = {}
        solver.op_data.get_current_room.return_value = plan["train"][:]
        solver.refresh_current_room = MagicMock()
        solver.turn_on_room_detail = MagicMock()
        solver.enter_room = MagicMock()
        solver.back = MagicMock()
        solver.recog = MagicMock()
        return solver

    @staticmethod
    def _empty_room():
        return mastery_reader.RoomState("empty", mastery_reader.RoomPanel())

    @staticmethod
    def _training_room():
        return mastery_reader.RoomState(
            "training", mastery_reader.RoomPanel(countdown_state="active")
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_stale_active_empty_room_resets_db_and_proceeds(self):
        """死锁修复核心：DB active 不再整房跳过——照常进房读屏幕，截图权威把过期
        active 重置 idle，空闲×未保护 → 正常安排。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        stale = {"id": 7, "status": "training"}
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=self._empty_room(),
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=stale
            ),
            patch("arknights_mower.utils.mastery_db.get_all_plans", return_value=[]),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan", return_value=None
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        solver.enter_room.assert_called_with("train")
        upd.assert_called_once_with(7, "idle")  # 截图权威：过期 active → idle
        solver.turn_on_room_detail.assert_called_with("train")  # 未早退跳过
        self.assertEqual(result, {})
        self.assertNotIn("train", plan)  # 排班正常完成

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_locked_room_skips_when_not_following_schedule(self):
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=self._training_room(),
            ),
            patch("arknights_mower.solvers.mastery_reader.reconcile_short"),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        solver.turn_on_room_detail.assert_not_called()
        solver.back.assert_called_once_with()
        self.assertNotIn("train", plan)
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_locked_room_freezes_train_slot_when_following_schedule(self):
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(base_schedule.config.conf, "assistant_follows_schedule", True),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=self._training_room(),
            ),
            patch("arknights_mower.solvers.mastery_reader.reconcile_short"),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        solver.back.assert_called_once_with(0.5)  # 冻结不早退；仅排班收尾 back
        solver.refresh_current_room.assert_called_once_with(
            "train", [1]
        )  # idx1=Current
        solver.turn_on_room_detail.assert_called_with("train")
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_protected_room_skips(self):
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        room = self._empty_room()
        room.protected = True
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=room,
            ),
            patch("arknights_mower.solvers.mastery_reader.reconcile_short"),
        ):
            solver.agent_arrange_room({}, "train", plan)
        solver.turn_on_room_detail.assert_not_called()
        solver.back.assert_called_once_with()
        self.assertNotIn("train", plan)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_enable_mastery_off_keeps_blocked_room_check_no_reconcile(self):
        """§16.11：OFF 时排班照常但保留「被占用就不硬塞」防卡检查——锁定房仍跳过，
        但不跑 reconcile（自动收取/对账全停）。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=self._training_room(),
            ),
            patch("arknights_mower.solvers.mastery_reader.reconcile_short") as rec,
        ):
            solver.agent_arrange_room({}, "train", plan)
        rec.assert_not_called()
        solver.back.assert_called_once_with()
        self.assertNotIn("train", plan)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_enable_mastery_off_empty_room_proceeds(self):
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=self._empty_room(),
            ),
            patch("arknights_mower.solvers.mastery_reader.reconcile_short") as rec,
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        rec.assert_not_called()
        solver.turn_on_room_detail.assert_called_with("train")
        self.assertEqual(result, {})


class TestScanDispatchMastery(unittest.TestCase):
    """#74 第3段：扫描 = 唯一周期派发点——`_auto_schedule_mastery_after_scan` 对材料
    足够的 idle 计划入队「开始训练」SKILL_UPGRADE（plan_key 指定计划，无逻辑标记）。
    """

    def _solver(self):
        solver = base_schedule.BaseSchedulerSolver()
        solver.task = None
        solver.tasks = []
        return solver

    def _idle_plan(self, pid=3, char_id="char_a", skill_index=1):
        return {
            "id": pid,
            "char_id": char_id,
            "char_name": "测试干员",
            "skill_index": skill_index,
            "skill_name": "二技能·测试技能",
            "target_level": 3,
            "status": "idle",
            "priority": 1,
        }

    @patch.object(base_schedule.BaseSchedulerSolver, "__init__", lambda x: None)
    def test_dispatch_scan_start_tasks_enqueues_for_idle_sufficient(self):
        solver = self._solver()
        idle = self._idle_plan()
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans", return_value=[idle]
            ),
            patch.object(base_schedule.config.conf, "enable_mastery", True),
        ):
            base_schedule.BaseSchedulerSolver._dispatch_scan_start_tasks(
                solver,
                [{"char_id": "char_a", "skill_index": 1, "achievable": True}],
            )
        self.assertEqual(len(solver.tasks), 1)
        task = solver.tasks[0]
        self.assertEqual(task.type, TaskTypes.SKILL_UPGRADE)
        self.assertEqual(task.plan_key, "3")
        self.assertIn("开始训练", task.meta_data, "meta_data 是描述性标签，非逻辑标记")
        self.assertLessEqual(task.time, datetime.now() + timedelta(seconds=1))

    @patch.object(base_schedule.BaseSchedulerSolver, "__init__", lambda x: None)
    def test_dispatch_scan_start_tasks_skips_non_idle_and_unconfirmed(self):
        solver = self._solver()
        idle_ok = self._idle_plan(pid=3, char_id="char_a", skill_index=1)
        idle_no_material = self._idle_plan(pid=4, char_id="char_b", skill_index=1)
        training = self._idle_plan(pid=5, char_id="char_c", skill_index=0)
        training["status"] = "training"
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans",
                return_value=[idle_ok, idle_no_material, training],
            ),
        ):
            base_schedule.BaseSchedulerSolver._dispatch_scan_start_tasks(
                solver, [{"char_id": "char_a", "skill_index": 1}]
            )
        self.assertEqual(len(solver.tasks), 1, "只入队 idle 且材料足够的计划")
        self.assertEqual(solver.tasks[0].plan_key, "3")

    @patch.object(base_schedule.BaseSchedulerSolver, "__init__", lambda x: None)
    def test_dispatch_scan_start_tasks_dedup_same_plan(self):
        # TASK-01：同计划恒 ≤1 条 SKILL_UPGRADE（按 plan_key 去重，重复扫描原地刷新）
        solver = self._solver()
        idle = self._idle_plan()
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans", return_value=[idle]
            ),
        ):
            for _ in range(3):
                base_schedule.BaseSchedulerSolver._dispatch_scan_start_tasks(
                    solver, [{"char_id": "char_a", "skill_index": 1}]
                )
        upgrades = [t for t in solver.tasks if t.type == TaskTypes.SKILL_UPGRADE]
        self.assertEqual(len(upgrades), 1)

    @patch.object(base_schedule.BaseSchedulerSolver, "__init__", lambda x: None)
    def test_auto_schedule_mastery_after_scan_gates_on_enable_mastery(self):
        # §16.11：OFF 时仓库扫描保留（retry/auto_schedule/workshop 照跑），
        # 但不入队开始训练任务
        solver = self._solver()
        idle = self._idle_plan()
        with (
            patch(
                "arknights_mower.utils.mastery_db.retry_failed_plans", return_value=0
            ),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={
                    "scheduled": [{"char_id": "char_a", "skill_index": 1}],
                    "skipped": [],
                },
            ),
            patch(
                "arknights_mower.utils.mastery_recommendation.compute_workshop_config",
                return_value=None,
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans", return_value=[idle]
            ),
            patch.object(base_schedule.config.conf, "enable_mastery", False),
        ):
            solver._auto_schedule_mastery_after_scan()
        self.assertEqual(solver.tasks, [], "OFF 时不入队开始训练任务")

    @patch.object(base_schedule.BaseSchedulerSolver, "__init__", lambda x: None)
    def test_auto_schedule_mastery_after_scan_enqueues_when_on(self):
        solver = self._solver()
        idle = self._idle_plan()
        with (
            patch(
                "arknights_mower.utils.mastery_db.retry_failed_plans", return_value=0
            ),
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={
                    "scheduled": [{"char_id": "char_a", "skill_index": 1}],
                    "skipped": [],
                },
            ),
            patch(
                "arknights_mower.utils.mastery_recommendation.compute_workshop_config",
                return_value=None,
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_all_plans", return_value=[idle]
            ),
            patch.object(base_schedule.config.conf, "enable_mastery", True),
        ):
            solver._auto_schedule_mastery_after_scan()
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SKILL_UPGRADE)


if __name__ == "__main__":
    unittest.main()
