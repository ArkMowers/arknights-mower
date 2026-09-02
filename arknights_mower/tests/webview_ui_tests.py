import unittest
from unittest import mock

from webview_ui import (
    _LINUX_WEBVIEW_INSTALL_HINT,
    linux_webview_backend_error,
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


if __name__ == "__main__":
    unittest.main()
