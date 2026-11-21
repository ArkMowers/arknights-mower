from flask import Blueprint, abort, request

from arknights_mower.utils import config, managed_device, process_control
from arknights_mower.utils.web_auth import check_request_origin, require_token
from arknights_mower.views.software_update import result

process_control_bp = Blueprint(
    "process_control", __name__, url_prefix="/process-control"
)


@process_control_bp.before_request
@require_token
def authorize():
    if request.method == "POST":
        if request.headers.get("X-Mower-Control") != "1":
            abort(403)
        check_request_origin()


@process_control_bp.get("/info")
@result
def info():
    return process_control.info()


@process_control_bp.get("/status")
@result
def status():
    return process_control.status(request.args.get("id"))


@process_control_bp.post("/action")
@result
def action():
    data = request.get_json(silent=True) or {}
    if not managed_device.extra_settings_allowed(config.conf) and data.get(
        "action"
    ) in {"restart", "stop"}:
        return {
            "ok": False,
            "error": "manager_owned_setting",
            "message": "请通过多开管理器操作，或开启该实例的额外设置",
        }, 403
    return process_control.request_action(data.get("action"))
