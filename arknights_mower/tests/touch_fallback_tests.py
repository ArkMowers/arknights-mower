import unittest
from contextlib import suppress
from unittest.mock import MagicMock, call, patch

from arknights_mower.utils.device.device import Device
from arknights_mower.utils.recognize import Scene
from arknights_mower.utils.solver import BaseSolver


class TestTouchFallback(unittest.TestCase):
    """测试 touch_fallback 配置项和相关逻辑"""

    def test_touch_fallback_default_is_false(self):
        """touch_fallback 默认值应为 False"""
        from arknights_mower.utils.config.conf import SimulatorPart

        sim = SimulatorPart()
        self.assertFalse(sim.touch_fallback)

    @patch.object(BaseSolver, "__init__", lambda x: None)
    @patch("arknights_mower.utils.solver.caller_info", return_value="test_caller")
    def test_ctap_deduplication(self, mock_caller_info):
        """ctap 在 10 秒内同一调用者重复调用时应跳过 tap"""
        solver = BaseSolver()
        solver.tap_info = (None, None)
        solver.tap = MagicMock()
        solver.sleep = MagicMock()
        solver.device = MagicMock()

        solver.ctap((1410, 870))

        solver.tap.assert_called_once()
        solver.tap.reset_mock()

        solver.ctap((1410, 870))

        solver.tap.assert_not_called()
        solver.sleep.assert_called_once()

    @patch.object(BaseSolver, "__init__", lambda x: None)
    def test_tap_without_fallback(self):
        """touch_fallback=False 时，login 使用原有逻辑"""
        solver = BaseSolver()
        solver.device = MagicMock()
        solver.device.is_avd_like = False  # 非 AVD 模式（touch_fallback=False 且未自动检测到 AVD）
        solver.recog = MagicMock()
        solver.scene = MagicMock(return_value=Scene.LOGIN_START)
        # 第一次 False 进入循环，第二次 True 使 while 退出，避免死循环
        solver.is_login = MagicMock(side_effect=[False, True, True])
        solver.sleep = MagicMock()
        solver.tap_element = MagicMock()

        with patch("arknights_mower.utils.config.conf") as mock_conf:
            mock_conf.touch_fallback = False
            mock_conf.stop_mower = MagicMock()
            mock_conf.stop_mower.is_set.return_value = False
            mock_conf.MAX_RETRYTIME = 1
            # login 方法会调用 tap
            with suppress(AttributeError, TypeError):
                solver.login()

        # touch_fallback=False 时，不调用 device.tap(AVD_LOGIN_START_TAP)
        from arknights_mower.utils.solver import AVD_LOGIN_START_TAP

        self.assertNotIn(
            call(AVD_LOGIN_START_TAP),
            solver.device.tap.call_args_list,
        )
        # 非 AVD 路径应走正常坐标的 control.tap
        solver.device.tap.assert_called_with((665, 741))

    @patch.object(BaseSolver, "__init__", lambda x: None)
    def test_tap_with_fallback(self):
        """touch_fallback=True 时，login 使用 device.tap(AVD_LOGIN_START_TAP)"""
        solver = BaseSolver()
        solver.device = MagicMock()
        solver.device.is_avd_like = True  # AVD 行为由 touch_fallback=True 触发
        solver.recog = MagicMock()
        solver.scene = MagicMock(return_value=Scene.LOGIN_START)
        # 第一次 False 进入循环，第二次 True 使 while 退出，避免死循环
        solver.is_login = MagicMock(side_effect=[False, True, True])
        solver.sleep = MagicMock()

        with patch("arknights_mower.utils.config.conf") as mock_conf:
            mock_conf.touch_fallback = True
            mock_conf.stop_mower = MagicMock()
            mock_conf.stop_mower.is_set.return_value = False
            mock_conf.MAX_RETRYTIME = 1
            with suppress(AttributeError, TypeError):
                solver.login()

        from arknights_mower.utils.solver import AVD_LOGIN_START_TAP

        solver.device.tap.assert_called_with(AVD_LOGIN_START_TAP)

    @patch.object(BaseSolver, "__init__", lambda x: None)
    def test_tap_with_avd_mode_autodetect(self):
        """avd_mode=True（自动检测）且 touch_fallback=False 时，login 同样走 AVD 路径"""
        solver = BaseSolver()
        solver.device = MagicMock()
        solver.device.is_avd_like = True  # 模拟自动检测到 AVD（avd_mode=True）
        solver.recog = MagicMock()
        solver.scene = MagicMock(return_value=Scene.LOGIN_START)
        # 第一次 False 进入循环，第二次 True 使 while 退出，避免死循环
        solver.is_login = MagicMock(side_effect=[False, True, True])
        solver.sleep = MagicMock()

        with patch("arknights_mower.utils.config.conf") as mock_conf:
            mock_conf.touch_fallback = False  # 用户未手动开启
            mock_conf.stop_mower = MagicMock()
            mock_conf.stop_mower.is_set.return_value = False
            mock_conf.MAX_RETRYTIME = 1
            with suppress(AttributeError, TypeError):
                solver.login()

        from arknights_mower.utils.solver import AVD_LOGIN_START_TAP

        solver.device.tap.assert_called_with(AVD_LOGIN_START_TAP)


class TestIsAvdLike(unittest.TestCase):
    """测试 Device.is_avd_like 属性：touch_fallback 或 avd_mode 任一为真即为 AVD 类环境"""

    def _make_device(self, avd_mode: bool) -> Device:
        # 绕过 __init__（避免建立 adb 连接），仅构造实例并设置标记
        device = Device.__new__(Device)
        device.avd_mode = avd_mode
        return device

    @patch("arknights_mower.utils.config.conf")
    def test_false_when_both_off(self, mock_conf):
        mock_conf.touch_fallback = False
        self.assertFalse(self._make_device(False).is_avd_like)

    @patch("arknights_mower.utils.config.conf")
    def test_true_when_touch_fallback(self, mock_conf):
        mock_conf.touch_fallback = True
        self.assertTrue(self._make_device(False).is_avd_like)

    @patch("arknights_mower.utils.config.conf")
    def test_true_when_avd_mode(self, mock_conf):
        mock_conf.touch_fallback = False
        self.assertTrue(self._make_device(True).is_avd_like)


if __name__ == "__main__":
    unittest.main()
