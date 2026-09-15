#!/usr/bin/env python3

import json
import multiprocessing as mp
import os
import sys
from pathlib import Path

import webview

from arknights_mower.utils.path import get_path


def choose_instance_directory(window, directory=""):
    if sys.platform != "darwin":
        return window.create_file_dialog(
            dialog_type=webview.FOLDER_DIALOG, directory=directory
        )

    # pywebview 5.1 does not enable directory creation on NSOpenPanel.
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


class Api:
    def __init__(self, storage_path=None, ready=None):
        self._ready = ready
        self.storage_path = (
            Path(storage_path)
            if storage_path is not None
            else get_path("@app/instances.json", space="")
        )
        try:
            with self.storage_path.open("r", encoding="utf-8") as f:
                self.instances = json.load(f)
        except Exception:
            self.instances = []
            self.save()

    def save(self):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as f:
            json.dump(self.instances, f, ensure_ascii=False)

    def get_instances(self):
        return self.instances

    def mark_ready(self):
        if self._ready is not None:
            self._ready.set()

    def add(self, name, path):
        self.instances.append({"name": name, "path": path})
        self.save()

    def remove(self, idx):
        del self.instances[idx]
        self.save()

    def rename(self, idx, name):
        self.instances[idx]["name"] = name
        self.save()

    def select_path(self, idx):
        window = webview.active_window()
        folder = choose_instance_directory(window, self.instances[idx]["path"])
        if not folder:
            return None
        if not isinstance(folder, str):
            folder = folder[0]
        self.instances[idx]["path"] = folder
        self.save()
        return folder

    def start(self, idx):
        from subprocess import Popen
        from threading import Thread

        from arknights_mower.utils.update_runtime import (
            active_job,
            installation_root,
            launch_environment,
        )

        if active_job():
            return {"ok": False, "message": "软件更新或进程操作期间无法启动新实例"}
        frozen = getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")
        instance = self.instances[idx]
        if frozen:
            mower = Path(sys.executable).resolve().parent / (
                "mower.exe" if sys.platform == "win32" else "mower"
            )
            command = [str(mower), instance["path"], instance["name"]]
        else:
            command = [
                sys.executable,
                str(installation_root() / "webview_ui.py"),
                instance["path"],
                instance["name"],
            ]
        env = launch_environment(
            {"data_dir": os.environ.get("MOWER_DATA_DIR", ""), "managed": True}
        )
        process = Popen(command, cwd=installation_root(), env=env)
        # Reap instances even while the manager window stays open.
        Thread(target=process.wait, daemon=True).start()
        return {"ok": True}


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
        width=400,
        height=500,
    )

    def receive():
        try:
            while True:
                message = connection.recv()
                if message == "exit":
                    window.destroy()
                    return
                if message == "show":
                    window.show()
                    window.restore()
        except (EOFError, OSError):
            return

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
