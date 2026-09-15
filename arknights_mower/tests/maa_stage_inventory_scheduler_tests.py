import sys
import unittest
from datetime import datetime, timedelta
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
    maa_penguin_id="",
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
        maa_penguin_id=maa_penguin_id,
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


class MaaFightPenguinTests(unittest.TestCase):
    """#206：penguin_id 由硬编码空串改为配置下发，企鹅上报原为硬编码常开。"""

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

    def test_fight_sends_empty_penguin_id_by_default(self):
        # 默认空串：行为与旧硬编码 "" 一致，企鹅上报不受影响
        task_config = self._append_fight().args[1]
        self.assertIs(task_config["report_to_penguin"], True)
        self.assertEqual(task_config["penguin_id"], "")

    def test_fight_sends_configured_penguin_id(self):
        # 填写企鹅 id：如实下发
        task_config = self._append_fight(maa_penguin_id="penguin-abc").args[1]
        self.assertEqual(task_config["penguin_id"], "penguin-abc")

    def test_fight_penguin_id_is_string_type(self):
        # penguin_id 按协议为 string：默认下发空字符串而非 null
        task_config = self._append_fight().args[1]
        self.assertIsInstance(task_config["penguin_id"], str)


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


def _rg_conf(
    *,
    theme="Sami",
    mode=0,
    squad="",
    difficulty=-1,
    stop_at_final_boss=False,
    stop_at_max_level=False,
    investment_enabled=True,
    stop_when_investment_full=False,
    investment_with_more_score=False,
    collectible_mode_shopping=False,
    collectible_mode_squad="",
    refresh_trader_with_dice=False,
    start_with_elite_two=False,
    only_start_with_elite_two=False,
    collectible_mode_start_list=None,
    expected_collapsal_paradigms=("目空一些", "睁眼瞎"),
    monthly_squad_auto_iterate=False,
    monthly_squad_check_comms=False,
    deep_exploration_auto_iterate=False,
    first_floor_foldartal="",
    start_foldartal_list=None,
    blackflow_cultivation_target="swaddled_cat",
    find_playtime_target=1,
):
    """Roguelike 长任务走 maa_plan_solver 的 conf，构造 .RG 分支所需的最小实例。"""
    return SimpleNamespace(
        maa_gap=4,
        RG=True,
        SSS=False,
        RCL=False,
        RA=False,
        SF=False,
        maa_rg_sleep_min="12:00",
        maa_rg_sleep_max="12:00",
        maa_rg_theme=theme,
        rogue=SimpleNamespace(
            squad=squad,
            roles="",
            core_char="",
            use_support=False,
            use_nonfriend_support=False,
            start_with_elite_two=start_with_elite_two,
            only_start_with_elite_two=only_start_with_elite_two,
            mode=mode,
            refresh_trader_with_dice=refresh_trader_with_dice,
            expected_collapsal_paradigms=list(expected_collapsal_paradigms),
            difficulty=difficulty,
            stop_at_final_boss=stop_at_final_boss,
            stop_at_max_level=stop_at_max_level,
            investment_enabled=investment_enabled,
            stop_when_investment_full=stop_when_investment_full,
            investment_with_more_score=investment_with_more_score,
            collectible_mode_shopping=collectible_mode_shopping,
            collectible_mode_squad=collectible_mode_squad,
            collectible_mode_start_list=collectible_mode_start_list or {},
            monthly_squad_auto_iterate=monthly_squad_auto_iterate,
            monthly_squad_check_comms=monthly_squad_check_comms,
            deep_exploration_auto_iterate=deep_exploration_auto_iterate,
            first_floor_foldartal=first_floor_foldartal,
            start_foldartal_list=start_foldartal_list or [],
            blackflow_cultivation_target=blackflow_cultivation_target,
            find_playtime_target=find_playtime_target,
        ),
    )


class MaaRoguelikeTests(unittest.TestCase):
    """#264：Roguelike 下发补齐通用字段；协议注明「仅某主题/某模式」的字段按条件省略。"""

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def _run_rogue(self, **overrides):
        solver = BaseSchedulerSolver()
        solver.recog = MagicMock()
        solver.last_execution = {"maa": None}
        solver.credit_fight = None
        solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(days=1))]
        mock_maa = MagicMock()
        # running() 立即返回 False：MAA 运行循环一次都不进，只断言 append_task 参数。
        mock_maa.running.return_value = False

        def _init_maa():
            solver.MAA = mock_maa

        with (
            patch.object(base_schedule.config, "conf", _rg_conf(**overrides)),
            patch.object(solver, "back_to_index"),
            patch.object(solver, "initialize_maa", side_effect=_init_maa),
            patch.object(solver, "append_maa_task"),
            patch.object(solver, "rest_until_next_task"),
            patch.object(solver, "maa_stop"),
            patch.object(base_schedule, "get_server_weekday", return_value=1),
            patch.object(base_schedule, "send_message"),
        ):
            solver.maa_plan_solver()
        return mock_maa.append_task.call_args

    def test_rogue_sends_common_fields_with_protocol_defaults(self):
        # 默认值对照活文档：difficulty=-1、investment_enabled=True；这里 mode=0、主题 Sami
        # 满足 stop_at_final_boss/stop_at_max_level 的条件（如实下发配置值），
        # 投资/指路鳞字段按协议在 investment_enabled 时整体下发（值内联条件，此处为 False），
        # 烧水/直升字段不满足各自条件，不进入任务参数。
        call = self._run_rogue(theme="Sami")
        task_type, task_config = call.args
        self.assertEqual(task_type, "Roguelike")
        self.assertEqual(task_config["difficulty"], -1)
        self.assertIs(task_config["stop_at_final_boss"], False)
        self.assertEqual(task_config["stop_at_max_level"], False)
        self.assertEqual(task_config["investment_enabled"], True)
        self.assertIs(task_config["stop_when_investment_full"], False)
        self.assertIs(task_config["investment_with_more_score"], False)
        self.assertIs(task_config["refresh_trader_with_dice"], False)
        self.assertNotIn("collectible_mode_shopping", task_config)
        self.assertNotIn("collectible_mode_squad", task_config)
        self.assertNotIn("start_with_elite_two", task_config)
        self.assertNotIn("only_start_with_elite_two", task_config)

    def test_rogue_includes_stop_at_final_boss_for_non_phantom(self):
        # Phantom 之外的主题下发 stop_at_final_boss（协议：除 Phantom 外均适用）
        task_config = self._run_rogue(theme="Mizuki", stop_at_final_boss=True).args[1]
        self.assertIs(task_config["stop_at_final_boss"], True)

    def test_rogue_omits_stop_at_final_boss_for_phantom(self):
        # Phantom 主题不适用：不下发 stop_at_final_boss（stop_at_max_level 无主题限制仍下发）
        task_config = self._run_rogue(theme="Phantom").args[1]
        self.assertNotIn("stop_at_final_boss", task_config)
        self.assertIn("stop_at_max_level", task_config)

    def test_rogue_omits_stop_at_levels_outside_mode0(self):
        # stop_at_final_boss/stop_at_max_level 仅在策略为 0（刷等级）时下发（MAA 的 Mode==Exp 分支）
        for theme, mode in (
            ("Sami", 1),
            ("Sami", 4),
            ("Mizuki", 5),
            ("BlackFlow", 30001),
        ):
            task_config = self._run_rogue(
                theme=theme, mode=mode, stop_at_final_boss=True, stop_at_max_level=True
            ).args[1]
            self.assertNotIn("stop_at_final_boss", task_config)
            self.assertNotIn("stop_at_max_level", task_config)

    def test_rogue_includes_expected_collapsal_for_sami_mode5(self):
        # 协议注明 expected_collapsal_paradigms 仅在主题为 Sami 且策略为 5 时有效：
        # 该组合下如实下发配置的坍缩范式列表。
        task_config = self._run_rogue(
            theme="Sami", mode=5, expected_collapsal_paradigms=("目空一些", "一抹黑")
        ).args[1]
        self.assertEqual(
            task_config["expected_collapsal_paradigms"], ["目空一些", "一抹黑"]
        )

    def test_rogue_omits_expected_collapsal_outside_sami_mode5(self):
        # Sami+其它策略、其它主题都不适用：不下发 expected_collapsal_paradigms
        # （与 stop_at_final_boss 的 Phantom 处理一致，字段隐藏即不进入任务参数）。
        for theme, mode in (("Sami", 0), ("Sami", 6), ("Mizuki", 5), ("Phantom", 5)):
            task_config = self._run_rogue(theme=theme, mode=mode).args[1]
            self.assertNotIn("expected_collapsal_paradigms", task_config)

    def test_rogue_omits_expected_collapsal_when_list_empty(self):
        # Sami + 策略 5 但坍缩范式列表为空：不下发 expected_collapsal_paradigms
        task_config = self._run_rogue(
            theme="Sami", mode=5, expected_collapsal_paradigms=()
        ).args[1]
        self.assertNotIn("expected_collapsal_paradigms", task_config)

    def test_rogue_forwards_blackflow_theme_and_mode_30001(self):
        # 主题 BlackFlow 与模式 30001 原样转发（新增枚举穿透后端）；
        # 策略非 0 时 stop_at_final_boss/stop_at_max_level 不下发。
        task_config = self._run_rogue(theme="BlackFlow", mode=30001).args[1]
        self.assertEqual(task_config["theme"], "BlackFlow")
        self.assertEqual(task_config["mode"], 30001)
        self.assertNotIn("stop_at_final_boss", task_config)
        self.assertNotIn("stop_at_max_level", task_config)

    def test_rogue_forwards_theme_gated_modes(self):
        # 主题限定模式原样转发：Sarkaz 的 10001 与 JieGarden 的 20001（后端只透传数值）
        sarkaz = self._run_rogue(theme="Sarkaz", mode=10001).args[1]
        self.assertEqual(sarkaz["theme"], "Sarkaz")
        self.assertEqual(sarkaz["mode"], 10001)
        jiegarden = self._run_rogue(theme="JieGarden", mode=20001).args[1]
        self.assertEqual(jiegarden["theme"], "JieGarden")
        self.assertEqual(jiegarden["mode"], 20001)

    def test_rogue_sends_monthly_squad_fields_for_mode6(self):
        # 模式 6（月度小队）：协议两键在模式匹配时下发，通信检查先勾自动切换后才下发
        task_config = self._run_rogue(
            theme="Sami",
            mode=6,
            squad="生活至上分队",
            monthly_squad_auto_iterate=True,
            monthly_squad_check_comms=True,
        ).args[1]
        self.assertIs(task_config["monthly_squad_auto_iterate"], True)
        self.assertIs(task_config["monthly_squad_check_comms"], True)

    def test_rogue_omits_check_comms_without_auto_iterate(self):
        # 自动切换未勾选：通信检查不下发（与 MAA XAML 的可视条件一致）
        task_config = self._run_rogue(
            theme="Mizuki", mode=6, monthly_squad_check_comms=True
        ).args[1]
        self.assertIs(task_config["monthly_squad_auto_iterate"], False)
        self.assertNotIn("monthly_squad_check_comms", task_config)

    def test_rogue_sends_deep_exploration_for_mode7(self):
        # 模式 7（深入调查）：deep_exploration_auto_iterate 在模式匹配时下发
        task_config = self._run_rogue(
            theme="Sarkaz", mode=7, deep_exploration_auto_iterate=True
        ).args[1]
        self.assertIs(task_config["deep_exploration_auto_iterate"], True)

    def test_rogue_omits_mode_gated_fields_outside_modes(self):
        # 模式 0：月度小队/深入调查字段均不下发
        task_config = self._run_rogue(theme="Sami", mode=0).args[1]
        self.assertNotIn("monthly_squad_auto_iterate", task_config)
        self.assertNotIn("deep_exploration_auto_iterate", task_config)

    def test_rogue_sends_first_floor_foldartal_for_sami_collectible(self):
        # Sami + 模式 4：板子名非空时下发 first_floor_foldartal（协议值为字符串）
        task_config = self._run_rogue(
            theme="Sami", mode=4, squad="指挥分队", first_floor_foldartal="远见"
        ).args[1]
        self.assertEqual(task_config["first_floor_foldartal"], "远见")

    def test_rogue_omits_first_floor_foldartal_outside_conditions(self):
        # 非 Sami 或非模式 4：不下发；板子名为空同样不下发
        task_config = self._run_rogue(
            theme="Mizuki", mode=4, squad="指挥分队", first_floor_foldartal="远见"
        ).args[1]
        self.assertNotIn("first_floor_foldartal", task_config)
        task_config = self._run_rogue(
            theme="Sami", mode=0, squad="指挥分队", first_floor_foldartal="远见"
        ).args[1]
        self.assertNotIn("first_floor_foldartal", task_config)
        task_config = self._run_rogue(theme="Sami", mode=4, squad="指挥分队").args[1]
        self.assertNotIn("first_floor_foldartal", task_config)

    def test_rogue_sends_start_foldartal_list_for_foldartal_squad(self):
        # Sami + 模式 4 + 生活至上分队 + 列表非空：下发 start_foldartal_list
        task_config = self._run_rogue(
            theme="Sami",
            mode=4,
            squad="生活至上分队",
            start_foldartal_list=["板子一", "板子二"],
        ).args[1]
        self.assertEqual(task_config["start_foldartal_list"], ["板子一", "板子二"])

    def test_rogue_omits_start_foldartal_list_outside_foldartal_squad(self):
        # 非生活至上分队或列表为空：不下发 start_foldartal_list
        task_config = self._run_rogue(
            theme="Sami",
            mode=4,
            squad="指挥分队",
            start_foldartal_list=["板子一"],
        ).args[1]
        self.assertNotIn("start_foldartal_list", task_config)
        task_config = self._run_rogue(theme="Sami", mode=4, squad="生活至上分队").args[
            1
        ]
        self.assertNotIn("start_foldartal_list", task_config)

    def test_rogue_sends_blackflow_fields_for_baby_animal(self):
        # BlackFlow + 模式 30001：策略固定 baby_animal，目标品种取自配置
        task_config = self._run_rogue(
            theme="BlackFlow",
            mode=30001,
            blackflow_cultivation_target="swaddled_dog",
        ).args[1]
        self.assertEqual(task_config["blackflow_strategy"], "baby_animal")
        self.assertEqual(task_config["blackflow_cultivation_target"], "swaddled_dog")

    def test_rogue_omits_blackflow_fields_outside_baby_animal(self):
        # 非 30001 模式：黑流树海字段不下发
        task_config = self._run_rogue(theme="BlackFlow", mode=0).args[1]
        self.assertNotIn("blackflow_strategy", task_config)
        self.assertNotIn("blackflow_cultivation_target", task_config)

    def test_rogue_sends_playtime_target_for_jiegarden(self):
        # 界园 + 模式 20001：下发 find_playTime_target（协议键为大写 T）
        task_config = self._run_rogue(
            theme="JieGarden", mode=20001, find_playtime_target=2
        ).args[1]
        self.assertEqual(task_config["find_playTime_target"], 2)

    def test_rogue_omits_playtime_target_outside_conditions(self):
        # 界园非 20001 或其他主题：不下发 find_playTime_target
        task_config = self._run_rogue(theme="JieGarden", mode=0).args[1]
        self.assertNotIn("find_playTime_target", task_config)
        task_config = self._run_rogue(theme="Sarkaz", mode=20001).args[1]
        self.assertNotIn("find_playTime_target", task_config)

    def test_rogue_forwards_elite_two_fields_for_mizuki_sami_mode4(self):
        # 协议注明 start_with_elite_two 仅适用于模式 4，MAA 另限主题 Mizuki/Sami 且直升值
        # 需与战术分队类同步（RoguelikeSquadIsProfessional）；只凹仅受模式/主题限制。
        task_config = self._run_rogue(
            theme="Mizuki",
            mode=4,
            squad="突击战术分队",
            start_with_elite_two=True,
            only_start_with_elite_two=True,
        ).args[1]
        self.assertIs(task_config["start_with_elite_two"], True)
        self.assertIs(task_config["only_start_with_elite_two"], True)
        # 非战术分队时直升下发 False、只凹仍为 True（协议值语义如此；start=false 与 only=true
        # 的组合会被 MAA 核心判定非法，由前端联动在直升不可见时清除只凹，见 only_elite_two_needs_reset）
        task_config = self._run_rogue(
            theme="Sami",
            mode=4,
            squad="指挥分队",
            start_with_elite_two=True,
            only_start_with_elite_two=True,
        ).args[1]
        self.assertIs(task_config["start_with_elite_two"], False)
        self.assertIs(task_config["only_start_with_elite_two"], True)

    def test_rogue_omits_elite_two_fields_outside_mode4(self):
        # 策略 4 之外：不下发 start_with_elite_two/only_start_with_elite_two
        for theme, mode in (
            ("Mizuki", 0),
            ("Sami", 5),
            ("BlackFlow", 30001),
        ):
            task_config = self._run_rogue(
                theme=theme,
                mode=mode,
                squad="突击战术分队",
                start_with_elite_two=True,
                only_start_with_elite_two=True,
            ).args[1]
            self.assertNotIn("start_with_elite_two", task_config)
            self.assertNotIn("only_start_with_elite_two", task_config)

    def test_rogue_forwards_elite_two_fields_false_on_other_themes_mode4(self):
        # 策略 4 且主题非 Mizuki/Sami：两个键仍下发但值为 False（与 MAA 一致，
        # 勾选值不会在 Phantom/萨卡兹/界园/黑流树海上生效）
        for theme in ("Phantom", "Sarkaz", "JieGarden", "BlackFlow"):
            task_config = self._run_rogue(
                theme=theme,
                mode=4,
                squad="突击战术分队",
                start_with_elite_two=True,
                only_start_with_elite_two=True,
            ).args[1]
            self.assertIs(task_config["start_with_elite_two"], False)
            self.assertIs(task_config["only_start_with_elite_two"], False)

    def test_rogue_forwards_common_configured_fields(self):
        # 通用字段配置后如实下发（难度、投资开关、等级停止）
        task_config = self._run_rogue(
            difficulty=2,
            investment_enabled=False,
            stop_at_max_level=True,
        ).args[1]
        self.assertEqual(task_config["difficulty"], 2)
        self.assertEqual(task_config["investment_enabled"], False)
        self.assertIs(task_config["stop_at_max_level"], True)

    def test_rogue_forwards_collectible_fields_for_mode4(self):
        # 协议注明 collectible_mode_* 仅用于策略 4（刷开局）：配置后如实下发，
        # collectible_mode_squad 填了分队名则不再跟随 squad。
        task_config = self._run_rogue(
            mode=4,
            collectible_mode_shopping=True,
            collectible_mode_squad="指挥分队",
        ).args[1]
        self.assertIs(task_config["collectible_mode_shopping"], True)
        self.assertEqual(task_config["collectible_mode_squad"], "指挥分队")

    def test_rogue_omits_collectible_fields_outside_mode4(self):
        # 策略 4 之外的组合不下发 collectible_mode_*
        for theme, mode in (
            ("Sami", 0),
            ("Sami", 1),
            ("Sami", 5),
            ("Mizuki", 6),
            ("BlackFlow", 30001),
        ):
            task_config = self._run_rogue(
                theme=theme,
                mode=mode,
                collectible_mode_shopping=True,
                collectible_mode_squad="指挥分队",
            ).args[1]
            self.assertNotIn("collectible_mode_shopping", task_config)
            self.assertNotIn("collectible_mode_squad", task_config)

    def test_rogue_forwards_collectible_start_list_for_mode4(self):
        # 协议注明 collectible_mode_start_list 仅在策略为 4 时有效：未勾「只凹」时
        # 下发完整奖励表，未配置的键为 False（与 MAA 一致）
        task_config = self._run_rogue(
            mode=4, collectible_mode_start_list={"hot_water": True, "key": True}
        ).args[1]
        self.assertEqual(
            task_config["collectible_mode_start_list"],
            {
                "hot_water": True,
                "shield": False,
                "ingot": False,
                "hope": False,
                "random": False,
                "key": True,
                "dice": False,
                "ideas": False,
                "ticket": False,
            },
        )

    def test_rogue_omits_collectible_start_list_when_only_start_elite_two(self):
        # MAA：勾选「只凹开局干员直升精二」（战术分队类 + 非 Phantom 主题）时不下发奖励表
        task_config = self._run_rogue(
            theme="Sami",
            mode=4,
            squad="突击战术分队",
            start_with_elite_two=True,
            only_start_with_elite_two=True,
            collectible_mode_start_list={"hot_water": True},
        ).args[1]
        self.assertNotIn("collectible_mode_start_list", task_config)

    def test_rogue_omits_collectible_start_list_outside_mode4(self):
        # 策略 4 之外不下发 collectible_mode_start_list
        for theme, mode in (("Sami", 0), ("Sami", 1), ("Mizuki", 6)):
            task_config = self._run_rogue(
                theme=theme, mode=mode, collectible_mode_start_list={"hot_water": True}
            ).args[1]
            self.assertNotIn("collectible_mode_start_list", task_config)

    def test_rogue_forwards_stop_when_investment_full_for_mode1(self):
        # MAA 在 investment_enabled 时下发投资类字段，值内联策略 1（刷源石锭）限制，主题不限
        for theme in ("Sami", "BlackFlow"):
            task_config = self._run_rogue(
                theme=theme, mode=1, stop_when_investment_full=True
            ).args[1]
            self.assertIs(task_config["stop_when_investment_full"], True)

    def test_rogue_false_value_outside_mode1_when_investment_enabled(self):
        # 投资开启但策略不是 1：stop_when_investment_full 仍下发，值为 False（与 MAA 一致）
        for theme, mode in (("Sami", 0), ("Sami", 4), ("Sarkaz", 10001)):
            task_config = self._run_rogue(
                theme=theme, mode=mode, stop_when_investment_full=True
            ).args[1]
            self.assertIs(task_config["stop_when_investment_full"], False)

    def test_rogue_omits_stop_when_investment_fields_when_investment_disabled(self):
        # 未投资源石锭时不下发 stop_when_investment_full 与 investment_with_more_score
        task_config = self._run_rogue(
            mode=1, investment_enabled=False, stop_when_investment_full=True
        ).args[1]
        self.assertNotIn("stop_when_investment_full", task_config)
        self.assertNotIn("investment_with_more_score", task_config)

    def test_rogue_forwards_investment_with_more_score_for_mode1(self):
        # investment_with_more_score 仅在策略 1 且主题非 BlackFlow 时值为 True
        task_config = self._run_rogue(
            theme="Sami", mode=1, investment_with_more_score=True
        ).args[1]
        self.assertIs(task_config["investment_with_more_score"], True)
        task_config = self._run_rogue(
            theme="BlackFlow", mode=1, investment_with_more_score=True
        ).args[1]
        self.assertIs(task_config["investment_with_more_score"], False)
        task_config = self._run_rogue(
            theme="Sami", mode=0, investment_with_more_score=True
        ).args[1]
        self.assertIs(task_config["investment_with_more_score"], False)

    def test_rogue_forwards_refresh_trader_for_mizuki(self):
        # 协议注明 refresh_trader_with_dice（指路鳞）仅支持主题 Mizuki
        task_config = self._run_rogue(
            theme="Mizuki", refresh_trader_with_dice=True
        ).args[1]
        self.assertIs(task_config["refresh_trader_with_dice"], True)

    def test_rogue_forwards_refresh_trader_false_outside_mizuki(self):
        # 指路鳞键始终下发，值内联 Mizuki 限制：其他主题为 False（与 MAA 一致）
        for theme in ("Sami", "Sarkaz", "Phantom"):
            task_config = self._run_rogue(
                theme=theme, refresh_trader_with_dice=True
            ).args[1]
            self.assertIs(task_config["refresh_trader_with_dice"], False)


if __name__ == "__main__":
    unittest.main()
