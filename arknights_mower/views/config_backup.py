"""Configuration-directory ZIP download and restore endpoints."""

import sqlite3
from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse

import yaml
from flask import Blueprint, abort, current_app, request, send_file

from arknights_mower.utils.config_backup import (
    MAX_BACKUP_BYTES,
    LocalConfigError,
    backup_lock,
    export_archive,
    import_configuration,
)

config_backup_bp = Blueprint("config_backup", __name__, url_prefix="/config-backup")


@config_backup_bp.before_request
def authorize():
    if (
        hasattr(current_app, "token")
        and request.headers.get("token", "") != current_app.token
    ):
        abort(403)
    if request.method == "POST":
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)
        limit = MAX_BACKUP_BYTES + (
            65536 if request.mimetype == "multipart/form-data" else 0
        )
        if request.content_length and request.content_length > limit:
            abort(413)


@config_backup_bp.get("/export")
def export_backup():
    try:
        raw = export_archive()
    except LocalConfigError as exc:
        return {"ok": False, "message": str(exc)}, 409
    result = send_file(
        BytesIO(raw),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"mower-config-{datetime.now():%Y%m%d-%H%M%S}.zip",
        max_age=0,
    )
    result.headers["Cache-Control"] = "no-store"
    return result


@config_backup_bp.post("/import")
def import_backup():
    with current_app.config.get("CONFIG_BACKUP_MAINTENANCE_LOCK", backup_lock):
        if current_app.config["CONFIG_BACKUP_BUSY"]():
            return {
                "ok": False,
                "message": "请先停止 Mower，并等待更新任务结束后再导入配置",
            }, 409
        try:
            if request.mimetype == "multipart/form-data":
                uploaded = request.files.get("backup")
                if uploaded is None:
                    raise ValueError("缺少备份文件")
                raw = uploaded.stream.read(MAX_BACKUP_BYTES + 1)
            else:
                raw = request.stream.read(MAX_BACKUP_BYTES + 1)
            if len(raw) > MAX_BACKUP_BYTES:
                abort(413)
            recovery = import_configuration(raw)
        except LocalConfigError as exc:
            return {"ok": False, "message": str(exc)}, 409
        except (ValueError, TypeError, RecursionError, yaml.YAMLError):
            return {
                "ok": False,
                "message": "备份格式不正确或配置值无效，请选择包含 config 文件夹的 ZIP 备份（需要 conf.yml 和 plan.json）",
            }, 400
        except (OSError, sqlite3.Error):
            current_app.logger.exception("配置导入写入失败")
            return {
                "ok": False,
                "message": "配置写入失败，请检查磁盘空间和目录权限；导入前备份保存在 config-backups 目录",
            }, 500
        return {
            "ok": True,
            "message": "配置已导入。当前管理页面端口、访问令牌、网络代理、托盘及窗口尺寸保持不变。",
            "recovery_path": recovery,
        }
