import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# base_schedule 的导入链会初始化森空岛模块；调度接线测试不依赖网络。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402


def _conf(*, enabled=True):
    return SimpleNamespace(
        maa_stage_inventory_enable=enabled,
        maa_stage_limit_rules=[
            {
                "stage": "1-7",
                "operator": "and",
                "enabled": True,
                "items": [{"item_id": "30012", "limit": 10}],
            }
        ],
        maa_stage_ratio_rules=[],
        maa_weekly_plan=[
            SimpleNamespace(
                weekday="周一",
                stage=["1-7", "CE-6"],
                medicine=0,
                sanity_threshold=0,
            )
        ],
        maa_expiring_medicine=False,
        exipring_medicine_on_weekend=False,
        maa_eat_stone=False,
    )


class MaaStageInventorySchedulerTests(unittest.TestCase):
    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_maa_fight_task_omits_stage_that_reached_inventory_limit(self):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []

        with (
            patch.object(base_schedule.config, "conf", _conf()),
            patch.object(base_schedule, "get_server_weekday", return_value=0),
            patch.object(base_schedule, "cultivateDepotSolver") as refresh_solver,
            patch(
                "arknights_mower.utils.maa_stage_inventory.load_inventory_snapshot",
                return_value=({"30012": 10, "4001": 0}, "2026-09-04 12:00:00"),
            ),
        ):
            solver.append_maa_task("Fight")

        refresh_solver.return_value.start.assert_called_once_with()
        solver.MAA.append_task.assert_called_once()
        task_type, task_config = solver.MAA.append_task.call_args.args
        self.assertEqual(task_type, "Fight")
        self.assertEqual(task_config["stage"], "CE-6")
        self.assertEqual(solver.stages, ["CE-6"])

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_local_operation_plan_omits_stage_that_reached_inventory_limit(self):
        solver = BaseSchedulerSolver()

        with (
            patch.object(base_schedule.config, "conf", _conf()),
            patch.object(base_schedule, "get_server_weekday", return_value=0),
            patch.object(base_schedule, "cultivateDepotSolver"),
            patch(
                "arknights_mower.utils.maa_stage_inventory.load_inventory_snapshot",
                return_value=({"30012": 10, "4001": 0}, "2026-09-04 12:00:00"),
            ),
        ):
            stages = solver.mower_stage_plan()

        self.assertEqual(stages, ["CE-6"])

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_disabled_inventory_selection_keeps_original_plan(self):
        solver = BaseSchedulerSolver()

        with (
            patch.object(base_schedule.config, "conf", _conf(enabled=False)),
            patch.object(base_schedule, "cultivateDepotSolver") as refresh_solver,
        ):
            stages = solver.apply_maa_stage_inventory_rules(["1-7", "CE-6"])

        self.assertEqual(stages, ["1-7", "CE-6"])
        refresh_solver.assert_not_called()


if __name__ == "__main__":
    unittest.main()
