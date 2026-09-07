import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# base_schedule 的导入链会初始化森空岛模块；调度接线测试不依赖网络。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402


def _conf(
    *,
    enabled=True,
    medicine_expire_days=0,
    expiring_medicine_on_weekend=False,
):
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
                weekday=name, stage=["1-7", "CE-6"], medicine=0, sanity_threshold=0
            )
            for name in ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
        ],
        medicine_expire_days=medicine_expire_days,
        expiring_medicine_on_weekend=expiring_medicine_on_weekend,
        maa_eat_stone=False,
    )


class MaaFightMedicineExpireDaysTests(unittest.TestCase):
    """#263：Fight 下发 medicine_expire_days，替换已弃用的 expiring_medicine。"""

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _append_fight(self, **overrides):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []
        weekday = overrides.pop("weekday", 0)
        with (
            patch.object(solver, "maybe_switch_expired_activity_plan"),
            # 本类只测 medicine_expire_days 取值，绕过库存选关（不注入快照、不依赖 depot）
            patch.object(
                base_schedule.config, "conf", _conf(enabled=False, **overrides)
            ),
            patch.object(
                base_schedule,
                "get_server_weekday",
                return_value=weekday,
            ),
            patch.object(base_schedule, "cultivateDepotSolver"),
        ):
            solver.append_maa_task("Fight")
        return solver.MAA.append_task.call_args

    def test_disabled_medicine_sends_zero_and_no_legacy_key(self):
        # 默认不使用：medicine_expire_days 为 0，且不带已弃用的 expiring_medicine
        call = self._append_fight(medicine_expire_days=0, weekday=0)
        task_type, task_config = call.args
        self.assertEqual(task_type, "Fight")
        self.assertEqual(task_config["medicine_expire_days"], 0)
        self.assertNotIn("expiring_medicine", task_config)

    def test_configured_medicine_sends_days_regardless_of_weekday(self):
        # 未勾选周末限定：任何一天都下发配置的天数
        for weekday in (0, 6):
            call = self._append_fight(medicine_expire_days=3, weekday=weekday)
            task_config = call.args[1]
            self.assertEqual(task_config["medicine_expire_days"], 3)

    def test_weekend_only_weekday_sends_zero(self):
        # 勾选周末限定：非周末传 0
        call = self._append_fight(
            medicine_expire_days=3, expiring_medicine_on_weekend=True, weekday=0
        )
        task_config = call.args[1]
        self.assertEqual(task_config["medicine_expire_days"], 0)

    def test_weekend_only_weekend_sends_configured_days(self):
        # 勾选周末限定：周末传配置的天数
        call = self._append_fight(
            medicine_expire_days=3, expiring_medicine_on_weekend=True, weekday=6
        )
        task_config = call.args[1]
        self.assertEqual(task_config["medicine_expire_days"], 3)


class MaaStageInventorySchedulerTests(unittest.TestCase):
    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_maa_fight_task_omits_stage_that_reached_inventory_limit(self):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []

        with (
            patch.object(solver, "maybe_switch_expired_activity_plan") as auto_switch,
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
        auto_switch.assert_called_once_with()
        solver.MAA.append_task.assert_called_once()
        task_type, task_config = solver.MAA.append_task.call_args.args
        self.assertEqual(task_type, "Fight")
        self.assertEqual(task_config["stage"], "CE-6")
        self.assertEqual(solver.stages, ["CE-6"])

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_local_operation_plan_omits_stage_that_reached_inventory_limit(self):
        solver = BaseSchedulerSolver()

        with (
            patch.object(solver, "maybe_switch_expired_activity_plan") as auto_switch,
            patch.object(base_schedule.config, "conf", _conf()),
            patch.object(base_schedule, "get_server_weekday", return_value=0),
            patch.object(base_schedule, "cultivateDepotSolver"),
            patch(
                "arknights_mower.utils.maa_stage_inventory.load_inventory_snapshot",
                return_value=({"30012": 10, "4001": 0}, "2026-09-04 12:00:00"),
            ),
        ):
            stages = solver.mower_stage_plan()

        auto_switch.assert_called_once_with()
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
