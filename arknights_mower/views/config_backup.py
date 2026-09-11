"""Full configuration download and restore endpoints."""

import json
import sqlite3
from datetime import datetime
from io import BytesIO
from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, request, send_file

from arknights_mower.utils.config_backup import (
    MAX_BACKUP_BYTES,
    backup_lock,
    export_configuration,
    import_configuration,
    serialize_backup,
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
        if request.content_length and request.content_length > MAX_BACKUP_BYTES:
            abort(413)


@config_backup_bp.get("/export")
def export_backup():
    result = send_file(
        BytesIO(serialize_backup(export_configuration()).encode("utf-8")),
        mimetype="application/json",
        as_attachment=True,
        download_name=f"mower-config-{datetime.now():%Y%m%d-%H%M%S}.json",
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
            raw = request.stream.read(MAX_BACKUP_BYTES + 1)
            if len(raw) > MAX_BACKUP_BYTES:
                abort(413)
            backup = json.loads(raw)
            recovery = import_configuration(backup)
        except (ValueError, TypeError, RecursionError):
            # Validation errors may contain passwords/keys; never echo input.
            return {
                "ok": False,
                "message": "备份格式不正确、内容不完整或配置值无效，请选择 Mower 导出的完整配置 JSON 文件",
            }, 400
        except (OSError, sqlite3.Error):
            current_app.logger.exception("配置导入写入失败")
            return {
                "ok": False,
                "message": "配置写入失败，请检查磁盘空间和目录权限；导入前备份保存在 config-backups 目录",
            }, 500
        return {
            "ok": True,
            "message": "配置已导入，当前管理页面端口、访问令牌和网络代理保持不变。请刷新页面；窗口设置重启 Mower 后生效。",
            "recovery_path": recovery,
            "token": getattr(current_app, "token", ""),
        }
