"""Authenticated instance management through the shared manager controller."""

import json

import yaml
from flask import Blueprint, request
from werkzeug.exceptions import RequestEntityTooLarge

from arknights_mower.utils import update_runtime as runtime
from arknights_mower.utils.log import logger
from arknights_mower.utils.manager_instances import (
    InstanceController,
    InstanceTargetChangedError,
)
from arknights_mower.utils.path import get_path
from arknights_mower.utils.web_auth import (
    origin_allowed,
    preflight_allowed,
    require_token,
)

instances_bp = Blueprint("instances", __name__, url_prefix="/instances")
_MAX_REQUEST_BYTES = 1024 * 1024
_ARGUMENT_COUNTS = {
    "add": 3,
    "remove": 2,
    "rename": 3,
    "set_path": 3,
    "update_settings": 3,
    "update_all_settings": 2,
    "start": 2,
    "stop": 2,
    "start_all": 1,
    "stop_all": 1,
}
_ROW_ACTIONS = frozenset(
    ("remove", "rename", "set_path", "update_settings", "start", "stop")
)


@instances_bp.before_request
def authorize():
    if request.method == "OPTIONS":
        if preflight_allowed():
            return None
        return {"ok": False, "message": "实例管理预检请求来源或操作无效"}, 403
    return authorize_operation()


@instances_bp.errorhandler(403)
def unauthorized(_error):
    return {"ok": False, "message": "实例管理需要有效的访问令牌"}, 403


@require_token
def authorize_operation():
    if request.method == "POST":
        if request.headers.get("X-Mower-Settings") != "1":
            return {"ok": False, "message": "实例管理请求缺少确认标记"}, 403
        origin = request.headers.get("Origin")
        if origin and not origin_allowed(origin):
            return {"ok": False, "message": "实例管理请求必须来自当前网页"}, 403
        if request.content_length and request.content_length > _MAX_REQUEST_BYTES:
            return {"ok": False, "message": "实例管理请求过大"}, 413


@instances_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _execute(action):
    try:
        result = action(InstanceController(defer_load=True))
        if result is None:
            return {"ok": True}
        if isinstance(result, dict) and result.get("ok") is False:
            return result, 409
        return result
    except (InstanceTargetChangedError, runtime.LockBusyError) as exc:
        return {"ok": False, "message": str(exc)}, 409
    except RequestEntityTooLarge:
        return {"ok": False, "message": "实例管理请求过大"}, 413
    except (ValueError, TypeError, RecursionError, yaml.YAMLError) as exc:
        return {
            "ok": False,
            "message": str(exc) if isinstance(exc, ValueError) else "实例管理请求无效",
        }, 400
    except (OSError, runtime.InstanceScanError):
        logger.exception("实例管理操作未完成")
        return {
            "ok": False,
            "message": "无法读取或保存实例，请检查实例配置、运行状态和目录权限后重试",
        }, 503


def _identity(value):
    return (
        isinstance(value, dict)
        and set(value) == {"name", "path"}
        and all(isinstance(item, str) for item in value.values())
    )


def _arguments():
    raw = request.stream.read(_MAX_REQUEST_BYTES + 1)
    if len(raw) > _MAX_REQUEST_BYTES:
        raise RequestEntityTooLarge()
    try:
        body = json.loads(raw) if request.is_json else None
    except (ValueError, RecursionError):
        body = None
    if not isinstance(body, dict) or set(body) != {"action", "args"}:
        raise ValueError("实例管理请求需要包含操作和参数")
    action, args = body["action"], body["args"]
    if (
        not isinstance(action, str)
        or action not in _ARGUMENT_COUNTS
        or not isinstance(args, list)
        or len(args) != _ARGUMENT_COUNTS[action]
    ):
        raise ValueError("不支持的实例管理操作或参数")
    if action in _ROW_ACTIONS:
        if type(args[0]) is not int or args[0] < 0 or not _identity(args[-1]):
            raise ValueError("实例管理操作缺少有效的实例身份")
    else:
        targets = args[-1]
        if not isinstance(targets, list) or not all(map(_identity, targets)):
            raise ValueError("实例管理操作缺少有效的实例列表")
    return action, args


@instances_bp.get("")
def get_instances():
    return _execute(lambda controller: controller.get_instances())


@instances_bp.post("/actions")
def instance_action():
    def perform(controller):
        action, args = _arguments()
        operation = getattr(controller, action)
        if action == "stop_all":
            return operation(*args, last_directory=get_path("@app"))
        return operation(*args)

    return _execute(perform)
