import json
import logging
import platform
from threading import Lock
from typing import Any, NamedTuple

WINDOW_SHELL_PROTOCOL = "mower-window-shell-v1"
WINDOW_SHELL_EVENT = "mower-window-state"


class WindowSize(NamedTuple):
    """A desktop window footprint in logical pixels."""

    width: int
    height: int


class WindowRatio(NamedTuple):
    """A desktop window footprint as a fraction of the screen work area."""

    width: float
    height: float


DESKTOP_WINDOW_WIDTH = 1450
DESKTOP_WINDOW_HEIGHT = 850
DESKTOP_WINDOW_MIN_SIZE = WindowSize(1024, 640)
DESKTOP_WINDOW_TITLEBAR_HEIGHT = 36
DESKTOP_WINDOW_CONTROLS_WIDTH = 46 * 3
DESKTOP_WINDOW_SIDEBAR_CONTROL_WIDTH = 44

_SPI_GETWORKAREA = 0x0030

_BACKGROUND_COLORS = {
    "light": "#FAF9F7",
    "dark": "#18181C",
}

logger = logging.getLogger(__name__)

# Cached after the first successful probe: it is read before the window exists
# (the process is not yet DPI-aware, so Windows returns *logical* pixels), and
# every later open/save sizing reuses that same logical area instead of
# re-probing under a has-changed DPI-awareness and mixing logical with physical.
_WORK_AREA_CACHE: WindowSize | None = None


def window_background_color(theme: str) -> str:
    return _BACKGROUND_COLORS.get(theme, _BACKGROUND_COLORS["light"])


def is_windows(system: str | None = None) -> bool:
    """True when the running (or supplied) platform resolves to Windows."""
    return normalize_platform(system) == "windows"


def window_dpi_scale(hwnd: int) -> float:
    """Return the display scale factor (1.0, 1.25, 1.5, ...) for a native window handle.

    ``GetDpiForWindow`` only exists on Windows 10 1607+, and the process reports a
    meaningful DPI only once it is DPI-aware, so callers read this after the window
    exists. A missing API or a failed probe resolves to a neutral scale of 1.0.
    """
    try:
        import ctypes
        from ctypes import wintypes

        get_dpi = getattr(ctypes.windll.user32, "GetDpiForWindow", None)
        if get_dpi is None:
            return 1.0
        get_dpi.argtypes = [wintypes.HWND]
        get_dpi.restype = wintypes.UINT
        raw = int(get_dpi(hwnd))
        return max(raw / 96.0, 1.0) if raw else 1.0
    except Exception:
        return 1.0


def _screen_work_area() -> WindowSize | None:
    """Primary display work area; None when it cannot be detected."""
    global _WORK_AREA_CACHE
    if _WORK_AREA_CACHE is not None:
        return _WORK_AREA_CACHE
    try:
        if is_windows():
            import ctypes
            from ctypes import wintypes

            rect = wintypes.RECT()
            if ctypes.windll.user32.SystemParametersInfoW(
                _SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
            ):
                width = rect.right - rect.left
                height = rect.bottom - rect.top
                if width > 0 and height > 0:
                    _WORK_AREA_CACHE = WindowSize(width, height)
                    return _WORK_AREA_CACHE
        else:
            import tkinter as tk

            root = tk.Tk()
            try:
                root.withdraw()
                width = root.winfo_screenwidth()
                height = root.winfo_screenheight()
            finally:
                root.destroy()
            if width > 0 and height > 0:
                _WORK_AREA_CACHE = WindowSize(width, height)
                return _WORK_AREA_CACHE
    except Exception:
        pass
    return None


def configured_desktop_window_size(size: WindowSize) -> WindowSize:
    """Return the configured startup size within the shell minimum and the display."""
    min_size = DESKTOP_WINDOW_MIN_SIZE
    work_area = _screen_work_area()
    if work_area:
        max_width, max_height = work_area.width, work_area.height
    else:
        max_width = max_height = float("inf")
    return WindowSize(
        min(max(int(size.width), min_size.width), max_width),
        min(max(int(size.height), min_size.height), max_height),
    )


def default_desktop_window_size() -> WindowSize:
    """Return the default startup footprint for the shell within the display."""
    return configured_desktop_window_size(
        WindowSize(DESKTOP_WINDOW_WIDTH, DESKTOP_WINDOW_HEIGHT)
    )


def window_size_from_ratio(ratio: WindowRatio) -> WindowSize:
    """Derive a logical window size from a fraction of the screen work area, then
    clamp it to the shell minimum and the current display. A user-stored ratio is
    kept proportional, so a window enlarged on a large display round-trips on the
    next launch instead of snapping back to the fixed default footprint."""
    work_area = _screen_work_area()
    if work_area:
        width = round(work_area.width * ratio.width)
        height = round(work_area.height * ratio.height)
    else:
        width, height = DESKTOP_WINDOW_WIDTH, DESKTOP_WINDOW_HEIGHT
    return configured_desktop_window_size(WindowSize(width, height))


def ratio_from_window_size(size: WindowSize) -> WindowRatio | None:
    """Fraction of the screen work area the window currently occupies; None when
    the work area cannot be detected (caller then keeps the previous value)."""
    work_area = _screen_work_area()
    if not work_area or work_area.width <= 0 or work_area.height <= 0:
        return None
    return WindowRatio(size.width / work_area.width, size.height / work_area.height)


def normalize_platform(system: str | None = None) -> str:
    current = (system or platform.system()).lower()
    return {
        "windows": "windows",
        "darwin": "macos",
        "macos": "macos",
        "linux": "linux",
    }.get(current, "unsupported")


class WindowShellBridge:
    """The complete and intentionally small API exposed to the desktop WebUI."""

    def __init__(
        self,
        window: Any,
        system: str | None = None,
        initial_size: WindowSize = WindowSize(
            DESKTOP_WINDOW_WIDTH, DESKTOP_WINDOW_HEIGHT
        ),
    ):
        self._window = window
        self._platform = normalize_platform(system)
        self._lock = Lock()
        self._state = {
            "state": "normal",
            "maximized": False,
            "minimized": False,
            "width": initial_size.width,
            "height": initial_size.height,
        }

    def minimize(self) -> bool:
        return self._call_window("minimize")

    def maximize(self) -> bool:
        return self._call_window("maximize")

    def restore(self) -> bool:
        return self._call_window("restore")

    def close(self) -> bool:
        # The custom titlebar follows direct-close behavior for this iteration;
        # the existing tray lifecycle remains owned by webview_ui.
        self._window.confirm_close = False
        return self._call_window("destroy")

    def start_resize(self, edge: str) -> bool:
        if self._platform != "windows":
            return False
        try:
            from arknights_mower.utils.windows_frameless import (
                begin_windows_resize,
            )

            return begin_windows_resize(self._window, edge)
        except Exception:
            logger.exception("Desktop window resize could not start: %s", edge)
            return False

    def get_window_state(self) -> dict[str, Any]:
        with self._lock:
            return {"protocol": WINDOW_SHELL_PROTOCOL, **self._state}

    def get_platform(self) -> dict[str, str]:
        return {
            "protocol": WINDOW_SHELL_PROTOCOL,
            "event": WINDOW_SHELL_EVENT,
            "platform": self._platform,
        }

    def _call_window(self, method_name: str) -> bool:
        try:
            getattr(self._window, method_name)()
            return True
        except Exception:
            logger.exception("Desktop window command failed: %s", method_name)
            return False

    def _set_native_state(self, state: str) -> None:
        with self._lock:
            self._state.update(
                state=state,
                maximized=state == "maximized",
                minimized=state == "minimized",
            )
        self._publish_state()

    def _on_maximized(self) -> None:
        self._set_native_state("maximized")

    def _on_minimized(self) -> None:
        self._set_native_state("minimized")

    def _on_restored(self) -> None:
        self._set_native_state("normal")

    def _on_resized(self, width: int, height: int) -> None:
        with self._lock:
            self._state.update(width=int(width), height=int(height))
        self._publish_state()

    def _publish_state(self) -> None:
        payload = json.dumps(self.get_window_state(), ensure_ascii=False)
        event_name = json.dumps(WINDOW_SHELL_EVENT)
        script = (
            f"window.dispatchEvent(new CustomEvent({event_name}, "
            f"{{ detail: {payload} }}));"
        )
        try:
            self._window.evaluate_js(script)
        except Exception:
            # Native state remains authoritative even if the page is still
            # loading or has already gone away.
            logger.debug("Window state event could not be delivered", exc_info=True)


def attach_window_shell(
    window: Any,
    system: str | None = None,
    initial_size: WindowSize = WindowSize(DESKTOP_WINDOW_WIDTH, DESKTOP_WINDOW_HEIGHT),
) -> WindowShellBridge:
    bridge = WindowShellBridge(window, system, initial_size)

    # pywebview 5.1 Window.expose only serializes the functions passed here.
    # Never pass the bridge or Window object itself to js_api.
    window.expose(
        bridge.minimize,
        bridge.maximize,
        bridge.restore,
        bridge.close,
        bridge.start_resize,
        bridge.get_window_state,
        bridge.get_platform,
    )

    window.events.maximized += bridge._on_maximized
    window.events.minimized += bridge._on_minimized
    window.events.restored += bridge._on_restored
    window.events.resized += bridge._on_resized
    return bridge
