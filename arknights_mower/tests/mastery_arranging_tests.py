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

    #73 三态倒计时：_read_train_countdown3 改读 read_time 返回秒（None/0/正数），
    START(=now) 即 00:00:00 语义 → 0（为0 → 不占用，同读失败效果）。
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
        未确认身份的 219（误判的运行页）不走 deadline、立即保守退出——见
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
            # 前两次（读占用×2）无倒计时（00:00:00 语义 =0 → 不占用）；第三次起是
            # 确认流程（第一次无倒计时继续等，第二次读到有效倒计时确认开始）——219 不再读倒计时（#72）
            return 0 if read_count["n"] <= 3 else 7200

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
            patch.object(mastery, "_schedule_swap_if_needed"),
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

    def test_confirm_then_read_countdown_on_skill_select(self):
        """#53 实机：确认升级后训练已开始，但运行页被识别成 TRAIN_SKILL_SELECT，
        此时也要能读到倒计时、确认训练开始（而不是一直等 TRAIN_MAIN 到超时）。
        """
        solver = MagicMock()
        solver.find.return_value = ((1563, 832), (1880, 1048))  # skill_confirm
        solver.train_scene.side_effect = [
            Scene.TRAIN_SKILL_UPGRADE,  # 确认页 → tap 确认
            Scene.TRAIN_SKILL_SELECT,  # 训练运行页（被误识别成选择技能页）
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
            patch.object(mastery, "_schedule_swap_if_needed"),
            patch.object(mastery, "_schedule_collect"),
        ):
            mastery._start_new_training(solver, plan)
        training_calls = [c for c in upd.call_args_list if c.args[1] == "training"]
        self.assertTrue(
            training_calls, "在 TRAIN_SKILL_SELECT 上读到有效倒计时也应确认训练开始"
        )

    # --- #72：运行中的训练页被误判成 219（未经过训练位确认）→ 不数星星、不点技能行 ---
    def test_misjudged_skill_select_no_identity_exits(self):
        """误判的 219：倒计时、面板文字都不可读（真技能选择页读不到主面板区域）
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
        """误判的 219 即使倒计时可读（物理上仍是运行页）也因未确认身份而保守退出。

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
        reads = iter([0, 0, 7200])

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
            patch.object(mastery, "_schedule_swap_if_needed"),
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
            patch.object(mastery, "_schedule_swap_if_needed"),
            patch.object(mastery, "_schedule_collect"),
            patch.object(mastery, "get_char_name", return_value="兜底干员") as gcn,
        ):
            result = mastery._confirm_training_started(
                solver, plan, START + timedelta(minutes=10)
            )
        self.assertEqual(result, "started")
        self.assertIn("兜底干员", send.call_args[0][0])
        gcn.assert_called_once_with("char_test")


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

    def _confirm(self, swap_scheduled, **kw):
        solver = self._solver()
        plan = make_plan()
        with (
            patch.object(mastery, "datetime", FixedDateTime),
            patch("arknights_mower.utils.mastery_db.update_plan_status"),
            patch("arknights_mower.utils.email.send_message"),
            patch.object(mastery, "_arrange_support"),
            patch.object(
                mastery, "_schedule_swap_if_needed", return_value=swap_scheduled
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
        self.assertTrue(scheduled, "立即换人应排 SWAP_SUPPORT")
        self.assertEqual(len(solver.tasks), 1)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)

    def test_schedule_swap_delayed_returns_true(self):
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
        self.assertTrue(scheduled)
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
        self.assertFalse(scheduled, "步级未知回退专三 → 不换人")
        self.assertEqual(route_calls, [None], "应把缺省 step_level 传给路线加载")

    def test_run_swap_support_schedules_collect_after_swap(self):
        # §16.10：SWAP_SUPPORT 完成后重读倒计时再排收取。倒计时得「值得换」
        # （换后真实 ≥ 301，read_time=15000→250 分钟）才会真正执行换人。
        solver = self._solver()
        solver.read_time.return_value = 15000  # 250 分钟，换后真实 ≈ 330 分钟
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
        solver = self._solver()
        solver.read_time.return_value = read_seconds
        solver.task = task
        solver.choose_train.side_effect = Exception("选人流程超时")
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
        solver = self._solver()
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

    def test_swap_support_correction_not_worthwhile_no_swap(self):
        # #80 acceptance 2：时间不足（换后真实 < 301）的步，纠错只纠成 operator，
        # **不触发不该发生的减半换人**（只排收取退出）
        solver = self._solver()
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
        solver = self._solver()
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
        solver = self._solver()
        solver.read_time.return_value = 15000
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
        self.assertTrue(scheduled)
        self.assertEqual(solver.tasks[0].type, TaskTypes.SWAP_SUPPORT)
        self.assertEqual(solver.tasks[0].plan_key, str(plan["id"]))

    def test_schedule_collect_after_swap_closes_detail_before_read(self):
        # 读倒计时前若停在主页面带进驻详情浮窗（INFRA_DETAILS）→ 先关浮窗回主页面再读
        solver = self._solver()
        solver.read_time.return_value = (
            15000  # 250 分钟，值得换（否则 worth 门跳过换人）
        )
        solver.train_scene.side_effect = [Scene.INFRA_DETAILS, Scene.TRAIN_MAIN]
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
        solver.back.assert_called_once()  # 关掉进驻详情浮窗
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
        self.assertTrue(scheduled, "专三计划专一步应减半换人")
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
        self.assertFalse(scheduled, "专三步路线无 swap_target → 不换人")

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
            return False

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

    def test_confirm_passes_step_level_on_run_page_219(self):
        # #53/#72：确认后的运行页被识别成 TRAIN_SKILL_SELECT（219）——step_level 读取
        # 必须覆盖它，否则实机永远读不到步级、专三计划专一/专二步不减半换人
        solver = self._lit_solver(lit=2)
        solver.train_scene.return_value = Scene.TRAIN_SKILL_SELECT
        plan = make_plan()
        swap_calls = []

        def fake_swap(s, p, execute_time, step_level=None):
            swap_calls.append(step_level)
            return False

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
        self.assertEqual(swap_calls, [2], "运行页(219)也应读到图标当前步级（专二）")

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
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.read_time.return_value = 15000  # 250 分钟，值得换（否则 worth 门跳过）
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
            patch.object(mastery, "_schedule_collect"),
            patch.object(config_mod.conf, "assistant_follows_schedule", False),
            patch.object(config_mod.conf, "enable_mastery", True),
        ):
            mastery.run_swap_support(solver)
        solver.choose_train.assert_called_once_with(["艾丽妮", "Current"])
        self.assertEqual(route_calls, [2], "run_swap_support 应进房读图标得当前步级")

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
        g.return_value = plan
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(plan, True)
            ) as ra,
            patch.object(mastery, "_start_new_training") as snt,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=plan)
        snt.assert_called_once_with(solver, plan, arrange_support=True)

    @patch("arknights_mower.utils.mastery_db.get_plan_by_id")
    def test_collect_task_also_resolves_scan_plan(self, g):
        # 收取任务（meta_data=收取标签，无任何标记）带 plan_key → 同样解析 scan_plan
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
        g.return_value = plan
        with (
            patch.object(config_mod.conf, "enable_mastery", True),
            patch.object(
                mastery_reader, "reconcile_and_act", return_value=(plan, False)
            ) as ra,
            patch.object(mastery, "_start_new_training") as snt,
        ):
            mastery.run_mastery_task(solver)
        ra.assert_called_once_with(solver, scan_plan=plan)
        snt.assert_called_once_with(solver, plan, arrange_support=False)

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
                mastery_reader, "reconcile_and_act", return_value=(None, True)
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
                mastery_reader, "reconcile_and_act", return_value=(None, True)
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
                mastery_reader, "reconcile_and_act", return_value=(None, True)
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


if __name__ == "__main__":
    unittest.main()
