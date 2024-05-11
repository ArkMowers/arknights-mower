#!/usr/bin/env python3
import html
import multiprocessing
from threading import Thread

window = None
task_process = None
log_thread = None


def read_log(conn):
    while True:
        try:
            msg = conn.recv()
            if msg["type"] == "log":
                log = msg["data"]
                window.evaluate_js(f'append_log("{html.escape(log)}")')
        except Exception:
            pass


def task_ra(settings, write):
    import logging

    from arknights_mower.solvers.reclamation_algorithm import ReclamationAlgorithm
    from arknights_mower.utils import config, rapidocr
    from arknights_mower.utils.log import Handler, logger

    wh = Handler(write)
    wh.setLevel(logging.INFO)
    logger.addHandler(wh)

    logger.setLevel("INFO")

    config.ADB_CONTROL_CLIENT = "maatouch"
    config.ADB_DEVICE = [settings["adb"]]
    config.TAP_TO_LAUNCH = {"enable": False, "x": 0, "y": 0}
    config.APPNAME = (
        "com.hypergryph.arknights"
        if settings["package_type"] == "official"
        else "com.hypergryph.arknights.bilibili"
    )
    config.FEATURE_MATCHER = "flann"

    rapidocr.initialize_ocr()

    solver = ReclamationAlgorithm()
    solver.run()


class Api:
    def __init__(self):
        self.settings = {
            "package_type": "official",
            "adb": "127.0.0.1:5555",
        }

    def get_settings(self):
        return self.settings

    def set_settings(self, settings):
        self.settings = settings

    def start_task(self, task):
        global task_process
        global log_thread
        if task == "ra":
            read, write = multiprocessing.Pipe()
            task_process = multiprocessing.Process(
                target=task_ra,
                args=(
                    self.settings,
                    write,
                ),
                daemon=False,
            )
            task_process.start()
            log_thread = Thread(
                target=read_log,
                args=(read,),
                daemon=True,
            )
            log_thread.start()


def jump_to_index(window):
    window.load_url("/toolbox/index.html")


if __name__ == "__main__":
    multiprocessing.freeze_support()

    import webview

    api = Api()
    window = webview.create_window(
        title="工具箱",
        url="dist/index.html",
        js_api=api,
        min_size=(400, 600),
        width=400,
        height=600,
    )
    webview.start(jump_to_index, window, http_server=True)

    if task_process and task_process.is_alive():
        task_process.terminate()
