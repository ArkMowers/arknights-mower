from threading import Event, Lock

from arknights_mower.utils.log import logger

_UI_TIMEOUT = 2.0
_DRAG_DISTANCE = 4


def _load_cocoa():
    import AppKit
    import Foundation
    from PyObjCTools import AppHelper
    from webview.platforms.cocoa import BrowserView

    return AppKit, Foundation, AppHelper, BrowserView


def _rectangle(frame):
    return (
        frame.origin.x,
        frame.origin.y,
        frame.size.width,
        frame.size.height,
    )


class CocoaWindow:
    capabilities = {"enabled": True, "move": "native", "resize": "native"}

    def __init__(self, window, regions, on_state_changed):
        self.window = window
        self.capabilities = dict(type(self).capabilities)
        self.regions = regions
        self.on_state_changed = on_state_changed
        self._dependencies = None
        self._native = None
        self._view = None
        self._monitor = None
        self._observers = []
        self._disposed = False
        self._input_disabled = False
        self._pressed = None
        self._normal_frame = None
        self._state = "normal"
        self._changing_frame = False

    def _on_ui(self, operation, *, cleanup=False):
        if self._dependencies is None:
            self._dependencies = _load_cocoa()
        _, foundation, helper, _ = self._dependencies
        if foundation.NSThread.isMainThread():
            return operation()

        completed = Event()
        guard = Lock()
        result = []
        pending = [True]

        def invoke():
            with guard:
                if not pending[0]:
                    return
                pending[0] = False
            try:
                result.append((True, operation()))
            except Exception as error:
                result.append((False, error))
            finally:
                completed.set()

        helper.callAfter(invoke)
        if not completed.wait(_UI_TIMEOUT):
            if not cleanup:
                with guard:
                    pending[0] = False
            raise TimeoutError("Cocoa window operation timed out")
        success, value = result[0]
        if not success:
            raise value
        return value

    def _resolve_window(self):
        _, _, _, browser_view = self._dependencies
        browser = browser_view.instances.get(self.window.uid)
        if browser is None:
            raise RuntimeError("Cocoa window is unavailable")
        self._native = browser.window
        self._view = browser.webkit
        return browser

    def install(self):
        def install_on_ui():
            if self._monitor is not None:
                return
            if self._disposed:
                raise RuntimeError("Cocoa window adapter is disposed")
            self._resolve_window()
            if not callable(getattr(self._native, "performWindowDragWithEvent_", None)):
                raise RuntimeError("Cocoa system window dragging is unavailable")
            appkit, foundation, _, _ = self._dependencies
            mask = (
                appkit.NSLeftMouseDownMask
                | appkit.NSLeftMouseDraggedMask
                | appkit.NSLeftMouseUpMask
            )
            try:
                self._monitor = (
                    appkit.NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
                        mask, self._handle_event
                    )
                )
                if self._monitor is None:
                    raise RuntimeError("Cocoa event monitor is unavailable")
                center = foundation.NSNotificationCenter.defaultCenter()
                for name in (
                    appkit.NSWindowDidResizeNotification,
                    appkit.NSWindowDidMoveNotification,
                    appkit.NSWindowDidMiniaturizeNotification,
                    appkit.NSWindowDidDeminiaturizeNotification,
                    appkit.NSWindowDidEnterFullScreenNotification,
                    appkit.NSWindowDidExitFullScreenNotification,
                ):
                    observer = center.addObserverForName_object_queue_usingBlock_(
                        name, self._native, None, self._native_state_changed
                    )
                    self._observers.append(observer)
                self._state = self._get_state_on_ui()
            except Exception:
                self._cleanup_on_ui()
                raise

        self._on_ui(install_on_ui)

    def _get_state_on_ui(self):
        if self._native.isMiniaturized():
            return "minimized"
        if self._native.styleMask() & (1 << 14):  # NSFullScreenWindowMask
            return "maximized"
        screen = self._native.screen()
        if screen is not None:
            frame = _rectangle(self._native.frame())
            visible = _rectangle(screen.visibleFrame())
            if all(
                abs(actual - expected) <= 1 for actual, expected in zip(frame, visible)
            ):
                return "maximized"
        return "normal"

    def get_state(self):
        return self._on_ui(self._get_state_on_ui)

    def _native_state_changed(self, _notification=None):
        if self._disposed:
            return
        try:
            state = self._get_state_on_ui()
            if state == "normal" and not self._changing_frame:
                self._normal_frame = _rectangle(self._native.frame())
        except Exception:
            logger.exception("Unable to read Cocoa window state")
            self._recover_native_decorations()
            return
        if state != self._state:
            self._state = state
            self._notify_state_changed()

    def _notify_state_changed(self):
        try:
            self.on_state_changed()
        except Exception:
            logger.exception("Unable to publish Cocoa window state")

    def _recover_native_decorations(self):
        self._stop_input()
        try:
            self.fallback_decorations()
        except Exception:
            logger.exception("Unable to restore Cocoa window decorations")

    def _set_frame(self, frame):
        appkit, _, _, _ = self._dependencies
        self._changing_frame = True
        try:
            self._native.setFrame_display_(appkit.NSMakeRect(*frame), True)
        finally:
            self._changing_frame = False
        self._native_state_changed()

    def minimize(self):
        def minimize_on_ui():
            if self._disposed or self._native is None:
                return False
            self._native.miniaturize_(None)
            self._native_state_changed()
            return True

        return self._on_ui(minimize_on_ui)

    def maximize(self):
        def maximize_on_ui():
            if self._disposed or self._native is None:
                return False
            if self._native.isMiniaturized():
                self._native.deminiaturize_(None)
            if self._get_state_on_ui() == "maximized":
                return True
            screen = self._native.screen()
            if screen is None:
                return False
            self._normal_frame = _rectangle(self._native.frame())
            self._set_frame(_rectangle(screen.visibleFrame()))
            return True

        return self._on_ui(maximize_on_ui)

    def restore(self):
        def restore_on_ui():
            if self._disposed or self._native is None:
                return False
            if self._native.isMiniaturized():
                self._native.deminiaturize_(None)
                self._native_state_changed()
                return True
            if self._native.styleMask() & (1 << 14):
                self._native.toggleFullScreen_(None)
                return True
            if self._get_state_on_ui() != "maximized":
                return True
            if self._normal_frame is None:
                return False
            self._set_frame(self._normal_frame)
            return True

        return self._on_ui(restore_on_ui)

    def work_area(self):
        def work_area_on_ui():
            screen = self._native.screen() if self._native is not None else None
            if screen is None:
                return None
            size = screen.visibleFrame().size
            return int(size.width), int(size.height)

        return self._on_ui(work_area_on_ui)

    def _event_position(self, event):
        point = self._view.convertPoint_fromView_(event.locationInWindow(), None)
        bounds = self._view.bounds()
        x = point.x - bounds.origin.x
        y = point.y - bounds.origin.y
        if not self._view.isFlipped():
            y = bounds.size.height - y
        return x, y, bounds.size.width, bounds.size.height

    def _handle_event(self, event):
        try:
            return self._handle_event_on_ui(event)
        except Exception:
            logger.exception("Cocoa window input handling failed")
            self._recover_native_decorations()
            return event

    def _handle_event_on_ui(self, event):
        if self._disposed or self._input_disabled or event.window() != self._native:
            return event
        appkit, _, _, _ = self._dependencies
        kind = event.type()
        if kind == appkit.NSLeftMouseDown:
            self._pressed = None
            x, y, width, height = self._event_position(event)
            if self.regions.hit_test(x, y, width, height) != "move":
                return event
            if event.clickCount() == 2:
                if self._get_state_on_ui() == "maximized":
                    self.restore()
                else:
                    self.maximize()
                return None
            self._pressed = (x, y, event)
            return None
        if self._pressed is not None:
            if kind == appkit.NSLeftMouseDragged:
                x, y, _, _ = self._event_position(event)
                previous_x, previous_y, original_press = self._pressed
                if (x - previous_x) ** 2 + (y - previous_y) ** 2 >= _DRAG_DISTANCE**2:
                    self._pressed = None
                    self._native.performWindowDragWithEvent_(original_press)
                return None
            if kind == appkit.NSLeftMouseUp:
                self._pressed = None
                return None
        return event

    def _cleanup_on_ui(self):
        appkit, foundation, _, _ = self._dependencies
        errors = []
        if self._monitor is not None:
            try:
                appkit.NSEvent.removeMonitor_(self._monitor)
                self._monitor = None
            except Exception as error:
                errors.append(error)
        center = foundation.NSNotificationCenter.defaultCenter()
        remaining = []
        for observer in reversed(self._observers):
            try:
                center.removeObserver_(observer)
            except Exception as error:
                remaining.append(observer)
                errors.append(error)
        self._observers = list(reversed(remaining))
        self._pressed = None
        if errors:
            raise errors[0]

    def _stop_input(self):
        self._input_disabled = True
        if self._dependencies is not None:
            try:
                self._on_ui(self._cleanup_on_ui, cleanup=True)
            except Exception:
                logger.exception("Unable to release Cocoa window observers")

    def dispose(self):
        self._disposed = True
        self._stop_input()

    def fallback_decorations(self):
        def restore_on_ui():
            browser = self._resolve_window()
            appkit, _, _, _ = self._dependencies
            mask = self._native.styleMask()
            mask &= ~(1 << 15)  # NSFullSizeContentViewWindowMask
            mask |= (
                appkit.NSTitledWindowMask
                | appkit.NSClosableWindowMask
                | appkit.NSMiniaturizableWindowMask
            )
            self._native.setStyleMask_(mask)
            self._native.setTitlebarAppearsTransparent_(False)
            self._native.setTitleVisibility_(0)
            for button in (
                appkit.NSWindowCloseButton,
                appkit.NSWindowMiniaturizeButton,
                appkit.NSWindowZoomButton,
            ):
                self._native.standardWindowButton_(button).setHidden_(False)
            browser.frameless = False
            self.capabilities["enabled"] = False
            self._notify_state_changed()

        self._on_ui(restore_on_ui)
