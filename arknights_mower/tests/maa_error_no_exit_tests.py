import sys
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

# base_schedule 的导入链会初始化森空岛模块；调度接线测试不依赖网络。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

import arknights_mower.solvers.base_schedule as base_schedule  # noqa: E402
from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402


class MaaErrorNoExitTests(unittest.TestCase):
    """#259：MAA 调用出错时异常路径不再调用 device.exit() 关闭游戏。

    原行为是 maa_plan_solver 里任何异常都落到 except Exception → device.exit()
    关游戏再重拉。修正后保留「瞬时错误不杀游戏、确认真死才重启」原则：出错时
    只释放 MAA（self.MAA = None）、记录错误、通知用户、本轮跳过，交给下个调度周期。
    """

    def setUp(self):
        # 未预期的异常必须使测试失败，不能进入真实休眠或被吞掉后假通过。
        # 检查预期异常的用例在自己的 with 中覆盖这两个 mock。
        self.unexpected_idle = self.enterContext(
            patch.object(BaseSchedulerSolver, "_idle_sleep")
        )
        self.unexpected_error = self.enterContext(
            patch.object(base_schedule, "save_exception")
        )
        self.addCleanup(self.unexpected_idle.assert_not_called)
        self.addCleanup(self.unexpected_error.assert_not_called)

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_initialize_maa_failure_does_not_exit_game(self):
        # 初始化连不上 MAA（initialize_maa 抛错）→ 异常路径不得关闭游戏
        solver = BaseSchedulerSolver()
        solver.device = MagicMock()
        solver.recog = MagicMock()
        solver.last_execution = {"maa": None}
        solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(hours=1))]
        with (
            patch.object(base_schedule.config, "conf", SimpleNamespace(maa_gap=4)),
            patch.object(solver, "back_to_index"),
            patch.object(
                solver, "initialize_maa", side_effect=RuntimeError("MAA 连接失败")
            ),
            patch.object(solver, "_idle_sleep"),
            patch.object(base_schedule, "send_message") as send_message,
            patch.object(base_schedule, "save_exception"),
        ):
            solver.maa_plan_solver()

        solver.device.exit.assert_not_called()
        solver.device.check_current_focus.assert_not_called()
        # 出错的 MAA 实例被释放
        self.assertIsNone(solver.MAA)
        # 仍然通知用户（原有错误通知保留）
        send_message.assert_any_call("MAA 连接失败", "MAA调用出错！", level="ERROR")

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_task_dispatch_failure_does_not_exit_game(self):
        # 任务中途下发出错（append_maa_task 抛错）→ 同样不关闭游戏
        solver = BaseSchedulerSolver()
        solver.device = MagicMock()
        solver.recog = MagicMock()
        solver.last_execution = {"maa": None}
        solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(hours=1))]
        with (
            patch.object(base_schedule.config, "conf", SimpleNamespace(maa_gap=4)),
            patch.object(solver, "back_to_index"),
            patch.object(solver, "initialize_maa"),
            patch.object(
                solver, "append_maa_task", side_effect=RuntimeError("任务下发失败")
            ),
            patch.object(solver, "_idle_sleep"),
            patch.object(base_schedule, "send_message") as send_message,
            patch.object(base_schedule, "save_exception"),
        ):
            solver.maa_plan_solver()

        solver.device.exit.assert_not_called()
        solver.device.check_current_focus.assert_not_called()
        send_message.assert_any_call("任务下发失败", "MAA调用出错！", level="ERROR")

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_error_path_resets_scene_timer_before_idle_sleep(self):
        # 评审 P2：异常路径在 _idle_sleep 前必须重置 recog.last_scene，否则休眠会被
        # check_freeze 当成「同一场景超时」再次 device.exit() 关闭游戏（参照 rest_until_next_task）。
        solver = BaseSchedulerSolver()
        solver.device = MagicMock()
        solver.recog = MagicMock()
        solver.recog.last_scene = "previous-scene"
        solver.last_execution = {"maa": None}
        solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(hours=1))]
        captured = {}

        def _capture(remaining_time):
            captured["last_scene"] = solver.recog.last_scene

        with (
            patch.object(base_schedule.config, "conf", SimpleNamespace(maa_gap=4)),
            patch.object(solver, "back_to_index"),
            patch.object(
                solver, "initialize_maa", side_effect=RuntimeError("MAA 连接失败")
            ),
            patch.object(solver, "_idle_sleep", side_effect=_capture),
            patch.object(base_schedule, "send_message"),
            patch.object(base_schedule, "save_exception"),
        ):
            solver.maa_plan_solver()

        self.assertIsNone(captured["last_scene"])
        solver.device.exit.assert_not_called()

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_long_task_crash_does_not_exit_game_or_retry(self):
        # 肉鸽/保全/盐酸长任务 MAA 运行中断 → 不关游戏、不原地重试、本轮跳过
        solver = BaseSchedulerSolver()
        solver.device = MagicMock()
        solver.recog = MagicMock()
        solver.last_execution = {"maa": None}
        solver.credit_fight = None
        solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(days=1))]
        conf = SimpleNamespace(
            RG=True,
            SSS=False,
            RCL=False,
            RA=False,
            SF=False,
            maa_rg_sleep_min="12:00",
            maa_rg_sleep_max="12:00",
            maa_rg_theme="Sami",
            rogue=SimpleNamespace(
                squad="",
                roles="",
                core_char="",
                use_support=False,
                use_nonfriend_support=False,
                mode=0,
                refresh_trader_with_dice=False,
                expected_collapsal_paradigms=[],
                difficulty=-1,
                stop_at_final_boss=False,
                stop_at_max_level=False,
                investment_enabled=True,
                stop_when_investment_full=False,
                investment_with_more_score=False,
                collectible_mode_shopping=False,
                collectible_mode_squad="",
            ),
        )
        mock_maa = MagicMock()
        # running() 立即返回 False：MAA 运行循环一次都不进，留下 maa_crash=True
        mock_maa.running.return_value = False

        def _init_maa():
            solver.MAA = mock_maa

        with (
            patch.object(base_schedule.config, "conf", conf),
            patch.object(solver, "back_to_index"),
            patch.object(solver, "initialize_maa", side_effect=_init_maa) as init_maa,
            patch.object(solver, "append_maa_task"),
            patch.object(solver, "rest_until_next_task"),
            patch.object(base_schedule, "get_server_weekday", return_value=1),
            patch.object(base_schedule, "send_message") as send_message,
        ):
            solver.maa_plan_solver()

        solver.device.exit.assert_not_called()
        solver.device.check_current_focus.assert_not_called()
        send_message.assert_any_call("MAA 肉鸽/保全/盐酸运行中断", level="ERROR")
        # 不原地重试：initialize_maa 只被调两次（日常一次 + 长任务一次），无第三次
        self.assertEqual(init_maa.call_count, 2)

    @patch.object(BaseSchedulerSolver, "__init__", lambda self: None)
    def test_normal_completion_does_not_exit_game(self):
        # MAA 正常完成的路径不受影响：运行结束后不新增任何退出逻辑
        solver = BaseSchedulerSolver()
        solver.device = MagicMock()
        solver.recog = MagicMock()
        solver.last_execution = {"maa": None}
        solver.credit_fight = None
        solver.tasks = [SimpleNamespace(time=datetime.now() + timedelta(days=1))]
        mock_maa = MagicMock()
        # 先运行一轮再正常结束（running True → False），不触发 maa_crash
        mock_maa.running.side_effect = [True, False]

        def _init_maa():
            solver.MAA = mock_maa

        with (
            patch.object(
                base_schedule.config,
                "conf",
                SimpleNamespace(
                    maa_gap=4,
                    maa_restore_theme_enable=False,
                    RG=False,
                    SSS=False,
                    RCL=False,
                    RA=False,
                    SF=False,
                    maa_rg_sleep_min="12:00",
                    maa_rg_sleep_max="12:00",
                ),
            ),
            patch.object(solver, "back_to_index"),
            patch.object(solver, "initialize_maa", side_effect=_init_maa),
            patch.object(solver, "append_maa_task"),
            patch.object(solver, "sleep"),
            patch.object(solver, "rest_until_next_task") as rest,
            patch.object(base_schedule, "get_server_weekday", return_value=1),
            patch.object(base_schedule, "send_message"),
        ):
            solver.maa_plan_solver()

        solver.device.exit.assert_not_called()
        solver.device.check_current_focus.assert_not_called()
        rest.assert_called_once()


if __name__ == "__main__":
    unittest.main()
