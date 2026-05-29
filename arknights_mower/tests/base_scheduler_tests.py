import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import arknights_mower.solvers.base_schedule as base_schedule
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.operators import Operator
from arknights_mower.utils.plan import Plan, PlanConfig, Room
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.scheduler_task import TaskTypes, find_next_task

with patch.dict("sys.modules", {"RecruitSolver": MagicMock()}):
    pass


class TestBaseScheduler(unittest.TestCase):
    @patch.object(BaseSchedulerSolver, "__init__", lambda x: None)
    def test_run_order_solver_uses_current_time_for_expired_exhaust_task(self):
        solver = BaseSchedulerSolver()
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


if __name__ == "__main__":
    unittest.main()
