"""Instance configuration and persistent-data ZIP download and restore endpoints."""

import sqlite3
from datetime import datetime
from io import BytesIO

import yaml
from flask import Blueprint, abort, current_app, request, send_file

from arknights_mower.utils import config_profiles as profiles
from arknights_mower.utils.config_backup import (
    BackupSizeError,
    LocalConfigError,
    backup_limit_label,
    backup_lock,
    export_archive,
    get_backup_limit_bytes,
)
from arknights_mower.utils.log import logger
from arknights_mower.utils.web_auth import check_request_origin, require_token

config_backup_bp = Blueprint("config_backup", __name__, url_prefix="/config-backup")


@config_backup_bp.errorhandler(413)
def upload_too_large(error):
    return {
        "ok": False,
        "message": f"备份文件不能超过 {backup_limit_label()}，可在运行日志的数据库管理中调整备份大小上限",
    }, 413


@config_backup_bp.before_request
@require_token
def authorize():
    if request.method == "POST":
        if request.headers.get("X-Mower-Settings") != "1":
            abort(403)
        check_request_origin()
        limit = get_backup_limit_bytes() + (
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
                "message": "请先停止 Mower，并等待更新任务、AI 回复和回收站上报结束后再导入档案",
            }, 409
        try:
            if request.mimetype == "multipart/form-data":
                uploaded = request.files.get("backup")
                if uploaded is None:
                    raise ValueError("缺少备份文件")
                raw = uploaded.stream.read(get_backup_limit_bytes() + 1)
            else:
                raw = request.stream.read(get_backup_limit_bytes() + 1)
            if len(raw) > get_backup_limit_bytes():
                abort(413)
            recovery = profiles.import_backup(
                raw,
                expected_generation=request.headers.get("X-Mower-Config-Generation"),
            )
            current_app.config.get("CONFIGURATION_ACTIVATED", lambda: None)()
        except profiles.ProfileConflict as exc:
            return {"ok": False, "code": exc.code, "message": str(exc)}, 409
        except LocalConfigError as exc:
            return {"ok": False, "message": str(exc)}, 409
        except BackupSizeError as exc:
            return {"ok": False, "message": str(exc)}, 400
        except (ValueError, TypeError, RecursionError, yaml.YAMLError):
            return {
                "ok": False,
                "message": "备份格式不正确或配置值无效，请选择包含 config 文件夹的 ZIP 备份（需要 conf.yml 和 plan.json）",
            }, 400
        except (OSError, sqlite3.Error):
            logger.exception("档案导入写入失败")
            return {
                "ok": False,
                "message": "档案写入失败，请检查磁盘空间和目录权限；导入前备份保存在 config-backups 目录",
            }, 500
        return {
            "ok": True,
            "message": "档案已导入。当前管理页面端口、访问令牌、网络代理、托盘及窗口尺寸保持不变。",
            "recovery_path": recovery,
        }
