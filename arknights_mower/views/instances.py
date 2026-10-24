"""Keep global instance management within the local desktop manager."""

from flask import Blueprint

from arknights_mower.utils.web_auth import require_token

instances_bp = Blueprint("instances", __name__, url_prefix="/instances")


@instances_bp.errorhandler(403)
def unauthorized(_error):
    return {"ok": False, "message": "实例管理需要有效的访问令牌"}, 403


@instances_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@instances_bp.route("", methods=["GET", "OPTIONS"])
@instances_bp.route("/actions", methods=["POST", "OPTIONS"])
@require_token
def reject_instance_management():
    return (
        {
            "ok": False,
            "code": "instance_management_unavailable",
            "message": "请在运行 Mower 的电脑上使用多开管理器管理实例",
        },
        403,
        {"Cache-Control": "no-store"},
    )
