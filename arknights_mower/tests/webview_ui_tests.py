import tempfile
import unittest
from pathlib import Path
from unittest import mock

from arknights_mower.utils.config import gui
from webview_ui import (
    _LINUX_WEBVIEW_INSTALL_HINT,
    DEFAULT_WINDOW_SIZE,
    MIN_WINDOW_SIZE,
    linux_webview_backend_error,
    resolve_window_size,
    sanitize_window_size,
)


class TestLinuxWebviewBackendError(unittest.TestCase):
    def test_non_linux_platform_returns_none(self):
        # 后端检查只在 Linux 上生效；其它平台直接放行，避免在 macOS/Windows 误触发。
        with mock.patch("webview_ui.platform.system", return_value="Windows"):
            self.assertIsNone(linux_webview_backend_error())
        with mock.patch("webview_ui.platform.system", return_value="Darwin"):
            self.assertIsNone(linux_webview_backend_error())

    def test_linux_without_backend_returns_hint(self):
        # 显式让两个后端都导入失败，无论开发机是否装了 webview/gi/qtpy，断言都确定
        # 成立，避免在配好依赖的 Linux 机器上跑单测时误报失败。
        with (
            mock.patch("webview_ui.platform.system", return_value="Linux"),
            mock.patch(
                "builtins.__import__", side_effect=ImportError("backend unavailable")
            ),
        ):
            self.assertEqual(linux_webview_backend_error(), _LINUX_WEBVIEW_INSTALL_HINT)

    def test_install_hint_covers_each_distro(self):
        # 提示文案必须覆盖三个发行版的具体安装命令，缺库时用户能照着安装。
        hint = _LINUX_WEBVIEW_INSTALL_HINT
        self.assertIn("libwebkit2gtk-4.1-0", hint)
        self.assertIn("gir1.2-webkit2-4.1", hint)
        self.assertIn("webkit2gtk4.1", hint)
        self.assertIn("gi-girepository", hint)
        self.assertIn("webkit2gtk-4.1", hint)
        self.assertIn("sudo apt install", hint)
        self.assertIn("sudo dnf install", hint)
        self.assertIn("sudo pacman -S", hint)


class TestSanitizeWindowSize(unittest.TestCase):
    def test_valid_size_kept(self):
        self.assertEqual(sanitize_window_size(1450, 850), (1450, 850))

    def test_zero_size_ignored(self):
        # WebView2 销毁路径的残留事件：0x0 不得进入窗口尺寸
        self.assertIsNone(sanitize_window_size(0, 0))

    def test_tiny_width_ignored(self):
        self.assertIsNone(sanitize_window_size(50, 850))

    def test_tiny_height_ignored(self):
        self.assertIsNone(sanitize_window_size(1450, 30))

    def test_boundary_min_kept(self):
        self.assertEqual(
            sanitize_window_size(MIN_WINDOW_SIZE, MIN_WINDOW_SIZE),
            (MIN_WINDOW_SIZE, MIN_WINDOW_SIZE),
        )

    def test_below_min_ignored(self):
        self.assertIsNone(sanitize_window_size(MIN_WINDOW_SIZE - 1, 850))

    def test_non_numeric_ignored(self):
        self.assertIsNone(sanitize_window_size("tiny", 850))

    def test_non_finite_ignored(self):
        # int(inf) 抛 OverflowError，同样视为损坏尺寸
        self.assertIsNone(sanitize_window_size(float("inf"), 850))
        self.assertIsNone(sanitize_window_size(float("-inf"), 850))


class TestResolveWindowSize(unittest.TestCase):
    def test_valid_conf_size_kept(self):
        self.assertEqual(resolve_window_size(1450, 850), (1450, 850))

    def test_broken_conf_falls_back_to_default(self):
        # conf.yml 已被旧 bug 写坏（极小/零尺寸）时兜底到默认启动尺寸
        self.assertEqual(resolve_window_size(0, 0), DEFAULT_WINDOW_SIZE)
        self.assertEqual(resolve_window_size(50, 850), DEFAULT_WINDOW_SIZE)
        self.assertEqual(resolve_window_size("tiny", 850), DEFAULT_WINDOW_SIZE)

    def test_non_finite_conf_falls_back_to_default(self):
        self.assertEqual(resolve_window_size(float("inf"), 850), DEFAULT_WINDOW_SIZE)


class TestGuiWindowSize(unittest.TestCase):
    def test_missing_file_returns_none(self):
        # gui.yml 还不存在（首次运行）→ 返回 None，由调用方兜底默认尺寸。
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                self.assertIsNone(gui.load_window_size())

    def test_save_then_load_roundtrip(self):
        # 存进去的尺寸能原样读回，验证读写都落在 gui.yml 上。
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                gui.save_window_size((1600, 900))
                self.assertEqual(gui.load_window_size(), (1600, 900))

    def test_corrupt_content_returns_none(self):
        # 内容非法（宽为非数字）→ 返回 None，不把坏值传出去。
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "gui.yml"
            p.write_text("width: abc\nheight: 900\n", encoding="utf-8")
            with mock.patch.object(gui, "gui_path", p):
                self.assertIsNone(gui.load_window_size())


if __name__ == "__main__":
    unittest.main()
