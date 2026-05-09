from __future__ import annotations

from threading import Thread

import time

from flask import Blueprint, jsonify

from arknights_mower.utils import config

scheduler_bp = Blueprint("scheduler", __name__)

scheduler_thread: Thread | None = None
scheduler_pause = None
_STOP_TIMEOUT = 10


def _is_alive() -> bool:
    return scheduler_thread is not None and scheduler_thread.is_alive()


def get_status() -> dict:
    if not _is_alive():
        return {"engine": "v1"}
    status = {
        "engine": "scheduler",
        "status": "working",
    }
    if scheduler_pause:
        status["is_paused"] = scheduler_pause.is_paused
        if scheduler_pause.is_paused:
            status["status"] = "paused"
    return status


@scheduler_bp.route("/start-scheduler/<start_type>")
def start_scheduler(start_type):
    global scheduler_thread, scheduler_pause
    if _is_alive():
        return "false"
    config.stop_mower.clear()

    from arknights_mower.scheduler.infra.thread_pause import ThreadPauseController

    scheduler_pause = ThreadPauseController()

    from arknights_mower.scheduler.bootstrap import run

    scheduler_thread = Thread(
        target=run, kwargs={"pause": scheduler_pause}, daemon=True
    )
    scheduler_thread.start()
    return "true"


@scheduler_bp.route("/stop-scheduler")
def stop_scheduler():
    global scheduler_thread, scheduler_pause
    if scheduler_thread is None:
        return "true"
    config.stop_mower.set()
    if scheduler_pause:
        scheduler_pause.request_stop()
    scheduler_thread.join(_STOP_TIMEOUT)
    if scheduler_thread.is_alive():
        return "false"
    scheduler_thread = None
    scheduler_pause = None
    return "true"


@scheduler_bp.route("/pause-scheduler")
def pause_scheduler():
    if scheduler_pause:
        scheduler_pause.pause()
        return "true"
    return "false"


@scheduler_bp.route("/resume-scheduler")
def resume_scheduler():
    if scheduler_pause:
        scheduler_pause.resume()
        return "true"
    return "false"


@scheduler_bp.route("/test-scene")
def test_scene_route():
    from arknights_mower.utils.device.device import Device
    from arknights_mower.utils.recognize import Recognizer
    from arknights_mower.utils.scene import SceneComment

    device = Device()
    recog = Recognizer(device)
    results = []
    for i in range(5):
        recog.update()
        scene = recog.get_scene()
        results.append({"tick": i, "scene": int(scene), "label": SceneComment.get(scene, "UNKNOWN")})
        time.sleep(5)
    return jsonify(results)
