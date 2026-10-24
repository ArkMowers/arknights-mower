import json
import platform
from threading import Event, Lock, Thread, current_thread
from typing import Any, NamedTuple

from arknights_mower.utils.log import logger
from arknights_mower.utils.window_regions import WindowHitRegions

WINDOW_SHELL_PROTOCOL = "mower-window-shell-v1"
WINDOW_SHELL_EVENT = "mower-window-state"
WINDOW_SHELL_CLOSE_EVENT = "mower-window-close-request"


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
DESKTOP_WINDOW_MIN_WIDTH = 600
DESKTOP_WINDOW_MIN_HEIGHT = 400
DESKTOP_WINDOW_MIN_SIZE = WindowSize(
    DESKTOP_WINDOW_MIN_WIDTH, DESKTOP_WINDOW_MIN_HEIGHT
)
DESKTOP_WINDOW_TITLEBAR_HEIGHT = 36
DESKTOP_WINDOW_CONTROLS_WIDTH = 46 * 3
DESKTOP_WINDOW_SIDEBAR_CONTROL_WIDTH = 80

_SPI_GETWORKAREA = 0x0030

_BACKGROUND_COLORS = {
    "light": "#FAF9F7",
    "dark": "#18181C",
}

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
        from arknights_mower.utils.window_backend import screen_work_area

        area = screen_work_area()
        if area is not None:
            width, height = area
            if width > 0 and height > 0:
                _WORK_AREA_CACHE = WindowSize(width, height)
                return _WORK_AREA_CACHE
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
    except Exception:
        pass
    return None


def desktop_window_min_size() -> WindowSize:
    """Return the shell minimum footprint within the current display work area.

    To support tiling and Windows Snap (1/2, 1/3, 1/4 screen layouts) across
    different resolutions and DPI scaling factors, the base minimum size is
    (600, 400), clamped so it never exceeds 35% of the screen work area width
    and 40% of the height on smaller displays or virtual machines.
    """
    work_area = _screen_work_area()
    if work_area and work_area.width > 0 and work_area.height > 0:
        return WindowSize(
            min(DESKTOP_WINDOW_MIN_WIDTH, max(300, int(work_area.width * 0.35))),
            min(DESKTOP_WINDOW_MIN_HEIGHT, max(300, int(work_area.height * 0.4))),
        )
    return DESKTOP_WINDOW_MIN_SIZE


def configured_desktop_window_size(size: WindowSize) -> WindowSize:
    """Return the configured startup size within the shell minimum and the display."""
    min_size = desktop_window_min_size()
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
    """Keep Restore visibly smaller than Maximize on small work areas."""
    work_area = _screen_work_area()
    if work_area is None:
        return configured_desktop_window_size(
            WindowSize(DESKTOP_WINDOW_WIDTH, DESKTOP_WINDOW_HEIGHT)
        )
    return configured_desktop_window_size(
        WindowSize(
            min(DESKTOP_WINDOW_WIDTH, round(work_area.width * 0.8)),
            min(DESKTOP_WINDOW_HEIGHT, round(work_area.height * 0.9)),
        )
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
        tray_enabled: bool = True,
        backend: str | None = None,
        managed: bool = False,
    ):
        self._window = window
        self._tray_enabled = tray_enabled
        self._managed = managed
        self._platform = normalize_platform(system)
        self._backend = backend or {
            "windows": "winforms",
            "macos": "cocoa",
            "linux": "gtk",
        }.get(self._platform)
        self._native = None
        self._regions = WindowHitRegions()
        self._ready = self._backend == "winforms" or self._backend is None
        self._ready_event = Event()
        if self._ready:
            self._ready_event.set()
        self._disposed = False
        self._pending_state = Event()
        self._pending_close = Event()
        self._close_listener_ready = False
        self._direct_close = False
        self._page_loaded = False
        self._worker = None
        self.on_mode_changed = None
        self.on_ready = None
        self._last_mode = None
        self._lock = Lock()
        self._state = {
            "state": "normal",
            "maximized": False,
            "minimized": False,
            "width": initial_size.width,
            "height": initial_size.height,
        }

    def minimize(self) -> bool:
        if self._native is not None and hasattr(self._native, "minimize"):
            return self._call_native("minimize")
        return self._call_window("minimize")

    def maximize(self) -> bool:
        if self._native is not None:
            return self._call_native("maximize")
        return self._call_window("maximize")

    def restore(self) -> bool:
        if self._native is not None:
            return self._call_native("restore")
        return self._call_window("restore")

    def initialize_native(self):
        """Attach input handlers after pywebview has created its native window."""
        if self._ready or self._disposed:
            return
        actual = getattr(getattr(self._window, "gui", None), "__name__", "")
        backend = actual.rsplit(".", 1)[-1] if actual else self._backend
        self._backend = backend
        from arknights_mower.utils.window_backend import create_native_window

        try:
            self._native = create_native_window(
                backend, self._window, self._regions, self._pending_state.set
            )
            if self._native.install() is False:
                raise RuntimeError("Native title bar installation failed")
        except Exception:
            logger.exception("Native title bar support could not be installed")
            if self._native is not None:
                # Each adapter releases a partially installed input handler.
                # Closing the whole adapter here would also retire controls
                # that are still needed if restoring decorations fails.
                if self._native.capabilities["enabled"]:
                    try:
                        self._native.fallback_decorations()
                    except Exception:
                        logger.exception(
                            "Native window decorations could not be restored"
                        )
        finally:
            self._ready = True
            self._ready_event.set()
        if self._disposed:
            if self._native is not None:
                self._native.dispose()
            return
        self._worker = Thread(target=self._publish_native_changes, daemon=True)
        self._worker.start()
        self._pending_state.set()
        if self.on_ready is not None and self._window.events.loaded.is_set():
            self.on_ready()

    def wait_until_ready(self, timeout=5):
        return self._ready_event.wait(timeout)

    def _publish_native_changes(self):
        # Native GUI callbacks only set this event. A single worker coalesces
        # changes so evaluate_js never waits for its own GUI thread.
        while True:
            self._pending_state.wait()
            self._pending_state.clear()
            if self._disposed:
                return
            try:
                if (
                    self._close_listener_ready
                    and self._pending_close.is_set()
                    and (self._page_loaded or self._window.events.loaded.is_set())
                ):
                    event = json.dumps(WINDOW_SHELL_CLOSE_EVENT)
                    accepted = self._window.evaluate_js(
                        f"!window.dispatchEvent(new CustomEvent({event}, "
                        "{cancelable: true}));"
                    )
                    # A reloaded page may not have installed its listener yet.
                    # Keep the request until that listener acknowledges delivery.
                    if accepted is True:
                        self._pending_close.clear()
                self._publish_state()
            except Exception:
                logger.exception("Native window state could not be published")

    def dispose(self):
        self._disposed = True
        self._pending_state.set()
        self._regions.update({"width": 1, "height": 1, "regions": []})
        if self._native is not None:
            self._native.dispose()
        if self._worker is not None and self._worker is not current_thread():
            self._worker.join(timeout=1)

    def _call_native(self, operation):
        try:
            return getattr(self._native, operation)() is True
        except Exception:
            logger.exception("Native desktop window command failed: %s", operation)
            return False

    def _capabilities(self):
        if self._native is not None:
            return dict(self._native.capabilities)
        return {
            "enabled": self._backend is not None,
            "move": "bridge" if self._backend == "winforms" else "native",
            "resize": "native" if self._backend == "cocoa" else "html",
        }

    def set_hit_regions(self, payload):
        if self._disposed:
            return False
        return self._regions.update(payload)

    def close(self) -> bool:
        self._direct_close = True
        self._window.confirm_close = False
        if self._call_window("destroy"):
            return True
        self._direct_close = False
        return False

    def request_native_close(self) -> bool:
        if (
            self._disposed
            or self._direct_close
            or self._managed
            or self._backend != "cocoa"
        ):
            return False
        self._pending_close.set()
        self._pending_state.set()
        return True

    def ready_for_native_close(self) -> bool:
        if self._disposed or self._backend != "cocoa":
            return False
        self._close_listener_ready = True
        self._pending_state.set()
        return True

    def get_normal_size(self) -> WindowSize | None:
        if self._native is None:
            return None
        try:
            size = self._native.get_normal_size()
            return WindowSize(*size) if size is not None else None
        except Exception:
            logger.debug("Native window size probe unavailable", exc_info=True)
            return None

    def _on_loaded(self):
        self._page_loaded = True
        self._request_publish()

    def get_close_preference(self) -> dict:
        if self._managed:
            return {"managed": True, "tray_enabled": False}
        from arknights_mower.utils.config.gui import load_close_preference

        return {**load_close_preference(), "tray_enabled": self._tray_enabled}

    def set_close_preference(self, choice: str, remember: bool) -> bool:
        from arknights_mower.utils.config.gui import save_close_preference

        if choice == "tray" and not self._tray_enabled:
            raise ValueError("System tray is disabled")
        return save_close_preference(choice, remember)

    def get_window_launch_mode(self) -> str:
        from arknights_mower.utils.config.gui import load_window_launch_mode

        return load_window_launch_mode()

    def set_window_launch_mode(self, mode: str) -> bool:
        from arknights_mower.utils.config.gui import save_window_launch_mode

        return save_window_launch_mode(mode)

    def start_move(self) -> bool:
        """Hand a title bar press to the shell so it runs the drag itself.

        The call returns only once the user lets go of the button, because the
        shell's move loop owns the mouse for the whole drag.
        """
        if self._backend != "winforms":
            return False
        try:
            from arknights_mower.utils.windows_frameless import (
                begin_windows_move,
            )

            return begin_windows_move(self._window)
        except Exception:
            logger.exception("Desktop window move could not start")
            return False

    def start_resize(self, edge: str) -> bool:
        if self._backend != "winforms":
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
        # The initial maximize event can arrive before Vue registers its
        # listener. A query must reflect the actual native window, not that
        # potentially stale event cache.
        native_state_confirmed = False
        if self._native is not None:
            try:
                state = self._native.get_state()
                if state in ("normal", "maximized", "minimized"):
                    native_state_confirmed = True
                    with self._lock:
                        self._state.update(
                            state=state,
                            maximized=state == "maximized",
                            minimized=state == "minimized",
                        )
            except Exception:
                logger.debug("Native window state probe unavailable", exc_info=True)
        elif self._backend == "winforms":
            try:
                import ctypes
                from ctypes import wintypes

                from arknights_mower.utils.windows_frameless import _winforms_hwnd

                handle = _winforms_hwnd(self._window)
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                user32.IsWindow.argtypes = [wintypes.HWND]
                user32.IsWindow.restype = wintypes.BOOL
                user32.IsIconic.argtypes = [wintypes.HWND]
                user32.IsIconic.restype = wintypes.BOOL
                user32.IsZoomed.argtypes = [wintypes.HWND]
                user32.IsZoomed.restype = wintypes.BOOL
                if user32.IsWindow(handle):
                    native_state_confirmed = True
                    state = (
                        "minimized"
                        if user32.IsIconic(handle)
                        else "maximized"
                        if user32.IsZoomed(handle)
                        else "normal"
                    )
                    with self._lock:
                        self._state.update(
                            state=state,
                            maximized=state == "maximized",
                            minimized=state == "minimized",
                        )
            except Exception:
                logger.debug("Native window state probe unavailable", exc_info=True)
        with self._lock:
            return {
                "protocol": WINDOW_SHELL_PROTOCOL,
                **self._state,
                "capabilities": self._capabilities(),
                "native_state_confirmed": native_state_confirmed,
            }

    def get_platform(self) -> dict[str, Any]:
        if not self._ready:
            raise RuntimeError("Native window is still initializing")
        return {
            "protocol": WINDOW_SHELL_PROTOCOL,
            "event": WINDOW_SHELL_EVENT,
            "close_event": WINDOW_SHELL_CLOSE_EVENT,
            "platform": self._platform,
            "capabilities": self._capabilities(),
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
        self._request_publish()

    def _on_maximized(self) -> None:
        self._set_native_state("maximized")

    def _on_minimized(self) -> None:
        self._set_native_state("minimized")

    def _on_restored(self) -> None:
        self._set_native_state("normal")

    def _on_resized(self, width: int, height: int) -> None:
        with self._lock:
            self._state.update(width=int(width), height=int(height))
        self._request_publish()

    def _request_publish(self):
        if self._disposed:
            return
        if self._backend != "winforms":
            self._pending_state.set()
        else:
            self._publish_state()

    def _publish_state(self) -> None:
        if self._disposed:
            return
        if self._backend != "winforms" and not (
            self._page_loaded or self._window.events.loaded.is_set()
        ):
            return
        state = self.get_window_state()
        mode = state["state"]
        if (
            state["native_state_confirmed"]
            and mode in ("normal", "maximized")
            and mode != self._last_mode
        ):
            self._last_mode = mode
            if self.on_mode_changed is not None:
                try:
                    self.on_mode_changed(mode)
                except Exception:
                    logger.exception("Desktop window mode could not be saved")
        payload = json.dumps(state, ensure_ascii=False)
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
    tray_enabled: bool = True,
    backend: str | None = None,
    managed: bool = False,
) -> WindowShellBridge:
    bridge = WindowShellBridge(
        window, system, initial_size, tray_enabled, backend, managed
    )

    # pywebview 5.1 Window.expose only serializes the functions passed here.
    # Never pass the bridge or Window object itself to js_api.
    window.expose(
        bridge.minimize,
        bridge.maximize,
        bridge.restore,
        bridge.close,
        bridge.start_move,
        bridge.start_resize,
        bridge.get_window_state,
        bridge.get_platform,
        bridge.ready_for_native_close,
        bridge.set_hit_regions,
        bridge.get_close_preference,
        bridge.set_close_preference,
        bridge.get_window_launch_mode,
        bridge.set_window_launch_mode,
    )

    window.events.maximized += bridge._on_maximized
    window.events.minimized += bridge._on_minimized
    window.events.restored += bridge._on_restored
    window.events.resized += bridge._on_resized
    window.events.shown += bridge.initialize_native
    window.events.loaded += bridge._on_loaded
    window.events.closed += bridge.dispose
    return bridge
