"""Response observation follows consumers without changing request handling."""

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from arknights_mower.utils import webview_response


class NativeEvent:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def __isub__(self, handler):
        self.handlers.remove(handler)
        return self

    def __len__(self):
        return len(self.handlers)


@pytest.fixture
def engine(monkeypatch):
    class EdgeChrome:
        def __init__(self, consumers=()):
            self.pywebview_window = SimpleNamespace(
                events=SimpleNamespace(response_received=list(consumers))
            )
            self.webview = SimpleNamespace(
                CoreWebView2=SimpleNamespace(WebResourceResponseReceived=NativeEvent())
            )
            self.navigations = []
            self.requests = 0
            self.request_handler = lambda: None

        def on_webview_ready(self, sender, args):
            if args.IsSuccess:
                self.webview.CoreWebView2.WebResourceResponseReceived += (
                    self.on_web_resource_response
                )
                self.load_url("http://test/")

        def load_url(self, url):
            self.navigations.append((url, len(self.response_handlers)))

        def load_html(self, content, base_uri):
            self.navigations.append((content, len(self.response_handlers)))

        def on_web_resource_request(self, sender, args):
            self.requests += 1
            self.request_handler()
            return "request-result"

        def on_web_resource_response(self, sender, args):
            pass

        @property
        def response_handlers(self):
            return self.webview.CoreWebView2.WebResourceResponseReceived.handlers

    backend = SimpleNamespace(EdgeChrome=EdgeChrome)
    platforms = ModuleType("webview.platforms")
    platforms.edgechromium = backend
    monkeypatch.setitem(sys.modules, "webview.platforms", platforms)
    return backend


def ready(browser):
    browser.on_webview_ready(None, SimpleNamespace(IsSuccess=True))


def test_no_consumer_removes_observation_before_first_navigation(engine):
    webview_response._on_initialized("edgechromium")
    browser = engine.EdgeChrome()
    ready(browser)
    assert browser.navigations == [("http://test/", 0)]
    for _ in range(3):
        assert browser.on_web_resource_request(None, None) == "request-result"
    assert browser.requests == 3
    assert browser.response_handlers == []
    browser.load_html("html", "")
    browser.load_url("http://test/next")
    assert browser.navigations[-2:] == [("html", 0), ("http://test/next", 0)]


def test_existing_consumer_and_repeated_initialization_do_not_duplicate(engine):
    webview_response._on_initialized("edgechromium")
    adapter = engine.EdgeChrome
    webview_response._on_initialized("edgechromium")
    assert engine.EdgeChrome is adapter
    browser = adapter([lambda response: None])
    ready(browser)
    for _ in range(3):
        browser.on_web_resource_request(None, None)
    assert browser.navigations == [("http://test/", 1)]
    assert browser.response_handlers == [browser.on_web_resource_response]


def test_later_consumers_follow_requests_and_blocking_request_handlers(engine):
    webview_response._on_initialized("edgechromium")
    browser = engine.EdgeChrome()
    ready(browser)
    consumers = browser.pywebview_window.events.response_received
    consumers.append(lambda response: None)
    browser.on_web_resource_request(None, None)
    assert browser.response_handlers == [browser.on_web_resource_response]
    browser.request_handler = consumers.clear
    browser.on_web_resource_request(None, None)
    assert browser.response_handlers == []
    browser.request_handler = lambda: consumers.append(lambda response: None)
    browser.on_web_resource_request(None, None)
    assert browser.response_handlers == [browser.on_web_resource_response]


def test_recreated_windows_keep_separate_consumer_state(engine):
    webview_response._on_initialized("edgechromium")
    observed = engine.EdgeChrome([lambda response: None])
    first = engine.EdgeChrome()
    replacement = engine.EdgeChrome()
    for browser in (observed, first, replacement):
        ready(browser)
    assert len(observed.response_handlers) == 1
    assert first.response_handlers == replacement.response_handlers == []


def test_failed_initialization_does_not_access_response_event(engine):
    webview_response._on_initialized("edgechromium")
    browser = engine.EdgeChrome()
    browser.on_webview_ready(None, SimpleNamespace(IsSuccess=False))
    assert browser.navigations == []
    assert browser.response_handlers == []


@pytest.mark.parametrize("renderer", ["qt", "gtk", "cocoa", "mshtml", "cef"])
def test_other_renderers_are_unchanged(engine, renderer):
    original = engine.EdgeChrome
    webview_response._on_initialized(renderer)
    assert engine.EdgeChrome is original


def test_window_registration_waits_for_selected_renderer(engine):
    event = NativeEvent()
    window = SimpleNamespace(
        events=SimpleNamespace(initialized=event, response_received=NativeEvent())
    )
    original = engine.EdgeChrome
    webview_response.configure_response_observation(window)
    assert engine.EdgeChrome is original
    assert event.handlers == [webview_response._on_initialized]
    event.handlers[0]("edgechromium")
    assert engine.EdgeChrome is not original


def test_response_consumer_changes_synchronize_and_undo_failed_add():
    original = NativeEvent()
    calls = []
    browser = SimpleNamespace(
        _dispatch_response_observation=lambda: calls.append(len(original))
    )
    window = SimpleNamespace(_mower_response_browser=browser)
    event = webview_response._ResponseEvent(window, original)

    def handler(response):
        pass

    event += handler
    event -= handler
    assert calls == [1, 0]
    assert original.handlers == []

    def timeout():
        raise TimeoutError

    browser._dispatch_response_observation = timeout
    with pytest.raises(TimeoutError):
        event += handler
    assert original.handlers == []


def test_response_event_preserves_public_signal_operations():
    from webview.event import Event

    window = SimpleNamespace()
    original = Event(window)
    event = webview_response._ResponseEvent(window, original)
    assert not event.is_set()
    event.set("response metadata")
    assert event.wait(0)
    event.clear()
    assert not event.is_set()


def test_repeated_configuration_preserves_event_and_handlers(engine):
    original = NativeEvent()

    def handler(response):
        pass

    original += handler
    window = SimpleNamespace(
        events=SimpleNamespace(initialized=NativeEvent(), response_received=original)
    )
    webview_response.configure_response_observation(window)
    event = window.events.response_received
    webview_response.configure_response_observation(window)
    assert window.events.response_received is event
    assert len(event) == 1
    assert event.handlers == [handler]
    assert len(window.events.initialized) == 1


def test_gui_dispatch_cancels_pending_work_after_timeout(engine, monkeypatch):
    webview_response._on_initialized("edgechromium")
    browser = engine.EdgeChrome()
    ready(browser)
    browser.pywebview_window.events.response_received.append(lambda response: None)
    callbacks = []
    browser.form = SimpleNamespace(
        IsDisposed=False,
        Disposing=False,
        InvokeRequired=True,
        BeginInvoke=callbacks.append,
    )
    system = ModuleType("System")
    system.Action = lambda callback: callback
    monkeypatch.setitem(sys.modules, "System", system)
    monkeypatch.setattr(webview_response, "_DISPATCH_TIMEOUT", 0)
    with pytest.raises(TimeoutError):
        browser._dispatch_response_observation()
    assert len(callbacks) == 1
    callbacks[0]()
    assert browser.response_handlers == []


def test_gui_dispatch_updates_on_gui_thread_and_ignores_disposed_window(engine):
    webview_response._on_initialized("edgechromium")
    browser = engine.EdgeChrome()
    ready(browser)
    browser.pywebview_window.events.response_received.append(lambda response: None)
    browser.form = SimpleNamespace(
        IsDisposed=False, Disposing=False, InvokeRequired=False
    )
    browser._dispatch_response_observation()
    assert browser.response_handlers == [browser.on_web_resource_response]
    browser.form.IsDisposed = True
    browser.pywebview_window.events.response_received.clear()
    browser._dispatch_response_observation()
    assert browser.response_handlers == [browser.on_web_resource_response]


def test_dependency_upgrade_requires_adapter_review():
    root = Path(__file__).parents[2]
    for name in ("requirements.in", "requirements.txt"):
        assert (
            "pywebview==6.2.1" in (root / name).read_text(encoding="utf-8").splitlines()
        )
