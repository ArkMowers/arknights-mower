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
    package_type=1,
    medicine_expire_days=0,
    expiring_medicine_on_weekend=False,
    maa_report_to_yituliu=False,
    maa_yituliu_id="",
):
    return SimpleNamespace(
        package_type=package_type,
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
        maa_report_to_yituliu=maa_report_to_yituliu,
        maa_yituliu_id=maa_yituliu_id,
    )


def _mall_conf(
    *,
    squad=1,
    credit_fight_enabled=True,
    ignore_blacklist=False,
    visit_friend_enable=True,
    visit_friend_mode="maa",
    maa_mall_only_buy_discount=False,
    maa_mall_reserve_max_credit=False,
):
    return SimpleNamespace(
        maa_mall_buy="招聘许可,技巧概要·卷2",
        maa_mall_blacklist="加急许可,碳,碳素,家具零件",
        maa_credit_fight=credit_fight_enabled,
        credit_fight=SimpleNamespace(squad=squad),
        maa_mall_ignore_blacklist_when_full=ignore_blacklist,
        visit_friend_enable=visit_friend_enable,
        visit_friend_mode=visit_friend_mode,
        maa_mall_only_buy_discount=maa_mall_only_buy_discount,
        maa_mall_reserve_max_credit=maa_mall_reserve_max_credit,
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


class MaaFightYituliuTests(unittest.TestCase):
    """#265：Fight 补齐协议可加字段 report_to_yituliu / yituliu_id，默认关闭。"""

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _append_fight(self, **overrides):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []
        with (
            patch.object(solver, "maybe_switch_expired_activity_plan"),
            patch.object(
                base_schedule.config, "conf", _conf(enabled=False, **overrides)
            ),
            patch.object(base_schedule, "get_server_weekday", return_value=0),
            patch.object(base_schedule, "cultivateDepotSolver"),
        ):
            solver.append_maa_task("Fight")
        return solver.MAA.append_task.call_args

    def test_fight_defaults_report_disabled_and_id_empty(self):
        # 默认关闭：report_to_yituliu 为 false，yituliu_id 为空字符串
        task_config = self._append_fight().args[1]
        self.assertEqual(task_config["report_to_yituliu"], False)
        self.assertEqual(task_config["yituliu_id"], "")

    def test_fight_enabled_report_and_id_round_trip(self):
        # 开启上报并填 id：如实下发
        task_config = self._append_fight(
            maa_report_to_yituliu=True, maa_yituliu_id="yituliu-abc"
        ).args[1]
        self.assertEqual(task_config["report_to_yituliu"], True)
        self.assertEqual(task_config["yituliu_id"], "yituliu-abc")

    def test_fight_id_is_string_type(self):
        # yituliu_id 按协议为 string：默认下发空字符串而非 null
        task_config = self._append_fight().args[1]
        self.assertIsInstance(task_config["yituliu_id"], str)


class MaaMallFormationIndexTests(unittest.TestCase):
    """#261：Mall 下发协议字段 formation_index，替换非协议字段 select_formation。"""

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _append_mall(self, **overrides):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []
        solver.credit_fight = None
        with patch.object(base_schedule.config, "conf", _mall_conf(**overrides)):
            solver.append_maa_task("Mall")
        return solver.MAA.append_task.call_args

    def test_mall_uses_formation_index_and_drops_select_formation(self):
        call = self._append_mall(squad=1)
        task_type, task_config = call.args
        self.assertEqual(task_type, "Mall")
        self.assertIn("formation_index", task_config)
        self.assertNotIn("select_formation", task_config)

    def test_mall_formation_index_is_squad_without_mapping(self):
        # 0 = 当前编队，1–4 指定对应编队，直接透传 squad
        for squad in (0, 1, 2, 3, 4):
            task_config = self._append_mall(squad=squad).args[1]
            self.assertEqual(task_config["formation_index"], squad)

    def test_mall_formation_index_clamps_out_of_range(self):
        # 钳制到 0–4，防御未来配置越界（不做 -1 变换）
        self.assertEqual(self._append_mall(squad=9).args[1]["formation_index"], 4)
        self.assertEqual(self._append_mall(squad=-3).args[1]["formation_index"], 0)


class MaaMallDiscountCreditTests(unittest.TestCase):
    """#265：Mall 补齐协议可加字段 only_buy_discount / reserve_max_credit，默认均 false。"""

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _append_mall(self, **overrides):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []
        solver.credit_fight = None
        with patch.object(base_schedule.config, "conf", _mall_conf(**overrides)):
            solver.append_maa_task("Mall")
        return solver.MAA.append_task.call_args

    def test_mall_defaults_send_false_for_both_discount_fields(self):
        # 默认未开启：两个字段都下发 false（协议默认值，不省略）
        task_config = self._append_mall().args[1]
        self.assertEqual(task_config["only_buy_discount"], False)
        self.assertEqual(task_config["reserve_max_credit"], False)

    def test_mall_enabled_both_discount_fields_round_trip(self):
        # 两个开关开启时如实下发 true
        task_config = self._append_mall(
            maa_mall_only_buy_discount=True,
            maa_mall_reserve_max_credit=True,
        ).args[1]
        self.assertEqual(task_config["only_buy_discount"], True)
        self.assertEqual(task_config["reserve_max_credit"], True)

    def test_mall_discount_fields_each_controlled_independently(self):
        # 两个开关互不影响：各开启一个，另一个保持 false
        task_config = self._append_mall(
            maa_mall_only_buy_discount=True,
            maa_mall_reserve_max_credit=False,
        ).args[1]
        self.assertEqual(task_config["only_buy_discount"], True)
        self.assertEqual(task_config["reserve_max_credit"], False)


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


class MaaClientTypeTests(unittest.TestCase):
    """#260：StartUp 与 Fight 下发协议必填的 client_type，由 package_type 推导。"""

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _append(self, task_type, package_type):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []
        with (
            patch.object(solver, "maybe_switch_expired_activity_plan"),
            patch.object(
                base_schedule.config,
                "conf",
                _conf(enabled=False, package_type=package_type),
            ),
            patch.object(base_schedule, "get_server_weekday", return_value=0),
            patch.object(base_schedule, "cultivateDepotSolver"),
        ):
            solver.append_maa_task(task_type)
        return solver.MAA.append_task.call_args

    def test_startup_sends_official_for_official_package(self):
        # 官服（package_type=1）推导为 Official
        call = self._append("StartUp", 1)
        self.assertEqual(call.args, ("StartUp", {"client_type": "Official"}))

    def test_startup_sends_bilibili_for_bilibili_package(self):
        # B 服（package_type != 1）推导为 Bilibili
        call = self._append("StartUp", 2)
        self.assertEqual(call.args, ("StartUp", {"client_type": "Bilibili"}))

    def test_fight_sends_official_for_official_package(self):
        # 官服 package_type=1 时 Fight 与 StartUp 一致下发 Official
        call = self._append("Fight", 1)
        task_type, task_config = call.args
        self.assertEqual(task_type, "Fight")
        self.assertEqual(task_config["client_type"], "Official")

    def test_fight_sends_bilibili_for_bilibili_package(self):
        # B 服 package_type=2 时 Fight 下发 Bilibili
        call = self._append("Fight", 2)
        task_config = call.args[1]
        self.assertEqual(task_config["client_type"], "Bilibili")


class MaaVisitFriendModeTests(unittest.TestCase):
    """#262：visit_friend_enable + visit_friend_mode 控制访问好友交给 mower 还是 MAA。

    开启且 mode=mower 时走原生 CreditSolver、Mall 不下发 visit_friends；开启且 mode=maa
    时 Mall 下发 visit_friends: true 且原生跳过；关闭时两者都不做；Visit 死分支已移除。
    """

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _append_mall(self, **overrides):
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.stages = []
        solver.credit_fight = None
        with patch.object(base_schedule.config, "conf", _mall_conf(**overrides)):
            solver.append_maa_task("Mall")
        return solver.MAA.append_task.call_args

    def test_mall_dispatches_visit_friends_when_enabled_and_maa(self):
        # 开启且 mode=maa 时 Mall 下发 visit_friends: true，交给 MAA 处理
        task_config = self._append_mall(
            visit_friend_enable=True, visit_friend_mode="maa"
        ).args[1]
        self.assertEqual(task_config["visit_friends"], True)

    def test_mall_dispatches_visit_friends_false_when_enabled_and_mower(self):
        # 开启且 mode=mower 时 Mall 下发 visit_friends: false，访问好友走 mower 原生
        task_config = self._append_mall(
            visit_friend_enable=True, visit_friend_mode="mower"
        ).args[1]
        self.assertEqual(task_config["visit_friends"], False)

    def test_mall_dispatches_visit_friends_false_when_disabled(self):
        # 关闭时 Mall 下发 visit_friends: false（即使 mode=maa）
        task_config = self._append_mall(
            visit_friend_enable=False, visit_friend_mode="maa"
        ).args[1]
        self.assertEqual(task_config["visit_friends"], False)

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _plan(self, enable, mode):
        solver = BaseSchedulerSolver()
        solver.device = MagicMock()
        solver.recog = MagicMock()
        with (
            patch.object(
                base_schedule.config,
                "conf",
                SimpleNamespace(visit_friend_enable=enable, visit_friend_mode=mode),
            ),
            patch.object(base_schedule, "CreditSolver") as credit,
        ):
            result = solver.visit_friend_plan_solver()
        return result, credit

    def test_enabled_mower_runs_native_credit_solver(self):
        # 开启且 mode=mower 访问好友走原生 CreditSolver
        result, credit = self._plan(True, "mower")
        credit.assert_called_once()
        self.assertTrue(result)

    def test_enabled_maa_skips_native_credit_solver(self):
        # 开启且 mode=maa 原生访问好友跳过，避免与 MAA 的 Mall.visit_friends 双跑
        result, credit = self._plan(True, "maa")
        credit.assert_not_called()
        self.assertFalse(result)

    def test_disabled_skips_native_credit_solver(self):
        # 关闭时原生访问好友跳过（即使 mode=mower）
        result, credit = self._plan(False, "mower")
        credit.assert_not_called()
        self.assertFalse(result)

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_visit_type_is_dead_and_omits_append_task(self):
        # Visit 死分支已移除：下发 Visit 不再有任何 append_task 调用（功能并入 Mall.visit_friends）
        solver = BaseSchedulerSolver()
        solver.MAA = MagicMock()
        solver.append_maa_task("Visit")
        solver.MAA.append_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
