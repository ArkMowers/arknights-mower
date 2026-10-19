"""Native GTK and Qt window operations for the desktop title bar."""

from importlib import import_module
from threading import Event, Lock, get_ident

from arknights_mower.utils.log import logger

_GUI_TIMEOUT = 3.0
_EDGE_NAMES = {
    "top": "NORTH",
    "top-right": "NORTH_EAST",
    "right": "EAST",
    "bottom-right": "SOUTH_EAST",
    "bottom": "SOUTH",
    "bottom-left": "SOUTH_WEST",
    "left": "WEST",
    "top-left": "NORTH_WEST",
}


def _gui_call(post, is_gui_thread, action, *, cleanup=False):
    if is_gui_thread():
        return action()
    completed = Event()
    guard = Lock()
    pending = [True]
    result = []
    errors = []

    def run():
        with guard:
            if not pending[0]:
                return False
            pending[0] = False
        try:
            result.append(action())
        except Exception as error:
            errors.append(error)
            if cleanup:
                logger.exception("Deferred desktop GUI cleanup failed")
        finally:
            completed.set()
        return False

    post(run)
    if not completed.wait(_GUI_TIMEOUT):
        if not cleanup:
            with guard:
                pending[0] = False
        raise TimeoutError("Desktop GUI did not accept the window operation")
    if errors:
        raise errors[0]
    return result[0]


class _TitlePress:
    def __init__(self):
        self.previous = None
        self.double_timestamp = None

    def is_double(self, x, y, timestamp, explicit=False, interval=400, distance=5):
        previous = self.previous
        self.previous = (x, y, timestamp)
        if explicit or (
            previous is not None
            and 0 < ((timestamp - previous[2]) & 0xFFFFFFFF) <= interval
            and abs(x - previous[0]) <= distance
            and abs(y - previous[1]) <= distance
        ):
            self.previous = None
            self.double_timestamp = timestamp
            return True
        return False


class GtkWindow:
    capabilities = {"enabled": True, "move": "native", "resize": "html"}

    def __init__(self, window, regions, on_state_changed):
        self._window = window
        self._regions = regions
        self._changed = on_state_changed
        self._backend = None
        self._native = None
        self._webview = None
        self._thread = None
        self._signals = []
        self._press = _TitlePress()
        self._active = False
        self.capabilities = dict(type(self).capabilities)

    def _call(self, action, *, cleanup=False):
        return _gui_call(
            self._backend.glib.idle_add,
            lambda: (
                self._thread == get_ident()
                or self._backend.glib.MainContext.default().is_owner()
            ),
            action,
            cleanup=cleanup,
        )

    def install(self):
        try:
            self._backend = import_module("webview.platforms.gtk")
            browser = self._backend.BrowserView.instances[self._window.uid]
            self._native, self._webview = browser.window, browser.webview

            def install_gui():
                if self._active:
                    return True
                self._thread = get_ident()
                gdk = self._backend.Gdk
                self._webview.add_events(gdk.EventMask.BUTTON_PRESS_MASK)
                self._signals.append(
                    (
                        self._webview,
                        self._webview.connect("button-press-event", self._button),
                    )
                )
                self._signals.append(
                    (
                        self._native,
                        self._native.connect("window-state-event", self._state),
                    )
                )
                self._signals.append(
                    (self._native, self._native.connect("destroy", self._destroy))
                )
                self.capabilities["enabled"] = True
                self._active = True
                return True

            return self._call(install_gui)
        except Exception:
            logger.exception("GTK title bar support could not be installed")
            self.dispose()
            self.fallback_decorations()
            return False

    def _button(self, widget, event):
        try:
            return self._button_gui(widget, event)
        except Exception:
            logger.exception("GTK system window operation failed")
            self.dispose()
            try:
                self.fallback_decorations()
            except Exception:
                logger.exception("GTK window decorations could not be restored")
            return False

    def _button_gui(self, widget, event):
        if not self._active or event.button != 1:
            return False
        width, height = widget.get_allocated_width(), widget.get_allocated_height()
        region = self._regions.hit_test(event.x, event.y, width, height)
        if region is None:
            self._press.previous = None
            return False
        gdk = self._backend.Gdk
        double_type = getattr(gdk.EventType, "_2BUTTON_PRESS", None)
        double_type = double_type or getattr(gdk.EventType, "DOUBLE_BUTTON_PRESS", None)
        if region == "move":
            if event.type == double_type and self._press.double_timestamp == event.time:
                return True
            settings = self._native.get_settings()
            interval = settings.get_property("gtk-double-click-time")
            distance = settings.get_property("gtk-double-click-distance")
            if self._press.is_double(
                event.x_root,
                event.y_root,
                event.time,
                event.type == double_type,
                interval,
                distance,
            ):
                if self._state_gui() == "maximized":
                    self._restore_gui()
                else:
                    self._native.maximize()
                return True
        else:
            self._press.previous = None
            if region not in _EDGE_NAMES or self._state_gui() != "normal":
                return False

        native = self._native.get_window()
        device = event.get_device()
        args = (event.button, int(event.x_root), int(event.y_root), event.time)
        if region == "move":
            operation = getattr(native, "begin_move_drag_for_device", None)
            if operation is not None and device is not None:
                operation(device, *args)
            else:
                self._native.begin_move_drag(*args)
        else:
            edge = getattr(gdk.WindowEdge, _EDGE_NAMES[region])
            operation = getattr(native, "begin_resize_drag_for_device", None)
            if operation is not None and device is not None:
                operation(edge, device, *args)
            else:
                self._native.begin_resize_drag(edge, *args)
        return True

    def _state(self, *_):
        self._notify_changed()
        return False

    def _destroy(self, *_):
        self.dispose()

    def _notify_changed(self):
        try:
            self._changed()
        except Exception:
            logger.exception("GTK window state notification failed")

    def _state_gui(self):
        native = self._native.get_window()
        state = native.get_state() if native is not None else 0
        flags = self._backend.Gdk.WindowState
        return (
            "minimized"
            if state & flags.ICONIFIED
            else "maximized"
            if state & (flags.MAXIMIZED | flags.FULLSCREEN)
            else "normal"
        )

    def get_state(self):
        return self._call(self._state_gui)

    def get_normal_size(self):
        def sample_gui():
            if self._state_gui() != "normal":
                return None
            width, height = self._native.get_size()
            return int(width), int(height)

        return self._call(sample_gui)

    def maximize(self):
        def maximize_gui():
            self._native.maximize()
            return True

        return self._call(maximize_gui)

    def _restore_gui(self):
        self._native.unfullscreen()
        self._native.deiconify()
        self._native.unmaximize()
        return True

    def restore(self):
        return self._call(self._restore_gui)

    def work_area(self):
        def area_gui():
            display = self._native.get_display()
            monitor = display.get_monitor_at_window(self._native.get_window())
            if monitor is None:
                return None
            area = monitor.get_workarea()
            return (int(area.width), int(area.height))

        try:
            return self._call(area_gui)
        except Exception:
            logger.debug("GTK monitor work area was unavailable", exc_info=True)
            return None

    def _dispose_gui(self):
        self._active = False
        signals, self._signals = self._signals, []
        errors = []
        remaining = []
        for widget, signal in reversed(signals):
            try:
                widget.disconnect(signal)
            except Exception as error:
                remaining.append((widget, signal))
                errors.append(error)
        self._signals = list(reversed(remaining))
        if errors:
            raise errors[0]

    def dispose(self):
        self._active = False
        if self._backend is None or not self._signals:
            return
        try:
            self._call(self._dispose_gui, cleanup=True)
        except Exception:
            logger.debug("GTK title bar cleanup was unavailable", exc_info=True)

    def fallback_decorations(self):
        if self._backend is None or self._native is None:
            raise RuntimeError("GTK window is unavailable")

        def decorate_gui():
            self._native.set_decorated(True)
            self.capabilities["enabled"] = False
            self._notify_changed()

        self._call(decorate_gui)


class QtWindow:
    capabilities = {"enabled": True, "move": "native", "resize": "html"}

    def __init__(self, window, regions, on_state_changed):
        self._window = window
        self._regions = regions
        self._changed = on_state_changed
        self._backend = None
        self._native = None
        self._app = None
        self._filter = None
        self._destroy_connected = False
        self._press = _TitlePress()
        self._active = False
        self.capabilities = dict(type(self).capabilities)

    def _call(self, action, *, cleanup=False):
        return _gui_call(
            self._native.create_window_trigger.emit,
            lambda: (
                self._backend.QtCore.QThread.currentThread() == self._native.thread()
            ),
            action,
            cleanup=cleanup,
        )

    def install(self):
        try:
            self._backend = import_module("webview.platforms.qt")
            self._native = self._backend.BrowserView.instances[self._window.uid]

            def install_gui():
                if self._active:
                    return True
                handle = self._native.windowHandle()
                if handle is None or not all(
                    callable(getattr(handle, method, None))
                    for method in ("startSystemMove", "startSystemResize")
                ):
                    raise RuntimeError(
                        "Qt system window operations require Qt 5.15 or later"
                    )
                owner = self

                class WindowFilter(self._backend.QtCore.QObject):
                    def eventFilter(self, watched, event):
                        return owner._event(watched, event)

                self._app = self._backend.QApplication.instance()
                self._filter = WindowFilter(self._app)
                self._app.installEventFilter(self._filter)
                self._native.destroyed.connect(self._destroy)
                self._destroy_connected = True
                self.capabilities["enabled"] = True
                self._active = True
                return True

            return self._call(install_gui)
        except Exception:
            logger.exception("Qt title bar support could not be installed")
            self.dispose()
            self.fallback_decorations()
            return False

    def _enum(self, group, name):
        qt = self._backend.QtCore.Qt
        return getattr(getattr(qt, group, qt), name)

    def _event_type(self, name):
        event = self._backend.QtCore.QEvent
        return getattr(getattr(event, "Type", event), name)

    def _event(self, watched, event):
        try:
            return self._event_gui(watched, event)
        except Exception:
            logger.exception("Qt system window operation failed")
            self._disable_gui()
            return False

    def _event_gui(self, watched, event):
        if not self._active:
            return False
        if watched is self._native and event.type() == self._event_type(
            "WindowStateChange"
        ):
            self._notify_changed()
            return False
        if event.type() not in (
            self._event_type("MouseButtonPress"),
            self._event_type("MouseButtonDblClick"),
        ) or event.button() != self._enum("MouseButton", "LeftButton"):
            return False
        ancestor = watched
        while ancestor is not None and ancestor is not self._native.view:
            ancestor = ancestor.parent()
        if ancestor is None:
            return False
        position = (
            event.globalPosition().toPoint()
            if hasattr(event, "globalPosition")
            else event.globalPos()
        )
        view = self._native.view
        local = view.mapFromGlobal(position)
        region = self._regions.hit_test(
            local.x(), local.y(), view.width(), view.height()
        )
        if region is None:
            self._press.previous = None
            return False
        if region == "move":
            if (
                event.type() == self._event_type("MouseButtonDblClick")
                and self._press.double_timestamp == event.timestamp()
            ):
                event.accept()
                return True
            if self._press.is_double(
                position.x(),
                position.y(),
                event.timestamp(),
                event.type() == self._event_type("MouseButtonDblClick"),
                self._app.doubleClickInterval(),
            ):
                if self._state_gui() == "maximized":
                    self._native.showNormal()
                else:
                    self._native.showMaximized()
                event.accept()
                return True
            started = self._native.windowHandle().startSystemMove()
        else:
            self._press.previous = None
            if region not in _EDGE_NAMES or self._state_gui() != "normal":
                return False
            edges = None
            for side in region.split("-"):
                edge = self._enum("Edge", side.title() + "Edge")
                edges = edge if edges is None else edges | edge
            started = self._native.windowHandle().startSystemResize(edges)
        if started:
            event.accept()
            return True
        logger.warning("Qt compositor declined the system window operation")
        self._disable_gui()
        return False

    def _disable_gui(self):
        self.dispose()
        try:
            self.fallback_decorations()
        except Exception:
            logger.exception("Qt window decorations could not be restored")

    def _notify_changed(self):
        try:
            self._changed()
        except Exception:
            logger.exception("Qt window state notification failed")

    def _state_gui(self):
        return (
            "minimized"
            if self._native.isMinimized()
            else "maximized"
            if self._native.isMaximized() or self._native.isFullScreen()
            else "normal"
        )

    def get_state(self):
        return self._call(self._state_gui)

    def get_normal_size(self):
        def sample_gui():
            if self._state_gui() != "normal":
                return None
            return self._native.width(), self._native.height()

        return self._call(sample_gui)

    def maximize(self):
        def maximize_gui():
            self._native.showMaximized()
            return True

        return self._call(maximize_gui)

    def restore(self):
        def restore_gui():
            self._native.showNormal()
            return True

        return self._call(restore_gui)

    def work_area(self):
        def area_gui():
            screen = self._native.windowHandle().screen()
            if screen is None:
                return None
            area = screen.availableGeometry()
            return (int(area.width()), int(area.height()))

        try:
            return self._call(area_gui)
        except Exception:
            logger.debug("Qt monitor work area was unavailable", exc_info=True)
            return None

    def _destroy(self, *_):
        self._destroy_connected = False
        try:
            self._dispose_gui()
        except Exception:
            logger.exception("Qt window destruction cleanup failed")

    def _dispose_gui(self):
        self._active = False
        if self._filter is not None:
            self._app.removeEventFilter(self._filter)
            self._filter.deleteLater()
            self._filter = None
        if self._destroy_connected:
            self._native.destroyed.disconnect(self._destroy)
            self._destroy_connected = False

    def dispose(self):
        self._active = False
        if self._filter is None and not self._destroy_connected:
            return
        try:
            self._call(self._dispose_gui, cleanup=True)
        except Exception:
            logger.debug("Qt title bar cleanup was unavailable", exc_info=True)

    def fallback_decorations(self):
        if self._native is None:
            raise RuntimeError("Qt window is unavailable")

        def decorate_gui():
            self._native.setWindowFlag(
                self._enum("WindowType", "FramelessWindowHint"), False
            )
            self._native.show()
            self.capabilities["enabled"] = False
            self._notify_changed()

        self._call(decorate_gui)
