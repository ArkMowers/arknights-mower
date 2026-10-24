"""Authenticated instance GUI preferences for browser and desktop clients."""

from flask import Blueprint, abort, request

from arknights_mower.utils.config import gui
from arknights_mower.utils.web_auth import preflight_allowed, require_token

gui_bp = Blueprint("gui", __name__, url_prefix="/gui")


@gui_bp.before_request
def authorize():
    if request.method == "OPTIONS":
        if not preflight_allowed():
            abort(403)
        return None
    return authorize_operation()


@require_token
def authorize_operation():
    return None


@gui_bp.get("/sidebar")
def sidebar():
    return {"sidebar": gui.load_sidebar()}


@gui_bp.put("/sidebar")
def save_sidebar():
    if request.content_length is not None and request.content_length > 1024 * 1024:
        abort(413)
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or "sidebar" not in data:
        return {"ok": False, "message": "缺少侧栏配置"}, 400
    try:
        return {"sidebar": gui.save_sidebar(data["sidebar"])}
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}, 400
    except (OSError, TimeoutError):
        return {"ok": False, "message": "侧栏配置保存失败，请稍后重试"}, 503


@gui_bp.get("/appearance")
def appearance():
    return {
        "software_version_display": gui.load_software_version_display(),
        "software_version_language": gui.load_software_version_language(),
        "task_settings_layout": gui.load_task_settings_layout(),
    }


@gui_bp.put("/appearance")
def save_appearance():
    if request.content_length is not None and request.content_length > 1024 * 1024:
        abort(413)
    data = request.get_json(silent=True)
    try:
        return gui.save_appearance(data)
    except ValueError as exc:
        return {"ok": False, "message": str(exc)}, 400
    except (OSError, TimeoutError):
        return {"ok": False, "message": "外观配置保存失败，请稍后重试"}, 503
