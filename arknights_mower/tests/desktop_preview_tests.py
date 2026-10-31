"""Offline desktop examples retain native controls and isolate application state."""

import builtins
import json
import multiprocessing
import runpy
import sys
from io import BytesIO
from pathlib import Path
from threading import Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import pytest

from arknights_mower.utils import desktop_preview
from arknights_mower.utils.window_shell import WindowSize


class _Event:
    def __init__(self):
        self.callbacks = []

    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self


class _Window:
    def __init__(self):
        self.api = {}
        self.events = SimpleNamespace(
            **{
                name: _Event()
                for name in (
                    "maximized",
                    "minimized",
                    "restored",
                    "resized",
                    "shown",
                    "loaded",
                    "closed",
                )
            }
        )
        self.minimize = Mock()
        self.maximize = Mock()
        self.restore = Mock()
        self.destroy = Mock()

    def expose(self, *functions):
        self.api.update((function.__name__, function) for function in functions)


@pytest.fixture
def example_build(tmp_path):
    root = tmp_path / "dist-preview"
    root.mkdir()
    (root / "index.html").write_text("<html>offline example</html>", encoding="utf-8")
    (root / "assets").mkdir()
    (root / "assets" / "demo.js").write_text("example()", encoding="utf-8")
    (root / "frontend-routes.json").write_text(
        json.dumps(["/", "/mowersettings"]), encoding="utf-8"
    )
    (tmp_path / "outside.txt").write_text("private configuration", encoding="utf-8")
    return root


def _request(server, url, path=None, method="GET"):
    parsed = urlsplit(url)
    target = path or parsed.path + "?" + parsed.query
    source = BytesIO(
        f"{method} {target} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode()
    )
    response = BytesIO()
    connection = SimpleNamespace(
        makefile=lambda *args: source,
        sendall=response.write,
        settimeout=Mock(),
    )
    server.RequestHandlerClass(connection, ("127.0.0.1", 53000), server)
    headers, body = response.getvalue().split(b"\r\n\r\n", 1)
    return int(headers.split(b" ", 2)[1]), body


def _forbid_application_imports(name, *args, **kwargs):
    if name.startswith(
        (
            "arknights_mower.utils.config",
            "arknights_mower.utils.instance_supervisor",
            "arknights_mower.utils.manager_instances",
            "server",
            "flask",
        )
    ):
        raise AssertionError(f"Desktop preview imported application state: {name}")
    return _original_import(name, *args, **kwargs)


_original_import = builtins.__import__


def test_missing_build_reports_the_build_command_without_opening_a_window(tmp_path):
    with (
        patch.object(desktop_preview, "ThreadingHTTPServer") as server,
        patch.object(desktop_preview.logger, "error") as error,
        patch.dict(sys.modules, {"webview": SimpleNamespace()}),
    ):
        assert desktop_preview.run_preview(tmp_path) == 2
    server.assert_not_called()
    assert "npm run build:mock" in error.call_args.args[0]


@pytest.mark.parametrize("start_failure", [False, True])
def test_preview_serves_only_built_assets_and_closes_its_server(
    example_build, start_failure
):
    window = _Window()
    native_resize = Mock()
    servers = []
    threads = []
    real_server = desktop_preview.ThreadingHTTPServer

    def create_server(*args, **kwargs):
        server = real_server(*args, **kwargs)
        servers.append(server)
        return server

    def create_thread(*args, **kwargs):
        thread = Thread(*args, **kwargs)
        threads.append(thread)
        return thread

    def show_example(**kwargs):
        assert kwargs == {"private_mode": True}
        url = webview.create_window.call_args.args[1]
        parsed = urlsplit(url)
        assert parsed.hostname == "127.0.0.1"
        query = parse_qs(parsed.query)
        assert query["window_shell"] == ["1"]
        assert query["native_preview"] == ["1"]
        assert query["instance_name"] == ["离线预览"]
        assert _request(servers[0], url) == (200, b"<html>offline example</html>")
        assert _request(servers[0], url, "/assets/demo.js") == (200, b"example()")
        assert _request(servers[0], url, "/mowersettings") == (
            200,
            b"<html>offline example</html>",
        )
        assert _request(servers[0], url, "/mowersettings", "HEAD") == (200, b"")
        for path in (
            "/status",
            "/api/start",
            "/assets/",
            "/../outside.txt",
            "/%2e%2e/outside.txt",
            "/%5c..%5coutside.txt",
            "/C:outside.txt",
        ):
            assert _request(servers[0], url, path)[0] == 404

        api = window.api
        assert api["get_platform"]()["protocol"] == "mower-window-shell-v1"
        assert api["get_platform"]()["platform"] == "windows"
        assert api["set_hit_regions"]({"width": 900, "height": 600, "regions": []})
        assert api["get_close_preference"]() == {
            "choice": "exit",
            "remember": False,
            "tray_enabled": False,
        }
        assert api["set_close_preference"]("exit", True)
        assert api["get_close_preference"]()["remember"] is True
        assert api["get_window_launch_mode"]() == "normal"
        assert api["set_window_launch_mode"]("maximized")
        assert api["get_window_launch_mode"]() == "maximized"
        assert api["mark_ready"]() is True
        assert "get_instances" not in api
        assert not {"start", "stop", "add", "remove", "update_settings"} & api.keys()
        assert api["minimize"]()
        assert api["maximize"]()
        assert api["restore"]()
        assert api["close"]()
        window.minimize.assert_called_once()
        window.maximize.assert_called_once()
        window.restore.assert_called_once()
        window.destroy.assert_called_once()
        if start_failure:
            raise RuntimeError("native backend unavailable")

    webview = SimpleNamespace(
        create_window=Mock(return_value=window), start=Mock(side_effect=show_example)
    )
    with (
        patch.dict(
            sys.modules,
            {
                "webview": webview,
                "arknights_mower.utils.windows_frameless": SimpleNamespace(
                    install_windows_frameless_resize=native_resize
                ),
            },
        ),
        patch(
            "arknights_mower.utils.window_shell.platform.system", return_value="Windows"
        ),
        patch.object(
            desktop_preview,
            "default_desktop_window_size",
            return_value=WindowSize(900, 600),
        ),
        patch.object(
            desktop_preview,
            "desktop_window_min_size",
            return_value=WindowSize(600, 400),
        ),
        patch.object(desktop_preview, "ThreadingHTTPServer", side_effect=create_server),
        patch.object(desktop_preview, "Thread", side_effect=create_thread),
        patch("builtins.__import__", side_effect=_forbid_application_imports),
    ):
        if start_failure:
            with pytest.raises(RuntimeError, match="native backend unavailable"):
                desktop_preview.run_preview(example_build)
        else:
            assert desktop_preview.run_preview(example_build) == 0

    native_resize.assert_called_once_with(
        window, WindowSize(900, 600), WindowSize(600, 400)
    )
    options = webview.create_window.call_args.kwargs
    assert options["frameless"] is True
    assert options.get("draggable") is True
    assert options["easy_drag"] is False
    assert options["shadow"] is True
    assert options["confirm_close"] is False
    assert (options["width"], options["height"], options["min_size"]) == (
        900,
        600,
        WindowSize(600, 400),
    )
    assert servers[0].socket.fileno() == -1
    assert not threads[0].is_alive()
    assert not window.api["set_hit_regions"](
        {"width": 900, "height": 600, "regions": []}
    )


@pytest.mark.parametrize("system", ["Darwin", "Linux"])
@pytest.mark.parametrize("start_failure", [False, True])
def test_preview_keeps_native_decorations_without_attaching_a_custom_shell(
    example_build, system, start_failure
):
    window = _Window()

    def show_example(**kwargs):
        options = webview.create_window.call_args.kwargs
        query = parse_qs(urlsplit(webview.create_window.call_args.args[1]).query)
        assert options["frameless"] is False
        assert query["window_shell"] == ["0"]
        assert "get_platform" not in window.api
        assert window.api["get_window_launch_mode"]() == "normal"
        if start_failure:
            raise RuntimeError("native backend unavailable")

    webview = SimpleNamespace(
        create_window=Mock(return_value=window), start=Mock(side_effect=show_example)
    )
    with (
        patch.dict(sys.modules, {"webview": webview}),
        patch(
            "arknights_mower.utils.window_shell.platform.system", return_value=system
        ),
        patch.object(
            desktop_preview,
            "default_desktop_window_size",
            return_value=WindowSize(900, 600),
        ),
        patch.object(
            desktop_preview,
            "desktop_window_min_size",
            return_value=WindowSize(600, 400),
        ),
        patch.object(desktop_preview, "attach_window_shell") as attach,
        patch("builtins.__import__", side_effect=_forbid_application_imports),
    ):
        if start_failure:
            with pytest.raises(RuntimeError, match="native backend unavailable"):
                desktop_preview.run_preview(example_build)
        else:
            assert desktop_preview.run_preview(example_build) == 0
    attach.assert_not_called()


def test_preview_cli_exits_before_supervision_or_application_imports():
    run_preview = Mock(return_value=0)
    with (
        patch.object(sys, "argv", ["webview_ui.py", "--preview"]),
        patch.dict(
            sys.modules,
            {
                "arknights_mower.utils.desktop_preview": SimpleNamespace(
                    run_preview=run_preview
                )
            },
        ),
        patch.object(multiprocessing, "freeze_support") as freeze_support,
        patch("builtins.__import__", side_effect=_forbid_application_imports),
        pytest.raises(SystemExit) as exit_info,
    ):
        runpy.run_path(
            str(Path(__file__).resolve().parents[2] / "webview_ui.py"),
            run_name="__main__",
        )
    assert exit_info.value.code == 0
    run_preview.assert_called_once_with()
    freeze_support.assert_not_called()


def test_preview_cli_requires_the_single_explicit_flag():
    run_preview = Mock()
    with (
        patch.object(sys, "argv", ["webview_ui.py", "--preview", "--background"]),
        patch.dict(
            sys.modules,
            {
                "arknights_mower.utils.desktop_preview": SimpleNamespace(
                    run_preview=run_preview
                )
            },
        ),
        patch.object(
            multiprocessing, "freeze_support", side_effect=RuntimeError("normal launch")
        ),
        pytest.raises(RuntimeError, match="normal launch"),
    ):
        runpy.run_path(
            str(Path(__file__).resolve().parents[2] / "webview_ui.py"),
            run_name="__main__",
        )
    run_preview.assert_not_called()


@pytest.mark.parametrize(
    ("flag", "module_name", "entrypoint"),
    [
        ("--jpeg-encode-worker", "jpeg_worker", "worker_main"),
        ("--process-control-worker", "process_control", "worker_main"),
        ("--software-update-worker", "software_update_worker", "main"),
        ("--maa-check-worker", "maa_check", "worker_main"),
    ],
)
def test_worker_flags_keep_priority_over_preview(flag, module_name, entrypoint):
    worker = Mock()
    run_preview = Mock()
    with (
        patch.object(sys, "argv", ["webview_ui.py", flag, "--preview"]),
        patch.dict(
            sys.modules,
            {
                f"arknights_mower.utils.{module_name}": SimpleNamespace(
                    **{entrypoint: worker}
                ),
                "arknights_mower.utils.desktop_preview": SimpleNamespace(
                    run_preview=run_preview
                ),
            },
        ),
        pytest.raises(SystemExit),
    ):
        runpy.run_path(
            str(Path(__file__).resolve().parents[2] / "webview_ui.py"),
            run_name="__main__",
        )
    worker.assert_called_once_with("--preview")
    run_preview.assert_not_called()
