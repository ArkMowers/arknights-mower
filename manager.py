#!/usr/bin/env python3

import json
import os
import sys
from pathlib import Path

import webview

from arknights_mower.utils.path import get_path


class Api:
    def __init__(self, storage_path=None):
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
        folder = window.create_file_dialog(dialog_type=webview.FOLDER_DIALOG)
        if folder is None:
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
        env = launch_environment({"data_dir": os.environ.get("MOWER_DATA_DIR", "")})
        process = Popen(command, cwd=installation_root(), env=env)
        # Reap exited instances while the manager remains open, so process
        # control does not mistake an unreaped child for a running instance.
        Thread(target=process.wait, daemon=True).start()
        return {"ok": True}


def jump_to_index(window):
    window.load_url("/manager/index.html")


if __name__ == "__main__":
    from threading import Thread
    from time import sleep

    from arknights_mower.utils.update_runtime import RuntimeRegistration, active_job
    from webview_ui import exit_if_webview_backend_missing

    if active_job() and not os.environ.get("MOWER_RESTART_JOB"):
        sys.exit("软件更新或进程操作正在进行，请等待完成后启动多开管理器")
    # 多开管理器和主程序一样依赖窗口后端，宿主缺 GTK/WebKit2 原生库时先给出中文
    # 安装指引再退出，避免裸 WebViewException。
    exit_if_webview_backend_missing()

    api = Api()
    window = webview.create_window(
        title="多开管理器",
        url="ui/dist/index.html",
        js_api=api,
        min_size=(400, 500),
        width=400,
        height=500,
    )
    registration = RuntimeRegistration("manager")

    def watch_update():
        while not registration.shutdown_requested():
            sleep(0.5)
        window.destroy()

    def manager_ready():
        registration.record["ready"] = True
        registration.publish()

    window.events.loaded += manager_ready
    Thread(target=watch_update, daemon=True).start()
    webview.start(jump_to_index, window, http_server=True)
    registration.close()
