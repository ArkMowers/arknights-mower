"""Instance-owned relay settings, protected by the existing Web UI token."""

from flask import Blueprint, abort, current_app, request

from arknights_mower.utils.mower_relay import settings
from arknights_mower.utils.web_auth import require_token

relay_bp = Blueprint("relay", __name__, url_prefix="/relay")


@relay_bp.before_request
def authorize():
    if not getattr(current_app, "token", ""):
        abort(403)


@relay_bp.route("/settings", methods=["GET", "POST"])
@require_token
def relay_settings():
    client = current_app.extensions.get("mower_relay")
    if client is None:
        return {"ok": False, "message": "请在桌面实例中设置中转"}, 409
    if request.method == "POST":
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            abort(403)
        try:
            settings.save(request.get_json(silent=True), token_ready=client.token_ready)
        except ValueError as exc:
            return {"ok": False, "message": str(exc)}, 400
        except OSError:
            return {"ok": False, "message": "中转配置保存失败，请检查目录权限"}, 500
        client.start()
    return {
        "ok": True,
        **settings.public_settings(),
        **client.status(),
        "token_ready": client.token_ready,
    }
