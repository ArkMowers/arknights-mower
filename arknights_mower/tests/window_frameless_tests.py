"""无边框窗口样式组合的回归用例。

windows_frameless 在导入时就要 ctypes.wintypes，Linux 上不存在这个模块，所以按需在
用例内部导入，整个文件在非 Windows 平台照常收集、不报错。
"""

import os
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import Mock, call, patch


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


@unittest.skipUnless(os.name == "nt", "Native window hit tests require Windows")
class TestTitlebarHitTest(unittest.TestCase):
    def test_native_caption_bounds_and_resize_edges_at_supported_dpi_scales(self):
        from arknights_mower.utils import windows_frameless

        window = SimpleNamespace(uid="offline-titlebar-hit-test")
        user32 = Mock()
        user32.GetDpiForWindow = None
        user32.GetWindowLongPtrW.return_value = 1
        user32.SetWindowLongPtrW.return_value = 1
        user32.CallWindowProcW.return_value = 1
        user32.IsZoomed.return_value = False
        user32.GetSystemMetrics.side_effect = lambda metric: {32: 8, 33: 8, 92: 0}[
            metric
        ]
        user32.SetWindowPos.return_value = True

        def get_window_rect(hwnd, pointer):
            rect = pointer._obj
            rect.left, rect.top, rect.right, rect.bottom = 100, 100, 1300, 900
            return True

        user32.GetWindowRect.side_effect = get_window_rect
        with (
            patch.object(windows_frameless, "_winforms_hwnd", return_value=0x1234),
            patch.object(windows_frameless, "_user32", return_value=user32),
            patch.object(windows_frameless, "_apply_dwm_window_chrome"),
            patch.dict(windows_frameless._hooks, clear=True),
        ):
            for scale, last_row, content_row, control_last_x, caption_first_x in (
                (1.0, 35, 36, 79, 80),
                (1.25, 44, 45, 99, 100),
                (1.5, 53, 54, 119, 120),
                (2.0, 71, 72, 159, 160),
            ):
                with (
                    self.subTest(scale=scale),
                    patch.object(
                        windows_frameless, "window_dpi_scale", return_value=scale
                    ),
                ):
                    windows_frameless._install_hook(
                        window,
                        windows_frameless.WindowSize(1200, 800),
                        windows_frameless.WindowSize(600, 400),
                    )
                    callback = windows_frameless._hooks[window.uid][0]
                    for x, y, expected in (
                        (400, last_row, 2),
                        (400, content_row, 1),
                        (400, content_row + 8, 1),
                        (control_last_x, 20, 1),
                        (caption_first_x, 20, 2),
                        (1, 1, 13),
                        (1199, 1, 14),
                        (1, 799, 16),
                        (1199, 799, 17),
                        (1, 100, 10),
                        (1199, 100, 11),
                        (400, 1, 12),
                        (400, 799, 15),
                    ):
                        position = ((100 + y) << 16) | (100 + x)
                        self.assertEqual(
                            callback(0x1234, 0x0084, 0, position),
                            expected,
                            f"scale={scale}, relative point=({x}, {y})",
                        )


@unittest.skipUnless(os.name == "nt", "WinForms layout messages require Windows")
class TestMinimizedWindowLayout(unittest.TestCase):
    def setUp(self):
        from arknights_mower.utils import windows_frameless

        self.module = windows_frameless
        self.window = SimpleNamespace(uid="offline-minimized-layout-test")
        self.form = Mock()
        self.user32 = Mock()
        self.user32.GetDpiForWindow = None
        self.user32.GetWindowLongPtrW.return_value = 1
        self.user32.SetWindowLongPtrW.return_value = 1
        self.user32.CallWindowProcW.return_value = 73
        self.user32.IsZoomed.return_value = False
        self.user32.IsIconic.return_value = False
        self.user32.SetWindowPos.return_value = True
        self.rect = (100, 100, 1300, 900)

        def get_window_rect(hwnd, pointer):
            rect = pointer._obj
            rect.left, rect.top, rect.right, rect.bottom = self.rect
            return True

        self.user32.GetWindowRect.side_effect = get_window_rect
        patches = ExitStack()
        self.addCleanup(patches.close)
        for name, value in (
            ("_winforms_hwnd", lambda window: 0x1234),
            ("_winforms_window", lambda window: self.form),
            ("_user32", lambda: self.user32),
            ("_apply_dwm_window_chrome", Mock()),
            ("window_dpi_scale", lambda hwnd: 1),
        ):
            patches.enter_context(patch.object(self.module, name, value))
        patches.enter_context(patch.dict(self.module._hooks, clear=True))
        self.module._install_hook(
            self.window,
            self.module.WindowSize(1200, 800),
            self.module.WindowSize(600, 400),
        )
        self.callback = self.module._hooks[self.window.uid][0]
        self.user32.reset_mock()

    def test_minimized_position_message_suspends_layout_before_native_dispatch(self):
        self.user32.IsIconic.return_value = True
        order = Mock()
        order.attach_mock(self.form.SuspendLayout, "suspend")
        order.attach_mock(self.user32.CallWindowProcW, "dispatch")
        order.attach_mock(self.form.ResumeLayout, "resume")

        def dispatch(original, hwnd, message, w_param, l_param):
            if message == 0x0047:
                self.callback(hwnd, 0x0005, 1, (26 << 16) | 158)
            return 73

        self.user32.CallWindowProcW.side_effect = dispatch

        self.assertEqual(self.callback(0x1234, 0x0047, 0, 0), 73)

        self.assertEqual(
            order.mock_calls,
            [
                call.suspend(),
                call.dispatch(1, 0x1234, 0x0047, 0, 0),
                call.dispatch(1, 0x1234, 0x0005, 1, (26 << 16) | 158),
                call.resume(False),
            ],
        )
        self.user32.GetWindowRect.assert_not_called()
        self.user32.SetWindowPos.assert_not_called()

    def test_visible_position_messages_keep_normal_layout(self):
        for maximized in (False, True):
            with self.subTest(maximized=maximized):
                self.user32.IsZoomed.return_value = maximized
                self.user32.GetWindowRect.reset_mock()
                self.user32.CallWindowProcW.reset_mock()

                self.assertEqual(self.callback(0x1234, 0x0047, 0, 0), 73)

                self.user32.CallWindowProcW.assert_called_once_with(
                    1, 0x1234, 0x0047, 0, 0
                )
                self.form.SuspendLayout.assert_not_called()
                self.form.ResumeLayout.assert_not_called()
                self.assertEqual(self.user32.GetWindowRect.call_count, not maximized)
        self.user32.SetWindowPos.assert_not_called()

    def test_minimizing_a_maximized_window_preserves_the_normal_restore_rect(self):
        self.rect = (200, 150, 1400, 950)
        self.callback(0x1234, 0x0047, 0, 0)
        self.user32.IsZoomed.return_value = True
        self.callback(0x1234, 0x0005, 2, 0)
        self.user32.IsZoomed.return_value = False
        self.user32.IsIconic.return_value = True
        self.rect = (-32000, -32000, -31842, -31974)
        self.callback(0x1234, 0x0047, 0, 0)
        self.callback(0x1234, 0x0005, 1, 0)
        self.user32.IsIconic.return_value = False
        self.user32.IsZoomed.return_value = True
        self.callback(0x1234, 0x0005, 2, 0)
        self.callback(0x1234, 0x0047, 0, 0)
        self.user32.IsZoomed.return_value = False
        self.callback(0x1234, 0x0005, 0, 0)
        self.callback(0x1234, 0x8001, 0, 0)

        self.user32.PostMessageW.assert_called_once_with(0x1234, 0x8001, 0, 0)
        self.user32.SetWindowPos.assert_called_once_with(
            0x1234, None, 200, 150, 1200, 800, 0x0014
        )
        self.form.SuspendLayout.assert_called_once_with()
        self.form.ResumeLayout.assert_called_once_with(False)

    def test_failed_layout_suspension_still_forwards_the_native_message(self):
        self.user32.IsIconic.return_value = True
        self.form.SuspendLayout.side_effect = RuntimeError("Layout unavailable")

        with patch.object(self.module.logger, "exception"):
            self.assertEqual(self.callback(0x1234, 0x0047, 0, 0), 73)

        self.user32.CallWindowProcW.assert_called_once_with(1, 0x1234, 0x0047, 0, 0)
        self.form.ResumeLayout.assert_not_called()

    def test_failed_layout_resume_does_not_repeat_the_native_message(self):
        self.user32.IsIconic.return_value = True
        self.form.ResumeLayout.side_effect = RuntimeError("Layout unavailable")

        with patch.object(self.module.logger, "exception") as log_error:
            self.assertEqual(self.callback(0x1234, 0x0047, 0, 0), 73)

        self.form.SuspendLayout.assert_called_once_with()
        self.form.ResumeLayout.assert_called_once_with(False)
        self.user32.CallWindowProcW.assert_called_once_with(1, 0x1234, 0x0047, 0, 0)
        log_error.assert_called_once()

    def test_native_dispatch_failure_still_releases_layout_suspension(self):
        self.user32.IsIconic.return_value = True
        self.user32.CallWindowProcW.side_effect = [RuntimeError("Dispatch failed"), 73]

        with patch.object(self.module.logger, "exception"):
            self.assertEqual(self.callback(0x1234, 0x0047, 0, 0), 73)

        self.form.SuspendLayout.assert_called_once_with()
        self.form.ResumeLayout.assert_called_once_with(False)


@unittest.skipUnless(os.name == "nt", "DWM window attributes require Windows")
class TestDwmWindowChrome(unittest.TestCase):
    def setUp(self):
        from arknights_mower.utils import windows_frameless

        self.module = windows_frameless

    def test_requests_native_rounded_corners_and_system_border_color(self):
        set_attribute = Mock(return_value=0)
        dwmapi = SimpleNamespace(DwmSetWindowAttribute=set_attribute)

        with patch.object(self.module.ctypes, "WinDLL", return_value=dwmapi):
            self.module._apply_dwm_window_chrome(0x1234)

        self.assertEqual(
            [
                (call.args[0], call.args[1], call.args[2]._obj.value, call.args[3])
                for call in set_attribute.call_args_list
            ],
            [(0x1234, 33, 2, 4), (0x1234, 34, 0xFFFFFFFF, 4)],
        )

    def test_rejected_corner_preference_does_not_prevent_border_request(self):
        set_attribute = Mock(side_effect=[-2147024809, 0])
        dwmapi = SimpleNamespace(DwmSetWindowAttribute=set_attribute)

        with patch.object(self.module.ctypes, "WinDLL", return_value=dwmapi):
            self.module._apply_dwm_window_chrome(0x1234)

        self.assertEqual(set_attribute.call_count, 2)
        border_request = set_attribute.call_args
        self.assertEqual(border_request.args[1], 34)
        self.assertEqual(border_request.args[2]._obj.value, 0xFFFFFFFF)

    def test_unsupported_attributes_leave_window_setup_available(self):
        set_attribute = Mock(return_value=-2147024809)
        dwmapi = SimpleNamespace(DwmSetWindowAttribute=set_attribute)

        with patch.object(self.module.ctypes, "WinDLL", return_value=dwmapi):
            self.assertIsNone(self.module._apply_dwm_window_chrome(0x1234))

        self.assertEqual(set_attribute.call_count, 2)

    def test_missing_library_or_entrypoint_leave_window_setup_available(self):
        for library_result in (OSError("unavailable"), SimpleNamespace()):
            with self.subTest(library_result=library_result):
                if isinstance(library_result, OSError):
                    library = patch.object(
                        self.module.ctypes, "WinDLL", side_effect=library_result
                    )
                else:
                    library = patch.object(
                        self.module.ctypes, "WinDLL", return_value=library_result
                    )
                with library:
                    self.assertIsNone(self.module._apply_dwm_window_chrome(0x1234))


class TestDesktopWindowMinSize(unittest.TestCase):
    def test_default_minimum_size_for_standard_work_area(self):
        from unittest.mock import patch

        from arknights_mower.utils import window_shell
        from arknights_mower.utils.window_shell import (
            WindowSize,
            configured_desktop_window_size,
            desktop_window_min_size,
        )

        with patch.object(
            window_shell, "_screen_work_area", return_value=WindowSize(1920, 1040)
        ):
            size = desktop_window_min_size()
            self.assertEqual(size, WindowSize(600, 400))

        with patch.object(
            window_shell, "_screen_work_area", return_value=WindowSize(1000, 800)
        ):
            size = desktop_window_min_size()
            self.assertEqual(size, WindowSize(350, 320))

        with patch.object(
            window_shell, "_screen_work_area", return_value=WindowSize(1920, 1040)
        ):
            # Smaller than minimum: clamped to (600, 400)
            size = configured_desktop_window_size(WindowSize(450, 350))
            self.assertEqual(size, WindowSize(600, 400))

            # Larger than minimum: preserved
            size = configured_desktop_window_size(WindowSize(800, 600))
            self.assertEqual(size, WindowSize(800, 600))


if __name__ == "__main__":
    unittest.main()
