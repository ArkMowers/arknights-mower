"""Exercise Linux GUI adapters with native event and window substitutes."""

from queue import Queue
from threading import Thread, get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from arknights_mower.utils import linux_window


class GtkWidget:
    def __init__(self):
        self.callbacks = {}
        self.disconnected = []

    def connect(self, name, callback):
        signal = len(self.callbacks) + 1
        self.callbacks[signal] = (name, callback)
        return signal

    def disconnect(self, signal):
        self.disconnected.append(signal)

    def emit(self, name, event=None):
        callback = next(
            callback for kind, callback in self.callbacks.values() if kind == name
        )
        return callback(self, event) if event is not None else callback(self)


@pytest.fixture
def gtk(monkeypatch):
    view = GtkWidget()
    view.add_events = Mock()
    view.get_allocated_width = lambda: 1000
    view.get_allocated_height = lambda: 700
    native = GtkWidget()
    native.state = 0
    handle = SimpleNamespace(
        get_state=lambda: native.state,
        begin_move_drag_for_device=Mock(),
        begin_resize_drag_for_device=Mock(),
    )
    native.get_window = lambda: handle
    native.get_settings = lambda: SimpleNamespace(
        get_property=lambda name: 400 if name.endswith("time") else 5
    )
    native.maximize = Mock(side_effect=lambda: setattr(native, "state", 2))
    native.deiconify = Mock(
        side_effect=lambda: setattr(native, "state", native.state & ~1)
    )
    native.unmaximize = Mock(
        side_effect=lambda: setattr(native, "state", native.state & ~2)
    )
    native.unfullscreen = Mock(
        side_effect=lambda: setattr(native, "state", native.state & ~4)
    )
    native.begin_move_drag = Mock()
    native.begin_resize_drag = Mock()
    native.set_decorated = Mock()
    monitor = SimpleNamespace(
        get_workarea=lambda: SimpleNamespace(width=1920, height=1040)
    )
    native.get_display = lambda: SimpleNamespace(
        get_monitor_at_window=lambda window: monitor
    )
    backend = SimpleNamespace(
        BrowserView=SimpleNamespace(
            instances={"test": SimpleNamespace(window=native, webview=view)}
        ),
        glib=SimpleNamespace(
            idle_add=Mock(side_effect=lambda callback: callback()),
            MainContext=SimpleNamespace(
                default=lambda: SimpleNamespace(is_owner=lambda: True)
            ),
        ),
        Gdk=SimpleNamespace(
            WindowState=SimpleNamespace(ICONIFIED=1, MAXIMIZED=2, FULLSCREEN=4),
            WindowEdge=SimpleNamespace(
                NORTH=1,
                NORTH_EAST=2,
                EAST=3,
                SOUTH_EAST=4,
                SOUTH=5,
                SOUTH_WEST=6,
                WEST=7,
                NORTH_WEST=8,
            ),
            EventMask=SimpleNamespace(BUTTON_PRESS_MASK=16),
            EventType=SimpleNamespace(BUTTON_PRESS=1, _2BUTTON_PRESS=2),
        ),
    )
    monkeypatch.setattr(linux_window, "import_module", lambda name: backend)
    regions = SimpleNamespace(hit_test=Mock(return_value="move"))
    changed = Mock()
    adapter = linux_window.GtkWindow(SimpleNamespace(uid="test"), regions, changed)
    assert adapter.install() is True
    return SimpleNamespace(
        adapter=adapter,
        native=native,
        handle=handle,
        view=view,
        backend=backend,
        regions=regions,
        changed=changed,
    )


def gtk_event(**values):
    return SimpleNamespace(
        **{
            "button": 1,
            "x": 40,
            "y": 20,
            "x_root": 140,
            "y_root": 120,
            "time": 1000,
            "type": 1,
            "get_device": lambda: "pointer-device",
            **values,
        }
    )


def test_gtk_moves_with_the_actual_native_press(gtk):
    assert gtk.view.emit("button-press-event", gtk_event()) is True
    gtk.regions.hit_test.assert_called_once_with(40, 20, 1000, 700)
    gtk.handle.begin_move_drag_for_device.assert_called_once_with(
        "pointer-device", 1, 140, 120, 1000
    )
    gtk.native.begin_move_drag.assert_not_called()


@pytest.mark.parametrize(
    "region, edge",
    [
        ("top", 1),
        ("top-right", 2),
        ("right", 3),
        ("bottom-right", 4),
        ("bottom", 5),
        ("bottom-left", 6),
        ("left", 7),
        ("top-left", 8),
    ],
)
def test_gtk_passes_each_resize_edge_and_real_event_to_gdk(gtk, region, edge):
    gtk.regions.hit_test.return_value = region
    assert gtk.view.emit("button-press-event", gtk_event()) is True
    gtk.handle.begin_resize_drag_for_device.assert_called_once_with(
        edge, "pointer-device", 1, 140, 120, 1000
    )


def test_gtk_uses_gtk_drag_api_when_device_api_is_unavailable(gtk):
    del gtk.handle.begin_move_drag_for_device
    del gtk.handle.begin_resize_drag_for_device
    gtk.view.emit("button-press-event", gtk_event())
    gtk.native.begin_move_drag.assert_called_once_with(1, 140, 120, 1000)
    gtk.regions.hit_test.return_value = "bottom-right"
    gtk.view.emit("button-press-event", gtk_event(time=1600))
    gtk.native.begin_resize_drag.assert_called_once_with(4, 1, 140, 120, 1600)


def test_gtk_leaves_html_controls_and_nonprimary_buttons_untouched(gtk):
    gtk.regions.hit_test.return_value = None
    assert gtk.view.emit("button-press-event", gtk_event()) is False
    assert gtk.view.emit("button-press-event", gtk_event(button=3)) is False
    gtk.handle.begin_move_drag_for_device.assert_not_called()


def test_gtk_double_click_toggles_once_for_gdk_duplicate_event(gtk):
    gtk.view.emit("button-press-event", gtk_event())
    gtk.view.emit("button-press-event", gtk_event(time=1100))
    gtk.view.emit("button-press-event", gtk_event(time=1100, type=2))
    gtk.native.maximize.assert_called_once_with()
    assert gtk.adapter.get_state() == "maximized"
    gtk.view.emit("button-press-event", gtk_event(time=2000))
    gtk.view.emit("button-press-event", gtk_event(time=2100, type=2))
    gtk.native.unmaximize.assert_called_once_with()
    assert gtk.adapter.get_state() == "normal"


def test_gtk_restore_unmaximizes_and_native_state_events_notify(gtk):
    gtk.native.state = 3
    assert gtk.adapter.get_state() == "minimized"
    assert gtk.adapter.restore() is True
    gtk.native.deiconify.assert_called_once_with()
    gtk.native.unmaximize.assert_called_once_with()
    assert gtk.adapter.get_state() == "normal"
    assert gtk.adapter.maximize() is True
    gtk.native.emit("window-state-event", SimpleNamespace())
    gtk.changed.assert_called_once_with()
    assert gtk.adapter.work_area() == (1920, 1040)


def test_gtk_dispose_disconnects_all_signals_and_prevents_late_drags(gtk):
    gtk.adapter.dispose()
    gtk.adapter.dispose()
    assert gtk.view.disconnected == [1]
    assert gtk.native.disconnected == [2, 1]
    assert gtk.view.emit("button-press-event", gtk_event()) is False
    gtk.handle.begin_move_drag_for_device.assert_not_called()


def test_gtk_native_drag_error_restores_decorations_and_notifies(gtk):
    gtk.handle.begin_move_drag_for_device.side_effect = RuntimeError("No display")
    assert gtk.view.emit("button-press-event", gtk_event()) is False
    gtk.native.set_decorated.assert_called_once_with(True)
    assert gtk.adapter.capabilities == {
        "enabled": False,
        "move": "native",
        "resize": "html",
    }
    gtk.changed.assert_called_once_with()
    assert gtk.view.disconnected == [1]


def test_gtk_worker_dispatches_window_commands_to_the_gui_thread(gtk):
    pending = Queue()
    gtk.backend.glib.idle_add = pending.put
    gtk.backend.glib.MainContext.default = lambda: SimpleNamespace(
        is_owner=lambda: False
    )
    results = []
    worker = Thread(target=lambda: results.append(gtk.adapter.maximize()))
    worker.start()
    callback = pending.get(timeout=1)
    gtk.native.maximize.assert_not_called()
    callback()
    worker.join(1)
    assert not worker.is_alive()
    assert results == [True]


class Point:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y

    def toPoint(self):
        return self


@pytest.fixture
def qt(monkeypatch):
    gui_thread = get_ident()
    handle = SimpleNamespace(
        startSystemMove=Mock(return_value=True),
        startSystemResize=Mock(return_value=True),
    )
    native = SimpleNamespace(state="normal")
    native.destroyed = SimpleNamespace(connect=Mock(), disconnect=Mock())
    native.thread = lambda: gui_thread
    native.windowHandle = lambda: handle
    native.create_window_trigger = SimpleNamespace(
        emit=Mock(side_effect=lambda callback: callback())
    )
    native.showMaximized = Mock(
        side_effect=lambda: setattr(native, "state", "maximized")
    )
    native.showNormal = Mock(side_effect=lambda: setattr(native, "state", "normal"))
    native.isMaximized = lambda: native.state == "maximized"
    native.isMinimized = lambda: native.state == "minimized"
    native.isFullScreen = lambda: native.state == "fullscreen"
    native.setWindowFlag = Mock()
    native.show = Mock()
    view = SimpleNamespace(
        mapFromGlobal=lambda point: Point(point.x() - 100, point.y() - 50),
        width=lambda: 1000,
        height=lambda: 700,
    )
    native.view = view
    app = SimpleNamespace(
        installEventFilter=Mock(),
        removeEventFilter=Mock(),
        doubleClickInterval=lambda: 400,
    )

    class QObject:
        def __init__(self, parent):
            self.parent = parent
            self.deleteLater = Mock()

    backend = SimpleNamespace(
        BrowserView=SimpleNamespace(instances={"test": native}),
        QApplication=SimpleNamespace(instance=lambda: app),
        QtCore=SimpleNamespace(
            QThread=SimpleNamespace(currentThread=get_ident),
            QObject=QObject,
            QEvent=SimpleNamespace(
                WindowStateChange=1, MouseButtonPress=2, MouseButtonDblClick=3
            ),
            Qt=SimpleNamespace(
                LeftButton=1,
                TopEdge=2,
                RightEdge=4,
                BottomEdge=8,
                LeftEdge=16,
                FramelessWindowHint=32,
            ),
        ),
    )
    handle.screen = lambda: SimpleNamespace(
        availableGeometry=lambda: SimpleNamespace(
            width=lambda: 1600, height=lambda: 860
        )
    )
    monkeypatch.setattr(linux_window, "import_module", lambda name: backend)
    regions = SimpleNamespace(hit_test=Mock(return_value="move"))
    changed = Mock()
    adapter = linux_window.QtWindow(SimpleNamespace(uid="test"), regions, changed)
    assert adapter.install() is True
    return SimpleNamespace(
        adapter=adapter,
        native=native,
        handle=handle,
        view=view,
        backend=backend,
        app=app,
        regions=regions,
        changed=changed,
    )


def qt_event(kind=2, timestamp=1000, button=1):
    return SimpleNamespace(
        type=lambda: kind,
        button=lambda: button,
        timestamp=lambda: timestamp,
        globalPos=lambda: Point(140, 70),
        accept=Mock(),
    )


def test_qt_filters_webengine_children_and_uses_system_move(qt):
    child = SimpleNamespace(parent=lambda: qt.view)
    event = qt_event()
    assert qt.adapter._filter.eventFilter(child, event) is True
    qt.handle.startSystemMove.assert_called_once_with()
    qt.regions.hit_test.assert_called_once_with(40, 20, 1000, 700)
    event.accept.assert_called_once_with()


def test_qt_uses_qt6_event_positions_and_scoped_edge_enums(qt):
    qt.backend.QtCore.Qt.Edge = SimpleNamespace(TopEdge=2, LeftEdge=16)
    qt.regions.hit_test.return_value = "top-left"
    event = qt_event()
    del event.globalPos
    event.globalPosition = lambda: Point(140, 70)
    assert qt.adapter._filter.eventFilter(qt.view, event) is True
    qt.handle.startSystemResize.assert_called_once_with(18)


def test_qt_does_not_intercept_controls_or_other_windows(qt):
    qt.regions.hit_test.return_value = None
    assert qt.adapter._filter.eventFilter(qt.view, qt_event()) is False
    unrelated = SimpleNamespace(parent=lambda: None)
    assert qt.adapter._filter.eventFilter(unrelated, qt_event()) is False
    assert qt.adapter._filter.eventFilter(qt.view, qt_event(button=2)) is False
    qt.handle.startSystemMove.assert_not_called()


def test_qt_double_click_uses_real_native_state_and_show_normal(qt):
    qt.adapter._filter.eventFilter(qt.view, qt_event())
    qt.adapter._filter.eventFilter(qt.view, qt_event(timestamp=1100, kind=3))
    qt.native.showMaximized.assert_called_once_with()
    assert qt.adapter.get_state() == "maximized"
    qt.adapter._filter.eventFilter(qt.view, qt_event(timestamp=2000))
    qt.adapter._filter.eventFilter(qt.view, qt_event(timestamp=2100, kind=3))
    qt.native.showNormal.assert_called_once_with()
    qt.adapter._filter.eventFilter(qt.native, qt_event(kind=1))
    qt.changed.assert_called_once_with()
    qt.native.state = "minimized"
    assert qt.adapter.get_state() == "minimized"
    assert qt.adapter.restore() is True
    assert qt.adapter.get_state() == "normal"
    assert qt.adapter.maximize() is True
    assert qt.adapter.work_area() == (1600, 860)


def test_qt_dispose_removes_filter_and_schedules_deletion(qt):
    event_filter = qt.adapter._filter
    qt.adapter.dispose()
    qt.adapter.dispose()
    qt.app.removeEventFilter.assert_called_once_with(event_filter)
    event_filter.deleteLater.assert_called_once_with()
    qt.native.destroyed.disconnect.assert_called_once_with(qt.adapter._destroy)
    assert event_filter.eventFilter(qt.view, qt_event()) is False


def test_qt_native_destruction_releases_the_application_event_filter(qt):
    event_filter = qt.adapter._filter
    qt.native.thread = Mock(side_effect=RuntimeError("Native QWidget was deleted"))
    qt.native.destroyed.connect.call_args.args[0]()
    qt.app.removeEventFilter.assert_called_once_with(event_filter)
    qt.native.destroyed.disconnect.assert_not_called()
    assert event_filter.eventFilter(qt.view, qt_event()) is False


def test_native_work_area_queries_allow_an_unavailable_monitor(gtk, qt):
    gtk.native.get_display = lambda: SimpleNamespace(
        get_monitor_at_window=lambda _: None
    )
    qt.handle.screen = lambda: None
    assert gtk.adapter.work_area() is None
    assert qt.adapter.work_area() is None


def test_qt_rejects_old_qt_and_restores_native_window_decorations(qt):
    qt.adapter.dispose()
    del qt.handle.startSystemMove
    assert qt.adapter.install() is False
    qt.native.setWindowFlag.assert_called_once_with(32, False)
    qt.native.show.assert_called_once_with()
    assert qt.adapter.capabilities["enabled"] is False


def test_qt_compositor_rejection_restores_decorations_and_notifies(qt):
    event_filter = qt.adapter._filter
    qt.handle.startSystemMove.return_value = False
    assert event_filter.eventFilter(qt.view, qt_event()) is False
    qt.native.setWindowFlag.assert_called_once_with(32, False)
    qt.app.removeEventFilter.assert_called_once_with(event_filter)
    qt.changed.assert_called_once_with()
    assert qt.adapter.capabilities["enabled"] is False


def test_qt_worker_dispatches_using_the_existing_gui_signal(qt):
    pending = Queue()
    qt.native.create_window_trigger.emit = pending.put
    results = []
    worker = Thread(target=lambda: results.append(qt.adapter.restore()))
    worker.start()
    callback = pending.get(timeout=1)
    qt.native.showNormal.assert_not_called()
    callback()
    worker.join(1)
    assert not worker.is_alive()
    assert results == [True]


def test_expired_gui_dispatch_does_not_apply_late_window_commands(gtk, monkeypatch):
    pending = Queue()
    monkeypatch.setattr(linux_window, "_GUI_TIMEOUT", 0.01)
    gtk.backend.glib.idle_add = pending.put
    gtk.backend.glib.MainContext.default = lambda: SimpleNamespace(
        is_owner=lambda: False
    )
    gtk.adapter._thread = None
    with pytest.raises(TimeoutError):
        gtk.adapter.maximize()
    callback = pending.get_nowait()
    assert callback() is False
    gtk.native.maximize.assert_not_called()


def test_gtk_fullscreen_counts_as_maximized_and_restore_exits_it(gtk):
    gtk.native.state = 4
    assert gtk.adapter.get_state() == "maximized"
    gtk.regions.hit_test.return_value = "bottom-right"
    assert gtk.view.emit("button-press-event", gtk_event()) is False
    gtk.handle.begin_resize_drag_for_device.assert_not_called()
    assert gtk.adapter.restore() is True
    gtk.native.unfullscreen.assert_called_once_with()
    assert gtk.adapter.get_state() == "normal"


def test_qt_fullscreen_counts_as_maximized_and_double_click_restores_it(qt):
    qt.native.state = "fullscreen"
    assert qt.adapter.get_state() == "maximized"
    assert qt.adapter._filter.eventFilter(qt.view, qt_event(kind=3)) is True
    qt.native.showNormal.assert_called_once_with()
    qt.native.showMaximized.assert_not_called()
    assert qt.adapter.get_state() == "normal"


def test_gtk_decoration_failure_keeps_custom_controls_visible(gtk):
    gtk.native.set_decorated.side_effect = RuntimeError("Decoration unavailable")
    with pytest.raises(RuntimeError, match="Decoration unavailable"):
        gtk.adapter.fallback_decorations()
    assert gtk.adapter.capabilities["enabled"] is True
    gtk.changed.assert_not_called()
    gtk.handle.begin_move_drag_for_device.side_effect = RuntimeError("Drag failed")
    assert gtk.view.emit("button-press-event", gtk_event()) is False
    assert gtk.adapter.capabilities["enabled"] is True


def test_qt_decoration_failure_keeps_custom_controls_visible(qt):
    qt.native.setWindowFlag.side_effect = RuntimeError("Decoration unavailable")
    with pytest.raises(RuntimeError, match="Decoration unavailable"):
        qt.adapter.fallback_decorations()
    assert qt.adapter.capabilities["enabled"] is True
    qt.changed.assert_not_called()
    qt.handle.startSystemMove.side_effect = RuntimeError("Drag failed")
    assert qt.adapter._filter.eventFilter(qt.view, qt_event()) is False
    assert qt.adapter.capabilities["enabled"] is True


def test_gtk_install_failure_does_not_disable_controls_when_decorating_fails(gtk):
    gtk.adapter.dispose()
    gtk.view.connect = Mock(side_effect=RuntimeError("Signals unavailable"))
    gtk.native.set_decorated.side_effect = RuntimeError("Decoration unavailable")
    with pytest.raises(RuntimeError, match="Decoration unavailable"):
        gtk.adapter.install()
    assert gtk.adapter.capabilities["enabled"] is True


def test_qt_install_failure_does_not_disable_controls_when_decorating_fails(qt):
    qt.adapter.dispose()
    del qt.handle.startSystemMove
    qt.native.setWindowFlag.side_effect = RuntimeError("Decoration unavailable")
    with pytest.raises(RuntimeError, match="Decoration unavailable"):
        qt.adapter.install()
    assert qt.adapter.capabilities["enabled"] is True


def test_gtk_timed_out_cleanup_still_disconnects_signals_when_gui_resumes(
    gtk, monkeypatch
):
    pending = Queue()
    monkeypatch.setattr(linux_window, "_GUI_TIMEOUT", 0.01)
    gtk.backend.glib.idle_add = pending.put
    gtk.backend.glib.MainContext.default = lambda: SimpleNamespace(
        is_owner=lambda: False
    )
    gtk.adapter._thread = None
    gtk.adapter.dispose()
    assert gtk.view.disconnected == []
    assert gtk.adapter._active is False
    pending.get_nowait()()
    assert gtk.view.disconnected == [1]
    assert gtk.native.disconnected == [2, 1]


def test_qt_timed_out_cleanup_still_removes_filter_when_gui_resumes(qt, monkeypatch):
    pending = Queue()
    monkeypatch.setattr(linux_window, "_GUI_TIMEOUT", 0.01)
    qt.native.create_window_trigger.emit = pending.put
    qt.native.thread = lambda: -1
    event_filter = qt.adapter._filter
    qt.adapter.dispose()
    qt.app.removeEventFilter.assert_not_called()
    assert qt.adapter._active is False
    pending.get_nowait()()
    qt.app.removeEventFilter.assert_called_once_with(event_filter)
    event_filter.deleteLater.assert_called_once_with()


def test_gtk_cleanup_retains_failed_signal_for_a_later_attempt(gtk):
    original_disconnect = gtk.view.disconnect
    gtk.view.disconnect = Mock(side_effect=RuntimeError("Temporarily busy"))
    gtk.adapter.dispose()
    assert gtk.native.disconnected == [2, 1]
    assert len(gtk.adapter._signals) == 1
    gtk.view.disconnect = original_disconnect
    gtk.adapter.dispose()
    assert gtk.view.disconnected == [1]
    assert gtk.adapter._signals == []


def test_native_state_callback_failures_do_not_escape_gui_callbacks(gtk, qt):
    gtk.changed.side_effect = RuntimeError("Subscriber failed")
    qt.changed.side_effect = RuntimeError("Subscriber failed")
    assert gtk.native.emit("window-state-event", SimpleNamespace()) is False
    assert qt.adapter._filter.eventFilter(qt.native, qt_event(kind=1)) is False
