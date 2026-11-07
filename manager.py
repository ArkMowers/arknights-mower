#!/usr/bin/env python3

import multiprocessing as mp
import os
import sys
from pathlib import Path

# The copied manager executable also serves as the detached software updater.
if __name__ == "__main__" and sys.argv[1:2] == ["--software-update-worker"]:
    from arknights_mower.utils.software_update_worker import main as update_main

    update_main(sys.argv[2])
    sys.exit()

import webview

from arknights_mower.utils import manager_common
from arknights_mower.utils.folder_dialog import choose_directory
from arknights_mower.utils.manager_instances import InstanceController
from arknights_mower.utils.path import get_path, resolve_config_path


def choose_instance_directory(window, directory=""):
    if sys.platform != "darwin":
        return choose_directory(window, directory, title="选择实例保存目录")

    # Instance directories use a native panel with directory creation enabled.
    # Its JS API runs on a worker thread; Cocoa dialogs belong on the main thread.
    from concurrent.futures import Future

    from AppKit import NSModalResponseOK, NSOpenPanel
    from Foundation import NSURL, NSThread
    from PyObjCTools import AppHelper

    result = Future()

    def show():
        try:
            panel = NSOpenPanel.openPanel()
            panel.setTitle_("选择实例保存目录")
            panel.setCanChooseFiles_(False)
            panel.setCanChooseDirectories_(True)
            panel.setAllowsMultipleSelection_(False)
            panel.setCanCreateDirectories_(True)
            if directory and Path(directory).is_dir():
                panel.setDirectoryURL_(NSURL.fileURLWithPath_(directory))
            folder = (
                str(panel.URL().path())
                if panel.runModal() == NSModalResponseOK
                else None
            )
            result.set_result(folder)
        except Exception as error:
            result.set_exception(error)

    if NSThread.isMainThread():
        show()
    else:
        AppHelper.callAfter(show)
    return result.result()


class Api(InstanceController):
    def __init__(
        self,
        storage_path=None,
        ready=None,
        window=None,
    ):
        super().__init__(storage_path, ready)
        self._window = window

    def select_device_path(self, key, current=""):
        from arknights_mower.utils.managed_device import fields

        field = next((item for item in fields() if item["key"] == key), None)
        if field is None or field["kind"] not in {"directory", "file"}:
            raise ValueError("不支持的设备路径配置")
        return self._choose_path(field, current)

    def select_common_path(self, key, current=""):
        field = next(
            (item for item in manager_common.FIELDS if item["key"] == key), None
        )
        if field is None or field["kind"] not in {"directory", "file"}:
            raise ValueError("不支持的公共路径配置")
        return self._choose_path(field, current)

    def _choose_path(self, field, current):
        if not isinstance(current, str):
            raise ValueError("路径必须是文本")
        current = resolve_config_path(current)
        window = self._window if self._window is not None else webview.active_window()
        if field["kind"] == "directory":
            result = choose_directory(window, current, title=field["label"])
        else:
            result = window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                directory=str(Path(current).parent) if current else "",
            )
        return result if isinstance(result, str) else result[0] if result else None

    def select_path(self, idx, target=None):
        with self._operation():
            original = self._target_instance(idx, target).copy()
            self._editable(original, self._records())
        window = self._window if self._window is not None else webview.active_window()
        folder = choose_instance_directory(window, original["path"])
        if not folder:
            return None
        if not isinstance(folder, str):
            folder = folder[0]
        self._update(
            idx, {"path": folder}, {key: original[key] for key in ("name", "path")}
        )
        return folder


def manager_app():
    """Serve the manager directly, keeping /assets rooted at the shared dist."""
    from bottle import Bottle, static_file

    app = Bottle()
    root = get_path("@internal/ui/dist")

    @app.get("/")
    @app.get("/<filepath:path>")
    def asset(filepath="manager/index.html"):
        return static_file(filepath, root=str(root))

    return app


def manager_window(connection, ready, closed):
    from threading import Thread

    from arknights_mower.utils.desktop_process import watch_parent

    watch_parent()
    api = Api(ready=ready)
    window = webview.create_window(
        title="多开管理器",
        url=manager_app(),
        js_api=api,
        min_size=(400, 500),
        width=800,
        height=500,
    )
    api._window = window

    def receive():
        try:
            while True:
                message = connection.recv()
                if message == "request_exit":
                    allowed = api.request_close()
                    connection.send(allowed)
                    if allowed:
                        window.destroy()
                        return
                    window.show()
                    window.restore()
                if message == "exit":
                    window.destroy()
                    return
                if message == "show":
                    window.show()
                    window.restore()
        except (EOFError, OSError):
            return

    def closing():
        if not api.request_close():
            window.hide()
            return False
        return True

    window.events.closing += closing
    window.events.closed += closed.set
    Thread(target=receive, daemon=True).start()
    webview.start(http_server=True)


def run_manager():
    from queue import Empty

    from arknights_mower.utils import update_runtime as runtime
    from arknights_mower.utils.manager_tray import start_manager_tray
    from webview_ui import close_child, exit_if_webview_backend_missing

    if runtime.active_job() and not os.environ.get("MOWER_RESTART_JOB"):
        sys.exit("软件更新或进程操作正在进行，请等待完成后启动多开管理器")
    exit_if_webview_backend_missing()
    if existing := runtime.unified_managers():
        runtime.send_instance_command(existing[0], "show")
        return
    background = os.environ.get("MOWER_BACKGROUND") == "1"
    registration = runtime.RuntimeRegistration("manager")
    registration.record["unified_tray"] = True
    registration.publish()
    commands = mp.Queue()
    tray_ready = mp.Event()
    window_ready = mp.Event()
    window_closed = mp.Event()
    tray_process = mp.Process(
        target=start_manager_tray, args=(commands, tray_ready), daemon=True
    )
    window_process = None
    connection = None

    def show_window():
        nonlocal window_process, connection
        if window_process and window_process.is_alive():
            connection.send("show")
            return
        close_child(window_process)
        if connection is not None:
            connection.close()
        window_ready.clear()
        window_closed.clear()
        connection, child = mp.Pipe()
        window_process = mp.Process(
            target=manager_window,
            args=(child, window_ready, window_closed),
            daemon=True,
        )
        window_process.start()
        child.close()

    try:
        tray_process.start()
        if not background:
            show_window()
        while not registration.shutdown_requested():
            if window_process is not None and window_closed.is_set():
                close_child(window_process)
                window_process = None
                connection.close()
                connection = None
            if not tray_process.is_alive():
                raise RuntimeError("多开管理器托盘启动失败")
            if tray_ready.is_set() and (background or window_ready.is_set()):
                if not registration.record["ready"]:
                    registration.record["ready"] = True
                    registration.publish()
                    if ready_file := os.environ.get("MOWER_SMOKE_READY_FILE"):
                        Path(ready_file).write_text("ready", encoding="utf-8")
            if "show" in registration.take_commands():
                show_window()
            try:
                message = commands.get(timeout=0.5)
            except Empty:
                continue
            if message[0] == "show":
                show_window()
            elif message[0] == "instance":
                for record in runtime.managed_instances():
                    if record["id"] == message[1]:
                        runtime.send_instance_command(record, message[2])
            elif message[0] == "close_instances":
                for record in runtime.managed_instances():
                    runtime.send_instance_command(record, "exit")
            elif message[0] == "close_manager":
                if window_process is not None and window_process.is_alive():
                    connection.send("request_exit")
                    if not connection.poll(2) or connection.recv() is not True:
                        continue
                break
    finally:
        close_child(window_process, connection)
        close_child(tray_process)
        if connection is not None:
            connection.close()
        registration.close()


if __name__ == "__main__":
    mp.freeze_support()
    run_manager()
