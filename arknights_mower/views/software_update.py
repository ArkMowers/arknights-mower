"""Authenticated desktop software-update API."""

from functools import wraps
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, request

from arknights_mower.utils import software_update as updater

software_update_bp = Blueprint(
    "software_update", __name__, url_prefix="/software-update"
)


@software_update_bp.before_request
def authorize():
    if (
        hasattr(current_app, "token")
        and request.headers.get("token", "") != current_app.token
    ):
        abort(403)
    if request.method == "POST":
        if request.headers.get("X-Mower-Update") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)


def result(function):
    @wraps(function)
    def wrapped():
        try:
            return function()
        except Exception as exc:
            return {"ok": False, "message": str(exc)}, 400

    return wrapped


@software_update_bp.get("/info")
@result
def info():
    return updater.info()


@software_update_bp.get("/status")
@result
def status():
    return updater.status()


@software_update_bp.post("/settings")
@result
def settings():
    return updater.save_settings(request.get_json())


@software_update_bp.post("/check")
@result
def check():
    data = request.get_json()
    return updater.check(data.get("channel"))


@software_update_bp.post("/start")
@result
def start():
    data = request.get_json()
    if not isinstance(data.get("background", False), bool):
        raise ValueError("后台启动选项必须是布尔值")
    return updater.submit(data.get("check_id"), data.get("background", False))


@software_update_bp.post("/manual")
@result
def manual():
    return updater.upload_package(
        request.files.get("file"),
        background=request.form.get("background", "false") == "true",
    )
