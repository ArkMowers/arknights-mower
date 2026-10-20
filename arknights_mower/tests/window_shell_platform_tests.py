"""Verify native adapters through the bridge and desktop-window lifecycle."""

import ctypes
import json
from queue import Queue
from threading import Event, Thread, current_thread, get_ident
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from arknights_mower.utils import window_backend, window_shell


class Signal:
    def __init__(self, before_fire=None):
        self.handlers = []
        self.flag = Event()
        self.before_fire = before_fire

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args):
        if self.before_fire is not None:
            self.before_fire(*args)
        self.flag.set()
        for handler in tuple(self.handlers):
            handler(*args)

    def is_set(self):
        return self.flag.is_set()


class DesktopWindow:
    def __init__(self, backend):
        self.uid = "offline-desktop"
        self.gui = SimpleNamespace(__name__="webview.platforms." + backend)
        self.events = SimpleNamespace(
            **{
                name: Signal()
                for name in (
                    "shown",
                    "loaded",
                    "resized",
                    "maximized",
                    "minimized",
                    "restored",
                    "closing",
                    "closed",
                )
            }
        )
        self.exposed = {}
        self.current_size = (1000, 600)
        self.events.resized.before_fire = self._resize
        self.evaluations = Queue()
        self.close_requests = Queue()
        self.close_dispatches = Queue()
        self.close_listener_ready = False
        self.evaluation_threads = []
        self.confirm_close = True
        self.minimize = Mock()
        self.maximize = Mock()
        self.restore = Mock()
        self.destroy = Mock(side_effect=self._destroy)

    def expose(self, *methods):
        self.exposed.update((method.__name__, method) for method in methods)

    def _resize(self, width, height):
        self.current_size = (width, height)

    def evaluate_js(self, script):
        if window_shell.WINDOW_SHELL_CLOSE_EVENT in script:
            assert "{cancelable: true}" in script
            self.close_dispatches.put(self.close_listener_ready)
            if not self.close_listener_ready:
                return False
            self.close_requests.put(get_ident())
            return True
        state, _ = json.JSONDecoder().raw_decode(script.split("detail: ", 1)[1])
        self.evaluation_threads.append(get_ident())
        self.evaluations.put(state)

    def wait_for_state(self, expected):
        deadline = monotonic() + 2
        while True:
            state = self.evaluations.get(timeout=max(0.01, deadline - monotonic()))
            if state["state"] == expected:
                return state
            assert monotonic() < deadline, f"No {expected} state was published"

    def _destroy(self):
        self.events.closing.fire()
        self.events.closed.fire()


class NativeWindow:
    def __init__(self, backend, regions, changed, window):
        self.backend = backend
        self.regions = regions
        self.changed = changed
        self.state = "normal"
        self.capabilities = {
            "enabled": True,
            "move": "native",
            "resize": "native" if backend == "cocoa" else "html",
        }
        self.install = Mock(return_value=True)
        self.dispose = Mock()
        self.get_state = Mock(side_effect=lambda: self.state)
        self.get_normal_size = Mock(
            side_effect=lambda: (
                window.current_size if self.get_state() == "normal" else None
            )
        )
        self.maximize = Mock(side_effect=lambda: self.change_state("maximized"))
        self.restore = Mock(side_effect=lambda: self.change_state("normal"))
        self.fallback_decorations = Mock(side_effect=self._decorate)

    def change_state(self, state):
        self.state = state
        self.changed()
        return True

    def _decorate(self):
        self.capabilities["enabled"] = False
        self.changed()


@pytest.fixture
def native_factory(monkeypatch):
    adapters = []

    def create(backend, window, regions, changed):
        adapter = NativeWindow(backend, regions, changed, window)
        adapters.append(adapter)
        return adapter

    monkeypatch.setattr(window_backend, "create_native_window", create)
    return SimpleNamespace(adapters=adapters, create=create)


@pytest.mark.parametrize(
    "backend, system", [("cocoa", "Darwin"), ("gtk", "Linux"), ("qt", "Linux")]
)
def test_real_attach_exposes_functions_and_waits_for_native_initialization(
    native_factory, backend, system
):
    window = DesktopWindow(backend)
    bridge = window_shell.attach_window_shell(window, system=system, backend=backend)
    try:
        assert set(window.exposed) == {
            "minimize",
            "maximize",
            "restore",
            "close",
            "start_move",
            "start_resize",
            "get_window_state",
            "get_platform",
            "ready_for_native_close",
            "set_hit_regions",
            "get_close_preference",
            "set_close_preference",
            "get_window_launch_mode",
            "set_window_launch_mode",
        }
        assert all(callable(method) for method in window.exposed.values())
        assert bridge.wait_until_ready(timeout=0) is False
        with pytest.raises(RuntimeError, match="initializing"):
            window.exposed["get_platform"]()
        window.events.shown.fire()
        assert bridge.wait_until_ready(timeout=0) is True
        adapter = native_factory.adapters[0]
        adapter.install.assert_called_once_with()
        handshake = window.exposed["get_platform"]()
        assert handshake["platform"] == ("macos" if backend == "cocoa" else "linux")
        assert handshake["capabilities"] == adapter.capabilities
        window.events.shown.fire()
        assert len(native_factory.adapters) == 1
        adapter.install.assert_called_once_with()
    finally:
        bridge.dispose()


def test_actual_native_backend_owns_the_bridge_after_window_creation(native_factory):
    window = DesktopWindow("qt")
    bridge = window_shell.attach_window_shell(window, system="Linux", backend="gtk")
    try:
        window.events.shown.fire()
        assert native_factory.adapters[0].backend == "qt"
    finally:
        bridge.dispose()


def test_bridge_routes_commands_and_prioritizes_native_state_over_stale_events(
    native_factory,
):
    window = DesktopWindow("cocoa")
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    try:
        window.events.shown.fire()
        adapter = native_factory.adapters[0]
        assert window.exposed["maximize"]() is True
        adapter.maximize.assert_called_once_with()
        window.maximize.assert_not_called()
        window.events.restored.fire()
        assert window.exposed["get_window_state"]()["state"] == "maximized"
        assert window.exposed["restore"]() is True
        adapter.restore.assert_called_once_with()
        window.restore.assert_not_called()
        window.events.maximized.fire()
        assert window.exposed["get_window_state"]()["state"] == "normal"
        adapter.state = "minimized"
        assert window.exposed["get_window_state"]()["minimized"] is True
        assert window.exposed["start_move"]() is False
        assert window.exposed["start_resize"]("bottom-right") is False
        assert window.exposed["minimize"]() is True
        window.minimize.assert_called_once_with()
    finally:
        bridge.dispose()


def test_bridge_passes_html_regions_to_the_installed_native_adapter_and_clears_on_close(
    native_factory,
):
    window = DesktopWindow("gtk")
    bridge = window_shell.attach_window_shell(window, system="Linux", backend="gtk")
    window.events.shown.fire()
    adapter = native_factory.adapters[0]
    assert (
        window.exposed["set_hit_regions"](
            {
                "width": 1000,
                "height": 700,
                "regions": [
                    {"kind": "move", "x": 50, "y": 0, "width": 800, "height": 36}
                ],
            }
        )
        is True
    )
    assert adapter.regions.hit_test(100, 20, 1000, 700) == "move"
    assert adapter.regions.hit_test(900, 20, 1000, 700) is None
    assert window.exposed["close"]() is True
    assert window.confirm_close is False
    adapter.dispose.assert_called_once_with()
    assert adapter.regions.hit_test(100, 20, 1000, 700) is None
    assert bridge.set_hit_regions({"width": 1, "height": 1, "regions": []}) is False
    assert bridge._worker.is_alive() is False


@pytest.mark.parametrize("decoration_failure", [False, True])
def test_bridge_install_failure_only_disables_html_after_decoration_succeeds(
    monkeypatch, native_factory, decoration_failure
):
    def create(*args):
        adapter = native_factory.create(*args)
        adapter.install.side_effect = RuntimeError("Input adapter unavailable")
        if decoration_failure:
            adapter.fallback_decorations.side_effect = RuntimeError(
                "Decorations unavailable"
            )
        return adapter

    monkeypatch.setattr(window_backend, "create_native_window", create)
    window = DesktopWindow("gtk")
    bridge = window_shell.attach_window_shell(window, system="Linux", backend="gtk")
    try:
        window.events.shown.fire()
        adapter = native_factory.adapters[0]
        assert bridge.wait_until_ready(timeout=0) is True
        adapter.dispose.assert_not_called()
        adapter.fallback_decorations.assert_called_once_with()
        assert bridge.get_platform()["capabilities"]["enabled"] is decoration_failure
    finally:
        bridge.dispose()


def test_native_notifications_publish_mode_and_capabilities_on_one_worker(
    native_factory,
):
    window = DesktopWindow("qt")
    window.events.loaded.fire()
    bridge = window_shell.attach_window_shell(window, system="Linux", backend="qt")
    modes = []
    bridge.on_mode_changed = modes.append
    try:
        window.events.shown.fire()
        window.wait_for_state("normal")
        adapter = native_factory.adapters[0]
        adapter.change_state("maximized")
        window.wait_for_state("maximized")
        adapter.capabilities["enabled"] = False
        adapter.change_state("normal")
        assert window.wait_for_state("normal")["capabilities"]["enabled"] is False
        assert modes == ["normal", "maximized", "normal"]
        assert len(set(window.evaluation_threads)) == 1
        assert window.evaluation_threads[0] != get_ident()
    finally:
        bridge.dispose()


def test_mode_save_failure_does_not_stop_native_state_updates(native_factory):
    window = DesktopWindow("cocoa")
    window.events.loaded.fire()
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    bridge.on_mode_changed = Mock(
        side_effect=[OSError("Read-only configuration"), None]
    )
    try:
        window.events.shown.fire()
        window.wait_for_state("normal")
        native_factory.adapters[0].change_state("maximized")
        window.wait_for_state("maximized")
        assert bridge._worker.is_alive() is True
        assert [call.args for call in bridge.on_mode_changed.call_args_list] == [
            ("normal",),
            ("maximized",),
        ]
    finally:
        bridge.dispose()


def test_unconfirmed_mode_keeps_display_state_and_saves_after_native_recovery(
    monkeypatch, native_factory
):
    def create(*args):
        adapter = native_factory.create(*args)
        adapter.get_state.side_effect = TimeoutError("GUI temporarily unavailable")
        return adapter

    monkeypatch.setattr(window_backend, "create_native_window", create)
    window = DesktopWindow("cocoa")
    window.events.loaded.fire()
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    modes = []
    bridge.on_mode_changed = modes.append
    try:
        window.events.shown.fire()
        window.wait_for_state("normal")
        assert modes == []
        adapter = native_factory.adapters[0]
        adapter.get_state.side_effect = lambda: adapter.state
        adapter.change_state("normal")
        window.wait_for_state("normal")
        assert modes == ["normal"]
    finally:
        bridge.dispose()


@pytest.fixture
def desktop_url_window(monkeypatch):
    import webview

    import webview_ui
    from arknights_mower.utils import config, path, windows_frameless
    from arknights_mower.utils.config import gui

    window = DesktopWindow("gtk")
    create_window = Mock(return_value=window)
    prepare_backend = Mock()
    start = Mock()
    browser_open = Mock()
    instance_name = "测试实例 & + / ?"
    browser_url = "http://127.0.0.1:18080?token=offline-session"
    monkeypatch.setattr(config, "load_conf", Mock())
    monkeypatch.setattr(config, "conf", SimpleNamespace(theme="dark"))
    monkeypatch.setattr(path, "global_space", path.global_space)
    monkeypatch.setattr(
        gui, "load_window_ratio", lambda: window_shell.WindowRatio(0.5, 0.6)
    )
    monkeypatch.setattr(gui, "load_window_launch_mode", lambda: "normal")
    monkeypatch.setattr(gui, "save_window_ratio", Mock())
    monkeypatch.setattr(
        window_shell, "_screen_work_area", lambda: window_shell.WindowSize(2000, 1000)
    )
    monkeypatch.setattr(window_backend, "prepare_window_backend", prepare_backend)
    monkeypatch.setattr(windows_frameless, "install_windows_frameless_resize", Mock())
    monkeypatch.setattr(webview_ui, "title_version", lambda *args: "offline-version")
    monkeypatch.setattr(webview_ui, "width", 1450, raising=False)
    monkeypatch.setattr(webview_ui, "height", 850, raising=False)
    monkeypatch.setattr(webview, "create_window", create_window)
    monkeypatch.setattr(webview, "start", start)
    monkeypatch.setattr("webbrowser.open", browser_open)

    def launch(backend):
        prepare_backend.return_value = backend
        window.gui.__name__ = "webview.platforms." + backend
        webview_ui.webview_window(
            SimpleNamespace(recv=Mock(side_effect=EOFError)),
            path.global_space,
            instance_name,
            "127.0.0.1",
            18080,
            browser_url,
            True,
        )

    return SimpleNamespace(
        launch=launch,
        create_window=create_window,
        prepare_backend=prepare_backend,
        start=start,
        browser_open=browser_open,
        browser_url=browser_url,
        instance_name=instance_name,
    )


@pytest.mark.parametrize(
    "backend, shell_enabled",
    [
        ("winforms", True),
        ("cocoa", True),
        ("gtk", True),
        ("qt", True),
        ("unknown", False),
    ],
)
def test_desktop_window_keeps_encoded_instance_name_in_its_own_url(
    desktop_url_window, backend, shell_enabled
):
    fixture = desktop_url_window
    with pytest.raises(SystemExit):
        fixture.launch(backend)
    args, kwargs = fixture.create_window.call_args
    assert (
        args[0]
        == f"arknights-mower offline-version - mower@18080({fixture.instance_name})"
    )
    query = {
        "token": ["offline-session"],
        "instance_name": [fixture.instance_name],
        "window_theme": ["dark"],
        "mower_version": ["offline-version"],
    }
    if shell_enabled:
        query["window_shell"] = ["1"]
    assert parse_qs(urlsplit(args[1]).query) == query
    assert kwargs["frameless"] is shell_enabled
    fixture.browser_open.assert_not_called()


@pytest.mark.parametrize("backend", ["winforms", "cocoa", "gtk", "qt", "unknown"])
def test_desktop_window_start_failure_opens_the_original_browser_url(
    desktop_url_window, backend
):
    fixture = desktop_url_window
    fixture.start.side_effect = RuntimeError("Window startup unavailable")
    fixture.launch(backend)
    fixture.create_window.assert_called_once()
    fixture.browser_open.assert_called_once_with(fixture.browser_url)


def test_desktop_backend_initialization_failure_opens_the_original_browser_url(
    desktop_url_window,
):
    fixture = desktop_url_window
    fixture.prepare_backend.side_effect = RuntimeError("Backend unavailable")
    fixture.launch("gtk")
    fixture.create_window.assert_not_called()
    fixture.start.assert_not_called()
    fixture.browser_open.assert_called_once_with(fixture.browser_url)


def run_desktop_window(
    monkeypatch,
    native_factory,
    backend,
    launch_mode,
    scenario,
    loaded_before_shown=False,
):
    import webview

    import webview_ui
    from arknights_mower.utils import config, path
    from arknights_mower.utils.config import gui

    window = DesktopWindow(backend)
    create_window = Mock(return_value=window)
    save_ratio = Mock()
    save_mode = Mock()
    forbidden_win32 = Mock(
        side_effect=AssertionError("Non-Windows window entered Win32")
    )
    monkeypatch.setattr(ctypes, "WinDLL", forbidden_win32, raising=False)
    monkeypatch.setattr(
        window_shell.platform,
        "system",
        lambda: "Darwin" if backend == "cocoa" else "Linux",
    )
    monkeypatch.setattr(
        window_shell, "_screen_work_area", lambda: window_shell.WindowSize(2000, 1000)
    )
    monkeypatch.setattr(window_backend, "prepare_window_backend", lambda: backend)
    monkeypatch.setattr(config, "load_conf", Mock())
    monkeypatch.setattr(config, "conf", SimpleNamespace(theme="light"))
    monkeypatch.setattr(path, "global_space", path.global_space)
    monkeypatch.setattr(
        gui, "load_window_ratio", lambda: window_shell.WindowRatio(0.5, 0.6)
    )
    monkeypatch.setattr(gui, "load_window_launch_mode", lambda: launch_mode)
    monkeypatch.setattr(gui, "save_window_ratio", save_ratio)
    monkeypatch.setattr(gui, "save_window_mode", save_mode)
    monkeypatch.setattr(webview_ui, "title_version", lambda *args: "offline-version")
    monkeypatch.setattr(
        webview_ui, "width", getattr(webview_ui, "width", 1450), raising=False
    )
    monkeypatch.setattr(
        webview_ui, "height", getattr(webview_ui, "height", 850), raising=False
    )
    monkeypatch.setattr(webview, "create_window", create_window)

    def start(**kwargs):
        assert kwargs == {"gui": backend if backend in ("gtk", "qt") else None}
        if loaded_before_shown:
            load_errors = []

            def load():
                try:
                    window.events.loaded.fire()
                except Exception as error:
                    load_errors.append(error)

            loaded = Thread(target=load)
            loaded.start()
            assert window.events.loaded.flag.wait(timeout=1)
            window.events.shown.fire()
            loaded.join(timeout=1)
            assert loaded.is_alive() is False
            assert load_errors == []
        else:
            window.events.shown.fire()
            window.events.loaded.fire()
        scenario(window, native_factory.adapters[0], save_mode)

    monkeypatch.setattr(webview, "start", start)
    child = SimpleNamespace(recv=Mock(side_effect=EOFError))
    with pytest.raises(SystemExit):
        webview_ui.webview_window(
            child,
            path.global_space,
            "Offline",
            "127.0.0.1",
            18080,
            "http://127.0.0.1:18080/",
            False,
        )
    forbidden_win32.assert_not_called()
    assert create_window.call_args.kwargs["frameless"] is True
    assert create_window.call_args.kwargs["easy_drag"] is False
    assert create_window.call_args.kwargs["width"] == 1000
    assert create_window.call_args.kwargs["height"] == 600
    assert "window_shell=1" in create_window.call_args.args[1]
    assert window.exposed["get_window_state"].__self__._worker.is_alive() is False
    return save_ratio


@pytest.mark.parametrize("backend", ["gtk", "qt", "cocoa"])
def test_real_desktop_window_keeps_normal_ratio_through_maximize_and_close(
    monkeypatch, native_factory, backend
):
    def scenario(window, adapter, save_mode):
        window.events.resized.fire(1200, 700)
        window.wait_for_state("normal")
        adapter.change_state("maximized")
        window.events.resized.fire(2000, 1000)
        window.wait_for_state("maximized")
        assert "maximized" in [call.args[0] for call in save_mode.call_args_list]
        window.events.closing.fire()
        window.events.resized.fire(1500, 800)
        window.events.closed.fire()

    saved = run_desktop_window(monkeypatch, native_factory, backend, "normal", scenario)
    saved.assert_called_once_with(window_shell.WindowRatio(0.6, 0.7))


@pytest.mark.parametrize("loaded_before_shown", [False, True])
def test_cocoa_startup_maximize_mode_callback_releases_normal_size_persistence(
    monkeypatch, native_factory, loaded_before_shown
):
    def scenario(window, adapter, save_mode):
        adapter.maximize.assert_called_once_with()
        window.wait_for_state("maximized")
        assert save_mode.call_args.args == ("maximized",)
        window.events.resized.fire(2000, 1000)
        adapter.change_state("normal")
        window.wait_for_state("normal")
        assert save_mode.call_args.args == ("normal",)
        window.events.resized.fire(1200, 700)
        window.wait_for_state("normal")
        window.events.closing.fire()
        window.events.closed.fire()

    saved = run_desktop_window(
        monkeypatch,
        native_factory,
        "cocoa",
        "maximized",
        scenario,
        loaded_before_shown=loaded_before_shown,
    )
    saved.assert_called_once_with(window_shell.WindowRatio(0.6, 0.7))


@pytest.mark.parametrize("backend", ["gtk", "qt", "cocoa"])
@pytest.mark.parametrize("recover", [False, True])
def test_real_desktop_window_requires_confirmed_state_for_saved_normal_size(
    monkeypatch, native_factory, backend, recover
):
    def scenario(window, adapter, save_mode):
        window.events.resized.fire(1200, 700)
        window.wait_for_state("normal")
        adapter.state = "maximized"
        adapter.get_state.side_effect = TimeoutError("GUI temporarily unavailable")
        window.events.resized.fire(2000, 1000)
        window.wait_for_state("normal")
        if recover:
            adapter.get_state.side_effect = lambda: adapter.state
            adapter.change_state("normal")
            window.wait_for_state("normal")
            window.events.resized.fire(1300, 750)
            window.wait_for_state("normal")
        window.events.closing.fire()
        window.events.closed.fire()

    saved = run_desktop_window(monkeypatch, native_factory, backend, "normal", scenario)
    expected = (
        window_shell.WindowRatio(0.65, 0.75)
        if recover
        else window_shell.WindowRatio(0.6, 0.7)
    )
    saved.assert_called_once_with(expected)


@pytest.mark.parametrize("backend", ["gtk", "qt", "cocoa"])
def test_real_desktop_window_saves_normal_size_when_startup_modes_are_coalesced(
    monkeypatch, native_factory, backend
):
    can_publish = Event()
    publish = window_shell.WindowShellBridge._publish_native_changes

    def publish_after_restore(bridge):
        assert can_publish.wait(timeout=2)
        publish(bridge)

    monkeypatch.setattr(
        window_shell.WindowShellBridge,
        "_publish_native_changes",
        publish_after_restore,
    )

    def scenario(window, adapter, save_mode):
        adapter.maximize.assert_called_once_with()
        assert adapter.state == "maximized"
        try:
            adapter.change_state("normal")
        finally:
            can_publish.set()
        window.wait_for_state("normal")
        assert "maximized" not in [call.args[0] for call in save_mode.call_args_list]
        window.events.resized.fire(1200, 700)
        window.wait_for_state("normal")
        window.events.closing.fire()
        window.events.closed.fire()

    try:
        saved = run_desktop_window(
            monkeypatch, native_factory, backend, "maximized", scenario
        )
    finally:
        can_publish.set()
    saved.assert_called_once_with(window_shell.WindowRatio(0.6, 0.7))


@pytest.mark.parametrize("backend", ["cocoa", "gtk", "qt"])
def test_delayed_maximize_resize_reads_current_normal_geometry(
    monkeypatch, native_factory, backend
):
    def scenario(window, adapter, save_mode):
        window.events.resized.fire(1200, 700)
        window.wait_for_state("normal")
        probing, resume = Event(), Event()

        def state():
            if current_thread().name == "delayed-size-sample":
                probing.set()
                assert resume.wait(2)
            return adapter.state

        adapter.get_state.side_effect = state
        adapter.state = "maximized"
        old = Thread(
            name="delayed-size-sample",
            target=lambda: window.events.resized.fire(2000, 1000),
        )
        old.start()
        try:
            assert probing.wait(2)
            adapter.state = "normal"
            window.current_size = (1200, 700)
        finally:
            resume.set()
            old.join(2)
        assert not old.is_alive()
        window.events.closing.fire()
        window.events.closed.fire()

    saved = run_desktop_window(monkeypatch, native_factory, backend, "normal", scenario)
    saved.assert_called_once_with(window_shell.WindowRatio(0.6, 0.7))


def test_native_close_waits_for_the_frontend_close_choice(native_factory):
    window = DesktopWindow("cocoa")
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    try:
        window.events.shown.fire()
        assert bridge.request_native_close() is True
        assert window.close_requests.empty()
        window.events.loaded.fire()
        window.close_listener_ready = True
        assert window.exposed["ready_for_native_close"]() is True
        assert window.close_requests.get(timeout=2) != get_ident()
        window.destroy.assert_not_called()
        assert bridge.close() is True
        assert bridge.request_native_close() is False
        window.destroy.assert_called_once_with()
    finally:
        bridge.dispose()


def test_native_close_waits_for_listener_acknowledgement_after_page_load(
    native_factory,
):
    window = DesktopWindow("cocoa")
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    try:
        window.events.shown.fire()
        assert bridge.request_native_close() is True
        window.events.loaded.fire()
        window.wait_for_state("normal")
        assert window.close_requests.empty()
        assert window.close_dispatches.empty()
        assert bridge._pending_close.is_set()
        window.close_listener_ready = True
        assert window.exposed["ready_for_native_close"]() is True
        assert window.close_requests.get(timeout=2) != get_ident()
        assert window.exposed["ready_for_native_close"]() is True
    finally:
        bridge.dispose()
    assert window.close_requests.empty()
    assert bridge.request_native_close() is False
    assert window.exposed["ready_for_native_close"]() is False


def test_native_close_survives_a_page_reload_without_a_listener(native_factory):
    window = DesktopWindow("cocoa")
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    try:
        window.events.shown.fire()
        window.events.loaded.fire()
        window.close_listener_ready = True
        assert bridge.ready_for_native_close() is True
        window.wait_for_state("normal")
        window.close_listener_ready = False
        assert bridge.request_native_close() is True
        assert window.close_dispatches.get(timeout=2) is False
        assert window.close_requests.empty()
        assert bridge._pending_close.is_set()
        window.close_listener_ready = True
        assert bridge.ready_for_native_close() is True
        window.close_requests.get(timeout=2)
    finally:
        bridge.dispose()
    assert window.close_requests.empty()


def test_disposal_prevents_delivery_of_a_close_waiting_for_the_listener(native_factory):
    window = DesktopWindow("cocoa")
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    window.events.shown.fire()
    assert bridge.request_native_close() is True
    window.events.loaded.fire()
    window.wait_for_state("normal")
    bridge.dispose()
    window.close_listener_ready = True
    assert bridge.ready_for_native_close() is False
    assert bridge.request_native_close() is False
    bridge._on_loaded()
    bridge._publish_state()
    assert not bridge._worker.is_alive()
    assert window.close_dispatches.empty()
    assert window.close_requests.empty()


def test_native_close_dispatch_failure_retains_request_until_next_handshake(
    monkeypatch, native_factory
):
    window = DesktopWindow("cocoa")
    bridge = window_shell.attach_window_shell(window, system="Darwin", backend="cocoa")
    dispatched = Event()
    evaluate = window.evaluate_js

    def fail_first_close(script):
        if window_shell.WINDOW_SHELL_CLOSE_EVENT in script and not dispatched.is_set():
            dispatched.set()
            raise RuntimeError("The page was replaced before dispatch")
        return evaluate(script)

    window.evaluate_js = fail_first_close
    log = Mock()
    monkeypatch.setattr(window_shell.logger, "exception", log)
    try:
        window.events.shown.fire()
        window.events.loaded.fire()
        window.close_listener_ready = True
        assert bridge.ready_for_native_close() is True
        assert bridge.request_native_close() is True
        assert dispatched.wait(2)
        assert bridge._pending_close.is_set()
        assert window.close_requests.empty()
        assert bridge.ready_for_native_close() is True
        window.close_requests.get(timeout=2)
    finally:
        bridge.dispose()
    assert window.close_requests.empty()
    log.assert_called_once()


def test_native_red_button_keeps_size_tracking_until_close_is_confirmed(
    monkeypatch, native_factory
):
    def scenario(window, adapter, save_mode):
        window.close_listener_ready = True
        assert window.exposed["ready_for_native_close"]() is True
        closing_handler = window.events.closing.handlers[0]
        assert closing_handler() is False
        window.close_requests.get(timeout=2)
        window.events.resized.fire(1200, 700)
        window.wait_for_state("normal")
        assert window.exposed["close"]() is True

    saved = run_desktop_window(monkeypatch, native_factory, "cocoa", "normal", scenario)
    saved.assert_called_once_with(window_shell.WindowRatio(0.6, 0.7))
