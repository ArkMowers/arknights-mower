"""无边框窗口样式组合的回归用例。

windows_frameless 在导入时就要 ctypes.wintypes，Linux 上不存在这个模块，所以按需在
用例内部导入，整个文件在非 Windows 平台照常收集、不报错。
"""

import os
import unittest


@unittest.skipUnless(os.name == "nt", "WinForms 窗口样式只在 Windows 上组合")
class TestFramelessWindowStyle(unittest.TestCase):
    def test_keeps_the_caption_styles_the_shell_animates_on(self):
        # 壳层只对同时带 WS_CAPTION 与最小化/最大化框样式的窗口播放最小化、最大化/
        # 还原与吸附过渡；少了 WS_CAPTION 窗口就是硬切。这里把组合固定下来，避免以后
        # 又把标题栏样式摘掉。真正的无边框由 WM_NCCALCSIZE 返回 0（客户区覆盖整个窗口）
        # 保证，不靠摘样式。
        from arknights_mower.utils import windows_frameless

        style = windows_frameless.frameless_window_style(0)
        for bit in (
            windows_frameless._WS_CAPTION,
            windows_frameless._WS_THICKFRAME,
            windows_frameless._WS_MINIMIZEBOX,
            windows_frameless._WS_MAXIMIZEBOX,
            windows_frameless._WS_SYSMENU,
        ):
            self.assertTrue(style & bit)

    def test_keeps_style_bits_the_window_already_had(self):
        # 组合是「补上」不是「重写」：WinForms 自己加的 WS_CLIPSIBLINGS 等位不能被抹掉。
        from arknights_mower.utils import windows_frameless

        existing = 0x04000000  # WS_CLIPSIBLINGS
        self.assertEqual(
            windows_frameless.frameless_window_style(existing) & existing, existing
        )


class _FakeEntryPoint:
    """一个 user32 入口点：只记录调用，不真的打到壳层。

    calls 记自己的入参；log 是共享的调用流水，用来固定几个入口之间的先后。
    """

    def __init__(self, log, name):
        self.argtypes = None
        self.restype = None
        self.calls = []
        self.log = log
        self.name = name


class _FakeFunction(_FakeEntryPoint):
    def __init__(self, result, log, name):
        super().__init__(log, name)
        self._result = result

    def __call__(self, *args):
        self.calls.append(args)
        self.log.append(self.name)
        return self._result


class _FakeCursorPos(_FakeEntryPoint):
    def __init__(self, cursor, log):
        super().__init__(log, "GetCursorPos")
        self._cursor = cursor

    def __call__(self, pointer):
        self.calls.append(pointer)
        self.log.append(self.name)
        pointer._obj.x, pointer._obj.y = self._cursor
        return True


class _FakeUser32:
    def __init__(self, cursor):
        self.log = []
        self.ReleaseCapture = _FakeFunction(True, self.log, "ReleaseCapture")
        self.SendMessageW = _FakeFunction(0, self.log, "SendMessageW")
        self.GetCursorPos = _FakeCursorPos(cursor, self.log)


@unittest.skipUnless(os.name == "nt", "交回壳层的消息只在 Windows 上发送")
class TestPressHandover(unittest.TestCase):
    """标题栏拖拽与拉伸边共用「把按下交回壳层」这一步，这里固定它发出去的内容。"""

    def setUp(self):
        from arknights_mower.utils import windows_frameless

        self.module = windows_frameless

    def _patch(self, name, value):
        original = getattr(self.module, name)
        setattr(self.module, name, value)
        self.addCleanup(setattr, self.module, name, original)

    def _hand_over(self, cursor, hit_code):
        fake = _FakeUser32(cursor)
        self._patch("_user32", lambda: fake)
        self.module._hand_press_to_shell(0x1234, hit_code)
        return fake

    def test_sends_the_press_as_a_non_client_button_down(self):
        fake = self._hand_over((321, 654), self.module._HTCAPTION)

        self.assertEqual(len(fake.SendMessageW.calls), 1)
        hwnd, message, w_param, l_param = fake.SendMessageW.calls[0]
        self.assertEqual(hwnd, 0x1234)
        self.assertEqual(message, self.module._WM_NCLBUTTONDOWN)
        self.assertEqual(w_param, self.module._HTCAPTION)
        self.assertEqual(l_param, ((654 & 0xFFFF) << 16) | (321 & 0xFFFF))

    def test_releases_the_capture_the_page_is_holding(self):
        # 页面自己按下时已经拿到了鼠标捕获，不放开的话壳层的移动循环收不到任何移动。
        fake = self._hand_over((10, 10), self.module._HTCAPTION)

        self.assertEqual(len(fake.ReleaseCapture.calls), 1)

    def test_asks_for_the_cursor_before_it_lets_go_of_the_capture(self):
        # 三步的次序都是必要的：光标位置要填进 lParam，捕获要在发消息之前放开，
        # 发消息必须在 UI 线程上（_run_on_ui_thread 的用例管这一段）。换了次序
        # 移动循环就起不来，而这一点在测试里看不出来，所以固定下来。
        fake = self._hand_over((11, 22), self.module._HTCAPTION)

        self.assertEqual(fake.log, ["GetCursorPos", "ReleaseCapture", "SendMessageW"])

    def test_packs_negative_coordinates_as_signed_words(self):
        # 副屏在主屏左侧时窗口坐标是负的，lParam 的每个半字是 16 位有符号数。
        fake = self._hand_over((-40, -7), self.module._HTCAPTION)

        _, _, _, l_param = fake.SendMessageW.calls[0]
        self.assertEqual(l_param, ((-7 & 0xFFFF) << 16) | (-40 & 0xFFFF))

    def test_the_title_bar_hands_over_the_caption_hit_code(self):
        # 入口自己挑命中码：标题栏交回 HTCAPTION，拉伸边交回 HTLEFT 一类。
        fake = _FakeUser32((7, 8))
        self._patch("_user32", lambda: fake)
        self._patch("_winforms_window", lambda window: object())
        self._patch("_winforms_hwnd", lambda window: 0x1234)
        self._patch("_run_on_ui_thread", lambda form, action: action())

        self.assertTrue(self.module.begin_windows_move(object()))

        self.assertEqual(len(fake.SendMessageW.calls), 1)
        self.assertEqual(fake.SendMessageW.calls[0][2], self.module._HTCAPTION)


if __name__ == "__main__":
    unittest.main()
