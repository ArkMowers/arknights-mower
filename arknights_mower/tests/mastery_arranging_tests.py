import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import numpy as np

import arknights_mower.solvers.mastery as mastery
from arknights_mower.solvers import mastery_reader
from arknights_mower.utils import config as config_mod
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.scheduler_task import TaskTypes

START = datetime(2026, 7, 31, 12, 0, 0)


def make_plan(**overrides):
    plan = {
        "id": 1,
        "char_id": "char_test",
        "char_name": "测试干员",
        "skill_index": 1,  # 技能2
        "skill_name": "测试技能",
        "target_level": 3,
        "status": "idle",
    }
    plan.update(overrides)
    return plan


def _to_seconds(dt):
    """fake execute_time(datetime) → read_time 秒；None → None（倒计时读失败）。

    #73 三态倒计时：_read_train_countdown3 改读 read_time 返回秒（None/0/正数）。
    #211：0（00:00:00）是待收取、训练位锁定，与 None（空闲）语义不同——空闲房应传
    None，待收取才传 START（=now，秒 0）。
    """
    if dt is None:
        return None
    return max(0, int((dt - START).total_seconds()))


def _mastery_canvas(lit):
    """构造 1080p 画布，点亮主面板前 lit 颗专精图标。

    #76：主面板专精图标在训练中 = 当前步目标级（亮 N 颗=专N），模拟当前步级。
    """
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    for i, ((x0, y0), (x1, y1)) in enumerate(mastery_reader.MASTERY_ICON_PIPS):
        if i < lit:
            img[y0:y1, x0:x1] = (255, 200, 92)
    return img


class FixedDateTime(datetime):
    """冻结的假时钟，替换 mastery 模块的 datetime。"""

    now_value = START

    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return cls.now_value.replace(tzinfo=tz)
        return cls.now_value


class TestArrangingConvergence(unittest.TestCase):
    """#18 模拟场景测试：fake solver 驱动真实 _start_new_training，断言有限步内收敛。

    _start_new_training 内 `from mastery_db import update_plan_status` 是函数体内局部
    import，因此要 patch 源模块 mastery_db / email，而非 mastery 模块本身。
    """

    def setUp(self):
        FixedDateTime.now_value = START

    def run_arranging(self, solver, plan, advance=timedelta(0)):
        """跑 _start_new_training，返回 (solver, update_plan_status mock)。

        advance：每轮 now() 额外前跳的时长。freeze 测试传 timedelta(minutes=1)
        让 5 分钟 deadline 几秒内可触发；其余场景传 0（冻结时钟）即可。
        """

        class Clock(FixedDateTime):
            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    FixedDateTime.now_value += advance
                    return FixedDateTime.now_value
                return FixedDateTime.now_value.replace(tzinfo=tz)

        clock = Clock if advance else FixedDateTime
        with (
            patch.object(mastery, "datetime", clock),
            # #73 三态倒计时在 reader 层算结束时刻（datetime.now()+秒）→ reader 的
            # datetime 也要冻结，否则占用重排时间用真实时钟、断言时间漂移
            patch.object(mastery_reader, "datetime", clock),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message"),
        ):
            mastery._start_new_training(solver, plan)
        return solver, upd

    @staticmethod
    def _seq(scenes, fallback=Scene.TRAIN_SKILL_SELECT):
        """按列表喂场景，耗尽后停在 fallback。"""

        def _next():
            return scenes.pop(0) if scenes else fallback

        return _next

    def make_solver(
        self,
        scene=None,
        scenes=None,
        scene_fallback=Scene.TRAIN_SKILL_SELECT,
        execute_time=None,
        slots=None,
        choose_train=None,
    ):
        solver = MagicMock()
        if scenes is not None:
            solver.train_scene.side_effect = self._seq(scenes, scene_fallback)
        else:
            solver.train_scene.return_value = scene
        # #73 三态倒计时：读 read_time 返回秒（None=读失败 / 0=00:00:00 / >0=有值）
        solver.read_time.return_value = _to_seconds(execute_time)
        solver.get_agent_from_room.return_value = (
            slots if slots else [{"agent": ""}, {"agent": ""}]
        )
        if choose_train is not None:
            solver.choose_train.side_effect = choose_train
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.tasks = []
        solver.task = None
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        solver.recog.update = MagicMock()
        return solver

    # --- 死循环回归：TRAIN_SKILL_SELECT 无限停留 ---
    def test_freeze_skill_select_does_not_infinite_loop(self):
        """#19 修复前 TRAIN_SKILL_SELECT 分支无超时退出会永远循环。

        现在：经训练位确认进入 219 后若一直卡在 219（ctap 不导航），5 分钟
        deadline 后走统一超时出口 → 置 failed + back() 退出。时钟每轮推进，
        否则 `now() > deadline` 永不成立、测试会真的挂死。
        未确认身份的 219（重启停在技能选择页/手动进入）不走 deadline、立即保守退出——见
        test_misjudged_skill_select_no_identity_exits。
        """
        scenes = [
            Scene.TRAIN_MAIN,  # 读占用(无) → 读槽位(空) → back
            Scene.TRAIN_MAIN,  # 训练位已确认 → 点开技能选择页（身份确认）
            Scene.TRAIN_SKILL_SELECT,  # 读档位(0) → ctap（不导航，卡住）
        ]
        solver = self.make_solver(scenes=scenes)
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan, advance=timedelta(minutes=1))

        self.assertTrue(solver.back.called, "超时后应退出训练室")
        args = upd.call_args[0]
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1], "failed")
        self.assertIn("超时", upd.call_args[1]["failed_reason"])

    # --- 训练室被占用：有倒计时 → idle + 重排 + 退出 ---
    def test_occupied_room_reschedules_and_exits(self):
        execute_time = START + timedelta(hours=2)
        solver = self.make_solver(scene=Scene.TRAIN_MAIN, execute_time=execute_time)
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)

        self.assertEqual(upd.call_args[0][1], "idle")
        self.assertTrue(solver.back.called)
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(
            solver.tasks[0].time, execute_time + mastery.ARRANGING_RETRY_BUFFER
        )
        self.assertFalse(solver.tap.called, "占用时不应盲点选择技能")

    # --- 无倒计时 + 训练位坐错人 → choose_train 换人 ---
    def test_wrong_operator_triggers_swap(self):
        # 场景推进：TRAIN_MAIN(读槽位发现坐错人→换人→back) → TRAIN_MAIN(训练位已确认
        # → 点开技能选择页) → TRAIN_SKILL_SELECT(读档位→ctap，此后停 219，推进时钟收敛)
        solver = self.make_solver(
            scenes=[
                Scene.TRAIN_MAIN,
                Scene.TRAIN_MAIN,
                Scene.TRAIN_SKILL_SELECT,
            ],
            slots=[{"agent": ""}, {"agent": "错误干员"}],
        )
        plan = make_plan()
        self.run_arranging(solver, plan, advance=timedelta(minutes=1))
        solver.choose_train.assert_called()
        self.assertEqual(solver.choose_train.call_args[0][0], ["Current", "测试干员"])

    # --- 00:00:00 待收取：训练位锁定，不换人 ---
    def test_waiting_collect_zero_exits_without_swap(self):
        """#211：00:00:00（待收取，有倒计时值为 0）→ 训练位锁定，保持 idle 退出，
        不触发坐错人换人（旧 _read_train_countdown 把 zero 折叠成 None、误判空闲，
        会换入锁定的训练位，原靠 train_slot_locked 兜底）。"""
        solver = self.make_solver(
            scene=Scene.TRAIN_MAIN,
            slots=[{"agent": ""}, {"agent": "错误干员"}],
        )
        solver.read_time.return_value = 0  # 00:00:00
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)
        self.assertFalse(solver.choose_train.called, "待收取不应换训练位")
        self.assertEqual(upd.call_args[0][1], "idle")
        self.assertTrue(solver.back.called)

    # --- 换人失败 → failed + 退出 ---
    def test_swap_failure_marks_failed(self):
        def boom(*args, **kwargs):
            raise Exception("选人流程超时")

        solver = self.make_solver(
            scene=Scene.TRAIN_MAIN,
            slots=[{"agent": ""}, {"agent": "错误干员"}],
            choose_train=boom,
        )
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)
        args = upd.call_args[0]
        self.assertEqual(args[0], 1)
        self.assertEqual(args[1], "failed")
        self.assertTrue(solver.back.called)

    # --- 空闲训练室 → 正常开始 ---
    def test_free_room_starts_normally(self):
        read_count = {"n": 0}

        def fake_read(*args, **kwargs):
            read_count["n"] += 1
            # 前几次（读占用×N）无倒计时（空闲 → 读失败 None，不占用）；确认流程
            # 读到有效倒计时（7200）确认开始——219 不再读倒计时（#72）
            return None if read_count["n"] <= 3 else 7200

        scenes = [
            Scene.TRAIN_MAIN,  # 迭代1：读倒计时(无) → 读槽位(空) → back
            Scene.TRAIN_MAIN,  # 迭代2：tap 选择技能（身份确认）
            Scene.TRAIN_SKILL_SELECT,  # 迭代3：读档位(0) → ctap 技能
            Scene.TRAIN_SKILL_UPGRADE,  # 迭代4：tap 确认 → 进入确认流程
        ]
        solver = self.make_solver(scenes=scenes, scene_fallback=Scene.TRAIN_MAIN)
        solver.read_time.side_effect = fake_read
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)

        training_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        self.assertTrue(training_calls, "正常开始后应转入 training 状态")

    # --- 技能升级页确认按钮：必须用 skill_confirm 模板定位，不用旧坐标 ---
    def test_upgrade_confirm_taps_skill_confirm_position(self):
        """#53 实机：升级确认按钮在 (1574,896)-(1870,968)，旧坐标 (0.87w,0.9h)=(1670,972)
        会点到按钮下方、关掉弹窗退回技能选择页死循环。确认必须点 skill_confirm 按钮中心。
        """
        skill_confirm_pos = ((1563, 832), (1880, 1048))  # find 返回的可点区域
        solver = MagicMock()
        solver.find.return_value = skill_confirm_pos
        solver.train_scene.side_effect = [
            Scene.TRAIN_SKILL_UPGRADE,
            Scene.TRAIN_MAIN,
        ]
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.tasks = []
        solver.task = None
        solver.recog.w = 1920
        solver.recog.h = 1080
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
        ):
            mastery._start_new_training(solver, plan)
        tap_calls = [c.args[0] for c in solver.tap.call_args_list]
        self.assertIn(
            skill_confirm_pos, tap_calls, "确认按钮应该用 skill_confirm 模板位置点"
        )
        self.assertNotIn(
            (solver.recog.w * 0.87, solver.recog.h * 0.9),
            tap_calls,
            "不应再用会错过按钮的旧坐标 (0.87w, 0.9h)",
        )

    def test_confirm_after_skill_select_backs_to_main_before_countdown(self):
        """#89：确认升级后游戏自动退回技能选择页（真 219，读不出倒计时）——必须 back
        一次回训练室主页面（217）再读倒计时（§16.10 第 3 步「再退出一次」），否则 219
        左下角是协助位天赋文本、会被 OCR 当倒计时反复读甚至假确认开始。
        """
        solver = MagicMock()
        solver.find.return_value = ((1563, 832), (1880, 1048))  # skill_confirm
        solver.train_scene.side_effect = [
            Scene.TRAIN_SKILL_UPGRADE,  # 确认页 → tap 确认
            Scene.TRAIN_SKILL_SELECT,  # 确认后自动退回技能选择页 → back
            Scene.TRAIN_MAIN,  # back 回主页面 → 读倒计时确认开始
        ]
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.tasks = []
        solver.task = None
        solver.recog.w = 1920
        solver.recog.h = 1080
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
        ):
            mastery._start_new_training(solver, plan)
        training_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        self.assertTrue(
            training_calls, "确认后 back 回主页面读到有效倒计时也应确认训练开始"
        )
        # 219 上必须先 back 再读倒计时：read_time 只在回主页面后被调用一次
        call_names = [c[0] for c in solver.method_calls]
        self.assertLess(call_names.index("back"), call_names.index("read_time"))
        self.assertEqual(solver.read_time.call_count, 1)

    # --- #72：未经身份确认的 219（重启停在技能选择页/手动进入）→ 不数星星、不点技能行 ---
    def test_misjudged_skill_select_no_identity_exits(self):
        """未经身份确认的 219：倒计时、面板文字都不可读（技能选择页读不到主面板区域）
        → 数星星前无身份确认，星星可能误读非零值（误开训练/误判完成）→ 保持 idle
        重排退出，绝不 ctap/tap。这是 #72 的核心红测试（旧代码在此会 ctap）。"""
        solver = self.make_solver(
            scene=Scene.TRAIN_SKILL_SELECT,
            execute_time=START,  # 误判页上倒计时不可读（读不到返回 now）
        )
        solver.read_screen.return_value = ""  # 真技能选择页读不到面板文字
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)

        idle_calls = [c for c in upd.call_args_list if c.args[1] == "idle"]
        self.assertTrue(idle_calls, "误判 219 应保持 idle 重排")
        self.assertTrue(solver.back.called, "应退出训练室")
        self.assertEqual(len(solver.tasks), 1, "应重排一条 SKILL_UPGRADE 任务")
        self.assertEqual(
            solver.tasks[0].time,
            START + mastery.ARRANGING_RETRY_BUFFER,
        )
        self.assertFalse(solver.ctap.called, "未确认身份时不应数星星/点技能行")
        self.assertFalse(solver.tap.called, "未确认身份时不应点技能选择按钮")

    def test_misjudged_skill_select_with_readable_countdown_exits(self):
        """未经身份确认的 219 即使倒计时「可读」也因未确认身份而保守退出。

        旧守卫靠"在 219 上读主面板倒计时/面板当探针"判占用（#69/B4）；#72 起 219
        不再读主面板区域，身份确认只认 TRAIN_MAIN 训练位校验这一步，与倒计时是否
        可读无关（#72 验收 2：219 分支不再读主面板区域当探针）。"""
        solver = self.make_solver(
            scene=Scene.TRAIN_SKILL_SELECT,
            execute_time=START + timedelta(hours=2),  # 旧守卫能读到未来倒计时
        )
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)

        idle_calls = [c for c in upd.call_args_list if c.args[1] == "idle"]
        self.assertTrue(idle_calls, "误判 219 应保持 idle 重排")
        self.assertTrue(solver.back.called, "应退出训练室")
        self.assertEqual(
            solver.tasks[0].time,
            START + mastery.ARRANGING_RETRY_BUFFER,
        )
        self.assertFalse(solver.ctap.called, "未确认身份时不应点技能行")
        self.assertFalse(solver.tap.called, "未确认身份时不应点技能选择按钮")

    # --- #70/B5：已到target档位读失败保守化 ---
    def test_unreadable_tier_no_blind_start(self):
        """经训练位确认进入真 219（身份已确认；TRAIN_MAIN 上的技能选择 tap 属正常导航），
        档位读失败（None，无法判是否已到 target）→ 保持 idle 重排退出，绝不点技能行。"""
        solver = self.make_solver(
            scenes=[
                Scene.TRAIN_MAIN,  # 读占用(无) → 读槽位(空) → back
                Scene.TRAIN_MAIN,  # 训练位已确认 → 点开技能选择页（身份确认）
                Scene.TRAIN_SKILL_SELECT,  # 读档位 → 失败（img=None）
            ]
        )
        solver.recog.img = None  # 档位读取失败
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)

        idle_calls = [c for c in upd.call_args_list if c.args[1] == "idle"]
        self.assertTrue(idle_calls, "档位不可读时应保持 idle 重排")
        self.assertTrue(solver.back.called, "应退出训练室")
        self.assertEqual(len(solver.tasks), 1, "应重排一条 SKILL_UPGRADE 任务")
        self.assertEqual(
            solver.tasks[0].time,
            START + mastery.ARRANGING_RETRY_BUFFER,
        )
        self.assertFalse(solver.ctap.called, "档位不可读时不应点技能行")

    def test_exit_occupied_recheck_task_labeled(self):
        """#153：_exit_occupied 的 plan_key=None 重检任务带描述性 meta_data
        （计划干员+技能+「占用中」），任务列表不再只显示类型名。"""
        solver = self.make_solver()
        plan = make_plan(char_name="测试干员", skill_name="测试技能")
        with patch("arknights_mower.utils.mastery_db.update_plan_status"):
            mastery._exit_occupied(solver, plan, None, trigger="档位读取失败")
        self.assertEqual(len(solver.tasks), 1)
        task = solver.tasks[0]
        self.assertIsNone(task.plan_key)
        self.assertEqual(task.meta_data, "测试干员（测试技能） 占用中")
        self.assertTrue(solver.back.called)

    def test_read_tier_zero_proceeds_to_start(self):
        """经训练位确认进入真 219，档位读到 0（明确低于 target）→ 正常开始流程
        （点技能行），不保守退出。"""
        solver = self.make_solver(
            scenes=[
                Scene.TRAIN_MAIN,
                Scene.TRAIN_MAIN,
                Scene.TRAIN_SKILL_SELECT,
            ]
        )
        # recog.img 为全零画布 → _read_slot_mastery_tier 返回 0（明确未专精）
        plan = make_plan(target_level=3)
        self.run_arranging(solver, plan, advance=timedelta(minutes=1))

        self.assertTrue(solver.ctap.called, "档位=0 明确低于 target 时应继续点技能行")

    def test_skill_select_tier_at_target_completes(self):
        """经训练位确认进入真 219，目标槽档位读到 ≥ target → 判 completed（#63/#67
        已到target检测），不重复开始训练。"""
        solver = self.make_solver(
            scenes=[
                Scene.TRAIN_MAIN,
                Scene.TRAIN_MAIN,
                Scene.TRAIN_SKILL_SELECT,
            ]
        )
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # 技能2（skill_index=1）三颗星全亮 → 档位 3 ≥ target 3
        for (x0, y0), (x1, y1) in mastery_reader.SKILL_SLOT_PIPS[1]:
            img[y0:y1, x0:x1] = 255
        solver.recog.img = img
        plan = make_plan(skill_index=1, target_level=3)
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan",
                return_value=None,
            ),
            patch("arknights_mower.utils.email.send_message"),
        ):
            mastery._start_new_training(solver, plan)

        completed_calls = [c for c in upd.call_args_list if c.args[1] == "completed"]
        self.assertTrue(completed_calls, "档位≥target 应判完成")
        self.assertTrue(solver.back.called, "完成后应退出训练室")
        self.assertFalse(solver.ctap.called, "已完成不应点技能行")

    # --- #69/B3：训练位坐错人 + 换人失败 → failed + 一次 ERROR 通知（全流程） ---
    def test_arranging_swap_failure_sends_error(self):
        """换人失败（choose_train 抛异常，含 D4 训练位锁定）→ 计划 failed + 一次 ERROR。"""

        def boom(*args, **kwargs):
            raise Exception("训练位被锁定，无法换入指定干员")

        solver = self.make_solver(
            scene=Scene.TRAIN_MAIN,
            slots=[{"agent": ""}, {"agent": "错误干员"}],
            choose_train=boom,
        )
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message") as send,
        ):
            mastery._start_new_training(solver, plan)

        failed_calls = [c for c in upd.call_args_list if c.args[1] == "failed"]
        self.assertTrue(failed_calls, "换人失败应标记 failed")
        self.assertTrue(solver.back.called, "失败后应退出训练室")
        self.assertTrue(
            any(c.kwargs.get("level") == "ERROR" for c in send.call_args_list),
            "换人失败应发一次 ERROR 通知",
        )

    # --- #69/B2：确认开始读到的面板与计划不符 → 计划 failed，绝不写 training ---
    def test_confirm_rejects_wrong_operator_panel(self):
        """确认时读到陌生干员的面板 → 不写 training，标记 failed + 一次 ERROR 通知。"""
        solver = self.make_solver(
            scene=Scene.TRAIN_MAIN,
            execute_time=START + timedelta(hours=2),
        )
        solver.read_screen.return_value = "[错误干员]其他技能"
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message") as send,
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )

        self.assertEqual(result, "failed")
        training_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        self.assertFalse(training_calls, "面板与计划不符时不得写 training")
        failed_calls = [c for c in upd.call_args_list if c.args[1] == "failed"]
        self.assertTrue(failed_calls, "应标记 failed")
        self.assertTrue(solver.back.called, "失败后应退出训练室")
        self.assertTrue(
            any(c.kwargs.get("level") == "ERROR" for c in send.call_args_list),
            "应发一次 ERROR 通知",
        )

    def test_confirm_unreadable_panel_does_not_write(self):
        """倒计时有效但面板干员名不可读（OCR 失败）→ 不写 training，直到超时。"""

        class _Advance(FixedDateTime):
            @classmethod
            def now(cls, tz=None):
                FixedDateTime.now_value += timedelta(minutes=1)
                if tz is not None:
                    return FixedDateTime.now_value.replace(tzinfo=tz)
                return FixedDateTime.now_value

        solver = self.make_solver(
            scene=Scene.TRAIN_MAIN,
            execute_time=START + timedelta(hours=2),
        )
        solver.read_screen.return_value = ""
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", _Advance),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )

        self.assertEqual(result, "timeout")
        training_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        self.assertFalse(training_calls, "面板不可读时不得把陌生人的倒计时写进计划")

    def test_arranging_no_wrong_start_on_mismatch(self):
        """#69/B2 全流程（#72 真实页面模型）：219 经训练位确认进入、不读面板文字，
        确认页读到陌生干员面板 → 计划 failed，绝不写 training。"""
        reads = iter([None, None, 7200])

        def fake_read(*args, **kwargs):
            return next(reads, 0)

        scenes = [
            Scene.TRAIN_MAIN,  # 读占用(无) → 读槽位(空) → back
            Scene.TRAIN_MAIN,  # tap 选择技能（身份确认）
            Scene.TRAIN_SKILL_SELECT,  # 读档位(0) → ctap 技能
            Scene.TRAIN_SKILL_UPGRADE,  # tap 确认 → 确认页读到陌生干员面板
        ]
        solver = self.make_solver(scenes=scenes, scene_fallback=Scene.TRAIN_MAIN)
        solver.read_time.side_effect = fake_read
        solver.read_screen.return_value = (
            "[错误干员]其他技能"  # 真 219 不读面板；确认页才读
        )
        plan = make_plan()
        _, upd = self.run_arranging(solver, plan)

        training_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        failed_calls = [c for c in upd.call_args_list if c.args[1] == "failed"]
        self.assertFalse(training_calls, "陌生干员面板下不得写 training")
        self.assertTrue(failed_calls, "应标记 failed")


class TestMasteryMailOperatorName(unittest.TestCase):
    """#53 根因3：邮件/日志文案用干员名（char_name，回退 get_char_name），不再用技能名/char_id。"""

    def setUp(self):
        FixedDateTime.now_value = START

    def make_solver(self, panel_text="[测试干员]测试技能"):
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = panel_text
        solver.tasks = []
        solver.task = None
        solver.recog.w = 1920
        solver.recog.h = 1080
        return solver

    def test_start_mail_uses_stored_char_name(self):
        solver = self.make_solver()
        plan = make_plan(char_name="测试干员")
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        msg = send.call_args[0][0]
        self.assertIn("测试干员", msg)
        self.assertNotIn("char_test", msg)

    def test_start_mail_falls_back_to_get_char_name(self):
        # 面板名用 char_id（char_name 为 NULL 时的匹配依据），邮件文案回退 get_char_name
        solver = self.make_solver(panel_text="[char_test]测试技能")
        plan = make_plan(char_name=None)
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
            patch.object(mastery, "get_char_name", return_value="兜底干员") as gcn,
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        self.assertIn("兜底干员", send.call_args[0][0])
        gcn.assert_called_once_with("char_test")


class TestPlanFailLabel(unittest.TestCase):
    """失败/超时邮件标签：技能真名 + 实际步级；步级未知不带档位（不用「技能序号 + 整体目标」。"""

    def test_uses_skill_name_and_actual_step(self):
        plan = make_plan(
            char_name="若叶睦", skill_name="二技能·破坏与滋养", target_level=3
        )
        self.assertEqual(
            mastery._plan_fail_label(plan, step_level=2), "若叶睦 二技能·破坏与滋养 专2"
        )

    def test_omits_tier_without_step(self):
        # 占用者非本计划干员 / 图标读失败 → 步级未知，不写档位（宁缺毋滥，不回退 target_level）
        plan = make_plan(
            char_name="若叶睦", skill_name="二技能·破坏与滋养", target_level=3
        )
        self.assertEqual(
            mastery._plan_fail_label(plan, step_level=None), "若叶睦 二技能·破坏与滋养"
        )

    def test_falls_back_to_skill_index_without_name(self):
        plan = make_plan(
            char_name="若叶睦", skill_name=None, skill_index=1, target_level=3
        )
        self.assertEqual(
            mastery._plan_fail_label(plan, step_level=2), "若叶睦 技能2 专2"
        )

    def test_exit_failed_email_uses_actual_step(self):
        solver = MagicMock()
        plan = make_plan(
            char_name="若叶睦", skill_name="二技能·破坏与滋养", target_level=3
        )
        with (
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
        ):
            mastery._exit_failed(
                solver, plan, "训练室面板干员/技能与计划不符，未开始训练", step_level=2
            )
        msg = send.call_args[0][0]
        self.assertIn("若叶睦 二技能·破坏与滋养 专2", msg)
        self.assertNotIn("技能2", msg)
        self.assertNotIn("专3", msg)

    def test_ownership_check_stranger_reports_occupier(self):
        """占用者非本计划干员（路人）：读图标档位进「实际占用」，不作计划步级。"""
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200  # 有倒计时
        solver.read_screen.return_value = "[路人干员]别的技能"  # 干员/技能都不匹配
        solver.recog.w = 1920
        solver.recog.h = 1080
        plan = make_plan(char_name="测试干员", skill_name="测试技能")
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_count_lit_mastery_icons", return_value=2) as cnt,
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "failed")
        cnt.assert_called_once()  # 路人档位也要读，供「实际占用」展示
        msg = send.call_args[0][0]
        self.assertIn("测试干员 测试技能", msg)  # 计划标签
        self.assertIn("路人干员（别的技能，专2）", msg)  # 实际占用
        self.assertNotIn("测试干员 测试技能 专", msg)  # 路人档位不作计划步级

    def test_ownership_check_own_operator_tier_is_plan_step(self):
        """占用者即本计划干员（仅技能不符）：档位作计划步级 + 实际占用都写。"""
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = (
            "[测试干员]一技能·多首野兽"  # 干员匹配、技能不符
        )
        solver.recog.w = 1920
        solver.recog.h = 1080
        plan = make_plan(char_name="测试干员", skill_name="测试技能")
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_count_lit_mastery_icons", return_value=2),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "failed")
        msg = send.call_args[0][0]
        self.assertIn("测试干员 测试技能 专2", msg)  # 档位作计划步级
        self.assertIn("测试干员（一技能·多首野兽，专2）", msg)

    def test_ownership_check_uses_scan_step_for_stranger(self):
        """扫描带的安排步级（专2）在路人占用时也报给用户：邮件=计划标签带专2 + 实际占用。"""
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = "[路人干员]别的技能"
        solver.recog.w = 1920
        solver.recog.h = 1080
        plan = make_plan(char_name="测试干员", skill_name="测试技能")
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_count_lit_mastery_icons", return_value=1),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10), True, step_level=2
            )
        self.assertEqual(result, "failed")
        msg = send.call_args[0][0]
        self.assertIn("测试干员 测试技能 专2", msg)  # 扫描步级=本次安排目标
        self.assertIn("路人干员（别的技能，专1）", msg)  # 实际占用（图标=1）


class TestStartTrainingMail(unittest.TestCase):
    """#90：开始训练邮件——协助位安排后重读倒计时再发；真名/目标级档位；两情况完成时间。

    邮件发送点从确认倒计时时刻移到协助位安排 + 换人判定之后（§16.10 第7步以当前读取
    为准）；档位 = 左下角专精图标读数（step_level，不加1）；真名 = plan["skill_name"]；
    完成时间：无减半 = 重读倒计时、有减半 = 换人任务时刻 + (300 + mastery_swap_buffer)。
    """

    def setUp(self):
        FixedDateTime.now_value = START

    def _solver(self):
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.tasks = []
        solver.task = None
        solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        solver.recog.update = MagicMock()
        return solver

    def _lit_solver(self, lit):
        solver = self._solver()
        solver.recog.img = _mastery_canvas(lit)
        return solver

    def test_mail_after_arrange_and_swap_uses_skill_name_and_step_tier(self):
        # 时机：协助位安排 → 换人判定 → 才发邮件；档位=图标读数（专二），真名=skill_name
        solver = self._lit_solver(lit=2)
        plan = make_plan(target_level=3)  # 专三计划，当前步=专二（图标亮2颗）
        order = []
        mail_msgs = []

        def fake_arrange(s, p, step_level=None):
            order.append("arrange")

        def fake_swap(s, p, execute_time, step_level=None):
            order.append("swap")
            return None

        def fake_send(msg, **kw):
            order.append("mail")
            mail_msgs.append(msg)

        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message", side_effect=fake_send),
            patch.object(mastery, "_arrange_support", side_effect=fake_arrange),
            patch.object(mastery, "_schedule_swap_if_needed", side_effect=fake_swap),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        self.assertEqual(
            order, ["arrange", "swap", "mail"], "邮件应在协助位安排+换人判定之后发"
        )
        msg = mail_msgs[0]
        self.assertIn("测试干员", msg)
        self.assertIn("测试技能", msg)  # 真名，不是「技能2」下标
        self.assertNotIn("技能2", msg)
        self.assertIn("专2", msg)  # 目标级 = 图标读数（专二），不是 plan target_level=3
        self.assertNotIn("专3", msg)
        self.assertIn("预计 14:00 完成", msg)  # 无减半 → 重读倒计时 START+2h

    def test_mail_swap_case_completion_uses_swap_time_plus_buffer(self):
        # 有减半：完成 = 换人任务时刻 + (300 + 缓冲) 分钟，附「将于 X 换入减半干员」；
        # 且排了换人则不排收取
        solver = self._lit_solver(lit=2)
        plan = make_plan()
        swap_time = START + timedelta(hours=1)
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=swap_time),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "efficiency": 75,
                    "mastery_swap_buffer": 10,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        sc.assert_not_called()  # 排了换人则不排收取
        msg = send.call_args.args[0]
        # 将于 swap_time 13:00 换入逻各斯；完成 = 13:00 + 310min → 18:10（300+缓冲=310）
        self.assertIn("将于 13:00 换入逻各斯", msg)
        self.assertIn("预计 18:10 完成", msg)

    def test_mail_rereads_countdown_after_arrange_for_swap_and_collect(self):
        # §16.10 第7步：协助位安排后重读倒计时，换人/收取/邮件完成时间都以此为准
        solver = self._lit_solver(lit=2)
        solver.read_time.side_effect = [7200, 5400]  # 初始 2h → 安排后 1.5h
        plan = make_plan()
        swap_calls = []
        collect_calls = []

        def fake_swap(s, p, execute_time, step_level=None):
            swap_calls.append(execute_time)
            return None

        def fake_collect(s, p, execute_time, tier=None):
            collect_calls.append(execute_time)

        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", side_effect=fake_swap),
            patch.object(mastery, "_schedule_collect", side_effect=fake_collect),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        expected = START + timedelta(seconds=5400)  # 12:00 + 1.5h = 13:30
        self.assertEqual(swap_calls, [expected], "换人判定用重读后的倒计时")
        self.assertEqual(collect_calls, [expected], "收取任务用重读后的倒计时")
        self.assertIn("预计 13:30 完成", send.call_args.args[0])
        # expires_at 也用换协助位后的最终倒计时（fresh≠安排前值 → 刷新一次 DB）
        expiry_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        self.assertEqual(len(expiry_calls), 2, "确认写一次 + 重读后刷新一次")
        self.assertEqual(
            expiry_calls[1].kwargs["expires_at"],
            expected.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def test_mail_falls_back_to_initial_countdown_when_reread_unreadable(self):
        # 重读失败（不在训练室主页面）→ 回退安排前倒计时，邮件仍发
        solver = self._lit_solver(lit=2)
        solver.train_scene.side_effect = [Scene.TRAIN_MAIN, Scene.INFRA_MAIN]
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        self.assertIn("预计 14:00 完成", send.call_args.args[0])  # 回退初始倒计时

    def test_mail_tier_unknown_when_icon_unreadable(self):
        # 档位（左下角专精图标）读不到 → 邮件显示「专精等级未知」，不回退 target_level
        solver = self._solver()  # 图标全灭 → step_level=0（读不到）
        plan = make_plan(target_level=3)
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        msg = send.call_args.args[0]
        self.assertIn("专精等级未知", msg)
        self.assertNotIn("专3", msg)
        self.assertNotIn("专2", msg)

    def test_re_read_closes_detail_window_and_reads(self):
        # 协助位安排后停在进驻详情浮窗 → 先关浮窗回主页面再读倒计时（点 arrange_check_in_on 关）
        solver = self._solver()
        solver.train_scene.side_effect = [Scene.INFRA_DETAILS, Scene.TRAIN_MAIN]
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            result = mastery._re_read_train_countdown(solver)
        self.assertEqual(result, START + timedelta(hours=2))
        # 205 放大视角关浮窗应点关闭按钮（arrange_check_in_on），不是 back（会退到基建）
        solver.find.assert_any_call("arrange_check_in_on")
        solver.tap.assert_called()
        solver.back.assert_not_called()  # 关掉进驻详情浮窗
        solver.read_time.assert_called_once()  # 关浮窗后重读倒计时

    def test_re_read_not_main_returns_none(self):
        # 不在训练室主页面 → None（调用方回退安排前倒计时）
        solver = self._solver()
        solver.train_scene.return_value = Scene.INFRA_MAIN
        self.assertIsNone(mastery._re_read_train_countdown(solver))


class TestSwapCollectGating(unittest.TestCase):
    """#73 §16.10：排了换人任务则不排收取；SWAP_SUPPORT 完成后重读倒计时再排收取。"""

    def setUp(self):
        FixedDateTime.now_value = START

    def _solver(self):
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.tasks = []
        solver.task = None
        solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        solver.recog.update = MagicMock()
        return solver

    def _swap_solver(self):
        """run_swap_support 用 solver：场景模拟 217 读槽位 → 浮窗 205 → 关回，后续回 217。

        #140：_read_slots_checked 读槽位前确认 217、读后确认浮窗开了（205）——测试 mock
        必须模拟 get_agent_from_room 开浮窗后场景变 205，否则读被判不可靠、换人分支不触发。
        """
        solver = self._solver()
        scenes = [
            Scene.TRAIN_MAIN,  # run_swap_support 场景检测（217）
            Scene.TRAIN_MAIN,  # 读槽位前置：主页面
            Scene.INFRA_DETAILS,  # 读槽位后：浮窗已开 → 关回
        ]

        def _scene():
            return scenes.pop(0) if scenes else Scene.TRAIN_MAIN

        solver.train_scene.side_effect = _scene
        return solver

    def _confirm(self, swap_scheduled, **kw):
        solver = self._solver()
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support"),
            patch.object(
                mastery,
                "_schedule_swap_if_needed",
                return_value=(START + timedelta(hours=1)) if swap_scheduled else None,
            ),
            patch.object(mastery, "_schedule_collect") as sc,
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        return result, sc

    def test_swap_scheduled_skips_collect(self):
        # §16.10：排了换人任务 → 不排收取（等 SWAP_SUPPORT 完成后重读倒计时再排收取）
        result, sc = self._confirm(swap_scheduled=True)
        self.assertEqual(result, "started")
        sc.assert_not_called()

    def test_no_swap_schedules_collect(self):
        result, sc = self._confirm(swap_scheduled=False)
        self.assertEqual(result, "started")
        sc.assert_called_once()

    def test_schedule_swap_immediate_schedules_now(self):
        # should_swap（remaining ≤ threshold）→ 立即排 SWAP_SUPPORT（修旧 silent-drop）
        solver = self._solver()
        plan = make_plan(target_level=2)
        with (
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 100,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "calc_swap_threshold", return_value=(True, 100.0)),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
        ):
            scheduled = mastery._schedule_swap_if_needed(
                solver, plan, START + timedelta(hours=2)
            )
        self.assertIsNotNone(scheduled, "立即换人应排 SWAP_SUPPORT")
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)

    def test_schedule_swap_delayed_returns_swap_time(self):
        solver = self._solver()
        plan = make_plan(target_level=2)
        with (
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "calc_swap_threshold", return_value=(False, 100.0)),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(mastery, "datetime", FixedDateTime),
        ):
            scheduled = mastery._schedule_swap_if_needed(
                solver, plan, START + timedelta(hours=2)
            )
        self.assertIsNotNone(scheduled)
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)

    def test_schedule_swap_step_unknown_falls_back_m3_skips(self):
        # #76：step_level 缺省（读不到）→ 回退 target_level=3 → level_3 路线无
        # swap_target → 不换人（保守，与旧行为一致）
        solver = self._solver()
        plan = make_plan(target_level=3)
        route_calls = []

        def fake_route(p, step_level=None):
            route_calls.append(step_level)
            return {
                "swap_target": None,
                "central_bonus": 5,
                "efficiency": 95,
                "job_match": True,
            }

        with (
            patch.object(mastery, "_get_plan_route", side_effect=fake_route),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
        ):
            scheduled = mastery._schedule_swap_if_needed(
                solver, plan, START + timedelta(hours=2)
            )
        self.assertIsNone(scheduled, "步级未知回退专三 → 不换人")
        self.assertEqual(route_calls, [None], "应把缺省 step_level 传给路线加载")

    def test_run_swap_support_schedules_collect_after_swap(self):
        # §16.10：SWAP_SUPPORT 完成后重读倒计时再排收取。倒计时得「值得换」
        # （换后真实 ≥ 301，read_time=15000→250 分钟）才会真正执行换人。
        solver = self._swap_solver()
        solver.read_time.return_value = 15000  # 250 分钟，换后真实 ≈ 330 分钟
        solver.get_agent_from_room.return_value = self._slots("夜半")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["逻各斯", "Current"])
        sc.assert_called_once()
        self.assertIsNotNone(
            sc.call_args.args[1], "换人后应排收取任务（重读倒计时时刻）"
        )

    def test_run_swap_support_unreadable_countdown_schedules_retry(self):
        solver = self._solver()
        solver.read_time.return_value = None  # 换人后倒计时读不到
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        sc.assert_called_once()
        self.assertEqual(
            sc.call_args.args[2],
            START + mastery.ARRANGING_RETRY_BUFFER,
            "倒计时读不到时保守重排到 now+2min",
        )

    def _fail_solver(self, read_seconds, task=None):
        """换人失败的 solver：choose_train 抛异常 + 指定倒计时读取。"""
        solver = self._swap_solver()
        solver.read_time.return_value = read_seconds
        solver.task = task
        solver.choose_train.side_effect = Exception("选人流程超时")
        # 协助位读可靠（reliable=True），did_swap 才触发——读失败不换（#117）
        solver.get_agent_from_room.return_value = self._slots("夜半")
        return solver

    def _swap_route(self):
        return {
            "swap_target": "逻各斯",
            "central_bonus": 5,
            "efficiency": 75,
            "job_match": True,
        }

    def _correction_route(self):
        return {
            "operator": "夜半",
            "swap_target": "逻各斯",
            "central_bonus": 5,
            "efficiency": 75,
            "job_match": True,
        }

    def _slots(self, support):
        return [{"agent": support}, {"agent": "能天使"}]

    def test_swap_support_corrects_stranger_slot(self):
        # #79：协助位是陌生人（非 operator 非 swap_target）→ 先纠错成 operator 再换人。
        # 倒计时得「值得换」（read_time=15000→250 分钟）才会换 swap_target。
        solver = self._swap_solver()
        solver.read_time.return_value = 15000  # 250 分钟，换后真实 ≈ 330 分钟
        solver.get_agent_from_room.return_value = self._slots("陌生人")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        calls = [c.args[0] for c in solver.choose_train.call_args_list]
        self.assertEqual(
            calls,
            [["夜半", "Current"], ["逻各斯", "Current"]],
            "陌生人 → 先纠错成 operator，再换入 swap_target",
        )
        upd.assert_called_once_with(1, "training", swap_frozen=1)
        sc.assert_called_once()

    def test_swap_support_protected_stranger_low_countdown_no_correction(self):
        # #107 保护门：逻各斯在协助位（非路线干员/减半对象）+ 剩余 < 5h+缓冲 →
        # 不纠不换，只排收取退出（不能落到 did_swap 用路线效率误判直接换减半）
        solver = self._solver()
        solver.read_time.return_value = 15000  # 250 分钟 < 310（300+缓冲10）
        solver.get_agent_from_room.return_value = self._slots("逻各斯")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        route = {
            "operator": "夜半",
            "swap_target": "缄默德克萨斯",
            "central_bonus": 5,
            "efficiency": 75,
            "job_match": True,
        }
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=route),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        upd.assert_not_called()
        sc.assert_called_once()
        solver.back.assert_called_once()

    def test_swap_support_protected_stranger_high_countdown_corrects(self):
        # #107 保护门：逻各斯在协助位 + 剩余 ≥ 5h+缓冲 → 照常纠成路线人再换减半对象
        solver = self._swap_solver()
        solver.read_time.return_value = 23400  # 390 分钟 ≥ 310
        solver.get_agent_from_room.return_value = self._slots("逻各斯")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        route = {
            "operator": "夜半",
            "swap_target": "缄默德克萨斯",
            "central_bonus": 5,
            "efficiency": 75,
            "job_match": True,
        }
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=route),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        calls = [c.args[0] for c in solver.choose_train.call_args_list]
        self.assertEqual(
            calls,
            [["夜半", "Current"], ["缄默德克萨斯", "Current"]],
            "剩余足够 → 先纠成路线人，再换入减半对象",
        )
        upd.assert_called_once_with(1, "training", swap_frozen=1)
        sc.assert_called_once()

    def test_swap_support_unreliable_read_no_swap(self):
        # #107/#117：读协助位失败（reliable=False）→ 不盲目换人（槽位未知，可能坐着
        # 受保护干员或已减半对象）——did_swap 需 reliable，「稳为先：读不到就不动」，
        # 只排收取退出
        solver = self._solver()
        solver.read_time.return_value = 15000  # 250 分钟 < 310
        solver.get_agent_from_room.side_effect = RuntimeError("OCR fail")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        route = {
            "operator": "夜半",
            "swap_target": "缄默德克萨斯",
            "central_bonus": 5,
            "efficiency": 75,
            "job_match": True,
        }
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=route),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        upd.assert_not_called()
        sc.assert_called_once()
        solver.back.assert_called_once()

    def test_swap_support_empty_slot_places_swap_target_directly(self):
        # #101：空位 + calc_swap_threshold(0,...) 的 should_swap（含 301 值得门）= True
        # → 直接放 swap_target，不先放 operator 再立刻换（不白放、不走 did_swap 绕过阈值）
        solver = self._swap_solver()
        solver.read_time.return_value = 24300  # 405 分钟 ∈ [401, 413] 值得窗
        solver.get_agent_from_room.return_value = self._slots("")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["逻各斯", "Current"])
        upd.assert_called_once_with(1, "training", swap_frozen=1)
        sc.assert_called_once()
        solver.back.assert_not_called()

    def test_swap_support_empty_slot_not_worthwhile_places_operator(self):
        # #101 review 修复：空位 + remaining<=threshold 但 should_swap=False（301 值得门
        # 不满足，swap_target 速率 ≤ operator）→ 不放 swap_target、补 operator + 重排阈值
        solver = self._swap_solver()
        solver.read_time.return_value = 15000  # 250 分钟 ≤ 阈值≈413 但值得门不满足
        solver.get_agent_from_room.return_value = self._slots("")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(
                mastery,
                "_schedule_swap_if_needed",
                return_value=START + timedelta(hours=1),
            ) as sched,
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["夜半", "Current"])
        upd.assert_not_called()  # 不置 swap_frozen
        sched.assert_called_once()  # 重排阈值时刻换人任务
        sc.assert_not_called()
        solver.back.assert_called_once()

    def test_swap_support_empty_slot_reread_failure_rearms_halving(self):
        # #101 review 修复：补位后重读面板失败（倒计时读不到）→ 轻量重试读成功 → 重排
        # 阈值任务（防合并后阈值任务被本 dispatch 消费、只排收取丢减半）
        solver = self._swap_solver()
        solver.read_time.side_effect = [
            None,
            None,
            15000,
        ]  # 初读失败→补位→重读失败→重试成功
        solver.get_agent_from_room.return_value = self._slots("")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(
                mastery,
                "_schedule_swap_if_needed",
                return_value=START + timedelta(hours=1),
            ) as sched,
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["夜半", "Current"])
        upd.assert_not_called()
        sched.assert_called_once()  # 重试读到倒计时 → 重排阈值任务
        sc.assert_not_called()  # 已排换人 → 不排收取
        solver.back.assert_called_once()

    def test_swap_support_empty_slot_places_operator_no_immediate_swap(self):
        # #101：空位 + 剩余 > 阈值 → 放 operator（拿前半程加成），**不立刻换**——
        # 重排阈值时刻换人任务（阈值时机不丢），不再 did_swap 绕过阈值
        solver = self._swap_solver()
        solver.read_time.return_value = 30000  # 500 分钟 > 阈值 ≈413（效率0）
        solver.get_agent_from_room.return_value = self._slots("")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(
                mastery,
                "_schedule_swap_if_needed",
                return_value=START + timedelta(hours=1),
            ) as sched,
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["夜半", "Current"])
        upd.assert_not_called()  # 不立刻换 → 不置 swap_frozen
        sched.assert_called_once()  # 重排阈值时刻换人任务
        sc.assert_not_called()  # 排了换人 → 不排收取
        solver.back.assert_called_once()

    def test_swap_support_empty_slot_countdown_failed_places_operator(self):
        # #101 验收：倒计时读失败（failed）→ 保守补 operator（不判 S/E）；重读仍失败 →
        # 保守排收取退出（00:00:00 zero 才不动，failed 仍补）
        solver = self._swap_solver()
        solver.read_time.return_value = None  # 倒计时读失败
        solver.get_agent_from_room.return_value = self._slots("")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["夜半", "Current"])
        upd.assert_not_called()  # 不判减半 → 不置 swap_frozen
        solver.back.assert_called_once()
        sc.assert_called_once()  # 保守排收取（下次进房再读）

    def test_swap_support_empty_fill_failure_swap_still_happens(self):
        # #100 review 修复（major：补位失败不阻塞减半）：空位放 operator 失败 → 直接
        # 尝试换入 swap_target（减半收益不丢）
        solver = self._swap_solver()
        solver.read_time.return_value = 30000  # 500 分钟 > 阈值 → 放 operator
        solver.get_agent_from_room.return_value = self._slots("")
        solver.choose_train.side_effect = [
            Exception("选人流程超时"),
            None,
        ]  # 补位失败→换人成功
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(mastery, "_notify_swap_correction_failed") as notify,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        calls = [c.args[0] for c in solver.choose_train.call_args_list]
        self.assertEqual(
            calls,
            [["夜半", "Current"], ["逻各斯", "Current"]],
            "补位失败后仍直接换入 swap_target（减半收益不丢）",
        )
        notify.assert_called_once()
        self.assertTrue(
            notify.call_args.kwargs.get("fallback_swap", False),
            "空位补位失败文案应如实说「将尝试直接换入减半对象」而非「跳过减半」",
        )
        upd.assert_called_once_with(1, "training", swap_frozen=1)
        sc.assert_called_once()

    def test_swap_support_zero_countdown_no_fill(self):
        # #100 review 修复（minor：00:00:00 收取边界不动协助位，铁律 6）：空位也不补、
        # 不纠错，只排收取退出
        solver = self._solver()
        solver.read_time.return_value = 0  # 00:00:00
        solver.get_agent_from_room.return_value = self._slots("")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()  # 00:00:00 不补位、不纠错
        solver.back.assert_called_once()
        sc.assert_called_once()

    def test_swap_support_correction_not_worthwhile_no_swap(self):
        # #80 acceptance 2：时间不足（换后真实 < 301）的步，纠错只纠成 operator，
        # **不触发不该发生的减半换人**（只排收取退出）
        solver = self._swap_solver()
        solver.read_time.return_value = 3600  # 60 分钟，换后真实 ≈ 79 分钟
        solver.get_agent_from_room.return_value = self._slots("陌生人")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(
            ["夜半", "Current"]
        )  # 只纠错，不换人
        upd.assert_not_called()  # 不置 swap_frozen
        solver.back.assert_called_once()  # 排收取后退出
        sc.assert_called_once()

    def test_swap_support_already_swap_target_no_swap(self):
        # #79：协助位已是 swap_target（已减半）→ 不再换、不置 swap_frozen
        solver = self._solver()
        solver.get_agent_from_room.return_value = self._slots("逻各斯")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        solver.back.assert_called_once()
        sc.assert_called_once()

    def test_swap_support_correction_failure_notifies(self):
        # #79：纠错失败 → 邮件通知 + 不换人 + 排收取退出
        solver = self._swap_solver()
        solver.get_agent_from_room.return_value = self._slots("陌生人")
        solver.choose_train.side_effect = Exception("选人流程超时")
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery, "_get_plan_route", return_value=self._correction_route()
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(mastery, "_notify_swap_correction_failed") as notify,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(
            ["夜半", "Current"]
        )  # 只纠错一次，不换人
        notify.assert_called_once()
        solver.back.assert_called_once()
        sc.assert_called_once()  # 收集仍保证

    def test_swap_failure_retries_in_place_then_gives_up(self):
        # #81：换人失败立刻原地重试（无 +5min 间隔、不排新任务），5 次仍失败 → 放弃
        # + ⑧ 通知，不置 swap_frozen（接受下次进房重排，暂时性失败可被救回）
        solver = self._fail_solver(read_seconds=15000)  # 250 分钟，换后真实 ≈ 330 分钟
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=self._swap_route()),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(mastery, "_notify_swap_giveup") as notify,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        self.assertEqual(
            solver.choose_train.call_count,
            1 + mastery.SWAP_RETRY_LIMIT,
            "首次失败 + 5 次原地重试",
        )
        self.assertFalse(
            [t for t in solver.tasks if t.type == TaskTypes.SWAP_SUPPORT],
            "不再重排 SWAP 任务（原地重试）",
        )
        notify.assert_called_once()
        upd.assert_not_called()  # 放弃不置 swap_frozen=1
        sc.assert_called_once()  # 收集任务仍保证

    def test_swap_not_worthwhile_skips_attempt(self):
        # #80 worth 门：派发时换后真实 < 301（不足 5 小时）→ 连尝试都不做，直接跳过换人
        # + 排收取退出（不通知⑧——这不是「重试后放弃」，而是调度前就判不值）
        solver = self._fail_solver(read_seconds=3600)  # 60 分钟，换后真实 ≈ 79 分钟
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=self._swap_route()),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(mastery, "_notify_swap_giveup") as notify,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()  # worth 门：不尝试换人
        notify.assert_not_called()
        upd.assert_not_called()
        solver.back.assert_called_once()
        sc.assert_called_once()

    def test_retry_in_place_not_worthwhile_gives_up(self):
        # #81：重试期间倒计时降到不足 5 小时 → 放弃 + ⑧ 通知，返回 False（不退出房间标记）
        solver = MagicMock()
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch.object(mastery, "_swap_still_worthwhile", return_value=False),
            patch.object(mastery, "_notify_swap_giveup") as notify,
            patch.object(mastery, "_try_swap") as ts,
        ):
            ok = mastery._retry_swap_in_place(
                solver, plan, self._swap_route(), "逻各斯"
            )
        self.assertFalse(ok)
        notify.assert_called_once()
        ts.assert_not_called()

    def test_swap_retry_succeeds_marks_frozen(self):
        # 暂时性失败可被救回：首次失败、重试成功 → swap_frozen=1，不通知
        solver = self._swap_solver()
        solver.read_time.return_value = 15000
        solver.get_agent_from_room.return_value = self._slots("夜半")
        attempts = {"n": 0}

        def flaky(*args, **kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise Exception("选人流程超时")

        solver.choose_train.side_effect = flaky
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=self._swap_route()),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(mastery, "_notify_swap_giveup") as notify,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        self.assertEqual(solver.choose_train.call_count, 2, "首次失败 + 重试成功")
        upd.assert_any_call(1, "training", swap_frozen=1)
        notify.assert_not_called()
        solver.back.assert_not_called()  # 重试成功与首试成功一致：不退出房间
        sc.assert_called_once()

    def test_swap_giveup_notifies_no_frozen(self):
        # #81：放弃发⑧ 通知（去重按 plan id，WARNING），不置 swap_frozen=1
        solver = self._fail_solver(read_seconds=15000)
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch.object(mastery, "_get_plan_route", return_value=self._swap_route()),
            patch.object(mastery, "_schedule_collect") as sc,
            patch(
                "arknights_mower.utils.mastery_db.should_notify", return_value=True
            ) as sn,
            patch("arknights_mower.utils.email.send_message") as send,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        sn.assert_called_once_with("swap_failed_giveup", str(plan["id"]))
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["level"], "WARNING")
        self.assertIn("换人失败已放弃", send.call_args.args[0])
        upd.assert_not_called()
        self.assertFalse(
            [t for t in solver.tasks if t.type == TaskTypes.SWAP_SUPPORT],
            "放弃后不排 SWAP",
        )
        sc.assert_called_once()

    def test_schedule_swap_task_carries_plan_key(self):
        # #77 补排去重键：SWAP 任务带 plan_key=计划ID（与 SKILL_UPGRADE 同形），
        # reconcile 恢复（_maybe_recover_swap）按它去重，不重复补排
        solver = self._solver()
        plan = make_plan(target_level=2)
        with (
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 100,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "calc_swap_threshold", return_value=(True, 100.0)),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
        ):
            scheduled = mastery._schedule_swap_if_needed(
                solver, plan, START + timedelta(hours=2)
            )
        self.assertIsNotNone(scheduled)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)
        self.assertEqual(solver.tasks[0].plan_key, str(plan["id"]))

    def test_schedule_collect_after_swap_closes_detail_before_read(self):
        # 读倒计时前若停在主页面带进驻详情浮窗（INFRA_DETAILS）→ 先关浮窗回主页面再读
        solver = self._swap_solver()
        solver.read_time.return_value = (
            15000  # 250 分钟，值得换（否则 worth 门跳过换人）
        )
        solver.get_agent_from_room.return_value = self._slots("夜半")
        solver.train_scene.side_effect = [
            Scene.INFRA_DETAILS,  # run_swap_support 场景检测：浮窗开着 → 先关回 217
            Scene.TRAIN_MAIN,
            Scene.TRAIN_MAIN,  # 读槽位前置：主页面
            Scene.INFRA_DETAILS,  # 读槽位后：浮窗已开 → 关回
        ]
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(mastery, "_get_plan_route", return_value=self._swap_route()),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        # 205 放大视角关浮窗应点关闭按钮（arrange_check_in_on），不是 back（会退到基建）
        solver.find.assert_any_call("arrange_check_in_on")
        solver.tap.assert_called()
        solver.back.assert_not_called()  # 关掉进驻详情浮窗
        sc.assert_called_once()


class TestRouteStepLevel(unittest.TestCase):
    """#76：路线按当前步目标级加载——专三计划专一/专二步用 level_1/2 路线减半换人。

    主面板专精图标在训练中 = 当前步目标级（亮 N 颗=专N），与 _schedule_collect 同源。
    """

    def setUp(self):
        FixedDateTime.now_value = START

    def _solver(self):
        solver = MagicMock()
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.tasks = []
        solver.task = None
        solver.recog.img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        solver.recog.update = MagicMock()
        return solver

    def _lit_solver(self, lit):
        solver = self._solver()
        solver.recog.img = _mastery_canvas(lit)
        return solver

    # --- _get_plan_route：step_level 优先，读不到（None/0）回退 target_level ---
    def test_get_plan_route_uses_step_level(self):
        plan = make_plan(target_level=3)
        calls = []
        with (
            patch(
                "arknights_mower.utils.mastery_recommendation.get_skill_data",
                return_value={
                    "characters": {"char_test": {"profession": "WARRIOR"}},
                },
            ),
            patch.object(
                mastery,
                "get_route_config",
                side_effect=lambda prof, level: calls.append((prof, level)) or {},
            ),
        ):
            mastery._get_plan_route(plan, step_level=1)
            mastery._get_plan_route(plan)
            mastery._get_plan_route(plan, step_level=0)
            # target_level=2 单步计划：step_level 缺省回退 target_level=2 → 行为不变（回归）
            mastery._get_plan_route(make_plan(target_level=2))
        self.assertEqual(
            calls,
            [("近卫", 1), ("近卫", 3), ("近卫", 3), ("近卫", 2)],
            "step_level=1 用专一路线；缺省/0 回退整体目标；target_level=2 回退专二",
        )

    # --- _schedule_swap_if_needed：专三计划专一/专二步换人，专三步不换 ---
    def test_schedule_swap_m3_plan_m1_step_schedules(self):
        solver = self._solver()
        plan = make_plan(target_level=3)
        route_calls = []

        def fake_route(p, step_level=None):
            route_calls.append(step_level)
            return {
                "swap_target": "艾丽妮",
                "central_bonus": 5,
                "efficiency": 75,
                "job_match": True,
            }

        with (
            patch.object(mastery, "_get_plan_route", side_effect=fake_route),
            patch.object(mastery, "calc_swap_threshold", return_value=(False, 100.0)),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(mastery, "datetime", FixedDateTime),
        ):
            scheduled = mastery._schedule_swap_if_needed(
                solver, plan, START + timedelta(hours=2), step_level=1
            )
        self.assertIsNotNone(scheduled, "专三计划专一步应减半换人")
        self.assertEqual(route_calls, [1], "路线应按当前步级（专一）加载")
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)

    def test_schedule_swap_m3_step_skips_via_route(self):
        solver = self._solver()
        plan = make_plan(target_level=3)
        with (
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": None,
                    "central_bonus": 5,
                    "efficiency": 95,
                    "job_match": True,
                },
            ),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
        ):
            scheduled = mastery._schedule_swap_if_needed(
                solver, plan, START + timedelta(hours=2), step_level=3
            )
        self.assertIsNone(scheduled, "专三步路线无 swap_target → 不换人")

    # --- _confirm_training_started：确认后读图标当前步级，传给协助位/换人安排 ---
    def test_confirm_passes_step_level_to_arrange_and_swap(self):
        solver = self._lit_solver(lit=2)
        plan = make_plan()
        arrange_calls = []
        swap_calls = []

        def fake_arrange(s, p, step_level=None):
            arrange_calls.append(step_level)

        def fake_swap(s, p, execute_time, step_level=None):
            swap_calls.append(step_level)
            return None

        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support", side_effect=fake_arrange),
            patch.object(mastery, "_schedule_swap_if_needed", side_effect=fake_swap),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        self.assertEqual(arrange_calls, [2], "协助位安排应按图标当前步级（专二）")
        self.assertEqual(swap_calls, [2], "换人判断应按图标当前步级（专二）")

    def test_confirm_backs_out_of_skill_select_before_reading(self):
        # #89：确认后的 219 是真技能选择页（读不出倒计时）。必须先在 219 上 back 回
        # 主页面（217）再读倒计时/图标——绝不能直接在 219 上读倒计时（左下角是协助位
        # 天赋文本，会被 OCR 当倒计时反复读，甚至偶然读出类时间文本 → 假确认开始）。
        solver = self._lit_solver(lit=2)
        solver.train_scene.side_effect = [
            Scene.TRAIN_SKILL_SELECT,  # 确认后自动退回技能选择页 → back
            Scene.TRAIN_MAIN,  # back 回主页面 → 读倒计时/图标
        ]
        plan = make_plan()
        swap_calls = []

        def fake_swap(s, p, execute_time, step_level=None):
            swap_calls.append(step_level)
            return None

        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", side_effect=fake_swap),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        solver.back.assert_called_once()
        # 219 上必须先 back 再读倒计时（read_time），杜绝假确认风险
        call_names = [c[0] for c in solver.method_calls]
        self.assertLess(call_names.index("back"), call_names.index("read_time"))
        self.assertEqual(
            swap_calls, [2], "back 回主页面后按图标当前步级（专二）换人判断"
        )

    def test_confirm_does_not_double_back_on_persistent_219(self):
        # #89 review：219 back 后若仍被读成 219（动画/识别抖动）→ 只 back 一次、
        # 不连发 BACK（否则会把已在主页面 217 的误读成 219 而误退训练室 → 超时假失败）。
        solver = self._lit_solver(lit=2)
        solver.train_scene.side_effect = [
            Scene.TRAIN_SKILL_SELECT,
            Scene.TRAIN_SKILL_SELECT,  # back 后仍读到 219 → 不再 back
            Scene.TRAIN_MAIN,  # 稳定回主页面 → 读倒计时/图标
        ]
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support"),
            patch.object(mastery, "_schedule_swap_if_needed", return_value=None),
            patch.object(mastery, "_schedule_collect"),
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        solver.back.assert_called_once()

    def test_arrange_support_uses_step_level_route(self):
        # 近卫 level_1 路线：协助位=赤冬。专三计划专一步按当前步级安排协助位。
        solver = self._solver()
        plan = make_plan(target_level=3)
        route_calls = []
        with (
            patch.object(
                mastery,
                "_get_plan_route",
                side_effect=lambda p, step_level=None: (
                    route_calls.append(step_level)
                    or {
                        "operator": "赤冬",
                        "efficiency": 75,
                        "job_match": True,
                        "swap_target": "艾丽妮",
                    }
                ),
            ),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
        ):
            mastery._arrange_support(solver, plan, step_level=1)
        solver.choose_train.assert_called_once_with(["赤冬", "Current"])
        self.assertEqual(route_calls, [1], "协助位路线按当前步级（专一）加载")

    # --- run_swap_support：倒计时门 + 进房读图标得当前步级，按步级路线换人 ---
    def test_run_swap_support_m3_plan_m2_step_swaps(self):
        # 专三计划专二步：倒计时 active + 主面板亮 2 颗 → 路线按 step_level=2 → 减半换人
        solver = self._lit_solver(lit=2)
        solver.train_scene.side_effect = [
            Scene.TRAIN_MAIN,  # run_swap_support 场景检测
            Scene.TRAIN_MAIN,  # 读槽位前置：主页面
            Scene.INFRA_DETAILS,  # 读槽位后：浮窗已开 → 关回
        ]
        solver.read_time.return_value = 15000  # 250 分钟，值得换（否则 worth 门跳过）
        solver.get_agent_from_room.return_value = [
            {"agent": "夜半"},
            {"agent": "能天使"},
        ]
        plan = make_plan(status="training", swap_frozen=0, target_level=3)
        route_calls = []
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                side_effect=lambda p, step_level=None: (
                    route_calls.append(step_level)
                    or {
                        "swap_target": "艾丽妮",
                        "central_bonus": 5,
                        "efficiency": 75,
                        "job_match": True,
                    }
                ),
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["艾丽妮", "Current"])
        self.assertEqual(route_calls, [2], "run_swap_support 应进房读图标得当前步级")
        sc.assert_called_once()
        self.assertEqual(
            sc.call_args.kwargs.get("tier"),
            2,
            "#150 收取任务档位标签用实际步级（panel.mastery_tier），不恒为专三",
        )

    def test_run_swap_support_m3_step_no_swap(self):
        # 专三步：倒计时 active + 主面板亮 3 颗 → level_3 路线无 swap_target → 不换人、退出房间
        solver = self._lit_solver(lit=3)
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 7200  # 倒计时 active（非0非空）
        plan = make_plan(status="training", swap_frozen=0, target_level=3)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": None,
                    "central_bonus": 5,
                    "efficiency": 95,
                    "job_match": True,
                },
            ),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        solver.back.assert_called_once()

    def test_run_swap_support_skill_select_scene_no_swap(self):
        # #78 整合：219=技能选择页读不出倒计时，场景门只放行 TRAIN_MAIN——219 不再换人
        solver = self._lit_solver(lit=2)
        solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
        solver.read_time.return_value = 7200
        plan = make_plan(status="training", swap_frozen=0, target_level=3)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "艾丽妮",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        solver.back.assert_called_once()
        sc.assert_called_once()  # 跳过换人也补排收取

    def test_run_swap_support_zero_countdown_no_swap(self):
        # 倒计时 00:00:00（待收取，zero）→ 不算训练确认，不换人
        solver = self._lit_solver(lit=2)
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 0  # zero
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        solver.back.assert_called_once()
        sc.assert_called_once()  # 收取仍保证

    def test_run_swap_support_unreadable_countdown_no_swap(self):
        # 倒计时读失败（failed，DB 过期/空房）→ 不算训练确认，不换人
        solver = self._lit_solver(lit=2)
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = None  # failed
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(mastery, "datetime", FixedDateTime),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        solver.back.assert_called_once()
        sc.assert_called_once()  # 收取仍保证
        self.assertEqual(
            sc.call_args.args[2],
            START + mastery.ARRANGING_RETRY_BUFFER,
            "倒计时读不到时保守重排到 now+2min",
        )

    def test_run_swap_support_not_main_scene_skips(self):
        # 进房后不在训练主页面（已完成页 TRAIN_FINISH）→ 图标不可靠，不换人、
        # 补排收取（§16.10）、退出房间
        solver = self._solver()
        solver.train_scene.return_value = Scene.TRAIN_FINISH
        plan = make_plan(status="training", swap_frozen=0, target_level=2)
        with (
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=plan
            ),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch.object(
                mastery,
                "_get_plan_route",
                return_value={
                    "swap_target": "逻各斯",
                    "central_bonus": 5,
                    "efficiency": 75,
                    "job_match": True,
                },
            ),
            patch.object(mastery, "_schedule_collect") as sc,
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_not_called()
        solver.back.assert_called_once()
        sc.assert_called_once()  # 跳过换人也补排收取


class TestAtTargetNotifyAndMaterialGate(unittest.TestCase):
    """#73 §16.9 ⑥ 已到target 通知；完成不级联开始下一个计划（#74 第2段）。"""

    def setUp(self):
        FixedDateTime.now_value = START

    def _lit_solver(self):
        solver = MagicMock()
        solver.train_scene.side_effect = [
            Scene.TRAIN_MAIN,  # 读占用(无) → 读槽位(空) → back
            Scene.TRAIN_MAIN,  # tap 选择技能（身份确认）
            Scene.TRAIN_SKILL_SELECT,  # 读档位 → 3（已到target）
        ]
        solver.read_time.return_value = None
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.get_agent_from_room.return_value = [{"agent": ""}, {"agent": ""}]
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.tasks = []
        solver.task = None
        solver.recog.update = MagicMock()
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for (x0, y0), (x1, y1) in mastery_reader.SKILL_SLOT_PIPS[1]:
            img[y0:y1, x0:x1] = 255
        solver.recog.img = img
        return solver

    def test_at_target_notifies_06(self):
        # 已到target（专3）→ 邮件⑥ + DB 标完成
        solver = self._lit_solver()
        plan = make_plan(skill_index=1, target_level=3)
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch(
                "arknights_mower.utils.mastery_db.get_next_idle_plan", return_value=None
            ),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_notify_at_target") as nat,
        ):
            mastery._start_new_training(solver, plan)
        nat.assert_called_once()
        statuses = [c.args[1] for c in upd.call_args_list]
        self.assertIn("completed", statuses)

    def test_at_target_completes_no_cascade(self):
        # #74 第2段：已到target 完成 → 只 completed + 退出，不再级联开始下一个 idle 计划
        solver = MagicMock()
        scenes = iter(
            [
                Scene.TRAIN_MAIN,  # 读占用(无) → 槽位 → back
                Scene.TRAIN_MAIN,  # tap 技能选择（身份确认）
                Scene.TRAIN_SKILL_SELECT,  # 读档位 → 3（已到target → 完成 → 退出）
            ]
        )
        solver.train_scene.side_effect = lambda: next(scenes, Scene.TRAIN_MAIN)
        reads = iter([None, None, None])  # 倒计时均为空（已到target，无占用）
        solver.read_time.side_effect = lambda *a, **k: next(reads, None)
        solver.read_screen.return_value = "[测试干员]测试技能"
        solver.get_agent_from_room.return_value = [{"agent": ""}, {"agent": ""}]
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.tasks = []
        solver.task = None
        solver.recog.update = MagicMock()
        img = np.zeros((1080, 1920, 3), dtype=np.uint8)
        for (x0, y0), (x1, y1) in mastery_reader.SKILL_SLOT_PIPS[1]:
            img[y0:y1, x0:x1] = 255
        solver.recog.img = img
        plan = make_plan(skill_index=1, target_level=3)
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.mastery_db.get_next_idle_plan") as g,
            patch("arknights_mower.utils.email.send_message"),
        ):
            mastery._start_new_training(solver, plan)
        g.assert_not_called()
        statuses = [c.args[1] for c in upd.call_args_list]
        arranging_ids = [
            c.args[0] for c in upd.call_args_list if c.args[1] == "arranging"
        ]
        self.assertIn("completed", statuses)
        self.assertEqual(
            arranging_ids,
            [1],
            "已到target 完成不再级联开始下一个计划（仅本级 arranging）",
        )
        self.assertTrue(solver.back.called, "完成后应退出训练室")


class TestStartWithReconciledRoom(unittest.TestCase):
    """#93：dispatch 已由 reconcile_and_act 进房读完全部状态（room），开始流程直接复用——

    不再重复 enter_room、不再开进驻详情浮窗重读槽位（消除重复进房与重复浮窗开关）。
    room.train_slot 为空串时无法区分「真空」与「读浮窗失败」——重读一次兜底（读失败恢复
    「空闲但训练位坐错人」换人校验、真空重读仍空无害）。
    """

    def setUp(self):
        FixedDateTime.now_value = START

    def _solver(self, scenes, slots=None):
        solver = MagicMock()
        it = iter(scenes)
        solver.train_scene.side_effect = lambda: next(it, Scene.TRAIN_MAIN)
        solver.read_time.return_value = None  # 无倒计时（空房）
        solver.read_screen.return_value = "[测试干员]测试技能"
        if slots is not None:
            solver.get_agent_from_room.return_value = slots
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.recog.update = MagicMock()
        solver.recog.img = None  # 技能页档位读失败 → 保守退出（干净收尾）
        solver.tasks = []
        solver.task = None
        return solver

    def _run(self, solver, plan, room):
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message"),
        ):
            mastery._start_new_training(solver, plan, room=room)
        return solver, upd

    def test_reuses_room_slot_skips_reentry_and_slot_read(self):
        scenes = [
            Scene.TRAIN_MAIN,  # 读倒计时(无) → 复用 room.train_slot（==计划干员，不换）→ continue
            Scene.TRAIN_MAIN,  # 训练位已确认 → 点开技能选择页
            Scene.TRAIN_SKILL_SELECT,  # 读档位(None) → 档位读取失败保守退出
        ]
        solver = self._solver(scenes)
        room = mastery_reader.RoomState("empty", train_slot="测试干员")
        plan = make_plan()
        _, upd = self._run(solver, plan, room)

        solver.enter_room.assert_not_called()
        solver.get_agent_from_room.assert_not_called()
        solver.choose_train.assert_not_called()
        statuses = [c.args[1] for c in upd.call_args_list]
        self.assertIn("idle", statuses, "档位读取失败 → 保持 idle 重排退出")

    def test_wrong_room_train_slot_swaps_without_reentry(self):
        # 真实流：choose_train 换完训练位后停在进驻详情浮窗（INFRA_DETAILS），循环里
        # back() 关浮窗回 TRAIN_MAIN 再点技能——测试建模这个中间场景（#93 对抗 review）。
        scenes = [
            Scene.TRAIN_MAIN,  # 读倒计时(无) → 复用 room.train_slot=错误干员 → 换人
            Scene.INFRA_DETAILS,  # choose_train 后浮窗开着 → 循环 back() 关闭
            Scene.TRAIN_MAIN,  # 训练位已确认 → 点开技能选择页
            Scene.TRAIN_SKILL_SELECT,  # 读档位(None) → 保守退出
        ]
        solver = self._solver(scenes)
        room = mastery_reader.RoomState("empty", train_slot="错误干员")
        plan = make_plan()
        self._run(solver, plan, room)

        solver.choose_train.assert_called_once_with(["Current", "测试干员"])
        solver.enter_room.assert_not_called()
        solver.get_agent_from_room.assert_not_called()

    def test_unread_room_slots_fall_back_to_fresh_read(self):
        # room.train_slot 空串（读浮窗失败 / 真空）无法区分 → 重读一次兜底：保持旧
        # 「开始时刻第二次读」的换人校验，不因复用 room 静默丢掉。重读路径自己 back()
        # 关浮窗，换人后停在 TRAIN_MAIN。
        scenes = [
            Scene.TRAIN_MAIN,  # 读倒计时(无) → room.train_slot=空 → 重读(错误干员) → 换人 → back 关浮窗
            Scene.TRAIN_MAIN,  # 训练位已确认 → 点开技能选择页
            Scene.TRAIN_SKILL_SELECT,  # 读档位(None) → 保守退出
        ]
        solver = self._solver(scenes, slots=[{"agent": ""}, {"agent": "错误干员"}])
        room = mastery_reader.RoomState("empty")  # train_slot 空串 → 触发重读
        plan = make_plan()
        self._run(solver, plan, room)

        solver.get_agent_from_room.assert_called()  # 空串 → 重读一次兜底
        solver.choose_train.assert_called_once_with(["Current", "测试干员"])
        solver.enter_room.assert_not_called()  # 仍不重复进房（room 非 None）

    def test_collect_continue_room_reused_through_dispatch(self):
        """#93 主场景接线：run_mastery_task → 真实 reconcile_and_act（mock 读房与对账）
        → 真实 _start_new_training 复用 waiting_collect room 槽位（arrange_support=True）。"""
        from arknights_mower.utils.scheduler_task import SchedulerTask

        solver = self._solver(
            [
                Scene.TRAIN_MAIN,  # 读倒计时(无) → 复用 room.train_slot（==计划干员）→ continue
                Scene.TRAIN_MAIN,  # 训练位已确认 → 点开技能选择页
                Scene.TRAIN_SKILL_SELECT,  # 读档位(None) → 保守退出
            ]
        )
        task = SchedulerTask(
            time=datetime.now(),
            task_type=TaskTypes.SKILL_UPGRADE,
            meta_data="测试计划 收取",
        )
        task.plan_key = "1"
        solver.task = task
        plan = make_plan()
        room = mastery_reader.RoomState("waiting_collect", train_slot="测试干员")
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch("arknights_mower.utils.mastery_db.get_plan_by_id", return_value=plan),
            patch.object(mastery_reader, "read_room_state", return_value=room),
            patch(
                "arknights_mower.utils.mastery_db.get_active_plan", return_value=None
            ),
            patch("arknights_mower.utils.mastery_db.get_all_plans", return_value=[]),
            patch.object(mastery_reader, "_reconcile", return_value=(plan, True)),
            patch.object(mastery, "datetime", FixedDateTime),
            patch.object(mastery_reader, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status") as upd,
            patch("arknights_mower.utils.email.send_message"),
        ):
            mastery.run_mastery_task(solver)
        solver.enter_room.assert_not_called()
        solver.get_agent_from_room.assert_not_called()
        solver.choose_train.assert_not_called()
        statuses = [c.args[1] for c in upd.call_args_list]
        self.assertIn("idle", statuses, "档位读取失败 → 保持 idle 重排退出")


class TestRunMasteryTaskDispatch(unittest.TestCase):
    """#74 第3段（2026-08-14 用户拍板「都去掉」）：run_mastery_task 对任何带 plan_key 的
    SKILL_UPGRADE 任务都解析其指定计划为 scan_plan（空闲格是否开始由 _reconcile 按 idle
    判定）；plan_key=None（占用重检）无指定计划。无标记、无进程内存记号。"""

    @staticmethod
    def _plan_key_task(plan_key="3"):
        from arknights_mower.utils.scheduler_task import SchedulerTask

        task = SchedulerTask(
            time=datetime.now(),
            task_type=TaskTypes.SKILL_UPGRADE,
            meta_data="测试计划 开始训练",
        )
        task.plan_key = plan_key
        return task

    def _solver(self):
        solver = MagicMock()
        solver.task = None
        return solver

    @patch("arknights_mower.utils.mastery_db.get_plan_by_id")
    def test_plan_key_task_starts_specified_plan(self, g):
        solver = self._solver()
        solver.task = self._plan_key_task("3")
        plan = make_plan(id=3)
        room = mastery_reader.RoomState("empty", train_slot="测试干员")
        g.return_value = plan
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(plan, True, room)
            ) as ra,
            patch.object(mastery, "_start_new_training") as snt,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=plan)
        snt.assert_called_once_with(
            solver, plan, arrange_support=True, room=room, step_level=None
        )

    @patch("arknights_mower.utils.mastery_db.get_plan_by_id")
    def test_scan_task_carries_step_level_to_start(self, g):
        # 扫描派发任务带 step_level（current_level+1）→ 传给安排流程（失败邮件报「本次要练的专几」）
        solver = self._solver()
        task = self._plan_key_task("3")
        task.step_level = 2
        solver.task = task
        plan = make_plan(id=3)
        room = mastery_reader.RoomState("empty", train_slot="测试干员")
        g.return_value = plan
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(plan, True, room)
            ),
            patch.object(mastery, "_start_new_training") as snt,
        ):
            mastery.run_mastery_task(solver)
        snt.assert_called_once_with(
            solver, plan, arrange_support=True, room=room, step_level=2
        )

    @patch("arknights_mower.utils.mastery_db.get_plan_by_id")
    def test_collect_task_also_resolves_scan_plan(self, g):
        # 收取任务（meta_data=收取标签，无任何标记）带 plan_key → 同样解析 scan_plan
        # （arrange_support=True：#104 收取→开下一级也照常安排路线 operator）
        from arknights_mower.utils.scheduler_task import SchedulerTask

        solver = self._solver()
        collect_task = SchedulerTask(
            time=datetime.now(),
            task_type=TaskTypes.SKILL_UPGRADE,
            meta_data="能天使 二技能 专一 → 专二",
        )
        collect_task.plan_key = "1"
        solver.task = collect_task
        plan = make_plan()
        room = mastery_reader.RoomState("empty", train_slot="测试干员")
        g.return_value = plan
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(plan, True, room)
            ) as ra,
            patch.object(mastery, "_start_new_training") as snt,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=plan)
        snt.assert_called_once_with(
            solver, plan, arrange_support=True, room=room, step_level=None
        )

    def test_recheck_task_passes_no_scan_plan(self):
        # plan_key=None（占用重检）→ 无指定计划 → scan_plan=None
        from arknights_mower.utils.scheduler_task import SchedulerTask

        solver = self._solver()
        solver.task = SchedulerTask(
            time=datetime.now(), task_type=TaskTypes.SKILL_UPGRADE
        )
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(None, True, None)
            ) as ra,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=None)

    @patch("arknights_mower.utils.mastery_db.get_plan_by_id")
    def test_plan_key_task_resolves_even_if_not_idle(self, g):
        # run_mastery_task 只负责按 plan_key 解析目标计划；是否仍 idle 由 _reconcile
        # 空闲格统一判定（见 test_empty_room_scan_driven_plan_no_longer_idle_skips）
        solver = self._solver()
        solver.task = self._plan_key_task("3")
        plan = make_plan(id=3, status="training")
        g.return_value = plan
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(None, True, None)
            ) as ra,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=plan)

    @patch("arknights_mower.utils.mastery_db.get_plan_by_id")
    def test_plan_key_task_unknown_plan_skips_scan_plan(self, g):
        solver = self._solver()
        solver.task = self._plan_key_task("999")
        g.return_value = None
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(None, True, None)
            ) as ra,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=None)

    def test_off_returns_without_dispatch(self):
        solver = self._solver()
        solver.task = self._plan_key_task("3")
        with (
            patch.object(config_mod.conf, "enable_mastery", False),
            patch.object(mastery_reader, "reconcile_and_act") as ra,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_not_called()


class TestTrainingSlotsFloatingWindow(unittest.TestCase):
    """#78 审计定案：_training_slots 读槽位后**不**自己关浮窗——由唯一调用方
    _start_new_training 关（单次 back），避免 _read_slots 自己关造成二次 back 退出房间。"""

    def _solver(self):
        solver = MagicMock()
        solver.get_agent_from_room.return_value = [
            {"agent": "逻各斯"},
            {"agent": "能天使"},
        ]
        return solver

    def test_leaves_floating_window_open_for_caller(self):
        solver = self._solver()
        support, train = mastery._training_slots(solver)
        self.assertEqual((support, train), ("逻各斯", "能天使"))
        solver.back.assert_not_called()

    def test_short_scan_returns_empty(self):
        solver = self._solver()
        solver.get_agent_from_room.return_value = [{"agent": "逻各斯"}]
        self.assertEqual(mastery._training_slots(solver), ("", ""))
        solver.back.assert_not_called()


class TestRouteConfigSupportsFormat(unittest.TestCase):
    """#91：get_route_config 兼容前端数组格式的自定义路线。

    旧代码把 supports 当 {"level_N": {}} 字典读，数组上 "level_1" in parsed 恒 False →
    自定义路线永远回退 DEFAULT_ROUTES（本次协助位失败直接根因：自定义特种路线
    缄默德克萨斯 从未生效，实测 get_route_config('特种',1) = DEFAULT 罗宾）。
    #91 修订：central_bonus（0/5）+ 缓冲统一从全局设置行读（默认 0/10），自定义与回退共用。
    """

    def _route(self, supports, profession="特种"):
        return {
            "profession": profession,
            "supports": json.dumps(supports, ensure_ascii=False),
            "is_default": 0,
        }

    def _settings(self, **overrides):
        s = {"central_bonus": 0, "mastery_swap_buffer": 10}
        s.update(overrides)
        return s

    def _config(self, profession, level, route_row, settings=None):
        with (
            patch("arknights_mower.utils.mastery_db.get_route", return_value=route_row),
            patch(
                "arknights_mower.utils.mastery_db.get_route_settings",
                return_value=self._settings(**(settings or {})),
            ),
        ):
            return mastery.get_route_config(profession, level)

    def test_custom_array_takes_precedence_over_default(self):
        # #91 回归锚点：自定义特种路线 level_1 = 缄默德克萨斯，不再回退 DEFAULT 罗宾
        custom = self._route(
            [
                {
                    "name": "缄默德克萨斯",
                    "skill_level": 1,
                    "efficiency": 30,
                    "swap": False,
                    "swap_name": "",
                    "match": False,
                }
            ]
        )
        entry = self._config("特种", 1, custom)
        self.assertEqual(entry["operator"], "缄默德克萨斯")
        self.assertEqual(entry["efficiency"], 30)
        self.assertIsNone(entry["swap_target"])
        self.assertEqual(entry["central_bonus"], 0, "中枢加成缺省=0（#91 修订）")
        self.assertEqual(entry["mastery_swap_buffer"], 10)

    def test_central_bonus_from_settings(self):
        # central_bonus 从全局设置行读（0/5），自定义与 DEFAULT 回退共用同一值
        custom = self._route(
            [
                {
                    "name": "缄默德克萨斯",
                    "skill_level": 1,
                    "efficiency": 30,
                    "swap": True,
                    "swap_name": "艾丽妮",
                    "match": False,
                }
            ]
        )
        entry = self._config("特种", 1, custom, {"central_bonus": 5})
        self.assertEqual(entry["central_bonus"], 5)
        fallback = self._config("特种", 1, None, {"central_bonus": 5})
        self.assertEqual(fallback["central_bonus"], 5, "DEFAULT 回退也用全局设置值")

    def test_custom_array_matches_step_level(self):
        custom = self._route(
            [
                {
                    "name": "罗宾",
                    "skill_level": 1,
                    "efficiency": 75,
                    "swap": True,
                    "swap_name": "逻各斯",
                    "match": "yes",
                },
                {
                    "name": "缄默德克萨斯",
                    "skill_level": 2,
                    "efficiency": 80,
                    "swap": True,
                    "swap_name": "艾丽妮",
                    "match": False,
                },
            ]
        )
        l1 = self._config("特种", 1, custom)
        l2 = self._config("特种", 2, custom)
        self.assertEqual(l1["operator"], "罗宾")
        self.assertEqual(l1["job_match"], True, "match='yes' 字符串也应判 True")
        self.assertEqual(l2["operator"], "缄默德克萨斯")
        self.assertEqual(l2["swap_target"], "艾丽妮")

    def test_custom_array_swap_false_ignores_swap_name(self):
        custom = self._route(
            [
                {
                    "name": "缄默德克萨斯",
                    "skill_level": 1,
                    "efficiency": 30,
                    "swap": False,
                    "swap_name": "艾丽妮",
                    "match": False,
                }
            ]
        )
        entry = self._config("特种", 1, custom)
        self.assertIsNone(entry["swap_target"], "swap=false 时 swap_name 不生效")

    def test_custom_array_missing_level_falls_back_to_default(self):
        custom = self._route(
            [
                {
                    "name": "缄默德克萨斯",
                    "skill_level": 1,
                    "efficiency": 30,
                    "swap": False,
                    "swap_name": "",
                    "match": False,
                }
            ]
        )
        entry = self._config("特种", 3, custom)
        self.assertEqual(
            entry["operator"], mastery.DEFAULT_ROUTES["特种"]["level_3"]["operator"]
        )
        self.assertIsNone(
            entry["swap_target"], "回退默认 level_3 swap_target=None 保住铁律 7"
        )

    def test_custom_array_empty_falls_back_to_default(self):
        entry = self._config("特种", 1, self._route([]))
        self.assertEqual(
            entry["operator"], mastery.DEFAULT_ROUTES["特种"]["level_1"]["operator"]
        )

    def test_custom_array_swap_true_empty_name_is_none(self):
        # swap=true 但 swap_name 空 → swap_target=None（shape 契约：None=不换）；match='no' → False
        custom = self._route(
            [
                {
                    "name": "缄默德克萨斯",
                    "skill_level": 1,
                    "efficiency": 30,
                    "swap": True,
                    "swap_name": "",
                    "match": "no",
                }
            ]
        )
        entry = self._config("特种", 1, custom)
        self.assertIsNone(entry["swap_target"], "swap_name 空等同不换（铁律 7 语义）")
        self.assertEqual(entry["job_match"], False)

    def test_legacy_dict_still_works(self):
        legacy = self._route(
            {
                "level_1": {
                    "operator": "赤冬",
                    "efficiency": 75,
                    "job_match": True,
                    "swap_target": "艾丽妮",
                }
            },
            profession="近卫",
        )
        entry = self._config("近卫", 1, legacy)
        self.assertEqual(entry["operator"], "赤冬")
        self.assertEqual(entry["swap_target"], "艾丽妮")
        self.assertEqual(entry["job_match"], True)

    def test_wrapped_supports_array_still_parses(self):
        # agent set_route 文档形态 {"supports": [...], "central_bonus": N}：数组仍按
        # skill_level 解析，但 central_bonus 一律从全局设置行读（包装里的值不再生效）
        wrapped = self._route(
            {
                "supports": [
                    {
                        "name": "缄默德克萨斯",
                        "skill_level": 1,
                        "efficiency": 30,
                        "swap": True,
                        "swap_name": "艾丽妮",
                        "match": False,
                    }
                ],
                "central_bonus": 7,
            }
        )
        entry = self._config("特种", 1, wrapped, {"central_bonus": 0})
        self.assertEqual(entry["operator"], "缄默德克萨斯")
        self.assertEqual(
            entry["central_bonus"], 0, "包装里 central_bonus=7 被忽略，读设置行 0"
        )


if __name__ == "__main__":
    unittest.main()
