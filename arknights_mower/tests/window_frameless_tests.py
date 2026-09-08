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


if __name__ == "__main__":
    unittest.main()
