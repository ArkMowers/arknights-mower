import sys
import types
import unittest
from unittest.mock import MagicMock

# base_schedule 导入链（cultivate_depot→skland）会在 skland 模块加载时调用
# SecuritySm.get_d_id() 发网络请求（环境性 flake，与测试无关）。测试不涉及
# skland，预置 stub 挡住，避免单测依赖外网。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.operators import Operators  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402

choose_train = BaseSchedulerSolver.choose_train


class TestUnscheduledTrainingRoom(unittest.TestCase):
    def make_operators(self, support="", trainee="号角", plan=None):
        data = object.__new__(Operators)
        data.plan = {} if plan is None else plan
        data.operators = {
            name: types.SimpleNamespace(
                name=name, current_room="train", current_index=index
            )
            for index, name in enumerate([support, trainee])
            if name
        }
        return data

    def test_room_slots_do_not_depend_on_schedule(self):
        for plan in (
            {},
            {"train": []},
            {"train": [types.SimpleNamespace(agent="暴雨")]},
        ):
            with self.subTest(plan=plan):
                data = self.make_operators(plan=plan)
                self.assertEqual(data.get_current_room("train", True), ["", "号角"])
                self.assertIsNone(data.get_current_room("train"))
                self.assertEqual(
                    data.get_current_room("train", current_index=[1]), ["", "号角"]
                )
                self.assertEqual(data.plan, plan)

    def test_empty_and_occupied_room_keep_both_slots(self):
        self.assertEqual(
            self.make_operators(trainee="").get_current_room("train", True), ["", ""]
        )
        self.assertEqual(
            self.make_operators(support="暴雨").get_current_room("train"),
            ["暴雨", "号角"],
        )

    def test_other_rooms_still_use_schedule_size(self):
        data = self.make_operators(
            plan={"central": [types.SimpleNamespace(agent="阿米娅")]}
        )
        self.assertEqual(data.get_current_room("central", True), [""])
        with self.assertRaises(KeyError):
            data.get_current_room("missing", True)

    def test_real_assistant_selection_without_train_schedule(self):
        for old_support in ("", "褐果"):
            with self.subTest(old_support=old_support):
                solver = make_solver(
                    [
                        Scene.INFRA_DETAILS,
                        Scene.INFRA_ARRANGE_ORDER,
                        Scene.INFRA_DETAILS,
                    ],
                    [
                        [{"agent": old_support}, {"agent": "号角"}],
                        [{"agent": "暴雨"}, {"agent": "号角"}],
                    ],
                )
                solver.op_data = self.make_operators(support=old_support)
                solver.choose_agent = types.MethodType(
                    BaseSchedulerSolver.choose_agent, solver
                )
                solver.detect_arrange_order.return_value = ("技能", False)
                solver.verify_agent.return_value = True

                def scan(agents, **kwargs):
                    self.assertEqual(agents, ["暴雨"])
                    agents.remove("暴雨")
                    return ["暴雨"], []

                solver.scan_agent.side_effect = scan
                choose_train(solver, ["暴雨", "Current"])
                solver.verify_agent.assert_called_once_with(["暴雨"], "train")
                solver.tap_confirm.assert_called_once_with("train")
                solver.choose_train_ope.assert_not_called()
                self.assertEqual(solver.op_data.plan, {})
                if not old_support:
                    # 协助位为空时不得把训练位当成原协助者点击取消。
                    solver.tap.assert_not_called()


def make_solver(scenes, scan_results):
    """fake solver：脚本化场景 + 分次返回的训练室槽位扫描结果。

    复刻 tests/mastery_arranging_tests.py 的 fake solver 范式：
    用 MagicMock 替身驱动真实的 choose_train 逻辑，断言选人调用。
    """
    solver = MagicMock()
    solver.scene.side_effect = list(scenes)
    solver.get_agent_from_room.side_effect = list(scan_results)

    def fake_find(res, *args, **kwargs):
        return True

    solver.find.side_effect = fake_find
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    solver.recog.w = 1920
    solver.recog.h = 1080
    solver.tasks = []
    solver.task = None
    return solver


class TestChooseTrainCurrentReplacement(unittest.TestCase):
    """#53 根因1：choose_train 的 Current 位置用替换后的实际干员名选人。

    修复前：INFRA_ARRANGE_ORDER 分支用 agents[idx]（可能是 'Current'）选人，
    'Current' 被当干员名 → 不点职业筛选 → 扫不到 → 触底 raise("重试一次") → failed。
    修复后：desired[idx] 是 scan 阶段替换后的真实干员名；agents[0]=="Current"
    的协助位视为保持原样，不进 select_targets，choose_agent 不再收到 'Current'。
    """

    def test_swap_trainer_keeps_assistant_and_swaps_real_name(self):
        """choose_train(['Current', '若叶睦'])：协助位不动，只换训练位（真实名）。"""
        solver = make_solver(
            scenes=[
                Scene.INFRA_DETAILS,
                Scene.INFRA_DETAILS,
                Scene.INFRA_ARRANGE_ORDER,
                Scene.INFRA_DETAILS,
            ],
            scan_results=[
                [{"agent": "褐果"}, {"agent": "桃金娘"}],
                [{"agent": "褐果"}, {"agent": "若叶睦"}],  # 换人后重扫：训练位已就位
            ],
        )
        choose_train(solver, ["Current", "若叶睦"])
        solver.choose_train_ope.assert_called_once_with("若叶睦")
        self.assertFalse(
            solver.choose_agent.called,
            "协助位 Current 应视为保持原样，不应触发 choose_agent",
        )

    def test_swap_assistant_picks_real_name(self):
        """choose_train(['夜莺', 'Current'])：idx0 换协助位走 choose_agent，传真实干员名。"""
        solver = make_solver(
            scenes=[
                Scene.INFRA_DETAILS,
                Scene.INFRA_DETAILS,
                Scene.INFRA_ARRANGE_ORDER,
                Scene.INFRA_DETAILS,
            ],
            scan_results=[
                [{"agent": "褐果"}, {"agent": "桃金娘"}],
                [{"agent": "夜莺"}, {"agent": "桃金娘"}],
            ],
        )
        choose_train(solver, ["夜莺", "Current"])
        solver.choose_agent.assert_called_once_with(["夜莺"], "train", True)
        self.assertFalse(
            solver.choose_train_ope.called,
            "idx1 Current 应视为保持原样（替换后与其 scan 相同），不应触发 choose_train_ope",
        )


class TestChooseTrainOpensCheckInDetail(unittest.TestCase):
    """#92 换协助位坐标：训练室主页面（TRAIN_MAIN/INFRA_DETAILS-no-room_detail）
    开进驻信息浮窗必须用 arrange_check_in 位置，不能用旧死坐标 (0.25w, 0.95h)。

    旧代码 tap((0.25w, 0.95h))=(480,1026) 在训练室落在左下角技能/进度面板 → 点出
    技能详情浮窗（非进驻信息浮窗）→ Scene -1 空转 7s → 出房重进。正确入口与
    turn_on_room_detail 同源：find("arrange_check_in")（屏幕左侧 ~(101,441)）。
    """

    def _make_solver(self, scenes, scan_results):
        """fake solver：脚本化场景 + 分次返回槽位扫描。find 侧状态化——room_detail
        在 arrange_check_in 被点过一次前视为浮窗未开（这正是 #92 的触发前提）。
        """
        solver = MagicMock()
        solver.scene.side_effect = list(scenes)
        solver.get_agent_from_room.side_effect = list(scan_results)
        state = {"detail_open": False}

        def fake_find(res, *args, **kwargs):
            if res == "arrange_check_in":
                # 屏幕左侧进驻按钮（真实识别约 (65,384)-(139,452)）
                return ((80, 380), (140, 460))
            if res == "room_detail":
                # 浮窗没点开之前找不到；点过 arrange_check_in 后视为已开
                return True if state["detail_open"] else None
            return True

        def fake_tap(pos, *args, **kwargs):
            if pos == ((80, 380), (140, 460)):
                state["detail_open"] = True

        solver.find.side_effect = fake_find
        solver.tap.side_effect = fake_tap
        # solver 是 MagicMock，self._open_check_in_detail 会自动 mock 成空方法——
        # 绑定真实方法（#92 新增的 `_open_check_in_detail` 走 find/tap/sleep）。
        solver._open_check_in_detail = types.MethodType(
            BaseSchedulerSolver._open_check_in_detail, solver
        )
        solver.train_scene.return_value = Scene.TRAIN_MAIN
        solver.recog.w = 1920
        solver.recog.h = 1080
        solver.tasks = []
        solver.task = None
        return solver

    def test_train_main_taps_arrange_check_in(self):
        """TRAIN_MAIN 分支：点 arrange_check_in 位置开进驻信息浮窗，不再点 (0.25w,0.95h)。"""
        solver = self._make_solver(
            scenes=[
                Scene.TRAIN_MAIN,
                Scene.INFRA_DETAILS,
                Scene.INFRA_ARRANGE_ORDER,
                Scene.INFRA_DETAILS,
            ],
            scan_results=[
                [{"agent": "褐果"}, {"agent": "桃金娘"}],
                [{"agent": "夜莺"}, {"agent": "桃金娘"}],
            ],
        )
        choose_train(solver, ["夜莺", "Current"])

        def _taps():
            return [c.args[0] for c in solver.tap.call_args_list]

        # 必须点过 arrange_check_in 位置
        self.assertTrue(
            any(call == ((80, 380), (140, 460)) for call in _taps()),
            "TRAIN_MAIN 分支应点 arrange_check_in 开进驻信息浮窗",
        )
        # 绝不能再点旧死坐标 (0.25w, 0.95h) = (480, 1026)
        self.assertFalse(
            any(call == (480, 1026) for call in _taps()),
            "不得再点 (0.25w, 0.95h) 死坐标",
        )
        solver.choose_agent.assert_called_once_with(["夜莺"], "train", True)

    def test_infra_details_no_room_detail_taps_arrange_check_in(self):
        """INFRA_DETAILS 但浮窗未开分支（#92 实机路径：general get_scene 标 205、
        room_detail 找不到）：同样点 arrange_check_in 而非死坐标。"""
        solver = self._make_solver(
            scenes=[
                Scene.INFRA_DETAILS,
                Scene.INFRA_DETAILS,
                Scene.INFRA_ARRANGE_ORDER,
                Scene.INFRA_DETAILS,
            ],
            scan_results=[
                [{"agent": "褐果"}, {"agent": "桃金娘"}],
                [{"agent": "夜莺"}, {"agent": "桃金娘"}],
            ],
        )
        choose_train(solver, ["夜莺", "Current"])

        def _taps():
            return [c.args[0] for c in solver.tap.call_args_list]

        self.assertTrue(
            any(call == ((80, 380), (140, 460)) for call in _taps()),
            "INFRA_DETAILS 浮窗未开分支应点 arrange_check_in",
        )
        self.assertFalse(
            any(call == (480, 1026) for call in _taps()),
            "不得再点 (0.25w, 0.95h) 死坐标",
        )
        solver.choose_agent.assert_called_once_with(["夜莺"], "train", True)


if __name__ == "__main__":
    unittest.main()
