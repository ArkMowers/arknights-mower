"""Small WinForms adaptation that restores OS-owned frameless resizing.

pywebview 5.1 sets ``FormBorderStyle.None`` for frameless windows, which removes
the native resize frame. This module keeps the window border visually absent,
but restores the standard sizing styles and returns native non-client hit-test
codes at the window edges. Windows still owns the resize loop, DPI handling,
cursor feedback, snapping, and multi-monitor interaction.
"""

import ctypes
import logging
from ctypes import wintypes
from typing import Any

from arknights_mower.utils.window_shell import (
    DESKTOP_WINDOW_CONTROLS_WIDTH,
    DESKTOP_WINDOW_SIDEBAR_CONTROL_WIDTH,
    DESKTOP_WINDOW_TITLEBAR_HEIGHT,
    WindowSize,
    is_windows,
    window_dpi_scale,
)

logger = logging.getLogger(__name__)

_hooks: dict[str, tuple[Any, ...]] = {}

_WS_THICKFRAME = 0x00040000
_WS_MINIMIZEBOX = 0x00020000
_WS_MAXIMIZEBOX = 0x00010000
_WS_SYSMENU = 0x00080000
_WS_CAPTION = 0x00C00000

_WM_NCLBUTTONDOWN = 0x00A1

_SWP_NOMOVE = 0x0002
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020

_MONITOR_DEFAULTTONEAREST = 2

_WINDOWS_FRAMELESS_ERROR = "pywebview WinForms window is not available"


def _winforms_window(window: Any):
    """Return the pywebview WinForms BrowserView that backs *window*."""
    from webview.platforms import winforms

    form = winforms.BrowserView.instances.get(window.uid)
    if form is None:
        raise RuntimeError(_WINDOWS_FRAMELESS_ERROR)
    return form


def _winforms_hwnd(window: Any) -> int:
    """Return the native Win32 handle for *window*'s WinForms form."""
    return int(_winforms_window(window).Handle.ToInt64())


def _user32() -> ctypes.WinDLL:
    return ctypes.WinDLL("user32", use_last_error=True)


_RESIZE_EDGE_HIT_TEST = {
    "left": 10,
    "right": 11,
    "top": 12,
    "top-left": 13,
    "top-right": 14,
    "bottom": 15,
    "bottom-left": 16,
    "bottom-right": 17,
}


def frameless_window_style(style: int) -> int:
    """Keep native window operations without restoring the painted caption shell."""
    return (style & ~_WS_CAPTION) | (
        _WS_THICKFRAME | _WS_MINIMIZEBOX | _WS_MAXIMIZEBOX | _WS_SYSMENU
    )


def begin_windows_resize(window: Any, edge: str) -> bool:
    """Start the native sizing loop from an in-window HTML edge grip."""
    hit_test = _RESIZE_EDGE_HIT_TEST.get(edge)
    if not is_windows() or hit_test is None:
        return False

    form = _winforms_window(window)
    hwnd = int(form.Handle.ToInt64())
    user32 = _user32()
    user32.ReleaseCapture.argtypes = []
    user32.ReleaseCapture.restype = wintypes.BOOL
    user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]
    user32.GetCursorPos.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t

    def start_native_resize() -> bool:
        point = _POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            raise ctypes.WinError(ctypes.get_last_error())
        user32.ReleaseCapture()
        position = ((point.y & 0xFFFF) << 16) | (point.x & 0xFFFF)
        user32.SendMessageW(hwnd, _WM_NCLBUTTONDOWN, hit_test, position)
        return True

    if form.InvokeRequired:
        from System import Boolean, Func

        return bool(form.Invoke(Func[Boolean](start_native_resize)))
    return start_native_resize()


class _POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [
        ("ptReserved", _POINT),
        ("ptMaxSize", _POINT),
        ("ptMaxPosition", _POINT),
        ("ptMinTrackSize", _POINT),
        ("ptMaxTrackSize", _POINT),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def install_windows_frameless_resize(
    window: Any,
    initial_size: WindowSize,
    min_size: WindowSize,
) -> bool:
    if not is_windows():
        return False
    layout_refreshed = False

    def install_after_show() -> None:
        try:
            _install_hook(window, initial_size, min_size)
        except Exception:
            logger.exception("Failed to install Windows frameless resize support")

    def refresh_after_load() -> None:
        nonlocal layout_refreshed
        if layout_refreshed:
            return
        try:
            _refresh_webview_layout(window)
            layout_refreshed = True
        except Exception:
            logger.exception(
                "Failed to refresh the WebView layout after startup sizing"
            )

    window.events.shown += install_after_show
    window.events.loaded += refresh_after_load
    return True


def _refresh_webview_layout(window: Any) -> None:
    """Make WebView2 consume the DPI-corrected outer size after navigation.

    pywebview 5.1 creates the WebView2 controller before the frameless form is
    calibrated to its requested logical size. On a scaled display the control
    can retain its smaller pre-calibration surface until the next user resize.
    A one-physical-pixel native resize, immediately restored, lets WinForms
    perform its normal DockStyle.Fill layout after WebView2 is ready.
    """
    hwnd = _winforms_hwnd(window)
    user32 = _user32()
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    rect = _RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError(ctypes.get_last_error())

    width = rect.right - rect.left
    height = rect.bottom - rect.top
    swp_flags = _SWP_NOMOVE | _SWP_NOZORDER | _SWP_NOACTIVATE
    if not user32.SetWindowPos(hwnd, None, 0, 0, width + 1, height, swp_flags):
        raise ctypes.WinError(ctypes.get_last_error())
    if not user32.SetWindowPos(hwnd, None, 0, 0, width, height, swp_flags):
        raise ctypes.WinError(ctypes.get_last_error())


def _install_hook(
    window: Any,
    initial_size: WindowSize,
    min_size: WindowSize,
) -> None:
    hwnd = _winforms_hwnd(window)
    user32 = _user32()
    long_ptr = ctypes.c_ssize_t
    wnd_proc_type = ctypes.WINFUNCTYPE(
        long_ptr,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    get_window_long = user32.GetWindowLongPtrW
    get_window_long.argtypes = [wintypes.HWND, ctypes.c_int]
    get_window_long.restype = long_ptr

    set_window_long = user32.SetWindowLongPtrW
    set_window_long.argtypes = [wintypes.HWND, ctypes.c_int, long_ptr]
    set_window_long.restype = long_ptr

    call_window_proc = user32.CallWindowProcW
    call_window_proc.argtypes = [
        long_ptr,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    call_window_proc.restype = long_ptr

    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.IsZoomed.restype = wintypes.BOOL
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.UINT,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL
    get_dpi_for_window = getattr(user32, "GetDpiForWindow", None)
    if get_dpi_for_window is not None:
        get_dpi_for_window.argtypes = [wintypes.HWND]
        get_dpi_for_window.restype = wintypes.UINT

    gwlp_wndproc = -4
    gwl_style = -16
    wm_nccalcsize = 0x0083
    wm_nchittest = 0x0084
    wm_getminmaxinfo = 0x0024
    wm_ncdestroy = 0x0082
    wm_size = 0x0005
    wm_windowposchanged = 0x0047
    wm_restore_normal_rect = 0x8001  # WM_APP + 1

    size_restored = 0
    size_maximized = 2

    htclient = 1
    htcaption = 2

    sm_cxsizeframe = 32
    sm_cysizeframe = 33
    sm_cxpaddedborder = 92

    def window_scale() -> float:
        return window_dpi_scale(hwnd)

    def system_metric(metric: int) -> int:
        metric_for_dpi = getattr(user32, "GetSystemMetricsForDpi", None)
        if get_dpi_for_window is not None and metric_for_dpi is not None:
            metric_for_dpi.argtypes = [ctypes.c_int, wintypes.UINT]
            metric_for_dpi.restype = ctypes.c_int
            return int(metric_for_dpi(metric, get_dpi_for_window(hwnd)))
        return int(user32.GetSystemMetrics(metric))

    def hit_test(l_param: int) -> int:
        rect = _RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return htclient

        x = ctypes.c_short(l_param & 0xFFFF).value
        y = ctypes.c_short((l_param >> 16) & 0xFFFF).value
        border_x = system_metric(sm_cxsizeframe) + system_metric(sm_cxpaddedborder)
        border_y = system_metric(sm_cysizeframe) + system_metric(sm_cxpaddedborder)

        maximized = bool(user32.IsZoomed(hwnd))
        left = not maximized and rect.left <= x < rect.left + border_x
        right = not maximized and rect.right - border_x <= x < rect.right
        top = not maximized and rect.top <= y < rect.top + border_y
        bottom = not maximized and rect.bottom - border_y <= y < rect.bottom

        if top and left:
            return _RESIZE_EDGE_HIT_TEST["top-left"]
        if top and right:
            return _RESIZE_EDGE_HIT_TEST["top-right"]
        if bottom and left:
            return _RESIZE_EDGE_HIT_TEST["bottom-left"]
        if bottom and right:
            return _RESIZE_EDGE_HIT_TEST["bottom-right"]
        if left:
            return _RESIZE_EDGE_HIT_TEST["left"]
        if right:
            return _RESIZE_EDGE_HIT_TEST["right"]
        if top:
            return _RESIZE_EDGE_HIT_TEST["top"]
        if bottom:
            return _RESIZE_EDGE_HIT_TEST["bottom"]
        scale = window_scale()
        in_titlebar = y < rect.top + round(DESKTOP_WINDOW_TITLEBAR_HEIGHT * scale)
        after_sidebar_control = x >= rect.left + round(
            DESKTOP_WINDOW_SIDEBAR_CONTROL_WIDTH * scale
        )
        before_controls = x < rect.right - round(DESKTOP_WINDOW_CONTROLS_WIDTH * scale)
        if in_titlebar and after_sidebar_control and before_controls:
            return htcaption
        return htclient

    def constrain_maximized_bounds(l_param: int) -> None:
        minmax = ctypes.cast(l_param, ctypes.POINTER(_MINMAXINFO)).contents
        scale = window_scale()
        minmax.ptMinTrackSize.x = round(min_size.width * scale)
        minmax.ptMinTrackSize.y = round(min_size.height * scale)

        monitor = user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return
        info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return

        minmax.ptMaxPosition.x = info.rcWork.left - info.rcMonitor.left
        minmax.ptMaxPosition.y = info.rcWork.top - info.rcMonitor.top
        minmax.ptMaxSize.x = info.rcWork.right - info.rcWork.left
        minmax.ptMaxSize.y = info.rcWork.bottom - info.rcWork.top

    original_proc = get_window_long(hwnd, gwlp_wndproc)
    normal_rect: _RECT | None = None
    was_maximized = False
    restore_pending = False

    @wnd_proc_type
    def window_proc(
        message_hwnd: int,
        message: int,
        w_param: int,
        l_param: int,
    ) -> int:
        nonlocal normal_rect, restore_pending, was_maximized
        try:
            if message == wm_restore_normal_rect:
                if normal_rect is not None:
                    width = normal_rect.right - normal_rect.left
                    height = normal_rect.bottom - normal_rect.top
                    user32.SetWindowPos(
                        hwnd,
                        None,
                        normal_rect.left,
                        normal_rect.top,
                        width,
                        height,
                        _SWP_NOZORDER | _SWP_NOACTIVATE,
                    )
                restore_pending = False
                return 0
            # Keep the WebView client flush with the real outer window. DWM
            # still owns clipping, shadow and the single outer corner.
            if message == wm_nccalcsize:
                return 0
            if message == wm_nchittest:
                result = hit_test(l_param)
                if result != htclient:
                    return result
            if message == wm_getminmaxinfo:
                call_window_proc(original_proc, message_hwnd, message, w_param, l_param)
                constrain_maximized_bounds(l_param)
                return 0
            if message == wm_size:
                result = call_window_proc(
                    original_proc, message_hwnd, message, w_param, l_param
                )
                if w_param == size_maximized:
                    was_maximized = True
                elif w_param == size_restored and was_maximized:
                    restore_pending = True
                    was_maximized = False
                    user32.PostMessageW(hwnd, wm_restore_normal_rect, 0, 0)
                return result
            if message == wm_windowposchanged:
                result = call_window_proc(
                    original_proc, message_hwnd, message, w_param, l_param
                )
                if (
                    not user32.IsZoomed(hwnd)
                    and not user32.IsIconic(hwnd)
                    and not was_maximized
                    and not restore_pending
                ):
                    rect = _RECT()
                    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                        normal_rect = rect
                return result
            if message == wm_ncdestroy:
                result = call_window_proc(
                    original_proc, message_hwnd, message, w_param, l_param
                )
                _hooks.pop(window.uid, None)
                return result
        except Exception:
            logger.exception("Windows frameless message handling failed")
        return call_window_proc(original_proc, message_hwnd, message, w_param, l_param)

    ctypes.set_last_error(0)
    previous_proc = set_window_long(
        hwnd,
        gwlp_wndproc,
        ctypes.cast(window_proc, ctypes.c_void_p).value,
    )
    if not previous_proc and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    # Keep the delegate alive as soon as Win32 owns its function pointer. If a
    # later sizing call fails, garbage-collecting it would leave a dangling
    # WNDPROC on a still-live window.
    _hooks[window.uid] = (window_proc, original_proc)

    original_rect = _RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(original_rect)):
        raise ctypes.WinError(ctypes.get_last_error())

    style = get_window_long(hwnd, gwl_style)
    ctypes.set_last_error(0)
    previous_style = set_window_long(
        hwnd,
        gwl_style,
        frameless_window_style(style),
    )
    if not previous_style and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())

    scale = window_scale()
    target_width = round(initial_size.width * scale)
    target_height = round(initial_size.height * scale)
    target_left = (
        original_rect.left
        + (original_rect.right - original_rect.left - target_width) // 2
    )
    target_top = (
        original_rect.top
        + (original_rect.bottom - original_rect.top - target_height) // 2
    )
    swp_flags = _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED
    if not user32.SetWindowPos(
        hwnd,
        None,
        target_left,
        target_top,
        target_width,
        target_height,
        swp_flags,
    ):
        raise ctypes.WinError(ctypes.get_last_error())

    # SWP_FRAMECHANGED rebuilds the non-client frame. Apply the final DWM
    # policy afterwards: one system-owned outer corner and no painted border.
    _apply_dwm_window_chrome(hwnd)


def _apply_dwm_window_chrome(hwnd: int) -> None:
    """Let DWM clip one real outer corner without painting another frame."""
    try:
        dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        set_attribute = dwmapi.DwmSetWindowAttribute
        set_attribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        set_attribute.restype = ctypes.c_long
        attributes = (
            (33, wintypes.DWORD(2)),  # DWMWA_WINDOW_CORNER_PREFERENCE: ROUND
            (34, wintypes.DWORD(0xFFFFFFFE)),  # DWMWA_BORDER_COLOR: COLOR_NONE
        )
        for attribute, value in attributes:
            result = set_attribute(
                hwnd,
                attribute,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result:
                logger.debug(
                    "DWM frame color attribute %s is not supported (HRESULT %#x)",
                    attribute,
                    result & 0xFFFFFFFF,
                )
    except (AttributeError, OSError):
        # These attributes are available on Windows 11. Older supported
        # systems keep their normal compositor-owned rendering.
        logger.debug("DWM window chrome policy is not supported", exc_info=True)
