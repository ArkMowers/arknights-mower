import unittest
from datetime import datetime
from unittest.mock import patch, MagicMock
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver
from arknights_mower.utils.logic_expression import LogicExpression
from arknights_mower.utils.plan import Room, PlanConfig, Plan

with patch.dict("sys.modules", {"RecruitSolver": MagicMock()}):
    from ..solvers import RecruitSolver


class TestBaseScheduler(unittest.TestCase):
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
            print(solver.op_data.plan_name)
            solver.party_time = datetime.now()
            solver.backup_plan_solver()
            self.assertEqual(solver.op_data.plan_name, "default_plan")

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
            run_order_buffer_time=20,
        )
        agent_base_config = PlanConfig(
            "稀音,黑键,焰尾,伊内丝",
            "稀音,柏喙,伊内丝",
            "伺夜,帕拉斯,雷蛇,澄闪,红云,乌有,年,远牙,阿米娅,桑葚,截云",
            ling_xi=2,
            free_blacklist="艾丽妮,但书,龙舌兰",
            run_order_buffer_time=20,
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
            self.assertEqual(solver.op_data.plan_name, "default_plan")


if __name__ == "__main__":
    unittest.main()
