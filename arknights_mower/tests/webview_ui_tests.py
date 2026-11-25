import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from arknights_mower import __version__
from arknights_mower.utils.config import gui
from arknights_mower.utils.window_shell import WindowRatio
from webview_ui import (
    _LINUX_WEBVIEW_INSTALL_HINT,
    DEFAULT_WINDOW_SIZE,
    MIN_WINDOW_SIZE,
    linux_webview_backend_error,
    resolve_window_size,
    sanitize_window_size,
    title_version,
    window_title,
)


class TestLinuxWebviewBackendError(unittest.TestCase):
    def test_non_linux_platform_returns_none(self):
        with mock.patch("webview_ui.subprocess.run") as launch:
            for system in ("Windows", "Darwin"):
                with mock.patch("webview_ui.platform.system", return_value=system):
                    self.assertIsNone(linux_webview_backend_error())
            launch.assert_not_called()

    def test_real_probe_imports_backends_in_child_in_desktop_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            modules = root / "webview/platforms"
            modules.mkdir(parents=True)
            (modules.parent / "__init__.py").touch()
            (modules / "__init__.py").touch()
            record = root / "imports"
            for backend, error in (("gtk", "ValueError"), ("qt", "ImportError")):
                (modules / f"{backend}.py").write_text(
                    "import os\n"
                    "from pathlib import Path\n"
                    "with Path(os.environ['PROBE_RECORD']).open('a') as stream:\n"
                    f"    print(os.getpid(), '{backend}', file=stream)\n"
                    f"if '{backend}' != os.environ['AVAILABLE_BACKEND']:\n"
                    f"    raise {error}('unavailable')\n"
                )
            for gui, kde, available, expected in (
                ("", False, "qt", ["gtk", "qt"]),
                ("", True, "qt", ["qt"]),
                ("gtk", True, "gtk", ["gtk"]),
                ("qt", False, "", ["qt", "gtk"]),
            ):
                with (
                    self.subTest(gui=gui, kde=kde, available=available),
                    mock.patch("webview_ui.platform.system", return_value="Linux"),
                    mock.patch.dict(
                        os.environ,
                        PYTHONPATH=temporary,
                        PROBE_RECORD=str(record),
                        AVAILABLE_BACKEND=available or "unavailable",
                        PYWEBVIEW_GUI=gui,
                    ),
                ):
                    if kde:
                        os.environ["KDE_FULL_SESSION"] = "1"
                    else:
                        os.environ.pop("KDE_FULL_SESSION", None)
                    record.unlink(missing_ok=True)
                    self.assertEqual(
                        linux_webview_backend_error(),
                        None if available else _LINUX_WEBVIEW_INSTALL_HINT,
                    )
                    imports = [line.split() for line in record.read_text().splitlines()]
                    self.assertEqual([name for _, name in imports], expected)
                    self.assertTrue(all(int(pid) != os.getpid() for pid, _ in imports))

    def test_frozen_manager_uses_bundled_desktop_probe_and_reports_failures(self):
        manager = Path("/install/多开管理器")
        with (
            mock.patch("webview_ui.platform.system", return_value="Linux"),
            mock.patch.object(sys, "frozen", True, create=True),
            mock.patch.object(sys, "executable", str(manager)),
            mock.patch("webview_ui.subprocess.run") as launch,
        ):
            launch.return_value.returncode = -11
            self.assertIn("-11", linux_webview_backend_error())
            launch.assert_called_once_with(
                [manager.with_name("mower"), "--check-linux-webview-backend"],
                timeout=15,
            )
            launch.side_effect = subprocess.TimeoutExpired("mower", 15)
            self.assertIn("超时", linux_webview_backend_error())
            launch.side_effect = OSError("cannot execute")
            self.assertIn("cannot execute", linux_webview_backend_error())

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


class TestGuiWindowRatio(unittest.TestCase):
    def test_missing_file_returns_none(self):
        # gui.yml 还不存在（首次运行）→ 返回 None，由调用方兜底默认比例。
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                self.assertIsNone(gui.load_window_ratio())

    def test_save_then_load_roundtrip(self):
        # 存进去的比例能原样读回，验证读写都落在 gui.yml 上。
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                gui.save_window_ratio(WindowRatio(0.6, 0.5))
                self.assertEqual(gui.load_window_ratio(), WindowRatio(0.6, 0.5))

    def test_corrupt_content_returns_none(self):
        # 内容非法（宽为非数字）→ 返回 None，不把坏值传出去。
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "gui.yml"
            p.write_text("ratio:\n  width: abc\n  height: 900\n", encoding="utf-8")
            with mock.patch.object(gui, "gui_path", p):
                self.assertIsNone(gui.load_window_ratio())


class TestGuiWindowMode(unittest.TestCase):
    def test_size_and_mode_share_existing_gui_file_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                self.assertEqual(gui.load_window_mode(), "normal")
                gui.save_window_ratio(WindowRatio(0.72, 0.81))
                gui.save_window_mode("maximized")
                self.assertEqual(gui.load_window_ratio(), WindowRatio(0.72, 0.81))
                gui.save_window_ratio(WindowRatio(0.65, 0.75))
                self.assertEqual(gui.load_window_mode(), "maximized")
                self.assertEqual(gui.load_window_ratio(), WindowRatio(0.65, 0.75))

    def test_unknown_window_mode_falls_back_to_normal(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "gui.yml"
            path.write_text("window_mode: invalid\n", encoding="utf-8")
            with mock.patch.object(gui, "gui_path", path):
                self.assertEqual(gui.load_window_mode(), "normal")
                with self.assertRaises(ValueError):
                    gui.save_window_mode("fullscreen")


class TestGuiDesktopPreferences(unittest.TestCase):
    def test_preferences_share_existing_gui_file_without_losing_ratio(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                gui.save_window_ratio(WindowRatio(0.7, 0.8))
                gui.save_window_mode("maximized")
                gui.save_close_preference("exit", True)
                gui.save_window_launch_mode("normal")
                self.assertEqual(gui.load_window_ratio(), WindowRatio(0.7, 0.8))
                self.assertEqual(gui.load_window_mode(), "maximized")
                self.assertEqual(
                    gui.load_close_preference(), {"choice": "exit", "remember": True}
                )
                self.assertEqual(gui.load_window_launch_mode(), "normal")

    def test_invalid_preferences_and_missing_values_have_safe_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(gui, "gui_path", Path(d) / "gui.yml"):
                self.assertEqual(gui.load_window_launch_mode(), "last")
                self.assertEqual(
                    gui.load_close_preference(), {"choice": "tray", "remember": False}
                )
                with self.assertRaises(ValueError):
                    gui.save_close_preference("killall", True)
                with self.assertRaises(ValueError):
                    gui.save_window_launch_mode("fullscreen")


class TestWindowTitle(unittest.TestCase):
    def test_composes_app_and_resource_version(self):
        # 标题 = 应用版本 + 资源包版本 + 实例标识；资源包版本来自 title_version 的尽力读取。
        with mock.patch(
            "webview_ui.title_version", return_value="4.1.6-alpha.3 - 2026.09.05"
        ):
            self.assertEqual(
                window_title("测试", 8080),
                "arknights-mower 4.1.6-alpha.3 - 2026.09.05 - mower@8080(测试)",
            )

    def test_omits_resource_version_when_absent(self):
        # 未装资源包时不显示资源包版本段（title_version 只返回应用版本）。
        with mock.patch("webview_ui.title_version", return_value="4.1.6-alpha.3"):
            self.assertEqual(
                window_title("", 8080),
                "arknights-mower 4.1.6-alpha.3 - mower@8080",
            )

    def test_title_version_appends_resource_when_present(self):
        # 资源包展示版本非空时，title_version 在应用版本后追加资源包版本号。
        with mock.patch(
            "arknights_mower.utils.resource_version.check_resource_update",
            return_value={"current_display": "2026.09.05"},
        ):
            self.assertEqual(title_version(), f"{__version__} - 2026.09.05")

    def test_title_version_omits_resource_when_absent(self):
        # 未装资源包时 title_version 只返回应用版本，不残留空号段。
        with mock.patch(
            "arknights_mower.utils.resource_version.check_resource_update",
            return_value={"current_display": ""},
        ):
            self.assertEqual(title_version(), __version__)

    def test_title_uses_parent_version_instead_of_child_resource_cache(self):
        with mock.patch(
            "arknights_mower.utils.resource_version.check_resource_update",
            side_effect=AssertionError("child resource cache must not override parent"),
        ):
            self.assertEqual(
                window_title("测试", 8080, "2026.09.06"),
                f"arknights-mower {__version__} - 2026.09.06 - mower@8080(测试)",
            )
            self.assertEqual(title_version(""), __version__)

    def test_resource_reload_sends_current_parent_version_to_window(self):
        import server

        conn = mock.Mock()
        with (
            mock.patch("server._webview_conn", return_value=conn),
            mock.patch(
                "arknights_mower.utils.resource_version.check_resource_update",
                return_value={"current_display": "2026.09.06"},
            ),
        ):
            server._request_title_refresh()
        conn.send.assert_called_once_with(("title", "2026.09.06"))


class TestWindowInstanceControls(unittest.TestCase):
    def run_window(self, channel=None, *, wait_for_startup=False, backend_error=None):
        import webview

        import webview_ui
        from arknights_mower.utils import config, path, window_backend, window_shell
        from arknights_mower.utils import manager_instances as controls

        window = mock.MagicMock()
        shell = mock.Mock()
        shell.get_platform.return_value = {"platform": "linux"}
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(path, "global_space", ""),
            mock.patch.object(config, "load_conf"),
            mock.patch.object(config, "conf", SimpleNamespace(theme="light")),
            mock.patch.object(gui, "load_window_ratio", return_value=None),
            mock.patch.object(gui, "load_window_mode", return_value="normal"),
            mock.patch.object(gui, "load_window_launch_mode", return_value="normal"),
            mock.patch.object(
                window_shell,
                "default_desktop_window_size",
                return_value=window_shell.WindowSize(1000, 700),
            ),
            mock.patch.object(
                window_shell,
                "desktop_window_min_size",
                return_value=window_shell.WindowSize(600, 400),
            ),
            mock.patch.object(
                window_backend,
                "prepare_window_backend",
                return_value="gtk",
                side_effect=backend_error,
            ),
            mock.patch.object(window_shell, "attach_window_shell", return_value=shell),
            mock.patch.object(
                window_shell, "ratio_from_window_size", return_value=None
            ),
            mock.patch.object(webview_ui, "title_version", return_value="test-version"),
            mock.patch.object(webview, "create_window", return_value=window),
            mock.patch.object(webview, "start") as start,
            mock.patch("webbrowser.open") as browser,
            mock.patch("threading.Thread"),
            mock.patch.object(
                controls,
                "get_path",
                return_value=Path(directory) / "instances.json",
            ),
            mock.patch.object(
                controls.runtime, "state_dir", return_value=Path(directory) / "runtime"
            ),
        ):
            try:
                webview_ui.webview_window(
                    channel or mock.Mock(),
                    "",
                    "current",
                    "127.0.0.1",
                    58000,
                    "http://local",
                    True,
                    wait_for_startup=wait_for_startup,
                )
            except SystemExit as exit:
                self.assertIsNone(exit.code)
            self.assertFalse((Path(directory) / "instances.json").exists())
            return webview.create_window, start, browser, window, shell

    def test_main_window_does_not_expose_instance_management(self):
        create, start, browser, window, _ = self.run_window()
        start.assert_called_once()
        browser.assert_not_called()
        options = create.call_args.kwargs
        self.assertIs(options.get("draggable"), True)
        self.assertIs(options["easy_drag"], False)
        window.expose.assert_not_called()

    def test_initial_window_and_browser_fallback_require_the_open_command(self):
        for failed_backend in (False, True):
            for result in ("open", "exit", EOFError(), None):
                with self.subTest(failed_backend=failed_backend, result=result):
                    channel = mock.Mock()
                    channel.poll.return_value = result is not None
                    if isinstance(result, Exception):
                        channel.recv.side_effect = result
                    else:
                        channel.recv.return_value = result
                    create, start, browser, _, shell = self.run_window(
                        channel,
                        wait_for_startup=True,
                        backend_error=RuntimeError("no renderer")
                        if failed_backend
                        else None,
                    )
                    channel.poll.assert_called_once()
                    self.assertGreater(channel.poll.call_args.args[0], 0)
                    self.assertEqual(create.call_count, int(not failed_backend))
                    self.assertEqual(
                        start.call_count, int(result == "open" and not failed_backend)
                    )
                    self.assertEqual(
                        browser.call_count, int(result == "open" and failed_backend)
                    )
                    if not failed_backend:
                        shell.dispose.assert_called_once()


if __name__ == "__main__":
    unittest.main()
