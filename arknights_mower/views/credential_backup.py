"""Authenticated password-protected credential transfer."""

from datetime import datetime
from io import BytesIO

from flask import Blueprint, abort, current_app, request, send_file

from arknights_mower.utils import config_profiles as profiles
from arknights_mower.utils import credential_backup as backups
from arknights_mower.utils.config_backup import backup_lock
from arknights_mower.utils.credential_store import CredentialStoreError
from arknights_mower.utils.web_auth import check_request_origin, require_token

credential_backup_bp = Blueprint(
    "credential_backup", __name__, url_prefix="/credential-backup"
)


@credential_backup_bp.before_request
@require_token
def authorize():
    if request.headers.get("X-Mower-Settings") != "1":
        abort(403)
    check_request_origin()
    request.max_content_length = backups.MAX_BACKUP_BYTES + 65536
    request.max_form_memory_size = 65536
    request.max_form_parts = 4
    if request.content_length and request.content_length > request.max_content_length:
        abort(413)


@credential_backup_bp.after_request
def no_cache(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@credential_backup_bp.errorhandler(413)
def too_large(error):
    return {"ok": False, "message": "凭据备份文件不能超过 4 MiB"}, 413


@credential_backup_bp.errorhandler(backups.CredentialBackupError)
def invalid_backup(error):
    return {"ok": False, "message": str(error)}, 400


@credential_backup_bp.errorhandler(backups.CredentialBackupRecoveryError)
def recovery_incomplete(error):
    return {"ok": False, "message": str(error)}, 500


@credential_backup_bp.errorhandler(CredentialStoreError)
def unavailable_credentials(error):
    return {"ok": False, "message": str(error)}, 409


@credential_backup_bp.errorhandler(profiles.ProfileConflict)
def changed_configuration(error):
    return {"ok": False, "code": error.code, "message": str(error)}, 409


@credential_backup_bp.errorhandler(OSError)
def storage_error(error):
    return {
        "ok": False,
        "message": "凭据备份操作失败，请检查磁盘空间和目录权限",
    }, 500


def _upload():
    uploaded = request.files.get("backup")
    if uploaded is None:
        raise backups.CredentialBackupError("请选择凭据备份文件")
    raw = uploaded.stream.read(backups.MAX_BACKUP_BYTES + 1)
    if len(raw) > backups.MAX_BACKUP_BYTES:
        abort(413)
    return raw, request.form.get("password", "")


@credential_backup_bp.post("/export")
def export_credentials():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise backups.CredentialBackupError("请填写备份口令")
    raw = backups.export_credential_backup(data.get("password", ""))
    return send_file(
        BytesIO(raw),
        mimetype="application/octet-stream",
        as_attachment=True,
        download_name=f"mower-credentials-{datetime.now():%Y%m%d-%H%M%S}.mower-credentials",
        max_age=0,
    )


@credential_backup_bp.post("/preview")
def preview_credentials():
    raw, password = _upload()
    return {"ok": True, **backups.inspect_credential_backup(raw, password)}


def _activate_credentials():
    from arknights_mower.utils import config
    from arknights_mower.utils.configuration_secrets import (
        _FIELDS,
        read_conf_credentials,
        with_conf_secrets,
    )

    candidate = type(config.conf).model_validate(
        with_conf_secrets(
            config.conf.model_dump(), read_conf_credentials(config.conf_path)
        )
    )
    config.conf = config.conf.model_copy(
        update={
            field: getattr(candidate, field)
            for field in _FIELDS
            if getattr(config.conf, field) != getattr(candidate, field)
        }
    )


@credential_backup_bp.post("/import")
def import_credentials():
    locks = current_app.config.get("CONFIG_PROFILES_LOCKS", lambda: backup_lock)
    with backup_lock, locks():
        profiles.check_generation(
            request.headers.get("X-Mower-Config-Generation"), allow_legacy=False
        )
        busy = current_app.config.get("CONFIG_PROFILES_BUSY")
        if busy is None or busy():
            return {
                "ok": False,
                "message": "请先停止 Mower，并等待更新、连接检查和其他后台操作结束后再导入凭据",
            }, 409
        if request.form.get("confirmed") != "1":
            raise backups.CredentialBackupError("请先查看凭据备份内容并确认覆盖")
        raw, password = _upload()
        result = backups.import_credential_backup(
            raw,
            password,
            activate=current_app.config.get(
                "CREDENTIALS_ACTIVATED", _activate_credentials
            ),
        )
    return {
        "ok": True,
        **result,
        "message": "凭据已导入。排班和其他配置保持不变，访问 Token 沿用本机设置。",
    }
