import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from arknights_mower.utils import cocoa_window


def rectangle(x, y, width, height):
    return SimpleNamespace(
        origin=SimpleNamespace(x=x, y=y),
        size=SimpleNamespace(width=width, height=height),
    )


class NativeWindow:
    def __init__(self):
        self.geometry = rectangle(40, 70, 900, 600)
        self.display = SimpleNamespace(visibleFrame=lambda: rectangle(0, 60, 1440, 800))
        self.minimized = False
        self.moves = []
        self.frames = []
        self.mask = (1 << 15) | 8
        self.buttons = {name: Mock() for name in (0, 1, 2)}
        self.setTitlebarAppearsTransparent_ = Mock()
        self.setTitleVisibility_ = Mock()
        self.toggleFullScreen_ = Mock()
        self.minimize_threads = []

    def frame(self):
        return self.geometry

    def screen(self):
        return self.display

    def isMiniaturized(self):
        return self.minimized

    def deminiaturize_(self, _sender):
        self.minimized = False

    def miniaturize_(self, _sender):
        self.minimized = True
        self.minimize_threads.append(threading.get_ident())

    def setFrame_display_(self, frame, _display):
        self.geometry = frame
        self.frames.append((cocoa_window._rectangle(frame), threading.get_ident()))

    def performWindowDragWithEvent_(self, event):
        self.moves.append(event)

    def styleMask(self):
        return self.mask

    def setStyleMask_(self, mask):
        self.mask = mask

    def standardWindowButton_(self, name):
        return self.buttons[name]


class CocoaWindowTests(unittest.TestCase):
    def setUp(self):
        self.native = NativeWindow()
        self.regions = SimpleNamespace(hit_test=Mock(return_value="move"))
        self.callback = Mock()
        self.view = SimpleNamespace(
            convertPoint_fromView_=lambda point, _: point,
            bounds=lambda: rectangle(0, 0, 900, 600),
            isFlipped=lambda: False,
        )
        self.browser = SimpleNamespace(
            window=self.native, webkit=self.view, frameless=True
        )
        self.monitors = []
        self.removed_monitors = []
        self.observers = []
        self.removed_observers = []
        self.pending = []
        self.queued = threading.Event()

        def add_monitor(mask, handler):
            monitor = (mask, handler)
            self.monitors.append(monitor)
            return monitor

        def add_observer(name, native, queue, handler):
            observer = (name, native, queue, handler)
            self.observers.append(observer)
            return observer

        self.center = SimpleNamespace(
            addObserverForName_object_queue_usingBlock_=Mock(side_effect=add_observer),
            removeObserver_=self.removed_observers.append,
        )
        self.appkit = SimpleNamespace(
            NSLeftMouseDownMask=1,
            NSLeftMouseDraggedMask=2,
            NSLeftMouseUpMask=4,
            NSLeftMouseDown=10,
            NSLeftMouseDragged=11,
            NSLeftMouseUp=12,
            NSWindowDidResizeNotification="resize",
            NSWindowDidMoveNotification="move",
            NSWindowDidMiniaturizeNotification="minimize",
            NSWindowDidDeminiaturizeNotification="restore",
            NSWindowDidEnterFullScreenNotification="enter_fullscreen",
            NSWindowDidExitFullScreenNotification="exit_fullscreen",
            NSTitledWindowMask=1,
            NSClosableWindowMask=2,
            NSMiniaturizableWindowMask=4,
            NSWindowCloseButton=0,
            NSWindowMiniaturizeButton=1,
            NSWindowZoomButton=2,
            NSMakeRect=rectangle,
            NSEvent=SimpleNamespace(
                addLocalMonitorForEventsMatchingMask_handler_=add_monitor,
                removeMonitor_=self.removed_monitors.append,
            ),
        )

        def enqueue(operation):
            self.pending.append(operation)
            self.queued.set()

        foundation = SimpleNamespace(
            NSThread=SimpleNamespace(
                isMainThread=lambda: (
                    threading.current_thread() is threading.main_thread()
                )
            ),
            NSNotificationCenter=SimpleNamespace(defaultCenter=lambda: self.center),
        )
        dependencies = (
            self.appkit,
            foundation,
            SimpleNamespace(callAfter=enqueue),
            SimpleNamespace(instances={"test": self.browser}),
        )
        self.loading = patch.object(
            cocoa_window, "_load_cocoa", return_value=dependencies
        )
        self.loader = self.loading.start()
        self.addCleanup(self.loading.stop)
        self.adapter = cocoa_window.CocoaWindow(
            SimpleNamespace(uid="test"), self.regions, self.callback
        )
        self.addCleanup(self.adapter.dispose)

    def event(self, kind, x=200, y=580, *, native=None, clicks=1):
        return SimpleNamespace(
            type=lambda: kind,
            window=lambda: native or self.native,
            locationInWindow=lambda: SimpleNamespace(x=x, y=y),
            clickCount=lambda: clicks,
        )

    def emit(self, name):
        for observed_name, observed_window, queue, handler in self.observers:
            if name == observed_name:
                self.assertIs(observed_window, self.native)
                self.assertIsNone(queue)
                handler(None)

    def drain(self):
        while self.pending:
            self.pending.pop(0)()

    def test_native_dependencies_are_loaded_only_when_window_is_used(self):
        self.loader.assert_not_called()
        self.adapter.install()
        self.loader.assert_called_once_with()
        self.assertEqual(len(self.monitors), 1)
        self.assertEqual(self.monitors[0][0], 7)
        self.assertEqual(self.adapter.work_area(), (1440, 800))

    def test_controls_other_windows_and_system_resize_edges_keep_their_events(self):
        self.adapter.install()
        handle = self.monitors[0][1]
        foreign = self.event(10, native=object())
        self.assertIs(handle(foreign), foreign)
        self.regions.hit_test.assert_not_called()
        for hit in (None, "left", "top_right"):
            self.regions.hit_test.return_value = hit
            down = self.event(10)
            drag = self.event(11, x=240)
            self.assertIs(handle(down), down)
            self.assertIs(handle(drag), drag)
        self.regions.hit_test.assert_called_with(200, 20, 900, 600)
        self.assertEqual(self.native.moves, [])
        self.assertEqual(self.native.mask, (1 << 15) | 8)

    def test_caption_drag_hands_over_the_original_mouse_down_after_threshold(self):
        self.adapter.install()
        handle = self.monitors[0][1]
        down = self.event(10)
        self.assertIsNone(handle(down))
        self.assertIsNone(handle(self.event(11, x=202)))
        self.assertEqual(self.native.moves, [])
        drag = self.event(11, x=205)
        self.assertIsNone(handle(drag))
        self.assertEqual(self.native.moves, [down])
        handle(self.event(11, x=230))
        self.assertEqual(self.native.moves, [down])

    def test_flipped_webview_and_released_click_do_not_start_a_drag(self):
        self.view.isFlipped = lambda: True
        self.adapter.install()
        handle = self.monitors[0][1]
        handle(self.event(10, y=20))
        self.regions.hit_test.assert_called_with(200, 20, 900, 600)
        self.assertIsNone(handle(self.event(12)))
        drag = self.event(11, x=230)
        self.assertIs(handle(drag), drag)
        self.assertEqual(self.native.moves, [])

    def test_double_click_maximizes_with_available_screen_and_restores_frame(self):
        self.adapter.install()
        handle = self.monitors[0][1]
        handle(self.event(10, clicks=2))
        self.assertEqual(self.adapter.get_state(), "maximized")
        self.assertEqual(
            cocoa_window._rectangle(self.native.frame()), (0, 60, 1440, 800)
        )
        self.assertEqual(self.callback.call_count, 1)
        handle(self.event(10, clicks=2))
        self.assertEqual(self.adapter.get_state(), "normal")
        self.assertEqual(
            cocoa_window._rectangle(self.native.frame()), (40, 70, 900, 600)
        )
        self.assertEqual(self.callback.call_count, 2)
        self.native.toggleFullScreen_.assert_not_called()

    def test_external_fullscreen_is_observed_and_restored_with_native_transition(self):
        self.adapter.install()
        self.native.mask |= 1 << 14
        self.emit("enter_fullscreen")
        self.assertEqual(self.adapter.get_state(), "maximized")
        self.assertTrue(self.adapter.restore())
        self.native.toggleFullScreen_.assert_called_once_with(None)
        self.assertEqual(self.native.frames, [])
        self.native.mask &= ~(1 << 14)
        self.emit("exit_fullscreen")
        self.assertEqual(self.adapter.get_state(), "normal")
        self.assertEqual(self.callback.call_count, 2)

    def test_native_minimize_restore_and_resize_notifications_update_state(self):
        self.adapter.install()
        self.adapter.maximize()
        self.native.minimized = True
        self.emit("minimize")
        self.assertEqual(self.adapter.get_state(), "minimized")
        self.assertEqual(self.callback.call_count, 2)
        self.assertTrue(self.adapter.restore())
        self.assertEqual(self.adapter.get_state(), "maximized")
        self.assertTrue(self.adapter.restore())
        self.assertEqual(self.adapter.get_state(), "normal")
        self.native.geometry = rectangle(30, 80, 800, 500)
        self.emit("resize")
        self.adapter.maximize()
        self.adapter.restore()
        self.assertEqual(
            cocoa_window._rectangle(self.native.frame()), (30, 80, 800, 500)
        )

    def test_dispose_removes_monitor_and_observers_once_and_stops_interception(self):
        self.adapter.install()
        handle = self.monitors[0][1]
        self.adapter.dispose()
        self.adapter.dispose()
        self.assertEqual(self.removed_monitors, self.monitors)
        self.assertEqual(self.removed_observers, list(reversed(self.observers)))
        down = self.event(10)
        self.assertIs(handle(down), down)
        self.emit("resize")
        self.callback.assert_not_called()
        self.assertFalse(self.adapter.maximize())

    def test_partial_install_failure_releases_already_registered_resources(self):
        add_observer = self.center.addObserverForName_object_queue_usingBlock_
        original = add_observer.side_effect

        def fail_second(*args):
            if self.observers:
                raise RuntimeError("observer registration failed")
            return original(*args)

        add_observer.side_effect = fail_second
        with self.assertRaisesRegex(RuntimeError, "registration failed"):
            self.adapter.install()
        self.assertEqual(self.removed_monitors, self.monitors)
        self.assertEqual(self.removed_observers, self.observers)
        self.assertTrue(self.adapter.maximize())
        self.assertTrue(self.adapter.restore())
        self.assertTrue(self.adapter.minimize())

    def test_worker_operations_execute_on_gui_thread(self):
        self.adapter.install()
        results = []
        worker = threading.Thread(
            target=lambda: results.append(self.adapter.maximize())
        )
        worker.start()
        self.assertTrue(self.queued.wait(1))
        self.assertEqual(self.native.frames, [])
        self.drain()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [True])
        self.assertEqual(self.native.frames[0][1], threading.get_ident())

    def test_ui_timeout_cancels_queued_mutation(self):
        self.adapter.install()
        errors = []

        def maximize():
            try:
                self.adapter.maximize()
            except TimeoutError as error:
                errors.append(error)

        with patch.object(cocoa_window, "_UI_TIMEOUT", 0.01):
            worker = threading.Thread(target=maximize)
            worker.start()
            worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(errors), 1)
        self.drain()
        self.assertEqual(self.native.frames, [])

    def test_worker_minimizes_on_gui_thread_and_publishes_observed_state(self):
        self.adapter.install()
        results = []
        worker = threading.Thread(
            target=lambda: results.append(self.adapter.minimize())
        )
        worker.start()
        self.assertTrue(self.queued.wait(1))
        self.assertEqual(self.native.minimize_threads, [])
        self.assertFalse(self.native.minimized)
        self.drain()
        worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertEqual(results, [True])
        self.assertEqual(self.native.minimize_threads, [threading.get_ident()])
        self.assertEqual(self.adapter.get_state(), "minimized")
        self.callback.assert_called_once_with()
        self.adapter.dispose()
        self.assertFalse(self.adapter.minimize())
        self.assertEqual(self.native.minimize_threads, [threading.get_ident()])

    def test_disposal_can_finish_when_gui_resumes_after_bounded_wait(self):
        self.adapter.install()
        with (
            patch.object(cocoa_window, "_UI_TIMEOUT", 0.01),
            patch.object(cocoa_window.logger, "exception") as log,
        ):
            worker = threading.Thread(target=self.adapter.dispose)
            worker.start()
            worker.join(1)
        self.assertFalse(worker.is_alive())
        log.assert_called_once()
        self.assertEqual(self.removed_monitors, [])
        self.drain()
        self.assertEqual(self.removed_monitors, self.monitors)
        self.assertEqual(len(self.removed_observers), 6)

    def test_fallback_restores_native_buttons_and_only_disables_this_adapter(self):
        self.adapter.install()
        self.adapter.dispose()
        self.adapter.fallback_decorations()
        self.assertFalse(self.native.mask & (1 << 15))
        self.assertEqual(self.native.mask & 15, 15)
        self.native.setTitlebarAppearsTransparent_.assert_called_once_with(False)
        self.native.setTitleVisibility_.assert_called_once_with(0)
        for button in self.native.buttons.values():
            button.setHidden_.assert_called_once_with(False)
        self.assertFalse(self.browser.frameless)
        self.assertFalse(self.adapter.capabilities["enabled"])
        self.assertEqual(self.adapter.capabilities["move"], "native")
        self.assertEqual(self.adapter.capabilities["resize"], "native")
        self.assertTrue(cocoa_window.CocoaWindow.capabilities["enabled"])
        self.callback.assert_called_once_with()

    def test_drag_failure_releases_listeners_and_restores_native_decorations(self):
        self.adapter.install()
        handle = self.monitors[0][1]
        self.native.performWindowDragWithEvent_ = Mock(
            side_effect=RuntimeError("drag failed")
        )
        handle(self.event(10))
        drag = self.event(11, x=230)
        with patch.object(cocoa_window.logger, "exception") as log:
            self.assertIs(handle(drag), drag)
        log.assert_called_once()
        self.assertEqual(self.removed_monitors, self.monitors)
        self.assertEqual(self.removed_observers, list(reversed(self.observers)))
        self.assertFalse(self.browser.frameless)
        self.assertEqual(
            self.adapter.capabilities,
            {"enabled": False, "move": "native", "resize": "native"},
        )
        self.callback.assert_called_once_with()

    def test_cleanup_and_notification_failures_do_not_escape_native_input_callback(
        self,
    ):
        self.adapter.install()
        handle = self.monitors[0][1]
        self.native.performWindowDragWithEvent_ = Mock(
            side_effect=RuntimeError("drag failed")
        )
        self.callback.side_effect = RuntimeError("notification failed")
        handle(self.event(10))
        drag = self.event(11, x=230)
        with (
            patch.object(cocoa_window.logger, "exception") as log,
            patch.object(
                self.appkit.NSEvent,
                "removeMonitor_",
                side_effect=RuntimeError("cleanup failed"),
            ),
        ):
            self.assertIs(handle(drag), drag)
        self.assertEqual(log.call_count, 3)
        self.assertEqual(self.removed_observers, list(reversed(self.observers)))
        self.assertFalse(self.browser.frameless)
        self.assertFalse(self.adapter.capabilities["enabled"])
        self.assertIs(handle(drag), drag)

    def test_failed_native_decoration_restoration_does_not_publish_disabled_shell(self):
        self.adapter.install()
        handle = self.monitors[0][1]
        self.native.performWindowDragWithEvent_ = Mock(
            side_effect=RuntimeError("drag failed")
        )
        self.native.setStyleMask_ = Mock(side_effect=RuntimeError("decoration failed"))
        handle(self.event(10))
        drag = self.event(11, x=230)
        with patch.object(cocoa_window.logger, "exception") as log:
            self.assertIs(handle(drag), drag)
        self.assertEqual(log.call_count, 2)
        self.assertTrue(self.adapter.capabilities["enabled"])
        self.callback.assert_not_called()
        # Input recovery must not retire the surviving custom control buttons.
        self.assertTrue(self.adapter.maximize())
        self.assertTrue(self.adapter.restore())
        self.assertTrue(self.adapter.minimize())

    def test_native_state_read_failure_recovers_without_escaping_notification(self):
        self.adapter.install()
        self.native.frame = Mock(side_effect=RuntimeError("state failed"))
        with patch.object(cocoa_window.logger, "exception") as log:
            self.emit("resize")
        log.assert_called_once()
        self.assertFalse(self.adapter.capabilities["enabled"])
        self.assertEqual(self.removed_monitors, self.monitors)
        self.callback.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
