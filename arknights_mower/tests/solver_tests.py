import unittest
from unittest.mock import MagicMock, patch

from arknights_mower.utils.csleep import MowerExit
from arknights_mower.utils.scene import Scene
from arknights_mower.utils.solver import BaseSolver


class TestSolverStartupLaunch(unittest.TestCase):
    """Solver 委托设备统一连接入口，不重复创建截图和触控服务。"""

    def setUp(self):
        self.create = self.enterContext(
            patch("arknights_mower.utils.solver.Device.create")
        )
        self.recog = self.enterContext(patch("arknights_mower.utils.solver.Recognizer"))

    def test_first_connection_uses_single_initial_attempt(self):
        solver = BaseSolver(connection_retries=1)
        self.create.assert_called_once_with(connection_retries=1)
        self.assertIs(solver.device, self.create.return_value)
        self.recog.assert_called_once_with(solver.device)

    def test_later_connection_uses_three_attempts(self):
        BaseSolver()
        self.create.assert_called_once_with(connection_retries=3)

    def test_supplied_device_is_reused(self):
        device = MagicMock()
        solver = BaseSolver(device)
        self.assertIs(solver.device, device)
        self.create.assert_not_called()

    def test_failed_connection_does_not_start_recognition(self):
        self.create.side_effect = ConnectionError("offline")
        with self.assertRaises(ConnectionError):
            BaseSolver()
        self.recog.assert_not_called()

    def test_stop_propagates_without_extra_attempt(self):
        self.create.side_effect = MowerExit
        with self.assertRaises(MowerExit):
            BaseSolver()
        self.create.assert_called_once_with(connection_retries=3)
        self.recog.assert_not_called()


class TestTapElement(unittest.TestCase):
    """tap_element：find 返回空时不 tap、不抛错、返回 False；找到时 tap 中心、返回 True。"""

    def setUp(self):
        self.solver = BaseSolver.__new__(BaseSolver)
        self.find_patch = patch.object(BaseSolver, "find")
        self.tap_patch = patch.object(BaseSolver, "tap")
        self.find_mock = self.find_patch.start()
        self.tap_mock = self.tap_patch.start()
        self.addCleanup(self.find_patch.stop)
        self.addCleanup(self.tap_patch.stop)

    def test_missing_element_no_tap_returns_false(self):
        self.find_mock.return_value = None
        result = self.solver.tap_element("confirm_blue")
        self.assertFalse(result)
        self.tap_mock.assert_not_called()

    def test_found_element_taps_center_returns_true(self):
        self.find_mock.return_value = [[100, 200], [300, 400]]
        result = self.solver.tap_element("confirm_blue")
        self.assertTrue(result)
        self.tap_mock.assert_called_once_with([[100, 200], [300, 400]], 0.5, 0.5, 1)


class TestRunClearsStaleScene(unittest.TestCase):
    """run：每圈结束清一次场景缓存，转移静默失败时不会拿陈旧场景一直空转。"""

    class _StaleSceneSolver(BaseSolver):
        """转移在陈旧场景上静默失败，画面刷新之后才认出正确场景。"""

        def __init__(self, recog):
            self.recog = recog
            self.iterations = 0

        def transition(self):
            self.iterations += 1
            if self.iterations > 3:
                raise AssertionError("run 未在刷新画面后退出，仍在陈旧场景上空转")
            if self.scene() == Scene.OPERATOR_ELIMINATE_AGENCY:
                return None  # 找不到要点的元素，静默失败
            return True

    class _StaleRecog:
        """get_scene 返回缓存场景，update 之后才看得到新画面。"""

        def __init__(self, scene, refreshed):
            self.scene = scene
            self.refreshed = refreshed

        def get_scene(self):
            return self.scene

        def update(self):
            self.scene = self.refreshed

        def check_current_focus(self):
            pass

    def test_stale_scene_does_not_spin_forever(self):
        recog = self._StaleRecog(Scene.OPERATOR_ELIMINATE_AGENCY, Scene.INFRA_MAIN)
        solver = self._StaleSceneSolver(recog)
        self.assertTrue(solver.run())
        self.assertEqual(solver.iterations, 2)


if __name__ == "__main__":
    unittest.main()
