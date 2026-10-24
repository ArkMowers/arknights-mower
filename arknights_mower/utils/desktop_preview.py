"""Open the built offline example with the real desktop window controls."""

import json
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import unquote, urlencode, urlsplit

from arknights_mower.utils.log import logger
from arknights_mower.utils.window_shell import (
    attach_window_shell,
    default_desktop_window_size,
    desktop_window_min_size,
    is_windows,
    window_background_color,
)


class _PreviewHandler(SimpleHTTPRequestHandler):
    timeout = 5

    def __init__(self, *args, root: Path, pages: frozenset[str], **kwargs):
        self._root = root
        self._pages = pages
        super().__init__(*args, directory=str(root), **kwargs)

    def send_head(self):
        path = unquote(urlsplit(self.path).path)
        parts = [part for part in path.split("/") if part]
        if any(part in (".", "..") or ":" in part for part in parts) or any(
            character in path for character in ("\\", "\x00")
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        if (path.rstrip("/").lower() or "/") in self._pages:
            candidate = self._root / "index.html"
        else:
            candidate = self._root.joinpath(*parts)
        candidate = candidate.resolve()
        if not candidate.is_relative_to(self._root):
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        if not candidate.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        try:
            stream = candidate.open("rb")
            size = candidate.stat().st_size
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return None
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", self.guess_type(str(candidate)))
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        return stream

    def log_message(self, format, *args):
        logger.debug("Desktop preview HTTP: %s", format % args)


class _PreviewSession:
    """Keep example data and window preferences in memory for this session."""

    def __init__(self):
        self._remember_close = False
        self._launch_mode = "normal"

    def get_close_preference(self) -> dict:
        return {
            "choice": "exit",
            "remember": self._remember_close,
            "tray_enabled": False,
        }

    def set_close_preference(self, choice: str, remember: bool) -> bool:
        if choice != "exit" or type(remember) is not bool:
            raise ValueError("Invalid preview close preference")
        self._remember_close = remember
        return True

    def get_window_launch_mode(self) -> str:
        return self._launch_mode

    def set_window_launch_mode(self, mode: str) -> bool:
        if mode not in ("last", "normal", "maximized"):
            raise ValueError("Invalid preview launch mode")
        self._launch_mode = mode
        return True

    def mark_ready(self) -> bool:
        return True

    def get_instances(self) -> list[dict]:
        return [
            {
                "name": "离线预览",
                "path": "预览数据/默认实例",
                "state": "running",
                "editable": False,
                "can_start": False,
                "can_stop": False,
            },
            {
                "name": "示例实例",
                "path": "预览数据/示例实例",
                "state": "stopped",
                "editable": False,
                "can_start": False,
                "can_stop": False,
            },
        ]


def _preview_pages(root: Path) -> frozenset[str]:
    try:
        pages = json.loads((root / "frontend-routes.json").read_text("utf-8"))
        return frozenset(
            {"/"}
            | {
                page.rstrip("/").lower() or "/"
                for page in pages
                if isinstance(page, str) and page.startswith("/")
            }
        )
    except (OSError, ValueError, TypeError):
        return frozenset({"/"})


def run_preview(build_directory: Path | None = None) -> int:
    """Serve built example assets until pywebview closes, without starting Mower."""
    root = (
        Path(build_directory)
        if build_directory is not None
        else Path(__file__).resolve().parents[2] / "ui" / "dist-preview"
    ).resolve()
    if not (root / "index.html").is_file():
        logger.error("未找到离线示例页面，请先在 ui 目录运行 npm run build:mock。")
        return 2

    import webview

    size = default_desktop_window_size()
    min_size = desktop_window_min_size()
    shell_enabled = is_windows()
    handler = partial(_PreviewHandler, root=root, pages=_preview_pages(root))
    with ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
        thread = Thread(
            target=server.serve_forever,
            kwargs={"poll_interval": 0.1},
            name="desktop-preview-http",
            daemon=True,
        )
        thread.start()
        bridge = None
        try:
            query = urlencode(
                {
                    "window_shell": "1" if shell_enabled else "0",
                    "native_preview": "1",
                    "window_theme": "light",
                    "instance_name": "离线预览",
                    "mower_version": "4.1.6-preview",
                }
            )
            window = webview.create_window(
                "Mower · 离线预览",
                f"http://127.0.0.1:{server.server_port}/?{query}",
                text_select=True,
                confirm_close=False,
                width=size.width,
                height=size.height,
                min_size=min_size,
                resizable=True,
                frameless=shell_enabled,
                draggable=True,
                easy_drag=False,
                shadow=True,
                background_color=window_background_color("light"),
            )
            if shell_enabled:
                bridge = attach_window_shell(
                    window, initial_size=size, tray_enabled=False
                )
            session = _PreviewSession()
            # Replace the four persistent APIs before the first navigation.
            # Window.expose uses function names as keys, so these take precedence.
            window.expose(
                session.get_close_preference,
                session.set_close_preference,
                session.get_window_launch_mode,
                session.set_window_launch_mode,
                session.get_instances,
                session.mark_ready,
            )
            if shell_enabled:
                from arknights_mower.utils.windows_frameless import (
                    install_windows_frameless_resize,
                )

                install_windows_frameless_resize(window, size, min_size)
            webview.start(private_mode=True)
        finally:
            try:
                if bridge is not None:
                    bridge.dispose()
            finally:
                server.shutdown()
                thread.join(timeout=3)
    return 0
