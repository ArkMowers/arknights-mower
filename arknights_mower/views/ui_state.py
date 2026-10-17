from flask import Blueprint, current_app, request

from arknights_mower.utils import ui_state
from arknights_mower.views.software_update import result

ui_state_bp = Blueprint("ui_state", __name__, url_prefix="/ui-state")


@ui_state_bp.before_request
def authorize():
    if (
        hasattr(current_app, "token")
        and request.headers.get("token", "") != current_app.token
    ):
        from flask import abort

        abort(403)


@ui_state_bp.get("/log-layout")
@result
def log_layout():
    return ui_state.get_log_layout()


@ui_state_bp.post("/log-layout")
@result
def save_log_layout():
    return ui_state.save_log_layout(request.get_json(silent=True) or {})
