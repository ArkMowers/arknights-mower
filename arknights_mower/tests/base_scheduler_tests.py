import sys
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

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
    def test_wait_drone_interface_can_require_bill_accelerate(self):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock(w=1920, h=1080)
        bill_results = iter((None, object()))
        solver.find = MagicMock(
            side_effect=lambda template: (
                next(bill_results) if template == "bill_accelerate" else object()
            )
        )
        solver.tap = MagicMock()

        solver._wait_drone_interface(interval=1, accelerate_template="bill_accelerate")

        self.assertEqual(
            solver.find.call_args_list,
            [call("bill_accelerate"), call("bill_accelerate")],
        )
        solver.tap.assert_called_once_with((96, 1026), interval=1)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_wait_drone_interface_accepts_either_button_by_default(self):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock(w=1920, h=1080)
        solver.find = MagicMock(return_value=object())
        solver.tap = MagicMock()

        solver._wait_drone_interface()

        solver.find.assert_called_once_with("factory_accelerate")
        solver.tap.assert_not_called()

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
    def test_handle_error_appends_immediate_empty_task_after_clearing(self):
        # #144：错误分支「检测到超过15分钟的任务」清空非专精任务后，补一条立即
        # 空任务，让下一次 run() 走正常 planned 分支重读心情/换班/跑单，而不是
        # rest_until_next_task 睡到远期专精重检开始（队列只剩远期专精时睡死）。
        import arknights_mower.utils.scheduler_task as st

        solver = BaseSchedulerSolver()
        solver.error = True
        now = datetime(2026, 8, 19, 12, 0, 0)
        solver.tasks = [
            st.SchedulerTask(
                time=now - timedelta(minutes=20),
                task_type=TaskTypes.RUN_ORDER,
                task_plan={"meeting": ["伊内丝"]},
            ),
            st.SchedulerTask(
                time=now + timedelta(hours=5),
                task_type=TaskTypes.SKILL_UPGRADE,
                task_plan={"train": ["Current", "泥岩"]},
            ),
        ]

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return cls.now_value.replace(tzinfo=tz)
                return cls.now_value

        FixedDateTime.now_value = now

        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(st, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "scene", return_value=Scene.INDEX),
        ):
            solver.handle_error(force=True)

        # 超时的非专精任务被清掉
        self.assertIsNone(find_next_task(solver.tasks, task_type=TaskTypes.RUN_ORDER))
        # 远期专精重检保留
        self.assertIsNotNone(
            find_next_task(solver.tasks, task_type=TaskTypes.SKILL_UPGRADE)
        )
        # 补了一条立即空任务（NOT_SPECIFIC，time=now）
        empty = find_next_task(solver.tasks, task_type=TaskTypes.NOT_SPECIFIC)
        self.assertIsNotNone(empty)
        self.assertEqual(empty.time, now)
        # 队列里有 time <= now 的任务 → __main__ 主循环不会 rest_until_next_task 睡满
        self.assertIsNotNone(find_next_task(solver.tasks, now + timedelta(seconds=1)))

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_handle_error_keeps_skill_upgrade_gate_when_nothing_overdue(self):
        # #144 负向对照：没有超时任务时（不触发清队），即使存在远期专精任务，
        # 第一个分支的 SKILL_UPGRADE 门也不应被放宽——不补空任务、任务列表不变。
        import arknights_mower.utils.scheduler_task as st

        solver = BaseSchedulerSolver()
        solver.error = True
        now = datetime(2026, 8, 19, 12, 0, 0)
        solver.tasks = [
            st.SchedulerTask(
                time=now + timedelta(hours=5),
                task_type=TaskTypes.SKILL_UPGRADE,
                task_plan={"train": ["Current", "泥岩"]},
            ),
        ]

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return cls.now_value.replace(tzinfo=tz)
                return cls.now_value

        FixedDateTime.now_value = now

        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(st, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "scene", return_value=Scene.INDEX),
        ):
            solver.handle_error(force=True)

        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SKILL_UPGRADE)
        self.assertIsNone(
            find_next_task(solver.tasks, task_type=TaskTypes.NOT_SPECIFIC)
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_idle_sleep_wakes_on_wake_event(self):
        # #141：web 一键专精派发后设 wake_scheduler → 休息被唤醒（不再睡满剩余时长），
        # 事件被消费（clear）；结束时照常刷新场景缓存
        from arknights_mower.utils import config as cfg

        solver = MagicMock()
        cfg.wake_scheduler.clear()
        cfg.wake_scheduler.set()
        BaseSchedulerSolver._idle_sleep(solver, 3600)
        self.assertFalse(cfg.wake_scheduler.is_set(), "唤醒事件应被消费（clear）")
        self.assertFalse(solver.sleeping, "try/finally 应复位 sleeping")
        solver.recog.update.assert_called_once()

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

    def _build_resting_solver(self):
        plan_config = {
            # 会客室真实容量为 2，办公室为 1。大组 = 会客室 2 名主力 + 办公室 1 名主力。
            "meeting": [Room("伊内丝", "大组", ["陈"]), Room("银灰", "大组", ["初雪"])],
            "contact": [Room("讯使", "大组", ["红"])],
            "dormitory_1": [
                Room("塑心", "", []),
                Room("冰酿", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
                Room("Free", "", []),
            ],
        }
        plan = {
            "default_plan": Plan(plan_config, PlanConfig("", "", "")),
            "backup_plans": [],
        }
        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.initialize_operators()
        solver.tasks = []
        return solver

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_low_resting_occupants_do_not_block_takable_group_beds(self):
        """低优占床消耗低优配额，但可被接管的床不能挡住主力大组下班。"""
        solver = self._build_resting_solver()
        for name, index in [("泥岩", 3), ("能天使", 4)]:
            solver.op_data.add(Operator(name, ""))
            op = solver.op_data.operators[name]
            op.current_room = "dormitory_1"
            op.current_index = index
            dorm = next(
                d for d in solver.op_data.dorm if d.position == ("dormitory_1", index)
            )
            dorm.name = name

        current_resting = (
            len(solver.op_data.dorm)
            - solver.op_data.available_free()
            - solver.op_data.available_free("low")
        )
        self.assertEqual(2, current_resting)
        self.assertEqual(0, solver.op_data.available_free("low"))

        plan = {}
        solver.get_resting_plan(
            solver.op_data.groups["大组"], [], plan, current_resting
        )

        self.assertEqual(["陈", "初雪"], plan["meeting"])
        self.assertEqual(["红"], plan["contact"])
        resting_names = {d.name for d in solver.op_data.dorm}
        self.assertIn("伊内丝", resting_names)
        self.assertIn("银灰", resting_names)
        self.assertIn("讯使", resting_names)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_resting_assigns_idle_low_replacement_to_dorm(self):
        solver = self._build_resting_solver()
        op = solver.op_data.operators["陈"]
        op.mood = 5
        op.current_room = ""
        op.room = ""
        solver.total_agent = [op]
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(BaseSchedulerSolver, "plan_metadata", lambda self: None),
        ):
            solver.resting()
        self.assertIn("陈", [d.name for d in solver.op_data.dorm])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_resting_low_replacements_get_distinct_slots(self):
        solver = self._build_resting_solver()
        for name in ["陈", "红"]:
            op = solver.op_data.operators[name]
            op.mood = 5
            op.current_room = ""
            op.room = ""
        solver.total_agent = [solver.op_data.operators[n] for n in ["陈", "红"]]
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(BaseSchedulerSolver, "plan_metadata", lambda self: None),
        ):
            solver.resting()
        dorm_names = [d.name for d in solver.op_data.dorm]
        self.assertEqual(1, dorm_names.count("陈"))
        self.assertEqual(1, dorm_names.count("红"))

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_resting_does_not_evict_resting_low_replacement(self):
        """生产日志中的低优互踢活锁：新低优不能覆盖正在休息的低优。"""
        solver = self._build_resting_solver()
        chen = solver.op_data.operators["陈"]
        chen.mood = 5
        chen.current_room = "dormitory_1"
        chen.current_index = 3
        occupied = next(
            d for d in solver.op_data.dorm if d.position == ("dormitory_1", 3)
        )
        occupied.name = "陈"

        hong = solver.op_data.operators["红"]
        hong.mood = 5
        hong.current_room = ""
        hong.room = ""
        solver.total_agent = [hong]
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(BaseSchedulerSolver, "plan_metadata", lambda self: None),
        ):
            solver.resting()

        dorm = {d.position: d.name for d in solver.op_data.dorm}
        self.assertEqual("陈", dorm[("dormitory_1", 3)])
        self.assertIn("红", dorm.values())
        self.assertNotEqual(
            ("dormitory_1", 3),
            next(d.position for d in solver.op_data.dorm if d.name == "红"),
        )

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_assign_dorm_returns_none_when_low_beds_are_occupied(self):
        solver = self._build_resting_solver()
        for name, index in [("陈", 3), ("红", 4)]:
            op = solver.op_data.operators[name]
            op.current_room = "dormitory_1"
            op.current_index = index
            next(
                d for d in solver.op_data.dorm if d.position == ("dormitory_1", index)
            ).name = name
        high = solver.op_data.operators["伊内丝"]
        high.current_room = "dormitory_1"
        high.current_index = 2
        next(
            d for d in solver.op_data.dorm if d.position == ("dormitory_1", 2)
        ).name = "伊内丝"

        self.assertIsNone(solver.op_data.assign_dorm("红", True))

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_group_dorm_assignment_rolls_back_when_capacity_is_insufficient(self):
        solver = self._build_resting_solver()
        for name, index in [("泥岩", 3), ("能天使", 4)]:
            solver.op_data.add(Operator(name, ""))
            op = solver.op_data.operators[name]
            op.current_room = "dormitory_1"
            op.current_index = index
            next(
                d for d in solver.op_data.dorm if d.position == ("dormitory_1", index)
            ).name = name
        high = solver.op_data.operators["伊内丝"]
        high.current_room = "dormitory_1"
        high.current_index = 2
        next(
            d for d in solver.op_data.dorm if d.position == ("dormitory_1", 2)
        ).name = "伊内丝"
        before = [(d.name, d.time) for d in solver.op_data.dorm]

        plan = {}
        solver.get_resting_plan(solver.op_data.groups["大组"], [], plan, 3)

        self.assertEqual({}, plan)
        self.assertEqual(before, [(d.name, d.time) for d in solver.op_data.dorm])

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
    def test_agent_get_mood_train_branch_unified_reader(self):
        # #94：训练室分支统一走 read_room_state(want_mood=True) 一次读全（含心情）
        # + reconcile_short，不再 get_agent_from_room 与 read_room_state 各开一次浮窗。
        solver = BaseSchedulerSolver()
        solver.global_plan = MagicMock()
        solver.initialize_operators()
        solver.op_data.add(Operator("艾雅法拉", "train"))
        solver.tasks = []
        solver._training_sm = MagicMock()

        room_state = MagicMock()
        mood_data = [{"agent": "艾雅法拉", "mood": 20.1234}]
        with (
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(
                mastery_reader,
                "read_room_state",
                return_value=(room_state, mood_data),
            ) as mock_read,
            patch.object(mastery_reader, "reconcile_short") as mock_reconcile,
        ):
            result = solver.agent_get_mood()

        self.assertIsNone(result)
        mock_read.assert_called_once_with(solver, enter=False, want_mood=True)
        mock_reconcile.assert_called_once_with(solver, room_state, defer_collect=False)

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_train_skips_when_occupants_fresh(self):
        # 审计修正（2026-08-16）：训练室与其他房间一致——当前房内干员都近期读过则跳过，
        # 不再被「计划在训练室但未进驻（等待中）的陈旧干员」每轮循环强制进房读心情
        # （10+ 次/2h 根因：get_agent_from_room 只刷房里干员的 time_stamp，等位干员
        # 永远陈旧 → 训练室永远在待读集合 → 原 room != "train" 免除永不跳过）。
        solver = BaseSchedulerSolver()
        solver.global_plan = MagicMock()
        solver.initialize_operators()
        solver.op_data.add(
            Operator(
                "艾雅法拉", "train", current_room="train", time_stamp=datetime.now()
            )
        )
        solver.op_data.add(
            Operator("能天使", "train", time_stamp=datetime.now() - timedelta(hours=3))
        )
        solver.tasks = []
        solver._training_sm = MagicMock()
        with (
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(mastery_reader, "read_room_state") as mock_read,
            patch.object(mastery_reader, "reconcile_short"),
        ):
            result = solver.agent_get_mood()
        self.assertIsNone(result)
        mock_read.assert_not_called()  # 占用者新鲜 → 跳过，不进训练室

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_train_reads_when_occupant_stale(self):
        # 对照：当前房内占用者心情陈旧 → 不跳过，照常进房读 + reconcile（死锁兜底保留）
        solver = BaseSchedulerSolver()
        solver.global_plan = MagicMock()
        solver.initialize_operators()
        solver.op_data.add(
            Operator(
                "艾雅法拉",
                "train",
                current_room="train",
                time_stamp=datetime.now() - timedelta(hours=3),
            )
        )
        solver.tasks = []
        solver._training_sm = MagicMock()
        room_state = MagicMock()
        mood_data = [{"agent": "艾雅法拉", "mood": 20.0}]
        with (
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(
                mastery_reader,
                "read_room_state",
                return_value=(room_state, mood_data),
            ) as mock_read,
            patch.object(mastery_reader, "reconcile_short") as mock_reconcile,
        ):
            result = solver.agent_get_mood()
        self.assertIsNone(result)
        mock_read.assert_called_once_with(solver, enter=False, want_mood=True)
        mock_reconcile.assert_called_once_with(solver, room_state, defer_collect=False)

    @staticmethod
    def _train_mismatch_solver(plan_agents, extra=None):
        """构造训练室缓存与静态计划错位的 solver（绕过 init_and_validate 的宿舍校验）。

        仅含训练室计划；训练室干员 current_room 留空 → get_current_room("train") 与
        计划错位 → fix_plan["train"] 会被生成。#207 守卫测试用。
        """
        from arknights_mower.utils.operators import Operators
        from arknights_mower.utils.plan import Plan, PlanConfig, Room

        plan_config = {"train": [Room(a, "", []) for a in plan_agents]}
        plan = {
            "default_plan": Plan(plan_config, PlanConfig("稀音", "稀音", "伺夜")),
            "backup_plans": [],
        }
        solver = BaseSchedulerSolver()
        solver.global_plan = plan
        solver.tasks = []
        solver._training_sm = MagicMock()
        op_data = Operators(plan)
        op_data.operators = {
            name: Operator(name, "train", idx, "", [], "high", operator_type="high")
            for idx, name in enumerate(plan_agents)
        }
        op_data.groups = {}
        if extra:
            op_data.operators.update(extra)
        solver.op_data = op_data
        return solver

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_generates_train_correction_when_unmanaged(self):
        # #207 点 1 删除：训练室缓存与计划错位（无专精活跃/无保护）→ 纠错任务含训练室。
        solver = self._train_mismatch_solver(["褐果", "桃金娘"])
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(BaseSchedulerSolver, "get_agent_from_room", return_value=[]),
        ):
            solver.agent_get_mood()
        task = next(
            (t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION), None
        )
        self.assertIsNotNone(task)
        self.assertIn("train", task.plan)
        self.assertEqual(task.plan["train"], ["褐果", "桃金娘"])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_train_correction_not_suppressed_when_mastery_off(self):
        # #207 守卫·铁律 10/§16.11：enable_mastery OFF 保护全停、排班照常排训练室——
        # 即使协助位是逻各斯，训练室纠错也不被弹掉、不发邮件。
        solver = self._train_mismatch_solver(
            ["褐果", "桃金娘"],
            extra={
                "逻各斯": Operator(
                    "逻各斯", "train", current_room="train", current_index=0
                )
            },
        )
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", False),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(BaseSchedulerSolver, "get_agent_from_room", return_value=[]),
            patch("arknights_mower.utils.email.send_message") as mock_send,
        ):
            solver.agent_get_mood()
        task = next(
            (t for t in solver.tasks if t.type == TaskTypes.SELF_CORRECTION), None
        )
        self.assertIsNotNone(task)
        self.assertIn("train", task.plan)
        mock_send.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_suppresses_train_correction_when_mastery_active(self):
        # #207 守卫·专精活跃：DB 有 active 计划 → 训练室纠错被弹出，不生成纠错任务。
        # 即便协助位同时是逻各斯（受保护），mastery 分支先行 → 不发提醒邮件。
        solver = self._train_mismatch_solver(
            ["褐果", "桃金娘"],
            extra={
                "逻各斯": Operator(
                    "逻各斯", "train", current_room="train", current_index=0
                )
            },
        )
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(mastery_reader, "reconcile_short"),
            patch.object(
                mastery_reader, "read_room_state", return_value=(MagicMock(), [])
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan",
                return_value={"id": 1, "status": "training"},
            ),
            patch("arknights_mower.utils.email.send_message") as mock_send,
        ):
            result = solver.agent_get_mood()
        self.assertIsNone(result)
        self.assertEqual(solver.tasks, [])
        mock_send.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_agent_get_mood_suppresses_train_correction_when_protected_and_emails(self):
        # #207 守卫·受保护：协助位是逻各斯（缓存）→ 训练室纠错弹出 + 节流提醒邮件。
        solver = self._train_mismatch_solver(
            ["褐果", "桃金娘"],
            extra={
                "逻各斯": Operator(
                    "逻各斯", "train", current_room="train", current_index=0
                )
            },
        )
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(BaseSchedulerSolver, "enter_room"),
            patch.object(BaseSchedulerSolver, "back"),
            patch.object(mastery_reader, "reconcile_short"),
            patch.object(
                mastery_reader, "read_room_state", return_value=(MagicMock(), [])
            ),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
            patch("arknights_mower.utils.mastery_db.should_notify", return_value=True),
            patch("arknights_mower.utils.email.send_message") as mock_send,
        ):
            result = solver.agent_get_mood()
        self.assertIsNone(result)
        self.assertEqual(solver.tasks, [])
        mock_send.assert_called_once()
        self.assertIn("受保护", mock_send.call_args[0][0])

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_train_mastery_active_signals(self):
        # #207 守卫·专精活跃信号：enable_mastery 门 + DB active + 队列 SKILL_UPGRADE/SWAP_SUPPORT。
        import arknights_mower.utils.scheduler_task as st

        solver = BaseSchedulerSolver()
        solver.tasks = []
        # OFF → 恒 False（残留 DB 计划不误伤，§9 OFF 语义）
        with patch.object(base_schedule.config.conf, "enable_mastery", False):
            self.assertFalse(solver._train_mastery_active())
        # ON + 无 DB active + 空队列 → False
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
        ):
            self.assertFalse(solver._train_mastery_active())
        # ON + DB active → True
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan",
                return_value={"id": 1},
            ),
        ):
            self.assertTrue(solver._train_mastery_active())
        # ON + 无 DB + 队列 SKILL_UPGRADE → True
        solver.tasks = [st.SchedulerTask(task_type=TaskTypes.SKILL_UPGRADE)]
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
        ):
            self.assertTrue(solver._train_mastery_active())
        # ON + 无 DB + 队列 SWAP_SUPPORT → True
        solver.tasks = [st.SchedulerTask(task_type=TaskTypes.SWAP_SUPPORT)]
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
        ):
            self.assertTrue(solver._train_mastery_active())

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_not_valid_train_operator_misplaced(self):
        # #207 点 4 删除：训练室高优干员错位 → not_valid() 不再恒 False。
        op = Operator(
            "艾雅法拉",
            "train",
            index=0,
            current_room="",
            current_index=-1,
            operator_type="high",
            time_stamp=datetime.now(),
        )
        self.assertTrue(op.not_valid())
        # 对照：就位 + 心情新鲜 → False
        op.current_room = "train"
        op.current_index = 0
        self.assertFalse(op.not_valid())

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_handle_error_keeps_swap_support_when_clearing(self):
        # #207：清队保留列表加 SWAP_SUPPORT——待执行的协助位换位任务不被清空。
        import arknights_mower.utils.scheduler_task as st

        solver = BaseSchedulerSolver()
        solver.error = True
        now = datetime(2026, 8, 19, 12, 0, 0)
        solver.tasks = [
            st.SchedulerTask(
                time=now - timedelta(minutes=20),
                task_type=TaskTypes.RUN_ORDER,
                task_plan={"meeting": ["伊内丝"]},
            ),
            st.SchedulerTask(
                time=now + timedelta(hours=5),
                task_type=TaskTypes.SWAP_SUPPORT,
                task_plan={"train": ["Current", "泥岩"]},
            ),
        ]

        class FixedDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                if tz is not None:
                    return cls.now_value.replace(tzinfo=tz)
                return cls.now_value

        FixedDateTime.now_value = now

        with (
            patch.object(base_schedule, "datetime", FixedDateTime),
            patch.object(st, "datetime", FixedDateTime),
            patch.object(BaseSchedulerSolver, "scene", return_value=Scene.INDEX),
        ):
            solver.handle_error(force=True)

        # 超时的非专精任务被清掉
        self.assertIsNone(find_next_task(solver.tasks, task_type=TaskTypes.RUN_ORDER))
        # 远期 SWAP_SUPPORT 保留
        self.assertIsNotNone(
            find_next_task(solver.tasks, task_type=TaskTypes.SWAP_SUPPORT)
        )
        # 补了一条立即空任务（NOT_SPECIFIC，time=now）
        empty = find_next_task(solver.tasks, task_type=TaskTypes.NOT_SPECIFIC)
        self.assertIsNotNone(empty)
        self.assertEqual(empty.time, now)

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

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_no_second_read_for_training_state(self):
        # 审计修复：training/空闲态 reconcile 只改 DB，物理房间不变——不二次读
        # read_room_state（面板 OCR + 可能重开进驻浮窗/技能页深读是纯浪费）。
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
            ) as mock_read,
            patch("arknights_mower.solvers.mastery_reader.reconcile_short"),
        ):
            solver.agent_arrange_room({}, "train", plan)
        self.assertEqual(mock_read.call_count, 1)
        self.assertNotIn("train", plan)  # 锁定 → 跳过

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_waiting_collect_collected_no_reread(self):
        """#210：reconcile 收集后 gate 复用 ① 槽位 + 状态设空闲 + 重算保护，不再重读。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        wc = mastery_reader.RoomState("waiting_collect", mastery_reader.RoomPanel())
        wc.slots_read = True  # ① 在 TRAIN_MAIN 读过槽位 → 复用路径
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=wc,
            ) as mock_read,
            patch(
                "arknights_mower.solvers.mastery_reader.reconcile_short",
                return_value=True,
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        self.assertEqual(mock_read.call_count, 1)  # 收集后不再重读
        solver.turn_on_room_detail.assert_called_with("train")  # 状态设空闲 → 正常安排
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_waiting_collect_not_collected_skips(self):
        """#210：reconcile 没收集（队列已有任务 skip）→ 状态/保护没变，跳过重读并冻结。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        wc = mastery_reader.RoomState("waiting_collect", mastery_reader.RoomPanel())
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=wc,
            ) as mock_read,
            patch(
                "arknights_mower.solvers.mastery_reader.reconcile_short",
                return_value=False,
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        self.assertEqual(mock_read.call_count, 1)  # 没收集不重读
        solver.turn_on_room_detail.assert_not_called()  # 仍待收取 → 锁定跳过
        solver.back.assert_called_once_with()
        self.assertNotIn("train", plan)
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_reconcile_error_no_crash_stays_locked(self):
        """#210 review：reconcile_short 抛异常时 collected 兜底为 False，不 UnboundLocalError，
        状态保持待收取 → 锁定跳过。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        wc = mastery_reader.RoomState("waiting_collect", mastery_reader.RoomPanel())
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                return_value=wc,
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.reconcile_short",
                side_effect=RuntimeError("对账失败"),
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        solver.turn_on_room_detail.assert_not_called()
        solver.back.assert_called_once_with()
        self.assertNotIn("train", plan)
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_collected_no_slots_read_rereads(self):
        """#210 review：TRAIN_FINISH 横幅页首次进房未读槽位，收集后重读拿进驻数据+保护。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        wc = mastery_reader.RoomState("waiting_collect", mastery_reader.RoomPanel())
        wc.slots_read = False  # 模拟 TRAIN_FINISH 横幅页首次进房
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                side_effect=[wc, self._empty_room()],
            ) as mock_read,
            patch(
                "arknights_mower.solvers.mastery_reader.reconcile_short",
                return_value=True,
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        self.assertEqual(mock_read.call_count, 2)  # ① + 收集后重读
        solver.turn_on_room_detail.assert_called_with("train")  # 重读后空闲 → 正常安排
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_read_failure_freezes_train_slot_when_following(self):
        """#211：读失败（room_state=None）保守冻结训练位，替代已删的 train_slot_locked。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(base_schedule.config.conf, "assistant_follows_schedule", True),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                side_effect=RuntimeError("读失败"),
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        solver.refresh_current_room.assert_called_once_with(
            "train", [1]
        )  # idx1=Current
        self.assertEqual(result, {})

    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_gate_read_failure_skips_when_not_following(self):
        """#211：读失败且不跟随排班 → 跳过训练室，不盲目安排。"""
        plan = {"train": ["干员A", "干员B"]}
        solver = self._make_solver(plan)
        with (
            patch.object(base_schedule.config.conf, "enable_mastery", True),
            patch.object(
                base_schedule.config.conf, "assistant_follows_schedule", False
            ),
            patch(
                "arknights_mower.solvers.mastery_reader.read_room_state",
                side_effect=RuntimeError("读失败"),
            ),
        ):
            result = solver.agent_arrange_room({}, "train", plan)
        solver.turn_on_room_detail.assert_not_called()
        solver.back.assert_called_once_with()
        self.assertNotIn("train", plan)
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
        # §16.11 铁律 10「留」半边：OFF 时仓库扫描钩子（retry/auto_schedule/workshop）
        # 照跑，只有派发受 enable_mastery 门控。三个钩子无条件被调 + dispatch 不被调
        # 钉死结构——把门误提到钩子前（failed 计划永不重置、idle 永不重排）套件会红。
        solver = self._solver()
        with (
            patch(
                "arknights_mower.utils.mastery_db.retry_failed_plans",
                return_value=0,
            ) as mock_retry,
            patch(
                "arknights_mower.utils.mastery_recommendation.auto_schedule_mastery_tasks",
                return_value={
                    "scheduled": [{"char_id": "char_a", "skill_index": 1}],
                    "skipped": [],
                },
            ) as mock_auto,
            patch(
                "arknights_mower.utils.mastery_recommendation.compute_workshop_config",
                return_value=None,
            ) as mock_workshop,
            patch.object(
                base_schedule.BaseSchedulerSolver, "_dispatch_scan_start_tasks"
            ) as mock_dispatch,
            patch.object(base_schedule.config.conf, "enable_mastery", False),
        ):
            solver._auto_schedule_mastery_after_scan()
        self.assertEqual(solver.tasks, [], "OFF 时不入队开始训练任务")
        mock_retry.assert_called()
        mock_auto.assert_called()
        mock_workshop.assert_called()
        mock_dispatch.assert_not_called()

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
