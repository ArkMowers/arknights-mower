"""Backend selection and work-area probes use the actual GUI implementation."""

import ctypes
import sys
from importlib import import_module
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import window_backend, window_shell


@pytest.fixture(autouse=True)
def isolate_backend(monkeypatch):
    monkeypatch.setattr(window_backend, "_SELECTED_BACKEND", None)
    monkeypatch.setattr(window_shell, "_WORK_AREA_CACHE", None)


def test_winforms_sizing_precedes_gui_dpi_initialization(monkeypatch):
    guilib = import_module("webview.guilib")
    initialize = Mock(side_effect=AssertionError("WinForms initialized too early"))
    monkeypatch.setattr(guilib, "initialize", initialize)
    monkeypatch.setattr(window_backend.platform, "system", lambda: "Windows")
    monkeypatch.delenv("PYWEBVIEW_GUI", raising=False)
    assert window_backend.prepare_window_backend() == "winforms"
    initialize.assert_not_called()


@pytest.fixture
def windows_work_area(monkeypatch):
    context = SimpleNamespace(value=-2, scale=1.5)

    def probe(action, parameter, output, flags):
        scale = 1 if context.value == -1 else context.scale
        rect = output._obj
        rect.left, rect.top = 0, 0
        rect.right, rect.bottom = round(2000 * scale), round(1000 * scale)
        return True

    user32 = SimpleNamespace(
        GetDpiForSystem=Mock(
            side_effect=lambda: 96 if context.value == -1 else round(96 * context.scale)
        ),
        SystemParametersInfoW=Mock(side_effect=probe),
        IsProcessDPIAware=Mock(return_value=True),
    )
    monkeypatch.setattr(ctypes, "windll", SimpleNamespace(user32=user32), raising=False)
    monkeypatch.setattr(window_backend.platform, "system", lambda: "Windows")
    return context, user32


@pytest.mark.parametrize("awareness", [-1, -2, -4])
@pytest.mark.parametrize("scale", [1, 1.25, 1.5, 2])
def test_windows_reopen_keeps_saved_screen_proportion(
    monkeypatch, tmp_path, windows_work_area, awareness, scale
):
    from arknights_mower.utils.config import gui

    context, user32 = windows_work_area
    context.value = awareness
    context.scale = scale
    monkeypatch.setattr(gui, "gui_path", tmp_path / "gui.yml")
    gui.gui_path.write_text(
        "ui_state_migrated: true\nratio:\n  width: 0.6\n  height: 0.7\n",
        encoding="utf-8",
    )
    for _ in range(3):
        monkeypatch.setattr(window_shell, "_WORK_AREA_CACHE", None)
        size = window_shell.window_size_from_ratio(gui.load_window_ratio())
        assert size == window_shell.WindowSize(1200, 700)
        assert context.value == awareness
        gui.save_window_ratio(window_shell.ratio_from_window_size(size))
        assert gui.load_window_ratio() == window_shell.WindowRatio(0.6, 0.7)
    assert user32.SystemParametersInfoW.call_count == 3


@pytest.mark.parametrize(
    "failure", ["false", "exception", "dpi-zero", "dpi-exception", "dpi-unavailable"]
)
def test_windows_unconfirmed_work_area_is_not_cached(windows_work_area, failure):
    context, user32 = windows_work_area
    if failure == "false":
        user32.SystemParametersInfoW.return_value = False
        user32.SystemParametersInfoW.side_effect = None
    elif failure == "exception":
        user32.SystemParametersInfoW.side_effect = OSError("Display unavailable")
    elif failure == "dpi-zero":
        user32.GetDpiForSystem.side_effect = None
        user32.GetDpiForSystem.return_value = 0
    elif failure == "dpi-exception":
        user32.GetDpiForSystem.side_effect = OSError("DPI unavailable")
    else:
        del user32.GetDpiForSystem
    assert window_shell._screen_work_area() is None
    assert context.value == -2
    assert window_shell._WORK_AREA_CACHE is None


def test_windows_legacy_unaware_work_area_stays_in_logical_pixels(windows_work_area):
    context, user32 = windows_work_area
    context.value = -1
    user32.IsProcessDPIAware.return_value = False
    del user32.GetDpiForSystem
    assert window_shell._screen_work_area() == window_shell.WindowSize(2000, 1000)


def test_linux_uses_the_backend_selected_by_pywebview(monkeypatch):
    guilib = import_module("webview.guilib")
    initialize = Mock(return_value=SimpleNamespace(__name__="webview.platforms.qt"))
    monkeypatch.setattr(guilib, "initialize", initialize)
    monkeypatch.setattr(window_backend.platform, "system", lambda: "Linux")
    assert window_backend.prepare_window_backend() == "qt"
    initialize.assert_called_once_with()


@pytest.mark.parametrize("backend", ["cocoa", "gtk", "qt"])
def test_work_area_uses_available_geometry_and_caches_logical_pixels(
    monkeypatch, backend
):
    monkeypatch.setattr(window_backend, "_SELECTED_BACKEND", backend)
    screen = SimpleNamespace(
        visibleFrame=lambda: SimpleNamespace(
            size=SimpleNamespace(width=1440, height=875)
        ),
        get_workarea=lambda: SimpleNamespace(width=1440, height=875),
        availableGeometry=lambda: SimpleNamespace(
            width=lambda: 1440, height=lambda: 875
        ),
    )
    modules = {
        "AppKit": SimpleNamespace(NSScreen=SimpleNamespace(mainScreen=lambda: screen)),
        "qtpy": ModuleType("qtpy"),
        "qtpy.QtWidgets": SimpleNamespace(
            QApplication=SimpleNamespace(primaryScreen=lambda: screen)
        ),
        "gi": ModuleType("gi"),
        "gi.repository": SimpleNamespace(
            Gdk=SimpleNamespace(
                Display=SimpleNamespace(
                    get_default=lambda: SimpleNamespace(
                        get_primary_monitor=lambda: screen
                    ),
                )
            )
        ),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    assert window_shell._screen_work_area() == window_shell.WindowSize(1440, 875)
    assert window_shell.ratio_from_window_size(window_shell.WindowSize(720, 700)) == (
        0.5,
        0.8,
    )


def test_missing_work_area_does_not_replace_a_saved_proportion(monkeypatch):
    monkeypatch.setattr(window_backend.platform, "system", lambda: "Linux")
    assert (
        window_shell.ratio_from_window_size(window_shell.WindowSize(800, 600)) is None
    )


def test_backend_initialization_failure_keeps_the_browser_fallback(monkeypatch):
    import webbrowser

    import webview

    import webview_ui
    from arknights_mower.utils import config, path

    monkeypatch.setattr(config, "load_conf", lambda: None)
    monkeypatch.setattr(path, "global_space", path.global_space)
    monkeypatch.setattr(
        window_backend,
        "prepare_window_backend",
        Mock(side_effect=RuntimeError("No GUI")),
    )
    open_browser, create_window = Mock(), Mock()
    monkeypatch.setattr(webbrowser, "open", open_browser)
    monkeypatch.setattr(webview, "create_window", create_window)
    url = "http://127.0.0.1:18080/?token=offline-test"
    webview_ui.webview_window(
        None, path.global_space, "Offline", "127.0.0.1", 18080, url, False
    )
    open_browser.assert_called_once_with(url)
    create_window.assert_not_called()
