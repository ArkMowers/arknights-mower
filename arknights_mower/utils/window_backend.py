"""Select the pywebview backend before choosing frameless window behavior."""

import os
import platform

from arknights_mower.utils.log import logger

_SELECTED_BACKEND = None
SUPPORTED_BACKENDS = frozenset(("winforms", "cocoa", "gtk", "qt"))


def prepare_window_backend():
    global _SELECTED_BACKEND
    # Keep Windows work-area detection ahead of WebView2's DPI initialization.
    if (
        platform.system() == "Windows"
        and os.environ.get("PYWEBVIEW_GUI", "").lower() != "qt"
    ):
        _SELECTED_BACKEND = "winforms"
    else:
        from webview.guilib import initialize

        backend = initialize()
        _SELECTED_BACKEND = backend.__name__.rsplit(".", 1)[-1]
    return _SELECTED_BACKEND


def screen_work_area():
    """The initial display's available logical area, without a whole-screen guess."""
    try:
        if (
            _SELECTED_BACKEND == "cocoa"
            or platform.system() == "Darwin"
            and _SELECTED_BACKEND is None
        ):
            from AppKit import NSScreen

            screen = NSScreen.mainScreen()
            if screen is not None:
                size = screen.visibleFrame().size
                return int(size.width), int(size.height)
        elif _SELECTED_BACKEND == "qt":
            from qtpy.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            if screen is not None:
                area = screen.availableGeometry()
                return int(area.width()), int(area.height())
        elif _SELECTED_BACKEND == "gtk":
            from gi.repository import Gdk

            display = Gdk.Display.get_default()
            if display is not None:
                monitor = display.get_primary_monitor() or display.get_monitor(0)
                if monitor is not None:
                    area = monitor.get_workarea()
                    return int(area.width), int(area.height)
    except Exception:
        logger.debug("Desktop work area was unavailable", exc_info=True)
    return None


def create_native_window(backend, window, regions, on_state_changed):
    if backend == "cocoa":
        from arknights_mower.utils.cocoa_window import CocoaWindow

        return CocoaWindow(window, regions, on_state_changed)
    if backend in ("gtk", "qt"):
        from arknights_mower.utils.linux_window import GtkWindow, QtWindow

        adapter = GtkWindow if backend == "gtk" else QtWindow
        return adapter(window, regions, on_state_changed)
    raise ValueError("Unsupported native window backend")
