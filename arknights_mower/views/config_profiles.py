"""Named configuration management endpoints for the current Mower instance."""

import json
import sqlite3
from contextlib import nullcontext
from datetime import datetime
from io import BytesIO

import yaml
from flask import Blueprint, abort, current_app, request, send_file

from arknights_mower.utils import config_profiles as profiles
from arknights_mower.utils.config_backup import (
    MAX_BACKUP_BYTES,
    LocalConfigError,
    backup_lock,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.web_auth import (
    origin_allowed,
    preflight_allowed,
    require_token,
)

config_profiles_bp = Blueprint(
    "config_profiles", __name__, url_prefix="/config-profiles"
)


@config_profiles_bp.before_request
def authorize():
    if request.method == "OPTIONS":
        if not preflight_allowed():
            abort(403)
        return None
    return authorize_operation()


@require_token
def authorize_operation():
    if request.method in {"POST", "PATCH"}:
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and not origin_allowed(origin):
            abort(403)
        limit = MAX_BACKUP_BYTES + (
            65536 if request.mimetype == "multipart/form-data" else 0
        )
        if request.content_length and request.content_length > limit:
            abort(413)


@config_profiles_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _locks():
    factory = current_app.config.get("CONFIG_PROFILES_LOCKS")
    return factory() if factory is not None else nullcontext()


def _busy():
    return bool(current_app.config.get("CONFIG_PROFILES_BUSY", lambda: False)())


def _body():
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValueError("请求需要包含档案名称或选择项目")
    return value


def _execute(action, *, mutation=True):
    try:
        with backup_lock, _locks():
            if mutation:
                profiles.check_generation(
                    request.headers.get("X-Mower-Config-Generation"), allow_legacy=False
                )
                if _busy():
                    return {
                        "ok": False,
                        "message": "请先停止 Mower，并等待设备操作、更新任务、AI 回复和回收站上报结束",
                    }, 409
            return action()
    except profiles.ProfileConflict as exc:
        return {"ok": False, "code": exc.code, "message": str(exc)}, 409
    except LocalConfigError as exc:
        return {"ok": False, "message": str(exc)}, 409
    except (ValueError, TypeError, RecursionError, yaml.YAMLError) as exc:
        return {
            "ok": False,
            "message": str(exc)
            if isinstance(exc, ValueError)
            else "档案内容或选择项目无效",
        }, 400
    except (OSError, sqlite3.Error):
        logger.exception("档案写入失败")
        return {
            "ok": False,
            "message": "档案操作未完成，请检查磁盘空间和目录权限；恢复备份保存在 config-backups 目录",
        }, 500


@config_profiles_bp.get("")
def get_profiles():
    return _execute(
        lambda: {**profiles.list_profiles(), "busy": _busy()}, mutation=False
    )


@config_profiles_bp.get("/export")
def export_profile():
    def action():
        return send_file(
            BytesIO(profiles.export_current_archive()),
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"mower-config-{datetime.now():%Y%m%d-%H%M%S}.zip",
            max_age=0,
        )

    return _execute(action, mutation=False)


@config_profiles_bp.post("")
def create_profile():
    def action():
        body = _body()
        return profiles.create_profile(
            body.get("name"),
            body.get("inherit", []),
            expected_generation=request.headers.get("X-Mower-Config-Generation"),
        )

    return _execute(action)


@config_profiles_bp.post("/<identifier>/activate")
def activate_profile(identifier):
    def action():
        body = _body()
        return profiles.activate_profile(
            identifier,
            body.get("keep", []),
            expected_generation=request.headers.get("X-Mower-Config-Generation"),
        )

    return _execute(action)


@config_profiles_bp.patch("/<identifier>")
def rename_profile(identifier):
    def action():
        return profiles.rename_profile(
            identifier,
            _body().get("name"),
            expected_generation=request.headers.get("X-Mower-Config-Generation"),
        )

    return _execute(action)


@config_profiles_bp.post("/import")
def import_profile():
    def action():
        if request.mimetype != "multipart/form-data":
            raise ValueError("请选择 ZIP 档案备份")
        uploaded = request.files.get("backup")
        if uploaded is None:
            raise ValueError("缺少备份文件")
        raw = uploaded.stream.read(MAX_BACKUP_BYTES + 1)
        if len(raw) > MAX_BACKUP_BYTES:
            abort(413)
        try:
            keep = json.loads(request.form.get("keep", "[]"))
        except (ValueError, TypeError) as exc:
            raise ValueError("档案选择项目无效") from exc
        return profiles.import_profile(
            raw,
            request.form.get("name"),
            keep,
            expected_generation=request.headers.get("X-Mower-Config-Generation"),
        )

    return _execute(action)
