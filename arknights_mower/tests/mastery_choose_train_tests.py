import sys
import unittest
from unittest.mock import MagicMock

# base_schedule 导入链（cultivate_depot→skland）会在 skland 模块加载时调用
# SecuritySm.get_d_id() 发网络请求（环境性 flake，与测试无关）。测试不涉及
# skland，预置 stub 挡住，避免单测依赖外网。
sys.modules.setdefault("arknights_mower.utils.skland", MagicMock())

from arknights_mower.solvers.base_schedule import BaseSchedulerSolver  # noqa: E402
from arknights_mower.utils.scene import Scene  # noqa: E402

choose_train = BaseSchedulerSolver.choose_train


def make_solver(scenes, scan_results, locked=False):
    """fake solver：脚本化场景 + 分次返回的训练室槽位扫描结果。

    复刻 tests/mastery_arranging_tests.py 的 fake solver 范式：
    用 MagicMock 替身驱动真实的 choose_train 逻辑，断言选人调用。

    locked=True：D4 锁定检测读到有效倒计时 → 训练位视为锁定。
    """
    solver = MagicMock()
    solver.scene.side_effect = list(scenes)
    solver.get_agent_from_room.side_effect = list(scan_results)

    def fake_find(res, *args, **kwargs):
        # 房间详情浮层常开；training_completed 模板不存在（否则 D4 会判锁定）
        if res == "training_completed":
            return None
        return True

    solver.find.side_effect = fake_find
    solver.train_scene.return_value = Scene.TRAIN_MAIN
    # #73 三态倒计时：train_slot_locked 改读 read_time（秒），locked=True 给未来倒计时
    solver.read_time.return_value = 7200 if locked else None
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


class TestChooseTrainD4LockSkip(unittest.TestCase):
    """#59 D4 / #69 B3：训练位锁定（🔴 训练中 / 🟡 待收取）时不能换 idx1。

    - idx1 是唯一变更且锁定 → choose_train 必须明确抛异常（修复前静默 return
      会让换人"看似成功"、流程继续点错干员开始）；
    - 锁定但还有 idx0 变更 → 只换协助位、不换训练位、不空转 2 分钟超时。
    """

    def test_locked_trainer_swap_raises(self):
        solver = make_solver(
            scenes=[Scene.INFRA_DETAILS],
            scan_results=[
                [{"agent": "褐果"}, {"agent": "桃金娘"}],
            ],
            locked=True,
        )
        with self.assertRaises(Exception) as ctx:
            choose_train(solver, ["Current", "若叶睦"])
        self.assertIn("训练位被锁定", str(ctx.exception))
        self.assertFalse(solver.choose_train_ope.called, "锁定的训练位不应尝试更换")
        self.assertFalse(solver.choose_agent.called, "协助位 Current 保持原样")

    def test_locked_trainer_keeps_assistant_then_raises(self):
        """idx0 也要换：先换协助位成功，重扫后训练位仍锁定 → 明确失败而非静默成功。"""
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
            locked=True,
        )
        with self.assertRaises(Exception) as ctx:
            choose_train(solver, ["夜莺", "若叶睦"])
        self.assertIn("训练位被锁定", str(ctx.exception))
        solver.choose_agent.assert_called_once_with(["夜莺"], "train", True)
        self.assertFalse(solver.choose_train_ope.called, "锁定的训练位不应尝试更换")

    def test_not_locked_still_swaps_trainer(self):
        solver = make_solver(
            scenes=[
                Scene.INFRA_DETAILS,
                Scene.INFRA_DETAILS,
                Scene.INFRA_ARRANGE_ORDER,
                Scene.INFRA_DETAILS,
            ],
            scan_results=[
                [{"agent": "褐果"}, {"agent": "桃金娘"}],
                [{"agent": "褐果"}, {"agent": "若叶睦"}],
            ],
            locked=False,
        )
        choose_train(solver, ["Current", "若叶睦"])
        solver.choose_train_ope.assert_called_once_with("若叶睦")


if __name__ == "__main__":
    unittest.main()
