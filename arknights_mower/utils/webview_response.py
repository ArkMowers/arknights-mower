"""Limit response observation in the pinned pywebview 6.2.1 EdgeChromium backend."""

from threading import Event, Lock

_DISPATCH_TIMEOUT = 3


class _ResponseEvent:
    """Preserve the public event while synchronizing changes before new requests."""

    def __init__(self, window, event):
        self._window = window
        self._event = event

    def __getattr__(self, name):
        return getattr(self._event, name)

    def __len__(self):
        return len(self._event)

    def _changed(self):
        browser = getattr(self._window, "_mower_response_browser", None)
        if browser is not None:
            browser._dispatch_response_observation()

    def __iadd__(self, handler):
        self._event += handler
        try:
            self._changed()
        except Exception:
            self._event -= handler
            raise
        return self

    def __isub__(self, handler):
        self._event -= handler
        try:
            self._changed()
        except Exception:
            self._event += handler
            raise
        return self

    __add__ = __iadd__
    __sub__ = __isub__


def configure_response_observation(window):
    """Install the compatibility adapter after backend selection, before creation."""
    if isinstance(window.events.response_received, _ResponseEvent):
        return
    window.events.response_received = _ResponseEvent(
        window, window.events.response_received
    )
    window.events.initialized += _on_initialized


def _on_initialized(renderer):
    if renderer != "edgechromium":
        return

    # Importing WinForms before pywebview selects its GUI changes DPI setup.
    from webview.platforms import edgechromium

    base = edgechromium.EdgeChrome
    if getattr(base, "_mower_response_adapter", False):
        return

    class MowerEdgeChrome(base):
        _mower_response_adapter = True

        def _dispatch_response_observation(self):
            if self.form.IsDisposed or self.form.Disposing:
                return
            if not self.form.InvokeRequired:
                self._sync_response_observation()
                return

            from System import Action

            done, lock = Event(), Lock()
            state = {"cancelled": False, "error": None}

            def update():
                with lock:
                    if state["cancelled"]:
                        return
                try:
                    if not self.form.IsDisposed and not self.form.Disposing:
                        self._sync_response_observation()
                except Exception as error:
                    state["error"] = error
                finally:
                    done.set()

            self.form.BeginInvoke(Action(update))
            if not done.wait(_DISPATCH_TIMEOUT):
                with lock:
                    state["cancelled"] = True
                raise TimeoutError("WebView2 response observation update timed out")
            if state["error"] is not None:
                raise state["error"]

        def _sync_response_observation(self):
            if not hasattr(self, "_mower_observing_responses"):
                return  # CoreWebView2 is not initialized yet.
            observe = bool(len(self.pywebview_window.events.response_received))
            if observe == self._mower_observing_responses:
                return
            core = self.webview.CoreWebView2
            if observe:
                core.WebResourceResponseReceived += self.on_web_resource_response
            else:
                core.WebResourceResponseReceived -= self.on_web_resource_response
            self._mower_observing_responses = observe

        def on_webview_ready(self, sender, args):
            if args.IsSuccess:
                self.pywebview_window._mower_response_browser = self
                # The upstream initializer subscribes before calling load_url/html.
                self._mower_observing_responses = True
            super().on_webview_ready(sender, args)

        def load_url(self, url):
            # Remove the unused upstream subscription before the first navigation.
            self._sync_response_observation()
            return super().load_url(url)

        def load_html(self, content, base_uri):
            self._sync_response_observation()
            return super().load_html(content, base_uri)

        def on_web_resource_request(self, sender, args):
            result = super().on_web_resource_request(sender, args)
            # Catch changes made inside blocking request handlers as well.
            self._sync_response_observation()
            return result

    edgechromium.EdgeChrome = MowerEdgeChrome
